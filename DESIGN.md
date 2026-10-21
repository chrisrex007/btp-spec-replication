# BTP Specification-Replication Framework — v1 Contract

## Goal

Given a natural-language specification and a black-box reference executable,
synthesize a replacement program whose observable stdin/stdout behaviour matches
the reference implementation. The offline runner now implements raw-feedback
repair; real GPU validation is deferred at the
[recorded testing stop](docs/checkpoints/raw-feedback-v1.md).

## v1 execution contract

- Every benchmark target is a deterministic command-line program.
- A test case is a complete string supplied to the program on standard input.
- Programs return their observable answer on standard output.
- Standard error is captured for diagnostics but is not part of output equality.
- A run is unsuccessful if it cannot be launched, times out, or exits non-zero.
- For successful runs, v1 uses exact stdout equality. More flexible comparators
  are intentionally deferred.

## Candidate programs

- Candidate source code is represented independently of how it is built or run.
- v1 supports Python and C++ candidates.
- The generator may choose either supported language.
- Python candidates are executed with the current Python interpreter.
- C++ candidates are compiled with a C++20 compiler before execution.

## Implemented baseline workflow

Phases 0–5 implement the no-feedback baseline:

1. Load a natural-language specification and input-format description.
2. Ask the configured LLM for one structured Python or C++ candidate.
3. Build/materialize the candidate.
4. Ask the LLM for complete stdin testcases.
5. Run every testcase against both the black-box reference and candidate.
6. Compare stdout exactly and persist results, failures, logs, and baseline score.

No black-box failures are shown back to the LLM in this baseline.

## Feedback workflow and continued development

The offline batch runner repairs the current candidate using raw differential
failures and reuses its development tests across iterations. It checkpoints
inference responses and experiment stages, and uses one in-process vLLM model.
This implemented path is awaiting actual GPU validation.

The intended research comparison uses:

- raw feedback: input + reference output + candidate output, or
- abstract feedback: an LLM-generated summary of failure patterns.

The no-feedback baseline is the third condition. Abstract feedback, paired arm
orchestration, reusable development/held-out pools, and final reporting remain
to implement. The [roadmap](docs/ROADMAP.md) groups them into three continuation
branches with separate deferred GPU acceptance checkpoints. Its material
research choices remain subject to phase review.

## Explicitly out of scope for v1

- HTTP/API interaction
- GUI interaction
- Stateful sessions
- Execution-trace/path feedback
- Advanced test-generation strategies
- Non-deterministic targets
- Languages other than Python and C++
