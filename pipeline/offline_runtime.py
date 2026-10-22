"""Direct, local-files-only model loading and structured vLLM inference."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import metadata
import math
import os
from pathlib import Path
import platform
import sys
import time

from .artifacts import digest, file_digest
from .env import load_dotenv


class RuntimeSetupError(RuntimeError):
    pass


class ContextBudgetExceeded(ValueError):
    def __init__(self, message: str, request=None, prompt_tokens=None) -> None:
        super().__init__(message)
        self.request = request
        self.prompt_tokens = prompt_tokens


@dataclass(frozen=True)
class RuntimeConfig:
    model: str
    dtype: str = "auto"
    tensor_parallel_size: int = 1
    max_model_len: int = 8192
    gpu_memory_utilization: float = 0.90
    max_num_seqs: int = 32
    max_tokens: int = 4096
    temperature: float = 0.2
    test_temperature: float = 0.6
    seed: int = 42

    def validate(self) -> None:
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("Set BTP_MODEL to a local model directory or cached model identifier")
        for name in ("tensor_parallel_size", "max_model_len", "max_num_seqs", "max_tokens"):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_tokens >= self.max_model_len:
            raise ValueError("max_tokens must be smaller than max_model_len to leave room for the prompt")
        if type(self.seed) is not int or not 0 <= self.seed < 2**63 - 100_000:
            raise ValueError("seed must be a nonnegative integer below 2**63 - 100000")
        if not math.isfinite(self.gpu_memory_utilization) or not 0 < self.gpu_memory_utilization <= 1:
            raise ValueError("gpu_memory_utilization must be finite and in (0, 1]")
        for name in ("temperature", "test_temperature"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.dtype not in {"auto", "half", "float16", "bfloat16", "float", "float32"}:
            raise ValueError("unsupported dtype; use auto, half, float16, bfloat16, float or float32")


def add_runtime_arguments(parser) -> None:
    parser.add_argument("--model", help="Local directory or cached identifier; defaults to BTP_MODEL")
    parser.add_argument("--dtype", default="auto")
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.90)
    parser.add_argument("--max-num-seqs", type=int, default=32)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--test-temperature", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=42)


def config_from_args(args) -> RuntimeConfig:
    load_dotenv()
    config = RuntimeConfig(**{
        name: (args.model if args.model is not None else os.getenv("BTP_MODEL", ""))
        if name == "model" else getattr(args, name)
        for name in RuntimeConfig.__dataclass_fields__
    })
    config.validate()
    return config


def default_config() -> RuntimeConfig:
    load_dotenv()
    config = RuntimeConfig(model=os.getenv("BTP_MODEL", ""))
    config.validate()
    return config


def enable_offline_mode() -> None:
    # Set before importing either the cache library or the model runtime.
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
                 "VLLM_NO_USAGE_STATS"):
        os.environ[name] = "1"


def describe_runtime(config: RuntimeConfig) -> dict:
    """Resolve model files and dependency metadata without constructing an LLM."""
    config.validate()
    enable_offline_mode()
    versions = {}
    for package in ("vllm", "huggingface_hub", "transformers", "torch"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeSetupError(f"Required runtime package {package!r} is not installed") from exc
    directory = Path(config.model).expanduser()
    if directory.exists():
        if not directory.is_dir():
            raise RuntimeSetupError("BTP_MODEL must name a directory, not a single weight file")
    else:
        try:
            from huggingface_hub import snapshot_download
            directory = Path(snapshot_download(repo_id=config.model, local_files_only=True))
        except Exception as exc:
            raise RuntimeSetupError(
                f"Model {config.model!r} is not available locally. Set BTP_MODEL to a complete "
                "local model directory or an already cached identifier. No download was attempted."
            ) from exc
    directory = directory.resolve()
    if not (directory / "config.json").is_file():
        raise RuntimeSetupError(f"Model directory has no config.json: {directory}")
    files = [p for p in sorted(directory.rglob("*")) if p.is_file() and ".git" not in p.parts]
    if not any(p.suffix in {".safetensors", ".bin", ".pt", ".gguf"} for p in files):
        raise RuntimeSetupError(f"No local weight files found in {directory}")
    manifest = {}
    for path in files:
        stat = path.stat()
        item = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if path.suffix in {".json", ".model", ".txt"}:
            item["sha256"] = file_digest(path)
        manifest[path.relative_to(directory).as_posix()] = item
    return {
        "backend": "vllm", "requested_model": config.model,
        "resolved_model": str(directory),
        "snapshot_revision": directory.name if directory.parent.name == "snapshots" else None,
        "model_manifest": manifest, "model_manifest_sha256": digest(manifest),
        "versions": versions, "settings": asdict(config),
        "python": sys.version, "executable": sys.executable, "platform": platform.platform(),
    }


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
    schema_name: str = "response"


@dataclass(frozen=True)
class InferenceOutput:
    response: str
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    batch_latency_s: float | None = None
    finish_reason: str | None = None


def batch_key(request: InferenceRequest) -> str:
    return digest({"schema": request.schema, "temperature": request.temperature,
                   "max_tokens": request.max_tokens, "seed": request.seed})


class OfflineVLLM:
    def __init__(self, config: RuntimeConfig, identity: dict) -> None:
        enable_offline_mode()
        try:
            from vllm import LLM, SamplingParams
            from vllm.sampling_params import StructuredOutputsParams
        except (ImportError, OSError) as exc:
            raise RuntimeSetupError(
                "A compatible vLLM installation with StructuredOutputsParams is required: " + str(exc)
            ) from exc
        self.config = config
        self.SamplingParams = SamplingParams
        self.StructuredOutputsParams = StructuredOutputsParams
        try:
            SamplingParams(
                max_tokens=config.max_tokens, seed=config.seed,
                structured_outputs=StructuredOutputsParams(json={"type": "object"}),
            )
        except Exception as exc:
            raise RuntimeSetupError(
                "vLLM must support SamplingParams(structured_outputs=StructuredOutputsParams(json=...)): "
                + str(exc)
            ) from exc
        try:
            self.llm = LLM(
                model=identity["resolved_model"], tokenizer=identity["resolved_model"],
                trust_remote_code=False, generation_config="vllm", dtype=config.dtype,
                tensor_parallel_size=config.tensor_parallel_size,
                max_model_len=config.max_model_len,
                gpu_memory_utilization=config.gpu_memory_utilization,
                max_num_seqs=config.max_num_seqs,
            )
            self.tokenizer = self.llm.get_tokenizer()
        except Exception as exc:
            raise RuntimeSetupError("Local model initialization failed: " + str(exc)) from exc

    def generate_batch(self, requests: list[InferenceRequest]) -> list[InferenceOutput]:
        if not requests:
            return []
        if len({batch_key(request) for request in requests}) != 1:
            raise ValueError("An inference batch must share schema and sampling settings")
        prompts, counts = [], []
        for request in requests:
            prompt = self.tokenizer.apply_chat_template(
                [{"role": "system", "content": request.system_prompt},
                 {"role": "user", "content": request.user_prompt}],
                tokenize=False, add_generation_prompt=True,
            )
            token_ids = self.tokenizer.encode(prompt, add_special_tokens=False)
            count = len(token_ids)
            if count + request.max_tokens > self.config.max_model_len:
                raise ContextBudgetExceeded(
                    f"{request.task}/{request.step}: {count} prompt + {request.max_tokens} "
                    f"output tokens exceeds context {self.config.max_model_len}; nothing was truncated",
                    request=request, prompt_tokens=count,
                )
            # Send exactly the tokens counted above, without adding another BOS.
            prompts.append({"prompt_token_ids": token_ids})
            counts.append(count)
        first = requests[0]
        params = self.SamplingParams(
            temperature=first.temperature, max_tokens=first.max_tokens, seed=first.seed,
            structured_outputs=self.StructuredOutputsParams(json=first.schema),
        )
        started = time.monotonic()
        outputs = self.llm.generate(prompts, params)
        elapsed = time.monotonic() - started
        if len(outputs) != len(requests) or any(not item.outputs for item in outputs):
            raise RuntimeError("vLLM returned missing outputs")
        return [InferenceOutput(
            response=item.outputs[0].text, latency_s=elapsed / len(outputs),
            prompt_tokens=count, completion_tokens=len(item.outputs[0].token_ids),
            batch_latency_s=elapsed, finish_reason=item.outputs[0].finish_reason,
        ) for item, count in zip(outputs, counts)]


class InferenceSession:
    """Invocation-owned lazy engine; model initialization never occurs at import."""
    def __init__(self, config: RuntimeConfig, identity: dict | None = None) -> None:
        self.config = config
        self.identity = describe_runtime(config) if identity is None else identity
        self.engine = None

    def generate_batch(self, requests: list[InferenceRequest]) -> list[InferenceOutput]:
        if not requests:
            return []
        if self.engine is None:
            self.engine = OfflineVLLM(self.config, self.identity)
        return self.engine.generate_batch(requests)
