import json
from pathlib import Path
import sys
import tempfile
import unittest

from pipeline.baseline import run_baseline
from pipeline.candidate import CandidateSource
from pipeline.task import BenchmarkTask


class BaselineTests(unittest.TestCase):
    def _make_task(self, root: Path) -> BenchmarkTask:
        spec = root / "spec.md"
        spec.write_text("Read an integer and print twice its value.", encoding="utf-8")
        (root / "blackbox.py").write_text(
            "import sys\nx=int(sys.stdin.read())\nprint(2*x)\n",
            encoding="utf-8",
        )
        return BenchmarkTask(
            name="double",
            specification_path=spec,
            reference_command=(sys.executable, "blackbox.py"),
            reference_cwd=root,
            input_format="One integer x followed by a newline.",
            timeout_seconds=5.0,
        )

    def test_complete_baseline_persists_score_and_artifacts(self):
        def fake_candidate_generator(**kwargs):
            return CandidateSource(
                language="python",
                source="import sys\nx=int(sys.stdin.read())\nprint(2*x)\n",
            )

        def fake_tests_generator(**kwargs):
            return ["1\n", "2\n", "5\n"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._make_task(root)
            run_root = root / "runs"

            summary = run_baseline(
                task,
                test_count=3,
                run_root=run_root,
                run_id="run-1",
                candidate_generator=fake_candidate_generator,
                tests_generator=fake_tests_generator,
            )

            run_dir = run_root / "run-1"
            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["n_pass"], 3)
            self.assertEqual(summary["n_fail"], 0)
            self.assertEqual(summary["accuracy"], 1.0)

            for relative in [
                "specification.txt",
                "task.json",
                "candidate/metadata.json",
                "candidate/main.py",
                "build.json",
                "tests.json",
                "results.json",
                "failures.json",
                "summary.json",
            ]:
                self.assertTrue((run_dir / relative).exists(), relative)

            failures = json.loads(
                (run_dir / "failures.json").read_text(encoding="utf-8")
            )
            self.assertEqual(failures, [])

    def test_baseline_records_output_mismatches(self):
        def wrong_candidate(**kwargs):
            return CandidateSource(
                language="python",
                source="import sys\nx=int(sys.stdin.read())\nprint(x+2)\n",
            )

        def tests_generator(**kwargs):
            return ["1\n", "2\n", "5\n"]

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = run_baseline(
                self._make_task(root),
                test_count=3,
                run_root=root / "runs",
                run_id="run-2",
                candidate_generator=wrong_candidate,
                tests_generator=tests_generator,
            )

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["n_pass"], 1)
            self.assertEqual(summary["n_fail"], 2)
            self.assertAlmostEqual(summary["accuracy"], 1 / 3)
            self.assertEqual(summary["status_counts"]["output_mismatch"], 2)

    def test_candidate_generation_failure_is_persisted(self):
        def broken_generator(**kwargs):
            raise ValueError("bad model response")

        def unused_tests(**kwargs):
            self.fail("test generation must not run after candidate generation fails")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = run_baseline(
                self._make_task(root),
                run_root=root / "runs",
                run_id="run-3",
                candidate_generator=broken_generator,
                tests_generator=unused_tests,
            )

            self.assertEqual(summary["status"], "candidate_generation_failed")
            persisted = json.loads(
                (root / "runs" / "run-3" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(persisted["status"], "candidate_generation_failed")


if __name__ == "__main__":
    unittest.main()
