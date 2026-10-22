"""Complete raw failures for direct candidate repair."""

CANDIDATE_FAILURES = {"output_mismatch", "candidate_timeout", "candidate_error"}


class RawFeedbackStrategy:
    def prepare(self, failures: list[dict]) -> list[dict]:
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
        return feedback
