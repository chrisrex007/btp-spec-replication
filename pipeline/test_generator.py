"""Basic LLM test-input generation for stdin/stdout programs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .llm_runtime import logged_call


PROMPT_PATH = Path(__file__).parent / "prompts" / "test_generation.txt"


def _deduplicate_preserving_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def test_generation_request(
    *, specification: str, input_format: str, count: int
) -> tuple[str, str, dict]:
    """Build prompts and schema shared by online and offline test generation."""

    if count <= 0:
        raise ValueError("count must be positive")
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_prompt = (
        "## Specification\n\n"
        + specification
        + "\n\n## Standard input format\n\n"
        + input_format
        + f"\n\nGenerate exactly {count} complete standard-input test cases."
    )
    schema = {
        "type": "object",
        "properties": {
            "tests": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": count,
                "maxItems": count,
            }
        },
        "required": ["tests"],
        "additionalProperties": False,
    }
    return system_prompt, user_prompt, schema


def parse_tests_response(raw: str) -> list[str]:
    """Parse test inputs and remove exact duplicates, preserving order."""

    tests = json.loads(raw)["tests"]
    if not isinstance(tests, list) or not all(isinstance(item, str) for item in tests):
        raise ValueError("LLM test response must contain a string array")
    unique = _deduplicate_preserving_order(tests)
    if not unique:
        raise ValueError("LLM produced no usable testcases")
    return unique


def generate_tests(
    *,
    specification: str,
    input_format: str,
    count: int,
    run_dir: str | Path,
    target: str,
    seed: int = 42,
    call_fn: Callable[..., str] = logged_call,
) -> list[str]:
    """Generate complete stdin payloads and remove exact duplicates."""

    system_prompt, user_prompt, schema = test_generation_request(
        specification=specification,
        input_format=input_format,
        count=count,
    )

    raw = call_fn(
        run_dir=run_dir,
        step="test_generation",
        target=target,
        iteration=0,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.6,
        max_tokens=12000,
        seed=seed,
        json_schema=schema,
        schema_name="test_inputs",
    )
    return parse_tests_response(raw)
