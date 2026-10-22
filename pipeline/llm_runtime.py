"""Shared helper for logged LLM calls."""

from __future__ import annotations

from pathlib import Path
import time

from . import llm_client, llm_log


def logged_call(
    *,
    run_dir: str | Path,
    step: str,
    target: str,
    iteration: int,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
) -> str:
    """Record a logical LLM call, including request schema and failure details."""

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    metadata = {
        "run_dir": run_path,
        "step": step,
        "target": target,
        "iteration": iteration,
        "model": llm_client.get_model(),
        "endpoint": llm_client.get_log_endpoint(),
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "json_schema": json_schema,
        "schema_name": schema_name,
    }
    started = time.monotonic()
    try:
        response = llm_client.call(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            json_schema=json_schema,
            schema_name=schema_name,
        )
    except Exception as exc:
        llm_log.log_call(
            **metadata,
            response=None,
            latency_s=time.monotonic() - started,
            error={
                "type": type(exc).__name__,
                "message": llm_client.redact_diagnostic(str(exc)),
            },
        )
        raise

    llm_log.log_call(
        **metadata, response=response, latency_s=time.monotonic() - started
    )
    return response
