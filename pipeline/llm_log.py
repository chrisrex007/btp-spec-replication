"""JSONL logging for every LLM invocation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .artifacts import ArtifactPersistenceError


def _append_record(run_dir: Path, filename: str, record: dict) -> None:
    log_path = Path(run_dir) / filename
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        raise ArtifactPersistenceError(f"Could not persist {log_path}: {exc}") from exc


def log_request(
    *,
    run_dir: Path,
    request_id: str,
    step: str,
    target: str,
    iteration: int,
    model: str,
    seed: int,
    temperature: float,
    max_tokens: int,
    system_prompt: str,
    user_prompt: str,
    inference_metadata: dict,
    json_schema: dict | None,
    schema_name: str,
) -> None:
    """Persist a pending request before any model resolution or inference."""
    _append_record(run_dir, "llm_requests.jsonl", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "target": target,
        "iteration": iteration,
        "step": step,
        "model": model,
        "inference": inference_metadata,
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "json_schema": json_schema,
        "schema_name": schema_name,
        "status": "pending",
    })


def log_call(
    run_dir: Path,
    step: str,
    target: str,
    iteration,
    model: str,
    seed,
    temperature,
    max_tokens,
    system_prompt: str,
    user_prompt: str,
    response: str | None,
    latency_s: float,
    *,
    request_id: str,
    inference_metadata: dict,
    json_schema: dict | None,
    schema_name: str,
    error: dict | None = None,
    completion_metadata: dict | None = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "target": target,
        "iteration": iteration,
        "step": step,
        "model": model,
        "inference": inference_metadata,
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "json_schema": json_schema,
        "schema_name": schema_name,
        "status": ("interrupted" if error and error["type"] == "KeyboardInterrupt"
                   else "error" if error is not None else "success"),
        "response": response,
        "completion": completion_metadata,
        "error": error,
        "latency_s": latency_s,
    }

    _append_record(run_dir, "llm_log.jsonl", record)
