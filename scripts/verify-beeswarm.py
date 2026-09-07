#!/usr/bin/env python3
"""Verify that a beeswarm's drawn dots match the values they declare.

A beeswarm makes one hard claim and one hard disclaimer: every dot sits
EXACTLY at its value on one shared linear value axis, and the perpendicular
(swarm) offset is packing only — it carries no value at all. Both halves can
be broken without anything erroring: a dot nudged along the value axis "to
open up space" renders fine and reads as a different number, and two dots
overprinted instead of dodged turn density into darkness, which the eye reads
as a value. `lint-skin.py` reads colors and fonts and `verify-geometry.py`
reads label masks; neither compares a drawn coordinate against the value
bound to it.

Nine invariants:

1. SHARED VALUE SCALE - every dot's position on the value axis must sit where
   one linear scale puts its declared value. Two dots declaring the same
   value must draw the same position, and the scale itself is derived from
   the distinct values (Theil-Sen, leave-one-out), so one dishonest dot
   cannot drag the line it is measured against. This is the mechanical form
   of the type's honest-data rule: overlap is NEVER resolved by moving a dot
   along the value axis.

2. NO OVERPRINT - no two dots may overlap. The dodge is the only honest
   resolution of crowding: two requests at the same latency read as swarm
   thickness, never as one darker dot. A pair closer than two radii is a
   packing failure this checker refuses to wave through.

3. ONE RADIUS - every dot shares one radius, focal included. Dot size as a
   second encoding is a bubble chart wearing the wrong name, and a bigger
   focal dot would also break the packing the no-overlap rule depends on.

4. ONE NON-FOCAL INK - every non-accent dot declares the same fill. Opacity
   as a value encoding while also dodging says one thing twice in two
   different lies; the swarm's only density cue is thickness.

5. AT MOST ONE ACCENT DOT - one focal claim per figure, on either skin.

6. UNPOSITIONED GEOMETRY - every coordinate read here is a raw attribute,
   so anything that positions a mark afterwards invalidates the check that
   passed. Two axes, and this check has been widened along both:

   CARRIER - a `transform` attribute, an inline `style="..."`, or a rule in
   a <style> block, on a dot, on a bound label or tick, or on an ancestor.
   Reading the attribute alone let `style="transform: translateX(...)"`
   slide a dot past every position check and still report clean.

   PROPERTY - `transform:` is one of four spellings. CSS Transforms Level 2
   splits it into `translate`/`rotate`/`scale`, which compose with it, so
   `style="translate: 80px 0"` moved a mark with the word "transform" never
   appearing. The SVG geometry properties (cx/cy/r/x/y) are shorter still:
   CSS beats the presentation attribute, so a rule replaces the very number
   verified here. CSS_MOVES_MARK_RE carries the full set.

   Rejected rather than resolved, as in verify-slopegraph.py: a partial
   implementation of the SVG transform stack is worse than an honest
   refusal, because it looks like coverage. The enumeration is the weak
   point and it is named as such - a property nobody here thought of is a
   door, which is why the set is spelled out at its definition.

7. BOUND LABELS, BOTH WAYS, ON A UNIQUE NAME - a dot that declares data-name
   has exactly one label bound to it and vice versa; the visible text matches
   the binding (case aside - labels ship small-caps); and each label sits
   nearer its own dot than any other named dot along the value axis, because
   two labels exchanged between outliers rename both while every number stays
   correct. The name itself must be non-empty and unique: identity is a map
   key, and a map key collides silently, so two dots sharing one data-name
   collapsed into a single entry and one label satisfied both. At most 6 dots
   are named - past that the tail is a list, not a story.

8. BOUND TICKS ON THE DOTS' SCALE - the value axis needs at least two tick
   labels bound with data-tick="x"/data-value, each printing exactly the
   number it declares and drawn where the dots' own scale puts that value.
   data-tick="y" is itself a finding: the swarm axis has no scale to tick.

9. FAIL CLOSED - a file that presents as a beeswarm but yields fewer than
   four dots on four distinct values is a finding, never a pass. Four
   because the scale test is leave-one-out and each fit needs three points;
   below that nothing here is verifiable. The documented budget (20-300
   dots) is enforced at BOTH ends on top of that floor.

The basis for geometry is the `data-value` each dot circle declares, never
the rendered text.

Vocabulary treaty: `data-value` ON A <circle> is the beeswarm contract.
Detection is deliberately element-scoped - the bubble contract puts
`data-value` on its <text> axis ticks (as does this one), so a source-wide
regex would claim every shipped bubble file. `data-series` (slopegraph),
`data-ranks` (bump) and `data-size` (bubble) are never bound here, so no
sibling checker claims a beeswarm file and this one claims none of theirs.

WHAT THIS DOES NOT CHECK, deliberately:

- **Absolute truth.** Every check is internal consistency; a figure wrong by
  one constant everywhere is self-consistent. The source line states the
  domain to the reader, and prose is not parsed.
- **The packing algorithm.** Which free slot a dot dodged to is presentation;
  any arrangement passes so long as no dot overprints another and none moved
  along the value axis. There is nothing to verify about an axis that
  carries no meaning except that nothing pretends it does.
- **Log scales.** The shipped grammar is linear only; a log-scaled swarm
  would need its own declaration before this checker could hold it to
  anything, so it is refused by the scale check rather than half-trusted.

Usage:
    python3 scripts/verify-beeswarm.py --all
    python3 scripts/verify-beeswarm.py skills/diagram-design/assets/example-beeswarm.html

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
# Every CSS property that can move or resize a mark WITHOUT touching the
# attributes this checker reads. The enumeration IS the invariant, and it has
# already been wrong twice: `transform:` alone missed `style="transform: ..."`
# entirely, and once that was fixed `style="translate: 80px 0"` walked past it
# too, because CSS Transforms Level 2 splits the transform into four separate
# properties. Three families reach a mark:
#
#   transform / translate / rotate / scale   the four transform properties;
#       the individual three compose WITH `transform`, so each is its own door
#   cx / cy / r / x / y                      SVG geometry properties. CSS wins
#       over the presentation attribute, so a rule here replaces the very
#       number that was verified - a more direct lie than any transform
#   offset and its path/distance/position/anchor/rotate longhands
#       CSS motion path, which places the element somewhere else entirely
#
# Anchored to a declaration start, so `text-transform:` (the full-editorial
# skin uses it) and `--custom:` never match, and the `rotate` inside
# `transform: rotate(45deg)` is read once as the property and never as the
# function in its value. A vendor prefix is optional so `-webkit-transform:`
# is not a free pass.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|cx|cy|r|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
# The COMPLETE numeric token an author may print: sign, comma-grouped
# thousands, decimals, leading-dot decimals, exponents. Matching only the
# first fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")

# Both quote styles: matching only double quotes drops a single-quoted dot
# from the verified set without a word, which is exactly how a lie ships.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
# The scope key - checked against a <circle>'s RAW attribute text, never the
# whole source (bubble ticks put data-value on <text>) and never only the
# parsed attributes (a circle whose markup is too broken to parse must still
# be claimed, so the breakage is a finding rather than a silent skip).
DECLARES_VALUE_RE = re.compile(r"\bdata-value\s*=", re.IGNORECASE)

# The accent stroke on either skin, hex or rgba. The focal count keys on the
# STROKE: it is the mark's edge and the thing a reader identifies the accent
# by, and an accent FILL on a muted-stroked dot already fails the one-ink
# rule instead.
ACCENT_RE = re.compile(
    r"#eb6c36\b|#f08a59\b|rgba\(\s*235\s*,\s*108\s*,\s*54\b|rgba\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)

# Coordinates ship rounded to one decimal, so an honest point sits within
# 0.05px of true; whole-pixel rounding sits within 0.5px. 1.0px clears both
# and still catches the smallest dishonest nudge worth making.
RESIDUAL_TOLERANCE = 1.0   # px, drawn position vs the shared value scale
SAME_VALUE_TOLERANCE = 1.0 # px, two dots declaring one value must share a position
RADIUS_TOLERANCE = 0.01    # px, the radius is a designed constant, not data
VALUE_TOLERANCE = 0.001    # printed tick label vs declared attribute
# Tick text is placed beside its gridline, not on it; 6px absorbs the anchor
# offset while a swapped tick pair is off by a full gridline gap.
TICK_TOLERANCE = 6.0       # px, tick position vs the scale the dots set
LABEL_TOLERANCE = 0.5      # px, slack before a label counts as another dot's
OVERLAP_SLACK = 0.5        # px, separation below which two dots overprint

MIN_DOTS, MAX_DOTS = 20, 300   # the documented budget, enforced at both ends
MAX_NAMED = 6                  # labeled dots; past this the tail is a list


class Dot:
    __slots__ = ("value", "cx", "cy", "r", "name", "fill", "accent", "offset")

    def __init__(self, value, cx, cy, r, name, fill, accent, offset):
        self.value = value
        self.cx, self.cy, self.r = cx, cy, r
        self.name = name
        self.fill = fill
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
    found = {}
    for match in ATTR_RE.finditer(raw):
        name = match.group("name").lower()
        if name not in found:            # a browser keeps the FIRST of a repeat
            found[name] = html.unescape(match.group("value"))
    return found


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value):
    """A finite float from a numeric token, or None.

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
    so one dishonest dot does not drag the line it is measured against.
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


def named_text(source: str) -> str:
    """The accessible name and description, where a figure says what it is."""
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_beeswarm(path: Path, source: str) -> bool:
    """Does this file present itself as a beeswarm?

    Deliberately generous on everything EXCEPT the element scope: a file that
    claims the type in its name, its accessible description, or by binding
    data-value on any <circle> is held to the contract, and one that claims
    it while declaring nothing parseable is the fail-closed case, not a pass.
    The circle restriction is the treaty line - `data-value` also appears on
    <text> axis ticks in the bubble contract (and this one), so matching the
    raw source would claim every shipped bubble file.
    """
    if path.name.startswith("example-beeswarm"):
        return True
    if DECLARES_VALUE_RE.search(source):
        for match in CIRCLE_RE.finditer(source):
            if DECLARES_VALUE_RE.search(match.group("attrs")):
                return True
    return "beeswarm" in named_text(source)


def transform_carrier(attrs: dict):
    """How this element carries a transform, phrased for the finding, or None.

    A transform reaches the renderer by three carriers and the `transform`
    ATTRIBUTE is only the most visible one. Reading the attribute alone let
    `style="transform: translateX(...)"` on a dot, a bound label, a tick or an
    ancestor group move the rendered mark after its raw coordinates had
    already been validated, and the file still reported clean. The third
    carrier, a rule in a <style> block, is reported separately because
    nothing here can tell which marks such a rule selects.
    """
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(style)
        if found is not None:
            return "style=%r (the %s property)" % (style, found.group("prop").lower())
    return None


def transformed_spans(source: str) -> list:
    """(start, end, how) for each range enclosed by a transformed <g>/<svg>.

    Element-level transforms are easy to see; an ancestor's is not, and shifts
    everything inside it identically - exactly the change that leaves all
    internal consistency intact while moving every mark on the page. Both
    element carriers count on a group: the attribute and an inline style.
    """
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        how = None
        if "transform" in attrs:
            how = "an ancestor <g>/<svg> transform"
        elif transform_carrier(attrs) is not None:
            how = "an ancestor <g>/<svg> style transform"
        events.append((match.start(), 0, how))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    # Sort on (offset, kind) only. The third field is a message now, so a
    # bare sort() would compare a str against None to break a tie and raise.
    events.sort(key=lambda event: (event[0], event[1]))
    stack, spans = [], []
    for position, kind, how in events:
        if kind == 0:
            stack.append((position, how))
        elif stack:
            start, was_transformed = stack.pop()
            if was_transformed:
                spans.append((start, position, was_transformed))
    # An unclosed transformed group covers everything after it.
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source), was_transformed))
    return spans


def parse_dots(source: str, findings: list, name: str) -> list:
    """Dot circles, with anything unparseable reported rather than dropped."""
    dots = []
    for match in CIRCLE_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        if "data-value" not in attrs:
            # A <circle> with no data-value is scenery - a paper underlay, a
            # legend swatch, a dot-grid cell - and skipping it is correct. But
            # one whose raw text DOES declare data-value and still parsed to
            # nothing is markup this checker cannot read, and dropping it
            # silently is how a lie ships.
            if DECLARES_VALUE_RE.search(raw):
                findings.append(
                    "%s:%d: a <circle> declares data-value but its attributes "
                    "could not be parsed — the checker will not silently skip "
                    "markup it cannot read. Use plain quoted attributes"
                    % (name, line_of(source, match.start()))
                )
            continue
        missing = [key for key in ("cx", "cy", "r") if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: a dot declares data-value=%r but is missing %s — a dot "
                "must declare its value and all three drawn quantities or it "
                "cannot be verified"
                % (name, line_of(source, match.start()), attrs["data-value"],
                   ", ".join(missing))
            )
            continue
        parsed = [number(attrs[key]) for key in ("data-value", "cx", "cy", "r")]
        if any(value is None for value in parsed):
            findings.append(
                "%s:%d: a dot has a value or coordinate that is not a finite "
                "number — cannot verify its position"
                % (name, line_of(source, match.start()))
            )
            continue
        if parsed[3] <= 0:
            findings.append(
                "%s:%d: a dot has r=%g — a dot with no area is a mark the "
                "reader cannot see, and an invisible item is an omission the "
                "source line never counted"
                % (name, line_of(source, match.start()), parsed[3])
            )
            continue
        accent = bool(ACCENT_RE.search(attrs.get("stroke", "")))
        dots.append(Dot(parsed[0], parsed[1], parsed[2], parsed[3],
                        attrs.get("data-name"), attrs.get("fill"),
                        accent, match.start()))
    return dots


def check_transforms(source: str, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label.

    Rejected rather than resolved, following verify-slopegraph.py: a partial
    implementation of the SVG transform stack is worse than an honest
    refusal, because it looks like coverage. All three carriers are held to
    that rule - the `transform` attribute, an inline `style="transform: ..."`,
    and a rule in a <style> block - because a gate that closes one of three
    doorways guards nothing at all.
    """
    spans = transformed_spans(source)

    def enclosing(offset):
        for start, end, how in spans:
            if start <= offset <= end:
                return how
        return None

    def report(offset, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw cx/cy/r and x/y "
            "attributes, so a transform moves the rendered mark away from the "
            "number it was checked against. Bake the offset into the "
            "coordinates instead" % (name, line_of(source, offset), what, how)
        )

    def check_element(offset, attrs, what):
        how = transform_carrier(attrs)
        if how is None:
            how = enclosing(offset)
        if how is not None:
            report(offset, what, how)

    for match in CIRCLE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-value" not in attrs:
            continue
        check_element(match.start(), attrs,
                      "the dot for value %s" % attrs["data-value"])

    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-name" not in attrs and "data-tick" not in attrs:
            continue
        # Named for what it is: a tick and an outlier label fail this check
        # for the same reason but are fixed in different places.
        kind = "tick" if "data-tick" in attrs else "label"
        check_element(match.start(), attrs, "a bound %s (%s)"
                      % (kind, plain(match.group("body"))[:20]))

    for match in STYLE_RE.finditer(source):
        found = CSS_MOVES_MARK_RE.search(match.group("body"))
        if found:
            findings.append(
                "%s:%d: a CSS `%s` declaration — this checker cannot tell "
                "which marks it applies to, and one that positions verified "
                "geometry invalidates every coordinate here. Remove it, or "
                "bake the offset into the coordinates"
                % (name, line_of(source, match.start("body") + found.start()),
                   found.group("prop").lower())
            )


def check_scale(dots: list, findings: list, source: str, name: str):
    """One shared linear value scale, and no dot may drift off it.

    Dots are collapsed to distinct values first: two dots declaring one value
    must share a position (their dodge is perpendicular, never along the
    axis), and the collapse also keeps Theil-Sen quadratic in the number of
    DISTINCT values rather than the number of dots, so a 300-dot swarm stays
    cheap to verify. Returns the (slope, intercept) fit so the tick check can
    measure against the same scale, or (None, None) when none is derivable.
    """
    groups: dict = {}
    for dot in dots:
        groups.setdefault(dot.value, []).append(dot)

    points = []
    for value, group in sorted(groups.items()):
        anchor = median([d.cx for d in group])
        for dot in group:
            if abs(dot.cx - anchor) > SAME_VALUE_TOLERANCE:
                findings.append(
                    "%s:%d: two dots declare the value %g but draw cx=%g and "
                    "cx=%g — dots sharing a value share a position, and their "
                    "dodge is perpendicular to the value axis, never along it"
                    % (name, line_of(source, dot.offset), value, dot.cx, anchor)
                )
        points.append((value, anchor))

    if len(points) < 2:
        findings.append(
            "%s: the value axis has no two distinct declared values, so its "
            "scale cannot be derived and no position on it is verifiable"
            % name
        )
        return None, None

    slope, intercept = fit(points)
    if len(points) >= 4:
        for index, (value, drawn) in enumerate(points):
            peers = points[:index] + points[index + 1:]
            peer_slope, peer_intercept = fit(peers)
            if peer_slope is None:
                continue
            expected = peer_slope * value + peer_intercept
            if abs(drawn - expected) > RESIDUAL_TOLERANCE:
                offender = groups[value][0]
                findings.append(
                    "%s:%d: the dot for value %g draws cx=%g where the shared "
                    "scale its peers describe puts it at %.1f — off by %.1f px. "
                    "Crowding is data; overlap is resolved by the dodge, never "
                    "by moving a dot along the value axis"
                    % (name, line_of(source, offender.offset), value, drawn,
                       expected, abs(drawn - expected))
                )
    return slope, intercept


def check_overlap(dots: list, findings: list, source: str, name: str) -> None:
    """No two dots may overprint — the dodge is the only honest resolution."""
    ordered = sorted(dots, key=lambda d: d.cx)
    for index, a in enumerate(ordered):
        for b in ordered[index + 1:]:
            if b.cx - a.cx >= a.r + b.r:
                break                      # sorted by cx: nothing further overlaps a
            gap = math.hypot(a.cx - b.cx, a.cy - b.cy) - (a.r + b.r)
            if gap < -OVERLAP_SLACK:
                findings.append(
                    "%s:%d: the dots for values %g and %g overlap by %.1f px — "
                    "crowded dots dodge perpendicular to the value axis so "
                    "density reads as thickness, never as a darker overprint"
                    % (name, line_of(source, a.offset), a.value, b.value, -gap)
                )


def check_radius(dots: list, findings: list, source: str, name: str) -> None:
    """One radius for every dot, focal included.

    The radius is a designed constant, not data — a second radius is either a
    second encoding (which is a bubble chart, a different contract) or a
    focal cue that breaks the packing the no-overlap rule depends on.
    """
    shared = median([d.r for d in dots])
    for dot in dots:
        if abs(dot.r - shared) > RADIUS_TOLERANCE:
            findings.append(
                "%s:%d: the dot for value %g has r=%g against the figure's "
                "shared r=%g — one radius for every dot, focal included. Size "
                "as a second encoding is a bubble chart, and this is not one"
                % (name, line_of(source, dot.offset), dot.value, dot.r, shared)
            )


def check_ink(dots: list, findings: list, source: str, name: str) -> None:
    """Every non-accent dot declares one identical fill.

    Opacity as a value encoding while also dodging says one thing twice in
    two different lies; thickness is the swarm's only density cue. Literal
    string comparison (whitespace aside) is deliberate: two spellings of one
    color are two chances for a later edit to fork them apart.
    """
    fills: dict = {}
    for dot in dots:
        if dot.accent:
            continue
        if dot.fill is None:
            findings.append(
                "%s:%d: the dot for value %g declares no fill attribute — the "
                "one-ink rule can only be checked against a fill declared on "
                "the mark itself"
                % (name, line_of(source, dot.offset), dot.value)
            )
            continue
        fills.setdefault(re.sub(r"\s+", "", dot.fill).casefold(), []).append(dot)
    if len(fills) > 1:
        majority = max(fills.values(), key=len)
        for group in fills.values():
            if group is majority:
                continue
            for dot in group:
                findings.append(
                    "%s:%d: the dot for value %g has fill=%r while the swarm's "
                    "shared ink is %r — one fill for every non-focal dot, "
                    "because tone would read as a value and the only honest "
                    "density cue is thickness"
                    % (name, line_of(source, dot.offset), dot.value, dot.fill,
                       majority[0].fill)
                )


def check_focal(dots: list, findings: list, source: str, name: str) -> None:
    """At most one dot wears the accent."""
    accented = [d for d in dots if d.accent]
    for extra in accented[1:]:
        findings.append(
            "%s:%d: the dot for value %g also carries the accent stroke — one "
            "accent dot max (the dot for value %g already has it). A second "
            "focal mark is a second editorial claim"
            % (name, line_of(source, extra.offset), extra.value,
               accented[0].value)
        )


def check_labels(dots: list, source: str, findings: list, name: str) -> None:
    """Named dots and bound labels pair one-to-one and sit together."""
    named = [d for d in dots if d.name is not None]
    if len(named) > MAX_NAMED:
        findings.append(
            "%s: %d dots carry data-name against a budget of %d — label the "
            "focal dot and the outliers a reader will look for; past that the "
            "tail is a list, not a story" % (name, len(named), MAX_NAMED)
        )
    # Identity is a map key, and a map key collides SILENTLY. Built as a
    # comprehension this dropped one of two dots sharing a data-name, so a
    # single label satisfied both and a file carrying two marks under one
    # name reported clean. The collision is detected here, never resolved by
    # letting the last writer win, and an ambiguous name is verified no
    # further: nothing about its position or its label is knowable.
    positions: dict = {}
    ambiguous = set()
    for dot in named:
        if not dot.name.strip():
            findings.append(
                "%s:%d: a dot declares an empty data-name — identity must be "
                "a name a label can be bound to, and an empty one binds "
                "nothing while satisfying every check that looks for a name"
                % (name, line_of(source, dot.offset))
            )
            ambiguous.add(dot.name)
            continue
        if dot.name in positions:
            findings.append(
                "%s:%d: a second dot declares data-name %r — one name, one "
                "mark. Two dots sharing a name collapse into one entry, so a "
                "single label satisfies both and neither position is checked"
                % (name, line_of(source, dot.offset), dot.name)
            )
            ambiguous.add(dot.name)
            continue
        positions[dot.name] = dot.cx
    for collided in ambiguous:
        positions.pop(collided, None)

    seen = set()
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label = attrs.get("data-name")
        if label is None:
            continue
        if label in ambiguous:
            continue      # the collision is the finding; placement is moot
        offset = match.start()
        body = plain(match.group("body"))
        if label not in positions:
            findings.append(
                "%s:%d: a label names dot %r, which no circle declares — a "
                "label with no mark is not verifiable and reads as data"
                % (name, line_of(source, offset), label)
            )
            continue
        if label in seen:
            findings.append(
                "%s:%d: a second label for dot %r — one dot, one label, or the "
                "figure states two things about one mark"
                % (name, line_of(source, offset), label)
            )
            continue
        seen.add(label)
        # Case-insensitive: labels ship small-caps ("REQ-4C1F" for a dot named
        # "req-4c1f"), and casing is presentation, not identity.
        if body.casefold() != label.casefold():
            findings.append(
                "%s:%d: a label bound to dot %r reads %r — the visible text "
                "and the binding must agree"
                % (name, line_of(source, offset), label, body[:28])
            )
            continue
        x = number(attrs.get("x"))
        if x is None:
            findings.append(
                "%s:%d: the label for dot %r has no readable x, so its "
                "placement cannot be checked"
                % (name, line_of(source, offset), label)
            )
            continue
        # Proximity along the VALUE axis only, and only against other NAMED
        # dots: a swarm label rides a leader above a dense band, so it is
        # legitimately nearer many anonymous dots than its own. The lie worth
        # catching is two outlier labels exchanged, which renames both.
        own = abs(x - positions[label])
        for other, other_x in positions.items():
            if other != label and abs(x - other_x) < own - LABEL_TOLERANCE:
                findings.append(
                    "%s:%d: the label for dot %r is drawn at x=%g, nearer "
                    "%r's position on the value axis than its own — a label "
                    "on the wrong dot renames the mark"
                    % (name, line_of(source, offset), label, x, other)
                )
                break
    for dot in named:
        if dot.name in ambiguous:
            continue      # already reported; a second finding is noise
        if dot.name not in seen:
            findings.append(
                "%s:%d: dot %r declares data-name but no label is bound to it "
                "— a name the reader never sees is a binding nothing can "
                "cross-check" % (name, line_of(source, dot.offset), dot.name)
            )


def check_ticks(scale, source: str, findings: list, name: str) -> None:
    """Bound value-axis ticks must print their value and sit on the dots' scale."""
    ticks = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        axis = attrs.get("data-tick")
        if axis is None:
            continue
        offset = match.start()
        if axis != "x":
            findings.append(
                "%s:%d: a tick label has data-tick=%r — a beeswarm has one "
                "value axis (data-tick=\"x\"); the swarm axis has no scale to "
                "tick" % (name, line_of(source, offset), axis)
            )
            continue
        declared = number(attrs.get("data-value"))
        if declared is None:
            findings.append(
                "%s:%d: a tick has no readable data-value — an unbound axis "
                "number is the cheapest way to relabel a whole chart"
                % (name, line_of(source, offset))
            )
            continue
        body = plain(match.group("body"))
        shown, reason = printed_number(body)
        if shown is None:
            findings.append(
                "%s:%d: the tick for %g %s (%r) — print one complete number "
                "per tick" % (name, line_of(source, offset), declared, reason,
                              body[:28])
            )
            continue
        if abs(shown - declared) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: a tick prints %r but declares %g — the label and the "
                "binding must state one number"
                % (name, line_of(source, offset), body[:28], declared)
            )
            continue
        position = number(attrs.get("x"))
        if position is None:
            findings.append(
                "%s:%d: the tick for %g has no readable position"
                % (name, line_of(source, offset), declared)
            )
            continue
        ticks.append((declared, position, offset))

    if len({value for value, _pos, _off in ticks}) < 2:
        findings.append(
            "%s: the value axis binds %d distinct tick value(s) — an axis "
            "needs at least two bound ticks (data-tick/data-value) or its "
            "printed scale is unverifiable against the drawn one"
            % (name, len({v for v, _p, _o in ticks}))
        )
        return
    slope, intercept = scale
    if slope is None:
        return  # already reported by check_scale
    for value, position, offset in ticks:
        expected = slope * value + intercept
        if abs(position - expected) > TICK_TOLERANCE:
            findings.append(
                "%s:%d: the tick for %g is drawn at %g but the scale the dots "
                "themselves describe puts that value at %.1f — the printed "
                "axis and the drawn positions disagree, so every reading off "
                "this axis is wrong"
                % (name, line_of(source, offset), value, position, expected)
            )


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    source = blank_comments(raw)
    findings: list = []
    dots = parse_dots(source, findings, path.name)

    distinct = len({d.value for d in dots})
    if len(dots) < 4 or distinct < 4:
        findings.append(
            "%s: presents as a beeswarm but declares %d verifiable dot(s) on "
            "%d distinct value(s) — each dot needs data-value, cx, cy and r, "
            "and the leave-one-out scale test needs four distinct values. "
            "Refusing to report OK on a file this checker could not read"
            % (path.name, len(dots), distinct)
        )
        return findings

    if len(dots) > MAX_DOTS:
        findings.append(
            "%s: %d dots against a budget of %d-%d — past the ceiling the "
            "packing outgrows the band and the swarm reads as texture; bin "
            "into a histogram instead" % (path.name, len(dots), MIN_DOTS,
                                          MAX_DOTS)
        )
    elif len(dots) < MIN_DOTS:
        findings.append(
            "%s: %d dots against a budget of %d-%d — below the floor there is "
            "no distribution to swarm, and a strip of labeled points or a "
            "table says it shorter" % (path.name, len(dots), MIN_DOTS,
                                       MAX_DOTS)
        )

    check_transforms(source, findings, path.name)
    scale = check_scale(dots, findings, source, path.name)
    check_overlap(dots, findings, source, path.name)
    check_radius(dots, findings, source, path.name)
    check_ink(dots, findings, source, path.name)
    check_focal(dots, findings, source, path.name)
    check_labels(dots, source, findings, path.name)
    check_ticks(scale, source, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a beeswarm."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_beeswarm(path, raw):
        return []
    return check_source(path, raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify beeswarm dot positions against the values they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a beeswarm",
    )
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    if args.all:
        targets = sorted(ASSET_DIR.glob("example-*.html"))
    else:
        targets = [Path(p) for p in args.paths]

    findings: list = []
    checked = 0
    skipped = 0
    for path in targets:
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
        if not looks_like_beeswarm(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d beeswarm finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK beeswarm: no beeswarm found to check%s" % tail)
        return 0
    print("OK beeswarm: %d file(s), every dot exactly at its value on one shared "
          "scale, no overprinted pair, one radius and one non-focal ink, at most "
          "one accent dot, and every bound label and tick agreeing with the mark "
          "it describes%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
