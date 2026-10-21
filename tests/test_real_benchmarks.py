from pathlib import Path
import os
import shutil
import unittest

from pipeline.execution import run_program
from pipeline.task import BenchmarkTask


REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = REPO_ROOT / "benchmarks"


CASES = [
    ("01_line_count", "a\nb\nlast", "2\n"),
    ("02_ascii_upper", "aZ-9\n", "AZ-9\n"),
    ("03_numeric_sort", "2\n02\n-1\n10\n2\n", "-1\n02\n2\n2\n10\n"),
    ("04_adjacent_run_count", "a\na\nb\na\n", "      2 a\n      1 b\n      1 a\n"),
    ("05_colon_field_select", "a:b\na:b:c\na::\nplain\n:b:c\n", "a\na:c\na:\nplain\n:c\n"),
    ("06_width_wrap", "123456789abc\nhi\n", "12345678\n9abc\nhi\n"),
    ("07_base64_encode", "hello", "aGVsbG8=\n"),
    ("08_json_compact", '{"b":[1,true,"é"],"a":null}', '{"b":[1,true,"\\u00e9"],"a":null}\n'),
    ("09_casefold_unique_sort", "b\nA\na\nB\nc\n", "A\nb\nc\n"),
    ("10_base64_decode", "aGVs\nbG8K\n", "hello\n"),
]


class RealBenchmarkTests(unittest.TestCase):
    def test_task_configs_have_no_separate_output_format(self):
        for directory, _, _ in CASES:
            task_path = BENCHMARK_ROOT / directory / "task.json"
            text = task_path.read_text(encoding="utf-8")
            self.assertNotIn('"output_format"', text, directory)
            BenchmarkTask.from_json(task_path)

    @unittest.skipIf(os.name == "nt", "GNU/Linux reference-oracle integration requires a Linux environment")
    def test_reference_oracles_match_spec_smoke_cases(self):
        for directory, stdin_data, expected in CASES:
            with self.subTest(directory=directory):
                task = BenchmarkTask.from_json(
                    BENCHMARK_ROOT / directory / "task.json"
                )
                executable = task.reference_command[0]
                if shutil.which(executable) is None:
                    self.skipTest(f"{executable} is not installed")

                result = run_program(
                    task.reference_command,
                    stdin_data,
                    cwd=task.reference_cwd,
                    timeout_seconds=task.timeout_seconds,
                )
                self.assertTrue(result.succeeded, result.to_dict())
                self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
