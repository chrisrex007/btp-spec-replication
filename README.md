# Rebuilding software behaviour from its specification

| Situation                                 | What it means                        | Is it our fault?                        |
| ----------------------------------------- | ------------------------------------ | --------------------------------------- |
| **We got it wrong**                       | We misread the description           | **Yes** - this is the only real failure |
| **The description is vague**              | Both answers are defensible readings | No                                      |
| **The software contradicts its own docs** | The software is buggy                | No - _useful finding_                   |

## 1. The Pipeline

The whole loop is five steps. All of it is driven by `pipeline/loop.py`; the file
named beside each step is where that step actually happens.

**Step 1 — Read the description and write down the rules.**
The model turns the English description into an explicit numbered list of rules.
Every rule must name the sentence it came from. This is enforced by the response
format itself, not by asking the model nicely — it physically cannot return a
rule without naming its source. _(`loop.py`, instructions in
`pipeline/prompts/rulegen_system.txt`)_

**Step 2 — Write code from the rules.**
Code is generated from the _rule list_, never from the raw description. This
matters: it forces every line of code to trace back to a written rule, instead of
the model quietly inventing behaviour that merely sounds sensible.
_(`loop.py`, instructions in `pipeline/prompts/codegen_system.txt`)_

**Step 3 — Invent test inputs and ask the sealed box.**
The system makes up its own test inputs, then runs them through the real software
to get the expected answers. Asking the real software is compulsory — the model
is never allowed to guess what it _would_ say. _(`loop.py` and
`pipeline/prompts/testgen_system.txt`; which software to call is set in
`pipeline/targets/ftfy.json`)_

**Step 4 — Run our code on the same inputs and sort out what went wrong.**
Our generated code runs on the same inputs and the answers are compared. Every
mismatch is sorted into the three buckets in the table above — our mistake, vague
wording, or a bug in the software. The generated code runs inside a guard that
limits time and memory, so a runaway program cannot take down a shared machine.

**Step 5 — Improve the description without looking at the failures, then repeat.**
This is a restriction we impose on ourselves deliberately. Before the description
is improved, the failures are rewritten into an abstract summary, and the
original failing examples are **thrown away**. The part of the system that
rewrites the description never sees them.

## 2. Repo Contents

```
README.md               this file

pipeline/
  loop.py               the whole loop, steps 1-5 above
  llm_client.py         talks to the language model
  llm_log.py            records every single model call, with its random seed
  compare_runner.py     runs our code and the real software on the same inputs
  sandbox.py            keeps generated code inside time and memory limits
  run_all.sh            runs the batch on the server

  prompts/              every instruction given to the model. These are part of
                        the method, not decoration - one of our findings is
                        entirely about a prompt's wording
  specs/                the written description fed to the system. Taken from
                        public documentation only, never from reading the source
  targets/              which software to test, and how to call it
  runs/                 the ftfy results (see runs/README.md)
  logs/                 console output from the runs

serving/                scripts that start the language model on the lab GPUs
test.py                 a hand-written ftfy implementation, kept for reference
```

## 3. Running it

```bash
cd /tmp/btp/pipeline

# one program, three rounds, with the checks from steps 2 and 6 turned on
venv/bin/python loop.py targets/ladder_r3.json \
    --iterations 3 --self-consistency --rule-completeness

# build a frozen exam set, then mark against it
venv/bin/python evaluate.py make-heldout targets/ladder_r3.json --n 40
venv/bin/python evaluate.py score targets/ladder_r3.json runs/ladder_r3 --iteration 3

# everything at once - this is the script that produced our current results
bash run_all.sh
```
