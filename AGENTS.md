# AGENTS.md

## Purpose

This repository is a research prototype for **specification-driven black-box program replication**.

Given:

1. a natural-language specification,
2. a black-box reference executable whose source is unavailable, and
3. a description of the valid stdin format,

the system asks an LLM to synthesize a replacement program and evaluates whether
the generated program matches the reference program's observable behaviour.

The research goal is **behavioural equivalence**, not source-code recovery or
algorithm reconstruction.

---

## Current project state

This is the historical one-shot implementation on `main`. Validation is
user-managed; implementation history is not current empirical evidence.
Use user-supplied task configurations and reference executables.

---

## Core research contract

For the current version, every target is a deterministic command-line program:

```text
stdin -> program -> stdout
```

The framework currently supports generated candidates in:

- Python
- C++20

The LLM may choose between those supported languages.

A test case is a complete stdin string.

For successful executions, output comparison is currently **exact stdout
equality**.

`stderr` is diagnostic only.

A candidate/reference execution is considered unsuccessful if it:

- cannot be launched,
- times out, or
- exits with a non-zero status.

Do not add HTTP, GUI, stateful-session, or execution-trace interfaces unless the
user explicitly changes the project scope.

---

## Current baseline pipeline

The implemented no-feedback pipeline is:

```text
natural-language specification
        |
        v
LLM candidate generation
        |
        v
Python/C++ build or materialization
        |
        v
LLM stdin test generation
        |
        v
same stdin sent to reference + candidate
        |
        v
exact stdout differential comparison
        |
        v
persist run artifacts + baseline accuracy
```

The baseline intentionally contains **no repair loop**.

---

## Planned research comparison

The intended main comparison is:

1. no-feedback/spec-only baseline,
2. raw failure feedback,
3. abstract failure feedback.

Raw feedback is expected to contain:

- stdin,
- black-box/reference stdout,
- generated-program stdout.

Abstract feedback will be produced by an LLM that groups/summarizes failure
patterns into behavioural classes.

When repair is implemented, repair the **current candidate directly**:

```text
specification + current candidate + feedback
                    |
                    v
               repair LLM
                    |
                    v
             repaired candidate
```

Do **not** reintroduce the old methodology of:

- rule generation,
- rule completeness,
- triage stages,
- specification rewriting/refinement,
- regenerating code indirectly through a rewritten specification.

Those were intentionally removed from the repository.

Execution-trace feedback is a possible later extension, not part of the current
core experiment.

---

## Important pending design cleanup

The current code/task schema still contains an `output_format` field.

The intended design is to **remove it**.

Reason:

- `input_format` is operational information needed to construct valid stdin.
- output semantics belong to the natural-language specification itself.
- providing a separate output-format description may leak extra behavioural
  information and make an incomplete specification artificially easier.

The desired task shape is therefore:

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

Before building later phases, remove `output_format` consistently from:

- benchmark task JSON,
- `BenchmarkTask`,
- candidate generation function arguments,
- candidate-generation prompt construction,
- documentation that depends on it.

Do not invent a replacement field unless the user asks for one.

---

## Repository layout

Current important files:

```text
AGENTS.md

pipeline/
  __init__.py
  baseline.py
  builder.py
  candidate.py
  differential.py
  env.py
  execution.py
  generator.py
  llm_client.py
  llm_log.py
  llm_runtime.py
  task.py
  test_generator.py
  prompts/
    code_generation.txt
    test_generation.txt

```

---

## Responsibilities of the current modules

### `pipeline/execution.py`

Generic process execution.

It captures:

- stdin,
- stdout,
- stderr,
- exit code,
- timeout status,
- duration,
- launch errors.

It does not use a shell.

Generated candidates must run with a **sanitized environment** so they do not
inherit API keys or Codespaces secrets.

This is not yet a complete OS-level sandbox.

### `pipeline/differential.py`

Runs the same testcase against reference and candidate and classifies:

- pass,
- output mismatch,
- reference timeout/error,
- candidate timeout/error.

### `pipeline/candidate.py`

Validated representation of generated source.

Supported languages are currently only:

- `python`
- `cpp`

Do not casually expand language support; it adds build/runtime complexity
without helping the current experiment.

### `pipeline/builder.py`

Materializes Python candidates and compiles C++ candidates with C++20.

Build failures are represented as experiment data rather than crashing the
whole experiment.

### `pipeline/generator.py`

Makes the initial structured LLM call to produce a candidate.

The candidate LLM must:

- read stdin,
- write only required output to stdout,
- emit no debugging text on stdout,
- choose Python or C++,
- return structured data matching the requested schema.

### `pipeline/test_generator.py`

Produces complete stdin payloads from the specification and input-format
description.

The current version intentionally uses only basic LLM test generation.

Do not add boundary-focused, mutation-based, coverage-guided, adversarial, or
failure-guided generation until that research phase is explicitly discussed.

### `pipeline/baseline.py`

Orchestrates one complete no-feedback experiment.

Typical command:

```bash
python -m pipeline.baseline path/to/task.json --tests 10
```

### `pipeline/llm_client.py`

OpenAI-compatible `/v1/chat/completions` client.

Supports local vLLM and authenticated hosted endpoints such as OpenRouter.

Configuration is via environment variables:

```text
BTP_LLM_ENDPOINT
BTP_LLM_API_KEY
BTP_MODEL
BTP_HTTP_REFERER
BTP_X_TITLE
```

Never hard-code or commit API keys.

### `pipeline/env.py`

Loads repository-root `.env` without overriding environment variables that are
already set.

### `pipeline/llm_log.py` / `pipeline/llm_runtime.py`

Preserve complete LLM call provenance such as:

- step,
- model,
- seed,
- temperature,
- max tokens,
- system prompt,
- user prompt,
- response,
- latency.

This logging is important for research reproducibility.

---

## OpenRouter / local model setup

A committed `.env.example` is provided.

For OpenRouter:

```env
BTP_LLM_ENDPOINT=https://openrouter.ai/api/v1/chat/completions
BTP_LLM_API_KEY=
BTP_MODEL=openrouter/free
BTP_HTTP_REFERER=https://github.com/chrisrex007/btp-spec-replication
BTP_X_TITLE=BTP Spec Replication
```

For local vLLM, no API key is required.

Never print, log, commit, or copy real API keys into repository files.

The generated candidate must never inherit `BTP_LLM_API_KEY`.

---

## Run artifacts

Generated experiment runs are written under:

```text
runs/<run-id>/
```

and are ignored by Git.

Current run artifacts may include:

```text
specification.txt
task.json
candidate/
  metadata.json
  main.py or main.cpp
  program
build.json
tests.json
results.json
failures.json
summary.json
llm_log.jsonl
```

Some of these are redundant by design for experiment inspection/reproducibility.
Do not aggressively remove run artifacts unless the user asks.

Do not commit ordinary generated runs.

Curated experimental results can be introduced later under a deliberate,
versioned results structure.

---

## Development rules

### Keep changes phase-scoped

The user prefers to review the project **one phase at a time**.

Do not jump ahead and implement future research phases without explicit
approval.

For a new phase:

1. explain the phase,
2. get feedback/approval,
3. implement only the approved scope,
4. update user-run pipeline commands and artifact documentation,
5. report exactly what changed.

### Ask on material research choices

If a decision could materially affect experimental validity, ask the user
instead of silently selecting an approach.

Do not re-ask decisions already settled in this file.

### Keep implementation simple

Prefer:

- Python standard library,
- small modules,
- dataclasses for structured results,
- explicit JSON artifacts,
- deterministic interfaces,
- dependency-free infrastructure where practical.

Avoid introducing frameworks or abstractions that are not yet necessary.

### Preserve reproducibility

Whenever an LLM is involved, retain enough metadata to reconstruct the call.

Do not claim an experiment succeeded unless it was actually executed.

Never fabricate performance numbers, behavioural accuracy, or experimental
results.

### Protect secrets

Generated LLM code is untrusted.

Do not expose parent environment secrets to generated candidates.

Do not commit:

- `.env`,
- API keys,
- secrets,
- ordinary `runs/`,
- generated bytecode,
- temporary build output.

### User-managed validation

Do not add automated harness checks unless the user explicitly asks. Agents must
not execute the pipeline, benchmarks, or candidate/reference programs. Inspect
source and diffs and maintain user-run pipeline commands in `README.md`.

---

## Git workflow

Use feature branches for implementation.

Do not push changes directly to `main` unless the user explicitly requests it.

Do not merge a pull request or branch automatically unless the user explicitly
asks.

Keep commits focused and descriptive.

---

## What to work on next

Do not assume the next step is implementation.

Current immediate state:

1. The historical one-shot baseline is implemented.
2. Validation outcomes must come from actual user-provided results.
3. `output_format` removal is an approved pending cleanup.
4. Phase 6 (raw-feedback repair) has not yet been fully reviewed/approved for
   implementation in the current continuation flow.

The next agent should therefore first respect any new instruction from the user.
If the user asks to continue the research plan, discuss **Phase 6 only** before
implementing it.
