#!/usr/bin/env python3
"""Run the repository's automated diagram gates on one generated file.

Wraps the two checkers SKILL.md §9 tells an agent to run — the packaged
``self_check.py`` (accessible-SVG contract, single-file safety) and
``scripts/verify-geometry.py`` (label masks clipped by later nodes) — and
adds the checks a model most often gets wrong: leftover template
placeholders, a viewBox off the preset, a node outside the canvas, a label
wider than its box, and an arrow that ends where no node is. Every check is
calibrated to report nothing on the shipped examples. Findings are plain
sentences the model can act on in a repair round.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent
SELF_CHECK = ROOT / "skills" / "diagram-design" / "scripts" / "self_check.py"
GEOMETRY = ROOT / "scripts" / "verify-geometry.py"

PLACEHOLDERS = (
    "[diagram-slug]",
    "[Diagram title]",
    "[Type]",
    "[One sentence describing what the diagram shows]",
    "Draw arrows first, then nodes. Replace with your content.",
)
FENCE_RE = re.compile(r"```(?:html)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_html(reply: str) -> str | None:
    """The HTML document inside a model reply, fenced or bare."""
    fenced = FENCE_RE.findall(reply)
    candidates = [block for block in fenced if "<svg" in block.casefold()] or fenced
    if candidates:
        text = max(candidates, key=len).strip()
    else:
        text = reply.strip()
    start = text.casefold().find("<!doctype html")
    if start < 0:
        start = text.casefold().find("<html")
    end = text.casefold().rfind("</html>")
    if start < 0 or end < 0:
        return None
    return text[start : end + len("</html>")] + "\n"


RECT_RE = re.compile(
    r'<rect\b[^>]*?\bx="(-?[\d.]+)"\s+y="(-?[\d.]+)"\s+width="([\d.]+)"\s+height="([\d.]+)"', re.IGNORECASE
)
SHAPE_RE = re.compile(r"<(rect|polygon|ellipse|circle)\b([^>]*)>", re.IGNORECASE)
ARROW_RE = re.compile(r'<(line|path|polyline)\b([^>]*\bmarker-end="url\(#[^"]+\)"[^>]*)>', re.IGNORECASE)
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
TEXT_RE = re.compile(r'<text\b([^>]*)>([^<]*)</text>', re.IGNORECASE)
# Average advance of Geist at weight 600, as a fraction of font-size; deliberately
# low so only clear overflows are reported.
GLYPH_EM = 0.5
NODE_MIN = (60.0, 40.0)
ARROW_TOLERANCE = 24.0
HAIRLINE_RE = re.compile(r'<line\b([^>]*)/?>', re.IGNORECASE)
# Types whose arrows join boxes. Sequence messages end on lifelines and axis
# arrows on charts point into space, so the dangling-arrow check skips them.
ARROW_TYPES = frozenset({
    "architecture", "data-flow", "db-schema", "dependency", "deployment", "dp-integration",
    "er", "flowchart", "high-level", "it-state", "layers", "loop", "medallion", "nested",
    "org-chart", "process", "state", "swimlane", "tree", "uml-class",
})


def _attr(attrs: str, name: str) -> str | None:
    match = re.search(rf'\b{name}="([^"]*)"', attrs, re.IGNORECASE)
    return match.group(1) if match else None


def _shape_boxes(svg: str) -> list[tuple[float, float, float, float]]:
    """Bounding boxes of everything an arrow could legitimately end on."""
    boxes = []
    for tag, attrs in SHAPE_RE.findall(svg):
        tag = tag.lower()
        try:
            if tag == "rect":
                x, y, w, h = (float(_attr(attrs, k) or 0) for k in ("x", "y", "width", "height"))
            elif tag == "polygon":
                nums = [float(n) for n in NUM_RE.findall(_attr(attrs, "points") or "")]
                xs, ys = nums[0::2], nums[1::2]
                if not xs:
                    continue
                x, y, w, h = min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
            elif tag == "circle":
                cx, cy, r = (float(_attr(attrs, k) or 0) for k in ("cx", "cy", "r"))
                x, y, w, h = cx - r, cy - r, 2 * r, 2 * r
            else:
                cx, cy, rx, ry = (float(_attr(attrs, k) or 0) for k in ("cx", "cy", "rx", "ry"))
                x, y, w, h = cx - rx, cy - ry, 2 * rx, 2 * ry
        except ValueError:
            continue
        # Label masks are 8-14px tall; anything an arrow may end on is taller.
        if w >= 24 and h >= 20:
            boxes.append((x, y, w, h))
    return boxes


def _arrow_span(tag: str, attrs: str) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Start and end of an arrow, for the absolute-command paths the templates use."""
    try:
        if tag == "line":
            x1, y1, x2, y2 = (float(_attr(attrs, k) or 0) for k in ("x1", "y1", "x2", "y2"))
            return (x1, y1), (x2, y2)
        data = _attr(attrs, "d") if tag == "path" else _attr(attrs, "points")
        if not data or re.search(r"[a-zHV]", data):
            return None  # relative or H/V commands: the end point is not the last pair
        nums = [float(n) for n in NUM_RE.findall(data)]
        if len(nums) < 4:
            return None
        return (nums[0], nums[1]), (nums[-2], nums[-1])
    except ValueError:
        return None


def _legend_top(svg: str, min_x: float, width: float, min_y: float, height: float) -> float:
    """The y of the legend hairline (SKILL.md §6), below which arrows are samples."""
    best = None
    for attrs in HAIRLINE_RE.findall(svg):
        if "marker-end" in attrs:
            continue
        try:
            x1, y1, x2, y2 = (float(_attr(attrs, k) or 0) for k in ("x1", "y1", "x2", "y2"))
        except ValueError:
            continue
        if abs(y1 - y2) < 1 and abs(x2 - x1) >= 0.6 * width and y1 > min_y + height / 2:
            best = y1 if best is None else max(best, y1)
    # Without a hairline, only the bottom strip the legend would occupy is exempt.
    return best if best is not None else min_y + height - 60


def _near_box(point: tuple[float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
    px, py = point
    for x, y, w, h in boxes:
        if x - ARROW_TOLERANCE <= px <= x + w + ARROW_TOLERANCE and y - ARROW_TOLERANCE <= py <= y + h + ARROW_TOLERANCE:
            return True
    return False


def layout_findings(html: str, type_slug: str | None = None) -> list[str]:
    """Defects the shipped gates do not see: overflow and dangling arrows."""
    findings = []
    boxes = VIEWBOX_RE.findall(html)
    if not boxes:
        return findings
    try:
        min_x, min_y, width, height = (float(v) for v in boxes[0].split())
    except ValueError:
        return findings
    max_x, max_y = min_x + width, min_y + height
    svg_match = re.search(r"<svg\b.*?</svg>", html, re.DOTALL | re.IGNORECASE)
    svg = svg_match.group(0) if svg_match else html
    for x, y, w, h in RECT_RE.findall(svg):
        x, y, w, h = float(x), float(y), float(w), float(h)
        if w >= NODE_MIN[0] and h >= NODE_MIN[1] and (x + w > max_x + 0.5 or y + h > max_y + 0.5 or x < min_x - 0.5 or y < min_y - 0.5):
            findings.append(
                f"node rect at ({x:g},{y:g}) {w:g}x{h:g} extends beyond the viewBox {boxes[0]}; "
                "shrink the layout or its gaps so every node keeps a 40px margin"
            )
    nodes = [(float(x), float(y), float(w), float(h)) for x, y, w, h in RECT_RE.findall(svg)
             if float(w) >= NODE_MIN[0] and float(h) >= NODE_MIN[1]]
    for attrs, text in TEXT_RE.findall(svg):
        label = re.sub(r"\s+", " ", text).strip()
        size = _attr(attrs, "font-size")
        anchor = (_attr(attrs, "text-anchor") or "").lower()
        if not label or not size or anchor != "middle":
            continue
        try:
            fs, tx, ty = float(size), float(_attr(attrs, "x") or "nan"), float(_attr(attrs, "y") or "nan")
        except ValueError:
            continue
        if fs < 11 or tx != tx or ty != ty:
            continue
        holders = [n for n in nodes if n[0] <= tx <= n[0] + n[2] and n[1] <= ty <= n[1] + n[3]]
        if not holders:
            continue
        box = min(holders, key=lambda n: n[2] * n[3])
        estimate = len(label) * fs * GLYPH_EM
        if estimate > box[2] - 8:
            findings.append(
                f"text {label!r} at {fs:g}px is about {estimate:.0f}px wide but its node box is only {box[2]:g}px; "
                "widen the box, shorten the label, or break it into two <text> lines"
            )
    if type_slug is not None and type_slug not in ARROW_TYPES:
        return findings
    shapes = _shape_boxes(svg)
    legend_top = _legend_top(svg, min_x, width, min_y, height)
    for tag, attrs in ARROW_RE.findall(svg):
        span = _arrow_span(tag.lower(), attrs)
        if span is None:
            continue
        (sx, sy), end = span
        if sy >= legend_top - 2 and end[1] >= legend_top - 2:
            continue  # legend key sample
        if not _near_box(end, shapes):
            findings.append(
                f"arrow ({tag.lower()} with marker-end) ends at ({end[0]:g},{end[1]:g}) where there is no node; "
                "extend it to the target box or remove it"
            )
    return findings


def structural_findings(html: str, expected_view_box: str | None = None) -> list[str]:
    findings = []
    for placeholder in PLACEHOLDERS:
        if placeholder in html:
            findings.append(f"template placeholder left in the file: {placeholder!r}")
    svgs = re.findall(r"<svg\b", html, re.IGNORECASE)
    if len(svgs) != 1:
        findings.append(f"expected exactly one <svg> element, found {len(svgs)}")
    boxes = VIEWBOX_RE.findall(html)
    if not boxes:
        findings.append("the <svg> has no viewBox attribute")
    elif expected_view_box:
        try:
            ex, ey, ew, eh = (int(float(v)) for v in expected_view_box.split())
            x, y, w, h = (int(float(v)) for v in boxes[0].split())
        except ValueError:
            findings.append(f"viewBox {boxes[0]!r} is not four numbers")
        else:
            if (x, y, w) != (ex, ey, ew) or not eh <= h <= eh + 120:
                findings.append(
                    f'viewBox is "{boxes[0]}" but the size preset requires "{expected_view_box}" '
                    "(height may grow by up to 120px for a legend strip)"
                )
    if "<script" in html.casefold() and "data-motion-mode" not in html:
        findings.append("static diagrams must not contain a <script> element")
    return findings


def gate_findings(path: Path) -> list[str]:
    findings = []
    try:
        self_check = _load(SELF_CHECK, "self_check")
        findings.extend(f"self_check: {error}" for error in self_check.verify(path))
    except Exception as exc:  # noqa: BLE001 - a crashed gate is itself a finding
        findings.append(f"self_check crashed: {exc}")
    if GEOMETRY.is_file():
        try:
            geometry = _load(GEOMETRY, "verify_geometry")
            findings.extend(f"geometry: {line}" for line in geometry.check(path))
        except Exception as exc:  # noqa: BLE001
            findings.append(f"verify-geometry crashed: {exc}")
    return findings


def verify_file(path: Path, expected_view_box: str | None = None, type_slug: str | None = None) -> list[str]:
    html = path.read_text(encoding="utf-8")
    return structural_findings(html, expected_view_box) + layout_findings(html, type_slug) + gate_findings(path)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: verify.py <diagram.html> [expected viewBox] [type]")
        return 2
    path = Path(sys.argv[1])
    findings = verify_file(path, sys.argv[2] if len(sys.argv) > 2 else None, sys.argv[3] if len(sys.argv) > 3 else None)
    for finding in findings:
        print(f"  - {finding}")
    print(("FAIL " if findings else "OK ") + str(path))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
