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
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

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
    m = re.search(r"\b" + re.escape(name) + r'\s*=\s*"([^"]*)"', attrs_str)
    return m.group(1) if m else None


def _is_accent(r: int, g: int, b: int) -> bool:
    """Detect accent fill — warm reddish-orange. Works for both light and dark skins."""
    return r >= 200 and g <= 150 and b <= 100


def _parse_color(color: str) -> tuple[int, int, int] | None:
    """Parse a CSS hex or rgb/rgba color into the visible 8-bit RGB components.

    For rgba() values with alpha < 1, blend the color against the canonical paper
    background (#f5f5f5) to match how the SVG actually renders on screen.
    """
    value = color.strip()
    if not value:
        return None

    paper = (245, 245, 245)

    def blend(rgb: tuple[int, int, int], alpha: float) -> tuple[int, int, int]:
        if alpha >= 1.0:
            return rgb
        return tuple(
            round(c * alpha + paper[idx] * (1.0 - alpha)) for idx, c in enumerate(rgb)
        )

    if HEX_RE.match(value):
        hex_value = value[1:]
        if len(hex_value) == 3:
            hex_value = "".join(ch * 2 for ch in hex_value)
        try:
            rgb = (
                int(hex_value[0:2], 16),
                int(hex_value[2:4], 16),
                int(hex_value[4:6], 16),
            )
            return rgb
        except ValueError:
            return None

    rgba_match = RGBA_RE.match(value)
    if rgba_match:
        try:
            rgb = (
                int(rgba_match.group(1)),
                int(rgba_match.group(2)),
                int(rgba_match.group(3)),
            )
            alpha = float(rgba_match.group(4))
            return blend(rgb, alpha)
        except ValueError:
            return None

    rgb_match = re.match(
        r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", value, re.IGNORECASE
    )
    if rgb_match:
        try:
            return (
                int(rgb_match.group(1)),
                int(rgb_match.group(2)),
                int(rgb_match.group(3)),
            )
        except ValueError:
            return None
    return None


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (channel / 255 for channel in rgb)

    def channel_to_linear(channel: float) -> float:
        if channel <= 0.03928:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    r_lin = channel_to_linear(r)
    g_lin = channel_to_linear(g)
    b_lin = channel_to_linear(b)
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def _contrast_ratio(
    foreground: tuple[int, int, int], background: tuple[int, int, int]
) -> float:
    lum_fg = _relative_luminance(foreground)
    lum_bg = _relative_luminance(background)
    lighter, darker = max(lum_fg, lum_bg), min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


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
        x = _attr(attrs_str, "x")
        y = _attr(attrs_str, "y")
        width = _attr(attrs_str, "width")
        height = _attr(attrs_str, "height")

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

        cells.append(
            {
                "row": row,
                "col": col,
                "value": value,
                "opacity": opacity,
                "focal": focal,
                "fill": fill,
                "x": float(x) if x is not None else None,
                "y": float(y) if y is not None else None,
                "width": float(width) if width is not None else None,
                "height": float(height) if height is not None else None,
            }
        )

    return cells


def parse_text_labels(source: str) -> list[dict]:
    """Return SVG text labels with their fill, x, y, and rendered text."""
    source_clean = COMMENT_RE.sub("", source)
    texts: list[dict] = []
    for m in TEXT_RE.finditer(source_clean):
        attrs = m.group("attrs")
        fill = _attr(attrs, "fill")
        if not fill:
            continue
        x = _attr(attrs, "x")
        y = _attr(attrs, "y")
        text_content = re.search(r">(.*?)</text>", m.group(0), re.DOTALL)
        texts.append(
            {
                "fill": fill,
                "x": float(x) if x is not None else None,
                "y": float(y) if y is not None else None,
                "text": text_content.group(1).strip() if text_content else "",
            }
        )
    return texts


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

    # Invariant 1: require a declared axis vocabulary and reject any cell whose
    # row/column are outside that vocabulary. Cell-derived fallback is intentionally
    # not allowed here: a malformed heatmap can otherwise pass when a row or column
    # is missing from the label axis but the remaining cells still produce a count.
    declared_rows, declared_cols = parse_axis_labels(source)
    if not declared_rows or not declared_cols:
        errors.append(
            f"{path.name}: heatmap is missing declared row/column axis labels; "
            "every row and column must be named via data-row-label and data-col"
        )
        return errors

    rows = declared_rows
    cols = declared_cols

    seen_rows: set[str] = set()
    seen_cols: set[str] = set()
    for c in cells:
        if c["row"] not in rows:
            errors.append(
                f"{path.name}: cell uses undeclared row '{c['row']}' — "
                "every cell must map to a declared row label"
            )
        if c["col"] not in cols:
            errors.append(
                f"{path.name}: cell uses undeclared column '{c['col']}' — "
                "every cell must map to a declared column label"
            )
        seen_rows.add(c["row"])
        seen_cols.add(c["col"])

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
        opaque_missing = [c for c in non_focal if c["opacity"] is None]
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

    # Require focal cell value text to maintain WCAG AA against the focal fill.
    text_labels = parse_text_labels(source)
    for focal in focal_cells:
        bg_rgb = _parse_color(focal["fill"])
        if bg_rgb is None:
            continue
        x0 = focal["x"] if focal["x"] is not None else 0.0
        y0 = focal["y"] if focal["y"] is not None else 0.0
        width = focal["width"] if focal["width"] is not None else 0.0
        height = focal["height"] if focal["height"] is not None else 0.0
        for text in text_labels:
            if text["x"] is None or text["y"] is None:
                continue
            if not (x0 <= text["x"] <= x0 + width and y0 <= text["y"] <= y0 + height):
                continue
            text_rgb = _parse_color(text["fill"])
            if text_rgb is None:
                continue
            ratio = _contrast_ratio(text_rgb, bg_rgb)
            if ratio < 4.5:
                errors.append(
                    f"{path.name}: focal cell ({focal['row']}, {focal['col']}) has text "
                    f"{text['text']!r} in {text['fill']} on fill {focal['fill']} "
                    f"({ratio:.2f}:1 contrast, below WCAG AA 4.5:1)"
                )

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
