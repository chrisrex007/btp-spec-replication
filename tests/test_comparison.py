from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

from pipeline.comparison import ComparisonConfig, run_comparison
from pipeline.experiment_io import read_json, atomic_json
from pipeline.offline_runtime import InferenceOutput
from pipeline.pools import freeze_pool
from pipeline.task import BenchmarkTask


class FakeRuntime:
    def __init__(self, repair=None):
        self.calls = []
        self.repair = repair

    def generate_batch(self, requests):
        self.calls.append(requests)
        responses = []
        for request in requests:
            source = "print(0)" if request.step == "initial_code_generation" else "import sys; print(int(sys.stdin.read()) * 2)"
            response = json.dumps({"language": "python", "filename": "main.py", "source": source})
            if request.step == "candidate_repair" and self.repair is not None:
                response = self.repair
            responses.append(InferenceOutput(response, 0.01))
        return responses


class ComparisonTests(unittest.TestCase):
    def setup_experiment(self, root):
        spec = root / "spec.md"
        spec.write_text("Read integer and output double.")
        task = BenchmarkTask(name="double", specification_path=spec,
            reference_command=(sys.executable, "-c", "import sys; print(int(sys.stdin.read())*2)"),
            reference_cwd=root, input_format="One integer", timeout_seconds=5)
        pool = root / "pool"
        freeze_pool(task, ["1", "2", "3", "4"], pool, development_count=2, held_out_count=2, seed=1)
        return task, {task.name: pool}, root / "experiment", ComparisonConfig(model="fake", seeds=(42,), max_repair_iterations=2)

    def test_paired_c0_development_only_and_raw_stopping(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, pools, output, config = self.setup_experiment(Path(tmp))
            (pools[task.name] / "held_out.json").unlink()
            runtime = FakeRuntime()
            result = run_comparison([task], pools, output, config=config, runtime=runtime)
            self.assertEqual(result["status"], "completed")
            baseline, raw = result["arms"]
            self.assertEqual(baseline["initial_source_hash"], raw["initial_source_hash"])
            self.assertEqual(baseline["final_iteration"], 0)
            self.assertEqual(raw["final_iteration"], 1)
            self.assertEqual(raw["development"]["accuracy"], 1)
            self.assertEqual([batch[0].step for batch in runtime.calls], ["initial_code_generation", "candidate_repair"])
            self.assertNotIn(sys.executable, runtime.calls[-1][0].user_prompt)
            result2 = run_comparison([task], pools, output, config=config, resume=True,
                runtime_factory=lambda: self.fail("completed resume loaded model"))
            self.assertEqual(result2["status"], "completed")

    def test_saved_initial_response_resumes_without_regeneration(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, pools, output, config = self.setup_experiment(Path(tmp))
            runtime = FakeRuntime()
            first = run_comparison([task], pools, output, config=config, runtime=runtime,
                                   should_stop=lambda: bool(runtime.calls))
            self.assertEqual(first["status"], "interrupted")
            resumed = FakeRuntime()
            run_comparison([task], pools, output, config=config, runtime=resumed, resume=True)
            self.assertEqual([batch[0].step for batch in resumed.calls], ["candidate_repair"])

    def test_rejects_configuration_and_candidate_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, pools, output, config = self.setup_experiment(Path(tmp))
            run_comparison([task], pools, output, config=config, runtime=FakeRuntime())
            with self.assertRaises(ValueError):
                run_comparison([task], pools, output, config=replace(config, max_repair_iterations=3), resume=True)
            path = output / "double/seed-42/arms/raw/iterations/001/candidate.json"
            source = read_json(path)
            source["source"] = "print(99)"
            atomic_json(path, source)
            with self.assertRaisesRegex(ValueError, "modified"):
                run_comparison([task], pools, output, config=config, resume=True)

    def test_parse_and_build_failure_keep_last_successful_candidate(self):
        invalid_code = json.dumps({"language": "python", "filename": "main.py", "source": "def broken("})
        for response in ("invalid json", invalid_code):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as tmp:
                task, pools, output, config = self.setup_experiment(Path(tmp))
                result = run_comparison([task], pools, output, config=config, runtime=FakeRuntime(repair=response))
                raw = result["arms"][1]
                self.assertEqual(raw["status"], "failed")
                self.assertEqual(raw["final_iteration"], 0)
                self.assertEqual(result["status"], "completed_with_failures")

    def test_reference_error_stops_all_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            task, pools, output, config = self.setup_experiment(Path(tmp))
            task = replace(task, reference_command=(sys.executable, "-c", "raise SystemExit(1)"))
            runtime = FakeRuntime()
            result = run_comparison([task], pools, output, config=config, runtime=runtime)
            self.assertEqual(result["status"], "completed_with_failures")
            self.assertEqual(len(runtime.calls), 1)
            for arm in result["arms"]:
                self.assertEqual(arm["reason"], "reference_invalid")
                self.assertIsNone(arm["development"]["accuracy"])
                self.assertEqual(arm["development"]["n_valid"], 0)
