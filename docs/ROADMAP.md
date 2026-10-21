# Remaining implementation and deferred GPU validation

Recorded: 2026-10-21.

GPU experiments are on hold. Development can continue with local unit tests,
fake inference runtimes, and saved fixtures. Each substantial branch gets a
source checkpoint and a pending GPU acceptance checklist. Implementation
completion and empirical validation must always be reported separately.

## Branch budget and order

Use **four work branches total**, including the existing branch: one frozen
checkpoint and three substantial continuation branches. `main` is unchanged
and is not an experimental work branch. Tags do not add branches. Create future
branches only when their work starts; do not create one branch per module or fix.

| Order | Branch | Scope | GPU stop |
| --- | --- | --- | --- |
| 0 | `experiments/real-software-v1` | Existing baseline, ten-target pilot, offline raw repair, Slurm setup and resume | `test-stop/raw-feedback-v1` / GPU-01: deferred |
| 1 | `experiments/comparison-foundation` | Reusable testcase pools, experiment protocol/configuration, paired baseline/raw orchestration, provenance and runner hardening | Proposed `test-stop/comparison-foundation-v1` / GPU-02 |
| 2 | `experiments/abstract-feedback` | Failure abstraction, direct repair with abstract feedback, complete three-arm integration | Proposed `test-stop/abstract-feedback-v1` / GPU-03 |
| 3 | `experiments/evaluation-reporting` | Held-out execution, aggregation, reproducibility checks, final run instructions and reporting | Proposed `test-stop/evaluation-reporting-v1` / GPU-04 |

The first checkpoint is created now, then branch 1 starts with this plan. The
three implementation scopes below are **proposed for phase review**, not an
instruction to implement every phase automatically. Follow the user's current
instruction and obtain agreement on material research choices before coding
them. Creating the continuation branch does not settle those choices.

Stack each continuation branch from the preceding completed source checkpoint.
This carries shared infrastructure forward and permits testing each historical
snapshot independently. Do not merge into `main`, push, or create later branches
automatically. Fixes discovered by later GPU testing must also be carried into
the active continuation branch deliberately; keep historical checkpoint tags
unchanged and record the revision actually retested.

## 1. Comparison foundation

Keep existing task, build, execution, and differential modules. Preserve the
one-task no-feedback baseline and one in-process offline vLLM instance per job.

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
  baseline and raw-feedback arms. Preserve iteration zero as the baseline;
  budgeted repairs modify each arm's current candidate directly.
- Ensure reference execution failures are distinguishable from candidate
  failures and cannot silently become evidence of incorrect candidate behavior.
- Extend checkpoints/fingerprints for code, prompts, configuration, pool identity,
  and arm/seed identity. Preserve all intermediate candidates and call records.
- Validate context budgets and configuration, harden scratch submission checks,
  and document recoverable stages and unfinished inference calls.

Local acceptance: fixture-based pool persistence/reload, no split overlap or
held-out leakage, identical initial source across arms, correct iteration-zero
baseline, isolated per-arm state, configuration mismatch rejection, reference
error handling, and interrupted/resumed fake-runtime execution. Run the existing
unit suite; retain the cheap `double` smoke test.

GPU-02: generate/reload actual development pools, run paired baseline/raw arms
on a small pilot, inspect lineage and prompt provenance, and exercise resume.
GPU-01 remains pending independently until it is actually tested.

## 2. Abstract feedback

Deliverables:

- A small abstraction module, structured response schema, and prompt that group
  observed development failures into behavioral classes supported by evidence.
- Persist the abstraction call, source failure identities, output, configuration,
  latency, and parsing errors. Do not silently fall back to raw feedback.
- Pass the specification, current candidate, and abstract feedback directly to
  repair. Do not generate rules, rewrite the specification, or regenerate through
  a rewritten specification.
- Batch abstraction and repair through the same offline model instance. Add
  the abstract arm alongside the existing paired baseline/raw arms, with shared
  initial sources and frozen pools, isolated checkpoints, and bounded rounds.
- Preserve build/parse failures and stopping reasons as experiment data.

Local acceptance: fixture abstractions, schema errors, provenance, private
reference-command exclusion, held-out isolation, arm independence, all three
arms' iteration histories, and resume across abstraction/repair stages.

GPU-03: exercise real abstraction and repair inference and inspect whether the
summaries are supported by the supplied failures. Verify complete three-arm
artifacts; measure outcomes without assuming abstract feedback improves them.

## 3. Evaluation and reporting

Deliverables:

- A separate evaluation path for frozen final candidates and held-out pools,
  with no feedback into candidate generation, filtering, or repair. Final
  candidate selection must be fixed before held-out outcomes are visible.
- Read-only aggregation of baseline/raw/abstract results by task, seed, arm,
  and repair iteration. Distinguish development agreement from held-out agreement.
- Report denominators, observed scores and deltas, build/runtime/reference
  failures, incomplete runs, stopping reasons, and inference cost/latency where
  recorded. Do not drop failed runs or invent token/cost measurements.
- Validate comparable configurations, shared initial candidates, pool identities,
  selected-target manifests, and provenance before comparing results.
- Export concise machine-readable and human-readable reports. Keep ordinary
  runs ignored; introduce curated versioned results only deliberately.
- Document the final Slurm run/resume workflow, backups, known limitations,
  and the required PARAM Shakti/NSM acknowledgement in research outputs.

Local acceptance: aggregate saved synthetic fixtures with known counts, including
failed/missing runs; reject mixed pools/configurations and verify evaluation
cannot modify candidates or feed held-out data into repairs.

GPU-04: after the protocol and pilot target set are frozen, run the final
approved experiment, archive persistent artifacts, and produce reports from
actual results. Passing local tests alone cannot close this checkpoint.

## Research choices still requiring agreement

Decide these before implementing their dependent behavior; do not choose them
from final held-out outcomes:

- Development/held-out pool sizes, generation and split procedure, validity
  checking, and exact pilot target-filtering rule across repeated seeds.
- Seed/repetition count, repair/stopping limits, and whether repair counts or
  inference/token budgets are matched across raw and abstract feedback. Extra
  abstraction calls must remain visible whichever comparison is chosen.
- Failure selection/order/truncation and treatment of candidate build/runtime
  failures and reference failures.
- Information visible to the abstraction LLM, abstraction output limits, and
  how unsupported summaries or parsing failures affect the experiment.
- Final-candidate selection, primary metrics, failure denominators, and any
  statistical summaries across tasks/seeds.

## What remains outside this plan

Execution traces, specification rewriting, advanced testcase generation, new
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

Testing can begin with GPU-01 while later development continues. The four GPU
checklists are integration milestones; the research comparison is the three
experimental arms at the final approved revision, not a comparison of branch
scores.
