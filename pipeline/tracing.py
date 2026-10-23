"""Source-round candidate-only trace preparation, persistence and resume."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time

from .artifacts import atomic_bytes, atomic_json, digest, file_digest, read_json
from .candidate import CandidateSource
from .checkpoints import CheckpointError, TaskCheckpoint, checked_payload, verify_payload
from .feedback import raw_feedback
from .trace_process import run_capture


PROTOCOL_VERSION = 1
HELPERS = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TraceConfig:
    max_events: int = 256
    timeout_seconds: float = 10.0
    build_timeout_seconds: float = 30.0
    gdb: str = "gdb"

    def validate(self):
        if type(self.max_events) is not int or self.max_events <= 0:
            raise ValueError("trace-max-events must be a positive integer")
        if any(not math.isfinite(value) or value <= 0
               for value in (self.timeout_seconds, self.build_timeout_seconds)):
            raise ValueError("Trace timeouts must be finite and positive")
        if not isinstance(self.gdb, str) or not self.gdb.strip():
            raise ValueError("trace-gdb must name an executable")


class TraceFailure(ValueError):
    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def _tool_identity(name: str, *, debugger=False) -> dict:
    executable = shutil.which(name)
    if executable is None:
        return {"requested": name, "path": None}
    path = Path(executable).resolve()
    if sys.platform != "linux" or not Path("/proc/self/stat").is_file():
        return {"requested": name, "path": str(path), "sha256": file_digest(path),
                "unsupported_platform": True}
    command = [str(path), "--version"]
    if debugger:
        command = [str(path), "-nx", "-nh", "--version"]
    result = run_capture(command, cwd=HELPERS, timeout=5.0)
    return {"requested": name, "path": str(path), "sha256": file_digest(path),
            "version": result["diagnostics"]["stdout"], "exit_code": result["exit_code"],
            "error": result["error"], "timed_out": result["truncation_reason"] == "timeout"}


def describe_tracing(config: TraceConfig) -> dict:
    """Freeze available tool identities; missing tools fail only tasks needing them."""
    config.validate()
    return {"protocol_version": PROTOCOL_VERSION, "settings": asdict(config),
            "system": platform.system(), "machine": platform.machine(),
            "python": {"path": sys.executable,
                       "resolved_binary": str(Path(sys.executable).resolve()), "version": sys.version,
                       "sha256": file_digest(Path(sys.executable))},
            "compiler": _tool_identity(os.environ.get("CXX", "g++")),
            "gdb": _tool_identity(config.gdb, debugger=True)}


def _publish(checkpoint: TaskCheckpoint, relative: str, identity: dict,
             produce, *, attachments=()) -> dict:
    """Publish a self-checksummed result last, then adopt it across a state crash.

    The envelope binds all attachments and the collection request. Incomplete
    outputs without an envelope are uncommitted work and may be recreated.
    """
    path = checkpoint.path(relative)
    if path.exists():
        payload = verify_payload(read_json(path), relative)
        if payload.get("identity") != identity:
            raise CheckpointError("Trace publication does not match its request: " + relative)
        for name, expected in payload.get("attachments", {}).items():
            attachment = checkpoint.path(name)
            if not attachment.is_file() or file_digest(attachment) != expected:
                raise CheckpointError("Missing or changed trace attachment: " + name)
            checkpoint.track(name)
        checkpoint.track(relative)
        checkpoint.save()
        return payload["result"]
    started = time.monotonic()
    try:
        result = produce()
    except OSError as exc:
        # Collection workspace/setup/cleanup errors belong to this task. Keep
        # publication and checkpoint validation outside this handler: failures
        # to persist or verify the envelope must still propagate.
        result = {
            "success": False, "collection_status": "failed", "lines": [],
            "complete": False, "truncation_reason": None, "event_count": 0,
            "total_event_count": None,
            "termination": {"kind": "collection_stopped", "reason": "collector_failed"},
            "error": {"reason": "collector_failed", "message": f"{type(exc).__name__}: {exc}"[:1000]},
            "duration_s": time.monotonic() - started, "command": None,
            "exit_code": None,
            "diagnostics": {name: {"text": "", "truncated": False}
                            for name in ("stdout", "stderr")},
        }
    checkpoint.validate()
    hashes = {}
    for name in attachments:
        if checkpoint.path(name).is_file():
            checkpoint.track(name)
            hashes[name] = checkpoint.state["artifacts"][name]
    checkpoint.write_json(relative, checked_payload({
        "schema_version": 2, "identity": identity, "attachments": hashes, "result": result,
    }))
    checkpoint.save()
    return result


def prepare_traces(checkpoint: TaskCheckpoint, config: TraceConfig, identity: dict) -> None:
    checkpoint.validate()
    iteration = checkpoint.state["last_evaluated_iteration"]
    directory = f"iterations/{iteration:03d}"
    candidate = CandidateSource.from_dict(checkpoint.read_json(directory + "/candidate.json"))
    failures = raw_feedback(checkpoint.read_json(directory + "/results.json"))
    if not failures:
        raise CheckpointError("Trace collection requested without eligible failures")
    source_path = directory + "/candidate/" + candidate.filename
    request = {
        "schema_version": 2, "protocol_version": PROTOCOL_VERSION, "source_iteration": iteration,
        "source_sha256": checkpoint.state["artifacts"][source_path],
        "tests_sha256": checkpoint.state["artifacts"]["tests.json"],
        "language": candidate.language, "case_ids": [case["case_id"] for case in failures],
        "failures_sha256": digest(failures), "settings": asdict(config), "collector": identity,
    }
    checkpoint.write_json(directory + "/trace_request.json", checked_payload(request))
    checkpoint.state["stage"] = "trace_collect"
    checkpoint.save()


def collect_traces(checkpoint: TaskCheckpoint, config: TraceConfig, identity: dict,
                   should_stop=lambda: False) -> None:
    checkpoint.validate()
    iteration = checkpoint.state["last_evaluated_iteration"]
    directory = f"iterations/{iteration:03d}"
    request = verify_payload(checkpoint.read_json(directory + "/trace_request.json"), "trace request")
    failures = raw_feedback(checkpoint.read_json(directory + "/results.json"))
    candidate = CandidateSource.from_dict(checkpoint.read_json(directory + "/candidate.json"))
    if (request["settings"] != asdict(config) or request["collector"] != identity
            or request["failures_sha256"] != digest(failures)
            or request["case_ids"] != [case["case_id"] for case in failures]
            or request["tests_sha256"] != checkpoint.state["artifacts"]["tests.json"]
            or request["source_sha256"] != checkpoint.state["artifacts"][directory + "/candidate/" + candidate.filename]
            or request["source_iteration"] != iteration or request["language"] != candidate.language
            or request["protocol_version"] != PROTOCOL_VERSION):
        raise CheckpointError("Trace request no longer matches the evaluated source and inputs")
    if sys.platform != "linux" or not Path("/proc/self/stat").is_file():
        raise TraceFailure("trace_setup_failed", "Path collection requires GNU/Linux with /proc")
    trace_dir = directory + "/traces"
    source_relative = trace_dir + "/build/" + candidate.filename
    executable_relative = trace_dir + "/build/program"
    source = checkpoint.path(source_relative)
    executable = checkpoint.path(executable_relative)
    build_identity = {"request_sha256": digest(request), "operation": "trace_build"}

    def build():
        started = time.monotonic()
        try:
            atomic_bytes(source, candidate.source.encode("utf-8"))
            source_digest = file_digest(source)
        except OSError as exc:
            raise CheckpointError(f"Cannot publish trace source: {exc}") from exc
        if source_digest != request["source_sha256"]:
            raise CheckpointError("Trace source differs from evaluated source")
        if candidate.language == "python":
            return {"success": True, "duration_s": time.monotonic() - started, "command": None}
        compiler = identity["compiler"]
        debugger = identity["gdb"]
        if compiler["path"] is None or debugger["path"] is None:
            return {"success": False, "error": "GNU g++ and Python-enabled GDB are required",
                    "duration_s": time.monotonic() - started, "command": None}
        if "Free Software Foundation" not in compiler["version"]["text"]:
            return {"success": False, "error": "Trace builds require GNU g++",
                    "duration_s": time.monotonic() - started, "command": None}
        # Compile to a temporary output; only a successful fresh binary can be
        # published. Preserve the source pathname used by its debug mappings.
        built_fresh = False
        with tempfile.TemporaryDirectory(prefix="btp-trace-build-") as temporary:
            temporary_executable = Path(temporary) / "program"
            command = [compiler["path"], "-std=c++20", "-O0", "-g", "-fno-inline", "-fno-pie",
                       "-no-pie", str(source), "-o", str(temporary_executable)]
            result = run_capture(command, cwd=source.parent, timeout=config.build_timeout_seconds)
            if result["error"] is None and result["exit_code"] == 0 and result["truncation_reason"] is None:
                if temporary_executable.is_file():
                    binary = temporary_executable.read_bytes()
                    try:
                        atomic_bytes(executable, binary)
                        executable.chmod(0o700)
                    except OSError as exc:
                        raise CheckpointError(f"Cannot publish trace binary: {exc}") from exc
                    built_fresh = True
        result.update(command=command, success=built_fresh, duration_s=time.monotonic() - started)
        return result

    built = _publish(checkpoint, trace_dir + "/build.json", build_identity, build,
                     attachments=(source_relative, executable_relative))
    if not built["success"]:
        raise TraceFailure("trace_build_failed", "Candidate trace build failed; inspect traces/build.json")
    feedback = []
    durations = []
    for case in failures:
        if should_stop():
            return
        case_id = case["case_id"]
        case_identity = {"request_sha256": digest(request), "case_id": case_id,
                         "input_sha256": digest(case["input"]), "operation": "trace_case"}

        def collect():
            started = time.monotonic()
            extra_env = {}
            with tempfile.TemporaryDirectory(prefix="btp-trace-") as temporary:
                if candidate.language == "python":
                    command = [sys.executable, str(HELPERS / "trace_python.py"), str(source)]
                else:
                    configuration = Path(temporary) / "config.json"
                    atomic_json(configuration, {"source": str(source)})
                    extra_env["BTP_TRACE_CONFIG"] = str(configuration)
                    command = [identity["gdb"]["path"], "-nx", "-nh", "-q", "-batch",
                               "-iex", "set auto-load off", "-iex", "set debuginfod enabled off",
                               "-x", str(HELPERS / "trace_gdb.py"), str(executable)]
                result = run_capture(command, cwd=source.parent, timeout=config.timeout_seconds,
                                     stdin=case["input"], trace=True, max_events=config.max_events,
                                     source_lines=len(candidate.source.splitlines()), extra_env=extra_env,
                                     python=candidate.language == "python")
            result["command"] = command
            result["duration_s"] = time.monotonic() - started
            result["collection_status"] = "failed" if result["error"] else (
                "complete" if result["complete"] else "truncated")
            return result

        result = _publish(checkpoint, trace_dir + f"/case-{case_id:06d}.json", case_identity, collect)
        if result["error"]:
            reason = result["error"]["reason"]
            raise TraceFailure("trace_unsupported" if reason == "unsupported_execution" else (
                "trace_empty" if reason == "trace_empty" else "trace_collection_failed"),
                result["error"]["message"])
        feedback.append({**case, "trace": {key: result[key] for key in (
            "lines", "collection_status", "complete", "truncation_reason", "event_count",
            "total_event_count", "termination")}})
        durations.append({"case_id": case_id, "duration_s": result["duration_s"]})
    checkpoint.write_json(directory + "/feedback.json", feedback)
    checkpoint.write_json(trace_dir + "/summary.json", {
        "source_iteration": iteration, "build_duration_s": built["duration_s"],
        "cases": durations, "collection_duration_s": sum(case["duration_s"] for case in durations),
        "n_cases": len(feedback), "n_truncated": sum(not item["trace"]["complete"] for item in feedback),
    })
    checkpoint.state["stage"] = "repair_request"
    checkpoint.save()
