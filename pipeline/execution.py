"""Process execution primitives for stdin/stdout benchmark programs.

This module intentionally provides execution, not security isolation. It avoids
shell invocation and enforces a wall-clock timeout, but a stronger sandbox or
resource-limiting layer can be added later without changing callers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence


def _as_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


@dataclass(frozen=True)
class ExecutionResult:
    """Complete observable result of one program invocation."""

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
) -> ExecutionResult:
    """Run command once, feeding stdin_data to standard input.

    The function never uses a shell. Launch failures and timeouts are returned
    as data rather than raised, so one broken candidate cannot terminate an
    experiment harness.
    """

    if not command:
        raise ValueError("command must contain at least one element")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    cmd = tuple(str(part) for part in command)
    run_env = None if env is None else {**os.environ, **dict(env)}
    started = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            input=stdin_data,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            cwd=None if cwd is None else str(cwd),
            env=run_env,
            shell=False,
            check=False,
        )
        return ExecutionResult(
            command=cmd,
            stdin=stdin_data,
            stdout=proc.stdout,
            stderr=proc.stderr,
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
