# AGENTS.md

## Purpose and phase

This is a research prototype for specification-driven black-box program
replication. Given a specification, valid stdin description and hidden reference
executable, synthesize a program with equivalent observable behaviour. Recovering
source code or reconstructing algorithms is not the goal.

The active branch is `experiments/abstract-feedback`, created from raw checkpoint
`fc95a260ddfb2096e561dd9cb99c660b1597e5a7`. The approved current phase is abstract
feedback: behavioural classes between evaluation and direct repair, resumable
abstraction artifacts and documentation. `experiments/raw-feedback` remains its
independent phase snapshot; raw empirical validation is still pending.
`experiments/no-feedback` remains a separate one-shot baseline with shared runtime
fixes and no repair code. Path/trace feedback and comparison require later phase
review as recorded in `docs/ROADMAP.md`. Comparison/pool work is preserved in Git
history, not active source.

## Research contract

- Targets are deterministic command-line programs; candidates use Python or
  C++20, chosen by the initial generation model.
- A case is one complete UTF-8 stdin string. Compare successful stdout by exact
  bytes, preserving line endings and invalid UTF-8 through JSON persistence.
  Stderr is diagnostic only.
- Launch failure, timeout or nonzero exit is unsuccessful. Any reference failure
  invalidates the task (`invalid_reference`, `accuracy: null`) and prevents
  abstraction and repair.
- The only model-visible task fields are specification and input format. Output
  behaviour belongs in the specification. Never expose private reference commands
  or task names in model prompts; never inspect the reference's source.
- Generate/deduplicate stdin once and reuse it in every round. Include all
  eligible failures in original input order; no feedback-case cap.
- Abstraction receives specification + input format + all current eligible raw
  failures (case ID, input, status, reference stdout, candidate stdout), without
  candidate source, passing cases, diagnostics or history. Case IDs are zero-based
  positions in the fixed deduplicated stdin set.
- Require structured behavioural classes with label, observed/expected behaviour
  and supporting case IDs. Check structure, IDs and complete coverage; allow
  overlap and singleton classes without a class cap. Semantic support is for user
  inspection. Do not add causal hypotheses, repair advice or a second judge call.
- Repair the latest candidate directly from specification + input format + current
  candidate + validated classes only. Do not attach raw cases or resolve their
  IDs into examples. Retain the candidate's language.
- Require an explicit nonnegative repair budget. Zero evaluates only the initial
  candidate. Stop on success, exhausted budget, malformed replacement, language
  change, build failure, invalid reference, unusable abstraction or complete-request
  context overflow. Abstraction itself does not consume a replacement round.
- No rollback, best-candidate selection, compiler-diagnostic feedback, implicit
  inference retries, rewritten specifications, rule generation or triage.
- Keep attempted and last-evaluated rounds distinct. A failed replacement must
  not inherit a successful final score from an earlier candidate. Abstraction
  failures terminate that task with null final accuracy and retain the last
  evaluated score; other tasks continue. No raw fallback or chunking.

## Runtime and persistence

Use direct in-process vLLM `LLM`, `SamplingParams` and
`StructuredOutputsParams`, with one lazy model per invocation. There is no HTTP
transport. Require only `BTP_MODEL` in `.env`: a local directory or already cached
identifier, without a fallback model. Set offline flags before importing model
libraries; resolve cache entries with `local_files_only=True`. Missing weights
must fail without download; remote custom code is disabled.

Shared defaults: seed 42, generation/abstraction/repair temperature 0.2, stdin
temperature 0.6, output limit 4096, context limit 8192, dtype auto, tensor
parallelism 1.
No default repair budget. README documents every other CLI option.
Abstraction preceding repair round i uses seed S + i and the shared output limit
and model; there are no abstraction-specific runtime options.

Checkpoint schema is 2. Save requests before inference and successful responses
before advancing state; publish artifacts/state atomically. Hash checkpoint
artifacts and reject tampering or incompatible/older checkpoints without
overwriting them. Resume cached successful inference before loading the model.
Batch only requests with compatible schema and sampling settings.
Freeze `feedback_mode: abstract` in run identity; raw checkpoints cannot resume
on this branch. Persist abstraction requests/responses separately under inference
step `failure_abstraction`, indexed by their evaluated source round. Save raw
evidence and validated classes separately; abstraction stages must not advance
`attempted_iteration`. Record abstraction tokens and latency separately from repair.
Record prompts, schemas, model identity, runtime versions, sampling settings,
latency, errors and available token counts. Output defaults to ignored `runs/`.
Exit codes are 0 for normal completion including exhausted budgets, 2 for setup
or task failures, and 130 for interruption.

Preserve redundant inspection artifacts, private configuration, model caches,
existing runs and historical commits. Do not remove ordinary runs as cleanup.

## Development rules

Completing the agreed roadmap is the highest priority, one approved phase at a
time. Ask about material research choices or conflicts across Markdown files;
continue independent authorized work while awaiting clarification. Do not
re-ask decisions already settled above.

**The user performs validation.** Agents must not execute the pipeline, load
models, download weights, compile/run candidates or execute reference programs.
Do not add or recreate automated harness checks, test directories or bundled
benchmarks. Source/diff inspection is permitted. Keep exact user-run commands,
requirements, artifacts, failure handling and later validation scenarios in the
root `README.md`. Report implementation and empirical validation separately.
Never fabricate accuracy, performance or experimental results.

Prefer the standard library, small modules, dataclasses and explicit JSON.
Remove orphan imports and obsolete comments when deleting source. Do not restore
removed deployment/scheduler infrastructure. Tracing and comparison/pool
integration are outside this phase.

For later comparison, all four arms must share a frozen initial candidate per
task/seed, development and held-out pools and relevant model configuration.
Repair arms share round budgets/stopping rules; abstraction and tracing overhead
must be recorded separately. Held-out outcomes must not influence repair.
Candidate-only tracing is a planned feedback side-channel; never trace the
reference, and score the uninstrumented candidate.

Generated code is untrusted. Never expose parent secrets to its environment.
Never read/copy/print private `.env` for documentation; preserve its format of
one `KEY=VALUE` per line with comments/optional quotes and shell precedence.
Edit only `.env.example` and documentation. Do not commit `.env`, secrets,
model weights, ordinary runs, bytecode or temporary build output.

Keep commits focused. Do not merge or push automatically, and never push to
`main` without an explicit request.
