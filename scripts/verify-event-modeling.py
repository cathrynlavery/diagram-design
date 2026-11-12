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


# ASCII-only SVG path tokens; float() alone would accept 2_24 and non-ASCII digits that browsers reject.
PATH_TOKEN = re.compile(r"[MLHV]|[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
PATH_SEPARATORS = re.compile(r"[ \t\n\r\f,]*")


def path_points(source: str) -> list[tuple[float, float]]:
    """Points of an absolute M/L/H/V path; empty for anything else."""
    if not PATH_SEPARATORS.fullmatch(PATH_TOKEN.sub(" ", source)):
        return []
    fields = PATH_TOKEN.findall(source)
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
        if any(not math.isfinite(value) for value in (x, y)):
            return []
        points.append((x, y))
    return points


def cell_rect(element: ET.Element) -> tuple[float, float, float, float] | None:
    rect = next((child for child in element if local(child.tag) == "rect"), None)
    return None if rect is None else rectangle(rect)


def widen(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    return (box[0] - ARROW_TOLERANCE, box[1] - ARROW_TOLERANCE, box[2] + ARROW_TOLERANCE, box[3] + ARROW_TOLERANCE)


def inside(point: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def crosses(first: tuple[float, float], second: tuple[float, float], box: tuple[float, float, float, float]) -> bool:
    """Whether a segment enters the interior of a box (Liang-Barsky clip)."""
    low, high = 0.0, 1.0
    dx, dy = second[0] - first[0], second[1] - first[1]
    for delta, offset in ((-dx, first[0] - box[0]), (dx, box[2] - first[0]), (-dy, first[1] - box[1]), (dy, box[3] - first[1])):
        if delta == 0:
            if offset <= 0:
                return False
            continue
        ratio = offset / delta
        if delta < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low >= high:
            return False
    return True


def open_head(shaft: list[tuple[float, float]], head: list[tuple[float, float]]) -> bool:
    """An open V whose middle point is the tip, ahead of the shaft end, with one wing on each side."""
    (px, py), (qx, qy) = shaft[-2], shaft[-1]
    run = math.dist(shaft[-2], shaft[-1])
    if run == 0:
        return False
    ux, uy = (qx - px) / run, (qy - py) / run
    first, (tx, ty), last = head
    sides = [ux * (wy - qy) - uy * (wx - qx) for wx, wy in (first, last)]
    return (
        (tx - qx) * ux + (ty - qy) * uy >= 0
        and all((wx - tx) * ux + (wy - ty) * uy < 0 for wx, wy in (first, last))
        and sides[0] * sides[1] < 0
    )


def arrow_follows(
    link: ET.Element, source: ET.Element, target: ET.Element,
    cells: list[tuple[float, float, float, float]],
) -> bool:
    """A shaft from the source cell to the target cell, missing every other cell, with one head at the target end."""
    drawn = [child.get("d", "") for child in link if local(child.tag) == "path"]
    paths = [path_points(data) for data in drawn]
    source_rect, target_rect = cell_rect(source), cell_rect(target)
    if len(paths) != 2 or not all(paths) or source_rect is None or target_rect is None:
        return False
    start, end = widen(source_rect), widen(target_rect)
    hull = (min(start[0], end[0]), min(start[1], end[1]), max(start[2], end[2]), max(start[3], end[3]))
    shaft, head = paths
    length = sum(math.dist(first, second) for first, second in zip(shaft, shaft[1:]))
    others = [cell for cell in cells if cell not in (source_rect, target_rect)]
    return (
        inside(shaft[0], start) and inside(shaft[-1], end) and length >= MIN_ARROW_LENGTH
        and all(inside(point, hull) for points in paths for point in points)
        and not any(crosses(first, second, cell) for first, second in zip(shaft, shaft[1:]) for cell in others)
        and all(math.dist(point, shaft[-1]) <= ARROW_TOLERANCE for point in head)
        and [token for token in PATH_TOKEN.findall(drawn[1]) if token.isalpha()] == ["M", "L", "L"]
        and open_head(shaft, head)
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
    cells = [box for element in svg.iter() if "data-event-kind" in element.attrib
             for box in [cell_rect(element)] if box is not None]
    layout: list[dict[str, tuple[float, float, float, float]]] = []
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
        boxes = {kind: cell_rect(found[0]) for kind, found in elements.items() if len(found) == 1}
        if all(boxes.get(kind) is not None for kind in KINDS):
            layout.append(boxes)
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
            elif not arrow_follows(found[0], elements[from_kind][0], elements[to_kind][0], cells):
                errors.append(f"{stage_id}: {rel} arrow must run from {from_id} to {to_id}")
    if len(layout) == len(stages):
        spans = [(min(box[0] for box in boxes.values()), max(box[2] for box in boxes.values())) for boxes in layout]
        if any(current[0] <= previous[1] for previous, current in zip(spans, spans[1:])):
            errors.append("stage columns must run left to right in stage order")
        for kind in KINDS:
            if len({(boxes[kind][1], boxes[kind][3]) for boxes in layout}) != 1:
                errors.append(f"{kind} cells must share one lane")
        rows = list(KINDS)
        if any(boxes[lower][1] < boxes[upper][3] for boxes in layout for upper, lower in zip(rows, rows[1:])):
            errors.append("lanes must run command, event, read model from top to bottom")
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
