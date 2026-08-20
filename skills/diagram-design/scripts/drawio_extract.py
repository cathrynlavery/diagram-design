#!/usr/bin/env python3
"""Extract a normalized intermediate representation (IR) from a draw.io file.

The deterministic half of the draw.io import flow: this script never makes a
design decision. It decodes whatever draw.io wrote (raw XML, deflate+base64
payloads, PNG/SVG files with an embedded ``mxfile``), flattens the mxGraphModel
into absolute-positioned nodes and edges, and reports structural signals — hubs,
containers, depth, cycles, leaf clusters — that the skill uses to pick a diagram
type and a level of detail.

Usage:
    python3 drawio_extract.py <file.drawio> [--page N|NAME] [--json]
                             [--max-rows N] [--out PATH]

Default output is a compact Markdown digest meant to be read into context.
``--json`` emits the full IR instead (every node, every edge, every style).

Exit codes: 0 ok, 2 unreadable / unsupported input.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import struct
import sys
import zlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree as ET

# --------------------------------------------------------------------------
# container / payload decoding
# --------------------------------------------------------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024


def _configure_stdout_utf8() -> None:
    """Emit digests as UTF-8 even when Windows selects a legacy codepage."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


class PayloadTooLarge(ValueError):
    """Raised when compressed metadata expands beyond the supported limit."""


def _fail(msg: str) -> "NoReturn":  # type: ignore[valid-type]
    print(f"drawio_extract: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _reject_unsafe_xml(xml: str, source: str) -> None:
    """Reject declarations that can make XML parsing expand external data."""
    upper = xml.upper()
    if "<!DOCTYPE" in upper or "<!ENTITY" in upper:
        _fail(f"{source}: DTD and entity declarations are not supported")


def _decompress_limited(data: bytes, wbits: int, limit: int = MAX_XML_BYTES) -> bytes:
    """Decompress without allowing a small payload to expand without bound."""
    decompressor = zlib.decompressobj(wbits)
    output = bytearray()
    chunk = data
    while chunk:
        remaining = limit + 1 - len(output)
        if remaining <= 0:
            raise PayloadTooLarge(f"decoded payload exceeds {limit} bytes")
        output.extend(decompressor.decompress(chunk, remaining))
        if len(output) > limit:
            raise PayloadTooLarge(f"decoded payload exceeds {limit} bytes")
        chunk = decompressor.unconsumed_tail
    if not decompressor.eof:
        raise zlib.error("incomplete compressed payload")
    remaining = limit + 1 - len(output)
    if remaining <= 0:
        raise PayloadTooLarge(f"decoded payload exceeds {limit} bytes")
    output.extend(decompressor.flush(remaining))
    if len(output) > limit:
        raise PayloadTooLarge(f"decoded payload exceeds {limit} bytes")
    return bytes(output)


def _inflate(payload: str) -> str | None:
    """Undo draw.io's base64 + raw-deflate + URL-encoding pipeline."""
    try:
        raw = base64.b64decode(payload, validate=False)
    except Exception:
        return None
    for wbits in (-15, 15, 47):
        try:
            text = _decompress_limited(raw, wbits).decode("utf-8", "replace")
        except PayloadTooLarge:
            _fail(
                f"decoded diagram exceeds the {MAX_XML_BYTES // (1024 * 1024)} MiB limit"
            )
        except Exception:
            continue
        # draw.io URL-encodes before deflating; unquote is a no-op if it didn't.
        return unquote(text)
    return None


def _png_embedded_xml(data: bytes) -> str | None:
    """Pull the ``mxfile`` tEXt/zTXt chunk out of a draw.io-exported PNG."""
    pos = len(PNG_MAGIC)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        ctype = data[pos + 4 : pos + 8]
        body_end = pos + 8 + length
        chunk_end = body_end + 4
        if chunk_end > len(data):
            _fail("PNG has a truncated metadata chunk")
        body = data[pos + 8 : body_end]
        pos = chunk_end
        if ctype not in (b"tEXt", b"zTXt", b"iTXt"):
            if ctype == b"IEND":
                break
            continue
        key, _, rest = body.partition(b"\x00")
        if key.lower() != b"mxfile":
            continue
        try:
            if ctype == b"tEXt":
                value = rest
            elif ctype == b"zTXt":
                value = _decompress_limited(rest[1:], 15)
            else:  # iTXt: compression flag, method, lang, translated key, text
                flag = rest[0:1]
                tail = rest[2:].split(b"\x00", 2)[-1]
                value = _decompress_limited(tail, 15) if flag == b"\x01" else tail
        except PayloadTooLarge:
            _fail(
                f"embedded PNG diagram exceeds the "
                f"{MAX_XML_BYTES // (1024 * 1024)} MiB limit"
            )
        except (IndexError, ValueError, zlib.error):
            _fail("PNG has invalid compressed draw.io metadata")
        return unquote(value.decode("utf-8", "replace"))
    return None


def _svg_embedded_xml(text: str) -> str | None:
    for match in re.finditer(
        r"\bcontent\s*=\s*([\"'])(.*?)\1", text, flags=re.IGNORECASE | re.DOTALL
    ):
        candidate = html.unescape(match.group(2))
        if "<mxfile" in candidate or "<mxGraphModel" in candidate:
            return candidate
    return None


def load_mxfile(path: Path) -> str:
    """Return the ``<mxfile>`` (or bare ``<mxGraphModel>``) XML for any input."""
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        _fail(
            f"{path.name}: input is {size} bytes; maximum is "
            f"{MAX_INPUT_BYTES // (1024 * 1024)} MiB"
        )
    data = path.read_bytes()
    if data.startswith(PNG_MAGIC):
        xml = _png_embedded_xml(data)
        if not xml:
            _fail(f"{path.name}: PNG has no embedded draw.io diagram")
        return xml
    text = data.decode("utf-8", "replace").lstrip("﻿").strip()
    if "<mxfile" in text or "<mxGraphModel" in text:
        return text
    if "<svg" in text[:2000]:
        xml = _svg_embedded_xml(text)
        if not xml:
            _fail(f"{path.name}: SVG has no embedded draw.io diagram")
        return xml
    inflated = _inflate(text)
    if inflated and "<mxGraphModel" in inflated:
        return inflated
    _fail(f"{path.name}: not a draw.io file (no mxfile, mxGraphModel, or payload)")


# --------------------------------------------------------------------------
# style + label helpers
# --------------------------------------------------------------------------

BR_RE = re.compile(r"<br\s*/?>|</p\s*>|</div\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


def parse_style(style: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not style:
        return out
    for part in style.split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        out[key.strip()] = value.strip() if sep else "1"
    return out


def clean_label(value: str | None) -> str:
    """draw.io labels are often HTML fragments; flatten to plain text lines."""
    if not value:
        return ""
    text = BR_RE.sub("\n", value)
    text = TAG_RE.sub("", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


SHAPE_FAMILIES = (
    ("mxgraph.aws", "aws"),
    ("mxgraph.azure", "azure"),
    ("mxgraph.gcp", "gcp"),
    ("mxgraph.kubernetes", "kubernetes"),
    ("mxgraph.cisco", "network"),
    ("mxgraph.veeam", "infra"),
    ("mxgraph.flowchart", "flowchart"),
    ("mxgraph.bpmn", "bpmn"),
    ("mxgraph.er", "er"),
    ("mxgraph.sysml", "uml"),
    ("mxgraph.archimate", "archimate"),
)

# style key -> canonical shape name, checked in order
SHAPE_KEYS = (
    ("swimlane", "swimlane"),
    ("ellipse", "ellipse"),
    ("rhombus", "rhombus"),
    ("triangle", "triangle"),
    ("cylinder", "cylinder"),
    ("cylinder3", "cylinder"),
    ("hexagon", "hexagon"),
    ("cloud", "cloud"),
    ("actor", "actor"),
    ("umlActor", "actor"),
    ("note", "note"),
    ("card", "card"),
    ("step", "step"),
    ("process", "process"),
    ("parallelogram", "parallelogram"),
    ("document", "document"),
    ("datastore", "cylinder"),
    ("umlLifeline", "lifeline"),
    ("umlFrame", "frame"),
    ("table", "table"),
    ("tableRow", "table-row"),
    ("partialRectangle", "table-row"),
    ("image", "image"),
    ("text", "text"),
    ("group", "group"),
)


def classify_shape(style: dict[str, str]) -> str:
    raw = style.get("shape", "")
    if raw:
        for key, name in SHAPE_KEYS:
            if raw == key or raw.startswith(key):
                return name
        for prefix, family in SHAPE_FAMILIES:
            if raw.startswith(prefix):
                return f"icon:{family}"
        return f"shape:{raw}"
    for key, name in SHAPE_KEYS:
        if key in style:
            return name
    if style.get("ellipse") == "1":
        return "ellipse"
    return "rect"


def shape_family(shape: str) -> str:
    if shape.startswith("icon:"):
        return shape.split(":", 1)[1]
    if shape.startswith("shape:"):
        return "custom"
    return shape


# --------------------------------------------------------------------------
# IR model
# --------------------------------------------------------------------------


@dataclass
class Node:
    id: str
    label: str = ""
    shape: str = "rect"
    parent: str | None = None
    depth: int = 0
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    fill: str = ""
    stroke: str = ""
    font_color: str = ""
    dashed: bool = False
    rounded: bool = False
    container: bool = False
    children: list[str] = field(default_factory=list)
    link: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    in_degree: int = 0
    out_degree: int = 0


@dataclass
class Edge:
    id: str
    source: str | None
    target: str | None
    label: str = ""
    dashed: bool = False
    bidirectional: bool = False
    undirected: bool = False
    style_name: str = ""
    waypoints: int = 0
    stroke: str = ""


@dataclass
class Page:
    id: str
    name: str
    index: int
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    @property
    def node_map(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}


def _num(geom: ET.Element | None, key: str) -> float:
    if geom is None:
        return 0.0
    try:
        return float(geom.get(key, "0") or 0)
    except ValueError:
        return 0.0


def parse_page(diagram: ET.Element, index: int) -> Page:
    name = diagram.get("name") or f"Page-{index + 1}"
    page = Page(id=diagram.get("id") or f"page-{index}", name=name, index=index)

    model = diagram.find(".//mxGraphModel")
    if model is None:
        text = (diagram.text or "").strip()
        inflated = _inflate(text) if text else None
        if not inflated:
            return page
        _reject_unsafe_xml(inflated, f"page {index}")
        model = ET.fromstring(inflated)
        if model.tag != "mxGraphModel":
            found = model.find(".//mxGraphModel")
            if found is None:
                return page
            model = found

    root = model.find("root")
    if root is None:
        return page

    # Pass 1: collect raw cells, unwrapping <object>/<UserObject> containers.
    raw: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for element in root:
        if element.tag in ("object", "UserObject"):
            cell = element.find("mxCell")
            if cell is None:
                continue
            attrs = {
                k: v
                for k, v in element.attrib.items()
                if k not in ("id", "label", "placeholders")
            }
            cid = element.get("id") or cell.get("id") or ""
            value = element.get("label", "")
        elif element.tag == "mxCell":
            cell = element
            attrs = {}
            cid = cell.get("id") or ""
            value = cell.get("value", "")
        else:
            continue
        if not cid:
            continue
        raw[cid] = {"cell": cell, "attrs": attrs, "value": value}
        order.append(cid)

    # Pass 2: vertices (absolute geometry resolved after the pass).
    edge_label_parts: dict[str, list[str]] = {}
    for cid in order:
        entry = raw[cid]
        cell = entry["cell"]
        style = parse_style(cell.get("style"))
        parent = cell.get("parent")
        if cell.get("edge") == "1":
            continue
        if cell.get("vertex") != "1":
            continue
        # An edge label is a vertex parented to an edge; fold it into the edge.
        parent_entry = raw.get(parent or "")
        parent_is_edge = bool(
            parent_entry and parent_entry["cell"].get("edge") == "1"
        )
        if parent_is_edge or "edgeLabel" in style:
            if parent:
                text = clean_label(entry["value"])
                if text:
                    edge_label_parts.setdefault(parent, []).append(text)
            continue

        geom = cell.find("mxGeometry")
        node = Node(
            id=cid,
            label=clean_label(entry["value"]),
            shape=classify_shape(style),
            parent=parent,
            x=_num(geom, "x"),
            y=_num(geom, "y"),
            w=_num(geom, "width"),
            h=_num(geom, "height"),
            fill=style.get("fillColor", ""),
            stroke=style.get("strokeColor", ""),
            font_color=style.get("fontColor", ""),
            dashed=style.get("dashed") == "1",
            rounded=style.get("rounded") == "1",
            container=style.get("container") == "1" or "swimlane" in style,
            link=entry["attrs"].get("link", ""),
            attrs={
                k: v
                for k, v in entry["attrs"].items()
                if k not in ("link", "tooltip")
            },
        )
        page.nodes.append(node)

    node_map = page.node_map

    # Resolve absolute geometry + depth by walking the parent chain.
    def resolve(node: Node, seen: set[str]) -> tuple[float, float, int]:
        if node.id in seen:
            return node.x, node.y, 0
        seen.add(node.id)
        parent = node_map.get(node.parent or "")
        if parent is None:
            return node.x, node.y, 0
        px, py, pdepth = resolve(parent, seen)
        return node.x + px, node.y + py, pdepth + 1

    for node in page.nodes:
        ax, ay, depth = resolve(node, set())
        node.x, node.y, node.depth = ax, ay, depth
        parent = node_map.get(node.parent or "")
        if parent is not None:
            parent.children.append(node.id)
            parent.container = True

    # Pass 3: edges.
    for cid in order:
        entry = raw[cid]
        cell = entry["cell"]
        if cell.get("edge") != "1":
            continue
        style = parse_style(cell.get("style"))
        geom = cell.find("mxGeometry")
        waypoints = 0
        if geom is not None:
            waypoints = len(
                [p for p in geom.findall(".//mxPoint") if p.get("as") is None]
            )
        label = clean_label(entry["value"])
        extra = edge_label_parts.get(cid, [])
        if extra:
            label = " / ".join([p for p in ([label] + extra) if p])
        source = cell.get("source")
        target = cell.get("target")
        page.edges.append(
            Edge(
                id=cid,
                source=source if source in node_map else None,
                target=target if target in node_map else None,
                label=label,
                dashed=style.get("dashed") == "1",
                bidirectional=style.get("startArrow", "none")
                not in ("none", "0", "")
                and style.get("endArrow", "classic") not in ("none", "0"),
                undirected=style.get("endArrow") in ("none", "0")
                and style.get("startArrow", "none") in ("none", "0", ""),
                style_name=style.get("shape", "")
                or ("orthogonal" if style.get("edgeStyle") else ""),
                waypoints=waypoints,
                stroke=style.get("strokeColor", ""),
            )
        )

    for edge in page.edges:
        if edge.source and edge.source in node_map:
            node_map[edge.source].out_degree += 1
        if edge.target and edge.target in node_map:
            node_map[edge.target].in_degree += 1

    return page


def parse_file(path: Path) -> list[Page]:
    xml = load_mxfile(path)
    _reject_unsafe_xml(xml, path.name)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        _fail(f"{path.name}: malformed XML ({exc})")
    if root.tag == "mxGraphModel":
        wrapper = ET.Element("diagram", {"name": path.stem, "id": "single"})
        wrapper.append(root)
        return [parse_page(wrapper, 0)]
    diagrams = root.findall(".//diagram")
    if not diagrams:
        _fail(f"{path.name}: mxfile contains no <diagram> pages")
    return [parse_page(d, i) for i, d in enumerate(diagrams)]


# --------------------------------------------------------------------------
# structural analysis — signals, not decisions
# --------------------------------------------------------------------------


def _has_cycle(nodes: list[Node], edges: list[Edge]) -> bool:
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        if edge.source and edge.target and edge.source in adjacency:
            adjacency[edge.source].append(edge.target)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def visit(start: str) -> bool:
        stack = [(start, iter(adjacency.get(start, [])))]
        color[start] = GREY
        while stack:
            nid, it = stack[-1]
            advanced = False
            for nxt in it:
                state = color.get(nxt, BLACK)
                if state == GREY:
                    return True
                if state == WHITE:
                    color[nxt] = GREY
                    stack.append((nxt, iter(adjacency.get(nxt, []))))
                    advanced = True
                    break
            if not advanced:
                color[nid] = BLACK
                stack.pop()
        return False

    return any(color[n.id] == WHITE and visit(n.id) for n in nodes)


def _aligned(boxes: list[Node], tolerance: float = 8.0) -> bool:
    """True when the boxes stack as lanes — shared left edge or shared top edge."""
    if len(boxes) < 2:
        return False
    same_x = max(n.x for n in boxes) - min(n.x for n in boxes) <= tolerance
    same_w = max(n.w for n in boxes) - min(n.w for n in boxes) <= tolerance
    same_y = max(n.y for n in boxes) - min(n.y for n in boxes) <= tolerance
    same_h = max(n.h for n in boxes) - min(n.h for n in boxes) <= tolerance
    return (same_x and same_w) or (same_y and same_h)


def analyze(page: Page) -> dict[str, Any]:
    nodes = page.nodes
    edges = page.edges
    drawable = [n for n in nodes if n.shape not in ("text",) and (n.label or n.children)]
    containers = [n for n in nodes if n.children]
    leaves = [n for n in nodes if not n.children]
    shapes: dict[str, int] = {}
    for node in nodes:
        shapes[shape_family(node.shape)] = shapes.get(shape_family(node.shape), 0) + 1

    def name_of(node: Node) -> str:
        return (node.label.replace("\n", " · ") or node.id)

    ranked = sorted(
        leaves, key=lambda n: (n.in_degree + n.out_degree), reverse=True
    )
    hubs = [
        {"id": n.id, "label": name_of(n), "degree": n.in_degree + n.out_degree}
        for n in ranked[:5]
        if (n.in_degree + n.out_degree) > 0
    ]
    sources = [name_of(n) for n in leaves if n.out_degree and not n.in_degree]
    sinks = [name_of(n) for n in leaves if n.in_degree and not n.out_degree]
    orphans = [name_of(n) for n in leaves if not n.in_degree and not n.out_degree]

    # Type candidates, strongest signal first. Advisory only.
    candidates: list[str] = []
    if shapes.get("lifeline"):
        candidates.append("sequence")
    if shapes.get("table") or shapes.get("er"):
        candidates.append("er")
    lanes = [n for n in nodes if n.shape == "swimlane" and n.children]
    if len(lanes) >= 2 and _aligned(lanes):
        candidates.append("swimlane")
    if shapes.get("rhombus"):
        candidates.append("flowchart")
    if shapes.get("ellipse", 0) >= max(2, len(leaves) // 3) and edges:
        candidates.append("state")
    if any(f in shapes for f in ("aws", "azure", "gcp", "kubernetes", "network")):
        candidates.append("architecture")
    if containers and not shapes.get("swimlane"):
        candidates.append("nested")
    if edges and not _has_cycle(nodes, edges) and len(sources) == 1:
        candidates.append("tree")
    if edges:
        candidates.append("architecture")
    if not candidates:
        candidates.append("architecture")

    seen: set[str] = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    # Collapse candidates: containers whose children are all leaves, and
    # fan-out clusters — the first things to merge when simplifying.
    collapsible = [
        {
            "id": c.id,
            "label": name_of(c),
            "children": len(c.children),
            "child_labels": [
                name_of(page.node_map[cid])
                for cid in c.children
                if page.node_map.get(cid) and page.node_map[cid].label
            ][:8],
        }
        for c in containers
        if c.children and all(not page.node_map[cid].children for cid in c.children)
    ]
    collapsible.sort(key=lambda c: c["children"], reverse=True)

    return {
        "nodes_total": len(nodes),
        "nodes_drawable": len(drawable),
        "containers": len(containers),
        "leaves": len(leaves),
        "edges_total": len(edges),
        "edges_labeled": sum(1 for e in edges if e.label),
        "edges_dangling": sum(1 for e in edges if not (e.source and e.target)),
        "max_depth": max((n.depth for n in nodes), default=0),
        "shapes": dict(sorted(shapes.items(), key=lambda kv: -kv[1])),
        "has_cycle": _has_cycle(nodes, edges),
        "hubs": hubs,
        "entry_points": sources[:6],
        "terminals": sinks[:6],
        "orphans": orphans[:6],
        "type_candidates": candidates[:3],
        "collapsible_groups": collapsible[:8],
        "over_node_budget": len(drawable) > 9,
        "over_edge_budget": len(edges) > 12,
    }


# --------------------------------------------------------------------------
# rendering the digest
# --------------------------------------------------------------------------


def _escape_markdown(text: str) -> str:
    encoded = html.escape(text, quote=False)
    return re.sub(r"([\\`*{}\[\]()#+\-.!_|>])", r"\\\1", encoded)


def _fold_lines(text: str, replacement: str) -> str:
    return replacement.join(text.splitlines())


def _escape_inline(text: str) -> str:
    return _escape_markdown(_fold_lines(text, " · "))


def _escape_table(text: str) -> str:
    return _escape_markdown(_fold_lines(text, " ⏎ "))


def page_bounds(page: Page) -> tuple[float, float, float, float]:
    boxes = [(n.x, n.y, n.x + n.w, n.y + n.h) for n in page.nodes if n.w and n.h]
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def digest(path: Path, pages: list[Page], selected: list[Page], max_rows: int) -> str:
    out: list[str] = []
    out.append(f"# draw.io IR — {_escape_inline(path.name)}")
    out.append("")
    out.append(
        f"{len(pages)} page(s): "
        + ", ".join(
            f"[{p.index}] {_escape_inline(p.name)} ({len(p.nodes)}n/{len(p.edges)}e)"
            for p in pages
        )
    )
    for page in selected:
        info = analyze(page)
        x0, y0, x1, y1 = page_bounds(page)
        out.append("")
        out.append(f"## Page {page.index} — {_escape_inline(page.name)}")
        out.append("")
        out.append(
            f"- source canvas: {int(x1 - x0)}×{int(y1 - y0)} px "
            f"(aspect {((x1 - x0) / (y1 - y0)):.2f})"
            if y1 > y0
            else "- source canvas: empty"
        )
        out.append(
            f"- nodes: {info['nodes_total']} total / {info['nodes_drawable']} drawable "
            f"/ {info['containers']} containers, depth {info['max_depth']}"
        )
        out.append(
            f"- edges: {info['edges_total']} ({info['edges_labeled']} labeled, "
            f"{info['edges_dangling']} dangling), cycle: {info['has_cycle']}"
        )
        out.append(f"- shapes: {info['shapes']}")
        out.append(f"- type candidates: {', '.join(info['type_candidates'])}")
        out.append(
            f"- budget: nodes {'OVER' if info['over_node_budget'] else 'ok'} (max 9), "
            f"edges {'OVER' if info['over_edge_budget'] else 'ok'} (max 12)"
        )
        if info["hubs"]:
            hubs = ", ".join(
                f"{_escape_inline(h['label'] or h['id'])}({h['degree']})"
                for h in info["hubs"]
            )
            out.append(f"- hubs (focal candidates): {hubs}")
        if info["entry_points"]:
            out.append(
                f"- entry points: {', '.join(_escape_inline(label) for label in info['entry_points'])}"
            )
        if info["terminals"]:
            out.append(
                f"- terminals: {', '.join(_escape_inline(label) for label in info['terminals'])}"
            )
        if info["orphans"]:
            out.append(
                f"- unconnected: {', '.join(_escape_inline(label) for label in info['orphans'])}"
            )
        if info["collapsible_groups"]:
            out.append("- collapsible groups (simplify here first):")
            for group in info["collapsible_groups"]:
                kids = ", ".join(_escape_inline(label) for label in group["child_labels"])
                out.append(
                    f"  - {_escape_inline(group['label'])} — "
                    f"{group['children']} children: {kids}"
                )

        out.append("")
        out.append("### Nodes")
        out.append("")
        out.append("| id | label | shape | depth | parent | deg | box |")
        out.append("|---|---|---|---|---|---|---|")
        listed = [n for n in page.nodes if n.label or n.children]
        for node in listed[:max_rows]:
            out.append(
                f"| {_escape_table(node.id)} | {_escape_table(node.label)} | "
                f"{_escape_table(node.shape)} | {node.depth} | "
                f"{_escape_table(node.parent or '-')} | {node.in_degree}/{node.out_degree} | "
                f"{int(node.x)},{int(node.y)} {int(node.w)}×{int(node.h)} |"
            )
        if len(listed) > max_rows:
            out.append(f"| … | +{len(listed) - max_rows} more (use --json) | | | | | |")

        out.append("")
        out.append("### Edges")
        out.append("")
        out.append("| source | target | label | style |")
        out.append("|---|---|---|---|")
        names = {n.id: (n.label.split("\n")[0] or n.id) for n in page.nodes}
        for edge in page.edges[:max_rows]:
            marks = []
            if edge.dashed:
                marks.append("dashed")
            if edge.bidirectional:
                marks.append("bidir")
            if edge.undirected:
                marks.append("undirected")
            out.append(
                f"| {_escape_table(names.get(edge.source or '', '?'))} | "
                f"{_escape_table(names.get(edge.target or '', '?'))} | "
                f"{_escape_table(edge.label) or '-'} | {' '.join(marks) or '-'} |"
            )
        if len(page.edges) > max_rows:
            out.append(f"| … | +{len(page.edges) - max_rows} more (use --json) | | |")
    out.append("")
    return "\n".join(out)


def to_json(path: Path, pages: list[Page], selected: list[Page]) -> str:
    payload = {
        "source": str(path),
        "pages_total": len(pages),
        "pages": [
            {
                "id": p.id,
                "name": p.name,
                "index": p.index,
                "bounds": dict(zip(("x0", "y0", "x1", "y1"), page_bounds(p))),
                "analysis": analyze(p),
                "nodes": [asdict(n) for n in p.nodes],
                "edges": [asdict(e) for e in p.edges],
            }
            for p in selected
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def select_pages(pages: list[Page], selector: str | None) -> list[Page]:
    if selector is None:
        return pages if len(pages) == 1 else pages[:1]
    if selector == "all":
        return pages
    if selector.isdigit():
        index = int(selector)
        match = [p for p in pages if p.index == index]
        if not match:
            _fail(f"no page with index {index} (have 0..{len(pages) - 1})")
        return match
    match = [p for p in pages if p.name.lower() == selector.lower()]
    if not match:
        names = ", ".join(p.name for p in pages)
        _fail(f"no page named {selector!r} (have: {names})")
    return match


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", help=".drawio / .xml / .drawio.png / .drawio.svg")
    parser.add_argument(
        "--page",
        help="page index, page name, or 'all' (default: first page)",
    )
    parser.add_argument("--json", action="store_true", help="emit the full IR as JSON")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=40,
        help="rows per table in the Markdown digest (default 40)",
    )
    parser.add_argument("--out", help="write to this path instead of stdout")
    args = parser.parse_args(argv)

    if args.max_rows < 1:
        parser.error("--max-rows must be at least 1")

    path = Path(args.file)
    if not path.is_file():
        _fail(f"{path}: no such file")

    pages = parse_file(path)
    selected = select_pages(pages, args.page)
    text = (
        to_json(path, pages, selected)
        if args.json
        else digest(path, pages, selected, args.max_rows)
    )
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} bytes)")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


if __name__ == "__main__":
    _configure_stdout_utf8()
    raise SystemExit(main())
