"""Batched offline inference using one in-process vLLM engine."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any


@dataclass(frozen=True)
class InferenceRequest:
    task: str
    step: str
    iteration: int
    system_prompt: str
    user_prompt: str
    schema: dict
    temperature: float
    max_tokens: int
    seed: int


@dataclass(frozen=True)
class InferenceOutput:
    response: str
    latency_s: float


class OfflineVLLM:
    """Own one vLLM model instance and reuse it for each batched request."""

    def __init__(
        self,
        *,
        model: str,
        dtype: str = "half",
        tensor_parallel_size: int = 1,
        max_model_len: int = 8192,
        gpu_memory_utilization: float = 0.90,
        max_num_seqs: int = 32,
    ) -> None:
        try:
            from vllm import LLM
        except ImportError as exc:
            raise RuntimeError(
                "Offline inference requires vLLM in the active Python environment"
            ) from exc

        self.model = model
        self.llm = LLM(
            model=model,
            dtype=dtype,
            tensor_parallel_size=tensor_parallel_size,
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            max_num_seqs=max_num_seqs,
        )
        self.tokenizer = self.llm.get_tokenizer()

    def _format_chat(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if not hasattr(self.tokenizer, "apply_chat_template"):
            raise RuntimeError("The configured model tokenizer has no chat template")
        return self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

    def generate_batch(self, requests: list[InferenceRequest]) -> list[InferenceOutput]:
        if not requests:
            return []
        config = {
            (item.temperature, item.max_tokens, item.seed, json_schema_key(item.schema))
            for item in requests
        }
        if len(config) != 1:
            raise ValueError("A vLLM batch must share sampling settings and JSON schema")

        from vllm import SamplingParams
        from vllm.sampling_params import GuidedDecodingParams

        first = requests[0]
        params = SamplingParams(
            temperature=first.temperature,
            max_tokens=first.max_tokens,
            seed=first.seed,
            guided_decoding=GuidedDecodingParams(json=first.schema),
        )
        prompts = [
            self._format_chat(item.system_prompt, item.user_prompt)
            for item in requests
        ]
        started = time.monotonic()
        outputs = self.llm.generate(prompts, params)
        total_latency = time.monotonic() - started
        if len(outputs) != len(requests):
            raise RuntimeError("vLLM returned a different number of outputs than prompts")

        # vLLM exposes total batch latency. Divide it evenly for per-task logs;
        # the shared batch latency is also written into each record.
        per_request = total_latency / len(outputs)
        return [
            InferenceOutput(response=output.outputs[0].text, latency_s=per_request)
            for output in outputs
        ]


def json_schema_key(schema: dict[str, Any]) -> str:
    """Stable comparison key for schemas in one guided-decoding batch."""

    import json

    return json.dumps(schema, sort_keys=True, separators=(",", ":"))
