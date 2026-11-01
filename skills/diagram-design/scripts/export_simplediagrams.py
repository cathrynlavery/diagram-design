#!/usr/bin/env python3
"""Export a diagram HTML file as an editable SimpleDiagrams document.

    python3 <skill-dir>/scripts/export_simplediagrams.py my-diagram.html
    python3 <skill-dir>/scripts/export_simplediagrams.py my-diagram.html "Flow.simplediagram"

SimpleDiagrams is a diagram editor for macOS whose documents are folder
packages ending in ``.simplediagram``. This writes document format 19:
https://github.com/mcquilleninteractive/simplediagrams-file-formats/tree/main/document/19

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
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field, replace
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

INHERITED = frozenset(
    {"fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap",
     "stroke-linejoin", "stroke-miterlimit", "fill-rule", "fill-opacity", "stroke-opacity",
     "color", "font-family", "font-size", "font-weight", "font-style", "text-anchor",
     "text-align", "text-transform", "text-decoration", "letter-spacing", "visibility",
     "marker-start", "marker-end"}
)  # fmt: skip
ICON_PAINT = frozenset(
    {"fill", "stroke", "stroke-width", "stroke-dasharray", "fill-opacity", "stroke-opacity",
     "opacity", "color"}
)  # fmt: skip
ICON_LINE = frozenset(
    {"stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "fill-rule",
     "marker-start", "marker-end"}
)  # fmt: skip
ICON_TEXT = frozenset(
    {"font-family", "font-size", "font-style", "font-weight", "letter-spacing", "text-anchor",
     "text-decoration"}
)  # fmt: skip
TRANSFORM_FRAME = frozenset({"transform-origin", "transform-box"})  # an icon with one is left out
GRADIENT_STOP = frozenset({"stop-color", "stop-opacity"})
EFFECTS = frozenset({"clip-path", "mask"})  # read only to report them: nothing here clips
PRESENTATION = (
    INHERITED | EFFECTS | TRANSFORM_FRAME | GRADIENT_STOP | {"opacity", "display", "transform"}
)
ICON_ATTRIBUTES = ICON_PAINT | ICON_LINE | EFFECTS | TRANSFORM_FRAME | GRADIENT_STOP
ICON_HANDLED = ICON_ATTRIBUTES | ICON_TEXT | {"display", "visibility", "transform"}
ICON_DROPPED_ATTRIBUTES = frozenset({"class", "style", "display", "visibility"})
TEXT_STYLE = ("fill", "font-family", "font-size", "font-style", "font-weight", "text-decoration")
NO_PAINT = frozenset({"none", "transparent"})
IMPORTANT = "!important"
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


# --------------------------------------------------------------------------
# Styles: presentation attributes, the carried stylesheet, inline style
# --------------------------------------------------------------------------


class Compound(NamedTuple):
    """One compound selector, such as ``rect.node#main``."""

    tag: str | None
    ids: frozenset[str]
    classes: frozenset[str]

    def matches(self, element: ET.Element) -> bool:
        """Whether the element has this tag, these IDs and these classes."""
        if self.tag is not None and _local(element) != self.tag:
            return False
        if self.ids and element.get("id") not in self.ids:
            return False
        return self.classes <= set(element.get("class", "").split())


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
        if not last.matches(element):
            return False
        for ancestor in reversed(ancestors):
            if outer and outer[-1].matches(ancestor):
                outer.pop()
        return not outer


def _declarations(body: str) -> Props:
    """Split ``a: b; c: d`` into a dict, keeping semicolons inside parentheses.

    A value keeps a normalised ``!important`` ending for the cascade to act on.
    """
    out: Props = {}
    depth, start = 0, 0
    for index, char in enumerate(body + ";"):
        depth += (char == "(") - (char == ")")
        if char == ";" and depth <= 0:
            name, colon, value = body[start:index].partition(":")
            if colon:
                name, value = name.strip(), IMPORTANT_RE.sub(IMPORTANT, value.strip())
                name = name if name.startswith("--") else name.lower()
                if value.endswith(IMPORTANT) or not out.get(name, "").endswith(IMPORTANT):
                    out[name] = value
            start = index + 1
    return out


def _compound(text: str) -> Compound | None:
    """Read a compound selector built from a tag, IDs and classes; ``None`` for any other."""
    match = re.fullmatch(r"([A-Za-z][\w-]*)?((?:[.#][\w-]+)*)", text)
    if match is None or not text:
        return None
    parts = re.findall(r"([.#])([\w-]+)", match.group(2))
    return Compound(
        match.group(1),
        frozenset(name for kind, name in parts if kind == "#"),
        frozenset(name for kind, name in parts if kind == "."),
    )


def parse_stylesheet(css: str) -> list[CssRule]:
    """Read the plain top-level rules, skipping at-rule groups such as dark-mode queries.

    Only descendant selectors built from tags, classes and IDs are understood. Any
    other selector (child, sibling, attribute, pseudo-class) is ignored, so the
    element keeps its presentation attributes for that property.
    """
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    rules: list[CssRule] = []
    depth, start, opening = 0, 0, 0
    for index, char in enumerate(css):
        if char == "{":
            opening = index if depth == 0 else opening
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth:
                continue
            selectors, body = css[start:opening].strip(), css[opening + 1 : index]
            start = index + 1
            if selectors.startswith("@"):
                continue
            declarations = _declarations(body)
            for selector in export_svg.selector_list_parts(selectors):
                compounds = [_compound(part) for part in selector.split()]
                valid = tuple(c for c in compounds if c is not None)
                if not valid or len(valid) != len(compounds):
                    continue
                specificity = (
                    sum(len(c.ids) for c in valid),
                    sum(len(c.classes) for c in valid),
                    sum(c.tag is not None for c in valid),
                )
                rules.append(CssRule(valid, specificity, len(rules), declarations))
        elif char == ";" and depth == 0:
            start = index + 1  # a statement such as @import
    return sorted(rules, key=lambda rule: (rule.specificity, rule.order))


def resolve_vars(value: str, props: Props, depth: int = 0) -> str:
    """Substitute ``var(--name, fallback)`` from inherited custom properties."""
    if "var(" not in value or depth > 8:
        return value

    def substitute(match: re.Match[str]) -> str:
        """One ``var()``: the property's value, or else its fallback."""
        name, _, fallback = match.group(1).partition(",")
        return resolve_vars(props.get(name.strip(), fallback.strip()), props, depth + 1)

    pattern = r"var\(\s*(--[\w-]+\s*(?:,[^()]*)?)\)"
    return resolve_vars(re.sub(pattern, substitute, value), props, depth + 1)


def expand_font_shorthand(value: str) -> Props:
    """Read ``font: italic 600 13px 'Geist', sans-serif`` into its longhand properties."""
    match = re.fullmatch(
        r"\s*(?:(italic|oblique|normal)\s+)?(?:(\d{3}|bold|bolder|lighter|normal)\s+)?"
        r"([\d.]+(?:px|rem))(?:\s*/\s*\S+)?\s+(.+)",
        value,
    )
    if match is None:
        return {}
    style, weight, size, family = match.groups()
    return {
        "font-size": size.removesuffix("px"),
        "font-family": family,
        "font-style": style or "normal",
        "font-weight": weight or "normal",
    }


def computed_properties(
    element: ET.Element,
    inherited: Props,
    rules: Sequence[CssRule],
    ancestors: Sequence[ET.Element],
) -> Props:
    """Cascade presentation attributes, then stylesheet rules, then inline style.

    The same order runs twice, because an ``!important`` declaration beats every normal one.
    Custom properties settle first, so ``font`` reads their final values wherever they are set.
    """
    props = {k: v for k, v in inherited.items() if k in INHERITED or k.startswith("--")}
    layers = [{k: v for k, v in element.attrib.items() if k in PRESENTATION}]
    layers += [rule.declarations for rule in rules if rule.applies(element, ancestors)]
    layers.append(_declarations(element.get("style", "")))
    declared = [
        item
        for important in (False, True)
        for layer in layers
        for item in layer.items()
        if item[1].endswith(IMPORTANT) == important
    ]
    declared.sort(key=lambda item: not item[0].startswith("--"))  # stable: keeps the cascade order
    for name, marked in declared:
        value = marked.removesuffix(IMPORTANT).rstrip()
        if name == "font":
            props.update(expand_font_shorthand(resolve_vars(value, props)))
        elif name in PRESENTATION or name.startswith("--"):
            props[name] = value
    return {k: v if k.startswith("--") else resolve_vars(v, props) for k, v in props.items()}


def _is_invisible(props: Props) -> bool:
    """Whether ``visibility`` hides an element, though a child of it may still show itself."""
    return props.get("visibility") in ("hidden", "collapse")


def _has_line(props: Props) -> bool:
    """Whether an element draws an outline."""
    stroke = props.get("stroke", "none").strip().lower()
    return bool(stroke) and stroke not in NO_PAINT and length(props.get("stroke-width"), 1.0) > 0


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


def length(
    value: str | None,
    default: float = 0.0,
    *,
    percent_of: float | None = None,
    font_size: float = 16.0,
) -> float:
    """Read an SVG length (the first of a list): plain, px, pt, rem, em or a percentage."""
    pattern = r"\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)(px|pt|rem|em|%)?"
    if (match := re.match(pattern, value or "")) is None:
        return default
    amount, unit = float(match.group(1)), match.group(2)
    if unit == "em":
        amount *= font_size
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


def decompose(m: Matrix) -> tuple[float, float, float] | None:
    """Rotation (degrees) and the two axis scales, or ``None`` when the transform skews."""
    a, b, c, d = m[:4]
    if abs(a * c + b * d) > 1e-6 * max(1.0, abs(a * d - b * c)):
        return None
    sx, sy = math.hypot(a, b), math.hypot(c, d)
    if sx < 1e-9 or sy < 1e-9:
        return None
    return math.degrees(math.atan2(b, a)), sx, sy


def placed_frame(local: Rect, m: Matrix) -> tuple[Rect, float] | None:
    """A frame drawn through a transform, as an unrotated frame and its rotation.

    ``None`` when the transform skews, since a skewed frame is no longer a frame.
    """
    if (turn := decompose(m)) is None:
        return None
    x, y, w, h = local
    cx, cy = apply(m, (x + w / 2, y + h / 2))
    w, h = w * turn[1], h * turn[2]
    return (cx - w / 2, cy - h / 2, w, h), round(turn[0], 4) % 360


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
    if (scale := x1 * x1 / (rx * rx) + y1 * y1 / (ry * ry)) > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    root = math.sqrt(max(0.0, numerator / (rx * rx * y1 * y1 + ry * ry * x1 * x1)))
    root = -root if large == sweep else root
    cx1, cy1 = root * rx * y1 / ry, -root * ry * x1 / rx
    cx = cos_phi * cx1 - sin_phi * cy1 + (start[0] + end[0]) / 2
    cy = sin_phi * cx1 + cos_phi * cy1 + (start[1] + end[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        """The signed angle from one vector to another."""
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    theta = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
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
SVG_TRANSFORM = re.compile(
    r"[\s,]*(?:(?:matrix|translate|scale|rotate|skewX|skewY)\s*\([-+.\deE\s,]*\)[\s,]*)*"
)
ABSOLUTE_SIZE = re.compile(rf"\s*{NUMBER}(?:px|pt|pc|in|cm|mm)?\s*", re.IGNORECASE)
ICON_STRUCTURE = frozenset({"svg", "g", "title", "desc", "metadata", "defs"})  # draw nothing
KNOWN_NAMESPACES = (f"{{{SVG_NAMESPACE}}}", "{http://www.w3.org/XML/1998/namespace}")


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


def _other_inline_styles(element: ET.Element, page: Props) -> str:
    """An element's inline declarations this export has no attribute for, with tokens resolved."""
    kept = []
    for name, marked in _declarations(element.get("style", "")).items():
        value = resolve_vars(marked.removesuffix(IMPORTANT).rstrip(), page)
        if name in ICON_HANDLED or name.startswith("--") or not value.strip():
            continue
        if name != "font" or not expand_font_shorthand(value):
            kept.append(f"{name}: {value}")
    return "; ".join(kept)


def _styled_clone(element: ET.Element, page: Props, stored: Props) -> tuple[ET.Element, Props]:
    """An element without its children and with the page's styling written onto it.

    Anything the export understands becomes an attribute, so a stylesheet's ``!important``
    cannot lose to an inline style in the copy. Other inline declarations stay inline.
    Returns the copy and what its children inherit in the stored icon.
    """
    written, dropped = ICON_ATTRIBUTES, ICON_DROPPED_ATTRIBUTES
    if _local(element) in ("text", "tspan"):
        written |= ICON_TEXT
    if page.get("transform", "").strip() in ("", "none"):  # nothing for a transform frame to move
        written, dropped = written - TRANSFORM_FRAME, dropped | TRANSFORM_FRAME
    kept = {k: v for k, v in element.attrib.items() if k not in dropped}
    clone = ET.Element(element.tag, kept)
    clone.text, clone.tail = element.text, element.tail
    if inline := _other_inline_styles(element, page):
        clone.set("style", inline)
    stored = computed_properties(clone, stored, (), ())
    for name in sorted(written & page.keys()):
        if page[name] != stored.get(name) and (name in ICON_PAINT or page[name].strip()):
            clone.set(name, page[name])
            stored[name] = page[name]
    if page.get("transform") != stored.get("transform"):
        value = _attribute_transform(page["transform"])
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


def _is_diamond(coordinates: Sequence[float]) -> bool:
    """Whether four points are a diamond: its diagonals cross at their middles, a notch's do not."""
    if len(coordinates) != 8:
        return False
    x0, y0, x1, y1, x2, y2, x3, y3 = coordinates
    return abs(x0 + x2 - x1 - x3) + abs(y0 + y2 - y1 - y3) < 0.01


def _attribute_transform(value: str) -> str:
    """A CSS transform as an SVG attribute says it, which is without units."""
    return re.sub(r"(?<=\d)(?:px|deg)\b", "", value)


def _readable_transform(props: Props) -> bool:
    """Whether an element's transform, if any, is one this export understands."""
    value = _attribute_transform(props.get("transform", "")).strip()
    if value in ("", "none"):
        return True
    return TRANSFORM_FRAME.isdisjoint(props) and SVG_TRANSFORM.fullmatch(value) is not None


def svg_asset(view: Rect, parts: Sequence[ET.Element], paint: Props) -> Asset | None:
    """Stand-alone SVG artwork drawing ``parts`` in ``view``, painted as placed."""
    if not all(MIN_SVG_DIMENSION <= size <= MAX_DIMENSION for size in view[2:]):
        return None
    root = ET.Element(f"{{{SVG_NAMESPACE}}}svg", {"viewBox": " ".join(f"{v:g}" for v in view)})
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


@dataclass(frozen=True, slots=True)
class Paint:
    """How an outline is painted, in the format's own terms."""

    fill: str
    stroke: str
    line_width: float
    pattern: LinePattern

    @property
    def filled(self) -> bool:
        """Whether there is a fill, rather than none."""
        return self.fill != TRANSPARENT


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

    def __init__(self, root: ET.Element) -> None:
        """Prepare to read ``root``: its stylesheet, its IDs and its page size."""
        self.root = root
        styles = (element.text or "" for element in root.iter() if _local(element) == "style")
        self.rules = parse_stylesheet("".join(styles))
        self.by_id = {element.get("id"): element for element in root.iter() if element.get("id")}
        self.markers = {key: e for key, e in self.by_id.items() if _local(e) == "marker"}
        view = [float(v) for v in NUMBER_RE.findall(root.get("viewBox", ""))]
        usable = len(view) == 4 and view[2] > 0 and view[3] > 0 and all(map(math.isfinite, view))
        self.view = view if usable else [0.0, 0.0, 1000.0, 600.0]
        if max(self.view[2:]) > MAX_DIMENSION:
            raise ValueError("the diagram's viewBox is larger than a SimpleDiagrams page can be")
        self.items: list[Drawn] = []
        self.background: str | None = None
        self.skipped: dict[str, int] = {}
        self.ancestors: list[ET.Element] = []
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
        self._walk(self.root, {}, origin, 1.0, [])
        if (count := len(self.items)) > MAX_ITEMS:
            raise ValueError(
                f"the diagram draws {count} shapes; this export handles up to {MAX_ITEMS}"
            )
        return self

    def _skip(self, what: str) -> None:
        """Count content that could not be translated, for one note per kind."""
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
            self._skip(f"<{name}> left out")
            return
        props = computed_properties(element, inherited, self.rules, ancestors)
        if props.get("display") == "none":
            return
        if not _readable_transform(props):
            self._skip("CSS transform this export cannot read may misplace a shape")
        matrix = multiply(matrix, parse_transform(props.get("transform")))
        opacity *= max(0.0, min(1.0, length(props.get("opacity"), 1.0, percent_of=1.0)))
        if opacity <= 0 or _is_invisible(props):
            return
        if any(props.get(effect, "none").strip().lower() != "none" for effect in EFFECTS):
            self._skip("clipping and masks left out; shapes are drawn unclipped")
        if name == "svg" and element is not self.root:
            self._nested_svg(element, props, matrix, opacity, ancestors)
        elif name in CONTAINERS:
            for child in element:
                self._walk(child, props, matrix, opacity, [*ancestors, element])
        elif handler := self.handlers.get(name):
            self.ancestors = ancestors  # text handlers style their children with it
            handler(element, props, matrix, opacity)
        else:
            self._skip(f"<{name}> left out")

    # -- paint ------------------------------------------------------------

    def _colour(self, value: str | None, props: Props) -> Colour | None:
        """A paint as a colour, noting any paint (a gradient, a pattern) it cannot show."""
        if value is None or value.strip().lower() in NO_PAINT:
            return None
        if (colour := parse_colour(value, props)) is None:
            self._skip("gradient, pattern or unknown colour, left transparent")
        return colour

    def _paint(self, props: Props, opacity: float, matrix: Matrix) -> Paint:
        """Fill, line and dash pattern, with line widths scaled as the transform scales."""
        fill = self._colour(props.get("fill", "black"), props)
        stroke = self._colour(props.get("stroke"), props)
        turn = decompose(matrix)
        scale = math.sqrt(turn[1] * turn[2]) if turn else 1.0
        width = max(0.0, length(props.get("stroke-width"), 1.0)) * scale if stroke else 0.0
        dash_values = re.split(r"[\s,]+", props.get("stroke-dasharray", "none").strip())
        dashes = [length(v) for v in dash_values if v and v != "none"]
        pattern: LinePattern = "solid"
        if any(dashes):
            pattern = "dotted" if dashes[0] <= max(1.5, width * 1.5) else "dashed"
        return Paint(
            colour_hex(fill, opacity * length(props.get("fill-opacity"), 1.0, percent_of=1.0)),
            colour_hex(stroke, opacity * length(props.get("stroke-opacity"), 1.0, percent_of=1.0)),
            round(min(10_000.0, width), 3),
            pattern,
        )

    def _ending(self, reference: str | None) -> Ending:
        """The line ending a ``marker-start`` or ``marker-end`` reference draws."""
        match = re.fullmatch(r"\s*url\(\s*['\"]?#([^'\")]+)['\"]?\s*\)\s*", reference or "")
        marker = self.markers.get(match.group(1)) if match else None
        if marker is None:
            return "none"
        drawable = ("polygon", "path", "polyline", "circle", "ellipse", "rect", "line")
        shape = next((child for child in marker.iter() if _local(child) in drawable), None)
        if shape is None:
            return "none"
        outer = computed_properties(marker, {}, self.rules, [self.root])
        props = computed_properties(shape, outer, self.rules, [self.root, marker])
        fill = props.get("fill", "black").strip().lower()
        filled = fill not in NO_PAINT
        colour = parse_colour(fill, props)
        painted_as_paper = colour_hex(colour)[:7] in (self.background, "#FFFFFF")
        outlined = _has_line(props) and parse_colour(props["stroke"], props) != colour
        hollow = not filled or (outlined and painted_as_paper)
        if _local(shape) in ("circle", "ellipse"):
            return "circle" if hollow else "solidCircle"
        numbers = NUMBER_RE.findall(shape.get("points") or shape.get("d") or "")
        coordinates = [float(number) for number in numbers]
        if _is_diamond(coordinates):
            return "openDiamond" if hollow else "diamond"
        if len(coordinates) == 6 and filled and hollow:
            return "solidArrow"
        if len(coordinates) not in (6, 8):
            self._skip("line ending other than an arrow, a circle or a diamond drawn as an arrow")
        return "filledArrow" if filled else "arrow"

    # -- shapes -----------------------------------------------------------

    def _add_box(
        self, basic: str | None, local: Rect, matrix: Matrix, paint: Paint, subpath: Subpath
    ) -> None:
        """Add a box: a Basic shape set in its frame, or else its exact closed path."""
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
        if self.items and isinstance(below := self.items[-1], Box) and _same_place(below, box):
            # A tint drawn over an opaque copy of the same shape, so lines behind it
            # stay hidden: one shape, keeping the tint at its own opacity.
            fill = box.paint.fill if box.paint.filled else below.paint.fill
            line = box.paint if box.paint.line_width > 0 else below.paint
            box.paint = Paint(fill, line.stroke, line.line_width, line.pattern)
            box.order = below.order
            self.items[-1] = box
        else:
            self.items.append(box)

    def _covers_canvas(self, x: float, y: float, w: float, h: float, matrix: Matrix) -> bool:
        """Whether a rectangle covers the whole page, as the paper does."""
        left, top, right, bottom = bounds([apply(matrix, (x, y)), apply(matrix, (x + w, y + h))])
        width, height = self.view[2:]
        return left <= 0.5 and top <= 0.5 and right >= width - 0.5 and bottom >= height - 0.5

    def _take_as_paper(self, props: Props, opacity: float) -> None:
        """The page itself: its opaque colour becomes the page's background.

        Decorative layers over it (the dot pattern) are left to the editor's grid.
        """
        fill = props.get("fill", "black")
        paper = None if "url(" in fill else self._colour(fill, props)
        alpha = opacity * length(props.get("fill-opacity"), 1.0, percent_of=1.0)
        if self.background is None and paper is not None and paper[3] * alpha >= 0.999:
            self.background = colour_hex(paper)

    def _rect(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A rectangle becomes a Square, Rounded Rectangle or Pill; the paper, the background."""
        vw, vh = self.view[2], self.view[3]
        x, y = length(element.get("x"), percent_of=vw), length(element.get("y"), percent_of=vh)
        w = length(element.get("width"), percent_of=vw)
        h = length(element.get("height"), percent_of=vh)
        if w <= 0 or h <= 0:
            return
        if self._covers_canvas(x, y, w, h, matrix) and not _has_line(props):  # else a page frame
            self._take_as_paper(props, opacity)
            return
        radius = length(element.get("rx", element.get("ry")))
        corners: list[Segment] = [Line((x + w, y)), Line((x + w, y + h)), Line((x, y + h))]
        outline = Subpath((x, y), corners, closed=True)
        paint = self._paint(props, opacity, matrix)
        self._add_box(rectangle_shape(w, h, radius), (x, y, w, h), matrix, paint, outline)

    def _ellipse(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A circle or ellipse becomes a Circle."""
        rx = length(element.get("rx", element.get("r")))
        ry = length(element.get("ry", element.get("r")))
        if rx > 0 and ry > 0:
            cx = length(element.get("cx"), percent_of=self.view[2])
            cy = length(element.get("cy"), percent_of=self.view[3])
            paint = self._paint(props, opacity, matrix)
            local = (cx - rx, cy - ry, 2 * rx, 2 * ry)
            self._add_box("Circle", local, matrix, paint, ellipse_subpath(cx, cy, rx, ry))

    def _line(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A ``<line>`` is an open outline of one segment."""
        vw, vh = self.view[2], self.view[3]
        start = (length(element.get("x1"), percent_of=vw), length(element.get("y1"), percent_of=vh))
        end = (length(element.get("x2"), percent_of=vw), length(element.get("y2"), percent_of=vh))
        paint = self._paint(props, opacity, matrix)
        self._add_outline(Subpath(start, [Line(end)]), paint, props, matrix)

    def _polyline(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """A polyline is an open outline of straight segments; a polygon, a closed one."""
        values = [float(v) for v in NUMBER_RE.findall(element.get("points", ""))]
        points = list(zip(values[0::2], values[1::2], strict=False))  # an odd last value is ignored
        if len(points) >= 2 and all(map(math.isfinite, values)):
            closed = _local(element) == "polygon"
            subpath = Subpath(points[0], [Line(p) for p in points[1:]], closed)
            self._add_outline(subpath, self._paint(props, opacity, matrix), props, matrix)

    def _path(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """Each subpath becomes its own outline; a hole in a filled shape keeps its line."""
        try:
            subpaths = parse_path_data(element.get("d", ""))
        except ValueError:
            self._skip("<path> with unreadable data left out")
            return
        paint = self._paint(props, opacity, matrix)
        outlines = [(s, s.flattened()) for s in subpaths if s.closed]
        for subpath in subpaths:
            # Inside an odd number of other outlines is a hole; in a hole again, an island.
            depth = sum(
                other is not subpath and point_in_polygon(subpath.start, flat)
                for other, flat in outlines
            )
            if subpath.closed and paint.filled and depth % 2 == 1:
                # A path cannot cut a hole in another, so a hole keeps only its outline.
                self._skip("hole in a filled shape, kept as an outline only")
                if paint.line_width > 0:
                    rim = Paint(TRANSPARENT, paint.stroke, paint.line_width, paint.pattern)
                    self._add_outline(subpath, rim, props, matrix)
                continue
            self._add_outline(subpath, paint, props, matrix)

    def _add_outline(self, subpath: Subpath, paint: Paint, props: Props, matrix: Matrix) -> None:
        """A closed outline becomes a box, an open one a stroke; one painting nothing is dropped."""
        if subpath.closed and len(subpath.flattened()) >= 3:
            if paint.filled or paint.line_width > 0:
                self._add_box(None, (0, 0, 0, 0), matrix, paint, subpath)
            return
        # SVG fills an open path as if it were closed: the fill goes below its line.
        fill = None
        if paint.filled and enclosed_area(subpath.flattened()) > MIN_FILLED_AREA:
            shape = Subpath(subpath.start, subpath.segments, closed=True)
            below = replace(paint, stroke=TRANSPARENT, line_width=0, pattern="solid")
            self._add_box(None, (0, 0, 0, 0), matrix, below, shape)
            fill, paint = self.items[-1], replace(paint, fill=TRANSPARENT)
        if paint.line_width > 0:  # an open shape with no line draws no line to keep
            start = self._ending(props.get("marker-start"))
            end = self._ending(props.get("marker-end"))
            stroke = Stroke(len(self.items), subpath.transformed(matrix), paint, start, end)
            stroke.fill = fill if isinstance(fill, Box) else None
            self.items.append(stroke)

    # -- text -------------------------------------------------------------

    def _text(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """Each ``<text>``, and each separately placed ``<tspan>`` in it, becomes one line."""

        def placed(node: ET.Element, size: float, x: float, y: float) -> Point:
            """Where a node places its text, from its own position or the one before."""
            x = length(node.get("x"), x, percent_of=self.view[2])
            y = length(node.get("y"), y, percent_of=self.view[3])
            dx = length(node.get("dx"), font_size=size)
            dy = length(node.get("dy"), font_size=size)
            return x + dx, y + dy

        size = length(props.get("font-size"), 16.0)
        lines: list[tuple[Point, Props, list[str]]] = [
            (placed(element, size, 0.0, 0.0), props, [element.text or ""])
        ]
        for child in element:
            if _local(child) == "textPath":
                self._skip("<textPath> left out")
            elif _local(child) in ("tspan", "a"):
                ancestors = [*self.ancestors, element]
                child_props = computed_properties(child, props, self.rules, ancestors)
                shown = child_props.get("display") != "none" and not _is_invisible(child_props)
                text = "".join(child.itertext())
                if shown and any(child.get(key) is not None for key in ("x", "y", "dy")):
                    child_size = length(child_props.get("font-size"), 16.0)
                    anchor = placed(child, child_size, *lines[-1][0])
                    lines.append((anchor, child_props, [text]))
                elif shown:
                    lines[-1][2].append(f" {text}" if child.get("dx") is not None else text)
                    line_style = lines[-1][1]
                    if any(child_props.get(k) != line_style.get(k) for k in TEXT_STYLE):
                        self._skip("styled words inside a line take the line's style")
            lines[-1][2].append(child.tail or "")
        for anchor, line_props, parts in lines:
            align = _alignment(line_props.get("text-anchor", ""))
            paint = line_props.get("fill", "black")
            self._add_label("".join(parts), anchor, line_props, matrix, opacity, align, paint)

    def _foreign_object(
        self, element: ET.Element, props: Props, matrix: Matrix, opacity: float
    ) -> None:
        """Plain HTML text in a box wraps in SimpleDiagrams as it does in the browser."""
        embedded = ("img", "svg", "video", "canvas", "iframe")
        if any(_local(child) in embedded for child in element.iter()):
            self._skip("<foreignObject> holding more than text left out")
            return
        x, y, w, h = (length(element.get(key)) for key in ("x", "y", "width", "height"))
        # The text takes the style of the innermost single wrapper, usually one <div>.
        holder, ancestors = element, list(self.ancestors)
        while len(holder) == 1:
            ancestors.append(holder)
            holder = holder[0]
            props = computed_properties(holder, props, self.rules, ancestors)
        if len(holder) > 1:
            self._skip("rich HTML text kept as plain text")
        align = _alignment(props.get("text-align", ""))
        wrap_box = (x, y, w, h) if w > 0 and h > 0 else None
        paint = props.get("color", "black")
        self._add_label(_html_text(element), (x, y), props, matrix, opacity, align, paint, wrap_box)

    def _use(self, element: ET.Element, props: Props, matrix: Matrix, opacity: float) -> None:
        """An icon placed by reference becomes SVG artwork, painted as the placement paints it."""
        reference = element.get("href") or element.get(XLINK_HREF) or ""
        target = self.by_id.get(reference[1:]) if reference.startswith("#") else None
        if target is None:
            self._skip("<use> of nothing left out")
            return
        colour = colour_hex(parse_colour(props.get("color", "black"), props))[:7]
        paint = {"color": colour} | ({"opacity": f"{opacity:g}"} if opacity < 1 else {})
        context = props | {"color": colour}  # what the icon's markup inherits on the page
        ancestors = [self.root]
        if _local(target) == "symbol":
            context = computed_properties(target, context, self.rules, ancestors)
            ancestors = [self.root, target]
        x, y = length(element.get("x")), length(element.get("y"))
        view = [float(v) for v in NUMBER_RE.findall(target.get("viewBox", ""))]
        if _local(target) == "symbol" and len(view) == 4 and view[2] > 0 and view[3] > 0:
            # A symbol draws its view box into the placement's width and height.
            painted = {k: v for k, v in target.attrib.items() if k in PRESENTATION - EFFECTS}
            w = length(element.get("width"), view[2], percent_of=view[2])
            h = length(element.get("height"), view[3], percent_of=view[3])
            parts = self._icon_copy(list(target), context, paint | painted, ancestors)
            box = (view[0], view[1], view[2], view[3])
            self._add_icon(box, parts, paint | painted, (x, y, w, h), matrix)
        else:
            parts = list(target) if _local(target) == "symbol" else [target]
            if (extent := self._extent(parts, props)) is None:
                return
            local = (x + extent[0], y + extent[1], extent[2], extent[3])
            copies = self._icon_copy(parts, context, paint, ancestors)
            self._add_icon(extent, copies, paint, local, matrix)

    def _nested_svg(
        self,
        element: ET.Element,
        props: Props,
        matrix: Matrix,
        opacity: float,
        ancestors: list[ET.Element],
    ) -> None:
        """A nested ``<svg>`` with a view box is an icon in its own frame, as a symbol is."""
        x, y = length(element.get("x")), length(element.get("y"))
        path = [*ancestors, element]
        view = [float(v) for v in NUMBER_RE.findall(element.get("viewBox", ""))]
        if len(view) != 4 or view[2] <= 0 or view[3] <= 0:
            moved = multiply(matrix, (1, 0, 0, 1, x, y))
            for child in element:
                self._walk(child, props, moved, opacity, path)
            return
        w = length(element.get("width"), self.view[2], percent_of=self.view[2])
        h = length(element.get("height"), self.view[3], percent_of=self.view[3])
        paint = {name: props[name] for name in sorted(ICON_PAINT & props.keys())}
        paint |= {k: props[k] for k in sorted(ICON_LINE & props.keys()) if props[k].strip()}
        paint.pop("opacity", None)  # already in ``opacity``, with the page's around it
        if opacity < 1:
            paint["opacity"] = f"{opacity:g}"
        parts = self._icon_copy(list(element), props, paint, path)
        box = (view[0], view[1], view[2], view[3])
        self._add_icon(box, parts, paint, (x, y, w, h), matrix)

    def _add_icon(
        self, view: Rect, parts: Sequence[ET.Element], paint: Props, local: Rect, matrix: Matrix
    ) -> None:
        """Add an icon as artwork, or note that it could not be stored; all hidden adds nothing."""
        if all(_local(item) in ICON_STRUCTURE for part in parts for item in part.iter()):
            return
        if (asset := svg_asset(view, parts, paint)) is None:
            self._skip("icon SimpleDiagrams cannot store safely left out")
        else:
            self._add_artwork(local, matrix, asset)

    def _icon_copy(
        self, parts: Sequence[ET.Element], page: Props, paint: Props, ancestors: list[ET.Element]
    ) -> list[ET.Element]:
        """Copies of icon markup, which is stored without the page's stylesheet."""
        stored = computed_properties(ET.Element("g", paint), {}, (), ())
        copies = (self._frozen(part, page, stored, ancestors) for part in parts)
        return [copy for copy in copies if copy is not None]

    def _frozen(
        self, element: ET.Element, page: Props, stored: Props, ancestors: list[ET.Element]
    ) -> ET.Element | None:
        """Copy one element for a stored icon; ``None`` when nothing of it shows.

        The app's renderer ignores ``display`` and ``visibility``, so what they hide is left out.
        """
        page = computed_properties(element, page, self.rules, ancestors)
        if page.get("display") == "none":
            return None
        clone, stored = _styled_clone(element, page, stored)
        path = [*ancestors, element]
        for child in element:
            if (copy := self._frozen(child, page, stored, path)) is not None:
                clone.append(copy)
            else:
                _keep_words_after_removed_child(clone, child.tail)
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

    def _extent(self, parts: Sequence[ET.Element], props: Props) -> Rect | None:
        """The bounds of drawing that has no view box of its own, with room for its lines."""
        saved, self.items = self.items, []
        for part in parts:
            self._walk(part, props, IDENTITY, 1.0, [])
        drawn, self.items = self.items, saved
        outlines = [
            (item.outline if isinstance(item, Box) else item.subpath.flattened(), item.paint)
            for item in drawn
            if isinstance(item, (Box, Stroke))
        ]
        if not outlines:
            return None
        left, top, right, bottom = bounds(point for outline, _ in outlines for point in outline)
        pad = max(paint.line_width for _, paint in outlines) / 2 + 0.5
        return left - pad, top - pad, right - left + 2 * pad, bottom - top + 2 * pad

    def _add_artwork(self, local: Rect, matrix: Matrix, asset: Asset) -> None:
        """Add a picture in its frame; a skewed or empty one cannot be shown."""
        placed = placed_frame(local, matrix)
        if placed is None or local[2] <= 0 or local[3] <= 0:
            self._skip("skewed or empty picture left out")
            return
        self.items.append(Artwork(len(self.items), *placed, asset))

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
        match props.get("text-transform", ""):
            case "uppercase":
                string = string.upper()
            case "lowercase":
                string = string.lower()
        turn = decompose(matrix)
        size = max(1.0, length(props.get("font-size"), 16.0))
        weight = props.get("font-weight", "400").lower()
        heavy = weight in ("bold", "bolder") or length(weight) >= 600
        text_opacity = opacity * length(props.get("fill-opacity"), 1.0, percent_of=1.0)
        style = TextStyle(
            font_family=_font_family(props.get("font-family")),
            font_size=size * (turn[2] if turn else 1.0),
            weight="bold" if heavy else "medium" if length(weight) >= 500 else "regular",
            italic=props.get("font-style", "") in ("italic", "oblique"),
            underlined="underline" in props.get("text-decoration", ""),
            colour=colour_hex(self._colour(paint, props), text_opacity),
        )
        spacing = length(props.get("letter-spacing"), font_size=size)
        self.items.append(
            Label(len(self.items), string, anchor, matrix, align, style, size, spacing, wrap_box)
        )


def _alignment(value: str) -> Alignment:
    """A ``text-anchor`` or ``text-align`` value as a text alignment."""
    if value in ("middle", "center"):
        return "center"
    return "trailing" if value in ("end", "right") else "leading"


HTML_BREAKS = ("br", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6")


def _html_text(element: ET.Element) -> str:
    """The words in an HTML fragment; a line break separates words."""
    words = [element.text or ""]
    for child in element:
        if _local(child) not in ("style", "script"):
            words += [" " if _local(child) in HTML_BREAKS else "", _html_text(child)]
        words.append(child.tail or "")
    return "".join(words)


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
    _fold_labels(labels, hosts)

    strokes = [item for item in items if isinstance(item, Stroke)]
    swimlanes = find_swimlanes(strokes, [label for label in labels if label.kind == "text"])
    lane_lines = {id(line) for shape in swimlanes for line in shape.dividers}
    strokes = [stroke for stroke in strokes if id(stroke) not in lane_lines]
    connections = _classify_strokes(strokes, boxes, hosts)
    _settle_boxes(boxes, containers, hosts, connections, paper)
    for artwork in (item for item in items if isinstance(item, Artwork)):
        artwork.kind, artwork.host = (
            "artwork",
            hosts.of([artwork.centre], artwork.order, artwork.area),
        )

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


def _fold_labels(labels: Sequence[Label], hosts: Hosts) -> None:
    """Fold each label into the box whose text it continues; the rest become free text."""
    # A box's text is read from its top line down, whatever order the SVG drew it in.
    for label in reading_order(labels):
        on = hosts.of([label.centre], label.order)
        if on is not None and _folds_into(label, on):
            on.labels.append(label)
        else:
            label.kind, label.host = "text", on
    for box in hosts.boxes:  # a custom outline can only hold its label in the middle
        extents = [label.page_bounds() for label in box.labels]
        if extents and box.basic is None and not _is_centred(_union(extents), box.frame):
            for label in box.labels:
                label.kind, label.host = "text", box
            box.labels.clear()


def _classify_strokes(
    strokes: Sequence[Stroke], boxes: Sequence[Box], hosts: Hosts
) -> list[Connection]:
    """Mark the connectors and return them with the boxes they touch; the rest are lines."""
    connections: list[Connection] = []
    for stroke in strokes:
        flat = stroke.subpath.flattened()
        others = [box for box in boxes if box is not stroke.fill]  # never its own fill
        start, end = _touching(others, flat[0]), _touching(others, flat[-1])
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
    hosts: Hosts,
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
        and hosts.of([box.centre], box.order, box.area) is None
    ]
    plain = [box for box in free_standing if box.paint.fill in (TRANSPARENT, paper)]
    labelling = _label_connectors(plain, [stroke for stroke, _, _ in connections])
    for box in boxes:
        if id(box) in labelling:
            continue  # drawn as its connector's label
        if box.matched and not box.labels and id(box) not in connected:
            box.keep_exact()
        box.kind, box.host = "box", hosts.of([box.centre], box.order, box.area)


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


def _touching(boxes: Sequence[Box], point: Point) -> Box | None:
    """The smallest box whose outline passes within attaching distance of ``point``."""

    def reach(box: Box) -> float:
        """How near the outline a line end attaches, allowing for the line's own width."""
        return ATTACH_TOLERANCE + box.paint.line_width / 2

    near = [
        box
        for box in boxes
        if box.near(point, reach(box)) and distance_to_outline(point, box.outline) <= reach(box)
    ]
    return min(near, key=attrgetter("area"), default=None)


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
        if len(stroke.subpath.segments) != 1 or stroke.start_ending != stroke.end_ending:
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
    return _rect_record(x, y, w, h)


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
            if math.dist(start, current) > ROUNDING_SIZE:
                return None  # a real curve, not a rounding or a hop
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
        span = max(1.0, needed / w)
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
        return element_record(core)

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


def export_document(html: str, source_path: Path) -> Export:
    """Translate source HTML into a SimpleDiagrams document."""
    root = ET.fromstring(export_svg.export_svg_document(html, source_path, system_fonts=True))
    reader = Reader(root).read()
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
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for what, count in sorted(export.skipped.items()):
        print(f"note: {what} ({count})", file=sys.stderr)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
