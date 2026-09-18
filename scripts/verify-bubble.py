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

Markup is read through the stdlib html.parser.HTMLParser, never a regex, so a
tag is recognized exactly when a browser would recognize it: a quoted `>`
inside an attribute value does not end the tag, a repeated attribute keeps its
FIRST value and the rest are not in the document at all, unquoted values and
upper-case names parse as their canonical form, and a comment's contents are
never live markup. The regex tag matcher this replaced stopped at the first
`>` it saw, so `<g data-note=">" transform="translate(0 -80)">` hid its
transform from the checker while Chromium applied it to every bubble inside -
the same fail-open shape verify-block-registry.py retired for the same reason.

No transform may move verified geometry or a bound label, and a transform
reaches the renderer by three carriers: the `transform` attribute, an inline
`style="..."`, and a rule in a <style> block. All three are refused, on the
element and on any ancestor <g>/<svg>, following verify-beeswarm.py; the
property set in CSS_MOVES_MARK_RE is the invariant, covering what moves or
resizes a circle (`cx`/`cy`/`r`) and what moves a label or tick (`x`/`y`).
CSS comments are stripped before any carrier is read, as the browser strips
them: `/**/transform:` is a live declaration, not a quirk.

Scope is read from the raw text with HTML comments removed, BEFORE the parser,
so a <circle> whose broken quoting keeps the parser from emitting it still
claims the file and is reported rather than skipped - the parser is exactly
what an unclosed quote defeats.

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
#   cx / cy / r / x / y                      SVG geometry properties. CSS wins
#       over the presentation attribute, so `style="r: 40px"` on a bubble
#       replaces the very radius that was verified, and x/y do the same to a
#       bound label or tick - a more direct lie than any transform
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
    r"|cx|cy|r|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
# The COMPLETE numeric token an author may print: sign, comma-grouped
# thousands, decimals, leading-dot decimals, exponents. Matching only the
# first fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")
# A CSS comment is whitespace to the browser, so `/**/transform:` is a live
# declaration. CSS_MOVES_MARK_RE allows only whitespace between a declaration
# boundary and the property name, which let a comment sitting there hide the
# property from it while Chromium applied it. Non-greedy and DOTALL: a comment
# spans lines, and a stylesheet holds many. See css_moves_mark.
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Detection only - deliberately a text search over the raw bytes, HTML comments
# removed, so a file that so much as mentions the binding in live markup is
# held to the contract even when the parser cannot read the tag that binds it.
# See declares_bubble.
DECLARES_BUBBLE_RE = re.compile(r"\bdata-size\s*=", re.IGNORECASE)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

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

GROUP_TAGS = ("g", "svg")                     # the only ancestors whose transform is inherited
BODY_TAGS = ("text", "title", "desc", "style")  # elements whose character data is read
MARK_TAGS = ("circle",)                       # the element this contract binds


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


class Bubble:
    __slots__ = ("name", "x", "y", "size", "cx", "cy", "r", "accent", "line")

    def __init__(self, name, x, y, size, cx, cy, r, accent, line):
        self.name = name
        self.x, self.y, self.size = x, y, size
        self.cx, self.cy, self.r = cx, cy, r
        self.accent = accent
        self.line = line


def first_wins(attrs) -> dict:
    """Attributes as the browser keeps them: on a repeat, the FIRST wins.

    HTML parsing drops a duplicate attribute rather than overwriting the one
    already on the token, so a second `r` on a circle is not merely ignored -
    it is not in the document at all. A dict comprehension does the opposite,
    and that gap is a fail-open every caller inherits: a circle carrying a
    dishonest first `r` and an honest second renders the dishonest radius
    while a last-wins reader checks, and passes, bytes the browser threw away.
    A present-but-valueless attribute is an empty string, not an absent one.
    """
    seen = {}
    for name, value in attrs:
        seen.setdefault(name, "" if value is None else value)
    return seen


class _Scanner(HTMLParser):
    """Collect circles, texts, title/desc and style elements with ancestry.

    HTMLParser already lowercases tag and attribute names, tolerates unquoted
    values and whitespace around `=`, unescapes entities, keeps a quoted `>`
    inside the value it belongs to, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text - each
    of those is exactly a case a regex tag matcher mishandles. Ancestry is
    tracked for <g>/<svg> only, the elements whose transform a child inherits.
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.circles: list = []
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
        if tag == "circle":
            self.circles.append(element)
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
    `style="transform: translateY(...)"` on a bubble, a bound label, a tick or
    an ancestor group move the rendered mark after its raw coordinates were
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
    `style="/**/transform: translateX(80px)"` moved a bubble while the
    anchored regex walked past the comment. Each comment is blanked to
    whitespace of the SAME length, newlines kept, so the searched text is
    aligned with the original character for character: every offset in the
    returned match is an offset into `css` as written, and a <style> finding
    that counts newlines up to the property names the right line.
    """
    stripped = CSS_COMMENT_RE.sub(
        lambda found: re.sub(r"[^\n]", " ", found.group()), css)
    return CSS_MOVES_MARK_RE.search(stripped)


def declares_bubble(source: str) -> bool:
    """Does the raw text, HTML comments removed, declare data-size anywhere?

    Read BEFORE the parser, because the parser is exactly what a broken quote
    defeats: `<circle data-size="9` with no closing quote is character data
    to HTMLParser, no <circle> is ever emitted, and a file whose only bubble
    signal was that tag would otherwise be skipped as out of scope - a
    fail-open. The raw signal claims the file and check_source then reports
    the tag the parser could not read. Comments are stripped first so a
    commented-out draft bubble does not claim an unrelated file.
    """
    return DECLARES_BUBBLE_RE.search(HTML_COMMENT_RE.sub("", source)) is not None


def plain(body: str) -> str:
    return body.strip()


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


def named_text(doc: _Scanner) -> str:
    """The accessible name and description, where a figure says what it is."""
    return " ".join(plain(element.body) for element in doc.named).casefold()


def looks_like_bubble(path: Path, source: str) -> bool:
    """Does this file present itself as a bubble chart?

    Deliberately generous - anything that claims the type in its name, its
    accessible description, or its markup is held to the contract, and a file
    that claims it while declaring nothing parseable is the fail-closed case,
    not a pass. Scoped to bubble-specific signals only: `data-size` rather
    than `data-series`, so this checker and `verify-slopegraph.py` never claim
    one another's files. A declaration inside an HTML comment is not live
    markup and claims nothing.
    """
    if path.name.startswith("example-bubble"):
        return True
    if declares_bubble(source):
        return True
    described = named_text(parse_document(source))
    return "bubble chart" in described or "bubble plot" in described


def parse_bubbles(doc: _Scanner, findings: list, name: str) -> list:
    """Bubble circles, with anything unparseable reported rather than dropped."""
    bubbles = []
    for element in doc.circles:
        attrs = element.attrs
        line = element.line
        if "data-size" not in attrs:
            # A <circle> with no data-size is scenery - a paper underlay, a
            # legend swatch, a dot-grid cell - and skipping it is correct. The
            # parser reads every tag the browser reads, so there is no
            # "declared but unparseable" case left to report here.
            continue
        label = attrs.get("data-name")
        if label is None:
            findings.append(
                "%s:%d: a bubble declares data-size but no data-name — an unnamed "
                "bubble cannot be labelled or cross-checked"
                % (name, line)
            )
            continue
        missing = [key for key in ("data-x", "data-y", "cx", "cy", "r")
                   if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: bubble %r is missing %s — a bubble must declare all three "
                "values and all three drawn quantities or it cannot be verified"
                % (name, line, label, ", ".join(missing))
            )
            continue
        parsed = [number(attrs[key])
                  for key in ("data-x", "data-y", "data-size", "cx", "cy", "r")]
        if any(value is None for value in parsed):
            findings.append(
                "%s:%d: bubble %r has a value or coordinate that is not a finite "
                "number — cannot verify its position or area"
                % (name, line, label)
            )
            continue
        if parsed[2] <= 0:
            # Area cannot encode a non-positive value; the honest treatment of
            # a zero or missing measurement is to omit the bubble and count the
            # omission in the source line, exactly as the reference says.
            findings.append(
                "%s:%d: bubble %r declares data-size=%g — area cannot encode a "
                "non-positive value. Omit the item and note the omission in the "
                "source line" % (name, line, label, parsed[2])
            )
            continue
        if parsed[5] <= 0:
            findings.append(
                "%s:%d: bubble %r has r=%g — a bubble with no area states no value"
                % (name, line, label, parsed[5])
            )
            continue
        accent = bool(ACCENT_RE.search(attrs.get("stroke", "")))
        bubbles.append(Bubble(label, parsed[0], parsed[1], parsed[2], parsed[3],
                              parsed[4], parsed[5], accent, line))
    return bubbles


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
            "%s:%d: %s carries %s — this checker validates raw cx/cy/r and x/y "
            "attributes, so a transform moves the rendered mark away from the "
            "number it was checked against. Bake the offset into the coordinates "
            "instead" % (name, element.line, what, how)
        )

    def check_element(element, what):
        how = transform_carrier(element.attrs)
        if how is None:
            how = element.ancestor
        if how is not None:
            report(element, what, how)

    for element in doc.circles:
        if "data-size" in element.attrs:
            check_element(element, "bubble %r" % element.attrs.get("data-name", "?"))

    for element in doc.texts:
        if "data-name" in element.attrs or "data-tick" in element.attrs:
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


def check_axis(bubbles: list, axis: str, findings: list, name: str):
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
    line = bubbles[0].line

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
                % (name, b.line, b.name, axis, value)
            )

    for index, drawn, expected in outliers(points, RESIDUAL_TOLERANCE):
        b = bubbles[index]
        findings.append(
            "%s:%d: bubble %r declares %s=%g but draws %s=%g where the shared %s "
            "scale its peers describe puts it at %.1f — off by %.1f px. Crowded "
            "bubbles are data; never nudge one aside"
            % (name, b.line, b.name, axis,
               points[index][0], drawn_attr, drawn, axis, expected,
               abs(drawn - expected))
        )
    return slope, intercept


def check_area(bubbles: list, findings: list, name: str) -> None:
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
                % (name, b.line, b.name, b.size, b.r, expected)
            )


def check_focal(bubbles: list, findings: list, name: str) -> None:
    """At most one bubble wears the accent."""
    accented = [b for b in bubbles if b.accent]
    for extra in accented[1:]:
        findings.append(
            "%s:%d: bubble %r also carries the accent stroke — one accent bubble "
            "max (%r already has it). A second focal mark is a second editorial "
            "claim, and the ink ramp exists so everything else stays ranked "
            "without spending the accent"
            % (name, extra.line, extra.name, accented[0].name)
        )


def check_paint_order(bubbles: list, findings: list, name: str) -> None:
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
                    % (name, a.line, a.name, a.r, b.name, b.r)
                )


def check_labels(bubbles: list, doc: _Scanner, findings: list, name: str) -> None:
    """Bound labels must name a real bubble, match it, and sit on it."""
    centres = {b.name: (b.cx, b.cy) for b in bubbles}
    seen = set()
    for element in doc.texts:
        attrs = element.attrs
        label = attrs.get("data-name")
        if label is None:
            continue
        line = element.line
        body = plain(element.body)
        if label not in centres:
            findings.append(
                "%s:%d: a label names bubble %r, which no circle declares — a "
                "label with no mark is not verifiable and reads as data"
                % (name, line, label)
            )
            continue
        if label in seen:
            findings.append(
                "%s:%d: a second label for bubble %r — one bubble, one label, or "
                "the figure states two things about one mark"
                % (name, line, label)
            )
            continue
        seen.add(label)
        # Case-insensitive: labels ship small-caps ("PAYMENTS" for a bubble
        # named "Payments"), and casing is presentation, not identity.
        if body.casefold() != label.casefold():
            findings.append(
                "%s:%d: a label bound to bubble %r reads %r — the visible text "
                "and the binding must agree"
                % (name, line, label, body[:28])
            )
            continue
        x, y = number(attrs.get("x")), number(attrs.get("y"))
        if x is None or y is None:
            findings.append(
                "%s:%d: the label for bubble %r has no readable x/y, so its "
                "placement cannot be checked"
                % (name, line, label)
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
                    % (name, line, label, x, y, nearest)
                )


def check_ticks(x_fit, y_fit, doc: _Scanner, findings: list, name: str) -> None:
    """Bound axis ticks must print their value and sit on the bubbles' scale."""
    ticks = {"x": [], "y": []}
    for element in doc.texts:
        attrs = element.attrs
        axis = attrs.get("data-tick")
        if axis is None:
            continue
        line = element.line
        if axis not in ("x", "y"):
            findings.append(
                "%s:%d: a tick label has data-tick=%r, which is neither 'x' nor "
                "'y'" % (name, line, axis)
            )
            continue
        declared = number(attrs.get("data-value"))
        if declared is None:
            findings.append(
                "%s:%d: a %s tick has no readable data-value — an unbound axis "
                "number is the cheapest way to relabel a whole chart"
                % (name, line, axis)
            )
            continue
        body = plain(element.body)
        shown, reason = printed_number(body)
        if shown is None:
            findings.append(
                "%s:%d: the %s tick for %g %s (%r) — print one complete number "
                "per tick" % (name, line, axis, declared, reason, body[:28])
            )
            continue
        if abs(shown - declared) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: a %s tick prints %r but declares %g — the label and the "
                "binding must state one number"
                % (name, line, axis, body[:28], declared)
            )
            continue
        position = number(attrs.get("x" if axis == "x" else "y"))
        if position is None:
            findings.append(
                "%s:%d: the %s tick for %g has no readable position"
                % (name, line, axis, declared)
            )
            continue
        ticks[axis].append((declared, position, line))

    for axis, fit_pair in (("x", x_fit), ("y", y_fit)):
        entries = ticks[axis]
        if len({value for value, _pos, _line in entries}) < 2:
            findings.append(
                "%s: the %s axis binds %d distinct tick value(s) — an axis needs "
                "at least two bound ticks (data-tick/data-value) or its printed "
                "scale is unverifiable against the drawn one"
                % (name, axis, len({v for v, _p, _l in entries}))
            )
            continue
        slope, intercept = fit_pair
        if slope is None:
            continue  # already reported by check_axis
        for value, position, line in entries:
            expected = slope * value + intercept
            if abs(position - expected) > TICK_TOLERANCE:
                findings.append(
                    "%s:%d: the %s tick for %g is drawn at %g but the scale the "
                    "bubbles themselves describe puts that value at %.1f — the "
                    "printed axis and the drawn positions disagree, so every "
                    "reading off this axis is wrong"
                    % (name, line, axis, value, position, expected)
                )


# === DRIVER ==================================================================


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    findings: list = []
    doc = parse_document(raw)
    if doc.error is not None:
        findings.append(
            "%s: presents as a bubble chart but could not be parsed as HTML (%s) — "
            "refusing to report OK on a file this checker could not read"
            % (path.name, doc.error)
        )
        return findings
    # The raw text claimed a bound <circle> the parser never emitted: an
    # unclosed quote turned the tag into character data. Nothing downstream
    # can verify a mark that does not exist, so say which tag was lost rather
    # than count zero bubbles and leave the author hunting for a circle that
    # is plainly there.
    if declares_bubble(raw) and not any("data-size" in e.attrs for e in doc.circles):
        findings.append(
            "%s: declares data-size but no complete <circle> could be parsed — an "
            "unclosed attribute quote swallows the tag; fix the markup. Refusing "
            "to report OK on a file this checker could not read" % path.name
        )
        return findings
    bubbles = parse_bubbles(doc, findings, path.name)

    if len(bubbles) < 4:
        findings.append(
            "%s: presents as a bubble chart but declares %d verifiable bubble(s) "
            "— each needs data-name, data-x, data-y, data-size, cx, cy and r, "
            "and the leave-one-out scale test needs four. Refusing to report OK "
            "on a file this checker could not read" % (path.name, len(bubbles))
        )
        return findings

    check_transforms(doc, findings, path.name)
    x_fit = check_axis(bubbles, "x", findings, path.name)
    y_fit = check_axis(bubbles, "y", findings, path.name)
    check_area(bubbles, findings, path.name)
    check_focal(bubbles, findings, path.name)
    check_paint_order(bubbles, findings, path.name)
    check_labels(bubbles, doc, findings, path.name)
    check_ticks(x_fit, y_fit, doc, findings, path.name)
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
