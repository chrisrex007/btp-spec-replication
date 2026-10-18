# Base64 text decoding

Read a valid Base64 representation of UTF-8 text.

Decode using the standard Base64 alphabet and `=` padding. Newline characters
may appear between encoded groups and do not contribute decoded bytes.

Write exactly the decoded UTF-8 text to standard output. Do not add, remove, or
normalize newline characters in the decoded data.

All benchmark inputs are valid encodings whose decoded byte sequence is valid
UTF-8.
