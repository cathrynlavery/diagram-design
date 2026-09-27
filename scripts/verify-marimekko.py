#!/usr/bin/env python3
"""Verify that a marimekko's drawn columns and segments match the amounts they declare.

A marimekko (mosaic) chart is the treemap's area encoding laid out on a grid:
**column width is the category's share of the whole, segment height is the
series' share within its category, so area is the joint share.** Every one of
those can be broken without anything erroring - a column widened to make a
label fit, a segment nudged taller for headroom, a series drawn in a different
order in one column - and the figure renders, the legend is present, and the
lie is in the geometry. `lint-skin.py` reads colors and fonts,
`verify-geometry.py` reads label masks against later-painted nodes, and
`verify-treemap.py` reads only files named for the parent type. None of them
compares a drawn rectangle against the amount sitting in its markup.

Nine invariants, in the spirit of ADR 0005 and the treemap checker:

1. COLUMNS SHARE ONE PLOT - every column spans the same top and bottom, so a
   segment's height is always a share of its own column. Columns run left to
   right with one constant gutter between them and never overlap.

2. WIDTH IS CATEGORY SHARE - each column's width over the sum of column widths
   must match its declared total over the grand total, as RELATIVE error.
   Absolute error passes exactly the narrow column most likely to be wrong.

3. SEGMENTS TILE THE COLUMN - within a column, segments sit flush from the
   column top to its bottom: no gaps, no overlaps, every one the full column
   width. A dropped segment or a padded one both break the tiling.

4. HEIGHT IS WITHIN-COLUMN SHARE - each segment's height over its column's
   height must match its amount over the column total, relative error again.

5. AREA IS JOINT SHARE - each segment's area over the total drawn area must
   match its amount over the grand total. With 2-4 honest this is implied;
   it is checked directly because area is the reading the type exists for.

6. ONE SERIES ORDER - the top-to-bottom order of series never contradicts
   itself across columns. A series that is second in one column and first in
   the next cannot be read across, and the row comparison is the point.

7. ONE ACCENT - at most one segment wears the accent stroke.

8. LABELS BOUND TO MEANING - an in-segment label is anchored inside the
   segment it binds and stays inside it; every number it prints is either
   the segment's amount or its within-column share. Every column has exactly
   one caption, centred on it, naming it and printing its share of the whole
   if it prints one. Every series has exactly one legend key naming it. An
   information marker sits inside the segment that hosts it.

9. UNPOSITIONED GEOMETRY and FAIL CLOSED - no transform may move verified
   geometry or a bound label, by any of the three carriers (the `transform`
   attribute, an inline `style`, a rule in a <style> block), on the element
   or on an ancestor <g>/<svg>, and no CSS `width`/`height` may resize a
   segment behind the attributes this checker measures. A file that presents
   as a marimekko but yields fewer than two parseable columns is a finding,
   never a pass, and so is one whose `data-segment` sits in markup too broken
   for any <rect> to carry it.

Markup is read through the stdlib html.parser.HTMLParser, never a regex, so a
tag is recognized exactly when a browser would recognize it: a quoted `>`
inside an attribute value does not end the tag, a repeated attribute keeps its
FIRST value and the rest are not in the document at all, unquoted values and
upper-case names parse as their canonical form, and a comment's contents are
never live markup. This follows verify-streamgraph.py and the fail-open shape
verify-block-registry.py retired: a regex tag matcher stops at the first `>`
it sees, so `<g data-note=">" transform="...">` hid its transform from the
checker while Chromium applied it to everything inside. Scope detection is
held to the same standard: `data-segment=` anywhere in the comment-stripped
source is the claim, the parser confirms which element carries it, and a
claim no parsed element carries is the fail-closed case.

The basis for every geometric check is the `data-amount` each segment's <rect>
declares, never the rendered text. A segment whose label is missing stays in
the verified set; the shipped example's narrowest column carries no label at
all and is named in the legend instead.

WHAT THIS DOES NOT CHECK, deliberately:

- **Absolute truth.** Every check is internal consistency; a figure wrong by
  the same factor everywhere is self-consistent and passes. The source line is
  where the unit and the period are stated to a reader, and prose is not parsed.
- **The column and series budgets.** 3-8 columns and 2-5 series are editorial
  guidance in type-treemap.md, not geometry.
- **Colour.** The accent-plus-ramp rule is `lint-skin.py`'s beat; only the
  accent COUNT is read here, off the stroke, as verify-beeswarm.py does.
- **Scenery.** A <rect> that declares no data-segment is decoration by
  contract (the paper mask under each segment is one) and is not compared
  against anything.

Usage:
    python3 scripts/verify-marimekko.py --all
    python3 scripts/verify-marimekko.py skills/diagram-design/assets/example-marimekko.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

# Every CSS property that can move or reshape a verified mark WITHOUT touching
# the attributes this checker reads. The enumeration IS the invariant - copied
# from verify-streamgraph.py and adapted to what moves a <rect> (x/y), a
# marker <circle> (cx/cy/r) and a bound label (x/y). Anchored to a
# declaration start so `text-transform:` never matches and the `rotate` inside
# `transform: rotate(45deg)` is read once as the property; a vendor prefix is
# optional so `-webkit-transform:` is not a free pass. `width`/`height` are
# in the set because SVG 2 makes them CSS geometry properties on a rect
# (Chromium honours it): `rect { width: ... }` or `style="width: ..."` draws
# a segment at a size the checked attributes never state. Every shipped page
# sizes its <svg> and its legend swatches with them in the stylesheet, so a
# <style> rule is only reported when its selector can reach a segment rect
# (see selector_reaches_segment); an inline style on a segment or an
# ancestor is reported outright. Comments are blanked before matching: the
# boundary allows only whitespace, and a browser reads `/* */` as exactly
# that, so `style="/**/transform: ..."` is a live transform.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|x|y|cx|cy|r|width|height"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
# The size pair above is the only part of the set whose <style> reading is
# gated on the selector; the rest is reported on any selector.
CSS_SIZE_PROPS = ("width", "height")
# A CSS comment, `/* ... */`, non-greedy so two comments in one declaration
# block do not merge into one; blanked to whitespace, never removed, so the
# line arithmetic in a finding stays right.
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# An HTML comment. The parser already refuses to tokenize its contents; scope
# detection reads raw text and must refuse the same way, or a commented-out
# draft claims an unrelated file.
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# The complete numeric token a label may print. Matching only the first
# fragment is how "2,140" once agreed with metadata that said 2.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
# The scope key, read off the comment-stripped RAW source and not off a tag,
# so a declaration inside markup too broken to parse is still a claim and the
# breakage is a finding rather than a silent skip. Which element carries it
# is the parser's call (see looks_like_marimekko), never a tag regex's: a
# `<rect\b[^>]*?data-segment` pattern stops at a quoted `>` and misses the
# live rect behind it. Detection only; parsing never uses it.
DECLARES_SEGMENT_RE = re.compile(r"\bdata-segment\s*=", re.IGNORECASE)
# The accent stroke on either skin, hex or rgba. The focal count keys on the
# STROKE, as in verify-beeswarm.py: it is the mark's edge and the thing a
# reader identifies the focal segment by.
ACCENT_RE = re.compile(
    r"#eb6c36\b|#f08a59\b|rgba\(\s*235\s*,\s*108\s*,\s*54\b|rgba\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)

# Relative tolerance on width, height and area shares. Column edges snap to
# the 4px grid and a 24px column cannot do better than a few percent; 8% is
# loose enough never to fire on honest snapping and tight enough to catch the
# smallest dishonest nudge worth making (the shipped sliver is off by 2.6%).
SHARE_TOLERANCE = 8.0      # percent, relative
EDGE_TOLERANCE = 0.5       # px, tiling, shared plot edges, gutter equality
ANCHOR_TOLERANCE = 1.0     # px, a label anchor vs the segment hosting it
CAPTION_TOLERANCE = 0.5    # px, caption x vs its column centre
PERCENT_TOLERANCE = 1.0    # percentage points, a printed integer percentage
AMOUNT_TOLERANCE = 0.001   # a printed amount vs the declared one
MARKER_EPSILON = 0.01      # px, an information marker crossing its segment

# Text extent is estimated from font metrics rather than measured in a
# browser, as verify-treemap.py does: the Latin advances are calibrated
# against Chromium renderings of the shipped Geist / Geist Mono faces and
# rounded UP, wide/full-width glyphs take a conservative 1em, so the estimate
# reports overflow slightly before real overflow, never after.
MONO_ADVANCE = 0.62
SANS_ADVANCE = 0.60
WIDE_ADVANCE = 1.00
ASCENT = 0.74

GROUP_TAGS = ("g", "svg")                     # the only ancestors whose transform is inherited
BODY_TAGS = ("text", "title", "desc", "style")  # elements whose character data is read
ROLES = ("label", "caption", "key")


# === PARSING =================================================================


class Element:
    """One start tag this checker cares about, as the browser tokenized it."""

    __slots__ = ("tag", "attrs", "line", "body", "ancestor")

    def __init__(self, tag, attrs, line, ancestor):
        self.tag = tag
        self.attrs = attrs          # first-wins dict, names lower-cased, values unescaped
        self.line = line
        self.body = ""              # character data up to the matching end tag
        self.ancestor = ancestor    # how the nearest transformed <g>/<svg> moves it, or None


class Segment:
    __slots__ = ("column", "series", "amount", "x", "y", "w", "h", "line", "accent", "element")

    def __init__(self, column, series, amount, x, y, w, h, line, accent, element):
        self.column, self.series, self.amount = column, series, amount
        self.x, self.y, self.w, self.h = x, y, w, h
        self.line, self.accent, self.element = line, accent, element

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    @property
    def area(self):
        return self.w * self.h

    def contains(self, px, py, slack=0.0):
        return (self.x - slack <= px <= self.right + slack
                and self.y - slack <= py <= self.bottom + slack)


class Column:
    __slots__ = ("name", "segments", "x", "w", "top", "bottom", "line")

    def __init__(self, name, segments):
        self.name = name
        self.segments = sorted(segments, key=lambda s: s.y)
        self.x = self.segments[0].x
        self.w = self.segments[0].w
        self.top = min(s.y for s in self.segments)
        self.bottom = max(s.bottom for s in self.segments)
        self.line = self.segments[0].line

    @property
    def right(self):
        return self.x + self.w

    @property
    def centre(self):
        return self.x + self.w / 2.0

    @property
    def height(self):
        return self.bottom - self.top

    @property
    def total(self):
        return sum(s.amount for s in self.segments)


def first_wins(attrs) -> dict:
    """Attributes as the browser keeps them: on a repeat, the FIRST wins.

    HTML parsing drops a duplicate attribute rather than overwriting the one
    already on the token, so a second `width` on a rect is not merely ignored -
    it is not in the document at all. A dict comprehension does the opposite,
    and that gap is a fail-open every caller inherits: a rect carrying a
    dishonest first `width` and an honest second renders the dishonest one
    while a last-wins reader checks, and passes, bytes the browser threw away.
    A present-but-valueless attribute is an empty string, not an absent one.
    """
    seen = {}
    for name, value in attrs:
        seen.setdefault(name, "" if value is None else value)
    return seen


class _Scanner(HTMLParser):
    """Collect rects, circles, texts, title/desc and style elements with ancestry.

    HTMLParser already lowercases tag and attribute names, tolerates unquoted
    values and whitespace around `=`, unescapes entities, keeps a quoted `>`
    inside the value it belongs to, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text - each
    of those is exactly a case a regex tag matcher mishandles. Ancestry is
    tracked for <g>/<svg> only, the elements whose transform a child inherits.
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.rects: list = []
        self.circles: list = []
        self.texts: list = []
        self.named: list = []      # <title> and <desc>
        self.styles: list = []
        self.segment_carriers = 0  # live elements of ANY tag that carry data-segment
        self.error = None
        self._groups: list = []    # (tag, how) per open <g>/<svg>
        self._open: list = []      # (tag, Element) per open body element
        try:
            self.feed(source)
            self.close()
        except Exception as exc:  # noqa: BLE001 - any parser failure fails closed
            self.error = "%s: %s" % (type(exc).__name__, exc)

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
        # Counted on every tag, before the scope filters below: the count is
        # how scope detection tells a legitimate carrier that is simply not a
        # <rect> (a legend key) from a claim no parsed element carries at all.
        if "data-segment" in attrs:
            self.segment_carriers += 1
        if tag in GROUP_TAGS:
            if not closes:
                how = None
                if "transform" in attrs:
                    how = "an ancestor <g>/<svg> transform"
                elif transform_carrier(attrs) is not None:
                    how = "an ancestor <g>/<svg> style transform"
                self._groups.append((tag, how))
            return
        if tag not in ("rect", "circle") and tag not in BODY_TAGS:
            return
        element = Element(tag, attrs, self.getpos()[0], self._ancestor())
        if tag == "rect":
            self.rects.append(element)
            return
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


def transform_carrier(attrs: dict):
    """How this element carries a transform, phrased for the finding, or None.

    A transform reaches the renderer by three carriers and the `transform`
    ATTRIBUTE is only the most visible one. Reading the attribute alone lets
    `style="transform: translateY(...)"` on a segment, a bound label or an
    ancestor group move the rendered mark after its raw coordinates were
    validated. The third carrier, a rule in a <style> block, is reported
    separately because nothing here can tell which marks such a rule selects.
    """
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(blank_css_comments(style))
        if found is not None:
            return "style=%r (the %s property)" % (style, found.group("prop").lower())
    return None


def blank_css_comments(css: str) -> str:
    """CSS with every `/* ... */` replaced by whitespace of the same line count.

    A browser drops a comment before it tokenizes declarations, so a comment
    is whitespace to it and must be whitespace to CSS_MOVES_MARK_RE, whose
    boundary permits nothing else. Newlines inside the comment are kept so a
    match offset still counts lines from the top of the <style> body.
    """
    return CSS_COMMENT_RE.sub(lambda found: " " + "\n" * found.group().count("\n"), css)


def strip_html_comments(source: str) -> str:
    return HTML_COMMENT_RE.sub(" ", source)


def selector_reaches_segment(selector: str, segments: list) -> bool:
    """Could this selector's subject be one of the segment rects? Coarse on purpose.

    Not a selector engine. A `rect` type selector or a `*` anywhere in the
    selector claims it; a subject that names any other element (`svg`, `text`,
    `.legend span`) cannot be a rect and is passed; a subject made of classes,
    ids and attributes alone (`.seg`, `[data-segment]`) reaches a segment when
    some segment rect actually carries one of them. Anything this misreads it
    misreads towards a finding, which is the direction a gate may err in.
    """
    for alternative in selector.split(","):
        if re.search(r"\brect\b|\*", alternative, re.IGNORECASE):
            return True
        compounds = [part for part in re.split(r"[\s>+~]+", alternative.strip()) if part]
        if not compounds:
            continue
        subject = re.sub(r"::?[\w-]+(?:\([^)]*\))?", "", compounds[-1])
        if re.match(r"[A-Za-z]", subject):
            continue
        classes = set(re.findall(r"\.([\w-]+)", subject))
        ids = set(re.findall(r"#([\w-]+)", subject))
        names = {name.lower() for name in re.findall(r"\[\s*([\w-]+)", subject)}
        for segment in segments:
            attrs = segment.element.attrs
            if (classes & set(attrs.get("class", "").split())
                    or attrs.get("id") in ids
                    or names & set(attrs)):
                return True
    return False


def css_geometry_declaration(css: str, segments: list):
    """The first declaration in a stylesheet that moves or resizes a verified mark.

    Transform-family and x/y/cx/cy/r declarations are reported whatever their
    selector, as before: nothing here can tell which marks they select. The
    size pair is gated on the selector because every shipped page has an
    honest `svg { width: 100% }` and `.card-dot { width: 7px }`, and a gate
    that fires on every shipped page is switched off, not obeyed.
    """
    for found in CSS_MOVES_MARK_RE.finditer(css):
        if found.group("prop").lower() not in CSS_SIZE_PROPS:
            return found
        start = found.start("prop")
        opened = css.rfind("{", 0, start)
        if opened < 0:
            continue  # a declaration outside any rule is not CSS a browser applies
        previous = max(css.rfind("}", 0, opened), css.rfind("{", 0, opened))
        if selector_reaches_segment(css[previous + 1:opened], segments):
            return found
    return None


def declares_segment_rect(doc: _Scanner) -> bool:
    """Does any live <rect> carry data-segment? The parser's word on the scope key."""
    return any("data-segment" in element.attrs for element in doc.rects)


def raw_declares_segment(source: str) -> bool:
    """Does data-segment= appear anywhere outside a comment? The raw claim."""
    return DECLARES_SEGMENT_RE.search(strip_html_comments(source)) is not None


def plain(body: str) -> str:
    return " ".join(body.split())


def number(value):
    """A finite float, or None - NaN satisfies every tolerance check silently."""
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def printed_numbers(body: str) -> list:
    """[(value, is_percent)] for every complete numeric token in visible text."""
    found = []
    for match in NUMBER_RE.finditer(body):
        value = number(match.group())
        if value is None:
            continue
        rest = body[match.end():].lstrip()
        found.append((value, rest.startswith("%")))
    return found


def estimated_advance(text: str, mono: bool) -> float:
    """Conservative text advance in em, per verify-treemap.py."""
    narrow = MONO_ADVANCE if mono else SANS_ADVANCE
    advance = 0.0
    for char in text:
        if unicodedata.category(char) in {"Mn", "Me"}:
            continue
        advance += WIDE_ADVANCE if unicodedata.east_asian_width(char) in {"W", "F"} else narrow
    return advance


def label_extent(attrs: dict, body: str):
    """(left, top, right, bottom) of a <text> in root user space, or None."""
    x, y = number(attrs.get("x")), number(attrs.get("y"))
    size = number(attrs.get("font-size", "12"))
    text = plain(body)
    if x is None or y is None or size is None or not text:
        return None
    mono = "mono" in attrs.get("font-family", "").lower()
    width = size * estimated_advance(text, mono)
    anchor = attrs.get("text-anchor", "start")
    left = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
    return (left, y - size * ASCENT, left + width, y)


def named_text(doc: _Scanner) -> str:
    return " ".join(plain(element.body) for element in doc.named).casefold()


def looks_like_marimekko(path: Path, source: str) -> bool:
    """Does this file present itself as a marimekko?

    Deliberately generous on everything EXCEPT the element scope: a file that
    claims the type in its name, its accessible description, or by binding
    data-segment on any <rect> is held to the contract, and one that claims
    it while declaring nothing parseable is the fail-closed case, not a pass.
    The rect restriction is the treaty line with the sibling gates: bump
    binds data-ranks on <path>, ridgeline data-bins on <path>, slopegraph
    data-series on <line>, bubble data-size and beeswarm data-value on
    <circle>, treemap data-share on <rect>. None of them reads data-segment,
    and this gate reads nothing of theirs.

    The raw claim and the parsed carrier are read together. HTML comments are
    stripped first, so a commented-out draft cannot claim a live file. Then
    the parser says which element carries data-segment: a <rect> claims the
    file; another element alone (a legend key on a bar chart) does not; and a
    raw `data-segment=` that NO parsed element carries is markup the browser
    tokenized differently from how it reads - claimed, so check_source can
    fail it closed rather than let the breakage read as out of scope.
    """
    if path.name.startswith("example-marimekko"):
        return True
    doc = parse_document(source)
    if declares_segment_rect(doc):
        return True
    if doc.segment_carriers == 0 and raw_declares_segment(source):
        return True
    described = named_text(doc)
    return "marimekko" in described or "mekko" in described or "mosaic chart" in described


def parse_segments(doc: _Scanner, findings: list, name: str) -> list:
    """Segment rects, with anything unparseable reported rather than dropped."""
    segments = []
    seen = {}
    for element in doc.rects:
        attrs = element.attrs
        series = attrs.get("data-segment")
        if series is None:
            # A <rect> with no data-segment is scenery by contract: the paper
            # mask under each segment, the page background, a legend swatch.
            continue
        line = element.line
        column = attrs.get("data-column")
        if not series or not column:
            findings.append(
                "%s:%d: a segment rect must name both its column (data-column) and "
                "its series (data-segment), and neither may be empty"
                % (name, line)
            )
            continue
        if "data-amount" not in attrs:
            findings.append(
                "%s:%d: segment %s × %s declares no data-amount — every segment "
                "states its amount or its width, height and area are unverifiable"
                % (name, line, column, series)
            )
            continue
        amount = number(attrs["data-amount"])
        if amount is None or amount <= 0:
            findings.append(
                "%s:%d: segment %s × %s declares data-amount=%r — an amount is a "
                "finite positive number; a series absent from a column is omitted, "
                "never drawn at zero" % (name, line, column, series, attrs["data-amount"])
            )
            continue
        geometry = [number(attrs.get(key)) for key in ("x", "y", "width", "height")]
        if any(value is None for value in geometry) or geometry[2] <= 0 or geometry[3] <= 0:
            findings.append(
                "%s:%d: segment %s × %s has missing or unparseable x/y/width/height — "
                "a rect this checker cannot measure is a finding, not a pass"
                % (name, line, column, series)
            )
            continue
        key = (column, series)
        if key in seen:
            findings.append(
                "%s:%d: a second rect declares segment %s × %s (first at line %d) — one "
                "segment, one rect, or the figure states two amounts for one cell"
                % (name, line, column, series, seen[key])
            )
            continue
        seen[key] = line
        accent = bool(ACCENT_RE.search(attrs.get("stroke", "")))
        segments.append(Segment(column, series, amount, *geometry, line, accent, element))
    return segments


def group_columns(segments: list, findings: list, name: str) -> list:
    """Columns left to right; a segment off its column's width is reported."""
    by_name: dict = {}
    for segment in segments:
        by_name.setdefault(segment.column, []).append(segment)
    columns = []
    for column_name, members in by_name.items():
        column = Column(column_name, members)
        for segment in column.segments:
            if abs(segment.x - column.x) > EDGE_TOLERANCE or abs(segment.w - column.w) > EDGE_TOLERANCE:
                findings.append(
                    "%s:%d: segment %s × %s spans x %g–%g but its column's first segment "
                    "spans %g–%g — every segment is the full width of its column, "
                    "because width is the column's share and belongs to no one segment"
                    % (name, segment.line, column.name, segment.series,
                       segment.x, segment.right, column.x, column.right)
                )
        columns.append(column)
    return sorted(columns, key=lambda c: c.x)


# === CHECKS ==================================================================


def is_bound(attrs: dict) -> bool:
    return "data-column" in attrs or "data-segment" in attrs or "data-role" in attrs


def check_transforms(doc: _Scanner, segments: list, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label.

    Rejected rather than resolved, following verify-slopegraph.py: a partial
    implementation of the SVG transform stack is worse than an honest
    refusal, because it looks like coverage. All three carriers are held to
    that rule on the element and on every <g>/<svg> above it, because a gate
    that closes one of three doorways guards nothing.
    """

    def report(element, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw rect and label "
            "coordinates, so a transform moves the rendered mark away from the "
            "number it was checked against. Bake the offset into the coordinates "
            "instead" % (name, element.line, what, how)
        )

    def check_element(element, what):
        how = transform_carrier(element.attrs)
        if how is None:
            how = element.ancestor
        if how is not None:
            report(element, what, how)

    for segment in segments:
        check_element(segment.element, "segment %s × %s" % (segment.column, segment.series))

    for element in doc.texts:
        if is_bound(element.attrs):
            check_element(element, "a bound label (%s)" % plain(element.body)[:20])

    for element in doc.styles:
        css = blank_css_comments(element.body)
        found = css_geometry_declaration(css, segments)
        if found:
            findings.append(
                "%s:%d: a CSS `%s` declaration — this checker cannot tell which "
                "marks it applies to, and one that positions verified geometry "
                "invalidates every coordinate here. Remove it, or bake the offset "
                "into the coordinates"
                % (name, element.line + css.count("\n", 0, found.start()),
                   found.group("prop").lower())
            )


def check_plot(columns: list, findings: list, name: str) -> bool:
    """Every column spans one plot; columns tile left to right with one gutter."""
    ok = True
    reference = columns[0]
    for column in columns[1:]:
        if abs(column.top - reference.top) > EDGE_TOLERANCE or \
                abs(column.bottom - reference.bottom) > EDGE_TOLERANCE:
            findings.append(
                "%s:%d: column %r spans y %g–%g but column %r spans %g–%g — every "
                "column is the full plot height, so a segment's height is always "
                "a share of its own column. A shorter column is a share of nothing"
                % (name, column.line, column.name, column.top, column.bottom,
                   reference.name, reference.top, reference.bottom)
            )
            ok = False
    gutters = []
    for left, right in zip(columns, columns[1:]):
        gap = right.x - left.right
        if gap < -EDGE_TOLERANCE:
            findings.append(
                "%s:%d: column %r starts at x=%g, %g px inside column %r (which ends at "
                "x=%g) — columns never overlap; the overlap is width stolen from one "
                "and given to the other"
                % (name, right.line, right.name, right.x, -gap, left.name, left.right)
            )
            ok = False
            continue
        gutters.append((gap, right))
    if gutters:
        reference_gap = gutters[0][0]
        for gap, column in gutters[1:]:
            if abs(gap - reference_gap) > EDGE_TOLERANCE:
                findings.append(
                    "%s:%d: the gutter before column %r is %g px but the first gutter "
                    "is %g px — one constant gutter, or a widened gap reads as a "
                    "narrower column"
                    % (name, column.line, column.name, gap, reference_gap)
                )
                ok = False
    return ok


def check_tiling(columns: list, findings: list, name: str) -> None:
    """Segments sit flush from the column top to its bottom."""
    for column in columns:
        for below, above in zip(column.segments, column.segments[1:]):
            gap = above.y - below.bottom
            if abs(gap) > EDGE_TOLERANCE:
                findings.append(
                    "%s:%d: segment %s × %s starts %g px %s the end of %s × %s — "
                    "segments tile their column with no gaps and no overlaps, so "
                    "every height stays a share of the column and no series is "
                    "padded or dropped silently"
                    % (name, above.line, column.name, above.series, abs(gap),
                       "below" if gap > 0 else "above", column.name, below.series)
                )


def relative(drawn: float, declared: float) -> float:
    return (drawn - declared) / declared * 100.0


def check_shares(columns: list, findings: list, name: str) -> None:
    """Width, height and area each match the share they encode."""
    grand_total = sum(column.total for column in columns)
    width_total = sum(column.w for column in columns)
    area_total = sum(segment.area for column in columns for segment in column.segments)
    for column in columns:
        declared = column.total / grand_total * 100.0
        drawn = column.w / width_total * 100.0
        drift = relative(drawn, declared)
        if abs(drift) > SHARE_TOLERANCE:
            findings.append(
                "%s:%d: column %r is %g px wide, %.2f%% of the column width, but its "
                "%g of %g total is %.2f%% — %+.1f%% relative. Width is the column's "
                "share of the whole; resize the column, never the number"
                % (name, column.line, column.name, column.w, drawn, column.total,
                   grand_total, declared, drift)
            )
        for segment in column.segments:
            declared_h = segment.amount / column.total * 100.0
            drawn_h = segment.h / column.height * 100.0
            drift = relative(drawn_h, declared_h)
            if abs(drift) > SHARE_TOLERANCE:
                findings.append(
                    "%s:%d: segment %s × %s is %g px tall, %.2f%% of its column, but "
                    "%g of the column's %g is %.2f%% — %+.1f%% relative. Height is the "
                    "share within the column; resize the segment, never the number"
                    % (name, segment.line, column.name, segment.series, segment.h,
                       drawn_h, segment.amount, column.total, declared_h, drift)
                )
            declared_a = segment.amount / grand_total * 100.0
            drawn_a = segment.area / area_total * 100.0
            drift = relative(drawn_a, declared_a)
            if abs(drift) > SHARE_TOLERANCE:
                findings.append(
                    "%s:%d: segment %s × %s draws %.2f%% of the area but %g of %g is "
                    "%.2f%% of the whole — %+.1f%% relative. Area is the joint share, "
                    "the one reading a marimekko exists to give"
                    % (name, segment.line, column.name, segment.series, drawn_a,
                       segment.amount, grand_total, declared_a, drift)
                )


def check_series_order(columns: list, findings: list, name: str) -> None:
    """The top-to-bottom order of series never contradicts itself."""
    before: dict = {}   # (earlier, later) -> column that established it
    for column in columns:
        order = [segment.series for segment in column.segments]
        for i, earlier in enumerate(order):
            for later in order[i + 1:]:
                if (later, earlier) in before:
                    findings.append(
                        "%s:%d: column %r draws %r above %r, but column %r draws them "
                        "the other way round — one fixed series order in every column, "
                        "or a row cannot be read across the figure"
                        % (name, column.line, column.name, earlier, later,
                           before[(later, earlier)])
                    )
                before.setdefault((earlier, later), column.name)


def check_accent(segments: list, findings: list, name: str) -> None:
    """At most one segment wears the accent."""
    accented = [segment for segment in segments if segment.accent]
    for extra in accented[1:]:
        findings.append(
            "%s:%d: segment %s × %s also carries the accent stroke — one focal "
            "segment max (%s × %s already has it). A second accent is a second "
            "claim about what the figure is about"
            % (name, extra.line, extra.column, extra.series,
               accented[0].column, accented[0].series)
        )


def check_labels(doc: _Scanner, columns: list, findings: list, name: str) -> None:
    """Every bound string is anchored where it belongs and prints what it binds."""
    by_key = {(s.column, s.series): s for c in columns for s in c.segments}
    by_column = {column.name: column for column in columns}
    series = {s.series for c in columns for s in c.segments}
    grand_total = sum(column.total for column in columns)
    captions: dict = {}
    keys: dict = {}

    for element in doc.texts:
        attrs = element.attrs
        if not is_bound(attrs):
            continue
        line, body = element.line, plain(element.body)
        role = attrs.get("data-role")
        if role not in ROLES:
            findings.append(
                "%s:%d: a bound text (%r) declares data-role=%r — a bound string is a "
                "segment label, a column caption or a series key, or it cannot be "
                "checked against anything" % (name, line, body[:24], role)
            )
            continue

        if role == "label":
            key = (attrs.get("data-column"), attrs.get("data-segment"))
            segment = by_key.get(key)
            if segment is None:
                findings.append(
                    "%s:%d: label %r binds segment %s × %s, which no rect declares — a "
                    "label with no segment is not verifiable and reads as data"
                    % (name, line, body[:24], key[0], key[1])
                )
                continue
            x, y = number(attrs.get("x")), number(attrs.get("y"))
            if x is None or y is None or not segment.contains(x, y, ANCHOR_TOLERANCE):
                findings.append(
                    "%s:%d: label %r is anchored at (%s, %s), outside the %gx%g segment "
                    "%s × %s it binds — a label sits inside the segment it names"
                    % (name, line, body[:24],
                       "%g" % x if x is not None else "?", "%g" % y if y is not None else "?",
                       segment.w, segment.h, segment.column, segment.series)
                )
                continue
            extent = label_extent(attrs, element.body)
            if extent is not None:
                left, top, right, bottom = extent
                overflow = {"left": segment.x - left, "top": segment.y - top,
                            "right": right - segment.right, "bottom": bottom - segment.bottom}
                breached = {side: over for side, over in overflow.items() if over > ANCHOR_TOLERANCE}
                if breached:
                    detail = " / ".join("%.1f %s" % (over, side) for side, over in breached.items())
                    findings.append(
                        "%s:%d: label %r overflows its %gx%g segment %s × %s by %s — drop "
                        "the label and name the segment in the legend; never widen the "
                        "segment to fit it"
                        % (name, line, body[:24], segment.w, segment.h,
                           segment.column, segment.series, detail)
                    )
            column = by_column[segment.column]
            within = segment.amount / column.total * 100.0
            for value, is_percent in printed_numbers(body):
                if is_percent:
                    if abs(value - within) > PERCENT_TOLERANCE:
                        findings.append(
                            "%s:%d: label %r prints %g%% but segment %s × %s is %.1f%% of "
                            "its column — the label and the amount must state one fact"
                            % (name, line, body[:24], value, segment.column,
                               segment.series, within)
                        )
                elif abs(value - segment.amount) > AMOUNT_TOLERANCE:
                    findings.append(
                        "%s:%d: label %r prints %g but segment %s × %s declares "
                        "data-amount=%g — the label and the amount must state one fact"
                        % (name, line, body[:24], value, segment.column,
                           segment.series, segment.amount)
                    )

        elif role == "caption":
            column = by_column.get(attrs.get("data-column"))
            if column is None:
                findings.append(
                    "%s:%d: caption %r binds column %r, which no segment declares"
                    % (name, line, body[:24], attrs.get("data-column"))
                )
                continue
            if column.name in captions:
                findings.append(
                    "%s:%d: a second caption for column %r — one column, one caption"
                    % (name, line, column.name)
                )
                continue
            captions[column.name] = line
            x = number(attrs.get("x"))
            if x is None or abs(x - column.centre) > CAPTION_TOLERANCE:
                findings.append(
                    "%s:%d: the caption for column %r is anchored at x=%s but the column "
                    "is centred at x=%g — a caption off its column renames the column "
                    "beside it" % (name, line, column.name,
                                   "%g" % x if x is not None else "?", column.centre)
                )
            if column.name not in body:
                findings.append(
                    "%s:%d: the caption for column %r reads %r, which does not name that "
                    "column — bind the visible name, or a caption can label the wrong "
                    "column while its data-column stays right"
                    % (name, line, column.name, body[:24])
                )
            share = column.total / grand_total * 100.0
            for value, is_percent in printed_numbers(body):
                if is_percent and abs(value - share) > PERCENT_TOLERANCE:
                    findings.append(
                        "%s:%d: the caption for column %r prints %g%% but the column is "
                        "%.1f%% of the whole — the caption and the amounts must state "
                        "one fact" % (name, line, column.name, value, share)
                    )

        elif role == "key":
            label = attrs.get("data-segment")
            if label not in series:
                findings.append(
                    "%s:%d: legend key %r names series %r, which no segment declares"
                    % (name, line, body[:24], label)
                )
                continue
            if label in keys:
                findings.append(
                    "%s:%d: a second legend key for series %r — one series, one key"
                    % (name, line, label)
                )
                continue
            keys[label] = line
            if label not in body:
                findings.append(
                    "%s:%d: the legend key for series %r reads %r, which does not name "
                    "it — bind the visible name as well as the series"
                    % (name, line, label, body[:24])
                )

    for column in columns:
        if column.name not in captions:
            findings.append(
                "%s:%d: column %r has no caption (a <text> with data-role=\"caption\" and "
                "data-column) — every column is named, or the reader cannot say what "
                "a width belongs to" % (name, column.line, column.name)
            )
    for label in sorted(series):
        if label not in keys:
            findings.append(
                "%s: series %r has no legend key (a <text> with data-role=\"key\" and "
                "data-segment) — every series is named once, or a row can be dropped "
                "from the reading silently" % (name, label)
            )


def check_markers(doc: _Scanner, segments: list, findings: list, name: str) -> None:
    """An information marker disc stays inside the segment hosting it."""
    for element in doc.circles:
        attrs = element.attrs
        cx, cy, radius = number(attrs.get("cx")), number(attrs.get("cy")), number(attrs.get("r"))
        if cx is None or cy is None or radius is None or not 4.0 <= radius <= 6.0:
            continue
        hosts = [s for s in segments if s.contains(cx, cy)]
        if not hosts:
            continue
        host = min(hosts, key=lambda s: s.area)
        overflow = {"left": host.x - (cx - radius), "top": host.y - (cy - radius),
                    "right": (cx + radius) - host.right, "bottom": (cy + radius) - host.bottom}
        breached = {side: over for side, over in overflow.items() if over > MARKER_EPSILON}
        if breached:
            detail = " / ".join("%.1f %s" % (over, side) for side, over in breached.items())
            findings.append(
                "%s:%d: information marker overflows its %gx%g segment %s × %s by %s — "
                "drop the marker and identify the segment in the legend"
                % (name, element.line, host.w, host.h, host.column, host.series, detail)
            )


# === DRIVER ==================================================================


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    findings: list = []
    doc = parse_document(raw)
    if doc.error is not None:
        findings.append(
            "%s: presents as a marimekko but could not be parsed as HTML (%s) — "
            "refusing to report OK on a file this checker could not read"
            % (path.name, doc.error)
        )
        return findings
    if (not declares_segment_rect(doc) and doc.segment_carriers == 0
            and raw_declares_segment(raw)):
        # The raw source says data-segment=, the browser's tokenizer found no
        # element carrying it: an unbalanced quote swallowed the attribute
        # into a neighbour's value. The old regex gate skipped this shape
        # whenever a quoted `>` preceded it; a claim the file cannot back is
        # a finding, never a skip.
        findings.append(
            "%s: declares data-segment but no complete <rect> could be parsed — "
            "the declaration sits inside markup the browser tokenizes differently "
            "from how it reads (an unbalanced quote swallows every attribute after "
            "it); fix the markup. Refusing to report OK on a file this checker "
            "could not read" % path.name
        )
        return findings
    segments = parse_segments(doc, findings, path.name)
    columns = group_columns(segments, findings, path.name)
    if len(columns) < 2:
        findings.append(
            "%s: presents as a marimekko but declares %d verifiable column(s) — every "
            "segment needs a <rect> with data-column, data-segment, data-amount and "
            "x/y/width/height. Refusing to report OK on a file this checker could not read"
            % (path.name, len(columns))
        )
        return findings

    check_transforms(doc, segments, findings, path.name)
    if check_plot(columns, findings, path.name):
        check_tiling(columns, findings, path.name)
        check_shares(columns, findings, path.name)
    check_series_order(columns, findings, path.name)
    check_accent(segments, findings, path.name)
    check_labels(doc, columns, findings, path.name)
    check_markers(doc, segments, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a marimekko."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_marimekko(path, raw):
        return []
    return check_source(path, raw)


def targets(args: argparse.Namespace) -> list:
    if args.all:
        return sorted(ASSET_DIR.glob("example-*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify marimekko columns and segments against the amounts they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a marimekko",
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
        if not looks_like_marimekko(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d marimekko finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK marimekko: no marimekko found to check%s" % tail)
        return 0
    print("OK marimekko: %d file(s), width is category share, height is within-column "
          "share, area is joint share, one series order, one accent, no transforms on "
          "verified geometry, and every label, caption and key bound to what it names%s"
          % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
