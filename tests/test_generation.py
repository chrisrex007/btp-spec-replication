import json
import tempfile
import unittest

from pipeline.generator import generate_candidate
from pipeline.test_generator import generate_tests


class GenerationTests(unittest.TestCase):
    def test_candidate_generation_parses_structured_response(self):
        captured = {}

        def fake_call(**kwargs):
            captured.update(kwargs)
            return json.dumps(
                {
                    "language": "cpp",
                    "filename": "main.cpp",
                    "source": "#include <iostream>\nint main(){return 0;}\n",
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            candidate = generate_candidate(
                specification="Double an integer.",
                input_format="One integer.",
                run_dir=tmp,
                target="double",
                call_fn=fake_call,
            )

        self.assertEqual(candidate.language, "cpp")
        self.assertEqual(candidate.filename, "main.cpp")
        self.assertIn("int main", candidate.source)
        self.assertEqual(captured["step"], "initial_code_generation")
        self.assertNotIn("Standard output format", captured["user_prompt"])
        self.assertEqual(
            captured["json_schema"]["properties"]["language"]["enum"],
            ["python", "cpp"],
        )

    def test_test_generation_deduplicates_preserving_order(self):
        def fake_call(**kwargs):
            return json.dumps({"tests": ["1\n", "2\n", "1\n", "3\n"]})

        with tempfile.TemporaryDirectory() as tmp:
            tests = generate_tests(
                specification="Echo an integer.",
                input_format="One integer.",
                count=4,
                run_dir=tmp,
                target="echo",
                call_fn=fake_call,
            )

        self.assertEqual(tests, ["1\n", "2\n", "3\n"])

    def test_test_generation_rejects_nonpositive_count(self):
        with self.assertRaises(ValueError):
            generate_tests(
                specification="x",
                input_format="x",
                count=0,
                run_dir=".",
                target="x",
            )


if __name__ == "__main__":
    unittest.main()
