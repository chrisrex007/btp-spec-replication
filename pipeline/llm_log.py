"""JSONL logging for every LLM invocation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


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
    endpoint: str,
    json_schema: dict | None,
    schema_name: str,
    error: dict | None = None,
) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "iteration": iteration,
        "step": step,
        "model": model,
        "endpoint": endpoint,
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "json_schema": json_schema,
        "schema_name": schema_name,
        "status": "error" if error is not None else "success",
        "response": response,
        "error": error,
        "latency_s": latency_s,
    }

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    log_path = run_path / "llm_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")
