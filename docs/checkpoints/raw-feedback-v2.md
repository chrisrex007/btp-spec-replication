# Raw-feedback foundation checkpoint

Date: 2026-10-21. Source tag: `test-stop/raw-feedback-v2`.

Implemented raw strategy extraction, generic repair prompts, configuration and
checkpoint validation, source/prompt fingerprints, saved inference recovery,
reference-error accounting, context checks, token/latency provenance, and Slurm
scratch/allocation/resume safeguards. The one-task baseline remains independent.

Local validation: `python -m unittest discover -s tests -v` ran 42 tests:
41 passed, one GNU/Linux reference-oracle integration test explicitly skipped
on Windows. Slurm guard tests ran locally; no cluster commands were executed.

GPU-02 remains pending: actual model load/inference, context behavior, Slurm
signal delivery/resumption and artifact inspection require the user's allocation.
The original `test-stop/raw-feedback-v1` and historical branch remain unchanged.
