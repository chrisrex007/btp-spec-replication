"""Versioned task checkpoints with atomic publication and artifact integrity."""
from __future__ import annotations

from pathlib import Path

from .artifacts import atomic_bytes, atomic_json, digest, file_digest, json_text, read_json, utc_now


class CheckpointError(ValueError):
    pass


def checked_payload(value: dict) -> dict:
    return {**value, "content_sha256": digest(value)}


def verify_payload(value: object, label: str) -> dict:
    if not isinstance(value, dict) or value.get("schema_version") != 2:
        raise CheckpointError(f"{label}: checkpoint schema version 2 is required; use a new run")
    payload = {k: v for k, v in value.items() if k != "content_sha256"}
    if value.get("content_sha256") != digest(payload):
        raise CheckpointError(f"{label}: checksum mismatch")
    return payload


class TaskCheckpoint:
    def __init__(self, root: Path, state: dict) -> None:
        self.root = root.resolve()
        self.state = state

    def path(self, relative: str) -> Path:
        requested = Path(relative)
        if requested.is_absolute() or ".." in requested.parts:
            raise CheckpointError("Artifact path must stay within its task directory")
        path = (self.root / requested).resolve()
        if not path.is_relative_to(self.root):
            raise CheckpointError("Artifact path escapes its task directory")
        return path

    def validate(self) -> None:
        if not isinstance(self.state.get("artifacts"), dict):
            raise CheckpointError("Invalid artifact manifest")
        for relative, expected in self.state["artifacts"].items():
            path = self.path(relative)
            if not path.is_file() or file_digest(path) != expected:
                raise CheckpointError(f"Missing or changed artifact: {path}")

    def track(self, relative: str) -> None:
        path = self.path(relative)
        actual = file_digest(path)
        expected = self.state["artifacts"].get(relative)
        if expected is not None and expected != actual:
            raise CheckpointError(f"Artifact changed after publication: {path}")
        self.state["artifacts"][relative] = actual

    def write_bytes(self, relative: str, value: bytes) -> None:
        path = self.path(relative)
        if relative in self.state["artifacts"]:
            self.validate()
            if path.read_bytes() != value:
                raise CheckpointError(f"Refusing to replace a published artifact: {path}")
            return
        atomic_bytes(path, value)
        self.track(relative)

    def write_json(self, relative: str, value: object) -> None:
        self.write_bytes(relative, json_text(value).encode("utf-8"))

    def read_json(self, relative: str):
        if relative not in self.state["artifacts"]:
            raise CheckpointError(f"Artifact is not committed: {relative}")
        path = self.path(relative)
        if file_digest(path) != self.state["artifacts"][relative]:
            raise CheckpointError(f"Changed artifact: {path}")
        return read_json(path)

    def save(self) -> None:
        self.state["updated_at"] = utc_now()
        atomic_json(self.root / "state.json", checked_payload(self.state))

    @classmethod
    def load(cls, root: Path, task: str, budget: int):
        state = verify_payload(read_json(root / "state.json"), str(root / "state.json"))
        stages = {"candidate_request", "candidate_response", "tests_request", "tests_response",
                  "trace_prepare", "trace_collect",
                  "repair_request", "repair_response", "evaluate", "completed", "failed"}
        attempted, evaluated = state.get("attempted_iteration"), state.get("last_evaluated_iteration")
        if (state.get("task") != task or state.get("stage") not in stages
                or type(attempted) is not int or not 0 <= attempted <= budget
                or (evaluated is not None and (type(evaluated) is not int or not 0 <= evaluated <= attempted))):
            raise CheckpointError("Invalid task checkpoint state")
        if state["stage"] in {"trace_prepare", "trace_collect"} and (
                evaluated is None or attempted != evaluated or evaluated >= budget):
            raise CheckpointError("Tracing must refer to an evaluated round with repair budget remaining")
        result = cls(root, state)
        result.validate()
        return result
