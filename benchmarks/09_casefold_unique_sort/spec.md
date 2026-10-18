# Stable case-insensitive unique ordering

Read zero or more newline-terminated ASCII text lines.

Compare lines using an ASCII case-insensitive key obtained by treating each
lowercase letter `a` through `z` as its corresponding uppercase letter.
Other bytes compare unchanged.

Sort lines by this case-insensitive key in ascending bytewise order. The sort is
stable: lines with equal keys retain their original relative order.

Then output only the first line from each group of equal case-insensitive keys.

Preserve the original spelling/capitalization of the representative line and
terminate every output line with a newline.
