"""Behavioural failure classes with mechanically checked evidence coverage."""
from __future__ import annotations

import json
from pathlib import Path


PROMPT_PATH = Path(__file__).parent / "prompts" / "abstraction.txt"
_TEXT_FIELDS = ("label", "observed_behavior", "expected_behavior")
ABSTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "classes": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    **{field: {"type": "string", "minLength": 1} for field in _TEXT_FIELDS},
                    "case_ids": {
                        "type": "array", "minItems": 1,
                        "items": {"type": "integer", "minimum": 0},
                    },
                },
                "required": [*_TEXT_FIELDS, "case_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["classes"],
    "additionalProperties": False,
}


class AbstractionParseError(ValueError):
    """The response does not have the required JSON structure."""


class AbstractionValidationError(ValueError):
    """Evidence references are invalid or fail to cover all observed failures."""


def abstraction_messages(*, specification: str, input_format: str,
                         failures: list[dict]) -> tuple[str, str, dict]:
    user_prompt = (
        "## Specification\n\n" + specification
        + "\n\n## Standard input format\n\n" + input_format
        + "\n\n## Current round raw failures\n\n"
        + json.dumps(failures, ensure_ascii=True, indent=2)
        + "\n\nReturn behavioural classes covering every supplied case_id."
    )
    return PROMPT_PATH.read_text(encoding="utf-8"), user_prompt, ABSTRACTION_SCHEMA


def parse_abstraction_response(raw: str, failures: list[dict]) -> dict:
    """Check shape and evidence membership, not semantic truth of descriptions."""
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise AbstractionParseError(f"Invalid abstraction JSON: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {"classes"}:
        raise AbstractionParseError("Abstraction must contain only a classes array")
    classes = value["classes"]
    if not isinstance(classes, list) or not classes:
        raise AbstractionParseError("Abstraction must contain at least one class")
    expected_fields = {*_TEXT_FIELDS, "case_ids"}
    eligible = {item["case_id"] for item in failures}
    covered = set()
    for index, item in enumerate(classes):
        if not isinstance(item, dict) or set(item) != expected_fields:
            raise AbstractionParseError(f"Class {index} must contain {sorted(expected_fields)} only")
        for field in _TEXT_FIELDS:
            if not isinstance(item[field], str) or not item[field].strip():
                raise AbstractionParseError(f"Class {index}: {field} must be nonblank text")
        ids = item["case_ids"]
        if not isinstance(ids, list) or not ids or any(type(case_id) is not int for case_id in ids):
            raise AbstractionParseError(f"Class {index}: case_ids must be a nonempty integer array")
        if len(set(ids)) != len(ids):
            raise AbstractionValidationError(f"Class {index}: duplicate case IDs")
        unknown = set(ids) - eligible
        if unknown:
            raise AbstractionValidationError(f"Class {index}: unknown case IDs {sorted(unknown)}")
        covered.update(ids)
    missing = eligible - covered
    if missing:
        raise AbstractionValidationError(f"Uncovered failure case IDs: {sorted(missing)}")
    return value
