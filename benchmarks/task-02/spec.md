# Scaled decimal expression evaluation

Read a complete finite arithmetic program from stdin, starting with fresh state.
Every nonempty line is either an expression, a variable assignment `v = expression`,
or `scale = k`. Blank lines are allowed. Each line ends with LF. Variable names
are single lowercase letters. All variables initially have value 0 with scale 0;
the global scale initially is 0. Assignments produce no output. An expression
line produces its value followed by LF. There is no state shared between inputs.

Numbers use arbitrary-precision signed decimal arithmetic. A value has both a
numeric value and a nonnegative scale (number of stored fractional digits).
An unsigned decimal literal consists of one or more decimal digits, optionally
followed by a dot and one or more decimal digits. Its scale is its number of
fractional digits, including trailing zeros. Leading zeros are allowed and do
not mean octal. Unary minus negates a value without changing its scale. Variables
preserve both the value and the scale assigned to them. Parentheses group
expressions. Whitespace may separate tokens but not split a literal or name.

Operators are unary minus, right-associative exponentiation `^`, multiplication,
division and remainder `* / %`, and addition/subtraction `+ -`. Unary minus binds
most tightly, then exponentiation, then `* / %` (left associative), then `+ -`
(left associative). There is also the function `sqrt(expression)`. Assignment
occurs only as a complete line, never inside another expression. Every exponent
is an integer literal from 0 through 8. There are no other operators or functions.

Let S be the current global scale, and let sa and sb be the scales of operands
a and b. Truncation always discards excess fractional digits toward zero; it
never rounds to nearest. Apply these rules at each individual operation:

- Addition and subtraction have scale max(sa,sb).
- Multiplication has scale min(sa+sb,max(S,sa,sb)).
- Division has scale S; truncate the exact quotient to that scale.
- For a%b, compute q = a/b truncated to S fractional digits, then compute
  a-q*b to scale max(S+sb,sa). The intermediate q*b in this definition is not
  truncated using the ordinary multiplication rule.
- For a^k with k>0, the result has scale min(sa*k,max(S,sa)). For k=0, the result
  is the integer 1 with scale 0, including when a is zero.
- sqrt(a) has scale max(S,sa); take the nonnegative square root and truncate it
  to that scale.

A `scale = k` line sets S to the integer literal k, between 0 and 20 inclusive.
Reading the identifier `scale` as an expression is not allowed. Literals have
at most 20 integer digits and 10 fractional digits. Each expression has at most
40 tokens, and each program has at most 40 nonempty lines. All divisors and
remainder divisors are nonzero; square-root arguments are nonnegative. All
intermediate results have at most 200 integer digits. Programs always terminate.

Output formatting uses no exponent notation and never wraps long lines. Any
numeric zero prints exactly `0`, regardless of its scale. A nonzero result with
scale 0 prints as an integer. Otherwise print exactly its stored number of
fractional digits, retaining trailing zeros. Omit the zero before the decimal
point when the magnitude is less than 1 (for example `.50` or `-.50`). Prefix a
minus sign exactly when the result is negative. There are no leading zeros in
the integer part, no plus signs, spaces, labels, or additional blank lines.
