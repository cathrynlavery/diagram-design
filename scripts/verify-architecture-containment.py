#!/usr/bin/env python3
"""Verify the Architecture containment HTML contract using only the stdlib.

Checks unique IDs, resolving parents, no cycles, geometric containment,
innermost-scope parents (only the outermost scope may omit data-parent),
<rect> bounds, admin-band vs traffic-box shapes with supported literal
stroke-dasharray declarations resolved by priority (unresolved computed values
are findings), PaaS placement, endpoint targets, declared peerings, sibling axes
(nested children perpendicular to their parent's), and the 4px grid. Geometry
is read from raw x/y/width/height, so a transform, moving inline CSS, nested
<svg> viewport, matching <style> rule, or geometry animation on a checked
element or its ancestors is a finding. External stylesheets and script are not
evaluated. Files without data-grammar="architecture-containment" are skipped.
This verifies authored declarations, not whether they describe an external
system.

Usage: python3 scripts/verify-architecture-containment.py [--all | FILE ...]
No arguments and --all check every shipped architecture-containment example.
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
GRAMMAR = "architecture-containment"
SCOPE_KINDS = {"admin", "traffic"}
NODE_KINDS = {"compute", "endpoint", "managed"}
ADMIN_RX = 4.0
TRAFFIC_RX = 8.0
GRID = 4.0
EPS = 1e-6
MAX_COORDINATE = 1e7
MAX_ADMIN = 2
MAX_TRAFFIC = 4
MAX_NODES = 8


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    content: list[str | Node] = field(default_factory=list)
    duplicates: set[str] = field(default_factory=set)

    def ancestors(self):
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent


class Scanner(HTMLParser):
    """HTML parsing honors unquoted attrs, entities, comments and raw style text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, 1)
        self.stack = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {}
        duplicates = set()
        for name, value in attrs:
            if name in values:
                duplicates.add(name)
            values.setdefault(name, value or "")
        node = Node(tag, values, self.getpos()[0], self.stack[-1], duplicates=duplicates)
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
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
        self.stack[-1].content.append(data)

    def finish(self, source):
        self.feed(source)
        self.close()
        if any(node.tag == "svg" for node in self.stack):
            self.errors.append("unclosed SVG")


@dataclass
class Box:
    node: Node
    identity: str
    x: float
    y: float
    w: float
    h: float
    rx: float | None
    dashed: bool
    kind: str
    parent_id: str | None
    target: str | None = None

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


def within_box(inner: Box, outer: Box) -> bool:
    return (inner.x + EPS >= outer.x and inner.y + EPS >= outer.y
            and inner.right <= outer.right + EPS and inner.bottom <= outer.bottom + EPS)


def overlaps(a: Box, b: Box) -> bool:
    return (a.x < b.right - EPS and a.right > b.x + EPS
            and a.y < b.bottom - EPS and a.bottom > b.y + EPS)


def identity_ok(raw: str) -> bool:
    return bool(raw) and ID_RE.fullmatch(raw) is not None


def css_without_comments(text: str, *, replacement: str = " ", mask: bool = False) -> str:
    """Remove actual comments without joining tokens or touching strings.

    A width-preserving mask lets the rule scanner find delimiters while keeping
    indices into the original declaration body, where comment boundaries matter.
    """
    output, quote, index = [], "", 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            output.append(text[index:index + 2])
            index += 2
            continue
        if quote:
            output.append(char)
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            output.append(char)
        elif text.startswith("/*", index):
            close = text.find("*/", index + 2)
            end = len(text) if close < 0 else close + 2
            output.append(" " * (end - index) if mask else replacement)
            index = end
            continue
        else:
            output.append(char)
        index += 1
    return "".join(output)


def split_top(text: str, separators: str) -> list[str]:
    """Split on separators outside quotes, brackets and parentheses."""
    parts, depth, quote, start = [], 0, "", 0
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
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
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


DASH_KEYWORDS = {"none", "inherit", "initial", "unset", "revert", "revert-layer"}
DASH_UNITS = {"", "px", "%", "em", "rem", "ex", "ch", "pt", "pc", "mm", "cm", "in", "vw", "vh"}


def dash_declaration_valid(raw: str) -> bool | None:
    """True for supported literals, False for invalid ones, None if unresolved.

    A valid computed value (for example var() or calc()) must not be discarded
    as though it were a syntactically invalid declaration. Keep it in the
    cascade and report that the checker cannot resolve it if it wins.
    """
    value = raw.strip().lower()
    if value in DASH_KEYWORDS:
        return True
    if any(char in value for char in "()\\"):
        return None
    if not value or re.search(r"^,|,$|,\s*,", value):
        return False
    unresolved = False
    for token in re.split(r"[\s,]+", value):
        match = re.fullmatch(f"({NUMBER})([a-z%]*)", token)
        if match is None:
            return False
        amount = float(match.group(1))
        if amount < 0:
            return False
        if not math.isfinite(amount) or match.group(2) not in DASH_UNITS:
            unresolved = True
    return None if unresolved else True


def declarations(text: str) -> dict[str, str]:
    """Resolve declarations by importance, then by their order in the block."""
    result = {}
    important = set()
    for part in split_top(css_without_comments(text), ";"):
        name, colon, value = part.partition(":")
        name = name.strip().lower()
        if colon and name and not name.startswith("--"):
            priority = re.search(r"!\s*important\s*$", value, flags=re.I)
            value = value[:priority.start()].strip() if priority else value.strip()
            # Invalid declarations must not hide a later valid value or erase
            # an earlier one merely because they carry !important.
            if (not value
                    or (name == "stroke-dasharray" and dash_declaration_valid(value) is False)
                    or (name in important and priority is None)):
                continue
            result[name] = value
            if priority:
                important.add(name)
    return result


GROUP_AT_RULES = {"media", "supports", "layer", "container", "scope", "document"}


def css_rules(text: str) -> list[tuple[str, dict[str, str]]]:
    """Return (selector list, declarations) for every style rule, recursing into
    conditional group at-rules and skipping @keyframes, @font-face and the like."""
    original = text
    text = css_without_comments(text, mask=True)
    rules: list[tuple[str, dict[str, str]]] = []
    index, start, quote = 0, 0, ""
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == ";":
            start = index + 1
        elif char == "{":
            depth, close, inner_quote = 1, index + 1, ""
            while close < len(text) and depth:
                inner = text[close]
                if inner == "\\":
                    close += 2
                    continue
                if inner_quote:
                    if inner == inner_quote:
                        inner_quote = ""
                elif inner in "\"'":
                    inner_quote = inner
                elif inner == "{":
                    depth += 1
                elif inner == "}":
                    depth -= 1
                close += 1
            prelude = css_without_comments(original[start:index], replacement="").strip()
            body = original[index + 1:close - 1]
            if prelude.startswith("@"):
                name = prelude[1:].split(None, 1)[0].lower() if len(prelude) > 1 else ""
                if name in GROUP_AT_RULES:
                    rules.extend(css_rules(body))
            elif prelude:
                rules.append((prelude, declarations(body)))
            index = start = close
            continue
        index += 1
    return rules


# Properties that can move or reshape rendered geometry away from the raw
# x/y/width/height attributes this checker reads.
MOVING_PROPERTIES = {"transform", "translate", "rotate", "scale", "offset", "zoom",
                     "x", "y", "width", "height", "rx", "ry", "animation", "animation-name"}
# CSS box positioning does not move SVG graphics today, but it has no place on a
# checked element either, so inline uses are rejected rather than trusted.
BOX_PROPERTIES = {"position", "left", "top", "right", "bottom", "inset", "margin"}
NEUTRAL_VALUES = {"none", "initial", "unset"}
TRANSFORM_FAMILY = {"transform", "translate", "rotate", "scale", "offset-path"}
MOVING_ANIMATION_ATTRS = {"x", "y", "width", "height", "rx", "ry", "transform", "style", "class", "stroke-dasharray"}
MOVES = "moves checked bounds away from their declared x/y/width/height"


def moving_property(name: str, value: str, inline: bool) -> bool:
    if name in TRANSFORM_FAMILY and value.strip().lower() in NEUTRAL_VALUES:
        return False
    if name in MOVING_PROPERTIES or name.startswith("offset-"):
        return True
    return inline and (name in BOX_PROPERTIES or name.startswith(("margin-", "inset-")))


LEGACY_PSEUDO_ELEMENTS = {"before", "after", "first-line", "first-letter"}
ATTRIBUTE_RE = re.compile(r"""\[\s*([\w-]+)\s*(?:([~|^$*]?=)\s*("[^"]*"|'[^']*'|[^\s\]]+)\s*([iIsS])?\s*)?\]\Z""")


def balanced_end(text: str, index: int, opening: str, closing: str) -> int:
    """Index just past the bracket that closes text[index], honouring quotes."""
    depth, quote = 0, ""
    for position in range(index, len(text)):
        char = text[position]
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return position + 1
    return len(text)


def selector_parts(selector: str) -> list[tuple[str, str]] | None:
    """Split one complex selector into (combinator, compound) pairs, left to
    right; the first combinator is empty. None when it cannot be parsed."""
    parts: list[tuple[str, str]] = []
    combinator, current, index = "", "", 0
    text = selector.strip()
    while index < len(text):
        char = text[index]
        if char in "([":
            close = balanced_end(text, index, char, ")" if char == "(" else "]")
            current += text[index:close]
            index = close
            continue
        if char in "\"'":
            return None
        if char.isspace() or char in ">+~":
            if current:
                parts.append((combinator, current))
                current, combinator = "", " "
            if char in ">+~":
                if combinator not in ("", " "):
                    return None
                combinator = char
            index += 1
            continue
        current += char
        index += 1
    if not current:
        return None
    parts.append((combinator, current))
    return parts


def match_attribute(token: str, node: Node) -> bool | None:
    match = ATTRIBUTE_RE.match(token)
    if not match:
        return None
    name, operator, raw, flag = match.groups()
    value = node.attrs.get(name.lower())
    if value is None:
        return False
    if not operator:
        return True
    expected = raw[1:-1] if raw[:1] in "\"'" else raw
    if flag and flag.lower() == "i":
        value, expected = value.lower(), expected.lower()
    if operator == "=":
        return value == expected
    if operator == "~=":
        return expected in value.split()
    if operator == "|=":
        return value == expected or value.startswith(expected + "-")
    if operator == "^=":
        return bool(expected) and value.startswith(expected)
    if operator == "$=":
        return bool(expected) and value.endswith(expected)
    return bool(expected) and expected in value


def match_compound(compound: str, node: Node, parent_of) -> bool | None:
    """True or False when every part can be evaluated; None (may match) when a
    part such as :not() or :hover cannot. Any definite failure wins."""
    if "\\" in compound or "|" in compound.split("[")[0]:
        return None
    results: list[bool | None] = []
    index = 0
    head = re.match(r"\*|[A-Za-z][\w-]*", compound)
    if head:
        results.append(head.group(0) == "*" or head.group(0).lower() == node.tag)
        index = head.end()
    while index < len(compound):
        char = compound[index]
        if char in ".#":
            name = re.match(r"[\w-]+", compound[index + 1:])
            if not name:
                return None if False not in results else False
            value = name.group(0)
            if char == ".":
                results.append(value in node.attrs.get("class", "").split())
            else:
                results.append(node.attrs.get("id") == value)
            index += 1 + len(value)
        elif char == "[":
            close = balanced_end(compound, index, "[", "]")
            results.append(match_attribute(compound[index:close], node))
            index = close
        elif char == ":":
            element = compound.startswith("::", index)
            name = re.match(r"[\w-]+", compound[index + (2 if element else 1):])
            if not name:
                return None if False not in results else False
            label = name.group(0).lower()
            index += (2 if element else 1) + len(name.group(0))
            if index < len(compound) and compound[index] == "(":
                index = balanced_end(compound, index, "(", ")")
            if element or label in LEGACY_PSEUDO_ELEMENTS:
                results.append(False)  # pseudo-elements never box SVG graphics
            elif label == "root":
                results.append(node.tag == "html" and parent_of(node) is None)
            else:
                results.append(None)
        else:
            return None if False not in results else False
    if False in results:
        return False
    return True if all(result is True for result in results) else None


def selector_may_match(parts: list[tuple[str, str]], index: int, node: Node | None, element: Node,
                       parent_of) -> bool:
    """Right-to-left match of parts[:index + 1] ending at node. node is None for
    a sibling we do not evaluate; element then supplies the shared parent."""
    if node is not None and match_compound(parts[index][1], node, parent_of) is False:
        return False
    if index == 0:
        return True
    combinator = parts[index][0]
    anchor = node if node is not None else element
    if combinator in "+~":
        # Sibling selectors are honoured conservatively: the sibling compound
        # is assumed to match and the rest is checked against the shared parent.
        return selector_may_match(parts, index - 1, None, anchor, parent_of)
    candidates: list[Node] = []
    current = parent_of(anchor)
    while current is not None:
        candidates.append(current)
        if combinator == ">" and in_svg(current):
            break
        current = parent_of(current)
    return any(selector_may_match(parts, index - 1, candidate, candidate, parent_of) for candidate in candidates)


HEAD_TAGS = {"head", "title", "meta", "link", "style", "script", "base", "noscript", "template"}


def ancestry(scanner: Scanner):
    """Parent lookup that adds the <html> and <body> a browser implies when a
    valid page omits those optional tags, so :root, html and body selectors
    resolve the way they do in the rendered page."""
    real_html = next((node for node in scanner.nodes if node.tag == "html"), None)
    has_body = any(node.tag == "body" for node in scanner.nodes)
    implied_html = None if real_html else Node("html", {}, 0)
    implied_body = None if has_body else Node("body", {}, 0)
    html = real_html or implied_html

    def parent_of(node: Node) -> Node | None:
        if node is html:
            return None
        if node is implied_body:
            return html
        parent = node.parent
        if parent is None:
            return None
        if parent.tag == "document":
            parent = html
        if parent is html and implied_body is not None and node.tag not in HEAD_TAGS | {"body"}:
            return implied_body
        return parent

    return parent_of


def in_svg(node: Node) -> bool:
    """SVG nesting is checked for malformation, so a parent inside the SVG is
    exact. HTML around it may rely on implied end tags, so a child combinator
    that reaches outside the SVG is treated as a descendant combinator."""
    return node.tag == "svg" or any(item.tag == "svg" for item in node.ancestors())


def rule_may_match(selector: str, node: Node, parent_of) -> bool:
    parts = selector_parts(selector)
    if parts is None:
        return True
    return selector_may_match(parts, len(parts) - 1, node, node, parent_of)


def dash_value(raw: str) -> bool | None:
    """True dashed, False solid, None when unspecified, inherited or invalid."""
    value = raw.strip().lower()
    if value in ("", "inherit", "unset", "revert", "revert-layer"):
        return None
    if value in ("none", "initial"):
        return False
    lengths = []
    for token in re.split(r"[\s,]+", value):
        match = re.fullmatch(f"({NUMBER})(px|%|em|rem|ex|ch|pt|pc|mm|cm|in|vw|vh)?", token)
        if not match or float(match.group(1)) < 0:
            return None
        lengths.append(float(match.group(1)))
    return any(length > 0 for length in lengths)


def is_dashed(node: Node, root: Node) -> bool:
    """Resolve stroke-dasharray as rendered: inline style beats the attribute,
    and the property inherits from ancestors up to the diagram SVG."""
    current: Node | None = node
    while current is not None:
        inline = declarations(current.attrs.get("style", "")).get("stroke-dasharray")
        keyword = inline.strip().lower() if inline is not None else ""
        if keyword in {"inherit", "unset", "revert"}:
            # These inherit the parent's computed value rather than resurrect
            # this element's lower-priority presentation attribute.
            values = ()
        elif keyword == "revert-layer":
            # Matching stylesheet rules are refused below, so reverting the
            # inline layer exposes the presentation attribute or inheritance.
            values = (current.attrs.get("stroke-dasharray"),)
        else:
            values = (inline, current.attrs.get("stroke-dasharray"))
        for raw in values:
            if raw is not None:
                if dash_declaration_valid(raw) is None:
                    raise ValueError(f"unsupported stroke-dasharray value: {raw!r}")
                resolved = dash_value(raw)
                if resolved is not None:
                    return resolved
        if current is root:
            break
        current = current.parent
    return False


def parse_box(node: Node, identity: str, kind: str, parent_id: str | None, target: str | None = None,
              root: Node | None = None) -> Box:
    attrs = node.attrs
    x = number(attrs.get("x", ""))
    y = number(attrs.get("y", ""))
    w = number(attrs.get("width", ""))
    h = number(attrs.get("height", ""))
    rx_raw = attrs.get("rx")
    rx = number(rx_raw) if rx_raw not in (None, "") else None
    dashed = is_dashed(node, root if root is not None else node)
    if w <= 0 or h <= 0:
        raise ValueError("bounds width and height must be positive")
    return Box(node, identity, x, y, w, h, rx, dashed, kind, parent_id, target)


def looks_like_containment(source: str) -> bool:
    scanner = Scanner()
    scanner.finish(source)
    return any(node.tag == "svg" and node.attrs.get("data-grammar") == GRAMMAR
               for node in scanner.nodes)


def check_source(path: Path, source: str) -> list[str]:
    scanner = Scanner()
    scanner.finish(source)
    findings: list[str] = []
    roots = [node for node in scanner.nodes
             if node.tag == "svg" and node.attrs.get("data-grammar") == GRAMMAR]
    if not roots:
        return []

    def fail(node: Node, message: str) -> None:
        findings.append(f"{path.name}:{node.line}: {message}")

    if len(roots) != 1:
        fail(roots[0], 'require exactly one svg data-grammar="architecture-containment"')
        return findings
    root = roots[0]
    findings.extend(f"{path.name}: {error}" for error in scanner.errors)
    for node in scanner.nodes:
        if node is root or root in node.ancestors():
            if node.duplicates:
                fail(node, f"duplicate attributes: {', '.join(sorted(node.duplicates))}")

    scopes: dict[str, Box] = {}
    nodes: dict[str, Box] = {}
    ids: dict[str, Node] = {}
    checked: list[Node] = []

    def register(identity: str, carrier: Node) -> bool:
        if not identity_ok(identity):
            fail(carrier, "identity must be a single XML Name starting with a letter")
            return False
        if identity in ids:
            fail(carrier, f'duplicate ID "{identity}"')
            return False
        ids[identity] = carrier
        return True

    for node in scanner.nodes:
        if root not in node.ancestors() and node is not root:
            continue
        attrs = node.attrs
        if "data-scope-id" in attrs:
            identity = attrs.get("data-scope-id", "")
            kind = attrs.get("data-scope-kind", "")
            if "data-parent" in attrs:
                parent_id = attrs.get("data-parent", "")
                if not identity_ok(parent_id):
                    fail(node, "data-parent must name the enclosing scope")
                    parent_id = parent_id or None
            else:
                parent_id = None
            if attrs.get("data-role") != "bounds":
                fail(node, "scope bounds must declare data-role=\"bounds\"")
            if kind not in SCOPE_KINDS:
                fail(node, "data-scope-kind must be admin or traffic")
            if not register(identity, node):
                continue
            checked.append(node)
            if node.tag != "rect":
                fail(node, f"scope bounds must be a <rect>, not <{node.tag}>")
                continue
            try:
                box = parse_box(node, identity, kind, parent_id, root=root)
            except ValueError as error:
                fail(node, str(error))
                continue
            if kind == "admin":
                if box.rx is None or abs(box.rx - ADMIN_RX) > EPS:
                    fail(node, "admin band must use rx=4")
                if not box.dashed:
                    fail(node, "admin band must use a dashed stroke")
                if box.w + EPS < box.h:
                    fail(node, "admin band must be a horizontal rectangle")
            elif kind == "traffic":
                if box.rx is None or abs(box.rx - TRAFFIC_RX) > EPS:
                    fail(node, "traffic box must use rx=8")
                if box.dashed:
                    fail(node, "traffic box must use a solid stroke")
            for value in (box.x, box.y, box.w, box.h):
                if not on_grid(value):
                    fail(node, "scope bounds must sit on the 4px grid")
                    break
            scopes[identity] = box
        elif "data-node-id" in attrs:
            identity = attrs.get("data-node-id", "")
            kind = attrs.get("data-kind", "")
            parent_id = attrs.get("data-parent", "")
            target = attrs.get("data-target")
            target = target if target not in (None, "") else None
            if kind not in NODE_KINDS:
                fail(node, "data-kind must be compute, endpoint, or managed")
            if not identity_ok(parent_id):
                fail(node, "data-parent must name the enclosing scope")
            if not register(identity, node):
                continue
            checked.append(node)
            bounds = [child for child in node.children if child.attrs.get("data-role") == "bounds"]
            if len(bounds) != 1:
                fail(node, "node must expose exactly one data-role=\"bounds\" rect")
                continue
            checked.append(bounds[0])
            if bounds[0].tag != "rect":
                fail(bounds[0], f"node bounds must be a <rect>, not <{bounds[0].tag}>")
                continue
            try:
                box = parse_box(bounds[0], identity, kind, parent_id, target, root=root)
            except ValueError as error:
                fail(bounds[0], str(error))
                continue
            box.node = node
            for value in (box.x, box.y, box.w, box.h):
                if not on_grid(value):
                    fail(bounds[0], "node bounds must sit on the 4px grid")
                    break
            if kind == "endpoint":
                if not identity_ok(target or ""):
                    fail(node, "endpoint must declare data-target naming a managed node")
            elif target is not None:
                fail(node, "only an endpoint may declare data-target")
            nodes[identity] = box

    if not any(box.kind == "admin" for box in scopes.values()):
        fail(root, "containment requires at least one admin band")
    if not any(box.kind == "traffic" for box in scopes.values()):
        fail(root, "containment requires at least one traffic box")
    admin_count = sum(1 for box in scopes.values() if box.kind == "admin")
    traffic_count = sum(1 for box in scopes.values() if box.kind == "traffic")
    if admin_count > MAX_ADMIN:
        fail(root, "admin budget is 2 bands")
    if traffic_count > MAX_TRAFFIC:
        fail(root, "traffic budget is 4 scopes")
    if len(nodes) > MAX_NODES:
        fail(root, "node budget is 8")

    known_scopes = set(scopes)

    def innermost_parent(box: Box, label: str) -> None:
        """Only an unenclosed (outermost) box may omit data-parent, and a declared
        parent that encloses the box must be the innermost scope that does."""
        enclosing = [scope for scope in scopes.values() if scope is not box and within_box(box, scope)]
        if not enclosing:
            return
        smallest = min(scope.w * scope.h for scope in enclosing)
        innermost = sorted(scope.identity for scope in enclosing if scope.w * scope.h <= smallest + EPS)
        if box.parent_id is None:
            fail(box.node, f'data-parent is required: {label} "{box.identity}" sits inside scope "{innermost[0]}"')
        elif box.parent_id in scopes and within_box(box, scopes[box.parent_id]) and box.parent_id not in innermost:
            fail(box.node, f'data-parent "{box.parent_id}" is not the innermost enclosing scope of '
                           f'{label} "{box.identity}"; use "{innermost[0]}"')

    for box in scopes.values():
        innermost_parent(box, "scope")
        if box.parent_id is None:
            continue
        if not identity_ok(box.parent_id) or box.parent_id not in known_scopes:
            fail(box.node, f'data-parent "{box.parent_id}" does not match any data-scope-id')
            continue
        parent = scopes[box.parent_id]
        if not within_box(box, parent):
            fail(box.node, f'scope "{box.identity}" is not geometrically inside parent "{box.parent_id}"')

    parent_of = {box.identity: box.parent_id for box in scopes.values()}
    reported: set[str] = set()
    for identity in scopes:
        if identity in reported:
            continue
        chain: list[str] = []
        current: str | None = identity
        while current is not None:
            if current in chain:
                cycle = chain[chain.index(current):] + [current]
                reported.update(cycle)
                fail(scopes[identity].node, f'parent cycle: {" -> ".join(cycle)}')
                break
            chain.append(current)
            if current not in known_scopes:
                break
            current = parent_of.get(current)

    traffic = {identity: box for identity, box in scopes.items() if box.kind == "traffic"}
    managed = {identity: box for identity, box in nodes.items() if box.kind == "managed"}

    for box in nodes.values():
        if box.parent_id not in known_scopes:
            fail(box.node, f'data-parent "{box.parent_id}" does not match any data-scope-id')
            continue
        parent = scopes[box.parent_id]
        if not within_box(box, parent):
            fail(box.node, f'node "{box.identity}" is not geometrically inside parent "{box.parent_id}"')
        innermost_parent(box, "node")
        if box.kind == "managed":
            if parent.kind != "admin":
                fail(box.node, "managed node must parent to an admin band")
            for traffic_id, traffic_box in traffic.items():
                if overlaps(box, traffic_box) or within_box(box, traffic_box):
                    fail(box.node, f'managed node "{box.identity}" must not sit inside traffic scope "{traffic_id}"')
                    break
        elif box.kind in {"compute", "endpoint"}:
            if parent.kind != "traffic":
                fail(box.node, f'{box.kind} node must parent to a traffic box')
            if not within_box(box, parent):
                fail(box.node, f'{box.kind} node "{box.identity}" must sit inside its traffic parent')
        if box.kind == "endpoint":
            if box.target not in managed:
                fail(box.node, f'data-target "{box.target}" must name a managed node')

    siblings: dict[str | None, list[Box]] = {}
    for box in scopes.values():
        if box.kind != "traffic":
            continue
        siblings.setdefault(box.parent_id, []).append(box)

    def row_axis(parent_id: str, seen: frozenset[str] = frozenset()) -> bool:
        """True when children of parent_id form a row. The first traffic level
        follows its parent's aspect; nested children take the perpendicular axis."""
        parent = scopes[parent_id]
        grandparent = parent.parent_id
        if parent.kind == "traffic" and grandparent in scopes and grandparent not in seen:
            return not row_axis(grandparent, seen | {parent_id})
        return parent.w + EPS >= parent.h

    for parent_id, group in siblings.items():
        if len(group) < 2 or parent_id not in scopes:
            continue
        row = row_axis(parent_id)
        origins = {round(item.y, 6) for item in group} if row else {round(item.x, 6) for item in group}
        if len(origins) > 1:
            if scopes[parent_id].kind == "traffic":
                axis = "a row sharing one y" if row else "a column sharing one x"
                fail(group[0].node, f'nested sibling traffic scopes in "{parent_id}" must take the axis '
                                    f'perpendicular to their parent\'s: {axis}')
            else:
                fail(group[0].node, "sibling traffic scopes must share one axis")
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                if overlaps(left, right):
                    fail(left.node, f'sibling traffic scopes "{left.identity}" and "{right.identity}" overlap')

    for node in scanner.nodes:
        if root not in node.ancestors() and node is not root:
            continue
        if "data-peering" not in node.attrs:
            continue
        peering = node.attrs.get("data-peering", "")
        source = node.attrs.get("data-from", "")
        target = node.attrs.get("data-to", "")
        if not identity_ok(peering):
            fail(node, "data-peering must be a single XML Name starting with a letter")
        if source not in traffic or target not in traffic:
            fail(node, "peering data-from and data-to must name traffic scopes")
        elif source == target:
            fail(node, "peering must join two distinct traffic scopes")

    check_moved_geometry(scanner, root, checked, fail)
    return findings


def check_moved_geometry(scanner: Scanner, root: Node, checked: list[Node], fail) -> None:
    """Containment is read from raw x/y/width/height, so nothing may move a
    checked element or any ancestor inside the diagram SVG: no transform
    attribute, no moving inline CSS, no nested viewport, no matching
    stylesheet rule, and no geometry animation."""
    affected: list[Node] = []
    seen: set[int] = set()
    for node in checked:
        for item in (node, *node.ancestors()):
            if item is root:
                break
            if id(item) not in seen:
                seen.add(id(item))
                affected.append(item)
    for node in affected:
        if "transform" in node.attrs:
            fail(node, f'transform attribute on <{node.tag}> {MOVES}')
        for name, value in declarations(node.attrs.get("style", "")).items():
            if moving_property(name, value, inline=True):
                fail(node, f'inline style "{name}" on <{node.tag}> {MOVES}')
        if node.tag == "svg":
            fail(node, f"nested <svg> viewport {MOVES}")

    parent_of = ancestry(scanner)
    for style in (node for node in scanner.nodes if node.tag == "style"):
        text = "".join(part for part in style.content if isinstance(part, str))
        for selector_list, decls in css_rules(text):
            moving = sorted(name for name, value in decls.items()
                            if name == "stroke-dasharray" or moving_property(name, value, inline=False))
            if not moving:
                continue
            for selector in split_top(selector_list, ","):
                if selector.strip() and any(rule_may_match(selector, node, parent_of) for node in affected):
                    effect = ("overrides the checked stroke-dasharray" if moving == ["stroke-dasharray"]
                              else MOVES)
                    fail(style, f'<style> rule "{selector.strip()}" sets {", ".join(moving)} on a checked '
                                f'element and {effect}')
                    break

    by_id = {node.attrs["id"]: node for node in scanner.nodes if node.attrs.get("id")}
    for node in scanner.nodes:
        if node.tag not in {"animate", "animatetransform", "animatemotion", "set"}:
            continue
        if root not in node.ancestors():
            continue
        href = node.attrs.get("href") or node.attrs.get("xlink:href") or ""
        target = by_id.get(href[1:]) if href.startswith("#") else node.parent
        if target is None or id(target) not in seen:
            continue
        attribute = node.attrs.get("attributename", "").strip().lower()
        if node.tag in {"animatetransform", "animatemotion"} or attribute in MOVING_ANIMATION_ATTRS:
            fail(node, f"<{node.tag}> on a checked element {MOVES}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped architecture containment example")
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
        if not looks_like_containment(source):
            continue
        checked += 1
        findings.extend(check_source(path, source))
    if not checked:
        print("error: no architecture containment diagrams found", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} architecture containment finding(s) across {checked} file(s).")
        return 1
    print(f"OK architecture containment: {checked} file(s); IDs, parents, geometry, PaaS placement and peerings agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
