#!/usr/bin/env python3
"""Verify ordered command, event, and read-model stages in shipped examples."""

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
KINDS = {"command": "CMD-", "event": "EVT-", "read-model": "VIEW-"}
LINKS = {"emits": ("command", "event"), "projects": ("event", "read-model")}
# Shafts stop short of the target box so the arrowhead tip lands on its edge.
ARROW_TOLERANCE = 12
MIN_ARROW_LENGTH = 24


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


def path_points(source: str) -> list[tuple[float, float]]:
    """Points of an absolute M/L/H/V path; empty for anything else."""
    fields = source.replace(",", " ").split()
    if len(fields) < 3 or fields[0] != "M":
        return []
    x, y = number(fields[1]), number(fields[2])
    points = [(x, y)]
    index = 3
    while index < len(fields):
        command = fields[index]
        if command == "L" and index + 2 < len(fields):
            x, y = number(fields[index + 1]), number(fields[index + 2])
            index += 3
        elif command in {"H", "V"} and index + 1 < len(fields):
            if command == "H":
                x = number(fields[index + 1])
            else:
                y = number(fields[index + 1])
            index += 2
        else:
            return []
        points.append((x, y))
    return points


def cell_box(element: ET.Element) -> tuple[float, float, float, float] | None:
    rect = next((child for child in element if local(child.tag) == "rect"), None)
    if rect is None:
        return None
    left, top, right, bottom = rectangle(rect)
    return (left - ARROW_TOLERANCE, top - ARROW_TOLERANCE, right + ARROW_TOLERANCE, bottom + ARROW_TOLERANCE)


def inside(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def arrow_follows(link: ET.Element, source: ET.Element, target: ET.Element) -> bool:
    """The first path runs from the source cell to the target cell; every path stays between them."""
    paths = [path_points(child.get("d", "")) for child in link if local(child.tag) == "path"]
    start, end = cell_box(source), cell_box(target)
    if not paths or not all(paths) or start is None or end is None:
        return False
    hull = (min(start[0], end[0]), min(start[1], end[1]), max(start[2], end[2]), max(start[3], end[3]))
    shaft = paths[0]
    length = sum(math.dist(first, second) for first, second in zip(shaft, shaft[1:]))
    return (
        inside(shaft[0], start) and inside(shaft[-1], end) and length >= MIN_ARROW_LENGTH
        and all(inside(point, hull) for points in paths for point in points)
    )


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    match = SVG_RE.search(source)
    if not match:
        return ["missing SVG"]
    try:
        svg = ET.fromstring(match.group())
    except ET.ParseError as exc:
        return [f"invalid SVG: {exc}"]
    if svg.attrib.get("data-diagram-type") != "event-modeling":
        return ["SVG must declare data-diagram-type=event-modeling"]

    parents = {child: parent for parent in svg.iter() for child in parent}
    errors = check_static_svg(source, svg, parents, "data-event-stage", "data-event-kind", link_attr="data-event-rel")
    stages = [element for element in svg.iter() if "data-event-stage" in element.attrib]
    if not 1 <= len(stages) <= 6:
        errors.append("expected 1 to 6 ordered stages")
    stage_ids: set[str] = set()
    global_ids: set[str] = set()
    for index, stage in enumerate(stages, 1):
        stage_id = stage.attrib["data-event-stage"]
        if not stage_id or stage_id in stage_ids:
            errors.append(f"blank or duplicate stage ID: {stage_id!r}")
        stage_ids.add(stage_id)
        if stage.attrib.get("data-stage-order") != str(index):
            errors.append(f"{stage_id}: stage order must be {index}")
        if stage.attrib.get("data-diagram-role") != "timeframe":
            errors.append(f"{stage_id}: stage role must be timeframe")
        elements = {kind: [] for kind in KINDS}
        links = {rel: [] for rel in LINKS}
        for element in stage.iter():
            kind = element.attrib.get("data-event-kind")
            if kind is not None:
                if kind not in elements:
                    errors.append(f"{stage_id}: unknown kind {kind!r}")
                    continue
                elements[kind].append(element)
                if element.attrib.get("data-diagram-role") != kind:
                    errors.append(f"{stage_id}: {kind} node role must be {kind}")
                element_id = element.attrib.get("data-event-id", "").strip()
                if not element_id.startswith(KINDS[kind]) or element_id in global_ids:
                    errors.append(f"{stage_id}: invalid or duplicate {kind} ID {element_id!r}")
                global_ids.add(element_id)
                if element_id and element_id not in visible(element, parents):
                    errors.append(f"{stage_id}: {kind} ID {element_id!r} is not printed")
            rel = element.attrib.get("data-event-rel")
            if rel is not None:
                if rel not in links:
                    errors.append(f"{stage_id}: unknown link {rel!r}")
                else:
                    links[rel].append(element)
        for kind in KINDS:
            if len(elements[kind]) != 1:
                errors.append(f"{stage_id}: expected one {kind}")
        for rel, (from_kind, to_kind) in LINKS.items():
            found = links[rel]
            if len(found) != 1:
                errors.append(f"{stage_id}: expected one {rel} link")
                continue
            if found[0].attrib.get("data-diagram-role") != "event-link":
                errors.append(f"{stage_id}: {rel} link role must be event-link")
            if len(elements[from_kind]) != 1 or len(elements[to_kind]) != 1:
                continue
            from_id = elements[from_kind][0].attrib.get("data-event-id", "")
            to_id = elements[to_kind][0].attrib.get("data-event-id", "")
            if found[0].attrib.get("data-from") != from_id or found[0].attrib.get("data-to") != to_id:
                errors.append(f"{stage_id}: {rel} endpoints do not match the stage")
            elif not arrow_follows(found[0], elements[from_kind][0], elements[to_kind][0]):
                errors.append(f"{stage_id}: {rel} arrow must run from {from_id} to {to_id}")
    headings = visible(svg, parents).casefold()
    for heading in ("command", "event", "read model", "time moves left to right"):
        if heading not in headings:
            errors.append(f"missing visible {heading} label")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check shipped event-modeling examples")
    args = parser.parse_args()
    paths = sorted(ASSETS.glob("example-event-modeling*.html")) if args.all else args.paths
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
