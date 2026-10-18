# Numeric line ordering

Read zero or more newline-terminated lines. Each line represents a signed
base-10 integer and may contain leading zeroes. A leading minus sign is allowed;
a leading plus sign is not.

Output all input lines ordered by ascending numeric value.

If two lines represent the same numeric value, order those lines by their
original byte sequence in ascending lexicographic order.

Preserve duplicate lines. Emit each output record followed by a newline.
