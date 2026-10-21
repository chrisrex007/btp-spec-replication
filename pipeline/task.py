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
        if not self.name or self.name in {".", ".."} or not _TASK_NAME_RE.fullmatch(self.name):
            raise ValueError(
                "task name must contain only letters, digits, '.', '_' or '-'"
            )
        if not self.reference_command:
            raise ValueError("reference command must not be empty")
        if not self.input_format.strip():
            raise ValueError("input_format must not be empty")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")

    @classmethod
    def from_json(cls, path: str | Path) -> "BenchmarkTask":
        config_path = Path(path).resolve()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        base = config_path.parent

        reference = data["reference"]
        specification_path = (base / data["specification"]).resolve()
        reference_cwd = (base / reference.get("cwd", ".")).resolve()

        return cls(
            name=data["name"],
            specification_path=specification_path,
            reference_command=tuple(str(x) for x in reference["command"]),
            reference_cwd=reference_cwd,
            input_format=data["input_format"],
            timeout_seconds=float(data.get("timeout_seconds", 2.0)),
        )

    def read_specification(self) -> str:
        return self.specification_path.read_text(encoding="utf-8")

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
