# What is in here

Every run we have ever done, kept including the ones that failed. Failed runs are
labelled rather than deleted — knowing what did not work is part of the record.

Each run folder holds one folder per round (`iter1`, `iter2`, ...) containing the
rules extracted, the code generated, the test inputs, the results, and how the
failures were sorted. `llm_log.jsonl` at the top of each run records every model
call with its random seed.

## The main results

These are the numbers quoted in the README.

| Folder | What it is |
|---|---|
| `ladder_r1` … `ladder_r5` | The five test programs, three rounds each. The headline results. |
| `ladder_scores.json` | All five collected into one summary. |
| `slugify` | Real library, used as a sanity check. |
| `ftfy` | Real library, used as a sanity check. |

## Searching for vague wording

| Folder | What it is |
|---|---|
| `ladder_r1_ambiguity` … `ladder_r5_ambiguity` | The direct search for alternative readings — the third and best of the three approaches. |
| `ladder_r2_behavioural` | The second approach: compare what the generated code *does* rather than what the rules *say*. |

## Controlled comparisons

This is where one thing is changed at a time, and it is the most defensible part
of the work.

| Folder | What it shows |
|---|---|
| `_arms/slugify_legacy` | The original, before we found the dropped-sentence problem. Scores 93% → 21% → 73%. |
| `_arms/slugify_fixed_r1`, `_arms/slugify_fixed_r2` | The same thing with the text-parsing bug fixed. Still 93% → 21% → 71% — which proved that bug was *not* the cause. Run twice to confirm. |
| `_arms/slugify_complete_r1` | With the missing check added. 93% → 97% → 95%. This is the comparison that identified the real problem. |
| `_arms/ftfy_legacy`, `_arms/ftfy_fixed`, `_arms/ftfy_complete_partial` | The same three-way comparison on the other library. |
| `_arms/ladder_r2_ambiguity_strict`, `_arms/ladder_r4_ambiguity_strict` | Cautiously-worded instructions versus neutral ones. The cautious version found nothing; the neutral version found real problems. Same code, different wording. |
| `_arms/ladder_r3_smt_partial` | First trial of the solver layer inside the loop. Two rounds only. |
| `_arms/slugify_consistency_control.json` | A check on the method itself: with nothing hidden to find, how often does it raise a false alarm? Answer: never. |

## Incomplete and failed

Kept deliberately.

| Folder | Why it stopped |
|---|---|
| `_arms/ladder_r3_partial`, `_arms/ladder_r5_partial`, `_arms/slugify_complete_r2_partial` | Cut short, superseded by the full runs above. |
| `_arms/ftfy_crashed_surrogate`, `_arms/ladder_r5_ambiguity_crashed` | Crashed mid-run. |
| `_arms/ftfy_null_run2` | Produced no usable test inputs at all — the input generator ran away into a repeating string and the whole list was discarded. This is what led us to salvage partial output instead of throwing it away, and to make the loop refuse to continue when it has tested nothing. |
| `_failed_ftfy_maxtokens` | Ran out of response length. |
| `_spikes_2026-09-02` | The earliest rough experiments, before the pipeline existed. Kept as history; their conclusion was later shown to be wrong. |
