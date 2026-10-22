# BTP Spec Replication: raw feedback

Generate a replacement for a deterministic stdin/stdout program from its
specification, compare it with a black-box reference, and repair the current
candidate using raw failures. Python and C++20 candidates are supported.

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
The reference command and task name are excluded from synthesis and stdin
generation prompts. The model receives only the specification and input format.

## Start and resume

Run from the repository root. This PowerShell example asks you to choose the
repair budget; replace the task path and run identifier with your own values:

```powershell
$taskPath = "path/to/task.json"
$runId = "my-raw-run"
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

## Options and fixed defaults

| Raw runner option | Default / meaning |
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
| `--temperature T` | `0.2` for generation and repair |
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
repair round `i` uses `S + i`. Seeds do not guarantee identical inference across
different hardware or runtime versions.

## Repair and scoring rules

Stdin is generated once and deduplicated by exact string equality in original
order. The resulting `tests.json` is reused unchanged for every round. Its
actual count can be smaller than `--tests` when the model returns duplicates.

All eligible failures from the current evaluated candidate are included in
input order: input, status, reference stdout, and candidate stdout. There is no
feedback-case limit. Repair receives the specification, input format, latest
candidate, and complete raw payload, and must retain the candidate's language.
Compiler diagnostics do not enter feedback. There is no rollback, best-candidate
selection, implicit inference retry, or regeneration through rewritten specs.

Successful executions require launch, completion within the timeout, and exit
status zero. Stdout comparison preserves exact bytes, including line endings
and invalid UTF-8. Stderr is diagnostic only. JSON uses ASCII escapes and UTF-8
`surrogateescape` representations; after loading JSON, recover original stdout
or stderr bytes using `value.encode("utf-8", errors="surrogateescape")`.

Accuracy is passing cases / all cases only when every reference execution
succeeds. Any reference launch error, timeout, or nonzero exit invalidates the
task with `invalid_reference` and `accuracy: null`. It cannot enter repair.

| Stop reason / status | Meaning |
| --- | --- |
| `no_failures` | Current candidate passes every generated case |
| `repair_budget_exhausted` | Evaluation completed; allowed replacements are exhausted, including budget zero |
| `invalid_reference` | At least one reference case failed; accuracy is unavailable |
| `candidate_parse_failed`, `test_generation_failed` | Initial structured response was unusable |
| `repair_parse_failed`, `language_changed` | Replacement was malformed or changed language; its raw response and any parsed source are retained |
| `build_failed`, `repair_build_failed` | Candidate could not be built; source and diagnostics are retained |
| `context_budget_exceeded` | Full prompt plus reserved output exceeds context; saved request is not shortened |
| `request_failed` | Request preparation failed; see task summary |
| `runtime_failed` | Inference/setup failed; requests remain pending for explicit resume |
| `artifact_failed` | Persistence/integrity failure; see root summary and original artifacts |
| `interrupted` | Stop requested; resume the checkpoint to continue |

Root status is `completed` only when all tasks complete normally; terminal task
failures produce `completed_with_failures`. A failed replacement's final task
accuracy is null. Its earlier score remains explicitly labelled
`last_evaluated_summary`, alongside distinct attempted and last-evaluated rounds.

Exit status is `0` for normal completion (including budget exhaustion), `2` for
setup, task, runtime or checkpoint failure, and `130` for interruption. Ctrl+C
requests a cooperative stop after the active inference/build/evaluation boundary;
it does not promise immediate termination of an active model call.

## Artifacts and checkpoint safety

Raw output defaults to ignored `runs/<experiment-id>/`:

```text
metadata.json                 # schema 2, frozen tasks/config/runtime/source identity
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
    feedback.json             # all failures used for the next repair, when needed
```

Requests are saved before inference. Successful responses are saved before state
advances. Files and state are published atomically; checkpoint hashes cover
candidate files/executables, stdin, responses, builds, evaluation and feedback.
Altered/missing tracked artifacts are rejected before reuse. Metadata and state
also have checksums. Append-only audit logs and the derived root summary are
diagnostic, not checkpoint authorities. Never edit checkpoints to bypass checks.

Resume reuses persisted successful inference and completed evaluations. The
model loads only when an uncached inference request remains. Compatible requests
are batched by schema, temperature, output limit and seed, even when tasks resume
at different stages/rounds. Inference records contain prompts, schemas, runtime
and model identity, settings, errors, latency and available token counts. Batch
wall time is repeated per response; do not sum it across batch members. A
per-response latency estimate is the batch generation time divided by its size.

Resume requires the same source/prompts, ordered tasks/specifications, model
files, package/runtime identity, output path and options. Model metadata files
are hashed; large weights are identified by file size/mtime and snapshot revision,
not full weight-file hashes. Keep model and reference assets immutable. These
checks detect checkpoint changes, not malicious rewriting of all hashes.

Old schema-1 checkpoints are rejected without migration or overwrite. A crash
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
| Out-of-memory/runtime error | Inspect the saved error; restore the environment and explicitly resume with identical options, or start a new identifier if options/model change. |
| Incompatible/changed checkpoint | Use a new identifier for old schemas or changed source/config/model/tasks. For accidental corruption, restore the exact original files; do not recalculate checksums. |

## Later validation by you

Record the Git revision, model/runtime identity and chosen options with results.
Use your own task definitions and inspect the listed artifacts; no automated
harness suite or fixture directory is provided.

1. Run ordinary Python and C++ tasks; inspect source, build output, stdin,
   results, inference records and the final score.
2. Choose budget zero and then a positive budget on separate identifiers; verify
   no replacement exceeds it and stdin stays identical across rounds.
3. Use a task with many failures; compare every eligible failure in input order
   with `feedback.json` and the full repair request.
4. Observe malformed, wrong-language or unbuildable replacements when they occur;
   confirm their responses/source are retained, repair stops, and final accuracy
   is null while the prior evaluated score is separately labelled.
5. Use references that cannot launch, time out or exit nonzero; confirm
   `invalid_reference`, null accuracy, no repair, and exit status 2.
6. Check line-ending and invalid-UTF-8 output differences; confirm they remain
   mismatches and JSON round-trips recover the exact stdout bytes.
7. Interrupt and resume around inference/build/evaluation boundaries. Confirm
   saved successful responses are reused, tasks at different rounds continue,
   and resuming a completed run does not initialize the model.
8. On copies kept for inspection, alter a tracked candidate, stdin, response or
   evaluation artifact, and try an older checkpoint. Confirm resume refuses
   without overwriting it. Also check missing weights and a full-feedback context
   overflow produce actionable errors and preserve available artifacts.

Generated programs receive a sanitized environment without parent secrets. This
is process execution rather than full OS isolation; filesystem isolation remains
future work. [DESIGN.md](DESIGN.md), [AGENTS.md](AGENTS.md) and the
[roadmap](docs/ROADMAP.md) define the agreed scope. Comparison/pools, abstract
feedback, tracing, deployment scaffolding and bundled benchmarks are deferred.
