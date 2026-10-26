# Specification-driven program replication: one-shot baseline

This branch generates one Python or C++20 candidate from a natural-language
specification, builds it, generates stdin tests, compares executions with a
private reference, and persists artifacts. The candidate is never modified
using evaluation feedback.

Inference is direct and local, using an in-process vLLM engine. No model server,
HTTP endpoint, API key, or remote model download is used. Validation belongs to
the user: agents must not run the pipeline or candidate/reference programs.

## Model and configuration

Use the existing **Qwen2.5-Coder-14B-Instruct** checkpoint at
`~/models/qwen2.5-coder-14b`. It is the largest locally available coding model;
its instruction tuning and code specialization suit this experiment. This is a
model-selection rationale, not evidence of benchmark performance. See the
[Qwen evaluation](https://qwenlm.github.io/blog/qwen2.5-coder-family/).

Privately edit repository-root `.env` to contain only:

```dotenv
BTP_MODEL=qwen2.5-coder-14b
```

Do not overwrite an existing private file using a shell command that prints or
copies its old contents. `.env.example` contains a placeholder. One `KEY=VALUE`
entry per line, optional `#` comments, and matching single/double quotes are
supported. Existing shell values take precedence.

`BTP_MODEL` is a single directory name, resolved beneath `~/models`. Remote model
IDs, absolute paths, traversal, symlinks outside the model root, missing model
files, and missing configuration fail clearly. The supported checkpoint layout
contains `config.json`, `tokenizer_config.json`, `tokenizer.json`, and either
`model.safetensors` or an index plus all indexed safetensor shards.

The engine uses BF16, 32,768-token context, one concurrent request, eager
execution, tensor parallelism 1, and GPU-memory utilization 0.80. The checkpoint's
chat template is applied by `LLM.chat`; existing JSON schemas constrain the
sampler through the explicitly selected XGrammar backend. Structural JSON
whitespace is restricted (`disable_any_whitespace=True`) to prevent unrestricted
whitespace loops between elements. Contents of string values, including stdin
spaces and escaped newlines, remain unchanged. This decoding setting differs
from the earlier failed runs and is recorded in inference metadata; it does not
guarantee completion or candidate correctness. Sampling defaults are explicit, rather than inherited from the
checkpoint's generation configuration. Both logical calls reuse the engine.
Initialization is included in the first call's latency. There are no inference
retries or fallback models. Fixed seeds do not guarantee bitwise reproducibility
across different GPU/library configurations.

## Python environment

Run setup from the repository root. The system Python is 3.9, and the previously
available pyenv Python 3.12 lacks its OpenSSL 1.1 runtime libraries. Use the
separate pinned Python below; these commands leave the system Python unchanged.
Setup downloads dependencies, but inference itself uses only local model files.
All environments, setup caches, and build outputs below are ignored by Git.

```bash
mkdir -p runs/setup
python3 -m pip install --index-url https://pypi.org/simple --target runs/setup/bootstrap 'uv==0.9.5'
UV_PYTHON_INSTALL_DIR="$PWD/runs/setup/python" UV_CACHE_DIR="$PWD/runs/setup/uv-cache" runs/setup/bootstrap/bin/uv python install 3.12.12
UV_CACHE_DIR="$PWD/runs/setup/uv-cache" runs/setup/bootstrap/bin/uv venv --python "$PWD/runs/setup/python/cpython-3.12.12-linux-x86_64-gnu/bin/python3.12" venv
UV_CACHE_DIR="$PWD/runs/setup/uv-cache" runs/setup/bootstrap/bin/uv pip install --python venv/bin/python --index-url https://pypi.org/simple 'vllm==0.21.0' 'cmake==3.31.6'
UV_CACHE_DIR="$PWD/runs/setup/uv-cache" runs/setup/bootstrap/bin/uv pip freeze --python venv/bin/python > runs/setup/inference-requirements.lock.txt
```

Do not recreate an existing working `venv`; run only the installation/freeze
commands when it already uses the prepared Python. Preserve the resolved lock
file with the experiment artifacts; it pins transitive dependencies for later
reinstallation. The prepared local wheel set and its SHA-256 manifest are under
`runs/setup/wheels/`. Once prepared, reinstall the exact environment without
network access using:

```bash
UV_CACHE_DIR="$PWD/runs/setup/uv-cache" runs/setup/bootstrap/bin/uv pip install --python venv/bin/python --no-index --find-links runs/setup/wheels --requirement runs/setup/inference-requirements.lock.txt
```

`g++` supporting C++20 is also required. Inference imports are
lazy, so importing the client does not load GPU weights. Offline and telemetry
disable flags are set before importing inference libraries.

## Frozen benchmark collection

The seven tasks are preselected before observing baseline results. Keep every
outcome, including 100% scores. Difficulty is a hypothesis: perfect agreement
on a small generated suite neither proves equivalence nor justifies deleting a
task. Report utility and algorithmic results separately. Public tasks may have
appeared in model training data; this collection is not claimed to be unseen.

| Task | Group | Reference and fixed behavior |
|---|---|---|
| task-01 | Utility | jq 1.6: recursively sort/deduplicate arrays; compact JSON with sorted keys |
| task-02 | Utility | GNU bc 1.07.1: bounded scaled decimal expression programs |
| task-03 | Utility | libxml2 2.9.13: inclusive canonical XML 1.0 with comments |
| task-04 | Utility | cmark 0.31.2: paragraph-only inline markup rendered as HTML |
| task-05 | Algorithmic | Codeforces 86D: weighted occurrence sums over intervals |
| task-06 | Algorithmic | Codeforces 446C: Fibonacci interval additions and modular sums |
| task-07 | Algorithmic | Codeforces 438D: sums, interval remainder updates, point assignments |

`benchmarks/collection.json` lists the task configs and provenance. Each task has
its frozen `spec.md`, `task.json`, and `provenance.json`. Provenance identifies
reference versions, source revisions and hashes, attribution, and preparation
status. The cmark source archive is preserved unchanged under
`benchmarks/upstream/`. Algorithmic references are unchanged accepted solutions
from the pinned [CodeContests dataset](https://huggingface.co/datasets/deepmind/code_contests).
Reference acquisition/build status is distinct from behavioral validation.

The specifications define bounded valid-input domains and exact output bytes.
These are specific modes/subsets, not replicas of every command-line option of
the upstream utilities. References run with an empty environment except the
explicit locale and, for bc, disabled numeric line wrapping. Every test starts
a fresh process; state within a finite stdin program does not persist across
tests. No input may access external files, networks, or an interactive session.

Only the specification and input description enter generation prompts. Task
names are neutral; reference source, executable identities, upstream tests,
and provenance stay private to the harness. Do not insert upstream test suites
into evaluation, change the frozen inputs/specifications after observing
failures, or regenerate candidates using failures.

## Prepare reference executables

The first three references already use installed `/usr/bin` utilities. Their
exact package versions and executable hashes are recorded in provenance. A
missing or different installation must be resolved before interpreting results.
Build the other references using these commands. They compile programs but do
not execute the reference programs or their test suites.

```bash
mkdir -p runs/reference-sources runs/reference-build
sha256sum benchmarks/upstream/cmark-0.31.2.tar.gz
tar -xzf benchmarks/upstream/cmark-0.31.2.tar.gz -C runs/reference-sources
venv/bin/cmake -S runs/reference-sources/cmark-0.31.2 -B runs/reference-build/cmark -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DBUILD_SHARED_LIBS=OFF
venv/bin/cmake --build runs/reference-build/cmark --parallel 4
g++ -O2 -std=c++20 benchmarks/task-05/reference.cpp -o runs/reference-build/task-05
g++ -O2 -std=c++20 benchmarks/task-06/reference.cpp -o runs/reference-build/task-06
g++ -O2 -std=c++20 benchmarks/task-07/reference.cpp -o runs/reference-build/task-07
```

Compare the printed archive hash with task-04 provenance. Do not run a task whose
provenance says its reference is unavailable. No alternative task is substituted
if an upstream reference cannot be obtained.

## Commands for user-run validation

After environment/reference preparation and private model configuration, run
these from the repository root. Select GPU 0, with sufficient free memory at
launch. Each command makes exactly one candidate-generation call and one basic
test-generation call when earlier stages succeed. Generation settings are:
candidate temperature 0.2 with 8192 output tokens; test temperature 0.6 with
24000 output tokens. The test output budget was increased from 12000 after an
incomplete test-generation response; preserve earlier failed runs and distinguish
these settings when reporting results. Prompt plus output must fit the 32768-token
context window. Model/schema/load failures stop the run and are persisted.

```bash
export PATH="$PWD/venv/bin:$PATH"
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-01/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-02/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-03/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-04/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-05/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-06/task.json --tests 20 --seed 42
CUDA_VISIBLE_DEVICES=0 venv/bin/python -m pipeline.baseline benchmarks/task-07/task.json --tests 20 --seed 42
```

Each invocation creates a timestamped run directory with microsecond precision.
An explicit `--run-id` must start with a letter or digit and contain only letters,
digits, dots, underscores, or hyphens; its resolved directory must stay inside
`--run-root`. Retain all runs, including
infrastructure failures and accidental reruns; identify the intended baseline
run explicitly in any report. Do not pick the best seed or repeat until a
preferred score appears.

User validation should confirm that both response schemas work, records retain
successful/failed logical calls, candidates remain unchanged, and artifact
files contain the exact evaluated inputs and outputs. Check that generated
inputs satisfy the frozen valid-input domains before interpreting scores.
For each task report
status, actual unique-case count, passes, candidate failures, reference failures,
accuracy, and run ID. A preparation or static review claim is not a validation
result. No pipeline, candidate, reference program, or benchmark test suite was
executed by the agent during preparation.

## Comparison and scoring

Each test is a complete stdin string, encoded as UTF-8 without newline
translation and supplied unchanged to both programs. Successful stdout must
match exactly, including line endings and invalid UTF-8 bytes. Stderr is
only diagnostic. Launch failures, timeouts, and non-zero exits are unsuccessful.

Any unsuccessful reference execution makes the whole run
`status: invalid_reference`, `accuracy: null`, with non-zero CLI exit status.
Preserve all individual results and count reference failures separately. With
all references successful, accuracy is `n_pass / n_total`; candidate errors and
timeouts count as failures. `n_valid` counts successful references; `n_fail`
counts failures among those valid completed cases. `n_candidate_failures` and
`n_reference_failures` independently count unsuccessful executions, including
cases where both fail. The execution counts include a partially evaluated case;
`n_total`, `n_valid`, and comparison status counts describe completed pairs.
An unexpected execution or persistence exception produces `execution_failed`
with null accuracy, unless a reference failure already requires
`invalid_reference`. Previously saved cases and per-program records remain. A `completed` run does not imply all
candidate cases passed. Scores measure agreement on generated cases, not proven
behavioral equivalence.

## Artifacts and execution boundary

Each baseline run is saved under ignored `runs/<run-id>/`:

```text
specification.txt
task.json
candidate/
  metadata.json
  main.py or main.cpp
  program                # compiled C++ candidates only
  build-output/          # C++ compiler stdout.bin and stderr.bin
executions/
  000001/
    reference.json
    candidate.json
    reference/           # stdout.bin and stderr.bin
    candidate/           # stdout.bin and stderr.bin
build.json
tests.json
results.json
failures.json
summary.json
llm_log.jsonl
```

An early failure leaves only artifacts produced before that failure. Exact
stdin duplicates are removed; evaluated count may be smaller than 20.

On the supported POSIX host, each subprocess starts in its own session. The
harness kills its process group on timeout and cleans up remaining group members
when the parent exits. This does not contain descendants that deliberately escape
the group.

Process output is captured directly into retained binary files. Comparisons read
fixed-size byte chunks, and JSON persistence decodes chunks losslessly using UTF-8
`surrogateescape`. Output is not truncated or held in memory as a complete string;
disk usage remains proportional to the full output. The internal result mappings
contain file-backed output values and must use `pipeline.artifacts.write_json`.
Persisted JSON still contains ordinary complete stdout/stderr strings. Each
program record is saved as it completes; aggregate results and failures are
atomically replaced after each case. ASCII-escaped JSON preserves undecodable bytes. After loading
JSON, recover stdout using `stored_stdout.encode("utf-8", "surrogateescape")`.
No comparison value uses replacement decoding or whitespace normalization.

`llm_log.jsonl` retains prompts, configured model, schema/name, seed, temperature,
token limit, response/error, and latency. Its `inference` object identifies
`vllm_offline`, the resolved model path, Python/vLLM/PyTorch/Transformers/XGrammar
versions, engine and sampling settings, and visible CUDA devices. Missing-model
failures are recorded with a null resolved path. Partial/truncated completion
text remains available for diagnosis when generation parsing fails. Old run
records remain untouched; newly generated records have no endpoint field.
The `completion` object records `finish_reason`, `stop_reason`, and `usage`
(prompt, completion, and total token counts) when inference returns a completion;
it is null if inference fails before that information is available. An unavailable
prompt token count and its total are null rather than estimated. A finish reason
of `length` identifies a length-limited completion and fails the generation stage
with an explicit token-limit diagnostic after saving the raw response. The logical-call `status`
describes whether inference returned text; the run summary records later parsing,
build, or execution failures. Raw completion text is retained even if parsing fails.

Generated candidates receive a sanitized environment instead of parent secrets.
This is not a full OS sandbox: code still executes on the host. Keep source,
build diagnostics, tests, execution records, summaries, and inference records;
do not commit private configuration, environments, caches, or ordinary runs.
