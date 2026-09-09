# Specification: Text Repair Function

Implement a single function `fix_text(text: str) -> str` that repairs common forms
of corrupted Unicode text ("mojibake") and normalizes text to a clean, correct
Unicode representation, without altering the actual linguistic content of the text.

## Scope of repairs

1. **Mojibake from encoding mismatches.** Text is sometimes correctly encoded as
   UTF-8 bytes, but those bytes get *decoded* using the wrong single-byte or
   legacy encoding (commonly Windows-1252 or Latin-1), producing a string of
   the "wrong" but valid-looking characters. Detect when a string's characters,
   if re-encoded using the encoding that was mistakenly used to decode them,
   would form valid UTF-8 bytes that decode to more sensible text — and if so,
   reverse the process. This mis-decoding can happen more than once in a row
   (double or triple mojibake); repairs should be applied repeatedly until no
   further reversible corruption is detected, without over-correcting text that
   is already correct.

2. **Do not corrupt already-correct text.** The repair must be conservative: if
   a string is already valid, sensible Unicode text, the function must return
   it unchanged (or with only the normalizations described below applied). The
   function must never "fix" text that isn't actually broken — a wrong-guess
   fix is worse than doing nothing, since it destroys real content.

3. **HTML/XML entity decoding.** Numeric character references (decimal and
   hexadecimal) and named character entities that appear literally in text
   (i.e., were never decoded by an HTML parser) should be decoded to the
   character they represent.

4. **Control and formatting characters.** Remove or replace Unicode control
   characters and non-printing formatting characters that have no legitimate
   role in plain text (e.g., stray C0/C1 control codes), while preserving
   legitimate whitespace (spaces, tabs, newlines).

5. **Unicode normalization.** Normalize the final output to Unicode Normalization
   Form C (NFC), so that characters representable either as a single precomposed
   codepoint or as a base character plus combining marks are represented
   consistently.

6. **Line endings.** Normalize all line-ending variants (CR, CRLF, and other
   Unicode line/paragraph separators) to a single consistent newline
   representation.

7. **Idempotence.** Applying the function twice to the same input must produce
   the same result as applying it once — i.e., `fix_text(fix_text(x)) == fix_text(x)`
   for any input `x`.

## Non-goals

- The function does not translate between human languages.
- The function does not attempt spelling or grammar correction.
- The function is not required to detect or repair corruption from encodings
  other than the common legacy single-byte Western encodings and UTF-8/UTF-16
  mismatches — exotic or rare legacy encodings are out of scope.
- The function should not change the semantic meaning of correctly-encoded text
  under any circumstance.

## Interface

```python
def fix_text(text: str) -> str:
    """Given a possibly-corrupted Unicode string, return a repaired,
    normalized version of the same text."""
```
