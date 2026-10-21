import json
from pathlib import Path
import sys
import tempfile
import unittest

from pipeline.offline_batch import BatchConfig, run_offline_batch
from pipeline.offline_runtime import InferenceOutput
from pipeline.task import BenchmarkTask


class FakeRuntime:
    def __init__(self):
        self.calls = []

    def generate_batch(self, requests):
        self.calls.append([request for request in requests])
        outputs = []
        for request in requests:
            if request.step == "initial_code_generation":
                source = "import sys\nprint(0)\n"
                response = json.dumps({
                    "language": "python", "filename": "main.py", "source": source
                })
            elif request.step == "test_generation":
                response = json.dumps({"tests": ["3\n", "3\n"]})
            elif request.step == "candidate_repair":
                source = "import sys\nx = int(sys.stdin.read())\nprint(x * 2)\n"
                response = json.dumps({
                    "language": "python", "filename": "main.py", "source": source
                })
            else:
                raise AssertionError(request.step)
            outputs.append(InferenceOutput(response=response, latency_s=0.01))
        return outputs


class OfflineBatchTests(unittest.TestCase):
    def _task(self, root: Path, name: str) -> BenchmarkTask:
        spec = root / f"{name}.md"
        spec.write_text("Read an integer and print twice its value.", encoding="utf-8")
        return BenchmarkTask(
            name=name,
            specification_path=spec,
            reference_command=(sys.executable, "-c", "import sys; print(int(sys.stdin.read()) * 2)"),
            reference_cwd=root,
            input_format="One integer followed by a newline.",
            timeout_seconds=5,
        )

    def test_rejects_invalid_configuration(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task(root, "double")
            base = BatchConfig(experiment_id="valid", output_root=root / "runs")
            for changes in ({"experiment_id": ".."}, {"feedback_cases": 0}, {"gpu_memory_utilization": float("nan")}, {"workers": 0}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    run_offline_batch([task], config=replace(base, **changes), runtime=FakeRuntime())

    def test_inference_record_reused_when_state_save_was_lost(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task(root, "double")
            config = BatchConfig(experiment_id="resume", output_root=root / "runs", max_repair_iterations=0)
            run_offline_batch([task], config=config, runtime=FakeRuntime(), should_stop=lambda: True)
            state_path = root / "runs/resume/double/state.json"
            state = json.loads(state_path.read_text())
            state["stage"] = "candidate_request"
            state_path.write_text(json.dumps(state))
            runtime = FakeRuntime()
            result = run_offline_batch([task], config=replace(config, resume=True), runtime=runtime)
            self.assertEqual(result["status"], "completed")
            self.assertEqual([call[0].step for call in runtime.calls], ["test_generation"])

    def test_reference_failure_stops_repair_and_is_terminal_failure(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = replace(self._task(root, "double"), reference_command=(sys.executable, "-c", "raise SystemExit(1)"))
            runtime = FakeRuntime()
            result = run_offline_batch([task], config=BatchConfig(experiment_id="invalid-ref", output_root=root / "runs"), runtime=runtime)
            self.assertEqual(result["status"], "completed_with_failures")
            summary = result["tasks"]["double"]["latest_summary"]
            self.assertEqual(summary["n_valid"], 0)
            self.assertIsNone(summary["accuracy"])
            self.assertEqual(len(runtime.calls), 2)

    def test_batches_tasks_repairs_and_persists_reusable_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [self._task(root, name) for name in ("double_a", "double_b")]
            config = BatchConfig(
                experiment_id="batch-1",
                output_root=root / "persistent-results",
                test_count=2,
                max_repair_iterations=1,
                workers=2,
            )
            runtime = FakeRuntime()
            summary = run_offline_batch(tasks, config=config, runtime=runtime)

            self.assertEqual(summary["status"], "completed")
            self.assertEqual(summary["n_terminal"], 2)
            self.assertEqual([len(batch) for batch in runtime.calls], [2, 2, 2])
            self.assertEqual(
                [batch[0].step for batch in runtime.calls],
                ["initial_code_generation", "test_generation", "candidate_repair"],
            )
            repair_prompt = runtime.calls[-1][0].user_prompt
            self.assertIn('"input": "3\\n"', repair_prompt)
            self.assertNotIn(sys.executable, repair_prompt)

            run_dir = root / "persistent-results" / "batch-1" / "double_a"
            for relative in (
                "state.json",
                "task.json",
                "specification.txt",
                "tests.json",
                "inference.jsonl",
                "iterations/000/candidate/main.py",
                "iterations/000/results.json",
                "iterations/001/candidate/main.py",
                "iterations/001/results.json",
                "iterations/001/failures.json",
                "summary.json",
            ):
                self.assertTrue((run_dir / relative).exists(), relative)

            # A fully completed resume validates the checkpoint without loading
            # the model or repeating any inference.
            config = BatchConfig(
                experiment_id="batch-1",
                output_root=root / "persistent-results",
                test_count=2,
                max_repair_iterations=1,
                workers=2,
                resume=True,
            )

            def should_not_load_model():
                self.fail("completed resume should not initialize or call the model")

            resumed = run_offline_batch(
                tasks, config=config, runtime_factory=should_not_load_model
            )
            self.assertEqual(resumed["status"], "completed")

    def test_checkpoint_after_batched_generation_resumes_without_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [self._task(root, "double")]
            config = BatchConfig(
                experiment_id="batch-resume",
                output_root=root / "results",
                test_count=1,
                max_repair_iterations=0,
            )
            runtime = FakeRuntime()
            interrupted = run_offline_batch(
                tasks,
                config=config,
                runtime=runtime,
                should_stop=lambda: True,
            )
            self.assertEqual(interrupted["status"], "interrupted")
            self.assertEqual(len(runtime.calls), 1)
            self.assertTrue(
                (root / "results" / "batch-resume" / "double" / "inference" /
                 "iteration-000-initial_code_generation.json").exists()
            )

            resume_runtime = FakeRuntime()
            resumed = run_offline_batch(
                tasks,
                config=BatchConfig(
                    experiment_id="batch-resume",
                    output_root=root / "results",
                    test_count=1,
                    max_repair_iterations=0,
                    resume=True,
                ),
                runtime=resume_runtime,
            )
            self.assertEqual(resumed["status"], "completed")
            # The candidate batch output was checkpointed and consumed directly.
            self.assertEqual([call[0].step for call in resume_runtime.calls], [
                "test_generation",
            ])


if __name__ == "__main__":
    unittest.main()
