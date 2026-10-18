# Colon-delimited field selection

Process the input one line at a time.

For a line containing at least one colon character, split the line into fields
at every colon. Empty fields count as fields. Number fields starting from 1.

Output field 1 and, if it exists, field 3, in that order. When both selected
fields exist, separate them with a single colon. If field 3 exists but is empty,
the separating colon is still present. If field 3 does not exist, output only
field 1.

A line containing no colon is output unchanged.

Emit one newline for every input line.
