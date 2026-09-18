#!/usr/bin/env python3
"""Export a diagram HTML file to a standalone, inline-safe SVG.

Ships inside the skill so an installed agent can produce a portable SVG without
re-deriving the transform:

    python3 <skill-dir>/scripts/export_svg.py my-diagram.html
    python3 <skill-dir>/scripts/export_svg.py my-diagram.html out.svg

Fixes the two export gaps that make a fragment unsafe to open or inline:

1. Class-styled diagrams keep their page ``<style>`` rules by embedding a
   scoped copy inside the SVG (otherwise every shape falls back to black).
2. Referenceable ``<defs>`` IDs (markers, patterns, gradients, …) are prefixed
   with the file slug so several exported figures can share one host document
   without ``url(#arrow)`` resolving to the wrong declaration.

The algorithm matches ``references/export.md``. No third-party deps.
"""

from __future__ import annotations

import argparse
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
CHROME_SELECTOR_RE = re.compile(
    r"^(?:"
    r"\*|html|body|main|header|footer|h1|h2|h3|p"
    r"|svg"  # bare `svg { min-width: … }` — layout for the HTML page only
    r"|\.frame|\.eyebrow|\.summary|\.cards?|\.card|\.footer|\.header"
    r")(?:\s|:|,|$)",
    re.IGNORECASE,
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


def ensure_xmlns(svg: str) -> str:
    if re.search(r'\bxmlns\s*=\s*["\']http://www\.w3\.org/2000/svg["\']', svg):
        return svg
    return re.sub(r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"', svg, count=1)


def ensure_viewbox(svg: str) -> None:
    if not re.search(r"\bviewBox\s*=", svg, re.IGNORECASE):
        raise ValueError("SVG is missing a viewBox; refuse to guess")


def set_root_id(svg: str, root_id: str) -> str:
    """Put `id="{root_id}"` on the opening <svg> tag (replace any existing id)."""

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        if re.search(r"\bid\s*=", tag, re.IGNORECASE):
            tag = re.sub(r'\bid\s*=\s*("[^"]*"|\'[^\']*\')', f'id="{root_id}"', tag, count=1)
        else:
            tag = tag[:-1] + f' id="{root_id}">'
        return tag

    return re.sub(r"<svg\b[^>]*>", repl, svg, count=1, flags=re.IGNORECASE)


def is_chrome_selector(selector: str) -> bool:
    parts = [part.strip() for part in selector.split(",") if part.strip()]
    if not parts:
        return True
    return all(CHROME_SELECTOR_RE.match(part) is not None for part in parts)


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
        elif part.startswith("#"):
            # Already an ID selector — leave alone (title/desc IDs stay global).
            scoped.append(part)
        else:
            scoped.append(f"#{root_id} {part}")
    return ", ".join(scoped)


def escape_css_for_xml(css: str) -> str:
    """Escape XML-sensitive characters in CSS embedded inside an SVG <style>."""
    # Order matters: amp first so we do not re-escape entities we just wrote.
    return css.replace("&", "&amp;").replace("<", "&lt;")


def diagram_css_from_html(html: str, root_id: str) -> str:
    """Filter page <style> rules down to diagram rules, scoped under root_id."""
    kept: list[str] = []
    for block in STYLE_BLOCK_RE.findall(html):
        for match in RULE_RE.finditer(block):
            selector = " ".join(match.group(1).split())
            body = match.group(2).strip()
            if not selector or not body:
                continue
            if is_chrome_selector(selector):
                continue
            # Escape rule text before it lands in SVG XML (e.g. content:"R&D").
            kept.append(
                escape_css_for_xml(f"{scope_selector(selector, root_id)} {{ {body} }}")
            )
    return "\n      ".join(kept)


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

    # No defs yet — insert one right after the opening svg tag (after title/desc
    # would also be fine; putting defs first keeps markers available).
    open_match = re.match(r"<svg\b[^>]*>", svg, re.IGNORECASE)
    assert open_match is not None
    insert_at = open_match.end()
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
            rf"url\(\s*#\s*{re.escape(old)}\s*\)",
            f"url(#{new})",
            svg,
            flags=re.IGNORECASE,
        )
        svg = re.sub(
            rf"""((?:xlink:)?href\s*=\s*['"])#{re.escape(old)}(['"])""",
            rf"\1#{new}\2",
            svg,
            flags=re.IGNORECASE,
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
    svg = extract_first_svg(html)
    ensure_viewbox(svg)
    svg = ensure_xmlns(svg)
    svg = set_root_id(svg, root_id)
    diagram_css = diagram_css_from_html(html, root_id)
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
