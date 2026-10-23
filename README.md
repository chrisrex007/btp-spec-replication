# BTP Spec Replication: path feedback

Generate a Python or C++20 candidate from a deterministic stdin/stdout program's
specification, compare it with a hidden reference, then repair the current
candidate using **all current raw failures plus candidate execution traces**.
Only ordinary uninstrumented executions determine accuracy. The reference is
never inspected, instrumented or traced. There is no abstraction call on this arm.

`experiments/path-feedback` starts from exact abstract checkpoint
`672b0999ee8792f54e0c03c5a87b6deee913cdb5`. Baseline, raw and abstract branches remain
independent snapshots. Raw, abstract and path empirical validation are pending.
Implementation and source/diff inspection do not establish experimental results.
The commands below are for you: agents do not run the pipeline, models, collectors,
candidates or references, and no automated harness/benchmarks are bundled.

## Requirements and private configuration

- GNU/Linux for path collection, with `/proc` available. One process/thread per
  candidate is supported. Containers must permit GDB to debug its own child.
- Python 3.10+ in an environment supported by the installed vLLM release.
- Compatible installed `vllm`, `torch`, `transformers` and `huggingface_hub`, and
  sufficient accelerator memory for your local model. vLLM must expose direct
  `LLM`, `SamplingParams`, and `vllm.sampling_params.StructuredOutputsParams` with
  JSON-schema output. See [offline structured output](https://docs.vllm.ai/en/stable/features/structured_outputs/#offline-inference).
- Complete local weights/configuration/tokenizer and a chat template supporting
  system/user messages. Remote custom code is disabled. Missing weights are never
  downloaded; local cache lookup uses `local_files_only=True`.
- GNU `g++` with C++20 support and Python-enabled GDB for C++ tracing. Use GDB 13+
  exposing the Python line-table, breakpoint and thread-event APIs and the
  debuginfod setting. `CXX` may select a GNU compiler executable; supply a path or
  executable name, not flags. Python-only collection does not require C++ tools.
- Your own specification and deterministic reference executable.

The only required repository-root `.env` entry is:

```dotenv
BTP_MODEL=/absolute/path/to/local/model
```

An already cached model identifier also works; there is no fallback model or
HTTP server. One lazy in-process vLLM model is reused per invocation, loading only
when an uncached inference request remains. Offline flags precede library imports.
The loader accepts one KEY=VALUE per line, blank/comment lines and optional matching
quotes. Shell values take precedence; `--model` overrides BTP_MODEL. Do not commit
or copy private `.env`. `.env.example` contains only a placeholder.

## Task definitions

Create your own task JSON and specification, for example:

```json
{
  "name": "task_one",
  "specification": "specification.md",
  "reference": {"command": ["python", "reference.py"], "cwd": "."},
  "input_format": "Describe one complete valid stdin string here.",
  "timeout_seconds": 2.0
}
```

Specification/reference paths resolve relative to the task JSON. Reference
commands are argv arrays, never shell commands. Names contain letters, digits,
periods, underscores or hyphens and must be unique within a run. Names and private
reference configuration are persisted for inspection but never added to model
prompts. Only specification and input_format are model-visible task fields;
describe required output behaviour in the specification.

## Start and resume

From the repository root in your GNU/Linux environment:

```bash
task_path=/absolute/path/to/task.json
run_id=my-path-run
read -r -p 'Maximum repair iterations (0 means initial evaluation only): ' repair_rounds
python -m pipeline.offline_batch --tasks "$task_path" --experiment-id "$run_id" --max-repair-iterations "$repair_rounds"
```

Every run requires an explicit nonnegative replacement budget. Round 000 is the
initial candidate; N permits at most N replacements. Zero evaluates only the
initial candidate and performs no tracing or repair.

Resume using identical tasks, identifier, budget, runtime and trace options:

```bash
python -m pipeline.offline_batch --tasks "$task_path" --experiment-id "$run_id" --max-repair-iterations "$repair_rounds" --resume
```

Restore the variables if using a new shell. Run one invocation per identifier.
An existing identifier requires `--resume`; changed source/options/model/tool
identity requires a new identifier. Raw/abstract checkpoints cannot resume here.

To choose explicit trace limits, use the same flags for both start and resume:

```bash
python -m pipeline.offline_batch --tasks "$task_path" --experiment-id my-bounded-path-run --max-repair-iterations "$repair_rounds" --trace-max-events 256 --trace-timeout-seconds 10 --trace-build-timeout-seconds 30 --trace-gdb /usr/bin/gdb
```

For multiple tasks, supply multiple paths after `--tasks`, or use
`--manifest /path/to/manifest.json`. A manifest is an array of task paths or
`{"tasks": ["one.json", "two.json"]}`; relative entries resolve against its parent.

A separate one-shot baseline has no repair, tracing or resume:

```bash
python -m pipeline.baseline "$task_path" --tests 20
```

Use `experiments/no-feedback` for the independent baseline snapshot and the raw
or abstract branches for those workflows. This branch's offline_batch runner
always uses path feedback; there is no feedback-mode selector.

## Options and defaults

| Runner option | Default / meaning |
| --- | --- |
| `--tasks PATH ...` / `--manifest PATH` | Exactly one source required |
| `--experiment-id ID` | Required unique run-directory identifier |
| `--max-repair-iterations N` | Required nonnegative replacement budget |
| `--resume` | Off; continue the identical checkpoint |
| `--output-root PATH` | Repository-root `runs/` |
| `--tests N` | 20 requested stdin strings before deduplication |
| `--workers N` | 4 task build/evaluation/collection workers; inference uses serial batches |
| `--trace-max-events N` | 256 retained line events per failing case; positive integer |
| `--trace-timeout-seconds S` | 10.0 seconds per failing case including collector startup; finite positive |
| `--trace-build-timeout-seconds S` | 30.0 seconds per evaluated C++ trace build; finite positive |
| `--trace-gdb PATH_OR_NAME` | gdb, resolved to a frozen executable identity |
| `--model PATH_OR_ID` | BTP_MODEL; no fallback |
| `--seed N` | 42 |
| `--temperature T` | 0.2 for initial generation and repair |
| `--test-temperature T` | 0.6 for stdin generation |
| `--max-tokens N` | 4096 output tokens per inference |
| `--max-model-len N` | 8192 total prompt plus reserved output tokens |
| `--dtype TYPE` | auto |
| `--tensor-parallel-size N` | 1 |
| `--gpu-memory-utilization FRACTION` | 0.90 |
| `--max-num-seqs N` | 32 |

Shared model/runtime options also apply to baseline. Baseline accepts a positional
task, `--tests`, `--run-root` (repository-root runs/) and optional `--run-id`, but
no repair/resume/trace options. Task ordinary execution timeout defaults to 2.0
seconds; ordinary C++ compilation has a separate 30-second timeout.
Generation seed is S, stdin seed S + 100000, replacement i seed S + i. Seeds do
not guarantee identical inference across hardware/runtime versions.

## Scoring and feedback

Generate/deduplicate stdin once by exact string equality in original order, then
reuse tests.json unchanged. Actual cases may be fewer than `--tests`. Each case
is a complete UTF-8 stdin string. Successful ordinary stdout is compared by exact
bytes, including line endings and invalid UTF-8. Stderr is diagnostic only.
Persist output using UTF-8 surrogateescape and ASCII-escaped JSON. Recover bytes
from a loaded output string with `value.encode("utf-8", errors="surrogateescape")`.

Accuracy is passing / all cases only when every reference succeeds. Any reference
launch failure, timeout or nonzero exit produces invalid_reference, null accuracy,
no tracing/repair and exit 2. Ordinary candidate errors/timeouts are failures.

When repair budget remains, trace every current output_mismatch, candidate_timeout
and candidate_error with a successful reference. Case IDs are zero-based positions
in the full fixed stdin set/results, not renumbered failure positions. Repair sees
specification, input format, current source and every raw failure with its trace:

```json
{
  "case_id": 3,
  "input": "example stdin\n",
  "status": "output_mismatch",
  "reference_stdout": "expected\n",
  "candidate_stdout": "observed\n",
  "trace": {
    "lines": [1, 2, 4, 5, 4, 5],
    "collection_status": "truncated",
    "complete": false,
    "truncation_reason": "event_limit",
    "event_count": 6,
    "total_event_count": null,
    "termination": {"kind": "collection_stopped", "reason": "event_limit"}
  }
}
```

This illustrates shape with a six-event limit, not the default or experimental
results. Line numbers are one-based locations in the exact current source.
Passing cases, history, diagnostics, private commands and task names are excluded.
There is no abstraction call or causal/repair-advice generator. Retain the current
language; no rollback, best-candidate selection, compiler feedback or retry.

## Collection semantics and limitations

Python uses a trusted sys.settrace wrapper with unchanged source, script-style
argv/__main__, normal stdin and candidate atexit callbacks. C++ uses a separately
compiled identical source with `-std=c++20 -O0 -g -fno-inline -fno-pie -no-pie`.
GDB installs candidate debug-line address breakpoints before execution, including
static initialization. It uses no user initialization, automatic scripts, startup
shell or debuginfod access. The normal optimized binary remains the scoring binary.

Only candidate-file source lines enter traces. Preserve their observed order and
repetitions; omit library/header locations, explicit call/branch events and values.
Python interpreter events and C++ debug-location hits have different granularity;
normalized format does not make their counts or timings equivalent. Collection
uses a separate source/build directory, and instrumentation/optimization/path
changes can affect execution. A trace describes that instrumented run, not the
reference or a guaranteed causal explanation for the ordinary failure.

One process/thread is supported. Standard Python thread starts and process APIs
are rejected; GDB detects additional threads and catches fork/vfork/exec. Native
extensions can bypass Python-level detection, and collectors are not a sandbox or
proof against malicious interference. Full OS/filesystem isolation is future work.

Events stream through a separate pipe. Keep at most N events; observing event N+1
proves event-limit truncation and terminates collection. Timeout also terminates
collection, preserving already observed valid lines. Nonempty valid prefixes are
usable, explicitly labelled `event_limit` or `timeout`. Total event count is null
when incomplete. Complete traces have collection_status complete, complete true,
null truncation_reason and a known event count. Exceptions, signals and nonzero
candidate exits can still yield valid traces. Termination describes the traced
program, separately from collector exit_code; collection limits are not ordinary
candidate outcomes.

Each stdout/stderr diagnostic channel retains at most 65536 bytes and marks excess
as truncated while continuing to drain it. GDB output may mix debugger and candidate
text. Diagnostics never enter repair. Cleanup handles the collector process group
and separately tracked inferiors/descendants, binding PID cleanup to process start
identity. Collection limits are independent of the ordinary scoring timeout.

Missing tools, trace-build failure, collector launch/protocol failure, bad mappings,
unsupported concurrency or empty traces terminate only that task. An empty prefix
is unusable even if timeout caused it. No raw fallback, automatic retry, skipped
failures, chunking or prompt-based trimming is allowed. Full prompt plus reserved
output must fit context; overflow preserves the complete request and stops.

## Artifacts, resume and overhead

Output defaults to ignored `runs/<experiment-id>/`:

```text
metadata.json                 # schema 2, feedback_mode: path and frozen identity
attempts.jsonl                # diagnostic invocation audit
summary.json                  # batch status and per-task state, no aggregate score
<task-name>/
  state.json                  # schema 2, stage, rounds, artifact hashes, checksum
  task.json
  specification.txt
  tests.json
  summary.json
  inference.jsonl
  inference/
    iteration-000-initial_code_generation.request.json
    iteration-000-initial_code_generation.response.json
    iteration-000-test_generation.request.json
    iteration-000-test_generation.response.json
    iteration-001-candidate_repair.request.json
    iteration-001-candidate_repair.response.json
    ...error-<id>.json
  iterations/000/
    candidate.json
    candidate/                # original source/metadata and normal C++ binary
    build.json
    results.json
    failures.json
    summary.json              # ordinary evaluation only
    trace_request.json        # source-round request saved before collection
    traces/
      build.json              # checked completion envelope + attachment hashes
      build/                  # identical source and separate C++ debug program
      case-000003.json         # checked per-case completion envelope
      summary.json            # trace build time and per-case collection time
    feedback.json             # all ordered raw failures plus usable traces
    trace_error.json          # terminal tracing error, when present
```

Trace build/case envelopes have schema_version, content_sha256, identity,
attachments and result. Their results retain commands, bounded diagnostics,
duration, errors and normalized observations. Transient command/config/output
paths may no longer exist after collection; the published source/binary and exact
parameters remain available. Requests bind source round/hash, fixed stdin hash,
eligible IDs/evidence hash, settings, protocol and tool identity.

Publish requests before collection/inference. Successful inference responses are
saved before advancing state. Hash original and trace source/binaries, results,
responses, trace cases/diagnostics, final feedback and errors. Build/case completion
envelopes are published atomically before checkpoint commits. Resume adopts a
matching checksummed envelope left just before a state-save crash, including
verifying its attachments. Incomplete work without a completion envelope may
repeat on explicit resume; completed cases are reused, not recollected.

trace_prepare and trace_collect belong to evaluated source round r. They never
advance attempted_iteration. Only committing repair request r+1 advances it.
Budget zero, success, invalid reference and exhausted budget produce no tracing.
Ctrl+C cooperates at operation/case boundaries; it does not promise immediate
cancellation of an active model call or build. Completed cases remain reusable.

Resume requires identical feedback mode, source/prompts, tasks, output location,
model/runtime, options and trace tool identities. Available Python/compiler/GDB
paths, binary hashes and version information are frozen; C++ tools are inspected
for identity even if the candidate is later Python. Missing C++ tools do not fail
Python collection. Installing/changing a tool changes identity and requires a new
identifier. Keep reference/model/tool assets immutable. Metadata/state checksums
and artifact hashes detect changes, not an actor rewriting every hash.

Resume successful inference before loading the model. Compatible schemas,
temperature/output limit/seed determine batches. Inference records retain prompts,
schemas, model/runtime identity, sampling, available token counts and latency.
Missing token counts remain null. Record candidate_repair usage separately from
trace build_duration_s and per-case duration_s in traces/summary.json. Cached
responses/cases retain original timings; reuse is not another call/collection.
Batch wall time is repeated per response, so count each batch once rather than
summing its copies. Append-only audits/root summaries are diagnostic, not authority.
Never edit checkpoints to bypass integrity checks or delete ordinary runs.

## Failure handling and troubleshooting

| Stop/status | Meaning / action |
| --- | --- |
| no_failures | Ordinary candidate passes every fixed case |
| repair_budget_exhausted | Ordinary evaluation completed with no replacements remaining |
| invalid_reference | Fix your private executable/configuration, then start a new identifier |
| candidate_parse_failed / test_generation_failed | Initial structured response unusable; inspect saved response |
| repair_parse_failed / language_changed | Replacement malformed/wrong-language; inspect retained response/source |
| build_failed / repair_build_failed | Ordinary build failed; inspect build.json; no diagnostic-driven repair |
| trace_setup_failed | Collection requires GNU/Linux; inspect trace_error.json |
| trace_build_failed | Missing GNU toolchain/GDB or failed debug build; inspect traces/build.json |
| trace_collection_failed | Collector launch, setup, protocol or mapping failure; inspect case result/diagnostics |
| trace_empty | No candidate source-line events; no raw-only fallback |
| trace_unsupported | Detected extra thread/process, exec or unsupported trace-hook change |
| context_budget_exceeded | Full request exceeds context; new identifier with a supported larger context and/or smaller output reservation; never silently trim feedback |
| request_failed | Request preparation failed; inspect task summary |
| runtime_failed | Inference/runtime failure; restore identical environment and explicitly resume |
| artifact_failed | Persistence/integrity failure; restore exact originals or use a new identifier |
| interrupted | Resume identical checkpoint to continue |

Trace failures and failed replacements have null final accuracy; the prior
ordinary score remains explicitly labelled last_evaluated_summary with distinct
attempted/last-evaluated rounds. Trace failure does not erase or rescore an ordinary
evaluation. Other tasks continue. Terminal failures are not retried by resume.
Root status is completed only when all tasks complete normally; task failures
produce completed_with_failures. Exit codes are 0 for normal completion including
budget exhaustion, 2 for setup/task/runtime/checkpoint failure, 130 for interruption.

For missing weights, supply a complete local/cached model; no downloads/fallback.
For runtime incompatibility, install mutually compatible versions exposing the
required structured-output API; saved versions/errors identify the problem. For
GDB errors, inspect Python support, version, ptrace permissions, GNU compiler and
source mappings. Do not substitute trace results for ordinary results. Use a new
identifier for changed settings/tools; never recompute hashes on edited checkpoints.

## Later validation by you

Record exact Git revision, model/runtime/tool identities and options with results.
Use your own task definitions. No accuracy, performance or compatibility result is
claimed until you execute and inspect your runs.

1. Run Python and C++ tasks. Inspect ordinary builds/results and separate trace
   copies/debug binaries. Check mismatches, loops, function bodies, static
   initialization, Python exit handlers, exceptions, crashes and timeout prefixes;
   locations must map to candidate source, excluding wrappers/libraries.
2. Compare every eligible failure and original ID/order with feedback.json and the
   repair request. Confirm passing cases/diagnostics/private commands/history are
   absent and there is no abstraction inference. Check fixed stdin across rounds.
3. Use zero and positive budgets on separate identifiers; check no trace after
   success, invalid reference or exhausted budget and no replacement beyond budget.
   Attempted/last-evaluated rounds stay equal throughout collection.
4. Choose small event/time limits on fresh identifiers. Inspect event N+1 truncation,
   known/unknown counts, nonempty timeout prefixes and explicit prompt labels.
   Empty/malformed traces must fail, never yield raw-only repair.
5. Observe missing tools, denied debugger launch, unusable mappings and debug-build
   failures when they occur. Check saved errors, null final accuracy, retained
   ordinary score, continued unrelated tasks and exit 2. Start new identifiers for
   changed tool identity rather than editing metadata.
6. Use your own single-thread/process violations through standard Python thread,
   fork/spawn/exec APIs and C++ thread/fork/exec calls. Confirm unsupported status
   and cleanup, including debugger inferiors outside its process group.
7. Use references that cannot launch, time out or exit nonzero. Confirm the entire
   task is invalid_reference with null accuracy and no trace/repair artifacts.
8. Inspect malformed/wrong-language/unbuildable replacements when produced: retained
   response/source, stopped task, null final accuracy and separately labelled prior
   score. Check exact line-ending and invalid-UTF-8 output round trips.
9. Interrupt/resume around trace request, debug build, individual case publication,
   final feedback, repair request/response and ordinary evaluation. Completed
   envelopes/cases/evaluations/inference must be reused. A fully cached completed
   run must not load the model. Inspect mixed-stage multi-task resume.
10. On inspection copies, alter/remove tracked trace source/binary/case/feedback or
    inference/evaluation artifacts; try raw/abstract/older checkpoints. Resume must
    reject without overwrite. Do not edit responses to manufacture model failures.
11. Inspect complete-request overflow with many failures/long traces: saved complete
    request, terminal overflow, no omitted cases or further shortening. Inspect
    large diagnostic output truncation flags separately from trace truncation.
12. Account for tracing build/case durations separately from repair token/latency
    records. Cached artifacts retain original measurements; count batch wall times
    once. Verify trace outcomes never overwrite ordinary results or accuracy.

[AGENTS.md](AGENTS.md), [DESIGN.md](DESIGN.md) and [the roadmap](docs/ROADMAP.md)
define the phase. Comparison/pools, process-tree tracing, full OS isolation and
deployment remain deferred. No merge or push is automatic.
