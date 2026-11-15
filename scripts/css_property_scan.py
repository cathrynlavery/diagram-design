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
# HTML's foreign-content recovery reparents these starts outside the SVG.
HTML_BREAKOUT = {
    "b", "big", "blockquote", "body", "br", "center", "code", "dd", "div", "dl", "dt",
    "em", "embed", "h1", "h2", "h3", "h4", "h5", "h6", "head", "hr", "i", "img", "li",
    "listing", "menu", "meta", "nobr", "ol", "p", "pre", "ruby", "s", "small", "span",
    "strong", "strike", "sub", "sup", "table", "tt", "u", "ul", "var",
}
HTML_INTEGRATION = {"foreignobject", "desc", "title"}


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


def has_escaped_property(css: str) -> bool:
    """Recognise declaration starts, including nested rule blocks and inline CSS.

    A colon in a selector prelude is followed by a rule block, not a declaration
    terminator. Custom-property values may contain blocks and stay opaque.
    """
    tokens = _tokens(css)
    count = len(tokens)

    def skip_block(i: int) -> int:
        stack = [{"(": ")", "[": "]", "{": "}"}[tokens[i][0]]]
        i += 1
        while i < count and stack:
            value = tokens[i][0]
            if value in ("(", "[", "{"):
                stack.append({"(": ")", "[": "]", "{": "}"}[value])
            elif value == stack[-1]:
                stack.pop()
            i += 1
        return i

    # Scan every rule block, but never function/bracket contents or a custom
    # property's component values. Use a worklist instead of recursion so a
    # deeply nested untrusted stylesheet cannot exhaust Python's call stack.
    blocks = [(0, count)]
    while blocks:
        i, limit = blocks.pop()
        while i < limit:
            if tokens[i][0] in (";", "}"):
                i += 1
                continue
            name, identifier = tokens[i]
            declaration = identifier and i + 1 < limit and tokens[i + 1][0] == ":"
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
                blocks.append((j + 1, end - 1 if end <= count and tokens[end - 1][0] == "}" else end))
                i = end
            else:
                i = j + 1
    return False


class _Styles(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.elements: list[tuple[str, str]] = []
        self.style_foreign = False
        self.style: list[str] | None = None
        self.escaped = False

    def set_cdata_mode(self, elem: str, *args, **kwargs) -> None:
        # HTMLParser otherwise treats SVG <style> as HTML raw text. In foreign
        # content, entities, markup comments and CDATA sections are parsed.
        if elem != "style" or not self.style_foreign:
            # Python 3.14 added an escapable keyword to this parser hook.
            super().set_cdata_mode(elem, *args, **kwargs)

    def leave_foreign_content(self) -> None:
        while self.elements and self.elements[-1][1] == "svg" and self.elements[-1][0] not in HTML_INTEGRATION:
            self.elements.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        parent, namespace = self.elements[-1] if self.elements else ("", "html")
        breakout = tag in HTML_BREAKOUT or (tag == "font" and any(
            key in ("color", "face", "size") for key, _ in attrs))
        if namespace == "svg" and parent not in HTML_INTEGRATION and breakout:
            self.leave_foreign_content()
            parent, namespace = self.elements[-1] if self.elements else ("", "html")
        if namespace == "svg" and parent in HTML_INTEGRATION:
            namespace = "html"  # HTML integration points in foreign content
        if tag == "svg":
            namespace = "svg"
        if namespace != "html" or tag not in {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }:
            self.elements.append((tag, namespace))
        # HTMLParser decodes attribute references even with convert_charrefs=False.
        for key, value in attrs:
            if key == "style":
                self.escaped |= has_escaped_property(value or "")
                break  # browsers use the first duplicate attribute
        if tag == "style":
            self.style = []
            self.style_foreign = namespace == "svg"

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        # HTML ignores the self-closing flag on a raw-text <style/>.
        namespace = self.elements[-1][1] if self.elements else "html"
        if namespace != "html":
            self.handle_endtag(tag)
        elif tag == "style":
            self.set_cdata_mode(tag)

    def handle_endtag(self, tag: str) -> None:
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
