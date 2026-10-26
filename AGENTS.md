# AGENTS.md

## Purpose and branch scope

This repository studies specification-driven black-box program replication.
Given a natural-language specification, a valid stdin description, and a hidden
reference executable, synthesize a replacement and measure behavioural agreement.
The goal is behavioural equivalence, not source recovery.

The active branch is `experiments/no-feedback`. Keep it self-contained and limited
to the one-shot baseline. Generate one candidate, build it, generate stdin tests,
compare executions, and persist artifacts. Do not add subsequent candidate
modification, failure-conditioned inference, or components belonging to other
experimental phases. Keep documentation specific to this branch as well.

## Research contract

- Targets are deterministic command-line programs with stdin/stdout interfaces.
- Generated candidates use Python or C++20 and the language standard library.
- One test case is a complete stdin string, encoded as UTF-8 without newline
  translation when supplied to either program.
- Successful executions require exact stdout equality, preserving original bytes.
  Do not normalize whitespace, line endings, or invalid UTF-8 sequences.
- Stderr is diagnostic only.
- Launch failures, timeouts, and non-zero exits are unsuccessful executions.
- Any unsuccessful reference execution invalidates the run: use
  `status: invalid_reference` and `accuracy: null`. Persist the individual results
  and count reference failures separately from candidate failures.
- When every reference execution succeeds, accuracy is passing cases divided by
  all evaluated cases. Candidate errors and timeouts count as failures.
- Do not add HTTP, GUI, or stateful target interfaces.

## Task information boundary

The LLM receives only the natural-language specification and input-format
description. Output behaviour belongs in the specification. There is no separate
output-format field.

The reference command and working directory are harness-private. Never include
them in generation prompts. Keep task names neutral; names are for harness
identity and logging, not additional LLM-visible information.

Do not introduce intermediate rules, triage stages, specification rewriting, or
indirect regeneration through a rewritten specification.

## Environment configuration

Preserve the repository-root `.env` format: one `KEY=VALUE` entry per line,
optional `#` comments, and matching single or double quotes around values.
Existing shell values take precedence. Only `BTP_MODEL` is required; it names a
local directory or an already cached model identifier. No server, credentials,
or downloads are used. Resolve files locally before creating one invocation-owned,
lazy vLLM engine. `.env.example` contains a placeholder only.
Existing shell values take precedence. The client requires only `BTP_MODEL`, a
single local checkpoint directory name beneath `~/models`. Use direct offline
vLLM inference; do not restore HTTP endpoints, API keys, attribution headers,
remote model downloads, or model fallback. `.env.example` contains a placeholder.

Never read, print, copy, or commit private `.env` values merely to document its
format. Deployment infrastructure, scheduler details, and specific hardware or
model choices are outside current guidance.

## Artifacts and reproducibility

Keep generated runs under ignored `runs/<run-id>/`. Preserve source, build
diagnostics, complete stdin tests, execution results, failures, summaries, and
LLM records; do not remove artifacts aggressively.

LLM records must retain prompts, local model identity, runtime versions, seed, temperature,
token limit, response schema and schema name, response or error, and latency.
LLM records must retain prompts, model, resolved local model path, offline backend,
runtime versions, inference settings, seed, temperature, token limit, response
schema and schema name, response or error, and latency.
Preserve failed logical calls as well as successful calls. Never log credentials.

Subprocess output uses lossless UTF-8 `surrogateescape` decoding internally.
Use ASCII-escaped JSON when persisting it so invalid bytes remain recoverable.
Do not replace undecodable bytes in values used for comparison.

## Development and testing

Work one reviewed phase at a time. Before extending scope, explain the phase and
get user approval. Ask before choices that materially affect experimental validity
or when Markdown instructions conflict. Do not re-ask decisions settled here.

Validation is user-managed. Do not add automated harness checks unless the user
explicitly asks. Agents must not execute the pipeline, benchmarks, or generated
and reference programs. Agents may inspect source and diffs. Maintain exact
user-run pipeline commands in repository-root `README.md`.

Report implementation and validation separately. State that the pipeline was not
executed by the agent; use actual user-provided outcomes for validation claims.
Never fabricate results or carry historical scores forward as current evidence.

Prefer standard-library Python, small modules, dataclasses, explicit JSON, and
deterministic interfaces. Avoid unnecessary frameworks and speculative features.
Basic test generation is the current scope; do not introduce specialized
generation strategies without review.

## Secrets and Git

Generated code is untrusted. Its execution must use a sanitized environment that
does not inherit parent secrets. Environment sanitization is not a full OS sandbox.

Do not commit `.env`, keys, secrets, ordinary runs, bytecode, or temporary build
output. Keep commits short and focused. Do not push to `main` or merge any branch
or pull request unless the user explicitly asks.
