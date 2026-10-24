#!/usr/bin/env python3
"""Verify the invariants a service blueprint can silently break.

A service blueprint's whole claim is a **shared stage grid split by a line of
visibility**: customer and frontstage sit above it, backstage (and support)
sit below it. Every way of breaking that claim still renders — nothing errors,
and neither `lint-skin.py` nor `verify-geometry.py` reads a cell against the
layer it belongs to or a stage header against the column it occupies.

Each layer group declares `data-layer`, each cell declares `data-stage` plus
`data-name`, and the visibility line declares `data-role="visibility"`. The
checker holds the drawing to those declarations:

1. LAYER ORDER — optional evidence, then customer, frontstage, backstage, then
   optional support, top to bottom. A missing required layer, a duplicate, or
   a row in the wrong vertical order fails closed.
2. VISIBILITY — exactly one `data-role="visibility"` line, spanning the plot,
   sitting between the frontstage row bottom and the backstage row top (±2px),
   with every evidence / customer / frontstage cell above it and every
   backstage / support cell below it, and a stroke that clears 3:1 against
   paper once rgba alpha, `stroke-opacity`, and `opacity` are combined.
3. STAGE GRID — every cell sits inside its stage header's column (left and
   right edge); column widths equal; gutters equal.
4. CENSUS — every stage has a customer, frontstage, and backstage cell. Empty
   is allowed only with an explicit `—` / `Not applicable` `data-name`.
5. FOCAL — at most one `data-focal="true"` cell, and no other row mark
   painted with the accent.
6. BUDGET — at most 6 stages; no extra `data-layer` values.
7. PRINT — each cell's visible text contains its `data-name`.
8. NO CSS MOTION OF MARKS — `transform` / geometry properties in attributes,
   inline style, or `<style>`, on cells, stage headers, rule lines, and text,
   or on any group that contains them.

Usage:
    python3 scripts/verify-service-blueprint.py --all
    python3 scripts/verify-service-blueprint.py skills/diagram-design/assets/example-service-blueprint.html

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

RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(
    r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL
)
# Both quote styles are valid SVG; a skipped attribute would hide a mark
# from every check.
ATTR_RE = re.compile(r"""(?P<name>[\w:-]+)\s*=\s*(?:"(?P<dq>[^"]*)"|'(?P<sq>[^']*)')""")
TAG_RE = re.compile(r"<[^>]+>")
# CSS width/height redraw a rect at a size its attributes do not state.
CSS_SIZE_RE = re.compile(r"(?:^|[{;}\n])\s*(?P<prop>width|height)\s*:", re.IGNORECASE)
COMMENT_CSS_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_RULE_RE = re.compile(r"(?P<selector>[^{}]+)\{(?P<body>[^{}]*)\}")
SVG_MARK_ELEMENTS = frozenset(
    {"rect", "line", "text", "tspan", "g", "path", "polygon", "polyline", "circle", "ellipse", "use"}
)
SVG_MARK_TAG_RE = re.compile(
    r"<(?:rect|line|text|tspan|g|path|polygon|polyline|circle|ellipse|use)\b[^>]*>", re.IGNORECASE
)
SVG_TOKEN_RE = re.compile(r"""\b(?:class|id)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)\s*:",
    re.IGNORECASE,
)
RGBA_RE = re.compile(
    r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*([\d.]+)\s*\)", re.IGNORECASE
)
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
PAPER_RE = re.compile(r"--color-paper\s*:\s*(#[0-9a-fA-F]{6})")
ACCENT_RE = re.compile(r"--color-accent\s*:\s*(#[0-9a-fA-F]{6})")
TEXT_OPEN_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>", re.IGNORECASE)
STYLE_PAINT_RE = re.compile(
    r"(?:^|;)\s*(?P<prop>opacity|stroke-opacity|stroke|stroke-width|display|visibility)\s*:",
    re.IGNORECASE,
)

CANONICAL_LAYERS = ("evidence", "customer", "frontstage", "backstage", "support")
REQUIRED_LAYERS = ("customer", "frontstage", "backstage")
VISIBLE_LAYERS = frozenset({"evidence", "customer", "frontstage"})
HIDDEN_LAYERS = frozenset({"backstage", "support"})
EMPTY_NAMES = frozenset({"—", "-", "not applicable", "n/a"})
MAX_STAGES = 6
GEOMETRY_TOLERANCE = 2.0
WCAG_NON_TEXT = 3.0


# Quoted CSS data is not a declaration: `--note: "a;transform:b"` moves nothing (#431).
# A quote opens a string only where the browser tokenizes one, so a comment, an
# unquoted url() (escapes included, so `url(a\)"b)` is one token) and an escaped
# character are consumed first and kept as written. A string that never closes on
# its line is kept as well - a line feed, carriage return or form feed ends it - so
# the checker still fails closed on it. Every other character of a string becomes a space and its newlines
# stay, so each offset and line number still points into the CSS as written.
# CSS the browser may read differently comes back unblanked: a character reference
# (decoded before CSS sees it inside <svg> and in every attribute value) or an escape
# left outside a string (`u\72 l(` is `url(`).
CSS_STRING_RE = re.compile(
    r"""/\*.*?(?:\*/|\Z)|url\((?![ \t\n\r\f]*["'])(?:\\[\s\S]|[^)\\])*\)|\\[\s\S]"""
    r"""|(?P<string>"(?:\\[\s\S]|[^"\\\n\r\f])*"|'(?:\\[\s\S]|[^'\\\n\r\f])*')""",
    re.DOTALL | re.IGNORECASE,
)


def blank_css_strings(css: str) -> str:
    """CSS with the contents of every quoted string blanked, same length and lines."""
    blanked = CSS_STRING_RE.sub(
        lambda found: re.sub(r"[^\n]", " ", found.group()) if found.group("string") else found.group(),
        css,
    )
    return css if "\\" in blanked or html.unescape(css) != css else blanked


def attrs_of(tag_attrs: str) -> dict[str, str]:
    return {
        m.group("name").lower(): m.group("dq") if m.group("dq") is not None else m.group("sq")
        for m in ATTR_RE.finditer(tag_attrs)
    }


def parse_number(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def transform_carrier(attrs: dict[str, str]) -> str | None:
    if "transform" in attrs:
        return f"transform={attrs['transform']!r}"
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(blank_css_strings(style))
        if found is not None:
            return f"style={style!r} (the {found.group('prop').lower()} property)"
    return None


def transformed_spans(source: str) -> list[tuple[int, int, str]]:
    events: list[tuple[int, int, str | None]] = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        events.append((match.start(), 0, transform_carrier(attrs)))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))

    spans: list[tuple[int, int, str]] = []
    stack: list[tuple[int, str | None]] = []
    for position, kind, how in events:
        if kind == 0:
            stack.append((position, how))
        elif stack:
            start, transformed_by = stack.pop()
            if transformed_by is not None:
                spans.append((start, position, transformed_by))
    for start, transformed_by in stack:
        if transformed_by is not None:
            spans.append((start, len(source), transformed_by))
    return spans


def layer_at(source: str, offset: int) -> str | None:
    stack: list[str | None] = []
    events: list[tuple[int, int, str | None]] = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        events.append((match.start(), 0, attrs.get("data-layer")))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))
    current: str | None = None
    covering: str | None = None
    for position, kind, layer in events:
        if position > offset:
            break
        if kind == 0:
            stack.append(current)
            if layer:
                current = layer
        elif stack:
            current = stack.pop()
        covering = current
    return covering


# Contrast helpers match verify-dumbbell.py (sRGB, WCAG 1.4.11).
def _channel(component: int) -> float:
    fraction = component / 255.0
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    value = color.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    red, green, blue = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(foreground: str, background: str) -> float:
    first, second = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def composite(foreground: str, alpha: float, background: str) -> str:
    fore = [int(foreground.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    back = [int(background.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4)]
    blended = [round(fore[i] * alpha + back[i] * (1 - alpha)) for i in range(3)]
    return "#%02x%02x%02x" % tuple(blended)


def parse_hex(color: str) -> str | None:
    value = color.strip()
    if not HEX_RE.match(value):
        return None
    if len(value) == 4:
        return "#" + "".join(ch * 2 for ch in value[1:])
    return value.lower()


def paint_base(paint: str | None) -> tuple[str, float] | None:
    """(#rrggbb, alpha) for a hex or rgba paint, else None."""
    if paint is None:
        return None
    rgba = RGBA_RE.fullmatch(paint.strip())
    if rgba:
        hex_color = "#%02x%02x%02x" % (
            int(rgba.group(1)),
            int(rgba.group(2)),
            int(rgba.group(3)),
        )
        return hex_color, float(rgba.group(4))
    parsed = parse_hex(paint)
    if parsed is None:
        return None
    return parsed, 1.0


def visible_stroke(attrs: dict[str, str], paper: str) -> tuple[str | None, str | None]:
    """(painted color, None) or (None, why the paint cannot be measured).

    The rgba alpha, `stroke-opacity`, and `opacity` all multiply into what the
    browser paints, so each one is combined before contrast is measured.
    Paint set through inline style is not read, so it is rejected.
    """
    style = attrs.get("style")
    if style is not None:
        found = STYLE_PAINT_RE.search(style)
        if found is not None:
            return None, (
                f"inline style sets {found.group('prop').lower()!r}; put the paint in "
                "presentation attributes so contrast can be measured"
            )
    if attrs.get("display", "").strip().lower() == "none" or attrs.get(
        "visibility", ""
    ).strip().lower() in {"hidden", "collapse"}:
        return None, "the line is hidden by display/visibility"
    width = attrs.get("stroke-width")
    if width is not None:
        parsed_width = parse_number(width)
        if parsed_width is None or parsed_width <= 0:
            return None, f"stroke-width={width!r} does not draw a visible line"
    base = paint_base(attrs.get("stroke"))
    if base is None:
        return None, "stroke is not a parseable hex or rgba color"
    color, alpha = base
    for name in ("stroke-opacity", "opacity"):
        raw = attrs.get(name)
        if raw is None:
            continue
        value = parse_number(raw)
        if value is None or not 0 <= value <= 1:
            return None, f"{name}={raw!r} is not a number between 0 and 1"
        alpha *= value
    return composite(color, alpha, paper), None


class Cell:
    __slots__ = ("layer", "stage", "name", "x", "y", "w", "h", "focal", "index")

    def __init__(
        self,
        index: int,
        layer: str,
        stage: str,
        name: str,
        x: float,
        y: float,
        w: float,
        h: float,
        focal: bool,
    ) -> None:
        self.index = index
        self.layer = layer
        self.stage = stage
        self.name = name
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.focal = focal

    @property
    def bottom(self) -> float:
        return self.y + self.h


class Header:
    __slots__ = ("stage", "x", "w")

    def __init__(self, stage: str, x: float, w: float) -> None:
        self.stage = stage
        self.x = x
        self.w = w


class RowMark:
    """Any rect inside a data-layer row: a cell or its underlay."""

    __slots__ = ("x", "y", "paints", "name", "focal")

    def __init__(
        self, x: float | None, y: float | None, paints: list[str], name: str | None, focal: bool
    ) -> None:
        self.x = x
        self.y = y
        self.paints = paints
        self.name = name
        self.focal = focal


def rect_paints(attrs: dict[str, str]) -> list[str]:
    paints = [attrs[key] for key in ("fill", "stroke") if key in attrs]
    style = attrs.get("style")
    if style:
        for declaration in style.split(";"):
            prop, _, value = declaration.partition(":")
            if prop.strip().lower() in {"fill", "stroke"}:
                paints.append(value.strip())
    return paints


def parse_marks(
    source: str, errors: list[str], row_marks: list[RowMark] | None = None
) -> tuple[list[Header], list[Cell], list[dict[str, str]]]:
    source = COMMENT_RE.sub("", source)
    headers: list[Header] = []
    cells: list[Cell] = []
    visibility: list[dict[str, str]] = []

    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if row_marks is not None and layer_at(source, match.start()) is not None:
            row_marks.append(
                RowMark(
                    parse_number(attrs.get("x")),
                    parse_number(attrs.get("y")),
                    rect_paints(attrs),
                    attrs.get("data-name"),
                    attrs.get("data-focal", "").lower() == "true",
                )
            )
        stage = attrs.get("data-stage")
        name = attrs.get("data-name")
        x = parse_number(attrs.get("x"))
        y = parse_number(attrs.get("y"))
        w = parse_number(attrs.get("width"))
        h = parse_number(attrs.get("height"))
        if stage is None:
            continue
        if x is None or w is None or w <= 0:
            errors.append(
                f"stage {stage!r} mark is missing a finite x/width; the stage grid "
                "cannot be checked"
            )
            continue
        if name is None:
            headers.append(Header(stage, x, w))
            continue
        if y is None or h is None or h <= 0:
            errors.append(
                f"cell {name!r} is missing a finite y/height; layer order cannot be checked"
            )
            continue
        layer = layer_at(source, match.start())
        if layer is None:
            errors.append(
                f"cell {name!r} is not inside a data-layer group; wrap each row "
                "so layer order is declared"
            )
            continue
        focal = attrs.get("data-focal", "").lower() == "true"
        cells.append(Cell(len(cells), layer, stage, name, x, y, w, h, focal))

    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == "visibility":
            visibility.append(attrs)

    return headers, cells, visibility


def check_transforms(source: str, errors: list[str]) -> None:
    source = COMMENT_RE.sub("", source)
    spans = transformed_spans(source)

    def enclosing(offset: int) -> str | None:
        for start, end, how in spans:
            if start <= offset <= end:
                return f"ancestor {how}"
        return None

    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-stage" not in attrs and "data-name" not in attrs:
            continue
        kind = "cell" if "data-name" in attrs else "stage header"
        how = transform_carrier(attrs) or enclosing(match.start())
        if how is not None:
            errors.append(
                f"service-blueprint {kind} carries {how}; bake the movement into its "
                "coordinates so the verifier checks what the browser draws"
            )
        sized = CSS_SIZE_RE.search(attrs.get("style", ""))
        if sized is not None:
            errors.append(
                f"service-blueprint {kind} {attrs.get('data-name') or attrs.get('data-stage')!r} "
                f"sets its size in CSS (the {sized.group('prop').lower()} property); state "
                "width and height as attributes so the verifier checks what the browser draws"
            )

    # The printed and header checks read text by its x/y, so a transform on a
    # label (or on a group holding it) draws it somewhere the checks never look.
    for match in TEXT_OPEN_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        how = transform_carrier(attrs) or enclosing(match.start())
        if how is not None:
            errors.append(
                f"service-blueprint text carries {how}; bake the movement into its "
                "x/y so the verifier checks what the browser draws"
            )

    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") not in {
            "visibility",
            "interaction",
            "internal-interaction",
        }:
            continue
        how = transform_carrier(attrs) or enclosing(match.start())
        if how is not None:
            errors.append(
                f"service-blueprint {attrs.get('data-role')} line carries {how}; bake "
                "the movement into its coordinates so the verifier checks what the "
                "browser draws"
            )

    # Class and id names carried by SVG marks themselves; HTML chrome around
    # the figure (cards, captions) does not count.
    svg_tokens = {
        token
        for tag in SVG_MARK_TAG_RE.finditer(source)
        for match in SVG_TOKEN_RE.finditer(tag.group(0))
        for token in (match.group(1) or match.group(2) or "").split()
    }
    for match in STYLE_RE.finditer(source):
        found = CSS_MOVES_MARK_RE.search(blank_css_strings(match.group("body")))
        if found is not None:
            errors.append(
                f"CSS {found.group('prop').lower()!r} declaration can move verified "
                "service-blueprint geometry; bake the movement into the coordinates instead"
            )
        for rule in CSS_RULE_RE.finditer(COMMENT_CSS_RE.sub(" ", match.group("body"))):
            sized = CSS_SIZE_RE.search(rule.group("body"))
            if sized is None:
                continue
            for part in split_selector_list(rule.group("selector")):
                if selector_can_reach_marks(part, svg_tokens):
                    errors.append(
                        f"CSS {sized.group('prop').lower()!r} declaration can resize "
                        f"service-blueprint marks ({part.strip()}); state sizes as attributes instead"
                    )
                    break


def _selector_boundaries(selector: str, stops: str) -> list[int]:
    """Offsets of stop characters outside quoted strings, brackets and parens."""
    found: list[int] = []
    depth = 0
    quote = ""
    index = 0
    while index < len(selector):
        char = selector[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char in "[(":
            depth += 1
        elif char in "])":
            depth = max(0, depth - 1)
        elif depth == 0 and (char in stops or (" " in stops and char.isspace())):
            found.append(index)
        index += 1
    return found


def split_selector_list(selectors: str) -> list[str]:
    """Split a selector list on top-level commas only."""
    parts: list[str] = []
    start = 0
    for comma in _selector_boundaries(selectors, ","):
        parts.append(selectors[start:comma])
        start = comma + 1
    parts.append(selectors[start:])
    return [part for part in parts if part.strip()]


def selector_subject(selector: str) -> str:
    """The last compound of a selector, after its final top-level combinator."""
    text = selector.strip()
    cuts = _selector_boundaries(text, " >+~")
    return text[cuts[-1] + 1:].strip() if cuts else text


def _pseudo_functions(compound: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a compound into its text outside :name(...) and those functions."""
    outside: list[str] = []
    functions: list[tuple[str, str]] = []
    index = 0
    while index < len(compound):
        match = re.match(r":{1,2}([\w-]+)\(", compound[index:])
        if match is None:
            outside.append(compound[index])
            index += 1
            continue
        depth = 1
        cursor = index + match.end()
        quote = ""
        while cursor < len(compound) and depth:
            char = compound[cursor]
            if quote:
                if char == "\\":
                    cursor += 1
                elif char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            cursor += 1
        functions.append((match.group(1).lower(), compound[index + match.end():cursor - 1]))
        index = cursor
    return "".join(outside), functions


def _without_attribute_values(compound: str) -> str:
    """Replace each [attribute...] block, quotes included, with an empty []."""
    out: list[str] = []
    depth = 0
    quote = ""
    escaped = False
    for char in compound:
        if depth:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif quote:
                if char == quote:
                    quote = ""
            elif char in "\"'":
                quote = char
            elif char == "]":
                depth = 0
                out.append("]")
            continue
        if char == "[":
            depth = 1
            out.append("[")
            continue
        out.append(char)
    return "".join(out)


# Pseudo-classes whose argument is a selector list the element itself must match.
MATCHES_ANY = frozenset({"is", "where", "matches", "-webkit-any", "-moz-any"})


def selector_can_reach_marks(selector: str, svg_tokens: set[str]) -> bool:
    """Whether a selector's subject can be one of the diagram's SVG marks.

    A named element decides it: an SVG shape or text element can be a mark;
    any other element (div, svg, section) is page layout. :is()/:where()
    lists are read: the subject can be a mark only if some alternative can.
    With no element named, a class or id that no SVG mark carries rules the
    subject out; anything else (attributes, other pseudo-classes, a mark's
    own class) is treated as able to reach a mark.
    """
    subject = selector_subject(selector)
    if not subject:
        return False
    outside, functions = _pseudo_functions(subject)
    # Attribute values are data, not selectors: "#ffffff" in [fill="#ffffff"]
    # is not an id.
    outside = _without_attribute_values(outside)
    element = re.match(r"[A-Za-z][\w-]*", outside)
    if element is not None:
        return element.group(0).lower() in SVG_MARK_ELEMENTS
    for name, argument in functions:
        if name in MATCHES_ANY and not any(
            selector_can_reach_marks(alternative, svg_tokens)
            for alternative in split_selector_list(argument)
        ):
            return False
    names = set(re.findall(r"[.#]([\w-]+)", outside))
    if names and not names <= svg_tokens:
        return False
    return True


def check_layers(cells: list[Cell], errors: list[str]) -> dict[str, list[Cell]]:
    by_layer: dict[str, list[Cell]] = {}
    for cell in cells:
        by_layer.setdefault(cell.layer, []).append(cell)

    unknown = sorted(layer for layer in by_layer if layer not in CANONICAL_LAYERS)
    if unknown:
        errors.append(
            f"budget: extra data-layer values {unknown}; allowed layers are "
            + ", ".join(CANONICAL_LAYERS)
        )

    for required in REQUIRED_LAYERS:
        if required not in by_layer:
            errors.append(
                f"layer order: missing required {required} row; a blueprint needs "
                "customer, frontstage, and backstage"
            )

    present = [layer for layer in CANONICAL_LAYERS if layer in by_layer]
    actual = sorted(
        (layer for layer in by_layer if layer in CANONICAL_LAYERS),
        key=lambda layer: min(cell.y for cell in by_layer[layer]),
    )
    if actual != present:
        errors.append(
            "layer order: rows must run evidence (optional), customer, frontstage, "
            f"backstage, support (optional) top to bottom; found {actual}"
        )
    else:
        # Every cell, not just each row's topmost one: a single cell that drops
        # into the next row's band breaks the order the reader sees.
        for upper, lower in zip(present, present[1:]):
            lower_top = min(cell.y for cell in by_layer[lower])
            for cell in by_layer[upper]:
                if cell.bottom > lower_top + GEOMETRY_TOLERANCE:
                    errors.append(
                        f"layer order: {upper} cell {cell.name!r} ends at "
                        f"y={cell.bottom:g}, below the {lower} row top at y={lower_top:g}"
                    )
    return by_layer


def check_visibility(
    source: str,
    cells: list[Cell],
    headers: list[Header],
    visibility: list[dict[str, str]],
    errors: list[str],
) -> None:
    if len(visibility) != 1:
        errors.append(
            f"visibility: exactly one data-role=\"visibility\" line is required; "
            f"found {len(visibility)}"
        )
        if not visibility:
            return

    attrs = visibility[0]
    x1 = parse_number(attrs.get("x1"))
    x2 = parse_number(attrs.get("x2"))
    y1 = parse_number(attrs.get("y1"))
    y2 = parse_number(attrs.get("y2"))
    if None in (x1, x2, y1, y2):
        errors.append("visibility: line is missing finite x1/x2/y1/y2 coordinates")
        return
    if abs(y1 - y2) > 1:
        errors.append("visibility: the line must be horizontal across the plot")
    y = (y1 + y2) / 2
    left, right = min(x1, x2), max(x1, x2)
    if headers:
        plot_left = min(header.x for header in headers)
        plot_right = max(header.x + header.w for header in headers)
        if left > plot_left + GEOMETRY_TOLERANCE or right < plot_right - GEOMETRY_TOLERANCE:
            errors.append(
                "visibility: line must span the plot, from the first stage header "
                "to the last"
            )

    front = [cell for cell in cells if cell.layer == "frontstage"]
    back = [cell for cell in cells if cell.layer == "backstage"]
    if front and back:
        front_bottom = max(cell.bottom for cell in front)
        back_top = min(cell.y for cell in back)
        if not (front_bottom - GEOMETRY_TOLERANCE <= y <= back_top + GEOMETRY_TOLERANCE):
            errors.append(
                "visibility: the line must sit between the frontstage row bottom and "
                f"the backstage row top (±{GEOMETRY_TOLERANCE:g}px); drawn at y={y:g}, "
                f"frontstage ends at {front_bottom:g}, backstage starts at {back_top:g}"
            )

    # Every cell on its own side of the line, not just the row extremes the
    # check above reads: one customer cell below the line reads as hidden work.
    for cell in cells:
        if cell.layer in VISIBLE_LAYERS and cell.bottom > y + GEOMETRY_TOLERANCE:
            errors.append(
                f"visibility: {cell.layer} cell {cell.name!r} reaches y={cell.bottom:g}, "
                f"below the line of visibility at y={y:g}"
            )
        elif cell.layer in HIDDEN_LAYERS and cell.y < y - GEOMETRY_TOLERANCE:
            errors.append(
                f"visibility: {cell.layer} cell {cell.name!r} starts at y={cell.y:g}, "
                f"above the line of visibility at y={y:g}"
            )

    paper_match = PAPER_RE.search(source)
    if paper_match is None:
        errors.append("visibility: contrast cannot be checked without --color-paper")
        return
    paper = paper_match.group(1).lower()
    painted, why = visible_stroke(attrs, paper)
    if painted is None:
        errors.append(f"visibility: {why}")
        return
    ratio = contrast(painted, paper)
    if ratio < WCAG_NON_TEXT:
        errors.append(
            f"visibility: stroke contrast is {ratio:.3f}:1 against paper, under the "
            f"{WCAG_NON_TEXT:.1f}:1 WCAG 1.4.11 asks"
        )


def check_grid(headers: list[Header], cells: list[Cell], errors: list[str]) -> None:
    if not headers:
        errors.append("stage grid: no stage headers declare data-stage")
        return
    seen: dict[str, Header] = {}
    for header in headers:
        if header.stage in seen:
            errors.append(f"stage grid: duplicate stage header {header.stage!r}")
            continue
        seen[header.stage] = header
    ordered = sorted(seen.values(), key=lambda header: header.x)
    if len(ordered) > MAX_STAGES:
        errors.append(
            f"budget: {len(ordered)} stages; at most {MAX_STAGES} stages on one blueprint"
        )
    widths = {round(header.w, 4) for header in ordered}
    if len(widths) > 1:
        errors.append(f"stage grid: column widths must be equal; found {sorted(widths)}")
    if len(ordered) >= 2:
        gutters = [
            round(ordered[i + 1].x - (ordered[i].x + ordered[i].w), 4)
            for i in range(len(ordered) - 1)
        ]
        if len(set(gutters)) > 1:
            errors.append(f"stage grid: gutters must be equal; found {gutters}")
        if any(gutter < 0 for gutter in gutters):
            errors.append(f"stage grid: columns overlap; gutters must be zero or more, found {gutters}")
    by_stage = {header.stage: header for header in ordered}
    for cell in cells:
        header = by_stage.get(cell.stage)
        if header is None:
            errors.append(
                f"stage grid: cell {cell.name!r} declares data-stage={cell.stage!r} "
                "with no matching header"
            )
            continue
        if abs(cell.x - header.x) > GEOMETRY_TOLERANCE:
            errors.append(
                f"stage grid: cell {cell.name!r} x={cell.x:g} does not match its "
                f"stage header column at x={header.x:g}"
            )
        if cell.x + cell.w > header.x + header.w + GEOMETRY_TOLERANCE:
            errors.append(
                f"stage grid: cell {cell.name!r} right edge x={cell.x + cell.w:g} runs "
                f"past its stage column, which ends at x={header.x + header.w:g}"
            )


def check_census(headers: list[Header], cells: list[Cell], errors: list[str]) -> None:
    stages = [header.stage for header in sorted(headers, key=lambda item: item.x)]
    # Unique while preserving order.
    unique_stages: list[str] = []
    for stage in stages:
        if stage not in unique_stages:
            unique_stages.append(stage)
    index = {(cell.layer, cell.stage): cell for cell in cells}
    duplicates = len(cells) - len(index)
    if duplicates:
        errors.append("census: duplicate cells share a layer and stage")
    for stage in unique_stages:
        for layer in REQUIRED_LAYERS:
            cell = index.get((layer, stage))
            if cell is None:
                errors.append(
                    f"census: stage {stage!r} is missing a {layer} cell (empty allowed "
                    "only with an explicit — / Not applicable data-name)"
                )
            elif not cell.name.strip():
                errors.append(
                    f"census: {layer} cell on stage {stage!r} has a blank data-name"
                )


def check_focal(
    source: str, cells: list[Cell], row_marks: list[RowMark], errors: list[str]
) -> None:
    focals = [cell for cell in cells if cell.focal]
    if len(focals) > 1:
        errors.append(
            f"focal: at most one cell may set data-focal; found {len(focals)}"
        )

    # The accent is what the reader sees, not the attribute: any row mark
    # painted with it must be the declared focal cell (or its underlay).
    accents: set[str] = set()
    accent_match = ACCENT_RE.search(source)
    if accent_match is not None:
        accents.add(accent_match.group(1).lower())
    for mark in row_marks:
        if mark.focal:
            for paint in mark.paints:
                base = paint_base(paint)
                if base is not None and base[0] != "#ffffff":
                    accents.add(base[0])
    if not accents:
        return
    focal_spots = {(cell.x, cell.y) for cell in focals}
    for mark in row_marks:
        if mark.focal:
            continue
        painted = [
            paint
            for paint in mark.paints
            if (base := paint_base(paint)) is not None and base[0] in accents
        ]
        if not painted:
            continue
        if mark.name is None and (mark.x, mark.y) in focal_spots:
            continue
        label = repr(mark.name) if mark.name is not None else f"at x={mark.x}, y={mark.y}"
        errors.append(
            f"focal: cell {label} is painted with the accent ({painted[0]}) but is "
            "not the data-focal cell; one accent cell per blueprint"
        )


def check_printed(source: str, cells: list[Cell], errors: list[str]) -> None:
    source = COMMENT_RE.sub("", source)
    texts: list[tuple[float, float, str]] = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        x = parse_number(attrs.get("x"))
        y = parse_number(attrs.get("y"))
        if x is None or y is None:
            continue
        body = TAG_RE.sub("", match.group("body"))
        body = (
            body.replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&nbsp;", " ")
        )
        texts.append((x, y, re.sub(r"\s+", " ", body).strip()))

    for cell in cells:
        collected = [
            body
            for x, y, body in texts
            if cell.x - 1 <= x <= cell.x + cell.w + 1
            and cell.y - 1 <= y <= cell.bottom + 6
        ]
        haystack = " ".join(collected)
        # Japanese (and similar) labels omit spaces between words. Two <text>
        # lines or whitespace-split <tspan>s inside one cell must still match
        # data-name when that cell's own collected parts are concatenated with
        # whitespace removed. Do not strip whitespace across neighbouring cells.
        compact = "".join(re.sub(r"\s+", "", part) for part in collected)
        if cell.name not in haystack and cell.name not in compact:
            errors.append(
                f"printed: cell {cell.name!r} has no visible text containing its "
                "data-name"
            )


def verify_file(path: Path) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    check_transforms(source, errors)
    row_marks: list[RowMark] = []
    headers, cells, visibility = parse_marks(source, errors, row_marks)
    if not cells:
        errors.append(
            "no cells declare data-stage and data-name; the blueprint data contract "
            "is missing"
        )
        return errors
    check_layers(cells, errors)
    check_visibility(source, cells, headers, visibility, errors)
    check_grid(headers, cells, errors)
    check_census(headers, cells, errors)
    check_focal(source, cells, row_marks, errors)
    check_printed(source, cells, errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify service-blueprint visibility-line grammar and stage grid."
    )
    parser.add_argument("paths", nargs="*", help="service-blueprint example HTML files")
    parser.add_argument(
        "--all",
        action="store_true",
        help="check every shipped example-service-blueprint*.html",
    )
    args = parser.parse_args()

    if args.all:
        paths = sorted(ASSET_DIR.glob("example-service-blueprint*.html"))
        if not paths:
            print(
                "FAIL service-blueprint: --all found no example-service-blueprint*.html "
                "under the skill assets"
            )
            return 2
    elif args.paths:
        paths = [Path(p) for p in args.paths]
    else:
        parser.print_usage()
        return 2

    failed = False
    for path in paths:
        if not path.is_file():
            print(f"FAIL {path}: no such file")
            failed = True
            continue
        findings = verify_file(path)
        if findings:
            failed = True
            print(f"FAIL {path}")
            for finding in findings:
                print(f"  - {finding}")
        else:
            print(f"OK {path}")
    if failed:
        return 1
    print(
        f"OK service-blueprint: {len(paths)} file(s) keep the visibility line on a "
        "shared stage grid"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
