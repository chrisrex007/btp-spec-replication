"""Single-call adapter over an invocation-owned local inference session."""
from pathlib import Path
import time

from .artifacts import atomic_json
from .llm_log import log_call, request_record, response_record
from .offline_runtime import InferenceRequest, InferenceSession, default_config


def logged_call(*, run_dir, step: str, target: str, iteration: int,
                system_prompt: str, user_prompt: str, temperature: float = 0.2,
                max_tokens: int = 4096, seed: int = 42, json_schema: dict | None = None,
                schema_name: str = "response", session: InferenceSession | None = None) -> str:
    session = session or InferenceSession(default_config())
    request = InferenceRequest(target, step, iteration, system_prompt, user_prompt,
                               json_schema or {}, temperature, max_tokens, seed, schema_name)
    record = request_record(request, session.identity)
    base = Path(run_dir) / "inference" / f"iteration-{iteration:03d}-{step}"
    atomic_json(str(base) + ".request.json", record)
    started = time.monotonic()
    try:
        outputs = session.generate_batch([request])
        if len(outputs) != 1 or not isinstance(outputs[0].response, str):
            raise RuntimeError("Expected one string response from the local runtime")
        response = response_record(record, outputs[0], latency_s=time.monotonic() - started)
    except Exception as exc:
        response = response_record(record, None, error=exc, latency_s=time.monotonic() - started)
        atomic_json(str(base) + ".error.json", response)
        log_call(Path(run_dir) / "llm_log.jsonl", record, response)
        raise
    atomic_json(str(base) + ".response.json", response)
    log_call(Path(run_dir) / "llm_log.jsonl", record, response)
    return outputs[0].response
