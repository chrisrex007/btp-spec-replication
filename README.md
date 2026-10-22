# Specification-driven program replication: one-shot baseline

Generate one Python or C++20 candidate from a specification and stdin description,
generate stdin cases, evaluate the unchanged candidate against a private reference,
and save the results. All validation is user-managed; agents must not execute the
pipeline or its target programs. No automated harness suite or example targets
are included.

## Prerequisites and local inference

Use Python 3.10+ and a compatible installation of `vllm`, `huggingface_hub`,
`transformers`, and `torch` in your chosen environment. The vLLM build must support
your platform/hardware and `StructuredOutputsParams` with `SamplingParams` and
`LLM`. See the [vLLM installation guide](https://docs.vllm.ai/en/stable/getting_started/installation/)
and [structured-output API](https://docs.vllm.ai/en/stable/features/structured_outputs/#offline-inference).
These dependencies and model files must already be available; the pipeline does
not install packages, provision hardware, or download weights. C++ candidates
also require `g++` with C++20 support (`CXX` can name another compiler executable).

Configure only the model in repository-root `.env`, keeping your own values private:

```dotenv
BTP_MODEL=/absolute/path/to/local/model
```

An already cached Hugging Face model identifier is also accepted. A complete local
model directory needs `config.json`, weights, tokenizer files, and the model's
other required assets. Missing/incomplete assets fail; they are never fetched.
Offline mode is enabled before importing model libraries. No HTTP server, API
endpoint, or API key is used. Model code requiring `trust_remote_code=True` is
unsupported. Prepare such assets or environments separately from this pipeline.

The `.env` loader supports `KEY=VALUE`, blank lines, `#` comments, matching quotes,
and optional `export` prefixes. Existing shell values override `.env`; `--model`
overrides both. The private `.env` is never changed by implementation work.

## Supply a task

Place your task JSON alongside its specification. Paths below are relative to
that JSON:

```json
{
  "name": "example",
  "specification": "spec.md",
  "reference": {"command": ["python", "reference.py"], "cwd": "."},
  "input_format": "Describe the complete valid stdin format here.",
  "timeout_seconds": 2.0
}
```

Use an interpreter/executable available in your environment. The specification
must state output semantics. Generation prompts receive only the specification
and stdin description; reference commands and task names are not prompt content.

## Commands for you to run

Run from the repository root, substituting the task path and a new run identifier:

```bash
python -m pipeline.baseline path/to/task.json --tests 20 --run-id my-baseline --seed 42
```

This command loads the local model once, then makes candidate-generation and
stdin-generation calls through the same engine. It executes both programs and
saves artifacts under `runs/my-baseline/`. This one-shot command has no resume;
use a new identifier after interruption. It never overwrites an existing run.

| Option | Default | Meaning |
| --- | --- | --- |
| `--model` | `BTP_MODEL` (required) | Local directory or cached identifier |
| `--tests` | `20` | Requested stdin count, before exact deduplication |
| `--run-root` | repository `runs/` | Artifact parent directory |
| `--run-id` | task plus UTC timestamp | New run directory identifier |
| `--seed` | `42` | Initial generation seed |
| `--temperature` | `0.2` | Candidate-generation sampling |
| `--test-temperature` | `0.6` | Stdin-generation sampling |
| `--max-tokens` | `4096` | Output budget for each inference call |
| `--max-model-len` | `8192` | Maximum prompt plus output token budget |
| `--dtype` | `auto` | vLLM weight dtype |
| `--tensor-parallel-size` | `1` | Runtime tensor parallelism |
| `--gpu-memory-utilization` | `0.90` | vLLM memory fraction |
| `--max-num-seqs` | `32` | Runtime sequence capacity |

Stdin generation uses seed `seed + 100000`. Sampling and engine settings are
recorded. Prompt-plus-output overflow fails without truncation. Explicit runtime
options must fit your local model and hardware; defaults are not an assurance of
hardware compatibility.

## Artifacts and result interpretation

The run contains `metadata.json`, `task.json`, `specification.txt`, candidate source
and `candidate/metadata.json`, `build.json`, `tests.json`, `results.json`,
`failures.json`, `summary.json`, and `llm_log.jsonl`. The `inference/` directory
stores each full request before inference and a response or error afterward.
Early failures leave only artifacts produced up to that point.

Metadata records the requested model, resolved local path, cache revision when
known, runtime versions/settings, and a file manifest. Small model metadata files
are hashed; large weight files are identified by their sizes and modification
times, not full weight checksums. Use immutable local model assets for research.
Inference records include prompts, schemas/names, seeds, responses/errors, token
counts, finish reasons, and latency (including model initialization in wall time).

Input is UTF-8 encoded without newline translation. Successful stdout must match
byte for byte; stderr is diagnostic. Output uses lossless UTF-8 `surrogateescape`
decoding and ASCII-escaped JSON. Recover original output bytes after JSON loading
with `stored_stdout.encode("utf-8", "surrogateescape")`.

If any reference cannot launch, times out, or exits nonzero, the run has
`invalid_reference` and `accuracy: null`. Otherwise accuracy is `n_pass/n_total`;
candidate errors/timeouts count as failures. `n_valid` counts successful reference
executions, `n_reference_failures` counts unsuccessful ones, and `n_fail` counts
failures among valid cases. `completed` does not imply 100% agreement.

CLI exit codes are `0` for completed evaluation, `2` for setup/stage/reference
failure, and `130` for user interruption. A failing summary retains its stage and
error; a build failure retains compiler diagnostics. Python syntax is validated
without executing the candidate during materialization.

## Troubleshooting and later validation

| Problem | Action |
| --- | --- |
| Missing model or cache entry | Set `BTP_MODEL` to a complete local model directory; obtain assets separately |
| Missing or incompatible dependencies | Use a vLLM-compatible environment exposing `StructuredOutputsParams`; inspect the saved error |
| Model initialization failure | Check model/hardware compatibility and explicit runtime options |
| Context overflow | Start a new run with a larger supported context or smaller output budget; nothing is silently shortened |
| Missing compiler | Provide `g++`/`CXX` if a C++ candidate was generated |
| Invalid reference | Inspect reference records, fix your external task/reference, and use a new run |
| Existing run directory | Choose a new `--run-id`; existing artifacts are preserved |

For later user validation, inspect Python and C++ materialization, mismatches that
differ only in line endings or invalid UTF-8, unsuccessful references, malformed
generation, missing weights, and context errors. No agent-run validation or
empirical success is claimed. Generated programs have sanitized environments;
this is not a full OS sandbox, and they still run on the host.
