# Deferred-GPU Development Roadmap

## Why this checkpoint exists

Real-model inference and PARAM Shakti experiments are intentionally paused.

Development continues with:

- unit tests,
- fixture-based tests,
- mocked LLM responses,
- deterministic local black-box/reference execution,
- schema/persistence/resume tests.

Do **not** consume GPU time or hosted-LLM quota merely to validate implementation
while this roadmap is being built.

The head of `experiments/real-software-v1` containing this document is the
**baseline testing stop point**. Preserve it as a reproducible checkpoint. It
contains the implemented Phases 0-5 baseline, the hidden-oracle real-software
benchmark definitions, and the current OpenAI-compatible LLM boundary. The ten
real-software targets have not yet been used for the real GPU pilot.

When GPU testing resumes, this checkpoint can be checked out independently and
used to verify the baseline before comparing later branches.

## Branch budget

Use **five work branches total, including this checkpoint branch**. Together
with `main`, the repository will therefore stay below seven branches.

Create branches sequentially from the preceding completed branch. Do not create
all future branches in advance.

| Branch | Scope | Deferred-GPU completion milestone |
| --- | --- | --- |
| `experiments/real-software-v1` | Existing Phase 0-5 baseline and real-software task definitions | Frozen baseline checkpoint; real-model pilot remains pending |
| `experiments/raw-feedback` | Raw-feedback repair loop, iteration state, offline inference boundary, checkpoint/resume, PARAM Shakti serving scaffolding | Raw repair works end-to-end with fixture LLM responses; no real inference required |
| `experiments/comparison-foundation` | Reusable testcase pools, batched generation, development/held-out split, shared initial candidates, experiment-arm configuration, stronger provenance | Baseline/raw comparison can be reproduced from frozen fixtures and persisted pools |
| `experiments/abstract-feedback` | Failure abstraction into behavioural classes, abstract-feedback repair, integration of baseline/raw/abstract arms | All three arms run through the same fixture-driven experiment runner |
| `experiments/evaluation-reporting` | Frozen held-out evaluation, aggregate metrics, regression/repair analysis, inference usage accounting, machine-readable and human-readable reports | Complete experiment can be prepared and locally validated without GPU calls |

No additional implementation branch should be introduced unless a genuinely
separate concern appears that cannot fit one of these scopes.

## Architectural inference stop point

All future LLM-dependent work must preserve a clean boundary between:

```text
prepare request
     |
     v
persist request + experiment state
     |
     +----> live OpenAI-compatible endpoint        (later)
     |
     +----> fixture/offline response               (now)
     |
     v
validate structured response
     |
     v
continue experiment
```

This is the key mechanism that allows implementation to continue while GPU
testing is deferred.

A workflow must be able to stop immediately before an inference request, save
enough state to resume, and later continue from a recorded response without
regenerating previous candidates/tests or changing experimental inputs.

## Branch 2: raw feedback

Implement the first actual repair strategy.

### Raw failure representation

A repair example contains the observable information already allowed by the
research design:

- stdin,
- reference stdout,
- candidate stdout,
- execution/comparison status when relevant.

Do not expose the reference command, executable name, source, or implementation
details to the repair model.

### Repair operation

Repair the **current candidate**, rather than rewriting the specification:

```text
specification
+ input format
+ current candidate source
+ raw failure examples
          |
          v
       repair LLM
          |
          v
   replacement candidate
```

Build the replacement and evaluate it on the development pool.

Support a configurable maximum number of repair iterations. Persist every
candidate, feedback payload, request, response, build result, and per-iteration
score.

### Offline/resume support

Refactor the LLM call path so a request has a serializable representation and
can be satisfied either by:

- the live OpenAI-compatible client, or
- a fixture/offline response.

Persist iteration state so an interrupted run can resume without repeating
completed LLM calls.

### PARAM Shakti scaffolding

Add configuration/scripts/documentation needed to launch an OpenAI-compatible
vLLM server under Slurm and point the existing pipeline at it, but do not lock
the model, GPU count, quantization, or tensor-parallel settings until actual
hardware is inspected.

No real GPU verification is required to complete this branch.

## Branch 3: comparison foundation

Make experimental comparisons fair and reusable.

### Persistent testcase pools

Move testcase generation out of individual strategy runs.

Support:

- generation in small batches,
- exact deduplication,
- deterministic persisted pool files,
- pool identity/hash/provenance,
- reuse without additional LLM calls.

This is where high-volume testcase generation is implemented. Hundreds of
testcases should be produced through multiple small requests, never one giant
prompt.

### Development and held-out split

Create a frozen split before repair:

- **development pool**: may drive failure feedback and repair,
- **held-out pool**: never shown to repair/abstraction steps and used only for
  final evaluation.

The split and seed must be persisted.

### Shared initial candidate

For a given task/seed/model, generate the initial candidate once.

The baseline result is that frozen initial candidate. Raw and abstract arms must
start from exactly the same candidate rather than independently regenerating
one.

### Pilot filtering

Use only the development/pilot pool for target eligibility.

If a target has 100% baseline agreement on that pool, remove it from the active
repair benchmark set as previously decided. Never use held-out results to make
this decision.

### Experiment configuration

Represent an experiment explicitly: task, model/config, seed, pool IDs, initial
candidate ID, strategy, iteration budget, and relevant prompt versions.

Improve provenance and resume checks so incompatible artifacts cannot be
silently mixed.

## Branch 4: abstract feedback

Implement the second repair treatment.

### Abstraction

Give an abstraction LLM the observed development failures and request a compact,
structured set of behavioural failure classes/patterns.

Persist both:

- the raw failures used to create the abstraction,
- the resulting abstraction.

### Abstract repair

The repair model receives:

- specification,
- input format,
- current candidate,
- abstract behavioural feedback.

It should **not** receive the individual raw failure examples in the abstract
arm.

### Three-arm integration

Run the comparison as:

```text
same frozen initial candidate
          |
          +---- baseline: no repair
          |
          +---- raw: raw failures -> repair
          |
          +---- abstract: failures -> abstraction -> repair
```

Use the same development pool, held-out pool, iteration budget, and relevant
model configuration across arms.

Local fixture tests should verify that information intended for one arm does not
leak into another.

## Branch 5: evaluation and reporting

Complete the research pipeline without requiring live inference during
development.

### Frozen held-out evaluation

Evaluate final/frozen candidates on the held-out pool only after the repair
process is finished.

The held-out results must not feed back into candidate selection or repair.

### Metrics

At minimum report:

- baseline development accuracy,
- per-iteration development accuracy,
- final held-out accuracy,
- absolute and relative repair improvement,
- pass-to-fail regressions,
- fail-to-pass repairs,
- comparison-status counts,
- number of repair iterations,
- number of LLM calls.

### Inference usage

Extend the LLM boundary/logging to retain available response metadata such as:

- actual returned model identifier,
- prompt tokens,
- completion tokens,
- total tokens,
- latency.

Do not assume a dollar cost for local PARAM Shakti inference. Token counts,
latency, call counts, and GPU/runtime metadata are the portable measurements.

### Reports

Produce stable machine-readable outputs (JSON and/or CSV) plus a concise
human-readable summary suitable for thesis analysis.

Aggregate across tasks, strategies, seeds, and models without deleting the
underlying per-run artifacts.

## What remains intentionally deferred

The following are not required before the five-branch roadmap is implemented:

- real GPU/model validation,
- choosing the final open-weight model,
- tuning vLLM for the actual GPU,
- running the 10-target pilot,
- deleting 100%-baseline pilot targets,
- generating the final large testcase pools,
- collecting final experimental numbers,
- trace-based feedback,
- advanced/adversarial/coverage-guided testcase generation,
- non-stdin/stdout targets.

## Later GPU validation order

When the GPU environment is ready, validate branches in order:

1. `experiments/real-software-v1` — baseline inference and pilot sanity.
2. `experiments/raw-feedback` — one failing target through raw repair.
3. `experiments/comparison-foundation` — pool generation/resume and fair baseline/raw comparison.
4. `experiments/abstract-feedback` — full three-arm comparison.
5. `experiments/evaluation-reporting` — end-to-end experiment and report generation.

This preserves a clear failure boundary: if a later branch fails under the real
model, the preceding branch remains an independently testable checkpoint.
