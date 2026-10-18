# Real-software benchmark experiments

These benchmark tasks use installed command-line software only as a hidden
reference oracle.

The synthesis and test-generation LLMs receive only:

- the natural-language specification, and
- the input-format description.

They do **not** receive the reference command, software name, executable path,
or source code.

## Initial difficulty sweep

The numbered tasks are ordered approximately from easier to harder:

1. `01_line_count`
2. `02_ascii_upper`
3. `03_numeric_sort`
4. `04_adjacent_run_count`
5. `05_colon_field_select`
6. `06_width_wrap`
7. `07_base64_encode`
8. `08_json_compact`
9. `09_casefold_unique_sort`
10. `10_base64_decode`

During the pilot sweep, any target that reaches 100% baseline agreement on the
pilot/development test pool should be removed from the active benchmark set.
Such a target provides no failures for the feedback loop and is not useful for
the core raw-vs-abstract repair comparison.

This filtering must happen using only the pilot/development pool, before final
held-out evaluation. Do not use final held-out scores to decide which targets
remain.

## Test volume

The current LLM testcase generator is intentionally basic. Do not request
hundreds of cases in one call.

When large test pools are introduced, generate them in batches, deduplicate and
persist the resulting pool, then reuse the same frozen pool across baseline/raw/
abstract conditions. This both saves LLM tokens and makes the comparison fair.
