"""Runs inside a target's own venv (so the real black-box package is importable).
Compares generated code's output against the oracle's output on a shared input set.
"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sandbox

# Cap this process before any generated code is imported or run. Without this a
# runaway implementation takes the host down instead of failing one test case.
sandbox.apply_limits()

target_config_path, iter_dir = sys.argv[1], sys.argv[2]

with open(target_config_path) as f:
    target = json.load(f)

exec(target["oracle_import"], globals())
oracle_fn = eval(target["oracle_call"])

with open(f"{iter_dir}/test_inputs.json", encoding="utf-8") as f:
    inputs = json.load(f)

spec = importlib.util.spec_from_file_location("gen_code", f"{iter_dir}/gen_code.py")
gen_code = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_code)
gen_fn = getattr(gen_code, target["gen_func_name"])

results = []
n_pass = 0
for i, text in enumerate(inputs):
    # The oracle is trusted code, but it is still guarded: a planted or genuine
    # defect in it should fail one case, not the run.
    ok_oracle, expected, oracle_error = sandbox.call_guarded(oracle_fn, text)
    if not ok_oracle:
        results.append({
            "index": i, "input": text, "expected_oracle_output": None,
            "actual_generated_output": None,
            "error": f"oracle failed: {oracle_error}", "passed": False,
        })
        continue
    ok, actual, error = sandbox.call_guarded(gen_fn, text)
    passed = ok and (actual == expected)
    n_pass += passed
    results.append({
        "index": i,
        "input": text,
        "expected_oracle_output": expected,
        "actual_generated_output": actual,
        "error": error,
        "passed": passed,
    })

with open(f"{iter_dir}/results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(json.dumps({"n_pass": n_pass, "n_total": len(inputs)}))
