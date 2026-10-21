"""Feedback strategies shared by direct candidate repair runners."""

CANDIDATE_FAILURES = {"output_mismatch", "candidate_timeout", "candidate_error"}


class RawFeedbackStrategy:
    kind = "raw"

    def prepare(self, failures: list[dict], limit: int) -> list[dict]:
        if type(limit) is not int or limit <= 0:
            raise ValueError("feedback limit must be a positive integer")
        feedback = []
        for item in failures:
            if item.get("status") not in CANDIDATE_FAILURES:
                continue
            reference = item["reference"]
            if reference.get("timed_out") or reference.get("launch_error") or reference.get("exit_code", 0) != 0:
                continue
            feedback.append({
                "input": item["input"], "status": item["status"],
                "reference_stdout": reference["stdout"],
                "candidate_stdout": item["candidate"]["stdout"],
            })
            if len(feedback) == limit:
                break
        return feedback
