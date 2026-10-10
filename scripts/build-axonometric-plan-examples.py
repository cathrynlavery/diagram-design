#!/usr/bin/env python3
"""Build the axonometric plan examples from one projection.

An axonometric plan is one plate (a floor slab or a site) carrying boxes: walls,
furniture, buildings, trees. Every coordinate comes from ``iso(x, y, z)`` in
``axonometry.py``; boxes on the plate are painted back to front by a depth sort
over their footprints, and rooms or buildings carry horizontal tags.
``scripts/verify-axonometric-plan.py`` recomputes every silhouette, the paint
order, and the tag positions from the attributes each element declares.

    python3 scripts/build-axonometric-plan-examples.py          # write the examples
    python3 scripts/build-axonometric-plan-examples.py --check  # fail if any file is stale
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
from axonometry import (FONT_LINK, FULL, MINIMAL, SKINS, Proj, Rect,  # noqa: E402
                        animated_page, cards_html, f, finish, outline, prism, solid, styles)

EYEBROW = "Axonometric plan · Diagram Design"
TREE_TOP = {"light": "#bfc0c0", "dark": "#949eb2"}
T = 6  # wall thickness


# ---------------------------------------------------------------- boxes and paint order


# ---------------------------------------------------------------------- boxes and paint order
# 场景包围框Box类，管理物体属性与渲染绘制顺序
@dataclass
class Box:
    rect: Rect                  # 包围框坐标
    h: float                    # 物体高度
    kind: str = "furniture"    # 物体类型 wall/furniture/building/tree/rack
    focal: bool = False         # 是否焦点物体
    inset_top: bool = False     # 顶部是否内凹
    name: str = ""              # 物体名称
    sub: str = ""               # 子描述
    step: int = 0               # 渲染绘制层级
    tag_at: tuple | None = None # 标签位置，None无标签


def behind(a: Rect, b: Rect) -> bool:
    """a is entirely farther from the viewer than b. 判断a在b后方，用于渲染遮挡排序"""
    e = 1e-6 # 浮点数计算误差容错
    return a.x1 <= b.x0 + e or a.y1 <= b.y0 + e



def bbox(P, box: Box, z):
    pts = prism(P, box.rect, z, z + box.h + (8 if box.kind == "tree" else 0))["poly"]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def depth_sort(P, boxes: list[Box], z) -> list[Box]:
    """Topological back-to-front order over boxes whose screen boxes overlap."""
    n = len(boxes)
    boxes_bb = [bbox(P, b, z) for b in boxes]
    succ = {i: set() for i in range(n)}
    indeg = [0] * n
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = boxes[i].rect, boxes[j].rect
            ai, bj = boxes_bb[i], boxes_bb[j]
            overlap = ai[0] < bj[2] and bj[0] < ai[2] and ai[1] < bj[3] and bj[1] < ai[3]
            if overlap and behind(a, b) and not behind(b, a) and j not in succ[i]:
                succ[i].add(j)
                indeg[j] += 1
    key = lambda k: (boxes[k].rect.x0 + boxes[k].rect.y0, boxes[k].rect.x0)
    ready = sorted((i for i in range(n) if indeg[i] == 0), key=key)
    order = []
    while ready:
        i = ready.pop(0)
        order.append(i)
        for j in succ[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                ready.append(j)
        ready.sort(key=key)
    if len(order) != n:
        raise ValueError("boxes form a depth cycle; split one of them")
    return [boxes[i] for i in order]


def depth_sort_phased(P, boxes: list[Box], z) -> list[Box]:
    """Back-to-front order that keeps every phase contiguous, so each phase can reveal as one
    group. Boxes of one step contract to a single node; static boxes stay on their own. The
    contracted graph must be acyclic, or a phase would have to paint on both sides of a box."""
    n = len(boxes)
    bb = [bbox(P, b, z) for b in boxes]
    edges = set()
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a, b = boxes[i].rect, boxes[j].rect
            ai, bj = bb[i], bb[j]
            overlap = ai[0] < bj[2] and bj[0] < ai[2] and ai[1] < bj[3] and bj[1] < ai[3]
            if overlap and behind(a, b) and not behind(b, a):
                edges.add((i, j))
    key = lambda k: (boxes[k].rect.x0 + boxes[k].rect.y0, boxes[k].rect.x0)
    node = lambda k: ("s", boxes[k].step) if boxes[k].step else ("b", k)
    members: dict = {}
    for k in range(n):
        members.setdefault(node(k), []).append(k)

    def topo(nodes, succ, rank):
        indeg = {v: 0 for v in nodes}
        for v in nodes:
            for w in succ[v]:
                indeg[w] += 1
        ready = sorted((v for v in nodes if indeg[v] == 0), key=rank)
        order = []
        while ready:
            v = ready.pop(0)
            order.append(v)
            for w in succ[v]:
                indeg[w] -= 1
                if indeg[w] == 0:
                    ready.append(w)
            ready.sort(key=rank)
        if len(order) != len(nodes):
            raise ValueError("a phase must paint on both sides of another box; move it or split the phase")
        return order

    groups = list(members)
    gsucc = {g: set() for g in groups}
    for i, j in edges:
        if node(i) != node(j):
            gsucc[node(i)].add(node(j))
    out = []
    for g in topo(groups, gsucc, lambda g: min(key(k) for k in members[g])):
        inner = members[g]
        isucc = {k: {j for i, j in edges if i == k and j in inner} for k in inner}
        out += [boxes[k] for k in topo(inner, isucc, key)]
    return out


def box_attrs(b: Box, z):
    a = f'data-box data-rect="{b.rect.attr()}" data-z="{f(z)}" data-h="{f(b.h)}" data-kind="{b.kind}"'
    if b.name:
        a += f' data-name="{b.name}"'
    if b.focal:
        a += " data-focal"
    return a


def draw_box(P, b: Box, z, sk, skin):
    """One box as a <g data-box>, its silhouette path first."""
    if b.kind == "tree":
        cx, cy = (b.rect.x0 + b.rect.x1) / 2, (b.rect.y0 + b.rect.y1) / 2
        trunk = prism(P, Rect(cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5, 0), z, z + 8)
        can = prism(P, b.rect, z + 8, z + 8 + b.h)
        body = [f'<path data-role="silhouette" d="{can["sil"]}" fill="{sk["base"]}"/>',
                f'<path d="{trunk["sil"]}" fill="{sk["chip_side"]}"/>',
                f'<path d="{can["sil"]}" fill="{sk["base"]}"/>',
                f'<path d="{can["right"]}" fill="rgba({sk["ink_rgb"]},0.12)"/>',
                f'<path d="{can["top"]}" fill="{TREE_TOP[skin]}"/>',
                f'<path d="{can["sil"]}" fill="none" stroke="{sk["sil"]}" stroke-width="0.6"/>']
        return f'<g {box_attrs(b, z + 8)}>' + "".join(body) + "</g>"
    if b.kind == "rack":
        # Shelving: house face shading, a shelf line every 14 units, and an upright every 30.
        tones, stroke, inner = styles(sk, False)
        r = b.rect
        pr, body = solid(P, r, z, z + b.h, sk, tones, stroke, inner)
        for zz in range(int(z) + 14, int(z + b.h), 14):
            a, c, e = P.iso(r.x0, r.y1, zz), P.iso(r.x1, r.y1, zz), P.iso(r.x1, r.y0, zz)
            body.append(f'<path d="M {f(a[0])} {f(a[1])} L {f(c[0])} {f(c[1])} L {f(e[0])} {f(e[1])}" fill="none" stroke="{inner}" stroke-width="0.6"/>')
        n = max(1, round((r.x1 - r.x0) / 30))
        for i in range(1, n):
            x = r.x0 + (r.x1 - r.x0) * i / n
            a, c = P.iso(x, r.y1, z), P.iso(x, r.y1, z + b.h)
            body.append(f'<line x1="{f(a[0])}" y1="{f(a[1])}" x2="{f(c[0])}" y2="{f(c[1])}" stroke="{inner}" stroke-width="0.6"/>')
        body += finish(pr, stroke, inner, 0.8)
        return f'<g {box_attrs(b, z)}>' + "".join(body) + "</g>"
    tones, stroke, inner = styles(sk, b.focal)
    pr, body = solid(P, b.rect, z, z + b.h, sk, tones, stroke, inner)
    if b.inset_top:
        body.append(f'<path d="{outline(P, b.rect.inset(3), z + b.h)}" fill="none" stroke="{inner}" stroke-width="0.6"/>')
    sw = 1.0 if b.kind in ("wall", "building") else 0.8
    body += finish(pr, stroke, inner, sw)
    return f'<g {box_attrs(b, z)}>' + "".join(body) + "</g>"


def tag(P, sk, name, sub, at, z, focal):
    """A horizontal tag on an opaque backing, centred on the plan point it names."""
    x, y = P.iso(at[0], at[1], z)
    wn = len(name) * 12 * 0.6
    ws = len(sub) * 8 * 0.62 + len(sub) * 0.64
    bw = math.ceil((max(wn, ws) + 16) / 4) * 4
    name_c = sk["accent"] if focal else sk["ink"]
    sub_c = sk["accent"] if focal else sk["muted"]
    edge = sk["accent"] if focal else sk["rule"]
    return (f'<g data-role="tag" data-name="{name}" data-at="{f(at[0])} {f(at[1])} {f(z)}">'
            f'<rect x="{f(x - bw / 2)}" y="{f(y - 16)}" width="{bw}" height="32" rx="2" fill="{sk["base"]}" stroke="{edge}" stroke-width="0.8"/>'
            f'<text data-role="name" x="{f(x)}" y="{f(y)}" text-anchor="middle" fill="{name_c}" font-size="12" font-weight="600" font-family="\'Geist\', sans-serif">{name}</text>'
            f'<text x="{f(x)}" y="{f(y + 11)}" text-anchor="middle" fill="{sub_c}" font-size="8" font-family="\'Geist Mono\', monospace" letter-spacing="0.08em">{sub}</text></g>')


# ---------------------------------------------------------------- figures


@dataclass
class Room:
    name: str
    sub: str
    rect: Rect
    tag_at: tuple
    focal: bool = False
    step: int = 0


@dataclass
class Plan:
    slug: str
    title: str
    desc: str
    plate: Rect
    plate_t: float
    boxes: list[Box]
    rooms: list[Room] = field(default_factory=list)
    flats: list[tuple[Rect, str]] = field(default_factory=list)   # flat floor marks: (rect, role)
    lines: list[tuple[tuple, tuple]] = field(default_factory=list)  # dashed centre lines on the plate
    caption: tuple[str, str] | None = None
    subtitle: str = ""
    cards: list = field(default_factory=list)
    footer: str = ""
    steps: int = 0
    phases: dict = field(default_factory=dict)  # step -> aria label, for plans revealed zone by zone


def build_svg(plan: Plan, skin: str, motion: bool, slug: str):
    sk = SKINS[skin]
    top = plan.plate_t
    P0 = Proj(0, 0)
    pts = prism(P0, plan.plate, 0, top)["poly"]
    for b in plan.boxes:
        pts += prism(P0, b.rect, top, top + b.h + (8 if b.kind == "tree" else 0))["poly"]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    ox = round(((1000 - (maxx - minx)) / 2 - minx) / 4) * 4
    oy = round((48 - miny) / 4) * 4
    P = Proj(ox, oy)
    vh = math.ceil((oy + maxy + (72 if plan.caption else 32)) / 4) * 4

    out = [f'<rect width="100%" height="100%" fill="{sk["paper"]}"/>',
           f'<g data-axo-plan data-origin="{f(ox)} {f(oy)}">']
    pr, body = solid(P, plan.plate, 0, top, sk, sk["shade"], sk["sil"], sk["inner"])
    out.append(f'<g data-plate data-rect="{plan.plate.attr()}" data-z="0" data-t="{f(top)}">' + "".join(body + finish(pr, sk["sil"], sk["inner"])) + "</g>")
    for rect, role in plan.flats:
        out.append(f'<path d="{outline(P, rect, top)}" fill="rgba({sk["ink_rgb"]},0.07)"/>')
    for a, b in plan.lines:
        pa, pb = P.iso(a[0], a[1], top), P.iso(b[0], b[1], top)
        out.append(f'<line x1="{f(pa[0])}" y1="{f(pa[1])}" x2="{f(pb[0])}" y2="{f(pb[1])}" stroke="rgba({sk["ink_rgb"]},0.25)" stroke-width="0.8" stroke-dasharray="6,5"/>')
    for r in plan.rooms:
        attrs = f'data-room data-name="{r.name}" data-rect="{r.rect.attr()}"' + (" data-focal" if r.focal else "")
        tint = f'<path d="{outline(P, r.rect, top)}" fill="rgba({sk["acc_rgb"]},0.12)"/>' if r.focal else ""
        out.append(f"<g {attrs}>{tint}</g>")

    if motion and plan.phases:
        return build_phased(plan, P, sk, skin, top, out, vh, ox, minx)
    tags = []
    for b in depth_sort(P, plan.boxes, top):
        g = draw_box(P, b, top, sk, skin)
        if b.kind == "building":
            at = b.tag_at or ((b.rect.x0 + b.rect.x1) / 2, (b.rect.y0 + b.rect.y1) / 2)
            t = tag(P, sk, b.name, b.sub, at, top + b.h, b.focal)
            if motion and b.step:
                out.append(f'<g data-motion-item data-step="{b.step}" data-appear aria-label="{b.name}, {b.sub}">' + g + t + "</g>")
            else:
                out.append(g)
                tags.append(t)
        else:
            out.append(g)
    for r in plan.rooms:
        tags.append(tag(P, sk, r.name, r.sub, r.tag_at, top, r.focal))
    out += tags
    out.append("</g>")
    if plan.caption:
        cy = vh - 28
        x0 = ox + minx
        out.append(f'<text x="{f(x0)}" y="{cy}" fill="{sk["muted"]}" font-size="8" font-family="\'Geist Mono\', monospace" letter-spacing="0.18em">{plan.caption[0]}</text>')
        out.append(f'<text x="{f(x0 + 120)}" y="{cy}" fill="{sk["muted"]}" font-size="8.5" font-family="\'Geist\', sans-serif" font-style="italic">{plan.caption[1]}</text>')
    return "\n        ".join(out), vh


def caption(plan, sk, vh, x0):
    cy = vh - 28
    return [f'<text x="{f(x0)}" y="{cy}" fill="{sk["muted"]}" font-size="8" font-family="\'Geist Mono\', monospace" letter-spacing="0.18em">{plan.caption[0]}</text>',
            f'<text x="{f(x0 + 120)}" y="{cy}" fill="{sk["muted"]}" font-size="8.5" font-family="\'Geist\', sans-serif" font-style="italic">{plan.caption[1]}</text>']


def build_phased(plan: Plan, P, sk, skin, top, out, vh, ox, minx):
    """A floor revealed zone by zone: each phase's boxes paint as one contiguous group, and
    its room tags arrive with it in a second group after every box."""
    run, run_step = [], 0

    def close():
        if run:
            out.append(f'<g data-motion-item data-step="{run_step}" data-appear aria-label="{plan.phases[run_step]}">' + "".join(run) + "</g>")
            run.clear()

    seen = set()
    for b in depth_sort_phased(P, plan.boxes, top):
        g = draw_box(P, b, top, sk, skin)
        if b.step:
            if b.step != run_step or not run:
                close()
                if b.step in seen:
                    raise ValueError(f"phase {b.step} paints in two runs")
                if seen and b.step < max(seen):
                    raise ValueError(f"phase {b.step} paints after phase {max(seen)}; number phases back to front so the DOM reads in narrative order")
                seen.add(b.step)
                run_step = b.step
            run.append(g)
        else:
            close()
            out.append(g)
    close()
    staged = {}
    for r in plan.rooms:
        t = tag(P, sk, r.name, r.sub, r.tag_at, top, r.focal)
        if r.step:
            staged.setdefault(r.step, []).append((r.name, t))
        else:
            out.append(t)
    for step in sorted(staged):
        names = " and ".join(n for n, _ in staged[step])
        out.append(f'<g data-motion-item data-step="{step}" data-appear aria-label="{names} tagged">' + "".join(t for _, t in staged[step]) + "</g>")
    out.append("</g>")
    if plan.caption:
        out += caption(plan, sk, vh, ox + minx)
    return "\n        ".join(out), vh


APPEAR_CSS = """
    /* Static source is the finished plan. Only an initialized enhancement hides
       the buildings, which then drop in by phase, never further than 16px. */
    .motion-ready [data-motion-item][data-appear] { opacity: 0; transform: translateY(-16px); transition: none; }
    .motion-ready [data-motion-item][data-appear].is-visible { opacity: 1; transform: none; transition: opacity var(--motion-step) var(--motion-ease), transform var(--motion-step) var(--motion-ease); }
    .motion-ready[data-frame="end"] [data-motion-item][data-appear],
    .motion-ready[data-frame="static"] [data-motion-item][data-appear] { opacity: 1; transform: none; }
"""


# ---------------------------------------------------------------- content


def hwall(y, *spans):
    return [Box(Rect(a, y, b, y + T), 22, "wall") for a, b in spans]


def vwall(x, *spans):
    return [Box(Rect(x, a, x + T, b), 22, "wall") for a, b in spans]


def office() -> Plan:
    W, D = 360, 240
    walls = (hwall(0, (0, W)) + vwall(0, (6, D))
             + hwall(D - 6, (6, 40), (76, W)) + vwall(W - 6, (6, D - 6))
             + vwall(214, (6, 50), (78, 160), (188, D - 6))
             + hwall(140, (6, 60), (92, 180), (204, 214))
             + vwall(164, (146, D - 6))
             + hwall(100, (220, 290), (318, W - 6)))
    desks = [Box(Rect(col, row, col + 44, row + 24), 10, inset_top=True) for row in (28, 84) for col in (24, 84, 144)]
    furniture = desks + [
        Box(Rect(246, 30, 330, 70), 10, inset_top=True),
        Box(Rect(330, 112, 348, 228), 16),
        Box(Rect(250, 150, 298, 190), 14, inset_top=True),
        Box(Rect(28, 168, 92, 184), 14),
    ]
    rooms = [
        Room("Open office", "24 desks", Rect(6, 6, 214, 140), (112, 124)),
        Room("Meeting room", "12 seats", Rect(220, 6, 354, 100), (288, 88), focal=True),
        Room("Kitchen", "café, lockers", Rect(220, 106, 354, 234), (274, 214)),
        Room("Lobby", "reception", Rect(6, 146, 164, 234), (96, 214)),
        Room("Booth", "1 person", Rect(170, 146, 214, 234), (192, 206)),
    ]
    return Plan(
        slug="axonometric-plan",
        title="Level 3 office · Where the team actually sits",
        desc="Axonometric floor plan of an office level with an open office, meeting room, kitchen, lobby, and phone booth, with the meeting room as the focal room.",
        plate=Rect(0, 0, W, D, 0), plate_t=6, boxes=walls + furniture, rooms=rooms,
        caption=("FOCAL ROOM", "Walls cut at desk height so every room reads from one view; the meeting room is the one under discussion."),
        subtitle="One floor, walls cut at desk height, so every room and what is in it reads from a single view.",
        cards=[("The headline", "coral", "One room is the subject", "The meeting room gets the accent because it is the room being discussed. It seats twelve, and the floor tint marks it without colouring the furniture."),
               ("", "ink", "Reading the plan", ["Walls are cut low so nothing hides a room", "Tags sit on the floor they name", "Furniture shows how each room is used", "Gaps in walls are doors"]),
               ("", "muted", "When to use it", "Office moves, seating plans, and space reviews. For a list of rooms and capacities, a table is faster.")],
        footer="office floor · axonometric plan")


SW, SD = 420, 300
TREES = [(184, y) for y in (24, 64, 104, 200, 244, 284)] + [(x, 128) for x in (40, 90, 140, 260, 300, 334)]


def campus() -> Plan:
    buildings = [
        Box(Rect(30, 30, 120, 110), 40, "building", focal=True, inset_top=True, name="Library", sub="phase 1", step=1),
        Box(Rect(240, 24, 330, 72), 64, "building", inset_top=True, name="Labs", sub="phase 1", step=1),
        Box(Rect(30, 186, 170, 214), 44, "building", inset_top=True, name="Dorm A", sub="phase 2", step=2, tag_at=(130, 200)),
        Box(Rect(30, 240, 170, 268), 44, "building", inset_top=True, name="Dorm B", sub="phase 2", step=2, tag_at=(70, 254)),
        Box(Rect(248, 188, 392, 272), 28, "building", inset_top=True, name="Sports hall", sub="phase 3", step=3),
        Box(Rect(350, 24, 404, 120), 16, "building", inset_top=True, name="Parking", sub="phase 3", step=3),
    ]
    trees = [Box(Rect(x - 10, y - 10, x + 10, y + 10, 10), 6, "tree") for x, y in TREES]
    return Plan(
        slug="axonometric-plan-campus",
        title="North campus · Three phases, six buildings",
        desc="Campus site plan with the library and labs in phase 1, two dorms in phase 2, and the sports hall and parking in phase 3, with the library as the focal building.",
        plate=Rect(0, 0, SW, SD, 6), plate_t=8, boxes=buildings + trees,
        flats=[(Rect(0, 144, SW, 168, 0), "road"), (Rect(196, 0, 220, SD, 0), "road")],
        lines=[((0, 156), (SW, 156)), ((208, 0), (208, SD))],
        caption=("FOCAL BUILDING", "The library opens in phase 1 and anchors the quad; housing and sport follow as enrolment grows."),
        subtitle="Six buildings in three phases. Each tag carries its phase, so the build order reads without a legend.",
        cards=[("The headline", "coral", "The library comes first", "Everything else on the site is placed around it, so it gets the accent and opens in phase 1 with the labs."),
               ("", "ink", "Reading the site", ["Heights are to scale with each other", "Roads cross at the quad", "Tags sit on the roof they name", "Trees mark the green edges"]),
               ("", "muted", "When to use it", "Master plans, site visits, and phasing reviews. For a schedule of phases and dates, use a Gantt chart.")],
        footer="campus · axonometric plan", steps=3)


def post(x, y):
    return Box(Rect(x - 3, y - 3, x + 3, y + 3, 3), 18, step=2)


def coffee_shop() -> Plan:
    W, D = 360, 260
    walls = (hwall(0, (0, W)) + vwall(0, (6, D))
             + hwall(D - 6, (6, 150), (190, W)) + vwall(W - 6, (6, D - 6))
             + hwall(80, (6, 30), (64, 290), (322, W - 6))
             + vwall(250, (6, 80)))
    kitchen = [Box(Rect(12, 12, 64, 26), 34, "rack"),
               Box(Rect(84, 12, 124, 36), 18),
               Box(Rect(136, 12, 164, 30), 16, inset_top=True),
               Box(Rect(100, 48, 196, 66), 14, inset_top=True)]
    restroom = [Box(Rect(264, 12, 288, 26), 16, inset_top=True),
                Box(Rect(320, 12, 340, 36), 12)]
    bar = [Box(Rect(10, 96, 32, 118), 30, step=1),
           Box(Rect(10, 122, 32, 162), 26, inset_top=True, step=1),
           Box(Rect(10, 166, 32, 180), 28, step=1),
           Box(Rect(10, 184, 32, 208), 16, inset_top=True, step=1),
           Box(Rect(78, 100, 94, 140), 20, inset_top=True, step=1),
           Box(Rect(78, 144, 94, 212), 16, step=1)]
    queue = [post(118, y) for y in (126, 158, 190, 222)]
    seating = [Box(Rect(x - 12, y - 12, x + 12, y + 12, 12), 12, inset_top=True, step=3)
               for x, y in ((222, 114), (290, 114), (222, 186), (290, 186))]
    seating += [Box(Rect(330, 100, 348, 240), 8, step=3),
                Box(Rect(206, 216, 306, 236), 12, inset_top=True, step=3)]
    rooms = [
        Room("Entrance", "door, queue", Rect(100, 86, 196, 254), (148, 170), step=2),
        Room("Espresso bar", "order, pickup", Rect(6, 86, 100, 254), (42, 228), focal=True, step=1),
        Room("Seating", "22 seats", Rect(196, 86, 354, 254), (252, 150), step=3),
        Room("Kitchen", "back of house", Rect(6, 6, 250, 80), (46, 60)),
        Room("Restroom", "1 stall", Rect(256, 6, 354, 80), (296, 50)),
    ]
    return Plan(
        slug="axonometric-plan-coffee-shop",
        title="Corner coffee shop · From the door to a seat",
        desc="Axonometric floor plan of a small coffee shop with an entrance and queue, an espresso bar, seating, a kitchen, and a restroom, with the espresso bar as the focal room.",
        plate=Rect(0, 0, W, D, 0), plate_t=6, boxes=walls + kitchen + restroom + bar + queue + seating, rooms=rooms,
        caption=("FOCAL ROOM", "Every customer passes the espresso bar twice, once to order and once to pick up, so it sits beside the door."),
        subtitle="One room with a kitchen behind it. The queue runs along the counter, so ordering, paying and pickup happen in one line.",
        cards=[("The headline", "coral", "The bar is the bottleneck", "Every order goes through two baristas and one espresso machine. The accent marks the bar because its length sets how many people can wait without blocking the door."),
               ("", "ink", "Reading the plan", ["Posts mark the queue lane along the counter", "The tall unit on the back bar is the fridge", "Round tables seat two, the long table seats six", "Gaps in walls are doors"]),
               ("", "muted", "When to use it", "Fit-outs, staffing reviews, and new-store briefs. For a list of equipment and costs, a table is faster.")],
        footer="coffee shop · axonometric plan", steps=3,
        phases={1: "The espresso bar: back bar and counter", 2: "The entrance and the queue posts", 3: "Seating: tables and the window bench"})


def warehouse() -> Plan:
    W, D = 460, 300
    walls = (hwall(0, (0, W)) + vwall(0, (6, 30), (70, 120), (160, 210), (250, D))
             + hwall(D - 6, (6, W - 6))
             + vwall(W - 6, (6, 40), (80, 130), (170, 220), (260, D - 6)))
    dock = lambda y: Rect(6, y, 18, y + 40, 0)
    receiving = [Box(Rect(36, y, 64, y + 28), h, inset_top=True, step=1) for y, h in ((36, 14), (126, 18), (216, 12))]
    racks = [Box(Rect(x0, y, x0 + 84, y + 14), 52, "rack", step=1) for y in (20, 72, 124) for x0 in (110, 214)]
    pick = [Box(Rect(110, 214, 298, 228), 24, "rack", step=2)]
    pick += [Box(Rect(x, 242, x + 16, 266), 14, inset_top=True, step=2) for x in (122, 162, 202)]
    packing = [Box(Rect(318, y, 354, y + 44), 14, inset_top=True, step=2) for y in (30, 110, 190)]
    packing += [Box(Rect(362, 20, 372, 236), 8, step=2)]
    shipping = [Box(Rect(392, y, 420, y + 28), h, inset_top=True, step=3) for y, h in ((46, 20), (136, 16), (226, 22))]
    rooms = [
        Room("Receiving", "3 dock doors", Rect(6, 6, 96, 294), (74, 174), step=1),
        Room("Storage", "6 racks", Rect(96, 6, 306, 196), (204, 162), step=1),
        Room("Pick zone", "carts, flow rack", Rect(96, 196, 306, 294), (254, 272), step=2),
        Room("Packing", "3 stations", Rect(306, 6, 380, 294), (338, 262), focal=True, step=2),
        Room("Shipping", "3 dock doors", Rect(380, 6, 454, 294), (424, 186), step=3),
    ]
    return Plan(
        slug="axonometric-plan-warehouse",
        title="Fulfillment floor · Dock to dock",
        desc="Axonometric plan of a fulfillment warehouse: receiving docks, storage racks, a pick zone, packing stations, and shipping docks, with packing as the focal zone.",
        plate=Rect(0, 0, W, D, 0), plate_t=6, boxes=walls + receiving + racks + pick + packing + shipping, rooms=rooms,
        flats=[(dock(30), "dock"), (dock(120), "dock"), (dock(210), "dock")],
        lines=[((96, 6), (96, 294)), ((306, 6), (306, 294)), ((380, 6), (380, 294)), ((96, 196), (306, 196))],
        caption=("FOCAL ZONE", "Goods move left to right; packing is where most orders wait, so it gets the accent."),
        subtitle="Goods come in on the left and leave on the right. Everything in between is storage, picking and packing, laid out in that order.",
        cards=[("The headline", "coral", "Packing sets the pace", "Receiving and storage can run ahead. An order only ships when someone packs it, so the three stations are the accent and the place to add capacity first."),
               ("", "ink", "Reading the plan", ["Tall racks hold reserve stock", "The low flow rack faces the pick lane", "The conveyor carries packed orders to shipping", "Gaps in the side walls are dock doors"]),
               ("", "muted", "When to use it", "Layout changes, peak season planning, and new-hire walkthroughs. For pick rates by zone, use a bar chart.")],
        footer="fulfillment floor · axonometric plan", steps=3,
        phases={1: "Inbound: receiving pallets and storage racks", 2: "Pick and pack: carts, flow rack, and packing stations", 3: "Outbound: shipping pallets"})


FIGURES = {"axonometric-plan": office, "axonometric-plan-campus": campus,
           "axonometric-plan-coffee-shop": coffee_shop, "axonometric-plan-warehouse": warehouse}
ANIMATED = ("axonometric-plan-campus", "axonometric-plan-coffee-shop", "axonometric-plan-warehouse")


def render_all() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for name, make in FIGURES.items():
        for variant, skin in (("", "light"), ("-dark", "dark"), ("-full", "light")):
            plan = make()
            slug = f"{name}{variant}"
            body, vh = build_svg(plan, skin, False, slug)
            sk = SKINS[skin]
            if variant == "-full":
                html = FULL.format(eyebrow=EYEBROW, title=plan.title, font=FONT_LINK, slug=slug, desc=plan.desc, vh=vh,
                                   body=body, subtitle=plan.subtitle, cards=cards_html(plan.cards), footer=plan.footer)
            else:
                html = MINIMAL.format(eyebrow=EYEBROW, title=plan.title, font=FONT_LINK, slug=slug, desc=plan.desc, vh=vh,
                                      body=body, **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})
            files[ASSETS / f"example-{slug}.html"] = html
        if name in ANIMATED:
            plan = make()
            slug = f"{name}-animated"
            body, vh = build_svg(plan, "light", True, slug)
            files[ASSETS / f"example-{slug}.html"] = animated_page(
                plan.title, plan.desc, slug, body, vh, plan.steps, "Axonometric plan · Optional motion",
                APPEAR_CSS, "The complete site plan is shown above.")
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if any generated example differs from disk")
    args = parser.parse_args()
    stale = []
    files = render_all()
    for path, html in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != html:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(html, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("stale axonometric plan examples (run scripts/build-axonometric-plan-examples.py):")
        for name in stale:
            print(f"  - {name}")
        return 1
    if args.check:
        print(f"OK axonometric plan examples: {len(files)} files up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
