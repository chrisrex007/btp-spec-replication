# Base64 text encoding

Read the complete UTF-8 input and encode its exact UTF-8 byte sequence using the
standard Base64 alphabet:

`A-Z`, `a-z`, `0-9`, `+`, `/`

Use `=` padding as required.

Wrap encoded output at 76 Base64 characters per line. For non-empty input,
terminate the final encoded line with a newline. For empty input, produce no
output.
