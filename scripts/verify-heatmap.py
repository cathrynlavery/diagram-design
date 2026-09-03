#!/usr/bin/env python3
"""Verify that a heatmap's drawn cells match the values they declare.

A heatmap makes one claim: **fill opacity is a monotone ramp on the declared
data value, and nothing else encodes quantity**. Row and column are categories;
their visual positions are only "which row" and "which column", not quantities
measured against a scale. Only the fill encodes "how much" — and the ramp must
be non-decreasing.

Four invariants:

1. COMPLETE GRID — every (row, col) pair in the declared row-and-column
   vocabulary is present. A missing cell is a gap in the reading that looks
   like "zero" but was never drawn.

2. MONOTONE FILL — non-focal cells whose data-value is higher must have a fill
   opacity that is >= the opacity of any cell with a lower data-value. The ramp
   must be non-decreasing: a lighter cell at a higher value inverts the visual
   scale and reverses every comparison. Cells with the same value must have the
   same opacity (tolerance ±0.03 to absorb floating-point representation).

3. ONE FOCAL MAX — at most one cell carries data-focal="true" or uses accent
   fill (R >= 200, G <= 150, B <= 100). The focal accent is an editorial marker
   for the single cell whose story the figure is about; using it on more than one
   inverts the ink-ramp contract the rest of the figure depends on.

4. FAIL CLOSED — zero parseable cells is a finding. A heatmap with no cells is
   not an empty-data edge case; it is an authoring error or a parse failure, and
   a checker that says OK because it found nothing to compare is the bug.

WHAT THIS DOES NOT CHECK, deliberately:

- **Cell geometry (x, y, width, height).** Both axes are categorical, so position
  encodes "which row/column", carried by axis labels — not a quantitative scale
  this checker can verify. A cell drawn at a wrong x,y is a layout error, not a
  data error; the label is what binds the mark to its identity.
- **The scale formula.** Monotone, not a specific slope or formula. Linear, sqrt,
  and log scales all pass as long as opacity is non-decreasing with value.
- **Text values inside cells.** Optional annotation; not part of the geometric
  contract.

Usage:
    python3 scripts/verify-heatmap.py --all
    python3 scripts/verify-heatmap.py skills/diagram-design/assets/example-heatmap.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
RGBA_RE = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)")

# CSS properties that can silently move a verified rect without changing its
# x/y/width/height attributes. Declaration-start anchoring avoids false matches
# on text-transform, custom-property values, etc.
# Mirrors verify-bump.py: checks transform/translate/rotate/scale and SVG
# presentation attributes that CSS can override (cx, cy, x, y, d, offset-*).
# Does NOT flag width/height since `svg { width: 100%; }` is standard responsive
# boilerplate and does not affect the verified rect attributes.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|cx|cy|x|y|d"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)


def _attr(attrs_str: str, name: str) -> str | None:
    m = re.search(r'\b' + re.escape(name) + r'\s*=\s*"([^"]*)"', attrs_str)
    return m.group(1) if m else None


def _is_accent(r: int, g: int, b: int) -> bool:
    """Detect accent fill — warm reddish-orange. Works for both light and dark skins."""
    return r >= 200 and g <= 150 and b <= 100


def parse_axis_labels(source: str) -> tuple[list[str], list[str]]:
    """Return (declared_rows, declared_cols) from axis-label text elements.

    Rows are declared with data-row-label="name" on <text> elements (left gutter).
    Columns are declared with data-col="name" on <text> elements (top header row).
    The order is preserved so the grid vocabulary is stable even if cells are absent.
    """
    source_clean = COMMENT_RE.sub("", source)
    declared_rows: list[str] = []
    declared_cols: list[str] = []
    seen_rows: set[str] = set()
    seen_cols: set[str] = set()

    for m in TEXT_RE.finditer(source_clean):
        attrs_str = m.group("attrs")
        row_label = _attr(attrs_str, "data-row-label")
        col_label = _attr(attrs_str, "data-col")
        if row_label and row_label not in seen_rows:
            declared_rows.append(row_label)
            seen_rows.add(row_label)
        if col_label and col_label not in seen_cols:
            declared_cols.append(col_label)
            seen_cols.add(col_label)

    return declared_rows, declared_cols


def parse_cells(source: str) -> list[dict]:
    """Return list of cell dicts: row, col, value, opacity, focal."""
    source_clean = COMMENT_RE.sub("", source)
    cells: list[dict] = []

    for m in RECT_RE.finditer(source_clean):
        attrs_str = m.group("attrs")
        row = _attr(attrs_str, "data-row")
        col = _attr(attrs_str, "data-col")
        val_str = _attr(attrs_str, "data-value")
        if not (row and col and val_str is not None):
            continue
        try:
            value = float(val_str)
        except ValueError:
            continue
        if not (0.0 <= value < 1e9) or value != value:  # reject nan/inf/negative
            continue

        fill = _attr(attrs_str, "fill") or ""
        focal = _attr(attrs_str, "data-focal") == "true"
        opacity: float | None = None

        rm = RGBA_RE.search(fill)
        if rm:
            try:
                r_ch = int(rm.group(1))
                g_ch = int(rm.group(2))
                b_ch = int(rm.group(3))
                opacity = float(rm.group(4))
            except ValueError:
                opacity = None
            else:
                if not (0.0 <= opacity <= 1.0):
                    opacity = None
                elif _is_accent(r_ch, g_ch, b_ch):
                    focal = True

        cells.append({
            "row": row,
            "col": col,
            "value": value,
            "opacity": opacity,
            "focal": focal,
            "fill": fill,
        })

    return cells


def check_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.name}: cannot read: {exc}"]

    # CSS-moves-geometry check.
    for style_body in STYLE_RE.findall(source):
        m = CSS_MOVES_MARK_RE.search(style_body)
        if m:
            errors.append(
                f"{path.name}: CSS property '{m.group('prop')}' can move verified "
                "cell geometry without changing the attributes this checker reads"
            )

    cells = parse_cells(source)

    if not cells:
        errors.append(
            f"{path.name}: no parseable heatmap cells found "
            "(need <rect data-row=... data-col=... data-value=...>)"
        )
        return errors

    focal_cells = [c for c in cells if c["focal"]]
    non_focal = [c for c in cells if not c["focal"]]

    # Invariant 3: at most one focal cell.
    if len(focal_cells) > 1:
        focal_ids = ", ".join(f"({c['row']},{c['col']})" for c in focal_cells)
        errors.append(
            f"{path.name}: found {len(focal_cells)} focal cells ({focal_ids}); "
            "at most 1 allowed — the focal accent marks one editorial cell, "
            "not a second data range"
        )

    # Invariant 1: complete N×M grid — use DECLARED axis labels as the vocabulary,
    # not the cells themselves. A heatmap that silently drops an entire row or column
    # reconstructed only from cells would shrink both actual and expected counts and
    # pass; declared labels are the authoritative source of the grid dimensions.
    declared_rows, declared_cols = parse_axis_labels(source)
    if declared_rows and declared_cols:
        rows = declared_rows
        cols = declared_cols
    else:
        # Fall back to cell-derived vocabulary only when no axis labels are present.
        rows = sorted(set(c["row"] for c in cells))
        cols = sorted(set(c["col"] for c in cells))

    expected = len(rows) * len(cols)
    actual = len(cells)

    if actual != expected:
        errors.append(
            f"{path.name}: expected {expected} cells "
            f"({len(rows)} rows × {len(cols)} cols) but found {actual}; "
            "every (row, col) pair must be present"
        )
    else:
        seen: set[tuple[str, str]] = set()
        for c in cells:
            key = (c["row"], c["col"])
            if key in seen:
                errors.append(
                    f"{path.name}: duplicate cell ({c['row']}, {c['col']}); "
                    "each (row, col) pair must appear exactly once"
                )
                break
            seen.add(key)

    # Invariant 2: monotone fill ramp for non-focal cells.
    if non_focal:
        opaque_missing = [
            c for c in non_focal if c["opacity"] is None
        ]
        if opaque_missing:
            for c in opaque_missing:
                errors.append(
                    f"{path.name}: non-focal cell ({c['row']}, {c['col']}) "
                    "has no parseable rgba fill — every non-focal cell must "
                    "declare its opacity through rgba(R,G,B,opacity)"
                )

        by_value: dict[float, list[float]] = {}
        for c in non_focal:
            if c["opacity"] is not None:
                by_value.setdefault(c["value"], []).append(c["opacity"])

        # Within each value, all opacities must be identical (±TOLERANCE).
        TOLERANCE = 0.03
        for val, opacities in sorted(by_value.items()):
            spread = max(opacities) - min(opacities)
            if spread > TOLERANCE:
                errors.append(
                    f"{path.name}: cells with data-value={val} have inconsistent "
                    f"opacities (spread {spread:.3f} > {TOLERANCE}); "
                    "every cell with the same value must use the same fill opacity"
                )

        # Across values, mean opacity must be non-decreasing.
        sorted_vals = sorted(by_value.keys())
        prev_opacity = -1.0
        prev_val = None
        for val in sorted_vals:
            mean_opacity = sum(by_value[val]) / len(by_value[val])
            if mean_opacity < prev_opacity - TOLERANCE:
                errors.append(
                    f"{path.name}: value {val} has mean fill opacity "
                    f"{mean_opacity:.3f}, which is less than value "
                    f"{prev_val}'s opacity {prev_opacity:.3f}; "
                    "the fill ramp must be non-decreasing — higher values "
                    "must use >= opacity than lower values"
                )
            prev_opacity = mean_opacity
            prev_val = val

    return errors


def _heatmap_examples(asset_dir: Path) -> list[Path]:
    """Return all heatmap example HTML files from the asset directory."""
    return sorted(asset_dir.glob("example-heatmap*.html"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify heatmap chart files.",
        epilog="Exit 0 = clean, 1 = findings, 2 = usage error.",
    )
    parser.add_argument(
        "files",
        nargs="*",
        metavar="FILE",
        help="Heatmap HTML files to check. Default: all example-heatmap*.html.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all example-heatmap*.html in the assets directory.",
    )
    args = parser.parse_args(argv)

    if args.all or not args.files:
        paths = _heatmap_examples(ASSET_DIR)
        if not paths:
            print("No heatmap examples found.", file=sys.stderr)
            return 1
    else:
        paths = [Path(f) for f in args.files]

    all_errors: list[str] = []
    for path in paths:
        all_errors.extend(check_file(path))

    if all_errors:
        for err in all_errors:
            print(err, file=sys.stderr)
        return 1

    print(f"OK — {len(paths)} file(s) checked, no findings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
