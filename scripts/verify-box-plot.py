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

Nine invariants:

1. SHARED VALUE SCALE - every mark's position on the value axis must sit
   where one linear scale puts its declared value. The scale is derived from
   the distinct values (Theil-Sen, leave-one-out), so one dishonest mark
   cannot drag the line it is measured against.

2. FIVE-NUMBER ORDER - each series declares wlo ≤ q1 ≤ q2 ≤ q3 ≤ whi as
   finite numbers. A median outside its box, or a whisker that grows inward,
   is not a five-number summary.

3. BOX GEOMETRY - the stroked box rect's left edge is q1 and its right edge
   is q3 on that scale. Width is not decoration.

4. MEDIAN GEOMETRY - the median is a vertical line through the box at q2.

5. WHISKER GEOMETRY - whisker-lo runs from wlo to q1 and whisker-hi from q3
   to whi, both on the series' category coordinate.

6. OUTLIERS OUTSIDE THE WHISKERS - every outlier sits strictly outside
   [wlo, whi] on the value axis, at its declared value. An inlier drawn as a
   dot is a box plot wearing a beeswarm costume.

7. AT MOST ONE ACCENT SERIES - one focal claim per figure, on either skin.

8. UNPOSITIONED GEOMETRY - every coordinate read here is a raw attribute.
   A `transform` attribute, an inline `style`, or a rule in a <style> block
   on a mark, a bound label or tick, or an ancestor is refused rather than
   resolved, as in verify-beeswarm.py.

9. FAIL CLOSED - a file that presents as a box plot but yields fewer than
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
GROUP_RE = re.compile(r"<g\b(?P<attrs>[^>]*)>(?P<body>.*?)</g>",
                      re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
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
    r"|cx|cy|r|x|y"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_Q1_RE = re.compile(r"\bdata-q1\s*=", re.IGNORECASE)
ACCENT_RE = re.compile(
    r"#bf4520\b|#f08a59\b|rgba\(\s*191\s*,\s*69\s*,\s*32\b|"
    r"rgba\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)

RESIDUAL_TOLERANCE = 1.0
VALUE_TOLERANCE = 0.001
TICK_TOLERANCE = 6.0
SAME_ROW_TOLERANCE = 1.0
MIN_SERIES, MAX_SERIES = 3, 8
MAX_OUTLIERS = 8


class Series:
    __slots__ = (
        "name", "q1", "q2", "q3", "wlo", "whi", "cy", "box_x", "box_w",
        "box_y", "box_h", "median_x", "wlo_x", "whi_x", "accent", "offset",
        "outliers",
    )

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


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
        for match in GROUP_RE.finditer(source):
            if DECLARES_Q1_RE.search(match.group("attrs")):
                return True
    text = named_text(source)
    return "box plot" in text or "boxplot" in text.replace("-", " ")


def transform_carrier(attrs: dict):
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(style)
        if found is not None:
            return "style=%r (the %s property)" % (
                style, found.group("prop").lower()
            )
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
    for match in STYLE_RE.finditer(source):
        if CSS_MOVES_MARK_RE.search(match.group("body")):
            findings.append(
                "%s:%d: a <style> rule positions a mark with CSS "
                "(transform/translate/rotate/scale, a geometry property, or "
                "a motion path) — bake the offset into the attributes; a "
                "partial transform stack is worse than an honest refusal"
                % (name, line_of(source, match.start()))
            )
    spans = transformed_spans(source)
    tagged = list(CIRCLE_RE.finditer(source)) + list(RECT_RE.finditer(source))
    tagged += list(LINE_RE.finditer(source)) + list(TEXT_RE.finditer(source))
    tagged += list(GROUP_RE.finditer(source))
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
        for start, end, ancestor in spans:
            if start < match.start() < end:
                findings.append(
                    "%s:%d: %s positions a mark — the checker reads raw "
                    "coordinates, so anything applied afterwards invalidates "
                    "the check that passed. Bake the offset into the attributes"
                    % (name, line_of(source, match.start()), ancestor)
                )
                break


def first_line(body: str, role: str):
    for match in LINE_RE.finditer(body):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == role:
            return attrs, match.start()
    return None, None


def first_rect(body: str, role: str):
    for match in RECT_RE.finditer(body):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") == role and "stroke" in attrs:
            return attrs, match.start()
    return None, None


def parse_series(source: str, findings: list, name: str) -> list:
    series = []
    for match in GROUP_RE.finditer(source):
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
        box, _ = first_rect(body, "box")
        median_line, _ = first_line(body, "median")
        whisker_lo, _ = first_line(body, "whisker-lo")
        whisker_hi, _ = first_line(body, "whisker-hi")
        if box is None or median_line is None or whisker_lo is None \
                or whisker_hi is None:
            findings.append(
                "%s: series %r is missing a stroked data-role=box rect, a "
                "data-role=median line, or a whisker-lo/whisker-hi pair"
                % (where, attrs["data-name"])
            )
            continue
        box_nums = [number(box.get(key)) for key in ("x", "y", "width", "height")]
        med_nums = [number(median_line.get(key)) for key in ("x1", "y1", "x2", "y2")]
        lo_nums = [number(whisker_lo.get(key)) for key in ("x1", "y1", "x2", "y2")]
        hi_nums = [number(whisker_hi.get(key)) for key in ("x1", "y1", "x2", "y2")]
        if any(value is None for value in box_nums + med_nums + lo_nums + hi_nums):
            findings.append(
                "%s: series %r has a coordinate that is not a finite number"
                % (where, attrs["data-name"])
            )
            continue
        cy_candidates = [lo_nums[1], lo_nums[3], hi_nums[1], hi_nums[3],
                         box_nums[1] + box_nums[3] / 2.0]
        cy = median(cy_candidates)
        outliers = []
        for circle in CIRCLE_RE.finditer(body):
            cattrs = attrs_of(circle.group("attrs"))
            if "data-x" not in cattrs:
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
        series.append(Series(
            name=attrs["data-name"],
            q1=parsed["q1"], q2=parsed["q2"], q3=parsed["q3"],
            wlo=parsed["wlo"], whi=parsed["whi"],
            cy=cy,
            box_x=box_nums[0], box_w=box_nums[2],
            box_y=box_nums[1], box_h=box_nums[3],
            median_x=med_nums[0],
            wlo_x=min(lo_nums[0], lo_nums[2]),
            whi_x=max(hi_nums[0], hi_nums[2]),
            accent=bool(ACCENT_RE.search(box.get("stroke", ""))),
            offset=match.start(),
            outliers=outliers,
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
        checks = [
            ("q1", item.q1, item.box_x, "the box's left edge"),
            ("q3", item.q3, item.box_x + item.box_w, "the box's right edge"),
            ("q2", item.q2, item.median_x, "the median line"),
            ("wlo", item.wlo, item.wlo_x, "the low whisker"),
            ("whi", item.whi, item.whi_x, "the high whisker"),
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
        if abs(item.box_w - abs(at(item.q3) - at(item.q1))) > RESIDUAL_TOLERANCE:
            findings.append(
                "%s: series %r box width is %g, but q3−q1 spans %gpx on the "
                "shared scale — width encodes the IQR"
                % (where, item.name, item.box_w,
                   abs(at(item.q3) - at(item.q1)))
            )
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
    return (slope, intercept, at)


def check_focal(items: list, findings: list, name: str) -> None:
    accents = [item for item in items if item.accent]
    if len(accents) > 1:
        findings.append(
            "%s: %d series wear the accent stroke — a box plot has at most "
            "one focal series" % (name, len(accents))
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


def check_source(path: Path, raw: str) -> list:
    source = blank_comments(raw)
    findings: list = []
    name = path.name
    items = parse_series(source, findings, name)
    names_ok = True
    check_names(items, findings, name)
    for item in items:
        item  # names checked
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
