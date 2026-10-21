import unittest
from pipeline.feedback import RawFeedbackStrategy
from pipeline.repair import repair_messages
from pipeline.candidate import CandidateSource


class FeedbackTests(unittest.TestCase):
    def test_whitelist_order_limit_and_reference_errors(self):
        def failure(value, status="output_mismatch"):
            return {"input": value, "status": status, "reference": {"stdout": "expected", "exit_code": 0, "command": "SECRET"}, "candidate": {"stdout": "actual", "stderr": "SECRET"}}
        result = RawFeedbackStrategy().prepare([failure("bad", "reference_error"), failure("first"), failure("second")], 1)
        self.assertEqual(result, [{"input": "first", "status": "output_mismatch", "reference_stdout": "expected", "candidate_stdout": "actual"}])
        self.assertNotIn("SECRET", str(result))

    def test_generic_feedback_prompt(self):
        _, prompt, _ = repair_messages(specification="spec", input_format="input", candidate=CandidateSource(language="python", filename="main.py", source="print(0)"), feedback_kind="abstract", feedback_text="class one")
        self.assertIn("abstract feedback", prompt)
        self.assertIn("class one", prompt)

