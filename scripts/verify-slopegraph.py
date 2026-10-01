#!/usr/bin/env python3
"""Verify that a slopegraph's drawn slopes match the values it prints.

A slopegraph makes exactly one claim: **both axes carry the same scale**, so the
angle of a line is a rate of change and two angles are comparable. Break that
claim and nothing errors - the figure renders, every label is present, and the
lie is in the geometry. `lint-skin.py` reads colors and fonts, `verify-geometry.py`
reads label masks against later-painted nodes, and neither compares a drawn
endpoint against the number sitting beside it.

Six invariants, each of which has shipped broken in a draft of this type:

1. SHARED SCALE - the left and right axes must map value to y through the same
   linear transform. Both halves are checked, slope *and* origin: a second axis
   that is rescaled makes every slope wrong by a factor, and one that is merely
   shifted makes every slope wrong by a constant. Checking the slope alone would
   pass the shifted case, which is the easier mistake to make.

2. NO JITTER - each declared value must sit where the shared scale puts it. The
   draft this checker was written against nudged two series apart by 3px because
   their labels collided at identical values; both then read as different
   numbers. Crowded endpoint labels are data, not a coordinate problem.

3. UNTRANSFORMED GEOMETRY - the coordinates read here are raw attributes, so any
   transform on verified geometry, on its labels, or on an ancestor moves the
   rendered mark away from the number this checker validated. A single
   `transform="translate(0 80)"` on one series line slid its endpoint 80px and
   every check still passed. A transform reaches the renderer by three carriers
   - the `transform` attribute, an inline `style="..."`, and a rule in a <style>
   block - and all three are refused, on the element and on any ancestor
   <g>/<svg>, following verify-beeswarm.py. Transforms are rejected rather than
   resolved: a partial implementation of the SVG transform stack is worse than
   an honest refusal, because it looks like coverage. CSS comments are stripped
   before any carrier is read, as the browser strips them: `/**/transform:` is
   a live declaration, not a quirk.

4. COMPLETE PRINTED VALUES - the whole visible numeric token must match the
   declared one. Matching only the first fragment read the label "512,000" as
   512 and agreed with metadata that said 512.

5. LABELS BOUND TO MEANING - state captions belong to a named axis, and each
   series name belongs to a series and an end. Unbound, the two captions can be
   swapped - reversing the reading of the entire figure - or two names exchanged
   between rows, with every geometric check still green.

6. FAIL CLOSED - a file that presents as a slopegraph but yields nothing
   parseable is a finding, never a pass. A checker that reports OK because it
   found nothing to compare is the bug, not the gate. `verify-treemap.py`
   returned early on `len(cells) < 3` and that is precisely how an undersized
   cell went unverified. Scope is therefore read twice - from the raw text,
   HTML comments removed, and through the parser - so a <line> whose broken
   quoting the parser cannot emit still claims the file and is reported.

Markup is read through the stdlib html.parser.HTMLParser, never a regex, so a
tag is recognized exactly when a browser would recognize it: a quoted `>`
inside an attribute value does not end the tag, a repeated attribute keeps its
FIRST value and the rest are not in the document at all, unquoted values and
upper-case names parse as their canonical form, and a comment's contents are
never live markup. The regex tag matcher this replaced stopped at the first
`>` it saw, so `<g data-note=">" transform="translate(0 -80)">` hid its
transform from the checker while Chromium applied it to every line inside -
the same fail-open shape verify-block-registry.py retired for the same reason.

The basis for geometry is the `data-from` / `data-to` pair each series line
declares, never the rendered text. Deriving the basis from text is what let a
treemap cell with no label drop silently out of the checked set; here a series
whose label is missing or restyled stays in the set and its missing label is
itself reported.

WHAT THIS DOES NOT CHECK, deliberately:

- **Direction.** An axis whose y grows with value is accepted. That is correct
  for a rank slopegraph, where rank 1 belongs at the top, and this checker has no
  way to tell an intended inversion from a mistaken one.
- **Absolute truth.** Every check here is internal consistency. If every label
  and every declared value is wrong by the same constant, the figure is
  self-consistent and passes; nothing in the file could reveal otherwise. The
  source line is where the domain is stated to a reader, and prose is not parsed.
- **Curvature below tolerance.** A value-to-y map that bends by less than
  RESIDUAL_TOLERANCE at every point is indistinguishable from a straight one.

Usage:
    python3 scripts/verify-slopegraph.py --all
    python3 scripts/verify-slopegraph.py skills/diagram-design/assets/example-slopegraph.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

# Every CSS property that can move or reshape a verified mark WITHOUT touching
# the attributes this checker reads. The enumeration IS the invariant - it is
# copied from verify-beeswarm.py, where it had already been wrong twice
# (`transform:` alone missed `style="transform: ..."`, and once that was fixed
# `style="translate: 80px 0"` walked past it because CSS Transforms Level 2
# splits the transform into four properties). Three families reach a mark:
#
#   transform / translate / rotate / scale   the four transform properties;
#       the individual three compose WITH `transform`, so each is its own door
#   x1 / y1 / x2 / y2 / x / y                the attributes this checker reads.
#       x and y are SVG geometry properties, and CSS wins over the presentation
#       attribute, so `style="y: 40px"` on a bound label moves it after its raw
#       y was validated. A <line>'s x1/y1/x2/y2 are not geometry properties in
#       any shipping browser, so a declaration naming them is dead today; it is
#       refused anyway because it costs nothing on honest markup and the
#       alternative is a checker that has to be re-hardened the day it stops
#       being dead
#   offset and its path/distance/position/anchor/rotate longhands
#       CSS motion path, which places the element somewhere else entirely
#
# Anchored to a declaration start, so `text-transform:` (the editorial skin
# uses it), `display:` and `--custom:` never match, and the `rotate` inside
# `transform: rotate(45deg)` is read once as the property and never as the
# function in its value. A vendor prefix is optional so `-webkit-transform:`
# is not a free pass.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|x1|y1|x2|y2|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
# A CSS comment is whitespace to the browser, so `/**/transform:` is a live
# declaration. CSS_MOVES_MARK_RE allows only whitespace between a declaration
# boundary and the property name, which let a comment sitting there hide the
# property from it while Chromium applied it. Non-greedy and DOTALL: a comment
# spans lines, and a stylesheet holds many. See css_moves_mark.
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Detection only - a raw-text signal read BEFORE the parser, because the parser
# is exactly what a broken quote defeats (see declares_series). Scoped to a
# <line> start tag: `data-series` on a <path> is the bump chart's vocabulary.
DECLARES_SERIES_RE = re.compile(r"<line\b[^>]*\bdata-series\s*=", re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# The COMPLETE numeric token an author may print: sign, comma-grouped thousands,
# decimals, leading-dot decimals, exponents. Matching only `-?\d+(\.\d+)?` read
# "1e3" as 1 and "512,000" as 512, so a mangled label agreed with its metadata.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")

# Coordinates ship rounded to one decimal, so a point can sit 0.05px from its
# true position honestly; an author rounding to whole pixels can sit 0.5px off.
# 1.0px clears both and still catches the smallest dishonest nudge worth making
# (the draft's was 3px). In data units at the shipped 0.844 px-per-ms scale that
# is 1.2ms of slack on values running 121-512 - about a quarter of one percent,
# below the precision the labels themselves claim.
RESIDUAL_TOLERANCE = 1.0   # px, per endpoint, against the shared scale
ORIGIN_TOLERANCE = 0.5     # px, between the two axes at mid-domain
SCALE_TOLERANCE = 1.0      # px, worst-case slope disagreement across the range
VALUE_TOLERANCE = 0.001    # printed label vs declared attribute
CAPTION_TOLERANCE = 0.5    # px, state caption x vs the axis it names
ROW_TOLERANCE = 0.5        # px, slack before a label counts as another row

GROUP_TAGS = ("g", "svg")                     # the only ancestors whose transform is inherited
BODY_TAGS = ("text", "title", "desc", "style")  # elements whose character data is read
MARK_TAGS = ("line",)                         # the element this contract binds


# === PARSING =================================================================


class Element:
    """One start tag this checker cares about, as the browser tokenized it."""

    __slots__ = ("tag", "attrs", "offset", "line", "body", "ancestor")

    def __init__(self, tag, attrs, offset, line, ancestor):
        self.tag = tag
        self.attrs = attrs          # first-wins dict, names lower-cased, values unescaped
        self.offset = offset        # offset of `<` in the source, for ordering
        self.line = line
        self.body = ""              # character data up to the matching end tag
        self.ancestor = ancestor    # how the nearest transformed <g>/<svg> moves it, or None


class Series:
    __slots__ = ("name", "frm", "to", "x1", "y1", "x2", "y2", "line")

    def __init__(self, name, frm, to, x1, y1, x2, y2, line):
        self.name = name
        self.frm, self.to = frm, to
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.line = line

    def value(self, end):
        return self.frm if end == "from" else self.to

    def endpoint_y(self, end):
        return self.y1 if end == "from" else self.y2

    def axis_x(self, end):
        return self.x1 if end == "from" else self.x2


def first_wins(attrs) -> dict:
    """Attributes as the browser keeps them: on a repeat, the FIRST wins.

    HTML parsing drops a duplicate attribute rather than overwriting the one
    already on the token, so a second `y2` on a line is not merely ignored -
    it is not in the document at all. A dict comprehension does the opposite,
    and that gap is a fail-open every caller inherits: a line carrying a
    dishonest first `y2` and an honest second renders the dishonest endpoint
    while a last-wins reader checks, and passes, bytes the browser threw away.
    A present-but-valueless attribute is an empty string, not an absent one.
    """
    seen = {}
    for name, value in attrs:
        seen.setdefault(name, "" if value is None else value)
    return seen


class _Scanner(HTMLParser):
    """Collect lines, texts, title/desc and style elements with ancestry.

    HTMLParser already lowercases tag and attribute names, tolerates unquoted
    values and whitespace around `=`, unescapes entities, keeps a quoted `>`
    inside the value it belongs to, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text - each
    of those is exactly a case a regex tag matcher mishandles. Ancestry is
    tracked for <g>/<svg> only, the elements whose transform a child inherits.
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.lines: list = []
        self.texts: list = []
        self.named: list = []      # <title> and <desc>
        self.styles: list = []
        self.error = None
        self._groups: list = []    # (tag, how) per open <g>/<svg>
        self._open: list = []      # (tag, Element) per open body element
        self._line_starts = [0]
        for index, char in enumerate(source):
            if char == "\n":
                self._line_starts.append(index + 1)
        try:
            self.feed(source)
            self.close()
        except Exception as exc:  # noqa: BLE001 - any parser failure fails closed
            self.error = "%s: %s" % (type(exc).__name__, exc)

    def _offset(self) -> int:
        line, column = self.getpos()
        return self._line_starts[line - 1] + column

    def _ancestor(self):
        for _tag, how in reversed(self._groups):
            if how is not None:
                return how
        return None

    def handle_starttag(self, tag, attrs):
        self._start(tag, first_wins(attrs), closes=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, first_wins(attrs), closes=True)

    def _start(self, tag, attrs, closes):
        if tag in GROUP_TAGS:
            if not closes:
                how = None
                if "transform" in attrs:
                    how = "an ancestor <g>/<svg> transform"
                elif transform_carrier(attrs) is not None:
                    how = "an ancestor <g>/<svg> style transform"
                self._groups.append((tag, how))
            return
        if tag not in MARK_TAGS and tag not in BODY_TAGS:
            return
        element = Element(tag, attrs, self._offset(), self.getpos()[0], self._ancestor())
        if tag == "line":
            self.lines.append(element)
            return
        if tag == "text":
            self.texts.append(element)
        elif tag == "style":
            self.styles.append(element)
        else:
            self.named.append(element)
        if not closes:
            self._open.append((tag, element))

    def handle_endtag(self, tag):
        stack = self._groups if tag in GROUP_TAGS else self._open if tag in BODY_TAGS else None
        if stack is None:
            return
        # Pop back to the matching open tag - an unclosed inner element ends
        # with its parent, as it does in the browser's tree.
        for index in range(len(stack) - 1, -1, -1):
            if stack[index][0] == tag:
                del stack[index:]
                return

    def handle_data(self, data):
        if self._open:
            # Innermost only: a <title> tooltip inside a <text> is not part of
            # the rendered label, and the browser does not draw it either.
            self._open[-1][1].body += data


def parse_document(source: str) -> _Scanner:
    return _Scanner(source)


def attrs_of(raw: str) -> dict:
    """First-wins attributes of one tag's raw attribute text, via the parser."""

    class _One(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.attrs = {}

        def handle_starttag(self, tag, attrs):
            self.attrs = first_wins(attrs)

        handle_startendtag = handle_starttag

    scanner = _One()
    scanner.feed("<x " + raw + ">")
    scanner.close()
    return scanner.attrs


def transform_carrier(attrs: dict):
    """How this element carries a transform, phrased for the finding, or None.

    A transform reaches the renderer by three carriers and the `transform`
    ATTRIBUTE is only the most visible one. Reading the attribute alone lets
    `style="transform: translateY(...)"` on a series line, a bound label or an
    ancestor group move the rendered mark after its raw coordinates were
    validated. The third carrier, a rule in a <style> block, is reported
    separately because nothing here can tell which marks such a rule selects.
    """
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = css_moves_mark(style)
        if found is not None:
            return "style=%r (the %s property)" % (style, found.group("prop").lower())
    return None


def css_moves_mark(css: str):
    """The first mark-moving declaration in CSS text, read past comments, or None.

    Every carrier goes through here - an inline style, an ancestor's inline
    style, a <style> block - because the browser drops `/* ... */` before it
    tokenizes, and CSS_MOVES_MARK_RE must see what the browser sees:
    `style="/**/transform: translateX(80px)"` moved a mark while the anchored
    regex walked past the comment. Each comment is blanked to whitespace of
    the SAME length, newlines kept, so the searched text is aligned with the
    original character for character: every offset in the returned match is
    an offset into `css` as written, and a <style> finding that counts
    newlines up to the property names the right line.
    """
    stripped = CSS_COMMENT_RE.sub(
        lambda found: re.sub(r"[^\n]", " ", found.group()), css)
    return CSS_MOVES_MARK_RE.search(stripped)


def declares_series(source: str) -> bool:
    """Does the raw text, HTML comments removed, put data-series on a <line>?

    Read BEFORE the parser, because the parser is exactly what a broken quote
    defeats: `<line data-series="Search` with no closing quote is character
    data to HTMLParser, no <line> is ever emitted, and a file whose only
    slopegraph signal was that tag would be skipped as out of scope - a
    fail-open. The raw signal claims the file and check_source then reports
    the tag the parser could not read. Comments are stripped first so a
    commented-out draft line does not claim an unrelated file.
    """
    return DECLARES_SERIES_RE.search(HTML_COMMENT_RE.sub("", source)) is not None


def plain(body: str) -> str:
    return body.strip()


def number(value):
    """A finite float from a complete numeric token, or None.

    `float("nan")` succeeds and then every `abs(x) > tolerance` comparison is
    False, so a NaN coordinate silently satisfied every check in the file. Any
    non-finite value is treated as unreadable instead.
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
    token. Trailing units are fine ("512ms"); a second number, or digits the
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
    """Robust (slope, intercept) for y = slope * value + intercept.

    Theil-Sen - the median of all pairwise slopes - rather than least squares, so
    that one dishonest point does not drag the line it is being measured against.
    Returns (None, None) when every value is the same, which is legitimate on an
    indexed axis and handled by the caller.
    """
    slopes = [
        (yb - ya) / (vb - va)
        for index, (va, ya) in enumerate(points)
        for vb, yb in points[index + 1:]
        if vb != va
    ]
    if not slopes:
        return None, None
    slope = median(slopes)
    return slope, median([y - slope * v for v, y in points])


def outliers(points: list, tolerance: float) -> list:
    """Points that disagree with the line their PEERS describe.

    Leave-one-out, because measuring a point against a fit that includes it lets
    it hide inside its own influence. Theil-Sen's breakdown point is around 29%,
    which is zero outliers on a three-point axis: an indexed three-series figure
    with one endpoint 3px wrong produced a whole-set fit that called all three
    points clean, because the contaminated slope passed within 1px of every one
    of them. Excluding the point under test removes that escape.

    Returns [(index, drawn, expected)]. Needs four points, so each fit is made
    from at least three.
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


def named_text(doc: _Scanner) -> str:
    """The accessible name and description, where a figure says what it is."""
    return " ".join(plain(element.body) for element in doc.named).casefold()


def looks_like_slopegraph(path: Path, source: str) -> bool:
    """Does this file present itself as a slopegraph?

    Deliberately generous. Anything that claims the type in its name, its
    accessible description, or its markup is held to the contract even if it
    declares no parseable series - that combination is the fail-closed case, not
    a pass. The whole document is searched: a 4000-character window missed a file
    whose only declaration sat behind a long stylesheet.

    Detection is scoped to the ELEMENT this contract binds. `data-series` alone
    is shared vocabulary across the chart variants - a bump chart binds it to
    <path>, and holding that file to the slopegraph contract rejects a figure
    for lacking <line> elements it never claimed to have. Two readings, each
    covering the other's blind spot: the raw text (comments stripped) claims a
    <line> whose broken quoting keeps the parser from ever emitting it, and
    the parser claims a <line> that declares data-series behind a quoted `>`,
    which the raw scan cannot see past but the browser still draws.
    """
    if path.name.startswith("example-slopegraph"):
        return True
    if declares_series(source):
        return True
    doc = parse_document(source)
    if any("data-series" in element.attrs for element in doc.lines):
        return True
    described = named_text(doc)
    return "slopegraph" in described or "slope graph" in described


def parse_series(doc: _Scanner, findings: list, name: str) -> list:
    """Series lines, with anything unparseable reported rather than dropped."""
    series = []
    for element in doc.lines:
        attrs = element.attrs
        label = attrs.get("data-series")
        if label is None:
            # A <line> with no data-series is scenery - an axis rule, a legend
            # swatch - and skipping it is correct. The parser reads every tag
            # the browser reads, so there is no "declared but unparseable"
            # case left to report here.
            continue
        line = element.line
        missing = [key for key in ("data-from", "data-to", "x1", "y1", "x2", "y2")
                   if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: series %r declares data-series but is missing %s — a series "
                "line must state both values and both endpoints or it cannot be verified"
                % (name, line, label, ", ".join(missing))
            )
            continue
        parsed = [number(attrs[key])
                  for key in ("data-from", "data-to", "x1", "y1", "x2", "y2")]
        if any(value is None for value in parsed):
            findings.append(
                "%s:%d: series %r has a value or coordinate that is not a finite "
                "number — cannot verify its slope"
                % (name, line, label)
            )
            continue
        series.append(Series(label, parsed[0], parsed[1], parsed[2], parsed[3],
                             parsed[4], parsed[5], line))
    return series


# === CHECKS ==================================================================


def check_transforms(doc: _Scanner, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label.

    All three carriers are held to that rule - the `transform` attribute, an
    inline `style="transform: ..."`, and a rule in a <style> block - on the
    element and on every <g>/<svg> above it, because a gate that closes one of
    three doorways guards nothing.
    """

    def report(element, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw x/y attributes, so "
            "a transform moves the rendered mark away from the number it was "
            "checked against. Bake the offset into the coordinates instead"
            % (name, element.line, what, how)
        )

    def check_element(element, what):
        how = transform_carrier(element.attrs)
        if how is None:
            how = element.ancestor
        if how is not None:
            report(element, what, how)

    for element in doc.lines:
        if "data-series" in element.attrs:
            check_element(element, "series %r" % element.attrs["data-series"])

    for element in doc.texts:
        if "data-series" in element.attrs or "data-axis" in element.attrs:
            check_element(element, "a bound label (%s)" % plain(element.body)[:20])

    for element in doc.styles:
        found = css_moves_mark(element.body)
        if found:
            findings.append(
                "%s:%d: a CSS `%s` declaration — this checker cannot tell "
                "which marks it applies to, and a transform on verified geometry "
                "invalidates every coordinate here. Remove it, or bake the offset "
                "into the coordinates"
                % (name, element.line + element.body.count("\n", 0, found.start("prop")),
                   found.group("prop").lower())
            )


def check_axes(series: list, findings: list, name: str) -> None:
    """Every series must span the same two axis positions."""
    for attr, end in (("x1", "from"), ("x2", "to")):
        positions = sorted({round(s.axis_x(end), 3) for s in series})
        if len(positions) > 1:
            offenders = ", ".join("%s at %g" % (s.name, s.axis_x(end)) for s in series)
            findings.append(
                "%s:%d: series do not share one %s — found %s (%s). Every line must "
                "run between the same two axes or the slopes are not comparable"
                % (name, series[0].line, attr,
                   "/".join("%g" % p for p in positions), offenders)
            )


def check_scale(series: list, findings: list, name: str) -> None:
    """The two axes must share one linear value-to-y map, and no point may drift."""
    left = [(s.frm, s.y1) for s in series]
    right = [(s.to, s.y2) for s in series]
    combined = left + right
    values = [v for v, _ in combined]
    span = max(values) - min(values)
    mid = (max(values) + min(values)) / 2.0
    line = series[0].line

    left_fit = fit(left)
    right_fit = fit(right)

    if left_fit[0] is not None and right_fit[0] is not None:
        slope_drift = abs(left_fit[0] - right_fit[0]) * span
        if slope_drift > SCALE_TOLERANCE:
            findings.append(
                "%s:%d: the two axes are not on the same scale — %.4g px/unit on the "
                "left against %.4g on the right, which puts the same value up to "
                "%.1f px apart across the plotted range. Both axes must use one scale "
                "or every slope is a lie"
                % (name, line, left_fit[0], right_fit[0], slope_drift)
            )
            return
        # Compared at mid-domain, not at value zero. Raw intercepts are the
        # predicted y AT zero, so on values in the billions two axes sharing one
        # transform disagreed by hundreds of pixels there through nothing but
        # float cancellation, and an honest figure was reported as shifted.
        origin_drift = abs((left_fit[0] * mid + left_fit[1])
                           - (right_fit[0] * mid + right_fit[1]))
        if origin_drift > ORIGIN_TOLERANCE:
            findings.append(
                "%s:%d: the two axes share a scale but not an origin — offset by "
                "%.1f px at mid-domain. A shifted axis tilts every slope by the same "
                "amount, so the comparison between series survives and every rate is "
                "wrong" % (name, line, origin_drift)
            )
            return
        # Both returns above are deliberate. Per-point residuals are measured
        # against "the" shared scale, so once the two axes disagree about what
        # that scale is there is nothing meaningful to measure against - every
        # point reports an error and the one finding that names the cause is
        # buried in its own consequences.
    elif left_fit[0] is None and right_fit[0] is None:
        findings.append(
            "%s:%d: neither axis has two distinct values, so the scale cannot be "
            "derived and no slope here is verifiable" % (name, line)
        )
        return

    ends = ["from"] * len(left) + ["to"] * len(right)
    for index, drawn, expected in outliers(combined, RESIDUAL_TOLERANCE):
        s = series[index % len(series)]
        value = combined[index][0]
        findings.append(
            "%s:%d: series %r draws its %s endpoint (%g) at y=%g where the shared "
            "scale its peers describe puts %g at y=%.1f — off by %.1f px. Do not move "
            "a point to make room for its label"
            % (name, s.line, s.name, ends[index], value, drawn,
               value, expected, abs(drawn - expected))
        )


def misplaced_row(series: list, owner: str, end: str, y: float):
    """A series whose endpoint is strictly nearer this label than its own owner's.

    Nearer, not nearest. Two series holding the same value at an end sit at the
    same y by necessity - that is the honest rendering of equal values, and it is
    also what an indexed slopegraph does at every from-endpoint - so a tie must
    pass. Only a label that has drifted onto a row genuinely closer to someone
    else has been mislabelled.
    """
    own = min(abs(y - s.endpoint_y(end)) for s in series if s.name == owner)
    for other in series:
        if other.name != owner and abs(y - other.endpoint_y(end)) < own - ROW_TOLERANCE:
            return other.name
    return None


def collect_bound_labels(doc: _Scanner, findings: list, name: str) -> dict:
    """Bound labels keyed by (series, end, role), with duplicates reported.

    Each value is (visible text, y, source offset, line); the offset keeps the
    caller's report order the document's order.
    """
    found = {}
    for element in doc.texts:
        attrs = element.attrs
        label, end = attrs.get("data-series"), attrs.get("data-end")
        if label is None or end is None:
            continue
        role = attrs.get("data-role", "value")
        key = (label, end, role)
        if key in found:
            # A second label for one endpoint used to overwrite the first, so a
            # figure could print two contradictory numbers for one point and be
            # judged on whichever came last.
            findings.append(
                "%s:%d: a second %s %s label for series %r — one endpoint, one "
                "label, or the figure states two things about one point"
                % (name, element.line, end, role, label)
            )
            continue
        found[key] = (plain(element.body), number(attrs.get("y")),
                      element.offset, element.line)
    return found


def check_labels(series: list, doc: _Scanner, findings: list, name: str) -> None:
    """Printed values and names must exist, be unique, match, and sit on their row."""
    bound = collect_bound_labels(doc, findings, name)
    declared = {s.name for s in series}

    for (label, end, role), (body, y, _offset, line) in sorted(
        bound.items(), key=lambda item: item[1][2]
    ):
        if label not in declared:
            findings.append(
                "%s:%d: a %s label names series %r, which no line declares — a label "
                "with no mark is not verifiable and reads as data"
                % (name, line, role, label)
            )
            continue
        if end not in ("from", "to"):
            findings.append(
                "%s:%d: label for series %r has data-end=%r, which is neither "
                "'from' nor 'to'" % (name, line, label, end)
            )
            continue
        # Row placement. A label bound to one series but drawn beside another's
        # endpoint mislabels the row, and no value check would notice: two names
        # exchanged between rows leaves every number correct in isolation.
        if y is not None:
            sits_by = misplaced_row(series, label, end, y)
            if sits_by is not None:
                findings.append(
                    "%s:%d: the %s %s label for series %r is drawn at y=%g, nearer "
                    "%r's endpoint than its own — a label on the wrong row renames "
                    "the line"
                    % (name, line, end, role, label, y, sits_by)
                )

    for s in series:
        for end in ("from", "to"):
            value_entry = bound.get((s.name, end, "value"))
            if value_entry is None:
                findings.append(
                    "%s:%d: series %r prints no %s endpoint value — a slopegraph must "
                    "label both ends, or the reader has a slope and no magnitude"
                    % (name, s.line, s.name, end)
                )
            else:
                body, _y, _offset, line = value_entry
                shown, reason = printed_number(body)
                if shown is None:
                    findings.append(
                        "%s:%d: the %s endpoint label for %r %s (%r) — label both "
                        "endpoints with one complete value each"
                        % (name, line, end, s.name, reason, body[:28])
                    )
                elif abs(shown - s.value(end)) > VALUE_TOLERANCE:
                    findings.append(
                        "%s:%d: series %r prints %r at its %s endpoint but declares "
                        "%g — the label and the geometry must state one number"
                        % (name, line, s.name, body, end, s.value(end))
                    )
            name_entry = bound.get((s.name, end, "name"))
            if name_entry is None:
                findings.append(
                    "%s:%d: series %r has no %s name label (data-role=\"name\") — a "
                    "slopegraph names every series at both ends, and an unbound name "
                    "can be swapped with another row undetected"
                    % (name, s.line, s.name, end)
                )
                continue
            body, _y, _offset, line = name_entry
            if body != s.name:
                findings.append(
                    "%s:%d: a name label bound to series %r reads %r — the visible "
                    "name and the binding must agree"
                    % (name, line, s.name, body[:28])
                )


def check_captions(series: list, doc: _Scanner, findings: list, name: str) -> None:
    """Each state caption must name the axis it is drawn against."""
    seen = {}
    for element in doc.texts:
        attrs = element.attrs
        end = attrs.get("data-axis")
        if end is None:
            continue
        if end not in ("from", "to"):
            findings.append(
                "%s:%d: a state caption has data-axis=%r, which is neither 'from' "
                "nor 'to'" % (name, element.line, end)
            )
            continue
        if end in seen:
            findings.append(
                "%s:%d: a second %r state caption — one axis, one caption"
                % (name, element.line, end)
            )
            continue
        seen[end] = (number(attrs.get("x")), plain(element.body),
                     attrs.get("data-state"), element.line)

    for end in ("from", "to"):
        if end not in seen:
            findings.append(
                "%s: no %r state caption (data-axis=%r) — an unbound caption pair can "
                "be swapped, which reverses the reading of the whole figure"
                % (name, end, end)
            )
            continue
        x, body, declared, line = seen[end]
        expected = series[0].axis_x(end)
        if x is None or abs(x - expected) > CAPTION_TOLERANCE:
            findings.append(
                "%s:%d: the %r state caption (%r) is drawn at x=%s but its axis is at "
                "x=%g — the captions are swapped or misplaced, which reverses the "
                "direction every slope is read in"
                % (name, line, end, body[:20],
                   "%g" % x if x is not None else "?", expected)
            )
        # Position alone is not enough: swapping just the two visible strings
        # leaves both captions where they were and reverses the figure anyway.
        # data-state binds the text, exactly as data-series binds a series name.
        if declared is None:
            findings.append(
                "%s:%d: the %r state caption (%r) has no data-state — its visible "
                "text is unbound, so it can be exchanged with the other caption and "
                "nothing here would notice"
                % (name, line, end, body[:20])
            )
        elif body != declared:
            findings.append(
                "%s:%d: the %r state caption reads %r but declares data-state=%r — the "
                "visible caption and its binding must agree"
                % (name, line, end, body[:20], declared)
            )

    if len(seen) == 2:
        first, second = seen["from"], seen["to"]
        if first[1] and first[1] == second[1]:
            findings.append(
                "%s:%d: both state captions read %r — two states the reader cannot "
                "tell apart is not a comparison"
                % (name, second[3], first[1])
            )


# === DRIVER ==================================================================


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    findings: list = []
    doc = parse_document(raw)
    if doc.error is not None:
        findings.append(
            "%s: presents as a slopegraph but could not be parsed as HTML (%s) — "
            "refusing to report OK on a file this checker could not read"
            % (path.name, doc.error)
        )
        return findings
    # The raw text claimed a bound <line> the parser never emitted: an unclosed
    # quote turned the tag into character data. Nothing downstream can verify
    # a mark that does not exist, so say which tag was lost rather than count
    # zero series and leave the author hunting for a line that is plainly there.
    if declares_series(raw) and not any("data-series" in e.attrs for e in doc.lines):
        findings.append(
            "%s: declares data-series on a <line> but no complete <line> could be "
            "parsed — an unclosed attribute quote swallows the tag; fix the markup. "
            "Refusing to report OK on a file this checker could not read" % path.name
        )
        return findings
    series = parse_series(doc, findings, path.name)

    if len(series) < 2:
        findings.append(
            "%s: presents as a slopegraph but declares %d verifiable series — every "
            "line needs data-series with data-from and data-to. Refusing to report "
            "OK on a file this checker could not read" % (path.name, len(series))
        )
        return findings

    check_transforms(doc, findings, path.name)
    check_axes(series, findings, path.name)
    check_scale(series, findings, path.name)
    check_labels(series, doc, findings, path.name)
    check_captions(series, doc, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a slopegraph."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_slopegraph(path, raw):
        return []
    return check_source(path, raw)


def targets(args: argparse.Namespace) -> list:
    if args.all:
        return sorted(ASSET_DIR.glob("example-*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify slopegraph slopes against the values they are labelled with."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a slopegraph",
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
        # Read once, then decide. Scope is reported separately from verification
        # in both modes: printing "1 file(s) verified" for a bar chart that was
        # skipped is a claim the run never made good on.
        if not looks_like_slopegraph(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d slopegraph finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK slopegraph: no slopegraph found to check%s" % tail)
        return 0
    print("OK slopegraph: %d file(s), one shared scale on both axes, no transforms on "
          "verified geometry, and every printed value, name and caption bound to what "
          "it describes%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
