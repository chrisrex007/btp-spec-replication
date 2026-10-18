"""Minimal OpenAI-compatible chat-completions client."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from .env import load_dotenv


load_dotenv()

DEFAULT_ENDPOINT = "http://127.0.0.1:8174/v1/chat/completions"
DEFAULT_MODEL = "qwen2.5-32b"


def get_endpoint() -> str:
    return os.environ.get("BTP_LLM_ENDPOINT", DEFAULT_ENDPOINT)


def get_model() -> str:
    return os.environ.get("BTP_MODEL", DEFAULT_MODEL)


def _build_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}

    api_key = os.environ.get("BTP_LLM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    http_referer = os.environ.get("BTP_HTTP_REFERER")
    if http_referer:
        headers["HTTP-Referer"] = http_referer

    x_title = os.environ.get("BTP_X_TITLE")
    if x_title:
        headers["X-Title"] = x_title

    return headers


def call(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
) -> str:
    """Call the configured OpenAI-compatible /v1/chat/completions endpoint."""

    endpoint = get_endpoint()
    payload = {
        "model": get_model(),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
    }

    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            },
        }

        # OpenRouter can route only to providers that actually honor parameters
        # such as response_format when this flag is enabled.
        if "openrouter.ai" in endpoint:
            payload["provider"] = {"require_parameters": True}

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=_build_headers(),
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = json.loads(response.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"LLM API returned HTTP {exc.code}: {detail or exc.reason}"
            )

            # Configuration/auth/schema errors should fail immediately.
            if exc.code in {400, 401, 402, 403, 404, 422}:
                raise last_error from exc

            if attempt < 3:
                time.sleep(5 * (attempt + 1))

        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(5 * (attempt + 1))

    assert last_error is not None
    raise last_error
