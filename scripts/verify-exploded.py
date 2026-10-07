#!/usr/bin/env python3
"""Verify exploded axonometric diagrams against the geometry they declare.

Each part carries its model box (``data-rect``, ``data-z``, ``data-t``,
``data-level``) and the figure carries its drawing origin and gap. This
checker reprojects every part with iso(x, y, z) = [x - y, (x + y) / 2 - z]
and fails when the drawing and the declaration disagree:

- a silhouette vertex or corner arc off the projection of its declared box;
- a level that does not share one z, a bottom level off z = 0, unequal gaps,
  or a gap under max(0.5 x top-face height, 3 x thickest non-container part);
- a leader that is not horizontal, does not start at its part's right
  extreme, or crosses another part; labels outside one column, closer than
  36px, or longer than two words;
- more than one focal part, a trace line that is not vertical and dashed, an
  SVG transform anywhere in the figure, a part with two labels, or an
  animated part whose lift is not its exploded z minus its closed z.

    python3 scripts/verify-exploded.py --all
    python3 scripts/verify-exploded.py skills/diagram-design/assets/example-exploded.html
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
TOL = 0.05
LABEL_PITCH = 36
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, attrs, parent
        self.children: list[Element] = []
        self.text = ""

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def walk(self):
        for child in self.children:
            yield child
            yield from child.walk()


class Tree(HTMLParser):
    VOID = {"path", "line", "circle", "rect", "polygon", "ellipse", "meta", "link", "br", "img", "input", "stop"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Element("#root", {}, None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        el = Element(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(el)
        if tag not in self.VOID:
            self.cur = el

    def handle_startendtag(self, tag, attrs):
        el = Element(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(el)

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        # A label's visible name includes inline tspan descendants, in source
        # order, as well as text before and after them.
        self.cur.text += data
        for ancestor in self.cur.ancestors():
            if ancestor.tag == "text":
                ancestor.text += data


# ---------------------------------------------------------------- projection (independent of the builder)


def corners(r):
    x0, y0, x1, y1, rad = r
    return [(x1 - rad, y1 - rad), (x0 + rad, y1 - rad), (x0 + rad, y0 + rad), (x1 - rad, y0 + rad)]


def outline_point(origin, r, theta, z, k=None):
    k = int(math.floor(theta / 90)) % 4 if k is None else k
    cx, cy = corners(r)[k]
    t = math.radians(theta)
    x, y = cx + r[4] * math.cos(t), cy + r[4] * math.sin(t)
    return (origin[0] + x - y, origin[1] + (x + y) / 2 - z)


def walk_points(origin, r, a, b, z):
    """Endpoints of each edge and quarter arc between outline angles a and b."""
    pts, arcs = [], []
    rising = b > a
    th = a
    step = 1 if rising else -1
    while (b - th) * step > 1e-9:
        nxt = min(b, (math.floor(th / 90) + 1) * 90) if rising else max(b, (math.ceil(th / 90) - 1) * 90)
        k = int(math.floor((th + nxt) / 2 / 90)) % 4
        pts.append(outline_point(origin, r, nxt, z, k))
        arcs.append(r[4] > 0)
        th = nxt
        if (b - th) * step > 1e-9:
            pts.append(outline_point(origin, r, th, z, int(math.floor((th + step) / 90)) % 4))
            arcs.append(False)
    return pts, arcs


def expected_silhouette(origin, r, z0, z1):
    pts = [outline_point(origin, r, 135, z1)]
    arcs = [False]
    p, a = walk_points(origin, r, 135, 315, z1)
    pts += p
    arcs += a
    pts.append(outline_point(origin, r, -45, z0))
    arcs.append(False)
    p, a = walk_points(origin, r, -45, 135, z0)
    pts += p
    arcs += a
    return pts, arcs


def silhouette_poly(origin, r, z0, z1, n=24):
    poly = [outline_point(origin, r, 135 + 180 * i / n, z1) for i in range(n + 1)]
    poly += [outline_point(origin, r, -45 + 180 * i / n, z0) for i in range(n + 1)]
    return poly


def parse_path(d):
    """Return (endpoints, is_arc, arcs as (rx, ry, rotation, large-arc, sweep)) for an absolute M/L/A/Z path."""
    token_re = re.compile(r"[MLAZ]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?")
    tokens = []
    end = 0
    for match in token_re.finditer(d):
        if d[end:match.start()].strip(" \t\r\n,"):
            raise ValueError(f"unsupported path token {d[end:match.start()]!r}")
        tokens.append(match.group())
        end = match.end()
    if d[end:].strip(" \t\r\n,"):
        raise ValueError(f"unsupported path token {d[end:]!r}")

    def operand(index):
        value = float(tokens[index])
        if not math.isfinite(value):
            raise ValueError("non-finite path operand")
        return value
    pts, arcs, radii = [], [], []
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd in ("M", "L"):
            pts.append((operand(i + 1), operand(i + 2)))
            arcs.append(False)
            i += 3
        elif cmd == "A":
            if tokens[i + 4] not in {"0", "1"} or tokens[i + 5] not in {"0", "1"}:
                raise ValueError("arc flags must be literal 0 or 1")
            radii.append(tuple(operand(i + k) for k in range(1, 6)))
            pts.append((operand(i + 6), operand(i + 7)))
            arcs.append(True)
            i += 8
        elif cmd == "Z":
            i += 1
        else:
            raise ValueError(f"unsupported path token {cmd!r}")
    return pts, arcs, radii


def crosses(y, xa, xb, poly):
    xs = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 - y) * (y2 - y) < 0:
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return any(xs[i] < xb and xs[i + 1] > xa for i in range(0, len(xs) - 1, 2))


def num(value, what, errors):
    try:
        return float(value)
    except (TypeError, ValueError):
        errors.append(f"{what} is not a number: {value!r}")
        return None


# ---------------------------------------------------------------- checks


def verify_source(source: str, name: str) -> list[str]:
    errors: list[str] = []
    tree = Tree()
    tree.feed(source)
    roots = [el for el in tree.root.walk() if el.tag == "g" and "data-exploded" in el.attrs]
    if len(roots) != 1:
        return [f"{name}: expected one <g data-exploded>; found {len(roots)}"]
    fig = roots[0]
    origin_vals = NUMBER.findall(fig.attrs.get("data-origin", ""))
    if len(origin_vals) != 2:
        return [f"{name}: data-origin must be two numbers"]
    origin = (float(origin_vals[0]), float(origin_vals[1]))
    gap = num(fig.attrs.get("data-gap"), f"{name}: data-gap", errors)
    if gap is None:
        return errors

    parts = []
    for el in fig.walk():
        if el.tag != "g" or "data-part" not in el.attrs:
            continue
        key = el.attrs["data-part"]
        vals = NUMBER.findall(el.attrs.get("data-rect", ""))
        if len(vals) != 5:
            errors.append(f"{name}: part {key!r} data-rect must be x0 y0 x1 y1 r")
            continue
        rect = tuple(float(v) for v in vals)
        z = num(el.attrs.get("data-z"), f"{name}: part {key!r} data-z", errors)
        t = num(el.attrs.get("data-t"), f"{name}: part {key!r} data-t", errors)
        level = num(el.attrs.get("data-level"), f"{name}: part {key!r} data-level", errors)
        if None in (z, t, level):
            continue
        parts.append(dict(key=key, el=el, rect=rect, z=z, t=t, level=int(level),
                          name=el.attrs.get("data-name", ""), housing=el.attrs.get("data-kind") == "housing",
                          focal="data-focal" in el.attrs, closed=el.attrs.get("data-closed-z")))
    if len(parts) < 2:
        errors.append(f"{name}: an exploded view needs at least two parts; found {len(parts)}")
        return errors

    # 1. Every silhouette is the projection of its declared box.
    for p in parts:
        sil = next((c for c in p["el"].walk() if c.tag == "path" and c.attrs.get("data-role") == "silhouette"), None)
        if sil is None:
            errors.append(f"{name}: part {p['key']!r} has no data-role=silhouette path")
            continue
        want, want_arcs = expected_silhouette(origin, p["rect"], p["z"], p["z"] + p["t"])
        try:
            got, got_arcs, radii = parse_path(sil.attrs.get("d", ""))
        except (ValueError, IndexError) as exc:
            errors.append(f"{name}: part {p['key']!r} silhouette is unreadable ({exc})")
            continue
        if len(got) != len(want) or got_arcs != want_arcs:
            errors.append(f"{name}: part {p['key']!r} silhouette has {len(got)} vertices; its box projects to {len(want)}")
            continue
        for i, (g, w) in enumerate(zip(got, want)):
            if abs(g[0] - w[0]) > TOL or abs(g[1] - w[1]) > TOL:
                errors.append(f"{name}: part {p['key']!r} silhouette vertex {i} is at {g}; iso() of its box puts it at ({w[0]:.2f}, {w[1]:.2f})")
                break
        r = p["rect"][4]
        for rx, ry, rotation, large, sweep in radii:
            if abs(rx - r * math.sqrt(2)) > TOL or abs(ry - r / math.sqrt(2)) > TOL:
                errors.append(f"{name}: part {p['key']!r} corner arc {rx:g}x{ry:g} is not the 2:1 ellipse of radius {r:g} ({r * math.sqrt(2):.2f}x{r / math.sqrt(2):.2f})")
                break
            # Both silhouette walks run clockwise on screen through quarter corners, so every
            # arc is unrotated, short, and sweeps positive. A flipped flag bends the corner
            # inward while its endpoints and radii still match.
            if rotation != 0 or large != 0 or sweep != 1:
                errors.append(f"{name}: part {p['key']!r} corner arc flags are rotation {rotation:g}, large-arc {large:g}, sweep {sweep:g}; a projected corner is 0 0 1")
                break

    # 2. Levels, equal gaps, the gap floor, and the bottom staying put.
    levels: dict[int, list[dict]] = {}
    for p in parts:
        levels.setdefault(p["level"], []).append(p)
    order = sorted(levels)
    if order != list(range(len(order))):
        errors.append(f"{name}: levels must run 0..{len(order) - 1}; found {order}")
    for k in order:
        zs = {round(p["z"], 3) for p in levels[k]}
        if len(zs) != 1:
            errors.append(f"{name}: level {k} parts sit at different z {sorted(zs)}; a level explodes together")
    if order and abs(levels[order[0]][0]["z"]) > TOL:
        errors.append(f"{name}: the bottom level must stay at z = 0; found {levels[order[0]][0]['z']}")
    for k0, k1 in zip(order, order[1:]):
        top = levels[k0][0]["z"] + max(p["t"] for p in levels[k0])
        actual = levels[k1][0]["z"] - top
        if abs(actual - gap) > TOL:
            errors.append(f"{name}: gap between levels {k0} and {k1} is {actual:g}; the figure declares {gap:g}, and gaps must be equal")
    top_h = max((p["rect"][2] - p["rect"][0] + p["rect"][3] - p["rect"][1]) / 2 for p in parts)
    solids = [p["t"] for p in parts if not p["housing"]] or [p["t"] for p in parts]
    floor = max(0.5 * top_h, 3 * max(solids))
    if gap + TOL < floor:
        errors.append(f"{name}: gap {gap:g} is under max(0.5 x top-face height, 3 x thickness) = {floor:g}")

    # 3. Labels: exactly one per part, one column, horizontal leaders from each part's right extreme.
    labels = {}
    part_names = {p["name"] for p in parts}
    for el in fig.walk():
        if el.tag == "g" and el.attrs.get("data-role") == "label":
            name_el = next((c for c in el.walk() if c.tag == "text" and c.attrs.get("data-role") == "name"), None)
            leader = next((c for c in el.walk() if c.tag == "line" and c.attrs.get("data-role") == "leader"), None)
            if name_el is None or leader is None:
                errors.append(f"{name}: a label group needs a data-role=name text and a data-role=leader line")
                continue
            text = name_el.text.strip()
            if text in labels:
                errors.append(f"{name}: part {text!r} has more than one label; each part gets exactly one")
                continue
            if text not in part_names:
                errors.append(f"{name}: label {text!r} names no declared part")
                continue
            labels[text] = (name_el, leader)
    polys = {p["key"]: silhouette_poly(origin, p["rect"], p["z"], p["z"] + p["t"]) for p in parts}
    columns, anchor_ys = set(), []
    for p in parts:
        if p["name"] not in labels:
            errors.append(f"{name}: part {p['key']!r} has no label named {p['name']!r}")
            continue
        name_el, leader = labels[p["name"]]
        words = p["name"].split()
        if len(words) > 2:
            errors.append(f"{name}: label {p['name']!r} has {len(words)} words; keep labels to one or two")
        x1, y1, x2, y2 = (float(leader.attrs.get(k, "nan")) for k in ("x1", "y1", "x2", "y2"))
        if abs(y1 - y2) > TOL:
            errors.append(f"{name}: leader for {p['name']!r} is not horizontal ({y1:g} to {y2:g})")
        top_right = outline_point(origin, p["rect"], -45, p["z"] + p["t"])
        bottom_right = outline_point(origin, p["rect"], -45, p["z"])
        ax, ay = top_right[0], (top_right[1] + bottom_right[1]) / 2
        if abs(y1 - ay) > TOL or abs(x1 - (ax + 6)) > TOL:
            errors.append(f"{name}: leader for {p['name']!r} starts at ({x1:g}, {y1:g}); the part's right extreme is ({ax:.2f}, {ay:.2f})")
        anchor_ys.append((ay, p["name"]))
        columns.add(round(float(name_el.attrs.get("x", "nan")), 2))
        for q in parts:
            if q is not p and crosses(y1, x1, x2, polys[q["key"]]):
                errors.append(f"{name}: leader for {p['name']!r} crosses part {q['key']!r}")
    if len(columns) > 1:
        errors.append(f"{name}: labels sit in {len(columns)} columns {sorted(columns)}; use one aligned column")
    anchor_ys.sort()
    for (ya, na), (yb, nb) in zip(anchor_ys, anchor_ys[1:]):
        if yb - ya < LABEL_PITCH - TOL:
            errors.append(f"{name}: labels {na!r} and {nb!r} are {yb - ya:.1f}px apart; the minimum is {LABEL_PITCH}")

    # 4. One focal part at most.
    focal = [p["key"] for p in parts if p["focal"]]
    if len(focal) > 1:
        errors.append(f"{name}: {len(focal)} focal parts {focal}; the accent goes on one")

    # 5. Trace lines run straight up and are dashed.
    for el in fig.walk():
        if el.tag == "line" and el.attrs.get("data-role") == "trace":
            if abs(float(el.attrs.get("x1", "nan")) - float(el.attrs.get("x2", "nan"))) > TOL:
                errors.append(f"{name}: trace line is not vertical")
            if not el.attrs.get("stroke-dasharray"):
                errors.append(f"{name}: trace line must be dashed")

    # 6. Geometry comes from coordinates alone: no SVG transform anywhere in the figure.
    for el in [fig, *fig.walk()]:
        if "transform" in el.attrs:
            errors.append(f"{name}: <{el.tag}> carries transform={el.attrs['transform']!r}; position comes from projected coordinates")

    # 7. Animated parts lift by exactly their explode distance.
    for p in parts:
        style = p["el"].attrs.get("style", "")
        if "data-motion-item" in p["el"].attrs:
            if p["closed"] is None:
                errors.append(f"{name}: animated part {p['key']!r} needs data-closed-z")
                continue
            m = re.fullmatch(r"\s*--lift:\s*(-?\d+(?:\.\d+)?)px;?\s*", style)
            if not m:
                errors.append(f"{name}: animated part {p['key']!r} must carry only style=\"--lift:Npx\"; found {style!r}")
                continue
            want = p["z"] - float(p["closed"])
            if abs(float(m.group(1)) - want) > TOL:
                errors.append(f"{name}: part {p['key']!r} lifts {m.group(1)}px; z {p['z']:g} minus closed z {p['closed']} is {want:g}")
        elif style:
            errors.append(f"{name}: static part {p['key']!r} carries a style attribute; position comes from geometry")
    return errors


def verify(path: Path) -> list[str]:
    try:
        display = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        display = str(path)
    return verify_source(path.read_text(encoding="utf-8"), display)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify exploded axonometric geometry.")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check every shipped example-exploded*.html")
    args = parser.parse_args()
    files = sorted(ASSETS.glob("example-exploded*.html")) if args.all else args.files
    if not files:
        parser.error("name files or pass --all")
    errors = []
    for path in files:
        errors += verify(path)
    if errors:
        print(f"FAIL exploded axonometric: {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK exploded axonometric: {len(files)} file(s) match their declared geometry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
