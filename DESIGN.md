# Specification-replication contract

## Task and scoring boundary

Replicate deterministic stdin/stdout behaviour from a specification and input
format. Candidates use Python or C++20; hidden reference commands are private to
the evaluator. Never inspect, instrument or trace the reference.

Each case is a complete UTF-8 stdin string. Capture ordinary stdout/stderr as
bytes and decode with UTF-8 surrogateescape without newline translation.
Successful stdout equality is byte-exact. ASCII-escaped JSON preserves invalid
UTF-8; stderr is diagnostic only. Launch failures, timeouts and nonzero exits
are unsuccessful. Any reference failure invalidates the whole task, producing
invalid_reference and null accuracy, without tracing or repair.

Generated programs and collectors receive sanitized environments. This provides
process execution and cleanup, not full security or filesystem isolation.

Ordinary GNU/Linux executions start in separate sessions, isolating references
and candidates from the runner's terminal interrupts. Their process groups are
terminated after completion or timeout, including surviving ordinary descendants.
Deliberately detached sessions require future OS isolation. Batch evaluation
observes cooperative stop requests between cases; an unfinished suite is not
published and may repeat on explicit resume.

## Direct inference and path workflow

This branch is experiments/path-feedback, based on abstract checkpoint
672b0999ee8792f54e0c03c5a87b6deee913cdb5. Baseline, raw and abstract branches remain
independent snapshots. Their source availability is not empirical validation.

The shared offline runtime resolves local directories/cached snapshots only,
sets offline flags before importing model libraries and owns one lazy vLLM
engine. Structured requests use JSON schemas, with no HTTP fallback, default
model, downloads or remote custom code. Count the complete chat-formatted prompt
plus reserved output against context; overflow is terminal, never shortened.

The baseline remains a one-shot workflow. The branch-local offline_batch runner
uses independent resumable task state machines:

```text
initial request -> saved response -> parse/build current candidate
                -> stdin request -> saved response -> fixed deduplicated stdin
                -> ordinary evaluation
                   -> terminal: success / budget exhausted / invalid reference
                   -> trace_prepare: save request for evaluated source round r
                   -> trace_collect: separate build, all failing case traces
                   -> raw failures + traces + latest candidate
                   -> saved repair request/response -> parse/build replacement
                   -> ordinary evaluation against the same stdin -> ...
```

The explicit replacement budget excludes round zero and trace collection. Initial
generation uses seed S, stdin generation S + 100000, and replacement i uses S + i.
Only committing a repair request advances attempted_iteration. Trace stages refer
to last_evaluated_iteration, with attempted_iteration unchanged.

Every eligible failure retains its zero-based position in the full fixed stdin
set. Eligible statuses are output_mismatch, candidate_timeout and candidate_error,
with a successful reference. Repair sees specification, input format, current
source, all eligible raw cases and normalized traces. Raw cases contain case_id,
input, status, reference_stdout and ordinary candidate_stdout. No passing cases,
diagnostics, task names, private commands, history or abstraction are attached.
Repair retains the language. No rollback, best-candidate selection, implicit
retry, compiler feedback, rewritten specification, rule generation or triage.

## Candidate-only traces

Trace source copies are byte-identical to evaluated source and separately hashed.
The evaluated source, normal C++ binary, execution results and accuracy are never
replaced by tracing artifacts. Python executes the source through a trusted
sys.settrace wrapper with script-style argv, __main__ and stdin. Include candidate
atexit handlers. Filter events to the exact candidate file. GNU g++ compiles a
separate C++20 binary using -O0 -g -fno-inline -fno-pie -no-pie. Python-enabled GDB
reads source line tables and installs unique-address breakpoints before run,
including static initialization, omitting header/library source mappings.

Python tracing invokes sys.executable without resolving its symlink, preserving
virtual-environment selection. Identity records both that invocation path and the
resolved binary. Compilation uses dont_inherit=True so only candidate future
directives apply. Python signal terminations retain a numeric signal_number and
use SIG<number> when no named enum member exists.

Normalize each case to ordered one-based source lines, retaining repetitions,
collection status, completeness, truncation reason, retained/total event counts
and traced-program termination. There are no explicit branch/function events or
variable snapshots. Cross-language normalization describes format, not equivalent
event granularity, timing or counts. Traced observations can differ from ordinary
execution because instrumentation, optimization and paths differ; only ordinary
results score. Traced stdout/stderr and debugger text are diagnostic only.

GNU/Linux and one process/thread are supported. Python audit hooks and standard
thread API guards detect process/thread creation; GDB watches threads and catches
fork/vfork/exec. Detected unsupported execution fails that task. These mechanisms
do not establish detection of every native-code creation path or resist arbitrary
interference with collectors; full OS isolation is deferred.

Defaults are 256 retained events/case, 10 seconds/case including startup, and
30 seconds/trace build. A further event proves event-limit truncation. Timeout
retains an already observed valid prefix. Events stream over an isolated pipe;
stdout/stderr are drained independently with 65536-byte retained prefixes each
and explicit diagnostic truncation flags. GDB initialization and automatic script
loading are disabled, with no startup shell or debuginfod access. Cleanup tracks
inferior process identities and descendants as well as the debugger process group.

A nonempty valid bounded prefix is usable, labelled event_limit or timeout.
Unknown total events remain null. Program exceptions, signals and nonzero exits
can be valid trace terminations. Collector/build/launch/protocol failures, empty
traces, invalid mappings and unsupported concurrency stop only the affected task.
There is no raw fallback, case omission, automatic collection retry or further
feedback trimming to fit context. Final task accuracy is null on tracing failure;
the ordinary score remains last_evaluated_summary. Other tasks continue.

## Persistence and resume

Checkpoint schema is 2, with feedback_mode: path. Identity freezes implementation
and prompts, ordered tasks/specifications, model/runtime, output path, options,
trace protocol/settings and Python/compiler/GDB identities. Tool paths, binary
hashes and available versions are recorded; absent C++ tools only fail collection
when a C++ candidate needs them. Raw/abstract/older/changed checkpoints are rejected
without migration or overwrite. Model metadata is hashed; large weights retain
the existing file-stat/snapshot identity rather than full weight hashes.

Requests are atomic and committed before inference or collection. Successful
inference responses precede stage advancement and are reused before loading the
model. Group only compatible schemas/sampling settings. Keep tokens and latency
attributable to candidate_repair; tracing adds no inference call.

Each source round saves trace_request.json, then a checksummed build envelope
binding source/executable hashes. Each case envelope binds its request/case/input,
normalized trace, bounded diagnostics, duration, command, errors and termination.
Publish these envelopes atomically and commit after each case. Resume validates
committed hashes and adopts matching self-checksummed envelopes published just
before a state crash. Incomplete work without a completion envelope may repeat
on explicit resume. Final feedback and a separate trace timing summary precede
repair. Persist trace_error.json for terminal collection failures.

Committed evaluations, builds and successful inference are reused. Malformed or
wrong-language replacements retain response and available source, with null final
accuracy and separate prior score. Runtime inference errors remain pending for
explicit resume; full-request overflow is terminal. Trace failure is terminal;
resume never silently recollects a published failure. Ctrl+C cooperates at active
operation/case boundaries, returning 130 with completed artifacts retained.

OSError during trace production, including temporary workspace setup or cleanup,
is published as a failed build/case envelope before the task terminates. Envelope
publication and checkpoint-integrity failures still propagate as artifact errors.

Hashes detect changed/missing artifacts, not an actor rewriting all hashes.
Append-only audit logs and root summaries are diagnostic, not checkpoint authority.
Keep model/reference assets immutable and never edit checkpoints to force cases.

## Validation and later scope

Implementation is prepared for user validation through source/diff inspection
only. Agents must not execute the pipeline, models, candidates, references or
collectors. No automated harness, fixture directory or benchmark suite is added.
README contains exact user commands, requirements, artifacts, failures and manual
validation scenarios. No accuracy or performance results are claimed.

Comparison/pools require a later phase review under docs/ROADMAP.md. All four arms
must later share frozen initial candidates, relevant model settings, development
and held-out pools. Repair budgets/stopping rules match; abstraction and tracing
overhead are separate. Held-out results never influence repair. Process trees,
additional languages/interfaces, full OS isolation and deployment remain deferred.
