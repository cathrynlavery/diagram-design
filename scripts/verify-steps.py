#!/usr/bin/env python3
"""Verify the structural claims of Steps diagrams.

Steps encodes order with one contiguous equal-width rail. Machine-readable
attributes bind every rail segment, printed number, and icon medallion to the
same stage so geometry cannot silently disagree with its labels.

What is measured must be what the browser draws, so the contract is an
allow-list rather than a list of known tricks:

- The page is parsed as HTML (comments are not marks). No element repeats an
  attribute; the page around the one SVG uses only the shipped page tags and
  attributes, and only the Google Fonts stylesheet link.
- A checked mark (rail rect, medallion circle, number text) carries only its
  own geometry, paint and data attributes, sits under nothing but plain <g>
  groups of the root SVG, and stays inside the viewBox. A number has no child
  elements. Rails fill and medallions stroke with a non-paper house ink;
  numbers are a solid house ink at font-size 8 or more.
- A <style> rule may not use escapes, @import or at-rules other than @media
  and @font-face; may not move anything; and may set only box-sizing, margin,
  padding and custom properties on selectors that can reach SVG content, only
  layout-neutral page properties on the SVG's HTML ancestors, and anything
  but movement on page elements outside the SVG.

Usage:
    python3 scripts/verify-steps.py --all
    python3 scripts/verify-steps.py skills/diagram-design/assets/example-steps.html
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
TOLERANCE = 0.01
CHECKED_ROLES = {"rail": "rect", "medallion": "circle", "number": "text"}
MARK_ATTRS = {
    "rail": {"x", "y", "width", "height", "fill", "fill-opacity", "data-role", "data-step", "data-index", "data-focal"},
    "medallion": {"cx", "cy", "r", "fill", "stroke", "stroke-width", "data-role", "data-step", "data-focal"},
    "number": {
        "x", "y", "fill", "font-size", "font-weight", "font-family", "text-anchor", "data-role", "data-step",
    },
}
GROUP_ATTRS = {
    "aria-hidden", "fill", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "font-family", "font-size", "font-weight", "letter-spacing", "text-anchor",
}
ROOT_ATTRS = {"viewbox", "xmlns", "role", "aria-labelledby"}
SVG_TAGS = {"svg", "title", "desc", "defs", "pattern", "g", "rect", "circle", "line", "path", "text", "tspan"}
HIDING_PROPS = {"display", "visibility", "opacity", "fill-opacity", "stroke-opacity", "clip-path", "mask", "filter"}
# House inks per paper (style-guide.md); a mark painted in the paper colour vanishes.
INK = {
    "#f5f5f5": {"#2d3142", "#4f5d75", "#2e5aa8", "#bf4520"},
    "#2d3142": {"#f5f5f5", "#bfc0c0", "#739fdf", "#f08a59"},
}
MIN_OPACITY = 0.4
MIN_FONT_SIZE = 8
HOUSE_FONTS = {"geist", "geist mono", "instrument serif"}
MAX_STROKE_WIDTH = 4
FONTS_HREF = "https://fonts.googleapis.com/css2?"
PAGE_TAGS = {
    "html": {"lang"}, "head": set(), "meta": {"charset", "name", "content"}, "title": set(),
    "link": {"href", "rel"}, "style": set(), "body": set(), "div": {"class"}, "p": {"class"},
    "h1": set(), "h2": set(), "h3": set(), "header": {"class"}, "footer": {"class"},
    "section": {"class"}, "article": {"class"}, "span": {"class"}, "main": {"class"}, "ul": {"class"},
    "ol": {"class"}, "li": {"class"}, "code": {"class"}, "em": {"class"}, "strong": {"class"},
    "small": {"class"}, "br": set(),
}
# Only block containers may hold the diagram SVG.
SVG_CONTAINERS = {"#document", "html", "body", "div", "main", "section", "article"}
VOID = {"meta", "link", "br", "img", "input", "hr", "source", "wbr"}
MOVEMENT = {
    "transform", "translate", "rotate", "scale", "perspective", "zoom", "position", "top", "right",
    "bottom", "left", "z-index", "float", "x", "y", "cx", "cy", "r", "rx", "ry", "d",
}
CSS_HIDING = HIDING_PROPS | {"content-visibility", "clip", "backdrop-filter", "mix-blend-mode"}
# Anything a rule that can match SVG content may set; the rest paints or sizes marks.
SVG_RULE_ALLOWED = {"box-sizing", "margin", "padding"}
# The root svg box may only fill its container.
SVG_BOX = {"width": {"100%"}, "max-width": {"100%", "none"}, "height": {"auto"}, "display": {"block"}}
# HTML ancestors of the SVG may lay the page out but not paint, size or reflow text inside it.
ANCESTOR_ALLOWED = {
    "box-sizing", "color", "font-family", "min-height", "align-items", "justify-content", "gap",
    "border-radius", "overflow-x", "width", "max-width", "display",
}
ANCESTOR_PREFIXES = ("margin", "padding", "border", "background")
ANCESTOR_VALUES = {"overflow-x": {"auto", "visible"}, "width": {"100%", "auto"}, "display": {"block", "flex", "grid"}}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str], parent: Node | None) -> None:
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Node] = []
        self.text = ""

    def ancestors(self) -> list[Node]:
        found, node = [], self.parent
        while node is not None:
            found.append(node)
            node = node.parent
        return found


class Tree(HTMLParser):
    """Build the element tree the browser sees: comments dropped, first duplicate attribute wins."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#document", {}, None)
        self.open = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, pairs: list[tuple[str, str | None]], closed: bool = False) -> None:
        names = [name for name, _ in pairs]
        if len(names) != len(set(names)):
            self.errors.append(f"attributes: <{tag}> repeats an attribute; the browser keeps only the first")
        attrs: dict[str, str] = {}
        for name, value in pairs:
            attrs.setdefault(name, value or "")
        node = Node(tag, attrs, self.open[-1])
        self.open[-1].children.append(node)
        self.nodes.append(node)
        if not closed and tag not in VOID:
            self.open.append(node)

    def handle_startendtag(self, tag: str, pairs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, pairs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.open) - 1, 0, -1):
            if self.open[index].tag == tag:
                del self.open[index:]
                break

    def handle_data(self, data: str) -> None:
        self.open[-1].text += data


def number(attrs: dict[str, str], key: str) -> float | None:
    try:
        value = float(attrs[key].strip().removesuffix("px"))
    except (KeyError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def color(value: str) -> tuple[str, float] | None:
    """A house colour as (#rrggbb, alpha); None for anything else (none, url(), currentColor)."""
    value = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", value):
        return value, 1.0
    match = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d+(?:\.\d+)?|\.\d+)\s*)?\)", value)
    if not match or any(int(part) > 255 for part in match.groups()[:3]):
        return None
    alpha = float(match.group(4)) if match.group(4) else 1.0
    return "#" + "".join(f"{int(part):02x}" for part in match.groups()[:3]), alpha


def inherited(node: Node, name: str, svg: Node) -> str | None:
    for item in [node, *node.ancestors()]:
        if name in item.attrs:
            return item.attrs[name]
        if item is svg:
            break
    return None


def attr_category(name: str) -> str:
    if name == "transform":
        return "transform"
    return "hidden" if name in HIDING_PROPS or name == "hidden" else "style"


def declarations(block: str) -> list[tuple[str, str]]:
    found = []
    for part in block.split(";"):
        name, colon, value = part.partition(":")
        if colon and name.strip():
            name = re.sub(r"^-(?:webkit|moz|ms|o)-", "", name.strip())
            found.append((name, value.replace("!important", "").strip()))
    return found


def css_blocks(css: str) -> list[tuple[str, str]] | None:
    """Top-level (prelude, body) pairs; None when text sits outside a block or braces do not balance."""
    blocks, depth, start, body_start = [], 0, 0, 0
    for index, char in enumerate(css):
        if char == "{":
            if depth == 0:
                body_start = index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                blocks.append((css[start:body_start - 1].strip(), css[body_start:index]))
                start = index + 1
    return blocks if depth == 0 and not css[start:].strip() else None


def selector_kind(selector: str, ancestor_tags: set[str], ancestor_classes: set[str]) -> str:
    """'svg' when it can match SVG content, 'ancestor' for the SVG's HTML ancestors, else 'page'."""
    flat = selector
    while re.search(r"\([^()]*\)|\[[^\[\]]*\]", flat):
        flat = re.sub(r"\([^()]*\)|\[[^\[\]]*\]", "", flat)
    compound = re.split(r"\s*[>+~]\s*|\s+", flat.strip())[-1]
    compound = re.sub(r"::?(?:before|after|marker|placeholder|selection)\b", "", compound)
    tag_match = re.match(r"[a-z][\w-]*|\*", compound)
    tag = tag_match.group(0) if tag_match else ""
    classes = set(re.findall(r"\.([\w-]+)", compound))
    if tag in SVG_TAGS:
        return "svg"
    if ":root" in compound or tag in ancestor_tags or classes & ancestor_classes:
        return "ancestor"
    # SVG content and the SVG's ancestors carry no other class, and no SVG element has an HTML tag.
    if (tag and tag != "*") or classes or "#" in compound:
        return "page"
    return "svg"


def rule_errors(selectors: str, body: str, ancestor_tags: set[str], ancestor_classes: set[str]) -> list[str]:
    errors = []
    decls = declarations(body)
    for selector in (part.strip() for part in selectors.split(",")):
        kind = selector_kind(selector, ancestor_tags, ancestor_classes)
        for name, value in decls:
            if name.startswith("--"):
                continue
            where = f"stylesheet rule {selector!r} sets {name}: {value}"
            if name in MOVEMENT or name.startswith(("offset", "inset")):
                errors.append(f"transform: {where}; nothing on the page may move")
            elif kind == "page":
                continue
            elif name in CSS_HIDING and not (name == "display" and value in ANCESTOR_VALUES["display"]):
                errors.append(f"hidden: {where} on content that holds the diagram")
            elif kind == "svg" and not (
                name in SVG_RULE_ALLOWED or (name in {"animation", "transition"} and value == "none")
                or (selector == "svg" and (name == "min-width" or value in SVG_BOX.get(name, ())))
            ):
                errors.append(f"style: {where} on SVG content; style marks with presentation attributes")
            elif kind == "ancestor":
                allowed = name in ANCESTOR_ALLOWED or name.startswith(ANCESTOR_PREFIXES)
                if name == "max-width":
                    width = re.fullmatch(r"(\d+(?:\.\d+)?)(px|r?em)", value)
                    floor = 960 if width and width.group(2) == "px" else 60
                    allowed = value in {"none", "100%"} or bool(width and float(width.group(1)) >= floor)
                elif name in ANCESTOR_VALUES:
                    allowed = value in ANCESTOR_VALUES[name]
                if not allowed:
                    errors.append(f"style: {where} on an HTML ancestor of the diagram")
    return errors


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


def stylesheet_errors(css: str, ancestor_tags: set[str], ancestor_classes: set[str]) -> list[str]:
    if "\\" in css:
        return ["style: CSS escapes are unsupported in a <style>"]
    css = blank_comments_outside_strings(blank_css_strings(css)).lower()
    errors = ["style: @import is unsupported"] if "@import" in css else []
    blocks = css_blocks(css)
    if blocks is None:
        return [*errors, "style: unsupported stylesheet structure"]
    for prelude, body in blocks:
        if prelude.startswith("@media"):
            errors.extend(stylesheet_errors(body, ancestor_tags, ancestor_classes))
        elif prelude == "@font-face":
            continue
        elif prelude.startswith("@"):
            errors.append(f"style: at-rule {prelude.split()[0]!r} is unsupported")
        else:
            errors.extend(rule_errors(prelude, body, ancestor_tags, ancestor_classes))
    return errors


def page_errors(tree: Tree) -> tuple[list[str], Node | None]:
    """The page skeleton around the one root SVG, and every element inside it."""
    errors: list[str] = []
    roots = [node for node in tree.nodes if node.tag == "svg" and not any(a.tag == "svg" for a in node.ancestors())]
    if len(roots) != 1:
        errors.append(f"page: expected exactly one diagram SVG, found {len(roots)}")
    svg = roots[0] if roots else None
    for node in tree.nodes:
        in_svg = svg is not None and (node is svg or svg in node.ancestors())
        if in_svg:
            if node.tag not in SVG_TAGS or (node.tag == "svg" and node is not svg):
                errors.append(f"hidden: <{node.tag}> is unsupported inside the diagram SVG")
            for name in {"style", "class"} & set(node.attrs):
                errors.append(f"style: <{node.tag}> in the diagram carries {name}; use presentation attributes")
            continue
        allowed = PAGE_TAGS.get(node.tag)
        extra = sorted(set(node.attrs) - (allowed or set()))
        if allowed is None or extra:
            errors.append(f"page: unsupported <{node.tag}> {' '.join(extra)}".rstrip() + " around the diagram")
        if node.tag == "link" and not (node.attrs.get("rel") == "stylesheet" and node.attrs.get("href", "").startswith(FONTS_HREF)):
            errors.append("page: only the Google Fonts stylesheet link is allowed")
    if svg is not None and any(node.tag not in SVG_CONTAINERS for node in svg.ancestors()):
        errors.append("page: the diagram SVG must sit in block containers (html, body, div, main, section, article)")
    if svg is not None and not set(svg.attrs) <= ROOT_ATTRS:
        errors.append(f"style: the diagram SVG carries {sorted(set(svg.attrs) - ROOT_ATTRS)}")
    return errors, svg


def mark_errors(node: Node, role: str, svg: Node, paper: str) -> list[str]:
    errors = []
    for name in sorted(set(node.attrs) - MARK_ATTRS[role]):
        errors.append(f"{attr_category(name)}: checked {role} mark carries unsupported {name}")
    if node.tag != CHECKED_ROLES[role]:
        errors.append(f"{role}: data-role='{role}' must be on a <{CHECKED_ROLES[role]}>")
    for ancestor in node.ancestors():
        if ancestor is svg:
            break
        if ancestor.tag != "g":
            errors.append(f"hidden: checked {role} mark sits inside <{ancestor.tag}>")
            continue
        for name in sorted(set(ancestor.attrs) - GROUP_ATTRS):
            errors.append(f"{attr_category(name)}: checked {role} mark has a g ancestor with {name}")
    inks = INK.get(paper, set())
    stroke = inherited(node, "stroke", svg)
    stroke_width = number({"w": inherited(node, "stroke-width", svg) or "1"}, "w")
    stroke_ink = color(stroke) if stroke else None
    if stroke not in (None, "none") and (not stroke_ink or stroke_ink[0] not in inks):
        errors.append(f"paint: checked {role} mark stroke {stroke!r} is not a house ink on this paper")
    if stroke_width is None or not 0 < stroke_width <= MAX_STROKE_WIDTH:
        errors.append(f"paint: checked {role} mark stroke-width must be within 0..{MAX_STROKE_WIDTH}")
    fill = color(inherited(node, "fill", svg) or "")
    if role == "rail":
        fill_opacity = number({"o": node.attrs.get("fill-opacity", "1")}, "o")
        if not (fill and fill[0] in inks and fill[1] > 0 and fill_opacity is not None and 0 < fill_opacity <= 1):
            errors.append(f"paint: rail fill {node.attrs.get('fill')!r} must be a visible non-paper house ink")
    if role == "medallion" and not (stroke_ink and stroke_ink[0] in inks and stroke_ink[1] >= MIN_OPACITY):
        errors.append(f"paint: medallion stroke {stroke!r} must be a visible non-paper house ink")
    if role == "number":
        if not (fill and fill[0] in inks and fill[1] >= MIN_OPACITY):
            errors.append(f"paint: number fill {node.attrs.get('fill')!r} must be a visible non-paper house ink")
        size = number({"s": inherited(node, "font-size", svg) or ""}, "s")
        if size is None or size < MIN_FONT_SIZE:
            errors.append(f"number: font-size must be at least {MIN_FONT_SIZE}")
        if node.children:
            errors.append("number: a printed number has no child elements")
        family = (inherited(node, "font-family", svg) or "").split(",")[0].strip(" '\"").lower()
        if family not in HOUSE_FONTS:
            errors.append(f"number: font-family must start with a house font ({', '.join(sorted(HOUSE_FONTS))})")
        # The centering check reads x as the number's middle.
        if (inherited(node, "text-anchor", svg) or "").strip() != "middle":
            errors.append("number: text-anchor must be middle")
    return errors


def close(first: float | None, second: float | None) -> bool:
    return first is not None and second is not None and abs(first - second) <= TOLERANCE


def verify(path: Path) -> list[str]:
    tree = Tree()
    tree.feed(path.read_text(encoding="utf-8"))
    tree.close()
    errors: list[str] = list(dict.fromkeys(tree.errors))
    found, svg = page_errors(tree)
    errors.extend(found)
    if svg is None:
        return errors
    ancestors = svg.ancestors()
    ancestor_tags = {node.tag for node in ancestors}
    ancestor_classes = {name for node in ancestors for name in node.attrs.get("class", "").split()}
    for node in tree.nodes:
        if node.tag == "style":
            errors.extend(stylesheet_errors(node.text, ancestor_tags, ancestor_classes))

    viewbox: tuple[float, float, float, float] | None = None
    try:
        values = tuple(float(value) for value in re.split(r"[\s,]+", svg.attrs.get("viewbox", "").strip()))
        if len(values) == 4 and all(math.isfinite(value) for value in values) and min(values[2:]) > 0:
            viewbox = values
    except ValueError:
        pass
    if viewbox is None:
        errors.append("canvas: missing or invalid SVG viewBox")
    paper_rect = next((child for child in svg.children if child.tag == "rect"), None)
    paper = (paper_rect.attrs.get("fill", "") if paper_rect else "").strip().lower()
    if paper not in INK:
        errors.append(f"paint: the SVG's first rect must be a house paper, found {paper!r}")

    found_marks: dict[str, list[tuple[str, dict[str, str], str]]] = {role: [] for role in CHECKED_ROLES}
    for node in tree.nodes:
        role = node.attrs.get("data-role")
        if role not in CHECKED_ROLES:
            continue
        errors.extend(error for error in mark_errors(node, role, svg, paper) if role != "rail" or "must be on a" not in error)
        found_marks[role].append((node.tag, node.attrs, node.text.strip()))
        if role == "number" and viewbox is not None:
            x, y = number(node.attrs, "x"), number(node.attrs, "y")
            vx, vy, vw, vh = viewbox
            if x is None or y is None or not (vx <= x <= vx + vw and vy <= y <= vy + vh):
                errors.append(f"canvas: number step {node.attrs.get('data-step', '')!r} falls outside the viewBox")
    errors = list(dict.fromkeys(errors))
    rails, medallions, numbers = found_marks["rail"], found_marks["medallion"], found_marks["number"]

    if not 3 <= len(rails) <= 7:
        errors.append(f"budget: expected 3..7 rail segments, found {len(rails)}")
        return errors

    by_index: dict[int, tuple[dict[str, str], str]] = {}
    for tag, attrs, _body in rails:
        if tag != "rect":
            errors.append("rail: data-role='rail' must be on a rect")
            continue
        step = attrs.get("data-step", "")
        try:
            index = int(attrs.get("data-index", ""))
        except ValueError:
            errors.append(f"rail: step {step!r} has a non-integer data-index")
            continue
        if index in by_index:
            errors.append(f"order: duplicate data-index {index}")
        by_index[index] = (attrs, step)
    expected_indices = list(range(1, len(rails) + 1))
    if sorted(by_index) != expected_indices:
        errors.append(f"order: data-index values must be {expected_indices}, found {sorted(by_index)}")
        return errors

    ordered = [by_index[index] for index in expected_indices]
    step_names = [step for _attrs, step in ordered]
    if any(not step for step in step_names) or len(step_names) != len(set(step_names)):
        errors.append("census: every rail segment needs one unique non-empty data-step")

    first = ordered[0][0]
    base_y, base_w, base_h = number(first, "y"), number(first, "width"), number(first, "height")
    if None in (base_y, base_w, base_h) or base_w <= 0 or base_h <= 0:
        errors.append("rail: x/y/width/height must be finite and positive")
        return errors
    previous_right: float | None = None
    centers: dict[str, float] = {}
    rail_center_y = base_y + base_h / 2
    for attrs, step in ordered:
        x, y, width, height = (number(attrs, key) for key in ("x", "y", "width", "height"))
        if None in (x, y, width, height):
            errors.append(f"rail: step {step!r} is missing finite geometry")
            continue
        if not close(y, base_y) or not close(width, base_w) or not close(height, base_h):
            errors.append(f"equal rail: step {step!r} does not share y, width, and height with its peers")
        if previous_right is not None and not close(x, previous_right):
            errors.append(f"contiguous rail: step {step!r} starts at {x:g}, expected {previous_right:g}")
        previous_right = x + width
        centers[step] = x + width / 2
        if viewbox is not None:
            vx, vy, vw, vh = viewbox
            if x < vx - TOLERANCE or x + width > vx + vw + TOLERANCE or y < vy - TOLERANCE or y + height > vy + vh + TOLERANCE:
                errors.append(f"canvas: rail step {step!r} falls outside the viewBox")

    focal_rails = [attrs.get("data-step", "") for _tag, attrs, _ in rails if attrs.get("data-focal") == "true"]
    if len(focal_rails) != 1:
        errors.append(f"focal: expected exactly one focal rail segment, found {len(focal_rails)}")

    def one_per_step(items: list[tuple[str, dict[str, str], str]], role: str) -> dict[str, tuple[dict[str, str], str]]:
        result: dict[str, tuple[dict[str, str], str]] = {}
        duplicates: list[str] = []
        for _tag, attrs, body in items:
            step = attrs.get("data-step", "")
            if step in result:
                duplicates.append(step)
            else:
                result[step] = (attrs, body)
        missing = sorted(set(step_names) - set(result))
        extra = sorted(set(result) - set(step_names))
        if missing or extra:
            errors.append(f"census: {role} steps differ from rail (missing={missing}, extra={extra})")
        for step in duplicates:
            errors.append(f"census: step {step!r} has more than one {role}")
        return result

    medals = one_per_step(medallions, "medallion")
    labels = one_per_step(numbers, "number")
    radii: list[float] = []
    for step in step_names:
        if step in medals:
            attrs, _ = medals[step]
            cx, cy, radius = number(attrs, "cx"), number(attrs, "cy"), number(attrs, "r")
            if not close(cx, centers.get(step)) or not close(cy, rail_center_y):
                errors.append(f"medallion: step {step!r} is not centered on its rail segment")
            if radius is None or radius <= 0:
                errors.append(f"medallion: step {step!r} has an invalid radius")
            else:
                radii.append(radius)
                if viewbox is not None:
                    vx, vy, vw, vh = viewbox
                    if cx is None or cy is None or cx - radius < vx - TOLERANCE or cx + radius > vx + vw + TOLERANCE or cy - radius < vy - TOLERANCE or cy + radius > vy + vh + TOLERANCE:
                        errors.append(f"canvas: medallion step {step!r} falls outside the viewBox")
        if step in labels:
            attrs, body = labels[step]
            index = step_names.index(step) + 1
            if body != f"{index:02d}":
                errors.append(f"number: step {step!r} prints {body!r}, expected {index:02d}")
            if not close(number(attrs, "x"), centers.get(step)):
                errors.append(f"number: step {step!r} is not centered on its rail segment")
    if radii and any(not close(radius, radii[0]) for radius in radii[1:]):
        errors.append("medallion: every stage must use the same radius")

    focal_medals = [attrs.get("data-step", "") for _tag, attrs, _ in medallions if attrs.get("data-focal") == "true"]
    if focal_rails and focal_medals != focal_rails:
        errors.append(f"focal: rail focal {focal_rails} and medallion focal {focal_medals} disagree")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    paths = sorted(ASSET_DIR.glob("example-steps*.html")) if args.all else args.paths
    if not paths:
        parser.error("pass one or more files, or --all")
    findings = 0
    for path in paths:
        errors = verify(path)
        if errors:
            findings += len(errors)
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK {path}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
