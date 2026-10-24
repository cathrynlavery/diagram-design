#!/usr/bin/env python3
"""Verify that an arc diagram's drawn arcs match the spans they declare.

An arc diagram makes one hard claim: nodes sit on one baseline at one shared
pitch, and every pairwise import is a semicircle whose height is exactly how
many seats it skips. Both halves can be broken without anything erroring: a
decorative tall arc on a neighbour reads as a skip-layer import, and a node
nudged off the pitch makes two spans of the same count draw at two heights.

`lint-skin.py` reads colors and fonts and `verify-geometry.py` reads label
masks; neither compares a drawn radius against the span bound to it.

Nine invariants:

1. ONE BASELINE - every node shares one y. The line is a seat rail, not a
   value axis; a node off the rail is a different layout grammar.

2. ONE PITCH - consecutive nodes, ordered by x, share one spacing. Height
   can only encode span when a seat is a constant.

3. SEMICIRCLE ARCS - each arc is `M x1,y A r,r 0 0 1 x2,y` with y on the
   baseline, sweep 1 (the arc rises in SVG coordinates), and r equal to
   half the endpoint distance. A quadratic that peaks wherever the author
   liked is not this variant.

4. SPAN IS THE SEAT COUNT - `data-span` equals how many seats sit between
   the two named nodes, inclusive of the far one (`|i-j|`). r must also
   equal pitch · span / 2, so a neighbour cannot wear a skip's height.

5. ENDPOINTS ARE THE NAMED NODES - the path starts and ends at the `data-from`
   / `data-to` node x positions. A path that names Auth and Checkout but
   lands on Catalog is a different import.

6. AT MOST ONE ACCENT ARC - one focal claim per figure, on either skin.

7. UNPOSITIONED GEOMETRY - every coordinate read here is a raw attribute.
   A `transform` attribute, an inline `style`, or a rule in a <style> block
   on a mark, a bound label, or an ancestor is refused rather than resolved.

8. BOUND NAMES, BOTH WAYS - every node circle has exactly one label bound
   to the same `data-name`, the visible text matches, and the name is
   non-empty and unique.

9. FAIL CLOSED - a file that presents as an arc diagram but yields fewer
   than four nodes or three arcs is a finding, never a pass. Four nodes
   give three pitches, which is the minimum that can confirm a shared seat.

Vocabulary treaty: `data-span` ON A <path> is the arc-diagram contract.
`data-value` on a <circle> is the beeswarm contract, `data-size` is bubble,
`data-series` is slopegraph and `data-ranks` is bump — none of them are
bound here, so no sibling checker claims an arc-diagram file and this one
claims none of theirs.

Usage:
    python3 scripts/verify-arc-diagram.py --all
    python3 scripts/verify-arc-diagram.py skills/diagram-design/assets/example-arc-diagram.html

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
PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>",
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
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_SPAN_RE = re.compile(r"\bdata-span\s*=", re.IGNORECASE)
ACCENT_RE = re.compile(
    r"#bf4520\b|#f08a59\b|rgba\(\s*191\s*,\s*69\s*,\s*32\b|"
    r"rgba\(\s*240\s*,\s*138\s*,\s*89\b",
    re.IGNORECASE,
)
ARC_D_RE = re.compile(
    r"^\s*M\s*(?P<x1>-?\d+(?:\.\d+)?)\s*,\s*(?P<y1>-?\d+(?:\.\d+)?)"
    r"\s*A\s*(?P<rx>-?\d+(?:\.\d+)?)\s*,\s*(?P<ry>-?\d+(?:\.\d+)?)"
    r"\s+(?P<rot>-?\d+(?:\.\d+)?)\s+(?P<large>[01])\s+(?P<sweep>[01])"
    r"\s+(?P<x2>-?\d+(?:\.\d+)?)\s*,\s*(?P<y2>-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)

COORD_TOLERANCE = 1.0
PITCH_TOLERANCE = 1.0
MIN_NODES, MAX_NODES = 4, 9
MIN_ARCS, MAX_ARCS = 3, 14


class Node:
    __slots__ = ("name", "cx", "cy", "r", "offset")

    def __init__(self, **kw):
        for key, value in kw.items():
            setattr(self, key, value)


class Arc:
    __slots__ = (
        "frm", "to", "span", "x1", "y1", "x2", "y2", "rx", "ry",
        "sweep", "accent", "offset",
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


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def named_text(source: str) -> str:
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_arc_diagram(path: Path, source: str) -> bool:
    """Does this file present itself as an arc diagram?

    Filename, accessible name, or a <path> that binds data-span. The
    element restriction is the treaty line — a source-wide data-span
    search is fine here because no sibling binds that attribute.
    """
    if path.name.startswith("example-arc-diagram"):
        return True
    if DECLARES_SPAN_RE.search(source):
        for match in PATH_RE.finditer(source):
            if DECLARES_SPAN_RE.search(match.group("attrs")):
                return True
    text = named_text(source)
    return "arc diagram" in text or "arcdiagram" in text.replace("-", " ")


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
    tagged = list(CIRCLE_RE.finditer(source)) + list(PATH_RE.finditer(source))
    tagged += list(TEXT_RE.finditer(source))
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


def parse_nodes(source: str, findings: list, name: str) -> list:
    nodes = []
    for match in CIRCLE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-name" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        cx = number(attrs.get("cx"))
        cy = number(attrs.get("cy"))
        radius = number(attrs.get("r"))
        label = attrs["data-name"].strip()
        if not label:
            findings.append(
                "%s: a node has an empty data-name — identity is a map key"
                % where
            )
            continue
        if None in (cx, cy, radius):
            findings.append(
                "%s: node %r has a coordinate that is not a finite number"
                % (where, label)
            )
            continue
        if radius <= 0:
            findings.append(
                "%s: node %r has r=%g — an invisible node is an uncounted "
                "omission" % (where, label, radius)
            )
            continue
        nodes.append(Node(name=label, cx=cx, cy=cy, r=radius, offset=match.start()))
    return nodes


def parse_arcs(source: str, findings: list, name: str) -> list:
    arcs = []
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        if not DECLARES_SPAN_RE.search(raw):
            continue
        attrs = attrs_of(raw)
        where = "%s:%d" % (name, line_of(source, match.start()))
        missing = [key for key in ("data-from", "data-to", "data-span", "d")
                   if key not in attrs]
        if missing:
            findings.append(
                "%s: an arc is missing %s — each arc declares the two nodes "
                "it joins, the seat-count it spans, and a path"
                % (where, ", ".join(missing))
            )
            continue
        span = number(attrs["data-span"])
        if span is None or span != int(span) or span < 1:
            findings.append(
                "%s: data-span=%r is not a positive integer seat count"
                % (where, attrs["data-span"])
            )
            continue
        parsed = ARC_D_RE.match(attrs["d"].strip())
        if parsed is None:
            findings.append(
                "%s: arc %s→%s is not a semicircle of the form "
                "M x1,y A r,r 0 0 1 x2,y — bake a rising semicircle into d"
                % (where, attrs["data-from"], attrs["data-to"])
            )
            continue
        nums = {key: number(parsed.group(key))
                for key in ("x1", "y1", "x2", "y2", "rx", "ry", "rot")}
        if any(value is None for value in nums.values()):
            findings.append(
                "%s: arc %s→%s has a coordinate that is not a finite number"
                % (where, attrs["data-from"], attrs["data-to"])
            )
            continue
        if nums["rot"] != 0 or parsed.group("large") != "0":
            findings.append(
                "%s: arc %s→%s uses a rotated or large-arc flag — this "
                "variant is a rising semicircle (rotation 0, large-arc 0, "
                "sweep 1)" % (where, attrs["data-from"], attrs["data-to"])
            )
            continue
        if parsed.group("sweep") != "1":
            findings.append(
                "%s: arc %s→%s has sweep=0 — sweep 1 rises above the "
                "baseline; sweep 0 draws the import under the seats"
                % (where, attrs["data-from"], attrs["data-to"])
            )
            continue
        fill = (attrs.get("fill") or "").strip().casefold()
        if fill not in ("none", "transparent"):
            findings.append(
                "%s: arc %s→%s has fill=%r — an arc is a stroke, not a wedge; "
                "set fill=\"none\""
                % (where, attrs["data-from"], attrs["data-to"],
                   attrs.get("fill", "(omitted, defaults to black)"))
            )
            continue
        arcs.append(Arc(
            frm=attrs["data-from"].strip(),
            to=attrs["data-to"].strip(),
            span=int(span),
            x1=nums["x1"], y1=nums["y1"], x2=nums["x2"], y2=nums["y2"],
            rx=nums["rx"], ry=nums["ry"],
            sweep=parsed.group("sweep"),
            accent=bool(ACCENT_RE.search(attrs.get("stroke", ""))),
            offset=match.start(),
        ))
    return arcs


def check_names(nodes: list, source: str, findings: list, name: str) -> dict:
    seen = {}
    for node in nodes:
        if node.name in seen:
            findings.append(
                "%s: two nodes share data-name=%r — a name that identifies "
                "two marks identifies neither" % (name, node.name)
            )
        seen[node.name] = node

    labels = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-name" not in attrs:
            continue
        label = attrs["data-name"].strip()
        body = plain(match.group("body"))
        x = number(attrs.get("x"))
        if label in labels:
            findings.append(
                "%s:%d: a second label for %r — one name, one label"
                % (name, line_of(source, match.start()), label)
            )
            continue
        labels[label] = (body, x, match.start())

    for node_name, node in seen.items():
        if node_name not in labels:
            findings.append(
                "%s: node %r has no bound label — a binding nothing "
                "cross-checks" % (name, node_name)
            )
            continue
        body, x, _offset = labels[node_name]
        if body.casefold() != node_name.casefold():
            findings.append(
                "%s: label for %r prints %r — the visible text has to match "
                "the binding" % (name, node_name, body)
            )
        if x is not None and abs(x - node.cx) > COORD_TOLERANCE:
            findings.append(
                "%s: label for %r sits at x=%g, off the node at x=%g"
                % (name, node_name, x, node.cx)
            )
    for label in labels:
        if label not in seen:
            findings.append(
                "%s: a label names %r, which is not a node"
                % (name, label)
            )
    return seen


def check_geometry(nodes: list, arcs: list, findings: list, name: str) -> None:
    if len(nodes) < MIN_NODES:
        return
    ordered = sorted(nodes, key=lambda node: node.cx)
    baseline = median([node.cy for node in ordered])
    for node in ordered:
        if abs(node.cy - baseline) > COORD_TOLERANCE:
            findings.append(
                "%s: node %r sits at y=%g, off the baseline y=%g — the "
                "line is a seat rail" % (name, node.name, node.cy, baseline)
            )

    pitches = [ordered[i + 1].cx - ordered[i].cx for i in range(len(ordered) - 1)]
    if any(p <= 0 for p in pitches):
        findings.append(
            "%s: two nodes share an x (or reverse order) — seats are a "
            "strict left-to-right rail" % name
        )
        return
    pitch = median(pitches)
    if pitch < 1:
        findings.append(
            "%s: the shared seat pitch is not a finite positive spacing"
            % name
        )
        return
    for gap in pitches:
        if abs(gap - pitch) > PITCH_TOLERANCE:
            findings.append(
                "%s: consecutive seats are spaced %gpx and %gpx — arc height "
                "can only encode span when the pitch is shared"
                % (name, pitch, gap)
            )
            break

    index = {node.name: i for i, node in enumerate(ordered)}
    by_name = {node.name: node for node in ordered}

    for arc in arcs:
        where = "%s" % name
        if arc.frm not in by_name or arc.to not in by_name:
            missing = [n for n in (arc.frm, arc.to) if n not in by_name]
            findings.append(
                "%s: arc %s→%s names %s, which is not a node"
                % (where, arc.frm, arc.to, ", ".join(missing))
            )
            continue
        if arc.frm == arc.to:
            findings.append(
                "%s: arc %s→%s joins a node to itself — a span of zero is "
                "not an import" % (where, arc.frm, arc.to)
            )
            continue
        expected_span = abs(index[arc.frm] - index[arc.to])
        if arc.span != expected_span:
            findings.append(
                "%s: arc %s→%s declares data-span=%d but the seats are %d "
                "apart — span is |i−j| on the rail"
                % (where, arc.frm, arc.to, arc.span, expected_span)
            )
        left = min(by_name[arc.frm].cx, by_name[arc.to].cx)
        right = max(by_name[arc.frm].cx, by_name[arc.to].cx)
        ends = sorted([arc.x1, arc.x2])
        if abs(ends[0] - left) > COORD_TOLERANCE or abs(ends[1] - right) > COORD_TOLERANCE:
            findings.append(
                "%s: arc %s→%s is drawn from x=%g to x=%g, but those nodes "
                "sit at x=%g and x=%g — move the path, never the names"
                % (where, arc.frm, arc.to, arc.x1, arc.x2,
                   by_name[arc.frm].cx, by_name[arc.to].cx)
            )
        if abs(arc.y1 - baseline) > COORD_TOLERANCE or abs(arc.y2 - baseline) > COORD_TOLERANCE:
            findings.append(
                "%s: arc %s→%s leaves the baseline (y=%g / %g vs %g)"
                % (where, arc.frm, arc.to, arc.y1, arc.y2, baseline)
            )
        expected_r = abs(right - left) / 2.0
        span_r = pitch * arc.span / 2.0
        if abs(arc.rx - expected_r) > COORD_TOLERANCE or abs(arc.ry - expected_r) > COORD_TOLERANCE:
            findings.append(
                "%s: arc %s→%s has r=%g, but a semicircle between its "
                "nodes has r=%g — height encodes the skip"
                % (where, arc.frm, arc.to, arc.rx, expected_r)
            )
        elif abs(arc.rx - span_r) > COORD_TOLERANCE:
            findings.append(
                "%s: arc %s→%s has r=%g, but span %d at pitch %g wants "
                "r=%g — a neighbour cannot wear a skip's height"
                % (where, arc.frm, arc.to, arc.rx, arc.span, pitch, span_r)
            )


def check_focal(arcs: list, findings: list, name: str) -> None:
    accents = [arc for arc in arcs if arc.accent]
    if len(accents) > 1:
        findings.append(
            "%s: %d arcs wear the accent stroke — an arc diagram has at "
            "most one focal import" % (name, len(accents))
        )


def check_source(path: Path, raw: str) -> list:
    source = blank_comments(raw)
    findings: list = []
    name = path.name
    nodes = parse_nodes(source, findings, name)
    arcs = parse_arcs(source, findings, name)
    check_names(nodes, source, findings, name)
    if len(nodes) > MAX_NODES:
        findings.append(
            "%s: %d nodes against a budget of %d-%d — split an overview "
            "from per-cluster detail"
            % (name, len(nodes), MIN_NODES, MAX_NODES)
        )
    elif len(nodes) < MIN_NODES:
        findings.append(
            "%s: presents as an arc diagram but declares %d verifiable "
            "node(s) — below %d there is no rail to skip along"
            % (name, len(nodes), MIN_NODES)
        )
    if len(arcs) > MAX_ARCS:
        findings.append(
            "%s: %d arcs against a budget of %d — past that the figure is "
            "a hairball, not a span story" % (name, len(arcs), MAX_ARCS)
        )
    elif len(arcs) < MIN_ARCS:
        findings.append(
            "%s: presents as an arc diagram but declares %d verifiable "
            "arc(s) — below %d there is no skip to compare against a "
            "neighbour" % (name, len(arcs), MIN_ARCS)
        )
    if len(nodes) >= MIN_NODES and len(arcs) >= MIN_ARCS:
        check_transforms(source, findings, name)
        check_geometry(nodes, arcs, findings, name)
        check_focal(arcs, findings, name)
    elif nodes or arcs:
        check_transforms(source, findings, name)
    return findings


def check(path: Path) -> list:
    raw = path.read_text(encoding="utf-8")
    if not looks_like_arc_diagram(path, raw):
        return []
    return check_source(path, raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify arc-diagram geometry against the spans the arcs declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as an arc diagram",
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
        if not looks_like_arc_diagram(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d arc-diagram finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK arc diagram: no arc diagram found to check%s" % tail)
        return 0
    print("OK arc diagram: %d file(s), every arc a rising semicircle on one "
          "shared pitch, span equal to the seat count, at most one accent "
          "import, and every bound label agreeing with the node it names%s"
          % (checked, tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
