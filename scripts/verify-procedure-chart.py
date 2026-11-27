#!/usr/bin/env python3
"""Verify Procedure chart symbols, registry links, geometry and charted time.

A Procedure chart (references/type-procedure-chart.md, after AFMAN 38-102
§11.3 and Figure 11.4) declares its whole procedure in data attributes:

* one personnel column on the far left and one element column per
  organizational element (`data-proc-column`, `data-proc-column-id`);
* a procedure root block and one block per artifact and per activity, using
  the Traceable block decomposition attributes (`data-block-id`,
  `data-block-parent`, `data-block-name`) so `--registry` can export them;
* activity symbols (`data-proc-symbol`) on a personnel or a paperwork track;
* plain flow lines inside a column and arrowed, labelled handoffs between
  columns, each joining two activity IDs (`data-from`, `data-to`);
* a legend that names procedure-chart meanings only; and
* an optional illustrative event trace kept apart from the definition.

This checker reads that declaration back against what is drawn. It fails a
symbol whose mark is the wrong shape (a diamond that is not an inspection), a
personnel symbol Figure 11.4 does not define, an ID that is duplicated or does
not resolve, an activity outside its column or row, a line that does not join
its two symbols, a column change that is not a labelled handoff starting at a
move symbol, an artifact whose last symbol contradicts its declared final
disposition, a printed ID or charted time that disagrees with its declaration,
a legend that omits a used symbol or names a decision, a trace that carries
block IDs or points at nothing, and any procedure-chart vocabulary used in a
file that is not a procedure chart.

The plausible rendered error it exists for: a chart whose header says
"charted time 1 d 32 min" when its declared steps sum to 1 d 30 min, or a
diamond on a procedure chart that a reader takes for a decision.

Usage:
    python3 scripts/verify-procedure-chart.py --all
    python3 scripts/verify-procedure-chart.py path/to/diagram.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from html_comments import COMMENT_RE
from verify_static_svg_visibility import hidden, local

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL)

PAPERWORK = (
    "origination", "operation", "move", "delay", "file", "inspection",
    "information-take-off", "destroy", "gap", "cross-over", "item-change",
)
PERSONNEL = ("operation", "inspection", "move")
LEGEND_NAMES = {
    "origination": "Origination", "operation": "Operation", "move": "Move", "delay": "Delay",
    "file": "File", "inspection": "Inspection", "information-take-off": "Information take-off",
    "destroy": "Destroy", "gap": "Gap", "cross-over": "Cross over", "item-change": "Item change",
}
DISPOSITIONS = {"file": "filed", "destroy": "destroyed", "move": "moved out"}
HALF = {"personnel": 12, "paperwork": 10}  # symbol box half-size per track
TOLERANCE = 1.0

MAX_STEPS = 12
MAX_ELEMENT_COLUMNS = 4
MAX_ARTIFACTS = 3
MAX_HANDOFFS = 6
MAX_ACTIVITIES = 24

PATH_TOKEN = re.compile(r"[MLHVQAZmlhvqaz]|[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def fmt_minutes(total: int) -> str:
    days, rest = divmod(total, 1440)
    hours, minutes = divmod(rest, 60)
    parts = [f"{days} d" if days else "", f"{hours} h" if hours else "", f"{minutes} min" if minutes else ""]
    return " ".join(p for p in parts if p) or "0 min"


def text_of(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def num(value: str | None) -> float:
    try:
        parsed = float(value) if value is not None else math.nan
    except ValueError:
        return math.nan
    return parsed if math.isfinite(parsed) else math.nan


def whole(value: str | None) -> int | None:
    if value is None or not re.fullmatch(r"\d+", value.strip()):
        return None
    return int(value)


def points(value: str) -> list[tuple[float, float]]:
    numbers = [num(v) for v in re.split(r"[\s,]+", value.strip()) if v]
    if len(numbers) % 2 or any(math.isnan(v) for v in numbers):
        return []
    return list(zip(numbers[0::2], numbers[1::2]))


def path_commands(d: str) -> list[tuple[str, list[float]]] | None:
    """Absolute path commands with their numbers; None for anything unparsable."""
    tokens = PATH_TOKEN.findall(d)
    if PATH_TOKEN.sub("", d).strip(" ,\t\n\r") or not tokens or tokens[0] != "M":
        return None
    commands: list[tuple[str, list[float]]] = []
    for token in tokens:
        if token.isalpha():
            if token.islower() and token != "z":
                return None  # relative commands would hide where a stroke lands
            commands.append((token.upper(), []))
        else:
            commands[-1][1].append(float(token))
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "A": 7, "Z": 0}
    for command, args in commands:
        if command not in arity or (arity[command] and len(args) % arity[command]) or (
            not arity[command] and args
        ):
            return None
    return commands


def path_vertices(d: str) -> list[tuple[float, float]] | None:
    commands = path_commands(d)
    if commands is None:
        return None
    x = y = 0.0
    out: list[tuple[float, float]] = []
    for command, args in commands:
        if command in {"M", "L"}:
            for i in range(0, len(args), 2):
                x, y = args[i], args[i + 1]
                out.append((x, y))
        elif command == "H":
            for v in args:
                x = v
                out.append((x, y))
        elif command == "V":
            for v in args:
                y = v
                out.append((x, y))
        elif command == "Q":
            for i in range(0, len(args), 4):
                x, y = args[i + 2], args[i + 3]
                out.append((x, y))
        elif command == "A":
            for i in range(0, len(args), 7):
                x, y = args[i + 5], args[i + 6]
                out.append((x, y))
    return out


# ---------------------------------------------------------------------------
# Symbol shapes (Figure 11.4)
# ---------------------------------------------------------------------------


def close(a: float, b: float, tol: float = TOLERANCE) -> bool:
    return abs(a - b) <= tol


def within(pts: list[tuple[float, float]], cx: float, cy: float, half: float) -> bool:
    return bool(pts) and all(abs(px - cx) <= half + TOLERANCE and abs(py - cy) <= half + TOLERANCE for px, py in pts)


def is_diamond(pts: list[tuple[float, float]], cx: float, cy: float) -> bool:
    if len(pts) != 4:
        return False
    top, right, bottom, left = pts
    return (
        close(top[0], cx) and close(bottom[0], cx) and close(left[1], cy) and close(right[1], cy)
        and top[1] < cy < bottom[1] and left[0] < cx < right[0]
        and close(cy - top[1], bottom[1] - cy) and close(cx - left[0], right[0] - cx)
    )


def mark_shape(mark: ET.Element, cx: float, cy: float, half: float) -> str | None:
    """Name the Figure 11.4 symbol a mark draws, or None if it draws none."""
    tag = local(mark.tag)
    if tag == "circle":
        r = num(mark.get("r"))
        if close(num(mark.get("cx")), cx) and close(num(mark.get("cy")), cy) and 4 <= r <= half + TOLERANCE:
            return "operation"
        return None
    if tag == "rect":
        x, y, w, h = (num(mark.get(k)) for k in ("x", "y", "width", "height"))
        if close(w, h) and w >= 8 and close(x + w / 2, cx) and close(y + h / 2, cy) and w / 2 <= half + TOLERANCE:
            return "origination"
        return None
    if tag == "polygon":
        pts = points(mark.get("points", ""))
        if not within(pts, cx, cy, half):
            return None
        if is_diamond(pts, cx, cy):
            return "inspection"
        if len(pts) == 3:
            top_a, top_b, apex = pts
            if close(top_a[1], top_b[1]) and apex[1] > top_a[1] and close(apex[0], (top_a[0] + top_b[0]) / 2):
                return "file"
        if len(pts) == 7:
            tip = max(pts, key=lambda p: p[1])
            if close(tip[0], cx) and sum(1 for p in pts if close(p[1], tip[1])) == 1 and tip[1] > cy:
                return "move"
        if len(pts) == 4:
            a, b, c, d = pts
            if close(a[1], b[1]) and close(c[1], d[1]) and a[1] < c[1] and close(a[0], c[0]) and close(b[0], d[0]):
                return "gap"  # top edge, then a crossing back to the bottom edge: an hourglass
        return None
    if tag == "path":
        commands = path_commands(mark.get("d", ""))
        vertices = path_vertices(mark.get("d", ""))
        if commands is None or vertices is None or not within(vertices, cx, cy, half):
            return None
        letters = [c for c, _ in commands]
        if letters == ["M", "H", "A", "H", "Z"]:
            return "delay"
        if letters == ["M", "L", "L"]:
            (x0, y0), (x1, y1), (x2, y2) = vertices
            if close(x0, x2) and x1 > x0 and close(y1, cy) and y0 < y1 < y2:
                return "information-take-off"
        if letters == ["M", "L", "M", "L"]:
            (a, b), (c, d) = vertices[0:2], vertices[2:4]
            crosses = (a[0] - b[0]) * (c[0] - d[0]) < 0 and all(
                not close(p[0], q[0]) and not close(p[1], q[1]) for p, q in ((a, b), (c, d))
            )
            if crosses:
                return "destroy"
        if letters == ["M", "V", "A", "V"]:
            xs = {round(v[0], 3) for v in vertices}
            if len(xs) == 1:
                return "cross-over"
        if letters == ["M", "H", "M", "H"]:
            (a, b), (c, d) = vertices[0:2], vertices[2:4]
            if close(a[1], b[1]) and close(c[1], d[1]) and not close(a[1], c[1]):
                return "item-change"
        return None
    return None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def one_mark(group: ET.Element) -> ET.Element | None:
    marks = [e for e in group.iter() if e.get("data-role") == "mark"]
    return marks[0] if len(marks) == 1 else None


def check_svg(svg: ET.Element) -> list[str]:
    errors: list[str] = []
    parents = {child: parent for parent in svg.iter() for child in parent}

    def shown(element: ET.Element) -> bool:
        node: ET.Element | None = element
        while node is not None:
            if hidden(node) or "transform" in node.attrib or "transform" in node.get("style", ""):
                return False
            node = parents.get(node)
        return True

    def in_group(element: ET.Element, role: str) -> bool:
        node = parents.get(element)
        while node is not None:
            if node.get("data-role") == role:
                return True
            node = parents.get(node)
        return False

    # Columns ---------------------------------------------------------------
    columns = [e for e in svg.iter() if "data-proc-column-id" in e.attrib]
    column_by_id: dict[str, tuple[float, float, str, str]] = {}
    for c in columns:
        cid = c.get("data-proc-column-id", "").strip()
        kind = c.get("data-proc-column")
        x0, w = num(c.get("x")), num(c.get("width"))
        if not cid or cid in column_by_id:
            errors.append(f"blank or duplicate column id {cid!r}")
            continue
        if kind not in {"personnel", "element"} or local(c.tag) != "rect" or math.isnan(x0) or not w > 0:
            errors.append(f"column {cid!r} must be a rect with data-proc-column personnel or element")
            continue
        column_by_id[cid] = (x0, x0 + w, kind, c.get("data-proc-column-label", "").strip())
    personnel = [cid for cid, c in column_by_id.items() if c[2] == "personnel"]
    elements = [cid for cid, c in column_by_id.items() if c[2] == "element"]
    if len(personnel) != 1:
        errors.append(f"expected exactly one personnel column, found {len(personnel)}")
    if not 1 <= len(elements) <= MAX_ELEMENT_COLUMNS:
        errors.append(f"expected 1 to {MAX_ELEMENT_COLUMNS} element columns, found {len(elements)}")
    ordered = sorted(column_by_id.items(), key=lambda kv: kv[1][0])
    if ordered and ordered[0][1][2] != "personnel":
        errors.append("the personnel column must be the leftmost column")
    for (a_id, a), (b_id, b) in zip(ordered, ordered[1:]):
        if b[0] < a[1] - TOLERANCE:
            errors.append(f"columns {a_id!r} and {b_id!r} overlap")
    for cid, c in column_by_id.items():
        if c[2] == "element" and not c[3]:
            errors.append(f"element column {cid!r} has no data-proc-column-label")

    def column_of(x: float) -> str | None:
        for cid, (x0, x1, _, _) in column_by_id.items():
            if x0 < x < x1:
                return cid
        return None

    # Procedure root --------------------------------------------------------
    roots = [e for e in svg.iter() if e.get("data-proc-kind") == "procedure"]
    if len(roots) != 1:
        return errors + [f"expected one data-proc-kind=procedure root, found {len(roots)}"]
    root = roots[0]
    root_id = root.get("data-block-id", "").strip()
    if not root_id or not root.get("data-block-name", "").strip():
        errors.append("procedure root needs data-block-id and data-block-name")
    if "data-block-parent" in root.attrib:
        errors.append("procedure root must not declare a data-block-parent")

    block_ids: dict[str, ET.Element] = {}
    for e in svg.iter():
        if "data-block-id" in e.attrib:
            bid = e.get("data-block-id", "").strip()
            if not bid or bid in block_ids:
                errors.append(f"blank or duplicate data-block-id {bid!r}")
            block_ids[bid] = e

    # Artifacts -------------------------------------------------------------
    artifacts = {e.get("data-block-id", ""): e for e in svg.iter() if e.get("data-proc-kind") == "artifact"}
    if not 1 <= len(artifacts) <= MAX_ARTIFACTS:
        errors.append(f"expected 1 to {MAX_ARTIFACTS} artifacts, found {len(artifacts)}")
    for aid, art in artifacts.items():
        if art.get("data-block-parent") != root_id:
            errors.append(f"artifact {aid!r} must name the procedure root {root_id!r} as its parent")
        name = art.get("data-block-name", "").strip()
        copies = whole(art.get("data-proc-copies"))
        source = art.get("data-proc-source", "").strip()
        disposition = art.get("data-proc-disposition", "")
        if not name or not copies or not source or disposition not in DISPOSITIONS:
            errors.append(f"artifact {aid!r} needs a name, copies >= 1, a source and a disposition "
                          f"({', '.join(DISPOSITIONS)})")
            continue
        labels = [t for t in art.iter() if t.get("data-proc-label") == "artifact"]
        expected = (f"{aid} {name} · {'1 copy' if copies == 1 else f'{copies} copies'} · source {source} · "
                    f"{DISPOSITIONS[disposition]}")
        if len(labels) != 1 or text_of(labels[0]) != expected or not shown(labels[0]):
            errors.append(f"artifact {aid!r} must print {expected!r}")

    # Activities ------------------------------------------------------------
    activities: dict[str, dict] = {}
    for e in svg.iter():
        if "data-proc-symbol" not in e.attrib or in_group(e, "legend"):
            continue
        aid = e.get("data-block-id", "").strip()
        symbol, track = e.get("data-proc-symbol"), e.get("data-proc-track")
        where = f"activity {aid or '?'}"
        if not aid:
            errors.append("an activity has no data-block-id")
            continue
        if e.get("data-block-parent") != root_id:
            errors.append(f"{where}: data-block-parent must be the procedure root {root_id!r}")
        if track not in HALF:
            errors.append(f"{where}: data-proc-track must be personnel or paperwork")
            continue
        allowed = PERSONNEL if track == "personnel" else PAPERWORK
        if symbol not in allowed:
            errors.append(f"{where}: {symbol!r} is not a Figure 11.4 {track} symbol "
                          f"(allowed: {', '.join(allowed)})")
            continue
        step = whole(e.get("data-proc-step"))
        at = points(e.get("data-proc-at", ""))
        if not step or len(at) != 1:
            errors.append(f"{where}: needs data-proc-step >= 1 and data-proc-at=\"x y\"")
            continue
        x, y = at[0]
        if track == "personnel":
            column = personnel[0] if personnel else None
            role = e.get("data-proc-role", "")
            if role not in elements:
                errors.append(f"{where}: data-proc-role {role!r} must name an element column")
            artifact = None
        else:
            column = e.get("data-proc-column", "")
            role = column
            artifact = e.get("data-proc-artifact", "")
            if column not in elements:
                errors.append(f"{where}: data-proc-column {column!r} must name an element column")
            if artifact not in artifacts:
                errors.append(f"{where}: data-proc-artifact {artifact!r} does not resolve to an artifact")
        if column is not None and column_of(x) != column:
            errors.append(f"{where}: drawn at x={x:g}, outside its {column!r} column")
        mark = one_mark(e)
        if mark is None:
            errors.append(f"{where}: needs exactly one data-role=mark element")
        else:
            drawn = mark_shape(mark, x, y, HALF[track])
            if drawn == "inspection" and symbol != "inspection":
                errors.append(f"{where}: draws a diamond but declares {symbol!r}; on a procedure chart "
                              f"a diamond means inspection")
            elif drawn != symbol:
                errors.append(f"{where}: mark does not draw a {symbol!r} symbol centred on its data-proc-at")
            if not shown(mark):
                errors.append(f"{where}: symbol is hidden, transparent or transformed")
        comments = [t for t in e.iter() if t.get("data-proc-label") == "comment"]
        name = e.get("data-block-name", "").strip()
        if not name or len(comments) != 1 or text_of(comments[0]) != name or not shown(comments[0]):
            errors.append(f"{where}: must print its data-block-name as its comment")
        elapsed = e.get("data-proc-elapsed-min")
        distance = e.get("data-proc-distance-m")
        meta = [aid]
        if elapsed is not None:
            if track != "paperwork" or whole(elapsed) is None:
                errors.append(f"{where}: data-proc-elapsed-min is a whole number on paperwork symbols only")
            else:
                meta.append(fmt_minutes(int(elapsed)))
        if distance is not None:
            if symbol != "move" or whole(distance) is None:
                errors.append(f"{where}: data-proc-distance-m is a whole number on move symbols only")
            else:
                meta.append(f"{int(distance)} m")
        metas = [t for t in e.iter() if t.get("data-proc-label") == "meta"]
        if len(metas) != 1 or text_of(metas[0]) != " · ".join(meta) or not shown(metas[0]):
            errors.append(f"{where}: must print {' · '.join(meta)!r}")
        target = e.get("data-proc-target-artifact")
        if target is not None and (symbol != "information-take-off" or target not in artifacts or target == artifact):
            errors.append(f"{where}: data-proc-target-artifact belongs on an information take-off and must "
                          f"name another artifact")
        if symbol == "information-take-off" and target is None:
            errors.append(f"{where}: an information take-off must name its data-proc-target-artifact")
        activities[aid] = {"el": e, "symbol": symbol, "track": track, "step": step, "x": x, "y": y,
                           "column": role if track == "personnel" else column, "draw_column": column,
                           "artifact": artifact}
    if not activities:
        return errors + ["no activities declared"]
    if len(activities) > MAX_ACTIVITIES:
        errors.append(f"{len(activities)} activities exceeds the budget of {MAX_ACTIVITIES}")

    # Rows: every step present, one y per step, steps descend the page.
    steps = sorted({a["step"] for a in activities.values()})
    if steps != list(range(1, len(steps) + 1)):
        errors.append(f"steps must run 1..N without gaps, found {steps}")
    if len(steps) > MAX_STEPS:
        errors.append(f"{len(steps)} steps exceeds the budget of {MAX_STEPS}")
    row_y: dict[int, float] = {}
    for aid, a in activities.items():
        if a["step"] in row_y and not close(row_y[a["step"]], a["y"]):
            errors.append(f"activity {aid}: step {a['step']} is drawn on two rows")
        row_y.setdefault(a["step"], a["y"])
    ys = [row_y[s] for s in sorted(row_y)]
    if any(b <= a for a, b in zip(ys, ys[1:])):
        errors.append("rows must run down the page in step order")
    # One symbol per track per row: two personnel symbols in a row, or two
    # symbols on one artifact line in a row, would make the order ambiguous.
    seen_slots: set[tuple[int, str]] = set()
    for aid, a in activities.items():
        slot = (a["step"], a["artifact"] or "personnel")
        if slot in seen_slots:
            errors.append(f"activity {aid}: two symbols share step {a['step']} on one line")
        seen_slots.add(slot)

    # Lines: personnel track and one line per artifact ----------------------
    flows = [e for e in svg.iter() if e.get("data-proc-connector") == "flow"]
    handoffs = [e for e in svg.iter() if e.get("data-proc-connector") == "handoff"]
    flow_pairs: dict[tuple[str, str], ET.Element] = {}
    for f in flows:
        pair = (f.get("data-from", ""), f.get("data-to", ""))
        if pair in flow_pairs:
            errors.append(f"duplicate flow line {pair[0]} -> {pair[1]}")
        flow_pairs[pair] = f
    handoff_pairs: dict[tuple[str, str], ET.Element] = {}
    handoff_ids: set[str] = set()
    for h in handoffs:
        hid = h.get("data-proc-connector-id", "").strip()
        if not hid or hid in handoff_ids or hid in block_ids:
            errors.append(f"blank or duplicate handoff id {hid!r} (connector IDs live apart from block IDs)")
        handoff_ids.add(hid)
        handoff_pairs[(h.get("data-from", ""), h.get("data-to", ""))] = h
    if len(handoffs) > MAX_HANDOFFS:
        errors.append(f"{len(handoffs)} handoffs exceeds the budget of {MAX_HANDOFFS}")

    expected_flows: set[tuple[str, str]] = set()
    expected_handoffs: set[tuple[str, str]] = set()
    lines = {"personnel": sorted((a for a in activities if activities[a]["track"] == "personnel"),
                                 key=lambda a: activities[a]["step"])}
    for art in artifacts:
        lines[art] = sorted((a for a in activities if activities[a]["artifact"] == art),
                            key=lambda a: activities[a]["step"])
    for line_id, ids in lines.items():
        if line_id != "personnel":
            if not ids:
                errors.append(f"artifact {line_id!r} has no activities")
                continue
            disposition = artifacts[line_id].get("data-proc-disposition")
            last = activities[ids[-1]]["symbol"]
            if disposition in DISPOSITIONS and last != disposition:
                errors.append(f"artifact {line_id!r} declares disposition {disposition!r} but its last "
                              f"symbol is {last!r}")
            offsets = {round(activities[a]["x"] - column_by_id[activities[a]["draw_column"]][0], 3)
                       for a in ids if activities[a]["draw_column"] in column_by_id}
            if len(offsets) > 1:
                errors.append(f"artifact {line_id!r} changes its line offset between columns")
        for a, b in zip(ids, ids[1:]):
            if activities[a]["track"] == "personnel" or activities[a]["draw_column"] == activities[b]["draw_column"]:
                expected_flows.add((a, b))
            else:
                expected_handoffs.add((a, b))

    for pair in sorted(set(flow_pairs) - expected_flows):
        errors.append(f"flow line {pair[0]} -> {pair[1]} does not join consecutive symbols on one line "
                      f"in one column")
    for pair in sorted(expected_flows - set(flow_pairs)):
        errors.append(f"missing flow line {pair[0]} -> {pair[1]}")
    for pair in sorted(set(handoff_pairs) - expected_handoffs):
        errors.append(f"handoff {pair[0]} -> {pair[1]} does not join consecutive symbols of one artifact "
                      f"across two columns")
    for pair in sorted(expected_handoffs - set(handoff_pairs)):
        errors.append(f"artifact changes column between {pair[0]} and {pair[1]} without a declared handoff")

    def ends(a: dict, top: bool) -> tuple[float, float]:
        half = HALF[a["track"]]
        return a["x"], a["y"] - half if top else a["y"] + half

    for (fa, fb), f in flow_pairs.items():
        if (fa, fb) not in expected_flows:
            continue
        a, b = activities[fa], activities[fb]
        x1, y1, x2, y2 = (num(f.get(k)) for k in ("x1", "y1", "x2", "y2"))
        start, end = ends(a, top=False), ends(b, top=True)
        if (local(f.tag) != "line" or not (close(x1, start[0]) and close(y1, start[1]) and close(x2, end[0])
                                           and close(y2, end[1]))):
            errors.append(f"flow line {fa} -> {fb} must run straight down from {start} to {end}")
        if f.get("marker-end") or f.get("marker-start"):
            errors.append(f"flow line {fa} -> {fb} is a plain line; arrowheads belong to handoffs")
        if not shown(f):
            errors.append(f"flow line {fa} -> {fb} is hidden or transformed")

    labels = {g.get("data-proc-label-for", ""): g for g in svg.iter() if "data-proc-label-for" in g.attrib}
    for (ha, hb), h in handoff_pairs.items():
        if (ha, hb) not in expected_handoffs:
            continue
        hid = h.get("data-proc-connector-id", "")
        a, b = activities[ha], activities[hb]
        if a["symbol"] != "move":
            errors.append(f"handoff {hid}: must start at a move symbol, not {a['symbol']!r}")
        if h.get("data-proc-artifact") != a["artifact"]:
            errors.append(f"handoff {hid}: data-proc-artifact must be {a['artifact']!r}")
        if not h.get("marker-end"):
            errors.append(f"handoff {hid}: needs an arrowhead (marker-end)")
        vertices = path_vertices(h.get("d", "")) if local(h.tag) == "path" else None
        start, end = ends(a, top=False), ends(b, top=True)
        if not vertices or not (close(vertices[0][0], start[0]) and close(vertices[0][1], start[1])
                                and close(vertices[-1][0], end[0]) and close(vertices[-1][1], end[1])):
            errors.append(f"handoff {hid}: path must run from {start} to {end}")
        if not shown(h):
            errors.append(f"handoff {hid}: is hidden or transformed")
        label = labels.get(hid)
        want = (f"{hid} {column_by_id.get(a['draw_column'], (0, 0, '', '?'))[3]} → "
                f"{column_by_id.get(b['draw_column'], (0, 0, '', '?'))[3]}")
        if label is None or text_of(label) != want or not shown(label):
            errors.append(f"handoff {hid}: must carry a visible label reading {want!r}")
    for orphan in sorted(set(labels) - handoff_ids):
        errors.append(f"label for {orphan!r} names no handoff")

    # Header and charted time ----------------------------------------------
    total = sum(int(a["el"].get("data-proc-elapsed-min")) for a in activities.values()
                if whole(a["el"].get("data-proc-elapsed-min")) is not None)
    declared = whole(root.get("data-proc-elapsed-total-min"))
    if declared is not None and declared != total:
        errors.append(f"procedure declares {declared} charted minutes but its steps sum to {total}")
    headers = [t for t in root.iter() if t.get("data-proc-label") == "header"]
    date, analyst = root.get("data-proc-date", "").strip(), root.get("data-proc-analyst", "").strip()
    if not date or not analyst:
        errors.append("procedure root needs data-proc-date and data-proc-analyst (AFMAN 38-102 §11.3.4.1)")
    header = text_of(headers[0]) if len(headers) == 1 and shown(headers[0]) else ""
    for part in (root_id, date, analyst):
        if part and part not in header:
            errors.append(f"header must print {part!r}")
    if total and f"charted time {fmt_minutes(total)}" not in header:
        errors.append(f"header must print 'charted time {fmt_minutes(total)}', the sum of its steps")

    # Legend ------------------------------------------------------------------
    legend_entries = [e for e in svg.iter() if "data-proc-legend" in e.attrib]
    legend_symbols: set[str] = set()
    for entry in legend_entries:
        symbol = entry.get("data-proc-legend", "")
        label = text_of(entry)
        if "decision" in label.casefold():
            errors.append(f"legend entry {symbol!r} names a decision; a procedure chart legend never mixes "
                          f"in flowchart meanings")
        if symbol not in LEGEND_NAMES or symbol in legend_symbols:
            errors.append(f"unknown or duplicate legend entry {symbol!r}")
            continue
        legend_symbols.add(symbol)
        mark = one_mark(entry)
        if label != LEGEND_NAMES[symbol]:
            errors.append(f"legend entry {symbol!r} must read {LEGEND_NAMES[symbol]!r}, not {label!r}")
        if mark is None:
            errors.append(f"legend entry {symbol!r} has no mark")
            continue
        centre = points(entry.get("data-proc-at", ""))
        if len(centre) != 1 or mark_shape(mark, *centre[0], 12) != symbol:
            errors.append(f"legend entry {symbol!r} does not draw its own symbol")
        if not shown(entry):
            errors.append(f"legend entry {symbol!r} is hidden or transformed")
    for symbol in sorted({a["symbol"] for a in activities.values()} - legend_symbols):
        errors.append(f"legend is missing the {symbol!r} symbol used on the chart")
    for e in svg.iter():
        if e.get("data-kind") == "decision" or e.get("data-flowchart") is not None:
            errors.append("flowchart decision markup inside a procedure chart")

    # Illustrative trace -------------------------------------------------------
    traces = [e for e in svg.iter() if e.get("data-role") == "trace"]
    if len(traces) > 1:
        errors.append("at most one illustrative trace")
    for trace in traces:
        if trace.get("data-proc-illustrative") != "true":
            errors.append("trace must declare data-proc-illustrative=\"true\"")
        if "illustrative" not in text_of(trace).casefold():
            errors.append("trace must say it is illustrative in visible text")
        if any(k.startswith("data-block-") for e in trace.iter() for k in e.attrib):
            errors.append("trace carries data-block-* attributes; the trace stays apart from the definition")
        last_step = 0
        trace_ids: set[str] = set()
        for event in (e for e in trace.iter() if "data-proc-trace-id" in e.attrib):
            tid = event.get("data-proc-trace-id", "").strip()
            of = event.get("data-proc-trace-of", "")
            if not tid or tid in trace_ids or tid in block_ids:
                errors.append(f"blank or duplicate trace id {tid!r}")
            trace_ids.add(tid)
            if of not in activities:
                errors.append(f"trace {tid}: data-proc-trace-of {of!r} names no activity")
                continue
            if activities[of]["step"] < last_step:
                errors.append(f"trace {tid}: runs backwards through the procedure")
            last_step = activities[of]["step"]
            if of not in text_of(event):
                errors.append(f"trace {tid}: must print the activity ID it refers to")
    for e in svg.iter():
        if "data-proc-trace-id" in e.attrib and not in_group(e, "trace"):
            errors.append("trace events must sit inside the data-role=trace group")

    return errors


def check(path: Path) -> list[str]:
    source = COMMENT_RE.sub("", path.read_text(encoding="utf-8"))
    svgs = SVG_RE.findall(source)
    charts = [s for s in svgs if re.search(r'\bdata-diagram\s*=\s*"procedure-chart"', s)]
    if not charts:
        if "data-proc-" in source:
            return ["procedure-chart vocabulary (data-proc-*) used outside a procedure chart"]
        return []
    if len(charts) != 1 or len(svgs) != 1:
        return ["a procedure chart file holds exactly one <svg data-diagram=\"procedure-chart\">"]
    try:
        svg = ET.fromstring(charts[0])
    except ET.ParseError as exc:
        return [f"invalid SVG: {exc}"]
    return check_svg(svg)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true",
                        help="check every shipped asset: procedure charts in full, all others for stray vocabulary")
    args = parser.parse_args()
    paths = sorted(ASSETS.glob("*.html")) if args.all else args.paths
    if not paths:
        parser.error("provide files or --all")
    failed = False
    charts = 0
    for path in paths:
        errors = check(path)
        if 'data-diagram="procedure-chart"' in path.read_text(encoding="utf-8"):
            charts += 1
        for error in errors:
            failed = True
            print(f"{path}: {error}", file=sys.stderr)
    if args.all and charts == 0:
        print("no shipped procedure chart found", file=sys.stderr)
        failed = True
    if not failed:
        print(f"OK procedure chart: {len(paths)} file(s) checked, {charts} procedure chart(s)")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
