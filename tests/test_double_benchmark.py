import os
from pathlib import Path
import sys
import unittest

from pipeline.execution import run_program
from pipeline.task import BenchmarkTask


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_PATH = REPO_ROOT / "benchmarks" / "double" / "task.json"


class DoubleBenchmarkTests(unittest.TestCase):
    def test_first_benchmark_is_complete_and_reference_runs(self):
        task = BenchmarkTask.from_json(TASK_PATH)

        self.assertEqual(task.name, "double")
        self.assertTrue(task.specification_path.exists())

        # Use the same black-box script with the current Python interpreter in
        # the test so this is portable even if the test environment names Python
        # differently from the task configuration.
        result = run_program(
            [sys.executable, "blackbox.py"],
            "-21\n",
            cwd=task.reference_cwd,
            timeout_seconds=task.timeout_seconds,
        )

        self.assertTrue(result.succeeded)
        self.assertEqual(result.stdout, "-42" + os.linesep)


if __name__ == "__main__":
    unittest.main()
