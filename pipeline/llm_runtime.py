"""Single-call adapter over an invocation-owned local inference session."""
from pathlib import Path
import sys
import time
import uuid

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
    max_tokens: int = 8192,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
    session: llm_client.InferenceSession | None = None,
) -> str:
    """Record a logical LLM call, including request schema and failure details."""

    run_path = Path(run_dir)
    run_path.mkdir(parents=True, exist_ok=True)
    if session is None:
        session = llm_client.InferenceSession()

    metadata = {
        "run_dir": run_path,
        "request_id": uuid.uuid4().hex,
        "step": step,
        "target": target,
        "iteration": iteration,
        "model": session.model,
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
    response = None
    started = time.monotonic()
    try:
        llm_log.log_request(**metadata)
        started = time.monotonic()
        model_path = session.resolve_model_path()
        metadata["inference_metadata"]["model_path"] = str(model_path)
        response = session.call(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            json_schema=json_schema,
            schema_name=schema_name,
            completion_metadata=completion_metadata,
        )
        llm_log.log_call(
            **metadata,
            response=response,
            completion_metadata=completion_metadata or None,
            latency_s=time.monotonic() - started,
        )
    except (Exception, KeyboardInterrupt) as exc:
        try:
            llm_log.log_call(
                **metadata,
                response=response,
                completion_metadata=completion_metadata or None,
                latency_s=time.monotonic() - started,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
        except (Exception, KeyboardInterrupt) as log_exc:
            print(
                f"Could not persist LLM failure for {metadata['request_id']}: "
                f"{type(log_exc).__name__}: {log_exc}; "
                f"original error: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            if isinstance(log_exc, KeyboardInterrupt) and not isinstance(exc, KeyboardInterrupt):
                raise KeyboardInterrupt(
                    f"Interrupted while recording {type(exc).__name__}: {exc}"
                ) from exc
        raise

    if completion_metadata.get("finish_reason") == "length":
        raise ValueError(
            f"{step} reached its {max_tokens}-token output limit; "
            "the complete raw response and token usage are preserved in llm_log.jsonl"
        )
    return response
