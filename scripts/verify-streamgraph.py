#!/usr/bin/env python3
"""Verify that a streamgraph's drawn layers match the values they declare.

A streamgraph makes two claims at once: **the envelope is the total** and **each
layer's thickness is its share**, both on one shared scale about one symmetric
midline. Break any of that and nothing errors - the figure renders, the legend
is present, and the lie is in the geometry. `lint-skin.py` reads colors and
fonts, `verify-geometry.py` reads label masks against later-painted nodes, and
neither compares a drawn boundary against the values sitting in the markup.

Seven invariants, in the spirit of ADR 0005 and the slopegraph checker:

1. SHARED COLUMNS - every layer's on-curve vertices sit at the same period
   x-positions. A layer sampled on its own grid cannot be stacked against the
   others, so a mismatch is reported and cross-layer geometry is not attempted.

2. ONE SCALE - per-period thickness must equal the declared value times one
   figure-wide scale. The scale is derived robustly (median of thickness/value
   over nonzero values), so a single dishonest band does not drag the scale it
   is measured against. A zero value must pinch to zero thickness - the pinch
   is data.

3. TILED STACK - each layer's bottom boundary is the previous layer's top, no
   gaps, no overlaps, in one fixed order. A per-period reordering, a silently
   inflated band, or a dropped sliver all break the tiling and are reported as
   the geometry they are.

4. SYMMETRIC BASELINE - envelope top and bottom must average to one constant
   midline at every period (baseline = -total/2). A midline that drifts turns
   layer wiggle into fake growth; a baseline pinned to the bottom is a stacked
   area presenting as a streamgraph.

5. DETERMINED CURVES - boundaries are cubic Beziers whose control points must
   sit where uniform Catmull-Rom at 1/6 chord puts them, computed from the
   on-curve vertices. Vertices carry the data; this pins the drawing *between*
   vertices to the vertices, so a curve cannot be reshaped to editorialise
   while every vertex stays true. Paths must be plain absolute M/C/L/Z -
   anything else is refused rather than half-parsed.

6. LABELS BOUND TO MEANING - each legend entry binds its layer and its printed
   total, and the total must equal the sum of that layer's declared values.
   Each period caption binds its column index and its visible text. Unbound,
   captions can be exchanged or a layer quietly dropped from the legend.

7. FAIL CLOSED - a file that presents as a streamgraph but yields nothing
   parseable is a finding, never a pass. A checker that reports OK because it
   found nothing to compare is the bug, not the gate.

The basis for geometry is the `data-values` list each layer's path declares,
never the rendered text. A layer whose legend entry is missing stays in the
verified set and its missing entry is itself reported.

WHAT THIS DOES NOT CHECK, deliberately:

- **Absolute truth.** Every check is internal consistency; a figure wrong by a
  constant factor everywhere is self-consistent and passes. The source line is
  where scale and bucket size are stated to a reader, and prose is not parsed.
- **The layer and period budgets.** 2-6 layers and 3-24 periods are editorial
  guidance in type-line.md, not geometry; a 30-period stream that tiles
  honestly is honest.
- **Colour.** The accent-plus-ramp rule is `lint-skin.py`'s beat.

Usage:
    python3 scripts/verify-streamgraph.py --all
    python3 scripts/verify-streamgraph.py skills/diagram-design/assets/example-streamgraph.html

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

PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
# `transform:` but not `text-transform:` - the editorial template uses the latter.
CSS_TRANSFORM_RE = re.compile(r"(?<![\w-])transform\s*:", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
# The complete numeric token a legend may print. Matching only the first
# fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")

# Both quote styles, exactly as in verify-slopegraph.py: a single-quoted layer
# that the parser cannot read must be reported, never silently dropped.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_LAYER_RE = re.compile(r"\bdata-layer\s*=", re.IGNORECASE)
# Path grammar: absolute M/C/L/Z and numbers only. Relative commands, arcs,
# shorthand curves and H/V would need a transform stack this checker refuses
# to half-implement; a partial parse looks like coverage without being it.
PATH_TOKEN_RE = re.compile(r"[MCLZmclzHhVvSsQqTtAa]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# Boundary coordinates ship rounded to 0.1px and adjacent layers may round a
# shared boundary independently; 1.0px of thickness slack clears honest
# rounding and still catches the smallest dishonest nudge worth making. At the
# shipped 1.25px-per-minute scale that is 0.8 of one build-minute.
RESIDUAL_TOLERANCE = 1.0   # px, per-period thickness vs the shared scale
STACK_TOLERANCE = 0.5      # px, between one layer's bottom and its neighbour's top
MIDLINE_TOLERANCE = 1.0    # px, envelope midline drift across periods
CONTROL_TOLERANCE = 0.75   # px, control point vs Catmull-Rom at 1/6 chord
VALUE_TOLERANCE = 0.001    # printed/declared totals vs the sum of values
CAPTION_TOLERANCE = 0.5    # px, period caption x vs its column


class Layer:
    __slots__ = ("name", "values", "top", "bottom", "offset", "controls")

    def __init__(self, name, values, top, bottom, offset):
        self.name = name
        self.values = values          # per-period, left to right
        self.top = top                # on-curve points, left to right
        self.bottom = bottom          # on-curve points, left to right
        self.offset = offset
        self.controls = []            # (boundary, segment, (c1, c2)) as drawn


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    """Comments out, length and line numbers preserved."""
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def attrs_of(raw: str) -> dict:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw)}


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value):
    """A finite float, or None - NaN satisfies every tolerance check silently."""
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def printed_number(body: str):
    """(value, reason) for a label's visible text - one complete token only."""
    match = NUMBER_RE.search(body)
    if match is None:
        return None, "prints no number"
    outside = body[:match.start()] + body[match.end():]
    if DIGIT_RE.search(outside):
        return None, "prints more than one numeric token"
    value = number(match.group())
    if value is None:
        return None, "prints a number this checker cannot read"
    return value, None


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def named_text(source: str) -> str:
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_streamgraph(path: Path, source: str) -> bool:
    """Does this file present itself as a streamgraph?

    Deliberately generous, and searched whole-document: anything that claims
    the type in its name, its accessible description, or its markup is held to
    the contract even if it declares nothing parseable - that combination is
    the fail-closed case, not a pass.
    """
    if path.name.startswith("example-streamgraph"):
        return True
    if DECLARES_LAYER_RE.search(source):
        return True
    described = named_text(source)
    return "streamgraph" in described or "stream graph" in described


def transformed_spans(source: str) -> list:
    """Offset ranges enclosed by a <g>/<svg> that carries a transform."""
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        events.append((match.start(), 0, "transform" in attrs_of(match.group("attrs"))))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, False))
    events.sort()
    stack, spans = [], []
    for position, kind, transformed in events:
        if kind == 0:
            stack.append((position, transformed))
        elif stack:
            start, was_transformed = stack.pop()
            if was_transformed:
                spans.append((start, position))
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source)))
    return spans


def parse_path_points(d: str):
    """((top_points, bottom_points_as_drawn, controls), reason).

    controls is [(sequence, segment_index, (c1, c2))] where sequence is "top"
    or "bottom" and segment_index counts C commands within that boundary.
    Only absolute M/C/L/Z are accepted; the exact structure is one M (start of
    the top boundary), C segments to its end, one L (drop to the bottom
    boundary), C segments back, and Z.
    """
    tokens = PATH_TOKEN_RE.findall(d)
    if "".join(tokens).replace(" ", "") != re.sub(r"[\s,]+", "", d):
        return None, "contains characters outside absolute M/C/L/Z path data"
    position = 0

    def take_numbers(count):
        nonlocal position
        taken = []
        while len(taken) < count and position < len(tokens):
            value = number(tokens[position])
            if value is None:
                return None
            taken.append(value)
            position += 1
        return taken if len(taken) == count else None

    sequences = []      # list of (command, coords)
    while position < len(tokens):
        command = tokens[position]
        position += 1
        if command in ("M", "L"):
            coords = take_numbers(2)
        elif command == "C":
            coords = take_numbers(6)
        elif command == "Z":
            coords = []
        elif command.isalpha():
            return None, "uses path command %r - only absolute M/C/L/Z are verifiable" % command
        else:
            return None, "has a number where a command was expected"
        if coords is None:
            return None, "has a malformed %s command" % command
        sequences.append((command, coords))

    if not sequences or sequences[0][0] != "M" or sequences[-1][0] != "Z":
        return None, "must begin with M and end with Z"
    if sum(1 for c, _ in sequences if c == "M") != 1:
        return None, "must contain exactly one subpath"
    if sum(1 for c, _ in sequences if c == "L") != 1:
        return None, "must contain exactly one L (the join between boundaries)"
    if sum(1 for c, _ in sequences if c == "Z") != 1:
        return None, "must contain exactly one Z"

    top, bottom, controls = [], [], []
    current, boundary = top, "top"
    top.append(tuple(sequences[0][1]))
    for command, coords in sequences[1:-1]:
        if command == "C":
            c1, c2, end = tuple(coords[0:2]), tuple(coords[2:4]), tuple(coords[4:6])
            controls.append((boundary, len(current) - 1, (c1, c2)))
            current.append(end)
        elif command == "L":
            if boundary == "bottom":
                return None, "must contain exactly one L"
            current, boundary = bottom, "bottom"
            bottom.append(tuple(coords))
    if len(top) < 3 or len(bottom) != len(top):
        return None, ("draws %d top and %d bottom vertices - both boundaries need "
                      "one on-curve vertex per period, at least three periods"
                      % (len(top), len(bottom)))
    return (top, bottom, controls), None


def parse_layers(source: str, findings: list, name: str) -> list:
    """Layer paths, with anything unparseable reported rather than dropped."""
    layers = []
    seen = set()
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        label = attrs.get("data-layer")
        if label is None:
            # A <path> with no data-layer is scenery. One whose raw text DOES
            # declare data-layer and still parsed to nothing is markup this
            # checker cannot read, and dropping it silently is how a lie ships.
            if DECLARES_LAYER_RE.search(raw):
                findings.append(
                    "%s:%d: a <path> declares data-layer but its attributes could "
                    "not be parsed — the checker will not silently skip markup it "
                    "cannot read. Use plain double-quoted attributes"
                    % (name, line_of(source, match.start()))
                )
            continue
        line = line_of(source, match.start())
        if label in seen:
            findings.append(
                "%s:%d: a second path declares data-layer=%r — one layer, one path"
                % (name, line, label)
            )
            continue
        missing = [key for key in ("data-values", "d") if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: layer %r is missing %s — a layer must declare its values "
                "and its geometry or it cannot be verified"
                % (name, line, label, ", ".join(missing))
            )
            continue
        values = [number(token) for token in attrs["data-values"].split(",")]
        if any(value is None for value in values):
            findings.append(
                "%s:%d: layer %r declares a value that is not a finite number — "
                "cannot verify its thickness" % (name, line, label)
            )
            continue
        if any(value < 0 for value in values):
            findings.append(
                "%s:%d: layer %r declares a negative value — a streamgraph layer "
                "is a magnitude; encode direction some other way" % (name, line, label)
            )
            continue
        parsed, reason = parse_path_points(attrs["d"])
        if parsed is None:
            findings.append("%s:%d: layer %r's path %s" % (name, line, label, reason))
            continue
        top, bottom, controls = parsed
        if len(values) != len(top):
            findings.append(
                "%s:%d: layer %r declares %d values but draws %d period vertices — "
                "every period needs exactly one declared value"
                % (name, line, label, len(values), len(top))
            )
            continue
        xs_top = [p[0] for p in top]
        xs_bottom = [p[0] for p in bottom]
        if xs_top != sorted(xs_top) or len(set(xs_top)) != len(xs_top):
            findings.append(
                "%s:%d: layer %r's top boundary does not run left to right across "
                "distinct period columns" % (name, line, label)
            )
            continue
        if xs_bottom != sorted(xs_bottom, reverse=True) or \
                sorted(round(x, 3) for x in xs_bottom) != [round(x, 3) for x in xs_top]:
            findings.append(
                "%s:%d: layer %r's bottom boundary does not mirror its top boundary's "
                "period columns right to left" % (name, line, label)
            )
            continue
        seen.add(label)
        # Store bottom left-to-right; remember the drawn order for controls.
        layers.append(Layer(label, values, top, list(reversed(bottom)), match.start()))
        layers[-1].controls = controls  # type: ignore[attr-defined]
    return layers


def check_transforms(source: str, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label."""
    spans = transformed_spans(source)

    def enclosed(offset):
        return any(start <= offset <= end for start, end in spans)

    def report(offset, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw path and label "
            "coordinates, so a transform moves the rendered mark away from the "
            "number it was checked against. Bake the offset into the coordinates "
            "instead" % (name, line_of(source, offset), what, how)
        )

    for match in PATH_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-layer" not in attrs:
            continue
        what = "layer %r" % attrs["data-layer"]
        if "transform" in attrs:
            report(match.start(), what, "transform=%r" % attrs["transform"])
        elif enclosed(match.start()):
            report(match.start(), what, "an ancestor <g>/<svg> transform")

    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-layer" not in attrs and "data-period" not in attrs \
                and "data-index" not in attrs:
            continue
        what = "a bound label (%s)" % plain(match.group("body"))[:20]
        if "transform" in attrs:
            report(match.start(), what, "transform=%r" % attrs["transform"])
        elif enclosed(match.start()):
            report(match.start(), what, "an ancestor <g>/<svg> transform")

    for match in STYLE_RE.finditer(source):
        found = CSS_TRANSFORM_RE.search(match.group("body"))
        if found:
            findings.append(
                "%s:%d: a CSS `transform` declaration — this checker cannot tell "
                "which marks it applies to, and a transform on verified geometry "
                "invalidates every coordinate here. Remove it, or bake the offset "
                "into the coordinates"
                % (name, line_of(source, match.start("body") + found.start()))
            )


def check_columns(layers: list, findings: list, source: str, name: str) -> bool:
    """Every layer must sample the same period columns. False stops geometry."""
    reference = [round(p[0], 3) for p in layers[0].top]
    agreed = True
    for layer in layers[1:]:
        columns = [round(p[0], 3) for p in layer.top]
        if columns != reference:
            findings.append(
                "%s:%d: layer %r samples periods at %s but %r samples %s — every "
                "layer must share one set of period columns or the stack cannot "
                "be verified"
                % (name, line_of(source, layer.offset), layer.name,
                   "/".join("%g" % c for c in columns[:4]) + ("…" if len(columns) > 4 else ""),
                   layers[0].name,
                   "/".join("%g" % c for c in reference[:4]) + ("…" if len(reference) > 4 else ""))
            )
            agreed = False
    return agreed


def check_scale(layers: list, findings: list, source: str, name: str) -> None:
    """Per-period thickness must equal value times one shared scale."""
    ratios = []
    for layer in layers:
        for i, value in enumerate(layer.values):
            thickness = layer.bottom[i][1] - layer.top[i][1]
            if value > 0:
                ratios.append(thickness / value)
    if not ratios:
        findings.append(
            "%s: every declared value is zero, so the scale cannot be derived and "
            "no thickness here is verifiable" % name
        )
        return
    scale = median(ratios)
    if scale <= 0:
        findings.append(
            "%s: the derived scale is not positive — layers draw their bottom "
            "boundary above their top, which is a folded geometry, not a stream"
            % name
        )
        return
    for layer in layers:
        worst = None
        for i, value in enumerate(layer.values):
            thickness = layer.bottom[i][1] - layer.top[i][1]
            drift = abs(thickness - value * scale)
            if drift > RESIDUAL_TOLERANCE and (worst is None or drift > worst[1]):
                worst = (i, drift, thickness, value)
        if worst is not None:
            i, drift, thickness, value = worst
            findings.append(
                "%s:%d: layer %r draws %.1f px of thickness at period %d where its "
                "declared value %g belongs at %.1f px on the shared scale — off by "
                "%.1f px. A zero must pinch to zero, and no band may be inflated "
                "to smooth the flow"
                % (name, line_of(source, layer.offset), layer.name, thickness, i,
                   value, value * scale, drift)
            )


def stacked_order(layers: list) -> list:
    """Layers bottom of the stack first, by mean bottom-boundary y (SVG y grows
    downward, so the bottom-most layer has the largest bottom y)."""
    return sorted(
        layers,
        key=lambda layer: -sum(p[1] for p in layer.bottom) / len(layer.bottom),
    )


def check_stack(layers: list, findings: list, source: str, name: str) -> None:
    """Layers must tile: each bottom is the previous top; envelope centred."""
    ordered = stacked_order(layers)
    for below, above in zip(ordered, ordered[1:]):
        worst = None
        for i in range(len(below.top)):
            gap = above.bottom[i][1] - below.top[i][1]
            if abs(gap) > STACK_TOLERANCE and (worst is None or abs(gap) > abs(worst[1])):
                worst = (i, gap)
        if worst is not None:
            i, gap = worst
            findings.append(
                "%s:%d: layer %r's bottom boundary sits %.1f px %s layer %r's top at "
                "period %d — the stack must tile with no gaps and no overlaps, in "
                "one fixed order, and no layer may be dropped from it silently"
                % (name, line_of(source, above.offset), above.name, abs(gap),
                   "below" if gap > 0 else "above", below.name, i)
            )

    envelope_bottom = ordered[0].bottom
    envelope_top = ordered[-1].top
    midlines = [(envelope_top[i][1] + envelope_bottom[i][1]) / 2.0
                for i in range(len(envelope_top))]
    centre = median(midlines)
    worst = None
    for i, midline in enumerate(midlines):
        drift = abs(midline - centre)
        if drift > MIDLINE_TOLERANCE and (worst is None or drift > worst[1]):
            worst = (i, drift)
    if worst is not None:
        i, drift = worst
        findings.append(
            "%s:%d: the baseline is not symmetric — the envelope midline drifts "
            "%.1f px off centre at period %d. A streamgraph centres every period "
            "on one midline (baseline = -total/2); a drifting or bottom-pinned "
            "baseline is a different chart wearing this one's name"
            % (name, line_of(source, ordered[0].offset), drift, i)
        )


def check_controls(layers: list, findings: list, source: str, name: str) -> None:
    """Control points must sit where Catmull-Rom at 1/6 chord puts them."""
    for layer in layers:
        boundaries = {
            "top": layer.top,
            "bottom": list(reversed(layer.bottom)),   # as drawn, right to left
        }
        worst = None
        for boundary, segment, (c1, c2) in layer.controls:
            points = boundaries[boundary]
            i = segment
            p0 = points[i - 1] if i > 0 else points[i]
            p1, p2 = points[i], points[i + 1]
            p3 = points[i + 2] if i + 2 < len(points) else points[i + 1]
            expected_c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
            expected_c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
            drift = max(abs(c1[0] - expected_c1[0]), abs(c1[1] - expected_c1[1]),
                        abs(c2[0] - expected_c2[0]), abs(c2[1] - expected_c2[1]))
            if drift > CONTROL_TOLERANCE and (worst is None or drift > worst[2]):
                worst = (boundary, i, drift)
        if worst is not None:
            boundary, i, drift = worst
            findings.append(
                "%s:%d: layer %r's %s boundary bends away from its vertices — a "
                "control point sits %.1f px from where Catmull-Rom at 1/6 chord "
                "puts it (segment %d). The curve between vertices is determined "
                "by the vertices; it is not free to editorialise"
                % (name, line_of(source, layer.offset), layer.name, boundary,
                   drift, i)
            )


def check_legend(layers: list, source: str, findings: list, name: str) -> None:
    """Every layer in the legend with its total; every total a sum, not a typo."""
    declared = {layer.name: layer for layer in layers}
    entries = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label = attrs.get("data-layer")
        if label is None:
            continue
        if label not in declared:
            findings.append(
                "%s:%d: a legend entry names layer %r, which no path declares — a "
                "label with no band is not verifiable and reads as data"
                % (name, line_of(source, match.start()), label)
            )
            continue
        if label in entries:
            findings.append(
                "%s:%d: a second legend entry for layer %r — one layer, one entry, "
                "or the figure states two totals for one band"
                % (name, line_of(source, match.start()), label)
            )
            continue
        entries[label] = (attrs.get("data-total"), plain(match.group("body")),
                          match.start())

    for layer in layers:
        entry = entries.get(layer.name)
        if entry is None:
            findings.append(
                "%s:%d: layer %r has no legend entry (a <text> with data-layer and "
                "data-total) — a streamgraph names every layer and prints its "
                "total, or a band can be dropped from the reading silently"
                % (name, line_of(source, layer.offset), layer.name)
            )
            continue
        declared_total, body, offset = entry
        total = number(declared_total)
        if total is None:
            findings.append(
                "%s:%d: the legend entry for %r has no readable data-total — the "
                "printed total must be bound to the number it claims to state"
                % (name, line_of(source, offset), layer.name)
            )
            continue
        expected = sum(layer.values)
        if abs(total - expected) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: layer %r declares a total of %g but its values sum to %g — "
                "the total is a sum, not a typed number"
                % (name, line_of(source, offset), layer.name, total, expected)
            )
        shown, reason = printed_number(body)
        if shown is None:
            findings.append(
                "%s:%d: the legend entry for %r %s (%r) — print exactly one "
                "complete total per entry, and keep digits out of layer names"
                % (name, line_of(source, offset), layer.name, reason, body[:28])
            )
        elif abs(shown - total) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: the legend entry for %r prints %r but declares %g — the "
                "label and the binding must state one number"
                % (name, line_of(source, offset), layer.name, body[:28], total)
            )


def check_captions(layers: list, source: str, findings: list, name: str) -> None:
    """Each period caption must sit on its own column and read its binding."""
    columns = [p[0] for p in layers[0].top]
    count = len(columns)
    seen = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-index" not in attrs and "data-period" not in attrs:
            continue
        index_raw = attrs.get("data-index")
        period = attrs.get("data-period")
        offset = match.start()
        if index_raw is None or period is None:
            findings.append(
                "%s:%d: a period caption must carry both data-index (its column) "
                "and data-period (its text) — half a binding can still be swapped"
                % (name, line_of(source, offset))
            )
            continue
        index = number(index_raw)
        if index is None or index != int(index) or not 0 <= int(index) < count:
            findings.append(
                "%s:%d: a period caption declares data-index=%r, which is not a "
                "column of this figure (0–%d)"
                % (name, line_of(source, offset), index_raw, count - 1)
            )
            continue
        index = int(index)
        if index in seen:
            findings.append(
                "%s:%d: a second caption for period %d — one column, one caption"
                % (name, line_of(source, offset), index)
            )
            continue
        seen[index] = (number(attrs.get("x")), period, plain(match.group("body")),
                       offset)

    for index in range(count):
        if index not in seen:
            findings.append(
                "%s: no caption for period %d (data-index=%r) — every bucket is "
                "named, or the reader cannot place the pinch this figure keeps"
                % (name, index, index)
            )
            continue
        x, period, body, offset = seen[index]
        expected = columns[index]
        if x is None or abs(x - expected) > CAPTION_TOLERANCE:
            findings.append(
                "%s:%d: the caption for period %d (%r) is drawn at x=%s but its "
                "column is at x=%g — a caption off its column renames the bucket"
                % (name, line_of(source, offset), index, body[:16],
                   "%g" % x if x is not None else "?", expected)
            )
        if body != period:
            findings.append(
                "%s:%d: the caption for period %d reads %r but declares "
                "data-period=%r — the visible text and its binding must agree"
                % (name, line_of(source, offset), index, body[:16], period)
            )


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    source = blank_comments(raw)
    findings: list = []
    layers = parse_layers(source, findings, path.name)

    if len(layers) < 2:
        findings.append(
            "%s: presents as a streamgraph but declares %d verifiable layer(s) — "
            "every band needs data-layer with data-values and an absolute M/C/L/Z "
            "path. Refusing to report OK on a file this checker could not read"
            % (path.name, len(layers))
        )
        return findings

    check_transforms(source, findings, path.name)
    if check_columns(layers, findings, source, path.name):
        check_scale(layers, findings, source, path.name)
        check_stack(layers, findings, source, path.name)
        check_controls(layers, findings, source, path.name)
        check_captions(layers, source, findings, path.name)
    check_legend(layers, source, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a streamgraph."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_streamgraph(path, raw):
        return []
    return check_source(path, raw)


def targets(args: argparse.Namespace) -> list:
    if args.all:
        return sorted(ASSET_DIR.glob("example-*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify streamgraph layers against the values they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a streamgraph",
    )
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    findings: list = []
    checked = 0
    skipped = 0
    for path in targets(args):
        if not path.is_file():
            print("error: %s is not a readable file" % path, file=sys.stderr)
            return 2
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print("error: cannot read %s: %s" % (path, error), file=sys.stderr)
            return 2
        if not looks_like_streamgraph(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d streamgraph finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK streamgraph: no streamgraph found to check%s" % tail)
        return 0
    print("OK streamgraph: %d file(s), one shared scale on a symmetric baseline, a "
          "tiled stack with determined curves, no transforms on verified geometry, "
          "and every total and caption bound to what it describes%s"
          % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
