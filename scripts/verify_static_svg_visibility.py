"""Visibility contract for the static traceability and event-modeling examples."""

from __future__ import annotations

import math
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable


# At 10% a house ink is about 1.2:1 against the paper; at 40% it stays near 2:1.
MIN_OPACITY = 0.4
MIN_FONT_SIZE = 8
MAX_STROKE_WIDTH = 4
INK = {
    "#f5f5f5": {"#2d3142", "#4f5d75", "#2e5aa8", "#bf4520"},
    "#2d3142": {"#f5f5f5", "#bfc0c0", "#739fdf", "#f08a59"},
}
RULE_INK = {"#f5f5f5": "#bfc0c0", "#2d3142": "rgba(245,245,245,0.12)"}
VIEW_BOX = "0 0 1200 720"
ROOT_ATTRIBUTES = {"viewBox", "role", "aria-labelledby", "data-diagram-type"}
FONTS_HREF = "https://fonts.googleapis.com/css2?"
# The page skeleton every example shares; anything else around the SVG can hide it.
PAGE_TAGS = {
    "html": {"lang"}, "head": set(), "meta": {"charset", "name", "content"}, "title": set(),
    "link": {"href", "rel"}, "style": set(), "body": set(), "div": {"class"}, "p": {"class"},
    "h1": set(), "section": set(), "h2": set(),
}
PAGE_CLASSES = {"div": {"frame", "canvas", "cards"}, "p": {"eyebrow", "subtitle"}}
SVG_PARENTS = [("html", None), ("body", None), ("div", "frame"), ("div", "canvas")]
STYLE_RE = re.compile(
    r"<!--.*?(?:-->|$)|<style\b[^>]*>(?P<body>.*?)</style\s*>", re.I | re.S
)
CSS_COMMENT_RE = re.compile(r"/\*.*?(?:\*/|$)", re.S)
CSS_ESCAPE_RE = re.compile(r"\\(?:[0-9a-fA-F]{1,6}(?:\r\n|[ \t\r\n\f])?|[^\r\n\f])")
CLASS_SELECTOR_RE = re.compile(rf"\.(?:[\w-]|{CSS_ESCAPE_RE.pattern})+")
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
# The shipped breakpoint only changes the HTML summary cards.
CARDS_MEDIA_RE = re.compile(r"@media\s*\(\s*max-width:\s*720px\s*\)\s*\{\s*(\.cards\s*\{[^{}]*\})\s*\}", re.I)
PAGE_PROPERTIES = {
    "body": {"margin", "background", "color", "font-family", "padding"},
    ".frame": {"max-width", "margin"},
    ".eyebrow": {"color", "font-size", "font-weight", "letter-spacing", "text-transform", "margin"},
    "h1": {"font-family", "font-size", "line-height", "margin"},
    ".subtitle": {"font-size", "line-height", "color", "margin"},
    ".canvas": {"overflow-x"},
    ".cards": {"display", "grid-template-columns", "gap", "margin-top"},
    ".cards section": {"border-top", "padding-top"},
    ".cards h2": {"font-family", "font-size", "margin"},
    ".cards p": {"font-size", "line-height", "color", "margin"},
}
# Page values that size or place the canvas.
PAGE_VALUES = {
    "body": {"margin": "0", "padding": "48px 32px"},
    ".frame": {"max-width": "1200px", "margin": "0 auto"},
    ".canvas": {"overflow-x": "auto"},
    ".cards": {"margin-top": "28px"},
}
SVG_PROPERTIES = {
    "display", "visibility", "opacity", "fill", "fill-opacity", "font-size",
    "stroke", "stroke-width", "stroke-opacity",
}
SVG_ATTRIBUTES = SVG_PROPERTIES | {
    "id", "class", "style", "role", "viewBox", "hidden", "x", "y", "width",
    "height", "rx", "ry", "x1", "y1", "x2", "y2", "d", "font-weight",
    "font-family", "text-anchor", "stroke-linecap", "stroke-linejoin",
}
SVG_TAGS = {"svg", "g", "defs", "title", "desc", "rect", "line", "path", "text", "tspan"}
STATIC_ONLY = {"transform", "translate", "scale", "rotate", "filter", "clip-path", "mask"}
SVG_LAYOUT = {"display": "block", "width": "100%", "min-width": "960px"}


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize(value: str) -> str:
    value = CSS_ESCAPE_RE.sub(decode_css_escape, value).casefold()
    return re.sub(r"\s*!\s*important\s*$", "", value).strip()


def decode_css_escape(match: re.Match[str]) -> str:
    token = match[0][1:]
    if token[0] not in "0123456789abcdefABCDEF":
        return token
    point = int(token.strip(), 16)
    if 0 < point <= 0x10FFFF and not 0xD800 <= point <= 0xDFFF:
        return chr(point)
    return "\ufffd"


def declarations(source: str) -> list[tuple[str, str]]:
    return [
        (CSS_ESCAPE_RE.sub(decode_css_escape, key.strip()).casefold(), normalize(value))
        for part in CSS_COMMENT_RE.sub(" ", source).split(";")
        for key, separator, value in (part.partition(":"),)
        if separator and key.strip()
    ]


class DocumentClasses(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key == "class" and value:
                self.names.update(value.split())


def styles(source: str, svg: ET.Element) -> Iterable[str]:
    document_classes = DocumentClasses()
    document_classes.feed(source)
    svg_classes = {name for node in svg.iter() for name in node.get("class", "").split()}
    for style in STYLE_RE.finditer(source):
        body = style.group("body")
        if body is None:
            continue
        css = CARDS_MEDIA_RE.sub(r"\1", CSS_COMMENT_RE.sub(" ", body))
        if CSS_RULE_RE.sub("", css).strip():
            yield "unsupported stylesheet structure"
        for selector, body in CSS_RULE_RE.findall(css):
            selector = re.sub(r"\s+", " ", selector.strip())
            rules = declarations(body)
            values = dict(rules)
            if selector.replace(" ", "") == "*,*::before,*::after" and rules == [("box-sizing", "border-box")]:
                continue
            if selector == "svg" and len(rules) == len(SVG_LAYOUT) and values == SVG_LAYOUT:
                continue
            if selector in PAGE_PROPERTIES and not (set(re.findall(r"\.([\w-]+)", selector)) & svg_classes):
                pinned = PAGE_VALUES.get(selector, {})
                if (
                    set(values) <= PAGE_PROPERTIES[selector] and values.get("display", "grid") == "grid"
                    and all(values.get(key, value) == value for key, value in pinned.items())
                ):
                    continue
            if CLASS_SELECTOR_RE.fullmatch(selector):
                name = CSS_ESCAPE_RE.sub(decode_css_escape, selector[1:])
                if name not in document_classes.names:
                    continue
            yield f"stylesheet must not select SVG or use an unsupported page rule: {selector!r}"


class PageSkeleton(HTMLParser):
    """Check the HTML around the SVG against the shared page skeleton."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, str | None]] = []
        self.depth = 0
        self.svgs = 0
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]], closed: bool = False) -> None:
        if self.depth:
            self.depth += not closed
            return
        if tag == "svg":
            self.svgs += 1
            if self.stack != SVG_PARENTS:
                self.errors.append("HTML must place the SVG directly in body > div.frame > div.canvas")
            self.depth = int(not closed)
            return
        names = dict(attrs)
        if (
            tag not in PAGE_TAGS or not set(names) <= PAGE_TAGS[tag]
            or "class" in names and names["class"] not in PAGE_CLASSES.get(tag, set())
            or tag == "link" and not (names.get("rel") == "stylesheet" and (names.get("href") or "").startswith(FONTS_HREF))
        ):
            self.errors.append(f"unsupported HTML around the SVG: <{tag} {' '.join(names)}>".replace(" >", ">"))
        if tag not in {"meta", "link"}:
            self.stack.append((tag, names.get("class")))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs, closed=True)

    def handle_endtag(self, tag: str) -> None:
        if self.depth:
            self.depth -= 1
        elif self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            self.errors.append(f"unbalanced HTML around the SVG: </{tag}>")


def page(source: str) -> list[str]:
    skeleton = PageSkeleton()
    skeleton.feed(source)
    skeleton.close()
    errors = skeleton.errors
    if skeleton.svgs != 1 or len(re.findall(r"<svg\b", source, re.I)) != 1:
        errors.append("HTML must contain exactly one rendered SVG")
    if skeleton.stack or skeleton.depth:
        errors.append("unclosed HTML around the SVG")
    return errors


def number(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError:
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def opacity(value: str) -> float:
    return number(value[:-1]) / 100 if value.endswith("%") else number(value)


def properties(node: ET.Element, key: str) -> Iterable[str]:
    if key in node.attrib:
        yield normalize(node.attrib[key])
    for name, value in declarations(node.get("style", "")):
        if name == key:
            yield value


def hidden(node: ET.Element) -> bool:
    return (
        local(node.tag) in {"defs", "title", "desc"}
        or "hidden" in node.attrib
        or normalize(node.get("aria-hidden", "")) == "true"
        or "none" in properties(node, "display")
        or any(value in {"hidden", "collapse"} for value in properties(node, "visibility"))
        or any(not opacity(value) >= MIN_OPACITY for value in properties(node, "opacity"))
    )


def ancestry(node: ET.Element, parents: dict[ET.Element, ET.Element]) -> Iterable[ET.Element]:
    while True:
        yield node
        parent = parents.get(node)
        if parent is None:
            break
        node = parent


def paint_visible(chain: list[ET.Element], channel: str) -> bool:
    if any(hidden(node) for node in chain):
        return False
    combined = math.prod(
        min((1.0, *(opacity(value) for value in properties(node, "opacity"))))
        for node in chain
    )
    return combined >= MIN_OPACITY and all(
        opacity(value) * combined >= MIN_OPACITY
        for node in chain for value in properties(node, f"{channel}-opacity")
    )


def rectangle(node: ET.Element) -> tuple[float, float, float, float]:
    x, y, width, height = (number(node.get(key, "0")) for key in ("x", "y", "width", "height"))
    return x, y, x + width, y + height


def overlaps(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return (
        max(first[0], second[0]) < min(first[2], second[2])
        and max(first[1], second[1]) < min(first[3], second[3])
    )


def drawn_path(source: str, viewport: tuple[float, ...]) -> bool:
    """Recognize the explicit absolute line commands emitted by the examples."""
    fields = source.replace(",", " ").split()
    if len(fields) < 5 or fields[0] != "M" or len(viewport) != 4:
        return False
    x, y = (number(value) for value in fields[1:3])
    points = [(x, y)]
    index = 3
    while index < len(fields):
        command = fields[index]
        index += 1
        if command == "L" and index + 1 < len(fields):
            x, y = (number(value) for value in fields[index:index + 2])
            index += 2
        elif command == "H" and index < len(fields):
            x = number(fields[index])
            index += 1
        elif command == "V" and index < len(fields):
            y = number(fields[index])
            index += 1
        else:
            return False
        points.append((x, y))
    left, top, right, bottom = viewport
    return all(left <= x <= right and top <= y <= bottom for x, y in points) and any(
        first != second for first, second in zip(points, points[1:])
    )


def check_static_svg(
    source: str, svg: ET.Element, parents: dict[ET.Element, ET.Element],
    group_attr: str, cell_attr: str, *, link_attr: str | None = None,
    gap_attr: str | None = None,
) -> list[str]:
    errors = [*styles(source, svg), *page(source)]
    if svg.get("viewBox") != VIEW_BOX or not set(svg.attrib) <= ROOT_ATTRIBUTES:
        errors.append(f"SVG root must keep viewBox={VIEW_BOX!r} and no size, style or visibility attributes")
    paper = next((normalize(child.get("fill", "")) for child in svg if local(child.tag) == "rect"), "")
    inks = INK.get(paper, set())
    rules = inks | {RULE_INK.get(paper, "")}
    if not inks:
        errors.append("SVG background must declare a house paper colour")
    view_box = [number(value) for value in svg.get("viewBox", "").replace(",", " ").split()]
    viewport: tuple[float, ...] = ()
    if len(view_box) == 4 and all(math.isfinite(value) for value in view_box) and min(view_box[2:]) > 0:
        x, y, width, height = view_box
        viewport = (x, y, x + width, y + height)
    else:
        errors.append("SVG must declare a positive finite viewBox")
    boxes: list[tuple[float, ...]] = []
    lines: list[tuple[float, ...]] = []
    for node in svg.iter():
        tag = local(node.tag)
        keys = set(node.attrib) | {name for name, _ in declarations(node.get("style", ""))}
        if tag not in SVG_TAGS or tag == "svg" and node is not svg:
            errors.append(f"unsupported SVG element: {tag}")
        for key in keys:
            if key in STATIC_ONLY or (key not in SVG_ATTRIBUTES and not key.startswith(("data-", "aria-"))):
                errors.append(f"unsupported SVG property on {tag}: {key}")
        for key, _ in declarations(node.get("style", "")):
            if key not in SVG_PROPERTIES:
                errors.append(f"unsupported SVG inline style on {tag}: {key}")
        chain = list(ancestry(node, parents))
        if any(local(parent.tag) in {"defs", "title", "desc"} for parent in chain):
            continue
        if hidden(node):
            errors.append(f"SVG {tag} is hidden or too faint")
        if tag in {"text", "tspan"}:
            fills = list(properties(node, "fill"))
            sizes = list(properties(node, "font-size"))
            if (tag == "text" and not fills) or any(fill not in inks for fill in fills):
                errors.append("SVG labels must use a house ink colour")
            if (tag == "text" and not sizes) or any(not number(size.removesuffix("px")) >= MIN_FONT_SIZE for size in sizes):
                errors.append(f"SVG label font size must be at least {MIN_FONT_SIZE}")
            if not paint_visible(chain, "fill"):
                errors.append("SVG label is hidden or too faint")
            point = {key: number(node.get(key, "0")) for key in ("x", "y") if tag == "text" or key in node.attrib}
            cell = next((parent for parent in chain[1:] if cell_attr in parent.attrib or gap_attr in parent.attrib), None)
            cell_rect = next((child for child in cell if local(child.tag) == "rect"), None) if cell is not None else None
            for bounds, where in ((viewport, "the viewBox"), (cell_rect is not None and rectangle(cell_rect), "its cell")):
                if bounds and not all(
                    bounds[index] <= point[key] <= bounds[index + 2] for index, key in enumerate(("x", "y")) if key in point
                ):
                    errors.append(f"SVG label is outside {where}")
        widths = [number(value) for value in properties(node, "stroke-width")]
        if any(not 0 <= width <= MAX_STROKE_WIDTH for width in widths):
            errors.append(f"SVG {tag} stroke can cover nearby content")
        if tag == "line":
            if not set(properties(node, "stroke")) or not set(properties(node, "stroke")) <= rules:
                errors.append("SVG line must use a house ink or rule colour")
            x1, y1, x2, y2 = (number(node.get(key, "0")) for key in ("x1", "y1", "x2", "y2"))
            outset = max(widths, default=1) / 2
            lines.append((min(x1, x2) - outset, min(y1, y2) - outset, max(x1, x2) + outset, max(y1, y2) + outset))
        if tag == "rect":
            parent = parents.get(node)
            if parent is None:
                errors.append("SVG rectangle must have a parent")
                continue
            siblings = [child for child in parent if local(child.tag) not in {"title", "desc", "defs"}]
            is_backdrop = parent is svg
            is_cell = cell_attr in parent.attrib or (gap_attr is not None and gap_attr in parent.attrib)
            if not siblings or siblings[0] is not node or not (is_backdrop or is_cell):
                errors.append("SVG rectangle can cover earlier content; put paper behind labels")
            if any(value != paper for value in properties(node, "fill")) or not list(properties(node, "fill")):
                errors.append("SVG cell rectangles must use the house paper colour")
            left, top, right, bottom = rectangle(node)
            if not left < right or not top < bottom:
                errors.append("SVG rectangle must have positive finite dimensions")
            elif viewport and not (viewport[0] <= left and viewport[1] <= top and right <= viewport[2] and bottom <= viewport[3]):
                errors.append("SVG rectangle is outside the viewBox")
            elif not is_backdrop:
                outset = max(widths, default=0) / 2
                box = (left - outset, top - outset, right + outset, bottom + outset)
                if any(overlaps(box, earlier) for earlier in boxes):
                    errors.append("SVG cell rectangle overlaps another cell and can cover its content")
                boxes.append(box)
        if tag == "path":
            parent = parents.get(node)
            if parent is None or link_attr is None or link_attr not in parent.attrib:
                errors.append("unsupported SVG path outside a typed arrow")
        if link_attr is not None and link_attr in node.attrib:
            paths = list(node)
            if not paths or any(
                local(path.tag) != "path"
                or not drawn_path(path.get("d", ""), viewport)
                or set(properties(path, "fill")) != {"none"}
                or not set(properties(path, "stroke"))
                or not set(properties(path, "stroke")) <= inks
                or not list(properties(path, "stroke-width"))
                or any(not 0 < number(width) <= MAX_STROKE_WIDTH for width in properties(path, "stroke-width"))
                or not paint_visible([path, *chain], "stroke")
                for path in paths
            ):
                errors.append(f"{node.attrib[link_attr]} must contain a visible arrow")
        if group_attr in node.attrib and tag != "g":
            errors.append(f"{group_attr} must mark a static SVG group")
    if any(overlaps(line, box) for line in lines for box in boxes):
        errors.append("SVG line crosses a cell and can cover its content")
    return errors
