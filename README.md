# BTP Spec Replication

Research infrastructure for synthesizing a program from a natural-language
specification and measuring its behavioural agreement with a black-box reference
implementation.

The current repository implements **Phases 0–5**: a complete one-shot baseline
with stdin/stdout programs. It does **not** implement feedback-driven repair yet.

## Requirements

- Python 3.10+
- `g++` with C++20 support if the LLM chooses C++
- An OpenAI-compatible `/v1/chat/completions` endpoint with structured-output
  support

## Fastest first run: OpenRouter + Codespaces

The repository includes a ready-to-run smoke-test benchmark at:

```text
benchmarks/double/
├── spec.md
├── blackbox.py
└── task.json
```

Copy the example environment file:

```bash
cp .env.example .env
```

Then edit `.env` and set your own OpenRouter key:

```env
BTP_LLM_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
BTP_LLM_API_KEY=your-key-here
BTP_MODEL=openrouter/free
BTP_HTTP_REFERER=https://github.com/chrisrex007/btp-spec-replication
BTP_X_TITLE=BTP Spec Replication
```

The pipeline loads the repository-root `.env` automatically and never
overrides variables that are already present in the shell/Codespaces
environment. `.env` is ignored by Git.

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

For OpenRouter, the client adds the Bearer token automatically. The
`HTTP-Referer` and `X-Title` headers are optional. Structured requests also
ask OpenRouter to route only through providers that honor the required request
parameters.

## Local vLLM

The same code still works without an API key:

```bash
export BTP_LLM_ENDPOINT=http://127.0.0.1:8174/v1/chat/completions
export BTP_MODEL=qwen2.5-32b
unset BTP_LLM_API_KEY
```

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
  "output_format": "Print one integer followed by a newline.",
  "timeout_seconds": 2.0
}
```

Paths are resolved relative to the task JSON file. The reference command is run
with the configured `cwd`.

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
