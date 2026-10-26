# One-shot local-inference contract

The workflow is specification and stdin description -> one generated candidate
-> Python syntax validation or C++20 compilation -> basic stdin generation ->
execution of the unchanged candidate/reference -> exact stdout comparison.

Only the specification and stdin description are LLM-visible. The reference is
harness-private. There is no separate output-format field or intermediate rule
generation/specification rewriting.

One invocation owns one lazy vLLM engine and reuses it for both inference stages.
`BTP_MODEL` names one local checkpoint directory beneath `~/models`; arbitrary
paths and remote/cached identifiers are rejected. Configuration loads explicitly
when the invocation's session is created, with shell values taking precedence.
Dependency metadata and local files are resolved before engine construction.
Offline flags precede model-library imports. No HTTP transport, credentials,
automatic downloads, or remote model code are used. Structured responses use
`StructuredOutputsParams`. There is no process-global model engine.

Requests are appended to `llm_requests.jsonl` before model resolution or inference.
Terminal records in `llm_log.jsonl` share the request ID and retain schema,
sampling, model identity, runtime versions, token counts and latency, including
initialization on the first call. An initialization failure is recorded against
the pending request. Inference-return status is separate from subsequent response
parsing or token-limit failure; raw text remains available. Runtime defaults are
listed in README.

Source, build diagnostics, complete stdin cases, execution results, failures,
summaries and inference records are saved under ignored `runs/`. Output capture
is binary with reversible UTF-8 `surrogateescape` decoding and ASCII-escaped JSON.
No whitespace, newline, or invalid-byte normalization is allowed.

Any unsuccessful reference invalidates accuracy. With valid references, candidate
failures count against agreement. Syntax/compile failures terminate the run.
CLI completion, failure and interruption return 0, 2 and 130 respectively.
Post-setup failures use one summary-finalization path with a diagnostic stage.
Interruptions preserve completed results and available execution counts, with
null accuracy. A previously observed reference failure keeps `invalid_reference`
even on interruption; an additional interruption flag still selects exit 130.
If summary persistence fails, the CLI reports that error separately on stderr
and returns the available summary without claiming completed accuracy. Existing
artifacts and temporary files are retained; recovery never reruns inference or
program execution.

Validation is user-managed. Agents inspect source and diffs only; they do not run
the pipeline, load models, download assets, or execute generated/reference code.
Do not add automated harness checks or bundled example targets. This branch
contains only the one-shot workflow; other experimental phases are separate.
