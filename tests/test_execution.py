import sys
import unittest

from pipeline.differential import ComparisonStatus, run_differential_case
from pipeline.execution import run_program


class ExecutionTests(unittest.TestCase):
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
        self.assertEqual(result.stdout, "HELLO\n")
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


class DifferentialTests(unittest.TestCase):
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
        self.assertEqual(result.reference.stdout, "10\n")
        self.assertEqual(result.candidate.stdout, "7\n")

    def test_candidate_nonzero_exit_is_detected(self):
        reference = [sys.executable, "-c", "print('ok')"]
        candidate = [sys.executable, "-c", "import sys; sys.exit(3)"]
        result = run_differential_case(reference, candidate, "")
        self.assertEqual(result.status, ComparisonStatus.CANDIDATE_ERROR)
        self.assertEqual(result.candidate.exit_code, 3)


if __name__ == "__main__":
    unittest.main()
