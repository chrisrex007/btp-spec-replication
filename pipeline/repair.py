"""Raw differential-failure feedback for direct candidate repair."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from .candidate import CandidateSource
from .generator import CANDIDATE_SCHEMA


PROMPT_PATH = Path(__file__).parent / "prompts" / "repair.txt"


def repair_messages(
    *,
    specification: str,
    input_format: str,
    candidate: CandidateSource,
    failures: list[dict],
) -> tuple[str, str, dict]:
    """Create a direct repair request from the current candidate and failures."""

    failure_text = json.dumps(failures, ensure_ascii=True, indent=2)
    user_prompt = (
        "## Specification\n\n"
        + specification
        + "\n\n## Standard input format\n\n"
        + input_format
        + "\n\n## Current candidate\n\n"
        + f"Language: {candidate.language}\nFilename: {candidate.filename}\n"
        + "```\n"
        + candidate.source
        + "\n```\n\n## Raw feedback\n\n"
        + failure_text
        + "\n\nReturn a complete repaired implementation."
    )
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    schema = deepcopy(CANDIDATE_SCHEMA)
    schema["properties"]["language"]["enum"] = [candidate.language]
    return system_prompt, user_prompt, schema
