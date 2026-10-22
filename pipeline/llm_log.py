"""Provenance for local inference requests, responses and failures."""
from dataclasses import asdict

from .artifacts import append_jsonl, digest, utc_now
from .offline_runtime import InferenceOutput, InferenceRequest


def request_record(request: InferenceRequest, runtime: dict) -> dict:
    identity = {"request": asdict(request), "runtime": runtime}
    return {"schema_version": 2, **identity, "fingerprint": digest(identity)}


def response_record(request: dict, output: InferenceOutput | None, *,
                    error: Exception | None = None, latency_s: float = 0.0,
                    batch_id: str | None = None, batch_size: int = 1) -> dict:
    payload = {
        "schema_version": 2, "request_fingerprint": request["fingerprint"],
        "timestamp": utc_now(), "status": "error" if error is not None else "success",
        "output": asdict(output) if output is not None else None,
        "error": {"type": type(error).__name__, "message": str(error)} if error is not None else None,
        "error_prompt_tokens": getattr(error, "prompt_tokens", None),
        "latency_s": latency_s, "batch_id": batch_id, "batch_size": batch_size,
    }
    return {**payload, "content_sha256": digest(payload)}


def log_call(path, request: dict, response: dict) -> None:
    append_jsonl(path, {"request": request, "response": response})
