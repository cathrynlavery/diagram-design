#!/usr/bin/env python3
"""Verify that a box plot's drawn marks match the five-number values they declare.

A box plot makes one hard claim: every box, median, whisker and outlier sits
EXACTLY at its value on one shared linear value axis. The perpendicular
(category) axis is a label rail — it carries no value. Both halves can be
broken without anything erroring: a box nudged along the value axis "to open
up space" renders fine and reads as a different quartile, and an outlier
drawn inside the whisker turns a genuine extreme into a point on the fence.

`lint-skin.py` reads colors and fonts and `verify-geometry.py` reads label
masks; neither compares a drawn coordinate against the five-number summary
bound to it.

Ten invariants:

1. SHARED VALUE SCALE - every mark's position on the value axis must sit
   where one linear scale puts its declared value. The scale is derived from
   the distinct values (Theil-Sen, leave-one-out), so one dishonest mark
   cannot drag the line it is measured against.

2. FIVE-NUMBER ORDER - each series declares wlo ≤ q1 ≤ q2 ≤ q3 ≤ whi as
   finite numbers. A median outside its box, or a whisker that grows inward,
   is not a five-number summary.

3. BOX GEOMETRY - the stroked box rect's left edge is q1 and its right edge
   is q3 on that scale. Width is not decoration.

4. MEDIAN GEOMETRY - the median is a vertical line at q2, both ends, running
   from the box's top edge to its bottom edge.

5. WHISKER GEOMETRY - whisker-lo runs from wlo to q1 and whisker-hi from q3
   to whi, horizontal through the box's row centre.

6. TUKEY FENCES - whiskers stay inside [q1 - 1.5 IQR, q3 + 1.5 IQR], and
   every outlier sits strictly outside both the whiskers and those fences,
   at its declared value. A circle with data-outlier must bind data-x and
   must sit inside the series group that name points at. An inlier drawn
   as a dot is a box plot wearing a beeswarm costume. A cap, when drawn,
   sits on a whisker end and crosses the whisker's row. An unbound circle
   inside a series is allowed only as a paper mask sharing an outlier's
   centre, painted only with the paper colour.

7. AT MOST ONE ACCENT SERIES - one focal claim per figure, on either skin.
   Fill and stroke are read from the attribute, the inline style and class
   rules, on the series group, any nested group, and every shape inside
   it: underlay, box, median, whiskers, caps, outliers and any path. Hex
   may carry alpha; rgb() counts as rgba().

8. BOUND LABELS - each series carries exactly one <text data-name> whose
   data-name and printed text both match the series, on the series' row
   and on the label rail left of the value axis. dx/dy, a positioned
   <tspan>, and a hiding attribute are refused.

9. UNPOSITIONED GEOMETRY - every coordinate read here is a raw attribute.
   A `transform` attribute, an inline `style`, or a rule in a <style> block
   on a mark, a bound label or tick, or an ancestor is refused rather than
   resolved, as in verify-beeswarm.py. CSS width/height on a box rect is
   refused too (a <style> rule only when its selector can reach a box).
   CSS comments are whitespace. A size rule whose subject has no type,
   class, id or attribute reaches a box. Backslash escapes, stylesheet
   links other than the font link, `<use>`, `<set>`/`<animate*>` and a
   nested `<svg>` viewport are refused. A series inside `<defs>` is not
   the series that gets drawn.

10. FAIL CLOSED - a file that presents as a box plot but yields fewer than
   three series on three distinct medians is a finding, never a pass. Three
   because the scale test is leave-one-out and each fit needs two intervals.

Vocabulary treaty: `data-q1` ON A <g> is the box-plot contract. Detection is
deliberately element-scoped so a source-wide regex cannot claim a sibling.
`data-value` on a <circle> is the beeswarm contract and is never bound here.
`data-size` (bubble), `data-series` (slopegraph) and `data-ranks` (bump) are
never bound here either.

Usage:
    python3 scripts/verify-box-plot.py --all
    python3 scripts/verify-box-plot.py skills/diagram-design/assets/example-box-plot.html

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

CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>",
                     re.IGNORECASE | re.DOTALL)
G_OPEN_RE = re.compile(r"<g\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
G_CLOSE_RE = re.compile(r"</g\s*>", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>",
                           re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>",
                      re.IGNORECASE | re.DOTALL)
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|cx|cy|r|x|y|width|height"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
# SVG 2 makes width/height CSS geometry properties on a <rect>, so they can
# resize a box the checked attributes never state. Every shipped page sizes
# its <svg> and HTML chrome with them in the stylesheet, so a <style> rule
# with one is only reported when its selector can reach a box rect, as in
# verify-marimekko.py; an inline style on a rect is reported outright.
# Comments are blanked first: a browser treats `/* */` as whitespace, so
# `rect{/**/width:300px}` is a live size rule. A subject with no type, class,
# id or attribute (`:nth-child`, `:not(...)`) can still be that rect.
CSS_SIZE_PROPS = ("width", "height")
FORBIDDEN_RE = re.compile(
    r"<(?P<tag>use|set|animate[\w-]*|foreignobject)\b",
    re.IGNORECASE,
)
LINK_RE = re.compile(r"<link\b(?P<attrs>[^>]*)>", re.IGNORECASE)
TSPAN_RE = re.compile(r"<tspan\b(?P<attrs>[^>]*)>", re.IGNORECASE)
NONRENDER_OPEN_RE = re.compile(
    r"<(?P<tag>defs|symbol|clipPath|mask|pattern|marker)\b[^>]*?(?P<selfclose>/?)>",
    re.IGNORECASE,
)
NONRENDER_CLOSE_RE = re.compile(
    r"</(?P<tag>defs|symbol|clipPath|mask|pattern|marker)\s*>",
    re.IGNORECASE,
)
PAINT_DECL_RE = re.compile(
    r"(?:^|[{;])\s*(?:fill|stroke)\s*:\s*([^;}{]+)",
    re.IGNORECASE,
)
STROKE_DECL_RE = re.compile(r"(?:^|[{;])\s*stroke\s*:\s*([^;}{]+)", re.IGNORECASE)
HIDE_DECL_RE = re.compile(
    r"(?:^|[{;])\s*(opacity|fill-opacity|stroke-opacity|visibility|display)"
    r"\s*:\s*([^;}{]+)",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
OPEN_TAG_RE = re.compile(r"<(?P<tag>[A-Za-z][\w-]*)\b(?P<attrs>[^>]*)>")
NON_MARK_TAGS = {"text", "tspan", "title", "desc"}
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_Q1_RE = re.compile(r"\bdata-q1\s*=", re.IGNORECASE)
TUKEY_K = 1.5
ACCENT_RE = re.compile(
    r"#(?:bf4520|f08a59)(?:[0-9a-f]{2})?\b|"
    r"rgba?\(\s*191\s*,\s*69\s*,\s*32\b|"
    r"rgba?\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)
MARK_ROLES = {"box", "median", "whisker-lo", "whisker-hi", "cap"}

RESIDUAL_TOLERANCE = 1.0
VALUE_TOLERANCE = 0.001
TICK_TOLERANCE = 6.0
SAME_ROW_TOLERANCE = 1.0
MIN_SERIES, MAX_SERIES = 3, 8
MAX_OUTLIERS = 8


class Series:
    __slots__ = (
        "name", "q1", "q2", "q3", "wlo", "whi", "cy", "box_x", "box_w",
        "box_y", "box_h", "median_x", "median_x2", "median_y", "wlo_x",
        "wlo_inner", "whi_x", "whi_inner", "whisker_y", "accent", "offset",
        "outliers", "labels", "body_at", "body_end", "medians", "caps",
    )

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class GroupMatch:
    """One <g> element with its full body, nested groups included."""
    __slots__ = ("_start", "_attrs", "_body", "_body_at")

    def __init__(self, start: int, attrs: str, body: str, body_at: int):
        self._start, self._attrs, self._body, self._body_at = (
            start, attrs, body, body_at)

    def start(self) -> int:
        return self._start

    def body_at(self) -> int:
        return self._body_at

    def group(self, key: str) -> str:
        return self._attrs if key == "attrs" else self._body


def groups_of(source: str) -> list:
    """Every <g> in document order, matched to its own closing tag.

    A non-greedy `<g>.*?</g>` stops at the first close, so a plain wrapper
    around the series would swallow the first series and hide it.
    """
    events = []
    for match in G_OPEN_RE.finditer(source):
        events.append((match.start(), 0, match))
    for match in G_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, match))
    events.sort(key=lambda event: (event[0], event[1]))
    stack, found = [], []
    for _position, kind, match in events:
        if kind == 0:
            if match.group("selfclose"):
                found.append(GroupMatch(match.start(), match.group("attrs"),
                                        "", match.end()))
            else:
                stack.append(match)
        elif stack:
            opened = stack.pop()
            found.append(GroupMatch(opened.start(), opened.group("attrs"),
                                    source[opened.end():match.start()],
                                    opened.end()))
    for opened in stack:
        found.append(GroupMatch(opened.start(), opened.group("attrs"),
                                source[opened.end():], opened.end()))
    found.sort(key=lambda group: group.start())
    return found


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def blank_css_comments(css: str) -> str:
    """CSS with every `/* ... */` replaced by whitespace a browser would see.

    Newlines inside the comment are kept so a match still counts lines.
    """
    return CSS_COMMENT_RE.sub(
        lambda found: " " + "\n" * found.group().count("\n"), css)


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


def printed_number(body: str):
    match = NUMBER_RE.search(body)
    if match is None:
        return None, "prints no number"
    outside = body[:match.start()] + body[match.end():]
    if DIGIT_RE.search(outside):
        return None, "prints more than one numeric token"
    value = number(match.group())
    if value is None:
        return None, "prints a number this checker cannot read"
    return value, None


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def fit(points: list) -> tuple:
    slopes = [
        (cb - ca) / (vb - va)
        for index, (va, ca) in enumerate(points)
        for vb, cb in points[index + 1:]
        if vb != va
    ]
    if not slopes:
        return None, None
    slope = median(slopes)
    return slope, median([c - slope * v for v, c in points])


def named_text(source: str) -> str:
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_box_plot(path: Path, source: str) -> bool:
    """Does this file present itself as a box plot?

    Filename, accessible name, or a <g> that binds data-q1. The group
    restriction is the treaty line — a source-wide data-q1 search is fine
    here because no sibling binds that attribute.
    """
    if path.name.startswith("example-box-plot"):
        return True
    if DECLARES_Q1_RE.search(source):
        for match in groups_of(source):
            if DECLARES_Q1_RE.search(match.group("attrs")):
                return True
    text = named_text(source)
    return "box plot" in text or "boxplot" in text.replace("-", " ")


def transform_carrier(attrs: dict, sizes: bool = False):
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is None:
        return None
    plain_style = blank_css_comments(style)
    if "\\" in plain_style:
        return "style=%r (a backslash escape)" % style
    for found in CSS_MOVES_MARK_RE.finditer(plain_style):
        prop = found.group("prop").lower()
        if prop in CSS_SIZE_PROPS and not sizes:
            continue
        return "style=%r (the %s property)" % (style, prop)
    return None


def selector_reaches_box(selector: str, boxes: list) -> bool:
    """Could this selector's subject be a box rect? Coarse on purpose.

    A `rect` type selector or a `*` claims it; a subject naming any other
    element cannot be a rect; a subject of classes, ids and attributes alone
    reaches a box when some box rect carries one of them. A subject with
    none of those (`:nth-child`, a bare `:not(...)`) can still be a rect, so
    it reaches one too. Misreads err towards a finding.
    """
    for alternative in selector.split(","):
        if "\\" in alternative or re.search(r"\brect\b|\*", alternative, re.IGNORECASE):
            return True
        compounds = [part for part in re.split(r"[\s>+~]+", alternative.strip()) if part]
        if not compounds:
            continue
        subject = re.sub(r"::?[\w-]+(?:\([^)]*\))?", "", compounds[-1])
        if re.match(r"[A-Za-z]", subject):
            continue
        classes = set(re.findall(r"\.([\w-]+)", subject))
        ids = set(re.findall(r"#([\w-]+)", subject))
        names = {name.lower() for name in re.findall(r"\[\s*([\w-]+)", subject)}
        if not classes and not ids and not names:
            return True
        for attrs in boxes:
            if (classes & set(attrs.get("class", "").split())
                    or attrs.get("id") in ids
                    or names & set(attrs)):
                return True
    return False


def selector_has_escape(css: str) -> bool:
    return any("\\" in chunk.group(1) for chunk in re.finditer(r"([^{}]+)\{", css))


def css_moves_mark(css: str, boxes: list):
    css = blank_css_comments(css)
    for found in CSS_MOVES_MARK_RE.finditer(css):
        if found.group("prop").lower() not in CSS_SIZE_PROPS:
            return found
        opened = css.rfind("{", 0, found.start("prop"))
        if opened < 0:
            continue
        previous = max(css.rfind("}", 0, opened), css.rfind("{", 0, opened))
        if selector_reaches_box(css[previous + 1:opened], boxes):
            return found
    return None


def transformed_spans(source: str) -> list:
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        how = None
        if "transform" in attrs:
            how = "an ancestor <g>/<svg> transform"
        elif transform_carrier(attrs) is not None:
            how = "an ancestor <g>/<svg> style transform"
        events.append((match.start(), 0, how))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))
    stack, spans = [], []
    for position, kind, how in events:
        if kind == 0:
            stack.append((position, how))
        elif stack:
            start, was_transformed = stack.pop()
            if was_transformed:
                spans.append((start, position, was_transformed))
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source), was_transformed))
    return spans


def check_transforms(source: str, findings: list, name: str) -> None:
    boxes = [attrs for attrs in (attrs_of(m.group("attrs"))
                                 for m in RECT_RE.finditer(source))
             if attrs.get("data-role") == "box"]
    for match in STYLE_RE.finditer(source):
        css = blank_css_comments(match.group("body"))
        where = "%s:%d" % (name, line_of(source, match.start()))
        if selector_has_escape(css):
            findings.append(
                "%s: a <style> selector contains a backslash escape — "
                "an escaped selector can rename the element a size rule reaches"
                % where
            )
        elif css_moves_mark(css, boxes) is not None:
            findings.append(
                "%s: a <style> rule positions a mark with CSS "
                "(transform/translate/rotate/scale, a geometry or box-size "
                "property, or a motion path) — bake the offset into the attributes; a "
                "partial transform stack is worse than an honest refusal"
                % where
            )
    spans = transformed_spans(source)
    rects = list(RECT_RE.finditer(source))
    tagged = list(CIRCLE_RE.finditer(source)) + rects
    tagged += list(LINE_RE.finditer(source)) + list(TEXT_RE.finditer(source))
    tagged += groups_of(source)
    for match in tagged:
        attrs = attrs_of(match.group("attrs"))
        how = transform_carrier(attrs, sizes=match in rects)
        if how is not None:
            findings.append(
                "%s:%d: %s positions a mark — the checker reads raw "
                "coordinates, so anything applied afterwards invalidates "
                "the check that passed. Bake the offset into the attributes"
                % (name, line_of(source, match.start()), how)
            )
            continue
        for start, end, ancestor in spans:
            if start < match.start() < end:
                findings.append(
                    "%s:%d: %s positions a mark — the checker reads raw "
                    "coordinates, so anything applied afterwards invalidates "
                    "the check that passed. Bake the offset into the attributes"
                    % (name, line_of(source, match.start()), ancestor)
                )
                break


def first_rect(body: str, role: str):
    for match in RECT_RE.finditer(body):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == role and "stroke" in attrs:
            return attrs, match.start()
    return None, None


def lines_with_role(body: str, role: str) -> list:
    found = []
    for match in LINE_RE.finditer(body):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == role:
            found.append(attrs)
    return found


def declared_paints(style: str) -> list:
    return [match.group(1).strip()
            for match in PAINT_DECL_RE.finditer(blank_css_comments(style))]


def class_paints(source: str) -> dict:
    """class name -> fill/stroke values from a rule that names the class.

    `stroke:<class>` keys hold the stroke values alone.
    """
    found = {}
    for match in STYLE_RE.finditer(source):
        css = blank_css_comments(match.group("body"))
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            paints = declared_paints(rule.group(2))
            if not paints:
                continue
            for alternative in rule.group(1).split(","):
                compounds = [part for part in re.split(r"[\s>+~]+", alternative.strip())
                             if part]
                if not compounds:
                    continue
                subject = compounds[-1]
                typed = re.match(r"([A-Za-z][\w-]*)", subject)
                if typed and typed.group(1).lower() in NON_MARK_TAGS:
                    continue
                # `.hot rect` paints the rects under whatever carries
                # .hot, so an ancestor class counts as well as the subject's.
                strokes = STROKE_DECL_RE.findall(rule.group(2))
                for cls in re.findall(r"\.([\w-]+)", alternative):
                    found.setdefault(cls, []).extend(paints)
                    found.setdefault("stroke:" + cls, []).extend(
                        value.strip() for value in strokes)
    return found


def element_paints(attrs: dict, paints: dict) -> list:
    values = [attrs[key] for key in ("fill", "stroke") if key in attrs]
    values.extend(declared_paints(attrs.get("style", "")))
    for cls in attrs.get("class", "").split():
        values.extend(paints.get(cls, []))
    return values


def stroke_paints(attrs: dict, paints: dict) -> list:
    """Stroke values an element states itself (attribute, style, class)."""
    values = [attrs["stroke"]] if "stroke" in attrs else []
    values.extend(value.strip() for value in
                  STROKE_DECL_RE.findall(blank_css_comments(attrs.get("style", ""))))
    for cls in attrs.get("class", "").split():
        values.extend(paints.get("stroke:" + cls, []))
    return values


def wears_accent(attrs: dict, paints: dict) -> bool:
    return any(ACCENT_RE.search(value) for value in element_paints(attrs, paints))


def figure_paper(source: str):
    """Fill of the full-bleed paper rect, if this figure states one."""
    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("width", "").strip() != "100%":
            continue
        fill = attrs.get("fill", "").strip().lower()
        if fill.startswith("#"):
            return fill
    return None


def hides(attrs: dict) -> bool:
    if "hidden" in attrs:
        return True
    if attrs.get("visibility", "").strip().lower() in {"hidden", "collapse"}:
        return True
    if attrs.get("display", "").strip().lower() == "none":
        return True
    for key in ("opacity", "fill-opacity", "stroke-opacity"):
        raw = attrs.get(key)
        if raw is None:
            continue
        value = number(str(raw).strip().rstrip("%"))
        if value is not None and value <= 0:
            return True
    for match in HIDE_DECL_RE.finditer(blank_css_comments(attrs.get("style", ""))):
        prop, raw = match.group(1).lower(), match.group(2).strip().lower()
        if prop == "display" and raw == "none":
            return True
        if prop == "visibility" and raw in {"hidden", "collapse"}:
            return True
        if prop.endswith("opacity"):
            value = number(raw.rstrip("%"))
            if value is not None and value <= 0:
                return True
    return False


def positioned_tspan(body: str) -> bool:
    for match in TSPAN_RE.finditer(body):
        attrs = attrs_of(match.group("attrs"))
        if any(key in attrs for key in ("x", "y", "dx", "dy")):
            return True
    return False


def font_stylesheet(href: str) -> bool:
    return href.startswith("https://fonts.googleapis.com/")


def nonrendering_spans(source: str) -> list:
    events = [(m.start(), 0, m.group("tag").lower())
              for m in NONRENDER_OPEN_RE.finditer(source)
              if not m.group("selfclose")]
    events += [(m.start(), 1, m.group("tag").lower())
               for m in NONRENDER_CLOSE_RE.finditer(source)]
    events.sort(key=lambda event: (event[0], event[1]))
    stack, spans = [], []
    for position, kind, tag in events:
        if kind == 0:
            stack.append((tag, position))
        elif stack and stack[-1][0] == tag:
            spans.append((stack.pop()[1], position))
        elif stack:
            stack.pop()
    return spans


def axis_left(items: list, source: str) -> float:
    lefts = []
    for item in items:
        lefts.extend((item.box_x, item.wlo_x))
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-tick", "").strip().casefold() != "x":
            continue
        tick_x = number(attrs.get("x"))
        if tick_x is not None:
            lefts.append(tick_x)
    return min(lefts) if lefts else 0.0


def view_x_span(source: str) -> tuple:
    match = re.search(r"<svg\b(?P<attrs>[^>]*)>", source, re.IGNORECASE)
    raw = "0 0 1000 500"
    if match is not None:
        raw = attrs_of(match.group("attrs")).get("viewbox", raw)
    parts = [number(part) for part in raw.replace(",", " ").split()[:4]]
    if len(parts) == 4 and all(part is not None for part in parts) and parts[2] > 0:
        return parts[0], parts[0] + parts[2]
    return 0.0, 1000.0


def parse_series(source: str, findings: list, name: str) -> list:
    paints = class_paints(source)
    paper = figure_paper(source)
    series = []
    groups = groups_of(source)
    svgs = [attrs_of(m.group("attrs")) for m in GROUP_OPEN_RE.finditer(source)
            if m.group(0)[:4].lower() == "<svg"]
    for match in groups:
        raw = match.group("attrs")
        if not DECLARES_Q1_RE.search(raw):
            continue
        attrs = attrs_of(raw)
        where = "%s:%d" % (name, line_of(source, match.start()))
        keys = ("data-name", "data-q1", "data-q2", "data-q3", "data-wlo",
                "data-whi")
        missing = [key for key in keys if key not in attrs]
        if missing:
            findings.append(
                "%s: a box-plot series is missing %s — each series declares "
                "its name and the five-number summary"
                % (where, ", ".join(missing))
            )
            continue
        parsed = {
            "q1": number(attrs["data-q1"]),
            "q2": number(attrs["data-q2"]),
            "q3": number(attrs["data-q3"]),
            "wlo": number(attrs["data-wlo"]),
            "whi": number(attrs["data-whi"]),
        }
        if any(value is None for value in parsed.values()):
            findings.append(
                "%s: series %r has a five-number value that is not a finite "
                "number — cannot verify its geometry"
                % (where, attrs["data-name"])
            )
            continue
        body = match.group("body")
        body_at = match.body_at()
        box, _ = first_rect(body, "box")
        median_lines = lines_with_role(body, "median")
        whisker_lines = lines_with_role(body, "whisker-lo")
        whisker_hi_lines = lines_with_role(body, "whisker-hi")
        if box is None or not median_lines or not whisker_lines \
                or not whisker_hi_lines:
            findings.append(
                "%s: series %r is missing a stroked data-role=box rect, a "
                "data-role=median line, or a whisker-lo/whisker-hi pair"
                % (where, attrs["data-name"])
            )
            continue
        whisker_lo, whisker_hi = whisker_lines[0], whisker_hi_lines[0]
        medians = []
        bad_coord = False
        for median_line in median_lines:
            med_nums = [number(median_line.get(key)) for key in ("x1", "y1", "x2", "y2")]
            if any(value is None for value in med_nums):
                bad_coord = True
                break
            medians.append(tuple(med_nums))
        box_nums = [number(box.get(key)) for key in ("x", "y", "width", "height")]
        lo_nums = [number(whisker_lo.get(key)) for key in ("x1", "y1", "x2", "y2")]
        hi_nums = [number(whisker_hi.get(key)) for key in ("x1", "y1", "x2", "y2")]
        if bad_coord or any(value is None for value in box_nums + lo_nums + hi_nums):
            findings.append(
                "%s: series %r has a coordinate that is not a finite number"
                % (where, attrs["data-name"])
            )
            continue
        caps = []
        for cap in lines_with_role(body, "cap"):
            cap_xs = [number(cap.get(key)) for key in ("x1", "y1", "x2", "y2")]
            if any(value is None for value in cap_xs):
                findings.append(
                    "%s: series %r has a cap coordinate that is not a finite "
                    "number" % (where, attrs["data-name"])
                )
                continue
            caps.append(tuple(cap_xs))
        cy = box_nums[1] + box_nums[3] / 2.0
        # Paint inherits, so the series <g> itself and any nested group
        # count, and so does any shape the series draws, not only the
        # rect/line/circle marks bound above.
        accent = wears_accent(attrs, paints) or any(
            wears_accent(attrs_of(mark.group("attrs")), paints)
            for mark in OPEN_TAG_RE.finditer(body)
            if mark.group("tag").lower() not in NON_MARK_TAGS
        )
        outliers = []
        unbound = []
        for circle in CIRCLE_RE.finditer(body):
            cattrs = attrs_of(circle.group("attrs"))
            if "data-outlier" not in cattrs:
                unbound.append(cattrs)
                continue
            if "data-x" not in cattrs:
                findings.append(
                    "%s: an outlier on %r declares data-outlier but no "
                    "data-x — a visible mark with no bound value is never "
                    "checked" % (where, attrs["data-name"])
                )
                continue
            cx = number(cattrs.get("cx"))
            ccy = number(cattrs.get("cy"))
            value = number(cattrs.get("data-x"))
            if None in (cx, ccy, value):
                findings.append(
                    "%s: an outlier on %r has a value or coordinate that is "
                    "not a finite number"
                    % (where, attrs["data-name"])
                )
                continue
            outliers.append((value, cx, ccy))
        # Paint inherits: a mask that states no stroke of its own takes the
        # stroke of the series group, a group inside it, a wrapper around
        # it, or the <svg> itself.
        wrappers = [attrs_of(g.group("attrs")) for g in groups
                    if g.body_at() <= match.start() < g.body_at() + len(g.group("body"))]
        inherited = set()
        for holder in [attrs] + svgs + wrappers + [attrs_of(g.group("attrs"))
                                                   for g in G_OPEN_RE.finditer(body)]:
            inherited.update(value.strip().lower()
                             for value in stroke_paints(holder, paints))
        for cattrs in unbound:
            cx = number(cattrs.get("cx"))
            ccy = number(cattrs.get("cy"))
            fill = cattrs.get("fill", "").strip().lower()
            painted = {value.strip().lower()
                       for value in element_paints(cattrs, paints)}
            if not stroke_paints(cattrs, paints):
                painted |= inherited
            colocated = (
                cx is not None and ccy is not None
                and any(abs(cx - ox) <= 0.5 and abs(ccy - oy) <= 0.5
                        for _value, ox, oy in outliers)
            )
            if not (colocated and paper is not None and fill == paper
                    and painted <= {paper, "none"}):
                findings.append(
                    "%s: series %r has an unbound circle — a circle without "
                    "data-outlier must be a paper mask on a bound outlier"
                    % (where, attrs["data-name"])
                )
        labels = []
        for text in TEXT_RE.finditer(body):
            tattrs = attrs_of(text.group("attrs"))
            if "data-name" not in tattrs:
                continue
            labels.append((tattrs["data-name"], plain(text.group("body")),
                           number(tattrs.get("x")), number(tattrs.get("y"))))
            if "dx" in tattrs or "dy" in tattrs:
                findings.append(
                    "%s: series %r bound label carries dx/dy — a shift the "
                    "checked x/y attributes never state"
                    % (where, attrs["data-name"])
                )
            if positioned_tspan(text.group("body")):
                findings.append(
                    "%s: series %r bound label has a positioned <tspan> — "
                    "the visible name is not where x/y say it is"
                    % (where, attrs["data-name"])
                )
            if hides(tattrs) or any(
                    hides(attrs_of(tspan.group("attrs")))
                    for tspan in TSPAN_RE.finditer(text.group("body"))):
                findings.append(
                    "%s: series %r hides its bound label — the name the "
                    "checker reads is not the name a reader sees"
                    % (where, attrs["data-name"])
                )
        med_nums = medians[0]
        series.append(Series(
            name=attrs["data-name"],
            q1=parsed["q1"], q2=parsed["q2"], q3=parsed["q3"],
            wlo=parsed["wlo"], whi=parsed["whi"],
            cy=cy,
            box_x=box_nums[0], box_w=box_nums[2],
            box_y=box_nums[1], box_h=box_nums[3],
            median_x=med_nums[0], median_x2=med_nums[2],
            median_y=(med_nums[1], med_nums[3]),
            wlo_x=min(lo_nums[0], lo_nums[2]),
            wlo_inner=max(lo_nums[0], lo_nums[2]),
            whi_x=max(hi_nums[0], hi_nums[2]),
            whi_inner=min(hi_nums[0], hi_nums[2]),
            whisker_y=(lo_nums[1], lo_nums[3], hi_nums[1], hi_nums[3]),
            accent=accent,
            offset=match.start(),
            outliers=outliers,
            labels=labels,
            body_at=body_at,
            body_end=body_at + len(body),
            medians=medians,
            caps=caps,
        ))
    return series


def check_scale(items: list, findings: list, source: str, name: str):
    points = []
    for item in items:
        points.extend([
            (item.q1, item.box_x),
            (item.q3, item.box_x + item.box_w),
            (item.q2, item.median_x),
            (item.wlo, item.wlo_x),
            (item.whi, item.whi_x),
        ])
        for value, cx, _cy in item.outliers:
            points.append((value, cx))
    distinct = {(v, x) for v, x in points}
    if len({v for v, _x in distinct}) < 2:
        findings.append(
            "%s: every declared value is the same — a box plot needs a "
            "finite nonzero value axis" % name
        )
        return None
    slope, intercept = fit(list(distinct))
    if slope is None or abs(slope) < 1e-9:
        findings.append(
            "%s: the value axis is not a finite nonzero linear scale"
            % name
        )
        return None
    # Leave-one-out: dropping any one point must still recover this slope
    # within 5%, so one dishonest mark cannot set the line it is judged on.
    if len(distinct) >= 3:
        for skip in distinct:
            rest = [point for point in distinct if point != skip]
            other_slope, _ = fit(rest)
            if other_slope is None:
                continue
            if abs(other_slope - slope) > 0.05 * abs(slope):
                findings.append(
                    "%s: the shared value scale is unstable — leaving out "
                    "value %g moves the slope from %g to %g. One mark is "
                    "setting the line it is measured against"
                    % (name, skip[0], slope, other_slope)
                )
                break

    def at(value: float) -> float:
        return slope * value + intercept

    for item in items:
        where = "%s:%d" % (name, source.count("\n", 0, item.offset) + 1)
        median_drawn = max((item.median_x, item.median_x2),
                           key=lambda drawn: abs(drawn - at(item.q2)))
        checks = [
            ("q1", item.q1, item.box_x, "the box's left edge"),
            ("q3", item.q3, item.box_x + item.box_w, "the box's right edge"),
            ("q2", item.q2, median_drawn, "the median line"),
            ("wlo", item.wlo, item.wlo_x, "the low whisker"),
            ("q1", item.q1, item.wlo_inner, "the low whisker's box end"),
            ("whi", item.whi, item.whi_x, "the high whisker"),
            ("q3", item.q3, item.whi_inner, "the high whisker's box end"),
        ]
        for label, value, drawn, role in checks:
            expected = at(value)
            if abs(drawn - expected) > RESIDUAL_TOLERANCE:
                findings.append(
                    "%s: series %r %s is drawn at x=%g, but its declared "
                    "%s=%g sits at x=%g on the shared scale — move the "
                    "geometry, never the number"
                    % (where, item.name, role, drawn, label, value, expected)
                )
        for x1, _y1, x2, _y2 in item.medians[1:]:
            expected = at(item.q2)
            for drawn in (x1, x2):
                if abs(drawn - expected) > RESIDUAL_TOLERANCE:
                    findings.append(
                        "%s: series %r the median line is drawn at x=%g, but "
                        "its declared q2=%g sits at x=%g on the shared scale "
                        "— move the geometry, never the number"
                        % (where, item.name, drawn, item.q2, expected)
                    )
                    break
        if abs(item.box_w - abs(at(item.q3) - at(item.q1))) > RESIDUAL_TOLERANCE:
            findings.append(
                "%s: series %r box width is %g, but q3−q1 spans %gpx on the "
                "shared scale — width encodes the IQR"
                % (where, item.name, item.box_w,
                   abs(at(item.q3) - at(item.q1)))
            )
        iqr = item.q3 - item.q1
        fence_lo, fence_hi = item.q1 - TUKEY_K * iqr, item.q3 + TUKEY_K * iqr
        for value, cx, ccy in item.outliers:
            expected = at(value)
            if abs(cx - expected) > RESIDUAL_TOLERANCE:
                findings.append(
                    "%s: series %r outlier %g is drawn at x=%g, but the "
                    "shared scale puts it at x=%g"
                    % (where, item.name, value, cx, expected)
                )
            if abs(ccy - item.cy) > SAME_ROW_TOLERANCE:
                findings.append(
                    "%s: series %r outlier %g sits at y=%g, off the series "
                    "row y=%g — the category axis is a label rail"
                    % (where, item.name, value, ccy, item.cy)
                )
            if item.wlo - VALUE_TOLERANCE <= value <= item.whi + VALUE_TOLERANCE:
                findings.append(
                    "%s: series %r outlier %g sits inside the whiskers "
                    "[%g, %g] — an outlier is strictly outside the fence"
                    % (where, item.name, value, item.wlo, item.whi)
                )
            elif fence_lo - VALUE_TOLERANCE <= value <= fence_hi + VALUE_TOLERANCE:
                findings.append(
                    "%s: series %r outlier %g sits inside the Tukey fences "
                    "[%g, %g] (q1 − 1.5·IQR, q3 + 1.5·IQR) — it is an inlier, "
                    "and the whisker should reach it"
                    % (where, item.name, value, fence_lo, fence_hi)
                )
    return (slope, intercept, at)


def check_focal(items: list, findings: list, name: str) -> None:
    accents = [item for item in items if item.accent]
    if len(accents) > 1:
        findings.append(
            "%s: %d series wear the accent (a box, underlay, median, "
            "whisker, cap or outlier) — a box plot has at most "
            "one focal series" % (name, len(accents))
        )


def check_shapes(items: list, findings: list, source: str, name: str) -> None:
    """The perpendicular half of the geometry: the scale test reads only x."""
    for item in items:
        where = "%s:%d" % (name, line_of(source, item.offset))
        top, bottom = item.box_y, item.box_y + item.box_h
        for _x1, y1, _x2, y2 in item.medians:
            if abs(min(y1, y2) - top) > SAME_ROW_TOLERANCE \
                    or abs(max(y1, y2) - bottom) > SAME_ROW_TOLERANCE:
                findings.append(
                    "%s: series %r median runs y=%g..%g, but the box spans "
                    "y=%g..%g — the median crosses the box from edge to edge"
                    % (where, item.name, min(y1, y2), max(y1, y2), top, bottom)
                )
        ends = (item.wlo_x, item.whi_x)
        for x1, y1, x2, y2 in item.caps:
            if not any(abs(x1 - end) <= RESIDUAL_TOLERANCE
                       and abs(x2 - end) <= RESIDUAL_TOLERANCE for end in ends):
                findings.append(
                    "%s: series %r cap is drawn at x=%g, but the whiskers "
                    "end at x=%g and x=%g — a cap marks a whisker's end"
                    % (where, item.name, x1, item.wlo_x, item.whi_x)
                )
            low, high = min(y1, y2), max(y1, y2)
            if not (low - SAME_ROW_TOLERANCE <= item.cy <= high + SAME_ROW_TOLERANCE
                    and low >= top - SAME_ROW_TOLERANCE
                    and high <= bottom + SAME_ROW_TOLERANCE):
                findings.append(
                    "%s: series %r cap runs y=%g..%g, off the whisker at "
                    "y=%g inside the box's rows y=%g..%g — a cap crosses its "
                    "whisker end" % (where, item.name, low, high, item.cy,
                                     top, bottom)
                )
        if any(abs(y - item.cy) > SAME_ROW_TOLERANCE for y in item.whisker_y):
            findings.append(
                "%s: series %r has a whisker endpoint off the row centre "
                "y=%g — whiskers are horizontal through the middle of the box"
                % (where, item.name, item.cy)
            )
        iqr = item.q3 - item.q1
        fence_lo, fence_hi = item.q1 - TUKEY_K * iqr, item.q3 + TUKEY_K * iqr
        if item.wlo < fence_lo - VALUE_TOLERANCE or item.whi > fence_hi + VALUE_TOLERANCE:
            findings.append(
                "%s: series %r whiskers [%g, %g] reach past the Tukey fences "
                "[%g, %g] — a value past the fence is an outlier, not the "
                "whisker end" % (where, item.name, item.wlo, item.whi,
                                 fence_lo, fence_hi)
            )


def check_labels(items: list, findings: list, source: str, name: str) -> None:
    left = axis_left(items, source)
    view_lo, view_hi = view_x_span(source)
    xs = [label[2] for item in items if len(item.labels) == 1
          for label in (item.labels[0],) if label[2] is not None]
    rail = median(xs) if xs else None
    for item in items:
        where = "%s:%d" % (name, line_of(source, item.offset))
        if len(item.labels) != 1:
            findings.append(
                "%s: series %r has %d bound category labels (<text data-name>) "
                "— each series names itself with exactly one"
                % (where, item.name, len(item.labels))
            )
            continue
        bound, shown, x, y = item.labels[0]
        if bound.strip() != item.name.strip() or shown != item.name.strip():
            findings.append(
                "%s: series %r is labelled data-name=%r printing %r — the "
                "visible label must name the series it sits beside"
                % (where, item.name, bound, shown)
            )
        if y is None or abs(y - item.cy) > item.box_h / 2.0:
            findings.append(
                "%s: series %r label sits at y=%s, off its row at y=%g"
                % (where, item.name, "?" if y is None else "%g" % y, item.cy)
            )
        off_rail = (
            x is None or x < view_lo - 0.5 or x > view_hi + 0.5
            or x >= left - 0.5
            or (rail is not None and abs(x - rail) > 1.0)
        )
        if off_rail:
            findings.append(
                "%s: series %r label sits at x=%s, off the label rail "
                "(the category gutter left of the value axis at x=%g)"
                % (where, item.name, "?" if x is None else "%g" % x, left)
            )


def check_names(items: list, findings: list, name: str) -> None:
    seen = {}
    for item in items:
        key = item.name.strip()
        if not key:
            findings.append(
                "%s: a series has an empty data-name — identity is a map key"
                % name
            )
            continue
        if key in seen:
            findings.append(
                "%s: two series share data-name=%r — a name that identifies "
                "two marks identifies neither" % (name, key)
            )
        seen[key] = item
    total_outliers = sum(len(item.outliers) for item in items)
    if total_outliers > MAX_OUTLIERS:
        findings.append(
            "%s: %d outliers against a budget of %d — past that the tail is "
            "a list, not a story" % (name, total_outliers, MAX_OUTLIERS)
        )


def check_ticks(scale, source: str, findings: list, name: str) -> None:
    if scale is None:
        return
    _slope, _intercept, at = scale
    ticks = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-tick" not in attrs:
            continue
        axis = attrs.get("data-tick", "").strip().casefold()
        if axis != "x":
            findings.append(
                "%s:%d: a tick label has data-tick=%r — a box plot has one "
                "value axis (data-tick=\"x\"); the category axis is a label "
                "rail and has no scale to tick"
                % (name, line_of(source, match.start()), attrs.get("data-tick"))
            )
            continue
        declared = number(attrs.get("data-value"))
        x = number(attrs.get("x"))
        shown, reason = printed_number(plain(match.group("body")))
        if declared is None or x is None:
            findings.append(
                "%s:%d: a value-axis tick is missing a finite data-value or x"
                % (name, line_of(source, match.start()))
            )
            continue
        if shown is None:
            findings.append(
                "%s:%d: a value-axis tick %s"
                % (name, line_of(source, match.start()), reason)
            )
            continue
        if abs(shown - declared) > VALUE_TOLERANCE:
            findings.append(
                "%s:%d: a tick declares data-value=%g but prints %g"
                % (name, line_of(source, match.start()), declared, shown)
            )
        expected = at(declared)
        if abs(x - expected) > TICK_TOLERANCE:
            findings.append(
                "%s:%d: a tick for %g is drawn at x=%g, but the boxes' scale "
                "puts that value at x=%g"
                % (name, line_of(source, match.start()), declared, x, expected)
            )
        ticks.append(declared)
    if len(set(ticks)) < 2:
        findings.append(
            "%s: the value axis needs at least two bound ticks so the printed "
            "scale and the drawn boxes cannot drift apart" % name
        )


def inside_span(offset: int, spans: list) -> bool:
    return any(start <= offset < end for start, end in spans)


def check_structure(source: str, items: list, findings: list, name: str) -> None:
    """Carriers that move or hide a series without touching a checked attribute."""
    for match in FORBIDDEN_RE.finditer(source):
        tag = match.group("tag").lower()
        findings.append(
            "%s:%d: <%s> is unsupported — it can move a series after the "
            "checker has read its raw coordinates"
            % (name, line_of(source, match.start()), tag)
        )
    opens = [match.start() for match in re.finditer(r"<svg\b", source, re.IGNORECASE)]
    if len(opens) > 1:
        findings.append(
            "%s:%d: a nested <svg> viewport shifts the series it wraps "
            "without a transform on the marks"
            % (name, line_of(source, opens[1]))
        )
    for match in LINK_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        rel = attrs.get("rel", "").casefold().split()
        if "stylesheet" not in rel:
            continue
        if font_stylesheet(attrs.get("href", "").strip()):
            continue
        findings.append(
            "%s:%d: a stylesheet link other than the font link can restyle "
            "a box the attributes never state"
            % (name, line_of(source, match.start()))
        )
    hidden = nonrendering_spans(source)
    for item in items:
        if inside_span(item.offset, hidden):
            findings.append(
                "%s:%d: series %r is inside a non-rendering container — a "
                "copy in <defs> is not the series that gets drawn"
                % (name, line_of(source, item.offset), item.name)
            )
    spans = [(item.body_at, item.body_end) for item in items]
    for circle in CIRCLE_RE.finditer(source):
        cattrs = attrs_of(circle.group("attrs"))
        if "data-outlier" not in cattrs:
            continue
        owner = cattrs["data-outlier"].strip()
        home = any(
            item.name.strip() == owner
            and item.body_at <= circle.start() < item.body_end
            for item in items
        )
        if not home:
            findings.append(
                "%s:%d: a data-outlier circle for %r is not inside that "
                "series group — a mark read outside the group it names is "
                "never checked against the fence"
                % (name, line_of(source, circle.start()), owner)
            )
    for regex in (RECT_RE, LINE_RE):
        for match in regex.finditer(source):
            role = attrs_of(match.group("attrs")).get("data-role")
            if role not in MARK_ROLES or inside_span(match.start(), spans):
                continue
            findings.append(
                "%s:%d: a data-role=%r mark sits outside every series group "
                "— geometry the checker does not bind to a five-number summary"
                % (name, line_of(source, match.start()), role)
            )


def check_source(path: Path, raw: str) -> list:
    source = blank_comments(raw)
    findings: list = []
    name = path.name
    items = parse_series(source, findings, name)
    names_ok = True
    check_names(items, findings, name)
    check_structure(source, items, findings, name)
    if len(items) > MAX_SERIES:
        findings.append(
            "%s: %d series against a budget of %d-%d — split an overview "
            "from per-series detail"
            % (name, len(items), MIN_SERIES, MAX_SERIES)
        )
    elif len(items) < MIN_SERIES:
        findings.append(
            "%s: presents as a box plot but declares %d verifiable "
            "series — below %d there is no distribution to summarise, and a "
            "table says it shorter" % (name, len(items), MIN_SERIES)
        )
        names_ok = False
    if names_ok and items:
        for item in items:
            if not (item.wlo <= item.q1 <= item.q2 <= item.q3 <= item.whi):
                findings.append(
                    "%s:%d: series %r declares wlo=%g, q1=%g, q2=%g, q3=%g, "
                    "whi=%g — a five-number summary is ordered "
                    "wlo ≤ q1 ≤ q2 ≤ q3 ≤ whi"
                    % (name, source.count("\n", 0, item.offset) + 1, item.name,
                       item.wlo, item.q1, item.q2, item.q3, item.whi)
                )
        check_transforms(source, findings, name)
        scale = check_scale(items, findings, source, name)
        check_shapes(items, findings, source, name)
        check_labels(items, findings, source, name)
        check_focal(items, findings, name)
        check_ticks(scale, source, findings, name)
    elif items:
        check_transforms(source, findings, name)
    return findings


def check(path: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    if not looks_like_box_plot(path, raw):
        return []
    return check_source(path, raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify box-plot geometry against the five-number values "
                    "they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a box plot",
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
        if not looks_like_box_plot(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d box-plot finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK box plot: no box plot found to check%s" % tail)
        return 0
    print("OK box plot: %d file(s), every box, median, whisker and outlier "
          "exactly at its value on one shared scale, ordered five-number "
          "summaries, at most one accent series, and every bound tick agreeing "
          "with the mark it names%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
