"""Bounded Linux collector processes, event pipes and process-group cleanup."""
from __future__ import annotations

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time


DIAGNOSTIC_LIMIT = 65536
ENVIRONMENT = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONIOENCODING": "utf-8",
               "PYTHONDONTWRITEBYTECODE": "1"}


def _process_identity(pid: int):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(fields[1]), fields[19]  # parent PID and process start ticks
    except (OSError, ValueError, IndexError):
        return None


def _children(pid: int) -> set[int]:
    children = set()
    for task in Path(f"/proc/{pid}/task").glob("*"):
        try:
            children.update(int(value) for value in (task / "children").read_text().split())
        except OSError:
            pass
    return children


def _cleanup(process, known: dict[int, str]):
    # GDB inferiors may have a different process group from the debugger. Track
    # their creation identities and also inspect owned descendants before kill.
    pending = [process.pid, *known]
    visited = set()
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        current = _process_identity(pid)
        if current is None or (pid in known and known[pid] != current[1]):
            continue
        known[pid] = current[1]
        for child in _children(pid):
            child_identity = _process_identity(child)
            if child_identity is not None and child_identity[0] == pid:
                known.setdefault(child, child_identity[1])
                pending.append(child)
    for pid, ticks in reversed(list(known.items())):
        current = _process_identity(pid)
        if current is not None and current[1] == ticks:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    current = _process_identity(process.pid)
    if current is not None and known.get(process.pid) == current[1]:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_capture(command: list[str], *, cwd: Path, timeout: float, stdin: str = "",
                trace: bool = False, max_events: int = 0, source_lines: int = 0,
                extra_env: dict | None = None, python: bool = False) -> dict:
    """Drain bounded diagnostics and a separate, validated incremental protocol.

    Only trusted compiler/debugger/Python executables are used as commands. The
    inferior receives no parent environment. No shell is started by this helper.
    """
    started = time.monotonic()
    logs = {"stdout": bytearray(), "stderr": bytearray()}
    discarded = {"stdout": False, "stderr": False}
    lines = []
    ready = False
    termination = None
    error = None
    truncated = None
    buffer = bytearray()
    process = None
    read_fd = write_fd = None
    selector = selectors.DefaultSelector()
    known_processes = {}

    def fail(message, reason="collector_failed"):
        nonlocal error
        if error is None:
            error = {"reason": reason, "message": message}

    def record(value):
        nonlocal ready, termination, truncated
        if not isinstance(value, dict) or termination is not None:
            fail("Invalid event or data after termination")
            return
        kind = value.get("type")
        if kind == "ready" and not ready and set(value) == {"type"}:
            ready = True
        elif kind == "line" and ready and set(value) == {"type", "line"}:
            line = value["line"]
            if type(line) is not int or not 1 <= line <= source_lines:
                fail("Trace location is outside the evaluated candidate source")
            elif len(lines) == max_events:
                truncated = "event_limit"
            else:
                lines.append(line)
        elif kind == "process" and ready and not python and set(value) == {"type", "pid", "start_ticks"}:
            pid = value["pid"]
            current = _process_identity(pid) if type(pid) is int and pid > 1 else None
            ticks = value["start_ticks"]
            if (type(pid) is not int or pid <= 1 or not isinstance(ticks, str) or not ticks.isdigit()
                    or (current is not None and current[1] != ticks)):
                fail("Debugger reported an invalid inferior process")
            else:
                # A short-lived inferior may already have exited, or been
                # reparented after a debugger crash. Bind cleanup to start ticks.
                known_processes[pid] = ticks
        elif kind == "end" and ready and set(value) == {"type", "termination"}:
            item = value["termination"]
            if (not isinstance(item, dict) or item.get("kind") not in {"exit", "exception", "signal"}
                    or (item.get("exit_code") is not None and type(item["exit_code"]) is not int)
                    or (item.get("kind") == "signal" and not isinstance(item.get("signal"), str))):
                fail("Invalid program termination record")
            else:
                termination = item
        elif kind == "error" and value.get("reason") in {"collector_failed", "unsupported_execution"}:
            fail(str(value.get("message", "Collector failed"))[:1000], value["reason"])
        else:
            fail("Unexpected collector protocol record")

    try:
        with tempfile.TemporaryFile() as input_file:
            input_file.write(stdin.encode("utf-8"))
            input_file.seek(0)
            env = {**ENVIRONMENT, **(extra_env or {})}
            if trace:
                read_fd, write_fd = os.pipe()
                env["BTP_TRACE_FD"] = str(write_fd)
            try:
                process = subprocess.Popen(
                    command, cwd=str(cwd), env=env, stdin=input_file,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                    start_new_session=True, pass_fds=(() if write_fd is None else (write_fd,)),
                )
                current = _process_identity(process.pid)
                if current is not None:
                    known_processes[process.pid] = current[1]
            except OSError as exc:
                fail(f"{type(exc).__name__}: {exc}", "collector_launch_failed")
            finally:
                if write_fd is not None:
                    os.close(write_fd)
                    write_fd = None
            if process is not None:
                for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                if read_fd is not None:
                    os.set_blocking(read_fd, False)
                    selector.register(read_fd, selectors.EVENT_READ, "events")
                while selector.get_map():
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        truncated = "timeout"
                        break
                    if error is not None or truncated is not None:
                        break
                    for key, _mask in selector.select(min(remaining, 0.1)):
                        data = os.read(key.fd, 8192)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        if key.data != "events":
                            log = logs[key.data]
                            available = DIAGNOSTIC_LIMIT - len(log)
                            log.extend(data[:available])
                            discarded[key.data] |= len(data) > available
                            continue
                        buffer.extend(data)
                        while b"\n" in buffer and error is None and truncated is None:
                            raw, _, tail = buffer.partition(b"\n")
                            buffer = bytearray(tail)
                            if len(raw) > 8192:
                                fail("Collector record exceeds protocol limit")
                                break
                            try:
                                record(json.loads(raw))
                            except (ValueError, UnicodeError, TypeError, KeyError, RecursionError) as exc:
                                fail("Malformed collector protocol: " + str(exc)[:200])
                        if len(buffer) > 8192 and truncated is None:
                            fail("Unterminated collector record exceeds protocol limit")
                if error is None and truncated is None:
                    try:
                        process.wait(timeout=max(0.001, timeout - (time.monotonic() - started)))
                    except subprocess.TimeoutExpired:
                        truncated = "timeout"
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        fail(f"Collector I/O failed: {type(exc).__name__}: {exc}")
    finally:
        if process is not None:
            _cleanup(process, known_processes)
            process.stdout.close()
            process.stderr.close()
        selector.close()
        for fd in (read_fd, write_fd):
            if fd is not None:
                os.close(fd)

    exit_code = None if process is None else process.returncode
    if trace and error is None:
        if not ready:
            fail("Collector did not finish initialization")
        elif truncated is None and buffer:
            fail("Collector ended with an incomplete protocol record")
        elif truncated is None and termination is None:
            if python:
                # os._exit and fatal signals bypass the wrapper's final record.
                termination = {"kind": "exit", "exit_code": exit_code}
            else:
                fail("Debugger ended without a termination record")
        if python and truncated is None and error is None:
            if exit_code < 0:
                termination = {"kind": "signal", "signal": signal.Signals(-exit_code).name,
                               "exit_code": exit_code}
            else:
                termination = {**termination, "exit_code": exit_code}
        if not python and truncated is None and error is None and exit_code != 0:
            fail("Debugger failed after reporting program termination")
        if not lines:
            fail("Collector produced no candidate source-line events", "trace_empty")
    return {
        "lines": lines, "complete": error is None and truncated is None,
        "truncation_reason": truncated, "event_count": len(lines),
        "total_event_count": len(lines) if error is None and truncated is None else None,
        "termination": termination or {"kind": "collection_stopped", "reason": truncated},
        "error": error, "exit_code": exit_code, "duration_s": time.monotonic() - started,
        "diagnostics": {name: {"text": bytes(value).decode("utf-8", errors="surrogateescape"),
                               "truncated": discarded[name]}
                        for name, value in logs.items()},
    }
