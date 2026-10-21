import sys
import types
import unittest
from unittest.mock import patch
from pipeline.offline_runtime import OfflineVLLM, InferenceRequest


class RuntimeTests(unittest.TestCase):
    def test_context_validation_and_token_accounting(self):
        runtime = OfflineVLLM.__new__(OfflineVLLM)
        runtime.max_model_len = 8
        runtime.tokenizer = types.SimpleNamespace(apply_chat_template=lambda *a, **kw: "prompt", encode=lambda *a, **kw: [1, 2, 3])
        calls = []
        def generate(prompts, params):
            calls.append(prompts)
            return [types.SimpleNamespace(outputs=[types.SimpleNamespace(text="{}", token_ids=[4, 5])])]
        runtime.llm = types.SimpleNamespace(generate=generate)
        modules = {"vllm": types.SimpleNamespace(SamplingParams=lambda **kw: kw), "vllm.sampling_params": types.SimpleNamespace(GuidedDecodingParams=lambda **kw: kw)}
        with patch.dict(sys.modules, modules):
            request = InferenceRequest("task", "step", 0, "system", "user", {}, 0.2, 5, 42)
            output = runtime.generate_batch([request])[0]
            self.assertEqual(output.prompt_tokens, 3)
            self.assertEqual(output.completion_tokens, 2)
            self.assertIsNotNone(output.batch_latency_s)
            runtime.max_model_len = 7
            with self.assertRaisesRegex(ValueError, "context budget"):
                runtime.generate_batch([request])
            self.assertEqual(len(calls), 1)
