"""Single-call adapter over an invocation-owned local inference session."""
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
        "inference_metadata": llm_client.inference_metadata(),
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "json_schema": json_schema,
        "schema_name": schema_name,
    }
    completion_metadata = {}
    started = time.monotonic()
    try:
        model_path = llm_client.resolve_model_path()
        metadata["inference_metadata"]["model_path"] = str(model_path)
        response = llm_client.call(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            json_schema=json_schema,
            schema_name=schema_name,
            completion_metadata=completion_metadata,
        )
    except Exception as exc:
        llm_log.log_call(
            **metadata,
            response=None,
            completion_metadata=completion_metadata or None,
            latency_s=time.monotonic() - started,
            error={
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )
        raise

    llm_log.log_call(
        **metadata,
        response=response,
        completion_metadata=completion_metadata or None,
        latency_s=time.monotonic() - started,
    )
    if completion_metadata.get("finish_reason") == "length":
        raise ValueError(
            f"{step} reached its {max_tokens}-token output limit; "
            "the complete raw response and token usage are preserved in llm_log.jsonl"
        )
    return response
