#!/usr/bin/env python3
"""Verify the invariants a sankey can silently break.

A sankey's claim is that **ribbon width is volume and volume is conserved**.
Every way of breaking that claim renders perfectly. Nothing errors, nothing
disappears, and no existing gate would notice: `lint-skin.py` reads colors,
fonts and the a11y contract; `verify-geometry.py` reads label masks against
later-painted nodes. Neither compares a ribbon against the number printed
beside it, and neither adds up what enters a node against what leaves it.

Five checks, in the order a defect is likely to reach review:

1. CONSERVATION - what enters a node must leave it. This is the check the type
   exists for. A ribbon quietly narrowed between two stages is invisible: the
   eye has no reference width to compare against, so 5,200 minutes arriving and
   4,800 departing looks exactly like 5,200 arriving and 5,200 departing. Volume
   that genuinely leaves the story must be drawn as a named node in the final
   column, not allowed to evaporate mid-diagram.

2. COLUMN TOTALS - every stage must carry the same total. This is conservation
   read the other way, and it is what catches a whole node being forgotten
   rather than a single ribbon being wrong.

3. RIBBON WIDTH CONSTANCY - a ribbon must be the same width at both ends. A
   ribbon that widens as it travels invents volume out of nothing; one that
   narrows destroys it. Because the two ends are hundreds of pixels apart, a
   taper of several pixels reads as perspective rather than as an error.

4. VALUE FIDELITY - a node's drawn height must match the value printed beside
   it, on one scale shared by every node in the figure. Checked as RELATIVE
   error, for the reason the treemap checker gives: an absolute threshold
   passes exactly the small nodes most likely to be wrong.

5. CONTROL-POINT PLACEMENT - both Bezier controls belong on the corridor
   midline, each at the y of the edge it steers. B'(1) = 3(P3 - P2), so the
   arrival tangent is set by the last control alone: on the midline it is
   exactly horizontal and the ribbon plugs into its bar flat. On the target's x
   the control coincides with the endpoint, the first derivative vanishes, and
   the eye reads B''(1) instead - steeply off horizontal, so every ribbon
   visibly skews into its bar. Every endpoint is still correct, so nothing
   else here would catch it.

`--all` adds two more. The light, dark and full-editorial variants must be
geometrically identical - they are one figure in three skins, and three
hand-maintained copies only stay in agreement if something checks. And any
```svg element pattern in `references/type-sankey.md` must be a literal excerpt
of the shipped example: a code sample is the one piece of geometry nothing
renders, so it rots in silence the first time the layout moves, and it is
exactly what the next contributor copies. The shipped reference carries no such
sample today; the gate binds the first one anyone adds. Both checks live here
rather than in a build script, because a generator that is not run proves
nothing.

Guards sit under all of that, because the worst outcome for a checker is not a
missed defect but a clean exit having read nothing. A <path> that does not parse
as a ribbon is reported rather than skipped, and so is a ribbon end that lands on
no node bar, a file whose node bars fall outside the size window, and a figure
with bars but no ribbons - each would otherwise quietly remove a shape from the
sums, or leave every check to pass vacuously. `--all` additionally refuses to run
unless all three shipped variants are present, because a glob that matches
nothing reads no files, finds no faults, and exits 0.

The widest guards run first. Everything here reads raw coordinates, which is
only sound while the markup means what it says - so a file carrying a transform,
a clip path, a mask or a hidden element is REFUSED, not checked. Any one of those
breaks all five invariants above while every number this checker reads stays
correct, and catching them properly would mean reimplementing a browser.

Underneath that sits the stance the rest of the file depends on, and it is worth
stating plainly because it was learned the expensive way. Every guard here began
as a BLOCKLIST, and each was patched three times over: stroke-width but not fill,
geometry but not containers, `0` but not `0%`, `4foo` but not `4cap`. A blocklist
fails OPEN - whatever it was never told about is certified - and an audit of this
file found seventeen constructs it certified as clean, each of which renders a
figure that lies while every number read here stays correct. An `<a
fill-opacity="0">` erases every ribbon under it. `<defs>` holds geometry that
never draws. `systemLanguage` suppresses an element. A nested `<svg>` rescales the
figure. A stylesheet can set `d` outright. A single-quoted attribute is invisible
to a scan built for double quotes.

So `certify_readable` runs before anything else and works from ALLOWLISTS -
elements, attributes, and the CSS properties a rule reaching the figure may set.
It fails CLOSED: a construct this checker has never been taught is a REFUSAL, not
a pass. When SVG or CSS grows something new, the cost of that staleness is a
rejection naming the thing it did not recognise - loud, and one line to fix -
rather than a silent certification of a figure that lies. That asymmetry is the
whole design.

The attribute scan underneath it is a small tokeniser rather than a
`name="value"` shape match, because the shape match was wrong four ways at once,
each of which turned every guard above into a no-op: single-quoted and unquoted
values were not seen at all, a repeated attribute resolved opposite to a browser
(which keeps the FIRST), character references were never decoded, and a `>`
inside a quoted value ended the element early for every pattern built on `[^>]*`.

Declining to certify is the honest answer throughout, and it costs nothing: no
shipped sankey uses any of it.

Pure Python and no browser, like every other gate in this repo.

Usage:
    python3 scripts/verify-sankey.py --all
    python3 scripts/verify-sankey.py skills/diagram-design/assets/example-sankey.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*)>", re.IGNORECASE)
# Every element that can paint, or be inherited from. One list, because splitting
# it - geometry may not carry style/class, containers may not carry the paint
# ATTRIBUTES - left exactly one gap open: a container carrying a style.
STYLED_GEOMETRY_RE = re.compile(r"<(?P<tag>path|rect|svg|g)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
# The two places stroke-width can reach geometry without appearing on it.
STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(?P<css>.*?)</style>", re.IGNORECASE | re.DOTALL)
ANY_ELEMENT_RE = re.compile(r"<(?P<tag>[a-z][\w:.-]*)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
CONTAINER_RE = re.compile(r"<(?P<tag>svg|g)\b(?P<attrs>[^>]*)>", re.IGNORECASE)
# Properties that decide whether a shape renders, and how wide. Any of them can
# reach a ribbon from a stylesheet or an ancestor without appearing on the ribbon
# itself - stroke-width was closed that way already, and fill arrived by exactly
# the same two routes one review later. So the rule is the property set, not the
# property: none of these may be declared anywhere this checker cannot read them.
INDIRECT_PAINT_PROPS = ("stroke-width", "fill", "fill-opacity", "opacity")
# The SVG number grammar, written once and used everywhere a number is read:
# path coordinates, lengths and alphas. It has been written four times in this
# file - once per reviewer - and each copy learned a different part of it. The
# forms that keep getting missed are all legal and all mean what they look
# like: ".75" is 0.75, "+1" is 1, "1.5e-1" is 0.15. A pattern built around the
# spellings the shipped example happens to use rejects a contributor who writes
# the same figure a different way, which is a gate failing at its actual job -
# and worse, a leading-dot coordinate read by "-?\\d+" silently becomes a
# DIFFERENT number rather than no number at all.
SVG_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
NUMBER = SVG_NUMBER

# Alpha can be written five ways and this file got it wrong three times by
# pattern-matching whichever one was in front of it. So: parse the colour's
# STRUCTURE. Legacy rgba(r, g, b, a); modern rgb(r g b / a) with any function
# name; #rgba and #rrggbbaa; the keyword `transparent`; and everything else,
# which is opaque. Anything shaped like a colour but not readable is reported
# rather than assumed either way.
HEX_COLOR_RE = re.compile(r"^#(?P<digits>[0-9a-f]+)$", re.IGNORECASE)
FUNC_COLOR_RE = re.compile(r"^(?P<name>[a-z-]+)\(\s*(?P<args>.*?)\s*\)$", re.IGNORECASE | re.DOTALL)
ALPHA_TOKEN_RE = re.compile(r"^(?P<number>" + SVG_NUMBER + r")(?P<pct>%?)$")
# The SVG number grammar, not the subset this file happens to use. ".75", "+1"
# and "1.5e-1" are all legal and all mean 0.75, 1 and 0.15 - writing a regex
# around the forms in the shipped example rejects a contributor who writes the
# same width a different way, which is a gate failing at its actual job.
LENGTH_RE = re.compile(
    r"^(?P<number>" + SVG_NUMBER + r")\s*(?P<unit>[a-z%]*)$",
    re.IGNORECASE,
)
# Absolute units convert to px exactly (CSS Values 3). Relative ones resolve
# against a font or a viewport this checker never sees, so a number carrying one
# cannot be compared to a pixel threshold at all - say so rather than guess.
PX_PER_UNIT = {
    "": 1.0, "px": 1.0, "pt": 96 / 72, "pc": 16.0,
    "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4, "q": 96 / 101.6,
}
# Whether a dash pattern survives is a different question from what it measures.
# A browser drops `stroke-dasharray` whole if any component is not a valid
# length, and draws a solid line - but where every unit IS valid, the sign of
# the number settles positivity on its own, whatever the unit later resolves
# to. So the dash test needs VALIDITY across the whole CSS length set, not
# resolvability across the absolute subset above: `4em 3em` and `4% 3%` do
# genuinely dash, and `4foo 3foo` renders as the solid line this form is not.
#
# Built from the structure CSS Values 4 gives them rather than hand-listed,
# because hand-listing overshot in both directions inside two review rounds:
# first `4foo` was accepted as a dash, then the correction rejected `4cap`,
# `4lh`, `4dvh`, `4cqw` and eleven other real units. The stems below are the
# spec's own families (§5.1.1 font-relative, §5.1.2 viewport-relative with its
# four viewport-size prefixes, §5.1.3 container-relative, §5.2 absolute).
#
# When CSS adds a unit this list will be stale, and the failure mode of that
# staleness is a REJECTION naming the unit it did not know - loud, and one line
# to fix. That is the right way round for a gate; the other way round is a
# silent pass.
_VIEWPORT_AXES = ("vw", "vh", "vi", "vb", "vmin", "vmax")
CSS_LENGTH_UNITS = frozenset(
    ("", "%")
    + ("cm", "mm", "q", "in", "pc", "pt", "px")                       # absolute
    + ("em", "rem", "ex", "rex", "cap", "rcap",                       # font-relative
       "ch", "rch", "ic", "ric", "lh", "rlh")
    + tuple(prefix + axis                                             # viewport-relative
            for prefix in ("", "s", "l", "d") for axis in _VIEWPORT_AXES)
    + tuple("cq" + axis[1:] for axis in _VIEWPORT_AXES)               # container-relative
)
NUMBER_RE = re.compile(SVG_NUMBER)
# Numbers FIRST, because the alternative is what broke this: scanning for
# [A-Za-z] independently reads the "e" of 5.2e2 as a path command, so a
# conforming ribbon written in exponent form was rejected as unparseable.
# Matching the number before the letter means an exponent is consumed as part
# of the number it belongs to and never offered as a command.
PATH_TOKEN_RE = re.compile(SVG_NUMBER + r"|[A-Za-z]")


def path_tokens(d: str) -> tuple[list, list]:
    """A path's commands and its coordinates, in one pass over the data."""
    commands, numbers = [], []
    for token in PATH_TOKEN_RE.findall(d):
        if token.isalpha():
            commands.append(token.upper())
        else:
            numbers.append(float(token))
    return commands, numbers
# The canonical ribbon: a move, a cubic down one edge, a straight end cap, a
# cubic back along the other edge, close. Anything else in the figure is not a
# ribbon - and a path that does not match is REPORTED rather than skipped,
# because a checker that silently parses nothing is worse than no checker.
RIBBON_COMMANDS = ["M", "C", "L", "C", "Z"]
RIBBON_COORDS = 16
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
# Reading attributes with a `name="value"` shape looked fine and was wrong four
# ways at once, each of which turns EVERY guard below into a no-op without
# touching a coordinate: a single-quoted or unquoted value is simply not seen,
# so style='stroke-width:30' sails past the ban on style; a repeated attribute
# resolves the opposite way from a browser, which keeps the FIRST; a character
# reference is never decoded, so fill="&#110;one" reads as a colour named
# "&#110;one"; and a ">" inside a quoted value ends the element early for any
# pattern built on [^>]*. So this is a small tokeniser rather than a shape
# match, and it is the ONE place markup becomes attributes.
OPEN_TAG_RE = re.compile(
    r"""<(?P<tag>[a-zA-Z][\w:.-]*)(?P<attrs>(?:"[^"]*"|'[^']*'|[^>"'])*)/?>"""
)
ATTRIBUTE_RE = re.compile(
    r"""(?P<name>[^\s=/>]+)\s*(?:=\s*(?P<value>"[^"]*"|'[^']*'|[^\s>]*))?"""
)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def attributes(raw: str) -> dict:
    """One element's attributes, resolved the way a browser resolves them."""
    found: dict = {}
    for m in ATTRIBUTE_RE.finditer(raw):
        name = m.group("name").lower()
        value = m.group("value") or ""
        if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]
        if name not in found:          # a browser keeps the FIRST of a repeat
            found[name] = html.unescape(value)
    return found


def elements(source: str):
    """Every element in document order, with comments blanked first so one can
    neither hide an element nor contribute one that never renders. Offsets are
    preserved, so a finding still points at the right line."""
    blanked = COMMENT_RE.sub(lambda m: " " * len(m.group(0)), source)
    for m in OPEN_TAG_RE.finditer(blanked):
        yield m.group("tag").lower(), attributes(m.group("attrs")), m.start()

TAG_RE = re.compile(r"<[^>]+>")
# The value line is the only label in a node's block that STARTS with a digit:
# the name starts with a letter and the sublabel with an em dash. Anchor on the
# leading number ONLY - requiring a unit word right after it silently stops
# matching the moment the format changes to something like "9,400 - 78%", and a
# value check that attaches to nothing passes everything.
VALUE_RE = re.compile(r"^(?P<num>\d[\d,]*(?:\.\d+)?)(?![\d,.])")

# A node bar is a thin vertical rect inside the plot band. The legend keys are
# 16x8 and the two background rects are the full viewBox, so both fall out on
# width and on the band test.
BAR_MIN_W, BAR_MAX_W = 5.0, 14.0
BAR_MIN_H = 2.0   # a small flow is still a node; swatches fall out on width and band
# The band's floor sits between the lowest plot row (bottom 456 in the shipped
# example) and the legend rule at y=492 — a bar is above it, a swatch below.
BAND_TOP, BAND_BOTTOM = 30.0, 480.0
COLUMN_EPS = 1.5      # x values this close are the same column
EDGE_EPS = 2.0        # a ribbon end this close to a bar edge is attached to it

RIBBON_WIDTH_TOL = 0.5   # px, a ribbon's two ends
NODE_TOL = 0.75          # px, in vs out at one node
COLUMN_TOL = 1.0         # px, stage against stage
SCALE_TOL = 4.0          # %, relative, drawn height vs printed value
CONTROL_TOL = 0.5        # px, a Bezier control against where it must sit
NON_VOLUME_MAX_STROKE = 2.0  # px, the widest a non-ribbon line may be drawn

# Constructs that decouple what renders from what the markup literally says. A
# checker that reads coordinates cannot reason about any of them, so a file
# using one is refused rather than certified. Scoped to sankey files only - other
# types use transforms legitimately, and this checker never sees them.
OPAQUE_CONSTRUCTS = (
    (re.compile(r"\btransform\s*=", re.IGNORECASE), "a transform"),
    (re.compile(r"\bclip-path\s*[=:]", re.IGNORECASE), "a clip path"),
    (re.compile(r"\bmask\s*=", re.IGNORECASE), "a mask"),
    (re.compile(r"\bdisplay\s*[:=]\s*[\"']?\s*none", re.IGNORECASE), "a hidden element"),
    # `collapse` is the second spelling of hidden, and on everything except a
    # table row it means exactly `hidden`. Matching one of the two was the same
    # mistake as matching one spelling of zero.
    (re.compile(r"\bvisibility\s*[:=]\s*[\"']?\s*(?:hidden|collapse)", re.IGNORECASE),
     "a hidden element"),
)
# Self-test at import: a pattern that cannot match is a check that does not
# exist, and it fails open. That has now happened twice - an escaping slip
# turns every \b into a literal backspace, and the first version of this
# guard only looked at the six patterns named at the time, so the seventh
# inherited the bug. So the test is over the SOURCE, not over a list someone
# has to remember to extend.
if chr(8) in Path(__file__).read_text(encoding="utf-8"):
    raise SystemExit(
        "verify-sankey.py contains a literal backspace: a \\b was written "
        "through a shell that ate an escape level, and every pattern using one "
        "has silently stopped matching. Rebuild the pattern with chr(92)."
    )


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


class Bar:
    __slots__ = ("x", "y", "w", "h", "offset", "value", "label", "values", "inflow", "outflow")

    def __init__(self, x: float, y: float, w: float, h: float, offset: int) -> None:
        self.x, self.y, self.w, self.h, self.offset = x, y, w, h, offset
        self.value: float | None = None
        self.label = ""
        self.values: list[tuple[float, str]] = []
        self.inflow = 0.0
        self.outflow = 0.0

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w


class Ribbon:
    __slots__ = ("x0", "y0t", "y0b", "x1", "y1t", "y1b", "controls", "offset")

    def __init__(self, nums: list[float], offset: int) -> None:
        # index:  0   1     2  3    4  5    6  7     8  9    10 11   12 13   14 15
        #      M x0,y0t  C xm,y0t xm,y1t x1,y1t  L x1,y1b  C xm,y1b xm,y0b x0,y0b  Z
        self.x0, self.y0t = nums[0], nums[1]
        self.x1, self.y1t = nums[6], nums[7]
        self.y1b = nums[9]
        self.y0b = nums[15]
        # (control x, control y, the y it must share) for all four handles.
        self.controls = (
            (nums[2], nums[3], nums[1]),    # leaving, top edge
            (nums[4], nums[5], nums[7]),    # arriving, top edge
            (nums[10], nums[11], nums[9]),  # leaving target, bottom edge
            (nums[12], nums[13], nums[15]), # arriving source, bottom edge
        )
        self.offset = offset

    @property
    def source_h(self) -> float:
        return self.y0b - self.y0t

    @property
    def target_h(self) -> float:
        return self.y1b - self.y1t

    @property
    def midline(self) -> float:
        return (self.x0 + self.x1) / 2


def length_px(raw: str | None) -> tuple[float | None, str | None]:
    """A length in px, or a reason it cannot be read.

    The ONE place a length becomes a number, for every attribute that carries
    one: stroke widths, bar widths, bar heights, bar coordinates. There were
    briefly three, each having learned a different part of the job - one knew
    units, one took the numeric part and threw the unit away (so a bar declared
    `8em` measured 8px and every sum below was computed against a bar that is
    not that size), and one demanded bare digits in a fixed attribute order.

    A relative unit is refused rather than guessed. `em` resolves against a font
    and `%` and `vw` against a viewport, none of which this checker sees, so any
    number it produced for them would be invented.
    """
    parsed = LENGTH_RE.match((raw or "").strip())
    if not parsed:
        return None, f"{raw!r} is not a length this checker can read"
    unit = parsed.group("unit").lower()
    if unit not in PX_PER_UNIT:
        return None, (
            f"{raw!r} carries {unit!r}, which resolves against a font or viewport "
            f"this checker never sees"
        )
    return float(parsed.group("number")) * PX_PER_UNIT[unit], None


def stroke_width_px(attrs: dict) -> tuple[float | None, str | None]:
    """Stroke width in px, defaulting to SVG's initial value when absent."""
    raw = attrs.get("stroke-width")
    if raw is None:
        return 1.0, None                      # SVG's initial value
    width, why = length_px(raw)
    return width, (f"stroke-width={why}" if why else None)


def fill_alpha(value: str) -> tuple[float | None, str | None]:
    """Alpha of a CSS colour, or a reason it cannot be read. None means opaque.

    Written once, for every syntax, because writing it per-syntax is how this
    file came to reject `rgb(235 108 54 / 0.16)` while accepting `#eb6c3600`.
    """
    colour = value.strip().lower()
    if not colour:
        return None, None
    if colour in {"none", "transparent"}:
        return 0.0, None

    hexed = HEX_COLOR_RE.match(colour)
    if hexed:
        digits = hexed.group("digits")
        if len(digits) in {3, 6}:
            return None, None                       # no alpha channel: opaque
        if len(digits) == 4:
            return int(digits[3] * 2, 16) / 255, None
        if len(digits) == 8:
            return int(digits[6:], 16) / 255, None
        return None, f"{value!r} is not a 3, 4, 6 or 8 digit hex colour"

    func = FUNC_COLOR_RE.match(colour)
    if not func:
        return None, None                           # a named colour: opaque

    args = func.group("args")
    token = None
    if "/" in args:                                 # modern: fn(a b c / alpha)
        token = args.split("/", 1)[1].strip()
    else:
        parts = [a.strip() for a in args.split(",")]
        if len(parts) == 4:                         # legacy: fn(a, b, c, alpha)
            token = parts[3]
        elif len(parts) != 1 and len(parts) != 3:
            return None, f"{value!r} has {len(parts)} components"
    if token is None:
        return None, None                           # no alpha given: opaque

    alpha, why = alpha_value(token)
    if why:
        return None, f"{value!r} has an alpha this checker cannot read"
    return alpha, None


def alpha_value(raw: str) -> tuple[float | None, str | None]:
    """A CSS <alpha-value> as the browser resolves it, or a reason it cannot be.

    The ONE place an alpha becomes a number, because there were three and each
    had learned a different half of the grammar. Two rules, and both are what
    the browser does rather than what the text says:

    - a percentage is the number over 100, so `50%` and `0.5` are one value;
    - the result is CLAMPED to [0, 1]. This is the half that bites. `-0.5`
      renders as 0 - fully transparent - so a ribbon painted that way is a gap
      in the flow while its authored text still reads as a colour with an
      alpha. Taking -0.5 to mean "not zero, therefore visible" certifies a
      figure with a hole in it. Above 1 clamps to 1 and is merely redundant.
    """
    parsed = ALPHA_TOKEN_RE.match(raw.strip())
    if not parsed:
        return None, f"{raw!r} is not a number this checker can read"
    alpha = float(parsed.group("number"))
    if parsed.group("pct"):
        alpha /= 100
    return max(0.0, min(1.0, alpha)), None


def paints_a_fill(attrs: dict) -> tuple[bool | None, str | None]:
    """Whether a shape paints its interior, or a reason that cannot be decided.

    A ribbon carries its volume in its FILL, so a canonical ribbon that paints
    no fill occupies the arithmetic without occupying the page: conservation
    still balances, every width is still correct, and the reader sees a gap
    where the flow should be. Absent fill is SVG's default black, which paints.

    Returns a reason rather than raising. A malformed value is a defect in the
    diagram and belongs in the findings list; letting it escape as a ValueError
    turns a CI diagnosis into a traceback, which tells the contributor nothing
    about what is wrong with their file.
    """
    alpha, why = fill_alpha(attrs.get("fill", ""))
    if why:
        return None, why
    if alpha == 0:
        return False, None

    raw = attrs.get("fill-opacity", "").strip()
    if raw:
        opacity, why = alpha_value(raw)
        if why:
            return None, f"fill-opacity={raw!r} is not a number"
        if opacity == 0:
            return False, None
    return True, None


def is_dashed(value: str) -> bool:
    """Whether a stroke-dasharray actually produces a dashed line.

    "Non-empty" is not the test. An invalid pattern makes the browser drop the
    property and draw a SOLID line, and so does an all-zero one - so
    `stroke-dasharray="banana"`, `"0"`, `"0 0"`, `"none"` and a negative dash
    all render exactly like no dash at all. Per SVG: every value must be a
    non-negative length, and at least one must be positive.
    """
    tokens = [t for t in re.split(r"[,\s]+", value.strip()) if t]
    if not tokens:
        return False
    lengths = []
    for token in tokens:
        parsed = LENGTH_RE.match(token)
        if not parsed:
            return False
        if parsed.group("unit").lower() not in CSS_LENGTH_UNITS:
            return False              # invalid unit: the whole declaration goes
        length = float(parsed.group("number"))
        if length < 0:
            return False
        lengths.append(length)
    # The list alternates dash, gap, dash, gap; an odd list is repeated once to
    # make it even. So it takes a positive DASH and a positive GAP to draw a
    # dashed line: "4000 0" is a 4000-long dash with nothing between, which is
    # a solid line with extra steps, and "0 4" is a run of nothing at all.
    if len(lengths) % 2:
        lengths = lengths * 2
    dashes, gaps = lengths[0::2], lengths[1::2]
    return any(d > 0 for d in dashes) and any(g > 0 for g in gaps)


def is_non_volume_path(attrs: dict) -> bool:
    """The one non-ribbon path the reference permits: dashed, hairline, unfilled.

    Every clause is load-bearing. Unfilled alone would let a fill="none" path
    with a 40px stroke render as a band and skip every check below, because a
    stroke that wide is exactly what a reader reads as volume. The dash pattern
    is what marks the line as a different kind of relationship rather than a
    thin ribbon, and the width cap keeps it from growing into one.
    """
    if attrs.get("fill", "").strip().lower() != "none":
        return False
    if not is_dashed(attrs.get("stroke-dasharray", "")):
        return False
    width, _ = stroke_width_px(attrs)
    return width is not None and width <= NON_VOLUME_MAX_STROKE


def contained(top: float, bottom: float, bar: Bar) -> bool:
    """Both edges of a ribbon end inside the bar it attaches to.

    Testing only the top edge lets a ribbon start just above the bar's foot and
    run far past it while still counting as attached, which credits the volume
    to the wrong node.
    """
    return bar.y - EDGE_EPS <= top and bottom <= bar.bottom + EDGE_EPS


def parse_bars(source: str) -> list[Bar]:
    """The node bars, read through the same attribute scan as everything else.

    This used to be its own regex requiring bare digits in a fixed attribute
    order, which meant `width="8px"` - a perfectly ordinary SVG length, and one
    `certify_readable` accepts - silently produced no bar at all, and the figure
    was then rejected for having too few. Two parsers for one value is the same
    fault this file has now been fixed for four times, so there is one.

    A bar that paints no fill is not a bar. `paints_a_fill` was already applied
    to ribbons for exactly this reason - a shape that occupies the arithmetic
    without occupying the page - and a node bar lies the same way: conservation
    balances, the stage totals agree, and the reader sees a column that is not
    there.
    """
    bars: list[Bar] = []
    for tag, attrs, offset in elements(source):
        if tag != "rect":
            continue
        painted, _why = paints_a_fill(attrs)
        if painted is False:
            continue                      # invisible: not a bar, and not measured
        box = [length_px(attrs.get(k))[0] for k in ("x", "y", "width", "height")]
        if any(v is None for v in box):
            continue
        x, y, w, h = box
        if not (BAR_MIN_W <= w <= BAR_MAX_W) or h < BAR_MIN_H:
            continue
        if y < BAND_TOP or y + h > BAND_BOTTOM:
            continue
        bars.append(Bar(x, y, w, h, offset))
    return bars


def parse_ribbons(source: str, findings: list[str], name: str) -> list[Ribbon]:
    ribbons: list[Ribbon] = []
    for m in PATH_RE.finditer(source):
        attrs = attributes(m.group("attrs"))
        d = attrs.get("d", "")
        commands, nums = path_tokens(d)
        if commands == RIBBON_COMMANDS and len(nums) == RIBBON_COORDS:
            paints, why = paints_a_fill(attrs)
            if why:
                findings.append(
                    f"{name}:{line_of(source, m.start())}: ribbon {why} — this checker "
                    f"cannot tell whether it renders, and an invisible ribbon still "
                    f"counts in every conservation sum"
                )
                continue
            if not paints:
                findings.append(
                    f"{name}:{line_of(source, m.start())}: ribbon paints no fill "
                    f"(fill={attrs.get('fill', '(absent)')!r}) — it would still be "
                    f"counted in every conservation sum while rendering nothing, so the "
                    f"arithmetic balances over a gap the reader can see. A ribbon "
                    f"carries its volume in its fill"
                )
                continue
            ribbons.append(Ribbon(nums, m.start()))
            continue
        # The reference permits exactly one non-ribbon path: a DASHED, HAIRLINE,
        # unfilled stroke for a relationship that is not a volume. Match that
        # description and nothing wider. "Unfilled" alone is far too loose — a
        # fill="none" path with a 40px stroke renders as a band indistinguishable
        # from a ribbon and would skip every check below. Width is what a reader
        # reads as volume, so the exemption is capped on stroke width and
        # requires the dash pattern that marks it as a different kind of line.
        if is_non_volume_path(attrs):
            continue
        findings.append(
            f"{name}:{line_of(source, m.start())}: <path> is neither a readable ribbon "
            f"(expected M/C/L/C/Z with {RIBBON_COORDS} coordinates; found "
            f"{'/'.join(commands) or 'none'} with {len(nums)}) nor an unfilled path — "
            f"this checker cannot confirm its width is conserved, so it must not ship "
            f"unexamined. A non-volume relationship takes fill=\"none\""
        )
    return ribbons


def attach_values(source: str, bars: list[Bar], findings: list[str], name: str) -> None:
    """Bind each bar to the value line printed in its label block.

    The shipped examples label a node three ways, one per column style: outside
    the figure anchored `end` (value LEFT of the bar), centred in the gutter
    anchored `middle` (value ABOVE the bar), and outside anchored `start`
    (value RIGHT of the bar). Each convention gets its own tight window rather
    than one loose proximity search: nearest-bar binding looks right until a
    node is shorter than its own label block, at which point the value
    belonging to the bar above drifts into the next bar's window and proximity
    hands it to the wrong node - silently, since both then look internally
    consistent. Here a value that fits more than one bar's window is a FINDING,
    not a coin toss.
    """
    for m in TEXT_RE.finditer(source):
        attrs = attributes(m.group("attrs"))
        # Through the same length parser as everything else. This was a bare
        # float() wrapped in `except ValueError: continue`, so a label written
        # <text x="528px"> - legal SVG, rendering in exactly the same place -
        # was silently dropped, and the bar it belonged to lost its printed
        # value from validation while the file still passed.
        x, why_x = length_px(attrs.get("x"))
        y, why_y = length_px(attrs.get("y"))
        if why_x or why_y or x is None or y is None:
            continue          # unreadable coordinates are refused by certify_readable
        body = plain(m.group("body"))
        hit = VALUE_RE.match(body)
        if not hit:
            continue
        anchor = attrs.get("text-anchor", "start")
        if anchor == "end":       # value line LEFT of its bar, outer column
            candidates = [
                bar for bar in bars
                if bar.x - 60 <= x <= bar.x - 2 and bar.y - 4 <= y <= bar.bottom + 20
            ]
        elif anchor == "middle":  # value line ABOVE its bar, in the stage gutter
            candidates = [
                bar for bar in bars
                if abs(x - (bar.x + bar.w / 2)) <= 8 and bar.y - 40 <= y <= bar.y - 2
            ]
        else:                     # value line RIGHT of its bar, outer column
            candidates = [
                bar for bar in bars
                if bar.right + 2 <= x <= bar.right + 60 and bar.y - 4 <= y <= bar.bottom + 20
            ]
        if not candidates:
            continue              # legend copy and annotations may open with a digit
        if len(candidates) > 1:
            findings.append(
                f"{name}:{line_of(source, m.start())}: the value line {body!r} sits "
                f"where it could label {len(candidates)} different node bars — a "
                f"reader has the same ambiguity, so the label must move until it "
                f"belongs to exactly one node"
            )
            continue
        host = candidates[0]
        # Record EVERY value-shaped line that binds, not just the first. Taking
        # the first and moving on lets a second, contradictory number sit in the
        # same block: the checker validates the one it read, and the reader is
        # shown the one it ignored.
        host.values.append((float(hit.group("num").replace(",", "")), body))
        if host.value is None:
            host.value = host.values[0][0]
            host.label = body


# === CERTIFY ONLY WHAT CAN BE READ ==========================================
#
# Every guard above this line is a BLOCKLIST, and each was patched three times:
# stroke-width but not fill, geometry but not containers, `0` but not `0%`,
# `4foo` but not `4cap`. A blocklist fails OPEN - whatever it has not been told
# about is certified - and SVG has far more ways to render differently than any
# list will hold. An audit of this file found seventeen, every one of which the
# checks below certified as clean: `<a fill-opacity="0">` erases every ribbon
# under it, `<defs>` holds geometry that never draws, `systemLanguage` suppresses
# an element, a nested `<svg>` rescales the figure, a stylesheet can set `d`
# outright, and a single-quoted attribute is invisible to a scan built for
# double quotes.
#
# So the sets below are ALLOWLISTS and they fail CLOSED: an element, attribute
# or CSS property this checker was never taught is a REFUSAL, not a pass.
# Staleness then costs a rejection naming the thing it did not know - loud, and
# one line to fix - rather than a silent certification of a figure that lies.
#
# Derived from the three shipped variants, plus the few constructs the type
# reference documents but the shipped example does not happen to use.
ALLOWED_TAGS = frozenset((
    # page chrome
    "html", "head", "meta", "title", "link", "style", "body",
    "div", "h1", "h3", "p", "span",
    # the figure
    "svg", "g", "desc", "defs", "pattern", "circle", "rect", "path", "line", "text",
))
SVG_TAGS = frozenset((
    "svg", "g", "desc", "title", "defs", "pattern", "circle", "rect", "path",
    "line", "text",
))
ALLOWED_ATTRS = frozenset((
    "aria-labelledby", "charset", "class", "content", "cx", "cy", "d", "fill",
    "font-family", "font-size", "font-style", "font-weight", "height", "href", "id", "lang",
    "letter-spacing", "name", "opacity", "patternunits", "r", "rel", "role",
    "rx", "stroke", "stroke-width", "text-anchor", "viewbox", "width",
    "x", "x1", "x2", "xmlns", "y", "y1", "y2",
    # documented in references/type-sankey.md, unused by the shipped example
    "fill-opacity", "stroke-dasharray", "stroke-opacity", "stroke-linecap",
    # Named so the generic "attribute I do not read" message does not fire on
    # top of the two dedicated ones, which say something more useful.
    "style", "transform", "clip-path", "mask", "visibility",
))
# A CSS rule reaches the figure when its selector names an SVG element or matches
# everything. Such a rule may declare only properties that cannot move, resize,
# repaint or hide geometry: the shipped files need `svg { width; min-width;
# display }` and the `*` reset, and nothing else has a reason to.
SVG_SELECTOR_TOKENS = frozenset(
    set(SVG_TAGS) | {"g", "tspan", "use", "image", "polygon", "polyline", "ellipse"}
)
SAFE_ON_SVG_PROPS = frozenset((
    "box-sizing", "margin", "padding", "width", "min-width", "max-width", "display",
))
SELECTOR_TOKEN_RE = re.compile(r"[a-z][\w-]*", re.IGNORECASE)
RULE_RE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
DEFS_BLOCK_RE = re.compile(r"<defs\b[^>]*>(?P<body>.*?)</defs>", re.IGNORECASE | re.DOTALL)
GEOMETRIC_ATTRS = ("x", "y", "width", "height", "x1", "y1", "x2", "y2", "cx", "cy", "r")
LEGEND_SWATCH = (16.0, 8.0)




def certify_readable(name: str, source: str) -> list[str]:
    """Refuse anything this checker cannot read, before it reads anything else.

    An empty result means every construct in the file is one the checks below
    genuinely understand - which is the only condition under which their silence
    is evidence that the figure is honest rather than evidence that it is opaque.
    """
    findings: list[str] = []

    def refuse(offset: int, why: str) -> None:
        findings.append(f"{name}:{line_of(source, offset)}: {why}")

    svg_roots = 0
    for tag, attrs, offset in elements(source):
        if tag not in ALLOWED_TAGS:
            refuse(offset, f"uses <{tag}>, which this checker does not read. An element "
                           f"it cannot read may paint, hide, clone or move a ribbon while "
                           f"every coordinate here stays correct, so refusing is the "
                           f"honest answer — teach it what <{tag}> does before allowing it")
            continue
        for attribute in sorted(attrs):
            if attribute not in ALLOWED_ATTRS:
                refuse(offset, f"<{tag}> carries {attribute!r}, which this checker does "
                               f"not read. Conditional processing, filters, clones and "
                               f"paint servers all arrive as an attribute and all change "
                               f"what renders without changing a number here")
        if tag in SVG_TAGS and ("style" in attrs or "class" in attrs):
            carried = " and ".join(k for k in ("style", "class") if k in attrs)
            refuse(offset, f"<{tag}> carries {carried}, which can set a paint property "
                           f"from outside the attributes this checker reads — and on a "
                           f"container it reaches every ribbon below it. A fill decides "
                           f"whether a shape renders at all, and stroke width is apparent "
                           f"volume: under stroke-width:30 a ribbon draws 30px wider than "
                           f"the fill it is measured by. Paint belongs in attributes on "
                           f"the element it paints, so what renders is what is measured")
        if tag == "svg":
            svg_roots += 1
            if svg_roots > 1:
                refuse(offset, "nests a second <svg>, which establishes a viewport of its "
                               "own — a transform written without the word, rescaling "
                               "every ribbon under it while the coordinates stay as "
                               "authored")
        # Every coordinate and size, read through the one length parser. These
        # used to be read where they were needed - with a bare float() in one
        # place, wrapped in `except ValueError: continue` - so `<text x="528px">`
        # is legal SVG that renders exactly where it says, and the label was
        # silently dropped from validation instead. A value this checker cannot
        # read is a check it is not performing, and the file still passed.
        full_bleed_size = (attrs.get("width", "").strip() == "100%"
                           and attrs.get("height", "").strip() == "100%")
        for geometric in GEOMETRIC_ATTRS:
            raw_value = attrs.get(geometric)
            if raw_value is None:
                continue
            if full_bleed_size and geometric in ("width", "height"):
                continue                          # the paper, sized to its parent
            _value, why_geom = length_px(raw_value)
            if why_geom:
                refuse(offset, f"<{tag}> has {geometric}={raw_value!r}, which this checker "
                               f"cannot resolve: {why_geom}. Every check below is "
                               f"arithmetic on these numbers")

        # A paint value this checker cannot read is refused rather than assumed
        # either way. Assuming it paints counts a shape that may not be there;
        # assuming it does not drops a shape that is. `parse_bars` and
        # `parse_ribbons` below can therefore both treat "not False" as painted,
        # because an undecidable fill never reaches them.
        if tag in SVG_TAGS:
            _painted, why_paint = paints_a_fill(attrs)
            if why_paint:
                refuse(offset, f"<{tag}> has a paint this checker cannot read: {why_paint}")

        # The full-bleed rect is the paper and its texture. It carries no volume
        # and nothing is measured against it, so a pattern fill there is the one
        # place a paint server says nothing about the flow.
        full_bleed = (attrs.get("width", "").strip() == "100%"
                      and attrs.get("height", "").strip() == "100%")
        for paint in (() if full_bleed else ("fill", "stroke")):
            if attrs.get(paint, "").strip().lower().startswith("url("):
                refuse(offset, f"<{tag}> paints its {paint} from a paint server, which can "
                               f"resolve to a fully transparent gradient or to nothing at "
                               f"all. This checker cannot follow the reference, so it "
                               f"cannot say whether the shape reaches the page")
        if tag == "rect":
            raw_w = (attrs.get("width") or "").strip()
            raw_h = (attrs.get("height") or "").strip()
            if raw_w == "100%" and raw_h == "100%":
                continue                                    # the paper, or its texture
            width, why_w = length_px(raw_w)
            height, why_h = length_px(raw_h)
            # y decides WHICH shape a rect may claim to be — a swatch lives in
            # the legend region and a bar in the plot band — so an unreadable y
            # is refused along with an unreadable size. Absent y is SVG's 0.
            y, why_y = length_px((attrs.get("y") or "0").strip() or "0")
            if why_w or why_h or why_y:
                refuse(offset, f"draws a <rect> whose size or position cannot be read: "
                               f"{why_w or why_h or why_y}. A bar height IS the volume it "
                               f"claims, so a value this checker has to guess at is a sum "
                               f"it cannot stand behind")
                continue
            if (width, height) == LEGEND_SWATCH and y is not None and y >= BAND_BOTTOM:
                continue                                    # a legend key, in the legend
            if (width is not None and height is not None and y is not None
                    and BAR_MIN_W <= width <= BAR_MAX_W and height >= BAR_MIN_H
                    and BAND_TOP <= y and y + height <= BAND_BOTTOM):
                continue                                    # a node bar; parse_bars reads it
            refuse(offset, f"draws a <rect> {raw_w or '?'}x{raw_h or '?'} at y={y:g}, "
                           f"which is neither a node bar, a legend swatch, nor the "
                           f"full-bleed paper — a bar lives inside the plot band and a "
                           f"swatch below it. A rect that is none of those is ink laid "
                           f"over the figure, and painted last it covers whatever was "
                           f"just measured")
        if tag == "line":
            width_px, why = stroke_width_px(attrs)
            if why or width_px is None:
                refuse(offset, f"<line> has {why}")
            elif width_px > NON_VOLUME_MAX_STROKE:
                refuse(offset, f"draws a <line> {width_px:g}px wide, which reads as a band "
                               f"of volume. A rule here is a hairline; volume is a ribbon")

    # <defs> is a definitions block: its contents render only where something
    # references them. The shipped files use it for the dot pattern and nothing
    # else, so a ribbon or a node bar parked in there draws nowhere while every
    # sum below still counts it — conservation balancing over a shape that is
    # not on the page.
    for block in DEFS_BLOCK_RE.finditer(source):
        for tag, _, offset in elements(block.group("body")):
            if tag in ("path", "rect", "line"):
                refuse(block.start("body") + offset,
                       f"puts a <{tag}> inside <defs>, where it defines a shape rather "
                       f"than drawing one. Every check below would still count it, so "
                       f"the figure would balance over geometry no reader can see")

    for block in STYLE_BLOCK_RE.finditer(source):
        body = CSS_COMMENT_RE.sub(" ", block.group("css"))
        for rule in RULE_RE.finditer(body):
            selector = rule.group("selector").strip()
            tokens = {t.lower() for t in SELECTOR_TOKEN_RE.findall(selector)}
            if not (tokens & SVG_SELECTOR_TOKENS or "*" in selector):
                continue                                    # page chrome only
            for declaration in rule.group("body").split(";"):
                if ":" not in declaration:
                    continue
                prop = declaration.split(":", 1)[0].strip().lower()
                if prop and prop not in SAFE_ON_SVG_PROPS:
                    refuse(block.start(),
                           f"a stylesheet rule for {selector!r} sets {prop!r}. A rule that "
                           f"reaches the figure may set only "
                           f"{', '.join(sorted(SAFE_ON_SVG_PROPS))} — anything else "
                           f"repaints, resizes, moves or hides geometry from a place no "
                           f"attribute records")
    return findings


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    name = path.name
    findings: list[str] = []

    # Everything below reads raw coordinates out of the markup. That is only
    # sound while the markup means what it says, so refuse the file outright if
    # it uses anything that moves, clips or hides geometry at render time —
    # a transform, a clip, a mask, or a hidden element. Each of those lets every
    # invariant here be broken while the numbers this checker reads stay
    # perfectly correct, and reimplementing SVG rendering to catch that would be
    # reimplementing a browser. Refusing to certify is the honest answer, and it
    # costs nothing: no shipped sankey uses any of them.
    for pattern, what in OPAQUE_CONSTRUCTS:
        hit = pattern.search(source)
        if hit:
            findings.append(
                f"{name}:{line_of(source, hit.start())}: uses {what}, which changes "
                f"what renders without changing the coordinates this checker reads — "
                f"every check below could pass on a figure that draws something else. "
                f"Lay sankey geometry out in absolute coordinates instead"
            )
    # `opacity` belongs with those, but it cannot be a pattern in that table:
    # zero has more spellings than a regex should be asked to hold, and the
    # previous one matched `0` and `0.0` while `.0`, `+0`, `0e5`, `0%` and any
    # negative all sailed past it into a figure with an invisible ribbon still
    # counted as flow. Same lesson as the lengths and the colours, for the
    # third time: parse the value the browser parses, do not match the forms
    # this file happens to use. Any element, because a node bar or a label
    # turned invisible is the same class of lie as a ribbon.
    for m in ANY_ELEMENT_RE.finditer(source):
        raw = attributes(m.group("attrs")).get("opacity")
        if raw is None:
            continue
        opacity, why = alpha_value(raw)
        if why:
            findings.append(
                f"{name}:{line_of(source, m.start())}: <{m.group('tag').lower()}> has "
                f"opacity={raw!r}, which is not a number this checker can read"
            )
        elif opacity == 0:
            findings.append(
                f"{name}:{line_of(source, m.start())}: <{m.group('tag').lower()}> is "
                f"fully transparent (opacity={raw!r}), so it renders as nothing while "
                f"every coordinate this checker reads stays correct — an invisible "
                f"ribbon still balances, and an invisible node bar still measures"
            )
    # And everything the checker has never been taught. This runs after the
    # constructs above so that a transform is reported as a transform, not as an
    # unrecognised attribute, and before everything below because none of it
    # means anything on a file whose markup cannot be read.
    findings.extend(certify_readable(name, source))
    if findings:
        return findings

    # And the same principle stated as an invariant rather than a blocklist,
    # because the indirect routes do not enumerate: a class, a bare element
    # selector, a rule on a container, an inherited attribute, a media query.
    # Patching them one at a time is an infinite ladder. So `stroke-width` may
    # appear ONLY as an attribute on the element it applies to. Declared in a
    # stylesheet or on an <svg>/<g> ancestor it reaches geometry this checker
    # measures without appearing anywhere it reads, and stroke width is
    # apparent volume.
    for block in STYLE_BLOCK_RE.finditer(source):
        for prop in INDIRECT_PAINT_PROPS:
            hit = re.search(rf"(?<![\w-]){re.escape(prop)}\s*:", block.group("css"), re.IGNORECASE)
            if hit:
                findings.append(
                    f"{name}:{line_of(source, block.start('css') + hit.start())}: a "
                    f"stylesheet rule sets {prop}, which reaches ribbons and node bars "
                    f"without appearing on them. Whether a shape renders, and how wide, "
                    f"has to be readable from the shape itself"
                )
    for m in CONTAINER_RE.finditer(source):
        attrs = attributes(m.group("attrs"))
        for prop in INDIRECT_PAINT_PROPS:
            if prop in attrs:
                findings.append(
                    f"{name}:{line_of(source, m.start())}: <{m.group('tag').lower()}> sets "
                    f"{prop}={attrs[prop]!r}, which every descendant inherits — including "
                    f"ribbons this checker measures by their fill. A ribbon with no fill "
                    f"of its own would render whatever this says. Set it per element"
                )
    # Which leaves the direct route: a stroke-width attribute is legitimate — the
    # legend swatches carry a 1px key stroke — but a fat one paints outside the
    # fill this checker measures, so a 30px stroke renders a ribbon 30px wider
    # than the volume it is credited with. A separator is a hairline; anything
    # thicker is being used as width, and width is the encoding.
    for m in STYLED_GEOMETRY_RE.finditer(source):
        attrs = attributes(m.group("attrs"))
        if "stroke-width" not in attrs:
            continue
        width, why = stroke_width_px(attrs)
        if why:
            findings.append(
                f"{name}:{line_of(source, m.start())}: <{m.group('tag').lower()}> {why} — "
                f"and an unread stroke width is an unknown amount of apparent volume"
            )
        elif width is not None and width > NON_VOLUME_MAX_STROKE:
            findings.append(
                f"{name}:{line_of(source, m.start())}: <{m.group('tag').lower()}> has "
                f"stroke-width={attrs['stroke-width']!r} = {width:g}px, which paints "
                f"outside the fill this checker measures — the shape renders wider than "
                f"the volume it is credited with. A separator is a hairline; keep it at "
                f"or under {NON_VOLUME_MAX_STROKE:g}px"
            )
    if findings:
        return findings

    bars = parse_bars(source)
    ribbons = parse_ribbons(source, findings, name)
    # A half-parsed figure is the worst outcome this checker can have: every
    # check below is per-node or per-ribbon, so a file with bars but no ribbons
    # (or the reverse) would pass in silence having verified nothing. Both sides
    # have to be present, and saying so is not the same as saying it is clean.
    if bars or ribbons:
        if len(bars) < 3:
            findings.append(
                f"{name}: found {len(ribbons)} ribbon(s) but only {len(bars)} node bar(s) — "
                f"a node bar is a rect {BAR_MIN_W:g}-{BAR_MAX_W:g}px wide and at least "
                f"{BAR_MIN_H:g}px tall inside the plot band. Nothing here could be checked, "
                f"which is not the same as nothing being wrong"
            )
        if len(ribbons) < 2:
            findings.append(
                f"{name}: found {len(bars)} node bar(s) but only {len(ribbons)} readable "
                f"ribbon(s) — a sankey with no ribbons carries no flow, and every "
                f"conservation check below would pass on it vacuously"
            )
    if len(bars) < 3 or len(ribbons) < 2:
        return findings
    attach_values(source, bars, findings, name)

    # 5. A ribbon must meet its node bars square-on.
    #
    #    For a cubic, B'(1) = 3(P3 - P2): the arrival tangent is set by the last
    #    control point and nothing else. Park both controls on the corridor
    #    midline and that tangent is exactly horizontal, so the ribbon plugs into
    #    the bar flat. Put one on the target's x instead and P2 coincides with
    #    P3, the first derivative vanishes, and the visible approach falls to
    #    B''(1) - measured at 133 degrees off horizontal for a ribbon in this
    #    figure. It renders as a band skewed into its own node, and no other
    #    check here would notice, because the endpoints are still correct.
    for r in ribbons:
        for index, (cx, cy, expected_y) in enumerate(r.controls, 1):
            if abs(cx - r.midline) > CONTROL_TOL:
                findings.append(
                    f"{name}:{line_of(source, r.offset)}: ribbon control point "
                    f"{index} sits at x={cx:g} instead of the corridor midline "
                    f"{r.midline:g} — the arrival tangent degenerates and the "
                    f"ribbon meets its node bar at a slant"
                )
            if abs(cy - expected_y) > CONTROL_TOL:
                findings.append(
                    f"{name}:{line_of(source, r.offset)}: ribbon control point "
                    f"{index} sits at y={cy:g} but its edge ends at {expected_y:g} — "
                    f"an edge whose control leaves its own y bulges away from the "
                    f"width the ribbon claims to carry"
                )

    # 3. A ribbon must not change width along its run.
    for r in ribbons:
        drift = abs(r.source_h - r.target_h)
        if drift > RIBBON_WIDTH_TOL:
            findings.append(
                f"{name}:{line_of(source, r.offset)}: ribbon leaves at "
                f"{r.source_h:.2f}px and arrives at {r.target_h:.2f}px — a "
                f"{drift:.2f}px change in width invents or destroys volume; "
                f"width must be constant along a ribbon"
            )

    # Attach every ribbon end to the bar it touches. An end that lands on no bar
    # is reported rather than dropped: an unattached ribbon is invisible to the
    # conservation sums, so silently skipping it would let the exact defect this
    # checker exists for slip through as a clean run.
    for r in ribbons:
        ends = {"leaves": False, "arrives": False}
        for bar in bars:
            if abs(r.x0 - bar.right) <= EDGE_EPS and contained(r.y0t, r.y0b, bar):
                bar.outflow += r.source_h
                ends["leaves"] = True
            if abs(r.x1 - bar.x) <= EDGE_EPS and contained(r.y1t, r.y1b, bar):
                bar.inflow += r.target_h
                ends["arrives"] = True
        loose = [side for side, hit in ends.items() if not hit]
        if loose:
            findings.append(
                f"{name}:{line_of(source, r.offset)}: ribbon "
                f"({r.x0:g},{r.y0t:g}) → ({r.x1:g},{r.y1t:g}) {' and '.join(loose)} at no "
                f"node bar — a ribbon that touches nothing is counted in no node's "
                f"balance, so it must not ship unattached"
            )

    # 1. Conservation, read at each node.
    for bar in bars:
        who = bar.label or f"{bar.w:g}x{bar.h:g} at {bar.x:g},{bar.y:g}"
        if bar.inflow > 0 and bar.outflow > 0:
            gap = abs(bar.inflow - bar.outflow)
            if gap > NODE_TOL:
                findings.append(
                    f"{name}:{line_of(source, bar.offset)}: node {who!r} takes in "
                    f"{bar.inflow:.2f}px and puts out {bar.outflow:.2f}px — {gap:.2f}px "
                    f"is unaccounted for. Flow that leaves the story needs its own "
                    f"named node in the final column, not a quiet disappearance"
                )
        for side, total in (("inflow", bar.inflow), ("outflow", bar.outflow)):
            if total > 0 and abs(total - bar.h) > NODE_TOL:
                findings.append(
                    f"{name}:{line_of(source, bar.offset)}: node {who!r} is {bar.h:.2f}px "
                    f"tall but its {side} sums to {total:.2f}px — the bar must be exactly "
                    f"as tall as the flow through it"
                )

    # 2. Every stage carries the same total.
    columns: dict[float, float] = {}
    for bar in bars:
        key = next((k for k in columns if abs(k - bar.x) <= COLUMN_EPS), bar.x)
        columns[key] = columns.get(key, 0.0) + bar.h
    if len(columns) >= 2:
        totals = sorted(columns.items())
        reference = totals[0][1]
        for x, total in totals[1:]:
            if abs(total - reference) > COLUMN_TOL:
                findings.append(
                    f"{name}: the stage at x={x:g} carries {total:.2f}px against "
                    f"{reference:.2f}px at x={totals[0][0]:g} — every stage of a sankey "
                    f"shows the same whole, so a stage that drops volume has to say "
                    f"where it went"
                )

    # 4. One scale, printed value to drawn height.
    for bar in bars:
        if len(bar.values) > 1:
            shown = " and ".join(repr(text) for _, text in bar.values[:3])
            findings.append(
                f"{name}:{line_of(source, bar.offset)}: node bar at {bar.x:g},{bar.y:g} "
                f"has more than one value printed beside it — {shown}. Only one can be "
                f"the height this bar draws, and a reader has no way to tell which. A "
                f"sublabel opens with an em dash so it is not read as a second value"
            )
    for bar in bars:
        if not bar.value:
            findings.append(
                f"{name}:{line_of(source, bar.offset)}: node bar at "
                f"{bar.x:g},{bar.y:g} has no readable value beside it — its drawn "
                f"height is then compared against nothing, and the fidelity check "
                f"below silently shrinks to the bars that do parse"
            )
    scaled = [(bar, bar.h / bar.value) for bar in bars if bar.value]
    if len(scaled) >= 3:
        reference = sorted(s for _, s in scaled)[len(scaled) // 2]   # median
        for bar, scale in scaled:
            relative = (scale - reference) / reference * 100
            if abs(relative) > SCALE_TOL:
                findings.append(
                    f"{name}:{line_of(source, bar.offset)}: node {bar.label!r} draws "
                    f"{bar.h:.2f}px for {bar.value:g}, which is {relative:+.1f}% off the "
                    f"scale the rest of the figure uses. Width is the only encoding; "
                    f"resize the node"
                )
    return findings


def geometry(path: Path) -> list[str]:
    """The shape of a figure, stripped of every token that a skin changes."""
    source = path.read_text(encoding="utf-8")
    shape = [
        f"bar {b.x:g} {b.y:g} {b.w:g} {b.h:g}"
        for b in sorted(parse_bars(source), key=lambda b: (b.x, b.y))
    ]
    ribbons = sorted(
        parse_ribbons(source, [], path.name),
        key=lambda r: (r.x0, r.y0t),
    )
    shape += [
        f"ribbon {r.x0:g} {r.y0t:g} {r.y0b:g} {r.x1:g} {r.y1t:g} {r.y1b:g}"
        for r in ribbons
    ]
    return shape


VARIANTS = ("example-sankey.html", "example-sankey-dark.html", "example-sankey-full.html")
REFERENCE_DOC = ROOT / "skills/diagram-design/references/type-sankey.md"
SVG_BLOCK_RE = re.compile(r"```svg\n(?P<body>.*?)```", re.DOTALL)
ELEMENT_RE = re.compile(
    r"<(?P<tag>rect|text|path)\b(?P<rest>[^>]*?)(?:/>|>(?P<body>.*?)</(?P=tag)>)",
    re.DOTALL | re.IGNORECASE,
)
WHITESPACE_RE = re.compile(r"\s+")


def squashed(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def check_reference_excerpt(findings: list[str]) -> None:
    """The type reference's element pattern must be a real excerpt.

    A code sample in a doc is the one piece of geometry nothing renders, so it
    drifts silently the first time the layout moves - and it is precisely what
    a contributor copies when building the next diagram of this type. Requiring
    it to appear verbatim in the shipped example makes the sample as trustworthy
    as the figure it came from.
    """
    if not REFERENCE_DOC.exists():
        findings.append(f"missing type reference: {REFERENCE_DOC.name}")
        return
    light = ASSET_DIR / VARIANTS[0]
    if not light.exists():
        return
    haystack = squashed(light.read_text(encoding="utf-8"))
    for block in SVG_BLOCK_RE.finditer(REFERENCE_DOC.read_text(encoding="utf-8")):
        for element in ELEMENT_RE.finditer(block.group("body")):
            needle = squashed(element.group(0))
            if needle not in haystack:
                findings.append(
                    f"{REFERENCE_DOC.name}: the element pattern shows "
                    f"{needle[:72]!r}, which is not in {VARIANTS[0]} — a sample "
                    f"nothing renders drifts the moment the layout moves, and it "
                    f"is what the next contributor will copy. Paste a real excerpt"
                )


def check_variants(paths: list[Path]) -> list[str]:
    if len(paths) < 2:
        return []
    findings: list[str] = []
    # Compare against the light minimal, not whatever the glob sorted first, so
    # the diagnostic names the canonical file a reader would go and look at.
    base = next((p for p in paths if p.name == VARIANTS[0]), paths[0])
    reference = geometry(base)
    for path in paths:
        if path == base:
            continue
        other = geometry(path)
        if other == reference:
            continue
        extra = [line for line in other if line not in reference]
        missing = [line for line in reference if line not in other]
        detail = (extra + missing)[:3]
        findings.append(
            f"{path.name}: geometry differs from {base.name} "
            f"({len(extra)} added, {len(missing)} missing; e.g. {'; '.join(detail)}) — "
            f"the variants are one figure in three skins, so only tokens may differ. "
            f"Regenerate them from a single model instead of editing each by hand"
        )
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("example-sankey*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify sankey flow conservation, ribbon width and value fidelity."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped sankey example")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    paths = targets(args)
    # A glob that matches nothing is the quietest way for a gate to stop
    # gating: it reads no files, finds no faults, and exits 0. --all knows
    # exactly which three files the type ships, so it can tell the difference
    # between "clean" and "not there".
    if args.all:
        missing = [name for name in VARIANTS if not (ASSET_DIR / name).exists()]
        if missing:
            print(
                f"error: --all expects the three shipped variants in "
                f"{ASSET_DIR.relative_to(ROOT).as_posix()}; missing "
                f"{', '.join(missing)}",
                file=sys.stderr,
            )
            return 2
    elif not paths:
        parser.print_help()
        return 2

    findings: list[str] = []
    for path in paths:
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        findings.extend(check(path))
    if args.all:
        findings.extend(check_variants(paths))
        check_reference_excerpt(findings)

    for finding in findings:
        print(finding)
    if findings:
        print(f"\n{len(findings)} sankey finding(s) across {len(paths)} file(s).")
        return 1
    print(
        f"OK sankey: {len(paths)} file(s), flow conserved at every node, stages carry "
        f"equal totals, ribbons hold their width"
        + (", variants share one geometry" if args.all else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
