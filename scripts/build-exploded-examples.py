#!/usr/bin/env python3
"""Build the exploded axonometric examples from one projection.

Every coordinate in the generated files comes from ``iso(x, y, z)``, the 2:1
dimetric projection documented in
``skills/diagram-design/references/type-exploded.md``. Nothing is placed by
hand, so the examples can be rebuilt after any change to the model and
``scripts/verify-exploded.py`` can recompute every silhouette from the
attributes each part declares.

    python3 scripts/build-exploded-examples.py          # write the examples
    python3 scripts/build-exploded-examples.py --check  # fail if any file is stale
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
from axonometry import (
    FONT_LINK,
    FULL,
    MINIMAL,
    SKINS,
    L,
    M,
    Proj,
    Rect,
    animated_page,
    cards_html,
    f,
    finish,
    outline,
    point,
    prism,
    solid,
    styles,
    walk,
)

# ---------------------------------------------------------------- parts


@dataclass
class Part:
    key: str
    name: str
    sub: str
    rect: Rect
    t: float
    kind: str = "slab"
    closed_z: float = 0
    level: int | None = None
    z: float = 0


WALL, FLOOR = 5, 3


def draw_part(P, p: Part, sk, focal: bool, uid: str):
    tones, stroke, inner = styles(sk, focal)
    z0, z1 = p.z, p.z + p.t
    if p.kind == "housing":
        # Back half only: silhouette, rim, cavity, and floor. housing_front() paints the
        # outer walls and the front rim after anything that sits inside.
        pr = prism(P, p.rect, z0, z1)
        ir = p.rect.inset(WALL)
        out = [f'<path data-role="silhouette" d="{pr["sil"]}" fill="{sk["base"]}"/>',
               f'<path d="{outline(P, p.rect, z1)}" fill="{sk["base"]}"/>']
        if tones[0]:
            out.append(f'<path d="{outline(P, p.rect, z1)}" fill="{tones[0]}"/>')
        out += [f'<path d="{outline(P, ir, z1)}" fill="{sk["base"]}"/>',
                f'<path d="{outline(P, ir, z1)}" fill="{sk["cavity"]}"/>',
                f'<clipPath id="{uid}-cavity"><path d="{outline(P, ir, z1)}"/></clipPath>',
                f'<g clip-path="url(#{uid}-cavity)"><path d="{outline(P, ir, z0 + FLOOR)}" fill="{sk["base"]}"/>'
                f'<path d="{outline(P, ir, z0 + FLOOR)}" fill="{sk["floor"]}"/>'
                f'<path d="{outline(P, ir, z0 + FLOOR)}" fill="none" stroke="{inner}" stroke-width="0.8"/></g>',
                f'<path d="{outline(P, ir, z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>',
                f'<path d="{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, 315, z1)}" fill="none" stroke="{stroke}" stroke-width="1.2" stroke-linejoin="round"/>']
        return pr, out
    if p.kind in ("keycaps", "switches"):
        return draw_key_grid(P, p, sk, focal)
    pr, out = solid(P, p.rect, z0, z1, sk, tones, stroke, inner)
    r = p.rect
    if p.kind in AI_DETAIL:
        out += finish(pr, stroke, inner)
        out += AI_DETAIL[p.kind](P, r, z1, sk, focal)
        return pr, out
    if p.kind == "plate":
        for k in KEYS:
            cx, cy = k.center()
            out.append(f'<path d="{outline(P, Rect(cx - 7, cy - 7, cx + 7, cy + 7, 1), z1)}" fill="{sk["cavity"]}" stroke="{inner}" stroke-width="0.5"/>')
    elif p.kind == "pcb":
        out += finish(pr, stroke, inner)
        for k in KEYS:
            cx, cy = k.center()
            out.append(f'<path d="{outline(P, Rect(cx - 3, cy - 3, cx + 3, cy + 3, 3), z1)}" fill="{sk["chip_top"]}"/>')
        for ax, ay, bx, by, h in ((64, 76, 92, 90, 2), (128, 78, 144, 88, 1.5), (104, 6, 124, 14, 4)):
            chip = prism(P, Rect(ax, ay, bx, by, 1), z1, z1 + h)
            out += [f'<path d="{chip["sil"]}" fill="{sk["chip_side"]}"/>', f'<path d="{chip["top"]}" fill="{sk["chip_top"]}"/>']
        return pr, out
    if p.kind == "display":
        out.append(f'<path d="{outline(P, r.inset(4), z1)}" fill="{sk["screen"]}"/>')
        cx = (r.x0 + r.x1) / 2
        out.append(f'<path d="{outline(P, Rect(cx - 16, r.y0 + 12, cx + 16, r.y0 + 22, 5), z1)}" fill="{sk["island"]}"/>')
    elif p.kind == "battery":
        out.append(f'<path d="{outline(P, r.inset(8), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        out.append(f'<path d="{outline(P, Rect(r.x0 + 12, r.y0 + 4, r.x0 + 36, r.y0 + 10, 0), z1)}" fill="{sk["chip_top"]}"/>')
    elif p.kind == "board":
        out += finish(pr, stroke, inner)
        cam = Rect(r.x0 + 8, r.y0 + 8, r.x0 + 52, r.y0 + 52, 8)
        cpr, cbody = solid(P, cam, z1, z1 + 6, sk, sk["shade"], sk["sil"], sk["inner"], role=False)
        out += cbody + finish(cpr, sk["sil"], sk["inner"], 1)
        for lx, ly in ((r.x0 + 21, r.y0 + 21), (r.x0 + 39, r.y0 + 39)):
            lens = Rect(lx - 8, ly - 8, lx + 8, ly + 8, 8)
            out += [f'<path d="{prism(P, lens, z1 + 6, z1 + 9)["sil"]}" fill="{sk["lens"]}"/>',
                    f'<path d="{outline(P, lens.inset(3), z1 + 9)}" fill="none" stroke="{sk["lens_ring"]}" stroke-width="0.8"/>']
        for ax, ay, bx, by, h in ((64, 16, 100, 52, 3), (20, 64, 44, 92, 2), (64, 64, 108, 84, 2)):
            chip = prism(P, Rect(r.x0 + ax, r.y0 + ay, r.x0 + bx, r.y0 + by, 1), z1, z1 + h)
            out += [f'<path d="{chip["sil"]}" fill="{sk["chip_side"]}"/>', f'<path d="{chip["top"]}" fill="{sk["chip_top"]}"/>']
        return pr, out
    elif p.kind == "insert":
        for well in (Rect(SPK.x0 - 4, SPK.y0 - 4, SPK.x1 + 4, SPK.y1 + 4, SPK.r + 4),
                     Rect(CABLE.x0 - 3, CABLE.y0 - 3, CABLE.x1 + 3, CABLE.y1 + 3, 5)):
            out.append(f'<path d="{outline(P, well, z1)}" fill="{sk["well"]}" stroke="{inner}" stroke-width="0.8"/>')
    elif p.kind == "speaker":
        for zz in range(int(z0) + 10, int(z0 + p.t * 0.72), 8):
            out.append(f'<path d="{M(point(P, r, 135, zz))} {walk(P, r, 135, -45, zz)}" fill="none" stroke="{inner}" stroke-width="0.6"/>')
        out.append(f'<path d="{outline(P, r.inset(10), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        dot = Rect(r.x0 + 36, r.y0 + 36, r.x1 - 36, r.y1 - 36, 10)
        out.append(f'<path d="{outline(P, dot, z1)}" fill="{sk["accent"] if focal else sk["chip_top"]}"/>')
    elif p.kind == "cable":
        for k in (6, 11):
            out.append(f'<path d="{outline(P, r.inset(k, 4), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
    elif p.kind == "lid":
        out.append(f'<path d="{outline(P, r.inset(14), z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        mark = Rect(cx - 14, cy - 14, cx + 14, cy + 14, 14)
        out.append(f'<path d="{outline(P, mark, z1)}" fill="none" stroke="{sk["sil"]}" stroke-width="1.2"/>')
        out.append(f'<path d="{outline(P, mark.inset(9), z1)}" fill="{sk["sil"]}"/>')
    out += finish(pr, stroke, inner)
    return pr, out


def housing_front(P, p: Part, sk, focal, buttons):
    """Outer walls and the front half of the rim, painted after the parts inside."""
    tones, stroke, inner = styles(sk, focal)
    z0, z1 = p.z, p.z + p.t
    ir = p.rect.inset(WALL)
    pr = prism(P, p.rect, z0, z1)
    rim = (f"{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, -45, z1)} "
           f"{L(point(P, ir, -45, z1))} {walk(P, ir, -45, 135, z1)} Z")
    walls = (f"{M(point(P, p.rect, 135, z1))} {walk(P, p.rect, 135, -45, z1)} "
             f"{L(point(P, p.rect, -45, z0))} {walk(P, p.rect, -45, 135, z0)} Z")
    out = [f'<path d="{walls}" fill="{sk["base"]}"/>', f'<path d="{rim}" fill="{sk["base"]}"/>']
    if tones[0]:
        out.append(f'<path d="{rim}" fill="{tones[0]}"/>')
    if tones[1]:
        out.append(f'<path d="{pr["left"]}" fill="{tones[1]}"/>')
    if tones[2]:
        out.append(f'<path d="{pr["right"]}" fill="{tones[2]}"/>')
    if buttons:
        r = p.rect
        for ya, yb in ((r.y0 + 60, r.y0 + 100), (r.y0 + 112, r.y0 + 132)):
            za, zb = z0 + p.t * 0.35, z0 + p.t * 0.75
            bar = [P.iso(r.x1 + 1.5, ya, zb), P.iso(r.x1 + 1.5, yb, zb), P.iso(r.x1 + 1.5, yb, za), P.iso(r.x1 + 1.5, ya, za)]
            out.append(f'<polygon points="{" ".join(f"{f(a)},{f(b)}" for a, b in bar)}" fill="{sk["base"]}" stroke="{inner}" stroke-width="0.8"/>')
    out.append(f'<path d="{M(point(P, ir, 135, z1))} {walk(P, ir, 135, -45, z1)}" fill="none" stroke="{inner}" stroke-width="0.8"/>')
    out.append(f'<path d="{pr["edge"]}" fill="none" stroke="{stroke}" stroke-width="1.2"/>')
    front = (f"{M(point(P, p.rect, 135, z1))} {L(point(P, p.rect, 135, z0))} "
             f"{walk(P, p.rect, 135, -45, z0)} {L(point(P, p.rect, -45, z1))}")
    out.append(f'<path d="{front}" fill="none" stroke="{stroke}" stroke-width="1.2" stroke-linejoin="round"/>')
    return out


# ---------------------------------------------------------------- layout


def levels_of(parts):
    idx, current, previous = [], -1, object()
    for p in parts:
        if p.level is None or p.level != previous:
            current += 1
        idx.append(current)
        previous = p.level if p.level is not None else object()
    return idx


def crosses(y, xa, xb, poly):
    xs = []
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 - y) * (y2 - y) < 0:
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return any(xs[i] < xb and xs[i + 1] > xa for i in range(0, len(xs) - 1, 2))


LABEL_PITCH = 36


def explode(parts, gap_k):
    """Assign z by level. Gap = max(gap_k x top-face height, 3 x part thickness), raised in
    4-unit steps until no leader crosses another part and no two labels sit closer than
    LABEL_PITCH. Raising the gap cannot fix two parts on one level, so that raises."""
    top_h = max((p.rect.x1 - p.rect.x0 + p.rect.y1 - p.rect.y0) / 2 for p in parts)
    tmax = max(p.t for p in parts if p.kind != "housing")
    gap = math.ceil(max(gap_k * top_h, 3 * tmax) / 4) * 4
    lv = levels_of(parts)
    while True:
        z = 0
        for k in range(max(lv) + 1):
            members = [p for p, level in zip(parts, lv) if level == k]
            for p in members:
                p.z = z
            z += max(p.t for p in members) + gap
        P = Proj(0, 0)
        prs = [prism(P, p.rect, p.z, p.z + p.t) for p in parts]
        right = max(pr["rx"] for pr in prs) + 48
        bad = False
        for i, pr in enumerate(prs):
            for j, q in enumerate(prs):
                if i != j and crosses(pr["anchor"][1], pr["anchor"][0] + 1, right, q["poly"]):
                    if lv[i] == lv[j]:
                        raise ValueError(f"leader of {parts[i].key} crosses {parts[j].key} on one level")
                    bad = True
        ys = sorted((pr["anchor"][1], lv[i], parts[i].key) for i, pr in enumerate(prs))
        for (y1, l1, k1), (y2, l2, k2) in zip(ys, ys[1:]):
            if y2 - y1 < LABEL_PITCH:
                if l1 == l2:
                    raise ValueError(f"labels of {k1} and {k2} collide on one level")
                bad = True
        if not bad:
            return gap
        gap += 4


# ---------------------------------------------------------------- figure


@dataclass
class Figure:
    slug: str
    title: str
    desc: str
    parts: list[Part]
    focus: str
    gap_k: float = 0.5
    buttons: bool = False
    caption: tuple[str, str] | None = None
    subtitle: str = ""
    cards: list[tuple[str, str, str, list[str] | str]] = field(default_factory=list)
    footer: str = ""


def label(sk, part, anchor, col_x, focal, motion):
    ax, ay = anchor
    cls = ' class="part-label"' if motion else ""
    lead = sk["lead_acc"] if focal else sk["lead"]
    dot = sk["accent"] if focal else sk["ink"]
    sub = sk["accent"] if focal else sk["muted"]
    return (f'<g data-role="label"{cls}>'
            f'<line data-role="leader" x1="{f(ax + 6)}" y1="{f(ay)}" x2="{f(col_x - 12)}" y2="{f(ay)}" stroke="{lead}" stroke-width="0.8"/>'
            f'<circle cx="{f(ax)}" cy="{f(ay)}" r="2" fill="{dot}"/>'
            f'<text data-role="name" x="{f(col_x)}" y="{f(ay - 1)}" fill="{sk["ink"]}" font-size="16" font-weight="600" font-family="\'Geist\', sans-serif">{part.name}</text>'
            f'<text x="{f(col_x)}" y="{f(ay + 15)}" fill="{sub}" font-size="10" font-family="\'Geist Mono\', monospace" letter-spacing="0.08em">{part.sub}</text></g>')


def build_svg(fig: Figure, skin: str, motion: bool, slug: str):
    sk = SKINS[skin]
    parts = fig.parts
    gap = explode(parts, fig.gap_k)
    P0 = Proj(0, 0)
    pts = [pt for p in parts for pt in prism(P0, p.rect, p.z, p.z + p.t)["poly"]]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    lead_w, label_w = 64, 240
    left = math.floor((1000 - (maxx - minx + lead_w + label_w)) / 2 / 4) * 4
    ox, oy = round((left - minx) / 4) * 4, round((40 - miny) / 4) * 4
    P = Proj(ox, oy)
    vh = math.ceil((oy + maxy + (72 if fig.caption else 32)) / 4) * 4
    col_x = ox + maxx + lead_w

    lv = levels_of(parts)
    top_level = max(lv)
    steps = top_level + 1
    housing = parts[0] if parts[0].kind == "housing" else None

    def attrs(i, p):
        a = (f'data-part="{p.key}" data-name="{p.name}" data-rect="{p.rect.attr()}" '
             f'data-z="{f(p.z)}" data-t="{f(p.t)}" data-level="{lv[i]}"')
        if p.kind == "housing":
            a += ' data-kind="housing"'
        if p.key == fig.focus:
            a += " data-focal"
        if motion:
            a += f' data-closed-z="{f(p.closed_z)}"'
        return a

    out = [f'<rect width="100%" height="100%" fill="{sk["paper"]}"/>',
           f'<g data-exploded data-origin="{f(ox)} {f(oy)}" data-gap="{f(gap)}">']
    b, t = parts[0], parts[-1]
    trace = "".join(
        f'<line data-role="trace" x1="{f(point(P, b.rect, th, b.z + b.t)[0])}" y1="{f(point(P, b.rect, th, b.z + b.t)[1])}" '
        f'x2="{f(point(P, b.rect, th, t.z)[0])}" y2="{f(point(P, b.rect, th, t.z)[1])}" stroke="{sk["trace"]}" stroke-width="0.8" stroke-dasharray="4,3"/>'
        for th in (135, -45))

    pr0, body0 = draw_part(P, b, sk, b.key == fig.focus, f"{slug}-{b.key}")
    if motion:
        out.append(f'<g {attrs(0, b)}>' + "".join(body0) + "</g>")
        out.append(f'<g data-motion-item data-step="{steps}" data-reveal aria-label="{b.name} stays put; trace lines show where each part sat">'
                   + trace + label(sk, b, pr0["anchor"], col_x, b.key == fig.focus, False) + "</g>")
    else:
        out.append(trace)
        out.append(f'<g {attrs(0, b)}>' + "".join(body0) + label(sk, b, pr0["anchor"], col_x, b.key == fig.focus, False) + "</g>")

    def group(i):
        p = parts[i]
        focal = p.key == fig.focus
        pr, body = draw_part(P, p, sk, focal, f"{slug}-{p.key}")
        lab = label(sk, p, pr["anchor"], col_x, focal, motion)
        if not motion:
            return f'<g {attrs(i, p)}>' + "".join(body) + lab + "</g>"
        step = top_level - lv[i] + 1
        return (f'<g {attrs(i, p)} data-motion-item data-step="{step}" style="--lift:{f(p.z - p.closed_z)}px" '
                f'aria-label="{p.name} lifts clear">' + "".join(body) + lab + "</g>")

    if housing:
        for i in range(1, len(parts) - 1):
            out.append(group(i))
        out.append(f'<g data-part-front="{housing.key}">' + "".join(housing_front(P, housing, sk, housing.key == fig.focus, fig.buttons)) + "</g>")
        out.append(group(len(parts) - 1))
    else:
        for i in range(1, len(parts)):
            out.append(group(i))
    out.append("</g>")
    if fig.caption:
        cy = vh - 28
        out.append(f'<text x="{left}" y="{cy}" fill="{sk["muted"]}" font-size="8" font-family="\'Geist Mono\', monospace" letter-spacing="0.18em">{fig.caption[0]}</text>')
        out.append(f'<text x="{left + 104}" y="{cy}" fill="{sk["muted"]}" font-size="8.5" font-family="\'Geist\', sans-serif" font-style="italic">{fig.caption[1]}</text>')
    return "\n        ".join(out), vh, steps


# ---------------------------------------------------------------- pages

MOTION_CSS = """
    /* Static source is the exploded frame. Only an initialized enhancement assembles it.
       Parts travel straight up, so a vertical translate is the whole explode. */
    .motion-ready [data-motion-item][data-part] { opacity: 1; transform: translateY(var(--lift)); }
    .motion-ready:not([data-frame="start"]) [data-motion-item][data-part] { transition: transform var(--motion-step) var(--motion-ease); }
    .motion-ready [data-motion-item][data-part].is-visible,
    .motion-ready[data-frame="end"] [data-motion-item][data-part],
    .motion-ready[data-frame="static"] [data-motion-item][data-part] { transform: none; }
    .motion-ready [data-part] .part-label { opacity: 0; transition: none; }
    .motion-ready [data-part].is-visible .part-label { opacity: 1; transition: opacity var(--motion-fast) linear var(--motion-step); }
    .motion-ready[data-frame="end"] .part-label,
    .motion-ready[data-frame="static"] .part-label { opacity: 1; }
    .motion-ready [data-motion-item][data-reveal] { opacity: 0; transform: none; transition: none; }
    .motion-ready [data-motion-item][data-reveal].is-visible { opacity: 1; transition: opacity var(--motion-step) var(--motion-ease); }
    .motion-ready[data-frame="end"] [data-motion-item][data-reveal],
    .motion-ready[data-frame="static"] [data-motion-item][data-reveal] { opacity: 1; }
    html[data-motion="static"] .part-label { opacity: 1 !important; }
    html[data-motion="step"] .part-label { transition: none !important; }
    @media (prefers-reduced-motion: reduce) { .part-label { opacity: 1 !important; } }
    @media print { .part-label { opacity: 1 !important; } }
"""


def exploded_animated(fig: Figure, slug: str, body: str, vh: int, steps: int) -> str:
    return animated_page(fig.title, fig.desc, slug, body, vh, steps, "Exploded axonometric · Optional motion",
                         MOTION_CSS, "The complete exploded diagram is shown above.")


EYEBROW = "Exploded axonometric · Diagram Design"

# ---------------------------------------------------------------- keyboard and agent stack detail

U, KPAD = 16, 10  # key unit and the case margin around the key field
KEY_ROWS = ([1] * 13, [1.5] + [1] * 10 + [1.5], [1.75] + [1] * 9 + [2.25],
            [2.25] + [1] * 8 + [2.75], [1.5, 1.5, 7, 1.5, 1.5])


@dataclass
class Key:
    rect: Rect
    mod: bool

    def center(self):
        return (self.rect.x0 + self.rect.x1) / 2, (self.rect.y0 + self.rect.y1) / 2


def key_layout():
    keys = []
    for row, widths in enumerate(KEY_ROWS):
        x = 0.0
        for w in widths:
            keys.append(Key(Rect(KPAD + x * U + 1, KPAD + row * U + 1, KPAD + (x + w) * U - 1, KPAD + (row + 1) * U - 1, 2),
                            mod=w != 1 or (row == 0 and x == 0)))
            x += w
    return keys


KEYS = key_layout()


def mini(P, rect, z0, z1, sk, tones, stroke, inner, top=None):
    """A small solid inside a part: face tones, an optional top fill, a thin outline."""
    pr = prism(P, rect, z0, z1)
    out = [f'<path d="{pr["sil"]}" fill="{sk["base"]}"/>']
    for path, tone in zip((pr["top"], pr["left"], pr["right"]), tones):
        if tone:
            out.append(f'<path d="{path}" fill="{tone}"/>')
    if top:
        out.append(f'<path d="{pr["top"]}" fill="{top}"/>')
    out += [f'<path d="{pr["edge"]}" fill="none" stroke="{inner}" stroke-width="0.5"/>',
            f'<path d="{pr["sil"]}" fill="none" stroke="{stroke}" stroke-width="0.8" stroke-linejoin="round"/>']
    return out


def draw_key_grid(P, p: Part, sk, focal: bool):
    """Keycaps or switches: one small solid per key, back to front. The part's own box is
    the envelope of the grid, so its silhouette is declared but not painted."""
    tones, stroke, inner = styles(sk, focal)
    z0, z1 = p.z, p.z + p.t
    pr = prism(P, p.rect, z0, z1)
    out = [f'<path data-role="silhouette" d="{pr["sil"]}" fill="none"/>']
    for k in sorted(KEYS, key=lambda k: (k.rect.y0, k.rect.x0)):
        if p.kind == "keycaps":
            top = f'rgba({sk["ink_rgb"]},0.12)' if k.mod else None
            out += mini(P, k.rect, z0, z1, sk, tones, stroke, inner, top)
            out.append(f'<path d="{outline(P, k.rect.inset(2.5), z1)}" fill="none" stroke="{inner}" stroke-width="0.5"/>')
        else:
            cx, cy = k.center()
            out += mini(P, Rect(cx - 6, cy - 6, cx + 6, cy + 6, 1), z0, z1, sk, tones, stroke, inner)
            for stem in (Rect(cx - 1, cy - 3.5, cx + 1, cy + 3.5, 0), Rect(cx - 3.5, cy - 1, cx + 3.5, cy + 1, 0)):
                out.append(f'<path d="{outline(P, stem, z1)}" fill="{sk["accent"] if focal else sk["chip_top"]}"/>')
    return pr, out


def vault_detail(P, r, z, sk, focal):
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    door = r.inset(12)
    dial = Rect(cx - 18, cy - 18, cx + 18, cy + 18, 18)
    tones, stroke, inner = styles(sk, False)
    out = [f'<path d="{outline(P, door, z)}" fill="none" stroke="{sk["inner"]}" stroke-width="0.8"/>']
    out += mini(P, dial, z, z + 5, sk, sk["shade"], sk["sil"], sk["inner"])
    out.append(f'<path d="{outline(P, dial.inset(6), z + 5)}" fill="none" stroke="{sk["inner"]}" stroke-width="0.8"/>')
    out.append(f'<path d="{outline(P, Rect(cx - 4, cy - 4, cx + 4, cy + 4, 4), z + 5)}" fill="{sk["chip_top"]}"/>')
    return out


SOCKETS = [(x, y) for y in (40, 80, 120) for x in (40, 80, 120)]
PLUGS = {(40, 40), (120, 40), (80, 80), (40, 120)}


def tools_detail(P, r, z, sk, focal):
    out = []
    for x, y in SOCKETS:
        well = Rect(r.x0 + x - 11, r.y0 + y - 11, r.x0 + x + 11, r.y0 + y + 11, 11)
        out.append(f'<path d="{outline(P, well, z)}" fill="{sk["well"]}" stroke="{sk["inner"]}" stroke-width="0.6"/>')
    for x, y in sorted(PLUGS, key=lambda c: (c[0] + c[1], c[0])):
        plug = Rect(r.x0 + x - 7, r.y0 + y - 7, r.x0 + x + 7, r.y0 + y + 7, 7)
        out += mini(P, plug, z, z + 10, sk, sk["shade"], sk["sil"], sk["inner"], sk["chip_top"])
    return out


CARDS = [(x, y) for y in (14, 86) for x in (14, 62, 110)]


def skills_detail(P, r, z, sk, focal):
    out = []
    tones = sk["shade"]
    for x, y in CARDS:
        card = Rect(r.x0 + x, r.y0 + y, r.x0 + x + 36, r.y0 + y + 60, 3)
        out += mini(P, card, z, z + 5, sk, tones, sk["sil"], sk["inner"])
        for i, w in enumerate((22, 26, 18, 24)):
            ly = card.y0 + 10 + i * 11
            line = Rect(card.x0 + 6, ly, card.x0 + 6 + w, ly + 3, 0)
            fill = sk["accent"] if i == 0 else f'rgba({sk["ink_rgb"]},0.30)'
            out.append(f'<path d="{outline(P, line, z + 5)}" fill="{fill}"/>')
    return out


def harness_detail(P, r, z, sk, focal):
    cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    chip = Rect(cx - 30, cy - 30, cx + 30, cy + 30, 4)
    out = [f'<path d="{outline(P, chip.inset(-10, 8), z)}" fill="none" stroke="{sk["inner"]}" stroke-width="0.8"/>']
    for k in range(-24, 25, 12):
        for a, b in (((cx + k, r.y0 + 12), (cx + k, cy - 40)), ((cx + k, cy + 40), (cx + k, r.y1 - 12)),
                     ((r.x0 + 12, cy + k), (cx - 40, cy + k)), ((cx + 40, cy + k), (r.x1 - 12, cy + k))):
            pa, pb = P.iso(a[0], a[1], z), P.iso(b[0], b[1], z)
            out.append(f'<line x1="{f(pa[0])}" y1="{f(pa[1])}" x2="{f(pb[0])}" y2="{f(pb[1])}" stroke="{sk["inner"]}" stroke-width="0.6"/>')
    c = prism(P, chip, z, z + 6)
    out += [f'<path d="{c["sil"]}" fill="{sk["chip_side"]}"/>', f'<path d="{c["top"]}" fill="{sk["chip_top"]}"/>',
            f'<path d="{outline(P, chip.inset(10), z + 6)}" fill="none" stroke="{sk["lens_ring"]}" stroke-width="0.8"/>']
    return out


def interface_detail(P, r, z, sk, focal):
    screen = r.inset(8)
    out = [f'<path d="{outline(P, screen, z)}" fill="{sk["screen"]}"/>']
    x0, y0 = screen.x0 + 12, screen.y0 + 14
    for i, w in enumerate((60, 84, 44, 72, 0)):
        ly = y0 + i * 18
        out.append(f'<path d="{outline(P, Rect(x0, ly, x0 + 6, ly + 4, 0), z)}" fill="rgba(245,245,245,0.85)"/>')
        if w:
            out.append(f'<path d="{outline(P, Rect(x0 + 12, ly, x0 + 12 + w, ly + 4, 0), z)}" fill="rgba(245,245,245,0.40)"/>')
        else:
            out.append(f'<path d="{outline(P, Rect(x0 + 12, ly - 2, x0 + 18, ly + 6, 0), z)}" fill="rgba(245,245,245,0.85)"/>')
    return out


AI_DETAIL = {"vault": vault_detail, "tools": tools_detail, "skills": skills_detail,
             "harness": harness_detail, "interface": interface_detail}

# ---------------------------------------------------------------- content

def app_stack():
    a = 200
    return [Part("data", "Data", "postgres, object store", Rect(0, 0, a, a, 12), t=16, closed_z=0),
            Part("logic", "Logic", "api, workers, queue", Rect(0, 0, a, a, 12), t=16, closed_z=16),
            Part("interface", "Interface", "web app, mobile", Rect(0, 0, a, a, 12), t=16, closed_z=32)]


PW, PD, PR = 140, 280, 24


def phone():
    body = Rect(0, 0, PW, PD, PR)
    return [Part("housing", "Housing", "aluminium frame", body, t=20, kind="housing", closed_z=0),
            Part("board", "Logic board", "soc, cameras", Rect(8, 8, PW - 8, 112, 4), t=4, kind="board", closed_z=3, level=1),
            Part("battery", "Battery", "li-ion cell", Rect(10, 136, PW - 10, PD - 12, 6), t=8, kind="battery", closed_z=3, level=1),
            Part("display", "Display", "oled, cover glass", body, t=6, kind="display", closed_z=20)]


BW, BD = 180, 180
SPK = Rect(36, 52, 128, 144, 46)
CABLE = Rect(138, 40, 170, 72, 4)


def unboxing():
    return [Part("box", "Box", "rigid board", Rect(0, 0, BW, BD, 4), t=72, kind="housing", closed_z=0),
            Part("insert", "Insert", "moulded pulp", Rect(6, 6, BW - 6, BD - 6, 2), t=12, kind="insert", closed_z=3),
            Part("cable", "Cable", "usb-c, 1 m", CABLE, t=14, kind="cable", closed_z=9, level=2),
            Part("speaker", "Speaker", "the product", SPK, t=60, kind="speaker", closed_z=9, level=2),
            Part("lid", "Lid", "printed sleeve", Rect(-3, -3, BW + 3, BD + 3, 6), t=28, kind="lid", closed_z=48)]


AI = 160


def ai_stack():
    slab = Rect(0, 0, AI, AI, 10)
    return [Part("vault", "Secrets vault", "scoped service token", Rect(16, 16, AI - 16, AI - 16, 8), t=24, kind="vault", closed_z=0),
            Part("tools", "Tools", "clis, apis, mcp, scripts", slab, t=14, kind="tools", closed_z=24),
            Part("skills", "Skills", "markdown playbooks", slab, t=12, kind="skills", closed_z=38),
            Part("harness", "Agent harness", "claude code, codex", slab, t=16, kind="harness", closed_z=50),
            Part("interface", "Interface", "chat or terminal", slab, t=10, kind="interface", closed_z=66)]


KW, KD = 13 * U + 2 * KPAD, 5 * U + 2 * KPAD


def keyboard():
    return [Part("case", "Case", "aluminium tray", Rect(0, 0, KW, KD, 6), t=22, kind="housing", closed_z=0),
            Part("pcb", "PCB", "hot-swap sockets", Rect(6, 6, KW - 6, KD - 6, 3), t=4, kind="pcb", closed_z=3),
            Part("plate", "Plate", "steel, one cutout per key", Rect(6, 6, KW - 6, KD - 6, 3), t=3, kind="plate", closed_z=12),
            Part("switches", "Switches", "mechanical, linear", Rect(KPAD + 2, KPAD + 2, KW - KPAD - 2, KD - KPAD - 2, 1), t=9, kind="switches", closed_z=10),
            Part("keycaps", "Keycaps", "pbt, 51 keys", Rect(KPAD + 1, KPAD + 1, KW - KPAD - 1, KD - KPAD - 1, 2), t=9, kind="keycaps", closed_z=19)]


FIGURES = {
    "exploded": lambda: Figure(
        slug="exploded",
        title="App stack · Three layers, one product",
        desc="Exploded view of a three-layer app stack: data at the base, logic in the middle, interface on top, with logic as the focal layer.",
        parts=app_stack(), focus="logic",
        caption=("FOCAL LAYER", "Logic is where the product decisions live; the other two layers are swappable."),
        subtitle="Three layers pulled apart along one axis. The middle one carries the product, and the other two can be swapped.",
        cards=[("The headline", "coral", "Logic is the layer that pays rent", "Swapping the database is a migration. Swapping the interface is a redesign. Rewriting the logic is a different product, so that layer gets the accent."),
               ("", "ink", "Reading the explode", ["Bottom layer stays put", "Equal gaps, one axis", "Dashed lines trace the outer corners", "Labels sit in one column"]),
               ("", "muted", "Why only three", "A stack this small reads at a glance. Past five parts the explode gets tall and the labels crowd; split it into two figures.")],
        footer="app stack · exploded axonometric"),
    "exploded-phone": lambda: Figure(
        slug="exploded-phone",
        title="Phone teardown · What sits under the glass",
        desc="Exploded view of a phone: the display lifts off the housing to show the logic board and battery inside, with the logic board as the focal part.",
        parts=phone(), focus="board", gap_k=0.75, buttons=True,
        subtitle="The display comes off first. Underneath, the logic board and battery share one level inside the housing, so they lift together.",
        cards=[("The headline", "coral", "The board is the phone", "Cameras, radios and the system chip all live on one small board. Everything else holds it, powers it, or shows its output."),
               ("", "ink", "How it was drawn", ["Rounded corners project as quarter ellipses", "The housing is a tray, so its front walls paint last", "Parts on one level explode together", "Gap widened so the display clears the board"]),
               ("", "muted", "Four parts", "A real teardown has dozens of parts. The diagram keeps the four a reader needs and drops the screws.")],
        footer="phone · exploded axonometric"),
    "exploded-unboxing": lambda: Figure(
        slug="exploded-unboxing",
        title="Unboxing · What you see, in the order you see it",
        desc="Exploded view of product packaging: printed lid, the speaker and its cable, the moulded insert that holds them, and the rigid box, with the speaker as the focal part.",
        parts=unboxing(), focus="speaker",
        subtitle="Read it top down and it is the unboxing: lid, product, insert, box. The product and its cable share a level because they sit side by side.",
        cards=[("The headline", "coral", "The product is the reveal", "Everything above the speaker is a lid and everything below it is a cradle. The accent marks the speaker because the packaging exists to present it."),
               ("", "ink", "Reading the explode", ["Lid telescopes over the box walls", "Insert wells match the parts they hold", "Cable and speaker lift as one level", "Box stays put"]),
               ("", "muted", "When to use it", "Packaging reviews, supplier briefs, and launch pages. For a list of what is in the box, a table is faster.")],
        footer="unboxing · exploded axonometric"),
    "exploded-ai-stack": lambda: Figure(
        slug="exploded-ai-stack",
        title="AI agent stack · What sits under the prompt",
        desc="Exploded view of an AI agent stack: a secrets vault at the base, then tools, skills, the agent harness that runs the model, and the chat or terminal interface on top, with skills as the focal layer.",
        parts=ai_stack(), focus="skills", gap_k=0.75,
        caption=("FOCAL LAYER", "Skills are plain files the agent reads before it acts. Swap the harness or the model and they still work."),
        subtitle="Five layers pulled apart along one axis. You type at the top, the harness runs the model, and skills decide how the work gets done.",
        cards=[("The headline", "coral", "Skills are the layer you own", "The interface and the harness come from a vendor and change every few months. A skill is a markdown playbook in your repo, so it carries over when the rest of the stack is swapped."),
               ("", "ink", "Reading the explode", ["Top layer is where you type", "The dark chip is the model inside the harness", "Each card on the skills layer is one playbook", "Plugs on the tools layer are the CLIs and APIs it can call"]),
               ("", "muted", "Why the vault is at the bottom", "Every tool call runs on a scoped service token. Keep it under everything else so no layer above holds a raw secret.")],
        footer="ai agent stack · exploded axonometric"),
    "exploded-keyboard": lambda: Figure(
        slug="exploded-keyboard",
        title="Mechanical keyboard · Five layers under your fingers",
        desc="Exploded view of a mechanical keyboard: the case, the PCB with hot-swap sockets, the steel plate, a switch for every key, and the keycaps on top, with the switches as the focal part.",
        parts=keyboard(), focus="switches", gap_k=0.7,
        subtitle="Keycaps come off first. Under them every key has its own switch, held by a steel plate and plugged into the board in the case.",
        cards=[("The headline", "coral", "The switches are the feel", "Keycaps change the sound and the look. The switch under each key sets how far it travels and how hard it pushes back, so the switches get the accent."),
               ("", "ink", "Reading the explode", ["One switch per keycap, one cutout per switch", "Hot-swap sockets mean no soldering", "The case is a tray, so its front walls paint last", "Wider keys sit on one centred switch"]),
               ("", "muted", "Small parts, one primitive", "Every keycap and switch is the same rounded prism as the case, just smaller. The part box is the envelope of its grid.")],
        footer="mechanical keyboard · exploded axonometric"),
}
ANIMATED = ("exploded-phone", "exploded-unboxing", "exploded-ai-stack", "exploded-keyboard")


def render_all() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for name, make in FIGURES.items():
        for variant, skin in (("", "light"), ("-dark", "dark"), ("-full", "light")):
            fig = make()
            slug = f"{name}{variant}"
            body, vh, _ = build_svg(fig, skin, False, slug)
            sk = SKINS[skin]
            if variant == "-full":
                html = FULL.format(eyebrow=EYEBROW, title=fig.title, font=FONT_LINK, slug=slug, desc=fig.desc, vh=vh, body=body,
                                   subtitle=fig.subtitle, cards=cards_html(fig.cards), footer=fig.footer)
            else:
                html = MINIMAL.format(eyebrow=EYEBROW, title=fig.title, font=FONT_LINK, slug=slug, desc=fig.desc, vh=vh, body=body,
                                      **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})
            files[ASSETS / f"example-{slug}.html"] = html
        if name in ANIMATED:
            fig = make()
            slug = f"{name}-animated"
            body, vh, steps = build_svg(fig, "light", True, slug)
            files[ASSETS / f"example-{slug}.html"] = exploded_animated(fig, slug, body, vh, steps)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if any generated example differs from disk")
    args = parser.parse_args()
    files = render_all()
    stale = []
    for path, html in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != html:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(html, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("stale exploded examples (run scripts/build-exploded-examples.py):")
        for name in stale:
            print(f"  - {name}")
        return 1
    if args.check:
        print(f"OK exploded examples: {len(files)} files up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
