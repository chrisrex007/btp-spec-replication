# Roadmap for baseline, raw, abstract, and path/trace comparison

Recorded: 2026-10-21.

The final experiment compares **no-feedback baseline vs raw feedback vs abstract
feedback vs candidate path/trace feedback**. Candidate tracing is core scope;
the reference remains a black box. The existing checkpoint already contains
raw repair and must not be described as a baseline-only implementation.

GPU experiments are on hold. Development can continue with local unit tests,
fake inference runtimes, and saved fixtures. Each substantial branch gets a
source checkpoint and a pending GPU acceptance checklist. Implementation
completion and empirical validation must always be reported separately.

## Branch budget and order

Use **five work branches total, six including `main`**: one preserved checkpoint
and four substantial continuation branches. Tags do not add branches. Create future
branches only when their work starts; do not create one branch per module or fix.

| Order | Branch | Scope | GPU stop |
| --- | --- | --- | --- |
| 1 | `experiments/real-software-v1` | Existing baseline, ten-target pilot, offline raw repair, Slurm setup and resume | `test-stop/raw-feedback-v1` / GPU-01: deferred |
| 2 | `experiments/raw-feedback` | Reusable repair orchestration, raw-feedback strategy, offline/resume hardening, configuration validation and Slurm safeguards | Proposed `test-stop/raw-feedback-v2` / GPU-02 |
| 3 | `experiments/comparison-foundation` | Reusable testcase pools, development/held-out separation, shared initial candidates and experiment provenance | Proposed `test-stop/comparison-foundation-v1` / GPU-03 |
| 4 | `experiments/feedback-variants` | Abstract feedback, Python/C++ candidate tracing and complete four-arm integration | Proposed `test-stop/feedback-variants-v1` / GPU-04 |
| 5 | `experiments/evaluation-reporting` | Held-out execution, metrics, regressions, token/runtime accounting and reproducible reports | Proposed `test-stop/evaluation-reporting-v1` / GPU-05 |

The existing checkpoint is preserved at `40d1871`. The planning-only
`experiments/comparison-foundation` branch was renamed to
`experiments/raw-feedback`; both it and the historical branch pointed to the
same commit before the rename. Recreate `comparison-foundation` when that phase
begins. No branch deletion or historical rewrite is required. The old proposed
`experiments/abstract-feedback` branch is replaced by `experiments/feedback-variants`.

The roadmap and branch organization are approved. Review each implementation
phase and settle its material research choices before coding it; the roadmap
does not imply that all of the capabilities below are already implemented.

Stack each continuation branch from the preceding completed source checkpoint.
This carries shared infrastructure forward and permits testing each historical
snapshot independently. Do not merge into `main`, push, or create later branches
automatically. Fixes discovered by later GPU testing must also be carried into
the active continuation branch deliberately; keep historical checkpoint tags
unchanged and record the revision actually retested.

## Shared architecture and comparison constraints

For each task/seed, preserve one frozen initial candidate C0. The baseline keeps
C0 without repair. Raw, abstract, and path/trace arms each start from that exact
source and repair their own current candidate through the same orchestration:

```text
development failures -> feedback strategy -> direct candidate repair
    -> build -> uninstrumented differential evaluation -> persist -> next round
```

All arms use the same development pool, held-out pool, and relevant model
configuration. Repair arms share the same maximum repair-iteration budget and
stopping rules. Equal rounds do not imply equal compute: record abstraction
inference and trace collection overhead separately. Final held-out evaluation
uses frozen candidates and never feeds back into filtering or repair.

Raw feedback contains failing stdin, reference stdout, candidate stdout, and
execution status where relevant. Abstract feedback groups those observed
failures into supported behavioral classes. Path/trace feedback adds a compact
trace of the current candidate to raw failures. Specification and input format
remain available to direct repair; reference command lines remain private.

## 1. Raw-feedback foundation

Keep existing task, build, execution, and differential modules. Preserve the
one-task no-feedback baseline and one in-process offline vLLM instance per job.

Deliverables:

- Extract a shared repair loop for feedback preparation, repair requests,
  build/evaluation, bounded iteration, stopping and persistence. Add a raw
  feedback strategy that later variants can use as the interface example.
- Preserve the current offline batching and checkpoint behavior while making
  strategy-specific feedback preparation separate from orchestration.
- Validate configuration and prompt/output context budgets, strengthen resume
  provenance for code/prompts/configuration, and preserve parse/build/runtime
  failures as experiment data.
- Keep reference execution failures distinguishable from candidate failures;
  they must not silently become evidence of incorrect candidate behavior.
- Harden scratch submission safeguards and document signal handling and
  unfinished inference calls. All cluster execution stays user-mediated.

Local acceptance: baseline regressions, raw feedback privacy, direct repair,
failure persistence, configuration rejection, bounded rounds, interrupted/resumed
fake-runtime execution, and completed resume without model initialization.

GPU-02: validate the shared raw loop with actual inference, context limits,
Slurm interruption/resume, and complete artifacts. GPU-01 remains independently
pending until its historical source snapshot has actually been tested.

## 2. Comparison foundation

Deliverables:

- Explicit experiment configuration for arms, seeds, test-pool references,
  repair limits, feedback limits, and artifact versions.
- Basic LLM testcase generation in bounded batches with exact deduplication,
  persisted content hashes, and reusable pools. No adversarial or failure-guided
  generation. Handle duplicate/short batches and persist the actual case count.
- Separate development/feedback and held-out pool interfaces, with no shared
  cases; filtering and repair must never read held-out outcomes. Freeze target
  selection using pilot/development results before final evaluation.
- Persist one initial candidate per task/seed and fork that exact source into
  baseline and raw-feedback arms, with the same mechanism available to the
  later abstract and path/trace arms. Preserve iteration zero as the baseline;
  budgeted repairs modify each arm's current candidate directly.
- Extend checkpoints/fingerprints with pool identity and arm/seed identity.
  Preserve all intermediate candidates and call records.

Local acceptance: fixture-based pool persistence/reload, no split overlap or
held-out leakage, identical initial source across arms, correct iteration-zero
baseline, isolated per-arm state, configuration mismatch rejection, reference
error handling, and interrupted/resumed fake-runtime execution. Run the existing
unit suite; retain the cheap `double` smoke test.

GPU-03: generate/reload actual development pools, run paired baseline/raw arms
on a small pilot, inspect lineage and prompt provenance, and exercise resume.
GPU-01 remains pending independently until it is actually tested.

## 3. Feedback variants: abstract and path/trace

Deliverables:

- A small abstraction module, structured response schema, and prompt that group
  observed development failures into behavioral classes supported by evidence.
- Persist the abstraction call, source failure identities, output, configuration,
  latency, and parsing errors. Do not silently fall back to raw feedback.
- Pass the specification, current candidate, and abstract feedback directly to
  repair. Do not generate rules, rewrite the specification, or regenerate through
  a rewritten specification.
- Add abstract and path/trace feedback strategies to the shared repair loop.
  Batch abstraction and repair through the same offline model instance.
- Provide a common trace collector interface with Python and C++ implementations
  and a shared normalized trace representation. Choose the collection mechanisms
  during this phase's design review, based on feasibility in the target environment.
- Trace only the current candidate on selected failing development inputs.
  Collect compact ordered source-location/path events; do not substitute
  aggregate coverage for an execution path or invent unavailable branch events.
- Persist traces separately from stdout, tied to candidate and input identities,
  with explicit collection errors, resource bounds and truncation. Never inspect
  or instrument the reference, and never silently substitute raw feedback when
  tracing fails.
- Always score the normal, uninstrumented candidate. Trace collection is a
  separate feedback operation with separately recorded runtime and status.
- Integrate all four arms with shared initial sources and frozen pools, isolated
  checkpoints, common repair limits and stopping rules, and bounded rounds.
- Preserve build/parse failures and stopping reasons as experiment data.

Local acceptance: fixture abstractions, malformed responses and unsupported
summaries, provenance, private reference-command exclusion, held-out isolation,
arm independence, all four arms' histories, and resume across feedback stages.
Use local deterministic Python/C++ programs to check trace event order,
normalization, truncation, collection failures, and independent uninstrumented
scoring. No GPU is needed for collector tests.

GPU-04: exercise real abstraction and trace-assisted repair inference, inspect
summary evidence and trace/source correspondence, and verify complete four-arm
artifacts and overhead accounting. Do not assume either variant improves results.

## 4. Evaluation and reporting

Deliverables:

- A separate evaluation path for frozen final candidates and held-out pools,
  with no feedback into candidate generation, filtering, or repair. Final
  candidate selection must be fixed before held-out outcomes are visible.
- Read-only aggregation of baseline/raw/abstract/path-trace results by task,
  seed, arm, and repair iteration. Report improvements and regressions; distinguish
  development agreement from held-out agreement.
- Report denominators, observed scores and deltas, build/runtime/reference
  failures, incomplete runs, stopping reasons, and recorded inference tokens,
  costs and latency. Account for abstraction inference and trace runtime
  separately. Do not drop failed runs or invent unavailable measurements.
- Validate comparable configurations, shared initial candidates, pool identities,
  selected-target manifests, and provenance before comparing results.
- Export concise machine-readable and human-readable reports. Keep ordinary
  runs ignored; introduce curated versioned results only deliberately.
- Document the final Slurm run/resume workflow, backups, known limitations,
  and the required PARAM Shakti/NSM acknowledgement in research outputs.

Local acceptance: aggregate saved synthetic fixtures with known counts, including
failed/missing runs; reject mixed pools/configurations and verify evaluation
cannot modify candidates or feed held-out data into repairs.

GPU-05: after the protocol and pilot target set are frozen, run the final
approved experiment, archive persistent artifacts, and produce reports from
actual results. Passing local tests alone cannot close this checkpoint.

## Research choices still requiring agreement

Decide these before implementing their dependent behavior; do not choose them
from final held-out outcomes:

- Development/held-out pool sizes, generation and split procedure, validity
  checking, and exact pilot target-filtering rule across repeated seeds.
- Seed/repetition count and the numerical repair/stopping limits. Matching
  maximum repair rounds and stopping rules across repair arms is already settled;
  extra abstraction and tracing overhead must remain visible in reports.
- Failure selection/order/truncation and treatment of candidate build/runtime
  failures and reference failures.
- Information visible to the abstraction LLM, abstraction output limits, and
  how unsupported summaries or parsing failures affect the experiment.
- Python/C++ tracing mechanisms, normalized event semantics, trace limits,
  selection/truncation, instrumentation divergence, and collection-failure policy.
- Final-candidate selection, primary metrics, failure denominators, and any
  statistical summaries across tasks/seeds.

## What remains outside this plan

Reference tracing, specification rewriting, advanced testcase generation, new
languages/interfaces, distributed serving, and HTTP model hosting are outside
the current experiment. Stronger OS sandboxing remains separate future work;
continue to sanitize generated candidate environments in every arm.

## When GPU access returns

Use checkpoint tags to reproduce source snapshots, not moving branch tips.
For each checklist, record tested revision, model revision, environment,
configuration, run ID, persistent artifact location, and observed result.
Use new run IDs for different snapshots/configurations; resume only a compatible
unfinished run. Shared frozen pools may be reused by later arms, but checkpoint
scores are development evidence until the final held-out protocol is run.

Testing can begin with GPU-01 while later development continues. The five GPU
checklists are integration milestones; the research comparison is the four
experimental arms at the final approved revision, not a comparison of branch
scores.
