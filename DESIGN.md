# One-shot baseline contract

This branch implements specification-driven black-box program replication:

```text
specification + input description
    -> one generated candidate
    -> Python materialization or C++20 compilation
    -> basic LLM stdin generation
    -> reference/candidate execution on identical stdin
    -> exact stdout comparison and persisted artifacts
```

Targets are deterministic command-line programs. Each test is a complete UTF-8
stdin string. Output semantics belong in the specification; there is no separate
output-format field. Only the specification and input description are supplied
to generation prompts. Reference commands remain harness-private.

Candidates use Python or C++20. The generated source is not modified after its
initial generation. Source, build diagnostics, test inputs, execution records,
failures, summaries, and inference records are retained under ignored `runs/`.

## Exact execution results

Capture stdout/stderr into retained binary files and compare them in bounded
byte chunks. Stream UTF-8 `surrogateescape` decoding into ASCII-escaped JSON,
preserving complete string values in persisted records without loading the full
output into memory. Internal result mappings use file-backed output values and
are serialized by `artifacts.write_json`. Save each program record immediately
and atomically update aggregate results after each case. Disk use is not capped.
On POSIX hosts, launch each subprocess in a new session and clean up its process
group on timeout or parent exit; this is not an OS sandbox. Stderr does not
affect output equality.

Launch failure, timeout, and non-zero exit make an execution unsuccessful.
Any unsuccessful reference execution invalidates the whole run, with
`status: invalid_reference` and no accuracy. Preserve every result and count
reference and candidate failures independently, including simultaneous failures.
Unexpected execution exceptions retain completed records and produce null accuracy;
a recorded reference failure still takes precedence as `invalid_reference`. If all references succeed, candidate failures
count against `n_pass / n_total`.

## Inference records

For each logical call, record prompts, model, resolved checkpoint path, offline
backend, Python/inference-library versions, engine/sampling settings, visible
CUDA devices, seed, temperature, token limit, response schema/name, response or
error, and latency. Record failures before re-raising them to the baseline's
stage handler. Preserve truncated response text for diagnosis. Keep credentials
out of records. There are no inference retries or alternate models.
When inference returns, record finish/stop reasons and actual prompt, completion,
and total token counts in `completion`. Unavailable counts are null. When no
completion is returned, this metadata is null. Logical-call success means text
was returned; subsequent JSON parsing failures belong to the stage/run summary. A length-limited
completion is preserved and rejected with an explicit token-limit diagnostic.

Inference uses one lazily initialized in-process vLLM engine and the local
checkpoint's chat template. `BTP_MODEL` names one directory under `~/models`;
reject remote identifiers, paths outside that root, and missing checkpoint files.
Set offline and telemetry-disable flags before importing inference libraries.
The checkpoint must already contain its configuration, tokenizer, and weights.
Engine initialization latency is included in the first logical call.
JSON-schema constraints are passed directly to the offline sampler with the
XGrammar backend explicitly selected and `disable_any_whitespace=True`. This
restricts structural whitespace while preserving string contents, including
complete stdin payloads. Record this decoding change as a different condition
from older runs with unrestricted structural whitespace. No completion repair
or regeneration is introduced. No HTTP
server or API credentials participate in inference.

## Scope and validation

Keep this branch limited to the one-shot implementation. Target HTTP/GUI
interfaces, stateful sessions, tracing, non-deterministic targets, specialized
test generation, additional languages, and deployment infrastructure are outside
this phase. In-process model inference is separate from the target program
interface. Preparing pinned dependencies and unchanged upstream references does
not constitute behavioural validation.

All validation is performed by the user using pipeline commands in `README.md`.
Agents may inspect code but must not run the pipeline or its target programs.
Implementation changes do not constitute empirical validation. Review material
research choices before changing the experiment's contract.

## Benchmark collection

Freeze the seven task specifications and reference provenance before inference.
Use neutral task identifiers. Keep accepted reference solutions, upstream tests,
and executable identities out of generation prompts. Each input starts a fresh
process; internal array updates or arithmetic variables do not create a shared
interactive session. Evaluate utilities and algorithmic programs as separate
groups. Retain every outcome, including 100% scores; these are preselected
challenge candidates rather than a set selected for observed baseline failures.
No upstream test suite is added to the basic LLM test-generation stage.
