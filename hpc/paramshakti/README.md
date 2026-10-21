# PARAM Shakti offline vLLM experiments

The cluster job runs the vLLM Python offline API (`LLM`, `SamplingParams`) in
the same process as the experiment runner. It does not start an HTTP server or
require an SSH tunnel. By default the selected Qwen2.5-7B-Instruct FP16 model
uses two V100 GPUs on one node. The model is loaded once per job and reused for
batched candidate generation, testcase generation, and repair.

All PARAM Shakti interaction must be performed by the user. Never share cluster
passwords, private keys, or tokens.

## Install vLLM once

On the login node, use the Python module verified for Python 3.10.13 and install
vLLM 0.7.3 in a home-directory virtual environment:

```bash
module load apps/python/3.10.13/modulefile
python3 --version
python3 -m venv "$HOME/venvs/vllm-0.7.3"
source "$HOME/venvs/vllm-0.7.3/bin/activate"
python -m pip install --upgrade pip
python -m pip install 'vllm==0.7.3'
python -c 'import torch, vllm; print("vLLM", vllm.__version__); print("PyTorch", torch.__version__, "CUDA", torch.version.cuda)'
deactivate
```

If package downloads are disallowed from the login node, ask cluster support
for the approved install method. Do not build vLLM from source on the login
node. The model cache is placed on scratch; experiment artifacts default to
`$HOME/btp-results` because scratch is not backed up and has a 30-day default
retention limit.

## Submit a multi-benchmark experiment

Ensure the project checkout is visible to the compute node. Set
`BTP_PROJECT_ROOT` to that checkout. Set `SCRATCH` (or `BTP_SCRATCH_ROOT`) to
the existing absolute scratch directory assigned to you; there is no guessed
account-specific default. Submit only from that directory or its descendants;
Slurm writes
its output file in the scratch submission directory:

```bash
export BTP_PROJECT_ROOT=/path/to/btp-spec-replication
export BTP_MODEL=Qwen/Qwen2.5-7B-Instruct
export BTP_EXPERIMENT_ID=pilot-qwen25-7b-20261020
mkdir -p "$SCRATCH/btp-submissions"
cd "$SCRATCH/btp-submissions"
sbatch --account="<your-account>" "$BTP_PROJECT_ROOT/hpc/paramshakti/run_offline_batch.sh"
```

The default manifest, `benchmarks/manifest.json`, includes the ten real-software
pilot benchmarks. Supply a different JSON manifest through `BTP_MANIFEST` or
override the job CLI if you want another task set. The manifest is an array of
task JSON paths, relative to the manifest file, or an object with a `tasks`
array.

Supply your account at submission time; account identifiers are not stored in
the script. Defaults are GPU partition, 2 GPUs on one node, 8 CPUs, 32 GB host
memory, and 3 hours. Override resource requests at submission time:

```bash
sbatch --account="<your-account>" --gres=gpu:2 --cpus-per-task=12 --mem=48G --time=06:00:00 "$BTP_PROJECT_ROOT/hpc/paramshakti/run_offline_batch.sh"
```

If changing the GPU count, keep it equal to `BTP_TENSOR_PARALLEL_SIZE` (default
2). For example, FP16 on the previously observed 16 GB V100 needs two GPUs.

The job script maps `BTP_TESTS`, `BTP_WORKERS`, `BTP_MAX_REPAIR_ITERATIONS`,
`BTP_FEEDBACK_CASES`, `BTP_SEED`, `BTP_MAX_MODEL_LEN`,
`BTP_GPU_MEMORY_UTILIZATION`, and `BTP_MAX_NUM_SEQS` to the Python runner.
`BTP_RESULTS_ROOT` can point to another
persistent home/project filesystem outside scratch. The script rejects results
under the configured scratch root. `BTP_SCRATCH_ROOT` controls the Hugging
Face cache location. The first run needs the public model files available in
the cache or a cluster-approved download route.

The runner batches prompts for all pending benchmark instances by stage.
Builds and differential evaluations run concurrently up to `BTP_WORKERS`.
Generated source, raw inference prompts/responses, tests, per-iteration results,
failures, state checkpoints, and experiment metadata are stored under:

```text
$HOME/btp-results/<experiment-id>/
```

To continue an interrupted experiment, resubmit the same experiment ID with
`BTP_RESUME=1`. Use `BTP_RESUME=0` (the default) for a fresh run; other values
are rejected. Before loading modules or initializing the model, the script
requires a Slurm job with allocated GPUs and checks the resolved submission
directory is inside the resolved scratch root. These checks cannot prevent an
incorrect submission from reaching Slurm: always `cd` to scratch **before**
running `sbatch`, and keep any `--output` override under scratch.
The runner validates a fingerprint of the task manifest and
inference configuration before reusing checkpoints. Slurm sends `USR1` two
minutes before the time limit; the runner finishes/persists the current batch
and exits so the same experiment can be resumed.

Inspect progress and logs with `squeue --me`, `sacct -j <job-id>`, and the
Slurm output file created in the submission directory. No endpoint or tunnel
is involved.
