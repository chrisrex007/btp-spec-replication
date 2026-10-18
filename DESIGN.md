# BTP Specification-Replication Framework — v1 Contract

## Goal

Given a natural-language specification and a black-box reference executable,
synthesize and iteratively improve a replacement program whose observable
stdin/stdout behaviour matches the reference implementation.

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
- The future generator may choose either supported language.
- Python candidates are executed with the current Python interpreter.
- C++ candidates are compiled with a C++20 compiler before execution.

## Planned LLM workflow

The LLM stages are intentionally not implemented in Phases 0–2. The intended
flow is:

1. Generate an initial candidate from the natural-language specification.
2. Generate stdin test cases from the specification/input-format description.
3. Run each test against both the black box and candidate.
4. Compare outputs and collect failures.
5. Repair the current candidate using either:
   - raw feedback: input + reference output + candidate output, or
   - abstract feedback: an LLM-generated summary of failure patterns.

## Explicitly out of scope for v1

- HTTP/API interaction
- GUI interaction
- Stateful sessions
- Execution-trace/path feedback
- Advanced test-generation strategies
- Non-deterministic targets
- Languages other than Python and C++
