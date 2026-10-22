# BTP Spec Replication

Research infrastructure for synthesizing a program from a natural-language
specification and measuring its behavioural agreement with a black-box reference
implementation.

Testing is user-owned. Agents must not run the pipeline or any unit,
integration, smoke, regression, or benchmark tests. Agents may implement
code and test cases and inspect source and diffs. The commands in this README
are for the user to execute; keep them current as implementation changes.

The repository includes a one-shot baseline and a separate
resumable offline batch runner with raw failure-feedback repair.

The [roadmap](docs/ROADMAP.md) defines five phases: no-feedback, raw feedback,
abstract feedback, candidate path/trace feedback, and comparison/reporting.
This branch organization is agreed. Further implementation waits for phase
review; completing the roadmap remains the highest priority. The current branch
is `experiments/raw-feedback`; `experiments/no-feedback` preserves the existing
baseline-only source checkpoint. Abstract and path/trace strategies remain
planned work, with uninstrumented candidate scoring.

## Requirements

- Python 3.10+
- `g++` with C++20 support if the LLM chooses C++

## One-task baseline

The bundled benchmarks have been removed. Supply your own task JSON,
specification, and black-box reference executable using the task format below.

The baseline uses an OpenAI-compatible client configured through repository-root
`.env`. Preserve this format, using your own values privately:

```dotenv
BTP_MODEL=your-model-name
BTP_LLM_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions
BTP_LLM_API_KEY=
```

Use one `KEY=VALUE` entry per line. Blank lines, `#` comments, and matching
single or double quotes around values are supported. The API key is optional
for endpoints that do not require authentication. `.env.example` contains only
placeholders; never commit or print private `.env` values.

For your own testing, replace `path/to/task.json` with your task's actual path:

```bash
python -m pipeline.baseline path/to/task.json --tests 10
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

Run the following commands yourself from the repository root. Agents must not
execute them, including tests that use fake inference runtimes. An implementation
is not empirically validated until you run the relevant checks and report the
results.

The unit tests require Python 3.10+ and do not require an LLM endpoint:

```bash
python -m unittest discover -s tests -v
```

Some legacy benchmark tests still depend on the removed bundled fixtures. Their
cleanup is pending review; the full suite is not currently expected to pass
without addressing those dependencies.
