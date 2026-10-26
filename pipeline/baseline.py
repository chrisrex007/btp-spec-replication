"""Generate one candidate and evaluate it using direct local inference."""
from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
import re
from typing import Callable

from .artifacts import write_json
from .builder import build_candidate
from .candidate import CandidateSource
from .differential import (
    DifferentialResult,
    run_differential_case,
    write_results,
)
from .generator import generate_candidate
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
    _write_json(run_dir / "summary.json", summary)
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

    (run_dir / "specification.txt").write_text(specification, encoding="utf-8")
    _write_json(run_dir / "task.json", task.to_dict())

    candidate_dir = run_dir / "candidate"
    candidate_dir.mkdir()

    try:
        candidate = candidate_generator(
            specification=specification,
            input_format=task.input_format,
            run_dir=run_dir,
            target=task.name,
            seed=seed,
        )
    except Exception as exc:
        return _finalize_summary(
            run_dir,
            {
                "run_id": selected_run_id,
                "task": task.name,
                "status": "candidate_generation_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "accuracy": None,
            },
        )

    try:
        _write_json(
            candidate_dir / "metadata.json",
            {
                "language": candidate.language,
                "filename": candidate.filename,
            },
        )

        build = build_candidate(candidate, candidate_dir)
        _write_json(run_dir / "build.json", build.to_dict())
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        _write_json(run_dir / "build.json", {"success": False, "error": error})
        return _finalize_summary(run_dir, {
            "run_id": selected_run_id, "task": task.name,
            "status": "build_failed", "error": error, "accuracy": None,
        })
    if not build.success or build.run_command is None:
        return _finalize_summary(
            run_dir,
            {
                "run_id": selected_run_id,
                "task": task.name,
                "status": "build_failed",
                "error": build.error,
                "accuracy": None,
            },
        )

    try:
        tests = tests_generator(
            specification=specification,
            input_format=task.input_format,
            count=test_count,
            run_dir=run_dir,
            target=task.name,
            seed=seed,
        )
        if not tests or not all(isinstance(item, str) for item in tests):
            raise ValueError("test generation must produce a nonempty list of strings")
        for item in tests:
            item.encode("utf-8")
    except Exception as exc:
        return _finalize_summary(
            run_dir,
            {
                "run_id": selected_run_id,
                "task": task.name,
                "status": "test_generation_failed",
                "error": f"{type(exc).__name__}: {exc}",
                "accuracy": None,
            },
        )

    _write_json(run_dir / "tests.json", tests)

    results = []
    execution_failures = Counter()
    execution_counts = Counter()

    def record_execution(role, result):
        execution_counts[role] += 1
        execution_failures[role] += not result.succeeded

    execution_error = None
    write_results(run_dir / "results.json", results)
    _write_json(run_dir / "failures.json", [])
    try:
        for index, test_input in enumerate(tests, 1):
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
            write_results(run_dir / "results.json", results)
            _write_json(run_dir / "failures.json", _failure_payload(results))
    except Exception as exc:
        execution_error = f"{type(exc).__name__}: {exc}"

    n_total = len(results)
    n_pass = sum(result.passed for result in results)
    status_counts = Counter(result.status.value for result in results)
    n_reference_failures = execution_failures["reference"]
    n_candidate_failures = execution_failures["candidate"]
    n_valid = sum(result.reference.succeeded for result in results)
    accuracy = (
        n_pass / n_total
        if n_total and not n_reference_failures and execution_error is None else None
    )

    summary = {
        "run_id": selected_run_id,
        "task": task.name,
        "status": ("invalid_reference" if n_reference_failures else
                   "execution_failed" if execution_error else "completed"),
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
    if execution_error is not None:
        summary["error"] = execution_error
    return _finalize_summary(run_dir, summary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_config")
    parser.add_argument("--tests", type=int, default=20)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--run-id")
    add_runtime_arguments(parser)
    args = parser.parse_args()
    try:
        config = config_from_args(args)
        task = BenchmarkTask.from_json(args.task_config)
        summary = run_baseline(task, test_count=args.tests, run_root=args.run_root,
                               run_id=args.run_id, runtime_config=config)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=True))
    return 130 if summary["status"] == "interrupted" else 0 if summary["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
