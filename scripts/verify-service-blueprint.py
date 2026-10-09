#!/usr/bin/env python3
"""Verify the invariants a service blueprint can silently break.

A service blueprint's whole claim is a **shared stage grid split by a line of
visibility**: customer and frontstage sit above it, backstage (and support)
sit below it. Every way of breaking that claim still renders — nothing errors,
and neither `lint-skin.py` nor `verify-geometry.py` reads a cell against the
layer it belongs to or a stage header against the column it occupies.

Each layer group declares `data-layer`, each cell declares `data-stage` plus
`data-name`, and the visibility line declares `data-role="visibility"`. The
checker holds the drawing to those declarations:

1. LAYER ORDER — optional evidence, then customer, frontstage, backstage, then
   optional support, top to bottom. A missing required layer, a duplicate, or
   a row in the wrong vertical order fails closed.
2. VISIBILITY — exactly one `data-role="visibility"` line, spanning the plot,
   sitting between the frontstage row bottom and the backstage row top (±2px),
   with a stroke that clears 3:1 against paper.
3. STAGE GRID — every cell's x matches its stage header; column widths equal;
   gutters equal.
4. CENSUS — every stage has a customer, frontstage, and backstage cell. Empty
   is allowed only with an explicit `—` / `Not applicable` `data-name`.
5. FOCAL — at most one `data-focal="true"` cell.
6. BUDGET — at most 6 stages; no extra `data-layer` values.
7. PRINT — each cell's visible text contains its `data-name`.
8. NO CSS MOTION OF MARKS — `transform` / geometry properties in attributes,
   inline style, or `<style>`.

Usage:
    python3 scripts/verify-service-blueprint.py --all
    python3 scripts/verify-service-blueprint.py skills/diagram-design/assets/example-service-blueprint.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(
    r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL
)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)\s*:",
    re.IGNORECASE,
)
RGBA_RE = re.compile(
    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", re.IGNORECASE
)
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
PAPER_RE = re.compile(r"--color-paper\s*:\s*(#[0-9a-fA-F]{6})")

CANONICAL_LAYERS = ("evidence", "customer", "frontstage", "backstage", "support")
REQUIRED_LAYERS = ("customer", "frontstage", "backstage")
EMPTY_NAMES = frozenset({"—", "-", "not applicable", "n/a"})
MAX_STAGES = 6
GEOMETRY_TOLERANCE = 2.0
WCAG_NON_TEXT = 3.0


def attrs_of(tag_attrs: str) -> dict[str, str]:
    return {m.group("name").lower(): m.group("value") for m in ATTR_RE.finditer(tag_attrs)}


def parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def transform_carrier(attrs: dict[str, str]) -> str | None:
    if "transform" in attrs:
        return f"transform={attrs['transform']!r}"
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(style)
        if found is not None:
            return f"style={style!r} (the {found.group('prop').lower()} property)"
    return None


def transformed_spans(source: str) -> list[tuple[int, int, str]]:
    events: list[tuple[int, int, str | None]] = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        events.append((match.start(), 0, transform_carrier(attrs)))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))

    spans: list[tuple[int, int, str]] = []
    stack: list[tuple[int, str | None]] = []
    for position, kind, how in events:
        if kind == 0:
            stack.append((position, how))
        elif stack:
            start, transformed_by = stack.pop()
            if transformed_by is not None:
                spans.append((start, position, transformed_by))
    for start, transformed_by in stack:
        if transformed_by is not None:
            spans.append((start, len(source), transformed_by))
    return spans


def layer_at(source: str, offset: int) -> str | None:
    stack: list[str | None] = []
    events: list[tuple[int, int, str | None]] = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        events.append((match.start(), 0, attrs.get("data-layer")))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))
    current: str | None = None
    covering: str | None = None
    for position, kind, layer in events:
        if position > offset:
            break
        if kind == 0:
            stack.append(current)
            if layer:
                current = layer
        elif stack:
            current = stack.pop()
        covering = current
    return covering


# Contrast helpers match verify-dumbbell.py (sRGB, WCAG 1.4.11).
def _channel(component: int) -> float:
    fraction = component / 255.0
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(foreground: str, background: str) -> float:
    first, second = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def composite(foreground: str, alpha: float, background: str) -> str:
    fore = [int(foreground.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    back = [int(background.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    blended = [round(fore[i] * alpha + back[i] * (1 - alpha)) for i in range(3)]
    return "#%02x%02x%02x" % tuple(blended)


def parse_hex(color: str) -> str | None:
    value = color.strip()
    if not HEX_RE.match(value):
        return None
    if len(value) == 4:
        return "#" + "".join(ch * 2 for ch in value[1:])
    return value.lower()


def visible_stroke(attrs: dict[str, str], paper: str) -> str | None:
    stroke = attrs.get("stroke")
    if stroke is None:
        return None
    rgba = RGBA_RE.fullmatch(stroke.strip())
    if rgba:
        hex_color = "#%02x%02x%02x" % (
            int(rgba.group(1)),
            int(rgba.group(2)),
            int(rgba.group(3)),
        )
        alpha = float(rgba.group(4))
        return composite(hex_color, alpha, paper)
    parsed = parse_hex(stroke)
    if parsed is None:
        return None
    opacity = parse_number(attrs.get("stroke-opacity") or attrs.get("opacity"))
    if opacity is None:
        opacity = 1.0
    return composite(parsed, opacity, paper)


class Cell:
    __slots__ = ("layer", "stage", "name", "x", "y", "w", "h", "focal", "index")

    def __init__(
        self,
        index: int,
        layer: str,
        stage: str,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        focal: bool,
    ) -> None:
        self.index = index
        self.layer = layer
        self.stage = stage
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.focal = focal

    @property
    def bottom(self) -> float:
        return self.y + self.h


class Header:
    __slots__ = ("stage", "x", "w")

    def __init__(self, stage: str, x: float, w: float) -> None:
        self.stage = stage
        self.x = x
        self.w = w


def parse_marks(
    source: str, errors: list[str]
) -> tuple[list[Header], list[Cell], list[dict[str, str]]]:
    source = COMMENT_RE.sub("", source)
    headers: list[Header] = []
    cells: list[Cell] = []
    visibility: list[dict[str, str]] = []

    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        stage = attrs.get("data-stage")
        name = attrs.get("data-name")
        x = parse_number(attrs.get("x"))
        y = parse_number(attrs.get("y"))
        w = parse_number(attrs.get("width"))
        h = parse_number(attrs.get("height"))
        if stage is None:
            continue
        if x is None or w is None or w <= 0:
            errors.append(
                f"stage {stage!r} mark is missing a finite x/width; the stage grid "
                "cannot be checked"
            )
            continue
        if name is None:
            headers.append(Header(stage, x, w))
            continue
        if y is None or h is None or h <= 0:
            errors.append(
                f"cell {name!r} is missing a finite y/height; layer order cannot be checked"
            )
            continue
        layer = layer_at(source, match.start())
        if layer is None:
            errors.append(
                f"cell {name!r} is not inside a data-layer group; wrap each row "
                "so layer order is declared"
            )
            continue
        focal = attrs.get("data-focal", "").lower() == "true"
        cells.append(Cell(len(cells), layer, stage, name, x, y, w, h, focal))

    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == "visibility":
            visibility.append(attrs)

    return headers, cells, visibility


def check_transforms(source: str, errors: list[str]) -> None:
    source = COMMENT_RE.sub("", source)
    spans = transformed_spans(source)

    def enclosing(offset: int) -> str | None:
        for start, end, how in spans:
            if start <= offset <= end:
                return f"ancestor {how}"
        return None

    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-name" not in attrs and attrs.get("data-role") != "visibility":
            continue
        how = transform_carrier(attrs) or enclosing(match.start())
        if how is not None:
            errors.append(
                f"service-blueprint cell carries {how}; bake the movement into its "
                "coordinates so the verifier checks what the browser draws"
            )

    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") not in {
            "visibility",
            "interaction",
            "internal-interaction",
        }:
            continue
        how = transform_carrier(attrs) or enclosing(match.start())
        if how is not None:
            errors.append(
                f"service-blueprint {attrs.get('data-role')} line carries {how}; bake "
                "the movement into its coordinates so the verifier checks what the "
                "browser draws"
            )

    for match in STYLE_RE.finditer(source):
        found = CSS_MOVES_MARK_RE.search(match.group("body"))
        if found is not None:
            errors.append(
                f"CSS {found.group('prop').lower()!r} declaration can move verified "
                "service-blueprint geometry; bake the movement into the coordinates instead"
            )


def check_layers(cells: list[Cell], errors: list[str]) -> dict[str, list[Cell]]:
    by_layer: dict[str, list[Cell]] = {}
    for cell in cells:
        by_layer.setdefault(cell.layer, []).append(cell)

    unknown = sorted(layer for layer in by_layer if layer not in CANONICAL_LAYERS)
    if unknown:
        errors.append(
            f"budget: extra data-layer values {unknown}; allowed layers are "
            + ", ".join(CANONICAL_LAYERS)
        )

    for required in REQUIRED_LAYERS:
        if required not in by_layer:
            errors.append(
                f"layer order: missing required {required} row; a blueprint needs "
                "customer, frontstage, and backstage"
            )

    present = [layer for layer in CANONICAL_LAYERS if layer in by_layer]
    actual = sorted(
        (layer for layer in by_layer if layer in CANONICAL_LAYERS),
        key=lambda layer: min(cell.y for cell in by_layer[layer]),
    )
    if actual != present:
        errors.append(
            "layer order: rows must run evidence (optional), customer, frontstage, "
            f"backstage, support (optional) top to bottom; found {actual}"
        )
    return by_layer


def check_visibility(
    source: str,
    cells: list[Cell],
    headers: list[Header],
    visibility: list[dict[str, str]],
    errors: list[str],
) -> None:
    if len(visibility) != 1:
        errors.append(
            f"visibility: exactly one data-role=\"visibility\" line is required; "
            f"found {len(visibility)}"
        )
        if not visibility:
            return

    attrs = visibility[0]
    x1 = parse_number(attrs.get("x1"))
    x2 = parse_number(attrs.get("x2"))
    y1 = parse_number(attrs.get("y1"))
    y2 = parse_number(attrs.get("y2"))
    if None in (x1, x2, y1, y2):
        errors.append("visibility: line is missing finite x1/x2/y1/y2 coordinates")
        return
    if abs(y1 - y2) > 1:
        errors.append("visibility: the line must be horizontal across the plot")
    y = (y1 + y2) / 2
    left, right = min(x1, x2), max(x1, x2)
    if headers:
        plot_left = min(header.x for header in headers)
        plot_right = max(header.x + header.w for header in headers)
        if left > plot_left + GEOMETRY_TOLERANCE or right < plot_right - GEOMETRY_TOLERANCE:
            errors.append(
                "visibility: line must span the plot, from the first stage header "
                "to the last"
            )

    front = [cell for cell in cells if cell.layer == "frontstage"]
    back = [cell for cell in cells if cell.layer == "backstage"]
    if front and back:
        front_bottom = max(cell.bottom for cell in front)
        back_top = min(cell.y for cell in back)
        if not (front_bottom - GEOMETRY_TOLERANCE <= y <= back_top + GEOMETRY_TOLERANCE):
            errors.append(
                "visibility: the line must sit between the frontstage row bottom and "
                f"the backstage row top (±{GEOMETRY_TOLERANCE:g}px); drawn at y={y:g}, "
                f"frontstage ends at {front_bottom:g}, backstage starts at {back_top:g}"
            )

    paper_match = PAPER_RE.search(source)
    if paper_match is None:
        errors.append("visibility: contrast cannot be checked without --color-paper")
        return
    paper = paper_match.group(1).lower()
    painted = visible_stroke(attrs, paper)
    if painted is None:
        errors.append("visibility: stroke is not a parseable hex or rgba color")
        return
    ratio = contrast(painted, paper)
    if ratio < WCAG_NON_TEXT:
        errors.append(
            f"visibility: stroke contrast is {ratio:.3f}:1 against paper, under the "
            f"{WCAG_NON_TEXT:.1f}:1 WCAG 1.4.11 asks"
        )


def check_grid(headers: list[Header], cells: list[Cell], errors: list[str]) -> None:
    if not headers:
        errors.append("stage grid: no stage headers declare data-stage")
        return
    seen: dict[str, Header] = {}
    for header in headers:
        if header.stage in seen:
            errors.append(f"stage grid: duplicate stage header {header.stage!r}")
            continue
        seen[header.stage] = header
    ordered = sorted(seen.values(), key=lambda header: header.x)
    if len(ordered) > MAX_STAGES:
        errors.append(
            f"budget: {len(ordered)} stages; at most {MAX_STAGES} stages on one blueprint"
        )
    widths = {round(header.w, 4) for header in ordered}
    if len(widths) > 1:
        errors.append(f"stage grid: column widths must be equal; found {sorted(widths)}")
    if len(ordered) >= 2:
        gutters = [
            round(ordered[i + 1].x - (ordered[i].x + ordered[i].w), 4)
            for i in range(len(ordered) - 1)
        ]
        if len(set(gutters)) > 1:
            errors.append(f"stage grid: gutters must be equal; found {gutters}")
    by_stage = {header.stage: header for header in ordered}
    for cell in cells:
        header = by_stage.get(cell.stage)
        if header is None:
            errors.append(
                f"stage grid: cell {cell.name!r} declares data-stage={cell.stage!r} "
                "with no matching header"
            )
            continue
        if abs(cell.x - header.x) > GEOMETRY_TOLERANCE:
            errors.append(
                f"stage grid: cell {cell.name!r} x={cell.x:g} does not match its "
                f"stage header column at x={header.x:g}"
            )


def check_census(headers: list[Header], cells: list[Cell], errors: list[str]) -> None:
    stages = [header.stage for header in sorted(headers, key=lambda item: item.x)]
    # Unique while preserving order.
    unique_stages: list[str] = []
    for stage in stages:
        if stage not in unique_stages:
            unique_stages.append(stage)
    index = {(cell.layer, cell.stage): cell for cell in cells}
    duplicates = len(cells) - len(index)
    if duplicates:
        errors.append("census: duplicate cells share a layer and stage")
    for stage in unique_stages:
        for layer in REQUIRED_LAYERS:
            cell = index.get((layer, stage))
            if cell is None:
                errors.append(
                    f"census: stage {stage!r} is missing a {layer} cell (empty allowed "
                    "only with an explicit — / Not applicable data-name)"
                )
            elif not cell.name.strip():
                errors.append(
                    f"census: {layer} cell on stage {stage!r} has a blank data-name"
                )


def check_focal(cells: list[Cell], errors: list[str]) -> None:
    focals = [cell for cell in cells if cell.focal]
    if len(focals) > 1:
        errors.append(
            f"focal: at most one cell may set data-focal; found {len(focals)}"
        )


def check_printed(source: str, cells: list[Cell], errors: list[str]) -> None:
    source = COMMENT_RE.sub("", source)
    texts: list[tuple[float, float, str]] = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        x = parse_number(attrs.get("x"))
        y = parse_number(attrs.get("y"))
        if x is None or y is None:
            continue
        body = TAG_RE.sub("", match.group("body"))
        body = (
            body.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
        )
        texts.append((x, y, re.sub(r"\s+", " ", body).strip()))

    for cell in cells:
        collected = [
            body
            for x, y, body in texts
            if cell.x - 1 <= x <= cell.x + cell.w + 1
            and cell.y - 1 <= y <= cell.bottom + 6
        ]
        haystack = " ".join(collected)
        if cell.name not in haystack:
            errors.append(
                f"printed: cell {cell.name!r} has no visible text containing its "
                "data-name"
            )


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    check_transforms(source, errors)
    headers, cells, visibility = parse_marks(source, errors)
    if not cells:
        errors.append(
            "no cells declare data-stage and data-name; the blueprint data contract "
            "is missing"
        )
        return errors
    check_layers(cells, errors)
    check_visibility(source, cells, headers, visibility, errors)
    check_grid(headers, cells, errors)
    check_census(headers, cells, errors)
    check_focal(cells, errors)
    check_printed(source, cells, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify service-blueprint visibility-line grammar and stage grid."
    )
    parser.add_argument("paths", nargs="*", help="service-blueprint example HTML files")
    parser.add_argument(
        "--all",
        action="store_true",
        help="check every shipped example-service-blueprint*.html",
    )
    args = parser.parse_args()

    if args.all:
        paths = sorted(ASSET_DIR.glob("example-service-blueprint*.html"))
        if not paths:
            print(
                "FAIL service-blueprint: --all found no example-service-blueprint*.html "
                "under the skill assets"
            )
            return 2
    elif args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        parser.print_usage()
        return 2

    failed = False
    for path in paths:
        if not path.is_file():
            print(f"FAIL {path}: no such file")
            failed = True
            continue
        findings = verify_file(path)
        if findings:
            failed = True
            print(f"FAIL {path}")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print(f"OK {path}")
    if failed:
        return 1
    print(
        f"OK service-blueprint: {len(paths)} file(s) keep the visibility line on a "
        "shared stage grid"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
