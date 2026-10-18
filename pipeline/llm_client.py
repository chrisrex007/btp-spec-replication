"""Minimal OpenAI-compatible chat-completions client for local LLM serving."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request


ENDPOINT = os.environ.get(
    "BTP_LLM_ENDPOINT",
    "http://127.0.0.1:8174/v1/chat/completions",
)
MODEL = os.environ.get("BTP_MODEL", "qwen2.5-32b")


def call(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
) -> str:
    """Call an OpenAI-compatible /v1/chat/completions endpoint."""

    payload = {
        "model": MODEL,
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
            "json_schema": {"name": schema_name, "schema": json_schema},
        }

    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_error: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = json.loads(response.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(5 * (attempt + 1))

    assert last_error is not None
    raise last_error
