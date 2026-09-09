import json
from datetime import datetime, timezone
from pathlib import Path


def log_call(run_dir: Path, step: str, target: str, iteration, model: str, seed,
             temperature, max_tokens, system_prompt: str, user_prompt: str,
             response: str, latency_s: float) -> None:
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "iteration": iteration,
        "step": step,
        "model": model,
        "seed": seed,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "response": response,
        "latency_s": latency_s,
    }
    log_path = Path(run_dir) / "llm_log.jsonl"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
