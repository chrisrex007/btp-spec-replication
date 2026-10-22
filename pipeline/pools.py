"""Frozen basic-generation pools with a held-out read boundary."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random

from .offline_runtime import InferenceRequest
from .task import BenchmarkTask
from .test_generator import parse_tests_response, test_generation_request


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _task(task):
    return {"name": task.name, "specification_sha256": _hash(task.read_specification()),
            "input_format_sha256": _hash(task.input_format)}


def _counts(development_count, held_out_count):
    for count in (development_count, held_out_count):
        if type(count) is not int or count <= 0:
            raise ValueError("Pool counts must be positive integers")


def freeze_pool(task: BenchmarkTask, inputs: list[str], output_dir: Path, *,
                development_count: int, held_out_count: int, seed: int) -> dict:
    _counts(development_count, held_out_count)
    if not isinstance(inputs, list) or not all(isinstance(x, str) for x in inputs):
        raise ValueError("Pool inputs must be a list of stdin strings")
    unique = list(dict.fromkeys(inputs))
    if len(unique) < development_count + held_out_count:
        raise ValueError("Insufficient unique inputs for requested pool counts")
    random.Random(seed).shuffle(unique)
    development = unique[:development_count]
    held_out = unique[development_count:development_count + held_out_count]
    metadata = {"schema_version": 1, "task": _task(task), "seed": seed,
                "requested": {"development": development_count, "held_out": held_out_count},
                "input_count": len(inputs), "unique_count": len(unique),
                "development": {"count": len(development), "sha256": _hash(development)},
                "held_out": {"count": len(held_out), "sha256": _hash(held_out)}}
    output_dir = Path(output_dir)
    if (output_dir / "metadata.json").exists():
        existing, _ = load_held_out(output_dir, task)
        if existing != metadata:
            raise ValueError("Refusing to replace an existing frozen pool")
        return existing
    _write(output_dir / "development.json", development)
    _write(output_dir / "held_out.json", held_out)
    # Metadata is the commit marker, published after both payloads.
    _write(output_dir / "metadata.json", metadata)
    return metadata


def _load(pool_dir, task, split):
    pool_dir = Path(pool_dir)
    metadata = _read(pool_dir / "metadata.json")
    if metadata.get("schema_version") != 1 or metadata.get("task") != _task(task):
        raise ValueError("Pool version or task identity mismatch")
    values = _read(pool_dir / (split + ".json"))
    if (not isinstance(values, list) or not all(isinstance(x, str) for x in values)
            or len(values) != len(set(values))):
        raise ValueError("Invalid pool payload")
    if metadata.get(split) != {"count": len(values), "sha256": _hash(values)}:
        raise ValueError("Pool payload hash or count mismatch")
    if metadata.get("requested", {}).get(split) != len(values) or not values:
        raise ValueError("Pool requested count mismatch")
    return metadata, values


def load_development(pool_dir, task):
    """Never open the held-out payload during repair or target selection."""
    return _load(pool_dir, task, "development")


def load_held_out(pool_dir, task):
    metadata, held_out = _load(pool_dir, task, "held_out")
    development_metadata, development = load_development(pool_dir, task)
    if metadata != development_metadata or set(development).intersection(held_out):
        raise ValueError("Pool splits overlap or metadata changed")
    return metadata, held_out


def generate_pool(task, output_dir, runtime, model, development_count,
                  held_out_count, seed, batch_size=20, max_batches=50, resume=False):
    """Reuse one caller-owned runtime; persist every basic generation response."""
    _counts(development_count, held_out_count)
    _counts(batch_size, max_batches)
    output_dir = Path(output_dir)
    system, user, schema = test_generation_request(
        specification=task.read_specification(), input_format=task.input_format, count=batch_size)
    config = {"schema_version": 1, "task": _task(task), "model": model,
              "development_count": development_count, "held_out_count": held_out_count,
              "seed": seed, "batch_size": batch_size, "max_batches": max_batches,
              "system_prompt": system, "user_prompt": user, "schema": schema,
              "temperature": 0.6, "max_tokens": 4096}
    config_path = output_dir / "generation.json"
    if config_path.exists():
        if not resume:
            raise ValueError("Pool generation exists; use resume")
        if _read(config_path) != config:
            raise ValueError("Pool generation configuration mismatch")
    elif resume:
        raise ValueError("No pool generation checkpoint to resume")
    else:
        if output_dir.exists() and any(output_dir.iterdir()):
            raise ValueError("Pool output directory must be empty")
        _write(config_path, config)
    if (output_dir / "metadata.json").exists():
        metadata, _ = load_held_out(output_dir, task)
        return metadata
    inputs = []
    for batch in range(max_batches):
        request = InferenceRequest(task.name, "pool_test_generation", batch,
                                   system, user, schema, 0.6, 4096, seed + batch)
        call_path = output_dir / "calls" / f"{batch:04d}.json"
        if call_path.exists():
            call = _read(call_path)
            if call.get("request") != asdict(request) or call.get("model") != model:
                raise ValueError("Pool inference checkpoint mismatch")
            if call.get("response_sha256") != _hash(call["output"]):
                raise ValueError("Pool inference response hash mismatch")
        else:
            outputs = runtime.generate_batch([request])
            if len(outputs) != 1:
                raise ValueError("Expected one pool inference response")
            output = asdict(outputs[0])
            call = {"model": model, "request": asdict(request), "output": output,
                    "response_sha256": _hash(output)}
            _write(call_path, call)
        try:
            inputs.extend(parse_tests_response(call["output"]["response"]))
        except (ValueError, KeyError, TypeError):
            # Malformed responses remain evidence and consume a bounded batch.
            continue
        if len(set(inputs)) >= development_count + held_out_count:
            return freeze_pool(task, inputs, output_dir, development_count=development_count,
                               held_out_count=held_out_count, seed=seed)
    raise ValueError("Pool generation exhausted max_batches without enough unique inputs")
