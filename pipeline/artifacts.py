"""Lossless, bounded-memory JSON persistence for captured process output."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class CapturedText:
    path: Path

    def chunks(self):
        with self.path.open("r", encoding="utf-8", errors="surrogateescape", newline="") as handle:
            while chunk := handle.read(65536):
                yield chunk


def outputs_equal(left: CapturedText, right: CapturedText) -> bool:
    with left.path.open("rb") as a, right.path.open("rb") as b:
        while True:
            x, y = a.read(65536), b.read(65536)
            if x != y:
                return False
            if not x:
                return True


def _write_value(handle, value):
    if isinstance(value, CapturedText):
        handle.write('"')
        for chunk in value.chunks():
            handle.write(json.dumps(chunk, ensure_ascii=True)[1:-1])
        handle.write('"')
    elif isinstance(value, dict):
        handle.write("{")
        for index, (key, item) in enumerate(value.items()):
            if index:
                handle.write(",")
            handle.write(json.dumps(key, ensure_ascii=True) + ":")
            _write_value(handle, item)
        handle.write("}")
    elif isinstance(value, (list, tuple)):
        handle.write("[")
        for index, item in enumerate(value):
            if index:
                handle.write(",")
            _write_value(handle, item)
        handle.write("]")
    else:
        handle.write(json.dumps(value, ensure_ascii=True))


def write_json(path: Path, value) -> None:
    """Replace a JSON artifact only after its complete contents have been written."""
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        _write_value(handle, value)
        handle.write("\n")
    temporary.replace(path)
