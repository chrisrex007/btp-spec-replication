"""Initial candidate generation from a natural-language specification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .candidate import CandidateSource
from .llm_runtime import logged_call


PROMPT_PATH = Path(__file__).parent / "prompts" / "code_generation.txt"

CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["python", "cpp"]},
        "filename": {"type": "string"},
        "source": {"type": "string"},
    },
    "required": ["language", "filename", "source"],
    "additionalProperties": False,
}


def candidate_messages(*, specification: str, input_format: str) -> tuple[str, str]:
    """Build specification-only candidate prompts."""

    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    user_prompt = (
        "## Specification\n\n"
        + specification
        + "\n\n## Standard input format\n\n"
        + input_format
        + "\n\nGenerate the complete candidate implementation."
    )
    return system_prompt, user_prompt


def parse_candidate_response(raw: str) -> CandidateSource:
    """Parse and validate a structured candidate response."""

    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"language", "filename", "source"}:
        raise ValueError("Candidate response must contain language, filename and source only")
    if not isinstance(value["filename"], str) or not value["filename"]:
        raise ValueError("Candidate response must provide a filename")
    return CandidateSource.from_dict(value)


def generate_candidate(
    *,
    specification: str,
    input_format: str,
    run_dir: str | Path,
    target: str,
    seed: int = 42,
    temperature: float = 0.2,
    max_tokens: int = 8192,
    call_fn: Callable[..., str] = logged_call,
) -> CandidateSource:
    """Generate one Python or C++ stdin/stdout candidate."""

    system_prompt, user_prompt = candidate_messages(
        specification=specification,
        input_format=input_format,
    )

    raw = call_fn(
        run_dir=run_dir,
        step="initial_code_generation",
        target=target,
        iteration=0,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
        json_schema=CANDIDATE_SCHEMA,
        schema_name="candidate_program",
    )
    return parse_candidate_response(raw)
