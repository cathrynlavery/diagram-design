#!/usr/bin/env python3
"""Export a diagram HTML file to a standalone, inline-safe SVG.

Ships inside the skill so an installed agent can produce a portable SVG without
re-deriving the transform:

    python3 <skill-dir>/scripts/export_svg.py my-diagram.html
    python3 <skill-dir>/scripts/export_svg.py my-diagram.html out.svg

Fixes the export gaps that make a fragment unsafe to open or inline:

1. Class-styled diagrams keep their page ``<style>`` rules by embedding a
   scoped copy inside the SVG (otherwise every shape falls back to black).
2. Referenceable ``<defs>`` IDs (markers, patterns, gradients, …) are prefixed
   with the file slug so several exported figures can share one host document
   without ``url(#arrow)`` resolving to the wrong declaration.
3. HTML-only attribute syntax (``<g data-motion-item>``, ``data-step=1``) is
   rewritten as XML so the standalone file parses.

The algorithm matches ``references/export.md``. No third-party deps.
"""

from __future__ import annotations

import argparse
import math
import html as html_entities
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable, Iterator

GOOGLE_FONTS_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1"
    "&amp;family=Geist:wght@400;500;600"
    "&amp;family=Geist+Mono:wght@400;500;600"
    "&amp;family=Noto+Serif:ital@0;1"
    "&amp;family=Noto+Sans+KR:wght@400;500;600"
    "&amp;family=Noto+Serif+KR:wght@400"
    "&amp;family=Noto+Sans+TC:wght@400;500;600"
    "&amp;family=Noto+Serif+TC:wght@400"
    "&amp;display=swap');"
)

# Page chrome that must not follow a diagram fragment out of its host document.
# The bare `svg { width; min-width }` rule is page layout too (see
# is_chrome_selector); `svg .zone` and `svg text` are diagram rules.
CHROME_SELECTOR_RE = re.compile(
    r"^(?:"
    r"\*|html|body|main|header|footer|h1|h2|h3|p"
    r"|\.frame|\.eyebrow|\.summary|\.cards?|\.card|\.footer|\.header"
    r")(?:\s|:|,|$)",
    re.IGNORECASE,
)
# A selector that starts at the <svg> element: `svg .zone`, `svg text`, `svg>g`.
SVG_TYPE_PREFIX_RE = re.compile(r"^svg(?![\w-])", re.IGNORECASE)
# Inherited properties the page sets on `body` that SVG content relies on:
# `stroke="currentColor"` reads `color`, and text without its own font rule
# reads `font-family`.
BODY_INHERITED_RE = re.compile(r"(?:^|;)\s*(color|font-family)\s*:\s*([^;]+)", re.IGNORECASE)
# Strings and escapes consume their comment-looking text before comments do.
CSS_COMMENT_OR_LITERAL_RE = re.compile(
    r'''"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|\\[\s\S]|/\*.*?\*/''',
    re.DOTALL,
)


def strip_css_comments(css: str) -> str:
    """Remove CSS comments while preserving quoted and escaped literals."""
    return CSS_COMMENT_OR_LITERAL_RE.sub(
        lambda token: "" if token.group(0).startswith("/*") else token.group(0), css
    )

# HTML-only attribute syntax that strict XML rejects: a valueless attribute
# (`<g data-motion-item>`) or an unquoted value (`data-step=1`).
XML_OPAQUE_OPEN_RE = re.compile(r"<!--|<!\[CDATA\[")
START_TAG_RE = re.compile(
    r"<([A-Za-z][\w:.-]*)"
    r"((?:\s+[^\s\"'<>/=]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*)"
    r"(\s*/?)>"
)
TAG_ATTR_RE = re.compile(
    r"(\s+)([^\s\"'<>/=]+)(?:(\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?"
)

CSS_URL_ATTRIBUTES = {
    "fill", "stroke", "filter", "clip-path", "mask", "cursor", "marker",
    "marker-start", "marker-mid", "marker-end",
}

DEFS_ID_TAGS = (
    "marker",
    "pattern",
    "linearGradient",
    "radialGradient",
    "filter",
    "clipPath",
    "mask",
    "symbol",
    "g",
    "path",
    "rect",
    "circle",
    "ellipse",
    "line",
    "polyline",
    "polygon",
    "text",
    "image",
    "use",
)

STYLE_BLOCK_RE = re.compile(r"<style\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)
# Opening and closing <svg> tags, so nested icon <svg> elements can be
# balanced instead of ending the diagram at the first </svg>.
SVG_TAG_RE = re.compile(
    r"<svg(?=[\s/>])(?:[^>\"']|\"[^\"]*\"|'[^']*')*>|</svg\s*>", re.IGNORECASE
)
# Consume every tag, including quoted attributes, before checking whether it
# changes the namespace of a style. Tag-looking attribute values are literal.
HTML_TOKEN_RE = re.compile(
    r"<!--.*?(?:-->|$)|<!\[CDATA\[.*?(?:\]\]>|$)|"
    r"<(?P<close>/)?(?P<tag>[A-Za-z][^\s/>]*)"
    r"(?:[^>\"']|\"[^\"]*\"|'[^']*')*>", re.IGNORECASE | re.DOTALL
)
CDATA_SECTION_RE = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
# Each alternative starts on a different character, and a comment cannot run
# past its first "*/", so a failed match backtracks linearly, not
# exponentially (an unfinished final rule followed by many comments).
CSS_RULE_ATOM = r'''(?:/\*(?:[^*]|\*(?!/))*\*/|\\[\s\S]|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|/(?!\*)|[^{}"'\\/])'''
RULE_RE = re.compile(rf"({CSS_RULE_ATOM}+)\{{({CSS_RULE_ATOM}*)\}}", re.DOTALL)

RGBA_ATTR_RE = re.compile(
    r'(fill|stroke)="rgba\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"'
)
TRANSPARENT_ATTR_RE = re.compile(r'(fill|stroke)="transparent"')


def slug_for(path: Path) -> str:
    """Stable ID prefix from the source basename (no extension)."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", path.stem).strip("-")
    if not slug:
        raise ValueError(f"cannot derive an ID slug from {path.name!r}")
    if slug[0].isdigit():
        slug = f"d-{slug}"
    return slug


def html_tokens(source: str) -> Iterator[tuple[re.Match[str], bool, int, int]]:
    """Yield markup with its SVG context and any opaque text body boundaries.

    HTML text elements consume through their end tag without interpreting the
    contents as markup. SVG title/desc remain HTML integration points instead.
    """
    contexts: list[str] = []
    pos = 0
    while token := HTML_TOKEN_RE.search(source, pos):
        name = (token.group("tag") or "").lower()
        in_svg = bool(contexts and contexts[-1] == "svg")
        body_end = end = token.end()
        self_closing = token.group(0).endswith("/>")
        text_element = name in {"script", "style"} or (
            not in_svg and name in {"textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript", "plaintext"}
        )
        if name and not token.group("close") and text_element and not (in_svg and self_closing):
            closing = (None if name == "plaintext" else re.compile(
                r"</" + name + r"(?=[\s/>])(?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
                re.IGNORECASE,
            ).search(source, end))
            body_end = closing.start() if closing else len(source)
            end = closing.end() if closing else len(source)
        elif name in {"svg", "foreignobject", "desc", "title"}:
            if token.group("close"):
                for index in range(len(contexts) - 1, -1, -1):
                    if contexts[index] == name:
                        del contexts[index:]
                        break
            elif not self_closing and (name == "svg" or in_svg):
                contexts.append(name)
        yield token, in_svg, body_end, end
        pos = end


def mask_opaque_html(source: str, *, styles: bool = False) -> str:
    out: list[str] = []
    pos = 0
    for token, _, _, end in html_tokens(source):
        out.append(source[pos:token.start()])
        name = (token.group("tag") or "").lower()
        if not name or (end > token.end() and (styles or name != "style")):
            out.append(" " * (end - token.start()))
        else:
            # Keep tag names and boundaries, but do not expose markup-looking
            # quoted attribute values to consumers of the masked source.
            suffix = "/>" if token.group(0).endswith("/>") else ">"
            attr_start = token.end("tag")
            out.append(source[token.start():attr_start])
            out.append(" " * (token.end() - len(suffix) - attr_start) + suffix)
            out.append(source[token.end():end])
        pos = end
    out.append(source[pos:])
    return "".join(out)


def extract_first_svg(html: str) -> str:
    """Return the first top-level <svg> element, including nested <svg> icons."""
    start = None
    depth = 0
    for tag in SVG_TAG_RE.finditer(mask_opaque_html(html, styles=True)):
        token = tag.group(0)
        if token.startswith("</"):
            if start is None:
                continue
            depth -= 1
            if depth == 0:
                return html[start:tag.end()]
        elif not token.endswith("/>"):
            if start is None:
                start = tag.start()
            depth += 1
    raise ValueError("no <svg> block found in source")


def xml_safe_comments(svg: str) -> str:
    """Make HTML comments valid XML comments; CDATA is copied unchanged.

    HTML allows `--` inside a comment and a body ending in `-`; XML allows
    neither. Each `--` becomes `- -` and a trailing `-` gets a space, so the
    comment text stays readable. Comments that are already valid XML are
    copied byte for byte.
    """
    out: list[str] = []
    pos = 0
    while True:
        opener = XML_OPAQUE_OPEN_RE.search(svg, pos)
        if opener is None:
            out.append(svg[pos:])
            break
        out.append(svg[pos:opener.start()])
        if opener.group(0) == "<!--":
            close_at = svg.find("-->", opener.end())
            if close_at == -1:
                out.append(svg[opener.start():])
                break
            body = svg[opener.end():close_at]
            # Browsers end these comments earlier than the next "-->", so the
            # markup after them is live; rewriting would silently drop it.
            if body.startswith((">", "->")) or "--!>" in body:
                raise ValueError(
                    "exported SVG has a comment a browser closes early "
                    "(<!-->, <!--->, or --!>); fix the comment in the source"
                )
            while "--" in body:
                body = body.replace("--", "- -")
            if body.endswith("-"):
                body += " "
            out.append("<!--" + body + "-->")
            pos = close_at + 3
        else:
            close_at = svg.find("]]>", opener.end())
            stop = len(svg) if close_at == -1 else close_at + 3
            out.append(svg[opener.start():stop])
            pos = stop
            if close_at == -1:
                break
    return "".join(out)


def _xml_start_tag(match: re.Match[str]) -> str:
    def attr(m: re.Match[str]) -> str:
        space, name, equals, value = m.groups()
        if value is None:
            return f'{space}{name}=""'
        if value[0] in "\"'":
            return m.group(0)
        return f'{space}{name}{equals}"{value}"'

    name, attrs, end = match.groups()
    return f"<{name}{TAG_ATTR_RE.sub(attr, attrs)}{end}>"


def _rewrite_start_tags(svg: str, transform: Callable[[re.Match[str]], str]) -> str:
    """Transform actual start tags, preserving comments and CDATA sections."""
    out: list[str] = []
    pos = 0
    while True:
        opener = XML_OPAQUE_OPEN_RE.search(svg, pos)
        text_end = opener.start() if opener else len(svg)
        out.append(START_TAG_RE.sub(transform, svg[pos:text_end]))
        if opener is None:
            break
        closer = "-->" if opener.group(0) == "<!--" else "]]>"
        close_at = svg.find(closer, opener.end())
        stop = len(svg) if close_at == -1 else close_at + len(closer)
        out.append(svg[opener.start() : stop])
        pos = stop
        if close_at == -1:
            break
    return "".join(out)


def xmlify_attributes(svg: str) -> str:
    """Rewrite valueless and unquoted HTML attributes as XML (`attr=""`)."""
    return _rewrite_start_tags(svg, _xml_start_tag)


# HTML named references that browsers decode even without a trailing semicolon.
LEGACY_ENTITY_NAMES = tuple(name for name in html_entities.entities.html5 if not name.endswith(";"))


def normalize_html_entities(svg: str) -> str:
    """Convert named HTML references to XML-safe text without decoding markup."""
    opaque = re.compile(
        r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|"
        r"(?P<opening><(?P<tag>style|script)\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>)"
        r".*?</(?P=tag)\s*>", re.DOTALL | re.IGNORECASE,
    )
    # Terminated names first; then HTML's legacy names, which also decode
    # without a semicolon (longest first, so "&notin" is not read as "&not").
    named = re.compile(
        r"&(?:[A-Za-z][A-Za-z0-9]+;|(?P<legacy>"
        + "|".join(sorted((re.escape(name) for name in LEGACY_ENTITY_NAMES), key=len, reverse=True))
        + r"))"
    )
    tag = re.compile(r"<[A-Za-z/!?](?:[^>\"']|\"[^\"]*\"|'[^']*')*>")

    def replace_entity(match: re.Match[str], in_attribute: bool = False) -> str:
        original = match.group(0)
        if original in ("&amp;", "&lt;", "&gt;", "&apos;", "&quot;"):
            return original
        if match.group("legacy") is not None:
            following = match.string[match.end() : match.end() + 1]
            # HTML leaves these undecoded inside attribute values.
            if in_attribute and (following == "=" or following.isalnum()):
                return original
            decoded = html_entities.entities.html5[match.group("legacy")]
        else:
            decoded = html_entities.entities.html5.get(original[1:])
        if decoded is None:
            return original
        return (html_entities.escape(decoded, quote=True)
                .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))

    def replace_in_attribute(match: re.Match[str]) -> str:
        return replace_entity(match, in_attribute=True)

    def normalize_region(region: str) -> str:
        parts: list[str] = []
        cursor = 0
        for token in tag.finditer(region):
            parts.append(named.sub(replace_entity, region[cursor : token.start()]))
            parts.append(named.sub(replace_in_attribute, token.group(0)))
            cursor = token.end()
        parts.append(named.sub(replace_entity, region[cursor:]))
        return "".join(parts)

    out: list[str] = []
    pos = 0
    for match in opaque.finditer(svg):
        out.append(normalize_region(svg[pos:match.start()]))
        opening = match.group("opening")
        if opening is not None:
            out.append(named.sub(replace_in_attribute, opening) + match.group(0)[len(opening):])
        else:
            out.append(match.group(0))
        pos = match.end()
    out.append(normalize_region(svg[pos:]))
    return "".join(out)


XML_REFERENCE_RE = re.compile(r"&(?:(amp|lt|gt|quot|apos);|#[0-9]+;?|#[xX][0-9A-Fa-f]+;?)")
XML_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def decode_xml_references(value: str) -> str:
    """Decode the references left after normalize_html_entities has run.

    Numeric references follow HTML (so &#128; is the euro sign); legacy names
    that HTML leaves literal in attributes stay literal.
    """
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name:
            return XML_NAMED[name]
        return html_entities.unescape(match.group(0))

    return XML_REFERENCE_RE.sub(replace, value)


def ensure_xmlns(svg: str) -> str:
    opening = START_TAG_RE.match(svg)
    if opening is None or opening.group(1) != "svg":
        raise ValueError("cannot identify SVG root namespace")
    for attribute in TAG_ATTR_RE.finditer(opening.group(2)):
        if attribute.group(2) == "xmlns":
            value = attribute.group(4)
            if value is not None and decode_xml_references(value[1:-1]) == "http://www.w3.org/2000/svg":
                return svg
            raise ValueError("SVG root namespace must be http://www.w3.org/2000/svg")
    return re.sub(r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"', svg, count=1)


def ensure_viewbox(svg: str) -> None:
    opening = START_TAG_RE.match(svg)
    raw = next(
        (attr.group(4) for attr in TAG_ATTR_RE.finditer(opening.group(2))
         if attr.group(2) == "viewBox"),
        None,
    ) if opening is not None and opening.group(1).lower() == "svg" else None
    if raw is None:
        raise ValueError("SVG is missing a viewBox; refuse to guess")
    value = decode_xml_references(raw[1:-1] if raw[0] in "\"'" else raw).strip(" \t\r\n")
    number = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
    separator = r"(?:[ \t\r\n]*,[ \t\r\n]*|[ \t\r\n]+)"
    parsed = re.fullmatch(separator.join([f"({number})"] * 4), value)
    if parsed is None:
        raise ValueError("SVG viewBox must contain four finite numbers")
    coordinates = [float(token) for token in parsed.groups()]
    if not all(math.isfinite(token) for token in coordinates) or min(coordinates[2:]) <= 0:
        raise ValueError("SVG viewBox must be finite with positive width and height")


def set_root_id(svg: str, root_id: str) -> str:
    """Put the scoped ID on the actual root id attribute, preserving other data."""
    opening = START_TAG_RE.match(svg)
    assert opening is not None
    name, attrs, end = opening.groups()
    replaced = False

    def replace_attr(attr: re.Match[str]) -> str:
        nonlocal replaced
        if attr.group(2) != "id":
            return attr.group(0)
        replaced = True
        return f'{attr.group(1)}id="{root_id}"'

    attrs = TAG_ATTR_RE.sub(replace_attr, attrs)
    if not replaced:
        attrs += f' id="{root_id}"'
    return f"<{name}{attrs}{end}>" + svg[opening.end():]


def selector_list_parts(selector: str) -> list[str]:
    """Split only selector-list commas, preserving quoted and escaped literals."""
    parts: list[str] = []
    start = 0
    depth = 0
    quote = ""
    pos = 0
    while pos < len(selector):
        char = selector[pos]
        if char == "\\":
            escape = css_escape(selector, pos)
            if escape:
                pos = escape[1]
                continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(selector[start:pos])
            start = pos + 1
        pos += 1
    parts.append(selector[start:])
    return parts


def is_chrome_selector(selector: str) -> bool:
    parts = [part.strip() for part in selector_list_parts(selector) if part.strip()]
    if not parts:
        return True
    return all(
        part.lower() == "svg" or CHROME_SELECTOR_RE.match(part) is not None for part in parts
    )


def css_escape(text: str, pos: int) -> tuple[str, int] | None:
    """Read one CSS identifier escape, including its optional hex terminator."""
    end = pos + 1
    if end == len(text) or text[end] in "\n\r\f":
        return None
    start = end
    while end < min(start + 6, len(text)) and text[end] in "0123456789abcdefABCDEF":
        end += 1
    if end == start:
        return text[end], end + 1
    code = int(text[start:end], 16)
    value = chr(code) if 0 < code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else "\ufffd"
    if end < len(text) and text[end] in " \t\n\r\f":
        end += 2 if text[end:end + 2] == "\r\n" else 1
    return value, end


def decoded_css_url_fragment(fragment: str) -> str:
    """Decode valid CSS escapes before comparing a local fragment with an ID."""
    decoded: list[str] = []
    pos = 0
    while pos < len(fragment):
        if fragment[pos] == "\\":
            escaped = css_escape(fragment, pos)
            if escaped is None:
                return fragment
            value, pos = escaped
            decoded.append(value)
        else:
            decoded.append(fragment[pos])
            pos += 1
    return "".join(decoded)


def css_id_token(text: str, pos: int) -> tuple[str, int] | None:
    """Read a whole valid CSS ID selector after '#', decoding identifier escapes."""
    def starts_name(index: int) -> bool:
        char = text[index:index + 1]
        return bool(char) and (char in "_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                               or ord(char) >= 128
                               or (char == "\\" and css_escape(text, index) is not None))

    if not starts_name(pos) and not (text[pos:pos + 1] == "-"
            and (starts_name(pos + 1) or text[pos + 1:pos + 2] == "-")):
        return None
    out: list[str] = []
    while pos < len(text):
        char = text[pos]
        if char == "\\":
            escaped = css_escape(text, pos)
            if escaped is None:
                break
            value, pos = escaped
            out.append(value)
        elif char in "_-abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" or ord(char) >= 128:
            out.append(char)
            pos += 1
        else:
            break
    return "".join(out), pos


def root_bound_compound(selector: str, root_id: str) -> bool:
    """Whether the first compound names this root outside attributes/functions."""
    pos = 0
    depth = 0
    quote = ""
    while pos < len(selector):
        char = selector[pos]
        if char == "\\":
            escaped = css_escape(selector, pos)
            pos = escaped[1] if escaped else pos + 1
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        elif depth == 0 and (char.isspace() or char in ">+~"):
            break
        elif depth == 0 and char == "#":
            token = css_id_token(selector, pos + 1)
            if token:
                value, pos = token
                if value == root_id:
                    return True
                continue
        pos += 1
    return False


def scope_selector(selector: str, root_id: str) -> str:
    scoped: list[str] = []
    for part in selector_list_parts(selector):
        part = part.strip()
        if not part:
            continue
        if part == ":root" or part.startswith(":root"):
            # `:root { … }` and rare `:root .x` → bind tokens to the SVG root.
            remainder = part[len(":root") :].strip()
            scoped.append(f"#{root_id}" + (f" {remainder}" if remainder else ""))
        elif root_bound_compound(part, root_id):
            # A compound such as `.diagram#root` already names the SVG itself.
            scoped.append(part)
        elif part.startswith("#"):
            # Already an ID selector — leave alone (title/desc IDs stay global).
            scoped.append(part)
        elif SVG_TYPE_PREFIX_RE.match(part):
            # The exported root is the <svg> itself, so `svg .zone` becomes
            # `#root .zone` (`#root svg .zone` would match nothing). A bare
            # `svg` in a mixed list is page layout and is dropped.
            rest = part[len("svg") :]
            if rest:
                scoped.append(f"#{root_id}{rest}")
        else:
            scoped.append(f"#{root_id} {part}")
    return ", ".join(scoped)


def body_inherited_css(selector: str, body: str, root_id: str) -> str:
    """Bind `color` / `font-family` from a dropped `body` rule to the SVG root."""
    parts = [part.strip().lower() for part in selector_list_parts(selector)]
    if "body" not in parts:
        return ""
    declarations = [
        f"{name.lower()}: {value.strip()}" for name, value in BODY_INHERITED_RE.findall(body)
    ]
    if not declarations:
        return ""
    return f"#{root_id} {{ {'; '.join(declarations)}; }}"


def escape_css_for_xml(css: str) -> str:
    """Escape XML-sensitive characters in CSS embedded inside an SVG <style>."""
    # Order matters: amp first so we do not re-escape entities we just wrote.
    return css.replace("&", "&amp;").replace("<", "&lt;")


def retarget_root_selector(selector: str, original_id: str, root_id: str) -> str:
    """Retarget whole decoded ID tokens, preserving unrelated escapes and literals."""
    out: list[str] = []
    quote = ""
    pos = 0
    while pos < len(selector):
        char = selector[pos]
        if char == "\\":
            escaped = css_escape(selector, pos)
            end = escaped[1] if escaped else pos + 1
            out.append(selector[pos:end])
            pos = end
            continue
        if quote:
            out.append(char)
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            out.append(char)
        elif char == "#":
            token = css_id_token(selector, pos + 1)
            if token:
                value, end = token
                out.append(f"#{root_id}" if value == original_id else selector[pos:end])
                pos = end
                continue
            out.append(char)
        else:
            out.append(char)
        pos += 1
    return "".join(out)


def _css_blocks(css: str) -> Iterator[tuple[str, str]]:
    """Yield whole balanced rules without flattening nested conditional blocks."""
    start = 0
    opening = -1
    depth = 0
    quote = ""
    escaped = False
    for index, char in enumerate(css):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "{":
            if depth == 0:
                opening = index
            depth += 1
        elif char == "}":
            if depth == 0:
                # Browsers ignore stray closing braces between top-level rules.
                start = index + 1
                continue
            depth -= 1
            if depth == 0:
                yield css[start:opening].strip(), css[opening + 1:index]
                start = index + 1
        elif char == ";" and depth == 0:
            # Statement at-rules are not diagram paint rules.
            start = index + 1
    if depth or quote:
        raise ValueError("diagram CSS has an unclosed rule or string")


class _CssRule:
    """Source spans plus one cached classification; nested bodies are not copied."""
    def __init__(self, css: str, start: int, opening: int):
        self.css = css
        self.selector = css[start:opening].strip()
        self.start = opening + 1
        self.end = opening + 1
        self.children: list[_CssRule] = []
        self.group = False
        self.statement = False


def _css_rule_tree(css: str) -> list[_CssRule]:
    """Scan braces once, then classify each block once in reverse order."""
    roots: list[_CssRule] = []
    stack: list[_CssRule] = []
    nodes: list[_CssRule] = []
    starts = [0]
    quote = ""
    escaped = False
    parentheses = 0
    for index, char in enumerate(css):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses = max(0, parentheses - 1)
        elif char == "{" and parentheses == 0:
            if len(stack) >= 1024:
                raise ValueError("diagram CSS nesting exceeds the supported limit of 1024 blocks")
            rule = _CssRule(css, starts[-1], index)
            (stack[-1].children if stack else roots).append(rule)
            nodes.append(rule)
            stack.append(rule)
            starts.append(index + 1)
        elif char == "}" and parentheses == 0:
            if stack:
                stack.pop().end = index
                starts.pop()
            starts[-1] = index + 1
        elif char == ";" and parentheses == 0:
            selector = css[starts[-1]:index].strip()
            if re.match(r"@layer\b", selector, re.IGNORECASE):
                rule = _CssRule(css, starts[-1], index)
                rule.statement = True
                # Statement terminators occupy the same end position as a closing brace.
                rule.end = index
                (stack[-1].children if stack else roots).append(rule)
                nodes.append(rule)
            starts[-1] = index + 1
    if stack or quote:
        raise ValueError("diagram CSS has an unclosed rule or string")
    for rule in reversed(nodes):
        selector = rule.selector
        if not rule.statement and selector.startswith("@") and not re.match(r"@(?:(?:-webkit-)?keyframes|font-face)\b", selector, re.IGNORECASE):
            rule.group = bool(re.match(r"@(?:media|supports|layer|container)\b", selector, re.IGNORECASE)) or any(
                not child.selector.startswith("@") or child.group or child.statement
                or re.match(r"@(?:(?:-webkit-)?keyframes|font-face)\b", child.selector, re.IGNORECASE) is not None
                for child in rule.children
            )
    return roots


def _css_rule_nodes(rules: list[_CssRule]) -> Iterator[_CssRule]:
    pending = list(reversed(rules))
    while pending:
        rule = pending.pop()
        yield rule
        if rule.group:
            pending.extend(reversed(rule.children))


def _keyframe_names(rules: list[_CssRule], root_id: str) -> dict[str, str]:
    names: dict[str, str] = {}
    for rule in _css_rule_nodes(rules):
        keyframe = re.fullmatch(r"@(?:-webkit-)?keyframes\s+(.+)", rule.selector, re.IGNORECASE)
        if keyframe is None:
            continue
        name = keyframe.group(1).strip()
        if name[:1] in ("\"", "'") and name[-1:] == name[:1]:
            name = name[1:-1]
        if not re.fullmatch(r"[A-Za-z_][\w-]*", name):
            raise ValueError(f"unsupported CSS keyframe name in SVG export: {rule.selector}")
        names[name] = f"{root_id}-{name}"
    return names


def _css_segments(text: str, separator: str) -> list[str]:
    # Separators inside strings, comments, functions or {} blocks do not split
    # values; a custom property's {...} value is one token stream. Braces count
    # only outside functions, as in _css_rule_tree. A stray closer is ignored;
    # a negative depth would stop all later splitting.
    pieces: list[str] = []
    start, parentheses, braces = 0, 0, 0
    quote = ""
    escaped = False
    comment = False
    index = 0
    while index < len(text):
        char = text[index]
        if comment:
            if text.startswith("*/", index):
                comment = False
                index += 1
        elif escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif text.startswith("/*", index):
            comment = True
            index += 1
        elif char in "\"'":
            quote = char
        elif char == "(":
            parentheses += 1
        elif char == ")":
            parentheses = max(0, parentheses - 1)
        elif char == "{" and parentheses == 0:
            braces += 1
        elif char == "}" and parentheses == 0:
            braces = max(0, braces - 1)
        elif char == separator and parentheses == 0 and braces == 0:
            pieces.append(text[start:index])
            start = index + 1
        index += 1
    pieces.append(text[start:])
    return pieces


def _animation_component(value: str, names: dict[str, str], shorthand: bool) -> str:
    tokens = re.compile(r"/\*.*?\*/|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|(?<![\w.\\-])[-_A-Za-z][\w-]*|[()]", re.DOTALL)
    depth = 0
    replacements: list[tuple[int, int, str]] = []
    found_name = False
    variable = False
    keywords = {"linear", "ease", "ease-in", "ease-out", "ease-in-out", "step-start", "step-end", "infinite", "normal", "reverse", "alternate", "alternate-reverse", "none", "forwards", "backwards", "both", "running", "paused"}
    for match in tokens.finditer(value):
        token = match.group(0)
        if token == "(":
            depth += 1
        elif token == ")":
            depth -= 1
        elif depth == 0 and not token.startswith("/*"):
            quote = token[:1] if token[:1] in ("\"", "'") else ""
            name = token[1:-1] if quote else token
            function = not quote and re.match(r"\s*\(", value[match.end():]) is not None
            variable = variable or (function and name.lower() == "var")
            if function or (not quote and name.lower() == "important"
                            and re.search(r"!\s*$", value[:match.start()])):
                continue
            # Unquoted none disables animation; CSS-wide values reset/inherit it.
            # Quoted spellings are actual keyframe names and must be namespaced.
            if not quote and name.lower() in {"none", "inherit", "initial", "unset", "revert", "revert-layer"}:
                continue
            if name in names:
                if shorthand and not quote and name.lower() in keywords:
                    raise ValueError("ambiguous CSS animation name in SVG export; use animation-name")
                replacements.append((match.start(), match.end(), f"{quote}{names[name]}{quote}"))
                found_name = True
    if "\\" in strip_css_comments(value) or (variable and not found_name):
        raise ValueError("unresolved CSS animation name in SVG export")
    for start, end, replacement in reversed(replacements):
        value = value[:start] + replacement + value[end:]
    return value


def _animation_property(prop: str) -> str:
    # Compare decoded identifiers, retaining the authored spelling in output.
    return decoded_css_url_fragment(strip_css_comments(prop).strip()).lower().removeprefix("-webkit-")


def _has_animation_property(css: str) -> bool:
    # Consume strings before declaration boundaries so property-looking text in
    # content values remains literal. Hex escapes may include one terminator.
    escape = r"\\(?:[0-9a-fA-F]{1,6}(?:\r\n|[ \t\r\n\f])?|[^\r\n\f])"
    tokens = re.compile(CSS_COMMENT_OR_LITERAL_RE.pattern
                        + rf"|(?:^|[;{{])\s*(?P<prop>(?:{escape}|[\w-])+)\s*:", re.DOTALL)
    return any(match.group("prop") is not None
               and _animation_property(match.group("prop")) in ("animation", "animation-name")
               for match in tokens.finditer(css))


def _animation_declarations(body: str, names: dict[str, str]) -> str:
    if not names:
        return body
    segments = _css_segments(body, ";")
    for index, segment in enumerate(segments):
        parts = _css_segments(segment, ":")
        prop, colon, value = parts[0], ":" if len(parts) > 1 else "", ":".join(parts[1:])
        key = _animation_property(prop)
        if colon and key in ("animation", "animation-name"):
            value = ",".join(_animation_component(part, names, key == "animation") for part in _css_segments(value, ","))
            segments[index] = prop + colon + value
    return ";".join(segments)


def namespace_inline_animations(svg: str, names: dict[str, str]) -> str:
    if not names:
        return svg
    if any(re.search(r"@(?:-webkit-)?keyframes\b", block, re.IGNORECASE) or _has_animation_property(block)
                     for block in (strip_css_comments(block) for block in STYLE_BLOCK_RE.findall(svg))):
        raise ValueError("unsupported SVG-local animation stylesheet in SVG export")

    def rewrite_tag(match: re.Match[str]) -> str:
        tag, attrs, end = match.groups()

        def rewrite_attr(attr: re.Match[str]) -> str:
            space, key, equals, value = attr.groups()
            if key == "style" and value is not None:
                quote = value[0]

                def decode_reference(reference: re.Match[str]) -> str:
                    raw = reference.group(0)
                    if raw.startswith("&#"):
                        return html_entities.unescape(raw)
                    return html_entities.entities.html5.get(raw[1:], raw)

                # The HTML source attribute is decoded by its native parser;
                # inspect those CSS literals, then encode once for XML output.
                decoded = re.sub(r"&(?:#(?:[xX][0-9A-Fa-f]+|[0-9]+)|[A-Za-z][A-Za-z0-9]+);", decode_reference, value[1:-1])
                rewritten = _animation_declarations(decoded, names)
                encoded = (html_entities.escape(rewritten, quote=True)
                           .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))
                return space + key + equals + quote + encoded + quote
            return attr.group(0)

        return f"<{tag}{TAG_ATTR_RE.sub(rewrite_attr, attrs)}{end}>"

    return _rewrite_start_tags(svg, rewrite_tag)


def _diagram_css_leaf(rule: _CssRule, root_id: str, names: dict[str, str], original_root_id: str, system_fonts: bool) -> str:
    kept: list[str] = []
    selector = rule.selector.strip()
    if rule.statement:
        return escape_css_for_xml(selector + ";")
    body = rule.css[rule.start:rule.end].strip()
    if not selector or not body:
        return ""
    if re.match(r"@(?:-webkit-)?keyframes\b", selector, re.IGNORECASE):
        prefix, name = selector.rsplit(None, 1)
        quote = name[:1] if name[:1] in ("\"", "'") else ""
        original = name[1:-1] if quote else name
        kept.append(escape_css_for_xml(f"{prefix} {quote}{names[original]}{quote} {{ {body} }}"))
        return "\n      ".join(kept)
    if re.match(r"@font-face\b", selector, re.IGNORECASE):
        if not system_fonts:
            kept.append(escape_css_for_xml(f"{selector} {{ {body} }}"))
        return "\n      ".join(kept)
    if selector.startswith("@"):
        print(f"warning: dropping unsupported CSS block in SVG export: {selector}", file=sys.stderr)
        return "\n      ".join(kept)
    if original_root_id:
        selector = retarget_root_selector(selector, original_root_id, root_id)
    # Preserve quoted whitespace and CSS escape terminators.
    selector = selector.strip()
    # Nested CSS blocks are carried as text, so their declarations cannot be
    # namespaced by the flat declaration rewriter. Refuse rather than break
    # a binding to the keyframes that this export renames.
    if names:
        pending_nested = list(rule.children)
        if any(not re.fullmatch(r"--[\w-]+\s*:", strip_css_comments(child.selector).strip())
               for child in rule.children):
            pending_nested.append(rule)
        while pending_nested:
            nested = pending_nested.pop()
            # Braces in a custom property's value carry tokens, not CSS rules.
            # Do not treat their token subtree as nested animation declarations.
            if re.fullmatch(r"--[\w-]+\s*:", strip_css_comments(nested.selector).strip()):
                continue
            pending_nested.extend(nested.children)
            # Scan direct declarations once; the last prefix segment is the
            # next child selector, not a declaration. Descendants are queued.
            segments: list[str] = []
            cursor = nested.children[0].end + 1 if nested is rule else nested.start
            for child in (nested.children[1:] if nested is rule else nested.children):
                segments.extend(_css_segments(nested.css[cursor:child.start - 1], ";")[:-1])
                cursor = child.end + 1
            segments.extend(_css_segments(nested.css[cursor:nested.end], ";"))
            for segment in segments:
                parts = _css_segments(segment, ":")
                key = _animation_property(parts[0])
                if len(parts) > 1 and key in ("animation", "animation-name"):
                    raise ValueError("unsupported nested CSS animation declaration in SVG export")
    body = _animation_declarations(body, names)
    inherited = body_inherited_css(selector, body, root_id)
    if inherited:
        kept.append(escape_css_for_xml(inherited))
    if is_chrome_selector(selector):
        return "\n      ".join(kept)
    kept.append(escape_css_for_xml(f"{scope_selector(selector, root_id)} {{ {body} }}"))
    return "\n      ".join(kept)


def _diagram_css_rules(rules: list[_CssRule], root_id: str, names: dict[str, str], original_root_id: str = "", system_fonts: bool = False) -> str:
    # Determine empty groups bottom-up, then emit without recursive string copies.
    nodes = list(_css_rule_nodes(rules))
    ordinary: dict[_CssRule, bool] = {}
    for rule in reversed(nodes):
        ordinary[rule] = any(ordinary[child] for child in rule.children) if rule.group else not rule.selector.startswith("@")
    for rule in nodes:
        if rule.group and ordinary[rule] and re.match(r"@scope\b", rule.selector, re.IGNORECASE):
            raise ValueError("unsupported CSS scope with paint rules in SVG export; move paint outside @scope")
    leaves = {rule: _diagram_css_leaf(rule, root_id, names, original_root_id, system_fonts)
              for rule in nodes if not rule.group}
    retained: dict[_CssRule, bool] = {}
    for rule in reversed(nodes):
        retained[rule] = any(retained[child] for child in rule.children) if rule.group else bool(leaves[rule])
    output: list[str] = []

    def siblings(items: list[_CssRule]) -> list[tuple[_CssRule, str]]:
        kept = [rule for rule in items if retained[rule]]
        return list(reversed([(rule, "" if index == 0 else "\n      ")
                              for index, rule in enumerate(kept)]))

    pending: list[tuple[_CssRule, str] | str] = siblings(rules)
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            output.append(item)
            continue
        rule, separator = item
        output.append(separator)
        if rule.group:
            output.append(escape_css_for_xml(rule.selector) + " {\n")
            pending.append("\n}")
            pending.extend(siblings(rule.children))
        else:
            output.append(leaves[rule])
    return "".join(output)


def _html_css_rules(html: str) -> list[_CssRule]:
    rules: list[_CssRule] = []
    for token, in_svg, body_end, _ in html_tokens(html):
        if (token.group("tag") or "").lower() != "style" or token.group("close"):
            continue
        block = html[token.end():body_end]
        if in_svg:
            block = CDATA_SECTION_RE.sub(lambda match: match.group(1), block)
        rules.extend(_css_rule_tree(strip_css_comments(block)))
    return rules


def diagram_css_from_html(html: str, root_id: str, original_root_id: str = "", system_fonts: bool = False) -> str:
    """Carry scoped diagram CSS while retaining its existing media conditions."""
    rules = _html_css_rules(html)
    return _diagram_css_rules(rules, root_id, _keyframe_names(rules, root_id), original_root_id, system_fonts)


def leading_accessibility_end(svg: str, pos: int) -> int:
    """Keep leading title/desc and comments ahead of a newly inserted defs."""
    token = re.compile(r"<!--.*?-->|<title\b[^>]*>|<desc\b[^>]*>", re.DOTALL | re.IGNORECASE)
    while True:
        start = re.match(r"\s*", svg[pos:])
        assert start is not None
        next_pos = pos + start.end()
        opening = token.match(svg, next_pos)
        if opening is None:
            return pos
        if opening.group(0).startswith("<!--"):
            pos = opening.end()
            continue
        name = "title" if opening.group(0).lower().startswith("<title") else "desc"
        endings = re.compile(rf"<!--.*?-->|<!\[CDATA\[.*?\]\]>|</{name}\s*>", re.DOTALL | re.IGNORECASE)
        close = next((match for match in endings.finditer(svg, opening.end()) if match.group(0).startswith("</")), None)
        if close is None:
            return pos
        pos = close.end()


def merge_style_into_defs(svg: str, style_css: str, system_fonts: bool = False) -> str:
    """Ensure one <defs> and place a <style> with fonts + diagram CSS first.

    With system_fonts the Google Fonts @import is left out, so the SVG makes no
    network request and its font stacks fall through to installed faces.
    """
    parts = [] if system_fonts else [GOOGLE_FONTS_IMPORT]
    if style_css.strip():
        parts.append(style_css.strip())
    if not parts:
        return svg
    style_tag = "<style>" + "\n      ".join(parts) + "</style>"

    defs_match = re.search(r"<defs\b[^>]*>", svg, re.IGNORECASE)
    if defs_match:
        insert_at = defs_match.end()
        return svg[:insert_at] + "\n      " + style_tag + svg[insert_at:]

    # Keep the authored first-child title/desc ahead of a newly created defs.
    open_match = re.match(r"<svg\b[^>]*>", svg, re.IGNORECASE)
    assert open_match is not None
    insert_at = leading_accessibility_end(svg, open_match.end())
    return (
        svg[:insert_at]
        + f"\n  <defs>\n      {style_tag}\n  </defs>"
        + svg[insert_at:]
    )


def find_defs_ids(svg: str) -> list[str]:
    """IDs on referenceable elements living under <defs>, including comments."""
    defs_blocks = re.findall(r"<defs\b[^>]*>(.*?)</defs>", svg, re.IGNORECASE | re.DOTALL)
    allowed_tags = {kind.lower() for kind in DEFS_ID_TAGS}
    found: list[str] = []
    seen: set[str] = set()
    for block in defs_blocks:
        for tag in START_TAG_RE.finditer(block):
            name, attrs, _ = tag.groups()
            if name.lower() not in allowed_tags:
                continue
            for attribute in TAG_ATTR_RE.finditer(attrs):
                _, name, _, quoted = attribute.groups()
                if name != "id" or quoted is None or quoted[0] not in "\"'":
                    continue
                ident = decode_xml_references(quoted[1:-1])
                if ident not in seen:
                    seen.add(ident)
                    found.append(ident)
                break
    return found


# Markup that can carry defs references: <style> blocks, tags (attribute
# values), and comments, which may hold an optional commented-out block.
# CDATA and <script> are matched so they are skipped, not rewritten.
REFERENCE_REGION_RE = re.compile(
    r"(?P<skip><!\[CDATA\[.*?\]\]>|<script\b.*?</script\s*>)"
    r"|<!--.*?-->|<style\b[^>]*>.*?</style\s*>"
    r"|<[A-Za-z/?!](?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
    re.IGNORECASE | re.DOTALL,
)


def namespace_defs_ids(svg: str, prefix: str) -> str:
    """Prefix defs IDs and compare each reference after exactly one XML decode.

    Only tags, comments and <style> blocks are rewritten; visible text keeps
    its wording. ID selectors in <style> rules follow the renamed IDs.
    """
    # Match opaque regions in one pass: a comment opener inside CDATA is text.
    live_svg = re.sub(r"<!\[CDATA\[.*?\]\]>|<!--.*?-->", "", svg, flags=re.DOTALL)
    commented_defs_tags = {"marker", "pattern", "lineargradient", "radialgradient", "filter", "clippath", "mask", "symbol"}

    def markup_ids(markup: str, allowed: set[str] | None = None) -> set[str]:
        found: set[str] = set()
        for tag in START_TAG_RE.finditer(markup):
            if allowed is not None and tag.group(1).lower() not in allowed:
                continue
            for attribute in TAG_ATTR_RE.finditer(tag.group(2)):
                _, name, _, quoted = attribute.groups()
                if name == "id" and quoted is not None and quoted[0] in "\"'":
                    found.add(decode_xml_references(quoted[1:-1]))
        return found

    live_defs_tags = {kind.lower() for kind in DEFS_ID_TAGS}
    live_ids = set().union(*(markup_ids(block, live_defs_tags)
        for block in re.findall(r"<defs\b[^>]*>(.*?)</defs>", live_svg, re.IGNORECASE | re.DOTALL)))
    commented_ids = set().union(*(markup_ids(comment, commented_defs_tags)
        for comment in re.findall(r"<!--.*?-->", svg, re.DOTALL)))
    # An optional commented definition must not redirect references to a live
    # element whose ID is left unchanged, even if both happen to use one name.
    unrenamed_live_ids = markup_ids(live_svg) - live_ids
    live_reference_ids = live_ids | (commented_ids - unrenamed_live_ids)
    ids = live_ids | commented_ids
    if not ids:
        return svg
    replacements = {old: html_entities.escape(f"{prefix}-{old}", quote=True) for old in ids}
    live_replacements = {old: replacements[old] for old in live_reference_ids}
    url_ref = re.compile(
        r"(?<![A-Za-z0-9_\\\-\u0080-\U0010ffff])(?i:url)\(\s*(?P<quote>[\"']|&quot;|&apos;|)\s*#\s*"
        r"(?P<ident>.*?)\s*(?P=quote)\s*\)", re.DOTALL,
    )

    raw_url_ref = re.compile(
        r"(?<![A-Za-z0-9_\\\-\u0080-\U0010ffff])(?i:url)\(\s*(?P<quote>[\"']|)\s*#\s*(?P<ident>.*?)\s*(?P=quote)\s*\)", re.DOTALL,
    )

    css_string = re.compile(
        r'''(?:"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*')''', re.DOTALL,
    )

    def rewrite_css_urls(css: str, commented: bool = False) -> str:
        """Consume complete identifiers before considering literal URL functions."""
        out: list[str] = []
        pos = 0
        while pos < len(css):
            if css[pos] in "\"'":
                literal = css_string.match(css, pos)
                end = literal.end() if literal else len(css)
            elif css.startswith("/*", pos):
                closing = css.find("*/", pos + 2)
                end = closing + 2 if closing >= 0 else len(css)
            else:
                token = css_id_token(css, pos)
                if token is not None:
                    _, end = token
                    # Only literal ASCII url(...) is in the supported grammar.
                    # Escape terminator whitespace is part of the identifier.
                    if css[pos:end].lower() == "url" and css[end:end + 1] == "(":
                        reference = raw_url_ref.match(css, pos)
                        if reference is not None:
                            out.append(rewrite_raw_url(reference, commented))
                            pos = reference.end()
                            continue
                else:
                    escaped = css_escape(css, pos) if css[pos] == "\\" else None
                    end = escaped[1] if escaped else pos + 1
            out.append(css[pos:end])
            pos = end
        return "".join(out)

    def rewrite_raw_url(match: re.Match[str], commented: bool = False) -> str:
        # CSS text with XML references already resolved (or CDATA, which has
        # none): compare the decoded CSS identity, preserving its escape
        # spelling when prefixing the reference. The caller XML-escapes.
        ident = decoded_css_url_fragment(match.group("ident"))
        if ident not in (ids if commented else live_reference_ids):
            return match.group(0)
        return f"url({match.group('quote')}#{prefix}-{match.group('ident')}{match.group('quote')})"

    def rewrite_url(match: re.Match[str], commented: bool = False) -> str:
        mapping = replacements if commented else live_replacements
        new = mapping.get(decoded_css_url_fragment(decode_xml_references(match.group("ident"))))
        if new is None:
            return match.group(0)
        return f"url({match.group('quote')}#{prefix}-{match.group('ident')}{match.group('quote')})"

    def rewrite_tag(tag: re.Match[str], commented: bool = False) -> str:
        mapping = replacements if commented else live_replacements
        # SMIL values describe the animated attribute, not the animation tag's
        # own paint. Only supported paint/reference targets carry CSS URLs.
        animation_values = {"set": {"to"}, "animate": {"from", "to", "values", "by"}}
        target = next((decode_xml_references(attr.group(4)[1:-1])
                       for attr in TAG_ATTR_RE.finditer(tag.group(2))
                       if attr.group(2) == "attributeName" and attr.group(4) is not None
                       and attr.group(4)[0] in "\"'"), "")
        animated_attributes = (animation_values.get(tag.group(1), set())
                               if target in CSS_URL_ATTRIBUTES else set())

        def rewrite_css_attribute(raw: str) -> str:
            # XML normalizes original literal whitespace before expanding
            # character references. References to controls must survive the
            # next parse; an amp-escaped reference must stay literal text.
            value = decode_xml_references(re.sub(r"\r\n?|[\n\t]", " ", raw))
            rewritten = rewrite_css_urls(value, commented)
            if rewritten == value:
                return raw
            return (escape_css_for_xml(rewritten).replace('"', "&quot;").replace("'", "&apos;")
                    .replace("\t", "&#9;").replace("\n", "&#10;").replace("\r", "&#13;"))

        def attribute(match: re.Match[str]) -> str:
            space, name, equals, quoted = match.groups()
            if quoted is None or quoted[0] not in "\"'":
                return match.group(0)
            raw = quoted[1:-1]
            value = decode_xml_references(raw)
            if name == "id" and value in replacements and (
                tag.group(1).lower() in commented_defs_tags if commented
                else value in live_ids and tag.group(1).lower() in live_defs_tags
            ):
                raw = replacements[value]
            elif name.lower() in {"href", "xlink:href"} and value.startswith("#") and value[1:] in mapping:
                raw = "#" + mapping[value[1:]]
            elif name.lower() == "style" or name in animated_attributes:
                raw = rewrite_css_attribute(raw)
            elif name.lower() in CSS_URL_ATTRIBUTES:
                raw = url_ref.sub(lambda reference: rewrite_url(reference, commented), raw)
            return space + name + equals + quoted[0] + raw + quoted[-1]

        name, attrs, end = tag.groups()
        return "<" + name + TAG_ATTR_RE.sub(attribute, attrs) + end + ">"

    # A complete tag consumes all quoted values before any URL-like metadata
    # can be considered separately. Every original reference is visited once.
    comment_tokens = re.compile(START_TAG_RE.pattern + "|" + url_ref.pattern, re.DOTALL)

    def rewrite_comment_token(match: re.Match[str]) -> str:
        token = match.group(0)
        tag = START_TAG_RE.fullmatch(token)
        return rewrite_tag(tag, commented=True) if tag is not None else rewrite_url(url_ref.fullmatch(token), commented=True)

    def retarget_style_selectors(region: str) -> str:
        # IDs are already decoded once, so CSS selectors compare against the
        # same value; the renamed token is CSS-escaped, then XML-escaped.
        style = STYLE_BLOCK_RE.fullmatch(region)
        if style is None:
            return url_ref.sub(rewrite_url, region)

        def retarget(css: str) -> str:
            for old in sorted(live_reference_ids, key=len, reverse=True):
                escaped_new = "".join(
                    char if char.isalnum() or char in "_-" or ord(char) >= 128
                    else f"\\{ord(char):x} " if ord(char) < 32 or ord(char) == 127
                    else "\\" + char
                    for char in f"{prefix}-{old}"
                )
                css = RULE_RE.sub(
                    lambda rule, old=old, new=escaped_new: retarget_root_selector(rule.group(1), old, new)
                    + "{" + rule.group(2) + "}",
                    css,
                )
            return rewrite_css_urls(css)

        # CDATA content is raw text: rewrite it inside its markers without XML
        # decoding or escaping. Only the text outside CDATA is XML-decoded and
        # re-escaped.
        content = style.group(1)
        parts: list[str] = []
        pos = 0
        for cdata in CDATA_SECTION_RE.finditer(content):
            parts.append(escape_css_for_xml(retarget(decode_xml_references(content[pos:cdata.start()]))))
            parts.append("<![CDATA[" + retarget(cdata.group(1)) + "]]>")
            pos = cdata.end()
        parts.append(escape_css_for_xml(retarget(decode_xml_references(content[pos:]))))
        # URLs in the style body were rewritten per segment above; only the
        # tags around it still go through the XML-level rewrite.
        return (url_ref.sub(rewrite_url, region[:style.start(1)]) + "".join(parts)
                + url_ref.sub(rewrite_url, region[style.end(1):]))

    def rewrite(region: re.Match[str]) -> str:
        token = region.group(0)
        if region.group("skip"):
            return token
        tag = START_TAG_RE.fullmatch(token)
        if tag is not None:
            return rewrite_tag(tag)
        if token.startswith("<!--"):
            return comment_tokens.sub(rewrite_comment_token, token)
        if token[:6].lower() == "<style":
            return retarget_style_selectors(token)
        return url_ref.sub(rewrite_url, token)

    return REFERENCE_REGION_RE.sub(rewrite, svg)


def _decoded_css_property_text(style: str) -> str:
    """Read opacity spellings conservatively without changing carried CSS."""
    style = strip_css_comments(html_entities.unescape(style))

    def escape(match: re.Match[str]) -> str:
        hexadecimal, literal = match.groups()
        if hexadecimal is not None:
            value = int(hexadecimal, 16)
            return chr(value) if 0 < value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF else "\ufffd"
        return "" if literal in "\r\n\f" else literal

    return re.sub(r"\\(?:([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?|([\s\S]))", escape, style)


def _css_paint_may_target_descendants(selector: str, children: list[ET.Element]) -> bool:
    """Exclude provably unrelated simple selectors; preserve unknown CSS cascades."""
    for branch in selector_list_parts(selector):
        # A hex escape's whitespace terminator belongs to its identifier.
        # Keep escaped branches conservative before splitting combinators.
        if "\\" in branch:
            return True
        terminal = re.split(r"[\s>+~]+", branch.strip())[-1]
        # Unsupported selectors remain conservative, including escaped names,
        # attribute selectors and pseudo-classes that can affect descendant paint.
        if not re.fullmatch(r"(?:[A-Za-z][\w-]*|\*)?(?:[.#][\w-]+)*", terminal) or not terminal:
            return True
        tag = re.match(r"^[A-Za-z][\w-]*", terminal)
        classes = re.findall(r"\.([\w-]+)", terminal)
        ids = re.findall(r"#([\w-]+)", terminal)
        for child in children:
            if tag and child.tag.rsplit("}", 1)[-1] != tag.group(0):
                continue
            if all(name in child.get("class", "").split() for name in classes) and all(
                name == child.get("id") for name in ids
            ):
                return True
    return False


def normalize_rgba_presentation_attrs(svg: str) -> str:
    """Split rgba paint and combine its alpha with existing presentation opacity."""

    # A parent's paint and opacity may be inherited independently. Converting
    # its color alpha into opacity would also change children overriding paint.
    try:
        elements = list(ET.fromstring(svg).iter())
        descendants = {
            index: list(element.iter())[1:]
            for index, element in enumerate(elements) if len(element)
        }
    except ET.ParseError:
        return svg  # The existing final XML validator supplies the public error.
    opacity_counts = {"fill-opacity": 0, "stroke-opacity": 0}
    styles = list(STYLE_BLOCK_RE.findall(svg))

    def collect_opacity_context(match: re.Match[str]) -> str:
        for attr in TAG_ATTR_RE.finditer(match.group(2)):
            key, value = attr.group(2), attr.group(4)
            if key in opacity_counts:
                opacity_counts[key] += 1
            elif key == "style" and value is not None:
                styles.append(value[1:-1])
        return match.group(0)

    _rewrite_start_tags(svg, collect_opacity_context)
    css_opacity = {
        key for key in opacity_counts
        if any(re.search(rf"(?:^|[;{{])\s*{key}\s*:", _decoded_css_property_text(style), re.IGNORECASE)
               for style in styles)
    }

    position = 0

    def normalize_tag(match: re.Match[str]) -> str:
        nonlocal position
        children = descendants.get(position, [])
        element = elements[position]
        position += 1
        name, attrs, end = match.groups()
        values = {
            attr.group(2): attr.group(4)[1:-1]
            for attr in TAG_ATTR_RE.finditer(attrs)
            if attr.group(4) is not None
        }
        updates: dict[str, str] = {}
        additions: list[str] = []
        for prop in ("fill", "stroke"):
            value = values.get(prop, "")
            if value == "transparent":
                updates[prop] = "none"
                continue
            rgba = RGBA_ATTR_RE.fullmatch(f'{prop}="{value}"')
            if rgba is None:
                continue
            _, r, g, b, alpha = rgba.groups()
            opacity_name = f"{prop}-opacity"
            # Presentation opacity may be overridden by CSS or inherited from
            # another element. Preserve the color alpha when that cascade is
            # unresolved instead of replacing it with opaque RGB.
            # Converting a parent is safe when descendants inherit its paint.
            # Preserve alpha if a descendant overrides that paint, including
            # a conservatively detected stylesheet or inline declaration.
            inline_paint = re.search(
                rf"(?:^|[;{{])\s*{prop}\s*:",
                _decoded_css_property_text(element.get("style", "")), re.I,
            )
            descendant_paint = any(
                prop in child.attrib
                or re.search(rf"(?:^|[;{{])\s*{prop}\s*:",
                             _decoded_css_property_text(child.get("style", "")), re.I)
                for child in children
            )
            stylesheet_paint = any(
                re.search(rf"(?:^|[;{{])\s*{prop}\s*:", _decoded_css_property_text(rule.group(2)), re.I)
                and _css_paint_may_target_descendants(rule.group(1), [element] + children)
                for style in STYLE_BLOCK_RE.findall(svg)
                for rule in RULE_RE.finditer(strip_css_comments(style))
            )
            if inline_paint or descendant_paint or stylesheet_paint or opacity_name in css_opacity or opacity_counts[opacity_name] > int(opacity_name in values):
                continue
            opacity = alpha if 0 <= float(alpha) <= 1 else "0" if float(alpha) < 0 else "1"
            if opacity_name in values:
                try:
                    original = values[opacity_name].strip()
                    amount = float(original.rstrip("%")) / (100 if original.endswith("%") else 1)
                except ValueError:
                    continue  # Keep paint intact when the opacity cannot be resolved here.
                if not math.isfinite(amount):
                    continue
                opacity = format(min(1, max(0, amount)) * max(0, min(1, float(alpha))), ".12g")
                updates[opacity_name] = opacity
            else:
                additions.append(f' {opacity_name}="{opacity}"')
            updates[prop] = "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in (r, g, b)))

        def replace_attr(attr: re.Match[str]) -> str:
            space, key, _equals, _value = attr.groups()
            return f'{space}{key}="{updates[key]}"' if key in updates else attr.group(0)

        return f"<{name}{TAG_ATTR_RE.sub(replace_attr, attrs)}{''.join(additions)}{end}>"

    return _rewrite_start_tags(svg, normalize_tag)


def has_diagram_stylesheet(svg: str) -> bool:
    """True when a <style> block contains CSS rules beyond the fonts @import."""
    for block in STYLE_BLOCK_RE.findall(svg):
        stripped = re.sub(r"@import\b[^;]*;", "", block, flags=re.IGNORECASE)
        stripped = strip_css_comments(stripped)
        if RULE_RE.search(stripped):
            return True
    return False


def assert_export_gate(svg: str) -> None:
    """Refuse a class-styled fragment that shipped without diagram CSS.

    A fonts-only <style> (Google Fonts @import with no rules) does not count —
    class-based fills would still render as black boxes.
    """
    uses_classes = False
    for region in REFERENCE_REGION_RE.finditer(svg):
        tag = START_TAG_RE.fullmatch(region.group(0))
        if tag is None:
            continue
        for attribute in TAG_ATTR_RE.finditer(tag.group(2)):
            if attribute.group(2) == "class" and attribute.group(4) is not None:
                uses_classes |= bool(decode_xml_references(attribute.group(4)[1:-1]).strip())
    if uses_classes and not has_diagram_stylesheet(svg):
        raise ValueError(
            "exported SVG uses class= but has no diagram CSS rules; class-based "
            "fills would render as black boxes. Carry the page CSS into the SVG."
        )


def export_svg_document(html: str, source_path: Path, system_fonts: bool = False) -> str:
    """Transform source HTML into a standalone SVG document string."""
    slug = slug_for(source_path)
    root_id = f"{slug}-root"
    svg = normalize_html_entities(xmlify_attributes(extract_first_svg(html)))
    ensure_viewbox(svg)
    svg = ensure_xmlns(svg)
    opening = START_TAG_RE.match(svg)
    assert opening is not None
    # Compare the decoded ID: CSS escapes resolve to characters, not to markup.
    original_root_id = next(
        (decode_xml_references(attr.group(4)[1:-1]) for attr in TAG_ATTR_RE.finditer(opening.group(2))
         if attr.group(2) == "id" and attr.group(4) is not None),
        "",
    )
    svg = set_root_id(svg, root_id)
    rules = _html_css_rules(html)
    names = _keyframe_names(rules, root_id)
    diagram_css = _diagram_css_rules(rules, root_id, names, original_root_id, system_fonts)
    svg = namespace_inline_animations(svg, names)
    svg = merge_style_into_defs(svg, diagram_css, system_fonts)
    svg = namespace_defs_ids(svg, slug)
    svg = xml_safe_comments(svg)
    svg = normalize_rgba_presentation_attrs(svg)
    assert_export_gate(svg)
    document = '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"
    # Catch any remaining XML-breaking characters in carried content.
    try:
        ET.fromstring(document)
    except ET.ParseError as exc:
        raise ValueError(f"exported SVG is not well-formed XML: {exc}") from exc
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export a diagram-design HTML file to a standalone SVG."
    )
    parser.add_argument("source", type=Path, help="Source .html diagram file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help="Output .svg path (default: <source-stem>.svg next to the source)",
    )
    parser.add_argument(
        "--system-fonts",
        action="store_true",
        help="omit the Google Fonts @import so the SVG makes no network request",
    )
    args = parser.parse_args(argv)

    source: Path = args.source
    if not source.is_file():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 2
    if source.name == "index.html" and source.parent.name == "assets":
        print(
            "error: refuse to export the gallery (assets/index.html); "
            "pick a specific diagram file",
            file=sys.stderr,
        )
        return 2

    try:
        html = source.read_text(encoding="utf-8")
        document = export_svg_document(html, source, system_fonts=args.system_fonts)
    except RecursionError:
        print("error: diagram CSS nesting exceeds the supported export depth", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = args.output if args.output is not None else source.with_suffix(".svg")
    try:
        output.write_text(document, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {output}: {exc}", file=sys.stderr)
        return 2
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
