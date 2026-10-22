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

Capture stdout/stderr in binary mode and decode with UTF-8 `surrogateescape`.
This keeps the existing string interface while preserving all original bytes.
Compare stdout without newline normalization or replacement decoding. Persist
process output in ASCII-escaped JSON so it remains recoverable. Stderr does not
affect output equality.

Launch failure, timeout, and non-zero exit make an execution unsuccessful.
Any unsuccessful reference execution invalidates the whole run, with
`status: invalid_reference` and no accuracy. Preserve every result and count
reference failures separately. If all references succeed, candidate failures
count against `n_pass / n_total`.

## Inference records

For each logical call, record prompts, model, sanitized endpoint, seed,
temperature, token limit, response schema/name, response or error, and latency.
Record failures before re-raising them to the baseline's stage handler. Keep
credentials out of records. Client retries contribute to the logical call's
latency; they are not separate inference records.

## Scope and validation

Keep this branch limited to the one-shot implementation. Target HTTP/GUI
interfaces, stateful sessions, tracing, non-deterministic targets, specialized
test generation, additional languages, and deployment infrastructure are outside
this phase. Model API access is separate from the target program interface.

All validation is performed by the user using pipeline commands in `README.md`.
Agents may inspect code but must not run the pipeline or its target programs.
Implementation changes do not constitute empirical validation. Review material
research choices before changing the experiment's contract.
