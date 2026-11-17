"""Refuse escaped CSS declaration names in static geometry verifiers (#518).

This is a bounded declaration-position scanner, not a CSS cascade evaluator.
Escapes in values, strings, comments, URLs and selector preludes remain data.
See https://www.w3.org/TR/css-syntax-3/#consume-declaration.
"""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re


ESCAPE = r"\\(?:[0-9a-fA-F]{1,6}(?:\r\n|[ \t\r\n\f])?|[^\r\n\f])"
ESCAPE_RE = re.compile(ESCAPE)
NAME_RE = re.compile(rf"(?:[-_a-zA-Z\x80-\U0010ffff]|{ESCAPE})(?:[-\w\x80-\U0010ffff]|{ESCAPE})*")
STRING_RE = re.compile(r'''"(?:\\(?:\r\n|[\s\S])|[^"\\\n\r\f])*(?:"|\\\Z|(?=[\n\r\f])|\Z)|'(?:\\(?:\r\n|[\s\S])|[^'\\\n\r\f])*(?:'|\\\Z|(?=[\n\r\f])|\Z)''')
WHITESPACE = " \t\n\r\f"
HTML_END_TAG_RE = re.compile(r"</([a-zA-Z][^ \t\n\r\f/>]*)")
# HTML's foreign-content recovery reparents these starts outside the SVG.
HTML_BREAKOUT = {
    "b", "big", "blockquote", "body", "br", "center", "code", "dd", "div", "dl", "dt",
    "em", "embed", "h1", "h2", "h3", "h4", "h5", "h6", "head", "hr", "i", "img", "li",
    "listing", "menu", "meta", "nobr", "ol", "p", "pre", "ruby", "s", "small", "span",
    "strong", "strike", "sub", "sup", "table", "tt", "u", "ul", "var",
}
HTML_INTEGRATION = {"foreignobject", "desc", "title"}
MATH_TEXT_INTEGRATION = {"mi", "mo", "mn", "ms", "mtext"}
HTML_TEXT_ONLY = {"textarea", "title", "xmp", "iframe", "noembed", "noframes", "script"}
# These at-rules contain descriptors rather than a nested rule list. Grouping
# rules inherit their surrounding context; keyframes contain qualified rules.
DESCRIPTOR_RULES = {
    "font-face", "font-feature-values", "font-palette-values", "property", "counter-style",
    "page", "color-profile", "position-try", "view-transition", "function",
}
KEYFRAME_RULES = {"keyframes", "-webkit-keyframes", "-moz-keyframes"}


def _decode(match: re.Match[str]) -> str:
    value = match[0][1:]
    if value[0] not in "0123456789abcdefABCDEF":
        return value
    point = int(value.strip(), 16)
    return chr(point) if 0 < point <= 0x10FFFF and not 0xD800 <= point <= 0xDFFF else "\ufffd"


def _tokens(css: str) -> list[tuple[str, bool]]:
    """Keep names and delimiters; make strings and unquoted URLs opaque."""
    css = css.replace("\x00", "\ufffd")
    tokens = []
    i = 0
    while i < len(css):
        if css[i] in WHITESPACE:
            i += 1
            continue
        if css.startswith("/*", i):
            end = css.find("*/", i + 2)
            i = end + 2 if end >= 0 else len(css)
            continue
        string = STRING_RE.match(css, i)
        if string:
            tokens.append(("<string>", False))
            i = string.end()
            continue
        name = NAME_RE.match(css, i)
        if name:
            text = name[0]
            start = i
            i = name.end()
            decoded = ESCAPE_RE.sub(_decode, text)
            if (decoded.lower() == "url" and css[i:i + 1] == "("
                    and (start == 0 or not re.match(r"[-#@\w\x80-\U0010ffff]", css[start - 1]))):
                content = i + 1
                while content < len(css) and css[content] in WHITESPACE:
                    content += 1
                if css[content:content + 1] not in ("'", '"'):
                    i = content
                    while i < len(css) and css[i] != ")":
                        escape = ESCAPE_RE.match(css, i)
                        i = escape.end() if escape else i + 1
                    i += i < len(css)
                    tokens.append(("<url>", False))
                    continue
            tokens.append((text, True))
            continue
        tokens.append((css[i], False))
        i += 1
    return tokens


def has_escaped_property(css: str, *, inline: bool = False) -> bool:
    """Recognise declaration starts, including nested rule blocks and inline CSS.

    A colon in a selector prelude is followed by a rule block, not a declaration
    terminator. Custom-property values may contain blocks and stay opaque.
    """
    tokens = _tokens(css)
    count = len(tokens)

    # Pair component boundaries once. Looking up each child's end avoids a
    # fresh walk through all descendants at every ancestor in deeply nested CSS.
    closing = {"(": ")", "[": "]", "{": "}"}
    ends = {}
    stack = []
    for offset, (value, _) in enumerate(tokens):
        if value in closing:
            stack.append((value, offset))
        elif stack and value == closing[stack[-1][0]]:
            _, opening = stack.pop()
            ends[opening] = offset + 1

    def skip_block(i: int) -> int:
        return ends.get(i, count)

    # Scan every rule block, but never function/bracket contents or a custom
    # property's component values. Use a worklist instead of recursion so a
    # deeply nested untrusted stylesheet cannot exhaust Python's call stack.
    blocks = [(0, count, inline)]
    while blocks:
        i, limit, declarations = blocks.pop()
        while i < limit:
            if tokens[i][0] in (";", "}"):
                i += 1
                continue
            name, identifier = tokens[i]
            declaration = declarations and identifier and i + 1 < limit and tokens[i + 1][0] == ":"
            custom = declaration and ESCAPE_RE.sub(_decode, name).startswith("--")
            j = i + 2 if declaration else i
            while j < limit:
                value = tokens[j][0]
                if value in ("(", "[") or (custom and value == "{"):
                    j = skip_block(j)
                    continue
                if value in (";", "}", "{"):
                    break
                j += 1
            if declaration and (custom or j == limit or tokens[j][0] != "{"):
                if "\\" in name:
                    return True
            if j < limit and tokens[j][0] == "{":
                end = skip_block(j)
                child_declarations = True  # an ordinary qualified rule's body
                if name == "@" and i + 1 < j and tokens[i + 1][1]:
                    at_rule = ESCAPE_RE.sub(_decode, tokens[i + 1][0]).lower()
                    child_declarations = (at_rule in DESCRIPTOR_RULES or
                                          (declarations and at_rule not in KEYFRAME_RULES))
                blocks.append((j + 1, end - 1 if j in ends else end, child_declarations))
                i = end
            else:
                i = j + 1
    return False


class _Styles(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.elements: list[tuple[str, str, bool]] = []
        self.style: list[str] | None = None
        self.escaped = False
        self.plaintext = False

    def set_cdata_mode(self, elem: str, *args, **kwargs) -> None:
        # HTML text-only modes do not apply to same-named SVG elements. Foreign
        # content still parses entities, markup comments and CDATA sections.
        namespace = self.elements[-1][1] if self.elements else "html"
        if namespace == "html":
            # Python 3.14 added an escapable keyword to this parser hook.
            super().set_cdata_mode(elem, *args, **kwargs)
            # Old HTMLParser only recognises bare </tag>. Browsers also end
            # text-only content at attributed/slashed appropriate end tags.
            self.interesting = re.compile(r"</" + re.escape(elem) + r"(?=[ \t\n\r\f/>])", re.I | re.ASCII)

    def parse_endtag(self, i: int) -> int:
        elem = self.cdata_elem
        if elem is None:
            name = HTML_END_TAG_RE.match(self.rawdata, i)
            if name is None:
                # Whitespace after </ does not open an end tag in HTML. Old
                # HTMLParser accepts it and could incorrectly leave SVG/MathML.
                return self.parse_bogus_comment(i)
            elem = name[1].lower()
            attributes = name.end()
        else:
            if not self.interesting.match(self.rawdata, i):
                return super().parse_endtag(i)
            attributes = i + 2 + len(elem)
        # Attributes on an end tag are ignored, but quoted > characters do not
        # finish it. Quotes in an unquoted value/name do not open a string.
        state = "before"
        for position in range(attributes, len(self.rawdata)):
            char = self.rawdata[position]
            if state in ("'", '"'):
                if char == state:
                    state = "after_value"
                continue
            if char == ">":
                self.handle_endtag(elem)
                self.clear_cdata_mode()
                return position + 1
            if state == "before":
                if char not in WHITESPACE and char != "/":
                    state = "name"
            elif state == "name":
                if char in WHITESPACE:
                    state = "after_name"
                elif char == "=":
                    state = "before_value"
                elif char == "/":
                    state = "before"
            elif state == "after_name":
                if char == "=":
                    state = "before_value"
                elif char == "/":
                    state = "before"
                elif char not in WHITESPACE:
                    state = "name"
            elif state == "before_value":
                if char not in WHITESPACE:
                    state = char if char in ("'", '"') else "unquoted"
            elif state == "unquoted":
                if char in WHITESPACE:
                    state = "before"
            elif state == "after_value":
                state = "before" if char in WHITESPACE or char == "/" else "name"
        return -1

    def leave_foreign_content(self) -> None:
        while self.elements:
            tag, namespace, html_point = self.elements[-1]
            if namespace == "html" or html_point or (namespace == "math" and tag in MATH_TEXT_INTEGRATION):
                break
            self.elements.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.plaintext:
            return
        parent, namespace, html_point = self.elements[-1] if self.elements else ("", "html", False)
        text_point = namespace == "math" and parent in MATH_TEXT_INTEGRATION
        breakout = tag in HTML_BREAKOUT or (tag == "font" and any(
            key in ("color", "face", "size") for key, _ in attrs))
        if namespace != "html" and not html_point and not text_point and breakout:
            self.leave_foreign_content()
            parent, namespace, html_point = self.elements[-1] if self.elements else ("", "html", False)
            text_point = namespace == "math" and parent in MATH_TEXT_INTEGRATION
        if html_point or (text_point and tag not in ("mglyph", "malignmark")):
            namespace = "html"
        if namespace == "html":
            if tag == "svg":
                namespace = "svg"
            elif tag == "math":
                namespace = "math"
        elif namespace == "math" and parent == "annotation-xml" and tag == "svg":
            namespace = "svg"  # this start tag is special even without an encoding
        encoding = next((value or "" for key, value in attrs if key == "encoding"), "")
        html_point = ((namespace == "svg" and tag in HTML_INTEGRATION) or
                      (namespace == "math" and tag == "annotation-xml" and
                       encoding.lower() in ("text/html", "application/xhtml+xml")))
        if namespace != "html" or tag not in {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }:
            self.elements.append((tag, namespace, html_point))
        # HTMLParser decodes attribute references even with convert_charrefs=False.
        for key, value in attrs:
            if key == "style":
                self.escaped |= has_escaped_property(value or "", inline=True)
                break  # browsers use the first duplicate attribute
        if tag == "style" and namespace in ("html", "svg"):
            self.style = []
        elif namespace == "html" and tag in HTML_TEXT_ONLY:
            # Older HTMLParser releases only know script/style raw text. Other
            # text-only elements also contain no tags or style attributes.
            self.set_cdata_mode(tag)
        elif namespace == "html" and tag == "plaintext":
            self.plaintext = True  # even an apparent </plaintext> is just text

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.plaintext:
            return
        self.handle_starttag(tag, attrs)
        # HTML ignores the self-closing flag on a raw-text <style/>.
        namespace = self.elements[-1][1] if self.elements else "html"
        if namespace != "html":
            self.handle_endtag(tag)
        elif tag == "style":
            self.set_cdata_mode(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.plaintext:
            return
        if tag in ("br", "p"):
            self.leave_foreign_content()
        if tag == "style" and self.style is not None:
            css = "".join(self.style)
            self.escaped |= has_escaped_property(css)
            self.style = None
        for i in range(len(self.elements) - 1, -1, -1):
            if self.elements[i][0] == tag:
                del self.elements[i:]
                break

    def handle_data(self, data: str) -> None:
        if self.style is not None:
            self.style.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(unescape("&" + name + ";"))

    def handle_charref(self, name: str) -> None:
        self.handle_data(unescape("&#" + name + ";"))

    def unknown_decl(self, data: str) -> None:
        if self.style is not None and data.startswith("CDATA["):
            self.style.append(data[6:])

    def finish(self) -> None:
        # Python 3.9 leaves an unterminated raw-text element buffered at EOF.
        # Supply only its end tag so its existing CSS text is delivered first.
        if self.style is not None:
            self.feed("</style>")
        self.close()
        if self.style is not None:
            self.handle_endtag("style")


def escaped_property_findings(source: str) -> list[str]:
    """Return a named unsupported-syntax failure, without changing source text."""
    styles = _Styles()
    styles.feed(source)
    styles.finish()
    if styles.escaped:
        return ["escaped CSS property names are unsupported; spell declaration names literally so geometry can be verified"]
    return []
