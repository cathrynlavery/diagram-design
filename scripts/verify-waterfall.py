#!/usr/bin/env python3
"""Verify the invariants a waterfall chart can silently break.

A waterfall's whole claim is that **the running total is conserved**: a start
total, a sequence of signed bridges, and an end total that reconciles. Every
way of breaking that claim renders perfectly — nothing errors, nothing
disappears, and neither `lint-skin.py` (colors, fonts, a11y) nor
`verify-geometry.py` (label masks vs later-painted nodes) reads a bar against
the arithmetic it participates in.

Each bar declares its role and value (`data-role`, `data-value`, `data-name`)
and each connector declares the running total it transports (`data-carry`).
The checker recomputes the walk from the declarations and holds the drawing to
it:

1. CONSERVATION — start + every signed delta must equal each subtotal and the
   end total, exactly. Declared values are data, so there is no tolerance.
2. SHARED SCALE AND BRIDGE GEOMETRY — the scale is fitted from the start
   anchor (baseline at its bottom, px-per-unit from its height over its
   value). Every total and subtotal must anchor at that baseline, and every
   bridge must span exactly the running totals before and after it, within
   GEOMETRY_TOLERANCE for integer-pixel rounding. Data coordinates round to
   the nearest pixel; they never snap to the 4px layout grid.
3. CARRIES — each gap between adjacent bars must be crossed by exactly one
   horizontal connector drawn at the running total it declares, spanning the
   full gap. A missing carry breaks the walk; a carry at the wrong level
   reconnects it to a different total.
4. PRINTED VALUES — every bar prints its declared value, and a delta prints
   it with an explicit sign. Geometry the reader cannot check against a
   number is taken on trust.
5. SIGN TREATMENT — increases share one fill and decreases another, and the
   two differ, so direction survives greyscale and colour-vision deficiency.
   At most one bar may take the accent focal treatment, which replaces its
   sign fill (the signed label and geometry still carry the direction).

Degenerate data fails closed with a named finding: a start total of zero or
less has no scale to fit, and a zero delta is invisible ink that still
occupies a column.

Usage:
    python3 scripts/verify-waterfall.py --all
    python3 scripts/verify-waterfall.py skills/diagram-design/assets/example-waterfall.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
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

# Integer-pixel rounding on a shared scale cannot miss by more than 0.5px per
# edge; 0.75 leaves headroom for the fit itself while staying far below the
# smallest honest bridge this budget allows.
GEOMETRY_TOLERANCE = 0.75
# A carry must reach both bars it connects. 2px forgives stroke caps, nothing
# more.
CARRY_SPAN_TOLERANCE = 2.0
VALUE_TOLERANCE = 1e-9
MAX_BARS = 8
MAX_SUBTOTALS = 1
ACCENT_STROKES = {"#eb6c36", "#f08a59"}
SIGN_CHARS = {"+": 1.0, "-": -1.0, "\u2212": -1.0}


def attrs_of(tag_attrs: str) -> dict[str, str]:
    return {m.group("name").lower(): m.group("value") for m in ATTR_RE.finditer(tag_attrs)}


def parse_number(raw: str) -> float | None:
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def transform_carrier(attrs: dict[str, str]) -> str | None:
    """Describe an attribute or inline style that can move verified geometry."""
    if "transform" in attrs:
        return f"transform={attrs['transform']!r}"
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(style)
        if found is not None:
            return f"style={style!r} (the {found.group('prop').lower()} property)"
    return None


def transformed_spans(source: str) -> list[tuple[int, int, str]]:
    """Return source spans covered by transformed SVG/group ancestors."""
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


def check_transforms(source: str, errors: list[str]) -> None:
    """Reject transforms that make rendered bar/carry geometry differ from raw coordinates."""
    source = COMMENT_RE.sub("", source)
    spans = transformed_spans(source)

    def enclosing(offset: int) -> str | None:
        for start, end, how in spans:
            if start <= offset <= end:
                return f"ancestor {how}"
        return None

    for pattern, contract_attr, label in (
        (RECT_RE, "data-role", "waterfall bar"),
        (LINE_RE, "data-carry", "waterfall carry"),
    ):
        for match in pattern.finditer(source):
            attrs = attrs_of(match.group("attrs"))
            if contract_attr not in attrs:
                continue
            how = transform_carrier(attrs) or enclosing(match.start())
            if how is not None:
                errors.append(
                    f"{label} carries {how}; bake the movement into its coordinates so "
                    "the verifier checks what the browser draws"
                )

    for match in STYLE_RE.finditer(source):
        found = CSS_MOVES_MARK_RE.search(match.group("body"))
        if found is not None:
            errors.append(
                f"CSS {found.group('prop').lower()!r} declaration can move verified waterfall "
                "geometry; bake the movement into the coordinates instead"
            )


class Bar:
    __slots__ = ("role", "value", "name", "x", "y", "w", "h", "fill", "stroke", "index")

    def __init__(self, index: int, role: str, value: float, name: str,
                 x: float, y: float, w: float, h: float, fill: str, stroke: str) -> None:
        self.index = index
        self.role = role
        self.value = value
        self.name = name
        self.x, self.y, self.w, self.h = x, y, w, h
        self.fill = fill
        self.stroke = stroke

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def label(self) -> str:
        return f"{self.name!r} (bar {self.index + 1})"


def parse_signed(raw: str, *, signed_required: bool) -> tuple[float | None, bool]:
    """Return (value, had_explicit_sign) for a declared or printed value."""
    text = raw.strip()
    if not text:
        return None, False
    sign = SIGN_CHARS.get(text[0])
    if sign is not None:
        magnitude = parse_number(text[1:].strip())
        if magnitude is None:
            return None, True
        return sign * magnitude, True
    if signed_required:
        return parse_number(text), False
    return parse_number(text), False


def parse_bars(source: str, errors: list[str]) -> list[Bar]:
    bars: list[Bar] = []
    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        role = attrs.get("data-role")
        if role is None:
            continue
        if role not in {"total", "delta", "subtotal"}:
            errors.append(f"bar {len(bars) + 1} declares unknown data-role {role!r}")
            continue
        name = attrs.get("data-name", f"#{len(bars) + 1}")
        raw_value = attrs.get("data-value", "")
        value, signed = parse_signed(raw_value, signed_required=(role == "delta"))
        if value is None:
            errors.append(f"{name!r}: data-value {raw_value!r} is not a number")
            continue
        if role == "delta" and not signed:
            errors.append(
                f"{name!r}: a delta must declare an explicit sign in data-value; got {raw_value!r}"
            )
        geometry = [parse_number(attrs.get(key, "")) for key in ("x", "y", "width", "height")]
        if any(v is None for v in geometry):
            errors.append(f"{name!r}: bar rect is missing numeric x/y/width/height")
            continue
        x, y, w, h = geometry  # type: ignore[assignment]
        if w <= 0 or h <= 0 or not all(map(math.isfinite, (x + w, y + h))):
            errors.append(f"{name!r}: bar geometry must have finite edges and positive dimensions")
            continue
        bars.append(
            Bar(len(bars), role, value, name, x, y, w, h,
                attrs.get("fill", ""), attrs.get("stroke", ""))
        )
    return bars


def check_structure(bars: list[Bar], errors: list[str]) -> bool:
    if len(bars) < 3:
        errors.append(f"a waterfall needs a start total, at least one delta, and an end total; found {len(bars)} bars")
        return False
    if len(bars) > MAX_BARS:
        errors.append(f"waterfall exceeds the budget of {MAX_BARS} bars: found {len(bars)}")
    if bars[0].role != "total":
        errors.append(f"the first bar must be the start total; {bars[0].label} declares {bars[0].role!r}")
        return False
    if bars[-1].role != "total":
        errors.append(f"the last bar must be the end total; {bars[-1].label} declares {bars[-1].role!r}")
        return False
    interior = bars[1:-1]
    for bar in interior:
        if bar.role == "total":
            errors.append(f"{bar.label}: an interior resting point is a subtotal, not a total")
            return False
    subtotals = [bar for bar in interior if bar.role == "subtotal"]
    if len(subtotals) > MAX_SUBTOTALS:
        errors.append(
            f"a walk that needs {len(subtotals)} subtotals is two walks; the budget allows {MAX_SUBTOTALS}"
        )
    if not any(bar.role == "delta" for bar in interior):
        errors.append("a waterfall with no delta bars is a bar chart wearing carries")
        return False
    for bar in bars:
        if bar.role in {"total", "subtotal"} and bar.value <= 0:
            errors.append(
                f"{bar.label}: a {bar.role} of {bar.value:g} has no anchored height on this grammar; "
                "totals must be positive"
            )
            return False
        if bar.role == "delta" and bar.value == 0:
            errors.append(f"{bar.label}: a zero delta is dropped, never drawn")
    return True


def running_levels(bars: list[Bar], errors: list[str]) -> list[tuple[float, float]] | None:
    """Return each bar's (level_before, level_after); None when conservation fails."""
    levels: list[tuple[float, float]] = []
    running = bars[0].value
    levels.append((0.0, running))
    conserved = True
    for bar in bars[1:]:
        if bar.role == "delta":
            before = running
            running += bar.value
            if not math.isfinite(running):
                errors.append(f"{bar.label}: the running total must remain finite")
                return None
            levels.append((before, running))
            if running < 0:
                errors.append(
                    f"{bar.label}: the running total falls to {running:g}; this grammar anchors totals "
                    "at a zero floor and cannot draw a negative walk"
                )
                conserved = False
        else:
            if abs(running - bar.value) > VALUE_TOLERANCE:
                errors.append(
                    f"{bar.label}: declares {bar.value:g} but the walk arrives at {running:g}; "
                    "the running total must conserve"
                )
                conserved = False
            levels.append((running, running))
            running = bar.value
    return levels if conserved else None


def check_geometry(bars: list[Bar], levels: list[tuple[float, float]], errors: list[str]) -> tuple[float, float] | None:
    start = bars[0]
    if start.h <= 0:
        errors.append(f"{start.label}: the start anchor has no height; no scale can be fitted")
        return None
    baseline = start.bottom
    scale = start.h / start.value
    for bar, (before, after) in zip(bars, levels):
        if bar.role in {"total", "subtotal"}:
            lo, hi = 0.0, bar.value
        else:
            lo, hi = min(before, after), max(before, after)
        expected_top = baseline - scale * hi
        expected_bottom = baseline - scale * lo
        if scale <= 0 or not all(map(math.isfinite, (scale, expected_top, expected_bottom))):
            errors.append(f"{bar.label}: shared scale and derived geometry must be finite and nonzero")
            return None
        if abs(bar.y - expected_top) > GEOMETRY_TOLERANCE:
            errors.append(
                f"{bar.label}: top edge drawn at y={bar.y:g} but the shared scale puts "
                f"the {hi:g} level at y={expected_top:.1f}"
            )
        if abs(bar.bottom - expected_bottom) > GEOMETRY_TOLERANCE:
            errors.append(
                f"{bar.label}: bottom edge drawn at y={bar.bottom:g} but the shared scale puts "
                f"the {lo:g} level at y={expected_bottom:.1f}"
            )
    return baseline, scale


def check_carries(source: str, bars: list[Bar], levels: list[tuple[float, float]],
                  baseline: float, scale: float, errors: list[str]) -> None:
    carries: list[tuple[float, float, float, float, str]] = []
    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        declared = attrs.get("data-carry")
        if declared is None:
            continue
        value = parse_number(declared)
        coords = [parse_number(attrs.get(key, "")) for key in ("x1", "y1", "x2", "y2")]
        if value is None or any(v is None for v in coords):
            errors.append(f"carry {declared!r}: non-numeric data-carry or coordinates")
            continue
        x1, y1, x2, y2 = coords  # type: ignore[assignment]
        if abs(y1 - y2) > VALUE_TOLERANCE:
            errors.append(f"carry {declared!r}: a carry is horizontal; drawn from y={y1:g} to y={y2:g}")
            continue
        carries.append((min(x1, x2), max(x1, x2), y1, value, declared))

    for left, right, (_, level) in zip(bars, bars[1:], levels):
        gap_start, gap_end = left.right, right.x
        matched = [
            carry for carry in carries
            if carry[0] <= gap_start + CARRY_SPAN_TOLERANCE and carry[1] >= gap_end - CARRY_SPAN_TOLERANCE
            and carry[0] >= left.x and carry[1] <= right.right
        ]
        gap_label = f"gap between {left.name!r} and {right.name!r}"
        if not matched:
            errors.append(f"{gap_label}: no carry spans it; the running total is not conserved across the gap")
            continue
        if len(matched) > 1:
            errors.append(f"{gap_label}: {len(matched)} carries cross one gap; a gap has one running total")
            continue
        _, _, y, value, declared = matched[0]
        if abs(value - level) > VALUE_TOLERANCE:
            errors.append(
                f"{gap_label}: carry declares {declared} but the running total between these bars is {level:g}"
            )
        expected_y = baseline - scale * level
        if abs(y - expected_y) > GEOMETRY_TOLERANCE:
            errors.append(
                f"{gap_label}: carry drawn at y={y:g} but the {level:g} level sits at y={expected_y:.1f}"
            )


def printed_values(source: str, bar: Bar) -> list[tuple[float, bool]]:
    values: list[tuple[float, bool]] = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        x, y = (parse_number(attrs.get(key, "")) for key in ("x", "y"))
        if any(key in attrs for key in ("style", "display", "visibility", "opacity", "fill-opacity")):
            continue
        expected_y = bar.bottom + 12 if bar.role == "delta" and bar.value < 0 else bar.y - 8
        if x is None or y is None or attrs.get("text-anchor") != "middle":
            continue
        if abs(x - (bar.x + bar.w / 2)) > GEOMETRY_TOLERANCE or abs(y - expected_y) > GEOMETRY_TOLERANCE:
            continue
        body = html.unescape(TAG_RE.sub("", match.group("body"))).strip()
        value, signed = parse_signed(body, signed_required=False)
        if value is not None:
            values.append((value, signed))
    return values


def check_printed(source: str, bars: list[Bar], errors: list[str]) -> None:
    for bar in bars:
        printed = printed_values(source, bar)
        needs_sign = bar.role == "delta"
        hit = any(
            abs(value - bar.value) <= VALUE_TOLERANCE and (signed or not needs_sign)
            for value, signed in printed
        )
        if not hit:
            wanted = f"{bar.value:+g}" if needs_sign else f"{bar.value:g}"
            errors.append(
                f"{bar.label}: no printed label states its value {wanted}"
                + (" with an explicit sign" if needs_sign else "")
            )


def check_sign_treatment(bars: list[Bar], errors: list[str], paper: str) -> None:
    focal = [bar for bar in bars if bar.stroke.lower() in ACCENT_STROKES]
    if len(focal) > 1:
        errors.append(
            "the accent focal treatment is editorial and marks at most one bar; found "
            + ", ".join(bar.label for bar in focal)
        )
    focal_set = set(id(bar) for bar in focal)
    # Absolute check: the documented mapping is tint-for-increase and hollow
    # paper-for-decrease, both over the muted stroke. Comparing the two polarity
    # sets against each other cannot see a single-polarity walk, or one whose
    # only bar of a polarity is focal, or a chart with the treatments swapped.
    # Only the two shipped themes have a documented pair; an unrecognised paper
    # falls through to the relative checks below rather than failing the file.
    THEME_TREATMENTS = {
        "#2d3142": ("rgba(191,192,192,0.15)", "#bfc0c0"),
        "#f5f5f5": ("rgba(79,93,117,0.15)", "#4f5d75"),
    }
    if paper in THEME_TREATMENTS:
        tint, stroke = THEME_TREATMENTS[paper]
        for bar in bars:
            if bar.role != "delta" or id(bar) in focal_set:
                continue
            expected_fill = tint if bar.value > 0 else paper
            if re.sub(r"\s+", "", bar.fill.lower()) != expected_fill or bar.stroke.lower() != stroke:
                errors.append(
                    f"{bar.label}: increases require the muted tint and decreases require "
                    f"hollow paper, both over the muted stroke"
                )
    rises = {bar.fill for bar in bars if bar.role == "delta" and bar.value > 0 and id(bar) not in focal_set}
    falls = {bar.fill for bar in bars if bar.role == "delta" and bar.value < 0 and id(bar) not in focal_set}
    if len(rises) > 1:
        errors.append(f"increases must share one fill; found {sorted(rises)}")
    if len(falls) > 1:
        errors.append(f"decreases must share one fill; found {sorted(falls)}")
    if len(rises) == 1 and len(falls) == 1 and rises == falls:
        errors.append(
            "increases and decreases share the same fill; sign must survive greyscale, "
            "so the two directions need distinct fill weights"
        )


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    paper_match = re.search(r'--color-paper\s*:\s*(#[0-9a-fA-F]{6})', source)
    paper = paper_match[1].lower() if paper_match else None
    bars = parse_bars(source, errors)
    if not bars:
        errors.append("no bars declare data-role/data-value; the waterfall data contract is missing")
        return errors
    if not check_structure(bars, errors):
        return errors
    check_transforms(source, errors)
    levels = running_levels(bars, errors)
    if levels is None:
        return errors
    fitted = check_geometry(bars, levels, errors)
    if fitted is not None:
        baseline, scale = fitted
        check_carries(source, bars, levels, baseline, scale, errors)
    check_printed(source, bars, errors)
    check_sign_treatment(bars, errors, paper)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify waterfall running-total conservation and bridge geometry.")
    parser.add_argument("paths", nargs="*", help="waterfall example HTML files")
    parser.add_argument("--all", action="store_true", help="check every shipped example-waterfall*.html")
    args = parser.parse_args()

    if args.all:
        paths = sorted(ASSET_DIR.glob("example-waterfall*.html"))
        if not paths:
            print("FAIL waterfall: --all found no example-waterfall*.html under the skill assets")
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
    print(f"OK waterfall: {len(paths)} file(s) conserve the running total and draw it where they claim")
    return 0


if __name__ == "__main__":
    sys.exit(main())
