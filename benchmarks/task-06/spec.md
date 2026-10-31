# Fibonacci interval additions and sums

Let F[1]=1, F[2]=1, and F[k]=F[k-1]+F[k-2] for k>2.
Read n and m, an array a of n positive integers, and then m operations.
Process the operations in input order, starting from the supplied array and
fresh state for each complete stdin input. All indices are 1-based.

An operation `1 l r` adds F[i-l+1] to a[i] for every l <= i <= r.
An operation `2 l r` requests the sum of a[l] through a[r], inclusive, modulo
1000000009. Updates affect all subsequent operations. The required remainder
is always the representative from 0 through 1000000008. Values may be maintained
modulo that modulus because only these sums are observable.

Constraints: 1 <= n,m <= 300000; initially 1 <= a[i] <= 1000000000;
1 <= l <= r <= n for every operation. The first line contains n and m;
the second contains n array values; each subsequent line is one operation.
All tokens are base-ten integers separated by ASCII whitespace.

For every type-2 operation, output its answer as one base-ten integer without
leading zeros, spaces, or labels, followed by one LF. Preserve operation order.
Type-1 operations produce no output. If there are no type-2 operations, stdout
must be empty. No other output is allowed.
