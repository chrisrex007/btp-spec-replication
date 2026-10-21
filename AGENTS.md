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

The preserved pre-comparison implementation branch is:

```text
experiments/real-software-v1
```

GPU testing is paused as of 2026-10-21. The tag
`test-stop/raw-feedback-v1` preserves the offline raw-feedback implementation
for later testing; it is not a validation claim. See
`docs/checkpoints/raw-feedback-v1.md` for the deferred GPU checklist.

Continue on `experiments/raw-feedback`, renamed from the planning-only
`experiments/comparison-foundation` branch. The approved roadmap in
`docs/ROADMAP.md` uses five work branches total, six including `main`:
`real-software-v1`, `raw-feedback`, `comparison-foundation`, `feedback-variants`,
and `evaluation-reporting`, all under `experiments/`. Create future branches
only when their phase starts. Preserve the existing checkpoint and historical
branch; the checkpoint includes raw repair, not only the no-feedback baseline.
GPU testing does not block local development; keep local unit checks.
Review each phase and material research choices before implementing it.

Do not merge it into `main` unless the user explicitly asks.

Phases 0-5 are implemented and have been exercised successfully in GitHub
Codespaces.

The verified smoke test was:

```bash
python -m unittest discover -s tests -v
```

with 26 tests passing, followed by:

```bash
python -m pipeline.baseline benchmarks/double/task.json --tests 10
```

which completed successfully with 10/10 differential tests passing.

Treat the `double` benchmark only as a plumbing/smoke test. Its 100% score is
not evidence that the synthesis approach works on difficult programs.

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
Choose collection mechanisms during the feedback-variants phase review.

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

Candidate path/trace feedback is part of the core planned experiment and will
be implemented alongside abstract feedback in `experiments/feedback-variants`.
Both plug into the shared repair orchestration; neither is implemented yet.
All differential scoring uses the normal uninstrumented candidate.

---

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

---

## Pilot benchmark policy

The current experiment branch starts with ten real command-line software
targets, ordered roughly from easy to hard.

If a target reaches 100% baseline agreement on the pilot/development test pool,
delete that target from the active benchmark set. The project is specifically
interested in tasks where failures exist and feedback can potentially improve
the candidate.

Never use final held-out scores to decide which targets remain. Filtering must
be based only on the pilot/development pool before held-out evaluation.

Large testcase pools are deferred. When added, generate them in batches, persist
and deduplicate them, and reuse the same frozen pool across experimental arms.

## Repository layout

Current important files:

```text
AGENTS.md

benchmarks/
  double/
    spec.md
    blackbox.py
    task.json

pipeline/
  __init__.py
  baseline.py
  offline_batch.py
  offline_runtime.py
  repair.py
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

tests/
  test_baseline.py
  test_builder.py
  test_double_benchmark.py
  test_execution.py
  test_generation.py
  test_llm_config.py
  test_task.py
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
python -m pipeline.baseline benchmarks/double/task.json --tests 10
```

### `pipeline/offline_batch.py` / `pipeline/offline_runtime.py`

The resumable multi-task runner uses one in-process vLLM `LLM` instance and
`SamplingParams` batches for initial generation, testcase generation, and raw
failure-feedback repair. It checkpoints each inference response and experiment
stage to persistent output storage. Benchmark builds and differential suites
run concurrently up to the configured worker count. Do not replace this path
with an HTTP server, Ray, or distributed serving unless the user changes scope.

### `pipeline/llm_client.py`

OpenAI-compatible `/v1/chat/completions` client.

Supports local vLLM through an OpenAI-compatible endpoint.

Configuration is via environment variables:

```text
BTP_LLM_ENDPOINT
BTP_LLM_API_KEY
BTP_MODEL
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

## PARAM Shakti GPU environment

The user now has approved access to IIT Kharagpur's **PARAM Shakti** HPC system.
The intended setup is batched offline vLLM inference within a Slurm job.

Official system guidance relevant to this project:

- Cluster login host: `paramshakti.iitkgp.ac.in`.
- Off-campus SSH access uses port `4422`.
- Workload scheduling is through Slurm.
- Heavy computation and model serving must run on allocated compute/GPU nodes,
  not on the login node.
- GPU jobs use the GPU partition and request GPUs through Slurm, e.g.
  `--gres=gpu:1` (or more only when actually needed).
- The documented GPU-node range is `gpu001` through `gpu022`.
- Use `/home/<username>/` primarily for persistent software/configuration.
- Use `/scratch/<username>/` for model weights, caches, datasets, experiment
  data, and other large project files.
- Home quota is up to 50 GB; scratch quota is up to 2 TB (soft limit).
- Scratch data is not backed up and has a 30-day default retention limit.
  Important results must be copied to a persistent home/project location.
- Submit Slurm jobs only while the current working directory is under `$SCRATCH`
  (or the user's corresponding scratch path). Submission from `/home` can
  trigger account restrictions. Keep Slurm output files in scratch as well.
- If the cluster sends an account-lockout warning, stop submitting/logging in
  and follow its support-ticket/unlock instructions. Never retry to test access.
- Login nodes are for simple tasks only. All CPU/memory-intensive work must run
  in scheduled compute-node jobs.
- PARAM Shakti is for academic research. Users are responsible for software
  and model license compliance, backups, and protection of generated data.
- Publications, presentations, thesis, webpages, and similar outputs must
  acknowledge PARAM Shakti and NSM. The user-provided acknowledgement template
  is recorded below; the user should also inform PARAM Shakti administration
  about outcomes for annual reporting/documentation.
- Users must not share passwords or allow multiple people to use the same
  account. A project adviser must already have a PARAM Shakti account before
  requesting group-member accounts.
- Check `hpc.iitkgp.ac.in` and relevant local newsgroups for cluster notices.
- Inspect the live module/software environment with `module avail` rather than
  assuming a particular CUDA/PyTorch version.
- Slurm fair-share/history affects scheduling priority, so do not hold GPU
  allocations idle unnecessarily.

Do not assume the exact GPU model or VRAM from the public documentation. Before
choosing the serving model, inspect the actual allocated node/GPU using the live
cluster environment (for example `nvidia-smi` from within a GPU allocation).

User-reported live checks on 2026-10-20 found a Tesla V100-PCIE-16GB on one
allocated node, with NVIDIA driver 550.163.01 (which reports CUDA 12.4). Treat
this as an observation for that allocation, not a guarantee for every GPU node.
The `apps/python/3.10.13/modulefile` module provided Python 3.10.13; loading
`apps/python-package/python/3.10.13` alone left the default Python 3.6.8 active.
The Apptainer 1.4.0 module failed to start because `libsubid.so.3` was missing,
and the CUDA 12.4 module did not provide `nvcc` in `PATH` during that check.

The user supplied the PARAM Shakti usage policy on 2026-10-20. Use this
acknowledgement in publications and related outputs, or a similar statement:

> We acknowledge National Supercomputing Mission (NSM) for providing computing
> resources of 'PARAM Shakti' at IIT Kharagpur, which is implemented by C-DAC
> and supported by the Ministry of Electronics and Information Technology
> (MeitY) and Department of Science and Technology (DST), Government of India.

### Intended offline inference architecture

The PARAM Shakti experiment runs in one Slurm job:

```text
Slurm GPU allocation -> offline_batch.py -> one vLLM LLM instance
                                           -> batched inference
                                           -> differential tests / repair
```

This workflow uses vLLM's Python `LLM` and `SamplingParams` APIs directly. Do
not start an HTTP server or SSH tunnel for this workflow. The existing
OpenAI-compatible client remains available for the one-task baseline.

### PARAM Shakti implementation rules

When continuing this setup:

1. All interaction with PARAM Shakti must be mediated by the user. Provide
   commands for the user to run and use the outputs they share; do not connect
   to the cluster or execute cluster commands directly. Never ask the user to
   share passwords, private keys, or other cluster credentials.
2. Submit jobs only from the user's `$SCRATCH` directory. Ensure the submission
   working directory and Slurm output path are under scratch; the job may read
   code from the project checkout while running on an allocated compute node.
3. Do not inspect or attach to other users' jobs or model services for this
   offline workflow; use the user's own Slurm allocation.
4. First inspect the live Slurm partitions, GPU availability, GPU model/VRAM,
   module versions, and account limits.
5. Choose an open-weight model only after the actual GPU memory is known.
6. Use vLLM's Python offline inference API (`LLM`, `SamplingParams`) for the
   Slurm batch runner; do not introduce an HTTP endpoint for that workflow.
7. Keep large Hugging Face/model caches on scratch, not in the repository and
   not unnecessarily in home.
8. Initialize the model only inside a Slurm GPU allocation/job and reuse the
   same in-process model instance for all requests in that job.
9. Save experiment outputs under persistent home/project storage; scratch is
   temporary, unbacked-up storage with a 30-day default retention period.
10. Keep generated candidate execution separate from model-serving credentials
   and cluster secrets.
11. Do not commit usernames, passwords, SSH private keys, access tokens, cluster
   secrets, or account-specific allocation identifiers.
12. Persist experiment metadata/results needed for the thesis outside scratch
   before its retention window can remove them.
13. Keep the offline Slurm runner modular and reuse task, candidate, build, and
    differential-testing components from the existing pipeline.

The initial serving choice is Qwen2.5-7B-Instruct in FP16 with tensor
parallelism across two V100 GPUs on one node, per the user's chosen FP16 setup.
The configurable job defaults to GPU partition, 2 GPUs, 8 CPUs, 32 GB memory,
and 3 hours. Supply the account privately at submission time. It uses vLLM
0.7.3 with Python 3.10.13 and
caps the context at 8192 tokens. Setup and resumption instructions are in
`hpc/paramshakti/`.

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
4. add/update tests,
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

### Maintain tests

Before considering infrastructure changes complete, run:

```bash
python -m unittest discover -s tests -v
```

Keep the test suite free of required external LLM/API calls where possible.

The `double` benchmark should remain a cheap local smoke test.

---

## Git workflow

Use feature branches for implementation.

The current continuation branch is:

```text
experiments/raw-feedback
```

Do not push changes directly to `main` unless the user explicitly requests it.

Do not merge a pull request or branch automatically unless the user explicitly
asks.

Keep commits focused and descriptive.

---

## What to work on next

Do not assume the next step is implementation.

Current immediate state:

1. The one-task no-feedback baseline remains the Phases 0-5 reference path.
2. The offline batch runner now supports batched generation, raw-feedback
   repair, checkpointing, and resumption.
3. PARAM Shakti execution must be initiated and managed by the user; use the
   provided Slurm script and review the outputs they share.
4. GPU validation is deferred at `test-stop/raw-feedback-v1`. Continue with
   the phase-scoped plan in `docs/ROADMAP.md`; do not wait for GPU testing to
   prepare the next phase. The branch/roadmap reorganization is implemented;
   the next code phase is reusable repair orchestration and raw-feedback
   strategy extraction, plus offline/resume/configuration/Slurm hardening.
5. The final comparison is baseline vs raw vs abstract vs candidate path/trace.
   Review each code phase and its material research choices before implementing
   it. Trace mechanisms, pool sizes, repetitions, feedback limits and final
   scoring details remain phase-review decisions.

The next agent should first follow the user's current instruction. Do not infer
additional research phases from the existence of the offline raw-feedback
runner; discuss any new experimental method before implementing it.
