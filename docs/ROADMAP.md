# Roadmap: baseline, raw, abstract, path/trace and comparison

Updated: 2026-10-22.

Completing this roadmap remains the highest implementation priority. Work is
reviewed one phase at a time; raw readiness and abstract feedback are approved.
Path/trace and comparison still require review before implementation. Source
availability does not establish empirical validation.

## Five branches in order

| Order | Branch | Scope and current status |
| --- | --- | --- |
| 1 | `experiments/no-feedback` | One generated candidate, local inference, one evaluation; shared runtime prerequisite implemented separately; user validation pending |
| 2 | `experiments/raw-feedback` | Independent snapshot at `fc95a26`: raw repair, schema-2 resume and artifacts implemented; user validation pending |
| 3 | `experiments/abstract-feedback` | Current phase: behavioural abstraction, classes-only direct repair and separate resumable artifacts implemented for user validation |
| 4 | `experiments/path-feedback` | Planned: Python/C++ candidate-only trace feedback in direct repair |
| 5 | `experiments/comparison` | Planned: four-arm integration, shared pools, metrics and reproducible reporting |

Use five phase branches total, six including `main`. Create future branches
only when reviewed work starts. Stack continuations from the preceding completed
source checkpoint, deliberately carrying shared fixes forward. Do not merge,
push or create later branches automatically. Historical commits/tags remain
unchanged; record exact revisions actually validated by the user.

## Preserved raw readiness delivery

- The no-feedback local-only runtime prerequisite was committed on its own
  branch (`052630f`, hardened in `00db654`), with shared source selectively
  carried into raw. Keep the baseline branch free of raw repair orchestration.
- Both workflows require a local directory/already cached `BTP_MODEL`, use
  direct structured vLLM inference, set offline flags before imports and never
  download missing weights. One lazy model is reused per invocation.
- Raw requires an explicit replacement budget, includes every eligible failure
  in input order and reuses one deduplicated stdin set. It repairs the current
  candidate in the same language, without rollback, best-candidate selection,
  compiler feedback, silent truncation or implicit retries.
- Stdout remains lossless through exact comparison and JSON persistence. Any
  reference failure invalidates the task with null accuracy.
- Schema-2 checkpoints commit requests/responses before stage changes, hash
  artifacts, reject corruption/older checkpoints and reuse persisted inference.
  Attempted and last-evaluated rounds remain distinct on failed replacements.
- Active comparison/pool modules, HTTP client, unused shell attributes and
  obsolete configuration/guidance are removed. WIP comparison/pool code remains
  available in history, including `595c1e0`; it is not approved active work.
- README supplies user start/resume commands, exact formats, defaults,
  artifacts, stopping reasons, exit codes, troubleshooting and later scenarios.

Raw implementation and source-only inspection establish **ready for your testing**.
Model/runtime compatibility and behavioural outcomes remain empirically pending
until the user runs their own tasks. Validation discoveries must be carried
deliberately into the active continuation branch and, where shared, baseline.

## Current abstract-feedback delivery

- Branch from exact raw revision `fc95a260ddfb2096e561dd9cb99c660b1597e5a7`,
  preserving the raw branch and historical commits. Raw validation is not a gate
  for this approved continuation; raw empirical validation remains pending.
- Abstraction sees specification, input format and all current indexed raw
  failures. It sees no candidate source, passing cases, diagnostics or history.
  Repair sees specification, input format, current candidate and classes only,
  with no attached raw examples or case-ID resolution.
- Classes contain a label, observed and expected behaviour, and evidence IDs.
  Require complete coverage; allow overlap and singleton classes without a cap.
  Validate structure and IDs mechanically; semantic support remains user-reviewed.
  Do not introduce causal hypotheses, repair advice or a second judge call.
- Extend schema-2 state with abstraction request/response stages and freeze
  `feedback_mode: abstract`. Preserve source-round-indexed evidence, inference
  requests/responses and validated classes. Resume cached successful inference;
  keep abstraction tokens and latency separate. Use shared model/sampling options.
- Abstraction does not advance attempted replacement rounds. Invalid summaries
  terminate only that task, with null final accuracy and retained prior score.
  Runtime errors remain pending for explicit resume; overflow is terminal.
  No raw fallback, retries, chunking, rollback or change to scoring/stopping rules.
- `pipeline.offline_batch` runs abstract repair on this branch. README supplies
  commands, response/artifact formats, failure handling and user-run scenarios.

Abstract implementation and source/diff inspection prepare this branch for user
testing. No pipeline, model, candidate or reference has been executed by the agent;
behavioural outcomes and runtime compatibility remain empirically pending.

## Later phase contracts

All four arms must share a frozen initial candidate per task/seed, development
and held-out pools and relevant model configuration. Repair arms share maximum
round budgets and stopping rules; record abstraction/tracing overhead separately.
Held-out outcomes must never influence filtering, feedback or repair. Shared
comparison/pool implementation belongs to the later reviewed scope.

Path feedback adds compact normalized traces of the current candidate, with
Python/C++ collectors, separate trace artifacts, collection errors and truncation
records. Never inspect
or instrument the reference. Score only uninstrumented candidate executions.
Choose tracing mechanisms during path-feedback review.

Do not restore rule generation, triage, specification rewriting or indirect
regeneration. Reference tracing, new languages/interfaces, advanced test
generation, serving/deployment scaffolding and full OS isolation are outside the
current phase. Preserve sanitized candidate environments and private config.

## User-owned validation

Agents must not run the pipeline, compile/run target programs, load models or
download weights. Do not recreate automated harness suites or bundled benchmarks.
Agents inspect source and diffs. The user runs the root README commands and
records source/model/runtime identity with results. Never infer empirical
success from implementation, saved source or historical checkpoints.
