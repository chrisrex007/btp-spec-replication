"""Atomic experiment artifacts and provenance-checked offline inference cache."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import uuid

from .offline_runtime import InferenceRequest


def atomic_json(path: Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def implementation_digest() -> str:
    root = Path(__file__).parent
    return digest({path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                   for path in sorted(root.rglob("*")) if path.suffix in {".py", ".txt"}})


class CachedInference:
    def __init__(self, runtime=None, runtime_factory=None, *, model: str):
        self.runtime = runtime
        self.runtime_factory = runtime_factory
        self.model = model

    def generate(self, items: list[tuple[Path, InferenceRequest]]) -> dict[str, str]:
        results = {}
        pending = {}
        seen = set()
        # Validate the entire cache before starting expensive inference.
        for path, request in items:
            path = Path(path)
            key = str(path)
            if key in seen:
                raise ValueError(f"duplicate inference artifact path: {path}")
            seen.add(key)
            identity = {"model": self.model, "request": asdict(request)}
            fingerprint = digest(identity)
            if path.exists():
                record = read_json(path)
                if (not isinstance(record, dict) or record.get("fingerprint") != fingerprint
                        or record.get("model") != self.model or record.get("request") != asdict(request)
                        or not isinstance(record.get("response"), str)
                        or record.get("response_sha256") != digest(record.get("response"))):
                    raise ValueError(f"inference checkpoint mismatch or corruption: {path}")
                results[key] = record["response"]
                continue
            group = digest({"temperature": request.temperature, "max_tokens": request.max_tokens,
                            "seed": request.seed, "schema": request.schema})
            pending.setdefault(group, []).append((path, request, identity, fingerprint))
        if pending and self.runtime is None:
            if self.runtime_factory is None:
                raise ValueError("pending inference requires runtime or runtime_factory")
            self.runtime = self.runtime_factory()
        for batch in pending.values():
            batch_id = uuid.uuid4().hex
            try:
                outputs = self.runtime.generate_batch([item[1] for item in batch])
                if len(outputs) != len(batch):
                    raise RuntimeError("runtime output count differs from request count")
                if any(not isinstance(output.response, str) for output in outputs):
                    raise RuntimeError("runtime responses must be strings")
            except Exception as exc:
                for path, _, identity, fingerprint in batch:
                    atomic_json(path.with_suffix(path.suffix + ".error.json"), {
                        **identity, "fingerprint": fingerprint, "batch_id": batch_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
                raise
            for (path, _, identity, fingerprint), output in zip(batch, outputs):
                atomic_json(path, {**identity, "fingerprint": fingerprint,
                                  "response": output.response, "response_sha256": digest(output.response), "batch_id": batch_id,
                                  "batch_size": len(batch),
                                  "latency_s": getattr(output, "latency_s", None),
                                  "batch_latency_s": getattr(output, "batch_latency_s", None),
                                  "prompt_tokens": getattr(output, "prompt_tokens", None),
                                  "completion_tokens": getattr(output, "completion_tokens", None)})
                results[str(path)] = output.response
        return results
