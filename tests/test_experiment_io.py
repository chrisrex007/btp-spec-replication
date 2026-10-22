from dataclasses import replace
from pathlib import Path
import tempfile
import types
import unittest
from pipeline.experiment_io import CachedInference, read_json, digest
from pipeline.offline_runtime import InferenceRequest

class CacheTests(unittest.TestCase):
    def request(self):
        return InferenceRequest("task", "generate", 0, "system", "user", {}, 0.2, 50, 1)

    def test_cached_no_load_and_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "response.json"
            runtime = types.SimpleNamespace(generate_batch=lambda requests: [types.SimpleNamespace(response="malformed") for _ in requests])
            cache = CachedInference(runtime_factory=lambda: runtime, model="model")
            self.assertEqual(cache.generate([(path, self.request())])[str(path)], "malformed")
            self.assertEqual(CachedInference(model="model").generate([(path, self.request())])[str(path)], "malformed")
            self.assertIsNone(read_json(path)["prompt_tokens"])
            with self.assertRaisesRegex(ValueError, "mismatch"):
                cache.generate([(path, replace(self.request(), user_prompt="different"))])

    def test_groups_sampling_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            def generate(requests):
                calls.append(requests)
                return [types.SimpleNamespace(response="{}", latency_s=1) for _ in requests]
            cache = CachedInference(runtime=types.SimpleNamespace(generate_batch=generate), model="model")
            request = self.request()
            cache.generate([(root / "a.json", request), (root / "b.json", replace(request, task="other")), (root / "c.json", replace(request, seed=2))])
            self.assertEqual([len(call) for call in calls], [2, 1])
            self.assertEqual(read_json(root / "a.json")["batch_id"], read_json(root / "b.json")["batch_id"])
            self.assertNotEqual(read_json(root / "a.json")["batch_id"], read_json(root / "c.json")["batch_id"])

    def test_count_failure_persists_error_not_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "response.json"
            cache = CachedInference(runtime=types.SimpleNamespace(generate_batch=lambda requests: []), model="model")
            with self.assertRaisesRegex(RuntimeError, "count"):
                cache.generate([(path, self.request())])
            self.assertFalse(path.exists())
            self.assertIn("error", read_json(path.with_suffix(".json.error.json")))

    def test_hash_canonical(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
