# BTP Spec Replication: abstract feedback

Generate a replacement for a deterministic stdin/stdout program from its
specification, compare it with a black-box reference, and repair the current
candidate using behavioural classes abstracted from raw failures. Python and
C++20 candidates are supported.

`experiments/abstract-feedback` starts from raw checkpoint
`fc95a260ddfb2096e561dd9cb99c660b1597e5a7`. `experiments/raw-feedback` remains
its independent phase snapshot. Raw and abstract empirical validation remain
pending; this continuation does not claim validated raw results.

This branch is **ready for your testing** after implementation and source-only
inspection. Empirical validation is pending. Agents must not execute the
pipeline, load models, download weights, or run candidate/reference programs.
The commands below are for you to run.

## Required local runtime

- Python 3.10+ in an environment supported by your installed vLLM release.
- Compatible installations of `vllm`, `torch`, `transformers`, and
  `huggingface_hub`, with hardware and memory sufficient for your chosen model.
- vLLM's direct `LLM` and `SamplingParams` interfaces, including
  `vllm.sampling_params.StructuredOutputsParams` and JSON-schema structured
  output. See [vLLM's offline structured-output documentation](https://docs.vllm.ai/en/stable/features/structured_outputs/#offline-inference).
- Complete, locally available model weights, configuration, tokenizer, and a
  chat template supporting system/user messages. Models requiring remote custom
  code are unsupported (`trust_remote_code=False`).
- `g++` with C++20 support if a candidate uses C++; an optional shell `CXX`
  variable may select another compatible compiler executable.
- Your own specification and deterministic reference executable. No tasks or
  benchmark fixtures are bundled.

No model server is needed. One lazy vLLM instance is reused for all uncached
inference within an invocation. Package versions and model identity are saved.
The runner resolves cached identifiers locally, then passes a resolved local
directory to vLLM. Offline flags are set before model-library imports, and cache
resolution uses `local_files_only=True`. Missing weights fail without download;
see [Hugging Face offline mode](https://huggingface.co/docs/huggingface_hub/en/package_reference/environment_variables#hfhuboffline).

## Private configuration

The only required `.env` entry is:

```dotenv
BTP_MODEL=/absolute/path/to/local/model
```

Use your own local directory (Windows paths may use forward slashes), or an
identifier whose complete snapshot is already cached. There is no default model.
The repository-root loader supports one `KEY=VALUE` per line, blank lines,
`#` comment lines, and matching single/double quotes around values. Existing
shell values take precedence. `--model` overrides `BTP_MODEL` for an invocation.
`.env.example` contains a placeholder; private `.env` is ignored by Git.

## Your task definition

Create a task JSON outside the source tree or in your own chosen location:

```json
{
  "name": "task_one",
  "specification": "specification.md",
  "reference": {
    "command": ["python", "reference.py"],
    "cwd": "."
  },
  "input_format": "Describe the complete valid stdin format here.",
  "timeout_seconds": 2.0
}
```

Replace the command with your actual black-box executable and its arguments.
The reference's source is never inspected. `specification` and `reference.cwd`
are resolved relative to the task JSON. Command arguments are passed unchanged
without a shell, and relative command paths resolve in `reference.cwd`.
The specification must be nonempty and describe output behaviour as well as
program semantics. There is no separate output-format field.

Names must be unique, neutral identifiers containing letters, digits, `.`, `_`
or `-`; `.` and `..` are invalid. Names differing only in case are duplicates.
Do not use `metadata.json`, `summary.json`, or `attempts.jsonl` as names.
The reference command and task name are excluded from every model prompt.
Initial synthesis and stdin generation receive only specification and input
format. Abstraction and repair receive the additional evidence described below.

## Start and resume

Run from the repository root. This PowerShell example asks you to choose the
repair budget; replace the task path and run identifier with your own values:

```powershell
$taskPath = "path/to/task.json"
$runId = "my-abstract-run"
$repairRounds = [int](Read-Host "Maximum repair iterations (0 means initial evaluation only)")
python -m pipeline.offline_batch --tasks $taskPath --experiment-id $runId --max-repair-iterations $repairRounds
```

Every run requires an explicit `--max-repair-iterations`; there is no implicit
budget. Round `000` is the initial candidate. A budget of `N` permits at most
`N` replacements after it. Zero performs initial evaluation only.

Resume with the same task, identifier, budget, runtime options and output root:

```powershell
python -m pipeline.offline_batch --tasks $taskPath --experiment-id $runId --max-repair-iterations $repairRounds --resume
```

If starting a new shell, restore those variables to the original values first.
An existing identifier requires `--resume`; a new run needs a fresh identifier.
Run only one invocation per experiment identifier at a time.
For multiple tasks, pass multiple JSON paths after `--tasks`, or replace
`--tasks $taskPath` with `--manifest path/to/manifest.json`. A manifest is a JSON
array of task JSON paths, or `{"tasks": ["task-one.json", "task-two.json"]}`;
relative entries resolve against the manifest's directory.

For a separate one-shot baseline without repair or resume:

```powershell
python -m pipeline.baseline $taskPath --tests 20
```

The baseline uses the same local runtime. The `experiments/no-feedback` branch
contains only that workflow; raw repair lives on `experiments/raw-feedback`.
On this branch, `pipeline.offline_batch` always uses abstract feedback; there is
no raw-mode selector or separate abstract runner. Use a fresh run identifier:
raw-branch checkpoints cannot resume here, even though both use schema 2.

## Options and fixed defaults

| Abstract runner option | Default / meaning |
| --- | --- |
| `--tasks PATH ...` / `--manifest PATH` | Exactly one source is required |
| `--experiment-id ID` | Required unique run-directory identifier |
| `--max-repair-iterations N` | Required nonnegative replacement budget |
| `--resume` | Off; continue the same checkpoint when supplied |
| `--output-root PATH` | Repository-root `runs/` |
| `--tests N` | `20` requested stdin strings, before deduplication |
| `--workers N` | `4` task build/evaluation workers; model calls remain serial batches |
| `--model PATH_OR_ID` | `BTP_MODEL`; no fallback model |
| `--seed N` | `42` |
| `--temperature T` | `0.2` for generation, abstraction and repair |
| `--test-temperature T` | `0.6` for stdin generation |
| `--max-tokens N` | `4096` output tokens per inference |
| `--max-model-len N` | `8192` total prompt + reserved output tokens |
| `--dtype TYPE` | `auto` |
| `--tensor-parallel-size N` | `1` |
| `--gpu-memory-utilization FRACTION` | `0.90` |
| `--max-num-seqs N` | `32` |

All runtime options also apply to `pipeline.baseline`. Its output options are
`--run-root` (repository-root `runs/`) and optional `--run-id`; it accepts one
positional task JSON and `--tests`, and has no repair or resume options.
Each task's execution timeout defaults to `2.0` seconds; C++ compilation has a
30-second timeout. Generation uses seed `S`, stdin generation `S + 100000`, and
repair round `i` uses `S + i`. Abstraction of round `i - 1` before that repair
also uses `S + i`, the same model, temperature and output limit. There are no
abstraction-specific runtime options. Seeds do not guarantee identical inference
across different hardware or runtime versions.

## Abstraction, repair and scoring rules

Stdin is generated once and deduplicated by exact string equality in original
order. The resulting `tests.json` is reused unchanged for every round. Its
actual count can be smaller than `--tests` when the model returns duplicates.

The branch-local workflow is:

```text
current candidate -> evaluate -> all indexed raw failures
                             -> abstraction LLM -> validated behavioural classes
                             -> repair current candidate -> evaluate same stdin
```

Abstraction receives the specification, input format and every eligible failure
from the current evaluated candidate, in input order. Each failure contains
`case_id`, `input`, `status`, `reference_stdout` and `candidate_stdout`. Its ID
is its zero-based position in `tests.json` (also the full `results.json`), not
its position in the failures list. IDs stay stable across rounds; only currently
failing IDs may be cited. Eligible statuses are `output_mismatch`,
`candidate_timeout` and `candidate_error`, with a successful reference execution.
There is no feedback-case limit. Candidate source, passing cases, stderr,
compiler diagnostics, private commands, task names and history are not supplied.

The abstraction response has exactly this structure:

```json
{
  "classes": [
    {
      "label": "Short behavioural description",
      "observed_behavior": "What the cited failures demonstrate",
      "expected_behavior": "What the specification and reference outputs support",
      "case_ids": [0, 3]
    }
  ]
}
```

The IDs above illustrate the shape; actual IDs must belong to the supplied
failure set. Require at least one class, nonblank text and nonempty integer ID
arrays. Reject extra fields, unknown IDs, IDs repeated within a class and missing
coverage. Every eligible failure must be cited at least once; classes may overlap
and narrow singleton classes are allowed. There is no class-count cap.

The prompt asks for relevant input conditions, supported observations and expected
behaviour, without causal speculation, fix suggestions, rewritten specifications,
invented cases or unsupported generalization. Mechanical validation checks shape,
IDs and coverage; it cannot establish semantic support. Inspect the descriptions
against their cited evidence yourself. There is no second judge call.

Repair receives specification, input format, latest candidate and the validated
classes only, including their IDs. It receives no appended raw cases or resolved
examples and must retain the candidate's language. There is no rollback,
best-candidate selection, raw fallback, chunking, implicit inference retry or
regeneration through rewritten specifications.

Abstraction runs only when another replacement is allowed. Budget zero, success,
reference failure and exhausted budget produce no abstraction call. Abstraction
belongs to evaluated source round `r` and does not advance `attempted_iteration`;
committing the next repair request advances it to `r + 1`.

Successful executions require launch, completion within the timeout, and exit
status zero. Stdout comparison preserves exact bytes, including line endings
and invalid UTF-8. Stderr is diagnostic only. JSON uses ASCII escapes and UTF-8
`surrogateescape` representations; after loading JSON, recover original stdout
or stderr bytes using `value.encode("utf-8", errors="surrogateescape")`.

Accuracy is passing cases / all cases only when every reference execution
succeeds. Any reference launch error, timeout, or nonzero exit invalidates the
task with `invalid_reference` and `accuracy: null`. It cannot enter abstraction
or repair.

| Stop reason / status | Meaning |
| --- | --- |
| `no_failures` | Current candidate passes every generated case |
| `repair_budget_exhausted` | Evaluation completed; allowed replacements are exhausted, including budget zero |
| `invalid_reference` | At least one reference case failed; accuracy is unavailable |
| `candidate_parse_failed`, `test_generation_failed` | Initial structured response was unusable |
| `abstraction_parse_failed` | Abstraction JSON or required structure was malformed, including empty classes, blank text, extra fields or invalid field types |
| `abstraction_validation_failed` | Classes cited unknown or repeated within-class IDs, or omitted eligible failures |
| `repair_parse_failed`, `language_changed` | Replacement was malformed or changed language; its raw response and any parsed source are retained |
| `build_failed`, `repair_build_failed` | Candidate could not be built; source and diagnostics are retained |
| `context_budget_exceeded` | Full prompt plus reserved output exceeds context; saved request is not shortened |
| `request_failed` | Request preparation failed; see task summary |
| `runtime_failed` | Inference/setup failed; requests remain pending for explicit resume |
| `artifact_failed` | Persistence/integrity failure; see root summary and original artifacts |
| `interrupted` | Stop requested; resume the checkpoint to continue |

Root status is `completed` only when all tasks complete normally; terminal task
failures produce `completed_with_failures`. Invalid abstraction terminates only
that task without requesting repair; other tasks continue. Its response and
error details are retained. Failed abstraction or replacement gives null final
task accuracy. The earlier score remains explicitly labelled
`last_evaluated_summary`, alongside distinct attempted and last-evaluated rounds.

Exit status is `0` for normal completion (including budget exhaustion), `2` for
setup, task, runtime or checkpoint failure, and `130` for interruption. Ctrl+C
requests a cooperative stop after the active inference/build/evaluation boundary;
it does not promise immediate termination of an active model call.

## Artifacts and checkpoint safety

Abstract output defaults to ignored `runs/<experiment-id>/`:

```text
metadata.json                 # schema 2; identity includes feedback_mode: abstract
attempts.jsonl                # invocation start/end audit
summary.json                  # derived batch status; no aggregate accuracy
<task-name>/
  state.json                  # schema 2, stage, rounds, artifact hashes, checksum
  task.json
  specification.txt
  tests.json                  # one fixed deduplicated stdin set
  summary.json                # terminal task outcome
  inference.jsonl             # diagnostic request/response audit
  inference/
    iteration-000-initial_code_generation.request.json
    iteration-000-initial_code_generation.response.json
    iteration-000-test_generation.request.json
    iteration-000-test_generation.response.json
    iteration-000-failure_abstraction.request.json
    iteration-000-failure_abstraction.response.json
    iteration-001-candidate_repair.request.json
    iteration-001-candidate_repair.response.json
    ...error-<id>.json         # inference failures, when present
  iterations/000/              # each evaluated or attempted candidate round
    candidate.json
    candidate/
      metadata.json
      main.py or main.cpp
      program or program.exe  # successful C++ build only
    build.json
    results.json
    failures.json
    summary.json
    feedback.json             # all indexed raw failures sent to abstraction, when needed
    abstraction.json          # validated classes used for the next repair
    abstraction_error.json    # parse/validation error instead, when present
```

Requests are saved before inference. Successful responses are saved before state
advances. Files and state are published atomically; checkpoint hashes cover
candidate files/executables, stdin, responses, builds, evaluation, raw evidence,
validated classes and abstraction error artifacts.
Altered/missing tracked artifacts are rejected before reuse. Metadata and state
also have checksums. Append-only audit logs and the derived root summary are
diagnostic, not checkpoint authorities. Never edit checkpoints to bypass checks.

Round `000` abstraction prepares replacement `001`, and similarly for subsequent
rounds. Abstraction uses separate `abstraction_request` / `abstraction_response`
stages. Its successful raw model response is retained even if class parsing fails.
`abstraction_error.json` records the evaluated source round, stop reason, error
type and message. Invalid summaries are terminal and are not regenerated by resume.

Resume reuses persisted successful inference, validated classes and completed
evaluations. The model loads only when an uncached inference request remains.
Compatible requests are batched by schema, temperature, output limit and seed,
even when tasks resume at different stages/rounds. Inference records contain prompts, schemas, runtime
and model identity, settings, errors, latency and available token counts. Batch
wall time is repeated per response; do not sum it across batch members. A
per-response latency estimate is the batch generation time divided by its size.
The `failure_abstraction` step identifies abstraction usage separately from
`candidate_repair`. Each response's output records available `prompt_tokens`,
`completion_tokens`, `latency_s` (generation estimate), `batch_latency_s` and
`finish_reason`; the response envelope also records observed call latency,
batch ID and size. Missing counts remain null, not zero. Cached responses retain
their original measurements; reuse is not another model call.

Resume requires the same feedback mode, source/prompts, ordered tasks/specifications,
model files, package/runtime identity, output path and options. Model metadata
files are hashed; large weights are identified by file size/mtime and snapshot revision,
not full weight-file hashes. Keep model and reference assets immutable. These
checks detect checkpoint changes, not malicious rewriting of all hashes.

Old schema-1 checkpoints, raw-branch checkpoints and changed implementation/run
identities are rejected without migration or overwrite. A crash
before initial `metadata.json` publication leaves an incomplete initialization;
choose a new identifier. Ordinary run artifacts must never be committed or
removed as source cleanup.

One-shot baseline artifacts instead sit directly in `runs/<run-id>/`, with
`candidate/`, build/tests/results/failures/summary, metadata, per-call inference
JSON and `llm_log.jsonl`. The baseline has no checkpoint/resume contract.

## Troubleshooting

| Problem | Action |
| --- | --- |
| Missing model/weights | Point `BTP_MODEL` at a complete local directory or an already cached snapshot. The runner never fetches missing files. |
| Missing/incompatible dependencies | Use a mutually compatible installed vLLM/Torch/Transformers/Hub environment exposing `StructuredOutputsParams`. Saved errors and versions identify the failure. No fallback API is used. |
| Tokenizer/chat-template failure | Supply local tokenizer/template files supporting system/user chat; custom remote code is disabled. |
| Context overflow | Inspect the saved complete request. Start a new identifier with a larger supported `--max-model-len` and/or a smaller output reservation. Feedback is never truncated. |
| Missing C++ compiler/build failure | Make the C++20 compiler available on PATH or set shell `CXX`; inspect `build.json`. Failed builds end the task without diagnostic-driven repair. |
| Invalid reference | Check the private command, working directory, timeout and captured results. Correct the reference, then use a new identifier. |
| Unusable abstraction | Inspect its saved response, `feedback.json`, `abstraction_error.json` and task summary. The task is terminal with no raw fallback; use a new identifier for another run. Do not edit checkpoint artifacts. |
| Out-of-memory/runtime error | Inspect the saved error; restore the environment and explicitly resume with identical options, or start a new identifier if options/model change. |
| Incompatible/changed checkpoint | Use a new identifier for old schemas or changed source/config/model/tasks. For accidental corruption, restore the exact original files; do not recalculate checksums. |

## Later validation by you

Record the Git revision, model/runtime identity and chosen options with results.
Use your own task definitions and inspect the listed artifacts; no automated
harness suite or fixture directory is provided.

1. Run ordinary Python and C++ tasks; inspect source, build output, stdin,
   results, inference records and final score. Inspect mixed output mismatches,
   execution errors and timeouts when they occur. Check overlapping classes and
   singleton classes remain usable when their evidence is valid and complete.
2. Choose budget zero and then a positive budget on separate identifiers; verify
   no replacement exceeds it and stdin stays identical across rounds. Confirm
   no abstraction after success, invalid reference or exhausted budget. During
   abstraction, attempted and last-evaluated rounds should remain equal.
3. Use a task with many failures; compare every eligible failure in input order
   with `feedback.json` and the abstraction request. Check IDs against the full
   fixed stdin set, including gaps for passing cases. Inspect class grounding
   and coverage. Confirm repair receives only classes, specification, input
   format and current source, with no appended raw cases or ID lookup payload.
4. Observe malformed, wrong-language or unbuildable replacements when they occur;
   confirm their responses/source are retained, repair stops, and final accuracy
   is null while the prior evaluated score is separately labelled.
5. Use references that cannot launch, time out or exit nonzero; confirm
   `invalid_reference`, null accuracy, no abstraction/repair, and exit status 2.
6. Check line-ending and invalid-UTF-8 output differences; confirm they remain
   mismatches and JSON round-trips recover the exact stdout bytes.
7. Interrupt and resume around abstraction request/response, class publication,
   repair request/response, build and evaluation boundaries. Confirm saved
   successful responses and classes are reused, tasks at different stages/rounds
   continue, and resuming a completed run does not initialize the model. A crash
   after class-file publication but before committing state may repeat parsing
   of the saved response, without repeating inference.
8. On copies kept for inspection, alter a tracked candidate, stdin, response or
   evaluation artifact, and try an older checkpoint. Confirm resume refuses
   without overwriting it. Include classes, raw evidence, abstraction responses,
   and a raw-branch schema-2 checkpoint. Check missing weights and full-request
   context overflow in abstraction and repair preserve requests without truncation.
9. When malformed summaries, extra fields, blank text, unknown IDs, duplicate IDs
   or incomplete coverage occur, inspect the corresponding abstraction stop reason,
   retained raw response and error artifact. Confirm no replacement is requested,
   final accuracy is null, the last score remains separately labelled, other
   tasks continue, and terminal failures produce exit status 2. Do not modify
   responses to force these cases; checkpoint integrity must remain enforced.
10. Compare `failure_abstraction` and `candidate_repair` records separately for
    prompts, schemas, model identity, sampling, token counts and latency. Account
    for each batch once when using batch wall time, including explicit resumed
    runtime-error attempts where applicable.

Generated programs receive a sanitized environment without parent secrets. This
is process execution rather than full OS isolation; filesystem isolation remains
future work. [DESIGN.md](DESIGN.md), [AGENTS.md](AGENTS.md) and the
[roadmap](docs/ROADMAP.md) define the agreed scope. Comparison/pools, tracing,
deployment scaffolding and bundled benchmarks are deferred.
