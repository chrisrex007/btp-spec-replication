# BTP Spec Replication

Research infrastructure for synthesizing a program from a natural-language
specification and measuring its behavioural agreement with a black-box reference
implementation.

The repository includes the Phases 0–5 one-shot baseline and a separate
resumable offline batch runner with raw failure-feedback repair.

GPU testing is currently paused. The source checkpoint and deferred acceptance
checks are recorded in [the testing stop](docs/checkpoints/raw-feedback-v1.md).
The [remaining-work roadmap](docs/ROADMAP.md) groups continued development into
three further branches (four work branches including the existing checkpoint).

## Requirements

- Python 3.10+
- `g++` with C++20 support if the LLM chooses C++
- vLLM 0.7.3 in the PARAM Shakti Slurm environment for offline batched runs

## Existing one-task baseline

The repository includes a ready-to-run smoke-test benchmark at:

```text
benchmarks/double/
├── spec.md
├── blackbox.py
└── task.json
```

The `.env.example` contains optional settings for the existing online baseline
client. The offline Slurm runner uses its `--model` option and does not read
`BTP_LLM_ENDPOINT`.

The baseline continues to use the OpenAI-compatible client. Configure a
compatible endpoint in `.env` only when running that baseline. The PARAM Shakti
workflow below uses the offline vLLM Python API directly and does not use an
HTTP server or tunnel.

Run the complete Phase 0–5 baseline:

```bash
python -m pipeline.baseline benchmarks/double/task.json --tests 10
```

This performs:

```text
specification
    ↓
LLM candidate generation
    ↓
candidate build
    ↓
LLM stdin testcase generation
    ↓
black-box vs candidate differential execution
    ↓
results + failures + baseline accuracy
```

For this baseline, the client loads repository-root `.env` without overriding
variables already set in the shell. `.env` is ignored by Git.

## PARAM Shakti offline batch experiments

Run [`pipeline.offline_batch`](pipeline/offline_batch.py) for batched candidate
generation, testcase generation, differential testing, and iterative raw
failure-feedback repair. It loads one vLLM `LLM` instance per job, batches
requests across benchmark tasks, and checkpoints progress for resumption.
Follow [the PARAM Shakti setup guide](hpc/paramshakti/README.md) for the Slurm
script and configuration. The selected Qwen2.5-7B-Instruct FP16 model uses two
V100 GPUs on one node. Inference runs directly through vLLM's Python API; no
HTTP server or tunnel is started. Model files use scratch; experiment artifacts
default to persistent home storage. All cluster interaction remains
user-mediated.

## Task configuration

A benchmark task is described by JSON:

```json
{
  "name": "example",
  "specification": "spec.md",
  "reference": {
    "command": ["python3", "blackbox.py"],
    "cwd": "."
  },
  "input_format": "One integer x followed by a newline.",
  "timeout_seconds": 2.0
}
```

Paths are resolved relative to the task JSON file. The reference command is run
with the configured `cwd`. The synthesis/test-generation LLMs receive the
natural-language specification and input-format description; they do not receive
the hidden reference command.

## Real-software pilot benchmarks

The `experiments/real-software-v1` branch contains ten hidden-oracle command-line
benchmarks under `benchmarks/01_...` through `benchmarks/10_...`. See
`benchmarks/README.md` for ordering and the pilot-selection policy.


## Run artifacts

Each run is written under `runs/<run-id>/`:

```text
specification.txt
task.json
candidate/
  metadata.json
  main.py or main.cpp
  program              # for compiled C++ candidates
build.json
tests.json
results.json
failures.json
summary.json
llm_log.jsonl
```

The baseline score in `summary.json` is:

```text
passing differential tests / total differential tests
```

No failing examples are fed back to the LLM in the current baseline.

## Security note

Generated candidates do not inherit the parent process environment, so API keys
and Codespaces secrets are not exposed through environment variables during
candidate execution. This is **not** a full sandbox: generated code still runs
on the host and stronger filesystem/process isolation is future work.

## Tests

The unit tests do not require an LLM endpoint:

```bash
python -m unittest discover -s tests -v
```

C++ build tests are skipped automatically when `g++` is unavailable.
