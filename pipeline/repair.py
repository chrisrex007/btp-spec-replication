"""Raw differential-failure feedback for direct candidate repair."""

from __future__ import annotations

import json
from pathlib import Path

from .candidate import CandidateSource
from .generator import CANDIDATE_SCHEMA


PROMPT_PATH = Path(__file__).parent / "prompts" / "repair.txt"


def repair_messages(
    *,
    specification: str,
    input_format: str,
    candidate: CandidateSource,
    failures: list[dict] | None = None,
    feedback_kind: str = "raw",
    feedback_text: str | None = None,
) -> tuple[str, str, dict]:
    """Create a direct repair request from the current candidate and failures."""

    failure_text = feedback_text if feedback_text is not None else json.dumps(failures or [], ensure_ascii=False, indent=2)
    user_prompt = (
        "## Specification\n\n"
        + specification
        + "\n\n## Standard input format\n\n"
        + input_format
        + "\n\n## Current candidate\n\n"
        + f"Language: {candidate.language}\nFilename: {candidate.filename}\n"
        + "```\n"
        + candidate.source
        + f"\n```\n\n## {feedback_kind} feedback\n\n"
        + failure_text
        + "\n\nReturn a complete repaired implementation."
    )
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    if feedback_kind != "raw":
        system_prompt = system_prompt.replace("raw\ndifferential-testing failures", f"{feedback_kind}\nfeedback")
    return system_prompt, user_prompt, CANDIDATE_SCHEMA
