"""Paired experiments over frozen development pools; held-out data is never read."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
from typing import Callable

from .builder import build_candidate
from .candidate import CandidateSource
from .differential import run_differential_suite
from .experiment_io import CachedInference, atomic_json, digest, implementation_digest, read_json
from .feedback import RawFeedbackStrategy
from .generator import CANDIDATE_SCHEMA, candidate_messages, parse_candidate_response
from .offline_runtime import InferenceRequest
from .pools import load_development
from .repair import repair_messages


@dataclass(frozen=True)
class ComparisonConfig:
    model: str
    seeds: tuple[int, ...]
    arms: tuple[str, ...] = ("baseline", "raw")
    max_repair_iterations: int = 2
    feedback_cases: int = 12
    max_tokens: int = 4096
    temperature: float = 0.2
    runtime_settings: dict = field(default_factory=dict)

    def validate(self):
        if not self.model or not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("model and unique explicit seeds are required")
        if any(type(seed) is not int or seed < 0 for seed in self.seeds):
            raise ValueError("seeds must be nonnegative integers")
        if not self.arms or len(set(self.arms)) != len(self.arms) or "baseline" not in self.arms:
            raise ValueError("unique arms including baseline are required")
        if set(self.arms) - {"baseline", "raw"}:
            raise ValueError("unsupported feedback arm")
        if any(type(v) is not int for v in (self.max_repair_iterations, self.feedback_cases, self.max_tokens)) or self.max_repair_iterations < 0 or self.feedback_cases <= 0 or self.max_tokens <= 0:
            raise ValueError("invalid repair limits")
        import math
        if not math.isfinite(self.temperature) or self.temperature < 0:
            raise ValueError("invalid temperature")


def summarize_results(results: list[dict]) -> dict:
    reference_errors = sum(item["status"] in {"reference_error", "reference_timeout"} for item in results)
    valid = len(results) - reference_errors
    passed = sum(item["passed"] for item in results)
    return {"n_total": len(results), "n_valid": valid, "n_reference_error": reference_errors,
            "n_pass": passed, "n_fail": valid - passed,
            "accuracy": passed / valid if valid else None}


def _candidate(path: Path) -> CandidateSource:
    return CandidateSource.from_dict(read_json(path))


def _validate_state(arm_dir: Path, state: dict) -> None:
    if state.get("status") not in {"pending", "completed", "failed"}:
        raise ValueError("invalid arm checkpoint status")
    iteration = state.get("iteration")
    if type(iteration) is not int or iteration < 0:
        raise ValueError("invalid checkpoint iteration")
    if state.get("final_iteration") is not None:
        if type(state["final_iteration"]) is not int or not 0 <= state["final_iteration"] <= iteration:
            raise ValueError("invalid final checkpoint iteration")
        directory = arm_dir / "iterations" / f"{state['final_iteration']:03d}"
        if digest(read_json(directory / "candidate.json")) != state["final_source_hash"]:
            raise ValueError("checkpoint candidate was modified")
        if digest(read_json(directory / "development.json")) != state["development_hash"]:
            raise ValueError("checkpoint development results were modified")


def _evaluate(task, arm_dir, iteration, candidate, tests, state, config):
    directory = arm_dir / "iterations" / f"{iteration:03d}"
    atomic_json(directory / "candidate.json", candidate.to_dict())
    build = build_candidate(candidate, directory / "candidate")
    atomic_json(directory / "build.json", build.to_dict())
    state["iteration"] = iteration
    if not build.success:
        state.update(status="failed", reason="build_failed", error=build.error or build.build_stderr)
        atomic_json(arm_dir / "state.json", state)
        return
    results = [item.to_dict() for item in run_differential_suite(
        task.reference_command, build.run_command, tests,
        timeout_seconds=task.timeout_seconds, reference_cwd=task.reference_cwd,
        candidate_cwd=directory / "candidate")]
    score = summarize_results(results)
    payload = {"summary": score, "results": results}
    atomic_json(directory / "development.json", payload)
    state.update(final_iteration=iteration, final_source_hash=digest(candidate.to_dict()),
                 development_hash=digest(payload), development=score)
    if score["n_reference_error"]:
        state.update(status="failed", reason="reference_invalid")
    elif state["arm"] == "baseline":
        state.update(status="completed", reason="baseline")
    elif score["n_fail"] == 0:
        state.update(status="completed", reason="development_perfect")
    elif iteration >= config.max_repair_iterations:
        state.update(status="completed", reason="repair_limit")
    else:
        state.update(status="pending", reason=None)
    atomic_json(arm_dir / "state.json", state)


def _summary(root: Path, units: list[dict], interrupted=False):
    rows = []
    for unit in units:
        for arm, state in unit["states"].items():
            rows.append({"task": unit["task"].name, "seed": unit["seed"], "arm": arm, **state})
    status = "interrupted" if interrupted or any(r["status"] == "pending" for r in rows) else (
        "completed_with_failures" if any(r["status"] == "failed" for r in rows) else "completed")
    payload = {"status": status, "arms": rows}
    atomic_json(root / "summary.json", payload)
    return payload


def run_comparison(tasks, pool_dirs: dict[str, Path], output_dir: Path, *,
                   config: ComparisonConfig, runtime=None, runtime_factory=None,
                   resume=False, should_stop: Callable[[], bool] = lambda: False):
    """Run paired arms with a shared C0 and batched cached inference.

    Pool sizes and seeds are explicit. This function reads development.json only;
    held_out.json belongs exclusively to the later evaluation command.
    """
    config.validate()
    tasks = list(tasks)
    if not tasks or len({t.name for t in tasks}) != len(tasks):
        raise ValueError("unique nonempty tasks required")
    pools = {task.name: load_development(Path(pool_dirs[task.name]), task) for task in tasks}
    root = Path(output_dir).resolve()
    config_dict = json.loads(json.dumps(asdict(config)))
    identity = {"schema_version": 1, "config": config_dict,
                "implementation": implementation_digest(),
                "tasks": [{**task.to_dict(), "specification": task.read_specification(),
                           "pool": pools[task.name][0]} for task in tasks]}
    fingerprint = digest(identity)
    if root.exists():
        if not resume:
            raise FileExistsError("experiment exists; use resume")
        if read_json(root / "metadata.json").get("fingerprint") != fingerprint:
            raise ValueError("experiment configuration, source, task or pool changed")
    elif resume:
        raise FileNotFoundError("cannot resume nonexistent experiment")
    else:
        atomic_json(root / "metadata.json", {**identity, "fingerprint": fingerprint})
    inference = CachedInference(runtime=runtime, runtime_factory=runtime_factory, model=config.model)
    units = []
    initial_requests = []
    for task in tasks:
        for seed in config.seeds:
            unit_dir = root / task.name / f"seed-{seed}"
            system, user = candidate_messages(specification=task.read_specification(), input_format=task.input_format)
            request = InferenceRequest(task.name, "initial_code_generation", 0, system, user,
                                       CANDIDATE_SCHEMA, config.temperature, config.max_tokens, seed)
            path = unit_dir / "inference" / "initial.json"
            initial_requests.append((path, request))
            units.append({"task": task, "seed": seed, "directory": unit_dir,
                          "initial_record": path, "states": {}})
    if should_stop():
        return _summary(root, units, True)
    initial = inference.generate(initial_requests)
    if should_stop():
        return _summary(root, units, True)
    for unit in units:
        task, unit_dir = unit["task"], unit["directory"]
        error = None
        try:
            candidate = parse_candidate_response(initial[str(unit["initial_record"] )])
        except (KeyError, TypeError, ValueError) as exc:
            error = str(exc)
            candidate = None
        if candidate is not None:
            frozen = unit_dir / "initial_candidate.json"
            if frozen.exists() and read_json(frozen) != candidate.to_dict():
                raise ValueError("frozen initial candidate was modified")
            atomic_json(frozen, candidate.to_dict())
        for arm in config.arms:
            arm_dir = unit_dir / "arms" / arm
            state_path = arm_dir / "state.json"
            if state_path.exists():
                state = read_json(state_path)
                _validate_state(arm_dir, state)
                if state.get("arm") != arm:
                    raise ValueError("checkpoint arm mismatch")
                if state.get("initial_source_hash") != (digest(candidate.to_dict()) if candidate else None):
                    raise ValueError("initial candidate lineage mismatch")
            else:
                state = {"arm": arm, "iteration": 0, "status": "pending", "final_iteration": None,
                         "initial_source_hash": digest(candidate.to_dict()) if candidate else None}
                if error:
                    state.update(status="failed", reason="initial_parse_failed", error=error)
                    atomic_json(state_path, state)
                else:
                    _evaluate(task, arm_dir, 0, candidate, pools[task.name][1], state, config)
            unit["states"][arm] = state
    while True:
        pending = [(unit, arm, state) for unit in units for arm, state in unit["states"].items()
                   if state["status"] == "pending"]
        if not pending or should_stop():
            return _summary(root, units, bool(pending))
        requests = []
        work = []
        for unit, arm, state in pending:
            task = unit["task"]
            arm_dir = unit["directory"] / "arms" / arm
            directory = arm_dir / "iterations" / f"{state['iteration']:03d}"
            candidate = _candidate(directory / "candidate.json")
            results = read_json(directory / "development.json")["results"]
            feedback = RawFeedbackStrategy().prepare(results, config.feedback_cases)
            atomic_json(directory / "feedback.json", {"kind": arm, "failures": feedback})
            system, user, schema = repair_messages(specification=task.read_specification(),
                input_format=task.input_format, candidate=candidate, failures=feedback)
            next_iteration = state["iteration"] + 1
            record = arm_dir / "inference" / f"repair-{next_iteration:03d}.json"
            request = InferenceRequest(task.name, "candidate_repair", next_iteration, system, user,
                schema, config.temperature, config.max_tokens, unit["seed"] + next_iteration)
            requests.append((record, request))
            work.append((unit, arm_dir, state, next_iteration, record))
        responses = inference.generate(requests)
        if should_stop():
            return _summary(root, units, True)
        for unit, arm_dir, state, iteration, record in work:
            try:
                candidate = parse_candidate_response(responses[str(record)])
                _evaluate(unit["task"], arm_dir, iteration, candidate,
                          pools[unit["task"].name][1], state, config)
            except (KeyError, TypeError, ValueError) as exc:
                state.update(status="failed", reason="repair_failed", error=str(exc))
                atomic_json(arm_dir / "state.json", state)
        _summary(root, units)
