# AGENTS.md

## Purpose and phase

This research prototype replicates deterministic command-line behaviour from a
specification, valid stdin description and hidden reference executable. Source
recovery and algorithm reconstruction are not goals.

The active branch is `experiments/path-feedback`, created from exact abstract
checkpoint `672b0999ee8792f54e0c03c5a87b6deee913cdb5` after phase review. The approved
phase is raw failures plus candidate source-line traces in direct repair, with
resumable trace artifacts and documentation. Preserve `experiments/no-feedback`,
`experiments/raw-feedback` and `experiments/abstract-feedback` as independent
snapshots. Raw and abstract empirical validation remain pending. Comparison/pools
require later review under `docs/ROADMAP.md`; their old source remains in history.

## Research contract

- Candidates are Python or C++20, selected by initial generation. A case is one
  complete UTF-8 stdin string. Compare successful stdout by exact bytes,
  preserving line endings and invalid UTF-8 through JSON. Stderr is diagnostic.
- Launch failure, timeout or nonzero exit is unsuccessful. Any reference failure
  invalidates the task (`invalid_reference`, `accuracy: null`) and prevents tracing
  and repair. Never inspect, instrument or trace the reference.
- Only specification and input format are model-visible task fields. Output
  behaviour belongs in the specification. Never expose private reference commands
  or task names in prompts.
- Generate/deduplicate stdin once and reuse it every round. Include every eligible
  current failure in original order, with zero-based IDs from the full fixed set.
- Repair sees specification, input format, latest candidate, all raw failures and
  their candidate traces. Raw fields are case ID, input, status, reference stdout
  and ordinary candidate stdout. Exclude passing cases, diagnostics and history.
  No behavioural abstraction, causal summaries, advice generation or judge calls.
- Trace every eligible output mismatch, candidate error and candidate timeout
  only when another replacement is allowed. Score only ordinary uninstrumented
  executions. Keep identical trace source copies and debug binaries separate.
- Trace ordered one-based source lines, including repetitions; no explicit
  function/branch events, values or library locations. Python uses sys.settrace;
  C++ uses a separate GNU g++ debug build and Python-enabled GDB on GNU/Linux.
  Normalized format does not imply identical event granularity across languages.
- Preserve the Python interpreter invocation path, including virtual-environment
  symlinks, and compile without inheriting wrapper future flags. Retain numeric
  signal identities even when Python has no named signal enum member.
- Support one process/thread. Detect standard Python thread/process APIs and GDB
  thread/fork/exec events; detected unsupported execution stops that task. Native
  code detection is limited; this is not full OS isolation.
- Configurable defaults: 256 retained events/case, 10 seconds/case including
  startup, 30 seconds/C++ trace build, debugger `gdb`. A further observed event
  proves event-limit truncation. Nonempty valid prefixes at limits/timeouts may
  enter repair, explicitly labelled. Empty/malformed traces or collector failures
  stop only that task, with null final accuracy and retained prior evaluation.
  No raw fallback, silent omissions, automatic retries or prompt-driven trimming.
- Require an explicit nonnegative replacement budget. Zero evaluates round zero
  only. Preserve language. Stop on success, exhausted budget, malformed or
  wrong-language replacement, build failure, invalid reference, unusable tracing
  or complete-request context overflow. Tracing consumes no replacement round.
- No rollback, best-candidate selection, compiler-diagnostic feedback, rewritten
  specifications, rule generation or triage. Keep attempted and last-evaluated
  rounds distinct; failed attempts never inherit an earlier final score.

## Runtime and persistence

Use direct in-process vLLM LLM, SamplingParams and StructuredOutputsParams, one
lazy model per invocation, no HTTP. Require only BTP_MODEL: local directory or
already cached identifier, no fallback. Set offline flags before library imports;
resolve with local_files_only=True. Missing weights fail without downloads;
remote custom code is disabled.

Shared defaults: seed 42, generation/repair temperature 0.2, stdin temperature
0.6, output limit 4096, context limit 8192, dtype auto, tensor parallelism 1.
No default repair budget. README documents every CLI option.

Checkpoint schema remains 2. Freeze feedback_mode: path, source/prompts, trace
protocol/settings/tool identities, runtime/model and tasks in identity. Reject
raw/abstract/older/changed checkpoints without overwriting them. Publish requests
before inference/collection, successful responses before advancing state, and
atomic checksummed trace envelopes before per-case checkpoint commits. Hash
source, trace builds, case results, diagnostics, feedback and errors. Reuse
completed trace artifacts, evaluations and inference on resume; adopt matching
completed envelopes after publication/state crashes. Incomplete uncommitted work
may repeat on explicit resume. Tracing stages do not advance attempted_iteration.
Record trace-build/collection overhead separately from repair tokens/latency.
Resume successful inference before loading the model; batch only compatible
schemas and sampling. Record prompts, schemas, identities, settings, versions,
timing, errors and available token counts. Output defaults to ignored runs/.
Exit codes: 0 normal completion including exhausted budget, 2 setup/task failure,
130 interruption. Preserve ordinary runs, inspection artifacts, caches, private
configuration and history; never remove runs as cleanup.

## Development rules

Complete the agreed roadmap one approved phase at a time. Ask about material
research choices or Markdown conflicts; do not re-ask the decisions above.

**The user performs validation.** Agents must not execute the pipeline, load
models, download weights, compile/run candidates, execute references or run the
collectors. Do not add/recreate automated harness checks, test directories or
bundled benchmarks. Source/diff inspection is permitted. Root README owns exact
user-run commands, dependencies, artifacts, failure handling and later validation
scenarios. Separate implementation readiness from empirical validation; never
fabricate results.

Prefer standard library, small modules, dataclasses and explicit JSON. Remove
orphan imports/comments when deleting code. Do not restore deployment/scheduler
infrastructure. Comparison/pool integration is outside this phase. Later four-arm
comparison must freeze the initial candidate per task/seed and model settings,
share development/held-out pools and repair budgets/stopping rules, record trace
and abstraction overhead separately, and keep held-out outcomes out of repair.

Generated code is untrusted. Never expose parent secrets; use sanitized candidate
and collector environments, isolated trace channels and process cleanup. Full OS
isolation remains future work. Never read/copy/print private .env; preserve its
KEY=VALUE format and shell precedence. Edit only .env.example and documentation
for configuration. Do not commit .env, secrets, weights, ordinary runs, bytecode
or temporary builds. Keep commits focused. Do not merge or push automatically;
never push to main without an explicit request.

On GNU/Linux, ordinary executions use separate sessions and clean up their process
groups on completion or timeout. Terminal interruption stops batch evaluation at
case boundaries without converting it into a reference/candidate failure; an
unfinished evaluation suite remains uncommitted and may repeat on explicit resume.
Collector workspace/setup failures are persisted per task; checkpoint validation
and artifact-publication failures remain distinct. Detached process sessions are
outside the cleanup guarantee and require later OS isolation.
