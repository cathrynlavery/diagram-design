#!/usr/bin/env python3
"""Verify no diagram label mask is clipped by a node painted after it.

SKILL.md §6 keeps an arrow label 6-10px clear of its connector, and §5 fixes the
paint order as background -> zones -> arrows -> labels -> nodes. Nothing keeps a
label mask off a *node*, so a label whose mask lands partly inside a node
rectangle that is painted later gets covered by the node fill: the text renders
as a fragment sitting on the node border.

Paint order is what makes this a defect rather than a stylistic choice:

* A mask overlapping a zone container is fine - zones are painted before labels,
  so the label stays on top. Zone eyebrows rely on this.
* A mask overlapping a node declared *later* in the document is clipped by that
  node. That is the failure this check reports.

Shape heuristics follow the shipped templates:

* A node is a `<rect>` at least 60x40 - large enough for a title and sublabel.
* A label mask is a `<rect>` 20-200 wide and 8-14 tall - the masking plate that
  SKILL.md §6 prescribes (markup in references/primitives-core.md) for arrow
  labels and zone eyebrows. The width cap covers the long mono plates shipped
  in example-sequence-oauth.html (128px) and the wider plates CJK labels need
  at the same glyph count.
* A mask fully contained in a node is a badge chip (`EXT`, `EDGE`, `ORIG`) and
  is legal.

It also checks connector routing (references/primitives-core.md rule 1). A
connector is a `<path>` or `<line>` that carries an arrow marker; a node, for
this check, is a stroked `<rect>` at least 60x40, so unstroked quadrant fills
and chart bars stay out of it. Five shapes are reported:

* A straight segment that is neither horizontal nor vertical. Loop write-back
  spokes (`class="spoke"`) are the documented radial exception and skipped.
* A horizontal or vertical segment lying on a node's border. It hides behind
  the node fill, so the arrow appears to start at the corner.
* A connector endpoint within 8px of a node corner, where the rounded corner
  makes the port ambiguous.
* Two connectors leaving (or two arriving at) the same edge of a node closer
  than primitives-core.md rule 4 allows: 12px, or 8px on an edge shorter than
  48px. A head-to-tail chain joint is allowed.
* Two connectors drawn within 1px of each other along a continuous stretch
  longer than 4px, straight or curved: the stacked trunk primitives-core.md
  rule 3 forbids. Curves and arcs are flattened into short chords so their
  shape is compared too. Forks and merges from one point count from that
  point; only a head-to-tail joint is exempt near the joint.

An arrowed path whose data the checker cannot parse is reported too, so a
connector never passes because nothing read it.

Usage:
    python3 scripts/verify-geometry.py --all
    python3 scripts/verify-geometry.py skills/diagram-design/assets/example-x.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

RECT_RE = re.compile(
    r"<rect\b[^>]*?"
    r'\bx="(?P<x>-?[\d.]+)"\s+'
    r'y="(?P<y>-?[\d.]+)"\s+'
    r'width="(?P<w>[\d.]+)"\s+'
    r'height="(?P<h>[\d.]+)"',
    re.IGNORECASE,
)

NODE_MIN_W = 60.0
NODE_MIN_H = 40.0
MASK_MIN_W = 20.0
MASK_MAX_W = 200.0
MASK_MIN_H = 8.0
MASK_MAX_H = 14.0
EPSILON = 0.5


class Rect:
    __slots__ = ("x", "y", "w", "h", "line", "offset")

    def __init__(self, x, y, w, h, line, offset) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h
        self.line, self.offset = line, offset

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def __repr__(self) -> str:
        return f"({self.x:g},{self.y:g} {self.w:g}x{self.h:g})"


def parse_rects(source: str) -> list[Rect]:
    rects: list[Rect] = []
    for match in RECT_RE.finditer(source):
        rects.append(
            Rect(
                float(match.group("x")),
                float(match.group("y")),
                float(match.group("w")),
                float(match.group("h")),
                source.count("\n", 0, match.start()) + 1,
                match.start(),
            )
        )
    return rects


def overlap(a: Rect, b: Rect) -> tuple[float, float]:
    return (
        min(a.right, b.right) - max(a.x, b.x),
        min(a.bottom, b.bottom) - max(a.y, b.y),
    )


def contained(inner: Rect, outer: Rect) -> bool:
    return (
        inner.x >= outer.x - EPSILON
        and inner.y >= outer.y - EPSILON
        and inner.right <= outer.right + EPSILON
        and inner.bottom <= outer.bottom + EPSILON
    )


TAG_RE = re.compile(
    r"<(?P<close>/?)(?P<tag>g|svg|rect|path|line)\b(?P<attrs>[^>]*?)(?P<empty>/?)>",
    re.IGNORECASE,
)
TRANSLATE_RE = re.compile(
    r"^\s*translate\(\s*([-+]?[\d.]+)(?:[\s,]+([-+]?[\d.]+))?\s*\)\s*$"
)
PATH_COMMAND_RE = re.compile(r"[\s,]*([MmLlHhVvQqCcSsTtAaZz])")
PATH_NUMBER_RE = re.compile(r"[\s,]*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
# Arc flags are one character and may run into the next number: `A 8 8 0 0120 20`.
PATH_FLAG_RE = re.compile(r"[\s,]*([01])")
PATH_END_RE = re.compile(r"[\s,]*$")
# Parameters each path command consumes per repetition.
PATH_ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "T": 2, "C": 6, "S": 4, "A": 7, "Z": 0}

AXIS_TOLERANCE = 0.5  # a segment this close to axis-aligned is orthogonal
BORDER_TOLERANCE = 1.0  # a segment this close to a node edge lies on it
BORDER_MIN_RUN = 4.0  # shorter shared runs are a port touching the edge, not a ride
PORT_TOLERANCE = 4.0  # an endpoint this close to a node outline attaches to it
CORNER_CLEARANCE = 8.0  # ports keep this far from a corner (primitives-core rule 1)
SHARED_PORT_MIN = 12.0  # two ports on one edge keep at least this far apart (rule 4)
SMALL_PORT_MIN = 8.0  # rule 4's floor for very small boxes...
SMALL_EDGE = 48.0  # ...meaning an edge shorter than this


def attribute(attrs: str, name: str) -> str | None:
    match = re.search(rf'(?<![\w-]){re.escape(name)}\s*=\s*"([^"]*)"', attrs)
    return match.group(1) if match else None


def number(attrs: str, name: str) -> float | None:
    value = attribute(attrs, name)
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


Segment = tuple[str, float, float, float, float]  # (kind, x1, y1, x2, y2)


CHORD_LENGTH = 2.0  # curves are flattened into chords about this long


def chord_count(points: list[tuple[float, float]]) -> int:
    """Chords to split a curve into, from the length of its control polygon."""

    length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
    return max(4, min(256, math.ceil(length / CHORD_LENGTH)))


def bezier(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Points along a quadratic or cubic Bezier, excluding its start."""

    steps = chord_count(points)
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        level = points
        while len(level) > 1:  # de Casteljau
            level = [
                (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                for a, b in zip(level, level[1:])
            ]
        out.append(level[0])
    return out


def arc(
    start: tuple[float, float], rx: float, ry: float, rotation: float,
    large: float, sweep: float, end: tuple[float, float],
) -> list[tuple[float, float]]:
    """Points along an SVG elliptical arc (SVG 2 appendix B.2.4), excluding its start."""

    (x1, y1), (x2, y2) = start, end
    rx, ry = abs(rx), abs(ry)
    if rx == 0 or ry == 0 or start == end:
        return [end]
    phi = math.radians(rotation)
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    hx, hy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos_p * hx + sin_p * hy, -sin_p * hx + cos_p * hy
    scale = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    denominator = (rx * y1p) ** 2 + (ry * x1p) ** 2
    numerator = (rx * ry) ** 2 - denominator
    root = math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    if large == sweep:
        root = -root
    cxp, cyp = root * rx * y1p / ry, -root * ry * x1p / rx
    cx = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2
    cy = sin_p * cxp + cos_p * cyp + (y1 + y2) / 2
    ux, uy = (x1p - cxp) / rx, (y1p - cyp) / ry
    vx, vy = (-x1p - cxp) / rx, (-y1p - cyp) / ry
    theta = math.atan2(uy, ux)
    delta = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(4, min(256, math.ceil(abs(delta) * max(rx, ry) / CHORD_LENGTH)))
    out = []
    for i in range(1, steps + 1):
        angle = theta + delta * i / steps
        ex, ey = rx * math.cos(angle), ry * math.sin(angle)
        out.append((cos_p * ex - sin_p * ey + cx, sin_p * ex + cos_p * ey + cy))
    out[-1] = end
    return out


def path_segments(d: str) -> list[Segment] | None:
    """Flatten a path into straight segments and curve chords, or None if unparseable.

    Straight commands become one `line` segment each. Curves and arcs become a
    run of short `curve` chords, so overlap checks can follow their shape.
    """

    segments: list[Segment] = []
    x = y = start_x = start_y = 0.0
    previous_control: tuple[str, float, float] | None = None  # for S and T reflection
    command = ""
    pos = 0
    while not PATH_END_RE.match(d, pos):
        match = PATH_COMMAND_RE.match(d, pos)
        if match:
            command, pos = match.group(1), match.end()
            if command in "Zz":
                if (x, y) != (start_x, start_y):
                    segments.append(("line", x, y, start_x, start_y))
                x, y = start_x, start_y
                continue
        elif not command or command in "Zz":
            return None  # numbers before the first command or after a closepath
        upper = command.upper()
        args: list[float] = []
        for slot in range(PATH_ARITY[upper]):
            pattern = PATH_FLAG_RE if upper == "A" and slot in (3, 4) else PATH_NUMBER_RE
            match = pattern.match(d, pos)
            if not match:
                return None  # truncated arguments or an unexpected character
            args.append(float(match.group(1)))
            pos = match.end()
        relative = command.islower()
        ox, oy = (x, y) if relative else (0.0, 0.0)
        if upper == "H":
            nx, ny = args[0] + ox, y
        elif upper == "V":
            nx, ny = x, args[0] + oy
        else:
            nx, ny = args[-2] + ox, args[-1] + oy
        if upper == "M":
            x, y = start_x, start_y = nx, ny
            command = "l" if relative else "L"  # implicit lineto after moveto
            previous_control = None
            continue
        if upper in "LHV":
            segments.append(("line", x, y, nx, ny))
            previous_control = None
        else:
            pairs = [(args[i] + ox, args[i + 1] + oy) for i in range(0, len(args) - 1, 2)]
            if upper in "ST":
                family = "C" if upper == "S" else "Q"
                if previous_control and previous_control[0] == family:
                    reflected = (2 * x - previous_control[1], 2 * y - previous_control[2])
                else:
                    reflected = (x, y)
                pairs = [reflected] + pairs
            if upper == "A":
                points = arc((x, y), args[0], args[1], args[2], args[3], args[4], (nx, ny))
                previous_control = None
            else:
                points = bezier([(x, y)] + pairs)
                family = "C" if upper in "CS" else "Q"
                previous_control = (family, pairs[-2][0], pairs[-2][1])
            px, py = x, y
            for qx, qy in points:
                segments.append(("curve", px, py, qx, qy))
                px, py = qx, qy
        x, y = nx, ny
    return segments


Offset = tuple[float, float]


def translation(attrs: str) -> Offset | None:
    """Offset a `transform` applies, (0, 0) when absent, None when not a translate."""

    transform = attribute(attrs, "transform")
    if transform is None:
        return 0.0, 0.0
    match = TRANSLATE_RE.match(transform)
    if not match:
        return None
    return float(match.group(1)), float(match.group(2) or 0.0)


def shapes(source: str):
    """Yield (tag, attrs, match start, offset) for each rect, path, and line.

    Offsets accumulate `translate()` on enclosing groups, so panels drawn with
    the same local coordinates (architecture delta snapshots) are compared in
    canvas space. Under any other transform, or inside a nested `<svg>` icon,
    the offset is None and the element is left out of connector checks.
    """

    stack: list[Offset | None] = []
    for match in TAG_RE.finditer(source):
        tag, attrs = match.group("tag").lower(), match.group("attrs")
        if tag in {"g", "svg"}:
            if match.group("close"):
                if stack:
                    stack.pop()
            elif not match.group("empty"):
                nested_svg = tag == "svg" and bool(stack)
                stack.append(None if nested_svg else translation(attrs))
            continue
        frame: Offset | None = (0.0, 0.0)
        for step in stack + [translation(attrs)]:
            if step is None or frame is None:
                frame = None
                break
            frame = (frame[0] + step[0], frame[1] + step[1])
        yield tag, attrs, match.start(), frame


def shifted(segments: list[Segment], frame: Offset) -> list[Segment]:
    dx, dy = frame
    return [(kind, x1 + dx, y1 + dy, x2 + dx, y2 + dy) for kind, x1, y1, x2, y2 in segments]


def connectors(source: str) -> list[tuple[int, str, list[Segment] | None]]:
    """Return (line number, short label, segments) for every arrowed connector.

    Segments are None for a path the parser cannot read, so the caller can
    fail closed instead of passing a connector nothing checked.
    """

    found: list[tuple[int, str, list[Segment] | None]] = []
    for tag, attrs, start, frame in shapes(source):
        if tag == "rect" or frame is None:
            continue
        if attribute(attrs, "marker-end") is None and attribute(attrs, "marker-start") is None:
            continue
        if "spoke" in (attribute(attrs, "class") or "").split():
            continue
        line = source.count("\n", 0, start) + 1
        if tag == "line":
            coords = [number(attrs, key) for key in ("x1", "y1", "x2", "y2")]
            if None in coords:
                continue
            x1, y1, x2, y2 = coords  # type: ignore[misc]
            segments: list[Segment] | None = [("line", x1, y1, x2, y2)]
            label = f"<line {x1:g},{y1:g} -> {x2:g},{y2:g}>"
        else:
            d = attribute(attrs, "d") or ""
            segments = path_segments(d)
            label = f'<path d="{d if len(d) <= 48 else d[:45] + "..."}">'
        if segments is None:
            found.append((line, label, None))
        elif segments:
            found.append((line, label, shifted(segments, frame)))
    return found


def stroked_nodes(source: str) -> list[Rect]:
    nodes: list[Rect] = []
    for tag, attrs, start, frame in shapes(source):
        if tag != "rect" or frame is None:
            continue
        x, y, w, h = (number(attrs, key) for key in ("x", "y", "width", "height"))
        if None in (x, y, w, h) or w < NODE_MIN_W or h < NODE_MIN_H:  # type: ignore[operator]
            continue
        stroke = (attribute(attrs, "stroke") or "none").strip().lower()
        if stroke in {"none", "transparent"} or number(attrs, "stroke-width") == 0:
            continue
        line = source.count("\n", 0, start) + 1
        nodes.append(Rect(x + frame[0], y + frame[1], w, h, line, start))
    return nodes


def rides_border(segment: Segment, node: Rect) -> str | None:
    _, x1, y1, x2, y2 = segment
    if abs(y1 - y2) <= AXIS_TOLERANCE:
        low, high = sorted((x1, x2))
        shared = min(high, node.right) - max(low, node.x)
        for edge, name in ((node.y, "top"), (node.bottom, "bottom")):
            if abs(y1 - edge) <= BORDER_TOLERANCE and shared > BORDER_MIN_RUN:
                return name
    if abs(x1 - x2) <= AXIS_TOLERANCE:
        low, high = sorted((y1, y2))
        shared = min(high, node.bottom) - max(low, node.y)
        for edge, name in ((node.x, "left"), (node.right, "right")):
            if abs(x1 - edge) <= BORDER_TOLERANCE and shared > BORDER_MIN_RUN:
                return name
    return None


def attached(px: float, py: float, node: Rect) -> bool:
    """True when an endpoint sits on (or just off) the node's outline."""

    outside_x = max(node.x - px, 0.0, px - node.right)
    outside_y = max(node.y - py, 0.0, py - node.bottom)
    inside = min(px - node.x, node.right - px, py - node.y, node.bottom - py)
    return max(outside_x, outside_y) <= PORT_TOLERANCE and inside <= PORT_TOLERANCE


def port_edge(px: float, py: float, node: Rect) -> tuple[str, float, float]:
    """Return (side, edge length, position along the edge) for an attached port."""

    distances = {
        "top": abs(py - node.y),
        "bottom": abs(py - node.bottom),
        "left": abs(px - node.x),
        "right": abs(px - node.right),
    }
    side = min(distances, key=distances.__getitem__)
    if side in {"top", "bottom"}:
        return side, node.w, px
    return side, node.h, py


def near_corner(px: float, py: float, node: Rect) -> tuple[float, float] | None:
    if not attached(px, py, node):
        return None
    for cx in (node.x, node.right):
        for cy in (node.y, node.bottom):
            if max(abs(px - cx), abs(py - cy)) < CORNER_CLEARANCE:
                return cx, cy
    return None


def check_connectors(path: Path, source: str) -> list[str]:
    nodes = stroked_nodes(source)
    findings: list[str] = []
    ports: list[tuple[int, float, float, int, str, str, int]] = []
    parsed: list[tuple[int, str, list[Segment]]] = []
    for ident, (line, label, segments) in enumerate(connectors(source)):
        where = f"{path.name}:{line}: connector {label}"
        if segments is None:
            findings.append(
                f"{where} has path data the checker cannot parse"
                f" - write it with absolute M/L/H/V/Q/C/A commands"
            )
            continue
        parsed.append((line, label, segments))
        for kind, x1, y1, x2, y2 in segments:
            if kind == "line" and abs(x1 - x2) > AXIS_TOLERANCE and abs(y1 - y2) > AXIS_TOLERANCE:
                findings.append(
                    f"{where} has a diagonal segment {x1:g},{y1:g} -> {x2:g},{y2:g}"
                    f" - route it as a rounded right-angle elbow"
                )
                break
        for segment in segments:
            if segment[0] != "line":
                continue
            hit = next(((node, side) for node in nodes if (side := rides_border(segment, node))), None)
            if hit:
                node, side = hit
                findings.append(
                    f"{where} runs along the {side} border of node {node} (line {node.line})"
                    f" - leave the node perpendicular to the edge the port sits on"
                )
                break
        ends = ((segments[0][1], segments[0][2]), (segments[-1][3], segments[-1][4]))
        for px, py in ends:
            corner = next(((node, c) for node in nodes if (c := near_corner(px, py, node))), None)
            if corner:
                node, (cx, cy) = corner
                findings.append(
                    f"{where} attaches at {px:g},{py:g}, within {CORNER_CLEARANCE:g}px of the"
                    f" {cx:g},{cy:g} corner of node {node} (line {node.line})"
                    f" - move the port onto the straight part of the edge"
                )
                break
        for (px, py), role in zip(ends, ("start", "end")):
            for index, node in enumerate(nodes):
                if attached(px, py, node):
                    ports.append((index, px, py, line, label, role, ident))
    findings.extend(shared_ports(path, nodes, ports))
    findings.extend(stacked_connectors(path, parsed))
    return findings


STACK_TOLERANCE = 1.0  # strokes this close are drawn on top of each other
SAMPLE_STEP = 1.0  # distance between samples when measuring a shared run


def bounds(segments: list[Segment], pad: float) -> tuple[float, float, float, float]:
    xs = [v for _, x1, _, x2, _ in segments for v in (x1, x2)]
    ys = [v for _, _, y1, _, y2 in segments for v in (y1, y2)]
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad


def distance_to_segment(px: float, py: float, segment: Segment) -> float:
    _, x1, y1, x2, y2 = segment
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    t = 0.0 if not length_sq else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def shared_run(a: list[Segment], b: list[Segment]) -> float:
    """Longest continuous stretch of connector `a` drawn within 1px of connector `b`.

    Straight runs and curve chords count alike, so a shared curved trunk is
    caught as well as a straight one. The run must be continuous: two separate
    right-angle crossings each touch for a pixel or two and never add up to a
    shared trunk. Only a head-to-tail joint, where one arrow ends and the
    other starts, is exempt near the joint; a fork or merge from one shared
    point is measured from that point.
    """

    left, top, right, bottom = bounds(b, STACK_TOLERANCE)
    a_left, a_top, a_right, a_bottom = bounds(a, 0.0)
    if a_right < left or a_left > right or a_bottom < top or a_top > bottom:
        return 0.0
    a_start, a_end = (a[0][1], a[0][2]), (a[-1][3], a[-1][4])
    b_start, b_end = (b[0][1], b[0][2]), (b[-1][3], b[-1][4])
    joints = [
        joint
        for joint, other in ((a_end, b_start), (a_start, b_end))
        if math.dist(joint, other) <= STACK_TOLERANCE
    ]
    boxes = [bounds([segment], STACK_TOLERANCE) for segment in b]

    def near(px: float, py: float) -> bool:
        if not (left <= px <= right and top <= py <= bottom):
            return False
        if any(math.dist((px, py), joint) < CORNER_CLEARANCE for joint in joints):
            return False
        return any(
            bx0 <= px <= bx1 and by0 <= py <= by1
            and distance_to_segment(px, py, segment) <= STACK_TOLERANCE
            for segment, (bx0, by0, bx1, by1) in zip(b, boxes)
        )

    longest = run = 0
    for _, x1, y1, x2, y2 in a:
        steps = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / SAMPLE_STEP))
        for i in range(steps):
            if near(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps):
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return longest * SAMPLE_STEP


def stacked_connectors(
    path: Path, parsed: list[tuple[int, str, list[Segment]]]
) -> list[str]:
    """Report two connectors drawn on top of each other (primitives-core rule 3)."""

    findings: list[str] = []
    for i, (line_a, label_a, segments_a) in enumerate(parsed):
        for line_b, label_b, segments_b in parsed[i + 1 :]:
            shared = max(shared_run(segments_a, segments_b), shared_run(segments_b, segments_a))
            if shared > BORDER_MIN_RUN:
                findings.append(
                    f"{path.name}:{line_b}: connector {label_b} runs on top of {label_a}"
                    f" (line {line_a}) for about {shared:g}px - offset one route by at least"
                    f" {SHARED_PORT_MIN:g}px so each arrow stays traceable"
                )
    return findings


def shared_ports(
    path: Path, nodes: list[Rect], ports: list[tuple[int, float, float, int, str, str, int]]
) -> list[str]:
    """Report two connectors leaving, or two arriving, at one point on a node.

    A head-to-tail joint, where one arrow lands and the next leaves, is a chain
    the reader traces in order (Medallion's documented promotion joints), so it
    is not reported. Two starts are a fork and two ends are a merge.
    """

    findings: list[str] = []
    for i, (node_a, ax, ay, line_a, label_a, role_a, id_a) in enumerate(ports):
        for node_b, bx, by, line_b, label_b, role_b, id_b in ports[i + 1 :]:
            if node_a != node_b or id_a == id_b or role_a != role_b:
                continue
            node = nodes[node_a]
            side_a, length, along_a = port_edge(ax, ay, node)
            side_b, _, along_b = port_edge(bx, by, node)
            if side_a != side_b:
                continue
            minimum = SMALL_PORT_MIN if length < SMALL_EDGE else SHARED_PORT_MIN
            gap = abs(along_a - along_b)
            if gap < minimum:
                findings.append(
                    f"{path.name}:{line_b}: connector {label_b} attaches {gap:g}px from"
                    f" {label_a} (line {line_a}) on the {side_a} edge of node {node}"
                    f" (line {node.line}) - fan the ports at least {minimum:g}px apart"
                )
    return findings


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    rects = parse_rects(source)
    nodes = [r for r in rects if r.w >= NODE_MIN_W and r.h >= NODE_MIN_H]
    masks = [
        r
        for r in rects
        if MASK_MIN_W <= r.w <= MASK_MAX_W and MASK_MIN_H <= r.h <= MASK_MAX_H
    ]

    findings: list[str] = []
    for mask in masks:
        for node in nodes:
            if node.offset <= mask.offset:
                continue  # painted before the label; the label stays on top
            dx, dy = overlap(mask, node)
            if dx <= 1.0 or dy <= 1.0 or contained(mask, node):
                continue
            findings.append(
                f"{path.name}:{mask.line}: label mask {mask} is clipped by node "
                f"{node} declared later at line {node.line} (overlap {dx:g}x{dy:g}px)"
                f" - move the label onto a free segment of its connector"
            )
            break
    findings.extend(check_connectors(path, source))
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    for path in paths:
        if not path.exists():
            findings.append(f"{path}: file not found")
            continue
        findings.extend(check(path))

    for finding in findings:
        print(finding)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
