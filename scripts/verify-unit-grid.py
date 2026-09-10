#!/usr/bin/env python3
"""Verify the equal-unit contract for shipped Unit Grid waffle charts.

Usage:
    python3 scripts/verify-unit-grid.py --all
    python3 scripts/verify-unit-grid.py path/to/example-unit-grid.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b(?P<attrs>[^>]*)>", re.IGNORECASE)
RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*)/?>", re.IGNORECASE)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')


def attrs(source: str) -> dict[str, str]:
    return {match.group("name"): match.group("value") for match in ATTR_RE.finditer(source)}


def cells(source: str) -> list[dict[str, str]]:
    return [attrs(match.group("attrs")) for match in RECT_RE.finditer(source)
            if "data-unit-cell" in attrs(match.group("attrs"))]


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    svg = next((attrs(match.group("attrs")) for match in SVG_RE.finditer(source)
                if "data-unit-grid" in attrs(match.group("attrs"))), None)
    if svg is None:
        return [f"{path.name}: missing data-unit-grid root"]
    findings: list[str] = []
    try:
        total = int(svg["data-unit-total"])
        filled = int(svg["data-unit-filled"])
        rows = int(svg["data-unit-rows"])
        columns = int(svg["data-unit-columns"])
    except (KeyError, ValueError):
        return [f"{path.name}: unit-grid metadata must declare integer total, filled, rows, and columns"]
    if (total, rows, columns) != (100, 10, 10):
        findings.append(f"{path.name}: canonical waffle must declare 100 total units in a 10 by 10 grid")
    if not 0 <= filled <= total:
        findings.append(f"{path.name}: filled count {filled} must be within 0..{total}")
    marks = cells(source)
    if len(marks) != total:
        findings.append(f"{path.name}: declares {total} units but has {len(marks)} data-unit-cell marks")
        return findings
    indices: set[int] = set()
    positions: set[tuple[float, float]] = set()
    sizes: set[tuple[float, float]] = set()
    geometry: list[tuple[int, float, float, float, float, str | None]] = []
    rendered_filled = 0
    for mark in marks:
        state = mark.get("data-unit-cell")
        if state not in {"filled", "empty"}:
            findings.append(f"{path.name}: data-unit-cell must be filled or empty")
        elif state == "filled":
            rendered_filled += 1
        try:
            index = int(mark["data-unit-index"])
            x, y = float(mark["x"]), float(mark["y"])
            width, height = float(mark["width"]), float(mark["height"])
        except (KeyError, ValueError):
            findings.append(f"{path.name}: every unit cell needs numeric index and geometry")
            continue
        if not all(math.isfinite(value) for value in (x, y, width, height)) or width <= 0 or height <= 0:
            findings.append(f"{path.name}: every unit cell needs finite positive geometry")
            continue
        indices.add(index)
        positions.add((x, y))
        sizes.add((width, height))
        geometry.append((index, x, y, width, height, state))
    if indices != set(range(total)):
        findings.append(f"{path.name}: unit indices must cover 0 through {total - 1} exactly once")
    if len(positions) != total:
        findings.append(f"{path.name}: unit cells must occupy unique positions")
    if len(sizes) != 1:
        findings.append(f"{path.name}: every unit cell must have identical dimensions")
    if rendered_filled != filled:
        findings.append(f"{path.name}: declares {filled} filled units but renders {rendered_filled}")
    xs = sorted({x for x, _ in positions})
    ys = sorted({y for _, y in positions})
    if len(xs) != columns or len(ys) != rows:
        findings.append(f"{path.name}: unit positions must form a {columns} by {rows} grid")
    elif len(sizes) == 1:
        width, height = next(iter(sizes))
        x_gutters = [right - left - width for left, right in zip(xs, xs[1:])]
        y_gutters = [lower - upper - height for upper, lower in zip(ys, ys[1:])]
        if any(not math.isclose(gutter, 4.0, abs_tol=1e-6) for gutter in x_gutters + y_gutters):
            findings.append(f"{path.name}: rows and columns must use a 4px gutter")

    overlap = False
    for offset, (_, x1, y1, width1, height1, _) in enumerate(geometry):
        for _, x2, y2, width2, height2, _ in geometry[offset + 1:]:
            if x1 < x2 + width2 and x2 < x1 + width1 and y1 < y2 + height2 and y2 < y1 + height1:
                overlap = True
                break
        if overlap:
            break
    if overlap:
        findings.append(f"{path.name}: unit cells must not overlap")

    if len(geometry) == total and indices == set(range(total)):
        reading_order = [mark[0] for mark in sorted(geometry, key=lambda mark: (mark[2], mark[1]))]
        if reading_order != list(range(total)):
            findings.append(f"{path.name}: unit indices must follow left-to-right, top-to-bottom reading order")
        filled_indices = {index for index, *_, state in geometry if state == "filled"}
        if filled_indices != set(range(filled)):
            findings.append(f"{path.name}: filled cells must occupy the first indices in reading order")
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    return sorted(ASSET_DIR.glob("example-unit-grid*.html")) if args.all else [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Unit Grid equal-cell waffle charts.")
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped Unit Grid example")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2
    findings: list[str] = []
    for path in targets(args):
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        findings.extend(check(path))
    if findings:
        print("\n".join(findings))
        return 1
    print(f"OK Unit Grid: {len(targets(args))} file(s) preserve equal unit cells and declared counts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
