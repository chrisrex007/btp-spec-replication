"""Generate one candidate and evaluate it using direct local inference."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import re
import sys
from typing import Callable

from .artifacts import ArtifactPersistenceError, atomic_bytes, write_json
from .builder import build_candidate
from .candidate import CandidateSource
from .differential import (
    DifferentialResult,
    run_differential_case,
    write_results,
)
from .generator import generate_candidate
from .llm_client import InferenceSession
from .llm_runtime import logged_call
from .task import BenchmarkTask
from .test_generator import generate_tests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO_ROOT / "runs"


def _write_json(path: Path, value) -> None:
    write_json(path, value)


def _default_run_id(task_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{task_name}-{stamp}"


def _failure_payload(results: list[DifferentialResult]) -> list[dict]:
    return [result.to_dict() for result in results if not result.passed]


def _finalize_summary(run_dir: Path, summary: dict) -> dict:
    try:
        _write_json(run_dir / "summary.json", summary)
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
        summary["summary_persistence_error"] = error
        summary.setdefault("failed_stage", "persist_summary")
        summary["accuracy"] = None
        if isinstance(exc, KeyboardInterrupt):
            summary["interrupted"] = True
            summary.setdefault("interrupted_stage", "persist_summary")
        if summary["n_reference_failures"]:
            summary["status"] = "invalid_reference"
        elif summary.get("interrupted"):
            summary["status"] = "interrupted"
        elif summary["status"] == "completed":
            summary["status"] = "execution_failed"
        print(
            f"Could not persist summary for {summary['run_id']}: {error}; "
            f"run error: {summary.get('error')}",
            file=sys.stderr,
        )
        if isinstance(exc, KeyboardInterrupt):
            # A single interrupt must not prevent saving its own run summary.
            try:
                _write_json(run_dir / "summary.json", summary)
            except (Exception, KeyboardInterrupt) as retry_exc:
                print(
                    f"Could not persist interrupted summary: "
                    f"{type(retry_exc).__name__}: {retry_exc}",
                    file=sys.stderr,
                )
    return summary


def run_baseline(
    task: BenchmarkTask,
    *,
    test_count: int = 20,
    run_root: str | Path = DEFAULT_RUN_ROOT,
    run_id: str | None = None,
    seed: int = 42,
    candidate_generator: Callable[..., CandidateSource] = generate_candidate,
    tests_generator: Callable[..., list[str]] = generate_tests,
) -> dict:
    """Run one complete no-feedback baseline experiment.

    Failures in candidate generation, building, or test generation are persisted
    as run summaries rather than silently losing the experiment record.
    """

    if test_count <= 0:
        raise ValueError("test_count must be positive")

    specification = task.read_specification()
    selected_run_id = _default_run_id(task.name) if run_id is None else run_id
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", selected_run_id):
        raise ValueError("run ID must be a plain directory name starting with a letter or digit")
    root = Path(run_root).resolve()
    run_dir = (root / selected_run_id).resolve()
    if run_dir.parent != root:
        raise ValueError("run directory must remain inside run root")
    run_dir.mkdir(parents=True, exist_ok=False)

    candidate_dir = run_dir / "candidate"
    tests = []
    results = []
    execution_failures = Counter()
    execution_counts = Counter()
    stage = "persist_setup"
    failed_stage = None
    status = "completed"
    error = None
    interrupted = False
    interrupted_stage = None
    evaluation_started = False
    build = None
    recovery_errors = []

    def record_execution(role, result):
        execution_counts[role] += 1
        execution_failures[role] += not result.succeeded

    try:
        atomic_bytes(run_dir / "specification.txt", specification.encode("utf-8"))
        _write_json(run_dir / "task.json", task.to_dict())
        candidate_dir.mkdir()

        stage = "candidate_generation"
        if candidate_generator is generate_candidate or tests_generator is generate_tests:
            session = InferenceSession()
            call_fn = partial(logged_call, session=session)
            if candidate_generator is generate_candidate:
                candidate_generator = partial(generate_candidate, call_fn=call_fn)
            if tests_generator is generate_tests:
                tests_generator = partial(generate_tests, call_fn=call_fn)
        candidate = candidate_generator(
            specification=specification,
            input_format=task.input_format,
            run_dir=run_dir,
            target=task.name,
            seed=seed,
        )
        stage = "persist_candidate_metadata"
        _write_json(
            candidate_dir / "metadata.json",
            {
                "language": candidate.language,
                "filename": candidate.filename,
            },
        )
        stage = "build"
        build = build_candidate(candidate, candidate_dir)
        stage = "persist_build"
        _write_json(run_dir / "build.json", build.to_dict())
        if not build.success or build.run_command is None:
            status = "build_failed"
            failed_stage = "build"
            error = build.error
        else:
            stage = "test_generation"
            generated_tests = tests_generator(
                specification=specification,
                input_format=task.input_format,
                count=test_count,
                run_dir=run_dir,
                target=task.name,
                seed=seed,
            )
            if (not isinstance(generated_tests, list) or not generated_tests
                    or not all(isinstance(item, str) for item in generated_tests)):
                raise ValueError("test generation must produce a nonempty list of strings")
            for item in generated_tests:
                item.encode("utf-8")
            tests = generated_tests

            stage = "persist_tests"
            _write_json(run_dir / "tests.json", tests)
            evaluation_started = True
            stage = "persist_results"
            write_results(run_dir / "results.json", results)
            _write_json(run_dir / "failures.json", [])
            for index, test_input in enumerate(tests, 1):
                stage = "execution"
                result = run_differential_case(
                    task.reference_command,
                    build.run_command,
                    test_input,
                    output_dir=run_dir / "executions" / f"{index:06d}",
                    timeout_seconds=task.timeout_seconds,
                    reference_cwd=task.reference_cwd,
                    candidate_cwd=candidate_dir,
                    on_execution=record_execution,
                )
                results.append(result)
                stage = "persist_results"
                write_results(run_dir / "results.json", results)
                _write_json(run_dir / "failures.json", _failure_payload(results))
    except KeyboardInterrupt as exc:
        interrupted = True
        interrupted_stage = stage
        failed_stage = stage
        status = "interrupted"
        error = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        failed_stage = stage
        error = f"{type(exc).__name__}: {exc}"
        status = (
            "execution_failed" if isinstance(exc, ArtifactPersistenceError) else
            {"candidate_generation": "candidate_generation_failed",
             "build": "build_failed",
             "test_generation": "test_generation_failed"}.get(stage, "execution_failed")
        )

    # Recovery is persistence only; it never retries generation or execution.
    recovery_writes = []
    if failed_stage == "build" and build is None:
        recovery_writes.append(partial(
            _write_json, run_dir / "build.json", {"success": False, "error": error}
        ))
    if interrupted and evaluation_started:
        recovery_writes.extend([
            partial(write_results, run_dir / "results.json", results),
            partial(_write_json, run_dir / "failures.json", _failure_payload(results)),
        ])
    for persist in recovery_writes:
        try:
            persist()
        except (Exception, KeyboardInterrupt) as exc:
            if isinstance(exc, KeyboardInterrupt):
                interrupted = True
                if interrupted_stage is None:
                    interrupted_stage = "persist_recovery"
            recovery_error = f"{type(exc).__name__}: {exc}"
            recovery_errors.append(recovery_error)
            print(f"Could not persist recovery artifact: {recovery_error}", file=sys.stderr)

    n_total = len(results)
    n_pass = sum(result.passed for result in results)
    status_counts = Counter(result.status.value for result in results)
    n_reference_failures = execution_failures["reference"]
    n_candidate_failures = execution_failures["candidate"]
    n_valid = sum(result.reference.succeeded for result in results)
    status = ("invalid_reference" if n_reference_failures else
              "interrupted" if interrupted else status)
    accuracy = n_pass / n_total if n_total and status == "completed" else None

    summary = {
        "run_id": selected_run_id,
        "task": task.name,
        "status": status,
        "n_requested_tests": test_count,
        "n_unique_tests": len(tests),
        "n_total": n_total,
        "n_valid": n_valid,
        "n_reference_failures": n_reference_failures,
        "n_candidate_failures": n_candidate_failures,
        "n_reference_executions": execution_counts["reference"],
        "n_candidate_executions": execution_counts["candidate"],
        "n_pass": n_pass,
        "n_fail": n_valid - n_pass,
        "accuracy": accuracy,
        "status_counts": dict(sorted(status_counts.items())),
    }
    if failed_stage is not None:
        summary["failed_stage"] = failed_stage
        summary["error"] = error
    if interrupted:
        summary["interrupted"] = True
        summary["interrupted_stage"] = interrupted_stage
    if recovery_errors:
        summary["recovery_persistence_errors"] = recovery_errors
    return _finalize_summary(run_dir, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_config")
    parser.add_argument("--tests", type=int, default=20)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        task = BenchmarkTask.from_json(args.task_config)
        summary = run_baseline(task, test_count=args.tests, run_root=args.run_root,
                               run_id=args.run_id, seed=args.seed)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=True))
    if summary.get("interrupted"):
        return 130
    return 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
