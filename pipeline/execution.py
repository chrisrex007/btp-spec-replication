"""Process execution primitives for stdin/stdout benchmark programs.

This module intentionally provides execution, not full security isolation. It
avoids shell invocation, enforces a wall-clock timeout, and can run with a
sanitized environment, but stronger OS-level sandboxing is still future work.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import math
import signal
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence

from .artifacts import CapturedText


@dataclass(frozen=True)
class ExecutionResult:
    """One invocation, with file-backed output decoded during JSON persistence.

    Persist to_dict() with artifacts.write_json: captured output is streamed as
    UTF-8 surrogateescape text with ASCII JSON escapes, preserving every byte.
    """

    command: tuple[str, ...]
    stdin: str
    stdout: CapturedText
    stderr: CapturedText
    exit_code: int | None
    timed_out: bool
    duration_s: float
    launch_error: str | None = None

    @property
    def succeeded(self) -> bool:
        return (
            self.launch_error is None
            and not self.timed_out
            and self.exit_code == 0
        )

    def to_dict(self) -> dict:
        data = dict(vars(self))
        data["command"] = list(self.command)
        data["succeeded"] = self.succeeded
        return data


def run_program(
    command: Sequence[str],
    stdin_data: str,
    *,
    output_dir: str | Path,
    timeout_seconds: float = 2.0,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    inherit_env: bool = True,
) -> ExecutionResult:
    """Run command once, feeding stdin_data to standard input.

    The function never uses a shell. Launch failures and timeouts are returned
    as data rather than raised, so one broken candidate cannot terminate an
    experiment harness.

    Set inherit_env=False for generated/untrusted candidates so API keys and
    other parent-process secrets are not passed through environment variables.
    """

    if not command:
        raise ValueError("command must contain at least one element")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    cmd = tuple(str(part) for part in command)
    if inherit_env:
        run_env = None if env is None else {**os.environ, **dict(env)}
    else:
        run_env = {} if env is None else dict(env)

    # Validate before launching any process. Never normalize stdin bytes.
    stdin_bytes = stdin_data.encode("utf-8")
    if os.name != "posix":
        raise RuntimeError("Process-group cleanup requires a POSIX host")
    capture_dir = Path(output_dir).resolve()
    capture_dir.mkdir(parents=True, exist_ok=True)
    stdout = CapturedText(capture_dir / "stdout.bin")
    stderr = CapturedText(capture_dir / "stderr.bin")
    started = time.monotonic()
    timed_out = False
    exit_code = None
    launch_error = None
    with stdout.path.open("xb") as out, stderr.path.open("xb") as err:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=out,
                stderr=err,
                cwd=None if cwd is None else str(cwd),
                env=run_env,
                shell=False,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            launch_error = f"{type(exc).__name__}: {exc}"
        else:
            try:
                proc.communicate(input=stdin_bytes, timeout=timeout_seconds)
                exit_code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
            finally:
                # Clean up descendants even if their parent exited successfully.
                # Descendants that deliberately escape the group require OS isolation.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    try:
                        if proc.stdin is not None:
                            proc.stdin.close()
                    except BrokenPipeError:
                        pass
                    finally:
                        proc.wait()

    return ExecutionResult(
        command=cmd,
        stdin=stdin_data,
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        timed_out=timed_out,
        duration_s=time.monotonic() - started,
        launch_error=launch_error,
    )
