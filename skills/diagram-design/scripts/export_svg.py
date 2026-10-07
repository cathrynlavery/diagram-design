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
import html as html_entities
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

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
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

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

DEFS_ID_TAGS = (
    "marker",
    "pattern",
    "linearGradient",
    "radialGradient",
    "filter",
    "clipPath",
    "mask",
    "symbol",
)

STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
SVG_BLOCK_RE = re.compile(r"<svg\b[^>]*>.*?</svg>", re.IGNORECASE | re.DOTALL)
RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)
RGBA_ATTR_RE = re.compile(
    r'(fill|stroke)="rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d*\.?\d+)\s*\)"'
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


def extract_first_svg(html: str) -> str:
    match = SVG_BLOCK_RE.search(html)
    if not match:
        raise ValueError("no <svg> block found in source")
    return match.group(0)


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


def xmlify_attributes(svg: str) -> str:
    """Rewrite valueless and unquoted HTML attributes as XML (`attr=""`).

    Comments and CDATA sections are copied unchanged.
    """
    out: list[str] = []
    pos = 0
    while True:
        opener = XML_OPAQUE_OPEN_RE.search(svg, pos)
        text_end = opener.start() if opener else len(svg)
        out.append(START_TAG_RE.sub(_xml_start_tag, svg[pos:text_end]))
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


XML_REFERENCE_RE = re.compile(r"&(?:(amp|lt|gt|quot|apos)|#([0-9]+)|#[xX]([0-9A-Fa-f]+));")
XML_NAMED = {"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'"}


def decode_xml_references(value: str) -> str:
    """Decode XML references only, after normalize_html_entities has run.

    Legacy HTML names that HTML leaves literal in attributes stay literal.
    """
    def replace(match: re.Match[str]) -> str:
        name, decimal, hexadecimal = match.groups()
        if name:
            return XML_NAMED[name]
        code = int(decimal) if decimal else int(hexadecimal, 16)
        return chr(code) if 0 < code <= 0x10FFFF else match.group(0)

    return XML_REFERENCE_RE.sub(replace, value)


def ensure_xmlns(svg: str) -> str:
    if re.search(r'\bxmlns\s*=\s*["\']http://www\.w3\.org/2000/svg["\']', svg):
        return svg
    return re.sub(r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"', svg, count=1)


def ensure_viewbox(svg: str) -> None:
    if not re.search(r"\bviewBox\s*=", svg, re.IGNORECASE):
        raise ValueError("SVG is missing a viewBox; refuse to guess")


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


def is_chrome_selector(selector: str) -> bool:
    parts = [part.strip() for part in selector.split(",") if part.strip()]
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
    for part in selector.split(","):
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
    parts = [part.strip().lower() for part in selector.split(",")]
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


def diagram_css_from_html(html: str, root_id: str, original_root_id: str = "") -> str:
    """Filter page <style> rules down to diagram rules, scoped under root_id."""
    kept: list[str] = []
    for block in STYLE_BLOCK_RE.findall(html):
        # A comment before a rule would otherwise become part of its selector
        # (`/* Tokens */ :root` is not recognised as `:root`).
        block = CSS_COMMENT_RE.sub("", block)
        for match in RULE_RE.finditer(block):
            selector = match.group(1).strip()
            if original_root_id:
                selector = retarget_root_selector(selector, original_root_id, root_id)
            # Retarget before collapsing whitespace: a hex escape consumes one
            # terminator, so a second space may be the descendant combinator.
            selector = " ".join(selector.split())
            body = match.group(2).strip()
            if not selector or not body:
                continue
            inherited = body_inherited_css(selector, body, root_id)
            if inherited:
                kept.append(escape_css_for_xml(inherited))
            if is_chrome_selector(selector):
                continue
            # Escape rule text before it lands in SVG XML (e.g. content:"R&D").
            kept.append(
                escape_css_for_xml(f"{scope_selector(selector, root_id)} {{ {body} }}")
            )
    return "\n      ".join(kept)


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


def merge_style_into_defs(svg: str, style_css: str) -> str:
    """Ensure one <defs> and place a <style> with fonts + diagram CSS first."""
    style_inner = GOOGLE_FONTS_IMPORT
    if style_css.strip():
        style_inner = f"{GOOGLE_FONTS_IMPORT}\n      {style_css.strip()}"
    style_tag = f"<style>{style_inner}</style>"

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
    """IDs on referenceable elements living under <defs>."""
    defs_blocks = re.findall(r"<defs\b[^>]*>(.*?)</defs>", svg, re.IGNORECASE | re.DOTALL)
    if not defs_blocks:
        return []
    tag_alt = "|".join(DEFS_ID_TAGS)
    pattern = re.compile(
        rf"<(?:{tag_alt})\b[^>]*\bid\s*=\s*[\"']([^\"']+)[\"']",
        re.IGNORECASE,
    )
    found: list[str] = []
    seen: set[str] = set()
    for block in defs_blocks:
        for match in pattern.finditer(block):
            ident = match.group(1)
            if ident not in seen:
                seen.add(ident)
                found.append(ident)
    return found


def namespace_defs_ids(svg: str, prefix: str) -> str:
    """Prefix defs IDs and rewrite url(#…)/href="#…" references, longest first."""
    ids = find_defs_ids(svg)
    if not ids:
        return svg
    for old in sorted(ids, key=len, reverse=True):
        new = f"{prefix}-{old}"
        svg = re.sub(
            rf'(\bid\s*=\s*[\'"]){re.escape(old)}([\'"])',
            rf"\1{new}\2",
            svg,
        )
        svg = re.sub(
            rf"(?i:url)\(\s*(?P<quote>[\"']|&quot;|&apos;|)\s*#\s*"
            rf"{re.escape(old)}\s*(?P=quote)\s*\)",
            lambda match: f"url({match.group('quote')}#{new}{match.group('quote')})",
            svg,
        )
        svg = re.sub(
            rf"""((?i:(?:xlink:)?href)\s*=\s*['"])#{re.escape(old)}(['"])""",
            rf"\1#{new}\2",
            svg,
        )
    return svg


def normalize_rgba_presentation_attrs(svg: str) -> str:
    """Split rgba()/transparent presentation attrs for strict SVG 1.1 importers."""

    def repl(match: re.Match[str]) -> str:
        prop, r, g, b, a = match.groups()
        return '{0}="#{1:02x}{2:02x}{3:02x}" {0}-opacity="{4}"'.format(
            prop, int(r), int(g), int(b), a
        )

    svg = RGBA_ATTR_RE.sub(repl, svg)
    svg = TRANSPARENT_ATTR_RE.sub(r'\1="none"', svg)
    return svg


def has_diagram_stylesheet(svg: str) -> bool:
    """True when a <style> block contains CSS rules beyond the fonts @import."""
    for block in STYLE_BLOCK_RE.findall(svg):
        stripped = re.sub(r"@import\b[^;]*;", "", block, flags=re.IGNORECASE)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.DOTALL)
        if RULE_RE.search(stripped):
            return True
    return False


def assert_export_gate(svg: str) -> None:
    """Refuse a class-styled fragment that shipped without diagram CSS.

    A fonts-only <style> (Google Fonts @import with no rules) does not count —
    class-based fills would still render as black boxes.
    """
    if re.search(r"\bclass\s*=", svg) and not has_diagram_stylesheet(svg):
        raise ValueError(
            "exported SVG uses class= but has no diagram CSS rules; class-based "
            "fills would render as black boxes. Carry the page CSS into the SVG."
        )


def export_svg_document(html: str, source_path: Path) -> str:
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
    diagram_css = diagram_css_from_html(html, root_id, original_root_id)
    svg = merge_style_into_defs(svg, diagram_css)
    svg = namespace_defs_ids(svg, slug)
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
        document = export_svg_document(html, source)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = args.output if args.output is not None else source.with_suffix(".svg")
    output.write_text(document, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
