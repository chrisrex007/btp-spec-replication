"""Process execution primitives for stdin/stdout benchmark programs.

This module intentionally provides execution, not full security isolation. It
avoids shell invocation, enforces a wall-clock timeout, and can run with a
sanitized environment, but stronger OS-level sandboxing is still future work.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Mapping, Sequence


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="surrogateescape")
    return value


@dataclass(frozen=True)
class ExecutionResult:
    """One invocation, with output decoded losslessly using UTF-8 surrogateescape.

    Encode stdout/stderr with the same codec and error handler to recover the
    original bytes. JSON writers must escape surrogate code points.
    """

    command: tuple[str, ...]
    stdin: str
    stdout: str
    stderr: str
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
        data = asdict(self)
        data["command"] = list(self.command)
        data["succeeded"] = self.succeeded
        return data


def run_program(
    command: Sequence[str],
    stdin_data: str,
    *,
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
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    cmd = tuple(str(part) for part in command)
    if inherit_env:
        run_env = None if env is None else {**os.environ, **dict(env)}
    else:
        run_env = {} if env is None else dict(env)

    started = time.monotonic()

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=None if cwd is None else str(cwd),
            env=run_env,
            shell=False,
            start_new_session=os.name == "posix",
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        try:
            stdout, stderr = proc.communicate(input=stdin_data.encode("utf-8"), timeout=timeout_seconds)
        finally:
            # Kill the owned session's process group even if its leader already
            # exited. Ordinary fork/spawn descendants must not survive a case.
            # Deliberately detached sessions require stronger OS isolation.
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                elif proc.poll() is None:
                    proc.kill()
            except ProcessLookupError:
                pass
            finally:
                proc.wait()
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    stream.close()
        return ExecutionResult(
            command=cmd,
            stdin=stdin_data,
            stdout=_as_text(stdout),
            stderr=_as_text(stderr),
            exit_code=proc.returncode,
            timed_out=False,
            duration_s=time.monotonic() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return ExecutionResult(
            command=cmd,
            stdin=stdin_data,
            stdout=_as_text(exc.stdout),
            stderr=_as_text(exc.stderr),
            exit_code=None,
            timed_out=True,
            duration_s=time.monotonic() - started,
        )
    except OSError as exc:
        return ExecutionResult(
            command=cmd,
            stdin=stdin_data,
            stdout="",
            stderr="",
            exit_code=None,
            timed_out=False,
            duration_s=time.monotonic() - started,
            launch_error=f"{type(exc).__name__}: {exc}",
        )
