# GPU testing stop: offline raw-feedback runner

Recorded: 2026-10-21. Status: **GPU validation deferred**.

The local Git tag `test-stop/raw-feedback-v1` identifies the source checkpoint.
It preserves the implementation on `experiments/real-software-v1` before
development continues on `experiments/comparison-foundation`. A checkpoint
records code available for testing; it does not certify experimental success.

## Architecture at this checkpoint

```text
specification + input format
    -> initial candidate generation
    -> Python materialization / C++20 build
    -> basic LLM stdin generation
    -> reference/candidate differential execution (exact stdout)
    -> baseline artifacts
    -> raw failures + current candidate -> direct repair
    -> rebuild and evaluate on the same development cases
    -> stop at success or configured repair limit

one Slurm GPU job
    -> one in-process vLLM instance shared across task batches
    -> inference response and stage checkpoints
    -> persistent experiment output and resume
```

The independent `pipeline.baseline` path remains the no-feedback reference.
The batch runner includes a ten-task manifest, raw-feedback prompts, bounded
parallel builds/evaluations, and checkpoint/resume support. Abstract feedback,
paired experimental arms, separate held-out evaluation, and consolidated
comparison reports are still absent.

## Validation evidence

- Historical Codespaces evidence in `AGENTS.md`: 26 unit tests passed and the
  `double` baseline passed 10/10 differential cases. This predates the offline
  runner and does not validate it.
- Local Windows/Python 3.12.5 run on 2026-10-21:
  `python -m unittest discover -s tests -v` ran 31 test methods. Thirty passed,
  including both offline-batch tests and the fake-vLLM runtime test. The real
  oracle smoke-test method failed four subcases: numeric sort, JSON compacting,
  case-insensitive unique sort, and base64 decoding. Observed issues included
  Windows `sort` being selected, the `python3` Store alias, and a base64 invalid
  input error. Linux reference-oracle validation remains pending; this is not a
  green full-suite result. The initial sandboxed attempt also had temporary-file
  and process permission errors; the reported results are from the permitted
  rerun outside that sandbox.
- A real vLLM model load, multi-GPU inference, cluster interruption/resumption,
  and real-software pilot results remain **pending**.
- Fake-runtime tests exercise orchestration, not actual GPU compatibility or
  the effectiveness of repair. No target has been removed on this evidence.

## Deferred GPU acceptance checklist (GPU-01)

Use the [PARAM Shakti guide](../../hpc/paramshakti/README.md). All cluster
commands are run by the user. Preserve this tag and test it in a separate
checkout when access returns; continuing development does not require waiting.

1. Inspect the user's live allocation, GPU model/VRAM, modules, account limits,
   Python, PyTorch, and vLLM versions. Check compiler/reference executables.
2. Submit from scratch with Slurm output under scratch, model caches under
   scratch, and experiment results under persistent home/project storage.
3. Load the configured FP16 model once inside the GPU job. Confirm batched
   candidate generation and testcase generation return parseable responses.
4. Exercise a small raw-repair run. Verify candidate builds, exact comparisons,
   failure feedback, per-iteration sources/results, and complete inference logs.
   A naturally perfect candidate may not exercise repair; record that limitation.
5. Interrupt a separate development run and resume its unchanged experiment ID
   and configuration. Verify persisted responses are reused, completed work is
   retained, and changed configurations are rejected.
6. Run the ten-target development pilot. Apply the existing perfect-baseline
   filtering policy using development results only. Do not interpret this
   checkpoint's scores as held-out results or a raw-vs-abstract comparison.
7. Record the Git revision, environment, commands, Slurm logs, artifact paths,
   failures, and observed results in persistent storage. Mark this checklist
   passed only after the actual run; document fixes with their own revisions.

## Items to resolve during continued development

- Separate feedback/development cases from held-out scoring, freeze reusable
  pools, and share the initial candidate across comparison arms.
- Specify which execution failures may become repair feedback; reference
  failures currently appear in the general failure list.
- Strengthen resume provenance to include prompt/code/configuration versions.
- Validate prompt-plus-output context budgets for repairs against the configured
  8192-token context before making large testcase requests.
- Harden scratch submission checks and exercise Slurm signal delivery on the
  actual cluster. A checkpoint after inference does not guarantee recovery of
  an inference call killed before its response was saved.

These are recorded follow-up tasks, not claims that this snapshot already
implements the final experimental protocol. See [the roadmap](../ROADMAP.md).
