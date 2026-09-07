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
    if indices != set(range(total)):
        findings.append(f"{path.name}: unit indices must cover 0 through {total - 1} exactly once")
    if len(positions) != total:
        findings.append(f"{path.name}: unit cells must not overlap at one position")
    if len(sizes) != 1:
        findings.append(f"{path.name}: every unit cell must have identical dimensions")
    if rendered_filled != filled:
        findings.append(f"{path.name}: declares {filled} filled units but renders {rendered_filled}")
    xs = {x for x, _ in positions}
    ys = {y for _, y in positions}
    if len(xs) != columns or len(ys) != rows:
        findings.append(f"{path.name}: unit positions must form a {columns} by {rows} grid")
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
