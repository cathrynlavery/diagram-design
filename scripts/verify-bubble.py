#!/usr/bin/env python3
"""Verify that a bubble chart's drawn geometry matches the values it declares.

A bubble chart makes three claims at once: x and y positions come off two
shared linear scales, and AREA — never radius — carries the third value. All
three can be broken without anything erroring: the figure renders, every label
is present, and the lie is in the geometry. `lint-skin.py` reads colors and
fonts, `verify-geometry.py` reads label masks against later-painted nodes, and
neither compares a drawn coordinate or radius against the value bound to it.

Seven invariants:

1. SHARED AXIS SCALES - every bubble's cx must sit where one linear x scale
   puts its declared x value, and cy likewise for y. A single bubble nudged
   aside "to stop it overlapping" reads as a different number, and crowded
   bubbles are data, not a coordinate problem.

2. AREA, NEVER RADIUS - r^2 must be proportional to the declared size across
   the whole set, i.e. r = K*sqrt(size) for one shared K. This is the type's
   one unforgivable error: a radius proportional to the value shows a 6x
   service as 36x the ink. Per-bubble consistency catches the global version
   too, because under r = c*size the ratio r^2/size is not constant.

3. ONE ACCENT BUBBLE - at most one bound circle may carry the accent stroke,
   on either skin. A second accent bubble is a second "focal" claim, and the
   one-accent rule is the whole colour system of the house style.

4. LARGEST FIRST - where two bubbles overlap, the one painted earlier must be
   the larger, or the smaller is buried under it and its area cannot be read.
   Ties pass: equal radii cannot bury each other in a way paint order fixes.

5. BOUND LABELS ON THEIR OWN BUBBLE - a label names the bubble it is bound to,
   its visible text matches the binding (case aside - labels ship small-caps),
   and it sits nearer its own bubble's centre than any other's. Two labels
   exchanged between bubbles rename both while every number stays correct.

6. BOUND TICKS ON THE SAME SCALE - each axis needs at least two tick labels
   bound with data-tick/data-value, each printing exactly the number it
   declares and drawn where the bubbles' own scale puts that value. Unbound
   axis numbers are the cheapest way to relabel a whole chart.

7. FAIL CLOSED - a file that presents as a bubble chart but yields fewer than
   four parseable bubbles is a finding, never a pass. Four because the outlier
   test is leave-one-out and each fit needs three points; below that nothing
   here is verifiable, and a checker that reports OK because it found nothing
   to compare is the bug, not the gate. The same rule covers a bubble whose
   peers all share one value on an axis: its leave-one-out fit is degenerate,
   so it would define the scale rather than be checked against it, and an
   unmeasurable mark is reported rather than skipped.

The basis for geometry is the `data-x` / `data-y` / `data-size` triple each
bubble circle declares, never the rendered text. The scales are derived from
the set itself (Theil-Sen, leave-one-out), so one dishonest bubble cannot drag
the line it is measured against.

Deliberately NOT `data-series`: that attribute belongs to the slopegraph
contract, and `verify-slopegraph.py` claims any file that uses it. A bubble
file is detected by `data-size`, its filename, or its accessible description.

WHAT THIS DOES NOT CHECK, deliberately:

- **Absolute truth.** Every check is internal consistency; a figure wrong by
  one constant everywhere is self-consistent. The source line states the
  domain and the area scale to the reader, and prose is not parsed.
- **Axis direction.** A y that grows downward with the value is accepted; an
  inverted axis is a legitimate design (error rate reading "up is worse").
- **Zero-based axes.** Whether the domain includes zero is stated in the
  source line, which this checker cannot read. The ticks it CAN read are
  pinned to the same scale as the bubbles, which is the checkable half.

Usage:
    python3 scripts/verify-bubble.py --all
    python3 scripts/verify-bubble.py skills/diagram-design/assets/example-bubble.html

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

CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
# `transform:` but not `text-transform:`. The full-editorial template uses the
# latter, so an unguarded pattern would report every editorial variant.
CSS_TRANSFORM_RE = re.compile(r"(?<![\w-])transform\s*:", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
# The COMPLETE numeric token an author may print: sign, comma-grouped
# thousands, decimals, leading-dot decimals, exponents. Matching only the
# first fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")

# Both quote styles: matching only double quotes drops a single-quoted circle
# from the verified set without a word, which is exactly how a lie ships.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_BUBBLE_RE = re.compile(r"\bdata-size\s*=", re.IGNORECASE)

# The accent stroke on either skin, hex or rgba. The focal count keys on the
# STROKE because the fill is a translucent tint the paper shows through; the
# stroke is the mark's edge and the thing a reader identifies the accent by.
ACCENT_RE = re.compile(
    r"#eb6c36\b|#f08a59\b|rgba\(\s*235\s*,\s*108\s*,\s*54\b|rgba\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)

# Coordinates ship rounded to one decimal, so an honest point sits within
# 0.05px of true; whole-pixel rounding sits within 0.5px. 1.0px clears both
# and still catches the smallest dishonest nudge worth making.
RESIDUAL_TOLERANCE = 1.0   # px, drawn centre vs the shared axis scale
RADIUS_TOLERANCE = 1.0     # px, drawn radius vs the shared area scale
VALUE_TOLERANCE = 0.001    # printed tick label vs declared attribute
# Tick text is placed beside its gridline, not on it: an x tick's anchor sits
# on the tick, but a y tick's BASELINE hangs ~4px below the line it names.
# 6px absorbs that offset; a swapped tick pair is off by a full gridline gap.
TICK_TOLERANCE = 6.0       # px, tick position vs the scale the bubbles set
LABEL_TOLERANCE = 0.5      # px, slack before a label counts as another bubble's
OVERLAP_SLACK = 0.5        # px, separation below which two bubbles overlap


class Bubble:
    __slots__ = ("name", "x", "y", "size", "cx", "cy", "r", "accent", "offset")

    def __init__(self, name, x, y, size, cx, cy, r, accent, offset):
        self.name = name
        self.x, self.y, self.size = x, y, size
        self.cx, self.cy, self.r = cx, cy, r
        self.accent = accent
        self.offset = offset


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    """Comments out, length and line numbers preserved.

    Markup inside a comment is not rendered, so treating it as data reports a
    commented-out old draft as a live defect. Replacing each comment with
    spaces of the same length keeps every later offset and line number honest.
    """
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def attrs_of(raw: str) -> dict:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw)}


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value):
    """A finite float from a complete numeric token, or None.

    `float("nan")` succeeds and then every `abs(x) > tolerance` comparison is
    False, so a NaN coordinate silently satisfies every check in the file.
    Any non-finite value is treated as unreadable instead.
    """
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def printed_number(body: str):
    """(value, reason) for a label's visible text.

    Returns a value only when the text carries exactly one complete numeric
    token. Trailing units are fine ("500ms"); a second number, or digits the
    token did not consume, is ambiguous and reported rather than guessed at.
    """
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


def fit(points: list) -> tuple:
    """Robust (slope, intercept) for coordinate = slope * value + intercept.

    Theil-Sen - the median of all pairwise slopes - rather than least squares,
    so one dishonest bubble does not drag the line it is measured against.
    Returns (None, None) when every value is the same, which the caller
    reports: an axis with one distinct value has no derivable scale.
    """
    slopes = [
        (cb - ca) / (vb - va)
        for index, (va, ca) in enumerate(points)
        for vb, cb in points[index + 1:]
        if vb != va
    ]
    if not slopes:
        return None, None
    slope = median(slopes)
    return slope, median([c - slope * v for v, c in points])


def outliers(points: list, tolerance: float) -> list:
    """Points that disagree with the line their PEERS describe.

    Leave-one-out, because measuring a point against a fit that includes it
    lets it hide inside its own influence. Needs four points, so each fit is
    made from at least three - which is why fewer than four bubbles is the
    fail-closed case rather than a smaller check.

    Returns [(index, drawn, expected)].
    """
    if len(points) < 4:
        return []
    found = []
    for index, (value, drawn) in enumerate(points):
        peers = points[:index] + points[index + 1:]
        slope, intercept = fit(peers)
        if slope is None:
            continue
        expected = slope * value + intercept
        if abs(drawn - expected) > tolerance:
            found.append((index, drawn, expected))
    return found


def named_text(source: str) -> str:
    """The accessible name and description, where a figure says what it is."""
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_bubble(path: Path, source: str) -> bool:
    """Does this file present itself as a bubble chart?

    Deliberately generous - anything that claims the type in its name, its
    accessible description, or its markup is held to the contract, and a file
    that claims it while declaring nothing parseable is the fail-closed case,
    not a pass. Scoped to bubble-specific signals only: `data-size` rather
    than `data-series`, so this checker and `verify-slopegraph.py` never claim
    one another's files.
    """
    if path.name.startswith("example-bubble"):
        return True
    if DECLARES_BUBBLE_RE.search(source):
        return True
    described = named_text(source)
    return "bubble chart" in described or "bubble plot" in described


def transformed_spans(source: str) -> list:
    """Offset ranges enclosed by a <g>/<svg> that carries a transform.

    Element-level transforms are easy to see; an ancestor's is not, and shifts
    everything inside it identically - exactly the change that leaves all
    internal consistency intact while moving every mark on the page.
    """
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
    # An unclosed transformed group covers everything after it.
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source)))
    return spans


def parse_bubbles(source: str, findings: list, name: str) -> list:
    """Bubble circles, with anything unparseable reported rather than dropped."""
    bubbles = []
    for match in CIRCLE_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        if "data-size" not in attrs:
            # A <circle> with no data-size is scenery - a paper underlay, a
            # legend swatch, a dot-grid cell - and skipping it is correct. But
            # one whose raw text DOES declare data-size and still parsed to
            # nothing is markup this checker cannot read, and dropping it
            # silently is how a lie ships.
            if DECLARES_BUBBLE_RE.search(raw):
                findings.append(
                    "%s:%d: a <circle> declares data-size but its attributes could "
                    "not be parsed — the checker will not silently skip markup it "
                    "cannot read. Use plain quoted attributes"
                    % (name, line_of(source, match.start()))
                )
            continue
        label = attrs.get("data-name")
        if label is None:
            findings.append(
                "%s:%d: a bubble declares data-size but no data-name — an unnamed "
                "bubble cannot be labelled or cross-checked"
                % (name, line_of(source, match.start()))
            )
            continue
        missing = [key for key in ("data-x", "data-y", "cx", "cy", "r")
                   if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: bubble %r is missing %s — a bubble must declare all three "
                "values and all three drawn quantities or it cannot be verified"
                % (name, line_of(source, match.start()), label, ", ".join(missing))
            )
            continue
        parsed = [number(attrs[key])
                  for key in ("data-x", "data-y", "data-size", "cx", "cy", "r")]
        if any(value is None for value in parsed):
            findings.append(
                "%s:%d: bubble %r has a value or coordinate that is not a finite "
                "number — cannot verify its position or area"
                % (name, line_of(source, match.start()), label)
            )
            continue
        if parsed[2] <= 0:
            # Area cannot encode a non-positive value; the honest treatment of
            # a zero or missing measurement is to omit the bubble and count the
            # omission in the source line, exactly as the reference says.
            findings.append(
                "%s:%d: bubble %r declares data-size=%g — area cannot encode a "
                "non-positive value. Omit the item and note the omission in the "
                "source line" % (name, line_of(source, match.start()), label,
                                 parsed[2])
            )
            continue
        if parsed[5] <= 0:
            findings.append(
                "%s:%d: bubble %r has r=%g — a bubble with no area states no value"
                % (name, line_of(source, match.start()), label, parsed[5])
            )
            continue
        accent = bool(ACCENT_RE.search(attrs.get("stroke", "")))
        bubbles.append(Bubble(label, parsed[0], parsed[1], parsed[2], parsed[3],
                              parsed[4], parsed[5], accent, match.start()))
    return bubbles


def check_transforms(source: str, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label."""
    spans = transformed_spans(source)

    def enclosed(offset):
        return any(start <= offset <= end for start, end in spans)

    def report(offset, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw cx/cy/r and x/y "
            "attributes, so a transform moves the rendered mark away from the "
            "number it was checked against. Bake the offset into the coordinates "
            "instead" % (name, line_of(source, offset), what, how)
        )

    for match in CIRCLE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-size" not in attrs:
            continue
        what = "bubble %r" % attrs.get("data-name", "?")
        if "transform" in attrs:
            report(match.start(), what, "transform=%r" % attrs["transform"])
        elif enclosed(match.start()):
            report(match.start(), what, "an ancestor <g>/<svg> transform")

    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-name" not in attrs and "data-tick" not in attrs:
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


def check_axis(bubbles: list, axis: str, findings: list, source: str,
               name: str):
    """One shared linear scale per axis, and no bubble may drift off it.

    Returns the (slope, intercept) fit for the axis so the tick check can
    measure against the same scale, or (None, None) when none is derivable.
    """
    if axis == "x":
        points = [(b.x, b.cx) for b in bubbles]
        drawn_attr = "cx"
    else:
        points = [(b.y, b.cy) for b in bubbles]
        drawn_attr = "cy"
    line = line_of(source, bubbles[0].offset)

    slope, intercept = fit(points)
    if slope is None:
        findings.append(
            "%s:%d: the %s axis has no two distinct declared values, so its scale "
            "cannot be derived and no position on it is verifiable"
            % (name, line, axis)
        )
        return None, None

    # A bubble whose PEERS all share one value cannot be measured: the
    # leave-one-out fit for it is degenerate, so `outliers` skips it, and the
    # full-set fit passes exactly through wherever it was drawn — its position
    # would define the scale rather than be checked by it. Fail closed: that
    # is an unverifiable mark, not a pass. (Greptile flagged the silent skip.)
    for index, (value, _drawn) in enumerate(points):
        peer_values = {points[i][0] for i in range(len(points)) if i != index}
        if len(peer_values) < 2:
            b = bubbles[index]
            findings.append(
                "%s:%d: bubble %r holds the only distinct %s value (%g) — its "
                "peers cannot describe a scale to check it against, so its "
                "position would define the axis instead of being verified by "
                "it. An axis needs two distinct values among the other bubbles"
                % (name, line_of(source, b.offset), b.name, axis, value)
            )

    for index, drawn, expected in outliers(points, RESIDUAL_TOLERANCE):
        b = bubbles[index]
        findings.append(
            "%s:%d: bubble %r declares %s=%g but draws %s=%g where the shared %s "
            "scale its peers describe puts it at %.1f — off by %.1f px. Crowded "
            "bubbles are data; never nudge one aside"
            % (name, line_of(source, b.offset), b.name, axis,
               points[index][0], drawn_attr, drawn, axis, expected,
               abs(drawn - expected))
        )
    return slope, intercept


def check_area(bubbles: list, findings: list, source: str, name: str) -> None:
    """r must equal K*sqrt(size) for one K shared by the whole set.

    The ratio r^2/size is constant under honest area encoding and varies under
    every dishonest alternative - radius-proportional sizing makes it grow
    linearly with the value, and a single inflated bubble moves only its own
    ratio. Leave-one-out again, so the offender is measured against its peers.
    """
    if len(bubbles) < 4:
        return
    ratios = [b.r * b.r / b.size for b in bubbles]
    for index, b in enumerate(bubbles):
        peers = ratios[:index] + ratios[index + 1:]
        expected = math.sqrt(median(peers) * b.size)
        if abs(b.r - expected) > RADIUS_TOLERANCE:
            findings.append(
                "%s:%d: bubble %r declares size %g but draws r=%g where the area "
                "scale its peers share puts %.1f — area must be proportional to "
                "the value (r = K*sqrt(size)), and radius-proportional sizing "
                "shows a 6x value as 36x the ink"
                % (name, line_of(source, b.offset), b.name, b.size, b.r, expected)
            )


def check_focal(bubbles: list, findings: list, source: str, name: str) -> None:
    """At most one bubble wears the accent."""
    accented = [b for b in bubbles if b.accent]
    for extra in accented[1:]:
        findings.append(
            "%s:%d: bubble %r also carries the accent stroke — one accent bubble "
            "max (%r already has it). A second focal mark is a second editorial "
            "claim, and the ink ramp exists so everything else stays ranked "
            "without spending the accent"
            % (name, line_of(source, extra.offset), extra.name, accented[0].name)
        )


def check_paint_order(bubbles: list, findings: list, source: str, name: str) -> None:
    """Where two bubbles overlap, the larger must be painted first.

    Painted later means painted on top: a small bubble under a large one is
    invisible and its area unreadable. Ties pass - equal radii cannot bury
    each other in a way order fixes - and separation by at least a hairline
    is the honest fix for near-touching bubbles, so only true overlap counts.
    """
    for index, a in enumerate(bubbles):
        for b in bubbles[index + 1:]:
            gap = math.hypot(a.cx - b.cx, a.cy - b.cy) - (a.r + b.r)
            if gap < -OVERLAP_SLACK and a.r < b.r:
                findings.append(
                    "%s:%d: bubble %r (r=%g) overlaps %r (r=%g) but is painted "
                    "first — draw overlapping bubbles largest-first so the small "
                    "one stays on top and both areas stay readable"
                    % (name, line_of(source, a.offset), a.name, a.r, b.name, b.r)
                )


def check_labels(bubbles: list, source: str, findings: list, name: str) -> None:
    """Bound labels must name a real bubble, match it, and sit on it."""
    centres = {b.name: (b.cx, b.cy) for b in bubbles}
    seen = set()
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label = attrs.get("data-name")
        if label is None:
            continue
        offset = match.start()
        body = plain(match.group("body"))
        if label not in centres:
            findings.append(
                "%s:%d: a label names bubble %r, which no circle declares — a "
                "label with no mark is not verifiable and reads as data"
                % (name, line_of(source, offset), label)
            )
            continue
        if label in seen:
            findings.append(
                "%s:%d: a second label for bubble %r — one bubble, one label, or "
                "the figure states two things about one mark"
                % (name, line_of(source, offset), label)
            )
            continue
        seen.add(label)
        # Case-insensitive: labels ship small-caps ("PAYMENTS" for a bubble
        # named "Payments"), and casing is presentation, not identity.
        if body.casefold() != label.casefold():
            findings.append(
                "%s:%d: a label bound to bubble %r reads %r — the visible text "
                "and the binding must agree"
                % (name, line_of(source, offset), label, body[:28])
            )
            continue
        x, y = number(attrs.get("x")), number(attrs.get("y"))
        if x is None or y is None:
            findings.append(
                "%s:%d: the label for bubble %r has no readable x/y, so its "
                "placement cannot be checked"
                % (name, line_of(source, offset), label)
            )
            continue
        own_cx, own_cy = centres[label]
        own = math.hypot(x - own_cx, y - own_cy)
        nearest = min(
            (other for other in centres if other != label),
            key=lambda other: math.hypot(x - centres[other][0],
                                         y - centres[other][1]),
            default=None,
        )
        if nearest is not None:
            near = math.hypot(x - centres[nearest][0], y - centres[nearest][1])
            if near < own - LABEL_TOLERANCE:
                findings.append(
                    "%s:%d: the label for bubble %r is drawn at (%g, %g), nearer "
                    "%r's centre than its own — a label on the wrong bubble "
                    "renames the mark"
                    % (name, line_of(source, offset), label, x, y, nearest)
                )


def check_ticks(x_fit, y_fit, source: str, findings: list, name: str) -> None:
    """Bound axis ticks must print their value and sit on the bubbles' scale."""
    ticks = {"x": [], "y": []}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        axis = attrs.get("data-tick")
        if axis is None:
            continue
        offset = match.start()
        if axis not in ("x", "y"):
            findings.append(
                "%s:%d: a tick label has data-tick=%r, which is neither 'x' nor "
                "'y'" % (name, line_of(source, offset), axis)
            )
            continue
        declared = number(attrs.get("data-value"))
        if declared is None:
            findings.append(
                "%s:%d: a %s tick has no readable data-value — an unbound axis "
                "number is the cheapest way to relabel a whole chart"
                % (name, line_of(source, offset), axis)
            )
            continue
        body = plain(match.group("body"))
        shown, reason = printed_number(body)
        if shown is None:
            findings.append(
                "%s:%d: the %s tick for %g %s (%r) — print one complete number "
                "per tick" % (name, line_of(source, offset), axis, declared,
                              reason, body[:28])
            )
            continue
        if abs(shown - declared) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: a %s tick prints %r but declares %g — the label and the "
                "binding must state one number"
                % (name, line_of(source, offset), axis, body[:28], declared)
            )
            continue
        position = number(attrs.get("x" if axis == "x" else "y"))
        if position is None:
            findings.append(
                "%s:%d: the %s tick for %g has no readable position"
                % (name, line_of(source, offset), axis, declared)
            )
            continue
        ticks[axis].append((declared, position, offset))

    for axis, fit_pair in (("x", x_fit), ("y", y_fit)):
        entries = ticks[axis]
        if len({value for value, _pos, _off in entries}) < 2:
            findings.append(
                "%s: the %s axis binds %d distinct tick value(s) — an axis needs "
                "at least two bound ticks (data-tick/data-value) or its printed "
                "scale is unverifiable against the drawn one"
                % (name, axis, len({v for v, _p, _o in entries}))
            )
            continue
        slope, intercept = fit_pair
        if slope is None:
            continue  # already reported by check_axis
        for value, position, offset in entries:
            expected = slope * value + intercept
            if abs(position - expected) > TICK_TOLERANCE:
                findings.append(
                    "%s:%d: the %s tick for %g is drawn at %g but the scale the "
                    "bubbles themselves describe puts that value at %.1f — the "
                    "printed axis and the drawn positions disagree, so every "
                    "reading off this axis is wrong"
                    % (name, line_of(source, offset), axis, value, position,
                       expected)
                )


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    source = blank_comments(raw)
    findings: list = []
    bubbles = parse_bubbles(source, findings, path.name)

    if len(bubbles) < 4:
        findings.append(
            "%s: presents as a bubble chart but declares %d verifiable bubble(s) "
            "— each needs data-name, data-x, data-y, data-size, cx, cy and r, "
            "and the leave-one-out scale test needs four. Refusing to report OK "
            "on a file this checker could not read" % (path.name, len(bubbles))
        )
        return findings

    check_transforms(source, findings, path.name)
    x_fit = check_axis(bubbles, "x", findings, source, path.name)
    y_fit = check_axis(bubbles, "y", findings, source, path.name)
    check_area(bubbles, findings, source, path.name)
    check_focal(bubbles, findings, source, path.name)
    check_paint_order(bubbles, findings, source, path.name)
    check_labels(bubbles, source, findings, path.name)
    check_ticks(x_fit, y_fit, source, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a bubble chart."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_bubble(path, raw):
        return []
    return check_source(path, raw)


def targets(args: argparse.Namespace) -> list:
    if args.all:
        return sorted(ASSET_DIR.glob("example-*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify bubble positions and areas against the values they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a bubble chart",
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
        # Read once, then decide. Scope is reported separately from
        # verification in both modes: printing "1 file(s) verified" for a
        # scatter that was skipped is a claim the run never made good on.
        if not looks_like_bubble(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d bubble finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK bubble: no bubble chart found to check%s" % tail)
        return 0
    print("OK bubble: %d file(s), shared x and y scales, area proportional to every "
          "declared size, at most one accent bubble, largest-first paint order, and "
          "every bound label and tick agreeing with the mark it describes%s"
          % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
