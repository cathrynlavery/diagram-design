#!/usr/bin/env python3
"""Verify the equal-unit contract for shipped Unit Grid waffle charts.

Usage:
    python3 scripts/verify-unit-grid.py --all
    python3 scripts/verify-unit-grid.py path/to/example-unit-grid.html
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b(?P<attrs>[^>]*)>", re.IGNORECASE)
RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*)/?>", re.IGNORECASE)
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)

# Match declarations, not text-transform or custom-property names. As in the
# waterfall verifier, CSS movement is rejected rather than cascade-resolved.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)\s*:",
    re.IGNORECASE,
)
# Paint is rejected in page CSS for the same reason: the cells carry their own fill.
CSS_PAINTS_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>fill|fill-opacity|opacity|visibility|filter|mask|mask-image|clip-path"
    r"|content-visibility|display(?=\s*:\s*none\b))\s*:",
    re.IGNORECASE,
)
# Children of these are never drawn in place.
UNRENDERED = {"defs", "symbol", "mask", "clippath", "pattern", "marker"}
CONTAINERS = {"svg", "g", "a", "switch"} | UNRENDERED
ANIMATIONS = {"animate", "set", "animatetransform", "animatemotion", "animatecolor"}
HEX_RE = re.compile(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})")
RGB_RE = re.compile(r"rgba?\(([^)]*)\)")


def declarations(style: str | None) -> dict[str, str]:
    pairs = (part.split(":", 1) for part in (style or "").split(";") if ":" in part)
    return {name.strip().lower(): value.replace("!important", "").strip() for name, value in pairs}


def color(value: str | None) -> tuple[float, float, float, float] | None:
    """Literal hex or rgb()/rgba() as RGBA; anything else is unresolvable."""
    value = (value or "").strip().lower()
    if match := HEX_RE.fullmatch(value):
        digits = match.group(1)
        if len(digits) <= 4:
            digits = "".join(digit * 2 for digit in digits)
        channels = [int(digits[i:i + 2], 16) for i in range(0, len(digits), 2)]
        return (*channels[:3], channels[3] / 255 if len(channels) == 4 else 1.0)
    if match := RGB_RE.fullmatch(value):
        parts = [part for part in re.split(r"[\s,/]+", match.group(1)) if part]
        try:
            numbers = [float(part[:-1]) / 100 if part.endswith("%") else float(part) for part in parts]
        except ValueError:
            return None
        if len(numbers) in (3, 4):
            return (*numbers[:3], numbers[3] if len(numbers) == 4 else 1.0)
    return None


def hidden_by(attributes: dict[str, str | None], style: dict[str, str]) -> list[str]:
    """Properties on one element that can hide a cell whatever its fill."""
    found = []
    for prop in ("opacity", "fill-opacity", "visibility", "display", "filter", "mask", "clip-path"):
        for value in (attributes.get(prop), style.get(prop)):
            if value is None:
                continue
            value = value.strip().lower()
            if prop in {"opacity", "fill-opacity"}:
                try:
                    shown = math.isclose(float(value[:-1]) / 100 if value.endswith("%") else float(value), 1.0)
                except ValueError:
                    shown = False
            elif prop == "visibility":
                shown = value in {"visible", "inherit"}
            elif prop == "display":
                shown = value != "none"
            else:
                shown = value == "none"
            if not shown:
                found.append(prop)
    return found


class Presentation(HTMLParser):
    """Read visible value labels and movement carriers without rendering HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.labels: dict[str, list[str]] = {"data-unit-percent": [], "data-unit-count": []}
        self.active_labels: list[tuple[str, str, list[str]]] = []
        self.styles: list[str] = []
        self.in_style = False
        # Inherited fill and hiding properties of the open svg/g/a/switch ancestors.
        self.stack: list[tuple[str, str | None, list[str]]] = []
        self.paints: list[tuple[str | None, str | None, str, list[str]]] = []
        self.later_rects: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        tag_attrs = dict(attributes)
        if tag == "style":
            self.in_style = True
        if tag in {"svg", "g"} or (tag == "rect" and "data-unit-cell" in tag_attrs):
            if "transform" in tag_attrs:
                self.errors.append(f"{tag} transform can move verified unit cells; use explicit coordinates")
            movement = CSS_MOVES_MARK_RE.search(tag_attrs.get("style") or "")
            if movement:
                self.errors.append(f"inline {movement['prop']} can move verified unit cells")
        if tag in ANIMATIONS:
            self.errors.append(f"<{tag}> can repaint or move verified unit cells; draw the final state")
        style = declarations(tag_attrs.get("style"))
        own_fill = style.get("fill") or tag_attrs.get("fill")
        if own_fill is not None and own_fill.strip().lower() == "inherit":
            own_fill = None
        parent_fill, parent_hides = (self.stack[-1][1], self.stack[-1][2]) if self.stack else (None, [])
        hides = parent_hides + hidden_by(tag_attrs, style) + ([tag] if tag in UNRENDERED else [])
        if tag in CONTAINERS:
            self.stack.append((tag, own_fill or parent_fill, hides))
        elif tag == "rect" and "data-unit-cell" in tag_attrs:
            # SVG paints an element with no fill anywhere in its ancestry black.
            fill = own_fill or parent_fill or "#000000"
            self.paints.append((tag_attrs.get("data-unit-index"), tag_attrs.get("data-unit-cell"), fill, hides))
        elif tag == "rect" and self.paints and (own_fill or "").strip().lower() != "none":
            self.later_rects.append(tag_attrs)
        for name in self.labels:
            if name in tag_attrs:
                self.active_labels.append((tag, name, []))

    def handle_startendtag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attributes)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self.in_style = False
        if tag in CONTAINERS and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        for entry in self.active_labels[:]:
            if entry[0] == tag:
                self.labels[entry[1]].append("".join(entry[2]).strip())
                self.active_labels.remove(entry)

    def handle_data(self, data: str) -> None:
        if self.in_style:
            self.styles.append(data)
        for _, _, fragments in self.active_labels:
            fragments.append(data)

    def check(self, filled: int, total: int) -> list[str]:
        for style in self.styles:
            movement = CSS_MOVES_MARK_RE.search(re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL))
            if movement:
                self.errors.append(f"CSS {movement['prop']} can move verified unit cells")
            paint = CSS_PAINTS_MARK_RE.search(re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL))
            if paint:
                self.errors.append(f"CSS {paint['prop']} can repaint or hide verified unit cells")
        self.check_paint()
        if self.labels["data-unit-percent"] != [f"{filled}%"]:
            self.errors.append(f"printed percentage must state {filled}% in one data-unit-percent label")
        wanted = f"{filled} complete · {total - filled} remaining"
        if self.labels["data-unit-count"] != [wanted]:
            self.errors.append(f"printed count must state {wanted!r} in one data-unit-count label")
        return self.errors

    def check_paint(self) -> None:
        """Bind each cell's drawn fill to its declared state."""
        css = re.sub(r"/\*.*?\*/", "", "".join(self.styles), flags=re.DOTALL)
        root = " ".join(re.findall(r":root\s*\{([^}]*)\}", css))
        tokens = {name: color(value) for name, value in declarations(root).items()}
        ink, accent = tokens.get("--ink"), tokens.get("--accent")
        if ink is None or accent is None:
            self.errors.append("page must declare literal --ink and --accent colours in :root to bind cell fills")
            return
        problems: dict[str, list[str]] = {}
        accents = 0
        remaining: set[tuple[float, float, float, float]] = set()
        for index, state, fill, hides in self.paints:
            for prop in dict.fromkeys(hides):
                problems.setdefault(f"hidden by {prop}", []).append(str(index))
            paint = color(fill)
            if state == "filled":
                drawn = paint in {ink, accent}
                accents += paint == accent and accent != ink
            elif state == "empty":
                drawn = paint is not None and paint[3] == 1 and paint not in {ink, accent}
                if drawn:
                    remaining.add(paint)
            else:
                continue
            if not drawn:
                problems.setdefault(f"declared {state} but painted {fill}", []).append(str(index))
        for problem, indices in problems.items():
            self.errors.append(f"unit cell(s) {', '.join(indices)} {problem}")
        if accents > 1:
            self.errors.append(f"{accents} completed cells use --accent; at most one completed cell may use --accent")
        if len(remaining) > 1:
            self.errors.append("remaining cells must share one fill")


def attrs(source: str) -> dict[str, str]:
    return {match.group("name").lower(): html.unescape(match.group("value"))
            for match in ATTR_RE.finditer(source)}


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
    presentation = Presentation()
    presentation.feed(source)
    findings.extend(f"{path.name}: {error}" for error in presentation.check(filled, total))
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

    def extent(mark: dict[str, str | None], name: str, default: float) -> float:
        try:
            return float(mark.get(name) or default)
        except ValueError:
            return math.inf  # shortcut: percentage sizes count as covering the whole grid
    for mark in presentation.later_rects:
        x, y = extent(mark, "x", 0.0), extent(mark, "y", 0.0)
        width, height = extent(mark, "width", 0.0), extent(mark, "height", 0.0)
        covered = next((index for index, x2, y2, width2, height2, _ in geometry
                        if x < x2 + width2 and x2 < x + width and y < y2 + height2 and y2 < y + height), None)
        if covered is not None:
            findings.append(f"{path.name}: a later <rect> covers unit cell {covered}; draw annotations outside the grid")
            break

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
