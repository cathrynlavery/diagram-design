#!/usr/bin/env python3
"""Verify the two invariants a treemap can silently break.

A treemap's whole claim is that **area is the encoding**. Both ways of breaking
that claim render perfectly - nothing errors, nothing disappears, and neither
`lint-skin.py` (colors, fonts, a11y) nor `verify-geometry.py` (label masks vs
later-painted nodes) reads a cell against the number printed inside it.

1. AREA FIDELITY - a cell's share of the drawn area must match the share its
   own label claims. This is checked as **relative** error, not percentage
   points: a 0.13pp slip is noise on a 59% cell and a quarter of a 0.5% cell,
   so an absolute threshold passes exactly the cell most likely to be wrong.
   The failure is real - the smallest cell absorbs the whole 4px-grid residue,
   because 4px is a third of a sliver and a rounding error on a giant.

2. LABEL AND MARKER FIT - a label or information marker must stay inside the
   cell it names. Cells have no clip path, so overflow bleeds into a neighbour
   or off the viewBox and reads as belonging to the wrong thing. A cell too
   small for its annotation is not a nudge-the-coordinates problem: drop the
   annotation (the cell keeps its honest area) or merge the tail into a named
   "Other".

Text extent is estimated from font metrics rather than measured in a browser,
deliberately: every other gate here is pure Python and runs in CI with no
browser. The Latin advances below are calibrated against Chromium renderings of
the shipped Geist / Geist Mono faces and rounded UP. Unicode wide/full-width
characters use a conservative 1em advance, so both estimates report overflow
slightly before real overflow, never after.

Usage:
    python3 scripts/verify-treemap.py --all
    python3 scripts/verify-treemap.py skills/diagram-design/assets/example-treemap.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

CELL_RE = re.compile(r"<rect\b(?P<attrs>[^>]*)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*)/?>", re.IGNORECASE)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')
ROTATE_RE = re.compile(r"rotate\(\s*(?P<deg>-?[\d.]+)")
TAG_RE = re.compile(r"<[^>]+>")
# A cell states its size one of two ways, and the two must not be confused: a
# magnitude ("4.78B") is a value to be normalised against the other cells, while
# a percentage ("59%", "0.6%") is already the claimed share. Reading "0.6%" as
# the number 0.6 against cells measured in billions produces nonsense, so the
# percentage pattern is tried first and anchored on the sign.
PCT_RE = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*%")
VALUE_RE = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>[BMK])\b")

MONO_ADVANCE = 0.62
SANS_ADVANCE = 0.60
WIDE_ADVANCE = 1.00
ASCENT = 0.74
UNITS = {None: 1.0, "K": 1e3, "M": 1e6, "B": 1e9}

# A treemap cell is large enough to hold a label and small enough not to be a
# page background or diagram container.
CELL_MIN_AREA = 400.0
CELL_MAX_W = 900.0
CELL_MAX_H = 460.0
EPSILON = 1.0
# Relative area tolerance. Grid snapping on a 1000x500 viewBox cannot do better
# than a couple of percent on a sub-1% cell; 8% is loose enough never to fire on
# honest rounding and tight enough to have caught the 30%-undersized sliver this
# check exists for.
AREA_TOLERANCE = 8.0
MARKER_EPSILON = 0.01


class Box:
    __slots__ = (
        "x",
        "y",
        "w",
        "h",
        "offset",
        "share",
        "share_errors",
        "rect_count",
    )

    def __init__(
        self, x: float, y: float, w: float, h: float, offset: int = 0, share: float | None = None
    ) -> None:
        self.x, self.y, self.w, self.h, self.offset = x, y, w, h, offset
        # Declared share of the whole, from data-share. None means the cell
        # never stated one, which for a treemap is itself a finding.
        self.share = share
        self.share_errors: list[str] = []
        self.rect_count = 1

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        return self.w * self.h

    def contains_point(self, x: float, y: float) -> bool:
        return (
            self.x - EPSILON <= x <= self.right + EPSILON
            and self.y - EPSILON <= y <= self.bottom + EPSILON
        )


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def estimated_advance(text: str, mono: bool) -> float:
    """Conservative text advance in em, preserving the calibrated Latin baseline."""
    narrow_advance = MONO_ADVANCE if mono else SANS_ADVANCE
    advance = 0.0
    for char in text:
        # Nonspacing and enclosing marks modify the preceding glyph; counting
        # them as another glyph rejects labels that do fit. Spacing combining
        # marks (Mc) retain the narrow estimate because they can advance.
        if unicodedata.category(char) in {"Mn", "Me"}:
            continue
        if unicodedata.east_asian_width(char) in {"W", "F"}:
            advance += WIDE_ADVANCE
        else:
            advance += narrow_advance
    return advance


def parse_cells(source: str, findings: list[str] | None = None) -> list[Box]:
    """Deduped cell rects. Each cell is painted twice: paper mask, then body.

    `data-share` may sit on either rect of the pair, so the declared share is
    merged across duplicates rather than read off whichever came first.
    """
    seen: list[Box] = []
    for m in CELL_RE.finditer(source):
        attrs = {a.group("name"): a.group("value") for a in ATTR_RE.finditer(m.group("attrs"))}
        has_share_metadata = "data-share" in attrs
        if attrs.get("rx") != "2" and not has_share_metadata:
            continue
        try:
            box = Box(
                float(attrs["x"]),
                float(attrs["y"]),
                float(attrs["width"]),
                float(attrs["height"]),
                m.start(),
            )
        except (KeyError, ValueError) as exc:
            if has_share_metadata and findings is not None:
                findings.append(
                    f"line {line_of(source, m.start())}: data-share rect has missing or "
                    f"unparseable x/y/width/height geometry ({exc})"
                )
            continue
        coordinates = (box.x, box.y, box.w, box.h)
        if has_share_metadata and (
            not all(math.isfinite(value) for value in coordinates) or box.w <= 0 or box.h <= 0
        ):
            if findings is not None:
                findings.append(
                    f"line {line_of(source, m.start())}: data-share rect geometry must have "
                    "finite x/y/width/height and strictly positive width/height; "
                    f"got x={box.x:g}, y={box.y:g}, width={box.w:g}, height={box.h:g}"
                )
            continue
        if "data-share" in attrs:
            raw_share = attrs["data-share"]
            try:
                parsed_share = float(raw_share)
            except ValueError:
                box.share_errors.append(f"data-share {raw_share!r} is not numeric")
            else:
                if not math.isfinite(parsed_share):
                    box.share_errors.append(f"data-share {raw_share!r} is not finite")
                elif not 0 < parsed_share <= 100:
                    box.share_errors.append(
                        f"data-share {raw_share!r} must be greater than 0 and at most 100"
                    )
                else:
                    box.share = parsed_share
        twin = next(
            (
                s
                for s in seen
                if abs(s.x - box.x) < 0.01
                and abs(s.y - box.y) < 0.01
                and abs(s.w - box.w) < 0.01
                and abs(s.h - box.h) < 0.01
            ),
            None,
        )
        if twin is not None:
            twin.rect_count += 1
            twin.share_errors.extend(box.share_errors)
            if twin.share is not None and box.share is not None and not math.isclose(
                twin.share, box.share, rel_tol=0.0, abs_tol=1e-9
            ):
                twin.share_errors.append(
                    f"duplicate rects declare conflicting data-share values "
                    f"{twin.share:g} and {box.share:g}"
                )
            if twin.share is None:
                twin.share = box.share
            continue
        seen.append(box)
    return [
        box
        for box in seen
        if box.share is not None
        or box.share_errors
        or (box.area >= CELL_MIN_AREA and box.w <= CELL_MAX_W and box.h <= CELL_MAX_H)
    ]


def label_box(attrs: dict[str, str], body: str) -> Box | None:
    """Estimated rendered box of a <text>, in root user space."""
    try:
        x = float(attrs["x"])
        y = float(attrs["y"])
        size = float(attrs.get("font-size", "12"))
    except (KeyError, ValueError):
        return None
    text = plain(body)
    if not text:
        return None
    mono = "mono" in attrs.get("font-family", "").lower()
    width = size * estimated_advance(text, mono)
    anchor = attrs.get("text-anchor", "start")

    transform = attrs.get("transform", "")
    if transform:
        m = ROTATE_RE.search(transform)
        # Only the quarter-turn cases are modelled; anything else is skipped
        # rather than guessed at.
        if m is None or abs(abs(float(m.group("deg"))) - 90.0) > 0.01:
            return None
        if anchor == "middle":
            top = y - width / 2
        elif anchor == "end":
            top = y
        else:
            top = y - width
        return Box(x - size * ASCENT, top, size, width)

    if anchor == "middle":
        left = x - width / 2
    elif anchor == "end":
        left = x - width
    else:
        left = x
    return Box(left, y - size * ASCENT, width, size)


def _number(match: re.Match[str] | None) -> float | None:
    if match is None:
        return None
    try:
        return float(match.group("num").replace(",", ""))
    except ValueError:
        return None


def parse_claim(text: str) -> tuple[float | None, float | None]:
    """(percentage, value) claimed by a label. Either may be absent."""
    percentage = _number(PCT_RE.search(text))
    value_match = VALUE_RE.search(text)
    value = _number(value_match)
    if value is not None and value_match is not None:
        value *= UNITS[value_match.group("unit")]
    return percentage, value


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    findings: list[str] = []
    parse_findings: list[str] = []
    cells = parse_cells(source, parse_findings)
    findings.extend(f"{path.name}:{finding}" for finding in parse_findings)
    if len(cells) < 3:
        findings.append(
            f"{path.name}: expected at least 3 parseable treemap cells, found {len(cells)} — "
            "the area contract cannot be verified"
        )
        return findings

    labels: dict[int, list[str]] = {index: [] for index in range(len(cells))}

    for m in TEXT_RE.finditer(source):
        attrs = {a.group("name"): a.group("value") for a in ATTR_RE.finditer(m.group("attrs"))}
        box = label_box(attrs, m.group("body"))
        if box is None:
            continue
        # Host is resolved from the text's ANCHOR, not its box corner. An
        # end- or middle-anchored label extends left of its anchor, so a box
        # corner can land outside the very cell the label belongs to - which
        # would silently attribute it to a neighbour, or to nothing at all.
        anchor_x, anchor_y = float(attrs["x"]), float(attrs["y"])
        host_index = None
        for index, cell in enumerate(cells):
            if not cell.contains_point(anchor_x, anchor_y):
                continue
            if host_index is None or cell.area < cells[host_index].area:
                host_index = index
        if host_index is None:
            continue
        host = cells[host_index]
        labels[host_index].append(plain(m.group("body")))

        # All four edges. Checking only right and bottom passes an end-anchored
        # label hanging off the left, or a label whose ascent clears the top -
        # both of which read as belonging to the neighbouring cell.
        overflow = {
            "left": host.x - box.x,
            "top": host.y - box.y,
            "right": box.right - host.right,
            "bottom": box.bottom - host.bottom,
        }
        breached = {side: over for side, over in overflow.items() if over > EPSILON}
        if breached:
            detail = " / ".join(f"{over:.1f} {side}" for side, over in breached.items())
            findings.append(
                f"{path.name}:{line_of(source, m.start())}: label "
                f"{plain(m.group('body'))[:38]!r} overflows its {host.w:g}x{host.h:g} cell "
                f"by {detail} — drop the label or merge the cell into a named Other"
            )

    # Information marks are 8–12px discs placed inside sliver cells. Their
    # one-letter text can fit while the surrounding disc still crosses a cell
    # boundary, so circles need their own containment check.
    for m in CIRCLE_RE.finditer(source):
        attrs = {a.group("name"): a.group("value") for a in ATTR_RE.finditer(m.group("attrs"))}
        try:
            cx = float(attrs["cx"])
            cy = float(attrs["cy"])
            radius = float(attrs["r"])
        except (KeyError, ValueError):
            continue
        if not 4.0 <= radius <= 6.0:
            continue
        host_index = None
        for index, cell in enumerate(cells):
            if not cell.contains_point(cx, cy):
                continue
            if host_index is None or cell.area < cells[host_index].area:
                host_index = index
        if host_index is None:
            continue
        host = cells[host_index]
        overflow = {
            "left": host.x - (cx - radius),
            "top": host.y - (cy - radius),
            "right": (cx + radius) - host.right,
            "bottom": (cy + radius) - host.bottom,
        }
        breached = {
            side: over for side, over in overflow.items() if over > MARKER_EPSILON
        }
        if breached:
            detail = " / ".join(f"{over:.1f} {side}" for side, over in breached.items())
            findings.append(
                f"{path.name}:{line_of(source, m.start())}: information marker "
                f"overflows its {host.w:g}x{host.h:g} cell by {detail} — "
                "drop the marker and identify the sliver in the legend"
            )

    # Every cell is checked against its OWN declared share, so the cell most
    # likely to be wrong is not the one exempt from checking. Deriving the
    # basis from in-cell labels instead leaves an unlabelled sliver - exactly
    # the cell a 4px grid distorts most - verified by nothing at all.
    for cell in cells:
        for error in cell.share_errors:
            findings.append(
                f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                f"has invalid share metadata: {error}"
            )
        if cell.rect_count > 2:
            findings.append(
                f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                f"is painted by {cell.rect_count} duplicate rects — expected at most a mask/body pair"
            )

    undeclared = [cell for cell in cells if cell.share is None and not cell.share_errors]
    if undeclared:
        # Fail closed. A treemap whose cells cannot be parsed is not a passing
        # treemap; it is an unchecked one, and saying "OK" to it is the bug.
        for cell in undeclared:
            findings.append(
                f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                f"has no data-share, so its area is unverifiable — every treemap cell "
                f"must declare its share of the whole, including cells too small to label"
            )
        return findings

    drawn_total = sum(cell.area for cell in cells)
    if not math.isfinite(drawn_total) or drawn_total <= 0:
        findings.append(
            f"{path.name}: parsed cell area total must be finite and positive; got {drawn_total:g}"
        )
        return findings
    if any(cell.share_errors for cell in cells):
        return findings

    share_total = sum(cell.share for cell in cells if cell.share is not None)
    if not 99.0 <= share_total <= 101.0:
        findings.append(
            f"{path.name}: data-share values total {share_total:g}%, not approximately 100% — "
            "every cell must declare its share of the same whole"
        )
        return findings

    for index, cell in enumerate(cells):
        assert cell.share is not None
        area_share = cell.area / drawn_total * 100
        declared = cell.share / share_total * 100
        relative = (area_share - declared) / declared * 100
        if abs(relative) > AREA_TOLERANCE:
            findings.append(
                f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                f"draws {area_share:.2f}% of the area but declares {declared:.2f}% — "
                f"{relative:+.1f}% relative. Area is the only encoding; resize the cell"
            )

        # A label and the metadata are two statements of one fact. Read every
        # percentage in the hosted labels: search() alone silently accepted a
        # later contradictory claim when the first happened to be correct.
        label_text = " ".join(labels[index])
        percentages = [
            value
            for match in PCT_RE.finditer(label_text)
            if (value := _number(match)) is not None
        ]
        distinct_percentages: list[float] = []
        for percentage in percentages:
            if not any(
                math.isclose(percentage, known, rel_tol=0.0, abs_tol=1e-9)
                for known in distinct_percentages
            ):
                distinct_percentages.append(percentage)
        if len(distinct_percentages) > 1:
            rendered = ", ".join(f"{value:g}%" for value in distinct_percentages)
            findings.append(
                f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                f"has conflicting percentage claims ({rendered}) — every hosted label "
                "must state the same share"
            )
            continue

        if distinct_percentages and declared > 0:
            percentage = distinct_percentages[0]
            drift = abs(percentage - declared)
            # 1pp covers honest rounding of a displayed integer percentage.
            if drift > 1.0:
                findings.append(
                    f"{path.name}:{line_of(source, cell.offset)}: cell {cell.w:g}x{cell.h:g} "
                    f"is labelled {percentage:g}% but declares {declared:.2f}% — "
                    f"the label and data-share must state the same fact"
                )
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("example-treemap*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify treemap area fidelity and label/marker fit."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped treemap example")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    findings: list[str] = []
    checked = 0
    for path in targets(args):
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        findings.extend(check(path))
        checked += 1

    for finding in findings:
        print(finding)
    if findings:
        print(f"\n{len(findings)} treemap finding(s) across {checked} file(s).")
        return 1
    print(
        f"OK treemap: {checked} file(s), area matches labels and every label/marker fits its cell"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
