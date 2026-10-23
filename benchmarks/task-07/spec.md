# Interval sums, remainders, and point assignments

Read n and m, an array a of n positive integers, and m operations. Each stdin
input starts from a fresh supplied array. Process operations in their given
order, with 1-based indices:

- `1 l r`: output the sum of a[l] through a[r], inclusive.
- `2 l r x`: replace each a[i], l <= i <= r, with a[i] modulo x. The result
  is the nonnegative remainder, between 0 and x-1.
- `3 k x`: replace a[k] with x.

Updates affect subsequent operations. Constraints: 1 <= n,m <= 100000;
initially 1 <= a[i] <= 1000000000; 1 <= l <= r <= n; 1 <= k <= n;
1 <= x <= 1000000000. Updated array entries may equal zero. The first line
contains n and m; the second contains n array values; the next m lines each
contain one operation in the indicated format. All tokens are base-ten integers
separated by ASCII whitespace.

For each type-1 operation, output exactly one line containing the base-ten sum,
without leading zeros, spaces, or labels, followed by LF. Sums may exceed signed
32-bit range. Other operations produce no output. If there are no type-1
operations, stdout must be empty. No other stdout is allowed.
