#!/usr/bin/env bash
# Submit with `sbatch --account=<your-account>` from your scratch directory.
# Set BTP_PROJECT_ROOT to the project checkout before submission.
# SBATCH command-line options may override the GPU/CPU/memory/time defaults.

#SBATCH --job-name=btp-offline
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:2
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=03:00:00
#SBATCH --signal=B:USR1@120
#SBATCH --output=btp-offline-%j.out

set -euo pipefail

fail() { echo "Configuration error: $*" >&2; exit 2; }

[[ -n "${SLURM_JOB_ID:-}" ]] || fail "Run inside a Slurm GPU batch allocation."
[[ -n "${SLURM_JOB_GPUS:-${SLURM_STEP_GPUS:-}}" ]] || fail "No Slurm GPU allocation detected."
SCRATCH_ROOT="${BTP_SCRATCH_ROOT:-${SCRATCH:-}}"
[[ "$SCRATCH_ROOT" == /* ]] || fail "Set SCRATCH or BTP_SCRATCH_ROOT to an absolute scratch directory."
SCRATCH_ROOT="$(realpath -e -- "$SCRATCH_ROOT")" || fail "Scratch directory does not exist."
[[ "$SCRATCH_ROOT" != / ]] || fail "Scratch root cannot be /."
[[ "${SLURM_SUBMIT_DIR:-}" == /* ]] || fail "SLURM_SUBMIT_DIR must be absolute."
SUBMIT_DIR="$(realpath -e -- "$SLURM_SUBMIT_DIR")" || fail "Submission directory does not exist."
[[ "$SUBMIT_DIR" == "$SCRATCH_ROOT" || "$SUBMIT_DIR" == "$SCRATCH_ROOT/"* ]] || fail "Submit only from scratch."
case "${BTP_RESUME:-0}" in
    0) RESUME_ARGS=() ;;
    1) RESUME_ARGS=(--resume) ;;
    *) fail "BTP_RESUME must be 0 or 1." ;;
esac
[[ -n "${BTP_EXPERIMENT_ID:-}" ]] || fail "Set BTP_EXPERIMENT_ID."

PROJECT_ROOT="${BTP_PROJECT_ROOT:-$SLURM_SUBMIT_DIR}"
RESULTS_ROOT="${BTP_RESULTS_ROOT:-$HOME/btp-results}"
[[ "$RESULTS_ROOT" == /* ]] || fail "BTP_RESULTS_ROOT must be absolute."
RESULTS_ROOT="$(realpath -m -- "$RESULTS_ROOT")"
[[ "$RESULTS_ROOT" != "$SCRATCH_ROOT" && "$RESULTS_ROOT" != "$SCRATCH_ROOT/"* ]] || fail "Store results on persistent home/project storage outside scratch."
VENV_PATH="${BTP_VENV_PATH:-$HOME/venvs/vllm-0.7.3}"

cd "$PROJECT_ROOT"
mkdir -p "$RESULTS_ROOT" "$SCRATCH_ROOT/huggingface"

module load apps/python/3.10.13/modulefile
source "$VENV_PATH/bin/activate"

export HF_HOME="$SCRATCH_ROOT/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export TRANSFORMERS_CACHE="$HF_HOME/transformers"
export HF_HUB_DISABLE_TELEMETRY=1

if [[ -z "${BTP_MODEL:-}" ]]; then
    BTP_MODEL="Qwen/Qwen2.5-7B-Instruct"
fi

echo "Project: $PROJECT_ROOT"
echo "Persistent results: $RESULTS_ROOT"
echo "Model cache: $HF_HOME"
echo "Slurm job: ${SLURM_JOB_ID:-unknown}"
echo "Node: $(hostname)"
nvidia-smi

# Replace the batch shell with Python so Slurm's pre-timeout USR1 signal reaches
# the runner, which finishes the current batch and checkpoints before exiting.
exec python -m pipeline.offline_batch \
    --manifest "${BTP_MANIFEST:-benchmarks/manifest.json}" \
    --experiment-id "${BTP_EXPERIMENT_ID:?Set BTP_EXPERIMENT_ID}" \
    --output-root "$RESULTS_ROOT" \
    --model "$BTP_MODEL" \
    --dtype "${BTP_DTYPE:-half}" \
    --tensor-parallel-size "${BTP_TENSOR_PARALLEL_SIZE:-2}" \
    --max-model-len "${BTP_MAX_MODEL_LEN:-8192}" \
    --gpu-memory-utilization "${BTP_GPU_MEMORY_UTILIZATION:-0.90}" \
    --max-num-seqs "${BTP_MAX_NUM_SEQS:-32}" \
    --workers "${BTP_WORKERS:-4}" \
    --tests "${BTP_TESTS:-20}" \
    --max-repair-iterations "${BTP_MAX_REPAIR_ITERATIONS:-2}" \
    --feedback-cases "${BTP_FEEDBACK_CASES:-12}" \
    --seed "${BTP_SEED:-42}" \
    "${RESUME_ARGS[@]}"
