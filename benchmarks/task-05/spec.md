# Weighted occurrence sums over intervals

Read n, t, then an array a of n positive integers, then t interval queries.
For a query [l,r], let K_s be the number of occurrences of integer s in the
inclusive subarray a[l],...,a[r]. The answer is the sum of K_s*K_s*s over all
distinct integers occurring in that subarray. Answer every query independently;
the array does not change.

Each query identifies a nonempty interval within the array.
All tokens are base-ten integers separated by ASCII whitespace.
The first line contains n and t; the second contains the n array values; the
next t lines each contain l and r. Indexing starts at 1.

Output exactly t lines in query order. Each line contains one base-ten integer
answer without leading zeros, extra spaces, or labels, followed by one LF.
Answers may exceed signed 32-bit range. No other stdout is allowed.
