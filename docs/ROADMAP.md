# Roadmap for baseline, raw, abstract, and path/trace comparison

Updated: 2026-10-22.

The final experiment compares **no-feedback baseline vs raw feedback vs abstract
feedback vs candidate path/trace feedback**. Candidate tracing is core scope;
the reference remains a black box.

Completing this roadmap is the highest-priority implementation goal. The user
has approved the five-phase branch organization and asked to wait for phase
review before further implementation. This does not authorize implementing all
phases now. Existing code is not evidence of completed phase review or empirical
validation.

Validation is user-managed. Agents must not execute the pipeline or its target
programs. Keep user-run pipeline commands in repository-root `README.md`.
Do not add automated harness checks unless the user explicitly asks. Deployment
details are deferred. Report implementation completion and empirical validation
separately; unexecuted checks remain pending.

## Branch budget and order

Use **five phase branches total, six including `main`**. Tags do not add branches.
Create future branches only when their work starts; do not create one branch per
module or fix.

| Order | Branch | Scope |
| --- | --- | --- |
| 1 | `experiments/no-feedback` | Spec-only baseline without a feedback or repair loop |
| 2 | `experiments/raw-feedback` | Raw failure feedback and direct repair of the current candidate |
| 3 | `experiments/abstract-feedback` | LLM abstraction of failure patterns within the shared repair loop |
| 4 | `experiments/path-feedback` | Python/C++ candidate tracing for failing inputs within the shared repair loop |
| 5 | `experiments/comparison` | Four-arm comparison, metrics, regressions, token/runtime accounting, and reproducible reports |

Review each implementation phase and settle its material research choices before
coding it. All arms must share frozen initial candidates, development/held-out
pools, and relevant model configuration, as required by `AGENTS.md`. Decide the
placement of unfinished shared infrastructure during phase review.

The baseline-only branch starts from the existing `main` source checkpoint
`3fd3ca7`. Raw-feedback source was checkpointed at `1436319`. Obsolete local
branch names have been removed; historical commits and checkpoint tags remain.
Unfinished comparison/pool work is preserved as a WIP checkpoint without treating it as approved
implementation. The abstract, path, and comparison branches will be created when
their reviewed work starts.

Stack each continuation branch from the preceding completed source checkpoint.
This carries shared infrastructure forward and permits testing each historical
snapshot independently. Do not merge into `main`, push, or create later branches
automatically. Fixes discovered by later user testing must also be carried into
the active continuation branch deliberately; keep historical checkpoint tags
unchanged and record the revision actually retested.

## What remains outside this plan

Reference tracing, specification rewriting, advanced testcase generation, new
languages/interfaces, distributed serving, and HTTP model hosting are outside
the current experiment. Stronger OS sandboxing remains separate future work;
continue to sanitize generated candidate environments in every arm.

## User-owned validation

The user will test each phase's source checkpoint using the commands in
`README.md`. Agents must not execute those commands. Separate checkpoints make
historical implementations independently testable; stacked branches can still
inherit earlier defects. Record the exact revision tested and carry fixes into
later phases deliberately.
