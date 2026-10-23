"""Build Python/C++ candidates into runnable commands."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import uuid

from .artifacts import atomic_bytes
from .candidate import CandidateSource
from .execution import run_program


@dataclass(frozen=True)
class BuildResult:
    success: bool
    language: str
    source_path: str
    run_command: tuple[str, ...] | None
    build_stdout: str = ""
    build_stderr: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "language": self.language,
            "source_path": self.source_path,
            "run_command": (
                None if self.run_command is None else list(self.run_command)
            ),
            "build_stdout": self.build_stdout,
            "build_stderr": self.build_stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "error": self.error,
        }


def build_candidate(
    candidate: CandidateSource,
    build_dir: str | Path,
    *,
    cpp_compiler: str | None = None,
    compile_timeout_seconds: float = 30.0,
) -> BuildResult:
    """Materialize candidate and return the command used to run it.

    Python is syntax-checked without executing it. C++ is compiled as C++20
    with optimization enabled. Build failures are returned as data.
    """

    if compile_timeout_seconds <= 0:
        raise ValueError("compile_timeout_seconds must be positive")

    out_dir = Path(build_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_path = (out_dir / candidate.filename).resolve()
    atomic_bytes(source_path, candidate.source.encode("utf-8"))

    if candidate.language == "python":
        try:
            compile(candidate.source, str(source_path), "exec", dont_inherit=True)
        except (SyntaxError, ValueError) as exc:
            return BuildResult(
                success=False, language=candidate.language, source_path=str(source_path),
                run_command=None, error=f"{type(exc).__name__}: {exc}",
            )
        return BuildResult(
            success=True,
            language=candidate.language,
            source_path=str(source_path),
            run_command=(sys.executable, str(source_path)),
        )

    compiler = cpp_compiler or os.environ.get("CXX", "g++")
    executable_name = "program.exe" if os.name == "nt" else "program"
    executable_path = (out_dir / executable_name).resolve()
    temporary_executable = executable_path.with_name(
        executable_path.stem + "." + uuid.uuid4().hex + executable_path.suffix)
    compile_command = (
        compiler,
        "-O2",
        "-std=c++20",
        str(source_path),
        "-o",
        str(temporary_executable),
    )
    try:
        result = run_program(
            compile_command,
            "",
            timeout_seconds=compile_timeout_seconds,
        )
        if result.succeeded:
            os.replace(temporary_executable, executable_path)
    finally:
        temporary_executable.unlink(missing_ok=True)

    if not result.succeeded:
        return BuildResult(
            success=False,
            language=candidate.language,
            source_path=str(source_path),
            run_command=None,
            build_stdout=result.stdout,
            build_stderr=result.stderr,
            exit_code=result.exit_code,
            timed_out=result.timed_out,
            error=result.launch_error,
        )

    return BuildResult(
        success=True,
        language=candidate.language,
        source_path=str(source_path),
        run_command=(str(executable_path),),
        build_stdout=result.stdout,
        build_stderr=result.stderr,
        exit_code=result.exit_code,
    )
