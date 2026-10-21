import sys
import types
import unittest
from unittest.mock import patch

from pipeline.offline_runtime import InferenceRequest, OfflineVLLM


class FakeTokenizer:
    def apply_chat_template(self, messages, *, tokenize, add_generation_prompt):
        assert tokenize is False
        assert add_generation_prompt is True
        return "<system>" + messages[0]["content"] + "<user>" + messages[1]["content"]


class FakeLLM:
    instances = []

    def __init__(self, **kwargs):
        self.config = kwargs
        self.prompts = []
        self.sampling_params = None
        self.__class__.instances.append(self)

    def get_tokenizer(self):
        return FakeTokenizer()

    def generate(self, prompts, params):
        self.prompts = prompts
        self.sampling_params = params
        return [types.SimpleNamespace(outputs=[types.SimpleNamespace(text=f"out-{i}")])
                for i, _ in enumerate(prompts)]


class OfflineRuntimeTests(unittest.TestCase):
    def test_one_engine_formats_and_generates_a_batch_with_json_guidance(self):
        FakeLLM.instances.clear()
        vllm = types.ModuleType("vllm")
        vllm.LLM = FakeLLM

        class FakeSamplingParams:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        class FakeGuidedDecodingParams:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        sampling_module = types.ModuleType("vllm.sampling_params")
        sampling_module.GuidedDecodingParams = FakeGuidedDecodingParams
        vllm.SamplingParams = FakeSamplingParams

        requests = [
            InferenceRequest(
                task=f"task-{i}",
                step="initial_code_generation",
                iteration=0,
                system_prompt="system",
                user_prompt=f"user-{i}",
                schema={"type": "object", "properties": {"source": {"type": "string"}}},
                temperature=0.2,
                max_tokens=100,
                seed=7,
            )
            for i in range(2)
        ]

        with patch.dict(sys.modules, {
            "vllm": vllm,
            "vllm.sampling_params": sampling_module,
        }):
            runtime = OfflineVLLM(
                model="model-id",
                dtype="half",
                tensor_parallel_size=2,
                max_model_len=8192,
            )
            outputs = runtime.generate_batch(requests)

        self.assertEqual(len(FakeLLM.instances), 1)
        self.assertEqual(FakeLLM.instances[0].config["tensor_parallel_size"], 2)
        self.assertEqual(len(FakeLLM.instances[0].prompts), 2)
        self.assertIn("<user>user-0", FakeLLM.instances[0].prompts[0])
        self.assertEqual(
            FakeLLM.instances[0].sampling_params.kwargs["guided_decoding"].kwargs["json"],
            requests[0].schema,
        )
        self.assertEqual([item.response for item in outputs], ["out-0", "out-1"])


if __name__ == "__main__":
    unittest.main()
