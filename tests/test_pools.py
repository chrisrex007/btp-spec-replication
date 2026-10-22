import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.offline_runtime import InferenceOutput
from pipeline.pools import _hash, freeze_pool, generate_pool, load_development, load_held_out
from pipeline.task import BenchmarkTask


class PoolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        spec = self.root / "spec.md"
        spec.write_text("Double the integer.", encoding="utf-8")
        self.task = BenchmarkTask("double", spec, ("secret-reference",), self.root, "One integer")

    def freeze(self, name="pool"):
        directory = self.root / name
        metadata = freeze_pool(self.task, ["1\n", "1\n", "2\n", "3\n", "4\n"],
                               directory, development_count=2, held_out_count=2, seed=42)
        return directory, metadata

    def test_deterministic_disjoint_deduplication(self):
        first, metadata = self.freeze()
        second, other = self.freeze("other")
        self.assertEqual(metadata, other)
        self.assertEqual(metadata["unique_count"], 4)
        self.assertEqual(load_development(first, self.task), load_development(second, self.task))
        self.assertFalse(set(load_development(first, self.task)[1]) & set(load_held_out(first, self.task)[1]))

    def test_development_never_opens_held_out(self):
        directory, _ = self.freeze()
        original = Path.read_text
        def guarded(path, *args, **kwargs):
            if path.name == "held_out.json":
                raise AssertionError("held-out read during development")
            return original(path, *args, **kwargs)
        with patch.object(Path, "read_text", guarded):
            self.assertEqual(len(load_development(directory, self.task)[1]), 2)

    def test_rejects_insufficient_and_tampered_pool(self):
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            freeze_pool(self.task, ["1", "1"], self.root / "short",
                        development_count=1, held_out_count=1, seed=1)
        directory, _ = self.freeze()
        (directory / "development.json").write_text('["changed", "2"]', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash"):
            load_development(directory, self.task)

    def test_rejects_changed_task(self):
        directory, _ = self.freeze()
        self.task.specification_path.write_text("Different specification", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "identity"):
            load_development(directory, self.task)

    def test_rejects_overlap_even_with_matching_payload_hash(self):
        directory, metadata = self.freeze()
        development = load_development(directory, self.task)[1]
        (directory / "held_out.json").write_text(json.dumps(development), encoding="utf-8")
        metadata["held_out"]["sha256"] = _hash(development)
        (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overlap"):
            load_held_out(directory, self.task)

    def test_generation_resume_reuses_calls_and_logs(self):
        class Runtime:
            calls = 0
            def generate_batch(self, requests):
                self.calls += 1
                if self.calls == 2:
                    raise RuntimeError("interrupted")
                values = ["1", "2"] if self.calls == 1 else ["3", "4"]
                return [InferenceOutput(json.dumps({"tests": values}), .1, 10, 5)]
        runtime = Runtime()
        directory = self.root / "generated"
        kwargs = dict(task=self.task, output_dir=directory, runtime=runtime, model="fixture",
                      development_count=2, held_out_count=2, seed=9, batch_size=2)
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            generate_pool(**kwargs)
        metadata = generate_pool(**kwargs, resume=True)
        self.assertEqual(runtime.calls, 3)
        self.assertEqual(metadata["unique_count"], 4)
        record = json.loads((directory / "calls/0000.json").read_text())
        self.assertNotIn("secret-reference", record["request"]["user_prompt"])
        self.assertEqual(record["output"]["prompt_tokens"], 10)
        generate_pool(**kwargs, resume=True)
        self.assertEqual(runtime.calls, 3)
        with self.assertRaisesRegex(ValueError, "configuration"):
            generate_pool(**{**kwargs, "seed": 10}, resume=True)

    def test_malformed_responses_are_bounded_and_persisted(self):
        class Runtime:
            def generate_batch(self, requests):
                return [InferenceOutput("not json", .1)]
        directory = self.root / "bad"
        with self.assertRaisesRegex(ValueError, "exhausted"):
            generate_pool(self.task, directory, Runtime(), "fixture", 1, 1, 42,
                          batch_size=2, max_batches=2)
        self.assertEqual(len(list((directory / "calls").glob("*.json"))), 2)
