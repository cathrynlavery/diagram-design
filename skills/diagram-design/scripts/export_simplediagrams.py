#!/usr/bin/env python3
"""Export a diagram HTML file as an editable SimpleDiagrams document.

    python3 <skill-dir>/scripts/export_simplediagrams.py my-diagram.html
    python3 <skill-dir>/scripts/export_simplediagrams.py my-diagram.html "Flow.simplediagram"

SimpleDiagrams is a diagram editor for macOS whose documents are folder
packages ending in ``.simplediagram``. This writes SimpleDiagrams document
format 19.

The diagram is translated shape by shape into SimpleDiagrams' hand-drawn
style, so it opens as something to keep editing rather than as a picture:

* a box becomes a shape from the built-in Basic library (Square, Rounded
  Rectangle, Pill, Circle, and a labelled or arrowed Diamond, Cylinder and so
  on); any other outline, such as a face of a 3D drawing, keeps its exact form;
* the text on a box becomes its label, and text on a small plain box by an arrow its label;
* a line with an arrowhead, or one joining two boxes, becomes a connector that
  follows the boxes when they move; lanes become one Swimlanes shape;
* icons become pictures, and whatever is drawn on a box is
  grouped with it; every other line and text keeps its exact place.

The work runs in three passes: ``Reader`` turns the SVG into drawn items,
``arrange`` decides what each becomes, and ``Writer`` builds the records.
The SVG comes from ``export_svg.py``, so both exports see the same drawing.

Standard library only, no network access, and the same input always produces
the same bytes. An existing output is never replaced. Content SimpleDiagrams
cannot hold is reported with one ``note:`` line per kind on stderr; exit
status 2 means nothing was written.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import re
import sys
import unicodedata
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from graphlib import TopologicalSorter
from operator import attrgetter
from pathlib import Path
from typing import Any, Literal, NamedTuple, TypeAlias

import export_svg

FORMAT_NAME = "com.simplediagrams.document"
FORMAT_VERSION = 19
SCHEMA_VERSION = FORMAT_VERSION - 1  # document.json always says one less
PACKAGE_SUFFIX = ".simplediagram"
BASIC_LIBRARY = "com.simplediagrams.shapeLibrary.basic"

# Identifiers are derived from the file name and drawing order, never random, so
# re-exporting an unchanged diagram is byte-for-byte identical.
ID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/cathrynlavery/diagram-design#simplediagrams"
)

# Format limits this export can reach (the rest are far beyond any diagram).
MAX_COORDINATE = 1_000_000_000.0
MAX_DIMENSION = 10_000_000.0
MAX_CONNECTION_POINTS = 128
MAX_FONT_FAMILY_BYTES = 256
MAX_NAME_BYTES = 512
# Arranging compares shapes with one another, so stop well before that is slow.
MAX_ITEMS = 5_000
OVERLAP_CHECK_LIMIT = 200  # larger translucent sets conservatively report possible overlap

# How the drawing is read as a diagram. Lengths are in SVG units.
# A line end this close to an outline attaches to it; arrows stop short for the head.
ATTACH_TOLERANCE = 6.0
# A box at least this big inside another is a node that box holds, not a tag on it,
NODE_SIZE = (48.0, 28.0)
# ... as is one taking at least this share of the outer box's area.
NODE_SHARE = 1 / 8
# A box this close to two of another's edges is part of it, such as a header band.
FLUSH_TOLERANCE = 2.0
# Lines of one label have anchors this close, and at most this many font sizes apart.
ALIGN_TOLERANCE = 2.0
LINE_SPACING = 1.9
# A label this close to a box's centre, as a share of its width and height, is centred.
CENTRED_SHARE = (0.1, 0.15)
# An outline matches a Basic shape when no point of either strays further from the
# other than this many points, or this share of the shape's smaller side.
MATCH_TOLERANCE = (1.0, 0.05)
# ... and only a shape filling about the same share of its bounds is compared at all.
MATCH_FILL_SHARE = 0.12
# A curve this short between a line's straight runs is a rounded corner or a hop
# over a crossing line, not part of its route.
ROUNDING_SIZE = 32.0
# SimpleDiagrams' Swimlanes: the thinnest lane and its title band across the top.
MIN_LANE = 28.0
TITLE_BAND = 28.0
# Corner radii that pick a rectangle's shape: a share of the shorter side, or points.
PILL_SHARE = 0.4
ROUNDED_RADIUS = 2.0
# An open path enclosing less than this, in square SVG units, has no fill to show.
MIN_FILLED_AREA = 0.01

# Text is placed without the fonts at hand, so its size is estimated, in font sizes,
# generously: SimpleDiagrams draws a missing font, such as Geist, in the system font.
CHAR_WIDTH, WIDE_CHAR_WIDTH, MONO_CHAR_WIDTH = 0.56, 0.7, 0.64
ASCENT, LINE_HEIGHT = 0.95, 1.25
# Room around a label, as a factor and points, so the editor never wraps a word the
# SVG kept on one line.
TEXT_ROOM = (1.2, 10.0)
# SimpleDiagrams insets a label this far from each side of its shape by default.
LABEL_INSET = 10.0
# An arrow's label box is at most this many times its text's size tall, and its
# edge no further than this from the line.
LABEL_BOX_HEIGHT = 3.0
LABEL_REACH = 12.0

STANDARD_POINTS = ((0, 0.5), (1, 0.5), (0.5, 0), (0.5, 1), (0, 0), (0, 1), (1, 0), (1, 1))

# Containers whose children are never drawn directly, and content with no
# SimpleDiagrams equivalent (counted and reported instead).
NOT_DRAWN = frozenset(
    {"defs", "marker", "pattern", "clipPath", "mask", "symbol", "title", "desc", "style",
     "script", "linearGradient", "radialGradient", "filter", "metadata"}
)  # fmt: skip
UNSUPPORTED = frozenset({"switch"})
CONTAINERS = frozenset({"svg", "g", "a"})
SHOWS_VISIBLE_CHILDREN = frozenset({"text", "use"})  # hidden, they still draw what shows itself

INHERITED = frozenset(
    {"fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap",
     "stroke-linejoin", "stroke-miterlimit", "fill-rule", "fill-opacity", "stroke-opacity",
     "color", "font-family", "font-size", "font-weight", "font-style", "text-anchor",
     "text-align", "text-transform", "text-decoration", "letter-spacing", "visibility",
     "marker-start", "marker-mid", "marker-end", "paint-order", "writing-mode"}
)  # fmt: skip
ICON_PAINT = frozenset(
    {"fill", "stroke", "stroke-width", "stroke-dasharray", "fill-opacity", "stroke-opacity",
     "opacity", "color"}
)  # fmt: skip
ICON_LINE = frozenset(
    {"stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "fill-rule",
     "marker-start", "marker-mid", "marker-end", "paint-order", "vector-effect"}
)  # fmt: skip
ICON_TEXT = frozenset(
    {"font-family", "font-size", "font-style", "font-weight", "letter-spacing", "text-anchor",
     "text-decoration"}
)  # fmt: skip
INDIVIDUAL_TRANSFORMS = frozenset({"translate", "rotate", "scale"})  # CSS-only, never read here
TRANSFORM_FRAME = frozenset({"transform-origin", "transform-box"})  # an icon with one is left out
GRADIENT_STOP = frozenset({"stop-color", "stop-opacity"})
EFFECTS = frozenset({"clip-path", "mask"})  # read only to report them: nothing here clips
PRESENTATION = (
    INHERITED
    | EFFECTS
    | TRANSFORM_FRAME
    | GRADIENT_STOP
    | {"opacity", "display", "transform", "vector-effect", "filter", "mix-blend-mode",
       "overflow"}
)  # fmt: skip
# Sizes and places CSS may set; this export reads them from attributes only, so it notes them.
PLACED_BOX = frozenset({"x", "y", "width", "height"})
GEOMETRY = {
    "rect": PLACED_BOX | {"rx", "ry"},
    "circle": frozenset({"cx", "cy", "r"}),
    "ellipse": frozenset({"cx", "cy", "rx", "ry"}),
    "path": frozenset({"d"}),
    "use": PLACED_BOX,
    "svg": PLACED_BOX,
    "foreignObject": PLACED_BOX,
}
CSS_GEOMETRY = frozenset().union(*GEOMETRY.values())
HTML_BOX_PAINT = frozenset(
    {"background", "background-color", "background-image", "border", "border-top", "border-right",
     "border-bottom", "border-left", "border-style", "box-shadow", "outline", "outline-style"}
)  # fmt: skip
NO_HTML_BOX_PAINT = frozenset({"none", "hidden", "transparent", "initial", "unset", "inherit"})
ZERO_WIDTH = re.compile(r"(?:0+\.?0*|\.0+)(?:px|em|rem)?")  # a border or outline drawing nothing
LINE_PLACEMENT = ("x", "y", "dy")  # a span with one starts a line of its own
ICON_ATTRIBUTES = ICON_PAINT | ICON_LINE | EFFECTS | TRANSFORM_FRAME | GRADIENT_STOP
# The starting value of each property a stored icon writes, which an absent one has.
INITIAL_VALUES = {
    "fill": "black", "stroke": "none", "stroke-width": "1", "stroke-dasharray": "none",
    "fill-opacity": "1", "stroke-opacity": "1", "opacity": "1", "color": "black",
    "stroke-dashoffset": "0", "stroke-linecap": "butt", "stroke-linejoin": "miter",
    "stroke-miterlimit": "4", "fill-rule": "nonzero", "marker-start": "none",
    "marker-mid": "none", "marker-end": "none", "paint-order": "normal", "vector-effect": "none", "clip-path": "none",
    "mask": "none", "stop-color": "black", "stop-opacity": "1", "font-size": "16",
    "font-family": "serif", "font-style": "normal", "font-weight": "400", "letter-spacing": "normal",
    "text-anchor": "start", "text-decoration": "none",
}  # fmt: skip
ICON_HANDLED = ICON_ATTRIBUTES | ICON_TEXT | {"display", "visibility", "transform"}
ICON_DROPPED_ATTRIBUTES = frozenset({"class", "style", "display", "visibility"})
TEXT_STYLE = ("fill", "font-family", "font-size", "font-style", "font-weight", "text-decoration")
NO_PAINT = frozenset({"none", "transparent"})
IMPORTANT = "!important"
# Properties whose values are keywords, read the same in any case.
KEYWORD_VALUED = frozenset(
    {"display", "visibility", "font-style", "font-weight", "text-anchor", "text-transform",
     "text-decoration", "writing-mode", "white-space", "overflow"}
)  # fmt: skip
MAX_VAR_LENGTH = 4096  # characters a var() may expand to; browsers also refuse long ones
MAX_VAR_DEPTH = 64  # nested var()s followed before a value counts as invalid
IMPORTANT_RE = re.compile(r"\s*!\s*important$", re.IGNORECASE)
GENERIC_FONTS = frozenset(
    {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-serif",
     "ui-sans-serif", "ui-monospace", "ui-rounded"}
)  # fmt: skip
NAMED_COLOURS = {  # the CSS basic colours, plus two common extras
    "black": (0, 0, 0), "silver": (192, 192, 192), "gray": (128, 128, 128),
    "grey": (128, 128, 128), "white": (255, 255, 255), "maroon": (128, 0, 0),
    "red": (255, 0, 0), "purple": (128, 0, 128), "fuchsia": (255, 0, 255),
    "green": (0, 128, 0), "lime": (0, 255, 0), "olive": (128, 128, 0),
    "yellow": (255, 255, 0), "navy": (0, 0, 128), "blue": (0, 0, 255),
    "teal": (0, 128, 128), "aqua": (0, 255, 255), "orange": (255, 165, 0),
}  # fmt: skip

Point: TypeAlias = tuple[float, float]
Rect: TypeAlias = tuple[float, float, float, float]  # x, y, width, height
Bounds: TypeAlias = tuple[float, float, float, float]  # left, top, right, bottom
Matrix: TypeAlias = tuple[float, float, float, float, float, float]  # SVG (a b c d e f)
Colour: TypeAlias = tuple[int, int, int, float]  # red, green, blue, alpha
Props: TypeAlias = dict[str, str]
Flips: TypeAlias = tuple[bool, bool]  # horizontal, vertical
Alignment: TypeAlias = Literal["leading", "center", "trailing"]
LinePattern: TypeAlias = Literal["solid", "dashed", "dotted"]
Ending: TypeAlias = Literal[
    "none", "arrow", "solidArrow", "filledArrow", "circle", "solidCircle", "openDiamond", "diamond"
]  # ``solidArrow`` is the format's name for a hollow arrow
Extent: TypeAlias = tuple[float, float, float, float]  # left, top, right, bottom
ItemKind: TypeAlias = Literal["", "box", "connector", "line", "text", "swimlanes", "artwork"]
Record: TypeAlias = dict[str, Any]  # a JSON object as written

TRANSPARENT = "#00000000"


class Note(str, Enum):
    """Every kind of content SimpleDiagrams cannot hold exactly, worded once.

    The helper prints one ``note:`` line per kind it meets, and the guide lists every
    kind in the same words, so the two cannot drift apart (a test compares them).
    ``{element}`` stands for the tag a note is about.
    """

    STYLESHEET_UNREAD = "stylesheet rules this export cannot read left unapplied"
    CSS_TRANSFORM = "CSS transform this export cannot read may misplace a shape"
    CSS_GEOMETRY = "sizes, places and corners set in CSS ignored; the SVG's own are used"
    UNKNOWN_PAINT = "gradient, pattern or unknown colour, left transparent"
    CLIPPED = "clipping and masks left out; shapes are drawn unclipped"
    FILTERED = "filters such as blur and shadow left out"
    BLENDED = "blend modes left out; shapes are drawn over one another plainly"
    SEE_THROUGH_OVERLAP = "see-through groups and outlined shapes drawn part by part; where parts overlap they look darker"
    STROKE_STYLE = "line caps, joins, dash details and uneven stroke scaling drawn in the SimpleDiagrams line style"
    PAINT_ORDER = "outlines the page paints beneath their fill drawn on top of it"
    ELEMENT_LEFT_OUT = "<{element}> left out"
    HIDDEN_CONTENT = "visible content inside a hidden <{element}> left out"
    UNREADABLE_PATH = "<path> with unreadable data left out"
    HOLE = "hole in a filled shape, kept as an outline only"
    COMPLEX_HOLES = "holes in a path with many contours may be filled in"
    CONTOUR_OVERLAP = "overlapping contours may fill areas that were clear"
    SKEWED_CORNERS = "rounded corners of a skewed rectangle drawn square"
    ENDING_COMPOSITE = "line endings made of several marks drawn as one ending"
    ENDING_PAINT_UNREAD = "line endings with paint this export cannot read take the line's colour"
    ENDING_OPACITY = "line endings with different opacity take the line's opacity"
    ENDING_RECOLOURED = "line endings painted another colour take the line's colour"
    ENDING_SHAPE = "line ending other than an arrow, a circle or a diamond drawn as an arrow"
    ENDING_DIRECTION = "arrowhead not pointing away from its line drawn pointing away"
    ENDING_DIRECTION_UNKNOWN = "arrowhead direction this export cannot read drawn pointing away"
    ENDING_DIAMOND_ORIENTATION = "rotated or skewed diamond line endings drawn along the line"
    MID_MARKERS = "markers between a line's ends left out"
    MARKERS_UNDRAWN = "markers on a closed shape or a line with no stroke left out"
    VERTICAL_TEXT = "vertical text drawn horizontally"
    CROSSED_TEXT = "crossed-out and overlined text drawn plain"
    TURNED_LETTERS = "letters turned one by one drawn upright"
    PLACED_LETTERS = "letters placed one by one drawn as one run of text"
    PRESERVED_SPACES = "runs of spaces in text joined into one"
    MOVED_WORDS = "words after hidden words in a line moved into their place"
    LINE_SHIFT = "words moved up or down in a line start a new line"
    WIDE_GAP = "a wide sideways gap inside a line became one space"
    STYLED_WORDS = "styled words inside a line take the line's style"
    OUTLINED_TEXT = "outlined text drawn filled with its outline colour"
    TEXT_OUTLINE = "outlines around filled text left out"
    SEE_THROUGH_WORDS = "see-through words inside a line drawn solid"
    NESTED_LINE = "a line placed inside a span joins that span's line"
    NESTED_GAP = "sideways gaps inside nested spans left out"
    TEXT_DISTORTED = "text skewed, stretched or mirrored drawn plainly"
    TEXT_SIZE = "text sizes beyond 1 to 720 points drawn at the nearest"
    FOREIGN_CONTENT = "<foreignObject> holding more than text left out"
    HTML_BREAKS = "line breaks in HTML text joined into one line"
    HTML_BOX = "HTML box background, border or shadow left out; its text is kept"
    HTML_PADDING = "HTML padding not read; the text sits at its box's edge"
    RICH_HTML = "rich HTML text kept as plain text"
    HTML_LAYOUT = "HTML layout such as flex or grid centring not read; the text sits at the top"
    ICON_VIEWPORT = "unframed icon with viewport-relative lengths left out"
    ICON_UNSAFE = "icon SimpleDiagrams cannot store safely left out"
    USE_OF_NOTHING = "<use> of nothing left out"
    ICON_TEXT_CASE = "letter case set by CSS left unchanged in stored icons"
    ICON_MARKERS = "markers in stored icons may be left out by the desktop renderer"
    ICON_COLOUR = "see-through or unknown icon colour stored as solid"
    ICON_CROPPED = "icon cropped to its box drawn whole"
    ICON_TEXT_BOUNDS = "estimated text bounds in unframed icons may crop letters"
    ICON_TEXT_OFFSETS = "text offsets in stored icons may be left out by the desktop renderer"
    PICTURE_SKEWED = "skewed or empty picture left out"

    def worded(self, element: str = "") -> str:
        """The note as printed, naming ``element`` where it speaks of one."""
        return self.value.format(element=element)


# The effect each undrawn property asks for, and the note that reports its loss.
UNDRAWN_NOTES = {
    "clip-path": Note.CLIPPED,
    "mask": Note.CLIPPED,
    "filter": Note.FILTERED,
    "mix-blend-mode": Note.BLENDED,
}


# --------------------------------------------------------------------------
# Styles: presentation attributes, the carried stylesheet, inline style
# --------------------------------------------------------------------------


class Compound(NamedTuple):
    """One compound selector, such as ``rect.node#main``."""

    tag: str | None
    ids: tuple[str, ...]
    classes: tuple[str, ...]
    attributes: frozenset[str] = frozenset()  # only where an unreadable selector is noted

    root_tests: int = 0

    def matches(self, element: ET.Element, *, is_root: bool) -> bool:
        """Whether the element has this tag, every one of these IDs, classes and attributes."""
        if (self.root_tests and not is_root) or (self.tag is not None and _local(element) != self.tag):
            return False
        if any(element.get("id") != name for name in self.ids):
            return False
        if any(element.get(name) is None for name in self.attributes):
            return False
        classes = set(element.get("class", "").split())
        return all(name in classes for name in self.classes)


@dataclass(frozen=True, slots=True)
class CssRule:
    """One plain stylesheet rule: descendant selectors and their declarations."""

    compounds: tuple[Compound, ...]
    specificity: tuple[int, int, int]
    order: int
    declarations: Props

    def applies(self, element: ET.Element, ancestors: Sequence[ET.Element]) -> bool:
        """Whether the rule selects the element, given its ancestors from the root down."""
        *outer, last = self.compounds
        if not last.matches(element, is_root=not ancestors):
            return False
        for index in range(len(ancestors) - 1, -1, -1):
            if outer and outer[-1].matches(ancestors[index], is_root=index == 0):
                outer.pop()
        return not outer


def _declarations(body: str) -> Props:
    """Split ``a: b; c: d`` into a dict, keeping semicolons inside parentheses.

    A value keeps a normalised ``!important`` ending for the cascade to act on.
    """
    out: Props = {}
    for declaration in export_svg._css_segments(export_svg.strip_css_comments(body), ";"):
        name, colon, value = declaration.partition(":")
        if not colon:
            continue
        name, value = name.strip(), IMPORTANT_RE.sub(IMPORTANT, value.strip())
        name = name if name.startswith("--") else name.lower()
        bare = value.removesuffix(IMPORTANT)
        if not bare and not name.startswith("--"):
            continue
        if name == "font" and not _var_calls(bare) and expand_font_shorthand(bare) is None:
            continue  # a syntactically invalid shorthand never enters the cascade
        if value.endswith(IMPORTANT) or not out.get(name, "").endswith(IMPORTANT):
            out.pop(name, None)  # the cascade reads the last place it was declared
            out[name] = value
    return out


def _compound(text: str) -> Compound | None:
    """Read a compound selector built from a tag or ``*``, IDs and classes; ``None`` for any other."""
    match = re.fullmatch(r"(\*|[A-Za-z][\w-]*)?((?:[.#][\w-]+|:root)*)", text)
    if match is None or not text:
        return None
    parts = re.findall(r"([.#])([\w-]+)", match.group(2))
    return Compound(
        None if match.group(1) == "*" else match.group(1),
        tuple(name for kind, name in parts if kind == "#"),
        tuple(name for kind, name in parts if kind == "."),
        root_tests=match.group(2).count(":root"),
    )


def parse_stylesheet(css: str) -> tuple[list[CssRule], list[CssRule]]:
    """The rules this export applies, in cascade order, and those it cannot apply.

    Applied: rules whose selectors are built from tags, ``*``, classes and IDs joined by
    descendant combinators. Every other rule that sets a presentation property, including
    one inside an ``@layer`` block or nested in another rule, is returned unapplied, with
    the parts it cannot test dropped, so the export notes it wherever it may apply.
    Conditional groups (``@media``, ``@supports``) and ``@keyframes`` are skipped: the export
    draws the page's default view, as the guide states.

    """
    css = export_svg.strip_css_comments(css)
    rules: list[CssRule] = []
    unread: list[CssRule] = []

    def set_aside(selector: str) -> None:
        """Keep a rule this export cannot apply, if it sets anything drawn."""
        loose = _readable_part(selector)
        if loose:
            unread.append(CssRule(loose, (0, 0, 0), len(unread), {}))

    pending = [(rule, False) for rule in reversed(export_svg._css_rule_tree(css))]
    while pending:
        rule, layered = pending.pop()
        prelude = rule.selector
        if rule.statement:
            continue
        if re.match(r"@layer\b", prelude, re.IGNORECASE):
            pending.extend((child, True) for child in reversed(rule.children))
            continue
        if prelude.startswith("@"):
            continue
        declarations = _rule_declarations(rule)
        nested_paint = False
        descendants = list(rule.children)
        while descendants and not nested_paint:
            child = descendants.pop()
            if not child.statement and not child.selector.startswith("@"):
                nested_paint = _affects_drawing(_rule_declarations(child))
                descendants.extend(child.children)
        for selector in export_svg.selector_list_parts(prelude):
            if nested_paint:
                set_aside(selector)  # a nested rule may paint a descendant
            if layered:
                if _affects_drawing(declarations):
                    set_aside(selector)
                continue
            compounds = [_compound(part) for part in selector.split()]
            valid = tuple(c for c in compounds if c is not None)
            if not valid or len(valid) != len(compounds):
                if _affects_drawing(declarations):
                    set_aside(selector)
                continue
            specificity = (
                sum(len(c.ids) for c in valid),
                sum(len(c.classes) + c.root_tests for c in valid),
                sum(c.tag is not None for c in valid),
            )
            rules.append(CssRule(valid, specificity, len(rules), declarations))
    return sorted(rules, key=lambda rule: (rule.specificity, rule.order)), unread


def _affects_drawing(declarations: Props) -> bool:
    """Whether a declaration may affect the drawing, including through a custom property."""
    return bool(
        (PRESENTATION | CSS_GEOMETRY | HTML_BOX_PAINT | INDIVIDUAL_TRANSFORMS | {"font", "marker"})
        & declarations.keys()
    ) or any(
        name.startswith("--") for name in declarations
    )


def _rule_declarations(rule: export_svg._CssRule) -> Props:
    """Read a rule's own declarations, leaving out nested selectors and bodies."""
    segments = []
    cursor = rule.start
    for child in rule.children:
        before = export_svg._css_segments(rule.css[cursor : child.start - 1], ";")
        segments.extend(before[:-1])
        cursor = child.end + 1
    segments.append(rule.css[cursor : rule.end])
    return _declarations(";".join(segments))


def _readable_part(selector: str) -> tuple[Compound, ...] | None:
    """Keep the constraints that can tell whether an unsupported selector may apply.

    Attribute tests keep presence, not values. Drop pseudo-classes and approximate
    combinators, except for interactive states that are outside the default view.
    """
    if re.search(
        r":(hover|focus|focus-within|focus-visible|active|visited|link|target)\b",
        selector,
    ):
        return None
    parts = re.sub(r"\s*[>+~&]\s*", " ", selector).split()
    compounds: list[Compound] = []
    for part in parts:
        without_pseudos = re.sub(r"::?[\w-]+(\([^)]*\))?", "", part)
        names = frozenset(re.findall(r"\[\s*([\w-]+)", without_pseudos))
        plain = re.sub(r"\[[^\]]*\]", "", without_pseudos)
        if compound := _compound(plain or ("*" if names else "")):
            compounds.append(compound._replace(attributes=names))
        else:
            return None
    return tuple(compounds) if compounds else None


# --- Custom properties -------------------------------------------------------

CSS_STRING = r"""(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')"""
VAR_NAME = re.compile(r"\s*(--[\w-]+)")
VAR_TOKEN = re.compile(rf"{CSS_STRING}|(?<![\w-])(?P<var>var\()|(?P<paren>[()])", re.IGNORECASE)


def _var_calls(value: str) -> list[re.Match[str]]:
    """The var() calls outside quoted strings, in source order."""
    return [token for token in VAR_TOKEN.finditer(value) if token.group("var")]


def _closing(text: str, opening: int) -> int | None:
    """The index of the matching closing parenthesis, ignoring quoted strings."""
    depth = 1
    for token in VAR_TOKEN.finditer(text, opening + 1):
        if token.group("var") or token.group("paren") == "(":
            depth += 1
        elif token.group("paren") == ")":
            depth -= 1
            if depth == 0:
                return token.start()
    return None


CustomValue: TypeAlias = Callable[[str], str | None]


def resolve_vars(value: str, custom_value: CustomValue, depth: int = 0) -> str | None:
    """``value`` with each ``var(--name, fallback)`` replaced; ``None`` when it is invalid.

    ``custom_value`` reads a settled custom property, returning ``None`` for an invalid one.
    A ``var()`` takes that value or its fallback, which may hold ``var()`` itself. The
    value is invalid, as in a browser, when a ``var()`` has neither, never closes, or would
    grow the value past ``MAX_VAR_LENGTH`` (properties that each repeat the one before
    could otherwise turn a short stylesheet into an exponentially long string).
    """
    calls = _var_calls(value)
    if not calls:
        return value
    if depth > MAX_VAR_DEPTH:
        return None
    pieces, size, index = [], 0, 0
    for call in calls:
        start = call.start()
        if start < index:
            continue  # a fallback is expanded only when it is used
        if (end := _closing(value, call.end() - 1)) is None:
            return None
        name, *fallbacks = export_svg._css_segments(value[call.end() : end], ",")
        name = name.strip()
        fallback = ",".join(fallbacks).strip() if fallbacks else None
        if not VAR_NAME.fullmatch(name):
            return None
        found = custom_value(name)
        if found is None and fallback is not None:
            found = resolve_vars(fallback, custom_value, depth + 1)
        if found is None:
            return None
        pieces += [value[index:start], found]
        size += start - index + len(found)  # bound the work as the value grows
        if size > MAX_VAR_LENGTH:
            return None
        index = end + 1
    if size + len(value) - index > MAX_VAR_LENGTH:
        return None
    pieces.append(value[index:])
    return "".join(pieces)


def _in_loops(graph: Mapping[str, set[str]]) -> set[str]:
    """The names in a dependency graph that depend, directly or through others, on themselves."""

    # A depth-first pass records finishing order. Walking the reversed edges in
    # reverse finishing order then visits one strongly connected component at a time.
    seen: set[str] = set()
    finished: list[str] = []
    reverse: dict[str, set[str]] = {name: set() for name in graph}
    for name, dependencies in graph.items():
        for dependency in dependencies:
            reverse[dependency].add(name)
        if name in seen:
            continue
        seen.add(name)
        stack = [(name, iter(dependencies))]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is None:
                finished.append(current)
                stack.pop()
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(graph[child])))

    looped: set[str] = set()
    seen.clear()
    for name in reversed(finished):
        if name in seen:
            continue
        component = {name}
        seen.add(name)
        frontier = [name]
        while frontier:
            for parent in reverse[frontier.pop()] - seen:
                component.add(parent)
                seen.add(parent)
                frontier.append(parent)
        if len(component) > 1 or name in graph[name]:
            looped.update(component)
    return looped


def custom_property_lookup(inherited: CustomValue, declared: Props) -> CustomValue:
    """Read custom properties on demand in the scope where they were declared.

    Settle each local value once, after its dependencies. Include fallback references
    when detecting cycles, because CSS invalidates every declaration in such a cycle.
    """
    if not declared:
        return inherited
    settled: dict[str, str | None] = {}

    def value_of(name: str) -> str | None:
        return settled[name] if name in settled else inherited(name)

    def lookup(name: str) -> str | None:
        if name in settled or name not in declared:
            return value_of(name)

        graph: dict[str, set[str]] = {}
        pending = {name}
        while pending:
            current = pending.pop()
            raw = declared[current]
            references = (
                match.group(1)
                for call in _var_calls(raw)
                if (match := VAR_NAME.match(raw, call.end()))
            )
            dependencies = {
                ref for ref in references if ref in declared and ref not in settled
            }
            graph[current] = dependencies
            pending.update(dependencies - graph.keys())

        looped = _in_loops(graph)
        settled.update(dict.fromkeys(looped))
        order = TopologicalSorter({key: graph[key] - looped for key in graph if key not in looped})
        for key in order.static_order():
            value = resolve_vars(declared[key], value_of)
            keyword = value.strip().lower() if value is not None else ""
            if keyword == "initial":
                value = None
            elif keyword in CSS_WIDE_KEYWORDS:
                value = inherited(key)
            settled[key] = value
        return settled[name]

    return lookup


class _ComputedProperties(dict[str, str]):
    """Paint properties and the custom-property scope inherited by descendants."""

    def __init__(self, props: Props, custom_value: CustomValue) -> None:
        super().__init__(props)
        self.custom_value = custom_value


def _custom_value_of(props: Props) -> CustomValue:
    return props.custom_value if isinstance(props, _ComputedProperties) else props.get


# --- The font shorthand and font weights --------------------------------------

FONT_LONGHANDS = ("font-style", "font-weight", "font-size", "font-family")
CSS_WIDE_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})
FONT_SHORTHAND = re.compile(
    r"(?P<prefix>(?:(?:normal|italic|oblique(?:\s+[-+]?[\d.]+(?:deg|rad|grad|turn))?|small-caps"
    r"|bold|bolder|lighter|[1-9]\d{0,2}(?:\.\d+)?|1000|(?:ultra-|extra-|semi-)?(?:condensed"
    r"|expanded))\s+){0,4})"
    r"(?P<size>[\d.]+(?:px|pt|pc|in|cm|mm|q|em|rem|ex|ch|%)|xx-small|x-small|small|medium"
    r"|large|x-large|xx-large|xxx-large|smaller|larger|0)(?:\s*/\s*\S+)?\s+(?P<family>\S.*)",
    re.IGNORECASE,
)


def expand_font_shorthand(value: str) -> Props | None:
    """The longhands ``font: italic 600 13px/1.4 'Geist', sans-serif`` sets, by the CSS
    grammar; ``None`` for a value a browser rejects, which leaves earlier ones in place.

    A CSS-wide keyword such as ``inherit`` sets every longhand to itself. The variant,
    stretch and line height it may also give are not drawn by a SimpleDiagrams label.
    """
    value = value.strip()
    if value.lower() in CSS_WIDE_KEYWORDS:
        return dict.fromkeys(FONT_LONGHANDS, value.lower())
    if (match := FONT_SHORTHAND.fullmatch(value)) is None:
        return None
    prefix = re.sub(
        r"(oblique)\s+[-+]?[\d.]+(?:deg|rad|grad|turn)\b",
        r"\1",
        match.group("prefix").lower(),
    )
    words = prefix.split()
    styles = [word for word in words if word in {"italic", "oblique"}]
    weights = [word for word in words if re.fullmatch(r"bold|bolder|lighter|[\d.]+", word)]
    stretches = [word for word in words if word.endswith(("condensed", "expanded"))]
    if (
        len(words) > 4
        or any(len(slot) > 1 for slot in (styles, weights, stretches))
        or words.count("small-caps") > 1
    ):
        return None
    family = match.group("family").strip()
    if not all(
        re.fullmatch(
            rf"{CSS_STRING}|[-_a-z][\w-]*(?:\s+[-_a-z][\w-]*)*",
            name.strip(),
            re.IGNORECASE,
        )
        and name.strip().lower() not in CSS_WIDE_KEYWORDS
        for name in export_svg._css_segments(family, ",")
    ):
        return None
    return {
        "font-style": styles[0] if styles else "normal",
        "font-weight": weights[0] if weights else "normal",
        "font-size": match.group("size"),
        "font-family": family,
    }


def absolute_weight(value: str, inherited: str) -> str:
    """A ``font-weight`` as a number: keywords by name, ``bolder`` and ``lighter`` by the
    CSS table from the inherited weight, and an unreadable one as the inherited weight."""
    parent = float(inherited) if re.fullmatch(r"[\d.]+", inherited) else 400.0
    word = value.strip().lower()
    if word == "bolder":
        weight = 400 if parent < 350 else 700 if parent < 550 else max(parent, 900)
    elif word == "lighter":
        weight = parent if parent < 100 else 100 if parent < 550 else 400 if parent < 750 else 700
    else:
        named = {"normal": 400.0, "bold": 700.0}.get(word)
        number = float(word) if re.fullmatch(r"\d+(?:\.\d+)?", word) else None
        weight = named or (number if number is not None and 1 <= number <= 1000 else parent)
    return f"{weight:g}"


def settled_font_size(value: str, parent: float) -> float | None:
    """A ``font-size`` in pixels; ``None`` for one this export cannot read, such as
    ``calc()``, which the guide says is drawn at the surrounding size."""
    word = value.strip().lower()
    if word in FONT_SIZE_KEYWORDS:
        return FONT_SIZE_KEYWORDS[word] * (parent if word in RELATIVE_KEYWORDS else 1)
    if not re.fullmatch(rf"{NUMBER}(?:px|pt|pc|in|cm|mm|q|em|rem|ex|ch|%)?", word):
        return None
    return length(word, parent, percent_of=parent, font_size=parent)


# --- The cascade ----------------------------------------------------------------


def _cascaded_declarations(
    element: ET.Element,
    rules: Sequence[CssRule],
    ancestors: Sequence[ET.Element],
    defaults: Props | None = None,
) -> list[tuple[str, str]]:
    """Declarations from lowest to highest priority, including source order."""
    matched = [rule for rule in rules if rule.applies(element, ancestors)]
    sources = [
        defaults or {},
        {k: v for k, v in element.attrib.items() if k in PRESENTATION},
    ]
    sources += [rule.declarations for rule in matched]
    sources.append(_declarations(element.get("style", "")))
    return [
        (name, marked.removesuffix(IMPORTANT).rstrip())
        for important in (False, True)
        for source in sources
        for name, marked in source.items()
        if marked.endswith(IMPORTANT) == important
    ]


def computed_properties(
    element: ET.Element,
    inherited: Props,
    rules: Sequence[CssRule],
    ancestors: Sequence[ET.Element],
    defaults: Props | None = None,
) -> _ComputedProperties:
    """An element's settled style: what it inherits, then a browser's ``defaults``,
    presentation attributes, stylesheet rules and its inline style, in cascade order.

    The order runs twice, because an ``!important`` declaration beats every normal one.
    Custom properties settle on demand when another declaration reads them. A
    value whose ``var()`` cannot settle is invalid where it is used, so it acts as
    ``unset``, as in a browser. CSS-wide keywords resolve last; ``revert`` and, with no
    layers read, ``revert-layer`` fall back to the browser's own value, as ``unset`` does.
    Sizes are settled to pixels and weights to numbers, so callers compare like with like.
    """
    props = {k: v for k, v in inherited.items() if k in INHERITED}
    declared = _cascaded_declarations(element, rules, ancestors, defaults)
    own_custom = {name: value for name, value in declared if name.startswith("--")}
    custom_value = custom_property_lookup(_custom_value_of(inherited), own_custom)
    for name, value in declared:
        if name == "font":
            settled = resolve_vars(value, custom_value)
            longhands = expand_font_shorthand(settled) if settled is not None else None
            if longhands is None and _var_calls(value):  # invalid where used
                longhands = dict.fromkeys(FONT_LONGHANDS, "unset")
            props.update(longhands or {})
        elif name == "marker":  # the shorthand sets all three; a later longhand still wins
            props.update(dict.fromkeys(("marker-start", "marker-mid", "marker-end"), value))
        elif name in PRESENTATION:
            props[name] = value
    for name, value in list(props.items()):
        settled = resolve_vars(value, custom_value)
        if settled is None:  # invalid where used
            settled = "unset"
        keyword = settled.strip().lower()
        if keyword in {"revert", "revert-layer"} and defaults and name in defaults:
            props[name] = defaults[name]
        elif (
            keyword == "inherit"
            or (name == "color" and keyword == "currentcolor")
            or (keyword in CSS_WIDE_KEYWORDS - {"initial"} and name in INHERITED)
        ):
            if name in inherited:
                props[name] = inherited[name]
            else:
                del props[name]
        elif keyword in CSS_WIDE_KEYWORDS:
            del props[name]  # the property's starting value, which an absent one reads as
        else:
            props[name] = keyword if name in KEYWORD_VALUED else settled
    parent_size = length(inherited.get("font-size"), 16.0)  # already settled, in pixels
    if "font-size" in props and props["font-size"] != inherited.get("font-size"):
        size = settled_font_size(props["font-size"], parent_size)
        props["font-size"] = f"{parent_size if size is None else size:g}"
    if "font-weight" in props and props["font-weight"] != inherited.get("font-weight"):
        props["font-weight"] = absolute_weight(
            props["font-weight"], inherited.get("font-weight", "400")
        )
    _settle_stroke_lengths(props)
    return _ComputedProperties(props, custom_value)


def _is_invisible(props: Props) -> bool:
    """Whether ``visibility`` hides an element, though a child of it may still show itself."""
    return props.get("visibility") in ("hidden", "collapse")


def _paint_opacity(props: Props, paint: str) -> float:
    """The fill or stroke opacity, independent of the opacity of the finished element."""
    return _opacity(props.get(f"{paint}-opacity"))


def _opacity(value: str | None) -> float:
    """Clamp each SVG/CSS opacity before multiplying it with other alpha values."""
    return max(0.0, min(1.0, length(value, 1.0, percent_of=1.0)))


def _has_fill(props: Props) -> bool:
    """Whether fill can show, allowing unknown paint to get a loss note."""
    fill = props.get("fill", "black")
    return (
        fill.strip().lower() not in NO_PAINT
        and _paint_opacity(props, "fill") > 0
        and ((colour := parse_colour(fill, props)) is None or colour[3] > 0)
    )


def _visible_html_text(props: Props) -> bool:
    """Whether HTML's text can show, even if its descendants choose other styles."""
    colour = props.get("color", "black")
    return (
        not _is_invisible(props)
        and length(props.get("font-size"), 16.0) > 0
        and colour.lower() != "transparent"
        and ((rgba := parse_colour(colour, props)) is None or rgba[3] > 0)
    )


def _uses_vertical_text(props: Props) -> bool:
    """Whether the author asks to lay glyphs out vertically."""
    return props.get("writing-mode", "").startswith(("vertical", "tb", "sideways"))


def _visible_text(props: Props) -> bool:
    """Whether this run can show any glyphs independently of its children."""
    return (
        not _is_invisible(props)
        and length(props.get("font-size"), 16.0) > 0
        and (_has_fill(props) or _has_line(props))
    )


def _has_line(props: Props) -> bool:
    """Whether an element draws an outline."""
    stroke = props.get("stroke", "none").strip().lower()
    return (
        bool(stroke)
        and stroke not in NO_PAINT
        and _paint_opacity(props, "stroke") > 0
        and length(props.get("stroke-width"), 1.0, percent_of=1.0) > 0
        and ((colour := parse_colour(stroke, props)) is None or colour[3] > 0)
    )


def parse_colour(value: str, props: Props) -> Colour | None:
    """Read a CSS colour; ``None`` when it is not one this export can show."""
    value = value.strip().lower()
    if value == "currentcolor":
        return parse_colour(props.get("color", "black"), {})
    if value.startswith("#"):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(c * 2 for c in digits)
        if len(digits) not in (6, 8) or any(c not in "0123456789abcdef" for c in digits):
            return None
        alpha = int(digits[6:8], 16) / 255 if len(digits) == 8 else 1.0
        return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16), alpha
    if match := re.fullmatch(r"rgba?\(([^)]*)\)", value):
        parts = [part for part in re.split(r"[\s,/]+", match.group(1).strip()) if part]
        try:
            channels = [float(p[:-1]) * 2.55 if p.endswith("%") else float(p) for p in parts[:3]]
            alpha = 1.0
            if len(parts) > 3:
                alpha = float(parts[3][:-1]) / 100 if parts[3].endswith("%") else float(parts[3])
        except ValueError:
            return None
        if len(channels) != 3 or not all(map(math.isfinite, [*channels, alpha])):
            return None
        r, g, b = (max(0, min(255, round(c))) for c in channels)
        return r, g, b, max(0.0, min(1.0, alpha))
    if value in NAMED_COLOURS:
        return (*NAMED_COLOURS[value], 1.0)
    return None


def colour_hex(colour: Colour | None, opacity: float = 1.0) -> str:
    """Format as ``#RRGGBB`` or ``#RRGGBBAA``; ``None`` (no paint) becomes fully transparent."""
    if colour is None:
        return TRANSPARENT
    r, g, b, alpha = colour
    alpha = max(0.0, min(1.0, alpha * opacity))
    if alpha >= 0.999:
        return f"#{r:02X}{g:02X}{b:02X}"
    return f"#{r:02X}{g:02X}{b:02X}{round(alpha * 255):02X}"


ABSOLUTE_UNITS = {
    "pt": 4 / 3,
    "pc": 16.0,
    "in": 96.0,
    "cm": 96 / 2.54,
    "mm": 96 / 25.4,
    "q": 96 / 101.6,
}


def length(
    value: str | None,
    default: float = 0.0,
    *,
    percent_of: float | None = None,
    font_size: float = 16.0,
) -> float:
    """Read an SVG length (the first of a list) in pixels: absolute units, em, rem, ex, ch or %."""
    pattern = r"\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)(px|pt|pc|in|cm|mm|q|rem|em|ex|ch|%)?"
    if (match := re.match(pattern, value or "", re.IGNORECASE)) is None:
        return default
    amount, unit = float(match.group(1)), (match.group(2) or "").lower()
    if unit in ABSOLUTE_UNITS:
        amount *= ABSOLUTE_UNITS[unit]
    elif unit == "em":
        amount *= font_size
    elif unit in ("ex", "ch"):
        amount *= font_size / 2  # the usual measure when the font's own is not known
    elif unit == "rem":
        amount *= 16.0
    elif unit == "%":
        if percent_of is None:
            return default
        amount = amount / 100 * percent_of
    return amount if math.isfinite(amount) else default


# --------------------------------------------------------------------------
# Geometry: transforms and path data
# --------------------------------------------------------------------------

IDENTITY: Matrix = (1, 0, 0, 1, 0, 0)
NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?"
NUMBER_RE = re.compile(NUMBER)
FONT_RELATIVE_LENGTH = re.compile(rf"{NUMBER}(?:rem|em|ex|ch)", re.IGNORECASE)
STROKE_LENGTHS = ("stroke-width", "stroke-dasharray", "stroke-dashoffset")
ICON_GEOMETRY_LENGTHS = frozenset({
    "x", "y", "dx", "dy", "width", "height", "r", "rx", "ry", "cx", "cy", "x1", "y1", "x2", "y2",
})


def _font_lengths_in_pixels(value: str, size: float) -> str:
    """Settle font-relative lengths, preserving other units and list separators."""
    return "".join(
        f"{length(token, font_size=size):g}" if FONT_RELATIVE_LENGTH.fullmatch(token) else token
        for token in re.split(r"([,\s]+)", value)
    )


def _settle_stroke_lengths(props: Props) -> None:
    """Freeze font-relative stroke lengths at the declaring element's font size."""
    size = length(props.get("font-size"), 16.0)
    for name in STROKE_LENGTHS:
        if value := props.get(name):
            props[name] = _font_lengths_in_pixels(value, size)





def multiply(m: Matrix, n: Matrix) -> Matrix:
    """The transform that applies ``n`` first, then ``m``."""
    a, b, c, d, e, f = m
    p, q, r, s, t, u = n
    return (
        a * p + c * q, b * p + d * q, a * r + c * s, b * r + d * s,
        a * t + c * u + e, b * t + d * u + f,
    )  # fmt: skip


def apply(m: Matrix, point: Point) -> Point:
    """Transform a point."""
    x, y = point
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


def _collapses(matrix: Matrix) -> bool:
    """Whether the transform collapses a drawing to a point or a line."""
    return abs(matrix[0] * matrix[3] - matrix[1] * matrix[2]) < 1e-12


def parse_transform(value: str | None) -> Matrix:
    """Read an SVG ``transform`` list; a malformed step is ignored, as browsers do."""
    result = IDENTITY
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", value or ""):
        v = [float(x) for x in NUMBER_RE.findall(args)]
        if not v or not all(map(math.isfinite, v)):
            continue
        step: Matrix
        match name, len(v):
            case "matrix", 6:
                step = (v[0], v[1], v[2], v[3], v[4], v[5])
            case "translate", _:
                step = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
            case "scale", _:
                step = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
            case "rotate", _:
                a = math.radians(v[0])
                step = (math.cos(a), math.sin(a), -math.sin(a), math.cos(a), 0, 0)
                if len(v) == 3:
                    around: Matrix = (1, 0, 0, 1, v[1], v[2])
                    step = multiply(multiply(around, step), (1, 0, 0, 1, -v[1], -v[2]))
            case "skewX", _:
                step = (1, 0, math.tan(math.radians(v[0])), 1, 0, 0)
            case "skewY", _:
                step = (1, math.tan(math.radians(v[0])), 0, 1, 0, 0)
            case _:
                continue
        result = multiply(result, step)
    return result


def decompose(m: Matrix) -> tuple[float, float, float, Flips] | None:
    """Rotation (degrees), the two axis scales and any mirroring, or ``None`` when it skews.

    A mirroring transform is read as the format reads flips: mirrored in the
    frame first, then turned. Either axis can carry the mirror, so the one that
    needs the smaller turn is chosen, which keeps text, never mirrored, upright.
    """
    a, b, c, d = m[:4]
    if abs(a * c + b * d) > 1e-6 * max(1.0, abs(a * d - b * c)):
        return None
    sx, sy = math.hypot(a, b), math.hypot(c, d)
    if sx < 1e-9 or sy < 1e-9:
        return None
    angle = math.degrees(math.atan2(b, a))
    if a * d - b * c >= 0:
        return angle, sx, sy, (False, False)
    across = math.degrees(math.atan2(-b, -a))  # the turn when the left-right mirror is used
    if abs(across) < abs(angle) - 1e-9:
        return across, sx, sy, (True, False)
    return angle, sx, sy, (False, True)


def placed_frame(local: Rect, m: Matrix) -> tuple[Rect, float] | None:
    """A frame drawn through a transform, as an unrotated frame and its rotation.

    ``None`` when the transform skews, since a skewed frame is no longer a frame.
    A mirroring transform's flips come from ``decompose``; only artwork stores them,
    since the rectangles and ellipses placed this way look the same mirrored.
    """
    if (turn := decompose(m)) is None:
        return None
    x, y, w, h = local
    cx, cy = apply(m, (x + w / 2, y + h / 2))
    w, h = w * turn[1], h * turn[2]
    return (cx - w / 2, cy - h / 2, w, h), round(turn[0], 4) % 360


def fit_view_box(viewport: Rect, view: Rect, setting: str | None) -> tuple[Rect, bool]:
    """Where a view box draws in its viewport, as ``preserveAspectRatio`` places it.

    Also says whether the browser crops the drawing to the viewport (``slice``), which an
    artwork frame cannot do: the artwork is stretched to its frame, never cropped.
    """
    words = (setting or "").replace("defer", "").split()
    align = words[0] if words else "xMidYMid"
    if align == "none":
        return viewport, False
    cropped = len(words) > 1 and words[1] == "slice"
    x, y, w, h = viewport
    scale = (max if cropped else min)(w / view[2], h / view[3])
    width, height = view[2] * scale, view[3] * scale
    across = {"xMin": 0.0, "xMax": 1.0}.get(align[:4], 0.5)
    down = {"YMin": 0.0, "YMax": 1.0}.get(align[4:], 0.5)
    return (x + (w - width) * across, y + (h - height) * down, width, height), cropped


class Line(NamedTuple):
    """A straight segment to ``end``."""

    end: Point


class Quad(NamedTuple):
    """A quadratic Bézier segment."""

    control: Point
    end: Point


class Cubic(NamedTuple):
    """A cubic Bézier segment."""

    control1: Point
    control2: Point
    end: Point


Segment: TypeAlias = Line | Quad | Cubic


def bezier(start: Point, segment: Segment, t: float) -> Point:
    """The point at ``t`` along a segment, by de Casteljau's construction."""
    controls: list[Point] = [start, *segment]
    while len(controls) > 1:
        controls = [
            ((1 - t) * p[0] + t * q[0], (1 - t) * p[1] + t * q[1])
            for p, q in itertools.pairwise(controls)
        ]
    return controls[0]


@dataclass(slots=True)
class Subpath:
    """One continuous run of path segments, in absolute coordinates."""

    start: Point
    segments: list[Segment] = field(default_factory=list)
    closed: bool = False

    def transformed(self, m: Matrix) -> Subpath:
        """The same subpath with every point transformed."""
        segments = [type(s)(*(apply(m, point) for point in s)) for s in self.segments]
        return Subpath(apply(m, self.start), segments, self.closed)

    def flattened(self, steps: int = 8) -> list[Point]:
        """The outline as straight pieces, for hit testing, matching and bounds."""
        points, current = [self.start], self.start
        for segment in self.segments:
            if isinstance(segment, Line):
                points.append(segment.end)
            else:
                points += [bezier(current, segment, i / steps) for i in range(1, steps + 1)]
            current = segment.end
        return points


def _arc_segments(
    start: Point, rx: float, ry: float, phi_degrees: float, large: bool, sweep: bool, end: Point
) -> list[Segment]:
    """Convert an elliptical arc to cubic segments (SVG implementation notes, F.6.5)."""
    if start == end:
        return []
    if rx == 0 or ry == 0:
        return [Line(end)]
    phi = math.radians(phi_degrees)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (start[0] - end[0]) / 2, (start[1] - end[1]) / 2
    x1, y1 = cos_phi * dx + sin_phi * dy, -sin_phi * dx + cos_phi * dy
    rx, ry = abs(rx), abs(ry)
    # The half chord measured in radii, with no squared radius that tiny radii could underflow.
    u, v = x1 / rx, y1 / ry
    reach = math.hypot(u, v)
    if not 0 < reach < math.inf:
        return [Line(end)]
    if reach > 1:  # radii too small to reach the end grow until they just do
        rx, ry, u, v, reach = rx * reach, ry * reach, u / reach, v / reach, 1.0
    root = math.sqrt(max(0.0, 1 / (reach * reach) - 1))
    root = -root if large == sweep else root
    cx1, cy1 = root * rx * v, -root * ry * u
    cx = cos_phi * cx1 - sin_phi * cy1 + (start[0] + end[0]) / 2
    cy = sin_phi * cx1 + cos_phi * cy1 + (start[1] + end[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        """The signed angle from one vector to another."""
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    # The start and end as seen from the centre, in radii: (x1 - cx1) / rx and so on.
    theta = angle(1, 0, u - root * v, v + root * u)
    delta = angle(u - root * v, v + root * u, -u - root * v, -v + root * u)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    pieces = max(1, math.ceil(abs(delta) / (math.pi / 2)))
    step = delta / pieces
    k = 4 / 3 * math.tan(step / 4)

    def on_ellipse(t: float) -> tuple[Point, Point]:
        """The point and tangent at parameter ``t``."""
        cos_t, sin_t = math.cos(t), math.sin(t)
        point = (
            cx + rx * cos_t * cos_phi - ry * sin_t * sin_phi,
            cy + rx * cos_t * sin_phi + ry * sin_t * cos_phi,
        )
        tangent = (
            -rx * sin_t * cos_phi - ry * cos_t * sin_phi,
            -rx * sin_t * sin_phi + ry * cos_t * cos_phi,
        )
        return point, tangent

    segments: list[Segment] = []
    for index in range(pieces):
        (p0, d0), (p1, d1) = (
            on_ellipse(theta + index * step),
            on_ellipse(theta + (index + 1) * step),
        )
        c1 = (p0[0] + k * d0[0], p0[1] + k * d0[1])
        c2 = (p1[0] - k * d1[0], p1[1] - k * d1[1])
        segments.append(Cubic(c1, c2, p1))
    segments[-1] = segments[-1]._replace(end=end)  # land exactly on the end point
    return segments


PATH_COMMAND_RE = re.compile(r"[\s,]*([MmLlHhVvCcSsQqTtAaZz])")
PATH_NUMBER_RE = re.compile(r"[\s,]*(" + NUMBER + ")")
PATH_FLAG_RE = re.compile(r"[\s,]*([01])")  # arc flags may be packed: "a5 5 0 01-1 2"
PATH_END_RE = re.compile(r"[\s,]*\Z")


def parse_path_data(data: str) -> list[Subpath]:
    """Parse SVG path data into absolute subpaths of lines, quadratics and cubics.

    Raises:
        ValueError: The data breaks the SVG path grammar.
    """
    position = 0

    def read(pattern: re.Pattern[str]) -> float:
        """The next number or flag, advancing past it."""
        nonlocal position
        if (match := pattern.match(data, position)) is None:
            raise ValueError("path data ends in the middle of a command")
        position = match.end()
        if not math.isfinite(value := float(match.group(1))):
            raise ValueError("path data holds a number too large to draw")
        return value

    def pair() -> Point:
        """The next coordinate pair."""
        return read(PATH_NUMBER_RE), read(PATH_NUMBER_RE)

    def at(point: Point) -> Point:
        """A point of the current command, made absolute when the command is relative."""
        if command.isupper():
            return point
        return point[0] + current[0], point[1] + current[1]

    subpaths: list[Subpath] = []
    current = start = (0.0, 0.0)
    last_control: Point | None = None  # a C, S, Q or T command's last control point
    command = previous = ""
    while not PATH_END_RE.match(data, position):
        if letter := PATH_COMMAND_RE.match(data, position):
            command, position = letter.group(1), letter.end()
        elif command in ("", "Z", "z"):
            raise ValueError("path data has a number where a command belongs")
        if not subpaths and command not in ("M", "m"):
            raise ValueError("path data must start with a move-to")
        upper = command.upper()
        # S and T mirror the last control point only after a curve of their own kind.
        mirrored = current
        if last_control is not None:
            mirrored = (2 * current[0] - last_control[0], 2 * current[1] - last_control[1])
        follows_cubic, follows_quadratic = previous in ("C", "S"), previous in ("Q", "T")
        previous, last_control = upper, None
        if upper == "Z":
            subpaths[-1].closed = True
            current = start
            continue
        if upper == "M":
            current = start = at(pair())
            subpaths.append(Subpath(start))
            command = "l" if command == "m" else "L"  # further pairs are line-tos
            continue
        if subpaths[-1].closed:
            subpaths.append(Subpath(current))  # drawing resumes after a close
        segments = subpaths[-1].segments
        match upper:
            case "L":
                segments.append(Line(at(pair())))
            case "H":
                segments.append(Line((at((read(PATH_NUMBER_RE), 0))[0], current[1])))
            case "V":
                segments.append(Line((current[0], at((0, read(PATH_NUMBER_RE)))[1])))
            case "C" | "S":
                reflected = mirrored if follows_cubic else current
                first = at(pair()) if upper == "C" else reflected
                second = at(pair())
                segments.append(Cubic(first, second, at(pair())))
                last_control = second
            case "Q" | "T":
                reflected = mirrored if follows_quadratic else current
                control = at(pair()) if upper == "Q" else reflected
                segments.append(Quad(control, at(pair())))
                last_control = control
            case _:  # A
                rx, ry, phi = read(PATH_NUMBER_RE), read(PATH_NUMBER_RE), read(PATH_NUMBER_RE)
                large, sweep = bool(read(PATH_FLAG_RE)), bool(read(PATH_FLAG_RE))
                segments += _arc_segments(current, rx, ry, phi, large, sweep, at(pair()))
        current = segments[-1].end if segments else current
    return [subpath for subpath in subpaths if subpath.segments]


def ellipse_subpath(cx: float, cy: float, rx: float, ry: float) -> Subpath:
    """An ellipse as four cubic segments, starting at its rightmost point."""
    k = 0.5522847498  # the standard cubic approximation of a quarter circle
    return Subpath(
        (cx + rx, cy),
        [
            Cubic((cx + rx, cy + k * ry), (cx + k * rx, cy + ry), (cx, cy + ry)),
            Cubic((cx - k * rx, cy + ry), (cx - rx, cy + k * ry), (cx - rx, cy)),
            Cubic((cx - rx, cy - k * ry), (cx - k * rx, cy - ry), (cx, cy - ry)),
            Cubic((cx + k * rx, cy - ry), (cx + rx, cy - k * ry), (cx + rx, cy)),
        ],
        closed=True,
    )


def rectangle_subpath(frame: Rect, rx: float, ry: float) -> Subpath:
    """The authored rectangle outline, including its clamped elliptical corners."""
    x, y, w, h = frame
    right, bottom = x + w, y + h
    rx, ry = min(rx, w / 2), min(ry, h / 2)
    if rx <= 0 or ry <= 0:
        return Subpath((x, y), [Line((right, y)), Line((right, bottom)), Line((x, bottom))], True)
    corners = (
        ((right - rx, y), (right, y + ry)),
        ((right, bottom - ry), (right - rx, bottom)),
        ((x + rx, bottom), (x, bottom - ry)),
        ((x, y + ry), (x + rx, y)),
    )
    segments: list[Segment] = []
    for start, end in corners:
        segments.append(Line(start))
        segments.extend(_arc_segments(start, rx, ry, 0, False, True, end))
    return Subpath((x + rx, y), segments, True)


def _polyline_points(value: str) -> list[Point]:
    """Finite points of a polygon or polyline, dropping an unmatched final number."""
    values = [float(token) for token in NUMBER_RE.findall(value)]
    return list(zip(values[::2], values[1::2], strict=False)) if all(map(math.isfinite, values)) else []


def bounds(points: Iterable[Point]) -> Bounds:
    """The smallest upright box holding every point."""
    xs, ys = zip(*points, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def edges(polygon: Sequence[Point]) -> Iterator[tuple[Point, Point]]:
    """Each side of a closed polygon, the closing side included."""
    return zip(polygon, [*polygon[1:], polygon[0]], strict=True)


def point_in_polygon(point: Point, polygon: Sequence[Point]) -> bool:
    """Whether a point lies inside a polygon, by the even-odd rule."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in edges(polygon):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def distance_to_outline(point: Point, polygon: Sequence[Point]) -> float:
    """How far a point lies from the nearest side of a closed polygon."""
    best = math.inf
    for (x1, y1), (x2, y2) in edges(polygon):
        dx, dy = x2 - x1, y2 - y1
        span = dx * dx + dy * dy
        t = 0.0 if span == 0 else ((point[0] - x1) * dx + (point[1] - y1) * dy) / span
        t = max(0.0, min(1.0, t))
        best = min(best, math.hypot(point[0] - (x1 + t * dx), point[1] - (y1 + t * dy)))
    return best


def signed_area(polygon: Sequence[Point]) -> float:
    """A closed polygon's area, positive one way round and negative the other."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges(polygon)) / 2


def painted_area(polygon: Sequence[Point]) -> float:
    """Roughly how much a polygon paints, even where it crosses itself and its signed area
    cancels out; zero only when every point lies on one line."""
    first = polygon[0] if polygon else (0.0, 0.0)
    return sum(abs(signed_area((first, b, c))) for b, c in itertools.pairwise(polygon[1:]))


def enclosed_area(polygon: Sequence[Point]) -> float:
    """The area a closed polygon encloses (the shoelace formula)."""
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in edges(polygon))) / 2


def densified(polygon: Sequence[Point], pieces: int = 6) -> list[Point]:
    """The polygon with points added along each side, so matching sees whole sides."""
    return [
        (a[0] + (b[0] - a[0]) * i / pieces, a[1] + (b[1] - a[1]) * i / pieces)
        for a, b in edges(polygon)
        for i in range(pieces)
    ]


def path_frame(subpath: Subpath, line_width: float) -> Rect:
    """The frame a path is written with: its bounds grown by half the line, never empty."""
    left, top, right, bottom = bounds(subpath.flattened())
    minimum = max(line_width, 1.0)
    width = max(right - left + line_width, minimum)
    height = max(bottom - top + line_width, minimum)
    return (left + right - width) / 2, (top + bottom - height) / 2, width, height


# --------------------------------------------------------------------------
# Recognising SimpleDiagrams' Basic shapes
# --------------------------------------------------------------------------


def _cylinder_outline(cap: float = 0.21, steps: int = 12) -> tuple[Point, ...]:
    """A cylinder's silhouette: half an ellipse over the top, half under the bottom."""
    turns = [math.pi * i / steps for i in range(steps + 1)]
    top = [(0.5 - 0.5 * math.cos(t), cap - cap * math.sin(t)) for t in turns]
    bottom = [(0.5 + 0.5 * math.cos(t), 1 - cap + cap * math.sin(t)) for t in turns]
    return (*top, *bottom)


# Outlines of the Basic shapes an SVG outline can become, as fractions of the frame,
# measured from the library's artwork with its hand-drawn wobble taken out.
# Rectangles and circles are chosen by element instead.
BASIC_OUTLINES: dict[str, tuple[Point, ...]] = {
    "Diamond": ((0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)),
    "Triangle": ((0.5, 0), (1, 1), (0, 1)),
    "Trapezoid": ((0.24, 0), (0.76, 0), (1, 1), (0, 1)),
    "parallelogram": ((0.2, 0), (1, 0), (0.8, 1), (0, 1)),
    "pentagon": ((0.5, 0), (1, 0.39), (0.8, 1), (0.2, 1), (0, 0.39)),
    "hexagon": ((0.25, 0), (0.75, 0), (1, 0.5), (0.75, 1), (0.25, 1), (0, 0.5)),
    "Octagon": ((0.3, 0), (0.7, 0), (1, 0.3), (1, 0.7), (0.7, 1), (0.3, 1), (0, 0.7), (0, 0.3)),
    "Chevron": ((0, 0), (0.52, 0), (1, 0.5), (0.52, 1), (0, 1), (0.47, 0.5)),
    "ProcessStep": ((0, 0), (0.8, 0), (1, 0.5), (0.8, 1), (0, 1)),
    "Document": ((0, 0), (0.66, 0), (1, 0.27), (1, 1), (0, 1)),
    "Cylinder": _cylinder_outline(),
}
FLIP_CHOICES: tuple[Flips, ...] = ((False, False), (True, False), (False, True), (True, True))


def _outline_gap(drawn: Sequence[Point], other: Sequence[Point], tolerance: float) -> float | None:
    """How far ``drawn`` strays from ``other``, or ``None`` once it strays too far."""
    gap = 0.0
    for point in drawn:
        if (distance := distance_to_outline(point, other)) > tolerance:
            return None
        gap = max(gap, distance)
    return gap


def match_basic_shape(outline: Sequence[Point]) -> tuple[str, Flips] | None:
    """The Basic shape that would draw this outline, set in its bounds, if any would."""
    left, top, right, bottom = bounds(outline)
    width, height = right - left, bottom - top
    if min(width, height) < 1:
        return None
    tolerance = max(MATCH_TOLERANCE[0], MATCH_TOLERANCE[1] * min(width, height))
    # How much of its bounds a shape fills rules most shapes out cheaply.
    filled = enclosed_area(outline) / (width * height)
    drawn = densified(outline)
    best: tuple[float, str, Flips] | None = None
    for item_id, reference in BASIC_OUTLINES.items():
        if abs(filled - enclosed_area(reference)) > MATCH_FILL_SHARE:
            continue
        for flip_x, flip_y in FLIP_CHOICES:
            placed = [
                (left + (1 - u if flip_x else u) * width, top + (1 - v if flip_y else v) * height)
                for u, v in reference
            ]
            if (forward := _outline_gap(drawn, placed, tolerance)) is None:
                continue
            if (backward := _outline_gap(densified(placed), outline, tolerance)) is None:
                continue
            if best is None or max(forward, backward) < best[0]:
                best = (max(forward, backward), item_id, (flip_x, flip_y))
    return None if best is None else (best[1], best[2])


def rectangle_shape(width: float, height: float, radius: float) -> str:
    """The Basic shape for a rectangle with corners of the given radius."""
    if radius >= PILL_SHARE * min(width, height):
        return "pill"
    return "rounded-rectangle" if radius >= ROUNDED_RADIUS else "Square"


# --------------------------------------------------------------------------
# Pictures: icons placed by reference and images embedded in the diagram
# --------------------------------------------------------------------------

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XML_NAMESPACE = "http://www.w3.org/XML/1998/namespace"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
ET.register_namespace("", SVG_NAMESPACE)  # stored artwork is written as plain <svg>
MAX_ASSETS_BYTES = 100 * 1024 * 1024
# An icon this small stays inside every limit SimpleDiagrams sets on elements and text.
MAX_ICON_BYTES = 256 * 1024
MAX_SVG_DEPTH, MAX_SVG_ATTRIBUTES, MAX_XML_NAME_BYTES = 128, 128, 256
MIN_SVG_DIMENSION = 0.000001

# A stored icon must be plainly static: nothing active, nothing loaded from elsewhere, no
# filters and no references to other elements' content. This is stricter than SimpleDiagrams'
# own check, so the app never refuses what is written here.
FORBIDDEN_IN_SVG = frozenset(
    {"a", "animate", "animatecolor", "animatemotion", "animatetransform", "audio", "canvas",
     "discard", "embed", "filter", "foreignobject", "iframe", "image", "object", "script", "set",
     "style", "use", "video"}
)  # fmt: skip
UNSAFE_IN_SVG = re.compile(r"javascript:|vbscript:|data:|file:|https?:|\\", re.IGNORECASE)
LOCAL_REFERENCE = re.compile(r"#[A-Za-z0-9_.:-]{1,256}")
LOCAL_URL = re.compile(r"url\(\s*['\"]?#([^'\")\s]+)", re.IGNORECASE)
SVG_TRANSFORM = re.compile(
    r"[\s,]*(?:(?:matrix|translate|scale|rotate|skewX|skewY)\s*\([-+.\deE\s,]*\)[\s,]*)*"
)
ABSOLUTE_SIZE = re.compile(rf"\s*{NUMBER}(?:px|pt|pc|in|cm|mm)?\s*", re.IGNORECASE)
FONT_SIZE_KEYWORDS = {
    "xx-small": 9.0, "x-small": 10.0, "small": 13.0, "medium": 16.0, "large": 18.0,
    "x-large": 24.0, "xx-large": 32.0, "xxx-large": 48.0, "smaller": 1 / 1.2, "larger": 1.2,
}  # fmt: skip
RELATIVE_KEYWORDS = frozenset({"smaller", "larger"})  # these scale the parent's size
ICON_STRUCTURE = frozenset({"svg", "g", "title", "desc", "metadata", "defs"})  # draw nothing
KNOWN_NAMESPACES = (f"{{{SVG_NAMESPACE}}}", f"{{{XML_NAMESPACE}}}")


class Asset(NamedTuple):
    """SVG artwork stored in the package's ``assets`` folder, named by its SHA-256 digest."""

    data: bytes

    @property
    def id(self) -> str:
        """The asset's identifier: the hex SHA-256 digest of its bytes."""
        return hashlib.sha256(self.data).hexdigest()

    @property
    def filename(self) -> str:
        """The file name inside ``assets``."""
        return f"{self.id}.svg"

    def record(self) -> Record:
        """The asset's entry in ``embedded_assets``."""
        return {
            "id": self.id,
            "kind": "svg_artwork",
            "filename": self.filename,
            "byte_count": len(self.data),
        }


def is_safe_svg(root: ET.Element) -> bool:
    """Whether an icon's SVG is plainly static; anything doubtful is left out with a note."""
    level, depth = [root], 0
    while level:
        level, depth = [child for element in level for child in element], depth + 1
    if depth > MAX_SVG_DEPTH:
        return False
    for element in root.iter():
        if not isinstance(element.tag, str) or len(element.attrib) > MAX_SVG_ATTRIBUTES:
            return False
        tag = _local(element).lower()
        if tag in FORBIDDEN_IN_SVG or tag.startswith("fe"):  # every filter primitive
            return False
        for name in (element.tag, *element.attrib):
            if len(name.encode("utf-8")) > MAX_XML_NAME_BYTES:
                return False
            if name.startswith("{") and not name.startswith(KNOWN_NAMESPACES):
                return False
        for name, value in element.attrib.items():
            local = name.rpartition("}")[2].lower()
            if local.startswith("on") or local in ("base", "href", "src"):
                return False
            if UNSAFE_IN_SVG.search(value) or "var(" in value:
                return False
            if name in ICON_PAINT and not value.strip():  # a token that resolved to nothing
                return False
            if local in TRANSFORM_FRAME:
                return False
            if local == "transform" and not SVG_TRANSFORM.fullmatch(value):
                return False  # percentages and functions an SVG attribute cannot say
            if local == "font-size" and not ABSOLUTE_SIZE.fullmatch(value):
                return False  # relative to the page, which the stored icon does not have
            # SimpleDiagrams reads each url( up to the first ")"; an unclosed one is refused.
            found = re.findall(r"url\(([^)]*)\)", value, re.IGNORECASE)
            if len(found) != value.lower().count("url("):
                return False
            targets = (ref.strip(" \t\n\r\f\v").strip("'\"") for ref in found)
            if not all(LOCAL_REFERENCE.fullmatch(target) for target in targets):
                return False
    return True


def _other_inline_styles(element: ET.Element, page: _ComputedProperties) -> str:
    """An element's inline declarations this export has no attribute for, with tokens resolved."""
    kept = []
    for name, marked in _declarations(element.get("style", "")).items():
        if name in ICON_HANDLED or name.startswith("--"):
            continue
        value = resolve_vars(marked.removesuffix(IMPORTANT).rstrip(), page.custom_value) or ""
        if value.strip() and (name != "font" or not expand_font_shorthand(value)):
            kept.append(f"{name}: {value}")
    return "; ".join(kept)


def _styled_clone(
    element: ET.Element, page: _ComputedProperties, stored: Props
) -> tuple[ET.Element, Props]:
    """An element without its children and with the page's styling written onto it.

    Anything the export understands becomes an attribute, so a stylesheet's ``!important``
    cannot lose to an inline style in the copy. Other inline declarations stay inline.
    Returns the copy and what its children inherit in the stored icon.
    """
    # Any element keeps its font size, which lengths such as width="2em" are measured by.
    written, dropped = ICON_ATTRIBUTES | {"font-size"}, ICON_DROPPED_ATTRIBUTES
    if _local(element) in ("text", "tspan"):
        written |= ICON_TEXT
    if page.get("transform", "").strip() in (
        "",
        "none",
    ):  # nothing for a transform frame to move
        written, dropped = written - TRANSFORM_FRAME, dropped | TRANSFORM_FRAME
    size = length(page.get("font-size"), 16.0)
    kept = {
        name: _font_lengths_in_pixels(value, size) if name in ICON_GEOMETRY_LENGTHS else value
        for name, value in element.attrib.items()
        if name not in dropped
    }
    clone = ET.Element(element.tag, kept)
    clone.text, clone.tail = element.text, element.tail
    if inline := _other_inline_styles(element, page):
        clone.set("style", inline)
    stored = computed_properties(clone, stored, (), ())
    # An absent property has its starting value, on the page and in the copy alike, so a
    # reset such as ``fill: initial`` is written out rather than left to the copied attribute.
    for name in sorted(written):
        wanted = page.get(name, INITIAL_VALUES.get(name))
        stored_default = (
            None if name == "font-family" and name in page else INITIAL_VALUES.get(name)
        )
        raw = clone.get(name)
        relative_stroke = (
            name in STROKE_LENGTHS and raw is not None and _font_lengths_in_pixels(raw, size) != raw
        )
        relative_font = name == "font-size" and raw is not None and not ABSOLUTE_SIZE.fullmatch(raw)
        if wanted is None or (
            wanted == stored.get(name, stored_default) and not (relative_stroke or relative_font)
        ):
            continue
        if name in ICON_PAINT or wanted.strip():  # an empty paint is kept, to be refused
            clone.set(name, wanted)
            stored[name] = wanted
    if page.get("transform") != stored.get("transform"):
        value = _attribute_transform(page.get("transform", "none"))  # reset: none
        if value.strip() == "none":
            clone.attrib.pop("transform", None)
        else:
            clone.set("transform", value)
    return clone, stored


def _keep_words_after_removed_child(parent: ET.Element, tail: str | None) -> None:
    """The words after a removed child still show, so they join what comes before it."""
    if tail and len(parent):
        parent[-1].tail = (parent[-1].tail or "") + tail
    elif tail:
        parent.text = (parent.text or "") + tail


def _is_diamond(points: Sequence[Point]) -> bool:
    """A simple marker diamond has centered horizontal and vertical diagonals."""
    if len(points) != 4:
        return False
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    if abs(x0 + x2 - x1 - x3) + abs(y0 + y2 - y1 - y3) >= 0.01:
        return False
    first, second = (abs(x2 - x0), abs(y2 - y0)), (abs(x3 - x1), abs(y3 - y1))
    if first[0] < first[1]:
        first, second = second, first
    return first[0] >= 0.01 and first[1] < 0.01 and second[0] < 0.01 and second[1] >= 0.01


def _attribute_transform(value: str) -> str:
    """A CSS transform as an SVG attribute says it, which is without units."""
    return re.sub(r"(?<=\d)(?:px|deg)\b", "", value)


def _readable_transform(props: Props) -> bool:
    """Whether an element's transform, if any, is one this export understands."""
    value = _attribute_transform(props.get("transform", "")).strip()
    if value in ("", "none"):
        return True
    return TRANSFORM_FRAME.isdisjoint(props) and SVG_TRANSFORM.fullmatch(value) is not None


def svg_asset(
    view: Rect, parts: Sequence[ET.Element], paint: Props, shared: Sequence[ET.Element] = ()
) -> Asset | None:
    """Stand-alone SVG artwork drawing ``parts`` in ``view``, painted as placed.

    ``shared`` definitions sit outside the placement's paint, which on the page they never
    inherit: a marker or pattern takes its paint from where it is defined.
    """
    if not all(MIN_SVG_DIMENSION <= size <= MAX_DIMENSION for size in view[2:]):
        return None
    root = ET.Element(f"{{{SVG_NAMESPACE}}}svg", {"viewBox": " ".join(f"{v:g}" for v in view)})
    if shared:
        ET.SubElement(root, f"{{{SVG_NAMESPACE}}}defs").extend(shared)
    group = ET.SubElement(root, f"{{{SVG_NAMESPACE}}}g", paint)
    group.extend(parts)
    if not is_safe_svg(root):
        return None
    text = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    data = text.encode("utf-8")
    return Asset(data) if len(data) <= MAX_ICON_BYTES else None


# --------------------------------------------------------------------------
# What the SVG draws, in source order
# --------------------------------------------------------------------------


class IconCopy(NamedTuple):
    """An icon's markup copied for storing, and the page definitions it paints with."""

    parts: list[ET.Element]
    shared: list[ET.Element]
    clashes: bool = False  # holds an id the page gives to another element first


class MarkerShape(NamedTuple):
    """A marker mark in its local geometry, with the transform and channels that paint it."""

    tag: str
    outline: Subpath
    transform: Matrix
    props: Props
    opacity: float
    filled: bool
    stroked: bool


@dataclass(frozen=True, slots=True)
class Paint:
    """How an outline is painted, in the format's own terms."""

    fill: str
    stroke: str
    line_width: float
    pattern: LinePattern
    opacity: float = 1.0  # element and ancestor opacity also applies to its markers

    @property
    def filled(self) -> bool:
        """Whether there is a fill, rather than none."""
        return not (len(self.fill) == 9 and self.fill.endswith("00"))


NO_PAINT_AT_ALL = Paint(TRANSPARENT, TRANSPARENT, 0, "solid")


@dataclass(frozen=True, slots=True)
class TextStyle:
    """The character style of one line of text."""

    font_family: str | None
    font_size: float
    weight: Literal["regular", "medium", "bold"]
    italic: bool
    underlined: bool
    colour: str

    def record(self) -> Record:
        """The style as a ``base_style`` or character-run record."""
        style: Record = {
            "font_size": _number(max(1.0, min(720.0, self.font_size)), 2),
            "weight": self.weight,
            "is_italic": self.italic,
            "is_underlined": self.underlined,
            "color_hex": self.colour,
        }
        if self.font_family:
            style["font_family"] = self.font_family
        return style


DEFAULT_TEXT = TextStyle(None, 15, "medium", False, False, "#212529")


@dataclass(slots=True)
class Item:
    """Something drawn. ``arrange`` decides its ``kind`` and the box it is drawn on."""

    order: int
    kind: ItemKind = field(default="", init=False)  # "" when it becomes part of a box
    host: Box | None = field(default=None, init=False)


@dataclass(slots=True)
class Box(Item):
    """A closed outline: becomes a Basic library shape, or a closed path when none fits."""

    frame: Rect  # before rotation
    rotation: float
    subpath: Subpath  # the exact outline, in page coordinates
    paint: Paint
    basic: str | None  # the Basic shape's item ID; None keeps the exact outline
    flips: Flips = (False, False)
    matched: bool = False  # the Basic shape was recognised from the outline
    outline: list[Point] = field(init=False)  # flattened, for hit testing
    extent: Bounds = field(init=False)
    labels: list[Label] = field(default_factory=list, init=False)
    points: list[Point] = field(default_factory=lambda: list(STANDARD_POINTS), init=False)

    def __post_init__(self) -> None:
        """Flatten the outline once, for the many hit tests that follow."""
        self.outline = self.subpath.flattened()
        self.extent = bounds(self.outline)

    def keep_exact(self) -> None:
        """Drop a recognised Basic shape and write the outline exactly as drawn."""
        self.frame = path_frame(self.subpath, self.paint.line_width)
        self.basic, self.flips, self.matched = None, (False, False), False

    @property
    def area(self) -> float:
        """The frame's area, for choosing the smallest of several boxes."""
        return self.frame[2] * self.frame[3]

    @property
    def centre(self) -> Point:
        """The frame's centre on the page."""
        return self.from_frame((0.5, 0.5))

    def near(self, point: Point, margin: float) -> bool:
        """A cheap test that rules most boxes out before the exact outline tests."""
        left, top, right, bottom = self.extent
        x, y = point
        return left - margin <= x <= right + margin and top - margin <= y <= bottom + margin

    def holds(self, point: Point) -> bool:
        """Whether a point lies inside the outline or on it."""
        return self.near(point, 1) and (
            point_in_polygon(point, self.outline) or distance_to_outline(point, self.outline) <= 1
        )

    def _mirrored(self, fraction: Point) -> Point:
        """Between the frame as drawn and as stored: a flipped shape's points mirror."""
        u, v = fraction
        return (1 - u if self.flips[0] else u), (1 - v if self.flips[1] else v)

    def to_frame(self, point: Point) -> Point:
        """A page point as a stored connection point: fractions of the unflipped frame."""
        x, y, w, h = self.frame
        a = math.radians(-self.rotation)
        dx, dy = point[0] - (x + w / 2), point[1] - (y + h / 2)
        u = (dx * math.cos(a) - dy * math.sin(a)) / w + 0.5
        v = (dx * math.sin(a) + dy * math.cos(a)) / h + 0.5
        return self._mirrored((u, v))

    def from_frame(self, fraction: Point) -> Point:
        """Where a stored connection point is drawn on the page."""
        x, y, w, h = self.frame
        u, v = self._mirrored(fraction)
        dx, dy = (u - 0.5) * w, (v - 0.5) * h
        a = math.radians(self.rotation)
        return (
            x + w / 2 + dx * math.cos(a) - dy * math.sin(a),
            y + h / 2 + dx * math.sin(a) + dy * math.cos(a),
        )

    def point_id_for(self, point: Point) -> int:
        """The connection point at ``point``, added there while there is room, else the nearest."""
        u, v = (round(max(0.0, min(1.0, f)), 6) for f in self.to_frame(point))
        if (u, v) in self.points:
            return self.points.index((u, v))
        if len(self.points) < MAX_CONNECTION_POINTS:
            self.points.append((u, v))
            return len(self.points) - 1
        return min(range(len(self.points)), key=lambda i: math.dist(self.points[i], (u, v)))


class Attachment(NamedTuple):
    """A connector end fixed to one of a box's connection points."""

    box: Box
    point_id: int


@dataclass(slots=True)
class Stroke(Item):
    """An open line: becomes a connector, or a path when it neither points nor joins."""

    subpath: Subpath
    paint: Paint
    start_ending: Ending
    end_ending: Ending
    start: Attachment | None = field(default=None, init=False)
    end: Attachment | None = field(default=None, init=False)
    label: Box | None = field(default=None, init=False)  # the box whose text labels it
    fill: Box | None = field(default=None, init=False)  # the box painting this open path's fill
    reach: float = field(default=0.0, init=False)  # how far its markers reach past its ends

    @property
    def marked(self) -> bool:
        """Whether either end has an arrowhead or other marker."""
        return self.start_ending != "none" or self.end_ending != "none"

    @property
    def centre(self) -> Point:
        """The centre of the line's bounds."""
        left, top, right, bottom = bounds(self.subpath.flattened())
        return (left + right) / 2, (top + bottom) / 2


@dataclass(slots=True)
class Label(Item):
    """One line with local measurements and a page-scaled output text style."""

    string: str
    anchor: Point  # x and baseline y in the text's own coordinates
    matrix: Matrix
    align: Alignment
    style: TextStyle
    local_font_size: float
    letter_spacing: float = 0.0
    wrap_box: Rect | None = None  # set for text that wraps in a box

    @property
    def width(self) -> float:
        """The text's estimated width, generous since its font may be missing."""
        if self.wrap_box:
            return self.wrap_box[2]
        if "mono" in (self.style.font_family or "").lower():
            advance = MONO_CHAR_WIDTH * len(self.string)
        else:
            advance = sum(
                WIDE_CHAR_WIDTH if c.isupper() or c.isdigit() else CHAR_WIDTH for c in self.string
            )
        return advance * self.local_font_size + self.letter_spacing * len(self.string)

    def local_box(self) -> Rect:
        """The text box in its own coordinates: estimated for SVG text, exact when wrapping."""
        if self.wrap_box:
            return self.wrap_box
        x, baseline = self.anchor
        width, size = self.width, self.local_font_size
        left = x - {"leading": 0, "center": width / 2, "trailing": width}[self.align]
        return left, baseline - size * ASCENT, width, size * LINE_HEIGHT

    def page_bounds(self) -> Bounds:
        """The text box's bounds on the page."""
        x, y, w, h = self.local_box()
        corners = ((x, y), (x + w, y), (x, y + h), (x + w, y + h))
        return bounds(apply(self.matrix, corner) for corner in corners)

    @property
    def page_anchor(self) -> Point:
        """The anchor on the page."""
        return apply(self.matrix, self.anchor)

    @property
    def upright(self) -> bool:
        """Whether the text is drawn without rotation or skew."""
        turn = decompose(self.matrix)
        return turn is not None and abs(turn[0]) < 0.01

    @property
    def centre(self) -> Point:
        """The text box's centre on the page."""
        left, top, right, bottom = self.page_bounds()
        return (left + right) / 2, (top + bottom) / 2


def reading_order(labels: Iterable[Label]) -> list[Label]:
    """Lines of text from the top down, then left to right."""
    return sorted(labels, key=lambda label: label.page_anchor[::-1])


@dataclass(slots=True)
class Artwork(Item):
    """A picture: an icon placed by reference."""

    frame: Rect  # before rotation
    rotation: float
    asset: Asset
    flips: Flips = (
        False,
        False,
    )  # a mirrored placement, mirrored in the frame before turning

    @property
    def area(self) -> float:
        """The frame's area."""
        return self.frame[2] * self.frame[3]

    @property
    def centre(self) -> Point:
        """The frame's centre on the page."""
        x, y, w, h = self.frame
        return x + w / 2, y + h / 2


@dataclass(slots=True)
class Swimlanes(Item):
    """Lanes drawn as parallel dividers with a title column: SimpleDiagrams' Swimlanes shape.

    Positions are kept in lane space, where lanes stack downwards whichever way
    they run on the page; ``vertical`` lanes are columns, so their space is the
    page's turned through a quarter.
    """

    vertical: bool
    across: tuple[float, float]  # where the lanes start and end, across the stacking
    levels: list[float]  # where the dividers lie, in stacking order
    strip: float  # the title column's thickness
    titles: list[Label]
    dividers: list[Stroke]
    paint: Paint

    @property
    def frame(self) -> Rect:
        """The page frame, with SimpleDiagrams' title band added across the top."""
        (left, right), top, bottom = self.across, self.levels[0], self.levels[-1]
        if self.vertical:
            return top, left - TITLE_BAND, bottom - top, right - left + TITLE_BAND
        return left, top - TITLE_BAND, right - left, bottom - top + TITLE_BAND

    def lane_of(self, point: Point) -> int | None:
        """The lane a page point lies in, if any."""
        x, y = _turned(point, self.vertical)
        if not self.across[0] <= x <= self.across[1]:
            return None
        spans = itertools.pairwise(self.levels)
        return next((i for i, (a, b) in enumerate(spans) if a <= y < b), None)


Drawn: TypeAlias = Box | Stroke | Label | Artwork
Shown: TypeAlias = Drawn | Swimlanes  # everything written, the lanes included
Handler: TypeAlias = Callable[[ET.Element, Props, Matrix, float], None]


def _turned(point: Point, vertical: bool) -> Point:
    """A page point in lane space: unchanged for rows, swapped for columns."""
    return (point[1], point[0]) if vertical else point


def _local(element: ET.Element) -> str:
    """The tag without its namespace: ``rect`` for an SVG rect, ``div`` for XHTML."""
    return element.tag.rpartition("}")[2] if isinstance(element.tag, str) else ""


def _clip_utf8(text: str, max_bytes: int, drop: Sequence[str] = ("Cc",)) -> str:
    """Drop characters of the given Unicode categories, then cut to a byte limit."""
    text = "".join(c for c in text if unicodedata.category(c) not in drop)
    return text.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")


class Reader:
    """Walks the exported SVG once and collects boxes, strokes and labels in drawing order."""

    def __init__(self, root: ET.Element, page: tuple[ET.Element, ET.Element] | tuple[()]) -> None:
        """Prepare to read ``root``: its stylesheet, its IDs and its page size."""
        self.root = root
        styles = (element.text or "" for element in root.iter() if _local(element) == "style")
        self.rules, self.unread = parse_stylesheet("".join(styles))
        self.page_ancestors = list(page)
        self.root_inherited: Props = {}
        if page:
            html, body = page
            html_style = computed_properties(html, {}, self.rules, ())
            self.root_inherited = computed_properties(body, html_style, self.rules, (html,))
        self.by_id: dict[str, ET.Element] = {}
        for element in root.iter():
            if name := element.get("id"):
                self.by_id.setdefault(name, element)  # the first wins, as in a browser
        self.parents = {child: parent for parent in root.iter() for child in parent}
        self.markers = {key: e for key, e in self.by_id.items() if _local(e) == "marker"}
        self.marker_readings: dict[
            tuple[ET.Element, tuple[float, float]], tuple[MarkerShape | None, list[Note]]
        ] = {}
        view = [float(v) for v in NUMBER_RE.findall(root.get("viewBox", ""))]
        usable = len(view) == 4 and all(map(math.isfinite, view)) and min(view[2:]) > 0
        if usable and min(view[2:]) < 0.001:
            raise ValueError("the diagram's viewBox is smaller than a SimpleDiagrams page can be")
        self.view = view if usable else [0.0, 0.0, 1000.0, 600.0]
        if max(self.view[2:]) > MAX_DIMENSION:
            raise ValueError("the diagram's viewBox is larger than a SimpleDiagrams page can be")
        self.items: list[Drawn] = []
        self.background: str | None = None
        self.skipped: dict[str, int] = {}
        self.measuring = False  # walking an icon only to find its bounds
        self.in_faded_group = False  # merged boxes would hide a compositing loss
        self.held_back: set[tuple[Note, str]] = set()  # raised only if nothing is stored
        self.ancestors: list[ET.Element] = []
        self.viewport = (self.view[2], self.view[3])  # what percentages are of, here
        self.handlers: dict[str, Handler] = {
            "rect": self._rect,
            "circle": self._ellipse,
            "ellipse": self._ellipse,
            "line": self._line,
            "polyline": self._polyline,
            "polygon": self._polyline,
            "path": self._path,
            "text": self._text,
            "foreignObject": self._foreign_object,
            "use": self._use,
        }

    def read(self) -> Reader:
        """Collect every drawn item, with the view box's corner as the page origin."""
        origin: Matrix = (1, 0, 0, 1, -self.view[0], -self.view[1])
        if self._selects_any(self.unread):
            self._skip(Note.STYLESHEET_UNREAD)
        self._root_background()
        self._walk(self.root, self.root_inherited, origin, 1.0, self.page_ancestors)
        if (count := len(self.items)) > MAX_ITEMS:
            raise ValueError(
                f"the diagram draws {count} shapes; this export handles up to {MAX_ITEMS}"
            )
        return self

    def _root_background(self) -> None:
        """Take an opaque colour the root ``<svg>`` is painted with as the page's background."""
        values = [
            (name, value)
            for name, value in _cascaded_declarations(self.root, self.rules, self.page_ancestors)
            if name in {"background", "background-color", "background-image"}
        ]
        if not values:
            return
        props = computed_properties(self.root, self.root_inherited, self.rules, self.page_ancestors)
        colour = None
        has_image = False
        for name, raw in values:
            value = resolve_vars(raw, props.custom_value) or ""
            if name != "background-color":
                has_image = bool(re.search(r"gradient\(|url\(", value, re.IGNORECASE))
            if name == "background-image":
                continue
            if name == "background":
                # The shorthand resets the colour when it specifies only an image or none.
                colour = None
                if has_image:
                    continue
            if value.lower() in CSS_WIDE_KEYWORDS | NO_PAINT or not value:
                colour = None
                continue
            tokens = re.findall(r"#[0-9a-fA-F]+|(?:rgba?|hsla?)\([^)]*\)|[a-zA-Z]+", value)
            for token in tokens:
                if (parsed := parse_colour(token, props)) is not None:
                    colour = parsed
                    break
        if has_image:
            self._skip(Note.UNKNOWN_PAINT)
        if colour is not None and colour[3] >= 0.999:
            self.background = colour_hex(colour)

    def _declares(
        self, element: ET.Element, ancestors: list[ET.Element], wanted: Callable[[str, str], bool]
    ) -> bool:
        """Whether the stylesheet or the inline style declares a property ``wanted`` accepts."""
        layers = [rule.declarations for rule in self.rules if rule.applies(element, ancestors)]
        layers.append(_declarations(element.get("style", "")))
        return any(wanted(name, value) for layer in layers for name, value in layer.items())

    def _note_css_geometry(
        self, element: ET.Element, ancestors: list[ET.Element], report: Callable[[Note], None] | None = None
    ) -> None:
        """Note sizes, places and transforms only CSS can set, which this export does not read."""
        emit = report or self._skip
        if self._declares(element, ancestors, _moves_alone):
            emit(Note.CSS_TRANSFORM)
        geometry = GEOMETRY.get(_local(element), frozenset())

        def differs(name: str, value: str) -> bool:
            """Whether CSS sets one of the element's sizes to other than its attribute says."""
            if name not in geometry:
                return False
            written, value = (
                element.get(name, "").strip(),
                value.removesuffix(IMPORTANT).strip(),
            )
            return value != written and length(value, math.nan) != length(written, math.nan)

        if geometry and self._declares(element, ancestors, differs):
            emit(Note.CSS_GEOMETRY)

    def _html_declares(
        self,
        element: ET.Element,
        props: Props,
        ancestors: list[ET.Element],
        wanted: Callable[[str, str], bool],
    ) -> bool:
        """Whether HTML that shows inside an element declares a property ``wanted`` accepts."""
        path = [*ancestors, element]
        for child in element:
            child_props = computed_properties(child, props, self.rules, path)
            if child.get("hidden") is not None or child_props.get("display") == "none":
                continue
            if not _is_invisible(child_props) and self._declares(child, path, wanted):
                return True
            if self._html_declares(child, child_props, path, wanted):
                return True
        return False

    def _selects_any(self, rules: Sequence[CssRule]) -> bool:
        """Whether any of the rules selects an element of the drawing."""
        if any(
            rule.applies(node, self.page_ancestors[:index])
            for index, node in enumerate(self.page_ancestors)
            for rule in rules
        ):
            return True  # an unread page declaration may set an inherited value
        stack = [(self.root, self.page_ancestors)]
        while stack:
            element, path = stack.pop()
            if any(rule.applies(element, path) for rule in rules):
                return True
            stack += [(child, [*path, element]) for child in element]
        return False

    def _note_undrawn(self, props: Props, report: Callable[[Note], None] | None = None) -> None:
        """Note each effect, such as clipping or a blur, that an element asks for."""
        emit = report or self._skip
        for name, note in UNDRAWN_NOTES.items():
            if props.get(name, "none").strip().lower() not in ("none", "normal"):
                emit(note)

    def _shows_inside(self, element: ET.Element, props: Props, ancestors: list[ET.Element]) -> bool:
        """Whether something inside a hidden element makes itself visible again."""
        path = [*ancestors, element]
        for child in element:
            child_props = computed_properties(child, props, self.rules, path)
            if child_props.get("display") == "none" or _local(child) in NOT_DRAWN:
                continue
            if not _is_invisible(child_props) or self._shows_inside(child, child_props, path):
                return True
        return False

    def _skip(self, note: Note, element: str = "") -> None:
        """Count content that could not be translated, for one note per kind.

        Walking an icon only to measure it holds its notes back: the icon is stored as SVG, and
        its copy raises the notes that apply to it. They are raised only if nothing is stored.
        """
        if self.measuring:
            self.held_back.add((note, element))
        else:
            what = note.worded(element)
            self.skipped[what] = self.skipped.get(what, 0) + 1

    def _walk(
        self,
        element: ET.Element,
        inherited: Props,
        matrix: Matrix,
        opacity: float,
        ancestors: list[ET.Element],
    ) -> None:
        """Style and transform one element, then draw it or walk into its children."""
        name = _local(element)
        if name in NOT_DRAWN:
            return
        if name in UNSUPPORTED:
            self._skip(Note.ELEMENT_LEFT_OUT, name)
            return
        props = computed_properties(element, inherited, self.rules, ancestors)
        if props.get("display") == "none":
            return
        if not _readable_transform(props):
            self._skip(Note.CSS_TRANSFORM)
        if element is not self.root:
            self._note_css_geometry(element, ancestors)
        matrix = multiply(matrix, parse_transform(props.get("transform")))
        if _collapses(matrix):
            return
        opacity *= _opacity(props.get("opacity"))
        if opacity <= 0:
            return
        self._note_undrawn(props)
        if name == "svg" and element is not self.root:
            self._nested_svg(element, props, matrix, opacity, ancestors)
        elif name in CONTAINERS:
            self._walk_group(element, props, matrix, opacity, [*ancestors, element])
        elif _is_invisible(props) and name not in SHOWS_VISIBLE_CHILDREN:
            # Hidden drawing; a child of it that shows itself has no equivalent here.
            if self._shows_inside(element, props, ancestors):
                self._skip(Note.HIDDEN_CONTENT, name)
        elif handler := self.handlers.get(name):
            self.ancestors = ancestors  # text handlers style their children with it
            handler(element, props, matrix, opacity)
        else:
            self._skip(Note.ELEMENT_LEFT_OUT, name)

    def _walk_group(
        self, element: ET.Element, props: Props, matrix: Matrix, opacity: float, path: list[ET.Element]
    ) -> None:
        """Walk a composited container without hiding overlapping parts in a box merge."""
        first = len(self.items)
        faded = _opacity(props.get("opacity")) < 1
        outer_group = self.in_faded_group
        self.in_faded_group = faded or outer_group
        try:
            for child in element:
                self._walk(child, props, matrix, opacity, path)
        finally:
            self.in_faded_group = outer_group
        if faded and _overlapping(self.items[first:]):
            self._skip(Note.SEE_THROUGH_OVERLAP)

    # -- paint ------------------------------------------------------------

    def _colour(self, value: str | None, props: Props) -> Colour | None:
        """A paint as a colour, noting any paint (a gradient, a pattern) it cannot show."""
        if value is None or value.strip().lower() in NO_PAINT:
            return None
        if (colour := parse_colour(value, props)) is None:
            self._skip(Note.UNKNOWN_PAINT)
            # A stored icon may keep this paint. Include its geometry when measuring.
            if self.measuring:
                return (0, 0, 0, 1.0)
        return colour

    def _paint(
        self, props: Props, opacity: float, matrix: Matrix, *, has_area: bool = True
    ) -> Paint:
        """Fill, line and dash pattern, with line widths scaled as the transform scales."""
        fill = self._colour(props.get("fill", "black"), props)
        stroke = self._colour(props.get("stroke"), props)
        turn = decompose(matrix)
        scale = math.sqrt(turn[1] * turn[2]) if turn else 1.0
        non_scaling = props.get("vector-effect", "").strip() == "non-scaling-stroke"
        if non_scaling:
            scale = 1.0
        width = max(0.0, self._either(props.get("stroke-width"), props, default=1.0)) * scale
        fill_hex = colour_hex(fill, opacity * _paint_opacity(props, "fill"))
        stroke_hex = colour_hex(stroke, opacity * _paint_opacity(props, "stroke"))
        if len(stroke_hex) == 9 and stroke_hex.endswith("00"):
            width = 0.0
        if (
            has_area and not (len(fill_hex) == 9 and fill_hex.endswith("00")) and width > 0
        ):  # the outline overlaps the fill
            if opacity < 1:  # a browser fades the two together, as one picture
                self._skip(Note.SEE_THROUGH_OVERLAP)
            order = props.get("paint-order", "").lower().split()
            if set(order) <= {"fill", "stroke", "markers"} and len(set(order)) == len(order):
                order += [part for part in ("fill", "stroke", "markers") if part not in order]
                if order.index("stroke") < order.index("fill"):
                    self._skip(Note.PAINT_ORDER)
        dash_values = re.split(r"[\s,]+", props.get("stroke-dasharray", "none").strip())
        dashes = [self._either(value, props) for value in dash_values if value and value != "none"]
        pattern: LinePattern = "solid"
        if any(dashes):
            pattern = "dotted" if dashes[0] <= max(1.5, width * 1.5) else "dashed"
        if width > 0 and (
            props.get("stroke-linecap", "butt") != "butt"
            or props.get("stroke-linejoin", "miter") != "miter"
            or length(props.get("stroke-miterlimit"), 4) != 4
            or pattern != "solid"
            or (not non_scaling and (turn is None or not math.isclose(turn[1], turn[2])))
        ):
            self._skip(Note.STROKE_STYLE)
        return Paint(fill_hex, stroke_hex, round(min(10_000.0, width), 3), pattern, opacity)

    def _marker(self, reference: str | None) -> ET.Element | None:
        """The ``<marker>`` a ``marker-start`` or ``marker-end`` value names, if any."""
        match = re.fullmatch(r"\s*url\(\s*['\"]?#([^'\")]+)['\"]?\s*\)\s*", reference or "")
        marker = self.markers.get(match.group(1)) if match else None
        if marker is None or any(
            length(marker.get(name), 3.0, percent_of=1.0) <= 0
            for name in ("markerWidth", "markerHeight")
        ):
            return None
        return marker

    def _marker_outlines(self, element: ET.Element, props: Props) -> list[Subpath]:
        """Normalize supported marker geometry to the same paths used by native shapes."""
        tag = _local(element)
        if tag == "path":
            try:
                return parse_path_data(element.get("d", ""))
            except ValueError:
                return []
        if tag in {"circle", "ellipse"}:
            if tag == "circle":
                rx = ry = self._either(element.get("r"), props)
            else:
                rx = self._across(element.get("rx"), props=props)
                ry = self._down(element.get("ry"), props=props)
            cx = self._across(element.get("cx"), props=props)
            cy = self._down(element.get("cy"), props=props)
            return [ellipse_subpath(cx, cy, rx, ry)] if rx > 0 and ry > 0 else []
        if tag == "rect":
            x, y = self._place(element, props)
            w = self._across(element.get("width"), props=props)
            h = self._down(element.get("height"), props=props)
            return [rectangle_subpath((x, y, w, h), 0, 0)] if w > 0 and h > 0 else []
        if tag == "line":
            points = [
                (self._across(element.get(x), props=props), self._down(element.get(y), props=props))
                for x, y in (("x1", "y1"), ("x2", "y2"))
            ]
        elif tag in {"polygon", "polyline"}:
            points = _polyline_points(element.get("points", ""))
        else:
            return []
        return [Subpath(points[0], [Line(p) for p in points[1:]], tag == "polygon")] if points else []

    def _marker_shape(
        self, marker: ET.Element, outer: Props, ancestors: list[ET.Element]
    ) -> tuple[MarkerShape | None, list[Note]]:
        """Choose the largest painted mark, noting when one native ending replaces several."""
        marks: list[MarkerShape] = []
        notes: list[Note] = []

        def walk(
            node: ET.Element, inherited: Props, path: list[ET.Element], opacity: float, matrix: Matrix
        ) -> None:
            for child in node:
                tag = _local(child)
                if tag in NOT_DRAWN:
                    continue
                props = computed_properties(child, inherited, self.rules, path)
                child_opacity = opacity * _opacity(props.get("opacity"))
                transform = multiply(matrix, parse_transform(props.get("transform")))
                if props.get("display") == "none" or child_opacity <= 0 or _collapses(transform):
                    continue
                first = len(marks)
                if not _is_invisible(props):
                    self._note_css_geometry(child, path, notes.append)
                    fill, stroke = _has_fill(props), _has_line(props)
                    capped = props.get("stroke-linecap", "butt").lower() in {"round", "square"}
                    if fill or stroke:
                        for outline in self._marker_outlines(child, props):
                            points = outline.flattened()
                            filled = fill and painted_area(points) > 0
                            stroked = stroke and len(points) > 1 and (
                                capped or any(point != points[0] for point in points[1:])
                            )
                            if filled or stroked:
                                marks.append(
                                    MarkerShape(tag, outline, transform, props, child_opacity, filled, stroked)
                                )
                walk(child, props, [*path, child], child_opacity, transform)
                if len(marks) > first:
                    self._note_undrawn(props, notes.append)

        matrix = parse_transform(outer.get("transform"))
        if outer.get("display") == "none" or _collapses(matrix):
            return None, notes
        walk(marker, outer, [*ancestors, marker], _opacity(outer.get("opacity")), matrix)
        if not marks:
            return None, notes
        self._note_undrawn(outer, notes.append)
        if len(marks) == 1:
            return marks[0], notes
        notes.append(Note.ENDING_COMPOSITE)

        def size(mark: MarkerShape) -> tuple[float, float]:
            left, top, right, bottom = bounds(
                apply(mark.transform, point) for point in mark.outline.flattened()
            )
            return (right - left) * (bottom - top), math.hypot(right - left, bottom - top)

        return max(reversed(marks), key=size), notes  # a same-sized mark painted later lies on top

    def _marker_reach(self, props: Props, line_width: float) -> float:
        """How far a line's markers can reach past its end, so an icon's bounds include them."""
        reach = 0.0
        for reference in (props.get("marker-start"), props.get("marker-end")):
            if (marker := self._marker(reference)) is not None:
                size = math.hypot(
                    length(marker.get("markerWidth"), 3.0), length(marker.get("markerHeight"), 3.0)
                )
                scale = 1.0 if marker.get("markerUnits") == "userSpaceOnUse" else line_width
                reach = max(reach, size * scale)
        return reach

    def _ending(
        self, reference: str | None, heading: float | None, at_start: bool, line: Paint
    ) -> Ending:
        """The line ending a ``marker-start`` or ``marker-end`` reference draws.

        ``heading`` is the way the line runs at that end. SimpleDiagrams draws an ending
        pointing away from the line, in its stroke colour and opacity. Differences are noted.
        """
        if (marker := self._marker(reference)) is None:
            return "none"
        # Definition styles are independent of each line. Percentages still use its viewport.
        key = (marker, self.viewport)
        if key not in self.marker_readings:
            inherited, path = self._context_of(marker)
            outer = computed_properties(marker, inherited, self.rules, path)
            self.marker_readings[key] = self._marker_shape(marker, outer, path)
        shown, notes = self.marker_readings[key]
        for note in notes:
            self._skip(note)
        if shown is None:
            return "none"
        tag, outline, transform, props, marker_opacity, filled, stroked = shown
        fill = parse_colour(props.get("fill", "black"), props) if filled else None
        stroke = parse_colour(props.get("stroke", "none"), props) if stroked else None
        painted_as_paper = fill is not None and colour_hex(fill)[:7] in (self.background, "#FFFFFF")
        hollow = not filled or (stroked and fill != stroke and painted_as_paper)
        recoloured = changed_opacity = unread_paint = False
        for channel, colour, draws in (("fill", fill, filled and not hollow), ("stroke", stroke, stroked)):
            if not draws:
                continue
            if colour is None:
                unread_paint = True
                continue
            opacity = line.opacity * marker_opacity * _paint_opacity(props, channel)
            ending = colour_hex(colour, opacity)
            recoloured |= ending[:7] != line.stroke[:7]
            changed_opacity |= (ending[7:] or "FF") != (line.stroke[7:] or "FF")
        if recoloured:
            self._skip(Note.ENDING_RECOLOURED)
        if changed_opacity:
            self._skip(Note.ENDING_OPACITY)
        if unread_paint:
            self._skip(Note.ENDING_PAINT_UNREAD)
        if tag in ("circle", "ellipse"):
            return "circle" if hollow else "solidCircle"
        # Relative commands and shorthand have already become absolute path segments.
        points = outline.flattened()
        returns_to_start = len(points) > 1 and points[-1] == points[0]
        if returns_to_start:
            points.pop()
        closed = outline.closed or returns_to_start
        direction = math.degrees(math.atan2(transform[1], transform[0]))
        if (closed or not stroked) and _is_diamond(points):
            if heading is not None:
                angle = _marker_axis(marker.get("orient"), heading, at_start) + direction - heading
                if decompose(transform) is None or abs((angle + 90) % 180 - 90) > 1:
                    self._skip(Note.ENDING_DIAMOND_ORIENTATION)
            return "openDiamond" if hollow else "diamond"
        if len(points) != 3:
            self._skip(Note.ENDING_SHAPE)
        elif heading is not None:
            # A simple triangle points left or right along the authored marker's axis.
            xs = [point[0] for point in points]
            at_left = sum(math.isclose(x, min(xs), abs_tol=0.01) for x in xs)
            at_right = sum(math.isclose(x, max(xs), abs_tol=0.01) for x in xs)
            if (at_left, at_right) in {(1, 2), (2, 1)}:
                tip = _marker_axis(marker.get("orient"), heading, at_start) + direction + 180 * (at_left == 1)
                away = heading + 180 * at_start
                if abs((tip - away + 180) % 360 - 180) > 1:
                    self._skip(Note.ENDING_DIRECTION)
            else:
                self._skip(Note.ENDING_DIRECTION_UNKNOWN)
        if len(points) == 3 and hollow and (filled or (stroked and closed)):
            return "solidArrow"  # an outlined triangle, which the format draws hollow
        return "filledArrow" if filled else "arrow"

    # -- shapes -----------------------------------------------------------

    def _add_box(
        self,
        basic: str | None,
        local: Rect,
        matrix: Matrix,
        paint: Paint,
        subpath: Subpath,
    ) -> None:
        """Add a painted box: a Basic shape set in its frame, or else its exact closed path."""
        if not paint.filled and paint.line_width <= 0:
            return
        page_subpath = subpath.transformed(matrix)
        order = len(self.items)
        if basic is None:
            box = Box(order, (0, 0, 1, 1), 0.0, page_subpath, paint, None)
            if (found := match_basic_shape(box.outline)) is not None:
                left, top, right, bottom = box.extent
                box.frame = (left, top, right - left, bottom - top)
                box.basic, box.flips, box.matched = found[0], found[1], True
            else:
                box.keep_exact()
        elif (placed := placed_frame(local, matrix)) is not None:
            box = Box(order, *placed, page_subpath, paint, basic)
        else:  # a skewed rectangle or circle is no longer one
            box = Box(order, (0, 0, 1, 1), 0.0, page_subpath, paint, None)
            box.keep_exact()
        if (
            not self.in_faded_group
            and self.items
            and isinstance(below := self.items[-1], Box)
            and _same_place(below, box)
            and (
                below.paint.line_width == 0
                or box.paint.line_width == 0
                or (
                    box.paint.line_width >= below.paint.line_width
                    and len(box.paint.stroke) == 7
                    and box.paint.pattern == "solid"
                )
            )
        ):  # keep both outlines if the lower one still shows through the upper one
            # A tint drawn over a copy of the same shape is one shape, its fill the two mixed
            # as the page shows them, so an opaque copy still hides what is behind it.
            fill = _over(box.paint.fill, below.paint.fill) if box.paint.filled else below.paint.fill
            line = box.paint if box.paint.line_width > 0 else below.paint
            box.paint = replace(line, fill=fill)
            box.order = below.order
            self.items[-1] = box
        else:
            self.items.append(box)

    def _covers_canvas(self, x: float, y: float, w: float, h: float, matrix: Matrix) -> bool:
        """Whether a rectangle covers the whole page, as the paper does."""
        left, top, right, bottom = bounds([apply(matrix, (x, y)), apply(matrix, (x + w, y + h))])
        width, height = self.view[2:]
        return left <= 0.5 and top <= 0.5 and right >= width - 0.5 and bottom >= height - 0.5

    def _take_as_paper(self, props: Props, opacity: float) -> bool:
        """Take a page-sized layer under the drawing as the page itself; whether it is used up.

        An opaque colour becomes the page's background, the last one drawn showing. The
        skill's dot pattern is left to the editor's grid, and a layer painting nothing draws
        nothing. A see-through colour is not used up: it is drawn as a shape over the page.
        """
        fill = props.get("fill", "black").strip()
        if fill.lower() in NO_PAINT:
            return True
        if match := re.fullmatch(r"url\(\s*['\"]?#([^'\")]+)['\"]?\s*\)", fill):
            server = self.by_id.get(match.group(1))
            return (
                server is not None
                and _local(server) == "pattern"
                and re.fullmatch(r"(?:[\w-]+-)?dots(?:-\d+)?", match.group(1)) is not None
                and len(server) == 1
                and _local(server[0]) == "circle"
            )  # other patterns and gradients go through the ordinary paint note
        if (colour := parse_colour(fill, props)) is None:
            return False  # drawn as a shape, which notes the colour it cannot show
        alpha = opacity * _paint_opacity(props, "fill")
        if colour[3] * alpha < 0.999:
            return False
        self.background = colour_hex(colour)
        return True

    def _rect(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A rectangle becomes a Square, Rounded Rectangle or Pill; the paper, the background."""
        x, y = (
            self._across(element.get("x"), props=props),
            self._down(element.get("y"), props=props),
        )
        w = self._across(element.get("width"), props=props)
        h = self._down(element.get("height"), props=props)
        if w <= 0 or h <= 0:
            return
        # One radius stands for both; either at zero squares the corners, as in a browser.
        rx_given, ry_given = element.get("rx"), element.get("ry")
        rx = self._across(rx_given, props=props) if rx_given is not None else None
        ry = self._down(ry_given, props=props) if ry_given is not None else None
        rx, ry = (
            (rx if rx is not None else ry or 0.0),
            (ry if ry is not None else rx or 0.0),
        )
        radius = rx if min(rx, ry) > 0 else 0.0
        upright = abs(matrix[1]) < 1e-9 and abs(matrix[2]) < 1e-9 and radius <= 0
        # The paper lies under everything; a page frame has a line, a later cover is drawn.
        may_be_paper = upright and not self.items and not self.measuring and not _has_line(props)
        covers = may_be_paper and self._covers_canvas(x, y, w, h, matrix)
        if covers and self._take_as_paper(props, opacity):
            return
        if radius > 0 and decompose(matrix) is None:
            self._skip(Note.SKEWED_CORNERS)
            rx = ry = 0
        frame = (x, y, w, h)
        outline = rectangle_subpath(frame, rx, ry)
        paint = self._paint(props, opacity, matrix)
        self._add_box(rectangle_shape(w, h, radius), frame, matrix, paint, outline)

    def _ellipse(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A circle or ellipse becomes a Circle."""
        if (radius := element.get("r")) is not None:
            rx = ry = self._either(radius, props)
        else:
            rx = self._across(element.get("rx"), props=props)
            ry = self._down(element.get("ry"), props=props)
        if rx > 0 and ry > 0:
            cx, cy = (
                self._across(element.get("cx"), props=props),
                self._down(element.get("cy"), props=props),
            )
            paint = self._paint(props, opacity, matrix)
            local = (cx - rx, cy - ry, 2 * rx, 2 * ry)
            self._add_box("Circle", local, matrix, paint, ellipse_subpath(cx, cy, rx, ry))

    def _line(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A ``<line>`` is an open outline of one segment."""
        start = (
            self._across(element.get("x1"), props=props),
            self._down(element.get("y1"), props=props),
        )
        end = (
            self._across(element.get("x2"), props=props),
            self._down(element.get("y2"), props=props),
        )
        paint = self._paint(props, opacity, matrix, has_area=False)
        self._add_outline(Subpath(start, [Line(end)]), paint, props, matrix)

    def _polyline(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A polyline is an open outline of straight segments; a polygon, a closed one."""
        points = _polyline_points(element.get("points", ""))
        if len(points) >= 2:
            closed = _local(element) == "polygon"
            subpath = Subpath(points[0], [Line(p) for p in points[1:]], closed)
            paint = self._paint(
                props, opacity, matrix, has_area=painted_area(points) > MIN_FILLED_AREA
            )
            self._add_outline(subpath, paint, props, matrix)

    def _path(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """Each subpath becomes its own outline; a hole in a filled shape keeps its line."""
        try:
            subpaths = parse_path_data(element.get("d", ""))
        except ValueError:
            self._skip(Note.UNREADABLE_PATH)
            return
        flattened = [subpath.flattened() for subpath in subpaths]
        # SVG closes open contours for fill only. Keep their strokes open.
        outlines = [
            (subpath, points, bounds(points))
            for subpath, points in zip(subpaths, flattened, strict=True)
            if painted_area(points) > 0
        ]
        extents = {id(subpath): extent for subpath, _, extent in outlines}
        paint = self._paint(props, opacity, matrix, has_area=bool(outlines))
        check_holes = len(outlines) <= OVERLAP_CHECK_LIMIT
        if paint.filled and not check_holes:
            self._skip(Note.COMPLEX_HOLES)
        filled_contours: list[tuple[Bounds, bool]] = []
        for index, (subpath, points) in enumerate(zip(subpaths, flattened, strict=True)):
            # Markers sit at the whole path's start and end, not at each subpath's.
            ends = {
                "marker-start": index == 0,
                "marker-end": index == len(subpaths) - 1,
            }
            subpath_props = {name: value for name, value in props.items() if ends.get(name, True)}
            extent = extents.get(id(subpath))
            if (
                check_holes and paint.filled and extent is not None
                and _is_hole(subpath, points, extent, outlines, props)
            ):
                # A path cannot cut a hole in another, so a hole keeps only its outline.
                self._skip(Note.HOLE)
                if paint.line_width > 0:
                    rim = replace(paint, fill=TRANSPARENT)
                    self._add_outline(subpath, rim, subpath_props, matrix, len(subpaths) > 1)
                continue
            self._add_outline(subpath, paint, subpath_props, matrix, len(subpaths) > 1)
            if (
                paint.filled
                and len(filled_contours) <= OVERLAP_CHECK_LIMIT
                and extent is not None
            ):
                filled_contours.append((extent, signed_area(points) > 0))
        # SVG fills a path once, cancelling areas by its fill rule before applying opacity.
        see_through = paint.filled and len(paint.fill) == 9
        if see_through and _bounds_overlap([extent for extent, _ in filled_contours]):
            self._skip(Note.SEE_THROUGH_OVERLAP)
        evenodd = props.get("fill-rule", "").strip().lower() == "evenodd"
        if check_holes and any(
            (evenodd or forward != reverse) and _intersects_bounds(a, b)
            for (a, forward), (b, reverse) in itertools.combinations(filled_contours, 2)
        ):
            self._skip(Note.CONTOUR_OVERLAP)

    def _add_outline(
        self,
        subpath: Subpath,
        paint: Paint,
        props: Props,
        matrix: Matrix,
        joined: bool = False,
    ) -> None:
        """A closed outline becomes a box, an open one a stroke; one painting nothing is dropped.

        ``joined`` says the subpath is one of several in a path, whose meeting points are
        middle vertices too.
        """
        between = joined or len(subpath.segments) > 1 or subpath.closed  # where marker-mid draws
        if between and self._marker(props.get("marker-mid")) is not None:
            self._skip(Note.MID_MARKERS)
        marked = any(self._marker(props.get(end)) for end in ("marker-start", "marker-end"))
        if marked and (subpath.closed or paint.line_width <= 0):
            self._skip(Note.MARKERS_UNDRAWN)
        if subpath.closed and len(subpath.flattened()) >= 3:
            if paint.filled or paint.line_width > 0:
                self._add_box(None, (0, 0, 0, 0), matrix, paint, subpath)
            return
        # SVG fills an open path as if it were closed: the fill goes below its line.
        fill = None
        if paint.filled and painted_area(subpath.flattened()) > MIN_FILLED_AREA:
            shape = Subpath(subpath.start, subpath.segments, closed=True)
            below = replace(paint, stroke=TRANSPARENT, line_width=0, pattern="solid")
            self._add_box(None, (0, 0, 0, 0), matrix, below, shape)
            fill, paint = self.items[-1], replace(paint, fill=TRANSPARENT)
        if paint.line_width > 0:  # an open shape with no line draws no line to keep
            points = subpath.flattened()
            ends = [
                self._ending(
                    props.get(end),
                    _heading(points, at_start=first),
                    first,
                    paint,
                )
                for end, first in (("marker-start", True), ("marker-end", False))
            ]
            start, end = ends
            stroke = Stroke(len(self.items), subpath.transformed(matrix), paint, start, end)
            stroke.fill = fill if isinstance(fill, Box) else None
            stroke.reach = self._marker_reach(props, paint.line_width)
            self.items.append(stroke)

    # -- text -------------------------------------------------------------

    def _note_text_effects(self, node: ET.Element, props: Props) -> None:
        """Note what a text or span asks for that a SimpleDiagrams label cannot draw."""
        if _is_invisible(props):
            return
        if _uses_vertical_text(props):
            self._skip(Note.VERTICAL_TEXT)
        if {"line-through", "overline"} & set(props.get("text-decoration", "").split()):
            self._skip(Note.CROSSED_TEXT)
        if any(float(turn) % 360 for turn in NUMBER_RE.findall(node.get("rotate") or "")):
            self._skip(Note.TURNED_LETTERS)

    def _text(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """Each ``<text>``, and each separately placed ``<tspan>`` in it, becomes one line."""
        self._note_text_effects(element, props)

        def placed(node: ET.Element, size: float, x: float, y: float) -> Point:
            """Where a node places its text, from its own position or the one before."""
            if any(
                len(NUMBER_RE.findall(node.get(key) or "")) > 1 for key in ("x", "y", "dx", "dy")
            ):
                self._skip(Note.PLACED_LETTERS)
            sized = {"font-size": f"{size:g}"}  # em is of the text's own size
            x = self._across(node.get("x"), x, props=sized)
            y = self._down(node.get("y"), y, props=sized)
            dx = self._across(node.get("dx"), props=sized)
            dy = self._down(node.get("dy"), props=sized)
            return x + dx, y + dy

        size = length(props.get("font-size"), 16.0)
        preserved = element.get(f"{{{XML_NAMESPACE}}}space") == "preserve"
        if preserved and re.search(r"\S {2,}\S", "".join(element.itertext())):
            self._skip(Note.PRESERVED_SPACES)
        shows = _visible_text(props)
        moved = Note.MOVED_WORDS
        lines: list[tuple[Point, Props, list[str]]] = [
            (
                placed(element, size, 0.0, 0.0),
                props,
                [_cased(element.text, props)] if shows else [],
            )
        ]
        # Hidden words keep their room in the browser; here the words after them move into it.
        after_hidden = not shows and bool((element.text or "").strip())
        for child in element:
            if _local(child) == "textPath":
                self._skip(Note.ELEMENT_LEFT_OUT, "textPath")
            elif _local(child) in ("tspan", "a"):
                ancestors = [*self.ancestors, element]
                child_props = computed_properties(child, props, self.rules, ancestors)
                before = "".join(lines[-1][2])
                pieces = self._text_pieces(child, child_props, ancestors, before)
                worded = [(words, style) for words, style in pieces if words.strip()]
                styles = [style for _, style in worded if style is not None]
                text = "".join(words for words, style in pieces if style is not None)
                if styles:
                    child_size = length(child_props.get("font-size"), 16.0)
                    if any(child.get(key) is not None for key in LINE_PLACEMENT):
                        if child.get("x") is None and "".join(lines[-1][2]).strip():
                            self._skip(Note.LINE_SHIFT)
                        anchor = placed(child, child_size, *lines[-1][0])
                        lines.append((anchor, styles[0], [text]))
                        after_hidden = False
                    else:
                        if text.strip() and not "".join(lines[-1][2]).strip():  # it starts the line
                            lines[-1] = (lines[-1][0], styles[0], lines[-1][2])
                        gap = self._across(child.get("dx"), props=child_props)
                        lines[-1][2].append(f" {text}" if gap > 0 else text)
                        if abs(gap) > child_size:
                            self._skip(Note.WIDE_GAP)
                    if not all(_same_text_style(style, lines[-1][1]) for style in styles):
                        self._skip(Note.STYLED_WORDS)
                    if after_hidden or _hidden_before_shown(worded):
                        self._skip(moved)
                elif text and not any(child.get(key) is not None for key in LINE_PLACEMENT):
                    # Visible separators contribute spacing without choosing the line style.
                    lines[-1][2].append(text)
                after_hidden = after_hidden or any(style is None for _, style in worded)
            tail = (child.tail or "").strip()
            if shows:
                if after_hidden and tail:
                    self._skip(moved)
                if tail and not "".join(lines[-1][2]).strip():
                    lines[-1] = (lines[-1][0], props, lines[-1][2])
                elif tail and not _same_text_style(lines[-1][1], props):
                    self._skip(Note.STYLED_WORDS)
                lines[-1][2].append(_cased(child.tail, props, "".join(lines[-1][2])))
            else:
                after_hidden = after_hidden or bool(tail)
        for anchor, line_props, parts in lines:
            align = _alignment(line_props.get("text-anchor", ""))
            paint = line_props.get("fill", "black")
            text = "".join(parts)
            unfilled = not _has_fill(line_props)
            if _has_line(line_props) and text.strip():
                if unfilled:
                    self._skip(Note.OUTLINED_TEXT)
                    paint = line_props["stroke"]
                    line_props = line_props | {
                        "fill-opacity": line_props.get("stroke-opacity", "1")
                    }
                    unfilled = False
                else:
                    self._skip(Note.TEXT_OUTLINE)
            if not unfilled:
                self._add_label(text, anchor, line_props, matrix, opacity, align, paint)

    def _text_pieces(
        self,
        node: ET.Element,
        props: Props,
        ancestors: list[ET.Element],
        before: str,
        faded: bool = False,
    ) -> list[tuple[str, Props | None]]:
        """A span's words in order, each with the style that shows it, or ``None`` when hidden.

        A span under ``display: none`` takes no room, so it has no pieces; a hidden one keeps
        its place in the line. ``before`` is the line's text ahead of the span. ``faded`` says
        an enclosing span has no opacity, which hides it all, as ``visibility`` cannot undo.
        """
        if props.get("display") == "none":
            return []
        self._note_text_effects(node, props)
        fade = length(props.get("opacity"), 1.0, percent_of=1.0)
        # A see-nothing span keeps its words' room but shows none of them, nor its children's.
        faded = faded or fade <= 0
        style = props if not faded and _visible_text(props) else None
        pieces: list[tuple[str, Props | None]] = [(_cased(node.text, props, before), style)]
        path = [*ancestors, node]
        for child in node:
            if _local(child) == "textPath":
                self._skip(Note.ELEMENT_LEFT_OUT, "textPath")
            ahead = before + "".join(words for words, _ in pieces)
            child_props = computed_properties(child, props, self.rules, path)
            drawn = _local(child) not in NOT_DRAWN and _local(child) != "textPath"
            inner = self._text_pieces(child, child_props, path, ahead, faded) if drawn else []
            placed = any(child.get(key) is not None for key in LINE_PLACEMENT)
            if placed and any(shown is not None and words.strip() for words, shown in inner):
                self._skip(Note.NESTED_LINE)
            elif self._across(child.get("dx"), props=child_props):
                self._skip(Note.NESTED_GAP)
            pieces += inner
            ahead = before + "".join(words for words, _ in pieces)
            pieces.append((_cased(child.tail, props, ahead), style))
        if any(shown is not None and words.strip() for words, shown in pieces):
            self._note_undrawn(props)
            if fade < 1:
                self._skip(Note.SEE_THROUGH_WORDS)
        return pieces

    def _foreign_object(
        self, element: ET.Element, props: Props, matrix: Matrix, opacity: float
    ) -> None:
        """Plain HTML text in a box wraps in SimpleDiagrams as it does in the browser."""
        embedded = ("img", "svg", "video", "canvas", "iframe")
        if any(_local(child) in embedded for child in element.iter()):
            self._skip(Note.FOREIGN_CONTENT)
            return
        x, y = self._place(element, props)
        w = self._across(element.get("width"), props=props)
        h = self._down(element.get("height"), props=props)
        if w <= 0 or h <= 0:
            return  # a viewport with no width or height shows nothing, as in a browser
        looks: set[tuple[object, ...]] = set()
        words, first_visible = self._html_text(element, props, list(self.ancestors), looks)
        if re.search(rf"\S\s*{LINE_BREAK}[\s{LINE_BREAK}]*\S", words):
            self._skip(Note.HTML_BREAKS)
        words = words.replace(LINE_BREAK, " ")
        if self._html_declares(element, props, list(self.ancestors), _paints_box):
            self._skip(Note.HTML_BOX)
        if self._html_declares(element, props, list(self.ancestors), _moves):
            self._skip(Note.CSS_TRANSFORM)
        if self._html_declares(element, props, list(self.ancestors), _pads):
            self._skip(Note.HTML_PADDING)
        # The text takes the style of the innermost single wrapper, usually one <div>; words
        # beside a wrapper make the text rich, and it keeps the style around them.
        holder, ancestors = element, list(self.ancestors)
        centred = False
        while (
            len(holder) == 1
            and _local(holder[0]) != "br"
            and (_is_invisible(props) or not _words_beside(holder))
        ):
            ancestors.append(holder)
            holder = holder[0]
            defaults = _html_defaults(holder, props)
            props = computed_properties(holder, props, self.rules, ancestors, defaults)
            layout = props.get("display", "").strip().startswith(HTML_LAYOUTS)
            centred = centred or (layout and self._declares(holder, ancestors, _aligns))
        if centred:
            self._skip(Note.HTML_LAYOUT)
        if first_visible is None:
            return
        if not _visible_html_text(props):
            props = first_visible
        if looks - {_html_look(props)}:
            self._skip(Note.RICH_HTML)
        align = _alignment(props.get("text-align", ""))
        wrap_box = (x, y, w, h) if w > 0 and h > 0 else None
        paint = props.get("color", "black")
        # HTML glyphs use CSS color and group opacity, independently of SVG fill opacity.
        self._add_label(
            words, (x, y), props | {"fill-opacity": "1"}, matrix, opacity, align, paint, wrap_box
        )

    def _html_text(
        self,
        element: ET.Element,
        props: Props,
        ancestors: list[ET.Element],
        looks: set[tuple[object, ...]],
        before: str = "",
    ) -> tuple[str, Props | None]:
        """Visible HTML words and the style of the first visible nonblank text.

        Block breaks and table-cell spaces are kept apart until the label is assembled.
        """
        shows = _visible_html_text(props)
        words = [_cased(element.text, props, before)] if shows else []
        first = props if shows and (element.text or "").strip() else None
        if first is not None:
            looks.add(_html_look(props))
        path = [*ancestors, element]
        flex = props.get("display", "").strip() in ("flex", "inline-flex")
        in_row = flex and not self._declares(element, ancestors, _stacks)  # items side by side
        for child in element:
            name = _local(child)
            defaults = _html_defaults(child, props)
            child_props = computed_properties(child, props, self.rules, path, defaults)
            display = child_props.get("display", "").strip()
            fade = length(child_props.get("opacity"), 1.0, percent_of=1.0)
            gone = child.get("hidden") is not None or display == "none" or fade <= 0
            if name == "br" and not gone:
                words.append(LINE_BREAK)
            elif name not in ("br", "style", "script") and not gone:
                cell = display == "table-cell" if display else name in ("td", "th")
                line = display.startswith(HTML_LINES) if display else name in HTML_LINE_TAGS
                gap = " " if cell or in_row else LINE_BREAK if line else ""
                ahead = before + "".join(words) + gap
                inner, inner_style = self._html_text(child, child_props, path, looks, ahead)
                if inner_style is not None:
                    self._note_undrawn(child_props)
                    if fade < 1:
                        self._skip(Note.SEE_THROUGH_WORDS)
                words += [gap, inner, gap]
                if first is None:
                    first = inner_style
            if shows:
                words.append(_cased(child.tail, props, before + "".join(words)))
                if (child.tail or "").strip():
                    looks.add(_html_look(props))
                    if first is None:
                        first = props
        return "".join(words), first

    def _use(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """An icon placed by reference becomes SVG artwork, painted as the placement paints it.

        Inside an icon being measured, a ``<use>`` is not followed: the stored copy cannot keep
        one, and following it could loop or multiply without end.
        """
        if self.measuring:
            self._skip(Note.ICON_UNSAFE)  # never kept in a copy
            return
        reference = element.get("href") or element.get(XLINK_HREF) or ""
        target = self.by_id.get(reference[1:]) if reference.startswith("#") else None
        if target is None:
            self._skip(Note.USE_OF_NOTHING)
            return
        parsed = parse_colour(props.get("color", "black"), props)
        solid = parsed is not None and parsed[3] >= 0.999  # else stored solid, as noted if used
        colour = colour_hex(parsed)[:7]
        context = _ComputedProperties(props | {"color": colour}, _custom_value_of(props))
        ancestors = self._ancestors_of(target)
        view = [float(v) for v in NUMBER_RE.findall(target.get("viewBox", ""))]
        framed = _local(target) in ("symbol", "svg") and len(view) == 4 and min(view[2:]) > 0
        if framed or _local(target) == "symbol":  # its children are copied, not the target
            context = computed_properties(target, context, self.rules, ancestors)
            if _local(target) == "svg" and context.get("display") == "none":
                return  # a hidden <svg> stays hidden where a <use> places it
            self._note_undrawn(context)  # the symbol's own effects, which no copy keeps
            ancestors = [*ancestors, target]
            # The symbol's own opacity layers on the placement's, as a group's would.
            opacity *= max(0.0, min(1.0, length(context.get("opacity"), 1.0, percent_of=1.0)))
        paint = {"color": colour} | ({"opacity": f"{opacity:g}"} if opacity < 1 else {})
        x, y = self._place(element, props)
        if framed:
            # A symbol or an svg draws its view box into the placement's width and height.
            # Its own paint, but not its effects (noted) nor its opacity (already in ``paint``).
            symbol_paint = PRESENTATION - UNDRAWN_NOTES.keys() - {"opacity"}
            painted = {k: v for k, v in target.attrib.items() if k in symbol_paint}
            if (size := painted.get("font-size")) is not None and not ABSOLUTE_SIZE.fullmatch(size):
                painted["font-size"] = context.get("font-size", INITIAL_VALUES["font-size"])
            font_size = length(context.get("font-size"), 16.0)
            for name in STROKE_LENGTHS:
                if (raw := painted.get(name)) is not None and _font_lengths_in_pixels(raw, font_size) != raw:
                    painted[name] = context.get(name, INITIAL_VALUES[name])
            if context.get("transform", "none").strip() != "none":  # set by a stylesheet too
                painted["transform"] = _attribute_transform(context["transform"])
            # Unsized, it takes the symbol's own size, or else the whole drawing's.
            width = element.get("width") or target.get("width") or "100%"
            height = element.get("height") or target.get("height") or "100%"
            w = self._across(width, view[2], props=props)
            h = self._down(height, view[3], props=props)
            icon = self._icon_copy(list(target), context, paint | painted, ancestors)
            if not solid and _uses_current_colour(icon.parts, painted):
                self._skip(Note.ICON_COLOUR)
            box = (view[0], view[1], view[2], view[3])
            frame = self._icon_frame((x, y, w, h), box, target)
            self._add_icon(box, icon, paint | painted, frame, matrix)
        else:
            parts = list(target) if _local(target) == "symbol" else [target]
            if (extent := self._extent(parts, context, ancestors)) is None:
                return
            if _local(target) == "symbol" and not _holds_text(target):  # its placement crops it
                w = self._across(element.get("width") or target.get("width") or "100%", props=props)
                h = self._down(element.get("height") or target.get("height") or "100%", props=props)
                self._note_overflow(extent, w, h, context)
            local = (x + extent[0], y + extent[1], extent[2], extent[3])
            icon = self._icon_copy(parts, context, paint, ancestors)
            if _sized_by_page([*icon.parts, *icon.shared], paint):
                self._skip(Note.ICON_VIEWPORT)
                return
            if not solid and _uses_current_colour(icon.parts, {}):
                self._skip(Note.ICON_COLOUR)
            if any(_holds_text(part) for part in icon.parts):
                self._skip(Note.ICON_TEXT_BOUNDS)
            self._add_icon(extent, icon, paint, local, matrix)

    def _nested_svg(
        self,
        element: ET.Element,
        props: Props,
        matrix: Matrix,
        opacity: float,
        ancestors: list[ET.Element],
    ) -> None:
        """A nested ``<svg>`` with a view box is an icon in its own frame, as a symbol is."""
        x, y = self._place(element, props)
        path = [*ancestors, element]
        view = [float(v) for v in NUMBER_RE.findall(element.get("viewBox", ""))]
        w = self._across(element.get("width"), self.viewport[0], props=props)
        h = self._down(element.get("height"), self.viewport[1], props=props)
        if w <= 0 or h <= 0:
            return  # a viewport with no width or height shows nothing, as in a browser
        if len(view) != 4 or view[2] <= 0 or view[3] <= 0:
            moved = multiply(matrix, (1, 0, 0, 1, x, y))
            outer, self.viewport = self.viewport, (w, h)  # its children's percentages are of it
            try:
                if not self.measuring and not _holds_text(element):  # text widths are estimated
                    self._note_overflow(self._extent(list(element), props, path), w, h, props)
                self._walk_group(element, props, moved, opacity, path)
            finally:
                self.viewport = outer
            return
        paint = {name: props[name] for name in sorted(ICON_PAINT & props.keys())}
        paint |= {k: props[k] for k in sorted(ICON_LINE & props.keys()) if props[k].strip()}
        paint.pop("opacity", None)  # already in ``opacity``, with the page's around it
        if opacity < 1:
            paint["opacity"] = f"{opacity:g}"
        icon = self._icon_copy(list(element), props, paint, path)
        box = (view[0], view[1], view[2], view[3])
        self._add_icon(box, icon, paint, self._icon_frame((x, y, w, h), box, element), matrix)

    def _place(self, element: ET.Element, props: Props) -> Point:
        """Where a ``<use>`` or nested ``<svg>`` places its content in the current viewport."""
        x = self._across(element.get("x"), props=props)
        return x, self._down(element.get("y"), props=props)

    def _across(self, value: str | None, default: float = 0.0, props: Props | None = None) -> float:
        """A horizontal length, a percentage of the viewport's width."""
        size = length((props or {}).get("font-size"), 16.0)
        return length(value, default, percent_of=self.viewport[0], font_size=size)

    def _down(self, value: str | None, default: float = 0.0, props: Props | None = None) -> float:
        """A vertical length, a percentage of the viewport's height."""
        size = length((props or {}).get("font-size"), 16.0)
        return length(value, default, percent_of=self.viewport[1], font_size=size)

    def _either(self, value: str | None, props: Props, default: float = 0.0) -> float:
        """An undirected SVG length resolves percentages against the normalized diagonal."""
        diagonal = math.hypot(*self.viewport) / math.sqrt(2)
        return length(
            value, default, percent_of=diagonal, font_size=length(props.get("font-size"), 16.0)
        )

    def _note_overflow(self, extent: Rect | None, w: float, h: float, props: Props) -> None:
        """Note drawing past a viewport with no view box, which a browser crops at its edges."""
        if extent is None or props.get("overflow", "hidden") in ("visible", "auto"):
            return
        left, top, width, height = extent
        reach = 2.0  # past the room ``_extent`` leaves around lines, so a crop shows
        if left < -reach or top < -reach or left + width > w + reach or top + height > h + reach:
            self._skip(Note.ICON_CROPPED)

    def _icon_frame(self, viewport: Rect, view: Rect, element: ET.Element) -> Rect:
        """An icon's frame inside its viewport, noting a crop the frame cannot show."""
        frame, cropped = fit_view_box(viewport, view, element.get("preserveAspectRatio"))
        if cropped:
            self._skip(Note.ICON_CROPPED)
        return frame

    def _add_icon(
        self, view: Rect, icon: IconCopy, paint: Props, local: Rect, matrix: Matrix
    ) -> None:
        """Add an icon as artwork, or note that it could not be stored; all hidden adds nothing."""
        if all(_local(item) in ICON_STRUCTURE for part in icon.parts for item in part.iter()):
            return
        if icon.clashes or (asset := svg_asset(view, icon.parts, paint, icon.shared)) is None:
            self._skip(Note.ICON_UNSAFE)
        else:
            self._add_artwork(local, matrix, asset)

    def _icon_copy(
        self, parts: Sequence[ET.Element], page: Props, paint: Props, ancestors: list[ET.Element]
    ) -> IconCopy:
        """Copies of icon markup, which is stored without the page's stylesheet.

        Definitions the icon paints with but does not hold, such as a gradient in the page's
        shared ``<defs>``, are copied too, styled as they are where they are defined.
        """
        stored = computed_properties(ET.Element("g", paint), {}, (), ())
        frozen = (self._frozen(part, page, stored, ancestors) for part in parts)
        copies = [copy for copy in frozen if copy is not None]
        held = _ids(copies)
        wanted = _references(copies, paint) - held
        shared: list[ET.Element] = []
        while wanted:
            name = min(wanted)  # a stable order, so an unchanged diagram re-exports byte for byte
            wanted.remove(name)
            if name in held or (definition := self.by_id.get(name)) is None:
                continue  # a reference to nothing paints nothing in the browser either
            inherited, path = self._context_of(definition)
            if (copy := self._frozen(definition, inherited, {}, path)) is not None:
                shared.append(copy)
                held |= _ids([copy])
                wanted |= _references([copy], {}) - held
        # An id the page resolves to another element would make the copy paint that one's twin.
        owned = (item for part in parts for item in part.iter() if item.get("id"))
        clashes = any(self.by_id.get(item.get("id", "")) is not item for item in owned)
        return IconCopy(copies, shared, clashes)

    def _ancestors_of(self, element: ET.Element) -> list[ET.Element]:
        """The original definition's ancestors, including the HTML context if present."""
        path = []
        node = self.parents.get(element)
        while node is not None:
            path.append(node)
            node = self.parents.get(node)
        return [*self.page_ancestors, *reversed(path)]

    def _context_of(self, element: ET.Element) -> tuple[Props, list[ET.Element]]:
        """What an element inherits where it sits on the page, and its ancestors, root first."""
        path = self._ancestors_of(element)
        inherited = self.root_inherited
        for depth in range(len(self.page_ancestors), len(path)):
            inherited = computed_properties(path[depth], inherited, self.rules, path[:depth])
        return inherited, path

    def _frozen(
        self,
        element: ET.Element,
        inherited: Props,
        stored: Props,
        ancestors: list[ET.Element],
        text_runs: list[tuple[str, Props | None]] | None = None,
        text_visible: bool = True,
    ) -> ET.Element | None:
        """Copy one element for a stored icon; ``None`` when nothing of it shows.

        The app's renderer ignores ``display`` and ``visibility``, so what they hide is left out.
        """
        page = computed_properties(element, inherited, self.rules, ancestors)
        if page.get("display") == "none":
            return None
        self._note_css_geometry(element, ancestors)
        tag = _local(element)
        for name in ("filter", "mix-blend-mode"):
            if page.get(name, "none").strip().lower() not in {"none", "normal"}:
                self._skip(UNDRAWN_NOTES[name])
        if tag in {"text", "tspan"} and _uses_vertical_text(page):
            self._skip(Note.VERTICAL_TEXT)
        if tag in {"text", "tspan"} and any(
            float(value) != 0 for name in ("dx", "dy") for value in NUMBER_RE.findall(element.get(name, ""))
        ):
            self._skip(Note.ICON_TEXT_OFFSETS)
        if tag in {"text", "tspan"} and any(
            _cased(words, page) != (words or "") for words in (
                element.text, *(child.tail for child in element)
            )
        ):
            self._skip(Note.ICON_TEXT_CASE)
        if (
            tag in {"line", "path", "polyline", "polygon", "rect", "circle", "ellipse"}
            and any(self._marker(page.get(name)) is not None for name in ("marker-start", "marker-mid", "marker-end"))
        ):
            self._skip(Note.ICON_MARKERS)
        if tag == "text":
            text_runs = []
        elif tag in NOT_DRAWN:
            text_runs = None
        text_visible = text_visible and _opacity(page.get("opacity")) > 0
        removed = _is_invisible(page)
        shown = text_visible and _visible_text(page) if text_runs is not None else False

        def record(words: str | None) -> None:
            if text_runs is not None and words and words.strip() and (removed or shown):
                text_runs.append((words, None if removed else page))

        record(element.text)
        clone, stored = _styled_clone(element, page, stored)
        path = [*ancestors, element]
        for child in element:
            if (copy := self._frozen(child, page, stored, path, text_runs, text_visible)) is not None:
                clone.append(copy)
            else:
                _keep_words_after_removed_child(clone, child.tail)
            record(child.tail)
        if tag == "text" and text_runs is not None and _hidden_before_shown(text_runs):
            self._skip(Note.MOVED_WORDS)
        if not _is_invisible(page):
            return clone
        draws = _local(element) in self.handlers or _local(element) in CONTAINERS
        inside = (item for child in clone for item in child.iter())
        if draws and all(_local(item) in ICON_STRUCTURE for item in inside):
            return None  # a hidden gradient or marker, by contrast, still paints what uses it
        clone.text = None  # only children that show themselves remain, without the words between
        for child in clone:
            child.tail = None
        return clone

    def _extent(
        self, parts: Sequence[ET.Element], props: Props, ancestors: list[ET.Element]
    ) -> Rect | None:
        """The bounds of drawing that has no view box of its own, with room for its lines.

        ``props`` and ``ancestors`` are those the stored copy is made with, so a symbol's own
        styling, such as its font size, sizes the frame as it sizes the copy.
        """
        saved, measuring, held_back = self.items, self.measuring, self.held_back
        self.items, self.measuring, self.held_back = [], True, set()
        for part in parts:
            self._walk(part, props, IDENTITY, 1.0, ancestors)
        drawn, noted = self.items, self.held_back
        self.items, self.measuring, self.held_back = saved, measuring, held_back
        points = [point for item in drawn for point in _drawn_points(item)]
        if not points:
            for note, element in sorted(noted):  # nothing is stored, so its losses are noted here
                self._skip(note, element)
            return None
        left, top, right, bottom = bounds(points)
        lines = [item.paint.line_width / 2 for item in drawn if isinstance(item, (Box, Stroke))]
        markers = [item.reach for item in drawn if isinstance(item, Stroke)]
        pad = max(lines + markers, default=0.0) + 0.5
        return left - pad, top - pad, right - left + 2 * pad, bottom - top + 2 * pad

    def _add_artwork(self, local: Rect, matrix: Matrix, asset: Asset) -> None:
        """Add a picture in its frame; a skewed or empty one cannot be shown."""
        placed, turn = placed_frame(local, matrix), decompose(matrix)
        if placed is None or turn is None or local[2] <= 0 or local[3] <= 0:
            self._skip(Note.PICTURE_SKEWED)
            return
        self.items.append(Artwork(len(self.items), *placed, asset, turn[3]))

    def _add_label(
        self,
        raw: str,
        anchor: Point,
        props: Props,
        matrix: Matrix,
        opacity: float,
        align: Alignment,
        paint: str,
        wrap_box: Rect | None = None,
    ) -> None:
        """Add one line of text, styled as the SVG styles it."""
        if not (string := re.sub(r"\s+", " ", raw).strip()):
            return
        turn = decompose(matrix)
        if turn is None or not math.isclose(turn[1], turn[2]) or turn[3] != (False, False):
            self._skip(Note.TEXT_DISTORTED)
        raw_size = length(props.get("font-size"), 16.0)
        if raw_size <= 0:
            return
        size = max(1.0, raw_size)
        if not 1 <= raw_size * (turn[2] if turn else 1.0) <= 720:
            self._skip(Note.TEXT_SIZE)
        text_opacity = opacity * _paint_opacity(props, "fill")
        style = TextStyle(
            font_family=_font_family(props.get("font-family")),
            font_size=size * (turn[2] if turn else 1.0),
            weight=_weight(props),
            italic=props.get("font-style", "") in ("italic", "oblique"),
            underlined="underline" in props.get("text-decoration", ""),
            colour=colour_hex(self._colour(paint, props), text_opacity),
        )
        spacing = length(props.get("letter-spacing"), font_size=size)
        self.items.append(
            Label(
                len(self.items),
                string,
                anchor,
                matrix,
                align,
                style,
                size,
                spacing,
                wrap_box,
            )
        )


def _alignment(value: str) -> Alignment:
    """A ``text-anchor`` or ``text-align`` value as a text alignment."""
    if value in ("middle", "center"):
        return "center"
    return "trailing" if value in ("end", "right") else "leading"


HTML_LINE_TAGS = frozenset(
    {"div", "p", "li", "ul", "ol", "table", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "header",
     "footer", "section", "article", "aside", "nav", "main", "figure", "figcaption", "dl", "dt",
     "dd", "pre", "hr", "blockquote", "address", "details", "summary", "fieldset", "legend",
     "form", "hgroup"}
)  # fmt: skip
# Above: the elements a browser starts on a line of their own.
HTML_LINES = ("block", "flex", "grid", "list-item", "table")  # displays that start a line
LINE_BREAK = "\u2028"  # where HTML text starts a line, unlike a newline in its source
HTML_LAYOUTS = ("flex", "grid", "inline-flex", "inline-grid")  # place text by rules not read here
HTML_ALIGNING = frozenset(
    {"align-items", "align-content", "align-self", "justify-content", "justify-items",
     "place-items", "place-content"}
)  # fmt: skip
HEADING_SIZES = {"h1": 2.0, "h2": 1.5, "h3": 1.17, "h4": 1.0, "h5": 0.83, "h6": 0.67}


def _html_defaults(element: ET.Element, inherited: Props) -> Props:
    """A browser's own styles for an HTML element, beneath any the page declares."""
    name = _local(element)
    defaults: Props = {}
    if name in ("b", "strong"):
        defaults["font-weight"] = "bolder"
    elif name == "th" or name in HEADING_SIZES:
        defaults["font-weight"] = "bold"
    if name in ("em", "i"):
        defaults["font-style"] = "italic"
    if name == "a" and element.get("href") is not None:
        defaults |= {"color": "#0000EE", "text-decoration": "underline"}
    if name in HEADING_SIZES:
        size = length(inherited.get("font-size"), 16.0) * HEADING_SIZES[name]
        defaults["font-size"] = f"{size:g}"
    return defaults


def _cased(words: str | None, props: Props, before: str = "") -> str:
    """Words in the case ``text-transform`` gives them; each span may give its own.

    ``before`` is the text ahead of them, so a word split across spans keeps one capital.
    """
    match props.get("text-transform", "").strip():
        case "uppercase":
            return (words or "").upper()
        case "lowercase":
            return (words or "").lower()
        case "capitalize":
            lead = before[-1:]
            capitalised = re.sub(
                r"(?<![\w'’])\w", lambda m: m.group(0).upper(), lead + (words or "")
            )
            return capitalised[len(lead) :]
    return words or ""


def _weight(props: Props) -> Literal["regular", "medium", "bold"]:
    """The SimpleDiagrams weight a settled ``font-weight``, a number, comes closest to."""
    weight = length(props.get("font-weight"), 400.0)
    return "bold" if weight >= 600 else "medium" if weight >= 500 else "regular"


def _html_look(props: Props) -> tuple[object, ...]:
    """What a SimpleDiagrams label can show of an HTML text style, however it is spelled."""
    return (
        round(length(props.get("font-size"), 16.0), 2),
        _weight(props),
        props.get("font-style", "") in ("italic", "oblique"),
        "underline" in props.get("text-decoration", ""),
        parse_colour(props.get("color", "black"), props),
        _font_family(props.get("font-family")),
    )


def _moves(name: str, value: str) -> bool:
    """Whether an HTML declaration moves its box from where the layout puts it."""
    return (name == "transform" or name in INDIVIDUAL_TRANSFORMS) and value.strip() != "none"


def _pads(name: str, value: str) -> bool:
    """Whether an HTML declaration pads its box's content away from the edge."""
    return name.startswith("padding") and length(value.removesuffix(IMPORTANT)) != 0


def _moves_alone(name: str, value: str) -> bool:
    """Whether a declaration moves an SVG element with a property only CSS has."""
    return name in INDIVIDUAL_TRANSFORMS and value.strip() != "none"


def _stacks(name: str, value: str) -> bool:
    """Whether a flex declaration stacks its items in a column rather than a row."""
    return name in ("flex-direction", "flex-flow") and "column" in value


def _aligns(name: str, value: str) -> bool:
    """Whether a flex or grid declaration moves text from the top-left corner."""
    return name in HTML_ALIGNING and any(word in value for word in ("center", "end"))


def _words_beside(holder: ET.Element) -> bool:
    """Whether words sit beside an element's one child, so the text mixes styles."""
    return bool((holder.text or "").strip() or (holder[0].tail or "").strip())


def _heading(points: Sequence[Point], *, at_start: bool) -> float | None:
    """The way a line runs at one end, in degrees; ``None`` when it has no length there."""
    if len(points) < 2:
        return None
    (x1, y1), (x2, y2) = (points[0], points[1]) if at_start else (points[-2], points[-1])
    if math.isclose(x1, x2) and math.isclose(y1, y2):
        return None
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _marker_axis(orient: str | None, heading: float, at_start: bool) -> float:
    """The way a marker's x-axis points, in degrees, as its ``orient`` turns it."""
    value = (orient or "0").strip()
    if value == "auto":
        return heading
    if value == "auto-start-reverse":
        return heading + 180 * at_start
    match = re.fullmatch(rf"({NUMBER})(deg|rad|grad|turn)?", value)
    if match is None:
        return 0.0  # an unreadable angle is no turn, as in SVG
    degrees_per = {"rad": 180 / math.pi, "grad": 0.9, "turn": 360.0}.get(match.group(2) or "", 1.0)
    return float(match.group(1)) * degrees_per


def _is_hole(
    subpath: Subpath,
    own: Sequence[Point],
    extent: Bounds,
    outlines: Sequence[tuple[Subpath, list[Point], Bounds]],
    props: Props,
) -> bool:
    """Whether an implicitly closed contour cuts an empty hole in a filled path, under its fill rule.

    Only a contour wholly inside others can be a hole; one that merely overlaps them adds
    its own area to the fill.
    """
    left, top, right, bottom = extent
    around = [
        flat
        for other, flat, (x1, y1, x2, y2) in outlines
        if other is not subpath
        and x1 <= left and y1 <= top and x2 >= right and y2 >= bottom
        and all(point_in_polygon(point, flat) for point in own)
    ]
    if not around:
        return False
    if props.get("fill-rule", "nonzero").strip().lower() == "evenodd":
        return len(around) % 2 == 1
    winding = sum(1 if signed_area(flat) > 0 else -1 for flat in [*around, own])
    return winding == 0  # nonzero: the region inside it is left unpainted


def _hidden_before_shown(worded: Sequence[tuple[str, Props | None]]) -> bool:
    """Whether hidden words come before shown ones, which then move into their room."""
    first = next((i for i, (_, style) in enumerate(worded) if style is None), None)
    return first is not None and any(style is not None for _, style in worded[first:])


def _drawn_points(item: Drawn) -> list[Point]:
    """Points bounding what an item draws, before the width of its lines."""
    if isinstance(item, (Box, Stroke)):  # the hull of its control points holds every curve
        return [item.subpath.start, *(point for part in item.subpath.segments for point in part)]
    if isinstance(item, Label):
        left, top, right, bottom = item.page_bounds()
        return [(left, top), (right, bottom)]
    return _frame_corners(item.frame, item.rotation)


def _overlapping(items: Sequence[Drawn]) -> bool:
    """Whether the drawn bounds of two items may overlap, including stroke widths."""
    extents = []
    for item in items[: OVERLAP_CHECK_LIMIT + 1]:
        left, top, right, bottom = bounds(_drawn_points(item))
        radius = item.paint.line_width / 2 if isinstance(item, (Box, Stroke)) else 0
        extents.append((left - radius, top - radius, right + radius, bottom + radius))
    return _bounds_overlap(extents)


def _intersects_bounds(a: Bounds, b: Bounds) -> bool:
    """Whether the two bounds overlap with positive area."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _bounds_overlap(extents: Sequence[Bounds]) -> bool:
    """Whether two bounds may intersect, conservatively warning beyond the work limit."""
    if len(extents) > OVERLAP_CHECK_LIMIT:
        return True
    return any(_intersects_bounds(a, b) for a, b in itertools.combinations(extents, 2))


def _frame_corners(frame: Rect, rotation: float) -> list[Point]:
    """The four corners of a frame turned about its centre."""
    x, y, w, h = frame
    turn = math.radians(rotation)
    cx, cy, cos, sin = x + w / 2, y + h / 2, math.cos(turn), math.sin(turn)
    return [
        (cx + dx * cos - dy * sin, cy + dx * sin + dy * cos)
        for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))
    ]


def _sized_by_page(parts: Sequence[ET.Element], paint: Props) -> bool:
    """Whether unframed artwork uses percentages that would change in its cropped viewport."""
    box_units = {
        "linearGradient": "gradientUnits",
        "radialGradient": "gradientUnits",
        "mask": "maskUnits",
        "pattern": "patternUnits",
    }
    if any("%" in paint.get(name, "") for name in STROKE_LENGTHS):
        return True
    for part in parts:
        for item in part.iter():
            # Percentages in a paint server's bounding-box region keep the same meaning.
            unit = box_units.get(_local(item))
            names = (
                ICON_GEOMETRY_LENGTHS.union(STROKE_LENGTHS)
                if unit is None or item.get(unit) == "userSpaceOnUse"
                else STROKE_LENGTHS
            )
            if any("%" in item.get(name, "") for name in names):
                return True
    return False


def _ids(parts: Sequence[ET.Element]) -> set[str]:
    """Every ``id`` in some markup."""
    return {name for part in parts for item in part.iter() if (name := item.get("id"))}


def _attribute_values(parts: Sequence[ET.Element], paint: Props) -> list[str]:
    """Every attribute value in stored icon markup, with the paint of the group around it."""
    return [
        *paint.values(),
        *(v for part in parts for item in part.iter() for v in item.attrib.values()),
    ]


def _references(parts: Sequence[ET.Element], paint: Props) -> set[str]:
    """Every local ``url(#…)`` that markup, or the paint around it, refers to."""
    return {name for value in _attribute_values(parts, paint) for name in LOCAL_URL.findall(value)}


def _uses_current_colour(parts: Sequence[ET.Element], paint: Props) -> bool:
    """Whether stored icon markup paints with ``currentColor``, which its placement sets."""
    return any("currentcolor" in value.lower() for value in _attribute_values(parts, paint))


def _text_look(props: Props) -> tuple[object, ...]:
    """What a style draws words with: the fill as a colour, and its settled font."""
    fill = props.get("fill", "black")
    paint: object = parse_colour(fill, props)
    if isinstance(paint, tuple):
        alpha = length(props.get("fill-opacity"), 1.0, percent_of=1.0)
        paint = (*paint[:3], round(paint[3] * max(0.0, min(1.0, alpha)), 3))
    else:
        paint = fill.strip().lower()  # a gradient or an unread colour compares as written
    others = (props.get(name, INITIAL_VALUES.get(name)) for name in TEXT_STYLE if name != "fill")
    return (paint, *others)


def _holds_text(element: ET.Element) -> bool:
    """Whether an element holds text, whose drawn width this export only estimates."""
    return any(_local(item) in ("text", "foreignObject") for item in element.iter())


def _same_text_style(one: Props, other: Props) -> bool:
    """Whether two styles draw words alike, as far as one SimpleDiagrams line can show."""
    return _text_look(one) == _text_look(other)


def _paints_box(name: str, value: str) -> bool:
    """Whether an HTML declaration paints a background, border, outline or shadow."""
    plain = value.removesuffix(IMPORTANT).strip().lower()
    if name not in HTML_BOX_PAINT or not plain:
        return False
    if (colour := parse_colour(plain, {})) is not None:
        return colour[3] > 0
    words = plain.split()
    if NO_HTML_BOX_PAINT.intersection(words):
        return False
    lined = name.startswith(("border", "outline"))
    return not (lined and any(ZERO_WIDTH.fullmatch(word) for word in words))


def _font_family(value: str | None) -> str | None:
    """The first named family; generic names fall back to the system font."""
    for family in (value or "").split(","):
        # A font name may hold no control or format characters at all.
        name = _clip_utf8(family.strip().strip("'\"").strip(), MAX_FONT_FAMILY_BYTES, ("Cc", "Cf"))
        if name and name.lower() not in GENERIC_FONTS:
            return name
    return None


# --------------------------------------------------------------------------
# Arranging: labels onto boxes, lines onto boxes, decorations into groups
# --------------------------------------------------------------------------


def arrange(items: Sequence[Drawn], paper: str) -> list[Swimlanes]:
    """Decide what each item becomes, so the diagram stays editable.

    * A **container** is a box holding a separate node-sized box: a zone, a
      lane, a panel. Nothing folds into it and nothing groups with it, because
      what it holds moves on its own. A box flush with two of its edges (a
      card's header band) is part of it, not held by it.
    * A label folds into the smallest box it sits on when it continues that
      box's text: the same alignment, at ordinary line spacing. Anything else
      (a table's rows, a corner numeral) stays free text exactly in place.
    * Lanes drawn as dividers with a title column become one Swimlanes shape.
    * A line becomes a connector when it has an arrowhead, or runs straight or
      square between two different boxes, as a relationship line does. Its ends
      attach to the boxes they touch. A curve without an arrowhead, such as an
      edge in a 3D drawing, stays a line.
    * An outline recognised as a Basic shape stays one only when it is labelled
      or an arrow ends on it, as a diagram's nodes are.
    * Everything else drawn on a box (a tag, a numeral, a divider) is hosted by
      that box, and the two are grouped.

    Attaching runs last, before anything is written, because it can add a
    connection point to a box and so must follow every change to its frame.

    The items are updated in place: their ``kind`` and ``host``, a box's
    ``labels`` and ``points``, and a stroke's ends and ``label``.

    Returns:
        The Swimlanes shapes found, which are written alongside the items.
    """
    boxes = [item for item in items if isinstance(item, Box)]
    containers = _containers(boxes)
    hosts = Hosts(boxes, containers)
    labels = [item for item in items if isinstance(item, Label)]
    _fold_labels(labels, hosts, items)

    strokes = [item for item in items if isinstance(item, Stroke)]
    swimlanes = find_swimlanes(strokes, [label for label in labels if label.kind == "text"])
    lane_lines = {id(line) for shape in swimlanes for line in shape.dividers}
    strokes = [stroke for stroke in strokes if id(stroke) not in lane_lines]
    connections = _classify_strokes(strokes, boxes, hosts)
    for artwork in (item for item in items if isinstance(item, Artwork)):
        artwork.kind, artwork.host = (
            "artwork",
            hosts.of([artwork.centre], artwork.order, artwork.area),
        )

    for box in boxes:
        box.kind, box.host = "box", hosts.of([box.centre], box.order, box.area)
    occupied = {id(item.host) for item in items if item.kind and item.host is not None}
    _settle_boxes(boxes, containers, occupied, connections, paper)

    for stroke, start, end in connections:
        flat = stroke.subpath.flattened()
        stroke.start = Attachment(start, start.point_id_for(flat[0])) if start else None
        stroke.end = Attachment(end, end.point_id_for(flat[-1])) if end else None
    return swimlanes


Connection: TypeAlias = tuple[Stroke, Box | None, Box | None]  # a connector and its ends' boxes


class Hosts:
    """Finds the box something is drawn on: the smallest box drawn before it, not a container."""

    def __init__(self, boxes: Sequence[Box], containers: set[int]) -> None:
        """Consider every box that is not a container."""
        self.boxes = [box for box in boxes if id(box) not in containers]

    def of(self, points: Sequence[Point], order: int, larger_than: float = 0.0) -> Box | None:
        """The smallest box drawn before ``order`` that holds every point and is large enough."""
        candidates = [
            box
            for box in self.boxes
            if box.order < order and box.area > larger_than and all(map(box.holds, points))
        ]
        return min(candidates, key=attrgetter("area"), default=None)


def _containers(boxes: Sequence[Box]) -> set[int]:
    """The boxes holding a separate node-sized box, by ``id``."""
    return {
        id(outer)
        for outer in boxes
        for inner in boxes
        if inner is not outer
        and inner.area < outer.area
        and outer.near(inner.centre, 0)
        and _is_node_sized(inner, outer)
        and _shared_edges(inner, outer) < 2
        and point_in_polygon(inner.centre, outer.outline)
    }


def _fold_labels(labels: Sequence[Label], hosts: Hosts, items: Sequence[Drawn]) -> None:
    """Fold each label into the box whose text it continues; the rest become free text.

    A label stays free when a line or shape drawn between its box and itself crosses it:
    folded in, it would be drawn with the box, beneath what the page draws over it.
    """
    # A box's text is read from its top line down, whatever order the SVG drew it in.
    for label in reading_order(labels):
        on = hosts.of([label.centre], label.order)
        if on is not None and _folds_into(label, on) and not _covered(label, on, items):
            on.labels.append(label)
        else:
            label.kind, label.host = "text", on
    for box in hosts.boxes:  # a custom outline can only hold its label in the middle
        extents = [label.page_bounds() for label in box.labels]
        if extents and box.basic is None and not _is_centred(_union(extents), box.frame):
            for label in box.labels:
                label.kind, label.host = "text", box
            box.labels.clear()


def _covered(label: Label, box: Box, items: Sequence[Drawn]) -> bool:
    """Whether something plainly visible, drawn after a box and before its label, crosses the
    middle of the label: a line through the words, not a faint tint or a tag at its edge."""
    left, top, right, bottom = label.page_bounds()
    inset_x, inset_y = (right - left) * 0.15, (bottom - top) * 0.3
    left, right, top, bottom = left + inset_x, right - inset_x, top + inset_y, bottom - inset_y
    for item in items:
        if not box.order < item.order < label.order:
            continue
        if isinstance(item, Artwork):  # a picture may hide the words if they move below it
            a, b, w, h = item.frame  # unturned, which is close enough to keep the words above
            if a < right and a + w > left and b < bottom and b + h > top:
                return True
            continue
        if not isinstance(item, (Box, Stroke)):
            continue
        lined = item.paint.line_width > 0 and item.paint.stroke != TRANSPARENT
        fill = parse_colour(item.paint.fill, {})
        if not lined and (fill is None or fill[3] < 0.5):
            continue
        outline = item.outline if isinstance(item, Box) else item.subpath.flattened()
        a, b, c, d = bounds(outline)
        pad = item.paint.line_width / 2
        if a - pad < right and c + pad > left and b - pad < bottom and d + pad > top:
            return True
    return False


def _classify_strokes(
    strokes: Sequence[Stroke], boxes: Sequence[Box], hosts: Hosts
) -> list[Connection]:
    """Mark the connectors and return them with the boxes they touch; the rest are lines."""
    connections: list[Connection] = []
    for stroke in strokes:
        flat = stroke.subpath.flattened()
        others = [box for box in boxes if box is not stroke.fill]  # never its own fill
        start = _touching(others, flat[0], marked=stroke.marked)
        end = _touching(others, flat[-1], marked=stroke.marked)
        joins = (
            start is not None
            and end is not None
            and start is not end
            and right_angle_route(stroke.subpath) is not None
        )
        if stroke.marked or joins:
            stroke.kind = "connector"
            connections.append((stroke, start, end))
        else:
            stroke.kind, stroke.host = "line", hosts.of([flat[0], flat[-1]], stroke.order)
    return connections


def _settle_boxes(
    boxes: Sequence[Box],
    containers: set[int],
    occupied: set[int],
    connections: Sequence[Connection],
    paper: str,
) -> None:
    """Decide which boxes keep their Basic shape, which label a connector, and their hosts.

    A recognised Basic shape stands for a diagram node: something labelled, or
    an arrow's end. Anywhere else, such as the faces of a 3D drawing joined by
    plain edges, the outline is kept exactly.
    """
    ended = [(stroke, box) for stroke, *ends in connections for box in ends if box is not None]
    connected = {id(box) for stroke, box in ended if stroke.marked}
    attached = {id(box) for _, box in ended}
    # An arrow's label box stands on its own: never attached to, holding or drawn on a shape.
    free_standing = [
        box
        for box in boxes
        if id(box) not in attached
        and id(box) not in containers
        and id(box) not in occupied
        and box.host is None
    ]
    plain = [box for box in free_standing if box.paint.fill in (TRANSPARENT, paper)]
    labelling = _label_connectors(plain, [stroke for stroke, _, _ in connections])
    for box in boxes:
        if id(box) in labelling:
            box.kind = ""  # drawn as its connector's label
        elif box.matched and not box.labels and id(box) not in connected:
            box.keep_exact()


def _label_connectors(boxes: Sequence[Box], connectors: Sequence[Stroke]) -> set[int]:
    """Give each connector the label the skill draws beside it; return the boxes used.

    An arrow's label is text on a small box with no outline, in the paper colour,
    beside or over its line. As the connector's own label it stays on the line
    when either end moves.
    """
    used: set[int] = set()
    for box in boxes:
        tallest = max((label.style.font_size for label in box.labels), default=0.0)
        if not tallest or box.paint.line_width > 0 or box.frame[3] > LABEL_BOX_HEIGHT * tallest:
            continue
        edge = densified(box.outline, 4)
        nearby = [
            (min(along(line, point).distance for point in edge), stroke)
            for stroke in connectors
            if stroke.label is None and (line := stroke.subpath.flattened())
        ]
        gap, nearest = min(nearby, key=lambda pair: pair[0], default=(math.inf, None))
        if nearest is not None and gap <= LABEL_REACH:  # the skill leaves a small gap
            nearest.label = box
            used.add(id(box))
    return used


def _over(top: str, base: str) -> str:
    """One fill for ``top`` painted over ``base``, composited as the browser does."""
    upper, lower = parse_colour(top, {}), parse_colour(base, {})
    if upper is None or lower is None:
        return top
    alpha = upper[3] + lower[3] * (1 - upper[3])
    if alpha <= 0:
        return TRANSPARENT
    red, green, blue = (
        round((u * upper[3] + v * lower[3] * (1 - upper[3])) / alpha)
        for u, v in zip(upper[:3], lower[:3], strict=True)
    )
    return colour_hex((red, green, blue, alpha))


def _same_place(below: Box, above: Box) -> bool:
    """Whether two boxes are the same shape in the same place, one painted over the other."""
    if (below.basic, below.rotation, below.flips) != (above.basic, above.rotation, above.flips):
        return False
    if any(abs(a - b) > 0.5 for a, b in zip(below.extent, above.extent, strict=True)):
        return False
    return (
        _outline_gap(densified(below.outline), above.outline, 0.5) is not None
        and _outline_gap(densified(above.outline), below.outline, 0.5) is not None
    )


def _is_node_sized(inner: Box, outer: Box) -> bool:
    """Whether a box inside another is big enough to be a node of its own, not a tag."""
    big_enough = inner.frame[2] >= NODE_SIZE[0] and inner.frame[3] >= NODE_SIZE[1]
    return inner.area >= outer.area * NODE_SHARE or big_enough


def _shared_edges(inner: Box, outer: Box) -> int:
    """How many of the outer frame's four edges the inner frame runs along."""
    (ix, iy, iw, ih), (ox, oy, ow, oh) = inner.frame, outer.frame
    pairs = ((ix, ox), (iy, oy), (ix + iw, ox + ow), (iy + ih, oy + oh))
    return sum(abs(a - b) <= FLUSH_TOLERANCE for a, b in pairs)


def _union(extents: Sequence[Extent]) -> Extent:
    """The bounds around several page bounds."""
    left, top, right, bottom = zip(*extents, strict=True)
    return min(left), min(top), max(right), max(bottom)


def _is_centred(extent: Extent, frame: Rect) -> bool:
    """Whether text with these page bounds sits in the middle of a box's frame."""
    left, top, right, bottom = extent
    x, y, w, h = frame
    return (
        abs((left + right) / 2 - (x + w / 2)) <= w * CENTRED_SHARE[0]
        and abs((top + bottom) / 2 - (y + h / 2)) <= h * CENTRED_SHARE[1]
    )


def _folds_into(label: Label, box: Box) -> bool:
    """A label becomes part of a box's own text when it continues the text already there."""
    if not label.upright or box.rotation != 0:
        return False
    if not box.labels:
        return True
    first, last = box.labels[0], box.labels[-1]
    x, y = label.page_anchor
    line_gap = LINE_SPACING * max(label.style.font_size, last.style.font_size)
    return (
        first.align == label.align
        and first.wrap_box is None
        and label.wrap_box is None
        and abs(first.page_anchor[0] - x) <= ALIGN_TOLERANCE
        and 0 < y - last.page_anchor[1] <= line_gap
    )


def _decorative_inset(inner: Bounds, outer: Bounds) -> bool:
    """Whether an inner outline closely follows all four sides of its visible border."""
    x1, y1, x2, y2 = inner
    left, top, right, bottom = outer
    return all(
        -0.001 <= gap <= ATTACH_TOLERANCE for gap in (x1 - left, y1 - top, right - x2, bottom - y2)
    )


def _touching(boxes: Sequence[Box], point: Point, *, marked: bool) -> Box | None:
    """Prefer direct contact for authored arrows, keeping an overlapping inset as one target."""

    def reach(box: Box) -> float:
        """How near a line end attaches, including the width of the box's stroke."""
        return ATTACH_TOLERANCE + box.paint.line_width / 2

    near = [
        (distance, box)
        for box in boxes
        if box.near(point, reach(box))
        and (distance := distance_to_outline(point, box.outline)) <= reach(box)
    ]
    if not near:
        return None
    smallest = min(near, key=lambda candidate: candidate[1].area)[1]
    if marked:
        # A nearby annotation should not steal an arrow that touches a node.
        # A close inset on all sides can be the labeled face of the same node.
        direct = [
            (distance, box)
            for distance, box in near
            if distance <= 0.5
            and (box is smallest or not _decorative_inset(smallest.extent, box.extent))
        ]
        if direct:
            return min(direct, key=lambda candidate: (candidate[0], candidate[1].area))[1]
    return smallest


class Along(NamedTuple):
    """Where a point lies beside an open line."""

    distance: float  # from the line
    share: float  # how far along the line its nearest place is, from 0 to 1
    offset: float  # to the right of the direction of travel, negative to the left


def along(line: Sequence[Point], point: Point) -> Along:
    """Project a point onto an open line drawn through ``line``'s points."""
    lengths = [math.dist(a, b) for a, b in itertools.pairwise(line)]
    total = sum(lengths) or 1.0
    best, travelled = Along(math.inf, 0.0, 0.0), 0.0
    for (a, b), size in zip(itertools.pairwise(line), lengths, strict=True):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = 0.0 if size == 0 else ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / size**2
        t = max(0.0, min(1.0, t))
        foot = (a[0] + t * dx, a[1] + t * dy)
        if (distance := math.dist(point, foot)) < best.distance:
            # (-dy, dx) points to the right of travel on a page whose y grows downwards.
            side = ((point[0] - foot[0]) * -dy + (point[1] - foot[1]) * dx) / size if size else 0.0
            best = Along(distance, (travelled + t * size) / total, side)
        travelled += size
    return best


# --------------------------------------------------------------------------
# Recognising swimlanes
# --------------------------------------------------------------------------


class Rule(NamedTuple):
    """A single straight segment in lane space: its span along its length, and where it lies."""

    start: float
    end: float
    at: float  # where it lies, across its own length
    stroke: Stroke


def find_swimlanes(strokes: Sequence[Stroke], labels: Sequence[Label]) -> list[Swimlanes]:
    """Find lanes as the skill draws them, in either direction.

    That is three or more plain parallel dividers of one length, at least a
    lane's thickness apart, a title column divided off across them, and a title
    in every lane. Requiring all of this keeps a chart's gridlines out.
    """
    found: list[Swimlanes] = []
    used: set[int] = set()
    for vertical in (False, True):
        for span, rules in _rules_by_span(strokes, vertical, used):
            # The title column's divider says where the lanes begin and end; the
            # dividers between its ends are the lanes', and any other line of the
            # same length (a legend's rule) is not.
            for column in _column_dividers(strokes, vertical, *span):
                shape = _lanes_at(column, span, rules, labels, vertical, used)
                if shape is None:
                    continue
                used.update(id(line) for line in shape.dividers)
                found.append(shape)
    return found


def _rules_by_span(
    strokes: Sequence[Stroke], vertical: bool, used: set[int]
) -> list[tuple[tuple[int, int], list[Rule]]]:
    """Plain single-segment lines across the stacking, grouped by where they start and end."""
    rules: list[Rule] = []
    for stroke in strokes:
        segments = stroke.subpath.segments
        if id(stroke) in used or stroke.marked or len(segments) != 1:
            continue
        (x1, y1), (x2, y2) = (
            _turned(stroke.subpath.start, vertical),
            _turned(segments[0].end, vertical),
        )
        if abs(y1 - y2) <= 0.5:
            rules.append(Rule(min(x1, x2), max(x1, x2), y1, stroke))

    def span(rule: Rule) -> tuple[int, int]:
        """Where a rule starts and ends, to the nearest unit."""
        return round(rule.start), round(rule.end)

    rules.sort(key=lambda rule: (*span(rule), rule.at))
    return [(key, list(run)) for key, run in itertools.groupby(rules, key=span)]


def _column_dividers(
    strokes: Sequence[Stroke], vertical: bool, left: float, right: float
) -> Iterator[Rule]:
    """Lines along the stacking, where a title column could be divided off between lanes' ends.

    Each is yielded in lane space turned a quarter: ``at`` is where it lies across
    the lanes, ``start`` and ``end`` where it runs along the stacking.
    """
    for stroke in strokes:
        if len(stroke.subpath.segments) != 1 or stroke.marked:
            continue
        (x1, y1) = _turned(stroke.subpath.start, vertical)
        (x2, y2) = _turned(stroke.subpath.segments[0].end, vertical)
        if abs(x1 - x2) <= 0.5 and left + MIN_LANE <= x1 <= right - MIN_LANE:
            yield Rule(min(y1, y2), max(y1, y2), x1, stroke)


def _lanes_at(
    column: Rule,
    span: tuple[int, int],
    rules: Sequence[Rule],
    labels: Sequence[Label],
    vertical: bool,
    used: set[int],
) -> Swimlanes | None:
    """The Swimlanes shape whose title column ``column`` divides off, if the lanes are all there.

    ``span`` is where the lanes start and end; ``rules`` are the lines of that span.
    """
    left, right = span
    dividers = [rule for rule in rules if column.start - 2 <= rule.at <= column.end + 2]
    levels = [rule.at for rule in dividers]
    spans = list(itertools.pairwise(levels))
    if len(levels) < 3 or abs(levels[0] - column.start) > 2 or abs(levels[-1] - column.end) > 2:
        return None
    if any(b - a < MIN_LANE for a, b in spans) or used & {id(rule.stroke) for rule in dividers}:
        return None
    titles: list[Label] = []
    for a, b in spans:
        title = next(
            (
                label
                for label in labels
                if label.kind == "text"
                and left <= _turned(label.centre, vertical)[0] <= column.at
                and a < _turned(label.centre, vertical)[1] < b
            ),
            None,
        )
        if title is None:
            return None
        titles.append(title)
    shape = Swimlanes(
        min(rule.stroke.order for rule in dividers),
        vertical,
        (left, right),
        levels,
        column.at - left,
        titles,
        [rule.stroke for rule in dividers] + [column.stroke],
        dividers[0].stroke.paint,
    )
    shape.kind = "swimlanes"
    for title in titles:
        title.kind, title.host = "", None  # the lane's title, not text of its own
    return shape


# --------------------------------------------------------------------------
# Writing format 19 records
# --------------------------------------------------------------------------


def _number(value: float, places: int = 3) -> float | int:
    """A number as written: in the format's bounds, and whole numbers without a fraction.

    Raises:
        ValueError: The number is not finite or lies beyond any coordinate the format holds.
    """
    if not math.isfinite(value) or abs(value) > MAX_COORDINATE:
        raise ValueError("the diagram has a coordinate beyond what SimpleDiagrams can hold")
    value = round(value, places)
    return int(value) if value == int(value) else value


def _rect_record(x: float, y: float, w: float, h: float) -> Record:
    """A rectangle record, such as a label's region in fractions of its shape."""
    return {"x": _number(x), "y": _number(y), "width": _number(w), "height": _number(h)}


def _frame_record(x: float, y: float, w: float, h: float) -> Record:
    """A shape's frame record.

    Raises:
        ValueError: The frame is empty or larger than the format holds.
    """
    if not (0 < w <= MAX_DIMENSION and 0 < h <= MAX_DIMENSION):
        raise ValueError("the diagram has a shape larger than SimpleDiagrams can hold")
    # Sizes are written to three decimal places; a speck must not round down to nothing.
    return _rect_record(x, y, max(w, 0.001), max(h, 0.001))


def utf16_length(text: str) -> int:
    """The length the format measures text ranges in: UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def text_record(
    string: str, style: TextStyle, alignment: Alignment = "center", runs: Sequence[Record] = ()
) -> Record:
    """A text record: one base style, with character runs where the style differs."""
    return {
        "string": string,
        "base_style": style.record(),
        "character_runs": list(runs),
        "base_alignment": alignment,
        "paragraph_runs": [],
    }


def text_content(lines: Sequence[Label], alignment: Alignment = "center") -> Record:
    """Lines of text as one record; a line styled unlike the first gets a character run.

    Runs span whole lines, so their ends always fall on line breaks, which are
    grapheme cluster boundaries as the format requires.
    """
    base = lines[0].style if lines else DEFAULT_TEXT
    base_record = base.record()
    runs: list[Record] = []
    location = 0
    for line in lines:
        size = utf16_length(line.string)
        if (style := line.style.record()) != base_record:
            runs.append({"range": {"location": location, "length": size}, "style": style})
        location += size + 1  # the line break
    return text_record("\n".join(line.string for line in lines), base, alignment, runs)


def element_record(
    core: Record, text_layout: Record | None = None, flips: Flips = (False, False)
) -> Record:
    """Nest an element's keys at the four levels the format stores them in."""
    presentation: Record = {
        "flip_horizontal": flips[0],
        "flip_vertical": flips[1],
        "content": {"is_locked": False, "content": core},
    }
    if text_layout is not None:
        presentation["text_layout"] = text_layout
    return {"content": presentation, "shape_data_definition_id": None, "shape_data_values": []}


def path_record(
    subpath: Subpath,
    origin: Point,
    pattern: LinePattern,
    endings: tuple[Ending, Ending] = ("none", "none"),
) -> Record:
    """A path's nodes, relative to its frame's corner, with SVG curves kept as control points."""

    def at(point: Point) -> Record:
        """A point relative to the frame's corner."""
        return {"x": _number(point[0] - origin[0]), "y": _number(point[1] - origin[1])}

    nodes: list[Record] = [{"point": at(subpath.start), "kind": "straight"}]
    for segment in subpath.segments:
        node: Record = {"point": at(segment.end), "kind": "straight"}
        match segment:
            case Quad(control, _):
                node["control_point"] = at(control)
            case Cubic(control1, control2, _):
                node["control_point"] = at(control1)
                node["second_control_point"] = at(control2)
        nodes.append(node)
    lands_on_start = math.dist(subpath.start, subpath.segments[-1].end) < 1e-6
    if subpath.closed and len(nodes) > 3 and lands_on_start:
        # The closing segment lands on the start: the first node carries its controls.
        closing = nodes.pop()
        nodes[0].update({k: v for k, v in closing.items() if k.endswith("control_point")})
    if subpath.closed and len(nodes) < 3:  # the format refuses fewer, as with a one-curve dome
        nodes.append({"point": at(subpath.start), "kind": "straight"})
    return {
        "nodes": nodes,
        "is_closed": subpath.closed,
        "is_smoothed": False,
        "stroke_pattern": pattern,
        "start_ending": endings[0],
        "end_ending": endings[1],
    }


Run: TypeAlias = tuple[bool, Point, Point]  # horizontal, start, end


def right_angle_route(subpath: Subpath) -> list[Point] | None:
    """The ends and corners of a line drawn square, or ``None`` when it is not square.

    A small curve joining two runs is a rounded corner or a hop over a crossing
    line. SimpleDiagrams 5.2 draws neither, so both are left out and the line
    keeps only its real corners, which the editor lets a person move. Two
    roundings back to back make a step, whose upright lies midway between them.
    """
    runs: list[Run] = []
    current = subpath.start
    for segment in subpath.segments:
        start, current = current, segment.end
        if not isinstance(segment, Line):
            hull = (start, *segment)
            if any(math.dist(a, b) > ROUNDING_SIZE for a, b in itertools.combinations(hull, 2)):
                return None  # the control hull is too large for a rounding or a hop
            continue
        horizontal = abs(current[1] - start[1]) <= 0.5
        if not horizontal and abs(current[0] - start[0]) > 0.5:
            return None  # a slanting line
        level = 1 if horizontal else 0
        if runs and runs[-1][0] == horizontal and abs(runs[-1][1][level] - start[level]) <= 0.5:
            runs[-1] = (horizontal, runs[-1][1], current)  # resumed after a hop
        elif math.dist(start, current) > 0:
            runs.append((horizontal, start, current))
    if not runs:
        return None

    def corner(horizontal: bool, on_run: Point, other: Point) -> Point:
        """Where a run meets the perpendicular through ``other``."""
        return (other[0], on_run[1]) if horizontal else (on_run[0], other[1])

    def corners(a: Run, b: Run) -> list[Point]:
        """The corners between two consecutive runs: one at a turn, two at a step."""
        if a[0] != b[0]:
            return [corner(a[0], a[1], b[1])]
        midway = ((a[2][0] + b[1][0]) / 2, (a[2][1] + b[1][1]) / 2)  # a step's upright
        return [corner(a[0], a[1], midway), corner(b[0], b[1], midway)]

    first, last = runs[0], runs[-1]
    route = [subpath.start, corner(first[0], first[1], subpath.start)]
    route += [point for a, b in itertools.pairwise(runs) for point in corners(a, b)]
    route += [corner(last[0], last[1], current), current]
    return [
        p for p, q in itertools.zip_longest(route, route[1:]) if q is None or math.dist(p, q) > 0.01
    ]


def connector_points(subpath: Subpath) -> list[Record]:
    """A direct connector's points: corners stay corners, curves pass through samples."""
    points: list[Record] = [{"x": subpath.start[0], "y": subpath.start[1], "kind": "straight"}]
    current = subpath.start
    for segment, following in itertools.zip_longest(subpath.segments, subpath.segments[1:]):
        curved = not isinstance(segment, Line)
        if curved:
            samples = (bezier(current, segment, t) for t in (0.25, 0.5, 0.75))
            points += [{"x": x, "y": y, "kind": "curve"} for x, y in samples]
        smooth = curved and following is not None and not isinstance(following, Line)
        x, y = segment.end
        points.append({"x": x, "y": y, "kind": "curve" if smooth else "straight"})
        current = segment.end
    if subpath.closed:
        points.append(dict(points[0]))
    return points


def label_layout(box: Box, lines: Sequence[Label]) -> Record | None:
    """Keep a box label where the SVG put it, with room to stay on its lines.

    A centred label uses the editor's default place, which reads best when the
    text is edited, unless the text would not fit inside that place's margins,
    as on a small tag: then its region spans the box, or wider, so no word wraps.
    Otherwise the region starts where the text starts and runs to the box's far
    edge, so longer text still has room. A flipped shape keeps the default
    place, so its label never depends on how flips are read.
    """
    if not lines or box.flips != (False, False):
        return None
    extents = [line.page_bounds() for line in lines]
    left, top, right, bottom = _union(extents)
    x, y, w, h = box.frame
    middle, align = (left + right) / 2, lines[0].align
    if align == "center" and _is_centred((left, top, right, bottom), box.frame):
        needed = max(e[2] - e[0] for e in extents) * TEXT_ROOM[0] + TEXT_ROOM[1]
        if needed <= w - 2 * LABEL_INSET:
            return None
        span = min(8.0, max(1.0, needed / w))  # the format holds a region up to 8 wide
        return {"frame": _rect_record((1 - span) / 2, 0, span, 1), "position": "middle"}
    if align == "center":
        half = max(1.0, min(middle - x, x + w - middle))
        region_left, region_right = middle - half, middle + half
    else:
        region_left = left - 1 if align == "leading" else x
        region_right = right + 1 if align == "trailing" else x + w
    width = max(0.001, min(8.0, (region_right - region_left) / w))
    height = max(0.001, min(8.0, (y + h - top) / h))
    fx = max(-width, min(1.0, (region_left - x) / w))
    fy = max(-height, min(1.0, (top - y) / h))
    return {"frame": _rect_record(fx, fy, width, height), "position": "top"}


class Writer:
    """Builds ``document.json`` with identifiers derived from the file name and order."""

    def __init__(self, slug: str) -> None:
        """Start numbering identifiers for the file named by ``slug``."""
        self.slug = slug
        self.counter = itertools.count(1)
        self.assets: list[Asset] = []

    def new_id(self) -> str:
        """The next identifier: a name-based UUID, the same on every export."""
        return str(uuid.uuid5(ID_NAMESPACE, f"{self.slug}/{next(self.counter)}")).upper()

    def document(self, reader: Reader, name: str) -> Record:
        """The whole document: one page holding every item, in drawing order."""
        swimlanes = arrange(reader.items, reader.background or "#FFFFFF")
        drawn = sorted(
            [*swimlanes, *(item for item in reader.items if item.kind)], key=lambda i: i.order
        )
        document_id, page_id = self.new_id(), self.new_id()
        ids = {id(item): self.new_id() for item in drawn}
        groups, group_ids = self._groups(drawn, ids)
        # Each picture is stored once, however many shapes show it.
        pictures = {item.asset.id: item.asset for item in drawn if isinstance(item, Artwork)}
        self.assets = [pictures[key] for key in sorted(pictures)]

        elements: list[Record] = []
        connections: list[Record] = []
        order: list[Record] = []
        for item in drawn:  # source order is drawing order, back to front
            item_id = ids[id(item)]
            match item:
                case Stroke(kind="connector"):
                    connections.append(self._connector(item, item_id, ids))
                    order.append({"kind": "connection", "id": item_id})
                    continue
                case Swimlanes():
                    record = self._swimlanes(item, item_id, drawn, ids, group_ids)
                case Box():
                    record = self._box(item, item_id)
                case Artwork():
                    record = self._artwork(item, item_id)
                case Stroke():
                    record = self._line(item, item_id)
                case Label():
                    record = self._free_text(item, item_id)
            record["content"]["content"]["content"]["z_index"] = len(elements)
            elements.append(record)
            order.append({"kind": "element", "id": item_id})

        page = self._page(page_id, reader, elements, connections, order, groups)
        return {
            "id": document_id,
            "schema_version": SCHEMA_VERSION,
            "revision": 0,
            "name": name,
            "selected_page_id": page_id,
            "pages": [page],
            "quick_styles": [],
            "embedded_assets": [asset.record() for asset in self.assets],
            "shape_data_definitions": [],
        }

    @staticmethod
    def _page(
        page_id: str,
        reader: Reader,
        elements: list[Record],
        connections: list[Record],
        order: list[Record],
        groups: list[Record],
    ) -> Record:
        """The page record, nested at the levels the format stores a page in."""
        # A page without a background is white paper in SimpleDiagrams, so only
        # a tinted paper needs a colour.
        background: Record = {"kind": "none"}
        if reader.background not in (None, "#FFFFFF"):
            background = {"kind": "solid", "color_hex": reader.background}
        core: Record = {
            "id": page_id,
            "name": "Page 1",
            "width": _number(reader.view[2]),
            "height": _number(reader.view[3]),
            "elements": [],
            "connections": [],
            "grid": {"spacing_x": 20, "spacing_y": 20, "origin": {"x": 0, "y": 0}},
        }
        layer = {"connections": connections, "elements": [], "groups": [], "content": core}
        return {
            "elements": elements,
            "content": {
                "background": background,
                "elements": [],
                "drawableOrder": order,
                "groups": groups,
                "content": layer,
            },
        }

    def _groups(
        self, drawn: Sequence[Shown], ids: dict[int, str]
    ) -> tuple[list[Record], dict[int, str]]:
        """One group per box with things drawn on it; a hosted box with a group joins as it.

        Returns the group records and each owning box's group identifier.
        """
        held: dict[int, list[Shown]] = {}
        for item in drawn:
            if item.host is not None:
                held.setdefault(id(item.host), []).append(item)
        owners = sorted(
            (item for item in drawn if isinstance(item, Box) and id(item) in held),
            key=lambda box: (box.area, box.order),
        )
        group_ids = {id(box): self.new_id() for box in owners}

        def member(item: Shown, owner: Box) -> Record:
            """A group member: a box that owns a group joins as that group."""
            if item is not owner and id(item) in group_ids:
                return {"kind": "group", "id": group_ids[id(item)]}
            return {"kind": "element", "id": ids[id(item)]}

        records = [
            {
                "id": group_ids[id(box)],
                "is_locked": False,
                "rotation_degrees": 0,
                "members": [member(item, box) for item in [box, *held[id(box)]]],
            }
            for box in owners
        ]
        return records, group_ids

    def _swimlanes(
        self,
        shape: Swimlanes,
        element_id: str,
        drawn: Sequence[Shown],
        ids: dict[int, str],
        group_ids: dict[int, str],
    ) -> Record:
        """The Swimlanes shape; each lane holds what is drawn in it, a group as a whole."""
        members: list[list[Record]] = [[] for _ in shape.titles]
        held: set[int] = set()
        for item in drawn:
            if isinstance(item, Swimlanes) or item.kind == "connector":
                continue
            top: Drawn = item
            while top.host is not None and id(top.host) in ids:  # a label box has no record
                top = top.host
            lane = shape.lane_of(top.centre)
            if lane is None or id(top) in held:
                continue
            held.add(id(top))
            grouped = id(top) in group_ids
            member_id = group_ids[id(top)] if grouped else ids[id(top)]
            members[lane].append({"kind": "group" if grouped else "element", "id": member_id})
        paint = Paint(TRANSPARENT, shape.paint.stroke, shape.paint.line_width, "solid")
        text = text_record("", shape.titles[0].style)
        core = self._core(element_id, "complex_shape", shape.frame, 0, paint, text, STANDARD_POINTS)
        # A lane's size is its share of the whole, so its measured thickness serves as is.
        lanes = [
            {
                "id": self.new_id(),
                "role": "lane",
                "text": text_content([label]),
                "size": _number(b - a),
                "members": held_here,
            }
            for label, (a, b), held_here in zip(
                shape.titles, itertools.pairwise(shape.levels), members, strict=True
            )
        ]
        record = element_record(core)
        record["complex_shape"] = {
            "type": "swimlanes",
            "version": 1,
            "settings": {
                "direction": "vertical" if shape.vertical else "horizontal",
                "title_strip_size": _number(max(shape.strip, MIN_LANE)),
                "title_band_size": _number(MIN_LANE),
            },
            "parts": lanes,
        }
        return record

    @staticmethod
    def _core(
        element_id: str,
        kind: str,
        frame: Rect,
        rotation: float,
        paint: Paint,
        text: Record,
        points: Sequence[Point],
    ) -> Record:
        """The keys every element kind shares."""
        return {
            "id": element_id,
            "kind": kind,
            "frame": _frame_record(*frame),
            "rotation_degrees": _number(rotation),
            "z_index": 0,
            "text_content": text,
            "style": {
                "fill_hex": paint.fill,
                "stroke_hex": paint.stroke,
                "line_width": _number(paint.line_width),
            },
            "connection_points": [
                {"id": i, "x": _number(u, 6), "y": _number(v, 6)} for i, (u, v) in enumerate(points)
            ],
        }

    def _box(self, box: Box, element_id: str) -> Record:
        """A box as a Basic library symbol, or as a closed path keeping its exact outline."""
        lines = reading_order(box.labels)
        text = text_content(lines, lines[0].align if lines else "center")
        if box.basic is not None:
            core = self._core(
                element_id, "symbol", box.frame, box.rotation, box.paint, text, box.points
            )
            core["symbol_reference"] = {
                "library_id": BASIC_LIBRARY,
                "item_id": box.basic,
                "asset_version": 1,
            }
            if box.paint.pattern != "solid":
                core["style"]["stroke_pattern_override"] = box.paint.pattern
            return element_record(core, label_layout(box, lines), box.flips)
        core = self._core(element_id, "path", box.frame, 0, box.paint, text, box.points)
        core["path"] = path_record(box.subpath, box.frame[:2], box.paint.pattern)
        return element_record(core)  # a path's label always sits in the default place

    def _artwork(self, artwork: Artwork, element_id: str) -> Record:
        """A picture: an icon's stored SVG artwork in its frame."""
        frame, text = artwork.frame, text_content([])
        core = self._core(
            element_id,
            "svg_artwork",
            frame,
            artwork.rotation,
            NO_PAINT_AT_ALL,
            text,
            STANDARD_POINTS,
        )
        core["embedded_asset_id"] = artwork.asset.id
        return element_record(core, flips=artwork.flips)

    def _line(self, stroke: Stroke, element_id: str) -> Record:
        """A line that is not a connector, as an open path."""
        frame = path_frame(stroke.subpath, stroke.paint.line_width)
        core = self._core(element_id, "path", frame, 0, stroke.paint, text_content([]), [])
        endings = (stroke.start_ending, stroke.end_ending)
        core["path"] = path_record(stroke.subpath, frame[:2], stroke.paint.pattern, endings)
        return element_record(core)

    def _free_text(self, label: Label, element_id: str) -> Record:
        """Text on no box, as a text element exactly where the SVG drew it."""
        x, y, w, h = label.local_box()
        if label.wrap_box is None:
            # Room to spare, so the editor never wraps a line the SVG kept whole.
            w, h = w * TEXT_ROOM[0] + TEXT_ROOM[1], h + 4
            shift = {"leading": 3, "center": (w - label.width) / 2, "trailing": w - label.width - 3}
            x, y = x - shift[label.align], y - 2
        placed = placed_frame((x, y, w, h), label.matrix)
        if placed is None:  # a skewed label keeps its size and stays upright
            cx, cy = apply(label.matrix, (x + w / 2, y + h / 2))
            placed = (cx - w / 2, cy - h / 2, w, h), 0.0
        frame, rotation = placed
        text = text_content([label], label.align)
        core = self._core(element_id, "text", frame, rotation, NO_PAINT_AT_ALL, text, [])
        position = "top" if label.wrap_box else "middle"
        return element_record(core, {"frame": _rect_record(0, 0, 1, 1), "position": position})

    @staticmethod
    def _connector(stroke: Stroke, connector_id: str, ids: dict[int, str]) -> Record:
        """A connector: its route, attached ends and label."""
        route = None if stroke.subpath.closed else right_angle_route(stroke.subpath)
        if route is not None and len(route) < 2:
            route = None  # too short to be squared; its two ends are kept as drawn
        square = route is not None and len(route) > 2
        if route is None:
            points = connector_points(stroke.subpath)
        else:
            points = [{"x": x, "y": y, "kind": "straight"} for x, y in route]
        content: Record = {
            "id": connector_id,
            "stroke_hex": stroke.paint.stroke,
            "line_width": _number(max(stroke.paint.line_width, 0.5)),
            "stroke_pattern": stroke.paint.pattern,
            "start_ending": stroke.start_ending,
            "end_ending": stroke.end_ending,
        }
        # Whether each end leaves level, read before attaching can move it.
        level_ends = [
            square and abs(points[i]["y"] - points[j]["y"]) <= 0.5 for i, j in ((0, 1), (-1, -2))
        ]
        ends = (("start", stroke.start, 0, 1), ("end", stroke.end, -1, -2))
        for (end, attached, index, next_index), leaves_level in zip(ends, level_ends, strict=True):
            if attached is None:
                continue
            content[f"{end}_attachment"] = {
                "element_id": ids[id(attached.box)],
                "connection_point_id": attached.point_id,
            }
            # Store where the attachment resolves, so readers that do not resolve it agree.
            x, y = attached.box.from_frame(attached.box.points[attached.point_id])
            points[index].update({"x": x, "y": y})
            if square:  # the neighbouring corner follows, so the end stays square
                points[next_index]["y" if leaves_level else "x"] = y if leaves_level else x
        content["points"] = [
            {"x": _number(p["x"]), "y": _number(p["y"]), "kind": p["kind"]} for p in points
        ]
        if stroke.label is not None:
            content["label"] = _connector_label(stroke.label, points)
        connection: Record = {"is_locked": False, "content": content}
        if square:
            # Only the real corners are stored; SimpleDiagrams draws them square.
            connection |= {
                "routing": "right_angle",
                "routes_around_shapes": True,
                "routing_rotation_degrees": 0,
            }
        return connection


def _connector_label(label: Box, points: Sequence[Record]) -> Record:
    """A connector's label, placed along the line as stored, as SimpleDiagrams draws it."""
    place = along([(p["x"], p["y"]) for p in points], label.centre)
    return {
        "content": text_content(reading_order(label.labels)),
        "position": _number(place.share, 4),
        "normal_offset": _number(place.offset),
    }


# --------------------------------------------------------------------------
# The package on disk
# --------------------------------------------------------------------------


class Export(NamedTuple):
    """A translated diagram: what the package holds, and what was left out."""

    manifest: Record
    document: Record
    skipped: dict[str, int]  # how many of each kind of content could not be translated
    assets: list[Asset]


def _page_style_elements(source: str) -> tuple[ET.Element, ET.Element] | tuple[()]:
    """Read HTML ancestors, or leave a standalone SVG as the root of its own cascade."""
    html, body = ET.Element("html"), ET.Element("body")
    elements = {"html": html, "body": body}
    page = False
    svg_depth = 0
    for token, _, _, _ in export_svg.html_tokens(source):
        name = (token.group("tag") or "").lower()
        if name == "svg":
            if page and not svg_depth:
                break
            if token.group("close"):
                svg_depth -= 1
            elif not token.group().endswith("/>"):
                svg_depth += 1
            continue
        if svg_depth or token.group("close") or not name:
            continue
        page = True
        if name not in elements:
            continue
        markup = export_svg.normalize_html_entities(export_svg.xmlify_attributes(token.group()))
        if (opening := export_svg.START_TAG_RE.fullmatch(markup)) is not None:
            for attr in export_svg.TAG_ATTR_RE.finditer(opening.group(2)):
                if raw := attr.group(4):
                    elements[name].attrib.setdefault(
                        attr.group(2).lower(), export_svg.decode_xml_references(raw[1:-1])
                    )
    return (html, body) if page else ()


def export_document(html: str, source_path: Path) -> Export:
    """Translate source HTML into a SimpleDiagrams document."""
    svg = export_svg.export_svg_document(html, source_path, system_fonts=True, scope_rules=False)
    root = ET.fromstring(svg)
    reader = Reader(root, _page_style_elements(html)).read()
    titles = (element.text for element in root if _local(element) == "title" and element.text)
    title = next(titles, None) or source_path.stem
    name = _clip_utf8(re.sub(r"\s+", " ", title).strip(), MAX_NAME_BYTES)
    writer = Writer(export_svg.slug_for(source_path))
    document = writer.document(reader, name)
    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "contains_legacy_source": False,
    }
    if sum(len(asset.data) for asset in writer.assets) > MAX_ASSETS_BYTES:
        raise ValueError("the diagram's pictures are larger than a SimpleDiagrams document holds")
    return Export(manifest, document, reader.skipped, writer.assets)


def _json(data: Record) -> str:
    """Stable JSON: sorted keys, so an unchanged diagram exports identical bytes."""
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


def write_package(destination: Path, export: Export) -> None:
    """Create a new package folder; an existing path is never replaced.

    A SimpleDiagrams document a person has since edited looks exactly like a
    fresh export, so overwriting could lose their work. Everything is
    serialised before the folder is created, so only a disk error can leave an
    incomplete package behind.
    """
    if destination.suffix != PACKAGE_SUFFIX:
        raise ValueError(f"the output name must end in {PACKAGE_SUFFIX}: {destination}")
    texts = {"manifest.json": _json(export.manifest), "document.json": _json(export.document)}
    try:
        destination.mkdir()
    except FileExistsError:
        raise ValueError(
            f"{destination} already exists; choose another name or remove it"
        ) from None
    try:
        (destination / "assets").mkdir()
        for name, text in texts.items():
            (destination / name).write_text(text, encoding="utf-8", newline="\n")
        for asset in export.assets:
            (destination / "assets" / asset.filename).write_bytes(asset.data)
    except OSError as exc:
        message = (
            f"could not complete {destination} ({exc.strerror}); remove it before trying again"
        )
        raise OSError(message) from exc


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; returns the exit status."""
    parser = argparse.ArgumentParser(
        description="Export a diagram-design HTML file as a SimpleDiagrams document."
    )
    parser.add_argument("source", type=Path, help="Source .html diagram file")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        help=f"New {PACKAGE_SUFFIX} path (default: <source-stem>{PACKAGE_SUFFIX} beside it)",
    )
    args = parser.parse_args(argv)

    source: Path = args.source
    if not source.is_file():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 2
    if source.name == "index.html" and source.resolve().parent.name == "assets":
        print(
            "error: refuse to export the gallery (assets/index.html); pick a specific diagram",
            file=sys.stderr,
        )
        return 2
    output: Path = args.output or source.with_suffix(PACKAGE_SUFFIX)
    try:
        export = export_document(source.read_text(encoding="utf-8"), source)
        write_package(output, export)
    except RecursionError:
        print("error: the diagram is nested too deeply to export", file=sys.stderr)
        return 2
    except ArithmeticError:  # numbers past what floating point holds, such as skewX(1e308)
        print("error: the diagram holds numbers too large or small to export", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for what, count in sorted(export.skipped.items()):
        print(f"note: {what} ({count})", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
