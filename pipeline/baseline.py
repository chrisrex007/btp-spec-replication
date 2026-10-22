"""Generate one candidate and evaluate it using direct local inference."""
from __future__ import annotations

import argparse
from functools import partial
import json
from pathlib import Path
import re
import sys

from .artifacts import atomic_bytes, atomic_json, implementation_digest, utc_now
from .builder import build_candidate
from .differential import run_differential_suite, summarize_results, write_results
from .generator import generate_candidate
from .llm_runtime import logged_call
from .offline_runtime import (
    ContextBudgetExceeded, InferenceSession, RuntimeConfig,
    add_runtime_arguments, config_from_args, default_config,
)
from .task import BenchmarkTask
from .test_generator import generate_tests


DEFAULT_RUN_ROOT = Path(__file__).resolve().parents[1] / "runs"


def run_baseline(task: BenchmarkTask, *, test_count: int = 20,
                 run_root: str | Path = DEFAULT_RUN_ROOT, run_id: str | None = None,
                 runtime_config: RuntimeConfig | None = None) -> dict:
    config = runtime_config or default_config()
    config.validate()
    if type(test_count) is not int or test_count <= 0:
        raise ValueError("test_count must be a positive integer")
    selected_id = run_id or task.name + "-" + utc_now().replace(":", "").replace(".", "")
    if selected_id in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._+-]+", selected_id):
        raise ValueError("run_id must be a plain directory identifier")
    root = Path(run_root).expanduser().resolve() / selected_id
    root.mkdir(parents=True, exist_ok=False)
    summary = {"run_id": selected_id, "task": task.name, "accuracy": None}
    stage = "setup"
    try:
        specification = task.read_specification()
        atomic_bytes(root / "specification.txt", specification.encode("utf-8"))
        atomic_json(root / "task.json", task.to_dict())
        session = InferenceSession(config)
        atomic_json(root / "metadata.json", {
            "schema_version": 2, "runtime": session.identity,
            "implementation_sha256": implementation_digest(), "created_at": utc_now(),
        })
        call = partial(logged_call, session=session)
        stage = "candidate_generation"
        candidate = generate_candidate(
            specification=specification, input_format=task.input_format,
            run_dir=root, target=task.name, seed=config.seed,
            temperature=config.temperature, max_tokens=config.max_tokens, call_fn=call,
        )
        candidate_dir = root / "candidate"
        atomic_json(candidate_dir / "metadata.json", candidate.to_dict())
        stage = "build"
        build = build_candidate(candidate, candidate_dir)
        atomic_json(root / "build.json", build.to_dict())
        if not build.success or build.run_command is None:
            summary.update(status="build_failed", error=build.error or build.build_stderr)
        else:
            stage = "test_generation"
            tests = generate_tests(
                specification=specification, input_format=task.input_format, count=test_count,
                run_dir=root, target=task.name, seed=config.seed + 100_000,
                temperature=config.test_temperature, max_tokens=config.max_tokens, call_fn=call,
            )
            atomic_json(root / "tests.json", tests)
            stage = "evaluation"
            results = run_differential_suite(
                task.reference_command, build.run_command, tests,
                timeout_seconds=task.timeout_seconds, reference_cwd=task.reference_cwd,
                candidate_cwd=candidate_dir,
            )
            write_results(root / "results.json", results)
            atomic_json(root / "failures.json", [r.to_dict() for r in results if not r.passed])
            summary.update(summarize_results(results), n_requested_tests=test_count,
                           n_unique_tests=len(tests))
    except KeyboardInterrupt:
        summary.update(status="interrupted", stage=stage)
    except Exception as exc:
        status = "context_budget_exceeded" if isinstance(exc, ContextBudgetExceeded) else stage + "_failed"
        summary.update(status=status, stage=stage, error=f"{type(exc).__name__}: {exc}")
    atomic_json(root / "summary.json", summary)
    return summary


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
