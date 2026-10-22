# BTP Spec Replication — no-feedback baseline

This branch synthesizes one Python or C++20 program from a natural-language
specification, generates stdin tests, compares the candidate with a black-box
reference, and saves the results. The generated candidate stays unchanged
throughout evaluation.

Validation belongs to the user. Agents must not run the pipeline or execute
candidate/reference programs. The commands below are for you to run.

## Requirements and configuration

- Python 3.10+.
- An OpenAI-compatible chat-completions endpoint with structured-output support.
- `g++` with C++20 support when a generated candidate uses C++.

Create or edit repository-root `.env` privately, using `.env.example` as a format
reference. Preserve existing settings if you already have a `.env` file.

```dotenv
BTP_MODEL=your-model-name
BTP_LLM_ENDPOINT=http://127.0.0.1:8000/v1/chat/completions
BTP_LLM_API_KEY=
```

Use one `KEY=VALUE` entry per line. Blank lines, `#` comments, and matching quotes
around values are supported. Existing shell environment values take precedence.
The API key is optional for endpoints without authentication. Optional
`BTP_HTTP_REFERER` and `BTP_X_TITLE` configure attribution headers. Never commit or
print your private `.env` values.

## Task configuration

Create a task JSON next to its specification and reference program:

```json
{
  "name": "example",
  "specification": "spec.md",
  "reference": {
    "command": ["python3", "blackbox.py"],
    "cwd": "."
  },
  "input_format": "One integer x followed by a newline.",
  "timeout_seconds": 2.0
}
```

Paths are resolved relative to the task JSON. Use a reference command available
on your machine; for example, replace `python3` if your interpreter has a different
name. The LLM receives the specification and input description. All required
output behaviour must be in the specification. The reference command is private
to the harness and is never included in generation prompts.

## Commands for user-run validation

Supply your own task JSON, specification, and black-box reference executable.
After privately configuring your endpoint, replace `path/to/task.json` below
with your actual task path and run the command yourself from the repository root:

```bash
python -m pipeline.baseline path/to/task.json --tests 10 --seed 42
```

The pipeline command makes model calls and executes the reference and candidate.

## Comparison and scoring

Each complete stdin string is encoded as UTF-8 and supplied unchanged to both
programs. Successful outputs must match exactly, including line endings and
invalid UTF-8 bytes. Stderr is diagnostic only. Launch failures, timeouts, and
non-zero exits are unsuccessful executions.

If any reference execution is unsuccessful, the run has
`status: invalid_reference`, `accuracy: null`, and a non-zero CLI exit status.
All results remain available for diagnosis. No partial accuracy is reported.

With all references successful, accuracy is `n_pass / n_total`. Candidate errors
and timeouts count as failures. `n_reference_failures` counts unsuccessful
reference executions, `n_valid` counts successful reference executions, and
`n_fail` counts failures among those valid cases. A `completed` run means evaluation
finished with valid references; it does not imply all candidates passed.

## Run artifacts

Each run is saved under ignored `runs/<run-id>/`:

```text
specification.txt
task.json
candidate/
  metadata.json
  main.py or main.cpp
  program or program.exe  # compiled C++ candidates only
build.json
tests.json
results.json
failures.json
summary.json
llm_log.jsonl
```

An early failure can leave only the artifacts produced before that failure.
`summary.json` records candidate-generation, build, test-generation, or reference
failure status. `tests.json` contains the deduplicated inputs actually evaluated;
their count can be smaller than the requested count.

Process output is captured as bytes and decoded losslessly with UTF-8
`surrogateescape`. JSON escapes preserve both Unicode and undecodable bytes.
After loading a result with Python's `json` module, recover the original stdout
with `stored_stdout.encode("utf-8", "surrogateescape")`.

`llm_log.jsonl` records each logical inference call, including failed calls. It
stores prompts, model, sanitized endpoint, seed, temperature, token limit,
response schema/name, response or error, and total latency. Endpoint credentials,
query parameters, and fragments are omitted; authentication headers are not
logged. Client retries remain inside the logical call and its total latency.

## Execution boundary

Generated candidates receive a sanitized environment instead of parent secrets.
This is not a full sandbox: code still runs on the host. Use your own task
references and report actual validation results separately from implementation.
