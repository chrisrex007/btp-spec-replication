"""Resumable batched offline generation and repair with one vLLM engine."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
from typing import Callable

from .builder import build_candidate
from .candidate import CandidateSource
from .differential import run_differential_suite
from .generator import CANDIDATE_SCHEMA, candidate_messages, parse_candidate_response
from .offline_runtime import InferenceOutput, InferenceRequest, OfflineVLLM
from .repair import repair_messages
from .feedback import RawFeedbackStrategy
from .task import BenchmarkTask
from .test_generator import parse_tests_response, test_generation_request


DEFAULT_RESULTS_ROOT = Path.home() / "btp-results"
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_STOP_REQUESTED = False


@dataclass(frozen=True)
class BatchConfig:
    experiment_id: str
    output_root: Path = DEFAULT_RESULTS_ROOT
    model: str = "Qwen/Qwen2.5-7B-Instruct"
    dtype: str = "half"
    tensor_parallel_size: int = 2
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.90
    max_num_seqs: int = 32
    test_count: int = 20
    max_repair_iterations: int = 2
    feedback_cases: int = 12
    workers: int = 4
    seed: int = 42
    resume: bool = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _round_dir(run_dir: Path, iteration: int) -> Path:
    return run_dir / "iterations" / f"{iteration:03d}"


def _response_path(run_dir: Path, iteration: int, step: str) -> Path:
    return run_dir / "inference" / f"iteration-{iteration:03d}-{step}.json"


def _save_state(run_dir: Path, state: dict) -> None:
    state["updated_at"] = _utc_now()
    _atomic_json(run_dir / "state.json", state)


def _terminal(state: dict) -> bool:
    return state["stage"] in {"completed", "failed"}


def _mark_failed(run_dir: Path, state: dict, status: str, error: str) -> None:
    state["stage"] = "failed"
    state["status"] = status
    state["error"] = error
    _atomic_json(run_dir / "summary.json", {
        "task": state["task"],
        "status": status,
        "iteration": state["iteration"],
        "error": error,
    })
    _save_state(run_dir, state)


def _write_inference(
    run_dir: Path,
    request: InferenceRequest,
    output: InferenceOutput,
    *,
    model: str,
    batch_size: int,
) -> None:
    record = {
        "timestamp": _utc_now(),
        "task": request.task,
        "step": request.step,
        "iteration": request.iteration,
        "model": model,
        "seed": request.seed,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "schema": request.schema,
        "system_prompt": request.system_prompt,
        "user_prompt": request.user_prompt,
        "response": output.response,
        "latency_s": output.latency_s,
        "batch_size": batch_size,
        "prompt_tokens": output.prompt_tokens,
        "completion_tokens": output.completion_tokens,
        "batch_latency_s": output.batch_latency_s,
    }
    _atomic_json(_response_path(run_dir, request.iteration, request.step), record)
    _append_jsonl(run_dir / "inference.jsonl", record)


def _request_for(
    task: BenchmarkTask,
    state: dict,
    stage: str,
    *,
    test_count: int,
    seed: int,
    feedback_cases: int,
) -> InferenceRequest:
    spec = task.read_specification()
    iteration = state["iteration"]
    if stage == "candidate_request":
        system, user = candidate_messages(specification=spec, input_format=task.input_format)
        return InferenceRequest(task.name, "initial_code_generation", 0, system, user,
                                CANDIDATE_SCHEMA, 0.2, 4096, seed)
    if stage == "tests_request":
        system, user, schema = test_generation_request(
            specification=spec, input_format=task.input_format, count=test_count
        )
        return InferenceRequest(task.name, "test_generation", 0, system, user,
                                schema, 0.6, 4096, seed + 100_000)
    if stage == "repair_request":
        round_dir = _round_dir(Path(state["run_dir"]), iteration)
        candidate_data = json.loads((round_dir / "candidate" / "metadata.json").read_text(encoding="utf-8"))
        candidate_path = round_dir / "candidate" / candidate_data["filename"]
        candidate = CandidateSource(
            language=candidate_data["language"],
            filename=candidate_data["filename"],
            source=candidate_path.read_text(encoding="utf-8"),
        )
        failures = json.loads((round_dir / "failures.json").read_text(encoding="utf-8"))
        feedback = RawFeedbackStrategy().prepare(failures, feedback_cases)
        system, user, schema = repair_messages(
            specification=spec,
            input_format=task.input_format,
            candidate=candidate,
            failures=feedback[:feedback_cases],
        )
        next_iteration = iteration + 1
        return InferenceRequest(task.name, "candidate_repair", next_iteration, system, user,
                                schema, 0.2, 4096, seed + next_iteration)
    raise ValueError(f"unsupported inference stage: {stage}")


def _execute_batch(
    tasks_by_name: dict[str, BenchmarkTask],
    states: list[dict],
    stage: str,
    runtime,
    config: BatchConfig,
    *,
    test_count: int,
    feedback_cases: int,
) -> None:
    next_stage = {
        "candidate_request": "candidate_response",
        "tests_request": "tests_response",
        "repair_request": "repair_response",
    }[stage]
    pending = []
    for state in states:
        run_dir = Path(state["run_dir"])
        try:
            request = _request_for(tasks_by_name[state["task"]], state, stage,
                                   test_count=test_count, seed=config.seed, feedback_cases=feedback_cases)
            path = _response_path(run_dir, request.iteration, request.step)
            if path.exists():
                record = json.loads(path.read_text(encoding="utf-8"))
                expected = {"task": request.task, "step": request.step, "iteration": request.iteration,
                            "system_prompt": request.system_prompt, "user_prompt": request.user_prompt,
                            "schema": request.schema, "model": config.model, "seed": request.seed,
                            "temperature": request.temperature, "max_tokens": request.max_tokens}
                if any(record.get(k) != v for k, v in expected.items()) or not isinstance(record.get("response"), str):
                    raise ValueError("inference checkpoint does not match request")
                state["stage"] = next_stage
                _save_state(run_dir, state)
            else:
                pending.append((state, request))
        except Exception as exc:
            _mark_failed(run_dir, state, "request_failed", f"{type(exc).__name__}: {exc}")
    if not pending:
        return
    # Engine failures propagate: a later job may resume pending requests.
    outputs = runtime.generate_batch([request for _, request in pending])
    if len(outputs) != len(pending):
        raise RuntimeError("offline runtime returned a different number of outputs than requests")
    for (state, request), output in zip(pending, outputs):
        run_dir = Path(state["run_dir"])
        _write_inference(run_dir, request, output, model=config.model, batch_size=len(pending))
        state["stage"] = next_stage
        _save_state(run_dir, state)


def _consume_candidate_response(run_dir: Path, state: dict, *, repair: bool) -> None:
    next_iteration = state["iteration"] + 1 if repair else 0
    step = "candidate_repair" if repair else "initial_code_generation"
    response = json.loads(_response_path(run_dir, next_iteration, step).read_text(encoding="utf-8"))["response"]
    try:
        candidate = parse_candidate_response(response)
    except Exception as exc:
        _mark_failed(run_dir, state, "candidate_parse_failed", f"{type(exc).__name__}: {exc}")
        return

    round_dir = _round_dir(run_dir, next_iteration)
    candidate_dir = round_dir / "candidate"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    (candidate_dir / candidate.filename).write_text(candidate.source, encoding="utf-8")
    _atomic_json(candidate_dir / "metadata.json", {
        "language": candidate.language,
        "filename": candidate.filename,
    })
    build = build_candidate(candidate, candidate_dir)
    _atomic_json(round_dir / "build.json", build.to_dict())
    if not build.success or build.run_command is None:
        _mark_failed(run_dir, state, "build_failed", build.error or build.build_stderr)
        return

    if repair:
        state["iteration"] = next_iteration
        state["stage"] = "evaluate"
    else:
        state["iteration"] = 0
        state["stage"] = "tests_request"
    _save_state(run_dir, state)


def _consume_tests_response(run_dir: Path, state: dict) -> None:
    record = json.loads(_response_path(run_dir, 0, "test_generation").read_text(encoding="utf-8"))
    try:
        tests = parse_tests_response(record["response"])
    except Exception as exc:
        _mark_failed(run_dir, state, "test_generation_failed", f"{type(exc).__name__}: {exc}")
        return
    _atomic_json(run_dir / "tests.json", tests)
    state["stage"] = "evaluate"
    _save_state(run_dir, state)


def _evaluate_one(task: BenchmarkTask, run_dir: Path, state: dict, max_repair_iterations: int) -> None:
    iteration = state["iteration"]
    round_dir = _round_dir(run_dir, iteration)
    try:
        build = json.loads((round_dir / "build.json").read_text(encoding="utf-8"))
        tests = json.loads((run_dir / "tests.json").read_text(encoding="utf-8"))
        if not build["success"] or not build["run_command"]:
            raise RuntimeError("candidate has no runnable build")
        results = run_differential_suite(
            task.reference_command,
            build["run_command"],
            tests,
            timeout_seconds=task.timeout_seconds,
            reference_cwd=task.reference_cwd,
            candidate_cwd=round_dir / "candidate",
        )
        payload = [result.to_dict() for result in results]
        failures = [item for item in payload if not item["passed"]]
        _atomic_json(round_dir / "results.json", payload)
        _atomic_json(round_dir / "failures.json", failures)
        passing = len(results) - len(failures)
        n_reference_error = sum(item["status"] in {"reference_error", "reference_timeout"} for item in payload)
        n_valid = len(results) - n_reference_error
        accuracy = passing / n_valid if n_valid else None
        round_summary = {
            "task": task.name,
            "iteration": iteration,
            "status": "completed",
            "n_total": len(results),
            "n_pass": passing,
            "n_valid": n_valid,
            "n_reference_error": n_reference_error,
            "n_fail": len(failures),
            "accuracy": accuracy,
            "status_counts": dict(sorted(Counter(item["status"] for item in payload).items())),
        }
        _atomic_json(round_dir / "summary.json", round_summary)
        state["latest_summary"] = round_summary
        if n_reference_error:
            _mark_failed(run_dir, state, "reference_invalid", "Reference execution failed on development pool")
            return
        if RawFeedbackStrategy().prepare(failures, 1) and iteration < max_repair_iterations:
            state["stage"] = "repair_request"
        else:
            state["stage"] = "completed"
            _atomic_json(run_dir / "summary.json", round_summary)
        _save_state(run_dir, state)
    except Exception as exc:
        _mark_failed(run_dir, state, "evaluation_failed", f"{type(exc).__name__}: {exc}")


def _progress_summary(experiment_dir: Path, states: list[dict]) -> dict:
    status_counts = Counter(state["stage"] for state in states)
    summary = {
        "experiment_id": experiment_dir.name,
        "updated_at": _utc_now(),
        "n_tasks": len(states),
        "n_terminal": sum(_terminal(state) for state in states),
        "n_failed": sum(state["stage"] == "failed" for state in states),
        "stages": dict(sorted(status_counts.items())),
        "tasks": {
            state["task"]: {
                "stage": state["stage"],
                "iteration": state["iteration"],
                "latest_summary": state.get("latest_summary"),
                "error": state.get("error"),
            }
            for state in states
        },
    }
    _atomic_json(experiment_dir / "summary.json", summary)
    return summary


def _initialize_experiment(
    tasks: list[BenchmarkTask], config: BatchConfig
) -> tuple[Path, list[dict]]:
    if config.experiment_id in {".", ".."} or not _ID_RE.fullmatch(config.experiment_id):
        raise ValueError("experiment_id may contain only letters, digits, '.', '_' or '-'")
    if not tasks:
        raise ValueError("at least one benchmark task is required")
    names = [task.name for task in tasks]
    if len(names) != len(set(names)):
        raise ValueError("task names in one batch must be unique")
    for name in ("test_count", "workers", "feedback_cases", "tensor_parallel_size", "max_model_len", "max_num_seqs"):
        value = getattr(config, name)
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if type(config.max_repair_iterations) is not int or config.max_repair_iterations < 0:
        raise ValueError("max_repair_iterations must be a nonnegative integer")
    if not math.isfinite(config.gpu_memory_utilization) or not 0 < config.gpu_memory_utilization <= 1:
        raise ValueError("gpu_memory_utilization must be finite and in (0, 1]")
    if not config.model.strip() or type(config.seed) is not int:
        raise ValueError("model must be nonempty and seed must be an integer")
    for task in tasks:
        if task.name in {".", ".."} or not _ID_RE.fullmatch(task.name):
            raise ValueError("task names must be safe directory identifiers")
        if not math.isfinite(task.timeout_seconds) or task.timeout_seconds <= 0:
            raise ValueError("task timeout must be positive and finite")

    experiment_dir = config.output_root.expanduser().resolve() / config.experiment_id
    fingerprint_payload = {
        "implementation_sha256": _sha256("".join(
            str(path.relative_to(Path(__file__).parent)) + ":" + _sha256(path.read_text(encoding="utf-8"))
            for path in sorted(Path(__file__).parent.rglob("*"))
            if path.suffix in {".py", ".txt"}
        )),
        "model": config.model,
        "dtype": config.dtype,
        "tensor_parallel_size": config.tensor_parallel_size,
        "test_count": config.test_count,
        "max_repair_iterations": config.max_repair_iterations,
        "max_model_len": config.max_model_len,
        "gpu_memory_utilization": config.gpu_memory_utilization,
        "max_num_seqs": config.max_num_seqs,
        "feedback_cases": config.feedback_cases,
        "seed": config.seed,
        "tasks": [
            {
                "name": task.name,
                "specification_sha256": _sha256(task.read_specification()),
                "reference_command": list(task.reference_command),
                "reference_cwd": str(task.reference_cwd),
                "input_format": task.input_format,
                "timeout_seconds": task.timeout_seconds,
            }
            for task in tasks
        ],
    }
    fingerprint = _sha256(json.dumps(fingerprint_payload, sort_keys=True))
    metadata_path = experiment_dir / "metadata.json"
    if experiment_dir.exists():
        if not config.resume:
            raise FileExistsError(f"{experiment_dir} exists; pass --resume to continue it")
        if not metadata_path.exists():
            raise ValueError("cannot resume: experiment metadata is missing")
        existing_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if existing_metadata.get("fingerprint") != fingerprint:
            raise ValueError("cannot resume: manifest or run configuration differs from saved metadata")
    else:
        if config.resume:
            raise FileNotFoundError(f"cannot resume; experiment does not exist: {experiment_dir}")
        experiment_dir.mkdir(parents=True)
        metadata = {
            "experiment_id": config.experiment_id,
            "created_at": _utc_now(),
            "git_revision": _git_revision(),
            "model": config.model,
            "dtype": config.dtype,
            "tensor_parallel_size": config.tensor_parallel_size,
            "max_model_len": config.max_model_len,
            "gpu_memory_utilization": config.gpu_memory_utilization,
            "max_num_seqs": config.max_num_seqs,
            "test_count": config.test_count,
            "max_repair_iterations": config.max_repair_iterations,
            "feedback_cases": config.feedback_cases,
            "seed": config.seed,
            "slurm_job_id": os.getenv("SLURM_JOB_ID"),
            "slurm_partition": os.getenv("SLURM_JOB_PARTITION"),
            "slurm_account": os.getenv("SLURM_JOB_ACCOUNT") or os.getenv("BTP_SLURM_ACCOUNT"),
            "tasks": fingerprint_payload["tasks"],
            "fingerprint": fingerprint,
        }
        _atomic_json(metadata_path, metadata)

    states = []
    for task in tasks:
        run_dir = experiment_dir / task.name
        run_dir.mkdir(parents=True, exist_ok=True)
        state_path = run_dir / "state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            valid_stages = {"candidate_request", "candidate_response", "tests_request", "tests_response",
                            "repair_request", "repair_response", "evaluate", "completed", "failed"}
            if (state.get("task") != task.name or state.get("run_dir") != str(run_dir)
                    or state.get("stage") not in valid_stages
                    or type(state.get("iteration")) is not int
                    or not 0 <= state["iteration"] <= config.max_repair_iterations):
                raise ValueError(f"invalid checkpoint for task {task.name}")
        else:
            state = {
                "task": task.name,
                "run_dir": str(run_dir),
                "stage": "candidate_request",
                "iteration": 0,
                "created_at": _utc_now(),
            }
            _save_state(run_dir, state)
            _atomic_json(run_dir / "task.json", task.to_dict())
            (run_dir / "specification.txt").write_text(task.read_specification(), encoding="utf-8")
        states.append(state)
    return experiment_dir, states


def run_offline_batch(
    tasks: list[BenchmarkTask],
    *,
    config: BatchConfig,
    runtime=None,
    runtime_factory: Callable[[], object] | None = None,
    should_stop: Callable[[], bool] = lambda: False,
) -> dict:
    """Run/resume a multi-task generate-test-repair experiment."""

    experiment_dir, states = _initialize_experiment(tasks, config)
    tasks_by_name = {task.name: task for task in tasks}
    _append_jsonl(experiment_dir / "attempts.jsonl", {
        "started_at": _utc_now(),
        "slurm_job_id": os.getenv("SLURM_JOB_ID"),
        "slurm_partition": os.getenv("SLURM_JOB_PARTITION"),
        "slurm_account": os.getenv("SLURM_JOB_ACCOUNT") or os.getenv("BTP_SLURM_ACCOUNT"),
        "slurm_cpus_per_task": os.getenv("SLURM_CPUS_PER_TASK"),
        "slurm_job_gpus": os.getenv("SLURM_JOB_GPUS"),
        "resume": config.resume,
    })
    if all(_terminal(state) for state in states):
        summary = _progress_summary(experiment_dir, states)
        summary["status"] = "completed_with_failures" if summary["n_failed"] else "completed"
        _atomic_json(experiment_dir / "summary.json", summary)
        _append_jsonl(experiment_dir / "attempts.jsonl", {
            "finished_at": _utc_now(), "status": summary["status"]
        })
        return summary
    if runtime is None:
        if runtime_factory is None:
            raise ValueError("provide runtime or runtime_factory for pending tasks")
        runtime = runtime_factory()

    while not all(_terminal(state) for state in states):
        progress = False
        for stage in ("candidate_request", "tests_request", "repair_request"):
            pending = [state for state in states if state["stage"] == stage]
            if pending:
                _execute_batch(
                    tasks_by_name,
                    pending,
                    stage,
                    runtime,
                    config,
                    test_count=config.test_count,
                    feedback_cases=config.feedback_cases,
                )
                progress = True
                if should_stop():
                    break
        if should_stop():
            break

        response_states = [
            state for state in states
            if state["stage"] in {"candidate_response", "tests_response", "repair_response"}
        ]
        if response_states:
            def consume(state: dict) -> None:
                run_dir = Path(state["run_dir"])
                try:
                    if state["stage"] == "candidate_response":
                        _consume_candidate_response(run_dir, state, repair=False)
                    elif state["stage"] == "tests_response":
                        _consume_tests_response(run_dir, state)
                    else:
                        _consume_candidate_response(run_dir, state, repair=True)
                except Exception as exc:
                    _mark_failed(run_dir, state, "artifact_failed", f"{type(exc).__name__}: {exc}")

            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                list(pool.map(consume, response_states))
            progress = True

        evaluating = [state for state in states if state["stage"] == "evaluate"]
        if evaluating:
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                futures = [
                    pool.submit(
                        _evaluate_one,
                        tasks_by_name[state["task"]],
                        Path(state["run_dir"]),
                        state,
                        config.max_repair_iterations,
                    )
                    for state in evaluating
                ]
                for future in futures:
                    future.result()
            progress = True

        _progress_summary(experiment_dir, states)
        if should_stop() or not progress:
            break

    summary = _progress_summary(experiment_dir, states)
    summary["status"] = ("interrupted" if not all(_terminal(s) for s in states) else
                         "completed_with_failures" if summary["n_failed"] else "completed")
    _atomic_json(experiment_dir / "summary.json", summary)
    _append_jsonl(experiment_dir / "attempts.jsonl", {
        "finished_at": _utc_now(), "status": summary["status"]
    })
    return summary


def _load_tasks(args) -> list[BenchmarkTask]:
    task_paths = list(args.tasks or [])
    if args.manifest:
        manifest_path = Path(args.manifest).resolve()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = data.get("tasks") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("manifest must be a JSON array or an object with a 'tasks' array")
        task_paths.extend(str((manifest_path.parent / item).resolve()) for item in entries)
    if not task_paths:
        raise ValueError("provide one or more --tasks paths or a --manifest")
    return [BenchmarkTask.from_json(path) for path in task_paths]


def _handle_checkpoint_signal(_signum, _frame) -> None:
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Batched offline vLLM benchmark and repair runner.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tasks", nargs="+", help="Benchmark task JSON files.")
    source.add_argument("--manifest", help="JSON array of task paths (relative to manifest) or {tasks: [...]}.")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--output-root", default=os.getenv("BTP_RESULTS_ROOT", str(DEFAULT_RESULTS_ROOT)))
    parser.add_argument("--model", default=os.getenv("BTP_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
    parser.add_argument("--dtype", default=os.getenv("BTP_DTYPE", "half"))
    parser.add_argument("--tensor-parallel-size", type=int, default=int(os.getenv("BTP_TENSOR_PARALLEL_SIZE", "2")))
    parser.add_argument("--max-model-len", type=int, default=int(os.getenv("BTP_MAX_MODEL_LEN", "8192")))
    parser.add_argument("--gpu-memory-utilization", type=float, default=float(os.getenv("BTP_GPU_MEMORY_UTILIZATION", "0.90")))
    parser.add_argument("--max-num-seqs", type=int, default=int(os.getenv("BTP_MAX_NUM_SEQS", "32")))
    parser.add_argument("--tests", type=int, default=20)
    parser.add_argument("--max-repair-iterations", type=int, default=2)
    parser.add_argument("--feedback-cases", type=int, default=12)
    parser.add_argument("--workers", type=int, default=int(os.getenv("BTP_WORKERS", "4")))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, _handle_checkpoint_signal)
    tasks = _load_tasks(args)
    config = BatchConfig(
        experiment_id=args.experiment_id,
        output_root=Path(args.output_root),
        model=args.model,
        dtype=args.dtype,
        tensor_parallel_size=args.tensor_parallel_size,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_num_seqs=args.max_num_seqs,
        test_count=args.tests,
        max_repair_iterations=args.max_repair_iterations,
        feedback_cases=args.feedback_cases,
        workers=args.workers,
        seed=args.seed,
        resume=args.resume,
    )
    # The factory initializes one engine only when unfinished tasks remain.
    # That same instance serves every batched generation and repair phase.
    summary = run_offline_batch(
        tasks,
        config=config,
        runtime_factory=lambda: OfflineVLLM(
            model=config.model,
            dtype=config.dtype,
            tensor_parallel_size=config.tensor_parallel_size,
            max_model_len=config.max_model_len,
            gpu_memory_utilization=config.gpu_memory_utilization,
            max_num_seqs=config.max_num_seqs,
        ),
        should_stop=lambda: _STOP_REQUESTED,
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["status"] in {"completed", "interrupted"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
