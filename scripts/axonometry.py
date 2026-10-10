"""Shared 2:1 dimetric projection for the axonometric example builders.

iso(x, y, z) = [x - y, (x + y) / 2 - z]. A rounded-rectangle footprint of corner
radius r projects to straight edges joined by quarter arcs of one ellipse with
rx = r * sqrt(2) and ry = r / sqrt(2), so one prism covers slab, box, and cylinder.
Used by build-exploded-examples.py and build-axonometric-plan-examples.py; the
verifiers reimplement the projection on purpose and do not import this module.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "skills/diagram-design/assets"
MOTION_TEMPLATE = ASSETS / "template-motion.html"

S2 = math.sqrt(2)

# Face tones per skin. Every value is a style-guide role or an rgba() of one.
SKINS = {
    "light": dict(
        paper="#f5f5f5", ink="#2d3142", muted="#4f5d75", soft="#5a6580", accent="#bf4520",
        ink_rgb="45,49,66", acc_rgb="191,69,32", base="#ffffff", rule="rgba(45,49,66,0.12)",
        shade=(None, "rgba(45,49,66,0.07)", "rgba(45,49,66,0.15)"),
        focal=("rgba(191,69,32,0.10)", "rgba(191,69,32,0.20)", "rgba(191,69,32,0.32)"),
        cavity="rgba(45,49,66,0.10)", floor="rgba(45,49,66,0.04)", well="rgba(45,49,66,0.14)",
        screen="#2d3142", island="#111111", chip_top="#4f5d75", chip_side="#2d3142",
        sil="#2d3142", inner="rgba(45,49,66,0.55)", trace="rgba(45,49,66,0.30)",
        lead="rgba(45,49,66,0.40)", lead_acc="rgba(191,69,32,0.60)", inner_acc="rgba(191,69,32,0.70)",
        lens="#2d3142", lens_ring="rgba(245,245,245,0.35)",
    ),
    "dark": dict(
        paper="#2d3142", ink="#f5f5f5", muted="#bfc0c0", soft="#949eb2", accent="#f08a59",
        ink_rgb="245,245,245", acc_rgb="240,138,89", base="#393e53", rule="rgba(245,245,245,0.12)",
        shade=("rgba(245,245,245,0.10)", None, "rgba(45,49,66,0.45)"),
        focal=("rgba(240,138,89,0.18)", None, "rgba(45,49,66,0.45)"),
        cavity="rgba(45,49,66,0.55)", floor="rgba(45,49,66,0.25)", well="rgba(45,49,66,0.40)",
        screen="#111111", island="#2d3142", chip_top="#949eb2", chip_side="#2d3142",
        sil="#f5f5f5", inner="rgba(245,245,245,0.45)", trace="rgba(245,245,245,0.30)",
        lead="rgba(245,245,245,0.40)", lead_acc="rgba(240,138,89,0.60)", inner_acc="rgba(240,138,89,0.70)",
        lens="#111111", lens_ring="rgba(245,245,245,0.35)",
    ),
}


# ---------------------------------------------------------------- projection


def f(value: float) -> str:
    rounded = round(value, 2)
    return str(int(rounded)) if rounded == int(rounded) else f"{rounded:g}"


class Proj:
    """iso(x, y, z) = [x - y, (x + y) / 2 - z], shifted to the drawing origin."""

    def __init__(self, ox: float, oy: float):
        self.ox, self.oy = ox, oy

    def iso(self, x, y, z):
        return (self.ox + x - y, self.oy + (x + y) / 2 - z)


@dataclass
class Rect:
    """A rounded-rectangle footprint. r = 0 is a box; r = w/2 = d/2 is a cylinder."""

    x0: float
    y0: float
    x1: float
    y1: float
    r: float = 0

    def centers(self):
        r = self.r
        return [(self.x1 - r, self.y1 - r), (self.x0 + r, self.y1 - r),
                (self.x0 + r, self.y0 + r), (self.x1 - r, self.y0 + r)]

    def inset(self, m, r=None):
        return Rect(self.x0 + m, self.y0 + m, self.x1 - m, self.y1 - m,
                    max(0, self.r - m) if r is None else r)

    def attr(self):
        return " ".join(f(v) for v in (self.x0, self.y0, self.x1, self.y1, self.r))


def corner(theta):
    return int(math.floor(theta / 90)) % 4


def point(P, rect, theta, z, k=None):
    k = corner(theta) if k is None else k
    cx, cy = rect.centers()[k]
    t = math.radians(theta)
    return P.iso(cx + rect.r * math.cos(t), cy + rect.r * math.sin(t), z)


def walk(P, rect, a, b, z):
    """Path commands from outline angle a to b. Each corner is a quarter of one 2:1 ellipse."""
    cmds = []
    rx, ry = rect.r * S2, rect.r / S2
    rising = b > a
    th = a
    while (b - th) * (1 if rising else -1) > 1e-9:
        nxt = min(b, (math.floor(th / 90) + 1) * 90) if rising else max(b, (math.ceil(th / 90) - 1) * 90)
        k = corner((th + nxt) / 2)
        end = point(P, rect, nxt, z, k)
        if rect.r > 0:
            cmds.append(f"A {f(rx)} {f(ry)} 0 0 {1 if rising else 0} {f(end[0])} {f(end[1])}")
        else:
            cmds.append(f"L {f(end[0])} {f(end[1])}")
        th = nxt
        if (b - th) * (1 if rising else -1) > 1e-9:
            nx = point(P, rect, th, z, corner(th + (1 if rising else -1)))
            cmds.append(f"L {f(nx[0])} {f(nx[1])}")
    return " ".join(cmds)


def M(p):
    return f"M {f(p[0])} {f(p[1])}"


def L(p):
    return f"L {f(p[0])} {f(p[1])}"


def outline(P, rect, z):
    return f"{M(point(P, rect, 0, z, 0))} {walk(P, rect, 0, 360, z)} Z"


def prism(P, rect, z0, z1):
    """Top face, the two visible side bands, the silhouette, the top-front edge, and the label anchor."""
    lt, ft, rt = point(P, rect, 135, z1), point(P, rect, 45, z1), point(P, rect, -45, z1)
    lb, fb, rb = point(P, rect, 135, z0), point(P, rect, 45, z0), point(P, rect, -45, z0)
    edge = f"{M(lt)} {walk(P, rect, 135, -45, z1)}"
    if rect.r == 0:
        edge += f" {M(ft)} {L(fb)}"
    n = 24
    poly = [point(P, rect, 135 + 180 * i / n, z1) for i in range(n + 1)]
    poly += [point(P, rect, -45 + 180 * i / n, z0) for i in range(n + 1)]
    return dict(
        top=outline(P, rect, z1),
        left=f"{M(lt)} {walk(P, rect, 135, 45, z1)} {L(fb)} {walk(P, rect, 45, 135, z0)} Z",
        right=f"{M(ft)} {walk(P, rect, 45, -45, z1)} {L(rb)} {walk(P, rect, -45, 45, z0)} Z",
        sil=f"{M(lt)} {walk(P, rect, 135, 315, z1)} {L(rb)} {walk(P, rect, -45, 135, z0)} Z",
        edge=edge,
        rx=rt[0],
        anchor=(rt[0], (rt[1] + rb[1]) / 2),
        poly=poly,
    )


def solid(P, rect, z0, z1, sk, tones, stroke, inner, role=True):
    pr = prism(P, rect, z0, z1)
    tag = ' data-role="silhouette"' if role else ""
    out = [f'<path{tag} d="{pr["sil"]}" fill="{sk["base"]}"/>']
    for path, tone in zip((pr["top"], pr["left"], pr["right"]), tones):
        if tone:
            out.append(f'<path d="{path}" fill="{tone}"/>')
    return pr, out


def finish(pr, stroke, inner, sw=1.2):
    return [f'<path d="{pr["edge"]}" fill="none" stroke="{inner}" stroke-width="0.8"/>',
            f'<path d="{pr["sil"]}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"/>']


def styles(sk, focal):
    return (sk["focal"] if focal else sk["shade"], sk["accent"] if focal else sk["sil"],
            sk["inner_acc"] if focal else sk["inner"])


# ---------------------------------------------------------------- pages

FONT_LINK = "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap"

MINIMAL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link href="{font}" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --color-paper:   {paper};
      --color-ink:     {ink};
      --color-muted:   {muted};
      --color-accent:  {accent};
      --font-sans:     'Geist', system-ui, sans-serif;
      --font-serif:    'Instrument Serif', serif;
      --font-mono:     'Geist Mono', ui-monospace, monospace;
    }}

    body {{
      font-family: var(--font-sans);
      background: var(--color-paper);
      color: var(--color-ink);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 3rem 2rem;
    }}

    .frame {{ max-width: 1200px; width: 100%; }}
    .diagram-container {{ width: 100%; overflow-x: auto; }}

    .eyebrow {{
      font-family: var(--font-mono);
      font-size: 0.66rem;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--color-muted);
      margin-bottom: 0.5rem;
    }}

    h1 {{
      font-family: var(--font-serif);
      font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem);
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 1.15;
      color: var(--color-ink);
      margin-bottom: 1.5rem;
    }}

    svg {{ width: 100%; min-width: 1000px; display: block; }}
    @media print {{
      .diagram-container {{ overflow-x: visible; }}
      svg {{ min-width: 0; }}
    }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{eyebrow}</p>
    <h1>{title}</h1>

    <div class="diagram-container">
      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
        <title id="{slug}-title">{title}</title>
        <desc id="{slug}-desc">{desc}</desc>
        {body}
      </svg>
    </div>
  </div>
</body>
</html>
"""

FULL = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <link href="{font}" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{ --color-paper:#f5f5f5; --color-paper-2:#ececec; --color-ink:#2d3142; --color-muted:#4f5d75; --color-soft:#5a6580; --color-rule:rgba(45,49,66,0.12); --color-accent:#bf4520; --color-link:#2e5aa8; --font-sans:'Geist',system-ui,sans-serif; --font-serif:'Instrument Serif',serif; --font-mono:'Geist Mono',ui-monospace,monospace; }}
    body {{ font-family: var(--font-sans); background: var(--color-paper); min-height: 100vh; padding: 3rem 2rem; color: var(--color-ink); }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .header {{ margin-bottom: 2.5rem; }}
    .header-eyebrow {{ font-family: var(--font-mono); font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.75rem; }}
    h1 {{ font-family: var(--font-serif); font-size: clamp(1.75rem, 3vw + 1rem, 2.5rem); font-weight: 400; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 0.5rem; }}
    .subtitle {{ font-size: 1rem; line-height: 1.55; color: var(--color-muted); max-width: 58ch; }}
    .diagram-container {{ overflow-x: auto; }}
    svg {{ width: 100%; min-width: 1000px; display: block; }}
    @media print {{ .diagram-container {{ overflow-x: visible; }} svg {{ min-width: 0; }} }}
    .cards {{ display: grid; grid-template-columns: 1.1fr 1fr 0.9fr; gap: 1rem; margin-top: 1.5rem; }}
    @media (max-width: 820px) {{ .cards {{ grid-template-columns: 1fr; }} }}
    .card {{ background: #fff; border-radius: 6px; border: 1px solid var(--color-rule); padding: 1.25rem; }}
    .card .eyebrow {{ font-family: var(--font-mono); font-size: 0.5rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.5rem; }}
    .card-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.875rem; padding-bottom: 0.875rem; border-bottom: 1px solid rgba(45,49,66,0.08); }}
    .card-dot {{ width: 7px; height: 7px; border-radius: 50%; }}
    .card-dot.ink {{ background: var(--color-ink); }} .card-dot.muted {{ background: var(--color-muted); }} .card-dot.coral {{ background: var(--color-accent); }}
    .card h3 {{ font-size: 0.875rem; font-weight: 600; }}
    .card p, .card ul {{ color: var(--color-muted); font-size: 0.8125rem; line-height: 1.55; list-style: none; }}
    .card li {{ margin-bottom: 0.3rem; padding-left: 0.875rem; position: relative; }}
    .card li::before {{ content: '·'; position: absolute; left: 0.2rem; color: rgba(45,49,66,0.45); }}
    .footer {{ margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(45,49,66,0.10); font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.06em; color: var(--color-soft); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <p class="header-eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p class="subtitle">{subtitle}</p>
    </div>

    <div class="diagram-container">
      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
        <title id="{slug}-title">{title}</title>
        <desc id="{slug}-desc">{desc}</desc>
        {body}
      </svg>
    </div>

    <div class="cards">
{cards}
    </div>

    <div class="footer">
      <span>{footer}</span>
      <span>example · diagram design</span>
    </div>
  </div>
</body>
</html>
"""

def animated_page(title: str, desc: str, slug: str, body: str, vh: int, steps: int, eyebrow: str, css: str, noscript: str) -> str:
    """Start from template-motion.html so the controller, controls, and fallbacks stay canonical."""
    src = MOTION_TEMPLATE.read_text(encoding="utf-8")
    src = src.replace("<title>Motion diagram template</title>", f"<title>{title}</title>", 1)
    src = src.replace("--motion-step: 480ms;", "--motion-step: 600ms;", 1)
    src = src.replace("--motion-hold: 720ms;", "--motion-hold: 900ms;", 1)
    src = src.replace("--motion-total: 3600ms;", f"--motion-total: {steps * 900}ms;", 1)
    src = src.replace("min-width: 960px;", "min-width: 1000px;", 1)
    src = src.replace("  </style>", css + "  </style>", 1)
    start = src.index("  <!-- Replace template-motion")
    end = src.index("    <div data-motion-controls")
    main = (f'  <main data-motion-root data-motion-mode="reveal" data-step-count="{steps}" data-step-current="{steps}" data-frame="static" data-static-frame="complete">\n'
            f'    <p class="eyebrow">{eyebrow}</p>\n'
            f'    <h1>{title}</h1>\n\n'
            f'    <div class="diagram-container">\n'
            f'      <svg viewBox="0 0 1000 {vh}" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">\n'
            f'        <title id="{slug}-title">{title}</title>\n'
            f'        <desc id="{slug}-desc">{desc}</desc>\n'
            f'        {body}\n'
            f'      </svg>\n'
            f'    </div>\n\n')
    src = src[:start] + main + src[end:]
    src = re.sub(r'Step <span data-motion-step-label>\d+</span> of \d+',
                 f'Step <span data-motion-step-label>{steps}</span> of {steps}', src, count=1)
    src = src.replace("The complete final diagram is shown above.", noscript, 1)
    return src


def cards_html(cards):
    out = []
    for eyebrow, dot, title, body in cards:
        inner = f"<p>{body}</p>" if isinstance(body, str) else "<ul>" + "".join(f"<li>{item}</li>" for item in body) + "</ul>"
        eb = f'<p class="eyebrow">{eyebrow}</p>' if eyebrow else ""
        out.append(f'      <div class="card">\n        {eb}\n        <div class="card-header"><span class="card-dot {dot}"></span><h3>{title}</h3></div>\n        {inner}\n      </div>')
    return "\n".join(out)
