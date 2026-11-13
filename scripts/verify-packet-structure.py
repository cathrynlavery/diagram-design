#!/usr/bin/env python3
"""Check the bounded packet examples against their visible bit ruler.

This checks drawing/data consistency, not the correctness of a protocol schema.
The HTML template and SVG vocabulary are deliberately bounded; unsupported
browser styling is rejected instead of interpreted through a partial cascade.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from verify_static_svg_visibility import FONT_FAMILIES, INK, normalize, page

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
EXAMPLES = [ASSETS / f"example-packet-structure{suffix}.html" for suffix in ("", "-dark", "-full")]
ATTRIBUTES = {
    "svg": {"xmlns", "viewBox", "role", "aria-labelledby", "data-diagram-type"},
    "title": {"id"}, "desc": {"id"},
    "g": {"data-packet-axis", "data-packet-source", "data-bit-boundary", "data-packet-row",
          "data-packet-field", "data-field-name", "data-bit-offset", "data-bit-width"},
    "rect": {"x", "y", "width", "height", "fill", "stroke", "stroke-width"},
    "line": {"x1", "y1", "x2", "y2", "stroke", "stroke-width", "data-packet-baseline"},
    "text": {"x", "y", "fill", "font-size", "font-family", "font-weight", "text-anchor",
             "data-packet-label", "data-packet-row-label", "data-packet-source-label"},
}


class SvgTree(HTMLParser):
    """Collect actual SVG elements, ignoring comments and raw-text HTML titles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.roots: list[ET.Element] = []
        self.stack: list[ET.Element] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if len(dict(attrs)) != len(attrs):
            self.errors.append("duplicate HTML or SVG attribute")
        if tag == "title" and not self.stack:
            self.set_cdata_mode(tag)
        if not self.stack and tag != "svg":
            return
        node = ET.Element(tag, {"viewBox" if key == "viewbox" else key: value or "" for key, value in attrs})
        if self.stack:
            self.stack[-1].append(node)
        else:
            self.roots.append(node)
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.stack:
            if self.stack[-1].tag != tag:
                self.errors.append("unbalanced SVG markup")
            else:
                self.stack.pop()

    def handle_data(self, value):
        if self.stack:
            node = self.stack[-1]
            if len(node):
                node[-1].tail = (node[-1].tail or "") + value
            else:
                node.text = (node.text or "") + value


def integer(value: str) -> int:
    return int(value) if re.fullmatch(r"[0-9]{1,6}", value) else -1


def number(value: str) -> float:
    """SVG numbers use ASCII digits, with neither Python separators nor units."""
    if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", value.strip(" \t\r\n")):
        return math.nan
    return float(value)


def rectangle(node: ET.Element) -> tuple[float, float, float, float]:
    x, y, width, height = (number(node.get(key, "0")) for key in ("x", "y", "width", "height"))
    return x, y, x + width, y + height


def text(node: ET.Element) -> str:
    # SVG collapses ASCII white space; NBSP and other Unicode spaces retain width.
    return re.sub(r"[ \t\r\n]+", " ", (node.text or "").strip(" \t\r\n"))


def text_box(node: ET.Element) -> tuple[float, float, float, float]:
    x, y, size = (number(node.get(key, "")) for key in ("x", "y", "font-size"))
    # Use a full em for ordinary sans glyphs (W exceeds 0.8em). Only the
    # clearly narrow Latin glyphs get a smaller bound. Non-Latin fallback
    # glyphs get two em; this is a fit bound, not a font-shaping engine.
    mono = "Mono" in node.get("font-family", "")
    width = size * sum(
        2.0 if ord(char) > 127 and char != "–" else
        0.66 if mono else 0.4 if char == " " else 0.6 if char in "ijlIfrt" else 1.0
        for char in text(node)
    )
    anchor = node.get("text-anchor", "start")
    left = x - width * {"start": 0, "middle": 0.5, "end": 1}.get(anchor, 0)
    return left, y - size, left + width, y + size * 0.25


def contains(outer, inner, inset=0) -> bool:
    return all(math.isfinite(value) for value in (*outer, *inner)) and (
        outer[0] + inset <= inner[0] <= inner[2] <= outer[2] - inset
        and outer[1] + inset <= inner[1] <= inner[3] <= outer[3] - inset
    )


def near(first, second) -> bool:
    return math.isfinite(first) and math.isfinite(second) and abs(first - second) <= 0.01


def inspect(source: str) -> tuple[list[str], tuple]:
    errors = page(source)
    parser = SvgTree()
    parser.feed(source)
    parser.close()
    errors += parser.errors
    if parser.stack or len(parser.roots) != 1:
        return errors + ["expected one complete SVG"], ()
    svg = parser.roots[0]
    if svg.get("data-diagram-type") != "packet-structure":
        errors.append("SVG must declare data-diagram-type=packet-structure")
    view = [number(value) for value in re.split(r"[ \t\r\n]+", svg.get("viewBox", "").strip(" \t\r\n"))]
    if len(view) != 4 or view[:3] != [0, 0, 1200] or not 368 <= view[3] <= 1248:
        return errors + ["expected viewBox='0 0 1200 H', with H from 368 to 1248"], ()
    viewport = (0, 0, view[2], view[3])
    children = list(svg)
    if len(children) < 5 or [node.tag for node in children[:3]] != ["title", "desc", "rect"]:
        return errors + ["SVG must start with title, desc and one backdrop"], ()
    backdrop = children[2]
    paper = backdrop.get("fill", "")
    inks = INK.get(paper, set())
    if rectangle(backdrop) != viewport or not inks or not set(backdrop.attrib) <= {"x", "y", "width", "height", "fill"}:
        errors.append("backdrop must fill the viewport with house paper")
    ids = [node.get("id") for node in svg.iter() if node.get("id")]
    if len(ids) != len(set(ids)) or svg.get("role") != "img" or svg.get("aria-labelledby", "").split() != ids[:2] or len(ids) != 2:
        errors.append("SVG must name its unique title and desc IDs")
    for node in svg.iter():
        if node.tag not in ATTRIBUTES or not set(node.attrib) <= ATTRIBUTES.get(node.tag, set()):
            errors.append(f"unsupported SVG element or attribute on {node.tag}")
        if node.tag not in {"text", "title", "desc"} and text(node):
            errors.append("text must be inside a visible text element")
        if node.tag in {"text", "title", "desc", "rect", "line"} and len(node):
            errors.append(f"unsupported children in SVG {node.tag}")
        if node.tag == "text":
            if (node.get("fill") not in inks or not 12 <= number(node.get("font-size", "")) <= 28
                or normalize(node.get("font-family", "")) not in FONT_FAMILIES
                or node.get("text-anchor", "start") not in {"start", "middle", "end"}
                or not text(node) or not contains(viewport, text_box(node))):
                errors.append("SVG text must be visible, readable and inside the viewBox")
        if node.tag in {"line", "rect"} and node is not backdrop:
            if node.get("stroke") not in inks or not 1 <= number(node.get("stroke-width", "")) <= 2:
                errors.append("packet rules and field borders need visible house ink")
        if node.tag == "rect" and (node.get("fill") != paper or not contains(viewport, rectangle(node))):
            errors.append("field rectangles must use paper and remain in the viewBox")

    axes = [node for node in children if node.tag == "g" and "data-packet-axis" in node.attrib]
    rows = [node for node in children if node.tag == "g" and "data-packet-row" in node.attrib]
    captions = [node for node in children[3:] if node.tag == "text"]
    if len(axes) != 1 or not 1 <= len(rows) <= 6 or len(captions) != 2 or len(children) != 3 + len(axes) + len(rows) + len(captions):
        return errors + ["expected one bit ruler, 1 to 6 rows and two captions"], ()
    axis = axes[0]
    bits = integer(axis.get("data-packet-axis", ""))
    source_ref = axis.get("data-packet-source", "").strip()
    if bits not in {8, 16, 32, 64} or not source_ref:
        return errors + ["ruler needs 8, 16, 32 or 64 bits and a source reference"], ()
    if set(axis.attrib) != {"data-packet-axis", "data-packet-source"}:
        errors.append("unsupported bit-ruler attributes")
    base = list(axis)[0] if len(axis) else ET.Element("missing")
    left, right, baseline, y2 = (number(base.get(key, "")) for key in ("x1", "x2", "y1", "y2"))
    if base.tag != "line" or base.get("data-packet-baseline") != "true" or not near(baseline, y2) or not 64 <= left < right <= 1168:
        return errors + ["ruler needs a horizontal visible baseline"], ()
    scale = (right - left) / bits
    ticks = list(axis)[1:]
    boundaries = [integer(tick.get("data-bit-boundary", "")) for tick in ticks]
    if not 2 <= len(ticks) <= bits + 1 or boundaries != sorted(set(boundaries)) or boundaries[0] != 0 or boundaries[-1] != bits:
        errors.append("bit ruler boundaries must increase from 0 to row width")
    for tick, boundary in zip(ticks, boundaries):
        if tick.tag != "g" or set(tick.attrib) != {"data-bit-boundary"} or [node.tag for node in tick] != ["line", "text"]:
            errors.append("each bit boundary needs one tick and its printed number")
            continue
        mark, label = tick
        x = left + boundary * scale
        if not all(near(number(mark.get(key, "")), x) for key in ("x1", "x2")) or not (
            baseline - 24 <= number(mark.get("y1", "")) <= baseline - 4
            and baseline + 4 <= number(mark.get("y2", "")) <= baseline + 24
            and near(number(label.get("x", "")), x) and label.get("text-anchor") == "middle"
            and baseline - 40 <= number(label.get("y", "")) <= baseline - 16
            and text_box(label)[1] >= baseline - 40
            and text_box(label)[3] <= number(mark.get("y1", "")) - 8
            and text(label) == str(boundary)
        ):
            errors.append("bit tick geometry or printed value disagrees with the ruler")
    ruler_labels = [text_box(tick[1]) for tick in ticks if len(tick) == 2 and tick[1].tag == "text"]
    if any(first[2] + 8 > second[0] for first, second in zip(ruler_labels, ruler_labels[1:])):
        errors.append("ruler labels need at least 8px horizontal clearance; label fewer boundaries")
    field_ids: set[str] = set()
    model = []
    previous_bottom = baseline + 24
    focal_fields = 0
    for index, row in enumerate(rows):
        offset = integer(row.get("data-packet-row", ""))
        if set(row.attrib) != {"data-packet-row"} or offset != index * bits:
            errors.append("packet rows must use contiguous absolute offsets in reading order")
        labels = [node for node in row if node.tag == "text" and node.get("data-packet-row-label") == "true"]
        fields = [node for node in row if node.tag == "g" and "data-packet-field" in node.attrib]
        if len(labels) != 1 or not fields or len(row) != len(labels) + len(fields):
            errors.append("each packet row needs one offset label and its field cells")
        cursor = offset
        band = None
        for field in fields:
            fid, name = field.get("data-packet-field", ""), field.get("data-field-name", "").strip()
            start, width = integer(field.get("data-bit-offset", "")), integer(field.get("data-bit-width", ""))
            if (set(field.attrib) != {"data-packet-field", "data-field-name", "data-bit-offset", "data-bit-width"}
                or not re.fullmatch(r"[a-z][a-z0-9-]*", fid) or fid in field_ids or not name):
                errors.append("field IDs and names must be nonblank and unique")
            field_ids.add(fid)
            if start != cursor or width <= 0 or start + width > offset + bits:
                errors.append(f"{fid}: field ranges must cover the row without gaps, overlaps or wrapping")
            cursor = start + width
            if [node.tag for node in field] != ["rect", "text", "text"]:
                errors.append(f"{fid}: expected a rectangle behind name and range labels")
                continue
            rect, label, span = field
            x1, top, x2, bottom = rectangle(rect)
            if not near(x1, left + (start - offset) * scale) or not near(x2, left + (start - offset + width) * scale):
                errors.append(f"{fid}: field geometry disagrees with its bit offset or width")
            if not 64 <= bottom - top <= 176 or top < previous_bottom + 16 or band is not None and (top, bottom) != band:
                errors.append(f"{fid}: field is outside its row band or overlaps another row")
            band = (top, bottom)
            for item in (label, span):
                if item.get("text-anchor", "start") != "start" or not contains((x1, top, x2, bottom), text_box(item), 8):
                    errors.append(f"{fid}: visible label does not fit its own field")
            if text_box(label)[3] + 4 > text_box(span)[1]:
                errors.append(f"{fid}: field labels overlap")
            if (label.get("data-packet-label") != "name" or text(label) != name
                or span.get("data-packet-label") != "range" or text(span) != f"{start}–{start + width - 1} / {width}b"):
                errors.append(f"{fid}: visible name or bit range disagrees with field data")
            focal_fields += rect.get("stroke") in {"#bf4520", "#f08a59"}
            model.append((offset, fid, name, start, width))
        if cursor != offset + bits:
            errors.append("field ranges must fill each declared row")
        if band:
            if labels and (text(labels[0]) != str(offset) or text_box(labels[0])[2] > left - 12
                           or not band[0] <= text_box(labels[0])[1] <= text_box(labels[0])[3] <= band[1]):
                errors.append("row offset label must identify its own row")
            previous_bottom = band[1]
    if not 2 <= len(model) <= 9 or focal_fields > 1:
        errors.append("packet overview needs 2 to 9 fields and at most one focal field")
    sources = [node for node in captions if node.get("data-packet-source-label") == "true"]
    headings = [node for node in captions if "data-packet-source-label" not in node.attrib]
    tick_tops = [text_box(tick[1])[1] for tick in ticks if len(tick) == 2 and tick[1].tag == "text"]
    if len(headings) != 1 or not tick_tops or text_box(headings[0])[3] + 8 > min(tick_tops):
        errors.append("packet heading must remain above the bit ruler")
    if len(sources) != 1 or text(sources[0]) != f"{source_ref} · {len(rows) * bits} bits" or text_box(sources[0])[1] < previous_bottom + 24:
        errors.append("source caption must print the source and complete bit length below the fields")
    return errors, (bits, source_ref, tuple(model))


def check(path: Path) -> list[str]:
    try:
        return inspect(path.read_text(encoding="utf-8"))[0]
    except (OSError, UnicodeError) as exc:
        return [f"cannot read packet example: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check the three shipped variants and their field parity")
    args = parser.parse_args()
    paths = EXAMPLES if args.all or not args.paths else args.paths
    failed, models = False, []
    for path in paths:
        errors = check(path)
        if not errors:
            models.append(inspect(path.read_text(encoding="utf-8"))[1])
        print(f"{'FAIL' if errors else 'PASS'} {path.name}")
        for error in errors:
            print(f"  {error}")
        failed |= bool(errors)
    if args.all and not failed and len(set(models)) != 1:
        print("FAIL packet variants must preserve the same bit layout, field labels and source")
        failed = True
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
