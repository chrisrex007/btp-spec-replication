# Paragraph markup to HTML

Convert a complete paragraph-only markup document from stdin into HTML. Input
uses ASCII printable characters and LF, with at most 8000 bytes. Empty lines
separate paragraphs; ignore empty lines at the beginning or end and collapse
multiple empty separator lines. Each nonempty line starts with a non-space
character. The allowed block structure consists only of paragraphs: inputs do
not contain headings, lists, block quotations, thematic breaks, indented or
fenced code blocks, raw HTML, autolinks, images, or link-reference definitions.
In particular, a line must not start a block construct of one of those types;
raw `<` is forbidden outside code spans and link destinations. The allowed
inline constructs are described below. Markup may be nested where permitted,
and unpaired delimiters are literal text.

Wrap each paragraph in `<p>` and `</p>`, followed by LF. Do not add whitespace
between paragraphs beyond this LF. Empty input, or input consisting only of
empty lines, produces empty stdout. Escape &, <, > and double quote in all
ordinary text and code text as &amp;, &lt;, &gt; and &quot;. Leave apostrophe and
slash unchanged. Emit decoded non-ASCII characters as UTF-8. Do not perform smart
quote, dash, ellipsis, or other typography substitutions.

Backslash escapes: outside code spans, a backslash followed by any ASCII
punctuation character makes that punctuation literal, so it cannot act as markup.
ASCII punctuation is every printable ASCII character other than letters, digits,
and space. A backslash before any other ordinary character stays literal.
A backslash immediately before an intra-paragraph LF instead makes a hard line
break. A backslash at the end of the paragraph is literal.

Character references outside code spans are decoded before HTML text escaping,
but their decoded characters do not create new markup delimiters. Recognize
exactly &amp;, &lt;, &gt;, &quot;, &apos;, decimal &#digits;, and hexadecimal
&#xhex; or &#Xhex;. A semicolon is required. Numeric references have 1 through 7
decimal digits or 1 through 6 hexadecimal digits, and their values are valid
Unicode scalars from U+0020 through U+10FFFF excluding U+007F through U+009F and
surrogates. Other ampersand sequences are ordinary literal text; other named
character references are absent from valid input.

Code spans: a maximal run of one or more backticks opens a code span if a later
maximal run of exactly the same length exists in that paragraph; the first such
run closes it. Runs of other lengths are part of its content. Replace each LF
in the content with one space. If the resulting content starts and ends with
space and contains a non-space character, remove exactly one space from each
end. Otherwise retain the content's spaces. Render as `<code>content</code>`,
escaping HTML as above. Inside a code span, backslashes, entities, emphasis, and
links have no special meaning. An unmatched backtick run remains literal.

Line breaks outside code spans: a regular LF inside a paragraph renders as LF.
Discard spaces immediately preceding it. If it is preceded by two or more
spaces, or by the hard-break backslash above, render `<br />` followed by LF
instead. The final LF terminating a paragraph is not an inline break. Discard
trailing spaces at the end of a paragraph; they never add a final `<br />`.

Emphasis uses maximal runs of `*` or `_`. A run is left-flanking when the next
character is not whitespace, and either the next character is not punctuation
or the previous character is whitespace or punctuation. It is right-flanking
when the previous character is not whitespace, and either the previous character
is not punctuation or the next character is whitespace or punctuation. For
these tests use characters in the original input; paragraph boundaries count
as whitespace. In this ASCII input, whitespace means space or LF, and punctuation
means ASCII punctuation as defined above. Escaped delimiters and delimiters
inside code spans do not participate.

A `*` run can open emphasis exactly when left-flanking and close exactly when
right-flanking. An `_` run can open when left-flanking and either not
right-flanking or preceded by punctuation; it can close when right-flanking
and either not left-flanking or followed by punctuation. Thus underscores
inside words do not form emphasis. An opening and closing run must use the
same character and be different runs, with nonempty content between them.
If either run can both open and close, their lengths must not sum to a multiple
of three unless both lengths are themselves multiples of three. This restriction
uses the delimiter-run lengths, including delimiters in a run that can be used
for other nesting.

A matching pair consumes two delimiters per side for strong emphasis whenever
both sides have at least two available; otherwise it consumes one per side for
ordinary emphasis. Render strong emphasis with `<strong>...</strong>` and
ordinary emphasis with `<em>...</em>`. Unused characters in a run remain available
for nesting or literal text. Literal copies of the same delimiter cannot occur
immediately inside their corresponding opening or closing delimiter, unless
backslash-escaped. Use these priorities to resolve ambiguous matches: prefer
fewer levels of nesting; for the same content prefer an outer em with inner
strong to an outer strong with inner em; overlapping spans favor the one whose
opening delimiter occurs first; competing openings for the same closing run
favor the later opening. Parse code spans and complete link structures more
tightly than emphasis, and do not let emphasis cross a link's label boundary.

Inline links have the form `[label](destination)` or
`[label](destination "title")`. No whitespace is allowed between the closing
label bracket and opening parenthesis. Destinations are absolute `https://` URLs
or paths starting with `/`, use only ASCII URL characters, and contain no
whitespace, backslashes, angle brackets, quotes, or entities. Parentheses in
destinations must be balanced. Titles, when present, are double-quoted and on
one line; backslash escapes and the allowed character references are decoded
inside them, but no emphasis or other markup is parsed there. A title is
separated from its destination by one or more spaces. Empty destinations,
reference links, and angle-bracket destination syntax are absent.

Labels may contain ordinary text, balanced brackets, code spans, character
references, backslash escapes, emphasis, and line breaks, but may not contain
another link. Render a valid link as `<a href="URL">LABEL</a>` or
`<a href="URL" title="TITLE">LABEL</a>`. Render LABEL as inline markup. Escape TITLE
like ordinary HTML text. For URL rendering retain ASCII alphanumerics and
`-_.+!*(),%#@?=;:/+$~`; render & as &amp; and apostrophe as &#x27;; percent-encode
other bytes with uppercase hexadecimal. Unmatched or otherwise non-link bracket
and parenthesis characters are literal. There are at most 20 paragraphs and no
more than 8 nested inline constructs. Produce only the HTML bytes described.
