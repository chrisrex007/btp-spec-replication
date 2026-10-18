# BTP Spec Replication

Research infrastructure for synthesizing a program from a natural-language
specification and measuring its behavioural agreement with a black-box reference
implementation.

The current repository implements **Phases 0–5**: a complete one-shot baseline
with stdin/stdout programs. It does **not** implement feedback-driven repair yet.

## Requirements

- Python 3.10+
- `g++` with C++20 support if the LLM chooses C++
- An OpenAI-compatible `/v1/chat/completions` endpoint that supports JSON-schema
  structured output

Configure the model endpoint with:

```bash
export BTP_LLM_ENDPOINT=http://127.0.0.1:8174/v1/chat/completions
export BTP_MODEL=qwen2.5-32b
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

## Run the baseline

From the repository root:

```bash
python -m pipeline.baseline path/to/task.json --tests 20
```

A run is written under `runs/<run-id>/`:

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

## Tests

The unit tests do not require an LLM endpoint:

```bash
python -m unittest discover -s tests -v
```

C++ build tests are skipped automatically when `g++` is unavailable.
