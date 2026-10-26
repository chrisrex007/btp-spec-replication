"""Direct, schema-constrained inference with a local vLLM checkpoint."""

from __future__ import annotations

from importlib import metadata
import json
import os
from pathlib import Path
import re
import sys

from .env import load_dotenv


load_dotenv()

ENGINE_SETTINGS = {
    "dtype": "bfloat16",
    "max_model_len": 32768,
    "max_num_seqs": 1,
    "enforce_eager": True,
    "gpu_memory_utilization": 0.80,
    "tensor_parallel_size": 1,
    "trust_remote_code": False,
    "generation_config": "vllm",
    "seed": 42,
    "structured_outputs_config": {
        "backend": "xgrammar",
        "disable_any_whitespace": True,
    },
}
SAMPLING_SETTINGS = {
    "n": 1,
    "top_p": 1.0,
    "top_k": -1,
    "repetition_penalty": 1.0,
}
_engine = None
_engine_model_path: Path | None = None


def get_model() -> str:
    """Return the configured directory name, including an unset value for logging."""
    return os.environ.get("BTP_MODEL", "").strip()


def resolve_model_path() -> Path:
    """Reject remote IDs, traversal, escaped symlinks, and incomplete checkpoints."""
    name = get_model()
    if not name:
        raise ValueError(
            "BTP_MODEL is required; set it to a directory name under ~/models"
        )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError("BTP_MODEL must be a single directory name under ~/models")
    root = (Path.home() / "models").resolve()
    model_path = (root / name).resolve()
    if model_path.parent != root or not model_path.is_dir():
        raise ValueError(f"Local model directory is missing or outside ~/models: {name}")

    def require_file(filename: str) -> Path:
        path = (model_path / filename).resolve()
        if not path.is_relative_to(model_path) or not path.is_file():
            raise ValueError(
                f"Local checkpoint file is missing or outside its directory: {filename}"
            )
        return path

    require_file("config.json")
    require_file("tokenizer_config.json")
    require_file("tokenizer.json")
    index = model_path / "model.safetensors.index.json"
    if index.is_file():
        data = json.loads(require_file(index.name).read_text(encoding="utf-8"))
        weight_map = data.get("weight_map")
        if not isinstance(weight_map, dict) or not weight_map:
            raise ValueError("Local checkpoint has an empty or invalid weight map")
        if not all(isinstance(value, str) for value in weight_map.values()):
            raise ValueError("Local checkpoint weight map must contain filenames")
        for filename in sorted(set(weight_map.values())):
            require_file(filename)
    else:
        require_file("model.safetensors")
    return model_path


def inference_metadata() -> dict:
    """Inspect package versions without importing GPU libraries or loading weights."""
    versions = {"python": sys.version.split()[0]}
    for package in ("vllm", "torch", "transformers", "xgrammar"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "backend": "vllm_offline",
        "model_path": None,
        "runtime_versions": versions,
        "engine_settings": dict(ENGINE_SETTINGS),
        "sampling_settings": dict(SAMPLING_SETTINGS),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def _get_engine():
    global _engine, _engine_model_path
    model_path = resolve_model_path()
    if _engine is not None:
        if model_path != _engine_model_path:
            raise RuntimeError("BTP_MODEL cannot change after the local model has loaded")
        return _engine

    # Set these before importing vLLM/Transformers/Hugging Face libraries.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["VLLM_NO_USAGE_STATS"] = "1"
    os.environ["VLLM_DO_NOT_TRACK"] = "1"
    try:
        from vllm import LLM
    except ImportError as exc:
        raise RuntimeError(
            "Offline inference requires the documented Python 3.12 vLLM "
            f"environment: {exc}"
        ) from exc

    _engine = LLM(model=str(model_path), tokenizer=str(model_path), **ENGINE_SETTINGS)
    _engine_model_path = model_path
    return _engine


def call(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    seed: int = 42,
    json_schema: dict | None = None,
    schema_name: str = "response",
    *,
    completion_metadata: dict | None = None,
) -> str:
    """Generate once locally, using the checkpoint's chat template and JSON schema.

    schema_name remains part of the caller/logging interface; vLLM accepts the
    schema itself. Optional completion_metadata receives termination and token
    counts without changing the string return value. Truncated text is returned
    intact for logging and parsing. There are no inference retries or fallbacks.
    """
    if completion_metadata is not None:
        completion_metadata.clear()
    engine = _get_engine()
    from vllm import SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    sampling = SamplingParams(
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
        structured_outputs=(
            None if json_schema is None else StructuredOutputsParams(json=json_schema)
        ),
        **SAMPLING_SETTINGS,
    )
    outputs = engine.chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        sampling_params=sampling,
        use_tqdm=False,
    )
    if len(outputs) != 1 or len(outputs[0].outputs) != 1:
        raise RuntimeError("Local inference did not return exactly one completion")
    request = outputs[0]
    completion = request.outputs[0]
    if completion_metadata is not None:
        prompt_tokens = (
            None if request.prompt_token_ids is None else len(request.prompt_token_ids)
        )
        completion_tokens = len(completion.token_ids)
        completion_metadata.update({
            "finish_reason": completion.finish_reason,
            "stop_reason": completion.stop_reason,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": (
                    None if prompt_tokens is None else prompt_tokens + completion_tokens
                ),
            },
        })
    return completion.text
