#!/usr/bin/env python3
"""Extract a normalized intermediate representation (IR) from Mermaid text.

Trust boundary: this program parses bounded text. It never evaluates, renders,
fetches, or executes Mermaid, JavaScript, URLs, directives, or label content.
Every label and directive value is untrusted data. Click targets and styling are
counted and discarded; retained labels are emitted only as inert text.

Supported grammars are flowchart/graph, sequenceDiagram, stateDiagram-v2, and
erDiagram. Inputs may be .mmd, .mermaid, or Markdown files containing fenced
``mermaid`` blocks.

Usage:
    python3 mermaid_extract.py <file> [--diagram N|all] [--json]
                               [--max-rows N] [--out PATH]

Exit codes: 0 success, 2 unreadable, unsupported, malformed, or over limits.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, NoReturn


MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_NODES = 2000
MAX_EDGES = 5000
SUPPORTED_KINDS = "flowchart, sequenceDiagram, stateDiagram-v2, erDiagram"
UNSUPPORTED_KINDS = {
    "pie",
    "mindmap",
    "gitgraph",
    "quadrantchart",
    "timeline",
    "c4context",
    "sankey",
    "sankey-beta",
    "gantt",
    "journey",
    "classdiagram",
    "statediagram",
}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd"}
MERMAID_SUFFIXES = {".mmd", ".mermaid"}


def _configure_stdout_utf8() -> None:
    """Emit digests as UTF-8 even when Windows selects a legacy codepage."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


def _fail(message: str) -> NoReturn:
    print(f"mermaid_extract: {message}", file=sys.stderr)
    raise SystemExit(2)


@dataclass
class Node:
    id: str
    label: str = ""
    shape: str = "rect"
    parent: str | None = None
    depth: int = 0
    container: bool = False
    children: list[str] = field(default_factory=list)
    fields: list[str] = field(default_factory=list)
    in_degree: int = 0
    out_degree: int = 0


@dataclass
class Edge:
    id: str
    source: str
    target: str
    label: str = ""
    style: str = "solid"
    arrowhead: str = "arrow"
    bidirectional: bool = False
    undirected: bool = False
    order: int = 0


@dataclass
class Diagram:
    index: int
    kind: str
    source_line: int
    direction: str = "TD"
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    fragments: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    discarded: dict[str, int] = field(
        default_factory=lambda: {"style_directives": 0, "click_handlers": 0}
    )
    _nodes_by_id: dict[str, Node] = field(default_factory=dict, init=False, repr=False)

    @property
    def node_map(self) -> dict[str, Node]:
        return self._nodes_by_id

    def add_node(
        self,
        node_id: str,
        label: str = "",
        shape: str = "rect",
        parent: str | None = None,
        container: bool = False,
    ) -> Node:
        existing = self._nodes_by_id.get(node_id)
        if existing is not None:
            if label and (label != node_id or existing.label == existing.id):
                existing.label = label
            if shape != "rect" or not existing.shape:
                existing.shape = shape
            if parent is not None and existing.parent is None:
                existing.parent = parent
                existing.depth = self._depth_for(parent)
                self._attach(parent, node_id)
            existing.container = existing.container or container
            return existing
        if len(self.nodes) >= MAX_NODES:
            _fail(f"node limit exceeded (max {MAX_NODES})")
        node = Node(
            id=node_id,
            label=label or node_id,
            shape=shape,
            parent=parent,
            depth=self._depth_for(parent),
            container=container,
        )
        self.nodes.append(node)
        self._nodes_by_id[node_id] = node
        if parent is not None:
            self._attach(parent, node_id)
        return node

    def _depth_for(self, parent: str | None) -> int:
        if parent is None:
            return 0
        parent_node = self._nodes_by_id.get(parent)
        return (parent_node.depth + 1) if parent_node is not None else 1

    def _attach(self, parent: str, child: str) -> None:
        parent_node = self._nodes_by_id.get(parent)
        if parent_node is not None and child not in parent_node.children:
            parent_node.children.append(child)
            parent_node.container = True

    def add_edge(
        self,
        source: str,
        target: str,
        label: str = "",
        style: str = "solid",
        arrowhead: str = "arrow",
        bidirectional: bool = False,
        undirected: bool = False,
    ) -> Edge:
        if len(self.edges) >= MAX_EDGES:
            _fail(f"edge limit exceeded (max {MAX_EDGES})")
        edge = Edge(
            id=f"e{len(self.edges) + 1}",
            source=source,
            target=target,
            label=label,
            style=style,
            arrowhead=arrowhead,
            bidirectional=bidirectional,
            undirected=undirected,
            order=len(self.edges) + 1,
        )
        self.edges.append(edge)
        return edge


@dataclass
class SourceBlock:
    index: int
    text: str
    source_line: int


def clean_label(value: str) -> str:
    """Flatten Mermaid label markup without interpreting it."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'`":
        text = text[1:-1]
    if text.startswith("`") and text.endswith("`"):
        text = text[1:-1]
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"(?<!&)#(quot|apos|amp|lt|gt);", r"&\1;", text)
    text = html.unescape(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"(?<!\w)[*_](.*?)[*_](?!\w)", r"\1", text)
    text = text.replace("\\\"", '"').replace("\\'", "'")
    return "\n".join(part.strip() for part in text.splitlines()).strip()


def _read_bounded(path: Path) -> str:
    try:
        with path.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
    except OSError as error:
        _fail(f"{path}: {error}")
    if len(data) > MAX_SOURCE_BYTES:
        _fail(
            f"source exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB limit"
        )
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        _fail(f"{path.name}: source is not valid UTF-8 text")


def load_blocks(path: Path) -> list[SourceBlock]:
    suffix = path.suffix.casefold()
    if suffix not in MERMAID_SUFFIXES | MARKDOWN_SUFFIXES:
        _fail(f"{path.name}: not a Mermaid file")
    source = _read_bounded(path)
    if suffix in MERMAID_SUFFIXES:
        return [SourceBlock(0, source, 1)]

    blocks: list[SourceBlock] = []
    lines = source.splitlines()
    start: int | None = None
    fence = ""
    content: list[str] = []
    for line_number, line in enumerate(lines, 1):
        if start is None:
            match = re.match(r"^\s*(`{3,}|~{3,})\s*mermaid\s*$", line, re.I)
            if match:
                start = line_number + 1
                fence = match.group(1)
                content = []
            continue
        if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
            blocks.append(SourceBlock(len(blocks), "\n".join(content), start))
            start = None
            fence = ""
            content = []
        else:
            content.append(line)
    if start is not None:
        _fail(f"{path.name}: unterminated mermaid fence starting at line {start - 1}")
    if not blocks:
        _fail(f"{path.name}: no fenced mermaid block found")
    return blocks


FRONTMATTER_MAX_LINES = 40


def _frontmatter_end(lines: list[str]) -> int:
    """Return the last line index of a leading `---` frontmatter block, or -1."""
    first = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first is None or lines[first].strip() != "---":
        return -1
    limit = min(len(lines), first + FRONTMATTER_MAX_LINES + 1)
    for index in range(first + 1, limit):
        if lines[index].strip() == "---":
            return index
    return -1


def _prepared_lines(block: SourceBlock) -> list[tuple[int, str]]:
    prepared: list[tuple[int, str]] = []
    in_directive = False
    lines = block.text.splitlines()
    frontmatter_end = _frontmatter_end(lines)
    for offset, raw in enumerate(lines):
        line_number = block.source_line + offset
        stripped = raw.strip()
        if offset <= frontmatter_end:
            # Mermaid's `--- title: ... ---` frontmatter is source config; the
            # redraw discards it the same way it discards `%%{init}%%`.
            prepared.append((line_number, ""))
            continue
        if in_directive:
            if "}%%" in stripped:
                in_directive = False
            prepared.append((line_number, ""))
            continue
        if stripped.startswith("%%{"):
            if "}%%" not in stripped:
                in_directive = True
            prepared.append((line_number, ""))
            continue
        if stripped.startswith("%%"):
            prepared.append((line_number, ""))
            continue
        prepared.append((line_number, raw.rstrip()))
    return prepared


def _kind_and_direction(
    lines: list[tuple[int, str]],
) -> tuple[str, str, int]:
    for position, (line_number, raw) in enumerate(lines):
        text = raw.strip()
        if not text:
            continue
        match = re.match(r"^(flowchart|graph)\s+(TD|TB|LR|RL|BT)\b", text, re.I)
        if match:
            return "flowchart", match.group(2).upper(), position
        if re.match(r"^sequenceDiagram\b", text, re.I):
            return "sequenceDiagram", "LR", position
        if re.match(r"^stateDiagram-v2\b", text, re.I):
            return "stateDiagram-v2", "TD", position
        if re.match(r"^erDiagram\b", text, re.I):
            return "erDiagram", "TD", position
        token = text.split(maxsplit=1)[0]
        if token.casefold() in UNSUPPORTED_KINDS:
            _fail(
                f"unsupported diagram kind: `{token}` (supported: {SUPPORTED_KINDS})"
            )
        _fail(f"not a Mermaid file at line {line_number}")
    _fail("not a Mermaid file")


def _top_level_mask(text: str) -> str:
    """Keep top-level syntax positions and blank quoted/bracketed content."""
    output = list(text)
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    pairs = {"]": "[", ")": "(", "}": "{"}
    for index, character in enumerate(text):
        if quote is not None:
            output[index] = " "
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "\"'`":
            quote = character
            output[index] = " "
            continue
        if character in "[({":
            stack.append(character)
            output[index] = " "
            continue
        if character in "])}":
            if stack and stack[-1] == pairs[character]:
                stack.pop()
            output[index] = " "
            continue
        if stack:
            output[index] = " "
    return "".join(output)


def _split_top_level(text: str, delimiter: str) -> list[str]:
    mask = _top_level_mask(text)
    parts: list[str] = []
    start = 0
    for index, character in enumerate(mask):
        if character == delimiter:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _statement_complete(text: str) -> bool:
    """Return whether quotes and node delimiters close within a statement."""
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    pairs = {"]": "[", ")": "(", "}": "{"}
    for character in text:
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in "\"'`":
            quote = character
        elif character in "[({":
            stack.append(character)
        elif character in "])}":
            if stack and stack[-1] == pairs[character]:
                stack.pop()
    return quote is None and not stack


def _logical_statements(
    lines: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Join multiline Mermaid strings before parsing semicolon statements."""
    logical: list[tuple[int, str]] = []
    pending: list[str] = []
    start_line = 0
    for line_number, raw in lines:
        if not pending and not raw.strip():
            continue
        if not pending:
            start_line = line_number
        pending.append(raw)
        combined = "\n".join(pending)
        if not _statement_complete(combined):
            continue
        logical.extend(
            (start_line, statement)
            for statement in _split_top_level(combined, ";")
        )
        pending = []
    if pending:
        _fail(f"unterminated statement at line {start_line}")
    return logical


SHAPE_FOR_DELIMITERS = (
    ("(((", ")))", "circle"),
    ("((", "))", "circle"),
    ("([", "])", "stadium"),
    ("{{", "}}", "hexagon"),
    ("[(", ")]", "cylinder"),
    ("[[", "]]", "subroutine"),
    ("[/", "/]", "parallelogram"),
    ("[\\", "\\]", "parallelogram"),
    ("[/", "\\]", "trapezoid"),
    ("[\\", "/]", "trapezoid"),
    ("[", "]", "rect"),
    ("(", ")", "round"),
    ("{", "}", "rhombus"),
    (">", "]", "asymmetric"),
)

EXPANDED_SHAPE_FAMILIES = {
    "rect": "rect",
    "rectangle": "rect",
    "proc": "rect",
    "process": "rect",
    "rounded": "round",
    "event": "round",
    "stadium": "stadium",
    "pill": "stadium",
    "terminal": "stadium",
    "circle": "circle",
    "circ": "circle",
    "sm-circ": "circle",
    "small-circle": "circle",
    "start": "circle",
    "dbl-circ": "circle",
    "double-circle": "circle",
    "fr-circ": "circle",
    "framed-circle": "circle",
    "stop": "circle",
    "cyl": "cylinder",
    "cylinder": "cylinder",
    "database": "cylinder",
    "db": "cylinder",
    "h-cyl": "cylinder",
    "horizontal-cylinder": "cylinder",
    "lin-cyl": "cylinder",
    "lined-cylinder": "cylinder",
    "diam": "rhombus",
    "decision": "rhombus",
    "diamond": "rhombus",
    "question": "rhombus",
    "hex": "hexagon",
    "hexagon": "hexagon",
    "prepare": "hexagon",
    "fr-rect": "subroutine",
    "framed-rectangle": "subroutine",
    "subproc": "subroutine",
    "subprocess": "subroutine",
    "subroutine": "subroutine",
    "lean-r": "parallelogram",
    "lean-l": "parallelogram",
    "in-out": "parallelogram",
    "lean-right": "parallelogram",
    "lean-left": "parallelogram",
    "out-in": "parallelogram",
    "trap-t": "trapezoid",
    "trap-b": "trapezoid",
    "trapezoid": "trapezoid",
    "inv-trapezoid": "trapezoid",
    "manual": "trapezoid",
    "priority": "trapezoid",
}


def classify_shape(expression: str) -> str:
    """Return the normalized Mermaid shape family for a node suffix."""
    for opening, closing, shape in SHAPE_FOR_DELIMITERS:
        if expression.startswith(opening) and expression.endswith(closing):
            return shape
    return "rect"


def _strip_class_suffix(text: str) -> str:
    """Drop Mermaid's `:::class` attachment; source styling is discarded."""
    mask = _top_level_mask(text)
    index = mask.find(":::")
    if index == -1:
        return text
    end = index + 3
    while end < len(text) and (text[end].isalnum() or text[end] in "_-"):
        end += 1
    return (text[:index] + text[end:]).strip()


def _parse_expanded_attributes(text: str) -> tuple[str, str] | None:
    """Normalize Mermaid v11.3+ ``@{ ... }`` node attributes.

    Only semantic label/shape data crosses the trust boundary. Image URLs,
    registered icon names, dimensions, and renderer configuration are dropped.
    """
    if not text.startswith("@{") or not text.endswith("}"):
        return None
    values: dict[str, str] = {}
    for raw_attribute in _split_top_level(text[2:-1], ","):
        key, separator, raw_value = raw_attribute.partition(":")
        if not separator:
            continue
        key = key.strip().casefold()
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", key):
            continue
        values[key] = clean_label(raw_value)
    shape_name = values.get("shape", "").casefold()
    if not shape_name:
        if "img" in values:
            shape_name = "image"
        elif "icon" in values:
            shape_name = "icon"
        else:
            shape_name = "rect"
    if not re.fullmatch(r"[a-z][a-z0-9-]*", shape_name):
        shape_name = "rect"
    shape = EXPANDED_SHAPE_FAMILIES.get(shape_name, shape_name)
    return values.get("label", ""), shape


def _parse_node_expression(expression: str) -> tuple[str, str, str] | None:
    text = _strip_class_suffix(expression.strip().rstrip(";").strip())
    if not text:
        return None
    match = re.match(r"^([\w.:-]+)", text, re.UNICODE)
    if match is None:
        return None
    node_id = match.group(1)
    rest = text[match.end() :].strip()
    if not rest:
        return node_id, node_id, "rect"
    expanded = _parse_expanded_attributes(rest)
    if expanded is not None:
        label, shape = expanded
        return node_id, label or node_id, shape
    for opening, closing, _shape in SHAPE_FOR_DELIMITERS:
        if rest.startswith(opening) and rest.endswith(closing):
            label = rest[len(opening) : len(rest) - len(closing)]
            return node_id, clean_label(label), classify_shape(rest)
    return None


@dataclass
class _Operator:
    start: int
    end: int
    label: str
    style: str
    arrowhead: str
    bidirectional: bool = False
    undirected: bool = False


def _operator_style(token: str) -> tuple[str, str, bool, bool]:
    style = "dashed" if "." in token else "thick" if "=" in token else "solid"
    arrowhead = "cross" if token.endswith("x") else "circle" if token.endswith("o") else "arrow"
    undirected = ">" not in token and not token.endswith(("x", "o"))
    bidirectional = (
        token.startswith("<") and token.endswith(">")
    ) or (token.startswith(("x", "o")) and token.endswith(("x", "o")))
    return style, arrowhead, bidirectional, undirected


def _edge_operators(text: str) -> list[_Operator]:
    mask = _top_level_mask(text)
    operators: list[_Operator] = []
    occupied: list[tuple[int, int]] = []

    # Labeled links carry the label between the opening and closing operator:
    # `A-- text -->B`, `A-. retry .-> B`, `A== critical ==> B`, and the
    # undirected forms of each. The compact form drops the spaces —
    # `B--yes-->C` — and may retain a left arrow/circle/cross marker, as in
    # `A<--yes-->B` or `A o--yes--o B`. Its label may not contain whitespace,
    # and the operator characters themselves may not open one (keeping
    # `A----->B` unlabeled and `A --o B --> C` two separate links).
    text_edge = re.compile(
        r"(?P<opening>"
        r"<(?:--|-\.|==)"
        r"|(?<![\w.:-])[xo](?:--|-\.|==)"
        r"|(?:--|-\.|==)"
        r")"
        r"(?:\s+(?P<spaced>.+?)\s+|(?![-=.\s])(?P<compact>[^\s|<>]+?))"
        r"(?P<closing>\.-+[>xo]|\.-+|-{2,}>|--[xo]|=+>|={2,}|-{3,})"
    )
    trailing_operator = re.compile(
        r"(?:\.-+[>xo]|\.-+|-{2,}>|--[xo]|=+>|={2,}|-{3,})"
        r"(?:\|[^|\n]*\|)?\s*$"
    )
    for match in text_edge.finditer(mask):
        opening = match.group("opening")
        operator_start = match.start()
        if opening.startswith(("x", "o")):
            prefix = mask[:operator_start]
            if not prefix.strip() or trailing_operator.search(prefix):
                # Here x/o is the endpoint before a regular opening operator,
                # not a left marker: `x--yes-->B` or `A-->x--go-->B`.
                operator_start += 1
                opening = opening[1:]
        token = opening + match.group("closing")
        label_group = "spaced" if match.group("spaced") is not None else "compact"
        style, arrowhead, bidirectional, undirected = _operator_style(token)
        operators.append(
            _Operator(
                operator_start,
                match.end(),
                clean_label(text[match.start(label_group) : match.end(label_group)]),
                style,
                arrowhead,
                bidirectional,
                undirected,
            )
        )
        occupied.append((operator_start, match.end()))

    pattern = re.compile(
        r"[xo][-=.]+[xo]|<[-=.]+>|-+\.-+>|=+>|-+(?:>|x|o)|-+\.-+|={3,}|-{3,}"
    )
    for match in pattern.finditer(mask):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        token = match.group()
        end = match.end()
        label = ""
        if end < len(text) and text[end] == "|":
            close = text.find("|", end + 1)
            if close != -1:
                label = clean_label(text[end + 1 : close])
                end = close + 1
        style, arrowhead, bidirectional, undirected = _operator_style(token)
        operators.append(
            _Operator(
                match.start(), end, label, style, arrowhead, bidirectional, undirected
            )
        )
        occupied.append((match.start(), end))
    return sorted(operators, key=lambda operator: operator.start)


def _endpoint_group(
    diagram: Diagram, text: str, parent: str | None
) -> list[str] | None:
    identifiers: list[str] = []
    for raw in _split_top_level(text.strip(), "&"):
        parsed = _parse_node_expression(raw)
        if parsed is None:
            return None
        node_id, label, shape = parsed
        diagram.add_node(node_id, label, shape, parent)
        identifiers.append(node_id)
    return identifiers or None


STYLE_DIRECTIVES = ("style ", "classDef ", "class ", "linkStyle ")


def _discard_nonsemantic(diagram: Diagram, text: str) -> bool:
    lowered = text.casefold()
    if any(lowered.startswith(prefix.casefold()) for prefix in STYLE_DIRECTIVES):
        diagram.discarded["style_directives"] += 1
        return True
    if lowered.startswith("click "):
        diagram.discarded["click_handlers"] += 1
        return True
    return False


def _parse_flowchart(
    diagram: Diagram, lines: list[tuple[int, str]], header_position: int
) -> None:
    containers: list[str] = []
    for line_number, raw in _logical_statements(lines[header_position + 1 :]):
        text = raw.strip()
        if not text:
            continue
        lowered = text.casefold()
        if _discard_nonsemantic(diagram, text):
            continue
        if lowered.startswith("direction "):
            if not containers:
                direction = text.split(maxsplit=1)[1].upper()
                if direction in {"TD", "TB", "LR", "RL", "BT"}:
                    diagram.direction = direction
            continue
        if lowered.startswith("subgraph "):
            spec = text.split(maxsplit=1)[1].strip()
            parsed = _parse_node_expression(spec)
            if parsed is None:
                generated = f"subgraph-{len([node for node in diagram.nodes if node.container]) + 1}"
                node_id, label = generated, clean_label(spec)
            else:
                node_id, label, _shape = parsed
            parent = containers[-1] if containers else None
            diagram.add_node(node_id, label, "container", parent, container=True)
            containers.append(node_id)
            continue
        if lowered == "end":
            if containers:
                containers.pop()
            continue

        operators = _edge_operators(text)
        parent = containers[-1] if containers else None
        if operators:
            segments: list[str] = []
            cursor = 0
            for operator in operators:
                segments.append(text[cursor : operator.start])
                cursor = operator.end
            segments.append(text[cursor:])
            if len(segments) != len(operators) + 1:
                _fail(f"malformed edge at line {line_number}")
            groups = [_endpoint_group(diagram, segment, parent) for segment in segments]
            if any(group is None for group in groups):
                _fail(f"malformed edge at line {line_number}")
            valid_groups = [group for group in groups if group is not None]
            for index, operator in enumerate(operators):
                for source in valid_groups[index]:
                    for target in valid_groups[index + 1]:
                        diagram.add_edge(
                            source,
                            target,
                            operator.label,
                            operator.style,
                            operator.arrowhead,
                            operator.bidirectional,
                            operator.undirected,
                        )
            continue
        if re.search(r"(?:--|==|-.).*?(?:>|x|o|-)", _top_level_mask(text)):
            _fail(f"malformed edge at line {line_number}")
        parsed = _parse_node_expression(text)
        if parsed is not None:
            node_id, label, shape = parsed
            diagram.add_node(node_id, label, shape, parent)


def _parse_sequence(
    diagram: Diagram, lines: list[tuple[int, str]], header_position: int
) -> None:
    fragment_stack: list[dict[str, Any]] = []
    participant_re = re.compile(
        r"^(?:create\s+)?(participant|actor)\s+"
        r"(?:\"([^\"]+)\"|'([^']+)'|([\w.:-]+))"
        r"(?:\s+as\s+(.+))?$",
        re.I,
    )
    # Endpoints may be bare ids or multi-word names introduced by a quoted
    # `participant "Alice Smith"` declaration; the lazy id keeps `A-->>B`
    # from swallowing dashes into the source.
    message_re = re.compile(
        r"^([\w.:-]+?(?: [\w.:-]+)*?)(?:\(\))?\s*"
        r"(<<--?>>|--?>>|--?>|--?\)|--?x)"
        r"\s*[+-]?\s*(?:\(\))?([\w.:-]+?(?: [\w.:-]+)*?)\s*:\s*(.*)$"
    )
    for line_number, raw in lines[header_position + 1 :]:
        text = raw.strip()
        if not text:
            continue
        lowered = text.casefold()
        if _discard_nonsemantic(diagram, text):
            continue
        participant = participant_re.match(text)
        if participant:
            kind = participant.group(1).casefold()
            quoted = participant.group(2) or participant.group(3)
            bare = participant.group(4)
            alias = participant.group(5)
            if quoted is not None:
                # `participant "Alice Smith" as A` — messages use the alias,
                # the quoted string is the display name.
                node_id = alias or quoted
                label = quoted
            else:
                # `participant A as Alice` — the bare token is the id.
                node_id = bare
                label = alias or bare
            diagram.add_node(
                node_id,
                clean_label(label),
                "actor" if kind == "actor" else "lifeline",
            )
            continue
        fragment = re.match(r"^(alt|opt|loop|par|critical|break)\b\s*(.*)$", text, re.I)
        if fragment:
            entry = {
                "kind": fragment.group(1).casefold(),
                "label": clean_label(fragment.group(2)),
                "line": line_number,
                "depth": len(fragment_stack),
                "regions": [],
            }
            diagram.fragments.append(entry)
            fragment_stack.append(entry)
            continue
        region = re.match(r"^(else|and|option)\b\s*(.*)$", text, re.I)
        if region and fragment_stack:
            fragment_stack[-1]["regions"].append(clean_label(region.group(2)))
            continue
        if lowered == "end":
            if fragment_stack:
                fragment_stack.pop()
            continue
        if lowered.startswith(("activate ", "deactivate ", "+", "-")):
            continue
        if lowered.startswith("note "):
            _, separator, note = text.partition(":")
            diagram.notes.append(clean_label(note if separator else text[5:]))
            continue
        message = message_re.match(text)
        if message:
            source, token, target, label = message.groups()
            # Auto-add endpoints only when undeclared, so an earlier
            # `actor`/`participant` declaration keeps its shape and label.
            for endpoint in (source, target):
                if endpoint not in diagram.node_map:
                    diagram.add_node(endpoint, endpoint, "lifeline")
            if token.endswith("x"):
                arrowhead = "cross"
            elif token.endswith(")"):
                arrowhead = "async"
            elif token.endswith(">>"):
                arrowhead = "arrow"
            else:  # `->` / `-->` are open arrows with no arrowhead
                arrowhead = "none"
            diagram.add_edge(
                source,
                target,
                clean_label(label),
                "dashed"
                if token.startswith("--") or token.startswith("<<--")
                else "solid",
                arrowhead,
                bidirectional=token.startswith("<<"),
                undirected=arrowhead == "none",
            )
            continue
        if re.search(r"<<--?>>|--?>>|--?>|--?\)|--?x", text):
            _fail(f"malformed edge at line {line_number}")


def _state_endpoint(
    diagram: Diagram,
    token: str,
    role: str,
    parent: str | None,
) -> str | None:
    value = _strip_class_suffix(token.strip())
    if value == "[*]":
        prefix = "start" if role == "source" else "end"
        count = sum(node.id.startswith("__" + prefix) for node in diagram.nodes)
        node_id = f"__{prefix}_{count + 1}"
        diagram.add_node(node_id, f"[{prefix}]", prefix, parent)
        return node_id
    parsed = _parse_node_expression(value)
    if parsed is None:
        return None
    node_id, label, shape = parsed
    diagram.add_node(node_id, label, "state" if shape == "rect" else shape, parent)
    return node_id


def _parse_state(
    diagram: Diagram, lines: list[tuple[int, str]], header_position: int
) -> None:
    containers: list[str] = []
    for line_number, raw in lines[header_position + 1 :]:
        text = raw.strip()
        if not text:
            continue
        if _discard_nonsemantic(diagram, text):
            continue
        if text == "}":
            if containers:
                containers.pop()
            continue
        parent = containers[-1] if containers else None
        direction_match = re.match(r"^direction\s+(TD|TB|LR|RL|BT)$", text, re.I)
        if direction_match and not containers:
            diagram.direction = direction_match.group(1).upper()
            continue
        composite = re.match(r"^state\s+([\w.:-]+)\s*\{$", text, re.I)
        if composite:
            node_id = composite.group(1)
            diagram.add_node(node_id, node_id, "container", parent, container=True)
            containers.append(node_id)
            continue
        alias = re.match(r'^state\s+"(.*?)"\s+as\s+([\w.:-]+)$', text, re.I)
        if alias:
            diagram.add_node(alias.group(2), clean_label(alias.group(1)), "state", parent)
            continue
        stereotype = re.match(
            r"^state\s+([\w.:-]+)\s+<<(fork|join|choice)>>$", text, re.I
        )
        if stereotype:
            diagram.add_node(
                stereotype.group(1), stereotype.group(1), stereotype.group(2).casefold(), parent
            )
            continue
        if "-->" in text:
            source_text, target_text = text.split("-->", 1)
            label = ""
            label_separator = re.search(r"(?<!:):(?!:)", target_text)
            if label_separator:
                label = target_text[label_separator.end() :]
                target_text = target_text[: label_separator.start()]
            source = _state_endpoint(diagram, source_text, "source", parent)
            target = _state_endpoint(diagram, target_text, "target", parent)
            if source is None or target is None:
                _fail(f"malformed edge at line {line_number}")
            diagram.add_edge(source, target, clean_label(label))
            continue
        description = re.match(r"^([A-Za-z_][\w.-]*)\s*:\s*(.+)$", text)
        if description:
            diagram.add_node(
                description.group(1), clean_label(description.group(2)), "state", parent
            )
            continue
        plain = re.match(r"^state\s+([\w.:-]+)$", text, re.I)
        if plain:
            diagram.add_node(plain.group(1), plain.group(1), "state", parent)


def _parse_er(
    diagram: Diagram, lines: list[tuple[int, str]], header_position: int
) -> None:
    current: Node | None = None
    relationship = re.compile(
        r"^([A-Za-z_][\w.-]*)\s+(\S*(?:--|\.\.)\S*)\s+"
        r"([A-Za-z_][\w.-]*)\s*(?::\s*(.*))?$"
    )
    for line_number, raw in lines[header_position + 1 :]:
        text = raw.strip()
        if not text:
            continue
        if _discard_nonsemantic(diagram, text):
            continue
        if text == "}":
            current = None
            continue
        direction_match = re.match(r"^direction\s+(TD|TB|LR|RL|BT)$", text, re.I)
        if direction_match and current is None:
            diagram.direction = direction_match.group(1).upper()
            continue
        entity = re.match(r"^([A-Za-z_][\w.-]*)\s*\{$", text)
        if entity:
            current = diagram.add_node(entity.group(1), entity.group(1), "table")
            continue
        if current is not None:
            current.fields.append(clean_label(text))
            continue
        edge = relationship.match(text)
        if edge:
            source, cardinality, target, relationship_label = edge.groups()
            diagram.add_node(source, source, "table")
            diagram.add_node(target, target, "table")
            left, separator, right = cardinality.partition("--")
            if not separator:
                left, separator, right = cardinality.partition("..")
            label_parts = [f"{left} {separator} {right}".strip()]
            if relationship_label:
                label_parts.append(clean_label(relationship_label))
            diagram.add_edge(
                source,
                target,
                " · ".join(label_parts),
                "dashed" if separator == ".." else "solid",
                "cardinality",
                undirected=True,
            )
            continue
        if "--" in text or ".." in text:
            _fail(f"malformed edge at line {line_number}")


def parse_block(block: SourceBlock) -> Diagram:
    lines = _prepared_lines(block)
    kind, direction, header_position = _kind_and_direction(lines)
    diagram = Diagram(block.index, kind, block.source_line, direction=direction)
    if kind == "flowchart":
        _parse_flowchart(diagram, lines, header_position)
    elif kind == "sequenceDiagram":
        _parse_sequence(diagram, lines, header_position)
    elif kind == "stateDiagram-v2":
        _parse_state(diagram, lines, header_position)
    else:
        _parse_er(diagram, lines, header_position)
    _finalize_degrees(diagram)
    return diagram


def _finalize_degrees(diagram: Diagram) -> None:
    nodes = diagram.node_map
    for edge in diagram.edges:
        if edge.source in nodes:
            nodes[edge.source].out_degree += 1
        if edge.target in nodes:
            nodes[edge.target].in_degree += 1


def _has_cycle(nodes: list[Node], edges: list[Edge]) -> bool:
    adjacency: dict[str, list[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.source in adjacency and edge.target in adjacency:
            adjacency[edge.source].append(edge.target)
    WHITE, GREY, BLACK = 0, 1, 2
    colors = {node.id: WHITE for node in nodes}

    def visit(start: str) -> bool:
        stack: list[tuple[str, Any]] = [(start, iter(adjacency[start]))]
        colors[start] = GREY
        while stack:
            node_id, targets = stack[-1]
            for target in targets:
                if colors.get(target, BLACK) == GREY:
                    return True
                if colors.get(target, BLACK) == WHITE:
                    colors[target] = GREY
                    stack.append((target, iter(adjacency.get(target, []))))
                    break
            else:
                colors[node_id] = BLACK
                stack.pop()
        return False

    return any(colors[node.id] == WHITE and visit(node.id) for node in nodes)


def shape_family(shape: str) -> str:
    return "container" if shape == "container" else shape


def analyze(diagram: Diagram) -> dict[str, Any]:
    containers = [node for node in diagram.nodes if node.container or node.children]
    leaves = [node for node in diagram.nodes if not (node.container or node.children)]
    shapes: dict[str, int] = {}
    for node in diagram.nodes:
        family = shape_family(node.shape)
        shapes[family] = shapes.get(family, 0) + 1

    def name(node: Node) -> str:
        return node.label.replace("\n", " · ") or node.id

    hubs = [
        {"id": node.id, "label": name(node), "degree": node.in_degree + node.out_degree}
        for node in sorted(
            leaves,
            key=lambda item: (item.in_degree + item.out_degree, item.id),
            reverse=True,
        )[:5]
        if node.in_degree + node.out_degree > 0
    ]
    entry_points = [name(node) for node in leaves if node.out_degree and not node.in_degree]
    terminals = [name(node) for node in leaves if node.in_degree and not node.out_degree]
    orphans = [name(node) for node in leaves if not node.in_degree and not node.out_degree]
    candidates = {
        "flowchart": ["flowchart" if shapes.get("rhombus") else "architecture", "architecture"],
        "sequenceDiagram": ["sequence"],
        "stateDiagram-v2": ["state machine"],
        "erDiagram": ["ER / data model"],
    }[diagram.kind]
    candidates = list(dict.fromkeys(candidates))
    collapsible = [
        {
            "id": node.id,
            "label": name(node),
            "children": len(node.children),
            "child_labels": [
                name(diagram.node_map[child])
                for child in node.children
                if child in diagram.node_map
            ][:8],
        }
        for node in containers
        if node.children
    ]
    collapsible.sort(key=lambda item: item["children"], reverse=True)
    drawable = len(leaves)
    return {
        "nodes_total": len(diagram.nodes),
        "nodes_drawable": drawable,
        "containers": len(containers),
        "leaves": len(leaves),
        "edges_total": len(diagram.edges),
        "edges_labeled": sum(bool(edge.label) for edge in diagram.edges),
        "edges_dangling": 0,
        "max_depth": max((node.depth for node in diagram.nodes), default=0),
        "shapes": dict(sorted(shapes.items(), key=lambda item: (-item[1], item[0]))),
        "has_cycle": _has_cycle(diagram.nodes, diagram.edges),
        "hubs": hubs,
        "entry_points": entry_points[:6],
        "terminals": terminals[:6],
        "orphans": orphans[:6],
        "type_candidates": candidates,
        "collapsible_groups": collapsible[:8],
        "over_node_budget": drawable > 9,
        "over_edge_budget": len(diagram.edges) > 12,
    }


def _escape_markdown(text: str) -> str:
    encoded = html.escape(text, quote=False)
    return re.sub(r"([\\`*{}\[\]()#+\-.!_|>])", r"\\\1", encoded)


def _escape_table(text: str) -> str:
    return _escape_markdown(text.replace("\n", " ⏎ "))


def digest(
    path: Path,
    diagrams: list[Diagram],
    selected: list[Diagram],
    max_rows: int,
) -> str:
    output = [f"# Mermaid IR — {path.name}", ""]
    output.append(
        f"{len(diagrams)} diagram(s): "
        + ", ".join(
            f"[{diagram.index}] {diagram.kind} ({len(diagram.nodes)}n/{len(diagram.edges)}e)"
            for diagram in diagrams
        )
    )
    for diagram in selected:
        info = analyze(diagram)
        output.extend(
            [
                "",
                f"## Diagram {diagram.index} — {diagram.kind}",
                "",
                f"- source layout: none (Mermaid is layout-free); direction: {diagram.direction}",
                f"- nodes: {info['nodes_total']} total / {info['nodes_drawable']} drawable / "
                f"{info['containers']} containers, depth {info['max_depth']}",
                f"- edges: {info['edges_total']} ({info['edges_labeled']} labeled, "
                f"{info['edges_dangling']} dangling), cycle: {info['has_cycle']}",
                f"- shapes: {info['shapes']}",
                f"- type candidates: {', '.join(info['type_candidates'])}",
                f"- budget: nodes {'OVER' if info['over_node_budget'] else 'ok'} (max 9), "
                f"edges {'OVER' if info['over_edge_budget'] else 'ok'} (max 12)",
            ]
        )
        if diagram.discarded["style_directives"] or diagram.discarded["click_handlers"]:
            output.append(
                f"- discarded: {diagram.discarded['style_directives']} style directives, "
                f"{diagram.discarded['click_handlers']} click handlers"
            )
        if diagram.fragments:
            fragments = ", ".join(
                f"{item['kind']}({_escape_markdown(item['label'] or 'unlabeled')})"
                for item in diagram.fragments
            )
            output.append(f"- fragments: {fragments}")
        if diagram.notes:
            output.append(
                f"- notes: {'; '.join(_escape_markdown(note) for note in diagram.notes[:6])}"
            )
        if info["hubs"]:
            output.append(
                "- hubs (focal candidates): "
                + ", ".join(
                    f"{_escape_markdown(hub['label'])}({hub['degree']})"
                    for hub in info["hubs"]
                )
            )
        if info["entry_points"]:
            output.append(
                f"- entry points: {', '.join(_escape_markdown(label) for label in info['entry_points'])}"
            )
        if info["terminals"]:
            output.append(
                f"- terminals: {', '.join(_escape_markdown(label) for label in info['terminals'])}"
            )
        if info["orphans"]:
            output.append(
                f"- unconnected: {', '.join(_escape_markdown(label) for label in info['orphans'])}"
            )
        if info["collapsible_groups"]:
            output.append("- collapsible groups (simplify here first):")
            for group in info["collapsible_groups"]:
                output.append(
                    f"  - {_escape_markdown(group['label'])} — {group['children']} children: "
                    + ", ".join(_escape_markdown(label) for label in group["child_labels"])
                )

        output.extend(
            [
                "",
                "### Nodes",
                "",
                "| id | label | shape | depth | parent | deg | fields |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for node in diagram.nodes[:max_rows]:
            output.append(
                f"| {_escape_table(node.id)} | {_escape_table(node.label)} | {node.shape} | "
                f"{node.depth} | {node.parent or '-'} | {node.in_degree}/{node.out_degree} | "
                f"{_escape_table('; '.join(node.fields)) or '-'} |"
            )
        if len(diagram.nodes) > max_rows:
            output.append(
                f"| … | +{len(diagram.nodes) - max_rows} more (use --json) | | | | | |"
            )

        output.extend(
            [
                "",
                "### Edges",
                "",
                "| source | target | label | style |",
                "|---|---|---|---|",
            ]
        )
        names = {node.id: node.label.split("\n")[0] for node in diagram.nodes}
        for edge in diagram.edges[:max_rows]:
            marks = [edge.style, edge.arrowhead]
            if edge.bidirectional:
                marks.append("bidir")
            if edge.undirected:
                marks.append("undirected")
            output.append(
                f"| {_escape_table(names.get(edge.source, edge.source))} | "
                f"{_escape_table(names.get(edge.target, edge.target))} | "
                f"{_escape_table(edge.label) or '-'} | {' '.join(marks)} |"
            )
        if len(diagram.edges) > max_rows:
            output.append(
                f"| … | +{len(diagram.edges) - max_rows} more (use --json) | | |"
            )
    output.append("")
    return "\n".join(output)


def to_json(path: Path, diagrams: list[Diagram], selected: list[Diagram]) -> str:
    return json.dumps(
        {
            "source": str(path),
            "diagrams_total": len(diagrams),
            "diagrams": [
                {
                    "index": diagram.index,
                    "kind": diagram.kind,
                    "source_line": diagram.source_line,
                    "direction": diagram.direction,
                    "analysis": analyze(diagram),
                    "discarded": diagram.discarded,
                    "fragments": diagram.fragments,
                    "notes": diagram.notes,
                    "nodes": [asdict(node) for node in diagram.nodes],
                    "edges": [asdict(edge) for edge in diagram.edges],
                }
                for diagram in selected
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def select_diagrams(diagrams: list[Diagram], selector: str | None) -> list[Diagram]:
    if selector is None:
        return diagrams[:1]
    if selector == "all":
        return diagrams
    if selector.isdigit():
        index = int(selector)
        selected = [diagram for diagram in diagrams if diagram.index == index]
        if not selected:
            _fail(f"no diagram with index {index} (have 0..{len(diagrams) - 1})")
        return selected
    _fail("--diagram must be an index or 'all'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", help=".mmd, .mermaid, or Markdown with mermaid fences")
    parser.add_argument(
        "--diagram", help="diagram index or 'all' (default: first diagram)"
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
        _fail("--max-rows must be at least 1")

    path = Path(args.file)
    if not path.is_file():
        _fail(f"{path}: no such file")
    blocks = load_blocks(path)
    diagrams = [parse_block(block) for block in blocks]
    selected = select_diagrams(diagrams, args.diagram)
    output = (
        to_json(path, diagrams, selected)
        if args.json
        else digest(path, diagrams, selected, args.max_rows)
    )
    if args.out:
        try:
            Path(args.out).write_text(output, encoding="utf-8")
        except OSError as error:
            _fail(f"cannot write {args.out}: {error}")
        print(f"wrote {args.out} ({len(output)} bytes)")
    else:
        sys.stdout.write(output if output.endswith("\n") else output + "\n")
    return 0


if __name__ == "__main__":
    _configure_stdout_utf8()
    raise SystemExit(main())
