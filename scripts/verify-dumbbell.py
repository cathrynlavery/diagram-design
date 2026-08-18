#!/usr/bin/env python3
"""Verify the two dumbbell rules that live in a formula rather than in a drawing.

Both rules in `references/type-bar.md` are formula-level: a generator implements
them arithmetically, and both fail in ways that render perfectly. Prose alone
cannot defend either, so both are executable here and the reference is checked
against this module rather than the other way round.

1. DOMAIN RESOLUTION - the axis bounds are a function of the data's range, never
   of its observed extremes. Taking `min`/`max` as the bounds IS the truncation
   the reference forbids: the plot width is fixed, so a narrowed domain raises
   px-per-unit and draws every gap wider. The subtle case is zero. A sign-based
   rule that says "all-positive" and "all-negative" silently omits data that
   only touches zero, and omits the all-zero dataset entirely - where the naive
   reading yields `floor == ceil == 0` and the position formula divides by zero.
   `resolve_domain` partitions the space exhaustively and guarantees
   `ceil > floor`, so coordinates are always finite.

2. NON-TEXT CONTRAST - the solid endpoint and the connector are the marks that
   carry "which series" and "which pair". WCAG 1.4.11 asks 3:1 of a graphical
   object required to understand the content, and shape redundancy does not
   waive it: a reader still has to see the solid mark's boundary and the line
   joining the pair. Accent-on-paper is 2.86:1 skin-wide and cannot carry that,
   so the boundary is carried by a stroke and the connector by an alpha that
   clears 3:1 in both themes. The thresholds are checked here against the tokens
   the reference actually documents, so the two cannot drift apart.

The check FAILS CLOSED. A reference this cannot parse, or a token it cannot
find, is a finding - never a silent pass.

Usage:
    python3 scripts/verify-dumbbell.py
    python3 scripts/verify-dumbbell.py --reference path/to/type-bar.md

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE = ROOT / "skills/diagram-design/references/type-bar.md"

# --- composition constants, quoted from the reference -----------------------
PLOT_X0 = 200          # left edge of the plot area
PLOT_WIDTH = 760       # 200 -> 960
MIN_GAP_PX = 16        # below this two r=6 marks read as one blob

# All-zero data has no range to scale against. A finite fallback span keeps the
# position formula defined; every dot lands on the floor, which is the truth.
ALL_ZERO_SPAN = 1.0

# --- skin tokens ------------------------------------------------------------
PAPER_LIGHT, PAPER_DARK = "#f5f5f5", "#2d3142"
WCAG_NON_TEXT = 3.0    # 1.4.11, graphical objects

# (label, ink hex, alpha, paper) - the connector in each theme
CONNECTORS = [
    ("connector (light)", "#2d3142", 0.55, PAPER_LIGHT),
    ("connector (dark)", "#f5f5f5", 0.40, PAPER_DARK),
]
# (label, stroke hex, paper) - the boundary of the solid endpoint
ENDPOINT_STROKES = [
    ("solid endpoint stroke (light)", "#2d3142", PAPER_LIGHT),
    ("solid endpoint stroke (dark)", "#f5f5f5", PAPER_DARK),
]
# Tokens the reference must actually name, so prose and code cannot drift.
REQUIRED_TOKENS = [
    "rgba(45,49,66,0.55)",
    "rgba(245,245,245,0.40)",
]


class DomainError(ValueError):
    """Raised when a domain cannot be resolved at all."""


# === DOMAIN =================================================================

def _nice_magnitude(value: float) -> float:
    """Smallest round number >= |value|, from the 1 / 2 / 2.5 / 5 / 10 ladder."""
    magnitude = abs(value)
    if magnitude == 0:
        return 0.0
    exponent = math.floor(math.log10(magnitude))
    base = 10.0 ** exponent
    for step in (1.0, 2.0, 2.5, 5.0, 10.0):
        candidate = step * base
        if candidate >= magnitude - 1e-12:
            return candidate
    return 10.0 * base


def resolve_domain(values):
    """Return (floor, ceil) for a dumbbell's value axis.

    Exhaustive over the sign of the data, including the two cases a sign-based
    rule drops: data that only touches zero, and data that is entirely zero.
    Guarantees ceil > floor, so the position formula never divides by zero.
    """
    numbers = [float(v) for v in values]
    if not numbers:
        raise DomainError("no values: a dumbbell needs at least one pair")
    if any(math.isnan(v) or math.isinf(v) for v in numbers):
        raise DomainError("non-finite value in input")

    low, high = min(numbers), max(numbers)

    if low == 0.0 and high == 0.0:
        floor, ceiling = 0.0, ALL_ZERO_SPAN      # every dot sits on the floor
    elif low >= 0.0:
        floor, ceiling = 0.0, _nice_magnitude(high)
    elif high <= 0.0:
        floor, ceiling = -_nice_magnitude(low), 0.0
    else:
        floor, ceiling = -_nice_magnitude(low), _nice_magnitude(high)

    if not ceiling > floor:
        raise DomainError(
            "degenerate domain %r..%r from values %r" % (floor, ceiling, numbers)
        )
    return floor, ceiling


def scale(value: float, floor: float, ceiling: float) -> float:
    """Map a value onto the plot's x axis. Mirrors the reference's formula."""
    span = ceiling - floor
    if span <= 0:
        raise DomainError("non-positive span %r" % (span,))
    return PLOT_X0 + (float(value) - floor) / span * PLOT_WIDTH


def is_truncated(values, floor: float, ceiling: float) -> bool:
    """True when the bounds hug the data instead of following its sign.

    This is the failure the honesty rule exists to prevent: bounds taken from
    the observed extremes rather than resolved from the data's range.
    """
    resolved_floor, resolved_ceiling = resolve_domain(values)
    return (floor, ceiling) != (resolved_floor, resolved_ceiling)


# === CONTRAST ===============================================================

def _channel(component: int) -> float:
    fraction = component / 255.0
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    value = color.lstrip("#")
    red, green, blue = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(foreground: str, background: str) -> float:
    first, second = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def composite(foreground: str, alpha: float, background: str) -> str:
    """Flatten a translucent stroke onto its background."""
    fore = [int(foreground.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    back = [int(background.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    blended = [round(fore[i] * alpha + back[i] * (1 - alpha)) for i in range(3)]
    return "#%02x%02x%02x" % tuple(blended)


# === CHECKS =================================================================

def check_domain_rules():
    """Exercise the scaling path over every sign case, including the zero ones."""
    findings = []
    cases = [
        ("all zero", [0, 0, 0, 0]),
        ("zero-touching positive", [0, 0, 5, 12]),
        ("zero-touching negative", [-12, -5, 0, 0]),
        ("all positive", [18, 66, 34, 71]),
        ("all negative", [-71, -34, -66, -18]),
        ("crossing zero", [-20, 5, 40, -3]),
        ("single identical pair", [7, 7]),
        ("tiny magnitudes", [0.0004, 0.0009]),
    ]
    for label, values in cases:
        try:
            floor, ceiling = resolve_domain(values)
        except DomainError as error:
            findings.append("%s: domain unresolved (%s)" % (label, error))
            continue
        if not ceiling > floor:
            findings.append("%s: ceil %r not above floor %r" % (label, ceiling, floor))
            continue
        for value in values:
            x = scale(value, floor, ceiling)
            if not math.isfinite(x):
                findings.append("%s: non-finite coordinate for %r" % (label, value))
            elif not (PLOT_X0 - 1e-6 <= x <= PLOT_X0 + PLOT_WIDTH + 1e-6):
                findings.append(
                    "%s: %r maps to %.3f, outside the plot area" % (label, value, x)
                )
    return findings


def check_contrast_rules():
    findings = []
    for label, ink, alpha, paper in CONNECTORS:
        ratio = contrast(composite(ink, alpha, paper), paper)
        if ratio < WCAG_NON_TEXT:
            findings.append(
                "%s: %.3f:1 against paper, under the %.1f:1 WCAG 1.4.11 asks"
                % (label, ratio, WCAG_NON_TEXT)
            )
    for label, stroke, paper in ENDPOINT_STROKES:
        ratio = contrast(stroke, paper)
        if ratio < WCAG_NON_TEXT:
            findings.append(
                "%s: %.3f:1 against paper, under the %.1f:1 WCAG 1.4.11 asks"
                % (label, ratio, WCAG_NON_TEXT)
            )
    return findings


def check_reference(path: Path):
    """Fail closed: the reference must name the tokens this module verifies."""
    findings = []
    if not path.is_file():
        return ["reference not found: %s" % path]
    text = path.read_text(encoding="utf-8")
    if "Dumbbell" not in text:
        return ["reference %s carries no dumbbell section to check" % path.name]
    for token in REQUIRED_TOKENS:
        if token not in text:
            findings.append(
                "reference does not document %s, so the checked value is not the "
                "shipped one" % token
            )
    if not re.search(r"\bfloor\b", text) or not re.search(r"\bceil\b", text):
        findings.append("reference does not name the domain bounds the formula uses")
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify the dumbbell's domain and non-text-contrast rules."
    )
    parser.add_argument(
        "--reference", type=Path, default=REFERENCE,
        help="path to type-bar.md (default: the shipped reference)",
    )
    args = parser.parse_args(argv)

    findings = []
    findings += check_domain_rules()
    findings += check_contrast_rules()
    findings += check_reference(args.reference)

    if findings:
        for finding in findings:
            sys.stderr.write("FAIL dumbbell: %s\n" % finding)
        sys.stderr.write("Summary: %d finding(s).\n" % len(findings))
        return 1
    sys.stdout.write(
        "OK dumbbell: domain resolves finitely over every sign case "
        "(including all-zero), and the documented connector and endpoint "
        "boundary clear 3:1 in both themes\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
