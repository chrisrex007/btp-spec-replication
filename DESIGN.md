# Specification-replication contract

## Task boundary

Replicate the observable behaviour of a deterministic stdin/stdout program from
its natural-language specification and input-format description. Reference
commands remain private to the evaluator. Candidates may be Python or C++20.
There are no HTTP/GUI targets or stateful sessions, and no reference inspection.

Each case is a complete UTF-8 stdin string. Capture stdout/stderr as bytes and
decode with UTF-8 `surrogateescape` without newline translation. Successful
stdout equality is byte-exact; stderr never affects equality. ASCII-escaped JSON
preserves these values losslessly. Launch errors, timeouts and nonzero exits are
failures. Any reference failure invalidates task accuracy rather than scoring
it as candidate failure. Generated candidate environments exclude parent secrets;
full OS isolation is separate future work.

## Shared direct inference

`offline_runtime.py` resolves only local directories/cached snapshots, sets
offline flags before loading libraries, records model/runtime identity and owns
one lazy vLLM engine per invocation. Sampling uses `StructuredOutputsParams` JSON
schemas. No HTTP fallback, default model, downloads or remote custom code.
Both entrypoints use the same runtime options and default sampling parameters.
Requests include the actual schema, seed, prompts, temperatures and output limit.
Successes and failures are recorded with timing and available token counts.

Prompt tokens are counted after chat formatting and passed directly to vLLM.
Prompt length plus reserved output must fit the configured context. Full-feedback
overflow is terminal and preserves the request; it is never shortened.

## One-shot and abstract workflows

`pipeline.baseline` generates one candidate, builds it, generates/deduplicates
stdin, evaluates and persists results. It has no repair or resume contract.
`experiments/no-feedback` contains only this baseline and shared infrastructure.

This branch is `experiments/abstract-feedback`, based on raw checkpoint
`fc95a260ddfb2096e561dd9cb99c660b1597e5a7`. The raw branch remains an independent
snapshot; neither raw nor abstract empirical validation is claimed.
`pipeline.offline_batch` owns independent task state machines:

```text
initial request -> saved response -> parse/build candidate
                -> stdin request -> saved response -> fixed unique stdin set
                -> evaluate -> no failures / exhausted budget / invalid reference
                            -> all indexed raw failures
                            -> abstraction request -> saved response -> validate classes
                            -> classes + latest candidate
                            -> repair request -> saved response -> parse/build
                            -> evaluate against the same stdin set -> ...
```

The required repair budget counts replacements, excluding initial round zero.
All eligible failures retain input order. Their case IDs are zero-based positions
in the fixed deduplicated stdin set, not positions within the failures array.
Abstraction receives specification, input format and every current raw failure:
case ID, input, status, reference stdout and candidate stdout. It receives no
source, passing cases, diagnostics, private commands, task names or history.

The response contains only a nonempty `classes` array. Each class contains
`label`, `observed_behavior`, `expected_behavior` and `case_ids`. Parsing requires
nonblank descriptions and nonempty integer ID arrays. Validation rejects unknown
or repeated within-class IDs and requires complete failure coverage. Overlap and
singleton classes are allowed; there is no class cap. The prompt prohibits causal
hypotheses, repair advice, specification rewriting and unsupported generalization.
Mechanical validation checks evidence references, not semantic grounding; that
remains for user inspection, without another model judge.

Repair receives specification, input format, current candidate and validated
classes only. Evidence IDs are not resolved into examples. Repair schemas restrict
the language to the current candidate's language; parsing checks it again.
Malformed responses, language changes and build failures stop the task. There is
no rollback, best-candidate selection, diagnostic-based repair or implicit retry.
Both new abstraction stages use the same lazy model and shared sampling settings.
Abstraction preceding replacement i uses seed S + i, without changing repair seeds.

## Persistence and resume

`artifacts.py` provides lossless JSON, atomic publication and hashing;
`checkpoints.py` enforces schema-2 state and artifact integrity. Metadata freezes
source/prompts, runtime/model identity, ordered task snapshots, output path and
options, including `feedback_mode: abstract`. State records stage, attempted
iteration, last evaluated iteration and hashes for committed artifacts. Older
schemas and changed/missing artifacts are rejected without migration or overwrite.

Requests are committed before inference. Successful responses are committed
before state advances. An interrupted request stage can adopt its saved matching
response; a response stage can repeat parsing/materialization without inference.
Committed builds/evaluations are reused. Uncommitted work can be repeated on
explicit resume. No engine is initialized unless uncached inference remains.
Requests at different stages/rounds are grouped by schema and sampling settings,
including seed. Builds/evaluations may run across tasks in a thread pool.

`abstraction_request` and `abstraction_response` belong to evaluated source round r
and do not advance `attempted_iteration`. Only committing the following replacement
request advances it to r + 1. Budget zero, success, reference failure and exhausted
budget never enter abstraction. Under round r, `feedback.json` holds indexed raw
evidence and `abstraction.json` holds validated classes. Separate inference files
use step `failure_abstraction` and source round r. Tokens, timing, errors and model
provenance remain attributable to abstraction separately from repair. Repeated
batch wall times must not be summed across batch members.

Malformed abstraction JSON/structure stops that task with
`abstraction_parse_failed`; invalid references, duplicate IDs or incomplete coverage
use `abstraction_validation_failed`. Retain the response and an
`abstraction_error.json` artifact, return null final accuracy and preserve the last
evaluated score. Other tasks continue. Runtime errors instead preserve pending
requests for explicit resume; context overflow is terminal. There is no raw
fallback, chunking or automatic retry. Raw-branch checkpoints are incompatible,
even though both branches use schema 2.

Every produced round retains source, build and available evaluation artifacts.
Malformed replacements retain their raw responses. Failed repairs have null
final accuracy and a separate last-evaluated score; no earlier candidate is
silently presented as the final successful replacement. Reference failures have
null accuracy even when some cases passed. Root summaries expose per-task state
without inventing aggregate accuracy.

Checksums detect changed checkpoint contents; they do not authenticate against
an actor rewriting files and hashes together. Model metadata is hashed, while
large weights use snapshot/file-stat identity. Reference/model assets must remain
immutable. Diagnostic append-only logs are not checkpoint authorities.

## Scope and validation

Abstract implementation is prepared for user validation; no empirical success is
claimed. Agents inspect source/diffs only, without pipeline execution, model
loading, downloads, compilation or program execution. User commands, artifact
layout, stopping reasons, exit codes and later scenarios live in `README.md`.
No automated harness checks or bundled fixtures are included.

Comparison/pools and candidate tracing are deferred to their
reviewed phases in [the roadmap](docs/ROADMAP.md). Their removed WIP source remains
in history. The later four-arm comparison must freeze initial candidates, share
development/held-out pools, keep held-out results out of repair, and account for
abstraction/tracing overhead separately. Trace only candidates, never references;
normal uninstrumented execution remains the scoring source.
