"""Command-line entry point for frozen pools and paired offline experiments."""
import argparse
import json
import math
import os
from pathlib import Path
import signal

from .comparison import ComparisonConfig, run_comparison
from .offline_batch import _load_tasks
from .offline_runtime import OfflineVLLM
from .pools import generate_pool


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pool = commands.add_parser("pool", help="Generate and freeze disjoint testcase pools")
    pool.add_argument("--output-root", required=True, type=Path)
    pool.add_argument("--development-count", required=True, type=int)
    pool.add_argument("--held-out-count", required=True, type=int)
    pool.add_argument("--pool-seed", required=True, type=int)
    pool.add_argument("--batch-size", default=20, type=int)
    pool.add_argument("--max-batches", default=50, type=int)
    run = commands.add_parser("run", help="Run paired arms on development inputs")
    run.add_argument("--pool-root", required=True, type=Path)
    run.add_argument("--output-dir", required=True, type=Path)
    run.add_argument("--seeds", required=True, nargs="+", type=int)
    run.add_argument("--arms", nargs="+", choices=("baseline", "raw"), default=["baseline", "raw"])
    run.add_argument("--max-repair-iterations", default=2, type=int)
    run.add_argument("--feedback-cases", default=12, type=int)
    run.add_argument("--max-tokens", default=4096, type=int)
    run.add_argument("--temperature", default=0.2, type=float)
    for command in (pool, run):
        source = command.add_mutually_exclusive_group(required=True)
        source.add_argument("--tasks", nargs="+")
        source.add_argument("--manifest")
        command.add_argument("--resume", action="store_true")
        command.add_argument("--model", default=os.getenv("BTP_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
        command.add_argument("--dtype", default=os.getenv("BTP_DTYPE", "half"))
        command.add_argument("--tensor-parallel-size", type=int, default=int(os.getenv("BTP_TENSOR_PARALLEL_SIZE", "2")))
        command.add_argument("--max-model-len", type=int, default=int(os.getenv("BTP_MAX_MODEL_LEN", "8192")))
        command.add_argument("--gpu-memory-utilization", type=float, default=float(os.getenv("BTP_GPU_MEMORY_UTILIZATION", "0.90")))
        command.add_argument("--max-num-seqs", type=int, default=int(os.getenv("BTP_MAX_NUM_SEQS", "32")))
    return parser


class _LazyRuntime:
    def __init__(self, factory):
        self.factory = factory
        self.instance = None

    def generate_batch(self, requests):
        if self.instance is None:
            self.instance = self.factory()
        return self.instance.generate_batch(requests)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if (not args.model or min(args.tensor_parallel_size, args.max_model_len, args.max_num_seqs) <= 0
            or not math.isfinite(args.gpu_memory_utilization)
            or not 0 < args.gpu_memory_utilization <= 1):
        parser.error("Invalid model/runtime configuration")
    tasks = _load_tasks(args)
    if not tasks or len({task.name for task in tasks}) != len(tasks):
        parser.error("Tasks must have unique names")
    factory = lambda: OfflineVLLM(
        model=args.model, dtype=args.dtype, tensor_parallel_size=args.tensor_parallel_size,
        max_model_len=args.max_model_len, gpu_memory_utilization=args.gpu_memory_utilization,
        max_num_seqs=args.max_num_seqs)
    stopped = False
    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True
    previous = None
    if hasattr(signal, "SIGUSR1"):
        previous = signal.signal(signal.SIGUSR1, stop)
    try:
        if args.command == "pool":
            if min(args.development_count, args.held_out_count, args.batch_size, args.max_batches) <= 0 or args.pool_seed < 0:
                parser.error("Pool counts and batch limits must be positive; seed must be nonnegative")
            runtime = _LazyRuntime(factory)
            summaries = {}
            for task in tasks:
                if stopped:
                    break
                summaries[task.name] = generate_pool(
                    task, args.output_root / task.name, runtime, args.model,
                    args.development_count, args.held_out_count, args.pool_seed,
                    batch_size=args.batch_size, max_batches=args.max_batches, resume=args.resume)
            summary = {"status": "interrupted" if stopped else "completed", "pools": summaries}
        else:
            config = ComparisonConfig(model=args.model, seeds=tuple(args.seeds), arms=tuple(args.arms),
                                      max_repair_iterations=args.max_repair_iterations,
                                      feedback_cases=args.feedback_cases, max_tokens=args.max_tokens,
                                      temperature=args.temperature)
            config.validate()
            summary = run_comparison(tasks, {task.name: args.pool_root / task.name for task in tasks},
                                     args.output_dir, config=config, runtime_factory=factory,
                                     resume=args.resume, should_stop=lambda: stopped)
        print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["status"] in {"completed", "interrupted"} else 2
    finally:
        if previous is not None:
            signal.signal(signal.SIGUSR1, previous)


if __name__ == "__main__":
    raise SystemExit(main())
