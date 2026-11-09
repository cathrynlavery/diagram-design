#!/usr/bin/env python3
"""Verify the source, requirement, design, and test links in trace diagrams."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL)
STYLE_RE = re.compile(
    r"<!--.*?(?:-->|$)|<style\b[^>]*>(?P<body>.*?)</style\s*>", re.IGNORECASE | re.DOTALL
)
CSS_COMMENT_OR_STRING_RE = re.compile(
    r"""/\*.*?(?:\*/|$)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""", re.DOTALL
)
CSS_ESCAPE = r"\\(?:[0-9a-fA-F]{1,6}(?:\r\n|[ \t\r\n\f])?|[^\r\n\f])"
CSS_ESCAPE_RE = re.compile(CSS_ESCAPE)
CSS_IDENTIFIER = rf"(?:[\w-]|{CSS_ESCAPE})+"
CSS_ATTRIBUTE_RE = re.compile(
    rf"{CSS_ESCAPE}|\[\s*(?:(?:{CSS_IDENTIFIER}|\*)?\|)?"
    rf"(?P<name>{CSS_IDENTIFIER})\s*(?:[~|^$*]?=|\])"
)
KINDS = {"source": "SRC-", "requirement": "REQ-", "design": "DES-", "test": "TST-"}
RELATIONS = {"derives": "source", "satisfies": "design", "verifies": "test"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def decode_css_escape(match: re.Match[str]) -> str:
    token = match[0][1:]
    if token[0] not in "0123456789abcdefABCDEF":
        return token
    codepoint = int(token.strip(), 16)
    if 0 < codepoint <= 0x10FFFF and not 0xD800 <= codepoint <= 0xDFFF:
        return chr(codepoint)
    return "\ufffd"


def inline_style(node: ET.Element) -> dict[str, str]:
    declarations = CSS_COMMENT_OR_STRING_RE.sub(" ", node.attrib.get("style", ""))
    return {
        CSS_ESCAPE_RE.sub(decode_css_escape, key.strip()).casefold(): value.strip().casefold()
        for key, separator, value in (
            part.partition(":") for part in declarations.split(";")
        )
        if key and separator
    }


def hidden(node: ET.Element) -> bool:
    tag = local(node.tag)
    style = inline_style(node)
    return (
        tag in {"defs", "title", "desc"}
        or node.attrib.get("aria-hidden") == "true"
        or "hidden" in node.attrib
        or node.attrib.get("display") == "none"
        or node.attrib.get("visibility") == "hidden"
        or node.attrib.get("opacity") in {"0", "0.0"}
        or node.attrib.get("fill") in {"none", "transparent"}
        or node.attrib.get("fill-opacity") in {"0", "0.0"}
        or style.get("display") == "none"
        or style.get("visibility") == "hidden"
        or style.get("opacity") in {"0", "0.0"}
        or style.get("fill") in {"none", "transparent"}
        or style.get("fill-opacity") in {"0", "0.0"}
    )


def visible(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    """Read SVG text outside hidden and non-rendering subtrees."""
    ancestor = parents.get(element)
    while ancestor is not None:
        if hidden(ancestor):
            return ""
        ancestor = parents.get(ancestor)

    chunks: list[str] = []

    def walk(node: ET.Element, in_text: bool = False) -> None:
        if hidden(node):
            return
        in_text = in_text or local(node.tag) == "text"
        if in_text and node.text:
            chunks.append(node.text)
        for child in node:
            walk(child, in_text)
            if in_text and child.tail:
                chunks.append(child.tail)

    walk(element)
    return " ".join(" ".join(chunks).split())


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    match = SVG_RE.search(source)
    if not match:
        return ["missing SVG"]
    try:
        svg = ET.fromstring(match.group())
    except ET.ParseError as exc:
        return [f"invalid SVG: {exc}"]
    if svg.attrib.get("data-diagram-type") != "requirement-traceability":
        return ["SVG must declare data-diagram-type=requirement-traceability"]

    errors: list[str] = []
    # Rules targeting structural groups can override the attributes checked below.
    for style in STYLE_RE.finditer(source):
        body = style.group("body")
        if body is None:
            continue
        css = CSS_COMMENT_OR_STRING_RE.sub(" ", body)
        selectors = re.findall(r"([^{}]+)\{", css)
        if any(
            CSS_ESCAPE_RE.sub(decode_css_escape, name).casefold() == "data-trace-row"
            for selector in selectors
            for match in CSS_ATTRIBUTE_RE.finditer(selector)
            if (name := match.group("name")) is not None
        ):
            errors.append("stylesheet must not select data-trace-row")
            break

    parents = {child: parent for parent in svg.iter() for child in parent}
    rows = [element for element in svg.iter() if "data-trace-row" in element.attrib]
    if not 1 <= len(rows) <= 6:
        errors.append("expected 1 to 6 requirement rows")
    ids: set[str] = set()
    row_ids: set[str] = set()
    for row in rows:
        requirement_id = row.attrib["data-trace-row"].strip()
        if "transform" in row.attrib or {"transform", "translate", "rotate", "scale"} & inline_style(row).keys():
            errors.append(f"{requirement_id}: requirement row must not use transform")
        if not requirement_id or requirement_id in row_ids:
            errors.append(f"blank or duplicate requirement row ID: {requirement_id!r}")
        row_ids.add(requirement_id)
        source_ref = row.attrib.get("data-trace-source", "").strip()
        if not source_ref:
            errors.append(f"{requirement_id}: missing source reference")

        by_kind: dict[str, list[ET.Element]] = {kind: [] for kind in KINDS}
        relationships: dict[str, list[ET.Element]] = {rel: [] for rel in RELATIONS}
        for element in row.iter():
            kind = element.attrib.get("data-trace-kind")
            if kind is not None:
                if kind not in by_kind:
                    errors.append(f"{requirement_id}: unknown element kind {kind!r}")
                    continue
                by_kind[kind].append(element)
                element_id = element.attrib.get("data-trace-id", "").strip()
                if not element_id.startswith(KINDS[kind]) or element_id in ids:
                    errors.append(f"{requirement_id}: invalid or duplicate {kind} ID {element_id!r}")
                ids.add(element_id)
                if element_id and element_id not in visible(element, parents):
                    errors.append(f"{requirement_id}: {kind} ID {element_id!r} is not printed")
            rel = element.attrib.get("data-trace-rel")
            if rel is not None:
                if rel not in relationships:
                    errors.append(f"{requirement_id}: unknown relationship {rel!r}")
                else:
                    relationships[rel].append(element)

        if len(by_kind["source"]) != 1 or len(by_kind["requirement"]) != 1:
            errors.append(f"{requirement_id}: needs one source and one requirement")
        if len(by_kind["design"]) > 1 or len(by_kind["test"]) > 1:
            errors.append(f"{requirement_id}: at most one design and one test in an overview row")
        if by_kind["source"] and by_kind["source"][0].attrib.get("data-source-ref") != source_ref:
            errors.append(f"{requirement_id}: source reference does not match row")
        if by_kind["source"] and source_ref not in visible(by_kind["source"][0], parents):
            errors.append(f"{requirement_id}: source citation is not printed")
        if by_kind["requirement"] and by_kind["requirement"][0].attrib.get("data-trace-id") != requirement_id:
            errors.append(f"{requirement_id}: printed requirement cell has a different ID")

        for rel, kind in RELATIONS.items():
            found = relationships[rel]
            if len(found) != 1:
                errors.append(f"{requirement_id}: expected one {rel} relationship")
                continue
            link = found[0]
            missing = link.attrib.get("data-trace-missing") == "true"
            endpoint = by_kind[kind][0].attrib.get("data-trace-id") if by_kind[kind] else None
            if link.attrib.get("data-trace-to") != requirement_id:
                errors.append(f"{requirement_id}: {rel} must target the requirement")
            if missing:
                if rel == "derives" or endpoint or link.attrib.get("data-trace-from"):
                    errors.append(f"{requirement_id}: invalid missing {rel} relationship")
                if not any(term in visible(link, parents).casefold() for term in ("no ", "missing", "open")):
                    errors.append(f"{requirement_id}: missing {rel} relationship needs a visible gap label")
            elif not endpoint or link.attrib.get("data-trace-from") != endpoint:
                errors.append(f"{requirement_id}: {rel} source does not resolve to a {kind} cell")

        for kind, rel_word in (("design", "satisfies"), ("test", "verifies")):
            if by_kind[kind] and rel_word not in visible(by_kind[kind][0], parents).casefold():
                errors.append(f"{requirement_id}: {kind} cell must print {rel_word}")

    headings = visible(svg, parents).casefold()
    for heading in ("source", "requirement", "satisfied by", "verified by"):
        if heading not in headings:
            errors.append(f"missing visible {heading} heading")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check shipped traceability examples")
    args = parser.parse_args()
    paths = sorted(ASSETS.glob("example-requirement-traceability*.html")) if args.all else args.paths
    if not paths:
        parser.error("provide files or --all")
    failed = False
    for path in paths:
        errors = check(path)
        if errors:
            failed = True
            for error in errors:
                print(f"{path}: {error}", file=sys.stderr)
        else:
            print(f"OK {path}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
