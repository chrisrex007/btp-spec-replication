"""Benchmark task configuration for stdin/stdout replication."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re


_TASK_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class BenchmarkTask:
    name: str
    specification_path: Path
    reference_command: tuple[str, ...]
    reference_cwd: Path
    input_format: str
    timeout_seconds: float = 2.0

    def __post_init__(self) -> None:
        if (not isinstance(self.name, str) or not self.name or self.name in {".", ".."}
                or not _TASK_NAME_RE.fullmatch(self.name)):
            raise ValueError(
                "task name must contain only letters, digits, '.', '_' or '-'"
            )
        if (not isinstance(self.reference_command, tuple) or not self.reference_command
                or not all(isinstance(part, str) and part for part in self.reference_command)):
            raise ValueError("reference command must not be empty")
        if not isinstance(self.input_format, str) or not self.input_format.strip():
            raise ValueError("input_format must not be empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")

    @classmethod
    def from_json(cls, path: str | Path) -> "BenchmarkTask":
        config_path = Path(path).resolve()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("task configuration must be a JSON object")
        base = config_path.parent

        reference = data["reference"]
        if (not isinstance(reference, dict) or not isinstance(reference.get("command"), list)
                or not reference["command"]):
            raise ValueError("reference.command must be a nonempty array of strings")
        specification_path = (base / data["specification"]).resolve()
        reference_cwd = (base / reference.get("cwd", ".")).resolve()
        if not specification_path.is_file() or not reference_cwd.is_dir():
            raise ValueError("specification file and reference working directory must exist")

        return cls(
            name=data["name"],
            specification_path=specification_path,
            reference_command=tuple(reference["command"]),
            reference_cwd=reference_cwd,
            input_format=data["input_format"],
            timeout_seconds=float(data.get("timeout_seconds", 2.0)),
        )

    def read_specification(self) -> str:
        specification = self.specification_path.read_text(encoding="utf-8")
        if not specification.strip():
            raise ValueError("specification must not be empty")
        return specification

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "specification_path": str(self.specification_path),
            "reference": {
                "command": list(self.reference_command),
                "cwd": str(self.reference_cwd),
            },
            "input_format": self.input_format,
            "timeout_seconds": self.timeout_seconds,
        }
