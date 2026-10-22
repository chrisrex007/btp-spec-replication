"""One-shot baseline replication run.

The one-shot workflow is:
specification -> candidate generation -> build -> test generation ->
differential execution -> persisted baseline score.

The candidate is generated once and evaluated without modification.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Callable

from .builder import build_candidate
from .candidate import CandidateSource
from .differential import (
    ComparisonStatus,
    DifferentialResult,
    run_differential_suite,
    write_results,
)
from .generator import generate_candidate
from .llm_client import redact_diagnostic
from .task import BenchmarkTask
from .test_generator import generate_tests


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUN_ROOT = REPO_ROOT / "runs"


def _write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _default_run_id(task_name: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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
    selected_run_id = run_id or _default_run_id(task.name)
    run_dir = Path(run_root).resolve() / selected_run_id
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
                "error": redact_diagnostic(f"{type(exc).__name__}: {exc}"),
                "accuracy": None,
            },
        )

    _write_json(
        candidate_dir / "metadata.json",
        {
            "language": candidate.language,
            "filename": candidate.filename,
        },
    )

    build = build_candidate(candidate, candidate_dir)
    _write_json(run_dir / "build.json", build.to_dict())
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
    except Exception as exc:
        return _finalize_summary(
            run_dir,
            {
                "run_id": selected_run_id,
                "task": task.name,
                "status": "test_generation_failed",
                "error": redact_diagnostic(f"{type(exc).__name__}: {exc}"),
                "accuracy": None,
            },
        )

    _write_json(run_dir / "tests.json", tests)

    results = run_differential_suite(
        task.reference_command,
        build.run_command,
        tests,
        timeout_seconds=task.timeout_seconds,
        reference_cwd=task.reference_cwd,
        candidate_cwd=candidate_dir,
    )
    write_results(run_dir / "results.json", results)
    _write_json(run_dir / "failures.json", _failure_payload(results))

    n_total = len(results)
    n_pass = sum(result.passed for result in results)
    status_counts = Counter(result.status.value for result in results)
    n_reference_failures = sum(
        result.status in {ComparisonStatus.REFERENCE_ERROR, ComparisonStatus.REFERENCE_TIMEOUT}
        for result in results
    )
    n_valid = n_total - n_reference_failures
    accuracy = n_pass / n_total if n_total and not n_reference_failures else None

    summary = {
        "run_id": selected_run_id,
        "task": task.name,
        "status": "invalid_reference" if n_reference_failures else "completed",
        "n_requested_tests": test_count,
        "n_unique_tests": len(tests),
        "n_total": n_total,
        "n_valid": n_valid,
        "n_reference_failures": n_reference_failures,
        "n_pass": n_pass,
        "n_fail": n_valid - n_pass,
        "accuracy": accuracy,
        "status_counts": dict(sorted(status_counts.items())),
    }
    return _finalize_summary(run_dir, summary)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a one-shot specification-replication baseline."
    )
    parser.add_argument("task_config", help="Path to a benchmark task JSON file.")
    parser.add_argument(
        "--tests",
        type=int,
        default=20,
        help="Number of testcases to request from the LLM (default: 20).",
    )
    parser.add_argument(
        "--run-root",
        default=str(DEFAULT_RUN_ROOT),
        help="Directory under which run folders are created.",
    )
    parser.add_argument("--run-id", default=None, help="Optional explicit run ID.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    task = BenchmarkTask.from_json(args.task_config)
    summary = run_baseline(
        task,
        test_count=args.tests,
        run_root=args.run_root,
        run_id=args.run_id,
        seed=args.seed,
    )
    print(json.dumps(summary, ensure_ascii=True))
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
