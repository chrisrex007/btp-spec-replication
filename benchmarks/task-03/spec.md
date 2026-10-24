# Canonical XML serialization

Read one well-formed XML 1.0 document encoded in UTF-8. Output its canonical XML
1.0 serialization WITH comments, encoded as UTF-8, with no byte-order mark and
no added final newline. This is inclusive canonicalization of the entire document,
not exclusive canonicalization and not XML canonicalization 1.1 or 2.0.

Parse XML before serialization. XML line ending normalization converts CRLF and
standalone CR into LF. Resolve predefined entities (&amp;, &lt;, &gt;, &apos;,
&quot;) and numeric character references. CDATA sections become ordinary text.
XML attribute normalization converts literal tabs and line breaks in attribute
values to spaces; a character inserted by a numeric character reference keeps
its referenced character. Preserve character data, including whitespace between
elements. There is no DTD and consequently no DTD-supplied defaults or entities.

Do not output an XML declaration. Expand every empty-element tag into separate
start and end tags. Preserve the original qualified element and attribute names,
including namespace prefixes; do not invent or rename prefixes. Start tags have
one space before every namespace declaration or attribute, no spaces around `=`,
and double-quoted values. End tags have no extra whitespace.

Maintain the namespace mappings actually in scope at each element, including
inherited mappings. Emit namespace declarations when the mapping differs from
the mapping already rendered by ancestors, including an empty default namespace
when needed to cancel an inherited default. Omit redundant declarations and the
implicit `xml` declaration. Sort namespace declarations by prefix in Unicode
code point order (the default namespace has empty prefix and is first). Emit
namespace declarations before ordinary attributes. Default namespaces do not
apply to unprefixed attributes. Sort ordinary attributes by namespace URI and
then local name, using Unicode code point order; attributes without a namespace
have the empty URI and precede namespaced attributes.

In text nodes, escape ampersand as &amp;, less-than as &lt;, greater-than as &gt;,
and CR as &#xD;. In attribute values, escape ampersand, less-than, and double quote
as &amp;, &lt;, and &quot;, and TAB, LF, CR as &#x9;, &#xA;, &#xD; respectively.
Do not escape other characters. Character references use precisely the spellings
above. In comments and processing instructions, retain the content and delimiters,
escaping CR as &#xD;. A processing instruction has one space between target and
nonempty data, and no space for empty data. Inside the root element, output
comments and processing instructions in document order without adding whitespace.
For each such node preceding the root, output the node followed by LF; for each
such node following the root, output LF followed by the node. Discard whitespace
outside the document element.

Input contains one root element. Names and prefixes are
ASCII XML names. Each nonempty namespace URI is an absolute URI. Namespace
bindings obey XML Namespaces 1.0; duplicate expanded attribute names are forbidden.
No DTD, entity declarations, external entities, XInclude processing, network
resources, or filesystem resources are allowed. Inputs may contain declarations,
namespace declarations, text, attributes, CDATA, comments, processing instructions,
and predefined or numeric references, provided all XML well-formedness conditions
hold. Write only the canonical bytes to stdout.
