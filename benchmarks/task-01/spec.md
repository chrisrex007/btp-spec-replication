# Recursive JSON array canonicalization

Read exactly one JSON value from stdin. The value may contain null, booleans,
integers, strings, arrays, and objects. Process every value recursively, from
children to parents. Leave primitive values unchanged. In an object, process
all property values and keep the property names. In an array, first process
all elements, then remove equal elements and sort the remaining elements by
the total order below. Equality is structural; object property insertion order
does not affect equality. The result contains each distinct processed element
exactly once, even when elements that were different before recursive processing
become equal afterwards.

The order of types, from smallest to largest, is null, false, true, numbers,
strings, arrays, objects. Compare integers numerically. Compare strings
lexicographically by Unicode code point, with a shorter proper prefix first.
Compare arrays lexicographically by their processed elements using this same
total order; a shorter proper prefix comes first. Compare objects first by the
sorted arrays of their property names. If those arrays are equal, compare the
arrays of corresponding values in that property-name order. Apply this ordering
recursively at every depth.

Write the transformed value as one compact JSON value followed by exactly one
LF byte. Object properties must appear in increasing Unicode code point order
at every depth. Use no whitespace outside strings. Emit non-ASCII characters
as UTF-8, not ASCII escape sequences. Escape double quotes and backslashes;
escape U+0008, U+0009, U+000A, U+000C, U+000D as \b, \t, \n, \f, \r respectively;
escape the other U+0000 through U+001F characters as lowercase \u00xx, and U+007F
as \u007f. Do not escape forward slashes or other Unicode characters. Emit
integers in ordinary base-ten notation without leading zeros, decimal points, or exponent notation;
zero is 0. Write JSON booleans and null in lowercase. Produce no other stdout.

The input has unique property names within each object, no surrogate code points,
and no floating-point numbers or negative-zero literal (`-0`). Every integer
lies between -1000000000 and 1000000000 inclusive. Nesting depth is at most 12, each container has at most 30
entries, each string has at most 100 Unicode characters, and the entire input is
at most 8000 UTF-8 bytes. Any permitted JSON whitespace may surround the value.
