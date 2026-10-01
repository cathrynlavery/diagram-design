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
   total, the total must equal the sum of that layer's declared values, and the
   entry's visible text must name the layer it binds and no other. Each period
   caption binds its column index and its visible text. Unbound, captions can be
   exchanged or a layer quietly dropped from the legend - and a right datum under
   a wrong string is still a wrong figure: an entry reading one layer's name over
   another's data-layer clears every numeric check and labels the wrong band.

7. FAIL CLOSED - a file that presents as a streamgraph but yields nothing
   parseable is a finding, never a pass. A checker that reports OK because it
   found nothing to compare is the bug, not the gate.

Markup is read through the stdlib html.parser.HTMLParser, never a regex, so a
tag is recognized exactly when a browser would recognize it: a quoted `>`
inside an attribute value does not end the tag, a repeated attribute keeps its
FIRST value and the rest are not in the document at all, unquoted values and
upper-case names parse as their canonical form, and a comment's contents are
never live markup. The regex tag matcher this replaced stopped at the first
`>` it saw, so `<g data-note=">" transform="translate(0 -80)">` hid its
transform from the checker while Chromium applied it to every layer inside -
the same fail-open shape verify-block-registry.py retired for the same reason.

No transform may move verified geometry or a bound label, and a transform
reaches the renderer by three carriers: the `transform` attribute, an inline
`style="..."`, and a rule in a <style> block. All three are refused, on the
element and on any ancestor <g>/<svg>, following verify-beeswarm.py; the
property set in CSS_MOVES_MARK_RE is the invariant, adapted to what moves a
path (`d`) and a label (`x`/`y`) rather than a circle. CSS text is read the
way the CSS tokenizer reads it: a `/* */` comment is whitespace, so
`style="/**/transform: ..."` is the transform property, not a free pass.

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
- **Scenery.** A <path> that declares no data-layer is decoration by contract
  and is not compared against anything; the guarantee here is that every tag
  that DOES declare a binding is read exactly as the browser reads it.

Usage:
    python3 scripts/verify-streamgraph.py --all
    python3 scripts/verify-streamgraph.py skills/diagram-design/assets/example-streamgraph.html

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
#   d / x / y                                SVG geometry properties. CSS wins
#       over the presentation attribute, so `style="d: path(...)"` on a layer
#       replaces the very path that was verified, and x/y do the same to a
#       bound label - a more direct lie than any transform
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
    r"|d|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
# CSS Syntax Level 3 section 4.3.2: a `/* ... */` comment is consumed as if
# it were whitespace, so the tokenizer sees `/**/transform:` as the transform
# property at a declaration start. CSS_MOVES_MARK_RE allows only whitespace
# between the boundary and the name, so the comment must be turned into the
# whitespace it is BEFORE the regex runs, or a comment is a free pass
# through the guard. Non-greedy and DOTALL: a comment may span lines and
# the first `*/` ends it, as in the tokenizer.
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
# Detection reads raw text, and a commented-out tag is not in the document
# a browser builds - stripped before the raw signal is consulted so an old
# draft in a comment cannot claim an unrelated file for this checker.
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# The complete numeric token a legend may print. Matching only the first
# fragment is how "512,000" once agreed with metadata that said 512.
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")
# Detection only - deliberately a text search over the raw text (HTML
# comments removed), so a file that so much as mentions a layer binding in
# live markup is held to the contract even when the parser finds no complete
# layer - that is check_source's fail-closed case, not a skip.
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

GROUP_TAGS = ("g", "svg")                     # the only ancestors whose transform is inherited
BODY_TAGS = ("text", "title", "desc", "style")  # elements whose character data is read


# === PARSING =================================================================


class Element:
    """One start tag this checker cares about, as the browser tokenized it."""

    __slots__ = ("tag", "attrs", "offset", "line", "body", "ancestor")

    def __init__(self, tag, attrs, offset, line, ancestor):
        self.tag = tag
        self.attrs = attrs          # first-wins dict, names lower-cased, values unescaped
        self.offset = offset        # byte offset of `<` in the source, for ordering
        self.line = line
        self.body = ""              # character data up to the matching end tag
        self.ancestor = ancestor    # how the nearest transformed <g>/<svg> moves it, or None


class Layer:
    __slots__ = ("name", "values", "top", "bottom", "line", "controls")

    def __init__(self, name, values, top, bottom, line):
        self.name = name
        self.values = values          # per-period, left to right
        self.top = top                # on-curve points, left to right
        self.bottom = bottom          # on-curve points, left to right
        self.line = line
        self.controls = []            # (boundary, segment, (c1, c2)) as drawn


def first_wins(attrs) -> dict:
    """Attributes as the browser keeps them: on a repeat, the FIRST wins.

    HTML parsing drops a duplicate attribute rather than overwriting the one
    already on the token, so a second `d` on a path is not merely ignored -
    it is not in the document at all. A dict comprehension does the opposite,
    and that gap is a fail-open every caller inherits: a path carrying an
    invalid first `d` and a valid second renders the invalid geometry while a
    last-wins reader checks, and passes, bytes the browser threw away.
    Confirmed in Chromium against the shipped example - the parsed DOM keeps
    `d="M 0 0 Z"` and the real path is absent. A present-but-valueless
    attribute is an empty string, not an absent attribute.
    """
    seen = {}
    for name, value in attrs:
        seen.setdefault(name, "" if value is None else value)
    return seen


class _Scanner(HTMLParser):
    """Collect paths, texts, title/desc and style elements with ancestry.

    HTMLParser already lowercases tag and attribute names, tolerates unquoted
    values and whitespace around `=`, unescapes entities, keeps a quoted `>`
    inside the value it belongs to, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text - each
    of those is exactly a case a regex tag matcher mishandles. Ancestry is
    tracked for <g>/<svg> only, the elements whose transform a child inherits.
    """

    def __init__(self, source: str):
        super().__init__(convert_charrefs=True)
        self.paths: list = []
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
        if tag != "path" and tag not in BODY_TAGS:
            return
        element = Element(tag, attrs, self._offset(), self.getpos()[0], self._ancestor())
        if tag == "path":
            self.paths.append(element)
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


def strip_css_comments(text: str) -> str:
    """CSS text with every `/* ... */` replaced by the whitespace it is.

    Each comment becomes one space plus the newlines it contained, so the
    result tokenizes as the browser tokenizes the original AND keeps every
    line number where it was: the <style> finding reports the line of the
    declaration by counting newlines up to the match, and a comment that
    swallowed its newlines would shift that line.
    """
    return CSS_COMMENT_RE.sub(lambda found: " " + "\n" * found.group().count("\n"), text)


def transform_carrier(attrs: dict):
    """How this element carries a transform, phrased for the finding, or None.

    A transform reaches the renderer by three carriers and the `transform`
    ATTRIBUTE is only the most visible one. Reading the attribute alone lets
    `style="transform: translateY(...)"` on a layer, a bound label or an
    ancestor group move the rendered mark after its raw coordinates were
    validated. The third carrier, a rule in a <style> block, is reported
    separately because nothing here can tell which marks such a rule selects.
    """
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(strip_css_comments(style))
        if found is not None:
            return "style=%r (the %s property)" % (style, found.group("prop").lower())
    return None


def plain(body: str) -> str:
    return body.strip()


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


def named_text(doc: _Scanner) -> str:
    return " ".join(plain(element.body) for element in doc.named).casefold()


def looks_like_streamgraph(path: Path, source: str) -> bool:
    """Does this file present itself as a streamgraph?

    Deliberately generous, and searched whole-document: anything that claims
    the type in its name, its accessible description, or its markup is held to
    the contract even if it declares nothing parseable - that combination is
    the fail-closed case, not a pass. HTML comments are not markup, so a
    commented-out draft of a layer cannot pull another example type into
    scope; a mangled tag whose bytes still say `data-layer=` can, and then
    the parser finding no complete layer is exactly what is reported.
    """
    if path.name.startswith("example-streamgraph"):
        return True
    if DECLARES_LAYER_RE.search(HTML_COMMENT_RE.sub(" ", source)):
        return True
    described = named_text(parse_document(source))
    return "streamgraph" in described or "stream graph" in described


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


def parse_layers(doc: _Scanner, findings: list, name: str) -> list:
    """Layer paths, with anything unparseable reported rather than dropped."""
    layers = []
    seen = set()
    for element in doc.paths:
        attrs = element.attrs
        label = attrs.get("data-layer")
        if label is None:
            # A <path> with no data-layer is scenery by contract. The parser
            # reads every tag the browser reads, so there is no "declared but
            # unparseable" case left to report here.
            continue
        line = element.line
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
        layer = Layer(label, values, top, list(reversed(bottom)), line)
        layer.controls = controls
        layers.append(layer)
    return layers


# === CHECKS ==================================================================


def is_bound_label(attrs: dict) -> bool:
    return "data-layer" in attrs or "data-period" in attrs or "data-index" in attrs


def check_transforms(doc: _Scanner, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label.

    Rejected rather than resolved, following verify-slopegraph.py: a partial
    implementation of the SVG transform stack is worse than an honest
    refusal, because it looks like coverage. All three carriers are held to
    that rule - the `transform` attribute, an inline `style="transform: ..."`,
    and a rule in a <style> block - on the element and on every <g>/<svg>
    above it, because a gate that closes one of three doorways guards nothing.
    """

    def report(element, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw path and label "
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

    for element in doc.paths:
        if "data-layer" in element.attrs:
            check_element(element, "layer %r" % element.attrs["data-layer"])

    for element in doc.texts:
        if is_bound_label(element.attrs):
            check_element(element, "a bound label (%s)" % plain(element.body)[:20])

    for element in doc.styles:
        # Comments become whitespace before the search (a `/**/` prefix is
        # not a declaration boundary the regex knows), with newlines kept so
        # the reported line is the declaration's line in the source.
        body = strip_css_comments(element.body)
        found = CSS_MOVES_MARK_RE.search(body)
        if found:
            findings.append(
                "%s:%d: a CSS `%s` declaration — this checker cannot tell which "
                "marks it applies to, and one that positions verified geometry "
                "invalidates every coordinate here. Remove it, or bake the offset "
                "into the coordinates"
                % (name, element.line + body.count("\n", 0, found.start()),
                   found.group("prop").lower())
            )


def check_columns(layers: list, findings: list, name: str) -> bool:
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
                % (name, layer.line, layer.name,
                   "/".join("%g" % c for c in columns[:4]) + ("…" if len(columns) > 4 else ""),
                   layers[0].name,
                   "/".join("%g" % c for c in reference[:4]) + ("…" if len(reference) > 4 else ""))
            )
            agreed = False
    return agreed


def check_scale(layers: list, findings: list, name: str) -> None:
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
                % (name, layer.line, layer.name, thickness, i, value, value * scale, drift)
            )


def stacked_order(layers: list) -> list:
    """Layers bottom of the stack first, by mean bottom-boundary y (SVG y grows
    downward, so the bottom-most layer has the largest bottom y)."""
    return sorted(
        layers,
        key=lambda layer: -sum(p[1] for p in layer.bottom) / len(layer.bottom),
    )


def check_stack(layers: list, findings: list, name: str) -> None:
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
                % (name, above.line, above.name, abs(gap),
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
            % (name, ordered[0].line, drift, i)
        )


def check_controls(layers: list, findings: list, name: str) -> None:
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
                % (name, layer.line, layer.name, boundary, drift, i)
            )


def layers_named_in(body: str, names) -> set:
    """Which declared layer names the visible text actually prints.

    Longest candidate first at each position, so a layer called "Unit" is
    not reported as appearing inside a sibling called "Unit tests".
    """
    ordered = sorted(names, key=len, reverse=True)
    found = set()
    index = 0
    while index < len(body):
        for candidate in ordered:
            if candidate and body.startswith(candidate, index):
                found.add(candidate)
                index += len(candidate)
                break
        else:
            index += 1
    return found


def check_legend(layers: list, doc: _Scanner, findings: list, name: str) -> None:
    """Every layer in the legend with its total; every total a sum, not a typo."""
    declared = {layer.name: layer for layer in layers}
    entries = {}
    for element in doc.texts:
        attrs = element.attrs
        label = attrs.get("data-layer")
        if label is None:
            continue
        if label not in declared:
            findings.append(
                "%s:%d: a legend entry names layer %r, which no path declares — a "
                "label with no band is not verifiable and reads as data"
                % (name, element.line, label)
            )
            continue
        if label in entries:
            findings.append(
                "%s:%d: a second legend entry for layer %r — one layer, one entry, "
                "or the figure states two totals for one band"
                % (name, element.line, label)
            )
            continue
        entries[label] = (attrs.get("data-total"), plain(element.body), element.line)

    for layer in layers:
        entry = entries.get(layer.name)
        if entry is None:
            findings.append(
                "%s:%d: layer %r has no legend entry (a <text> with data-layer and "
                "data-total) — a streamgraph names every layer and prints its "
                "total, or a band can be dropped from the reading silently"
                % (name, layer.line, layer.name)
            )
            continue
        declared_total, body, line = entry
        total = number(declared_total)
        if total is None:
            findings.append(
                "%s:%d: the legend entry for %r has no readable data-total — the "
                "printed total must be bound to the number it claims to state"
                % (name, line, layer.name)
            )
            continue
        expected = sum(layer.values)
        if abs(total - expected) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: layer %r declares a total of %g but its values sum to %g — "
                "the total is a sum, not a typed number"
                % (name, line, layer.name, total, expected)
            )
        shown, reason = printed_number(body)
        if shown is None:
            findings.append(
                "%s:%d: the legend entry for %r %s (%r) — print exactly one "
                "complete total per entry, and keep digits out of layer names"
                % (name, line, layer.name, reason, body[:28])
            )
        elif abs(shown - total) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: the legend entry for %r prints %r but declares %g — the "
                "label and the binding must state one number"
                % (name, line, layer.name, body[:28], total)
            )

        # The number is bound; the NAME must be bound too. An entry reading
        # "Unit · 688 min" above data-layer="End-to-end" with End-to-end's
        # real total satisfies every check above and still hands the reader
        # the wrong band. A hidden datum being right is not the figure being
        # right - the visible string is what anyone actually reads.
        printed = layers_named_in(body, declared)
        if layer.name not in printed:
            findings.append(
                "%s:%d: the legend entry for %r prints %r, which does not name "
                "that layer — bind the visible name as well as the number, or "
                "an entry can label the wrong band while its data-layer and its "
                "total stay right"
                % (name, line, layer.name, body[:28])
            )
        elif printed - {layer.name}:
            findings.append(
                "%s:%d: the legend entry for %r also prints %s — one entry names "
                "one band, or the reader cannot tell which band it labels"
                % (name, line, layer.name,
                   ", ".join(repr(other)
                             for other in sorted(printed - {layer.name})))
            )


def check_captions(layers: list, doc: _Scanner, findings: list, name: str) -> None:
    """Each period caption must sit on its own column and read its binding."""
    columns = [p[0] for p in layers[0].top]
    count = len(columns)
    seen = {}
    for element in doc.texts:
        attrs = element.attrs
        if "data-index" not in attrs and "data-period" not in attrs:
            continue
        index_raw = attrs.get("data-index")
        period = attrs.get("data-period")
        line = element.line
        if index_raw is None or period is None:
            findings.append(
                "%s:%d: a period caption must carry both data-index (its column) "
                "and data-period (its text) — half a binding can still be swapped"
                % (name, line)
            )
            continue
        index = number(index_raw)
        if index is None or index != int(index) or not 0 <= int(index) < count:
            findings.append(
                "%s:%d: a period caption declares data-index=%r, which is not a "
                "column of this figure (0–%d)"
                % (name, line, index_raw, count - 1)
            )
            continue
        index = int(index)
        if index in seen:
            findings.append(
                "%s:%d: a second caption for period %d — one column, one caption"
                % (name, line, index)
            )
            continue
        seen[index] = (number(attrs.get("x")), period, plain(element.body), line)

    for index in range(count):
        if index not in seen:
            findings.append(
                "%s: no caption for period %d (data-index=%r) — every bucket is "
                "named, or the reader cannot place the pinch this figure keeps"
                % (name, index, index)
            )
            continue
        x, period, body, line = seen[index]
        expected = columns[index]
        if x is None or abs(x - expected) > CAPTION_TOLERANCE:
            findings.append(
                "%s:%d: the caption for period %d (%r) is drawn at x=%s but its "
                "column is at x=%g — a caption off its column renames the bucket"
                % (name, line, index, body[:16],
                   "%g" % x if x is not None else "?", expected)
            )
        if body != period:
            findings.append(
                "%s:%d: the caption for period %d reads %r but declares "
                "data-period=%r — the visible text and its binding must agree"
                % (name, line, index, body[:16], period)
            )


# === DRIVER ==================================================================


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    findings: list = []
    doc = parse_document(raw)
    if doc.error is not None:
        findings.append(
            "%s: presents as a streamgraph but could not be parsed as HTML (%s) — "
            "refusing to report OK on a file this checker could not read"
            % (path.name, doc.error)
        )
        return findings
    layers = parse_layers(doc, findings, path.name)

    if len(layers) < 2:
        findings.append(
            "%s: presents as a streamgraph but declares %d verifiable layer(s) — "
            "every band needs data-layer with data-values and an absolute M/C/L/Z "
            "path. Refusing to report OK on a file this checker could not read"
            % (path.name, len(layers))
        )
        return findings

    check_transforms(doc, findings, path.name)
    if check_columns(layers, findings, path.name):
        check_scale(layers, findings, path.name)
        check_stack(layers, findings, path.name)
        check_controls(layers, findings, path.name)
        check_captions(layers, doc, findings, path.name)
    check_legend(layers, doc, findings, path.name)
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
