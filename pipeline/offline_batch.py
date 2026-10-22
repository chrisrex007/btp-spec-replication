"""Resumable raw-feedback repair using direct, local-only model inference."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from pathlib import Path
import re
import signal
import sys
import time
import uuid

from .artifacts import append_jsonl, atomic_json, digest, implementation_digest, read_json, utc_now
from .builder import build_candidate
from .candidate import CandidateSource
from .checkpoints import CheckpointError, TaskCheckpoint, checked_payload, verify_payload
from .differential import run_differential_suite
from .feedback import RawFeedbackStrategy
from .generator import CANDIDATE_SCHEMA, candidate_messages, parse_candidate_response
from .llm_log import log_call, request_record, response_record
from .offline_runtime import (
    ContextBudgetExceeded, InferenceRequest, InferenceSession, RuntimeConfig,
    add_runtime_arguments, batch_key, config_from_args, describe_runtime,
)
from .repair import repair_messages
from .task import BenchmarkTask
from .test_generator import parse_tests_response, test_generation_request


DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parents[1] / "runs"
_ID = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class BatchConfig:
    experiment_id: str
    max_repair_iterations: int
    runtime: RuntimeConfig
    output_root: Path = DEFAULT_RESULTS_ROOT
    test_count: int = 20
    workers: int = 4
    resume: bool = False

    def validate(self) -> None:
        self.runtime.validate()
        if self.experiment_id in {".", ".."} or not _ID.fullmatch(self.experiment_id):
            raise ValueError("experiment_id must be a plain directory identifier")
        if type(self.max_repair_iterations) is not int or self.max_repair_iterations < 0:
            raise ValueError("max_repair_iterations must be an explicit nonnegative integer")
        if self.runtime.seed + self.max_repair_iterations >= 2**63:
            raise ValueError("seed plus repair budget must be below 2**63")
        if any(type(value) is not int or value <= 0 for value in (self.test_count, self.workers)):
            raise ValueError("test_count and workers must be positive integers")


def _round(iteration: int) -> str:
    return f"iterations/{iteration:03d}"


def _inference_base(request: InferenceRequest) -> str:
    return f"inference/iteration-{request.iteration:03d}-{request.step}"


def _terminal(checkpoint: TaskCheckpoint) -> bool:
    return checkpoint.state["stage"] in {"completed", "failed"}


def _finish(checkpoint: TaskCheckpoint, status: str, reason: str,
            *, score: dict | None = None, error: str | None = None) -> None:
    summary = {
        "task": checkpoint.state["task"], "status": status, "stop_reason": reason,
        "attempted_iteration": checkpoint.state["attempted_iteration"],
        "last_evaluated_iteration": checkpoint.state["last_evaluated_iteration"],
        "accuracy": None,
    }
    if score is not None:
        summary.update(score)
    if error is not None:
        summary["error"] = error
    checkpoint.write_json("summary.json", summary)
    checkpoint.state.update(stage="completed" if status == "completed" else "failed", result=summary)
    checkpoint.save()


def _initialize(tasks: list[BenchmarkTask], config: BatchConfig, runtime_identity: dict):
    config.validate()
    if not tasks or len({task.name.casefold() for task in tasks}) != len(tasks):
        raise ValueError("At least one task is required and task names must be unique")
    if any(task.name.casefold() in {"metadata.json", "summary.json", "attempts.jsonl"} for task in tasks):
        raise ValueError("Task names must not collide with experiment metadata, summary or attempts files")
    root = config.output_root.expanduser().resolve() / config.experiment_id
    identity = {
        "implementation_sha256": implementation_digest(), "runtime": runtime_identity,
        "output_directory": str(root), "test_count": config.test_count, "workers": config.workers,
        "max_repair_iterations": config.max_repair_iterations,
        "tasks": [{"task": task.to_dict(), "specification": task.read_specification()}
                  for task in tasks],
    }
    if root.exists():
        if not config.resume:
            raise FileExistsError(f"{root} already exists; use --resume or a new experiment identifier")
        if not (root / "metadata.json").is_file():
            raise CheckpointError("Incomplete initialization: metadata is missing; use a new run")
        metadata = verify_payload(read_json(root / "metadata.json"), "experiment metadata")
        if metadata.get("identity") != identity or metadata.get("fingerprint") != digest(identity):
            raise CheckpointError("Cannot resume: implementation, model, task, directory or configuration changed")
        checkpoints = [TaskCheckpoint.load(root / task.name, task.name, config.max_repair_iterations)
                       for task in tasks]
    else:
        if config.resume:
            raise FileNotFoundError("Cannot resume a nonexistent experiment")
        root.mkdir(parents=True)
        checkpoints = []
        for task, snapshot in zip(tasks, identity["tasks"]):
            checkpoint = TaskCheckpoint(root / task.name, {
                "schema_version": 2, "task": task.name, "stage": "candidate_request",
                "attempted_iteration": 0, "last_evaluated_iteration": None,
                "artifacts": {}, "created_at": utc_now(),
            })
            checkpoint.write_json("task.json", snapshot["task"])
            checkpoint.write_bytes("specification.txt", snapshot["specification"].encode("utf-8"))
            checkpoint.save()
            checkpoints.append(checkpoint)
        # Publish metadata only after every initial task checkpoint exists.
        atomic_json(root / "metadata.json", checked_payload({
            "schema_version": 2, "created_at": utc_now(), "identity": identity,
            "fingerprint": digest(identity),
        }))
    return root, checkpoints


def _request_for(task: BenchmarkTask, checkpoint: TaskCheckpoint,
                 config: BatchConfig) -> InferenceRequest:
    checkpoint.validate()
    specification = checkpoint.path("specification.txt").read_text(encoding="utf-8")
    settings = config.runtime
    stage = checkpoint.state["stage"]
    if stage == "candidate_request":
        system, user = candidate_messages(specification=specification, input_format=task.input_format)
        return InferenceRequest(task.name, "initial_code_generation", 0, system, user,
                                CANDIDATE_SCHEMA, settings.temperature, settings.max_tokens,
                                settings.seed, "candidate_program")
    if stage == "tests_request":
        system, user, schema = test_generation_request(
            specification=specification, input_format=task.input_format, count=config.test_count)
        return InferenceRequest(task.name, "test_generation", 0, system, user, schema,
                                settings.test_temperature, settings.max_tokens,
                                settings.seed + 100_000, "test_inputs")
    if stage != "repair_request":
        raise ValueError(f"Unsupported request stage: {stage}")
    previous = checkpoint.state["last_evaluated_iteration"]
    if previous is None or previous >= config.max_repair_iterations:
        raise CheckpointError("Repair request is outside the configured round budget")
    directory = _round(previous)
    candidate = CandidateSource.from_dict(checkpoint.read_json(directory + "/candidate.json"))
    feedback = RawFeedbackStrategy().prepare(checkpoint.read_json(directory + "/failures.json"))
    if not feedback:
        raise CheckpointError("Repair requested without eligible failures")
    checkpoint.write_json(directory + "/feedback.json", feedback)
    system, user, schema = repair_messages(
        specification=specification, input_format=task.input_format, candidate=candidate,
        failures=feedback,
    )
    iteration = previous + 1
    return InferenceRequest(task.name, "candidate_repair", iteration, system, user, schema,
                            settings.temperature, settings.max_tokens,
                            settings.seed + iteration, "candidate_program")


def _verify_response(value: object, request: dict) -> dict:
    payload = verify_payload(value, "inference response")
    if (payload.get("status") != "success"
            or payload.get("request_fingerprint") != request["fingerprint"]
            or not isinstance(payload.get("output"), dict)
            or not isinstance(payload["output"].get("response"), str)):
        raise CheckpointError("Response does not match its request or contains no string output")
    return payload


def _advance_response(checkpoint: TaskCheckpoint, request: InferenceRequest) -> None:
    checkpoint.state["attempted_iteration"] = request.iteration
    checkpoint.state["stage"] = {
        "initial_code_generation": "candidate_response", "test_generation": "tests_response",
        "candidate_repair": "repair_response",
    }[request.step]
    checkpoint.save()


def _execute_requests(tasks: dict[str, BenchmarkTask], checkpoints: list[TaskCheckpoint],
                      config: BatchConfig, session: InferenceSession, should_stop) -> str | None:
    groups = {}
    for checkpoint in checkpoints:
        try:
            request = _request_for(tasks[checkpoint.state["task"]], checkpoint, config)
            base = _inference_base(request)
            record = request_record(request, session.identity)
            checkpoint.write_json(base + ".request.json", record)
            checkpoint.state["attempted_iteration"] = request.iteration
            checkpoint.save()  # A request is committed before calling the model.
            response_path = checkpoint.path(base + ".response.json")
            if response_path.exists():
                _verify_response(read_json(response_path), record)
                checkpoint.track(base + ".response.json")
                _advance_response(checkpoint, request)
            else:
                groups.setdefault(batch_key(request), []).append((checkpoint, request, record))
        except CheckpointError:
            raise
        except Exception as exc:
            _finish(checkpoint, "request_failed", "request_failed", error=f"{type(exc).__name__}: {exc}")
    for group in groups.values():
        while group:
            if should_stop():
                return None
            batch_id = uuid.uuid4().hex
            started = time.monotonic()
            try:
                outputs = session.generate_batch([item[1] for item in group])
                if len(outputs) != len(group) or any(not isinstance(item.response, str) for item in outputs):
                    raise RuntimeError("Runtime output count/type differs from requests")
            except ContextBudgetExceeded as exc:
                offending = [item for item in group if item[1] == exc.request]
                if not offending:
                    raise
                for checkpoint, request, record in offending:
                    error = response_record(record, None, error=exc,
                                            latency_s=time.monotonic() - started,
                                            batch_id=batch_id, batch_size=len(group))
                    checkpoint.write_json(_inference_base(request) + f".error-{batch_id}.json", error)
                    log_call(checkpoint.root / "inference.jsonl", record, error)
                    _finish(checkpoint, "context_budget_exceeded", "context_budget_exceeded", error=str(exc))
                group = [item for item in group if item not in offending]
                continue
            except Exception as exc:
                for checkpoint, request, record in group:
                    error = response_record(record, None, error=exc,
                                            latency_s=time.monotonic() - started,
                                            batch_id=batch_id, batch_size=len(group))
                    checkpoint.write_json(_inference_base(request) + f".error-{batch_id}.json", error)
                    log_call(checkpoint.root / "inference.jsonl", record, error)
                    checkpoint.save()  # Keep pending; only an explicit resume retries it.
                return f"{type(exc).__name__}: {exc}"
            for (checkpoint, request, record), output in zip(group, outputs):
                response = response_record(record, output, latency_s=time.monotonic() - started,
                                           batch_id=batch_id, batch_size=len(group))
                checkpoint.write_json(_inference_base(request) + ".response.json", response)
                # Commit response before advancing the stage; either boundary can resume.
                checkpoint.save()
                log_call(checkpoint.root / "inference.jsonl", record, response)
                _advance_response(checkpoint, request)
            break
    return None


def _consume(checkpoint: TaskCheckpoint) -> None:
    checkpoint.validate()
    stage = checkpoint.state["stage"]
    iteration = checkpoint.state["attempted_iteration"]
    step = "test_generation" if stage == "tests_response" else (
        "candidate_repair" if stage == "repair_response" else "initial_code_generation")
    base = f"inference/iteration-{iteration:03d}-{step}"
    request = checkpoint.read_json(base + ".request.json")
    response = _verify_response(checkpoint.read_json(base + ".response.json"), request)["output"]["response"]
    if stage == "tests_response":
        try:
            tests = parse_tests_response(response, request["request"]["schema"]["properties"]["tests"]["minItems"])
        except (ValueError, KeyError, TypeError) as exc:
            _finish(checkpoint, "test_generation_failed", "test_generation_failed", error=str(exc))
            return
        checkpoint.write_json("tests.json", tests)
        checkpoint.state["stage"] = "evaluate"
        checkpoint.save()
        return
    try:
        candidate = parse_candidate_response(response)
    except (ValueError, KeyError, TypeError) as exc:
        reason = "repair_parse_failed" if iteration else "candidate_parse_failed"
        _finish(checkpoint, reason, reason, error=str(exc))
        return
    if iteration:
        previous = checkpoint.state["last_evaluated_iteration"]
        current = checkpoint.read_json(_round(previous) + "/candidate.json")
        if candidate.language != current["language"]:
            _finish(checkpoint, "language_changed", "language_changed",
                    error="A repair must retain the current candidate's language")
            return
    directory = _round(iteration)
    checkpoint.write_json(directory + "/candidate.json", candidate.to_dict())
    source = directory + "/candidate/" + candidate.filename
    checkpoint.write_bytes(source, candidate.source.encode("utf-8"))
    checkpoint.write_json(directory + "/candidate/metadata.json", {
        "language": candidate.language, "filename": candidate.filename,
    })
    build_path = directory + "/build.json"
    if build_path in checkpoint.state["artifacts"]:
        build = checkpoint.read_json(build_path)
    else:
        build = build_candidate(candidate, checkpoint.path(directory + "/candidate")).to_dict()
        checkpoint.track(source)
        checkpoint.write_json(build_path, build)
    if build["success"] and candidate.language == "cpp":
        executable = Path(build["run_command"][0]).relative_to(checkpoint.root).as_posix()
        checkpoint.track(executable)
    if not build["success"] or not build["run_command"]:
        reason = "repair_build_failed" if iteration else "build_failed"
        _finish(checkpoint, reason, reason, error=build["error"] or build["build_stderr"])
        return
    checkpoint.state["stage"] = "evaluate" if iteration else "tests_request"
    checkpoint.save()


def _evaluate(task: BenchmarkTask, checkpoint: TaskCheckpoint, config: BatchConfig) -> None:
    checkpoint.validate()
    iteration = checkpoint.state["attempted_iteration"]
    directory = _round(iteration)
    results_path = directory + "/results.json"
    if results_path in checkpoint.state["artifacts"]:
        payload = checkpoint.read_json(results_path)
    else:
        build = checkpoint.read_json(directory + "/build.json")
        tests = checkpoint.read_json("tests.json")
        results = run_differential_suite(
            task.reference_command, build["run_command"], tests,
            timeout_seconds=task.timeout_seconds, reference_cwd=task.reference_cwd,
            candidate_cwd=checkpoint.path(directory + "/candidate"),
        )
        checkpoint.validate()
        payload = [item.to_dict() for item in results]
        checkpoint.write_json(results_path, payload)
    failures = [item for item in payload if not item["passed"]]
    checkpoint.write_json(directory + "/failures.json", failures)
    reference_failures = sum(item["status"] in {"reference_error", "reference_timeout"} for item in payload)
    passing = sum(item["passed"] for item in payload)
    valid = len(payload) - reference_failures
    score = {
        "status": "invalid_reference" if reference_failures else "completed",
        "n_total": len(payload), "n_valid": valid, "n_reference_failures": reference_failures,
        "n_pass": passing, "n_fail": valid - passing,
        "accuracy": passing / len(payload) if payload and not reference_failures else None,
        "status_counts": {status: sum(item["status"] == status for item in payload)
                          for status in sorted({item["status"] for item in payload})},
    }
    checkpoint.write_json(directory + "/summary.json", {"iteration": iteration, **score})
    checkpoint.state.update(last_evaluated_iteration=iteration, last_evaluated_summary=score)
    if reference_failures:
        _finish(checkpoint, "invalid_reference", "invalid_reference", score=score)
    elif not failures:
        _finish(checkpoint, "completed", "no_failures", score=score)
    elif iteration >= config.max_repair_iterations:
        _finish(checkpoint, "completed", "repair_budget_exhausted", score=score)
    else:
        checkpoint.state["stage"] = "repair_request"
        checkpoint.save()


def _summary(root: Path, checkpoints: list[TaskCheckpoint], *, status: str | None = None,
             error: str | None = None) -> dict:
    failed = sum(cp.state["stage"] == "failed" for cp in checkpoints)
    if status is None:
        status = "running" if any(not _terminal(cp) for cp in checkpoints) else (
            "completed_with_failures" if failed else "completed")
    value = {
        "schema_version": 2, "experiment_id": root.name, "status": status,
        "updated_at": utc_now(), "n_tasks": len(checkpoints), "n_failed": failed,
        "tasks": {cp.state["task"]: {
            "stage": cp.state["stage"], "attempted_iteration": cp.state["attempted_iteration"],
            "last_evaluated_iteration": cp.state["last_evaluated_iteration"],
            "last_evaluated_summary": cp.state.get("last_evaluated_summary"),
            "result": cp.state.get("result"),
        } for cp in checkpoints},
    }
    if error is not None:
        value["error"] = error
    atomic_json(root / "summary.json", value)
    return value


def run_offline_batch(tasks: list[BenchmarkTask], *, config: BatchConfig,
                      should_stop=lambda: False) -> dict:
    config.validate()
    runtime_identity = describe_runtime(config.runtime)
    root, checkpoints = _initialize(tasks, config, runtime_identity)
    session = InferenceSession(config.runtime, runtime_identity)
    by_name = {task.name: task for task in tasks}
    append_jsonl(root / "attempts.jsonl", {"started_at": utc_now(), "resume": config.resume})
    try:
        while any(not _terminal(cp) for cp in checkpoints):
            if should_stop():
                break
            pending = [cp for cp in checkpoints if cp.state["stage"] in {
                "candidate_request", "tests_request", "repair_request"}]
            error = _execute_requests(by_name, pending, config, session, should_stop)
            if error is not None:
                result = _summary(root, checkpoints, status="runtime_failed", error=error)
                append_jsonl(root / "attempts.jsonl", {"finished_at": utc_now(), "status": result["status"]})
                return result
            if should_stop():
                break
            responses = [cp for cp in checkpoints if cp.state["stage"] in {
                "candidate_response", "tests_response", "repair_response"}]
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                list(pool.map(_consume, responses))
            evaluating = [cp for cp in checkpoints if cp.state["stage"] == "evaluate"]
            with ThreadPoolExecutor(max_workers=config.workers) as pool:
                list(pool.map(lambda cp: _evaluate(by_name[cp.state["task"]], cp, config), evaluating))
            _summary(root, checkpoints)
    except KeyboardInterrupt:
        # Explicit stage boundaries already publish coherent state. Do not seal
        # partially completed in-memory writes merely because a stop arrived.
        result = _summary(root, checkpoints, status="interrupted")
    except Exception as exc:
        # Do not publish potentially partially advanced in-memory state on corruption.
        result = _summary(root, checkpoints, status="artifact_failed",
                          error=f"{type(exc).__name__}: {exc}")
    else:
        result = _summary(root, checkpoints, status="interrupted" if should_stop() else None)
    append_jsonl(root / "attempts.jsonl", {"finished_at": utc_now(), "status": result["status"]})
    return result


def _load_tasks(args) -> list[BenchmarkTask]:
    paths = list(args.tasks or [])
    if args.manifest:
        manifest = Path(args.manifest).resolve()
        value = read_json(manifest)
        entries = value.get("tasks") if isinstance(value, dict) else value
        if not isinstance(entries, list) or not all(isinstance(item, str) and item for item in entries):
            raise ValueError("Manifest must contain an array of task JSON paths")
        paths.extend(manifest.parent / item for item in entries)
    return [BenchmarkTask.from_json(path) for path in paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tasks", nargs="+")
    source.add_argument("--manifest")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--max-repair-iterations", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--tests", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--resume", action="store_true")
    add_runtime_arguments(parser)
    args = parser.parse_args()
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    previous = {}
    try:
        for name in ("SIGINT", "SIGTERM"):
            sig = getattr(signal, name, None)
            if sig is not None:
                previous[sig] = signal.signal(sig, stop)
        config = BatchConfig(
            experiment_id=args.experiment_id, max_repair_iterations=args.max_repair_iterations,
            runtime=config_from_args(args), output_root=args.output_root,
            test_count=args.tests, workers=args.workers, resume=args.resume,
        )
        result = run_offline_batch(_load_tasks(args), config=config, should_stop=lambda: stopped)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Setup/checkpoint failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(result, ensure_ascii=True))
    return 130 if result["status"] == "interrupted" else 0 if result["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
