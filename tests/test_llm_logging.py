import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline.llm_runtime import logged_call


class LLMLoggingTests(unittest.TestCase):
    def _request(self, run_dir):
        return dict(
            run_dir=run_dir, step="initial_code_generation", target="task",
            iteration=0, system_prompt="system", user_prompt="user", seed=7,
            temperature=0.3, max_tokens=100,
            json_schema={"type": "object"}, schema_name="candidate_program",
        )

    def _record(self, root):
        records = (root / "llm_log.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(records), 1)
        return json.loads(records[0])

    def test_success_includes_schema_and_request_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {
                "BTP_MODEL": "fixture-model",
                "BTP_LLM_ENDPOINT": "https://example.com/v1/chat/completions",
                "BTP_LLM_API_KEY": "",
            }), patch("pipeline.llm_runtime.llm_client.call", return_value="not json") as call:
                response = logged_call(**self._request(root))
            record = self._record(root)
        self.assertEqual(response, "not json")
        self.assertEqual(record["response"], response)
        self.assertEqual(record["status"], "success")
        self.assertIsNone(record["error"])
        self.assertEqual(record["json_schema"], {"type": "object"})
        self.assertEqual(record["schema_name"], "candidate_program")
        self.assertEqual(record["model"], "fixture-model")
        self.assertEqual(record["endpoint"], "https://example.com/v1/chat/completions")
        self.assertEqual(record["seed"], 7)
        self.assertEqual(record["temperature"], 0.3)
        self.assertEqual(record["max_tokens"], 100)
        self.assertGreaterEqual(record["latency_s"], 0)
        call.assert_called_once_with(
            "system", "user", temperature=0.3, max_tokens=100, seed=7,
            json_schema={"type": "object"}, schema_name="candidate_program",
        )

    def test_failed_request_is_recorded_and_reraised_without_credentials(self):
        endpoint = "https://name:password@example.com/v1/chat/completions?key=query-secret#private"
        error = RuntimeError("failed fixture-key at " + endpoint)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {
                "BTP_LLM_API_KEY": "fixture-key", "BTP_LLM_ENDPOINT": endpoint,
            }), patch("pipeline.llm_runtime.llm_client.call", side_effect=error):
                with self.assertRaises(RuntimeError) as raised:
                    logged_call(**self._request(root))
            text = (root / "llm_log.jsonl").read_text(encoding="utf-8")
            record = self._record(root)
        self.assertIs(raised.exception, error)
        self.assertEqual(record["status"], "error")
        self.assertIsNone(record["response"])
        self.assertEqual(record["error"]["type"], "RuntimeError")
        self.assertEqual(record["json_schema"], {"type": "object"})
        self.assertEqual(record["schema_name"], "candidate_program")
        self.assertEqual(record["endpoint"], "https://example.com/v1/chat/completions")
        for secret in ("fixture-key", "password", "query-secret", "#private"):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
