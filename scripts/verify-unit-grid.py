#!/usr/bin/env python3
"""Verify the equal-unit contract for shipped Unit Grid waffle charts.

Usage:
    python3 scripts/verify-unit-grid.py --all
    python3 scripts/verify-unit-grid.py path/to/example-unit-grid.html

The checks are static and deliberately strict: anything a browser could use to
draw a cell differently from its declared state is rejected rather than
resolved. Not covered: HTML ancestors of the SVG (clip-path, mask-image,
opacity on a wrapping div), scripts (lint-skin pins those), page CSS that
resizes SVG text, and engine differences between browsers.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

# Match declarations, not text-transform or custom-property names. As in the
# waterfall verifier, CSS movement is rejected rather than cascade-resolved.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)\s*:",
    re.IGNORECASE,
)
# Paint is rejected in page CSS for the same reason: the cells carry their own fill.
CSS_PAINTS_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>fill|fill-opacity|opacity|visibility|filter|mask|mask-image|clip-path"
    r"|content-visibility|stroke(?:-[a-z]+)*|mix-blend-mode|all|paint-order"
    r"|display(?=\s*:\s*none\b))\s*:",
    re.IGNORECASE,
)
# Geometry a stylesheet can override on a cell. Rules whose subject is the svg or an HTML
# element cannot reach a cell; class-only rules cannot either, because cells may not carry class.
CSS_GEOMETRY = ("width", "height", "rx", "ry", "r", "cx", "cy")
CSS_RULE_RE = re.compile(r"([^{}]*)\{([^{}]*)\}")
SAFE_SUBJECT_RE = re.compile(
    r"(?:(?:svg|html|body|main|div|section|article|header|footer|figure|figcaption|nav|aside|p|h[1-6]"
    r"|ul|ol|li|span|table|thead|tbody|tr|td|th|button|label|img)|\.[\w-]+)"
    r"(?:[.:][\w-]+(?:\([^)]*\))?)*",
    re.IGNORECASE,
)
CSS_ESCAPE_RE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\n\r\f]?|(.))", re.DOTALL)
FONTS_HREF = "https://fonts.googleapis.com/"
# A cell may sit only inside the chart root and plain groups or links.
CELL_ANCESTORS = {"g", "a"}
CONDITIONAL = ("systemlanguage", "requiredextensions", "requiredfeatures")
BLENDS = ("mix-blend-mode", "paint-order")
ANIMATIONS = {"animate", "set", "animatetransform", "animatemotion", "animatecolor"}
DRAWABLES = {"rect", "path", "polygon", "polyline", "line", "circle", "ellipse", "text",
             "image", "use", "foreignobject", "svg"}
MAX_CELL_STROKE = 2.0
GLYPH_EM = 0.65  # shortcut: a Geist upper bound; a wider face or all-caps W/M runs can exceed it
TEXT_INHERITED = ("font-size", "text-anchor", "letter-spacing")
# A tspan with none of these draws inside its parent's line and box.
TSPAN_MOVES = ("x", "y", "dx", "dy", "rotate", "textlength", "font-size", "letter-spacing", "style", "transform",
               "stroke", "stroke-width")
MIN_EMPTY_DISTANCE = 64.0  # RGB distance; the shipped empty fills sit above 150
HEX_RE = re.compile(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})")
RGB_RE = re.compile(r"rgba?\(([^)]*)\)")
NUMBER_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
PATH_TOKEN_RE = re.compile(r"[MmLlHhVvCcSsQqTtZzAa]|" + NUMBER_RE.pattern)
PATH_ARITY = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2}


# Quoted CSS data is not a declaration: `--note: "a;transform:b"` moves nothing (#431).
# A quote opens a string only where the browser tokenizes one, so a comment, an
# unquoted url() (escapes included, so `url(a\)"b)` is one token; not a `url(` right
# after a name character, `#`, `@` or a NUL (read as U+FFFD), as in `myurl(`, `#url(` or
# `@url(`) and an escaped character are consumed first and kept as written. A string
# that never closes on its line is kept as well - a line feed, carriage return or form
# feed ends it - so the checker still fails closed on it, though its `/*` and `*/`
# become spaces: they open and close no comment. Every other character of a string becomes a space and its newlines
# stay, so each offset and line number still points into the CSS as written.
# Only a string in a declaration is blanked. One the next `{` follows before any `;` or `}`
# sits in a selector or an at-rule prelude, as does one in a statement that starts with
# `@`; it is kept exactly as written, because selectors are matched against it. Inside
# a url() every character but a name character becomes `_`. Comments are removed with
# blank_comments_outside_strings, never a bare `/* ... */` regex, so a `/*` or `*/` in a
# kept string opens and closes no comment.
# CSS the browser may read differently comes back unblanked: a character reference
# (decoded before CSS sees it inside <svg> and in every attribute value) or an escape
# left outside a string (`u\72 l(` is `url(`). Its `/*` and `*/` become spaces, since
# a string may hold them, so no comment remover can hide a declaration in it.
CSS_STRING_RE = re.compile(
    r"""/\*.*?(?:\*/|\Z)|(?<![-#@\w\x00\x80-\U0010ffff])url\((?![ \t\n\r\f]*["'])(?:\\[\s\S]|[^)\\])*\)|\\[\s\S]"""
    r"""|(?P<string>"(?:\\[\s\S]|[^"\\\n\r\f])*"|'(?:\\[\s\S]|[^'\\\n\r\f])*')"""
    r"""|(?P<bad>"(?:\\[\s\S]|[^"\\\n\r\f])*|'(?:\\[\s\S]|[^'\\\n\r\f])*)""",
    re.DOTALL | re.IGNORECASE,
)


def blank_css_strings(css: str) -> str:
    """CSS with the contents of every quoted string in a declaration blanked, same length and lines."""
    masked = CSS_STRING_RE.sub(lambda found: " " * len(found.group()), css)

    def blank(found):
        text = found.group()
        if text[0] in "/\\":
            return text  # a comment or an escape
        if found.group("bad") is not None:
            return text.replace("/*", "  ").replace("*/", "  ")
        if text[0] not in "\"'":
            return text[:4] + re.sub(r"[^\w\n-]", "_", text[4:-1]) + ")"  # url()
        after = re.compile(r"[{;}]").search(masked, found.end())
        start = max(masked.rfind(mark, 0, found.start()) for mark in "{;}") + 1
        if (after and after.group() == "{") or masked[start:found.start()].lstrip().startswith("@"):
            return text
        return re.sub(r"[^\n]", " ", text)

    blanked = CSS_STRING_RE.sub(blank, css)
    if "\\" in blanked or html.unescape(css) != css:
        return css.replace("/*", "  ").replace("*/", "  ")
    return blanked


def blank_comments_outside_strings(css: str) -> str:
    """CSS with every comment the browser sees turned to spaces, newlines kept, same length.

    A `/*` inside a string or a url() opens no comment, as in the CSS tokenizer.
    """
    return CSS_STRING_RE.sub(
        lambda found: re.sub(r"[^\n]", " ", found.group()) if found.group().startswith("/*") else found.group(),
        css,
    )


def decode_css(text: str) -> str:
    """Undo HTML references and CSS escapes so `f\\69ll` reads as `fill`."""
    def char(match: re.Match[str]) -> str:
        if match.group(1):
            value = chr(min(int(match.group(1), 16), 0x10FFFF) or 0xFFFD)
        else:
            value = match.group(2)
        # An escaped / or * is an identifier character, never a comment delimiter.
        return "_" if value in "/*" else value
    return CSS_ESCAPE_RE.sub(char, html.unescape(text))


def declarations(style: str | None) -> dict[str, str]:
    pairs = (part.split(":", 1) for part in decode_css(style or "").split(";") if ":" in part)
    return {name.strip().lower(): value.replace("!important", "").strip() for name, value in pairs}


def number(value: str | None, default: float | None = None) -> float | None:
    """A unitless SVG number, the default when absent, or None when it cannot be read exactly."""
    if value is None:
        return default
    return float(value) if NUMBER_RE.fullmatch(value.strip()) else None


def color(value: str | None) -> tuple[float, float, float, float] | None:
    """Literal hex or rgb()/rgba() as RGBA with channels on 0..255 and alpha on 0..1; anything else is unresolvable."""
    value = (value or "").strip().lower()
    if match := HEX_RE.fullmatch(value):
        digits = match.group(1)
        if len(digits) <= 4:
            digits = "".join(digit * 2 for digit in digits)
        channels = [int(digits[i:i + 2], 16) for i in range(0, len(digits), 2)]
        return (*channels[:3], channels[3] / 255 if len(channels) == 4 else 1.0)
    if match := RGB_RE.fullmatch(value):
        parts = [part for part in re.split(r"[\s,/]+", match.group(1)) if part]
        if len(parts) not in (3, 4):
            return None
        try:
            # A percentage is of 255 for a colour channel and of 1 for alpha.
            numbers = [float(part[:-1]) * (2.55 if index < 3 else 0.01) if part.endswith("%") else float(part)
                       for index, part in enumerate(parts)]
        except ValueError:
            return None
        return (*numbers[:3], numbers[3] if len(numbers) == 4 else 1.0)
    return None


def hidden_by(attributes: dict[str, str], style: dict[str, str]) -> list[str]:
    """Properties on one element that can hide a cell whatever its fill."""
    found = []
    for prop in ("opacity", "fill-opacity", "visibility", "display", "filter", "mask", "clip-path"):
        for value in (attributes.get(prop), style.get(prop)):
            if value is None:
                continue
            value = value.strip().lower()
            if prop in {"opacity", "fill-opacity"}:
                try:
                    shown = math.isclose(float(value[:-1]) / 100 if value.endswith("%") else float(value), 1.0)
                except ValueError:
                    shown = False
            elif prop == "visibility":
                shown = value in {"visible", "inherit"}
            elif prop == "display":
                shown = value != "none"
            else:
                shown = value == "none"
            if not shown:
                found.append(prop)
    return found


def points_box(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def path_box(d: str) -> tuple[float, float, float, float] | None:
    """Bounds of every end and control point (a Bezier stays inside its control hull).

    Arcs and smooth S/T segments, whose reflected control points are not tracked, are unbounded.
    """
    if PATH_TOKEN_RE.sub("", d).strip(" \t\n\r,"):
        return None
    tokens = PATH_TOKEN_RE.findall(d)
    x = y = start_x = start_y = 0.0
    points: list[tuple[float, float]] = []
    command = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command, index = token, index + 1
            if command in "AaSsTt":
                return None
            if command in "Zz":
                x, y = start_x, start_y
            continue
        if command is None or command in "Zz":
            return None
        arity = PATH_ARITY[command.lower()]
        args = tokens[index:index + arity]
        if len(args) < arity or any(arg.isalpha() for arg in args):
            return None
        values = [float(arg) for arg in args]
        index += arity
        relative = command.islower()
        if command in "Hh":
            x = values[0] + (x if relative else 0)
            points.append((x, y))
        elif command in "Vv":
            y = values[0] + (y if relative else 0)
            points.append((x, y))
        else:
            segment = [(values[i] + (x if relative else 0), values[i + 1] + (y if relative else 0))
                       for i in range(0, arity, 2)]
            points.extend(segment)
            x, y = segment[-1]
            if command in "Mm":
                start_x, start_y = x, y
                command = "l" if relative else "L"
    return points_box(points)


def text_box(attributes: dict[str, str], text: str) -> tuple[float, float, float, float] | None:
    """Generous bounds for one line of text: each glyph at most 0.65em wide (Geist), 1.2em above and 0.4em below."""
    if any(name in attributes for name in ("dx", "dy", "rotate", "textlength", "writing-mode", "direction")):
        return None
    x, y, size = number(attributes.get("x"), 0.0), number(attributes.get("y"), 0.0), number(attributes.get("font-size"), 16.0)
    spacing_value = (attributes.get("letter-spacing") or "0").strip()
    spacing = number(spacing_value[:-2]) if spacing_value.endswith("em") else number(spacing_value.removesuffix("px"))
    if x is None or y is None or size is None or spacing is None:
        return None
    em = size * (GLYPH_EM + (spacing if spacing_value.endswith("em") else spacing / size if size else 0))
    width = len(" ".join(text.split())) * em
    anchor = (attributes.get("text-anchor") or "start").strip()
    left = {"start": x, "middle": x - width / 2, "end": x - width}.get(anchor)
    if left is None:
        return None
    return left, y - 1.2 * size, left + width, y + 0.4 * size


def drawn_box(tag: str, attributes: dict[str, str], text: str,
              stroke_width: float | None) -> tuple[float, float, float, float] | None:
    """Exact-or-larger bounds of a drawable, or None when they cannot be computed from its attributes."""
    get = attributes.get
    if tag in {"rect", "image", "foreignobject"}:
        box = (number(get("x"), 0.0), number(get("y"), 0.0), number(get("width")), number(get("height")))
        if None in box:
            return None
        x, y, width, height = box
        found = (x, y, x + width, y + height)
    elif tag == "circle":
        cx, cy, r = number(get("cx"), 0.0), number(get("cy"), 0.0), number(get("r"))
        found = None if None in (cx, cy, r) else (cx - r, cy - r, cx + r, cy + r)
    elif tag == "ellipse":
        cx, cy, rx, ry = number(get("cx"), 0.0), number(get("cy"), 0.0), number(get("rx")), number(get("ry"))
        found = None if None in (cx, cy, rx, ry) else (cx - rx, cy - ry, cx + rx, cy + ry)
    elif tag == "line":
        ends = [number(get(name), 0.0) for name in ("x1", "y1", "x2", "y2")]
        found = None if None in ends else points_box([(ends[0], ends[1]), (ends[2], ends[3])])
    elif tag in {"polygon", "polyline"}:
        values = (get("points") or "").replace(",", " ").split()
        numbers = [number(value) for value in values]
        if not numbers or None in numbers or len(numbers) % 2:
            return None
        found = points_box(list(zip(numbers[::2], numbers[1::2])))
    elif tag == "path":
        found = path_box(get("d") or "")
    elif tag == "text":
        found = text_box(attributes, text)
    else:  # use, nested svg: their drawing depends on content elsewhere
        return None
    if found is None or stroke_width is None:
        return None
    # Half the stroke falls outside the geometry; markers and miters on outlines can reach further.
    pad = stroke_width * (2 if tag in {"path", "polygon", "polyline", "line", "text"} else 0.5)
    return found[0] - pad, found[1] - pad, found[2] + pad, found[3] + pad


class Presentation(HTMLParser):
    """Find cells, labels, styles and later drawables the way a browser parses them."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.errors: list[str] = []
        self.labels: dict[str, list[str]] = {"data-unit-percent": [], "data-unit-count": []}
        self.active_labels: list[tuple[str, str, list[str]]] = []
        self.styles: list[str] = []
        self.in_style = False
        self.root: dict[str, str] | None = None
        # Elements open inside the chart root, root first.
        self.open: list[tuple[str, dict[str, str]]] = []
        self.cells: list[dict[str, str]] = []
        self.paints: list[tuple[str | None, str | None, str, list[str]]] = []
        self.later: list[dict[str, object]] = []
        self.active_texts: list[dict[str, object]] = []
        self.label_marks: list[tuple[str, str | None, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        for _, label, _ in self.active_labels:
            self.errors.append(f"the {label} label contains <{tag}>; print the value as plain text")
        names = [name for name, _ in attributes]
        for name in dict.fromkeys(name for name in names if names.count(name) > 1):
            self.errors.append(f"<{tag}> repeats attribute {name}; browsers keep only the first")
        tag_attrs = {name: value or "" for name, value in reversed(attributes)}  # first wins, as in browsers
        style = declarations(tag_attrs.get("style"))
        if tag == "style":
            self.in_style = True
        if tag == "link" and "stylesheet" in (tag_attrs.get("rel") or "").lower().split() \
                and not (tag_attrs.get("href") or "").startswith(FONTS_HREF):
            self.errors.append("only the Google Fonts stylesheet may be linked; a linked stylesheet can repaint cells")
        is_cell = tag == "rect" and "data-unit-cell" in tag_attrs
        if tag in {"svg", "g"} or is_cell:
            if "transform" in tag_attrs:
                self.errors.append(f"{tag} transform can move verified unit cells; use explicit coordinates")
            movement = CSS_MOVES_MARK_RE.search(decode_css(tag_attrs.get("style") or ""))
            if movement:
                self.errors.append(f"inline {movement['prop']} can move verified unit cells")
        if tag in ANIMATIONS:
            self.errors.append(f"<{tag}> can repaint or move verified unit cells; draw the final state")
        if self.open:
            if is_cell:
                self.cell(tag_attrs, style)
            elif self.paints and tag in DRAWABLES:
                self.drawable(tag, tag_attrs)
            if tag == "textpath" or (tag == "tspan" and any(name in tag_attrs for name in TSPAN_MOVES)):
                for text in self.active_texts:
                    text["exact"] = False
            self.open.append((tag, tag_attrs))
        elif tag == "svg" and "data-unit-grid" in tag_attrs and self.root is None:
            self.root = tag_attrs
            self.open.append((tag, tag_attrs))
        elif is_cell:
            self.errors.append(f"unit cell {tag_attrs.get('data-unit-index')} sits outside the data-unit-grid svg")
        for name in self.labels:
            if name in tag_attrs:
                self.label(name, tag, tag_attrs)
                self.active_labels.append((tag, name, []))

    def label(self, name: str, tag: str, attributes: dict[str, str]) -> None:
        """A printed value counts only as visible text inside the chart, held to the cells' rules."""
        if tag != "text" or not self.open or self.open[-1][1] is not attributes:
            self.errors.append(f"the {name} label must be a <text> inside the data-unit-grid svg")
            return
        fill = None
        inherited: dict[str, str] = {}
        for depth, (element_tag, element) in enumerate(reversed(self.open)):
            problems = hidden_by(element, declarations(element.get("style")))
            problems += [attr for attr in ("style", "transform", *CONDITIONAL) if attr in element]
            if 0 < depth < len(self.open) - 1 and element_tag not in CELL_ANCESTORS:
                problems.append(f"<{element_tag}> ancestor")
            for problem in dict.fromkeys(problems):
                self.errors.append(f"the {name} label is hidden or moved by {problem}")
            fill = fill if fill is not None else element.get("fill")
            for attr in TEXT_INHERITED:
                if attr in element:
                    inherited.setdefault(attr, element[attr])
        inherited.update({attr: value for attr, value in attributes.items()
                          if attr in {"x", "y", "dx", "dy", "rotate", "textlength", "writing-mode", "direction"}})
        self.label_marks.append((name, fill, inherited))

    def cell(self, attributes: dict[str, str], style: dict[str, str]) -> None:
        index = attributes.get("data-unit-index")
        chain = self.open + [("rect", attributes)]
        hides: list[str] = []
        fill = stroke = stroke_width = None
        for depth, (tag, element) in enumerate(reversed(chain)):
            element_style = declarations(element.get("style"))
            hides += hidden_by(element, element_style)
            if 0 < depth < len(chain) - 1 and tag not in CELL_ANCESTORS:
                hides.append(f"<{tag}> ancestor")
            if depth and tag == "a" and "transform" in element:
                self.errors.append("a transform can move verified unit cells; use explicit coordinates")
            if "style" in element:
                self.errors.append(f"style attribute on <{tag}> can repaint, hide or move unit cells; use presentation attributes")
            for name in CONDITIONAL:
                if name in element:
                    hides.append(f"{name} on <{tag}>")
            for name in BLENDS:
                if name in element:
                    self.errors.append(f"{name} on <{tag}> can change how unit cell {index} is painted")
            # The nearest declared fill, stroke and stroke-width win; inline style beats the attribute.
            own = {name: element_style.get(name) or element.get(name) for name in ("fill", "stroke", "stroke-width")}
            own = {name: value for name, value in own.items() if value is not None and value.strip().lower() != "inherit"}
            fill = fill if fill is not None else own.get("fill")
            stroke = stroke if stroke is not None else own.get("stroke")
            stroke_width = stroke_width if stroke_width is not None else own.get("stroke-width")
        if (stroke or "none").strip().lower() != "none":
            width = number(stroke_width, 1.0)
            if width is None or width > MAX_CELL_STROKE:
                self.errors.append(f"unit cell {index} stroke-width {stroke_width} can repaint the cell; keep cell strokes at or under {MAX_CELL_STROKE:g}")
        size = min(number(attributes.get("width"), 0.0) or 0.0, number(attributes.get("height"), 0.0) or 0.0)
        for name in ("rx", "ry"):
            radius = number(attributes.get(name), 0.0)
            if radius is None or radius > size / 4:
                self.errors.append(f"unit cell {index} {name} {attributes.get(name)} rounds away its area; keep corner radii at or under a quarter of the cell")
        if "class" in attributes:
            self.errors.append(f"unit cell {index} class can attach stylesheet rules; use presentation attributes")
        self.cells.append(attributes)
        # SVG paints an element with no fill anywhere in its ancestry black.
        self.paints.append((index, attributes.get("data-unit-cell"), fill or "#000000", hides))

    def drawable(self, tag: str, attributes: dict[str, str]) -> None:
        moved = any("transform" in element or "style" in element or (name == "svg" and depth)
                    for depth, (name, element) in enumerate(self.open))
        chain = list(reversed(self.open + [(tag, attributes)]))
        stroke_width = next((element.get("stroke-width") for _, element in chain if "stroke-width" in element), None)
        stroke = next((element.get("stroke") for _, element in chain if "stroke" in element), None)
        if tag == "text" and (stroke or "none").strip().lower() == "none":
            stroke_width = "0"  # unstroked glyphs draw only their fill
        if tag == "text":  # font-size, anchor and spacing inherit from the nearest group that sets them
            attributes = {**{name: value for name in TEXT_INHERITED for _, element in self.open
                             if (value := element.get(name)) is not None}, **attributes}
        record: dict[str, object] = {
            "tag": tag, "attrs": attributes, "text": [],
            "exact": not moved and "transform" not in attributes and "style" not in attributes,
            "stroke": number(stroke_width, 1.0),
        }
        self.later.append(record)
        if tag == "text":
            self.active_texts.append(record)

    def handle_startendtag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attributes)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self.in_style = False
        if tag == "text" and self.active_texts:
            self.active_texts.pop()
        if any(name == tag for name, _ in self.open):
            while self.open and self.open.pop()[0] != tag:
                pass
        for entry in self.active_labels[:]:
            if entry[0] == tag:
                self.labels[entry[1]].append("".join(entry[2]).strip())
                self.active_labels.remove(entry)

    def handle_data(self, data: str) -> None:
        if self.in_style:
            self.styles.append(decode_css(blank_css_strings(data)))
        for text in self.active_texts:
            text["text"].append(data)  # type: ignore[union-attr]
        for _, _, fragments in self.active_labels:
            fragments.append(data)

    def check(self, filled: int, total: int) -> list[str]:
        for style in self.styles:
            css = blank_comments_outside_strings(style)
            movement = CSS_MOVES_MARK_RE.search(css)
            if movement:
                self.errors.append(f"CSS {movement['prop']} can move verified unit cells")
            paint = CSS_PAINTS_MARK_RE.search(css)
            if paint:
                self.errors.append(f"CSS {paint['prop']} can repaint or hide verified unit cells")
            for selector, body in CSS_RULE_RE.findall(css):
                subjects = [re.split(r"[\s>+~]+", part.strip())[-1] for part in selector.split(",")]
                if all(SAFE_SUBJECT_RE.fullmatch(subject) for subject in subjects):
                    continue
                for prop in CSS_GEOMETRY:
                    if prop in declarations(body):
                        self.errors.append(f"CSS {prop} can resize verified unit cells; set geometry on the <rect>")
            if re.search(r"@import\b", css, re.IGNORECASE):
                self.errors.append("CSS @import can load rules that repaint cells")
        self.check_paint()
        if self.labels["data-unit-percent"] != [f"{filled}%"]:
            self.errors.append(f"printed percentage must state {filled}% in one data-unit-percent label")
        wanted = f"{filled} complete · {total - filled} remaining"
        if self.labels["data-unit-count"] != [wanted]:
            self.errors.append(f"printed count must state {wanted!r} in one data-unit-count label")
        return list(dict.fromkeys(self.errors))

    def check_paint(self) -> None:
        """Bind each cell's drawn fill to its declared state."""
        css = blank_comments_outside_strings("".join(self.styles))
        root = ";".join(re.findall(r":root\s*\{([^}]*)\}", css))
        tokens = {name: color(value) for name, value in declarations(root).items()}
        ink, accent = tokens.get("--ink"), tokens.get("--accent")
        if ink is None or accent is None:
            self.errors.append("page must declare literal --ink and --accent colours in :root to bind cell fills")
            return
        problems: dict[str, list[str]] = {}
        accents = 0
        remaining: set[tuple[float, float, float, float]] = set()
        for index, state, fill, hides in self.paints:
            for prop in dict.fromkeys(hides):
                problems.setdefault(f"hidden by {prop}", []).append(str(index))
            paint = color(fill)
            if state == "filled":
                drawn = paint in {ink, accent}
                accents += paint == accent and accent != ink
            elif state == "empty":
                drawn = paint is not None and paint[3] == 1 and paint not in {ink, accent}
                if drawn:
                    remaining.add(paint)
            else:
                continue
            if not drawn:
                problems.setdefault(f"declared {state} but painted {fill}", []).append(str(index))
        for problem, indices in problems.items():
            self.errors.append(f"unit cell(s) {', '.join(indices)} {problem}")
        allowed = {ink} | ({tokens["--muted"]} if tokens.get("--muted") else set())
        view = [number(value) for value in (self.root or {}).get("viewbox", "").replace(",", " ").split()]
        for name, fill, attributes in self.label_marks:
            size = number(attributes.get("font-size"), 16.0)
            text = (self.labels[name] or [""])[0]
            box = text_box(attributes, text)
            if color(fill or "#000000") not in allowed:
                self.errors.append(f"the {name} label is painted {fill}; use the --ink or --muted colour")
            if size is None or size < 8:
                self.errors.append(f"the {name} label font-size must be a number of at least 8")
            if len(view) != 4 or None in view or box is None or not (
                    view[0] <= box[0] and view[1] <= box[1] and box[2] <= view[0] + view[2] and box[3] <= view[1] + view[3]):
                self.errors.append(f"the {name} label must sit inside the chart viewBox")
        if accents > 1:
            self.errors.append(f"{accents} completed cells use --accent; at most one completed cell may use --accent")
        if len(remaining) > 1:
            self.errors.append("remaining cells must share one fill")
        for paint in remaining:
            if min(math.dist(paint[:3], token[:3]) for token in (ink, accent)) <= MIN_EMPTY_DISTANCE:
                self.errors.append(f"remaining-cell fill is too close to --ink or --accent to read as empty (RGB distance must exceed {MIN_EMPTY_DISTANCE:g})")


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    presentation = Presentation()
    presentation.feed(source)
    presentation.close()
    svg = presentation.root
    if svg is None:
        return [f"{path.name}: missing data-unit-grid root"]
    findings: list[str] = []
    try:
        total = int(svg["data-unit-total"])
        filled = int(svg["data-unit-filled"])
        rows = int(svg["data-unit-rows"])
        columns = int(svg["data-unit-columns"])
    except (KeyError, ValueError):
        return [f"{path.name}: unit-grid metadata must declare integer total, filled, rows, and columns"]
    if (total, rows, columns) != (100, 10, 10):
        findings.append(f"{path.name}: canonical waffle must declare 100 total units in a 10 by 10 grid")
    if not 0 <= filled <= total:
        findings.append(f"{path.name}: filled count {filled} must be within 0..{total}")
    findings.extend(f"{path.name}: {error}" for error in presentation.check(filled, total))
    marks = presentation.cells
    if len(marks) != total:
        findings.append(f"{path.name}: declares {total} units but has {len(marks)} data-unit-cell marks")
        return findings
    indices: set[int] = set()
    positions: set[tuple[float, float]] = set()
    sizes: set[tuple[float, float]] = set()
    geometry: list[tuple[int, float, float, float, float, str | None]] = []
    rendered_filled = 0
    for mark in marks:
        state = mark.get("data-unit-cell")
        if state not in {"filled", "empty"}:
            findings.append(f"{path.name}: data-unit-cell must be filled or empty")
        elif state == "filled":
            rendered_filled += 1
        try:
            index = int(mark["data-unit-index"])
            x, y = float(mark["x"]), float(mark["y"])
            width, height = float(mark["width"]), float(mark["height"])
        except (KeyError, ValueError):
            findings.append(f"{path.name}: every unit cell needs numeric index and geometry")
            continue
        if not all(math.isfinite(value) for value in (x, y, width, height)) or width <= 0 or height <= 0:
            findings.append(f"{path.name}: every unit cell needs finite positive geometry")
            continue
        indices.add(index)
        positions.add((x, y))
        sizes.add((width, height))
        geometry.append((index, x, y, width, height, state))
    if indices != set(range(total)):
        findings.append(f"{path.name}: unit indices must cover 0 through {total - 1} exactly once")
    if len(positions) != total:
        findings.append(f"{path.name}: unit cells must occupy unique positions")
    if len(sizes) != 1:
        findings.append(f"{path.name}: every unit cell must have identical dimensions")
    if rendered_filled != filled:
        findings.append(f"{path.name}: declares {filled} filled units but renders {rendered_filled}")
    xs = sorted({x for x, _ in positions})
    ys = sorted({y for _, y in positions})
    if len(xs) != columns or len(ys) != rows:
        findings.append(f"{path.name}: unit positions must form a {columns} by {rows} grid")
    elif len(sizes) == 1:
        width, height = next(iter(sizes))
        x_gutters = [right - left - width for left, right in zip(xs, xs[1:])]
        y_gutters = [lower - upper - height for upper, lower in zip(ys, ys[1:])]
        if any(not math.isclose(gutter, 4.0, abs_tol=1e-6) for gutter in x_gutters + y_gutters):
            findings.append(f"{path.name}: rows and columns must use a 4px gutter")

    overlap = False
    for offset, (_, x1, y1, width1, height1, _) in enumerate(geometry):
        for _, x2, y2, width2, height2, _ in geometry[offset + 1:]:
            if x1 < x2 + width2 and x2 < x1 + width1 and y1 < y2 + height2 and y2 < y1 + height1:
                overlap = True
                break
        if overlap:
            break
    if overlap:
        findings.append(f"{path.name}: unit cells must not overlap")

    if geometry:
        grid = (min(g[1] for g in geometry), min(g[2] for g in geometry),
                max(g[1] + g[3] for g in geometry), max(g[2] + g[4] for g in geometry))
        for record in presentation.later:
            tag = str(record["tag"])
            box = drawn_box(tag, record["attrs"], "".join(record["text"]), record["stroke"]) \
                if record["exact"] else None  # type: ignore[arg-type]
            if box is None:
                findings.append(f"{path.name}: a later <{tag}> cannot be bounded exactly, so it may cover the unit grid; draw it before the cells or with plain numeric geometry")
            elif box[0] < grid[2] and grid[0] < box[2] and box[1] < grid[3] and grid[1] < box[3]:
                findings.append(f"{path.name}: a later <{tag}> covers the unit grid; draw annotations outside it")

    if len(geometry) == total and indices == set(range(total)):
        reading_order = [mark[0] for mark in sorted(geometry, key=lambda mark: (mark[2], mark[1]))]
        if reading_order != list(range(total)):
            findings.append(f"{path.name}: unit indices must follow left-to-right, top-to-bottom reading order")
        filled_indices = {index for index, *_, state in geometry if state == "filled"}
        if filled_indices != set(range(filled)):
            findings.append(f"{path.name}: filled cells must occupy the first indices in reading order")
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    return sorted(ASSET_DIR.glob("example-unit-grid*.html")) if args.all else [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Unit Grid equal-cell waffle charts.")
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped Unit Grid example")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2
    findings: list[str] = []
    for path in targets(args):
        if not path.exists():
            print(f"error: {path} does not exist", file=sys.stderr)
            return 2
        findings.extend(check(path))
    if findings:
        print("\n".join(findings))
        return 1
    print(f"OK Unit Grid: {len(targets(args))} file(s) preserve equal unit cells and declared counts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
