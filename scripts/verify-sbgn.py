#!/usr/bin/env python3
"""Verify the SBGN process-description HTML contract using only the stdlib.

Checks unique IDs, arc kinds, bipartite species/process arcs, compartment
containment, glyph kinds, and the Bruno ceiling. Containment reads x, y, width
and height, so a transform or positional CSS on a glyph, its bounds or an
ancestor group inside the map is a finding. The crossing check reads raw path
data, so the same holds for an arc and its ancestor groups. Every connector drawn in the map
must be a declared arc, except legend samples inside <g data-role="legend">.
Arcs are flattened to their drawn stroke (curves and elliptical arcs sampled)
and may not cross, touch, overlap, or end on another arc, except at a shared
glyph port or under the documented hop over exactly one other route. Files without data-diagram="sbgn" are
skipped. This verifies authored declarations, not whether they describe an
external SBML model.

Usage: python3 scripts/verify-sbgn.py [--all | FILE ...]
No arguments and --all check every shipped SBGN example.
Exit: 0 clean, 1 contract findings, 2 unreadable input/usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER_RE = re.compile(NUMBER)
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
DIAGRAM = "sbgn"
GLYPH_KINDS = {"macromolecule", "process", "compartment", "source-sink"}
ARC_KINDS = {"consumption", "production", "reversible", "modulation"}
ARC_LIST = ", ".join(sorted(ARC_KINDS))
GLYPH_LIST = ", ".join(sorted(GLYPH_KINDS))
SPECIES = {"macromolecule", "source-sink"}
MAX_MACRO = 7
MAX_PROCESS = 6
MAX_COMPARTMENT = 1
MAX_SOURCE = 2
# The Bruno map draws 16 arcs; SBGN's ceiling replaces SKILL.md's 9 node / 12 arrow rows.
MAX_ARC = 16
GRID = 4.0
EPS = 1e-6
MAX_COORDINATE = 1e7
# CSS properties that move or resize an SVG element away from the x, y,
# width and height attributes the containment check reads.
POSITION_PROPERTIES = {
    "transform", "translate", "rotate", "scale", "x", "y", "width", "height",
    "offset", "offset-path", "offset-distance", "offset-position", "offset-anchor", "offset-rotate",
}
# Elements that draw a line between two places. Inside the map each must be a
# declared arc, part of a glyph, or a legend sample.
CONNECTOR_TAGS = {"path", "line", "polyline", "polygon", "use"}
NON_RENDERED = {"defs", "marker", "pattern", "clippath", "mask", "symbol", "lineargradient",
                "radialgradient", "filter", "title", "desc", "metadata"}
LEGEND_TAGS = {"g", "line", "rect", "circle", "text", "tspan"}
CSS_ESCAPE_RE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?|\\(.)", re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_BLOCK_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    duplicates: set[str] = field(default_factory=set)

    def ancestors(self):
        current = self.parent
        while current is not None:
            yield current
            current = current.parent


class Scanner(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, 1)
        self.stack = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []
        self.stylesheets: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        values = {}
        duplicates = set()
        for name, value in attrs:
            if name in values:
                duplicates.add(name)
            values.setdefault(name, value or "")
        node = Node(tag, values, self.getpos()[0], self.stack[-1], duplicates=duplicates)
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        indexes = [i for i, node in enumerate(self.stack) if node.tag == tag]
        in_svg = any(node.tag == "svg" for node in self.stack)
        if not indexes:
            if in_svg:
                self.errors.append(f"line {self.getpos()[0]}: malformed SVG closing tag {tag}")
            return
        index = indexes[-1]
        if in_svg and index != len(self.stack) - 1:
            self.errors.append(f"line {self.getpos()[0]}: malformed SVG nesting at {tag}")
        del self.stack[index:]

    def handle_data(self, data):
        if self.stack[-1].tag == "style":
            self.stylesheets.append((self.getpos()[0], data))

    def finish(self, source):
        self.feed(source)
        self.close()
        if any(node.tag == "svg" for node in self.stack):
            self.errors.append("unclosed SVG")


@dataclass
class Box:
    node: Node
    identity: str
    kind: str
    x: float
    y: float
    w: float
    h: float
    compartment: str | None = None

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h


def number(raw: str) -> float:
    if not NUMBER_RE.fullmatch(raw.strip()):
        raise ValueError("missing, malformed or non-finite number")
    value = float(raw)
    if not math.isfinite(value) or abs(value) > MAX_COORDINATE:
        raise ValueError("number must be finite and within 10,000,000 units")
    return value


def on_grid(value: float) -> bool:
    ratio = value / GRID
    return math.isfinite(ratio) and abs(ratio - round(ratio)) <= EPS


def identity_ok(raw: str) -> bool:
    return bool(raw) and ID_RE.fullmatch(raw) is not None


def within_box(inner: Box, outer: Box) -> bool:
    return (inner.x + EPS >= outer.x and inner.y + EPS >= outer.y
            and inner.right <= outer.right + EPS and inner.bottom <= outer.bottom + EPS)


def parse_bounds(carrier: Node) -> tuple[float, float, float, float]:
    bounds = [child for child in carrier.children if child.attrs.get("data-role") == "bounds"]
    target = bounds[0] if len(bounds) == 1 else carrier
    if carrier.attrs.get("data-role") == "bounds":
        target = carrier
    elif len(bounds) != 1 and carrier.tag != "rect":
        raise ValueError("glyph must expose exactly one data-role=\"bounds\" rect")
    if target.tag != "rect":
        # Only a rect is drawn from x, y, width and height; any other shape
        # would be measured at one place and drawn at another.
        raise ValueError(f"glyph bounds must be a <rect>; found <{target.tag}>")
    attrs = target.attrs
    x = number(attrs.get("x", ""))
    y = number(attrs.get("y", ""))
    w = number(attrs.get("width", ""))
    h = number(attrs.get("height", ""))
    if w <= 0 or h <= 0:
        raise ValueError("bounds width and height must be positive")
    return x, y, w, h


def _split_top_level(text: str, separators: str) -> list[str]:
    """Split at separators outside quotes, brackets and parentheses."""
    parts, current, depth, quote, index = [], [], 0, "", 0
    while index < len(text):
        char = text[index]
        escape = CSS_ESCAPE_RE.match(text, index) if char == "\\" else None
        if escape:
            # A hex escape may swallow one whitespace; it is not a combinator.
            current.append(escape.group(0))
            index = escape.end()
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and char in separators:
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _css_unescape(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            code = int(match.group(1), 16)
            return chr(code) if 0 < code <= 0x10FFFF else "\ufffd"
        return match.group(2)
    return CSS_ESCAPE_RE.sub(replace, text)


def positional_properties(declarations: str) -> list[str]:
    """CSS property names in a declaration block that can move an element."""
    found = []
    for declaration in _split_top_level(CSS_COMMENT_RE.sub("", declarations), ";"):
        name, colon, _value = declaration.partition(":")
        name = _css_unescape(name).strip().lower()
        if colon and name in POSITION_PROPERTIES:
            found.append(name)
    return found


# Selector matching is three-valued: True (matches), False (cannot match), or
# None (may match: a part the checker cannot evaluate, such as :hover or a
# sibling combinator). A rule is a finding unless every selector is False for
# every positioned element.
PSEUDO_ELEMENTS = {"before", "after", "first-line", "first-letter", "marker", "placeholder",
                   "selection", "backdrop", "file-selector-button"}
HEAD_TAGS = {"head", "title", "meta", "link", "style", "script", "base", "noscript", "template"}
ATTRIBUTE_RE = re.compile(
    r"""^\s*(?:(?P<ns>[^\s|=~^$*\]]*)\|(?!=))?(?P<name>[^\s|=~^$*\]]+)\s*"""
    r"""(?:(?P<op>[~|^$*]?=)\s*(?P<value>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s\]]+)"""
    r"""\s*(?P<flag>[iIsS])?)?\s*$""",
    re.DOTALL,
)


def _tri_and(left: bool | None, right: bool | None) -> bool | None:
    if left is False or right is False:
        return False
    if left is None or right is None:
        return None
    return True


def _tri_or(left: bool | None, right: bool | None) -> bool | None:
    if left is True or right is True:
        return True
    if left is None or right is None:
        return None
    return False


def _read_ident(text: str, index: int) -> tuple[str, int]:
    """Read a CSS identifier (escapes decoded) starting at index."""
    out = []
    while index < len(text):
        char = text[index]
        escape = CSS_ESCAPE_RE.match(text, index) if char == "\\" else None
        if escape:
            out.append(_css_unescape(escape.group(0)))
            index = escape.end()
        elif char.isalnum() or char in "-_" or ord(char) > 0x7F:
            out.append(char)
            index += 1
        else:
            break
    return "".join(out), index


def _read_group(text: str, index: int, close: str) -> tuple[str, int]:
    """Read from an opening ( or [ to its matching close, outside quotes."""
    depth, quote, start = 0, "", index
    while index < len(text):
        char = text[index]
        escape = CSS_ESCAPE_RE.match(text, index) if char == "\\" else None
        if escape:
            index = escape.end()
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    return text[start + 1:], index


def parse_selector(selector: str) -> list[tuple[str, str]] | None:
    """Split one complex selector into (combinator, compound) pairs.

    The first pair's combinator is empty. None means the selector could not be
    split (for example a leading combinator), which callers treat as may match.
    """
    parts: list[tuple[str, str]] = []
    current: list[str] = []
    pending = ""
    index = 0
    while index < len(selector):
        char = selector[index]
        escape = CSS_ESCAPE_RE.match(selector, index) if char == "\\" else None
        if escape:
            current.append(escape.group(0))
            index = escape.end()
            continue
        if char in "([":
            group, end = _read_group(selector, index, ")" if char == "(" else "]")
            current.append(selector[index:end])
            index = end
            continue
        if char in " \t\r\n\f>+~":
            if current:
                parts.append((pending, "".join(current)))
                current = []
                pending = " "
            if char in ">+~":
                if not parts:
                    return None
                pending = char
            index += 1
            continue
        current.append(char)
        index += 1
    if current:
        parts.append((pending, "".join(current)))
    elif parts and pending.strip():
        return None
    return parts or None


def _attribute_match(inner: str, node: Node) -> bool | None:
    match = ATTRIBUTE_RE.match(inner)
    if not match:
        return None
    if match.group("ns") not in (None, "", "*"):
        return None
    name = _css_unescape(match.group("name")).lower()
    if name not in node.attrs:
        return False
    op = match.group("op")
    if not op:
        return True
    raw = match.group("value")
    if raw[:1] in "\"'":
        raw = raw[1:-1]
    expected = _css_unescape(raw)
    actual = node.attrs[name]
    if (match.group("flag") or "").lower() == "i":
        expected, actual = expected.lower(), actual.lower()
    if op == "=":
        return actual == expected
    if op == "~=":
        return expected in actual.split()
    if op == "|=":
        return actual == expected or actual.startswith(expected + "-")
    if not expected:
        return False
    if op == "^=":
        return actual.startswith(expected)
    if op == "$=":
        return actual.endswith(expected)
    return expected in actual


def compound_match(compound: str, node: Node, parent_of) -> bool | None:
    """Match one compound selector against one element, three-valued."""
    result: bool | None = True
    index = 0
    name, end = _read_ident(compound, index)
    if compound.startswith("*"):
        name, end = "*", 1
    if end < len(compound) and compound[end] == "|":
        # A namespace prefix; the element name follows it.
        if name not in ("", "*"):
            result = None
        name, end = (("*", end + 2) if compound[end + 1:end + 2] == "*"
                     else _read_ident(compound, end + 1))
    if name and name != "*" and name.lower() != node.tag:
        return False
    index = end
    while index < len(compound):
        char = compound[index]
        if char == ".":
            value, index = _read_ident(compound, index + 1)
            if not value:
                result = _tri_and(result, None)
            elif value not in node.attrs.get("class", "").split():
                return False
        elif char == "#":
            value, index = _read_ident(compound, index + 1)
            if not value:
                result = _tri_and(result, None)
            elif node.attrs.get("id") != value:
                return False
        elif char == "[":
            inner, index = _read_group(compound, index, "]")
            result = _tri_and(result, _attribute_match(inner, node))
            if result is False:
                return False
        elif char == ":":
            element = compound.startswith("::", index)
            index += 2 if element else 1
            value, index = _read_ident(compound, index)
            if index < len(compound) and compound[index] == "(":
                _inner, index = _read_group(compound, index, ")")
            value = value.lower()
            if element or value in PSEUDO_ELEMENTS:
                # The rule styles a generated box, not the element itself.
                return False
            if value == "root":
                if not (node.tag == "html" and parent_of(node) is None):
                    return False
            else:
                result = _tri_and(result, None)
        else:
            return _tri_and(result, None)
    return result


def selector_matches(selector: str, node: Node, parent_of) -> bool | None:
    """Match a complex selector against node and its real ancestor chain."""
    parts = parse_selector(selector.strip())
    if parts is None:
        return None
    memo: dict[tuple[int, int], bool | None] = {}

    def match(position: int, element: Node) -> bool | None:
        key = (position, id(element))
        if key in memo:
            return memo[key]
        combinator, compound = parts[position]
        result = compound_match(compound, element, parent_of)
        if result is not False and position > 0:
            if combinator in "+~":
                rest: bool | None = None
            elif combinator == ">":
                parent = parent_of(element)
                rest = match(position - 1, parent) if parent is not None else False
            else:
                rest = False
                ancestor = parent_of(element)
                while ancestor is not None and rest is not True:
                    rest = _tri_or(rest, match(position - 1, ancestor))
                    ancestor = parent_of(ancestor)
            result = _tri_and(result, rest)
        memo[key] = result
        return result

    return match(len(parts) - 1, node)


def ancestry(scanner: Scanner):
    """Parent lookup that adds the <html> and <body> a browser would imply."""
    real_html = next((node for node in scanner.nodes if node.tag == "html"), None)
    has_body = any(node.tag == "body" for node in scanner.nodes)
    implied_html = None if real_html else Node("html", {}, 0)
    implied_body = None if has_body else Node("body", {}, 0)
    html = real_html or implied_html

    def parent_of(node: Node) -> Node | None:
        if node is implied_html or node is real_html:
            return None
        if node is implied_body:
            return html
        parent = node.parent
        if parent is None:
            return None
        if parent.tag == "document":
            parent = html
        if parent is html and implied_body is not None and node.tag not in HEAD_TAGS | {"head", "body"}:
            return implied_body
        return parent

    return parent_of


def sample_extent(node: Node) -> tuple[float, float, float, float] | None:
    """Axis-aligned extent (x0, y0, x1, y1) of a legend sample, None for text."""
    attrs = node.attrs
    if node.tag == "line":
        x1, y1 = number(attrs.get("x1", "0")), number(attrs.get("y1", "0"))
        x2, y2 = number(attrs.get("x2", "0")), number(attrs.get("y2", "0"))
        return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
    if node.tag == "rect":
        x, y = number(attrs.get("x", "0")), number(attrs.get("y", "0"))
        return x, y, x + number(attrs.get("width", "")), y + number(attrs.get("height", ""))
    if node.tag == "circle":
        cx, cy, r = number(attrs.get("cx", "0")), number(attrs.get("cy", "0")), number(attrs.get("r", ""))
        return cx - r, cy - r, cx + r, cy + r
    return None


def overlaps(extent: tuple[float, float, float, float], box: Box) -> bool:
    x0, y0, x1, y1 = extent
    return x0 <= box.right + EPS and x1 + EPS >= box.x and y0 <= box.bottom + EPS and y1 + EPS >= box.y


PATH_TOKEN_RE = re.compile(r"[A-Za-z]|" + NUMBER)
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "T": 2, "C": 6, "S": 4, "A": 7, "Z": 0}
CURVE_STEPS = 32
TOUCH = 1e-6  # distance under which two strokes count as meeting

Point = tuple[float, float]


@dataclass
class Route:
    """A drawn arc flattened to its stroke.

    segments holds (start, end, piece) with piece indexing pieces; each piece
    is one path command, kept so a hop (an elliptical arc command) and its
    chord can be found again.
    """
    node: Node
    name: str
    segments: list[tuple[Point, Point, int]]
    pieces: list[tuple[str, Point, Point]]
    head: Point
    tail: Point


def _quadratic(p0: Point, p1: Point, p2: Point) -> list[Point]:
    out = []
    for step in range(1, CURVE_STEPS + 1):
        t = step / CURVE_STEPS
        a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1]))
    return out


def _cubic(p0: Point, p1: Point, p2: Point, p3: Point) -> list[Point]:
    out = []
    for step in range(1, CURVE_STEPS + 1):
        t = step / CURVE_STEPS
        a, b, c, d = (1 - t) ** 3, 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t), t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def _elliptical_arc(p0: Point, rx: float, ry: float, rotation: float, large: float, sweep: float,
                    p1: Point) -> list[Point]:
    """Sample an SVG arc command (SVG 1.1 F.6.5 endpoint to center form)."""
    if large not in (0.0, 1.0) or sweep not in (0.0, 1.0):
        raise ValueError("arc flags must be 0 or 1")
    if _same(p0, p1):
        return []
    rx, ry = abs(rx), abs(ry)
    if rx <= EPS or ry <= EPS:
        return [p1]
    phi = math.radians(rotation % 360)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    scale = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry)
    if scale > 1:  # F.6.6: radii too small, scale them up
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    numerator = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    denominator = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    factor = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        factor = -factor
    cxp, cyp = factor * rx * y1p / ry, -factor * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (p0[0] + p1[0]) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (p0[1] + p1[1]) / 2

    def angle(ux: float, uy: float, vx: float, vy: float) -> float:
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    theta = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(CURVE_STEPS, math.ceil(abs(delta) / (math.pi / CURVE_STEPS)))
    out = []
    for step in range(1, steps + 1):
        t = theta + delta * step / steps
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append((cos_phi * x - sin_phi * y + cx, sin_phi * x + cos_phi * y + cy))
    out[-1] = p1
    return out


def flatten_route(node: Node, name: str) -> Route:
    """Flatten an arc element to the stroke a browser draws."""
    segments: list[tuple[Point, Point, int]] = []
    pieces: list[tuple[str, Point, Point]] = []

    def add(kind: str, start: Point, points: list[Point]) -> None:
        if not points:
            return
        pieces.append((kind, start, points[-1]))
        previous = start
        for point in points:
            if not _same(previous, point):
                segments.append((previous, point, len(pieces) - 1))
            previous = point

    if node.tag == "line":
        a = (number(node.attrs.get("x1", "0")), number(node.attrs.get("y1", "0")))
        b = (number(node.attrs.get("x2", "0")), number(node.attrs.get("y2", "0")))
        add("line", a, [b])
        return Route(node, name, segments, pieces, a, b)
    if node.tag in {"polyline", "polygon"}:
        values = [number(raw) for raw in re.split(r"[\s,]+", node.attrs.get("points", "").strip()) if raw]
        if len(values) < 4 or len(values) % 2:
            raise ValueError("points must list at least two x,y pairs")
        points = list(zip(values[::2], values[1::2]))
        if node.tag == "polygon":
            points.append(points[0])
        add("line", points[0], points[1:])
        return Route(node, name, segments, pieces, points[0], points[-1])
    if node.tag != "path":
        raise ValueError(f"<{node.tag}> cannot carry an arc")
    raw = node.attrs.get("d", "")
    tokens = PATH_TOKEN_RE.findall(raw)
    if "".join(tokens) != re.sub(r"[\s,]+", "", raw):
        raise ValueError("unsupported characters")
    current: Point | None = None
    start: Point | None = None
    first: Point | None = None
    control: Point | None = None  # last control point, for S and T reflection
    previous_command = ""
    command = ""
    index = 0
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command.upper() not in PATH_ARITY:
                raise ValueError(f"unsupported command {command}")
            if command.upper() == "Z":
                if current is None or start is None:
                    raise ValueError("Z before M")
                add("line", current, [start])
                current, control, previous_command = start, None, "Z"
                continue
        if not command or command.upper() == "Z":
            raise ValueError("coordinates without a command")
        upper = command.upper()
        arity = PATH_ARITY[upper]
        args = tokens[index:index + arity]
        if len(args) != arity or any(token.isalpha() for token in args):
            raise ValueError(f"command {command} needs {arity} numbers")
        values = [number(token) for token in args]
        index += arity
        if current is None and upper != "M":
            raise ValueError("path must start with M")
        ox, oy = current if (command.islower() and current is not None) else (0.0, 0.0)

        def at(i: int) -> Point:
            return values[i] + ox, values[i + 1] + oy

        if upper == "M":
            current = start = at(0)
            first = first or current
            command = "l" if command.islower() else "L"
            control, previous_command = None, "M"
            continue
        if upper == "L":
            target = at(0)
            add("line", current, [target])
            control = None
        elif upper == "H":
            target = (values[0] + ox, current[1])
            add("line", current, [target])
            control = None
        elif upper == "V":
            target = (current[0], values[0] + oy)
            add("line", current, [target])
            control = None
        elif upper in {"Q", "T"}:
            if upper == "Q":
                handle, target = at(0), at(2)
            else:
                handle = ((2 * current[0] - control[0], 2 * current[1] - control[1])
                          if control is not None and previous_command in {"Q", "T"} else current)
                target = at(0)
            add("curve", current, _quadratic(current, handle, target))
            control = handle
        elif upper in {"C", "S"}:
            if upper == "C":
                handle1, handle2, target = at(0), at(2), at(4)
            else:
                handle1 = ((2 * current[0] - control[0], 2 * current[1] - control[1])
                           if control is not None and previous_command in {"C", "S"} else current)
                handle2, target = at(0), at(2)
            add("curve", current, _cubic(current, handle1, handle2, target))
            control = handle2
        else:
            target = at(5)
            add("hop", current, _elliptical_arc(current, values[0], values[1], values[2],
                                                values[3], values[4], target))
            control = None
        current, previous_command = target, upper
    if first is None or current is None:
        raise ValueError("empty path")
    return Route(node, name, segments, pieces, first, current)


def _cross(ax: float, ay: float, bx: float, by: float) -> float:
    return ax * by - ay * bx


def _same(a: Point, b: Point) -> bool:
    return abs(a[0] - b[0]) <= TOUCH and abs(a[1] - b[1]) <= TOUCH


def segment_contact(s: tuple[Point, Point], t: tuple[Point, Point]) -> list[Point]:
    """Points where two segments meet, endpoints and joints included.

    A collinear overlap returns both ends of the shared run, so a caller can
    tell an overlap (two distinct points) from a single contact.
    """
    (p, p2), (q, q2) = s, t
    r = (p2[0] - p[0], p2[1] - p[1])
    d = (q2[0] - q[0], q2[1] - q[1])
    r_len, d_len = math.hypot(*r), math.hypot(*d)
    if r_len <= TOUCH or d_len <= TOUCH:
        return []
    qp = (q[0] - p[0], q[1] - p[1])
    denominator = _cross(r[0], r[1], d[0], d[1])
    slack_r, slack_d = TOUCH / r_len, TOUCH / d_len
    if abs(denominator) > 1e-12 * r_len * d_len:
        t_value = _cross(qp[0], qp[1], d[0], d[1]) / denominator
        u_value = _cross(qp[0], qp[1], r[0], r[1]) / denominator
        if -slack_r <= t_value <= 1 + slack_r and -slack_d <= u_value <= 1 + slack_d:
            t_value = min(1.0, max(0.0, t_value))
            return [(p[0] + t_value * r[0], p[1] + t_value * r[1])]
        return []
    if abs(_cross(qp[0], qp[1], r[0], r[1])) / r_len > TOUCH:
        return []  # parallel, apart
    rr = r[0] * r[0] + r[1] * r[1]
    t0 = (qp[0] * r[0] + qp[1] * r[1]) / rr
    t1 = t0 + (d[0] * r[0] + d[1] * r[1]) / rr
    low, high = max(0.0, min(t0, t1)), min(1.0, max(t0, t1))
    if high < low - slack_r:
        return []
    low, high = min(low, high), max(low, high)
    points = [(p[0] + low * r[0], p[1] + low * r[1])]
    if (high - low) * r_len > TOUCH:
        points.append((p[0] + high * r[0], p[1] + high * r[1]))
    return points


def on_bounds_edge(point: Point, box: Box) -> bool:
    x, y = point
    inside_x = box.x - TOUCH <= x <= box.right + TOUCH
    inside_y = box.y - TOUCH <= y <= box.bottom + TOUCH
    return ((inside_x and (abs(y - box.y) <= TOUCH or abs(y - box.bottom) <= TOUCH))
            or (inside_y and (abs(x - box.x) <= TOUCH or abs(x - box.right) <= TOUCH)))


def route_contacts(a: Route, b: Route) -> list[tuple[Point, int, int, bool]]:
    """Every contact between two routes: (point, piece in a, piece in b, overlap)."""
    found = []
    for s0, s1, piece_a in a.segments:
        for t0, t1, piece_b in b.segments:
            points = segment_contact((s0, s1), (t0, t1))
            for point in points:
                found.append((point, piece_a, piece_b, len(points) > 1))
    return found


def valid_hops(routes: list[Route]) -> set[tuple[int, int, int]]:
    """(route, piece, other route) for each documented hop.

    A hop is an elliptical arc command on route R1 whose chord (the gap it
    leaves) is crossed by exactly one other route R2, and whose drawn arc no
    route other than R2 touches. Contacts between that arc and R2 are the
    bridge itself.
    """
    allowed = set()
    for index, route in enumerate(routes):
        for piece, (kind, start, end) in enumerate(route.pieces):
            if kind != "hop":
                continue
            under, touching = set(), set()
            arc = [(s0, s1) for s0, s1, owner in route.segments if owner == piece]
            for other_index, other in enumerate(routes):
                if other_index == index:
                    continue
                for t0, t1, _owner in other.segments:
                    if segment_contact((start, end), (t0, t1)):
                        under.add(other_index)
                    if any(segment_contact(s, (t0, t1)) for s in arc):
                        touching.add(other_index)
            if len(under) == 1 and touching <= under:
                allowed.add((index, piece, next(iter(under))))
    return allowed


def looks_like_sbgn(source: str) -> bool:
    scanner = Scanner()
    scanner.finish(source)
    return any(node.tag == "svg" and node.attrs.get("data-diagram") == DIAGRAM
               for node in scanner.nodes)


def check_source(path: Path, source: str) -> list[str]:
    scanner = Scanner()
    scanner.finish(source)
    findings: list[str] = []
    roots = [node for node in scanner.nodes
             if node.tag == "svg" and node.attrs.get("data-diagram") == DIAGRAM]
    if not roots:
        return []

    def fail(node: Node, message: str) -> None:
        findings.append(f"{path.name}:{node.line}: {message}")

    if len(roots) != 1:
        fail(roots[0], 'require exactly one svg data-diagram="sbgn"')
        return findings
    root = roots[0]
    findings.extend(f"{path.name}: {error}" for error in scanner.errors)
    for node in scanner.nodes:
        if node is root or root in node.ancestors():
            if node.duplicates:
                fail(node, f"duplicate attributes: {', '.join(sorted(node.duplicates))}")

    glyphs: dict[str, Box] = {}
    ids: dict[str, Node] = {}

    def register(identity: str, carrier: Node) -> bool:
        if not identity_ok(identity):
            fail(carrier, "identity must be a single XML Name starting with a letter")
            return False
        if identity in ids:
            fail(carrier, f'duplicate ID "{identity}"')
            return False
        ids[identity] = carrier
        return True

    def identity_for(kind: str, attrs: dict[str, str]) -> str:
        if kind == "macromolecule" or kind == "source-sink":
            return attrs.get("data-entity-id", "")
        if kind == "process":
            return attrs.get("data-process-id", "")
        return attrs.get("data-compartment-id", "")

    position_checked: set[int] = set()
    positioned: list[Node] = []

    def check_position(node: Node, where: str, owner: str | None = None,
                       remedy: str = "place glyphs with x, y, width and height only") -> None:
        """Containment reads x/y/width/height; nothing may move what is drawn.

        owner names what an ancestor holds, so a nested <svg> can be reported.
        """
        if id(node) in position_checked:
            return
        position_checked.add(id(node))
        positioned.append(node)
        if "transform" in node.attrs:
            fail(node, f"{where} has a transform attribute; {remedy}")
        moved = positional_properties(node.attrs.get("style", ""))
        if moved:
            fail(node, f"{where} has a positional inline style ({', '.join(moved)}); {remedy}")
        if owner and node.tag in {"svg", "symbol"}:
            fail(node, f"{owner} sits inside a nested <{node.tag}>, which offsets and scales it")

    def check_ancestors(node: Node, owner: str, **kwargs: str) -> None:
        for ancestor in node.ancestors():
            if ancestor is root:
                break
            check_position(ancestor, f"ancestor <{ancestor.tag}> of {owner}", owner, **kwargs)

    for node in scanner.nodes:
        if node is not root and root not in node.ancestors():
            continue
        kind = node.attrs.get("data-kind", "")
        if kind in GLYPH_KINDS:
            identity = identity_for(kind, node.attrs)
            if not register(identity, node):
                continue
            owner = f'glyph "{identity}"'
            check_position(node, f"glyph <{node.tag}> of {owner}")
            for child in node.children:
                if child.attrs.get("data-role") == "bounds":
                    check_position(child, f"bounds <{child.tag}> of {owner}")
            check_ancestors(node, owner)
            try:
                x, y, w, h = parse_bounds(node)
            except ValueError as error:
                fail(node, str(error))
                continue
            if kind != "source-sink":
                for value in (x, y, w, h):
                    if not on_grid(value):
                        fail(node, "glyph bounds must sit on the 4px grid")
                        break
            compartment = node.attrs.get("data-compartment") or None
            glyphs[identity] = Box(node, identity, kind, x, y, w, h, compartment)

    # The crossing check below compares raw path data, so a transform or
    # positional CSS on an arc or its ancestors would move the drawn stroke
    # without moving what is measured.
    arc_remedy = "draw arcs in map coordinates with path data only"
    for node in scanner.nodes:
        if root not in node.ancestors() or node.attrs.get("data-kind") not in ARC_KINDS:
            continue
        owner = f'arc {node.attrs.get("data-from", "?")} to {node.attrs.get("data-to", "?")}'
        check_position(node, f"<{node.tag}> of {owner}", owner, remedy=arc_remedy)
        check_ancestors(node, owner, remedy=arc_remedy)

    blockers = [g for g in glyphs.values() if g.kind != "compartment"]
    for node in scanner.nodes:
        if root not in node.ancestors():
            continue
        chain = [node, *node.ancestors()]
        chain = chain[:chain.index(root)]
        if any(item.tag in NON_RENDERED for item in chain):
            continue
        if any(item.attrs.get("data-kind", "") in GLYPH_KINDS for item in chain):
            continue
        legend = next((item for item in chain
                       if item.tag == "g" and item.attrs.get("data-role") == "legend"), None)
        if legend is not None:
            check_position(node, f"legend <{node.tag}>")
            if node is legend:
                check_ancestors(node, "the legend")
            if node.tag not in LEGEND_TAGS:
                fail(node, f"legend samples use <line>, <rect>, <circle> and <text> only; found <{node.tag}>")
                continue
            try:
                extent = sample_extent(node)
            except ValueError as error:
                fail(node, f"legend sample <{node.tag}>: {error}")
                continue
            if extent is None:
                continue
            for glyph in blockers:
                if overlaps(extent, glyph):
                    fail(node, f'legend sample <{node.tag}> touches glyph "{glyph.identity}"; '
                               "keep legend samples clear of the map")
            continue
        if node.tag in CONNECTOR_TAGS and not ({"data-kind", "data-from", "data-to"} & node.attrs.keys()):
            fail(node, f"drawn connector <{node.tag}> declares no arc; give it data-kind, data-from and "
                       'data-to, or put a legend sample inside <g data-role="legend">')

    macros = [g for g in glyphs.values() if g.kind == "macromolecule"]
    processes = [g for g in glyphs.values() if g.kind == "process"]
    compartments = [g for g in glyphs.values() if g.kind == "compartment"]
    sources = [g for g in glyphs.values() if g.kind == "source-sink"]
    if not macros:
        fail(root, "SBGN requires at least one macromolecule")
    if not processes:
        fail(root, "SBGN requires at least one process")
    if not compartments:
        fail(root, "SBGN requires at least one compartment")
    if len(macros) > MAX_MACRO:
        fail(root, "macromolecule budget is 7")
    if len(processes) > MAX_PROCESS:
        fail(root, "process budget is 6")
    if len(compartments) > MAX_COMPARTMENT:
        fail(root, "compartment budget is 1")
    if len(sources) > MAX_SOURCE:
        fail(root, "source-sink budget is 2")
    arc_count = sum(1 for node in scanner.nodes
                    if root in node.ancestors() and node.attrs.get("data-kind") in ARC_KINDS)
    if arc_count > MAX_ARC:
        fail(root, f"arc budget is {MAX_ARC}; found {arc_count}")

    parent_of = ancestry(scanner)
    for line, sheet in scanner.stylesheets:
        sheet = CSS_COMMENT_RE.sub(lambda match: "\n" * match.group(0).count("\n"), sheet)
        for match in CSS_BLOCK_RE.finditer(sheet):
            moved = positional_properties(match.group(2))
            if not moved:
                continue
            selectors = [selector.strip() for selector in _split_top_level(match.group(1), ",")]
            reaching = [selector for selector in selectors if selector and any(
                selector_matches(selector, node, parent_of) is not False for node in positioned)]
            if reaching:
                at = line + sheet[:match.start(2)].count("\n")
                findings.append(
                    f"{path.name}:{at}: stylesheet rule {', '.join(reaching)!r} sets {', '.join(moved)} "
                    "on elements the diagram's glyphs or arcs can match; place glyphs with x, y, width and height only")

    compartment_ids = {g.identity for g in compartments}
    for box in glyphs.values():
        if box.kind in {"macromolecule", "process", "source-sink"}:
            if not box.compartment or box.compartment not in compartment_ids:
                fail(box.node, "data-compartment must name a compartment in this file")
                continue
            parent = glyphs[box.compartment]
            if not within_box(box, parent):
                fail(box.node, f'glyph "{box.identity}" is not geometrically inside compartment "{box.compartment}"')

    species = {g.identity for g in glyphs.values() if g.kind in SPECIES}
    process_ids = {g.identity for g in processes}

    for node in scanner.nodes:
        if node is not root and root not in node.ancestors():
            continue
        kind = node.attrs.get("data-kind", "")
        is_arc = "data-from" in node.attrs or "data-to" in node.attrs
        if kind not in ARC_KINDS:
            # An unknown kind must fail here: skipping it would also skip the
            # endpoint checks, so a typo would pass a species-to-species arc.
            if is_arc and not kind:
                fail(node, f"arc data-kind is missing; use one of {ARC_LIST}")
            elif is_arc:
                fail(node, f'arc data-kind "{kind}" must be one of {ARC_LIST}')
            elif "data-kind" in node.attrs and kind not in GLYPH_KINDS:
                fail(node, f'unknown data-kind "{kind}"; glyphs use {GLYPH_LIST}, arcs use {ARC_LIST}')
            continue
        source = node.attrs.get("data-from", "")
        target = node.attrs.get("data-to", "")
        if not identity_ok(source) or not identity_ok(target):
            fail(node, "arc data-from and data-to must be single XML Names")
            continue
        if kind == "consumption":
            if source not in species or target not in process_ids:
                fail(node, "consumption must run species → process")
        elif kind == "production":
            if source not in process_ids or target not in species:
                fail(node, "production must run process → species")
        elif kind == "modulation":
            if source not in species or target not in process_ids:
                fail(node, "modulation must run species → process")
        elif kind == "reversible":
            pair = {source, target}
            if not (pair & species and pair & process_ids):
                fail(node, "reversible must join a species and a process")

    # Arcs must not cross, stack, touch, or end on one another: any contact
    # without a gap reads as a junction. Two exemptions only: two arcs ending
    # at the same port on a glyph's bounds, and the documented hop over
    # exactly one other route (type-architecture.md).
    routes: list[Route] = []
    for node in scanner.nodes:
        if root not in node.ancestors() or node.attrs.get("data-kind") not in ARC_KINDS:
            continue
        name = f'{node.attrs.get("data-from", "?")} to {node.attrs.get("data-to", "?")}'
        try:
            routes.append(flatten_route(node, name))
        except ValueError as error:
            fail(node, f"arc {name}: path data could not be read ({error})")
    hops = valid_hops(routes)
    ports = [g for g in glyphs.values() if g.kind != "compartment"]
    for index, route in enumerate(routes):
        for other_index in range(index + 1, len(routes)):
            other = routes[other_index]
            reported: set[tuple[str, float, float]] = set()
            overlapped = False
            for point, piece, other_piece, overlap in route_contacts(route, other):
                if overlap:
                    if not overlapped:
                        overlapped = True
                        fail(other.node, f"arcs {route.name} and {other.name} overlap; "
                                         "offset one by 12px or more")
                    continue
                if (index, piece, other_index) in hops or (other_index, other_piece, index) in hops:
                    continue
                ends_here = [r for r in (route, other) if _same(point, r.head) or _same(point, r.tail)]
                if len(ends_here) == 2 and any(on_bounds_edge(point, glyph) for glyph in ports):
                    continue
                x, y = round(point[0], 2), round(point[1], 2)
                if len(ends_here) == 1:
                    ender = ends_here[0]
                    rest = other if ender is route else route
                    key = ("end", x, y)
                    message = (f"arc {ender.name} ends on arc {rest.name} at ({x:g}, {y:g}); "
                               "it reads as a junction")
                elif len(ends_here) == 2:
                    key = ("end", x, y)
                    message = (f"arcs {route.name} and {other.name} end at ({x:g}, {y:g}) "
                               "away from a glyph port; it reads as a junction")
                else:
                    key = ("cross", x, y)
                    message = (f"arcs {route.name} and {other.name} cross at ({x:g}, {y:g}) without a gap; "
                               "reroute one or bridge it with the hop from type-architecture.md")
                if key not in reported:
                    reported.add(key)
                    fail(other.node, message)

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped SBGN example")
    args = parser.parse_args()
    if args.all and args.paths:
        parser.error("use --all or explicit paths, not both")
    targets = sorted(ASSET_DIR.glob("example-*.html")) if args.all or not args.paths else [Path(value) for value in args.paths]
    checked, findings = 0, []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"error: cannot read {path}: {error}", file=sys.stderr)
            return 2
        if not looks_like_sbgn(source):
            continue
        checked += 1
        findings.extend(check_source(path, source))
    if not checked:
        print("error: no SBGN diagrams found", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} SBGN finding(s) across {checked} file(s).")
        return 1
    print(f"OK SBGN: {checked} file(s); IDs, bipartite arcs, compartments and budget agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
