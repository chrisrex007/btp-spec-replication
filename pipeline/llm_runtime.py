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
    """Call the configured LLM and persist the complete request/response."""

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    response = llm_client.call(
        system_prompt,
        user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
        json_schema=json_schema,
        schema_name=schema_name,
    )
    latency_s = time.monotonic() - started

    llm_log.log_call(
        run_dir=run_path,
        step=step,
        target=target,
        iteration=iteration,
        model=llm_client.MODEL,
        seed=seed,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response=response,
        latency_s=latency_s,
    )
    return response
