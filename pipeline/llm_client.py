"""One-shot schema-constrained requests to a vLLM-compatible chat server."""

from __future__ import annotations

import json
import math
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .env import load_dotenv


load_dotenv()

SAMPLING_SETTINGS = {
    "n": 1,
    "top_p": 1.0,
    "top_k": -1,
    "repetition_penalty": 1.0,
}


def get_model() -> str:
    """Return the server's configured served model name."""
    return os.environ.get("BTP_MODEL", "").strip()


def _configuration() -> tuple[str, float]:
    base = os.environ.get("BTP_BASE_URL", "http://127.0.0.1:8000/v1").strip()
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("BTP_BASE_URL must be an HTTP(S) base URL without credentials, query, or fragment")
    if not get_model():
        raise ValueError("BTP_MODEL is required; use the server's served model name")
    timeout = float(os.environ.get("BTP_HTTP_TIMEOUT", "1800"))
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("BTP_HTTP_TIMEOUT must be a finite positive number of seconds")
    return base.rstrip("/") + "/chat/completions", timeout


def inference_metadata() -> dict:
    """Record client settings; server internals cannot be inferred locally."""
    # Do not persist raw URLs: they may accidentally contain credentials.
    return {
        "backend": "vllm_http",
        "model_path": None,
        "runtime_versions": {"python": sys.version.split()[0]},
        "engine_settings": None,
        "sampling_settings": dict(SAMPLING_SETTINGS),
        "http_timeout_s": os.environ.get("BTP_HTTP_TIMEOUT", "1800"),
        "server_metadata": "Server model path, versions and launch settings must be retained separately",
    }


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def call(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
    *,
    completion_metadata: dict | None = None,
) -> str:
    """Request exactly one completion, without retries or model fallback."""
    if completion_metadata is not None:
        completion_metadata.clear()
    endpoint, timeout = _configuration()
    payload = {
        "model": get_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": False,
        **SAMPLING_SETTINGS,
    }
    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": json_schema},
        }
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Server error bodies and URLs may contain secrets; do not log them.
        status = exc.code
        exc.close()
        raise RuntimeError(f"Chat completion request failed with HTTP {status}") from None
    except URLError:
        raise RuntimeError("Chat completion server connection failed") from None
    if not isinstance(result, dict):
        raise RuntimeError("Chat completion response must be an object")
    choices = result.get("choices")
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise RuntimeError("Server did not return exactly one completion")
    completion = choices[0]
    if completion_metadata is not None:
        completion_metadata.update({
            "finish_reason": completion.get("finish_reason"),
            "stop_reason": completion.get("stop_reason"),
            "usage": result.get("usage"),
            "model": result.get("model"),
            "system_fingerprint": result.get("system_fingerprint"),
        })
    message = completion.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("content"), str):
        raise RuntimeError("Server completion does not contain text content")
    return message["content"]
