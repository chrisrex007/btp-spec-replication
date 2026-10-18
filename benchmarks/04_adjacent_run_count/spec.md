# Consecutive-line run counting

Read newline-terminated text lines.

Partition the input into maximal consecutive runs of lines that are byte-for-byte
identical. Lines that are equal but separated by a different line belong to
different runs.

For each run, output one line consisting of:

1. the run length as a decimal integer right-aligned in a field at least seven
   characters wide,
2. one space,
3. the original line contents,
4. a newline.

Preserve the order of runs.
