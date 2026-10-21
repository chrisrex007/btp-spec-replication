# Deferred-GPU Development Roadmap

## Final research destination

The project compares **three feedback approaches** against a no-feedback
baseline:

1. **Raw feedback** — failing stdin + reference stdout + candidate stdout.
2. **Abstract feedback** — behavioural failure classes summarized from observed
   failures; the repair model does not receive the individual raw examples.
3. **Path/trace feedback** — raw failure I/O plus the **candidate program's**
   execution path/trace for the failing input.

The final comparison is therefore:

```text
same frozen initial candidate
          |
          +---- baseline: no repair
          |
          +---- raw: raw failures -> repair
          |
          +---- abstract: failures -> abstraction -> repair
          |
          +---- path/trace: failures + candidate trace -> repair
```

The black-box/reference implementation remains opaque in every arm. Path/trace
feedback refers only to the generated candidate's execution, never to the
reference program's internal path.

## Why development continues without GPU testing

Real-model inference and PARAM Shakti experiments are intentionally paused.

Development continues using:

- unit tests,
- fixture-based tests,
- mocked/offline LLM responses,
- deterministic local black-box/reference execution,
- trace-collector unit tests,
- schema/persistence/resume tests.

Do **not** consume GPU time or hosted-LLM quota merely to validate architecture
while this roadmap is being implemented.

The head of `experiments/real-software-v1` is the **baseline testing stop
point**. Preserve it as a reproducible checkpoint. It contains the Phase 0-5
baseline, hidden-oracle real-software task definitions, and the current
OpenAI-compatible LLM boundary. The real-software pilot has not yet been run on
PARAM Shakti.

When GPU testing resumes, each later branch is another independently testable
architectural checkpoint.

## Branch budget

Use **five work branches total, including the frozen baseline checkpoint**.
Together with `main`, the repository stays at **six branches total**, below the
requested limit of seven.

Create later branches only after the previous branch is complete.

| Branch | Scope | Deferred-GPU completion milestone |
| --- | --- | --- |
| `experiments/real-software-v1` | Existing Phase 0-5 baseline and real-software task definitions | Frozen baseline checkpoint |
| `experiments/raw-feedback` | Generic repair framework, raw feedback, offline inference boundary, checkpoint/resume, PARAM Shakti serving scaffolding | Raw repair works end-to-end with fixture LLM responses |
| `experiments/comparison-foundation` | Reusable testcase pools, batched generation, dev/held-out split, shared initial candidates, experiment configs/provenance | Baseline/raw comparison reproducible from frozen fixtures and pools |
| `experiments/feedback-variants` | Abstract feedback + candidate path/trace feedback + four-arm integration | Baseline/raw/abstract/path arms all run through the same fixture-driven runner |
| `experiments/evaluation-reporting` | Frozen held-out evaluation, metrics, regressions, inference accounting, aggregate reports | Complete experiment can be prepared and locally validated without GPU calls |

No sixth work branch should be introduced unless a genuinely separate concern
cannot fit one of these scopes.

## Architectural inference stop point

Every future LLM-dependent operation must preserve a clean boundary:

```text
prepare structured request
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

A workflow must be able to stop immediately before inference, save enough state
to resume, and later continue from a recorded response without regenerating
earlier candidates/tests or changing experimental inputs.

This applies to:

- initial candidate generation,
- testcase generation,
- raw repair,
- failure abstraction,
- abstract repair,
- path/trace repair.

## Branch 2: raw feedback

Implement the first repair treatment and the reusable repair infrastructure that
later feedback strategies plug into.

### Raw failure representation

A raw failure contains only observable information allowed by the research
design:

- stdin,
- reference stdout,
- candidate stdout,
- comparison/execution status when relevant.

Never expose the reference command, executable name, source, or internal
implementation details to any LLM.

### Repair operation

Repair the **current candidate directly**:

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

Build the replacement and evaluate it on the development inputs available to
that run.

Support a configurable maximum number of repair iterations. Persist every:

- candidate snapshot,
- feedback payload,
- LLM request/response,
- build result,
- evaluation result,
- iteration summary.

### Generic repair/feedback interface

Avoid hard-wiring raw feedback into the orchestration layer. Introduce a small
strategy boundary so later branches can provide a different feedback payload
without duplicating the repair loop.

Conceptually:

```text
failures/current candidate
          |
          v
 feedback strategy
          |
          v
 structured repair context
          |
          v
 common repair loop
```

The exact class/module names can be chosen during implementation; keep the
interface small.

### Offline/resume support

Refactor the LLM path so each request has a serializable identity and can be
satisfied by:

- live OpenAI-compatible inference,
- fixture/offline response,
- previously persisted completed response.

Persist enough iteration state that interrupted runs resume without repeating
completed calls.

### PARAM Shakti scaffolding

Add configuration/scripts/documentation needed to launch an OpenAI-compatible
vLLM server under Slurm and point the existing pipeline at it.

Do not lock:

- final model,
- GPU count,
- quantization,
- tensor parallelism,
- context length,

until the actual GPU hardware/software is inspected.

No real GPU verification is required to complete this branch.

## Branch 3: comparison foundation

Make the experiment fair, reusable, and token-efficient.

### Persistent high-volume testcase pools

Move testcase generation out of individual strategy runs.

Support:

- generation in small batches,
- configurable batch size/count,
- exact deduplication,
- persisted pool files,
- stable pool identity/hash,
- generation provenance,
- resume after partial generation,
- reuse without additional LLM calls.

When real inference becomes available, hundreds of testcases should be produced
through multiple small calls rather than one giant prompt.

### Development and held-out split

Freeze a split before any repair:

- **development pool** — may drive failure discovery, abstraction, traces, and
  repair;
- **held-out pool** — never shown to any repair/feedback operation and used only
  for final evaluation.

Persist split membership and seed.

### Shared initial candidate

For a task/model/seed, generate the initial candidate exactly once.

Every arm starts from that same frozen source:

```text
initial candidate C0
   |
   +-- baseline
   +-- raw
   +-- abstract
   +-- path/trace
```

No arm independently regenerates C0.

### Pilot filtering

Use only the pilot/development pool to decide active targets.

If a target reaches 100% baseline agreement on that pool, delete it from the
active repair benchmark set as previously decided.

Never use held-out results to decide which targets remain.

### Experiment configuration/provenance

Represent an experiment explicitly with at least:

- task ID,
- model/config,
- seed,
- prompt versions,
- testcase pool IDs,
- dev/held-out split ID,
- initial candidate ID,
- feedback strategy,
- repair iteration budget.

Reject resume/reuse attempts that mix incompatible artifacts.

## Branch 4: feedback variants

Implement the remaining two feedback treatments and integrate all four arms.

### Abstract feedback

Observed development failures are passed to an abstraction LLM, which produces
a compact structured set of behavioural failure classes/patterns.

Persist both:

- raw failures used as abstraction input,
- resulting abstraction.

The abstract repair model receives:

- specification,
- input format,
- current candidate,
- abstract behavioural feedback.

It must **not** receive the individual raw failure examples.

### Path/trace feedback

For each selected failing development input, collect the **candidate's**
execution path/trace.

The path arm receives:

- specification,
- input format,
- current candidate,
- failing stdin,
- reference stdout,
- candidate stdout,
- compact normalized candidate trace.

No internal path or trace from the black-box/reference program is available or
permitted.

### Normalized trace model

Design a language-neutral trace representation before binding to a tracing
mechanism. It should be compact enough for LLM prompts and may contain
information such as:

- source line or stable source location,
- function name,
- branch/condition event when available,
- branch outcome when available,
- ordered executed path events.

Do **not** dump unbounded instruction-level traces, library internals, or every
runtime value into prompts.

Only failing development cases need traces.

### Python/C++ trace collectors

The candidate language can be Python or C++20, so trace collection needs a
common interface with language-specific implementations.

Important invariants:

- tracing must observe the candidate, not the reference;
- scoring still uses the ordinary uninstrumented candidate;
- trace collection must not alter stdout used for correctness;
- trace artifacts are persisted separately from differential outputs.

The exact Python and C++ instrumentation mechanisms are a material design choice
to review when this branch begins; do not silently commit to one in advance.

### Four-arm integration

The common experiment runner must support:

```text
baseline
raw
abstract
path/trace
```

with:

- same frozen C0,
- same development pool,
- same held-out pool,
- same repair iteration budget,
- same relevant model configuration.

Fixture tests must verify information isolation:

- baseline gets no feedback,
- raw gets raw examples,
- abstract gets abstraction but not raw examples,
- path gets raw I/O plus candidate trace,
- no arm ever gets held-out outcomes during repair.

## Branch 5: evaluation and reporting

Complete the research pipeline.

### Frozen held-out evaluation

After an arm finishes repair, freeze its final candidate and evaluate it on the
held-out pool.

Held-out results must not feed back into:

- repair,
- abstraction,
- path selection,
- iteration stopping based on correctness,
- target filtering.

### Core metrics

At minimum report per task/arm:

- baseline development accuracy,
- per-iteration development accuracy,
- final held-out accuracy,
- absolute repair improvement,
- relative repair improvement where meaningful,
- fail-to-pass repairs,
- pass-to-fail regressions,
- comparison-status counts,
- number of repair iterations,
- number of LLM calls.

For the three feedback arms also report feedback-specific quantities where
useful, for example:

- number of raw failures included,
- number of abstract classes,
- number/length of trace events supplied.

### Inference usage

Extend LLM logging to retain available response metadata:

- actual returned model identifier,
- prompt tokens,
- completion tokens,
- total tokens,
- latency.

For PARAM Shakti, do not invent a monetary API cost. Portable measurements are:

- tokens,
- calls,
- latency,
- GPU/runtime metadata.

This is especially important for comparing whether abstract feedback reduces
prompt volume relative to raw/path feedback.

### Reports

Produce stable machine-readable output (JSON and/or CSV) plus concise
human-readable summaries suitable for thesis analysis.

Aggregate across:

- tasks,
- seeds,
- models,
- feedback arms,
- repair iterations,

without deleting underlying per-run artifacts.

## What remains intentionally deferred

These are not prerequisites for implementing the five-branch roadmap:

- real GPU/model validation,
- final model selection,
- vLLM tuning for the allocated GPU,
- running the 10-target pilot,
- deleting 100%-baseline pilot targets,
- actually generating the final large testcase pools,
- collecting final experimental numbers,
- choosing exact Python/C++ path instrumentation,
- advanced/adversarial/coverage-guided testcase generation,
- non-stdin/stdout targets.

## Later GPU validation order

When GPU testing resumes, validate checkpoints in this order:

1. `experiments/real-software-v1`
   - baseline inference,
   - real-software pilot sanity.

2. `experiments/raw-feedback`
   - one failing target,
   - one or more raw repair iterations,
   - resume after a stopped inference request.

3. `experiments/comparison-foundation`
   - batched testcase generation,
   - frozen pools/splits,
   - shared initial candidate,
   - baseline vs raw fairness.

4. `experiments/feedback-variants`
   - abstract feedback,
   - candidate path/trace collection,
   - all four arms.

5. `experiments/evaluation-reporting`
   - complete held-out evaluation,
   - aggregate reports,
   - inference/resource accounting.

This preserves a clear failure boundary: if a later checkpoint fails under the
real model, the preceding branch remains independently testable.
