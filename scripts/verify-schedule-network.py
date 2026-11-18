#!/usr/bin/env python3
"""Recompute CPM and check the bounded, visible Schedule network SVG contract.

This checks the authored schedule and its static marks, not the truth of source
estimates, resource feasibility, calendars or arbitrary prose outside the SVG.
"""

from __future__ import annotations

import argparse
import copy
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from verify_static_svg_visibility import check_static_svg, local, rectangle

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b[^>]*>.*?</svg\s*>", re.S | re.I)
DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?\Z")
PATH_TOKEN = re.compile(r"[MLHVQ]|[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)")
FIELDS = ("name", "duration", "es", "ef", "ls", "lf", "tf", "status")
ROOT_DATA = {
    "data-diagram-type",
    "data-time-unit",
    "data-project-duration",
    "data-schedule-origin",
}
DATA = ROOT_DATA | {
    "data-task-id",
    "data-task-name",
    "data-duration",
    "data-critical",
    "data-rank",
    "data-diagram-role",
    "data-schedule-field",
    "data-schedule-link",
    "data-from",
    "data-to",
    "data-schedule-summary",
}


def decimal(value: str, *, aggregate: bool = False) -> Decimal:
    pattern = (
        re.compile(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,6})?\Z")
        if aggregate
        else DECIMAL
    )
    if not pattern.fullmatch(value):
        raise ValueError(f"expected bounded nonnegative decimal, got {value!r}")
    return Decimal(value)


def printed(value: Decimal) -> str:
    return (
        format(value, "f").rstrip("0").rstrip(".")
        if "." in format(value, "f")
        else str(value)
    )


def calculate(durations: dict[str, Decimal], edges: list[tuple[str, str]]) -> dict:
    """Exact forward/backward pass; all critical tasks and tight critical edges."""
    if not 2 <= len(durations) <= 8 or not 1 <= len(edges) <= 12:
        raise ValueError("expected 2..8 tasks and 1..12 precedence links")
    if any(
        not d.is_finite() or d <= 0 or not DECIMAL.fullmatch(format(d, "f"))
        for d in durations.values()
    ):
        raise ValueError("duration must be a bounded positive finite decimal")
    if len(set(edges)) != len(edges) or any(
        a not in durations or b not in durations or a == b for a, b in edges
    ):
        raise ValueError("duplicate, self or unresolved precedence link")
    pred = {k: [] for k in durations}
    succ = {k: [] for k in durations}
    for a, b in edges:
        pred[b].append(a)
        succ[a].append(b)
    reached = set()
    pending = [next(iter(durations))]
    while pending:
        k = pending.pop()
        if k in reached:
            continue
        reached.add(k)
        pending.extend(pred[k] + succ[k])
    if reached != set(durations):
        raise ValueError("schedule must be connected")
    order = []
    todo = set(durations)
    while todo:
        ready = sorted(k for k in todo if not set(pred[k]) & todo)
        if not ready:
            raise ValueError("precedence graph has a cycle")
        order.extend(ready)
        todo.difference_update(ready)
    result = {}
    for k in order:
        es = max((result[p]["ef"] for p in pred[k]), default=Decimal(0))
        rank = max((result[p]["rank"] + 1 for p in pred[k]), default=0)
        result[k] = {"es": es, "ef": es + durations[k], "rank": rank}
    if max(t["rank"] for t in result.values()) >= 5:
        raise ValueError("more than five precedence ranks")
    finish = max(result[k]["ef"] for k in durations if not succ[k])
    for k in reversed(order):
        lf = min((result[s]["ls"] for s in succ[k]), default=finish)
        ls = lf - durations[k]
        result[k].update(lf=lf, ls=ls, tf=ls - result[k]["es"])
    critical = {k for k, t in result.items() if t["tf"] == 0}
    return {
        "finish": finish,
        "tasks": result,
        "critical_edges": {
            (a, b)
            for a, b in edges
            if a in critical and b in critical and result[a]["ef"] == result[b]["es"]
        },
    }


class Attributes(HTMLParser):
    """Catch duplicate attributes before XML parsing or browser repair hides them."""

    def __init__(self):
        super().__init__()
        self.errors = []

    def handle_starttag(self, tag, attrs):
        names = [a for a, _ in attrs]
        if len(names) != len(set(names)):
            self.errors.append(f"duplicate attribute on {tag}")

    handle_startendtag = handle_starttag


def points(source: str, *, rounded: bool) -> list[tuple[float, float]]:
    """Absolute line/rounded-elbow path; Q is bounded by its orthogonal hull."""
    if not re.fullmatch(r"[\s,]*", PATH_TOKEN.sub("", source)):
        raise ValueError("unsupported arrow path command or number")
    tokens = PATH_TOKEN.findall(source)
    out = []
    i = 0
    x = y = 0.0
    while i < len(tokens):
        command = tokens[i]
        i += 1
        count = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4}.get(command)
        if (
            count is None
            or i + count > len(tokens)
            or (not out and command != "M")
            or (out and command == "M")
        ):
            raise ValueError("invalid arrow path")
        try:
            values = list(map(float, tokens[i : i + count]))
        except ValueError as exc:
            raise ValueError("invalid arrow number") from exc
        if not all(math.isfinite(v) for v in values):
            raise ValueError("nonfinite arrow point")
        i += count
        if command == "Q":
            if not rounded:
                raise ValueError("arrowhead must be a three-point V")
            cx, cy, nx, ny = values
            first = (cx - x, cy - y)
            second = (nx - cx, ny - cy)
            if (
                sorted(map(abs, first)) != [0, 8]
                or sorted(map(abs, second)) != [0, 8]
                or first[0] * second[0] + first[1] * second[1] != 0
            ):
                raise ValueError("rounded elbow must have perpendicular 8px legs")
            out.append((cx, cy))
            x, y = nx, ny
        elif command in ("M", "L"):
            x, y = values
        elif command == "H":
            x = values[0]
        else:
            y = values[0]
        out.append((x, y))
    if len(out) < 2:
        raise ValueError("arrow must have visible length")
    if rounded and any(
        a == b or a[0] != b[0] and a[1] != b[1] for a, b in zip(out, out[1:])
    ):
        raise ValueError("precedence shaft must be orthogonal and nonzero")
    return out


def intersects(a, b, box):
    # Shafts/control hulls are orthogonal. Strict interiors avoid false border hits.
    left, top, right, bottom = box
    if a[0] == b[0]:
        return left < a[0] < right and max(min(a[1], b[1]), top) < min(
            max(a[1], b[1]), bottom
        )
    return top < a[1] < bottom and max(min(a[0], b[0]), left) < min(
        max(a[0], b[0]), right
    )


def text_value(node):
    if list(node):
        raise ValueError(
            "bound labels must be plain visible text without child elements"
        )
    return (node.text or "").strip()


def number(node, key):
    try:
        value = float(node.get(key, ""))
    except ValueError:
        raise ValueError(f"missing or invalid {key}")
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    if not re.search(
        r"data-(?:diagram-type\s*=\s*[\"\']schedule-network|task-id\s*=|schedule-link\s*=)",
        source,
        re.I,
    ):
        return (
            ["canonical Schedule network file is missing its contract"]
            if path.name
            in {
                f"example-schedule-network{suffix}.html"
                for suffix in ("", "-dark", "-full")
            }
            else []
        )
    try:
        return check_source(source)
    except (
        ValueError,
        InvalidOperation,
        ET.ParseError,
        KeyError,
        OverflowError,
    ) as exc:
        return [str(exc)]


def check_source(source: str) -> list[str]:
    parser = Attributes()
    parser.feed(source)
    if parser.errors:
        return parser.errors
    matches = SVG_RE.findall(source)
    if len(matches) != 1:
        raise ValueError("schedule requires exactly one SVG")
    svg = ET.fromstring(matches[0])
    if svg.get("data-diagram-type") != "schedule-network":
        raise ValueError("missing schedule-network root declaration")
    if set(k for k in svg.attrib if k.startswith("data-")) != ROOT_DATA:
        raise ValueError("unsupported or missing schedule root data")
    if svg.get("data-schedule-origin") != "0":
        raise ValueError("schedule origin must be zero")
    unit = svg.get("data-time-unit", "")
    if not re.fullmatch(r"[a-z]{1,8}", unit):
        raise ValueError("duration unit must be 1..8 lowercase letters")
    declared_finish = decimal(svg.get("data-project-duration", ""), aggregate=True)
    for node in svg.iter():
        if any(k.startswith("data-") and k not in DATA for k in node.attrib):
            raise ValueError("unsupported scheduling data/constraint")
        if "style" in node.attrib or "class" in node.attrib:
            raise ValueError(
                "SVG marks must use presentation attributes, not inline style or class"
            )
    original_parents = {c: p for p in svg.iter() for c in p}
    tasks = {}
    durations = {}
    boxes = {}
    for node in svg.iter():
        if "data-task-id" not in node.attrib:
            continue
        if original_parents.get(node) is not svg:
            raise ValueError("task must be a direct visible child of the root SVG")
        id = node.get("data-task-id", "")
        name = node.get("data-task-name", "")
        if local(node.tag) != "g" or node.get("data-diagram-role") != "task":
            raise ValueError("task must be a task-role group")
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,5}", id) or id in tasks:
            raise ValueError("missing, invalid or duplicate task ID")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 -]{0,17}", name):
            raise ValueError("task name must be 1..18 ASCII characters")
        durations[id] = decimal(node.get("data-duration", ""))
        tasks[id] = node
        rects = [c for c in node if local(c.tag) == "rect"]
        if len(rects) != 1:
            raise ValueError("task needs one visible box")
        box = rectangle(rects[0])
        boxes[id] = box
        width = box[2] - box[0]
        if (
            box[3] - box[1] != 176
            or not 192 <= width <= 240
            or rects[0].get("rx") != "4"
        ):
            raise ValueError("task boxes must share bounded fixed grid dimensions")
    links = [n for n in svg.iter() if "data-schedule-link" in n.attrib]
    edges = []
    for n in links:
        if original_parents.get(n) is not svg:
            raise ValueError(
                "precedence link must be a direct visible child of the root SVG"
            )
        if (
            local(n.tag) != "g"
            or n.get("data-schedule-link") != "finish-to-start"
            or n.get("data-diagram-role") != "precedence"
        ):
            raise ValueError("only finish-to-start precedence groups supported")
        edges.append((n.get("data-from", ""), n.get("data-to", "")))
    model = calculate(durations, edges)
    if declared_finish != model["finish"]:
        raise ValueError("project finish disagrees with recomputed terminal EF")
    proxy = copy.deepcopy(svg)
    for key in ROOT_DATA - {"data-diagram-type"}:
        proxy.attrib.pop(key)
    parents = {c: p for p in proxy.iter() for c in p}
    # Independent geometry parsing happens before the visibility-only adapter.
    for n in proxy.iter():
        if local(n.tag) == "path":
            parent = parents[n]
            children = list(parent)
            pts = points(n.get("d", ""), rounded=children.index(n) == 0)
            n.set("d", "M " + " L ".join(f"{x:g} {y:g}" for x, y in pts))
    errors = check_static_svg(
        source,
        proxy,
        parents,
        "data-task-id",
        "data-task-id",
        link_attr="data-schedule-link",
    )
    backdrop = next((c for c in svg if local(c.tag) == "rect"), None)
    if backdrop is None:
        raise ValueError("missing full-paper SVG backdrop")
    paper = backdrop.get("fill")
    ink, muted = (
        ("#f5f5f5", "#bfc0c0") if paper == "#2d3142" else ("#2d3142", "#4f5d75")
    )
    widths = set()
    rank_x = {}
    for id, node in tasks.items():
        values = model["tasks"][id]
        critical = values["tf"] == 0
        if node.get("data-critical") != str(critical).lower():
            errors.append(f"{id}: critical task flag disagrees with total float")
        if node.get("data-rank") != str(values["rank"]):
            errors.append(f"{id}: wrong precedence rank")
        box = boxes[id]
        x, y = box[:2]
        width = box[2] - x
        widths.add(width)
        rank_x.setdefault(values["rank"], set()).add(x)
        rect = next(c for c in node if local(c.tag) == "rect")
        if rect.get("stroke") != ink or rect.get("stroke-width") != (
            "2" if critical else "1"
        ):
            errors.append(f"{id}: task border must encode critical status in ink")
        fields = {}
        for child in node:
            if local(child.tag) == "rect":
                continue
            field = child.get("data-schedule-field")
            if local(child.tag) != "text" or field not in FIELDS or field in fields:
                raise ValueError(
                    f"{id}: missing, duplicate or unsupported printed field"
                )
            fields[field] = child
        if set(fields) != set(FIELDS):
            raise ValueError(f"{id}: each printed field is required once")
        expected = {
            "name": id + ": " + node.get("data-task-name"),
            "duration": "DUR " + printed(durations[id]) + " " + unit,
            **{
                k: k.upper() + " " + printed(values[k])
                for k in ("es", "ef", "ls", "lf", "tf")
            },
            "status": "CRITICAL" if critical else "FLOAT",
        }
        slots = {
            "name": (16, 24, 12),
            "duration": (16, 48, 12),
            "es": (16, 76, 12),
            "ef": (width / 2 + 8, 76, 12),
            "ls": (16, 104, 12),
            "lf": (width / 2 + 8, 104, 12),
            "tf": (16, 132, 12),
            "status": (16, 156, 12),
        }
        for field, child in fields.items():
            if text_value(child) != expected[field]:
                errors.append(f"{id}: printed {field} must be {expected[field]!r}")
            dx, dy, size = slots[field]
            if (number(child, "x"), number(child, "y"), number(child, "font-size")) != (
                x + dx,
                y + dy,
                size,
            ):
                errors.append(f"{id}: printed {field} is outside its fixed grid slot")
            if (
                child.get("font-family") != "Geist Mono, monospace"
                or child.get("fill") != ink
            ):
                errors.append(
                    f"{id}: printed {field} must use explicit visible house ink and mono font"
                )
            available = (
                width - dx - 8
                if field in ("name", "duration", "status")
                else width / 2 - 16
            )
            if len(text_value(child)) * size * 0.65 > available:
                errors.append(
                    f"{id}: printed {field} exceeds the bounded cell; split the view"
                )
    if len(widths) != 1:
        errors.append("all task grids must have equal width")
    if any(len(xs) != 1 for xs in rank_x.values()):
        errors.append("tasks of one rank must share x")
    xs = [min(rank_x[r]) for r in sorted(rank_x)]
    if widths and any(b - a < next(iter(widths)) + 40 for a, b in zip(xs, xs[1:])):
        errors.append("precedence ranks must advance left to right with clear gutters")
    ports = {}
    segments = []
    for link, (a, b) in zip(links, edges):
        critical = (a, b) in model["critical_edges"]
        if link.get("data-critical") != str(critical).lower():
            errors.append(
                f"{a}->{b}: critical edge flag disagrees with tight critical endpoints"
            )
        children = list(link)
        if len(children) != 2 or any(local(c.tag) != "path" for c in children):
            raise ValueError("precedence link needs one shaft and one open arrowhead")
        shaft = points(children[0].get("d", ""), rounded=True)
        head = points(children[1].get("d", ""), rounded=False)
        s, t = boxes[a], boxes[b]
        tx, ty = head[1] if len(head) == 3 else (math.nan, math.nan)
        if not (
            shaft[0][0] == s[2]
            and s[1] + 16 <= shaft[0][1] <= s[3] - 16
            and tx == t[0]
            and t[1] + 16 <= ty <= t[3] - 16
            and shaft[-1] == (tx - 12, ty)
            and head == [(tx - 8, ty - 6), (tx, ty), (tx - 8, ty + 6)]
        ):
            errors.append(
                f"{a}->{b}: visible arrow endpoints must land on the named task ports"
            )
        if not (
            shaft[1][1] == shaft[0][1]
            and shaft[1][0] > shaft[0][0]
            and shaft[-2][1] == shaft[-1][1]
            and shaft[-2][0] < shaft[-1][0]
        ):
            errors.append(
                f"{a}->{b}: shaft must depart and arrive perpendicular to task edges"
            )
        ports.setdefault((a, "out"), []).append(shaft[0][1])
        ports.setdefault((b, "in"), []).append(ty)
        low, high = sorted((shaft[0][1], ty))
        if any(not (s[2] <= x <= t[0] and low <= y <= high) for x, y in shaft):
            errors.append(f"{a}->{b}: route must stay between the named task ports")
        for first, second in zip(shaft, shaft[1:]):
            for box in boxes.values():
                if (
                    first[0] == second[0]
                    and first[0] in (box[0], box[2])
                    and max(min(first[1], second[1]), box[1])
                    < min(max(first[1], second[1]), box[3])
                ) or (
                    first[1] == second[1]
                    and first[1] in (box[1], box[3])
                    and max(min(first[0], second[0]), box[0])
                    < min(max(first[0], second[0]), box[2])
                ):
                    errors.append(f"{a}->{b}: shaft runs along a task border")
            for previous_a, previous_b in segments:
                horizontal = first[1] == second[1]
                previous_horizontal = previous_a[1] == previous_b[1]
                if horizontal == previous_horizontal:
                    axis = 0 if horizontal else 1
                    cross = 1 - axis
                    if first[cross] == previous_a[cross] and max(
                        min(first[axis], second[axis]),
                        min(previous_a[axis], previous_b[axis]),
                    ) < min(
                        max(first[axis], second[axis]),
                        max(previous_a[axis], previous_b[axis]),
                    ):
                        errors.append(
                            "precedence shafts must not share a stacked segment"
                        )
                else:
                    h1, h2 = (first, second) if horizontal else (previous_a, previous_b)
                    v1, v2 = (previous_a, previous_b) if horizontal else (first, second)
                    if min(h1[0], h2[0]) <= v1[0] <= max(h1[0], h2[0]) and min(
                        v1[1], v2[1]
                    ) <= h1[1] <= max(v1[1], v2[1]):
                        errors.append(
                            "precedence shafts must not cross without separation"
                        )
        segments.extend(zip(shaft, shaft[1:]))
        # No shaft may run through any task interior, including its own endpoints.
        if any(
            intersects(p, q, box)
            for p, q in zip(shaft, shaft[1:])
            for box in boxes.values()
        ):
            errors.append(f"{a}->{b}: shaft crosses a task box")
        for child in children:
            if child.get("stroke") != (ink if critical else muted) or child.get(
                "stroke-width"
            ) != ("2" if critical else "1"):
                errors.append(
                    f"{a}->{b}: arrow ink/width must encode the complete critical set"
                )
    for values in ports.values():
        if any(b - a < 12 for a, b in zip(sorted(values), sorted(values)[1:])):
            errors.append("precedence ports must be fanned at least 12px apart")
    # Only individually bound text can draw a scheduling claim. Unbound text
    # with an anchor outside a box could otherwise overprint its real values.
    for node in svg.iter():
        if local(node.tag) == "text":
            parent = original_parents.get(node)
            if parent is svg:
                if "data-schedule-summary" not in node.attrib:
                    errors.append("root text must be a bound schedule summary")
            elif (
                parent not in tasks.values() or "data-schedule-field" not in node.attrib
            ):
                errors.append("task text must be bound directly to its task grid")
    summaries = {}
    for n in svg.iter():
        if "data-schedule-summary" in n.attrib:
            if original_parents.get(n) is not svg:
                raise ValueError(
                    "summary must be a direct visible child of the root SVG"
                )
            key = n.get("data-schedule-summary")
            if key in summaries or local(n.tag) != "text":
                raise ValueError("duplicate or invalid schedule summary")
            summaries[key] = text_value(n)
            slots = {
                "finish": (48, 48, 16),
                "assumptions": (48, 660, 12),
                "scale": (48, 688, 12),
            }
            if key not in slots:
                raise ValueError("unknown schedule summary")
            x, y, size = slots[key]
            if (number(n, "x"), number(n, "y"), number(n, "font-size")) != (
                x,
                y,
                size,
            ) or n.get("text-anchor", "start") != "start":
                errors.append("summary must keep its fixed visible start-anchored slot")
            if n.get("fill") != ink or n.get("font-family") != "Geist Mono, monospace":
                errors.append(
                    "summary must use explicit visible house ink and mono font"
                )
            right = x + len(text_value(n)) * size * 0.65
            bounds = (x, y - size, right, y + size * 0.2)
            height = float(svg.get("viewBox", "").split()[-1])
            if right > 1152 or bounds[1] < 0 or bounds[3] > height:
                errors.append("summary exceeds its visible viewport slot")
            if any(
                max(bounds[0], box[0]) < min(bounds[2], box[2])
                and max(bounds[1], box[1]) < min(bounds[3], box[3])
                for box in boxes.values()
            ):
                errors.append("summary text extent overlaps a task box")
    expected = {
        "finish": "PROJECT FINISH " + printed(model["finish"]) + " " + unit,
        "assumptions": "ILLUSTRATIVE SCHEDULE · "
        + unit
        + " · ORIGIN 0 · FINISH-TO-START · ZERO LAG",
        "scale": "Task widths and spacing are not proportional to time.",
    }
    if summaries != expected:
        errors.append(
            "visible project finish, unit, assumptions and non-time scale summaries must agree"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()
    files = (
        [
            ASSETS / f"example-schedule-network{suffix}.html"
            for suffix in ("", "-dark", "-full")
        ]
        if args.all
        else args.files
    )
    if not files:
        parser.error("provide FILE or --all with shipped examples")
    failed = False
    for path in files:
        try:
            errors = check(path)
        except (OSError, UnicodeError) as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print("FAIL", path)
            print("\n".join("  - " + e for e in errors))
        else:
            print("OK", path)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
