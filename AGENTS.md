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

The agreed five-phase order is no-feedback, raw feedback, abstract feedback,
candidate path/trace feedback, and comparison/reporting. See `docs/ROADMAP.md`
for branch names and scope.

`experiments/no-feedback` preserves the existing baseline-only source checkpoint.
The current checkout is `experiments/raw-feedback`, which already contains raw
repair. Unfinished comparison and testcase-pool work is preserved as a WIP
checkpoint on that branch; its presence does not mean its phase has been reviewed
or completed.

The roadmap is the highest-priority implementation goal, but the user has asked
to wait for phase review before further implementation. Branch organization is
agreed; individual implementation phases and material research choices still
require review. Preserve existing work and historical commits.

## Core research contract

Every target is a deterministic command-line program. Generated candidates may
use:

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

Do not add HTTP, GUI, or stateful-session interfaces unless the user explicitly
changes the project scope. Candidate execution tracing is approved as a feedback
side-channel; scoring still uses the normal uninstrumented stdin/stdout program.

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
3. abstract failure feedback,
4. candidate path/trace feedback.

Raw feedback is expected to contain:

- stdin,
- black-box/reference stdout,
- generated-program stdout.

Abstract feedback will be produced by an LLM that groups/summarizes failure
patterns into behavioural classes.

Path/trace feedback adds a compact, normalized execution trace of the current
candidate to raw failure feedback. Never inspect or instrument the reference.
Provide Python and C++ collectors behind a common trace interface, persist
traces separately from stdout, and record collection errors and truncation.
Choose collection mechanisms during the path-feedback phase review.

All four arms share the same frozen initial candidate per task/seed, development
pool, held-out pool, and relevant model configuration. Repair arms share the
same maximum iteration budget and stopping rules. Record abstraction inference
and tracing overhead separately; equal repair rounds do not imply equal compute.
Held-out outcomes must never influence filtering, feedback, or repair.

The shared repair loop must repair the **current candidate directly**:

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

Abstract feedback belongs to `experiments/abstract-feedback`; candidate
path/trace feedback belongs to the subsequent `experiments/path-feedback` phase.
Both must use the shared direct-repair orchestration.

## Task information boundary

The separate `output_format` field has been removed.

The LLM-visible task information is:

- natural-language specification,
- input-format description.

Output behaviour must be described by the specification itself.

The reference command in `task.json` is harness-private and must never be
included in synthesis or testcase-generation prompts. Task names should also stay
neutral/descriptive so future prompt changes do not accidentally reveal utility
names.

## Environment configuration

Preserve the repository-root `.env` format: one `KEY=VALUE` entry per line,
with optional comments and quoted values. The existing online client uses
`BTP_MODEL`.
`.env.example` contains placeholders only. Existing shell environment variables
take precedence over `.env` values. Never read, copy, or print private `.env`
values merely to document the format.

Cluster setup, hardware choices, scheduler commands, and deployment details
are not current project guidance. Do not reconstruct removed infrastructure
documentation or infer a required testing environment from historical files.

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

### Implementation priority and documentation conflicts

The highest-priority implementation goal is to complete the agreed scope of
`docs/ROADMAP.md`, following the phase-review rules above. Do not silently omit
required roadmap capabilities or introduce unrelated work.

If Markdown files disagree about scope, phase order, branch organization,
research methodology, or what to do or avoid, identify the conflict and ask the
user before implementing the affected work. Continue independent, already
authorized work while awaiting clarification.

### User-managed validation

Do not add automated harness checks unless the user explicitly asks. Agents must
not execute the pipeline, benchmarks, or generated and reference programs.
Agents may inspect source and diffs. Keep exact user-run pipeline commands,
prerequisites, and expected artifacts in repository-root `README.md`.

Report implementation and validation separately. State that the pipeline was not
executed by the agent; claim validation only from user-provided results.

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


Do not push changes directly to `main` unless the user explicitly requests it.

Do not merge a pull request or branch automatically unless the user explicitly
asks.

Keep commits short and focused.
