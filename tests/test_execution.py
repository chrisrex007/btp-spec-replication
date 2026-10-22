import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipeline.differential import ComparisonStatus, run_differential_case, write_results
from pipeline.execution import run_program


class ExecutionTests(unittest.TestCase):
    def test_stdin_carriage_returns_are_preserved(self):
        payload = "first\r\nsecond\rthird\n"
        result = run_program(
            [sys.executable, "-c",
             "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
            payload,
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, payload)

    def test_timeout_output_is_lossless(self):
        error = subprocess.TimeoutExpired(
            ["program"], 1, output=b"partial\r\n\xff", stderr=b"diagnostic\xfe"
        )
        with patch("pipeline.execution.subprocess.run", side_effect=error):
            result = run_program(["program"], "")
        self.assertTrue(result.timed_out)
        self.assertEqual(result.stdout.encode("utf-8", "surrogateescape"),
                         b"partial\r\n\xff")
        self.assertEqual(result.stderr.encode("utf-8", "surrogateescape"),
                         b"diagnostic\xfe")

    def test_stdin_stdout_capture(self):
        result = run_program(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write(sys.stdin.read().upper())",
            ],
            "hello\n",
        )
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, "HELLO" + os.linesep)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.exit_code, 0)
        self.assertFalse(result.timed_out)

    def test_timeout_is_data_not_exception(self):
        result = run_program(
            [sys.executable, "-c", "import time; time.sleep(1)"],
            "",
            timeout_seconds=0.05,
        )
        self.assertTrue(result.timed_out)
        self.assertFalse(result.succeeded)
        self.assertIsNone(result.exit_code)

    def test_launch_failure_is_data_not_exception(self):
        result = run_program(["definitely-not-a-real-command-btp"], "")
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.launch_error)
        self.assertIsNone(result.exit_code)

    def test_environment_can_be_sanitized(self):
        with patch.dict(os.environ, {"BTP_LLM_API_KEY": "should-not-leak"}):
            result = run_program(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.getenv('BTP_LLM_API_KEY', 'missing'))",
                ],
                "",
                inherit_env=False,
            )
        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, "missing" + os.linesep)


class DifferentialTests(unittest.TestCase):
    def test_newline_differences_are_mismatches(self):
        reference = [sys.executable, "-c", "import os; os.write(1, b'ok\\r\\n')"]
        candidate = [sys.executable, "-c", "import os; os.write(1, b'ok\\n')"]
        result = run_differential_case(reference, candidate, "")
        self.assertEqual(result.status, ComparisonStatus.OUTPUT_MISMATCH)
        self.assertEqual(result.reference.stdout, "ok\r\n")
        self.assertEqual(result.candidate.stdout, "ok\n")

    def test_invalid_utf8_differences_survive_comparison_and_json(self):
        reference = [sys.executable, "-c", "import os; os.write(1, b'\\xff')"]
        candidate = [sys.executable, "-c", "import os; os.write(1, b'\\xfe')"]
        result = run_differential_case(reference, candidate, "")
        self.assertEqual(result.status, ComparisonStatus.OUTPUT_MISMATCH)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.json"
            write_results(path, [result])
            stored = json.loads(path.read_text(encoding="utf-8"))[0]
        self.assertEqual(stored["reference"]["stdout"].encode("utf-8", "surrogateescape"), b"\xff")
        self.assertEqual(stored["candidate"]["stdout"].encode("utf-8", "surrogateescape"), b"\xfe")

    def test_matching_invalid_utf8_passes(self):
        command = [sys.executable, "-c", "import os; os.write(1, b'\\xff\\r\\n')"]
        result = run_differential_case(command, command, "")
        self.assertTrue(result.passed)

    def test_matching_outputs_pass(self):
        command = [
            sys.executable,
            "-c",
            "import sys; print(int(sys.stdin.read()) * 2)",
        ]
        result = run_differential_case(command, command, "5\n")
        self.assertTrue(result.passed)
        self.assertEqual(result.status, ComparisonStatus.PASS)

    def test_output_mismatch_is_detected(self):
        reference = [
            sys.executable,
            "-c",
            "import sys; print(int(sys.stdin.read()) * 2)",
        ]
        candidate = [
            sys.executable,
            "-c",
            "import sys; print(int(sys.stdin.read()) + 2)",
        ]
        result = run_differential_case(reference, candidate, "5\n")
        self.assertFalse(result.passed)
        self.assertEqual(result.status, ComparisonStatus.OUTPUT_MISMATCH)
        self.assertEqual(result.reference.stdout, "10" + os.linesep)
        self.assertEqual(result.candidate.stdout, "7" + os.linesep)

    def test_candidate_nonzero_exit_is_detected(self):
        reference = [sys.executable, "-c", "print('ok')"]
        candidate = [sys.executable, "-c", "import sys; sys.exit(3)"]
        result = run_differential_case(reference, candidate, "")
        self.assertEqual(result.status, ComparisonStatus.CANDIDATE_ERROR)
        self.assertEqual(result.candidate.exit_code, 3)

    def test_separate_working_directories_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reference_dir = root / "reference"
            candidate_dir = root / "candidate"
            reference_dir.mkdir()
            candidate_dir.mkdir()
            (reference_dir / "program.py").write_text(
                "print('same')\n", encoding="utf-8"
            )
            (candidate_dir / "program.py").write_text(
                "print('same')\n", encoding="utf-8"
            )

            result = run_differential_case(
                [sys.executable, "program.py"],
                [sys.executable, "program.py"],
                "",
                timeout_seconds=5.0,
                reference_cwd=reference_dir,
                candidate_cwd=candidate_dir,
            )

        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
