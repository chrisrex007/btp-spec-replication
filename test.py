import re
import html
import unicodedata

class FTFY:
    def __init__(self):
        self.explanation = []

    def mojibake(self, text):
        """Fixes mojibake and other problems with Unicode."""
        # Remove HTML entities
        text = html.unescape(text)

        # Replace curly quotes with their straight counterparts
        text = re.sub(r'&\s*[LR]quot\s*;', lambda m: m.group(0).replace('L', 'l').replace('R', 'r').replace('quot', '"'), text)

        # Remove curly quotes that are already in the text
        text = re.sub(r'[‘’»«]', lambda m: m.group(0).replace('‘', "'").replace('’', "'").replace('»', "'").replace('«', "'"), text)

        # Normalize whitespace and control characters
        text = re.sub(r'\s+', ' ', text)  # Replace multiple whitespace with a single space
        text = re.sub(r'[^\x00-\x7F]+', '', text)  # Remove non-ASCII characters
        text = re.sub(r'\n+', '\n', text)  # Replace multiple newline with a single newline
        text = re.sub(r'\t+', '\t', text)  # Replace multiple tab with a single tab

        # Fix mojibake
        text = self.fix_mojibake(text)

        # Add an explanation for the fixes applied
        self.explanation.append("Removed HTML entities.")
        self.explanation.append("Replaced curly quotes with their straight counterparts.")
        self.explanation.append("Removed curly quotes that are already in the text.")
        self.explanation.append("Normalized whitespace and control characters.")
        self.explanation.append("Fixed mojibake.")

        return text

    def fix_mojibake(self, text):
        """Fixes mojibake and other problems with Unicode."""
        # Remove Windows-1252 characters
        text = re.sub(r'[^\x00-\x7F\xA0-\xFF]', '', text)

        # Replace Windows-1252 characters with their Unicode counterparts
        text = re.sub(r'[\u0080-\u009F]', lambda m: self.char_to_unicode(m.group(0)), text)
        text = re.sub(r'[\u00A0-\u00FF]', lambda m: self.char_to_unicode(m.group(0)), text)

        return text

    def char_to_unicode(self, char):
        """Converts a Windows-1252 character to its Unicode counterpart."""
        if char == '\u0080':
            return '€'
        elif char == '\u0081':
            return '‚'
        elif char == '\u0082':
            return 'ƒ'
        elif char == '\u0083':
            return '…'
        elif char == '\u0084':
            return '†'
        elif char == '\u0085':
            return '‡'
        elif char == '\u0086':
            return 'ˆ'
        elif char == '\u0087':
            return '‰'
        elif char == '\u0088':
            return 'Š'
        elif char == '\u0089':
            return '‹'
        elif char == '\u008A':
            return 'Œ'
        elif char == '\u008B':
            return ''
        elif char == '\u008C':
            return 'Ž'
        elif char == '\u008D':
            return ''
        elif char == '\u008E':
            return ''
        elif char == '\u008F':
            return '‘'
        elif char == '\u0090':
            return '’'
        elif char == '\u0091':
            return '“'
        elif char == '\u0092':
            return '’'
        elif char == '\u0093':
            return '—'
        elif char == '\u0094':
            return '–'
        elif char == '\u0095':
            return '—'
        elif char == '\u0096':
            return '›'
        elif char == '\u0097':
            return ''
        elif char == '\u0098':
            return 'š'
        elif char == '\u0099':
            return '›'
        elif char == '\u009A':
            return 'œ'
        elif char == '\u009B':
            return ''
        elif char == '\u009C':
            return 'ž'
        elif char == '\u009D':
            return ''
        elif char == '\u009E':
            return ''
        elif char == '\u009F':
            return '‘'

        return ''

def main():
    test_cases = [
        # --- existing (corrected) ---
        ("P&EACUTE;REZ", "PÉREZ"),

        # 1. Single-layer cp1252 mojibake, Latin-1 range
        ("CafÃ©", "Café"),

        # 2. Bytes in the 0x80-0x9F range (sloppy-cp1252 territory)
        ("ÃœberstraÃŸe", "Überstraße"),

        # 3. 3-byte UTF-8 sequence (symbol outside Latin range)
        ("âœ” No problems", "✔ No problems"),

        # 4. 4-byte UTF-8 / astral plane (emoji)
        ("ðŸ˜Š", "😊"),

        # 5. Cyrillic - whole string is mojibake, no ASCII anchor
        ("ÐŸÑ€Ð¸Ð²ÐµÑ‚, Ð¼Ð¸Ñ€", "Привет, мир"),

        # 6. CJK - dense multi-byte, tests heuristic confidence
        ("æ—¥æœ¬èªž", "日本語"),

        # 7. Byte 0x9D has no cp1252 mapping; must survive as U+009D
        #    ('"' = U+201D -> E2 80 9D -> 'â' '€' '\x9d')
        ("â€œquotedâ€\x9d", '"quoted"'),

        # 8. Doubly-encoded: needs a second pass to reach a fixpoint
        ("The Mona Lisa doesnÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢t have eyebrows.",
         "The Mona Lisa doesn't have eyebrows."),

        # 9. FALSE POSITIVE GUARD - decodable, but must be left alone
        ("Ancien Régime", "Ancien Régime"),

        # 10. FALSE POSITIVE GUARD - the documented hard case
        ("IL Y MARQUÉ…", "IL Y MARQUÉ…"),
    ]

    for input_text, expected_output in test_cases:
        f = FTFY()
        actual_output = f.mojibake(input_text)
        print(f"Input: {input_text}")
        print(f"Expected Output: {expected_output}")
        print(f"Actual Output: {actual_output}")
        print(f"Explanation: {f.explanation}")
        print()

if __name__ == "__main__":
    main()
