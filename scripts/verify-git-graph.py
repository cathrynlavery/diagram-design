#!/usr/bin/env python3
"""Verify that a git graph's commits sit on lanes and a time grid.

A git graph makes one hard claim: time reads left to right on a shared column
grid, each branch is a horizontal lane, and a merge is a commit with exactly
two parents from earlier columns on different lanes. Timeline and swimlane
can fake the picture; they cannot keep those parent edges honest.

`lint-skin.py` reads colors and fonts and `verify-geometry.py` reads label
masks; neither compares a commit dot to its lane or a merge to its parents.

Invariants:

1. LANE Y - every commit sits on its lane rail's y.
2. COLUMN GRID - every commit sits on a shared pitch so column i is origin +
   i × pitch. Empty columns are allowed: the pitch is Δx / Δcolumn, not the
   gap between occupied x values.
3. MERGE PARENTS - every data-kind=merge commit has exactly two incoming
   connectors whose sources are earlier columns on different lanes.
4. NO RIGHT-TO-LEFT - a connector's path never decreases in x, and its
   source column is strictly earlier than its target.
5. CONNECTOR TURNS - a branch leaves the parent at the parent's column
   (vertical first, then horizontal on the child lane). A merge runs on
   the source lane and turns at the merge column (horizontal then
   vertical). Every segment of that elbow is checked. A second moveto or
   an unsupported command is not a connection. No segment is collinear
   with a lane it is not drawing, and two connectors may meet at a commit
   but must not share a run.
6. TAGS - every tag label names an existing commit and sits above it.
7. AT MOST TWO CORAL COMMITS - fill is a literal accent on ≤2 dots, read
   from the fill attribute, an inline style, or the nearest ancestor.
8. LANES DO NOT OVERLAP - consecutive lane y values clear two radii plus a
   gap. Two commits must not share a lane and a column. Every lane rail
   sits inside the root viewBox height with room for a commit radius.
9. UNPOSITIONED GEOMETRY - raw attributes only; a transform, a moving CSS
   rule, or a hidden bound mark is a finding. A <style> rule that hides a
   bound mark or its parent still counts as hiding it.
   A connector whose resolved stroke is none or transparent, or whose
   stroke-width is zero (inline style, attribute or ancestor), is hidden.
   A commit dot whose resolved fill is none or transparent with no visible
   stroke (unset, none/transparent, or zero stroke-width) is hidden.
10. FAIL CLOSED - a file that presents as a git graph but yields fewer than
   four commits, two lanes, or one merge is a finding.

Vocabulary treaty: `data-commit` ON A <circle> is the git-graph contract.
`data-span` is arc-diagram, `data-q1` is box plot, `data-value` is beeswarm,
`data-size` is bubble, `data-series` is slopegraph, `data-ranks` is bump.

Usage:
    python3 scripts/verify-git-graph.py --all
    python3 scripts/verify-git-graph.py skills/diagram-design/assets/example-git-graph.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

from css_property_scan import escaped_property_findings

import argparse
import html
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>",
                     re.IGNORECASE | re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
CONTAINER_TAGS = r"g|svg|defs|symbol|marker|mask|clipPath|pattern"
GROUP_OPEN_RE = re.compile(
    r"<(?P<tag>%s)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>" % CONTAINER_TAGS,
    re.IGNORECASE,
)
GROUP_CLOSE_RE = re.compile(r"</(?:%s)\s*>" % CONTAINER_TAGS, re.IGNORECASE)
NON_RENDERED = {"defs", "symbol", "marker", "mask", "clippath", "pattern"}
VIEWPORT_ATTRS = ("x", "y", "viewbox")
CSS_HIDES_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:"
    r"(?P<display>display)\s*:\s*none"
    r"|(?P<visibility>visibility)\s*:\s*(?:hidden|collapse)"
    r"|(?P<opacity>(?:fill-|stroke-)?opacity)\s*:\s*(?P<amount>[^;}]*)"
    r")",
    re.IGNORECASE,
)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)(?:</style\s*>|\Z)",
                      re.IGNORECASE | re.DOTALL)
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|cx|cy|r|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_COMMIT_RE = re.compile(r"\bdata-commit\s*=", re.IGNORECASE)
DECLARES_CONNECTOR_RE = re.compile(r"\bdata-(?:from|to)\s*=", re.IGNORECASE)
HEX_RE = re.compile(r"#([0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", re.IGNORECASE)
RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*[,\s]\s*([\d.]+)\s*[,\s]\s*([\d.]+)", re.IGNORECASE)
DEFAULT_ACCENTS = {(191, 69, 32), (240, 138, 89)}
COLOR_ACCENT_RE = re.compile(r"--color-accent\s*:\s*(?P<value>[^;}]+)", re.IGNORECASE)
RGBA_ZERO_RE = re.compile(
    r"^(?:rgb|hsl)a?\(\s*[^,/\s()]+(?:\s*,\s*|\s+)[^,/\s()]+(?:\s*,\s*|\s+)"
    r"[^,/\s()]+\s*[,/]\s*(?:0*\.?0+%?)\s*\)$|^#(?:[0-9a-f]{3}0|[0-9a-f]{6}00)$",
    re.IGNORECASE,
)
CSS_PAINT_RE = re.compile(r"(?:^|[{};\s])(?P<prop>stroke|fill)\s*:", re.IGNORECASE)
CSS_ALL_RE = re.compile(r"(?:^|[{};\s])all\s*:", re.IGNORECASE)
KEYFRAMES_RE = re.compile(r"@(?:-[a-z]+-)?keyframes\b", re.IGNORECASE)
OPEN_TAG_RE = re.compile(
    r"<(?P<close>/?)(?P<tag>[A-Za-z][\w:-]*)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>"
)
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
             "meta", "source", "track", "wbr"}
TOKEN_RE = re.compile(
    r"[MmLlHhVvZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
)
PATH_LEFTOVER_RE = re.compile(r"[^\s,]")
COORD_TOLERANCE = 1.0
PITCH_TOLERANCE = 1.0
LANE_GAP = 96
MIN_COMMITS, MAX_COMMITS = 4, 16
MIN_LANES, MAX_LANES = 2, 5
MAX_CORAL = 2


class Commit:
    __slots__ = ("name", "lane", "column", "cx", "cy", "r", "merge", "accent", "offset")

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class Connector:
    __slots__ = ("frm", "to", "points", "offset")

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class Lane:
    __slots__ = ("name", "y", "offset")

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


STYLE_OR_COMMENT_RE = re.compile(
    r"<style\b[^>]*>.*?(?:</style\s*>|\Z)|<!--(?:-?>|.*?--!?>)", re.IGNORECASE | re.DOTALL)


def blank_comments(source: str) -> str:
    return STYLE_OR_COMMENT_RE.sub(
        lambda m: m.group(0) if m.group(0)[:6].lower() == "<style"
        else re.sub(r"[^\n]", " ", m.group(0)), source)


def attrs_of(raw: str) -> dict:
    found = {}
    for match in ATTR_RE.finditer(raw):
        name = match.group("name").lower()
        if name not in found:
            found[name] = html.unescape(match.group("value"))
    return found


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value):
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def named_text(source: str) -> str:
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_git_graph(path: Path, source: str) -> bool:
    """Does this file present itself as a git graph?

    Filename, accessible name, or a <circle> that binds data-commit.
    """
    if path.name.startswith("example-git-graph"):
        return True
    if DECLARES_COMMIT_RE.search(source):
        for match in CIRCLE_RE.finditer(source):
            if DECLARES_COMMIT_RE.search(match.group("attrs")):
                return True
    text = named_text(source)
    compact = text.replace("-", " ")
    return "git graph" in text or "gitgraph" in compact


def rgb_of(value: str):
    text = value.split("!")[0].strip()
    found = HEX_RE.fullmatch(text)
    if found:
        digits = found.group(1)
        if len(digits) in (3, 4):
            digits = "".join(char * 2 for char in digits[:3])
        return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
    found = RGB_RE.match(text)
    if found:
        return tuple(round(float(part)) for part in found.groups())
    return None


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
            return text
        if found.group("bad") is not None:
            return text.replace("/*", "  ").replace("*/", "  ")
        if text[0] not in "\"'":
            return text[:4] + re.sub(r"[^\w\n-]", "_", text[4:-1]) + ")"
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
    """CSS with every comment the browser sees turned to spaces, newlines kept, same length."""
    return CSS_STRING_RE.sub(
        lambda found: re.sub(r"[^\n]", " ", found.group()) if found.group().startswith("/*") else found.group(),
        css,
    )


def transform_carrier(attrs: dict):
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(blank_css_strings(style))
        if found is not None:
            return "style=%r (the %s property)" % (
                style, found.group("prop").lower()
            )
    return None


def invisible_amount(value) -> bool:
    text = str(value).split("!")[0].strip().lower()
    scale = 1.0
    if text.endswith("%"):
        text, scale = text[:-1], 0.01
    try:
        amount = float(text) * scale
    except ValueError:
        return False
    return math.isfinite(amount) and amount <= 0


def hidden_carrier(attrs: dict):
    if attrs.get("display", "").strip().lower() == "none":
        return "display=%r" % attrs["display"]
    if attrs.get("visibility", "").strip().lower() in ("hidden", "collapse"):
        return "visibility=%r" % attrs["visibility"]
    for key in ("opacity", "fill-opacity", "stroke-opacity"):
        if key in attrs and invisible_amount(attrs[key]):
            return "%s=%r" % (key, attrs[key])
    style = attrs.get("style")
    if style is not None:
        cleaned = blank_comments_outside_strings(blank_css_strings(style))
        for found in CSS_HIDES_RE.finditer(cleaned):
            if found.group("opacity") and not invisible_amount(found.group("amount")):
                continue
            prop = found.group("display") or found.group("visibility") \
                or found.group("opacity")
            return "style=%r (the %s property)" % (style, prop.lower())
    return None


def is_bound(match) -> bool:
    raw = match.group("attrs")
    if match.re is PATH_RE:
        return DECLARES_CONNECTOR_RE.search(raw) is not None
    if match.re is CIRCLE_RE:
        return DECLARES_COMMIT_RE.search(raw) is not None
    attrs = attrs_of(raw)
    return "data-lane" in attrs or "data-tag" in attrs or "data-commit" in attrs


def declared_paint(attrs: dict, prop: str):
    """Value the element states itself: inline style outranks the presentation attribute."""
    style = attrs.get("style")
    if style is not None:
        found, important = None, False
        pattern = re.compile(
            r"(?:^|[{;}\n])\s*%s\s*:\s*(?P<value>[^;}]+)" % re.escape(prop),
            re.IGNORECASE,
        )
        cleaned = blank_comments_outside_strings(blank_css_strings(style))
        for match in pattern.finditer(cleaned):
            raw_value = match.group("value")
            is_important = re.search(r"!\s*important\s*$", raw_value, re.IGNORECASE) is not None
            if important and not is_important:
                continue
            found, important = raw_value.split("!")[0].strip(), is_important
        if found is not None:
            return found
    if prop in attrs:
        return attrs[prop]
    return None


def declared_fill(attrs: dict):
    return declared_paint(attrs, "fill")


def paint_spans(source: str, prop: str) -> list:
    """(start, end, value) for each container that a descendant would inherit prop from."""
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        events.append((match.start(), 0, attrs_of(match.group("attrs"))))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))
    stack, spans = [], []
    for position, kind, attrs in events:
        if kind == 0:
            current = declared_paint(attrs, prop)
            if current is None:
                current = stack[-1][1] if stack else None
            stack.append((position, current))
        elif stack:
            start, value = stack.pop()
            if value is not None:
                spans.append((start, position, value))
    for start, value in stack:
        if value is not None:
            spans.append((start, len(source), value))
    return spans


def fill_spans(source: str) -> list:
    return paint_spans(source, "fill")


def inherited_paint(spans: list, offset: int):
    """Value from the nearest enclosing container: the one that opens last before offset."""
    nearest = None
    for start, end, value in spans:
        if start < offset < end and (nearest is None or start > nearest[0]):
            nearest = (start, value)
    return nearest[1] if nearest else None


def inherited_fill(spans: list, offset: int):
    return inherited_paint(spans, offset)


def tokens_of(attrs: dict) -> set:
    tokens = {"attr:" + key.lower() for key in attrs}
    tokens |= {"class:" + name for name in attrs.get("class", "").split()}
    if attrs.get("id"):
        tokens.add("id:" + attrs["id"].strip())
    return tokens


def is_checked_mark(tag: str, raw_attrs: str) -> bool:
    attrs = attrs_of(raw_attrs)
    if tag == "circle":
        return "data-commit" in attrs
    if tag == "path":
        return "data-from" in attrs or "data-to" in attrs
    if tag == "line":
        return "data-lane" in attrs
    if tag == "text":
        return "data-lane" in attrs or "data-tag" in attrs or "data-commit" in attrs
    return False


def figure_elements(source: str) -> set:
    """(tag, tokens) for each <svg> holding a checked mark, everything inside it and everything around it."""
    found, stack, capture = set(), [], None
    for tag in OPEN_TAG_RE.finditer(source):
        name = tag.group("tag").lower()
        if tag.group("close"):
            if any(open_name == name for open_name, _tokens in stack):
                while stack.pop()[0] != name:
                    pass
            if capture is not None and len(stack) <= capture["depth"]:
                if capture["marked"]:
                    found.update(capture["elements"] + capture["around"])
                capture = None
            continue
        entry = (name, frozenset(tokens_of(attrs_of(tag.group("attrs")))))
        if capture is None and name == "svg":
            capture = {"depth": len(stack), "around": list(stack), "elements": [], "marked": False}
        if capture is not None:
            capture["elements"].append(entry)
            capture["marked"] |= is_checked_mark(name, tag.group("attrs"))
        if not tag.group("selfclose") and name not in VOID_TAGS:
            stack.append(entry)
    if capture is not None and capture["marked"]:
        found.update(capture["elements"] + capture["around"])
    return found


def css_hides(declarations: str) -> bool:
    for found in CSS_HIDES_RE.finditer(declarations):
        if found.group("opacity") and not invisible_amount(found.group("amount")):
            continue
        return True
    return False


def css_blocks(css: str) -> list:
    """(selector, its own declarations, inside @keyframes) for every block, nested ones included."""
    blocks, stack, text = [], [], ""
    for char in css:
        if char == "{":
            own, _sep, selector = text.rpartition(";")
            if stack:
                stack[-1][1].append(own)
            inside = bool(stack) and (stack[-1][2] or KEYFRAMES_RE.match(stack[-1][0]) is not None)
            stack.append([selector.strip(), [], inside])
            text = ""
        elif char == "}":
            if stack:
                selector, own, inside = stack.pop()
                blocks.append((selector, ";".join(own + [text]), inside))
            text = ""
        else:
            text += char
    while stack:
        selector, own, inside = stack.pop()
        blocks.append((selector, ";".join(own + [text]), inside))
        text = ""
    return blocks


def reaches_figure(selector: str, elements: set) -> bool:
    """Could a selector's subject match a checked mark, an element inside one or one around it?"""
    selector = re.sub(r"\"[^\"]*\"|'[^']*'", '""', selector)
    selector = re.sub(r"\([^)]*\)", "()", selector)
    selector = re.sub(r"\[\s*([\w:-]+)[^\]]*\]", r"[\1]", selector)
    for alternative in selector.split(","):
        subject = re.split(r"\s*[\s>+~]\s*", alternative.strip())[-1]
        typed = re.match(r"[A-Za-z][\w-]*", subject)
        tag = typed.group().lower() if typed else None
        need = {"class:" + name for name in re.findall(r"\.([\w-]+)", subject)}
        need |= {"id:" + name for name in re.findall(r"#([\w-]+)", subject)}
        need |= {"attr:" + name.lower() for name in re.findall(r"\[([\w:-]+)\]", subject)}
        if tag is None and not need:
            return True
        if any((tag is None or tag == element) and need <= tokens
               for element, tokens in elements):
            return True
    return False


def check_style_rules(source: str, findings: list, name: str) -> None:
    """A <style> rule outranks every fill, stroke and visibility attribute read here."""
    elements = figure_elements(source)
    for match in STYLE_RE.finditer(source):
        css = blank_comments_outside_strings(blank_css_strings(match.group("body")))
        css = css.replace("<!--", " ").replace("-->", " ")
        for selector, body, in_keyframes in css_blocks(css):
            if CSS_PAINT_RE.search(body) and reaches_figure(selector, elements):
                findings.append(
                    "%s:%d: a <style> rule %r sets stroke or fill, which outranks "
                    "the fill attributes the coral-commit count reads — paint "
                    "each mark with its own literal attribute"
                    % (name, line_of(source, match.start()), selector)
                )
            elif (CSS_ALL_RE.search(body) or (not in_keyframes and css_hides(body))) \
                    and reaches_figure(selector, elements):
                findings.append(
                    "%s:%d: a <style> rule %r hides or resets a bound mark "
                    "(display, visibility, zero opacity or the all shorthand) "
                    "— a commit, connector or tag readers cannot see still "
                    "counts. Remove the rule or aim it at a non-SVG element"
                    % (name, line_of(source, match.start()), selector)
                )


def transformed_spans(source: str) -> list:
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        events.append((match.start(), 0, match.group("tag").lower(),
                       attrs_of(match.group("attrs"))))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None, None))
    events.sort(key=lambda event: (event[0], event[1]))
    stack, spans = [], []
    for position, kind, tag, attrs in events:
        if kind == 0:
            how, effect = None, None
            nested_svg = tag == "svg" and any(entry[1] == "svg" for entry in stack)
            if "transform" in attrs:
                how, effect = "an ancestor <g>/<svg> transform", "moves"
            elif transform_carrier(attrs) is not None:
                how, effect = "an ancestor <g>/<svg> style transform", "moves"
            elif nested_svg and any(key in attrs for key in VIEWPORT_ATTRS):
                how, effect = (
                    "a nested <svg> viewport (%s)" % ", ".join(
                        key for key in VIEWPORT_ATTRS if key in attrs
                    ),
                    "moves",
                )
            elif tag in NON_RENDERED:
                how, effect = "a non-rendered <%s> container" % tag, "hides"
            elif hidden_carrier(attrs) is not None:
                how, effect = (
                    "an ancestor <%s> %s" % (tag, hidden_carrier(attrs)),
                    "hides",
                )
            stack.append((position, tag, how, effect))
        elif stack:
            start, _tag, how, effect = stack.pop()
            if how:
                spans.append((start, position, how, effect))
    for start, _tag, how, effect in stack:
        if how:
            spans.append((start, len(source), how, effect))
    return spans


def check_transforms(source: str, findings: list, name: str) -> None:
    check_style_rules(source, findings, name)
    check_connector_ink(source, findings, name)
    check_commit_ink(source, findings, name)
    for match in STYLE_RE.finditer(source):
        if CSS_MOVES_MARK_RE.search(blank_css_strings(match.group("body"))):
            findings.append(
                "%s:%d: a <style> rule positions a mark with CSS "
                "(transform/translate/rotate/scale, a geometry property, or "
                "a motion path) — bake the offset into the attributes; a "
                "partial transform stack is worse than an honest refusal"
                % (name, line_of(source, match.start()))
            )
    spans = transformed_spans(source)
    tagged = list(CIRCLE_RE.finditer(source)) + list(PATH_RE.finditer(source))
    tagged += list(LINE_RE.finditer(source)) + list(TEXT_RE.finditer(source))
    for match in tagged:
        attrs = attrs_of(match.group("attrs"))
        how = transform_carrier(attrs)
        if how is not None:
            findings.append(
                "%s:%d: %s positions a mark — the checker reads raw "
                "coordinates, so anything applied afterwards invalidates "
                "the check that passed. Bake the offset into the attributes"
                % (name, line_of(source, match.start()), how)
            )
            continue
        bound = is_bound(match)
        hidden = hidden_carrier(attrs) if bound else None
        if hidden is not None:
            findings.append(
                "%s:%d: %s hides a bound mark — a commit, connector or tag "
                "readers cannot see still counts. Remove it or draw it"
                % (name, line_of(source, match.start()), hidden)
            )
            continue
        for start, end, ancestor, effect in spans:
            if not start < match.start() < end:
                continue
            if effect == "moves":
                findings.append(
                    "%s:%d: %s positions a mark — the checker reads raw "
                    "coordinates, so anything applied afterwards invalidates "
                    "the check that passed. Bake the offset into the attributes"
                    % (name, line_of(source, match.start()), ancestor)
                )
                break
            if bound:
                findings.append(
                    "%s:%d: %s hides a bound mark — a commit, connector or "
                    "tag readers cannot see still counts. Remove it or draw it"
                    % (name, line_of(source, match.start()), ancestor)
                )
                break


def invisible_stroke(value) -> bool:
    text = str(value).strip().lower()
    return text in ("none", "transparent") or RGBA_ZERO_RE.match(text) is not None


def zero_stroke_width(value) -> bool:
    cleaned = re.sub(
        r"(?:px|em|rem|pt|pc|cm|mm|in|ex|ch|vw|vh|vmin|vmax)\s*$",
        "",
        str(value).split("!")[0].strip(),
        flags=re.IGNORECASE,
    )
    return invisible_amount(cleaned)


def check_connector_ink(source: str, findings: list, name: str) -> None:
    """A connector is a parent only if readers can see it: resolve its stroke and stroke-width."""
    strokes = paint_spans(source, "stroke")
    widths = paint_spans(source, "stroke-width")
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        if not DECLARES_CONNECTOR_RE.search(raw):
            continue
        attrs = attrs_of(raw)
        stroke = declared_paint(attrs, "stroke")
        if stroke is None:
            stroke = inherited_paint(strokes, match.start())
        width = declared_paint(attrs, "stroke-width")
        if width is None:
            width = inherited_paint(widths, match.start())
        label = "%s→%s" % (attrs.get("data-from", "?"), attrs.get("data-to", "?"))
        where = "%s:%d" % (name, line_of(source, match.start()))
        if stroke is None or invisible_stroke(stroke):
            findings.append(
                "%s: connector %s has no visible stroke (%s) — a connector "
                "readers cannot see still counts as a parent. Give it a "
                "stroke color" % (where, label,
                                  "stroke=%r" % stroke if stroke is not None
                                  else "no stroke set, SVG default is none")
            )
        elif width is not None and zero_stroke_width(width):
            findings.append(
                "%s: connector %s has stroke-width=%r — a connector readers "
                "cannot see still counts as a parent. Give it a positive "
                "stroke-width" % (where, label, width)
            )


def check_commit_ink(source: str, findings: list, name: str) -> None:
    """A commit dot is a parent only if readers can see it: resolve fill, stroke and stroke-width."""
    fills = fill_spans(source)
    strokes = paint_spans(source, "stroke")
    widths = paint_spans(source, "stroke-width")
    for match in CIRCLE_RE.finditer(source):
        raw = match.group("attrs")
        if not DECLARES_COMMIT_RE.search(raw):
            continue
        attrs = attrs_of(raw)
        fill = declared_fill(attrs)
        if fill is None:
            fill = inherited_fill(fills, match.start())
        if fill is None or not invisible_stroke(fill):
            continue
        stroke = declared_paint(attrs, "stroke")
        if stroke is None:
            stroke = inherited_paint(strokes, match.start())
        width = declared_paint(attrs, "stroke-width")
        if width is None:
            width = inherited_paint(widths, match.start())
        if stroke is None:
            stroke_detail = "no stroke"
        elif invisible_stroke(stroke):
            stroke_detail = "stroke=%r" % stroke
        elif width is not None and zero_stroke_width(width):
            stroke_detail = "stroke-width=%r" % width
        else:
            continue
        label = attrs.get("data-commit", "").strip() or "?"
        where = "%s:%d" % (name, line_of(source, match.start()))
        findings.append(
            "%s: commit %s has no visible paint (fill=%r, %s) — a commit "
            "readers cannot see still counts as a parent. Give it a fill or "
            "stroke color" % (where, label, fill, stroke_detail)
        )


def path_points(d: str):
    """Walk one continuous absolute M/H/V/L elbow. A second moveto or any other command is unreadable here."""
    text = d.strip()
    tokens = TOKEN_RE.findall(text)
    leftover = TOKEN_RE.sub(" ", text)
    if not tokens or PATH_LEFTOVER_RE.search(leftover):
        return None
    x = y = 0.0
    points = []
    cmd = None
    index = 0

    def take() -> float | None:
        nonlocal index
        if index >= len(tokens):
            return None
        token = tokens[index]
        if token.isalpha():
            return None
        index += 1
        return number(token)

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            if token not in "MHVLmhvl":
                return None
            if token in "Mm" and points:
                return None
            cmd = token
            index += 1
            continue
        if cmd is None:
            return None
        if cmd in "Mm":
            nx, ny = take(), take()
            if None in (nx, ny):
                return None
            if cmd == "m" and points:
                nx += x
                ny += y
            x, y = nx, ny
            points.append((x, y))
            cmd = "L" if cmd == "M" else "l"
        elif cmd in "Ll":
            nx, ny = take(), take()
            if None in (nx, ny):
                return None
            if cmd == "l":
                nx += x
                ny += y
            x, y = nx, ny
            points.append((x, y))
        elif cmd in "Hh":
            nx = take()
            if nx is None:
                return None
            if cmd == "h":
                nx += x
            x = nx
            points.append((x, y))
        elif cmd in "Vv":
            ny = take()
            if ny is None:
                return None
            if cmd == "v":
                ny += y
            y = ny
            points.append((x, y))
        else:
            return None
    return points if len(points) >= 2 else None


def accent_colors(source: str) -> set:
    declared = []
    for match in STYLE_RE.finditer(source):
        css = blank_comments_outside_strings(blank_css_strings(match.group("body")))
        for found in COLOR_ACCENT_RE.finditer(css):
            color = rgb_of(found.group("value"))
            if color is not None:
                declared.append(color)
    return DEFAULT_ACCENTS | set(declared[-1:])


def parse_lanes(source: str, findings: list, name: str) -> dict:
    lanes = {}
    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-lane" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        label = attrs["data-lane"].strip()
        declared = number(attrs.get("data-y"))
        y1 = number(attrs.get("y1"))
        y2 = number(attrs.get("y2"))
        if not label:
            findings.append("%s: a lane rail has an empty data-lane" % where)
            continue
        if None in (declared, y1, y2):
            findings.append(
                "%s: lane %r is missing a finite data-y / y1 / y2"
                % (where, label)
            )
            continue
        if abs(y1 - declared) > COORD_TOLERANCE or abs(y2 - declared) > COORD_TOLERANCE:
            findings.append(
                "%s: lane %r rail is at y=%g/%g, off data-y=%g"
                % (where, label, y1, y2, declared)
            )
        if label in lanes:
            findings.append("%s: two rails share data-lane=%r" % (where, label))
            continue
        lanes[label] = Lane(name=label, y=declared, offset=match.start())
    return lanes


def parse_commits(source: str, findings: list, name: str, accents: set,
                  spans: list) -> list:
    commits = []
    seen = set()
    seen_pos = set()
    for match in CIRCLE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-commit" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        label = attrs["data-commit"].strip()
        lane = attrs.get("data-lane", "").strip()
        column = number(attrs.get("data-column"))
        cx = number(attrs.get("cx"))
        cy = number(attrs.get("cy"))
        radius = number(attrs.get("r"))
        if not label:
            findings.append("%s: a commit has an empty data-commit" % where)
            continue
        if label in seen:
            findings.append("%s: two commits share data-commit=%r" % (where, label))
            continue
        seen.add(label)
        if not lane or column is None or column != int(column) or column < 0:
            findings.append(
                "%s: commit %r needs data-lane and a non-negative integer "
                "data-column" % (where, label)
            )
            continue
        cell = (lane, int(column))
        if cell in seen_pos:
            findings.append(
                "%s: commit %r sits on lane %r column %d, which already has "
                "a commit — overlapping dots cannot share a cell"
                % (where, label, lane, int(column))
            )
            continue
        seen_pos.add(cell)
        if None in (cx, cy, radius) or radius <= 0:
            findings.append(
                "%s: commit %r has a coordinate or r that is not a finite "
                "positive number" % (where, label)
            )
            continue
        own = declared_fill(attrs)
        fill = own if own is not None else (inherited_fill(spans, match.start()) or "")
        commits.append(Commit(
            name=label, lane=lane, column=int(column),
            cx=cx, cy=cy, r=radius,
            merge=attrs.get("data-kind", "").strip().casefold() == "merge",
            accent=rgb_of(fill) in accents,
            offset=match.start(),
        ))
    return commits


def parse_connectors(source: str, findings: list, name: str) -> list:
    connectors = []
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        if not DECLARES_CONNECTOR_RE.search(raw):
            continue
        attrs = attrs_of(raw)
        where = "%s:%d" % (name, line_of(source, match.start()))
        missing = [key for key in ("data-from", "data-to", "d") if key not in attrs]
        if missing:
            findings.append(
                "%s: a connector is missing %s — each connector names its "
                "source, its target, and an orthogonal elbow"
                % (where, ", ".join(missing))
            )
            continue
        points = path_points(attrs["d"])
        if points is None:
            findings.append(
                "%s: connector %s→%s is not a single continuous orthogonal "
                "M/H/V/L elbow"
                % (where, attrs["data-from"], attrs["data-to"])
            )
            continue
        connectors.append(Connector(
            frm=attrs["data-from"].strip(),
            to=attrs["data-to"].strip(),
            points=points,
            offset=match.start(),
        ))
    return connectors


def check_lane_labels(source: str, lanes: dict, findings: list, name: str) -> None:
    labels = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-lane" not in attrs or "data-tag" in attrs:
            continue
        label = attrs["data-lane"].strip()
        body = plain(match.group("body"))
        y = number(attrs.get("y"))
        if label in labels:
            findings.append("%s: a second label for lane %r" % (name, label))
            continue
        labels[label] = (body, y, match.start())
    for lane_name, lane in lanes.items():
        if lane_name not in labels:
            findings.append("%s: lane %r has no bound label" % (name, lane_name))
            continue
        body, y, _offset = labels[lane_name]
        if body != lane_name:
            findings.append(
                "%s: label for lane %r prints %r — the visible text has to "
                "match the binding" % (name, lane_name, body)
            )
        if y is None or abs(y - lane.y) > 8:
            findings.append(
                "%s: label for lane %r sits at y=%s, off the rail y=%g"
                % (name, lane_name, "?" if y is None else "%g" % y, lane.y)
            )
    for label in labels:
        if label not in lanes:
            findings.append("%s: a label names lane %r, which has no rail" % (name, label))


def check_geometry(commits: list, connectors: list, lanes: dict,
                   source: str, findings: list, name: str) -> None:
    by_name = {item.name: item for item in commits}
    for item in commits:
        where = "%s:%d" % (name, line_of(source, item.offset))
        if item.lane not in lanes:
            findings.append(
                "%s: commit %r names lane %r, which has no rail"
                % (where, item.name, item.lane)
            )
            continue
        expected_y = lanes[item.lane].y
        if abs(item.cy - expected_y) > COORD_TOLERANCE:
            findings.append(
                "%s: commit %r sits at y=%g, off its lane y=%g"
                % (where, item.name, item.cy, expected_y)
            )

    columns: dict[int, list] = {}
    for item in commits:
        columns.setdefault(item.column, []).append(item.cx)
    if len(columns) < 2:
        findings.append("%s: a git graph needs at least two columns" % name)
        return
    column_x = {col: median(xs) for col, xs in columns.items()}
    for item in commits:
        expected = column_x[item.column]
        if abs(item.cx - expected) > COORD_TOLERANCE:
            findings.append(
                "%s: commit %r sits at x=%g, off its grid column x=%g"
                % (name, item.name, item.cx, expected)
            )
    ordered_cols = sorted(column_x)
    pitches = []
    for i in range(len(ordered_cols) - 1):
        delta_col = ordered_cols[i + 1] - ordered_cols[i]
        delta_x = column_x[ordered_cols[i + 1]] - column_x[ordered_cols[i]]
        if delta_col <= 0:
            findings.append("%s: two columns share an x — time reads left to right" % name)
            return
        pitches.append(delta_x / delta_col)
    if any(gap <= 0 for gap in pitches):
        findings.append("%s: two columns share an x — time reads left to right" % name)
        return
    pitch = median(pitches)
    if any(abs(gap - pitch) > PITCH_TOLERANCE for gap in pitches):
        findings.append(
            "%s: column spacing is %gpx and %gpx — commits sit on one shared "
            "pitch" % (name, pitch, max(pitches, key=lambda gap: abs(gap - pitch)))
        )
    origins = [column_x[col] - col * pitch for col in ordered_cols]
    origin = median(origins)
    for item in commits:
        expected = origin + item.column * pitch
        if abs(item.cx - expected) > COORD_TOLERANCE:
            findings.append(
                "%s: commit %r sits at x=%g, off its grid column x=%g"
                % (name, item.name, item.cx, expected)
            )

    incoming: dict[str, list] = {item.name: [] for item in commits}
    for connector in connectors:
        where = "%s:%d" % (name, line_of(source, connector.offset))
        if connector.frm not in by_name or connector.to not in by_name:
            missing = [n for n in (connector.frm, connector.to) if n not in by_name]
            findings.append(
                "%s: connector %s→%s names %s, which is not a commit"
                % (where, connector.frm, connector.to, ", ".join(missing))
            )
            continue
        src, dst = by_name[connector.frm], by_name[connector.to]
        if src.column >= dst.column:
            findings.append(
                "%s: connector %s→%s runs right-to-left (column %d → %d) — "
                "parents sit on earlier columns"
                % (where, connector.frm, connector.to, src.column, dst.column)
            )
        xs = [x for x, _y in connector.points]
        if any(xs[i] < xs[i - 1] - COORD_TOLERANCE for i in range(1, len(xs))):
            findings.append(
                "%s: connector %s→%s goes right-to-left in its path — time "
                "reads left to right" % (where, connector.frm, connector.to)
            )
        start, end = connector.points[0], connector.points[-1]
        if abs(start[0] - src.cx) > COORD_TOLERANCE or abs(start[1] - src.cy) > COORD_TOLERANCE:
            findings.append(
                "%s: connector %s→%s starts at (%g,%g), off commit %s at "
                "(%g,%g)" % (where, connector.frm, connector.to,
                             start[0], start[1], src.name, src.cx, src.cy)
            )
        if abs(end[0] - dst.cx) > COORD_TOLERANCE or abs(end[1] - dst.cy) > COORD_TOLERANCE:
            findings.append(
                "%s: connector %s→%s ends at (%g,%g), off commit %s at "
                "(%g,%g)" % (where, connector.frm, connector.to,
                             end[0], end[1], dst.name, dst.cx, dst.cy)
            )
        check_connector_turn(connector, src, dst, lanes, findings, where)
        check_connector_crossing(connector, commits, findings, where)
        incoming[dst.name].append(connector)
    check_connector_overlap(connectors, findings, source, name)

    for item in commits:
        parents = incoming[item.name]
        if item.merge:
            if len(parents) != 2:
                findings.append(
                    "%s: merge commit %r has %d incoming connector(s) — a "
                    "merge has exactly two incoming connectors"
                    % (name, item.name, len(parents))
                )
                continue
            sources = [by_name[edge.frm] for edge in parents if edge.frm in by_name]
            if len(sources) != 2:
                continue
            if sources[0].lane == sources[1].lane:
                findings.append(
                    "%s: merge commit %r has both parents on lane %r — "
                    "parents sit on different lanes"
                    % (name, item.name, sources[0].lane)
                )
            if any(src.column >= item.column for src in sources):
                findings.append(
                    "%s: merge commit %r has a parent that is not on an "
                    "earlier column" % (name, item.name)
                )
        elif len(parents) > 1:
            findings.append(
                "%s: commit %r has %d incoming connectors without "
                "data-kind=merge — two parents make a merge commit"
                % (name, item.name, len(parents))
            )


def segment_distance(point, start, end) -> float:
    """Distance from point to the straight segment start-end."""
    px, py = point
    sx, sy = start
    ex, ey = end
    dx, dy = ex - sx, ey - sy
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return math.hypot(px - sx, py - sy)
    t = max(0.0, min(1.0, ((px - sx) * dx + (py - sy) * dy) / length_sq))
    return math.hypot(px - (sx + t * dx), py - (sy + t * dy))


def check_connector_crossing(connector, commits: list, findings: list,
                             where: str) -> None:
    """A connector touches only the two commits it names.

    Ink through a third dot reads as a connection its bindings do not
    declare, so any segment that reaches another commit's dot is a finding.
    """
    for item in commits:
        if item.name in (connector.frm, connector.to):
            continue
        reach = item.r + COORD_TOLERANCE
        for i in range(len(connector.points) - 1):
            if segment_distance((item.cx, item.cy), connector.points[i],
                                connector.points[i + 1]) < reach:
                findings.append(
                    "%s: connector %s→%s passes through commit %r — a "
                    "connector touches only the commits it names; move the "
                    "commit or the merge to another column"
                    % (where, connector.frm, connector.to, item.name)
                )
                break


def elbow_corners(points: list) -> list:
    """Interior vertices where an orthogonal path changes axis."""
    corners = []
    for i in range(1, len(points) - 1):
        dx1 = points[i][0] - points[i - 1][0]
        dy1 = points[i][1] - points[i - 1][1]
        dx2 = points[i + 1][0] - points[i][0]
        dy2 = points[i + 1][1] - points[i][1]
        axis1_h = abs(dy1) <= COORD_TOLERANCE
        axis2_h = abs(dy2) <= COORD_TOLERANCE
        if axis1_h != axis2_h:
            corners.append(points[i])
    return corners


def axis_aligned(p, q) -> bool:
    return abs(p[0] - q[0]) <= COORD_TOLERANCE or abs(p[1] - q[1]) <= COORD_TOLERANCE


def on_axis_segment(point, start, end) -> bool:
    """Does point sit on the axis-aligned segment start–end, inclusive?"""
    if not axis_aligned(start, end):
        return False
    x, y = point
    if abs(start[1] - end[1]) <= COORD_TOLERANCE:
        if abs(y - start[1]) > COORD_TOLERANCE:
            return False
        lo, hi = min(start[0], end[0]), max(start[0], end[0])
        return lo - COORD_TOLERANCE <= x <= hi + COORD_TOLERANCE
    if abs(x - start[0]) > COORD_TOLERANCE:
        return False
    lo, hi = min(start[1], end[1]), max(start[1], end[1])
    return lo - COORD_TOLERANCE <= y <= hi + COORD_TOLERANCE


def on_elbow_route(point, start, corner, end) -> bool:
    return on_axis_segment(point, start, corner) or on_axis_segment(point, corner, end)


def segment_overlap_length(a1, a2, b1, b2) -> float:
    """Length of collinear overlap of two axis-aligned segments, else 0."""
    if not axis_aligned(a1, a2) or not axis_aligned(b1, b2):
        return 0.0
    a_h = abs(a1[1] - a2[1]) <= COORD_TOLERANCE
    b_h = abs(b1[1] - b2[1]) <= COORD_TOLERANCE
    if a_h != b_h:
        return 0.0
    if a_h:
        if abs(a1[1] - b1[1]) > COORD_TOLERANCE:
            return 0.0
        lo = max(min(a1[0], a2[0]), min(b1[0], b2[0]))
        hi = min(max(a1[0], a2[0]), max(b1[0], b2[0]))
        return max(0.0, hi - lo)
    if abs(a1[0] - b1[0]) > COORD_TOLERANCE:
        return 0.0
    lo = max(min(a1[1], a2[1]), min(b1[1], b2[1]))
    hi = min(max(a1[1], a2[1]), max(b1[1], b2[1]))
    return max(0.0, hi - lo)


def check_connector_overlap(connectors: list, findings: list,
                            source: str, name: str) -> None:
    """Two connectors may meet at a commit; they must not share a run of ink."""
    for i, left in enumerate(connectors):
        for right in connectors[i + 1:]:
            for a in range(len(left.points) - 1):
                for b in range(len(right.points) - 1):
                    overlap = segment_overlap_length(
                        left.points[a], left.points[a + 1],
                        right.points[b], right.points[b + 1],
                    )
                    if overlap <= COORD_TOLERANCE:
                        continue
                    where = "%s:%d" % (name, line_of(source, left.offset))
                    findings.append(
                        "%s: connector %s→%s overlaps %s→%s — two connectors "
                        "may meet at a commit, not share a segment"
                        % (where, left.frm, left.to, right.frm, right.to)
                    )
                    return


def check_connector_turn(connector, src, dst, lanes: dict,
                         findings: list, where: str) -> None:
    """Branch turns at the parent column; merge turns at the merge column."""
    points = connector.points
    for i in range(len(points) - 1):
        if not axis_aligned(points[i], points[i + 1]):
            findings.append(
                "%s: connector %s→%s has a diagonal segment — elbows are "
                "orthogonal M/H/V/L" % (where, src.name, dst.name)
            )
            return

    same_lane = src.lane == dst.lane
    if same_lane:
        permitted_y = src.cy
        if any(abs(y - permitted_y) > COORD_TOLERANCE for _x, y in points):
            findings.append(
                "%s: connector %s→%s leaves lane %r — on-lane history stays "
                "on its rail" % (where, src.name, dst.name, src.lane)
            )
        check_collinear_segments(
            connector, src, dst, lanes, permitted_y, findings, where
        )
        return

    if dst.merge:
        expected = (dst.cx, src.cy)
        permitted_y = src.cy
        rule = (
            "a merge turns at the merge column (horizontal on the source "
            "lane, then vertical)"
        )
        kind = "merge"
    else:
        expected = (src.cx, dst.cy)
        permitted_y = dst.cy
        rule = (
            "a branch turns at the parent column (vertical first, then "
            "horizontal on the child lane)"
        )
        kind = "branch"

    start, end = (src.cx, src.cy), (dst.cx, dst.cy)
    if any(not on_elbow_route(point, start, expected, end) for point in points):
        findings.append(
            "%s: connector %s→%s leaves its %s route — %s"
            % (where, src.name, dst.name, kind, rule)
        )
    corners = elbow_corners(points)
    if len(corners) > 1:
        findings.append(
            "%s: connector %s→%s turns more than once — %s"
            % (where, src.name, dst.name, rule)
        )
    actual = corners[0] if corners else None
    if actual is None:
        if abs(end[0] - expected[0]) > COORD_TOLERANCE \
                or abs(end[1] - expected[1]) > COORD_TOLERANCE:
            findings.append(
                "%s: connector %s→%s turns at no elbow — %s"
                % (where, src.name, dst.name, rule)
            )
    elif abs(actual[0] - expected[0]) > COORD_TOLERANCE \
            or abs(actual[1] - expected[1]) > COORD_TOLERANCE:
        findings.append(
            "%s: connector %s→%s turns at (%g,%g) — %s"
            % (where, src.name, dst.name, actual[0], actual[1], rule)
        )
    check_collinear_segments(
        connector, src, dst, lanes, permitted_y, findings, where
    )


def check_collinear_segments(connector, src, dst, lanes: dict, permitted_y: float,
                             findings: list, where: str) -> None:
    """A horizontal run may sit on the lane it is drawing, not on another rail."""
    points = connector.points
    for i in range(len(points) - 1):
        (_x1, y1), (_x2, y2) = points[i], points[i + 1]
        if abs(y1 - y2) > COORD_TOLERANCE:
            continue
        y = y1
        if abs(y - permitted_y) <= COORD_TOLERANCE:
            continue
        for lane in lanes.values():
            if abs(y - lane.y) <= COORD_TOLERANCE:
                findings.append(
                    "%s: connector %s→%s has a segment collinear with lane "
                    "%r — no connector segment may run along a lane it is "
                    "not drawing"
                    % (where, src.name, dst.name, lane.name)
                )
                return


def check_tags(source: str, commits: list, findings: list, name: str) -> None:
    by_name = {item.name: item for item in commits}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-tag" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        tag = attrs["data-tag"].strip()
        bound = attrs.get("data-commit", "").strip()
        body = plain(match.group("body"))
        x = number(attrs.get("x"))
        y = number(attrs.get("y"))
        if not tag or tag != body:
            findings.append(
                "%s: tag %r prints %r — the visible text has to match data-tag"
                % (where, tag, body)
            )
        if bound not in by_name:
            findings.append(
                "%s: tag %r attaches to commit %r, which does not exist"
                % (where, tag, bound or "(missing)")
            )
            continue
        commit = by_name[bound]
        if x is None or abs(x - commit.cx) > 8:
            findings.append(
                "%s: tag %r sits at x=%s, off commit %s at x=%g"
                % (where, tag, "?" if x is None else "%g" % x, commit.name, commit.cx)
            )
        if y is None or y >= commit.cy - 8:
            findings.append(
                "%s: tag %r sits at y=%s, not above commit %s at y=%g"
                % (where, tag, "?" if y is None else "%g" % y, commit.name, commit.cy)
            )


def check_focal(commits: list, findings: list, name: str) -> None:
    accents = [item for item in commits if item.accent]
    if len(accents) > MAX_CORAL:
        findings.append(
            "%s: %d commits wear the accent fill — a git graph has at most "
            "two coral commits" % (name, len(accents))
        )


def check_lane_overlap(lanes: dict, commits: list, findings: list, name: str) -> None:
    if len(lanes) < 2:
        return
    radius = max((item.r for item in commits), default=8)
    ordered = sorted(lanes.values(), key=lambda lane: lane.y)
    for previous, current in zip(ordered, ordered[1:]):
        gap = current.y - previous.y
        if gap < LANE_GAP:
            findings.append(
                "%s: lanes %r and %r are %gpx apart — lanes do not overlap "
                "(need ≥ %dpx, about two radii plus a gutter)"
                % (name, previous.name, current.name, gap, LANE_GAP)
            )
        if gap < 2 * radius + 16:
            findings.append(
                "%s: lanes %r and %r overlap given commit r=%g"
                % (name, previous.name, current.name, radius)
            )


SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)


def root_viewbox(source: str):
    """(min_y, height) of the first <svg> viewBox, or None when absent or unreadable."""
    match = SVG_OPEN_RE.search(source)
    if not match:
        return None
    for attr in ATTR_RE.finditer(match.group(0)):
        if attr.group("name").lower() != "viewbox":
            continue
        parts = re.split(r"[\s,]+", attr.group("value").strip())
        if len(parts) != 4:
            return None
        try:
            min_y, height = float(parts[1]), float(parts[3])
        except ValueError:
            return None
        if not (math.isfinite(min_y) and math.isfinite(height)) or height <= 0:
            return None
        return min_y, height
    return None


def check_lane_canvas(source: str, lanes: dict, commits: list, findings: list, name: str) -> None:
    box = root_viewbox(source)
    if box is None:
        return
    top, height = box
    bottom = top + height
    radius = max((item.r for item in commits), default=8)
    for lane in sorted(lanes.values(), key=lambda item: item.y):
        if lane.y - radius < top or lane.y + radius > bottom:
            findings.append(
                "%s: lane %r sits at y=%g, outside the %g-high viewBox — "
                "use the 96px pitch from y=216 for four or five lanes"
                % (name, lane.name, lane.y, height)
            )


def check_source(path: Path, raw: str) -> list:
    escaped = escaped_property_findings(raw)
    if escaped:
        return [f"{path.name}: {finding}" for finding in escaped]
    source = blank_comments(raw)
    findings: list = []
    name = path.name
    accents = accent_colors(source)
    lanes = parse_lanes(source, findings, name)
    commits = parse_commits(source, findings, name, accents, fill_spans(source))
    connectors = parse_connectors(source, findings, name)
    if len(lanes) > MAX_LANES:
        findings.append(
            "%s: %d lanes against a budget of %d — split an overview from "
            "per-train detail" % (name, len(lanes), MAX_LANES)
        )
    elif len(lanes) < MIN_LANES:
        findings.append(
            "%s: presents as a git graph but declares %d verifiable lane(s) "
            "— below %d there is no branch to merge"
            % (name, len(lanes), MIN_LANES)
        )
    if len(commits) > MAX_COMMITS:
        findings.append(
            "%s: %d commits against a budget of %d — split an overview from "
            "a zoom" % (name, len(commits), MAX_COMMITS)
        )
    elif len(commits) < MIN_COMMITS:
        findings.append(
            "%s: presents as a git graph but declares %d verifiable "
            "commit(s) — below %d there is no branch-off and merge to check"
            % (name, len(commits), MIN_COMMITS)
        )
    merges = [item for item in commits if item.merge]
    if commits and not merges:
        findings.append(
            "%s: presents as a git graph but declares no merge commit — a "
            "merge is a dot with two parents, not a plain line"
            % name
        )
    if len(commits) >= MIN_COMMITS and len(lanes) >= MIN_LANES:
        check_transforms(source, findings, name)
        check_lane_labels(source, lanes, findings, name)
        check_geometry(commits, connectors, lanes, source, findings, name)
        check_tags(source, commits, findings, name)
        check_focal(commits, findings, name)
        check_lane_overlap(lanes, commits, findings, name)
        check_lane_canvas(source, lanes, commits, findings, name)
    elif commits or lanes:
        check_transforms(source, findings, name)
    return findings


def check(path: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    if not looks_like_git_graph(path, raw):
        return []
    return check_source(path, raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify git-graph geometry against lanes, columns, merges and tags."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a git graph",
    )
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    if args.all:
        targets = sorted(ASSET_DIR.glob("example-*.html"))
    else:
        targets = [Path(p) for p in args.paths]

    findings: list = []
    checked = 0
    skipped = 0
    for path in targets:
        if not path.is_file():
            print("error: %s is not a readable file" % path, file=sys.stderr)
            return 2
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print("error: cannot read %s: %s" % (path, error), file=sys.stderr)
            return 2
        if not looks_like_git_graph(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d git-graph finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK git graph: no git graph found to check%s" % tail)
        return 0
    print("OK git graph: %d file(s), every commit on its lane and column "
          "grid, every merge with exactly two earlier parents on different "
          "lanes, connectors that turn at the parent or merge column, no "
          "right-to-left connectors, tags on existing commits, at most two "
          "coral commits, and lanes that do not overlap and stay on the canvas%s"
          % (checked, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
