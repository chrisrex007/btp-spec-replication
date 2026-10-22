from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from pipeline.baseline import run_baseline
from pipeline.candidate import CandidateSource
from pipeline.task import BenchmarkTask


class BaselineTests(unittest.TestCase):
    def test_llm_failure_keeps_request_record_and_sanitized_stage_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._make_task(root)
            with patch.dict(os.environ, {
                "BTP_LLM_API_KEY": "fixture-key",
                "BTP_LLM_ENDPOINT": "https://example.com/v1/chat/completions",
            }), patch("pipeline.llm_runtime.llm_client.call",
                      side_effect=RuntimeError("failed fixture-key")):
                summary = run_baseline(task, run_root=root / "runs", run_id="llm-error")
            record = json.loads(
                (root / "runs/llm-error/llm_log.jsonl").read_text(encoding="utf-8")
            )
            saved = (root / "runs/llm-error/summary.json").read_text(encoding="utf-8")
        self.assertEqual(summary["status"], "candidate_generation_failed")
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["schema_name"], "candidate_program")
        self.assertIn("source", record["json_schema"]["properties"])
        self.assertNotIn("fixture-key", saved)

    def test_reference_failures_invalidate_the_run(self):
        references = (
            (("definitely-not-a-real-command-btp",), 5.0, "reference_error"),
            ((sys.executable, "-c", "raise SystemExit(3)"), 5.0, "reference_error"),
            ((sys.executable, "-c", "import time; time.sleep(5)"), 0.1, "reference_timeout"),
        )
        for command, timeout, expected_status in references:
            with self.subTest(reference=expected_status, command=command), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                task = replace(self._make_task(root), reference_command=command,
                               timeout_seconds=timeout)
                summary = run_baseline(
                    task, test_count=1, run_root=root / "runs", run_id="invalid",
                    candidate_generator=lambda **kwargs: CandidateSource(
                        language="python", source="print(2)"
                    ),
                    tests_generator=lambda **kwargs: ["1\n"],
                )
                self.assertEqual(summary["status"], "invalid_reference")
                self.assertIsNone(summary["accuracy"])
                self.assertEqual(summary["n_reference_failures"], 1)
                self.assertEqual(summary["n_valid"], 0)
                self.assertEqual(summary["n_fail"], 0)
                self.assertEqual(summary["status_counts"][expected_status], 1)
                saved = json.loads((root / "runs/invalid/summary.json").read_text(encoding="utf-8"))
                self.assertIsNone(saved["accuracy"])
                self.assertTrue((root / "runs/invalid/results.json").exists())
                self.assertTrue((root / "runs/invalid/failures.json").exists())

    def test_one_reference_error_invalidates_even_a_partly_passing_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._make_task(root)
            (root / "blackbox.py").write_text(
                "import sys\nx=int(sys.stdin.read())\n"
                "if x == 0: raise SystemExit(1)\nprint(2*x)\n",
                encoding="utf-8",
            )
            summary = run_baseline(
                task, test_count=2, run_root=root / "runs",
                candidate_generator=lambda **kwargs: CandidateSource(
                    language="python", source="import sys; print(2*int(sys.stdin.read()))"
                ),
                tests_generator=lambda **kwargs: ["0\n", "1\n"],
            )
        self.assertEqual(summary["status"], "invalid_reference")
        self.assertIsNone(summary["accuracy"])
        self.assertEqual(summary["n_pass"], 1)
        self.assertEqual(summary["n_valid"], 1)
        self.assertEqual(summary["n_reference_failures"], 1)
        self.assertEqual(summary["n_fail"], 0)

    def test_candidate_sees_only_specification_and_input_format(self):
        def candidate_generator(*, specification, input_format, run_dir, target, seed):
            self.assertIn("twice", specification)
            self.assertEqual(input_format, "One integer x followed by a newline.")
            return CandidateSource(language="python", source="print(2)")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = run_baseline(
                self._make_task(root), test_count=1, run_root=root / "runs",
                candidate_generator=candidate_generator,
                tests_generator=lambda **kwargs: ["1\n"],
            )
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["accuracy"], 1.0)

    def test_non_utf8_output_is_persisted_in_all_execution_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._make_task(root)
            (root / "blackbox.py").write_text(
                "import os; os.write(1, b'\\xff\\r\\n')", encoding="utf-8"
            )
            summary = run_baseline(
                task, test_count=1, run_root=root / "runs", run_id="binary",
                candidate_generator=lambda **kwargs: CandidateSource(
                    language="python", source="import os; os.write(1, b'\\xfe\\n')"
                ),
                tests_generator=lambda **kwargs: ["1\n"],
            )
            self.assertEqual(summary["accuracy"], 0.0)
            for name in ("results.json", "failures.json"):
                stored = json.loads((root / "runs/binary" / name).read_text(encoding="utf-8"))[0]
                self.assertEqual(stored["reference"]["stdout"].encode("utf-8", "surrogateescape"),
                                 b"\xff\r\n")
                self.assertEqual(stored["candidate"]["stdout"].encode("utf-8", "surrogateescape"),
                                 b"\xfe\n")

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
