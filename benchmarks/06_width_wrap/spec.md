# Fixed-width line wrapping

Read arbitrary printable ASCII text.

Maintain a column count independently for each input line. Insert a newline
before a character that would make the current output line exceed 8 characters.

An input newline is copied to the output and resets the column count to zero.
Empty input lines are therefore preserved.

Do not add an extra newline merely because end-of-file is reached. In other
words, if the final input line is not newline-terminated, the final wrapped
fragment is also not newline-terminated unless a wrap itself inserted a newline.
