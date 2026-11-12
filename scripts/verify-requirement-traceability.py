#!/usr/bin/env python3
"""Verify the source, requirement, design, and test links in trace diagrams."""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from verify_static_svg_visibility import check_static_svg, hidden, local, number, rectangle

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL)
KINDS = {"source": "SRC-", "requirement": "REQ-", "design": "DES-", "test": "TST-"}
RELATIONS = {"derives": "source", "satisfies": "design", "verifies": "test"}
COLUMNS = {"source": "source", "requirement": "requirement", "design": "satisfied by", "test": "verified by"}


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

    parents = {child: parent for parent in svg.iter() for child in parent}
    errors = check_static_svg(source, svg, parents, "data-trace-row", "data-trace-kind", gap_attr="data-trace-missing")
    rows = [element for element in svg.iter() if "data-trace-row" in element.attrib]
    if not 1 <= len(rows) <= 6:
        errors.append("expected 1 to 6 requirement rows")
    ids: set[str] = set()
    row_ids: set[str] = set()
    column_x = {
        label: number(element.get("x", ""))
        for element in svg if local(element.tag) == "text"
        for label in (visible(element, parents).casefold(),) if label in COLUMNS.values()
    }
    for row in rows:
        requirement_id = row.attrib["data-trace-row"].strip()
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

        # A cell shows its link only beside its own requirement and under its own heading.
        bands = set()
        for cell in row.iter():
            kind = cell.attrib.get("data-trace-kind")
            if kind is None and cell.attrib.get("data-trace-missing") == "true":
                kind = RELATIONS.get(cell.attrib.get("data-trace-rel", ""))
            rect = next((child for child in cell if local(child.tag) == "rect"), None)
            if kind not in COLUMNS or rect is None:
                continue
            left, top, right, bottom = rectangle(rect)
            bands.add((top, bottom))
            if not left <= column_x.get(COLUMNS[kind], math.nan) <= right:
                errors.append(f"{requirement_id}: {kind} cell is not under its column heading")
        if len(bands) > 1:
            errors.append(f"{requirement_id}: cells must share one row band; a cell sits outside its row")

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
