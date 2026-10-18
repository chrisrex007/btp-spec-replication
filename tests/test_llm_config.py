import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pipeline import llm_client
from pipeline.env import load_dotenv


class EnvTests(unittest.TestCase):
    def test_dotenv_does_not_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "BTP_MODEL=file-model\nBTP_NEW_VALUE=from-file\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {"BTP_MODEL": "already-set"},
                clear=False,
            ):
                os.environ.pop("BTP_NEW_VALUE", None)
                load_dotenv(env_file)
                self.assertEqual(os.environ["BTP_MODEL"], "already-set")
                self.assertEqual(os.environ["BTP_NEW_VALUE"], "from-file")
                os.environ.pop("BTP_NEW_VALUE", None)


class LLMClientConfigTests(unittest.TestCase):
    def test_openrouter_headers_include_api_key_and_optional_metadata(self):
        with patch.dict(
            os.environ,
            {
                "BTP_LLM_API_KEY": "test-key",
                "BTP_HTTP_REFERER": "https://example.com",
                "BTP_X_TITLE": "BTP Test",
            },
            clear=False,
        ):
            headers = llm_client._build_headers()

        self.assertEqual(headers["Authorization"], "Bearer test-key")
        self.assertEqual(headers["HTTP-Referer"], "https://example.com")
        self.assertEqual(headers["X-Title"], "BTP Test")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_api_key_header_is_optional_for_local_vllm(self):
        with patch.dict(os.environ, {}, clear=False):
            previous = os.environ.pop("BTP_LLM_API_KEY", None)
            try:
                headers = llm_client._build_headers()
            finally:
                if previous is not None:
                    os.environ["BTP_LLM_API_KEY"] = previous

        self.assertNotIn("Authorization", headers)


if __name__ == "__main__":
    unittest.main()
