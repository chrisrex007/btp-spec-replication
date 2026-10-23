"""Ordered, case-indexed raw evidence for candidate path feedback."""

CANDIDATE_FAILURES = {"output_mismatch", "candidate_timeout", "candidate_error"}


def raw_feedback(results: list[dict]) -> list[dict]:
    """Index the full ordered evaluation, rather than renumbering its failures."""
    feedback = []
    for case_id, item in enumerate(results):
        if item.get("status") not in CANDIDATE_FAILURES:
            continue
        reference = item["reference"]
        if reference.get("timed_out") or reference.get("launch_error") or reference.get("exit_code", 0) != 0:
            continue
        feedback.append({
            "case_id": case_id, "input": item["input"], "status": item["status"],
            "reference_stdout": reference["stdout"],
            "candidate_stdout": item["candidate"]["stdout"],
        })
    return feedback
