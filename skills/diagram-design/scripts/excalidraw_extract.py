#!/usr/bin/env python3
"""Extract a normalized intermediate representation (IR) from an Excalidraw scene.

Trust boundary: this program parses bounded JSON. It never renders, fetches, or
executes anything the scene carries. Element links, embed URLs, and binary file
payloads (``files``, ``fileId``, ``dataURL``) are counted and discarded; labels
are emitted only as inert, escaped text. Prompt-looking label content is
diagram data, never an instruction.

The input is a saved ``.excalidraw`` (or ``.excalidraw.json``) scene. PNG/SVG
exports are rejected with a named failure — ask for the source scene instead of
scraping pixels.

Usage:
    python3 excalidraw_extract.py <file.excalidraw> [--json]
                                  [--max-rows N] [--out PATH]

Default output is a compact Markdown digest meant to be read into context.
``--json`` emits the full IR instead. Exit codes: 0 ok, 2 unreadable /
unsupported / over limits.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn

MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_ELEMENTS = 10000
MAX_NODES = 2000
MAX_EDGES = 5000

EXCALIDRAW_SUFFIXES = (".excalidraw", ".json")
EXPORT_SUFFIXES = (".png", ".svg")

# Excalidraw element type -> IR shape family. Everything else is either an
# edge (arrow, line), folded (text), counted-and-dropped (freedraw, image
# pixels), or reported as unknown.
NODE_SHAPES = {
    "rectangle": "rect",
    "ellipse": "ellipse",
    "diamond": "rhombus",
    "image": "image",
    "embeddable": "embed",
    "iframe": "embed",
}
EDGE_TYPES = {"arrow", "line"}
CONTAINER_TYPES = {"frame", "magicframe"}


def _configure_stdout_utf8() -> None:
    """Emit digests as UTF-8 even when Windows selects a legacy codepage."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


def _fail(message: str) -> NoReturn:
    print(f"excalidraw_extract: {message}", file=sys.stderr)
    raise SystemExit(2)


# --------------------------------------------------------------------------
# IR model — mirrors the draw.io / Mermaid extractors' digest shape
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
    dashed: bool = False
    container: bool = False
    children: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
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
    waypoints: int = 0
    stroke: str = ""


@dataclass
class Scene:
    name: str
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    discarded: dict[str, int] = field(
        default_factory=lambda: {
            "freedraw_strokes": 0,
            "image_payloads": 0,
            "links": 0,
            "embeds": 0,
            "deleted_elements": 0,
            "unknown_elements": 0,
        }
    )

    @property
    def node_map(self) -> dict[str, Node]:
        return {node.id: node for node in self.nodes}


def clean_label(value: Any) -> str:
    """Excalidraw text is plain, but normalize whitespace defensively."""
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch >= " " or ch == "\t")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _num(element: dict[str, Any], key: str) -> float:
    """A geometry field as a finite float; absent or non-numeric reads as 0.

    A scene is untrusted input. An out-of-range int and the JSON tokens
    ``Infinity``/``NaN`` both survive as floats that only blow up later, in the
    digest's integer formatting, as an uncaught OverflowError or ValueError
    rather than the promised exit-2 diagnostic. Reject them here instead.
    """
    value = element.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    try:
        value = float(value)
    except OverflowError:
        _fail(f"invalid geometry: {key} is out of range")
    if not math.isfinite(value):
        _fail(f"invalid geometry: {key} must be finite")
    return value


def load_scene_data(path: Path) -> dict[str, Any]:
    suffix = path.suffix.casefold()
    if suffix in EXPORT_SUFFIXES:
        _fail(
            f"{path.name}: PNG/SVG exports are not supported; save the scene "
            "as .excalidraw and import that file"
        )
    if suffix not in EXCALIDRAW_SUFFIXES:
        _fail(f"{path.name}: not an Excalidraw file")
    try:
        with path.open("rb") as source:
            data = source.read(MAX_INPUT_BYTES + 1)
    except OSError as error:
        _fail(f"{path}: {error}")
    if len(data) > MAX_INPUT_BYTES:
        _fail(
            f"source exceeds the {MAX_INPUT_BYTES // (1024 * 1024)} MiB limit"
        )
    try:
        document = json.loads(
            data.decode("utf-8"),
            parse_constant=lambda token: _fail(
                f"invalid geometry: {token} is not finite"
            ),
        )
    except (UnicodeDecodeError, ValueError):
        _fail(f"{path.name}: not valid Excalidraw JSON")
    if not isinstance(document, dict) or document.get("type") != "excalidraw":
        _fail(f"{path.name}: not an Excalidraw scene (missing type: excalidraw)")
    elements = document.get("elements")
    if not isinstance(elements, list):
        _fail(f"{path.name}: scene has no elements array")
    if len(elements) > MAX_ELEMENTS:
        _fail(f"element limit exceeded (max {MAX_ELEMENTS})")
    return document


def parse_scene(path: Path, document: dict[str, Any]) -> Scene:
    scene = Scene(name=path.stem.removesuffix(".excalidraw"))
    elements = [
        element
        for element in document["elements"]
        if isinstance(element, dict) and isinstance(element.get("id"), str)
    ]

    live: list[dict[str, Any]] = []
    for element in elements:
        if not isinstance(element.get("type"), str):
            _fail("invalid element type: expected a string")
        if element.get("isDeleted"):
            scene.discarded["deleted_elements"] += 1
            continue
        live.append(element)

    by_id = {element["id"]: element for element in live}

    # Pass 1: fold bound text into its container (node label or edge label).
    bound_labels: dict[str, list[str]] = {}
    for element in live:
        if element.get("type") != "text":
            continue
        container = element.get("containerId")
        if isinstance(container, str) and container in by_id:
            text = clean_label(element.get("text"))
            if text:
                bound_labels.setdefault(container, []).append(text)

    def label_for(element: dict[str, Any]) -> str:
        return "\n".join(bound_labels.get(element["id"], []))

    # Pass 2: nodes (frames become containers; standalone text stays a node).
    frame_ids: set[str] = set()
    for element in live:
        kind = element.get("type")
        element_id = element["id"]
        if isinstance(element.get("link"), str) and element.get("link"):
            scene.discarded["links"] += 1
        if kind in EDGE_TYPES:
            continue
        if kind == "text":
            if isinstance(element.get("containerId"), str) and element["containerId"] in by_id:
                continue  # folded into its container in pass 1
            shape, label = "text", clean_label(element.get("text"))
        elif kind in CONTAINER_TYPES:
            frame_ids.add(element_id)
            shape = "frame"
            label = clean_label(element.get("name")) or f"Frame {len(frame_ids)}"
        elif kind in NODE_SHAPES:
            shape = NODE_SHAPES[kind]
            label = label_for(element)
            if kind == "image":
                # The pixels never cross the trust boundary; only the box does.
                scene.discarded["image_payloads"] += 1
            if kind in ("embeddable", "iframe"):
                scene.discarded["embeds"] += 1
        elif kind == "freedraw":
            scene.discarded["freedraw_strokes"] += 1
            continue
        elif kind in ("selection", "laser"):
            continue  # editor-only artifacts, no content
        else:
            scene.discarded["unknown_elements"] += 1
            continue
        if len(scene.nodes) >= MAX_NODES:
            _fail(f"node limit exceeded (max {MAX_NODES})")
        groups = [
            group for group in element.get("groupIds", []) if isinstance(group, str)
        ] if isinstance(element.get("groupIds"), list) else []
        scene.nodes.append(
            Node(
                id=element_id,
                label=label,
                shape=shape,
                x=_num(element, "x"),
                y=_num(element, "y"),
                w=_num(element, "width"),
                h=_num(element, "height"),
                fill=element.get("backgroundColor", "")
                if isinstance(element.get("backgroundColor"), str)
                else "",
                stroke=element.get("strokeColor", "")
                if isinstance(element.get("strokeColor"), str)
                else "",
                dashed=element.get("strokeStyle") in ("dashed", "dotted"),
                container=shape == "frame",
                groups=groups,
            )
        )

    node_map = scene.node_map

    # Frame membership: Excalidraw frames don't nest, so members sit at depth 1.
    for element in live:
        frame = element.get("frameId")
        if not isinstance(frame, str) or frame not in frame_ids:
            continue
        member = node_map.get(element["id"])
        parent = node_map.get(frame)
        if member is None or parent is None or member.id == parent.id:
            continue
        member.parent = frame
        member.depth = 1
        parent.children.append(member.id)

    # Pass 3: edges. Arrows are directed unless both arrowheads vanish; lines
    # are undirected unless the author added arrowheads.
    def binding_id(element: dict[str, Any], key: str) -> str | None:
        binding = element.get(key)
        if isinstance(binding, dict) and isinstance(binding.get("elementId"), str):
            bound = binding["elementId"]
            return bound if bound in node_map else None
        return None

    for element in live:
        kind = element.get("type")
        if kind not in EDGE_TYPES:
            continue
        if len(scene.edges) >= MAX_EDGES:
            _fail(f"edge limit exceeded (max {MAX_EDGES})")
        default_end = "arrow" if kind == "arrow" else None
        start_head = element.get("startArrowhead")
        end_head = element.get("endArrowhead", default_end)
        if start_head is not None and not isinstance(start_head, str):
            _fail("invalid startArrowhead: expected a string or null")
        if end_head is not None and not isinstance(end_head, str):
            _fail("invalid endArrowhead: expected a string or null")
        start_bound = binding_id(element, "startBinding")
        end_bound = binding_id(element, "endBinding")
        # The semantic source is the tail, not necessarily startBinding: a
        # start-only arrowhead points from the end binding back to the start.
        source, target = (
            (end_bound, start_bound)
            if start_head and not end_head
            else (start_bound, end_bound)
        )
        points = element.get("points")
        waypoints = max(len(points) - 2, 0) if isinstance(points, list) else 0
        scene.edges.append(
            Edge(
                id=element["id"],
                source=source,
                target=target,
                label=label_for(element),
                dashed=element.get("strokeStyle") in ("dashed", "dotted"),
                bidirectional=bool(start_head) and bool(end_head),
                undirected=not start_head and not end_head,
                waypoints=waypoints,
                stroke=element.get("strokeColor", "")
                if isinstance(element.get("strokeColor"), str)
                else "",
            )
        )

    for edge in scene.edges:
        source = node_map.get(edge.source or "")
        target = node_map.get(edge.target or "")
        if edge.bidirectional or edge.undirected:
            for endpoint in (source, target):
                if endpoint is not None:
                    endpoint.in_degree += 1
                    endpoint.out_degree += 1
        else:
            if source is not None:
                source.out_degree += 1
            if target is not None:
                target.in_degree += 1

    return scene


# --------------------------------------------------------------------------
# structural analysis — signals, not decisions
# --------------------------------------------------------------------------


def _has_cycle(nodes: list[Node], edges: list[Edge]) -> bool:
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.source and edge.target and edge.source in adjacency:
            adjacency[edge.source].append(edge.target)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {node.id: WHITE for node in nodes}

    def visit(start: str) -> bool:
        stack = [(start, iter(adjacency.get(start, [])))]
        color[start] = GREY
        while stack:
            node_id, targets = stack[-1]
            advanced = False
            for target in targets:
                state = color.get(target, BLACK)
                if state == GREY:
                    return True
                if state == WHITE:
                    color[target] = GREY
                    stack.append((target, iter(adjacency.get(target, []))))
                    advanced = True
                    break
            if not advanced:
                color[node_id] = BLACK
                stack.pop()
        return False

    return any(color[node.id] == WHITE and visit(node.id) for node in nodes)


def analyze(scene: Scene) -> dict[str, Any]:
    nodes = scene.nodes
    edges = scene.edges
    drawable = [
        node for node in nodes if node.shape != "text" and (node.label or node.children)
    ]
    containers = [node for node in nodes if node.children]
    leaves = [node for node in nodes if not node.children]
    shapes: dict[str, int] = {}
    for node in nodes:
        shapes[node.shape] = shapes.get(node.shape, 0) + 1

    def name_of(node: Node) -> str:
        return node.label.replace("\n", " · ") or node.id

    ranked = sorted(leaves, key=lambda n: n.in_degree + n.out_degree, reverse=True)
    hubs = [
        {"id": node.id, "label": name_of(node), "degree": node.in_degree + node.out_degree}
        for node in ranked[:5]
        if node.in_degree + node.out_degree > 0
    ]
    sources = [name_of(n) for n in leaves if n.out_degree and not n.in_degree]
    sinks = [name_of(n) for n in leaves if n.in_degree and not n.out_degree]
    orphans = [
        name_of(n)
        for n in leaves
        if not n.in_degree and not n.out_degree and n.shape != "frame"
    ]

    candidates: list[str] = []
    if shapes.get("rhombus"):
        candidates.append("flowchart")
    if shapes.get("ellipse", 0) >= max(2, len(leaves) // 3) and edges:
        candidates.append("state")
    if containers:
        candidates.append("nested")
    if edges and not _has_cycle(nodes, edges) and len(sources) == 1:
        candidates.append("tree")
    candidates.append("architecture")
    seen: set[str] = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]

    # Collapse candidates: frames whose members are all leaves, then explicit
    # groups — the first things to merge when simplifying.
    collapsible = [
        {
            "id": container.id,
            "label": name_of(container),
            "children": len(container.children),
            "child_labels": [
                name_of(scene.node_map[child])
                for child in container.children
                if scene.node_map.get(child) and scene.node_map[child].label
            ][:8],
        }
        for container in containers
        if container.children
        and all(not scene.node_map[child].children for child in container.children)
    ]
    group_members: dict[str, list[Node]] = {}
    for node in nodes:
        if node.groups:
            group_members.setdefault(node.groups[-1], []).append(node)
    for group_id, members in group_members.items():
        if len(members) < 2:
            continue
        collapsible.append(
            {
                "id": group_id,
                "label": f"group ({len(members)} members)",
                "children": len(members),
                "child_labels": [name_of(m) for m in members if m.label][:8],
            }
        )
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
        "shapes": dict(sorted(shapes.items(), key=lambda kv: (-kv[1], kv[0]))),
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


def scene_bounds(scene: Scene) -> tuple[float, float, float, float]:
    boxes = [(n.x, n.y, n.x + n.w, n.y + n.h) for n in scene.nodes if n.w and n.h]
    if any(not math.isfinite(value) for box in boxes for value in box):
        _fail("invalid geometry: bounding box overflow")
    if not boxes:
        return (0.0, 0.0, 0.0, 0.0)
    bounds = (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
    width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
    ratio = width / height if height > 0 else 0
    if not all(math.isfinite(value) for value in (width, height, ratio)):
        _fail("invalid geometry: canvas arithmetic overflow")
    return bounds


def digest(path: Path, scene: Scene, max_rows: int) -> str:
    info = analyze(scene)
    x0, y0, x1, y1 = scene_bounds(scene)
    out: list[str] = []
    out.append(f"# Excalidraw IR — {_escape_inline(path.name)}")
    out.append("")
    out.append(
        f"1 scene: {_escape_inline(scene.name)} "
        f"({len(scene.nodes)}n/{len(scene.edges)}e)"
    )
    out.append("")
    out.append(f"## Scene — {_escape_inline(scene.name)}")
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
    dropped = {key: count for key, count in scene.discarded.items() if count}
    if dropped:
        out.append(
            "- discarded: "
            + ", ".join(
                f"{count} {key.replace('_', ' ')}" for key, count in dropped.items()
            )
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
    listed = [n for n in scene.nodes if n.label or n.children]
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
    names = {n.id: (n.label.split("\n")[0] or n.id) for n in scene.nodes}
    for edge in scene.edges[:max_rows]:
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
    if len(scene.edges) > max_rows:
        out.append(f"| … | +{len(scene.edges) - max_rows} more (use --json) | | |")
    out.append("")
    return "\n".join(out)


def to_json(path: Path, scene: Scene) -> str:
    payload = {
        "source": str(path),
        "scene": {
            "name": scene.name,
            "bounds": dict(zip(("x0", "y0", "x1", "y1"), scene_bounds(scene))),
            "analysis": analyze(scene),
            "discarded": scene.discarded,
            "nodes": [asdict(node) for node in scene.nodes],
            "edges": [asdict(edge) for edge in scene.edges],
        },
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", help=".excalidraw / .excalidraw.json scene")
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
        _fail("--max-rows must be at least 1")

    path = Path(args.file)
    if not path.is_file():
        _fail(f"{path}: no such file")

    scene = parse_scene(path, load_scene_data(path))
    text = to_json(path, scene) if args.json else digest(path, scene, args.max_rows)
    if args.out:
        try:
            Path(args.out).write_text(text, encoding="utf-8")
        except OSError as error:
            _fail(f"cannot write {args.out}: {error}")
        print(f"wrote {args.out} ({len(text)} bytes)")
    else:
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


if __name__ == "__main__":
    _configure_stdout_utf8()
    raise SystemExit(main())
