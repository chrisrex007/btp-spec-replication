import json
import time
import urllib.error
import urllib.request

# On the dev laptop this points at an SSH tunnel (8174); running ON gpu74 it
# points straight at the local vLLM server (8100), which removes the tunnel --
# and every failure mode that came with it -- from the loop entirely.
import os

ENDPOINT = os.environ.get("BTP_LLM_ENDPOINT",
                          "http://127.0.0.1:8174/v1/chat/completions")
MODEL = "qwen2.5-32b"


def call(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 4096,
         seed: int = 42, json_schema: dict = None, schema_name: str = "response") -> str:
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
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    # The endpoint is reached through an SSH tunnel that can drop mid-run, which
    # would otherwise kill a multi-hour unattended loop on one transient error.
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]["content"]
        except urllib.error.URLError as e:
            last_err = e
            if attempt < 3:
                time.sleep(5 * (attempt + 1))
    raise last_err
