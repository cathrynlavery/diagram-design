#!/usr/bin/env python3
"""Extract a normalized intermediate representation (IR) from PlantUML text.

Trust boundary: this program parses bounded text. It never evaluates, renders,
fetches, or executes PlantUML, Graphviz, URLs, includes, macros, or label
content. Every label, note, stereotype, and URL is untrusted data. Includes,
themes loaded from a URL, and preprocessor bodies that would run fail closed.
Skinparams and local themes are counted and discarded; retained labels are
emitted only as inert text.

Supported kinds are sequence and class. Inputs may be .puml, .plantuml, .pu,
or Markdown files containing fenced ``plantuml`` / ``puml`` blocks.

Usage:
    python3 plantuml_extract.py <file> [--diagram N|all] [--json]
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
MAX_STATEMENT_CHARS = 4096
SUPPORTED_KINDS = "sequence, class"
UNSUPPORTED_STARTS = {
    "activity",
    "component",
    "deployment",
    "state",
    "usecase",
    "archimate",
    "board",
    "bpmn",
    "chen",
    "chronology",
    "creole",
    "ditaa",
    "dot",
    "ebnf",
    "files",
    "gantt",
    "git",
    "jcckit",
    "json",
    "latex",
    "math",
    "mindmap",
    "network",
    "nwdiag",
    "project",
    "regex",
    "salt",
    "smetana",
    "tree",
    "wbs",
    "wire",
    "yaml",
}
MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd"}
PLANTUML_SUFFIXES = {".puml", ".plantuml", ".pu"}
INCLUDE_RE = re.compile(
    r"^\s*(?:!include(?:url|sub)?\b|!import\b|%load_json\b|"
    r"!function\b|!procedure\b)",
    re.I,
)
DEFINE_INCLUDE_RE = re.compile(r"^\s*!define\b.*!include", re.I)
THEME_URL_RE = re.compile(r"^\s*!theme\b.*https?://", re.I)
START_RE = re.compile(r"^@start([A-Za-z][A-Za-z0-9_-]*)\b(?:\s+\S+|\(\s*\S+\s*\))?", re.I)
END_RE = re.compile(r"^@end([A-Za-z][A-Za-z0-9_-]*)\b", re.I)
FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*(plantuml|puml)\s*$", re.I)
CLASS_DECL_RE = re.compile(
    r"^\s*(?:abstract\s+)?(?:class|interface|enum)\b",
    re.I,
)
SEQ_DECL_RE = re.compile(r"^\s*(?:participant|actor)\b", re.I)
CLASS_REL_RE = re.compile(r"<\|--|-\|>|\*--|o--|<\|\.\.|\.\.\|>")
SEQ_ARROW_RE = re.compile(r"(->>|<<-|<->|-->|<--|<-|->)")
CLASS_ARROWS = (
    "<|--",
    "--|>",
    "<|..",
    "..|>",
    "*--",
    "--*",
    "o--",
    "--o",
    "-->",
    "<--",
    "..>",
    "<..",
    "--",
    "..",
)
SEQ_ARROWS = ("->>", "<<-", "<->", "-->", "<--", "<-", "->")
LIFELINE_KINDS = {
    "participant": "lifeline",
    "actor": "actor",
    "boundary": "lifeline",
    "control": "lifeline",
    "entity": "lifeline",
    "database": "lifeline",
    "collections": "lifeline",
    "queue": "lifeline",
}
CLASSIFIER_KINDS = {
    "class": "class",
    "abstract class": "abstract",
    "interface": "interface",
    "enum": "enum",
}
SKIN_PREFIXES = (
    "skinparam",
    "!theme",
    "autonumber",
    "hide",
    "show",
    "header",
    "footer",
    "legend",
    "caption",
    "scale",
    "sprite",
    "!pragma",
    "order ",
    "left to right direction",
    "top to bottom direction",
)
UNSUPPORTED_SEQUENCE = {
    "par",
    "critical",
    "break",
    "group",
    "box",
    "ref",
    "rnote",
    "hnote",
    "&",
}
UNSUPPORTED_CLASS = {
    "annotation",
    "abstract",
    "protocol",
    "struct",
    "exception",
    "metaclass",
    "stereotype",
}


def _configure_stdout_utf8() -> None:
    """Emit digests as UTF-8 even when Windows selects a legacy codepage."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="strict")


class ExtractError(Exception):
    """An input the extractor refuses. `main()` reports it and exits 2."""


def _fail(message: str) -> NoReturn:
    raise ExtractError(message)


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
    stereotype: str = ""
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
    cardinality: str = ""
    order: int = 0


@dataclass
class Diagram:
    index: int
    kind: str
    source_line: int
    direction: str = "TD"
    title: str = ""
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    fragments: list[dict[str, Any]] = field(default_factory=list)
    activations: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    discarded: dict[str, int] = field(
        default_factory=lambda: {"skin": 0, "includes": 0}
    )
    _nodes_by_id: dict[str, Node] = field(default_factory=dict, init=False, repr=False)
    _aliases: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    @property
    def node_map(self) -> dict[str, Node]:
        return self._nodes_by_id

    def resolve(self, token: str) -> str:
        key = token.strip()
        return self._aliases.get(key, self._aliases.get(key.casefold(), key))

    def alias(self, alias: str, node_id: str) -> None:
        self._aliases[alias] = node_id
        self._aliases[alias.casefold()] = node_id

    def add_node(
        self,
        node_id: str,
        label: str = "",
        shape: str = "rect",
        parent: str | None = None,
        container: bool = False,
        stereotype: str = "",
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
            if stereotype and not existing.stereotype:
                existing.stereotype = stereotype
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
            stereotype=stereotype,
        )
        self.nodes.append(node)
        self._nodes_by_id[node_id] = node
        self.alias(node_id, node_id)
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
        cardinality: str = "",
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
            cardinality=cardinality,
            order=len(self.edges) + 1,
        )
        self.edges.append(edge)
        return edge

    def add_activation(self, participant: str, action: str) -> None:
        self.activations.append(
            {
                "participant": participant,
                "action": action,
                "order": len(self.activations) + 1,
            }
        )


@dataclass
class SourceBlock:
    index: int
    text: str
    source_line: int
    start_kind: str = "uml"


def clean_label(value: str) -> str:
    """Flatten PlantUML / Creole / HTML label markup without interpreting it."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    text = text.replace("\\n", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"//(.*?)//", r"\1", text)
    text = re.sub(r'""(.*?)""', r"\1", text)
    text = re.sub(r"--([^-]+)--+", r"\1", text)
    text = text.replace('\\"', '"').replace("\\'", "'")
    return "\n".join(part.strip() for part in text.splitlines()).strip()


def _read_bounded(path: Path) -> str:
    try:
        with path.open("rb") as source:
            data = source.read(MAX_SOURCE_BYTES + 1)
    except OSError as error:
        _fail(f"{path}: {error}")
    if len(data) > MAX_SOURCE_BYTES:
        _fail(f"source exceeds the {MAX_SOURCE_BYTES // (1024 * 1024)} MiB limit")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        _fail(f"{path.name}: source is not valid UTF-8 text")


def _split_uml_regions(text: str, base_line: int) -> list[tuple[int, str, str]]:
    """Return (start_line, body, start_kind) for each @start/@end region."""
    regions: list[tuple[int, str, str]] = []
    lines = text.splitlines()
    start: int | None = None
    kind = "uml"
    body: list[str] = []
    for offset, raw in enumerate(lines):
        stripped = raw.strip()
        opened = START_RE.match(stripped)
        closed = END_RE.match(stripped)
        if start is None:
            if opened:
                start = base_line + offset + 1
                kind = opened.group(1).casefold()
                body = []
            continue
        if closed:
            regions.append((start, "\n".join(body), kind))
            start = None
            body = []
            continue
        body.append(raw)
    if start is not None:
        regions.append((start, "\n".join(body), kind))
    return regions


def load_blocks(path: Path) -> list[SourceBlock]:
    suffix = path.suffix.casefold()
    if suffix not in PLANTUML_SUFFIXES | MARKDOWN_SUFFIXES:
        _fail(f"{path.name}: not a PlantUML file")
    source = _read_bounded(path)
    collected: list[SourceBlock] = []

    def add(start_line: int, text: str, start_kind: str) -> None:
        collected.append(SourceBlock(len(collected), text, start_line, start_kind))

    if suffix in PLANTUML_SUFFIXES:
        regions = _split_uml_regions(source, 1)
        if not regions:
            _fail(f"{path.name}: no @startuml block found")
        for start_line, text, kind in regions:
            add(start_line, text, kind)
        return collected

    lines = source.splitlines()
    start: int | None = None
    fence = ""
    content: list[str] = []
    for line_number, line in enumerate(lines, 1):
        if start is None:
            match = FENCE_OPEN_RE.match(line)
            if match:
                start = line_number + 1
                fence = match.group(1)
                content = []
            continue
        if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line):
            block_text = "\n".join(content)
            regions = _split_uml_regions(block_text, start)
            if regions:
                for start_line, text, kind in regions:
                    add(start_line, text, kind)
            else:
                add(start, block_text, "uml")
            start = None
            fence = ""
            content = []
        else:
            content.append(line)
    if start is not None:
        _fail(f"{path.name}: unterminated plantuml fence starting at line {start - 1}")
    if not collected:
        _fail(f"{path.name}: no fenced plantuml block found")
    return collected


def _blank_comments(lines: list[str]) -> list[str]:
    prepared: list[str] = []
    in_block = False
    for raw in lines:
        if in_block:
            if "'/" in raw:
                in_block = False
            prepared.append("")
            continue
        stripped = raw.strip()
        if stripped.startswith("/'"):
            if "'/" not in stripped[2:]:
                in_block = True
            prepared.append("")
            continue
        if stripped.startswith("'"):
            prepared.append("")
            continue
        prepared.append(raw.rstrip())
    return prepared


def _refuse_includes(lines: list[tuple[int, str]]) -> None:
    for _line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if INCLUDE_RE.match(text) or DEFINE_INCLUDE_RE.match(text) or THEME_URL_RE.match(text):
            _fail("include not inlined")


def _unsupported_kind_message(token: str) -> str:
    return f"unsupported diagram kind: `{token}` (supported: {SUPPORTED_KINDS})"


def _unsupported_body_kind(text: str) -> str | None:
    """Return a named unsupported kind when the body is clearly not sequence/class."""
    if text.startswith("[*]"):
        return "state"
    if re.match(r"^state\b", text, re.I) and not _find_arrow(text, SEQ_ARROWS):
        return "state"
    match = re.match(r"^(component|usecase)\b", text, re.I)
    if match and not _find_arrow(text, SEQ_ARROWS):
        return match.group(1).casefold()
    return None


def _detect_kind(lines: list[tuple[int, str]]) -> str:
    has_class = False
    has_seq_decl = False
    has_class_rel = False
    has_seq_msg = False
    unsupported: str | None = None
    for _line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if CLASS_DECL_RE.match(text):
            has_class = True
        if SEQ_DECL_RE.match(text):
            has_seq_decl = True
        if CLASS_REL_RE.search(text):
            has_class_rel = True
        if SEQ_ARROW_RE.search(text) and ":" in text:
            has_seq_msg = True
        hint = _unsupported_body_kind(text)
        if hint and unsupported is None:
            unsupported = hint
    if has_class and has_seq_decl:
        _fail("mixed or unknown kind")
    if unsupported and not has_class and not has_seq_decl:
        _fail(_unsupported_kind_message(unsupported))
    if has_class or (has_class_rel and not has_seq_decl and not has_seq_msg):
        return "class"
    if has_seq_decl or has_seq_msg:
        return "sequence"
    if unsupported:
        _fail(_unsupported_kind_message(unsupported))
    _fail("mixed or unknown kind")


def _statement_too_long(line_number: int) -> NoReturn:
    _fail(
        f"statement at line {line_number} exceeds the "
        f"{MAX_STATEMENT_CHARS}-character limit"
    )


def _quoted_or_token(text: str) -> tuple[str, str]:
    """Return (display_or_id, remainder) from a leading quoted string or token."""
    stripped = text.strip()
    if stripped[:1] in "\"'":
        quote = stripped[0]
        end = 1
        while end < len(stripped):
            if stripped[end] == quote and stripped[end - 1] != "\\":
                break
            end += 1
        else:
            return stripped, ""
        return stripped[1:end], stripped[end + 1 :].strip()
    match = re.match(r"^([A-Za-z_][\w.-]*|[\w.-]+)\s*(.*)$", stripped)
    if not match:
        return stripped, ""
    return match.group(1), match.group(2).strip()


def _parse_classifier_header(text: str) -> tuple[str, str, str, str, bool] | None:
    match = re.match(
        r"^(abstract\s+class|class|interface|enum)\s+(.+)$",
        text,
        re.I,
    )
    if not match:
        return None
    kind = match.group(1).casefold()
    rest = match.group(2).strip()
    opens = rest.endswith("{")
    if opens:
        rest = rest[:-1].strip()
    stereotype = ""
    stereo = re.search(r"<<\s*(?:\(\s*[^)]*\)\s*)?([^>]*?)\s*>>", rest)
    if stereo:
        stereotype = clean_label(stereo.group(1))
        rest = (rest[: stereo.start()] + rest[stereo.end() :]).strip()
    display, remainder = _quoted_or_token(rest)
    node_id = display
    label = display
    as_match = re.match(r"^as\s+(\S+)\s*$", remainder, re.I)
    if as_match:
        node_id = as_match.group(1)
        label = display
    elif remainder:
        leftover = remainder.split()
        if leftover:
            node_id = leftover[0]
    return node_id, clean_label(label) or node_id, CLASSIFIER_KINDS[kind], stereotype, opens


def _parse_participant(text: str) -> tuple[str, str, str] | None:
    match = re.match(
        r"^(participant|actor|boundary|control|entity|database|collections|queue)\s+(.+)$",
        text,
        re.I,
    )
    if not match:
        return None
    kind = match.group(1).casefold()
    rest = match.group(2).strip()
    order = re.search(r"\border\s+\d+\b", rest, re.I)
    if order:
        rest = (rest[: order.start()] + rest[order.end() :]).strip()
    display, remainder = _quoted_or_token(rest)
    node_id = display
    label = display
    as_match = re.match(r"^as\s+(\S+)\s*$", remainder, re.I)
    if as_match:
        node_id = as_match.group(1)
        label = display
    elif remainder and not remainder.lower().startswith("order"):
        leftover = remainder.split()
        if leftover and leftover[0].lower() != "order":
            node_id = leftover[0]
    return node_id, clean_label(label) or node_id, LIFELINE_KINDS[kind]


def _find_arrow(text: str, arrows: tuple[str, ...]) -> tuple[str, str, str] | None:
    """Split *text* around the first relationship arrow that is not inside quotes."""
    in_quote: str | None = None
    escaped = False
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if in_quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == in_quote:
                in_quote = None
            index += 1
            continue
        if character in "\"'":
            in_quote = character
            index += 1
            continue
        for arrow in arrows:
            if text.startswith(arrow, index):
                left = text[:index].strip()
                right = text[index + len(arrow) :].strip()
                if left and right:
                    return left, arrow, right
        index += 1
    return None


def _split_cardinality(side: str) -> tuple[str, str]:
    """Split a class name from an optional quoted cardinality on either side."""
    text = side.strip()
    leading = re.match(r'^"([^"]*)"\s+(.+)$', text)
    if leading:
        return leading.group(2).strip(), leading.group(1)
    trailing = re.match(r'^(.+?)\s+"([^"]*)"$', text)
    if trailing:
        return trailing.group(1).strip(), trailing.group(2)
    return text, ""


def _relationship_kind(arrow: str) -> tuple[str, str, bool, bool, bool]:
    """Return (arrowhead, style, reverse, bidirectional, undirected)."""
    dashed = ".." in arrow
    style = "dashed" if dashed else "solid"
    if arrow in ("<|--", "--|>", "<|..", "..|>"):
        return "inheritance", style, arrow in ("<|--", "<|.."), False, False
    if arrow in ("*--", "--*"):
        return "composition", style, arrow == "--*", False, False
    if arrow in ("o--", "--o"):
        return "aggregation", style, arrow == "--o", False, False
    if arrow in ("-->", "<--", "..>", "<.."):
        return "association", style, arrow in ("<--", "<.."), False, False
    return "association", style, False, False, True


def _seq_arrow_style(arrow: str) -> tuple[str, str, bool, bool]:
    reverse = arrow in ("<--", "<<-", "<-")
    bidirectional = arrow == "<->"
    dashed = arrow in ("-->", "<--")
    async_arrow = arrow in ("->>", "<<-")
    if async_arrow:
        arrowhead = "async"
    elif arrow in ("->", "-->", "<--", "<-", "<->"):
        arrowhead = "arrow"
    else:
        arrowhead = "arrow"
    return ("dashed" if dashed else "solid"), arrowhead, reverse, bidirectional


def _consume_activation_marks(text: str) -> tuple[str, str | None]:
    stripped = text.strip()
    if stripped.startswith("++"):
        return stripped[2:].strip(), "activate"
    if stripped.startswith("--"):
        return stripped[2:].strip(), "deactivate"
    if stripped.endswith("++"):
        return stripped[:-2].strip(), "activate"
    if stripped.endswith("--"):
        return stripped[:-2].strip(), "deactivate"
    return stripped, None


def _is_skin(text: str) -> bool:
    lowered = text.casefold()
    return any(lowered.startswith(prefix) for prefix in SKIN_PREFIXES)


def _parse_sequence(diagram: Diagram, lines: list[tuple[int, str]]) -> None:
    fragment_stack: list[dict[str, Any]] = []
    note_target: str | None = None
    note_lines: list[str] = []
    note_start = 0
    skip_until_end = None

    def close_note() -> None:
        nonlocal note_target, note_lines
        body = clean_label("\n".join(note_lines))
        if body:
            diagram.notes.append(body)
            if note_target is not None:
                node_id = diagram.resolve(note_target)
                if node_id in diagram.node_map:
                    diagram.node_map[node_id].fields.append(body)
        note_target = None
        note_lines = []

    for line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if len(text) > MAX_STATEMENT_CHARS:
            _statement_too_long(line_number)
        lowered = text.casefold()
        if note_target is not None or note_lines:
            if lowered in {"end note", "endnote"}:
                close_note()
                continue
            note_lines.append(text)
            continue
        if skip_until_end is not None:
            if lowered == "end":
                skip_until_end = None
            continue
        if _is_skin(text):
            diagram.discarded["skin"] += 1
            continue
        title = re.match(r"^title\s+(.+)$", text, re.I)
        if title:
            diagram.title = clean_label(title.group(1))
            continue
        participant = _parse_participant(text)
        if participant:
            node_id, label, shape = participant
            diagram.add_node(node_id, label, shape)
            if node_id != label:
                diagram.alias(label, node_id)
            continue
        divider = re.match(r"^==+\s*(.*?)\s*==+$", text)
        if divider:
            diagram.fragments.append(
                {
                    "kind": "divider",
                    "label": clean_label(divider.group(1)),
                    "line": line_number,
                    "depth": len(fragment_stack),
                    "regions": [],
                }
            )
            continue
        fragment = re.match(r"^(alt|opt|loop)\b\s*(.*)$", text, re.I)
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
        region = re.match(r"^else\b\s*(.*)$", text, re.I)
        if region:
            if not fragment_stack:
                _fail(f"malformed statement at line {line_number}")
            fragment_stack[-1]["regions"].append(clean_label(region.group(1)))
            continue
        if lowered == "end":
            if fragment_stack:
                fragment_stack.pop()
                continue
            _fail(f"malformed statement at line {line_number}")
        first = lowered.split(maxsplit=1)[0]
        if first in UNSUPPORTED_SEQUENCE:
            _fail(f"unsupported sequence construct: {first}")
        activate = re.match(r"^(activate|deactivate)\s+(.+)$", text, re.I)
        if activate:
            action = activate.group(1).casefold()
            target = diagram.resolve(clean_label(activate.group(2)))
            if target not in diagram.node_map:
                diagram.add_node(target, target, "lifeline")
            diagram.add_activation(target, action)
            continue
        note = re.match(
            r"^note\s+(?:left|right|over|top|bottom)(?:\s+of)?\s+([^:]+?)(?:\s*:\s*(.*))?$",
            text,
            re.I,
        )
        if note:
            target_token = note.group(1).split(",")[0].strip()
            body = note.group(2)
            note_target = clean_label(target_token) or target_token
            if note_target not in diagram.node_map:
                resolved = diagram.resolve(note_target)
                if resolved not in diagram.node_map:
                    diagram.add_node(resolved, note_target, "lifeline")
                note_target = resolved
            if body is not None:
                note_lines = [body]
                close_note()
            else:
                note_lines = []
                note_start = line_number
            continue
        if lowered.startswith("note "):
            _fail(f"malformed statement at line {line_number}")
        split = _find_arrow(text, SEQ_ARROWS)
        if split:
            left, arrow, right = split
            left, left_mark = _consume_activation_marks(left)
            message = ""
            if ":" in right:
                right, _sep, message = right.partition(":")
            right, right_mark = _consume_activation_marks(right.strip())
            source_name = clean_label(left) or left
            target_name = clean_label(right) or right
            style, arrowhead, reverse, bidirectional = _seq_arrow_style(arrow)
            if reverse:
                source_name, target_name = target_name, source_name
            source = diagram.resolve(source_name)
            target = diagram.resolve(target_name)
            if source not in diagram.node_map:
                diagram.add_node(source, source_name, "lifeline")
            if target not in diagram.node_map:
                diagram.add_node(target, target_name, "lifeline")
            diagram.add_edge(
                source,
                target,
                clean_label(message),
                style,
                arrowhead,
                bidirectional=bidirectional,
            )
            if left_mark:
                diagram.add_activation(source, left_mark)
            if right_mark:
                diagram.add_activation(target, right_mark)
            continue
        if SEQ_ARROW_RE.search(text):
            _fail(f"malformed edge at line {line_number}")
        _fail(f"malformed statement at line {line_number}")
    if note_target is not None or note_lines:
        _fail(f"unterminated note at line {note_start}")
    if fragment_stack:
        _fail(f"unterminated fragment at line {fragment_stack[-1]['line']}")


def _parse_class(diagram: Diagram, lines: list[tuple[int, str]]) -> None:
    current: Node | None = None
    packages: list[str] = []
    in_skin_block = False
    for line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if len(text) > MAX_STATEMENT_CHARS:
            _statement_too_long(line_number)
        if in_skin_block:
            if text == "}":
                in_skin_block = False
            continue
        if _is_skin(text):
            diagram.discarded["skin"] += 1
            if text.endswith("{"):
                in_skin_block = True
            continue
        title = re.match(r"^title\s+(.+)$", text, re.I)
        if title:
            diagram.title = clean_label(title.group(1))
            continue
        if text == "}":
            if current is not None:
                current = None
                continue
            if packages:
                packages.pop()
                continue
            _fail(f"malformed statement at line {line_number}")
        package = re.match(r"^(package|namespace|together)\b\s*(.*)$", text, re.I)
        if package:
            rest = package.group(2).strip()
            opens = rest.endswith("{")
            if opens:
                rest = rest[:-1].strip()
            display, remainder = _quoted_or_token(rest or package.group(1))
            node_id = display or f"group{len(packages) + 1}"
            if remainder.lower().startswith("as "):
                node_id = remainder.split(None, 1)[1].strip() or node_id
            parent = packages[-1] if packages else None
            diagram.add_node(node_id, clean_label(display) or node_id, "container", parent, True)
            if opens:
                packages.append(node_id)
            continue
        header = _parse_classifier_header(text)
        if header:
            node_id, label, shape, stereotype, opens = header
            parent = packages[-1] if packages else None
            node = diagram.add_node(node_id, label, shape, parent, stereotype=stereotype)
            if node_id != label:
                diagram.alias(label, node_id)
            current = node if opens else None
            continue
        if current is not None:
            if text in {"--", "..", "==", "__"}:
                continue
            current.fields.append(clean_label(text))
            continue
        note = re.match(
            r"^note\s+(?:left|right|top|bottom)(?:\s+of)?\s+([^:]+?)(?:\s*:\s*(.*))?$",
            text,
            re.I,
        )
        if note:
            target_token = clean_label(note.group(1).split(",")[0])
            body = note.group(2)
            if body is None:
                _fail(f"malformed statement at line {line_number}")
            target = diagram.resolve(target_token)
            if target not in diagram.node_map:
                diagram.add_node(target, target_token, "class")
            cleaned = clean_label(body)
            diagram.notes.append(cleaned)
            diagram.node_map[target].fields.append(cleaned)
            continue
        split = _find_arrow(text, CLASS_ARROWS)
        if split:
            left, arrow, right = split
            label = ""
            if ":" in right:
                right, _sep, label = right.partition(":")
            left_name, left_card = _split_cardinality(left)
            right_name, right_card = _split_cardinality(right.strip())
            source_name = clean_label(left_name) or left_name
            target_name = clean_label(right_name) or right_name
            arrowhead, style, reverse, bidirectional, undirected = _relationship_kind(arrow)
            if reverse:
                source_name, target_name = target_name, source_name
                left_card, right_card = right_card, left_card
            source = diagram.resolve(source_name)
            target = diagram.resolve(target_name)
            if source not in diagram.node_map:
                diagram.add_node(source, source_name, "class")
            if target not in diagram.node_map:
                diagram.add_node(target, target_name, "class")
            cards = " .. ".join(part for part in (left_card, right_card) if part)
            relation_label = clean_label(label)
            parts = [part for part in (cards, relation_label) if part]
            diagram.add_edge(
                source,
                target,
                " · ".join(parts),
                style,
                arrowhead,
                bidirectional=bidirectional,
                undirected=undirected,
                cardinality=cards,
            )
            continue
        if CLASS_REL_RE.search(text) or "--" in text or ".." in text:
            _fail(f"malformed edge at line {line_number}")
        first = text.casefold().split(maxsplit=1)[0]
        if first in UNSUPPORTED_CLASS:
            _fail(f"unsupported class construct: {first}")
        _fail(f"malformed statement at line {line_number}")


def parse_block(block: SourceBlock) -> Diagram:
    if block.start_kind != "uml":
        token = block.start_kind
        if token in UNSUPPORTED_STARTS or token != "uml":
            _fail(_unsupported_kind_message(token if token != "uml" else block.start_kind))
    lines = [
        (block.source_line + offset, text)
        for offset, text in enumerate(_blank_comments(block.text.splitlines()))
    ]
    _refuse_includes(lines)
    kind = _detect_kind(lines)
    diagram = Diagram(block.index, kind, block.source_line, direction="LR" if kind == "sequence" else "TD")
    if kind == "sequence":
        _parse_sequence(diagram, lines)
    else:
        _parse_class(diagram, lines)
    if not diagram.nodes:
        _fail("mixed or unknown kind")
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


def analyze(diagram: Diagram) -> dict[str, Any]:
    containers = [node for node in diagram.nodes if node.container or node.children]
    leaves = [node for node in diagram.nodes if not (node.container or node.children)]
    shapes: dict[str, int] = {}
    for node in diagram.nodes:
        family = "container" if node.shape == "container" else node.shape
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
    candidates = ["sequence"] if diagram.kind == "sequence" else ["UML class"]
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


def _block_summary(block: SourceBlock, selected: list[Diagram]) -> str:
    """One header entry. A block that was not selected is parsed only to
    describe it, so a failure there is listed instead of ending the run."""
    diagram = next((item for item in selected if item.index == block.index), None)
    if diagram is None:
        try:
            diagram = parse_block(block)
        except ExtractError as error:
            return f"[{block.index}] unparsed: {_escape_markdown(str(error))}"
    return f"[{diagram.index}] {diagram.kind} ({len(diagram.nodes)}n/{len(diagram.edges)}e)"


def digest(
    path: Path,
    blocks: list[SourceBlock],
    selected: list[Diagram],
    max_rows: int,
) -> str:
    output = [f"# PlantUML IR — {path.name}", ""]
    output.append(
        f"{len(blocks)} diagram(s): "
        + ", ".join(_block_summary(block, selected) for block in blocks)
    )
    for diagram in selected:
        info = analyze(diagram)
        output.extend(
            [
                "",
                f"## Diagram {diagram.index} — {diagram.kind}",
                "",
                f"- source layout: none (PlantUML is layout-free); direction: {diagram.direction}",
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
        if diagram.title:
            output.append(f"- title: {_escape_markdown(diagram.title)}")
        if diagram.discarded["skin"] or diagram.discarded["includes"]:
            parts = []
            if diagram.discarded["skin"]:
                parts.append(f"{diagram.discarded['skin']} skinparam")
            if diagram.discarded["includes"]:
                parts.append(f"{diagram.discarded['includes']} includes")
            output.append(f"- discarded: {', '.join(parts)}")
        if diagram.fragments:
            fragments = ", ".join(
                f"{item['kind']}({_escape_markdown(item['label'] or 'unlabeled')})"
                for item in diagram.fragments
            )
            output.append(f"- fragments: {fragments}")
        if diagram.activations:
            output.append(
                "- activations: "
                + ", ".join(
                    f"{_escape_markdown(item['participant'])}:{item['action']}"
                    for item in diagram.activations[:12]
                )
            )
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
            if edge.cardinality:
                marks.append(edge.cardinality)
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


def to_json(path: Path, blocks: list[SourceBlock], selected: list[Diagram]) -> str:
    return json.dumps(
        {
            "source": str(path),
            "diagrams_total": len(blocks),
            "diagrams": [
                {
                    "index": diagram.index,
                    "kind": diagram.kind,
                    "source_line": diagram.source_line,
                    "direction": diagram.direction,
                    "title": diagram.title,
                    "analysis": analyze(diagram),
                    "discarded": diagram.discarded,
                    "fragments": diagram.fragments,
                    "activations": diagram.activations,
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


def select_blocks(blocks: list[SourceBlock], selector: str | None) -> list[SourceBlock]:
    """Pick blocks before parsing, so a bad block fails only when selected."""
    if selector is None:
        return blocks[:1]
    if selector == "all":
        return blocks
    if selector.isdigit():
        index = int(selector)
        selected = [block for block in blocks if block.index == index]
        if not selected:
            _fail(f"no diagram with index {index} (have 0..{len(blocks) - 1})")
        return selected
    _fail("--diagram must be an index or 'all'")


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except ExtractError as error:
        print(f"plantuml_extract: {error}", file=sys.stderr)
        raise SystemExit(2) from None


def _run(argv: list[str] | None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("file", help=".puml, .plantuml, .pu, or Markdown with plantuml fences")
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
    selected = [parse_block(block) for block in select_blocks(blocks, args.diagram)]
    output = (
        to_json(path, blocks, selected)
        if args.json
        else digest(path, blocks, selected, args.max_rows)
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
