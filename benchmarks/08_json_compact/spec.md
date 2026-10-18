# Compact JSON normalization

Read exactly one valid JSON value from standard input. JSON numbers in this
benchmark are integers only.

Parse the value and serialize the same data back to JSON with these rules:

- emit no insignificant whitespace,
- preserve object member order from the input,
- use lowercase JSON literals `true`, `false`, and `null`,
- use standard JSON string escaping,
- escape non-ASCII characters using `\uXXXX` notation,
- do not escape `/` unless required by JSON syntax,
- write one newline after the serialized value.

Nested arrays and objects are allowed.
