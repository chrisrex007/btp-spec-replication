"""Automated spec -> code -> oracle-test -> abstract-triage -> spec-refine loop.

Usage: python3 loop.py targets/<name>.json --iterations 3 --new-inputs 15
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import llm_client
import llm_log

PIPELINE_DIR = Path(__file__).parent


def logged_call(run_dir: Path, step: str, target: str, iteration, system: str, user: str,
                 temperature: float = 0.2, max_tokens: int = 4096, seed: int = 42,
                 json_schema: dict = None, schema_name: str = "response") -> str:
    start = time.monotonic()
    response = llm_client.call(system, user, temperature=temperature, max_tokens=max_tokens,
                                seed=seed, json_schema=json_schema, schema_name=schema_name)
    latency_s = time.monotonic() - start
    llm_log.log_call(
        run_dir=run_dir, step=step, target=target, iteration=iteration,
        model=llm_client.MODEL, seed=seed, temperature=temperature, max_tokens=max_tokens,
        system_prompt=system, user_prompt=user, response=response, latency_s=latency_s,
    )
    return response


def read(path):
    return Path(path).read_text(encoding="utf-8")


def write(path, content):
    Path(path).write_text(content, encoding="utf-8")


def extract_code_block(raw: str) -> str:
    m = re.search(r"```python\n(.*?)```", raw, re.DOTALL)
    return m.group(1) if m else raw


def extract_json_array(raw: str) -> list:
    """Parse a JSON array of strings, salvaging a truncated one.

    testgen on mojibake-heavy targets can degenerate into an unbounded repeating
    escape sequence ('\\xc3\\x82\\xc2\\x83...') that consumes the whole token
    budget, so the array never closes. Failing outright there discards every
    good input generated before the runaway string, which previously left the
    loop with zero test inputs.
    """
    fixed = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: "\\u00" + m.group(1), raw)
    start = fixed.find("[")
    if start == -1:
        raise ValueError("no JSON array found in response")
    end = fixed.rfind("]")
    if end > start:
        try:
            return json.loads(fixed[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Salvage: walk complete elements off the front, stop at the first
    # incomplete one rather than losing the whole array.
    decoder = json.JSONDecoder()
    items, pos = [], start + 1
    while pos < len(fixed):
        while pos < len(fixed) and fixed[pos] in ", \n\r\t":
            pos += 1
        if pos >= len(fixed) or fixed[pos] == "]":
            break
        try:
            value, pos = decoder.raw_decode(fixed, pos)
        except json.JSONDecodeError:
            break
        items.append(value)
    if not items:
        raise ValueError("no complete elements could be salvaged from response")
    return items


def drop_unencodable(items: list) -> list:
    """Discard items containing lone surrogates.

    testgen on mojibake targets emits literal \\udc9c-style escapes; JSON accepts
    them but UTF-8 cannot encode the resulting str, so persisting the input set
    dies mid-iteration. They are artifacts of the generator, not spec-relevant
    inputs, so the boundary is the right place to reject them.
    """
    kept = []
    for it in items:
        try:
            if isinstance(it, str):
                it.encode("utf-8")
            kept.append(it)
        except UnicodeEncodeError:
            pass
    return kept


def slugify_heading(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def extract_clauses(spec_text: str) -> list:
    """Derive spec_clause_id values from a spec's own numbered-list structure,
    qualified by the enclosing '## Heading' so ids stay unique across sections
    that each restart numbering at 1 (e.g. 'Scope of repairs' vs 'Additional
    Requirements' both having a '1.'). Returns [{id, heading, text}, ...].

    A clause runs from its '1.' marker until the next numbered item, the next
    heading, or the next unindented line — so wrapped prose and nested
    sub-bullets stay part of the clause. Truncating to the marker line alone
    silently drops most of a clause's content, and a clause that gets reflowed
    into sub-bullets by spec refinement loses all of it.
    """
    if os.environ.get("BTP_LEGACY_CLAUSE_PARSER"):
        # Ablation control: the pre-2026-09-03 behaviour, which kept only a
        # clause's marker line and silently discarded wrapped prose and nested
        # sub-bullets. Kept so the fix can be measured against it rather than
        # asserted -- setting this reproduces the 93% -> 21% slugify collapse.
        legacy = []
        heading = "spec"
        for line in spec_text.splitlines():
            heading_match = re.match(r"^##\s+(.+)$", line)
            if heading_match:
                heading = slugify_heading(heading_match.group(1))
                continue
            item_match = re.match(r"^(\d+)\.\s+(.*)$", line)
            if item_match:
                legacy.append({
                    "id": f"{heading}-{item_match.group(1)}",
                    "heading": heading,
                    "text": item_match.group(2).strip(),
                })
        return legacy

    clauses = []
    current_heading = "spec"
    current = None

    def flush():
        nonlocal current
        if current is not None:
            current["text"] = "\n".join(current.pop("lines")).strip()
            clauses.append(current)
            current = None

    for line in spec_text.splitlines():
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            flush()
            current_heading = slugify_heading(heading_match.group(1))
            continue
        item_match = re.match(r"^(\d+)\.\s+(.*)$", line)
        if item_match:
            flush()
            current = {
                "id": f"{current_heading}-{item_match.group(1)}",
                "heading": current_heading,
                "lines": [item_match.group(2).strip()],
            }
            continue
        if current is not None:
            if not line.strip():
                current["lines"].append("")
            elif line.startswith((" ", "\t")):
                current["lines"].append(line.strip())
            else:
                flush()
    flush()
    return clauses


def rulegen(spec_text: str, run_dir: Path, target: str, iteration, temperature: float = 0.2, seed: int = 42) -> list:
    clauses = extract_clauses(spec_text)
    clause_ids = [c["id"] for c in clauses]
    system = read(PIPELINE_DIR / "prompts/rulegen_system.txt")
    clause_listing = "\n".join(f"- `{c['id']}` ({c['heading']}): {c['text']}" for c in clauses)
    user = (
        "## Specification\n\n" + spec_text +
        "\n\n## Valid spec_clause_id values (use exactly one of these per rule)\n\n" + clause_listing +
        "\n\nDecompose this specification into an explicit list of atomic, testable rules."
    )
    schema = {
        "type": "object",
        "properties": {
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "rule_id": {"type": "string"},
                        "statement": {"type": "string"},
                        "spec_clause_id": {"type": "string", "enum": clause_ids},
                    },
                    "required": ["rule_id", "statement", "spec_clause_id"],
                },
            },
        },
        "required": ["rules"],
    }
    raw = logged_call(run_dir, "rulegen", target, iteration, system, user,
                       temperature=temperature, seed=seed, json_schema=schema, schema_name="rule_list")
    return json.loads(raw)["rules"]


def extract_interface(spec_text: str) -> str:
    """Pull the '## Interface' code block out of the spec so the required function
    signature survives even though it isn't a numbered rule clause."""
    m = re.search(r"##\s*Interface\s*\n+```python\n(.*?)```", spec_text, re.DOTALL)
    return m.group(1).strip() if m else ""


def codegen(rules: list, interface: str, run_dir: Path, target: str, iteration) -> str:
    system = read(PIPELINE_DIR / "prompts/codegen_system.txt")
    rule_listing = "\n".join(f"- [{r['rule_id']}] ({r['spec_clause_id']}) {r['statement']}" for r in rules)
    interface_block = f"\n\nRequired interface (match this exactly):\n\n```python\n{interface}\n```" if interface else ""
    user = (
        "Implement the following list of rules as a self-contained Python module.\n"
        "Use only the Python standard library (no third-party packages).\n"
        "Every rule below must be reflected in the implementation."
        + interface_block +
        "\n\nRules:\n\n" + rule_listing
    )
    raw = logged_call(run_dir, "codegen", target, iteration, system, user)
    return extract_code_block(raw)


def testgen(spec_text: str, domain_description: str, n: int, run_dir: Path, target: str, iteration) -> list:
    system = read(PIPELINE_DIR / "prompts/testgen_system.txt")
    user = (
        f"Generate {n} diverse test input strings for black-box testing of "
        f"{domain_description}, per this spec:\n\n{spec_text}\n\n"
        f"Cover a wide range of edge cases implied by the spec: typical valid "
        f"inputs, boundary cases, already-normalized inputs that should pass "
        f"through with minimal change, and adversarial/unusual inputs that "
        f"probe corners of the spec.\n"
        f"Output a JSON array of exactly {n} strings, and nothing else."
    )
    raw = logged_call(run_dir, "testgen", target, iteration, system, user, temperature=0.6,
                       max_tokens=12000)
    return drop_unencodable(extract_json_array(raw))


def abstract_failures(spec_text: str, failing_cases: list, run_dir: Path, target: str, iteration) -> str:
    system = read(PIPELINE_DIR / "prompts/abstraction_system.txt")
    user = (
        "## Current specification\n\n" + spec_text +
        "\n\n## Failing cases (input / expected oracle output / actual output / error)\n\n" +
        json.dumps(failing_cases, ensure_ascii=False, indent=2)
    )
    return logged_call(run_dir, "abstraction", target, iteration, system, user, temperature=0.2)


def triage(spec_text: str, failing_cases: list, run_dir: Path, target: str, iteration) -> list:
    system = read(PIPELINE_DIR / "prompts/triage_system.txt")
    indexed = [{"failure_index": i, **c} for i, c in enumerate(failing_cases)]
    user = (
        "## Current specification\n\n" + spec_text +
        "\n\n## Failing cases\n\n" + json.dumps(indexed, ensure_ascii=False, indent=2)
    )
    schema = {
        "type": "object",
        "properties": {
            "triage": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "failure_index": {"type": "integer"},
                        "category": {"type": "string", "enum": ["model_wrong", "spec_ambiguous", "executable_diverges"]},
                        "rationale": {"type": "string"},
                    },
                    "required": ["failure_index", "category", "rationale"],
                },
            },
        },
        "required": ["triage"],
    }
    raw = logged_call(run_dir, "triage", target, iteration, system, user,
                       json_schema=schema, schema_name="triage")
    return json.loads(raw)["triage"]


def leak_check(abstraction_text: str, failing_cases: list, min_len: int = 8) -> list:
    """Returns list of literal substrings from failing cases that leaked verbatim
    into the abstraction text — structural enforcement of the no-examples rule."""
    leaks = []
    for case in failing_cases:
        for field in ("input", "expected_oracle_output", "actual_generated_output"):
            val = case.get(field)
            if not isinstance(val, str) or len(val) < min_len:
                continue
            for i in range(0, len(val) - min_len + 1, min_len):
                chunk = val[i:i + min_len]
                if chunk.strip() and chunk in abstraction_text:
                    leaks.append(chunk)
    return leaks


def specrefine(spec_text: str, abstraction_text: str, run_dir: Path, target: str, iteration) -> str:
    system = read(PIPELINE_DIR / "prompts/specrefine_system.txt")
    user = (
        "## Current specification\n\n" + spec_text +
        "\n\n## Abstract failure classes from black-box testing\n\n" + abstraction_text
    )
    return logged_call(run_dir, "specrefine", target, iteration, system, user, temperature=0.2)


def run_iteration(target: dict, run_dir: Path, iteration: int, spec_text: str,
                   cumulative_inputs: list, n_new_inputs: int, target_config_path: Path):
    iter_dir = run_dir / f"iter{iteration}"
    iter_dir.mkdir(parents=True, exist_ok=True)
    write(iter_dir / "spec.md", spec_text)

    print(f"[{target['name']}][iter{iteration}] rulegen...")
    rules = rulegen(spec_text, run_dir, target["name"], iteration)
    write(iter_dir / "rules.json", json.dumps(rules, ensure_ascii=False, indent=2))

    print(f"[{target['name']}][iter{iteration}] codegen ({len(rules)} rules)...")
    interface = extract_interface(spec_text)
    code = codegen(rules, interface, run_dir, target["name"], iteration)
    write(iter_dir / "gen_code.py", code)

    print(f"[{target['name']}][iter{iteration}] testgen ({n_new_inputs} new inputs)...")
    new_inputs = []
    for attempt_n in (n_new_inputs, max(5, n_new_inputs // 2)):
        try:
            new_inputs = testgen(spec_text, target["domain_description"], attempt_n, run_dir, target["name"], iteration)
            break
        except Exception as e:
            print(f"  testgen parse failed ({e}), retrying with {max(5, n_new_inputs // 2)} inputs" if attempt_n == n_new_inputs
                  else f"  testgen parse failed again ({e}), continuing this iteration with no new inputs from testgen")

    for x in new_inputs:
        if x not in cumulative_inputs:
            cumulative_inputs.append(x)
    write(iter_dir / "test_inputs.json", json.dumps(cumulative_inputs, ensure_ascii=False, indent=2))

    if not cumulative_inputs:
        # Without this the loop tests nothing, sees no failures, and takes its
        # "no failures -> converged" branch: a null run that reports success.
        raise RuntimeError(
            f"{target['name']} iter{iteration}: no test inputs available. "
            "testgen produced none and none carried over -- refusing to continue, "
            "because an empty test set is indistinguishable from convergence.")

    print(f"[{target['name']}][iter{iteration}] running against oracle "
          f"({len(cumulative_inputs)} cumulative inputs)...")
    proc = subprocess.run(
        [target["venv_python"], str(PIPELINE_DIR / "compare_runner.py"),
         str(target_config_path), str(iter_dir)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stderr)
        raise RuntimeError(f"compare_runner failed for {target['name']} iter{iteration}")
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    print(f"[{target['name']}][iter{iteration}] {summary['n_pass']}/{summary['n_total']} passed")

    results = json.loads((iter_dir / "results.json").read_text(encoding="utf-8"))
    failing = [r for r in results if not r["passed"]]

    if failing:
        print(f"[{target['name']}][iter{iteration}] triaging {len(failing)} failure(s)...")
        triage_records = triage(spec_text, failing, run_dir, target["name"], iteration)
        write(iter_dir / "triage.json", json.dumps(triage_records, ensure_ascii=False, indent=2))

    return summary, failing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target_config")
    ap.add_argument("--iterations", type=int, default=3)
    ap.add_argument("--new-inputs", type=int, default=15)
    args = ap.parse_args()

    target_config_path = Path(args.target_config)
    target = json.loads(target_config_path.read_text())
    run_dir = PIPELINE_DIR / "runs" / target["name"]
    run_dir.mkdir(parents=True, exist_ok=True)

    spec_text = read(PIPELINE_DIR / target["initial_spec"])
    cumulative_inputs = []
    history = []

    for i in range(1, args.iterations + 1):
        summary, failing = run_iteration(
            target, run_dir, i, spec_text, cumulative_inputs, args.new_inputs, target_config_path,
        )
        history.append({"iteration": i, **summary, "spec_chars": len(spec_text)})

        if i == args.iterations:
            break
        if not failing:
            print(f"[{target['name']}] no failures at iter{i}, stopping early")
            break

        print(f"[{target['name']}][iter{i}] abstracting {len(failing)} failure(s) "
              f"(no raw examples will be shown to the spec-refiner)...")
        abstraction = abstract_failures(spec_text, failing, run_dir, target["name"], i)

        leaks = leak_check(abstraction, failing)
        if leaks:
            print(f"[{target['name']}][iter{i}] WARNING: {len(leaks)} literal fragment(s) "
                  f"leaked from examples into the abstraction text — retrying abstraction once")
            abstraction = abstract_failures(spec_text, failing, run_dir, target["name"], i)
            leaks = leak_check(abstraction, failing)
            if leaks:
                print(f"[{target['name']}][iter{i}] leak persisted after retry, flagging in log "
                      f"(spec-refine will still only see the abstraction text, not raw cases)")

        iter_dir = run_dir / f"iter{i}"
        write(iter_dir / "abstraction.txt", abstraction)
        write(iter_dir / "leak_check.json", json.dumps(leaks, ensure_ascii=False, indent=2))

        print(f"[{target['name']}][iter{i}] refining spec from abstraction only...")
        spec_text = specrefine(spec_text, abstraction, run_dir, target["name"], i)

    write(run_dir / "history.json", json.dumps(history, ensure_ascii=False, indent=2))
    write(run_dir / "final_spec.md", spec_text)
    print(f"\n[{target['name']}] history: " +
          ", ".join(f"iter{h['iteration']}={h['n_pass']}/{h['n_total']}" for h in history))


if __name__ == "__main__":
    main()
