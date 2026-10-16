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
# One whole arrow, matched at a candidate position. Sequence arrows are a
# dash run with an optional `[#color]` style and `<`/`<<` or `>`/`>>` heads,
# plus an `x` (lost) or `o` (circle) decoration after the head.
SEQ_ARROW_AT = re.compile(
    r"(?P<left><<?)?(?P<body1>-+)(?P<style>\[[^\[\]]*\])?(?P<body2>-*)(?P<right>>>?)?"
    r"(?P<decoration>[ox](?=[\s:]|$))?"
)
# Class arrows are a `-` or `.` run with an optional `[style]` or direction
# hint (`-up->`) and a head on either end.
CLASS_ARROW_AT = re.compile(
    r"(?P<left><\|(?=[-.])|[<*o#x}+^](?=[-.]))?"
    r"(?P<body1>(?P<char>[-.])(?P=char)*)"
    r"(?P<style>\[[^\[\]]*\]|(?:up|down|left|right|do|le|ri|u|d|l|r)(?=[-.]))?"
    r"(?P<body2>(?P=char)*)"
    r"(?P<right>\|>|[>*o#x{+^])?"
)
CLASS_HEADS = {
    "<|": "inheritance",
    "|>": "inheritance",
    "^": "inheritance",
    "*": "composition",
    "o": "aggregation",
    "<": "plain",
    ">": "plain",
}
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
SKIN_COMMANDS = (
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
    "order",
    "left to right direction",
    "top to bottom direction",
)
# A styling command is a whole word followed by whitespace, `{`, or the end of
# the statement, so `ShowService -> Client` and `show(): void` stay content.
SKIN_RE = re.compile(
    r"^(?:"
    + "|".join(re.escape(command).replace(r"\ ", r"\s+") for command in SKIN_COMMANDS)
    + r")(?=\s|\{|$)",
    re.I,
)
# Multi-line text blocks that end with a matching `end...` line.
TEXT_BLOCK_RE = re.compile(
    r"^(?:(?:left|right|center)\s+)?(header|footer|legend)(?:\s+(?:left|right|center|top|bottom))*\s*$",
    re.I,
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
    # `cardinality` is "<source> .. <target>" with `-` for an end that has
    # none, so `A "1" --> B` and `A --> B "1"` never read the same.
    cardinality: str = ""
    source_cardinality: str = ""
    target_cardinality: str = ""
    # Which end a diamond relationship can refer to when the arrow also has
    # a plain head (`*-->`, `o-->`). Empty when the diamond stands alone.
    navigable: str = ""
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
    # One entry per note: text, position (left/right/over/across/top/bottom),
    # every participant or class it covers, and where it sits in the message
    # sequence (`after_message`; `message` when it is attached to a message).
    note_details: list[dict[str, Any]] = field(default_factory=list)
    discarded: dict[str, int] = field(
        default_factory=lambda: {"skin": 0, "includes": 0}
    )
    _nodes_by_id: dict[str, Node] = field(default_factory=dict, init=False, repr=False)
    # Per statement line: "edge", "declaration", or "statement", as kind
    # detection read it and as the parser used it. Not part of the IR; the
    # verifier compares the two so they cannot drift apart.
    detected_roles: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    parsed_roles: dict[int, str] = field(default_factory=dict, init=False, repr=False)
    _aliases: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _bare_names: dict[str, list[str]] = field(default_factory=dict, init=False, repr=False)

    @property
    def node_map(self) -> dict[str, Node]:
        return self._nodes_by_id

    def resolve(self, token: str, scope: list[str] | None = None) -> str:
        """Resolve a name exactly (PlantUML names are case-sensitive).

        Class names declared inside a package get a package-qualified id. A
        bare reference resolves against the enclosing *scope* first, then to
        the one class with that bare name; an ambiguous bare name fails.
        """
        key = token.strip()
        if key in self._nodes_by_id:
            return key
        if key in self._aliases:
            return self._aliases[key]
        for package in reversed(scope or []):
            qualified = f"{package}.{key}"
            if qualified in self._nodes_by_id:
                return qualified
        matches = self._bare_names.get(key, [])
        if len(matches) > 1:
            _fail(
                f"ambiguous class name `{key}` (declared in several packages: "
                f"{', '.join(matches)}); qualify it"
            )
        if matches:
            return matches[0]
        return key

    def alias(self, alias: str, node_id: str) -> None:
        self._aliases.setdefault(alias, node_id)

    def bare_name(self, name: str, node_id: str) -> None:
        ids = self._bare_names.setdefault(name, [])
        if node_id not in ids:
            ids.append(node_id)

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
        source_cardinality: str = "",
        target_cardinality: str = "",
        navigable: str = "",
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
            cardinality=(
                f"{source_cardinality or '-'} .. {target_cardinality or '-'}"
                if source_cardinality or target_cardinality
                else ""
            ),
            source_cardinality=source_cardinality,
            target_cardinality=target_cardinality,
            navigable=navigable,
            order=len(self.edges) + 1,
        )
        self.edges.append(edge)
        return edge

    def add_activation(self, participant: str, action: str, after_message: int | None = None) -> None:
        """Record an activation change on the message timeline.

        ``after_message`` is the order of the last message before the bar
        starts or ends (0 = before the first message).
        """
        self.activations.append(
            {
                "participant": participant,
                "action": action,
                "order": len(self.activations) + 1,
                "after_message": len(self.edges) if after_message is None else after_message,
            }
        )


@dataclass
class SourceBlock:
    index: int
    text: str
    source_line: int
    start_kind: str = "uml"
    # A failure found while splitting the file (an unclosed block comment).
    # It belongs to this block alone and is raised only when it is selected.
    error: str | None = None


# Markup that PlantUML Creole or HTML would interpret. Only these tags are
# stripped, so `Box<T>`, `List<Order>`, and `Map<K, V>` keep their type
# parameters. Single-letter tags match lowercase only so a type parameter
# such as `<B>` or `<A, B>` stays text.
_MARKUP_TAGS = (
    "abbr|applet|audio|back|base|big|blockquote|body|br|button|canvas|center|"
    "code|color|del|div|em|embed|font|form|frame|frameset|h[1-6]|head|hr|html|"
    "iframe|img|input|ins|kbd|label|li|link|mark|math|meta|noscript|object|ol|"
    "option|plain|pre|script|select|size|small|source|span|strike|strong|style|"
    "sub|sup|svg|table|td|template|textarea|th|title|tr|tt|ul|video|wbr|xmp"
)
# Active-content tags are always stripped. Formatting tags are stripped only
# when they are not doubled, so `<<b>>` inside a quoted name stays text.
_ACTIVE_TAGS = (
    "applet|audio|base|button|canvas|embed|form|frame|frameset|iframe|img|input|"
    "link|math|meta|noscript|object|option|script|select|source|style|svg|"
    "template|textarea|video|xmp"
)
MARKUP_TAG_RE = re.compile(
    r"</?(?i:" + _ACTIVE_TAGS + r")(?=[\s/>:=])[^<>]*>"
    r"|(?<!<)</?(?:(?i:" + _MARKUP_TAGS + r")|[abipqsuw])(?=[\s/>:=])[^<>]*>(?!>)"
    r"|<[$&][^<>]*>"
)


def clean_label(value: str) -> str:
    """Flatten PlantUML / Creole / HTML label markup without interpreting it.

    Entities are decoded before tags are stripped, and stripping repeats until
    nothing changes, so `&lt;script&gt;` or a split tag cannot reassemble a
    tag in the output. Angle-bracket text that is not markup is kept.
    """
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    text = text.replace("\\n", "\n")
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    previous = None
    while previous != text:
        previous = text
        text = MARKUP_TAG_RE.sub("", text)
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
        # `utf-8-sig` drops a leading byte-order mark, so `@startuml` on the
        # first line is still found.
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail(f"{path.name}: source is not valid UTF-8 text")


def _split_uml_regions(
    text: str, base_line: int
) -> list[tuple[int, str, str, str | None]]:
    """Return (start_line, body, start_kind, error) for each @start/@end region.

    Block comments are tracked inside a region, so an ``@enduml`` line inside
    ``/' ... '/`` does not close the diagram early. A block must close with
    its own marker (`@startuml` with `@enduml`). An unclosed comment, a
    missing or mismatched closing marker, or a nested `@start` is recorded as
    that region's error instead of stopping the whole file, so other blocks
    stay selectable and the error is raised only when the block is selected.
    """
    regions: list[tuple[int, str, str, str | None]] = []
    lines = text.splitlines()
    start: int | None = None
    kind = "uml"
    body: list[str] = []
    error: str | None = None
    comment_start: int | None = None
    for offset, raw in enumerate(lines):
        stripped = raw.strip()
        opened = START_RE.match(stripped)
        closed = END_RE.match(stripped)
        line_number = base_line + offset
        if start is None:
            if opened:
                start = line_number + 1
                kind = opened.group(1).casefold()
                body = []
                error = None
            continue
        if comment_start is not None:
            if not _strip_block_comments(raw, True)[1]:
                comment_start = None
            body.append(raw)
            continue
        if not stripped.startswith("'") and _strip_block_comments(raw, False)[1]:
            comment_start = base_line + offset
            body.append(raw)
            continue
        if closed:
            closing = closed.group(1).casefold()
            if closing != kind and error is None:
                error = (
                    f"`@end{closed.group(1)}` at line {line_number} does not close "
                    f"`@start{kind}` at line {start - 1}"
                )
            regions.append((start, "\n".join(body), kind, error))
            start = None
            body = []
            continue
        if opened and error is None:
            error = f"nested @start{opened.group(1).casefold()} at line {line_number}"
        body.append(raw)
    if start is not None:
        if comment_start is not None:
            error = f"unterminated block comment at line {comment_start}"
        elif error is None:
            error = f"missing @end{kind} for @start{kind} at line {start - 1}"
        regions.append((start, "\n".join(body), kind, error))
    return regions


def load_blocks(path: Path) -> list[SourceBlock]:
    suffix = path.suffix.casefold()
    if suffix not in PLANTUML_SUFFIXES | MARKDOWN_SUFFIXES:
        _fail(f"{path.name}: not a PlantUML file")
    source = _read_bounded(path)
    collected: list[SourceBlock] = []

    def add(start_line: int, text: str, start_kind: str, error: str | None = None) -> None:
        collected.append(SourceBlock(len(collected), text, start_line, start_kind, error))

    if suffix in PLANTUML_SUFFIXES:
        regions = _split_uml_regions(source, 1)
        if not regions:
            _fail(f"{path.name}: no @startuml block found")
        for start_line, text, kind, error in regions:
            add(start_line, text, kind, error)
        return collected

    # Every fence is tracked, as the Mermaid importer does, so a plantuml
    # fence quoted inside another fence (a Markdown example) is not imported.
    lines = source.splitlines()
    start: int | None = None
    fence = ""
    capture = False
    content: list[str] = []
    for line_number, line in enumerate(lines, 1):
        if start is None:
            match = re.match(r"^\s*(`{3,}|~{3,})(.*)$", line)
            if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
                is_plantuml = bool(FENCE_OPEN_RE.match(line))
                if is_plantuml or re.match(r"^ {0,3}[`~]", line):
                    start = line_number + 1
                    fence = match.group(1)
                    capture = is_plantuml
                    content = []
            continue
        if re.match(rf"^\s*{re.escape(fence[0])}{{{len(fence)},}}\s*$", line) and (
            capture or re.match(r"^ {0,3}[`~]", line)
        ):
            if capture:
                block_text = "\n".join(content)
                regions = _split_uml_regions(block_text, start)
                if regions:
                    for start_line, text, kind, error in regions:
                        add(start_line, text, kind, error)
                else:
                    add(start, block_text, "uml")
            start = None
            fence = ""
            content = []
        elif capture:
            content.append(line)
    if start is not None and capture:
        # The open fence is its own block's error, so earlier blocks stay
        # selectable; it is raised only when this block is selected.
        add(start, "\n".join(content), "uml", f"unterminated plantuml fence starting at line {start - 1}")
    if not collected:
        _fail(f"{path.name}: no fenced plantuml block found")
    return collected


def _strip_block_comments(raw: str, in_block: bool) -> tuple[str, bool]:
    """Remove ``/' ... '/`` spans from one line, wherever they start.

    Returns the visible text and whether a block comment is still open at
    the end of the line, so a comment opened mid-line hides what follows.
    """
    visible: list[str] = []
    index = 0
    while index <= len(raw):
        if in_block:
            close = raw.find("'/", index)
            if close == -1:
                break
            index = close + 2
            in_block = False
            continue
        opening = raw.find("/'", index)
        if opening == -1:
            visible.append(raw[index:])
            break
        visible.append(raw[index:opening])
        index = opening + 2
        in_block = True
    return "".join(visible), in_block


def _blank_comments(lines: list[str]) -> list[str]:
    prepared: list[str] = []
    in_block = False
    for raw in lines:
        if not in_block and raw.strip().startswith("'"):
            prepared.append("")
            continue
        visible, in_block = _strip_block_comments(raw, in_block)
        prepared.append(visible.rstrip())
    if in_block:
        _fail("unterminated block comment")
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
    if re.match(r"^state\b", text, re.I) and not _scan_arrow(text, "sequence"):
        return "state"
    match = re.match(r"^(component|usecase)\b", text, re.I)
    if match and not _scan_arrow(text, "sequence"):
        return match.group(1).casefold()
    return None


def _statement_lines(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return statement text, skipping note, legend, styling, and class bodies.

    Body lines are content for the parser, so they must not decide the kind:
    a note that mentions ``class Foo`` or a member named ``participant`` is
    still text inside a block.
    """
    statements: list[tuple[int, str]] = []
    skin = _SkinBlocks()
    scratch = Diagram(0, "", 0)
    in_note = False
    in_class_body = False
    for _line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if in_note:
            if text.casefold() in {"end note", "endnote"}:
                in_note = False
            continue
        if in_class_body:
            if text == "}":
                in_class_body = False
            continue
        if skin.consume(scratch, text, _line_number):
            continue
        statements.append((_line_number, text))
        if _edge_split(text, "sequence") or _edge_split(text, "class"):
            continue  # an edge never opens a note or class body
        if re.match(r"^note\b", text, re.I) and not _note_has_inline_body(text):
            in_note = True
        elif CLASS_DECL_RE.match(text) and text.endswith("{"):
            in_class_body = True
    return statements


def _note_has_inline_body(text: str) -> bool:
    """True for a one-line note (`note over A : text`), False for a block opener."""
    in_quote: str | None = None
    for character in text:
        if in_quote:
            if character == in_quote:
                in_quote = None
        elif character == '"':
            in_quote = character
        elif character == ":":
            return True
    return False


def _edge_split(text: str, kind: str) -> tuple[str, re.Match[str], str] | None:
    """The one edge classifier, shared by kind detection and both parsers.

    A line is an edge when it has an arrow and the text before the arrow is
    one reference (a name, a quoted name, an inline `as` declaration for a
    sequence, plus a cardinality for a class). This runs before any
    declaration check, so `class -> B : hi` is a message from a participant
    named `class`. Problems on the far side of the arrow are reported by the
    edge parser as a malformed edge.
    """
    split = _scan_arrow(text, kind)
    if not split:
        return None
    left = split[0]
    if kind == "sequence":
        if left in {"[", "?"}:
            return split  # a boundary message; the parser names it
        return split if _endpoint_code(left, allow_as=True) else None
    left_name, _cardinality = _split_cardinality(left, before_arrow=True)
    return split if _endpoint_code(left_name) else None


def _detect_kind(lines: list[tuple[int, str]]) -> tuple[str, dict[int, str]]:
    """Return the diagram kind and the role of each statement line for it.

    Arrow and declaration forms decide the kind. A message label does not:
    a structural class relationship wins over a later plain arrow, and an
    unlabeled ``->`` is still a sequence message.
    """
    has_class = False
    has_seq_decl = False
    has_class_rel = False
    has_seq_arrow = False
    unsupported: str | None = None
    readings: list[tuple[int, bool, bool, bool, bool]] = []
    for line_number, text in _statement_lines(lines):
        seq_split = _edge_split(text, "sequence")
        class_split = _edge_split(text, "class")
        is_class_decl = is_seq_decl = False
        if seq_split or class_split:
            # Arrow first: an edge line is never a declaration.
            if class_split and _is_structural_link(class_split[1]):
                has_class_rel = True
            if seq_split:
                has_seq_arrow = True
        else:
            is_class_decl = bool(CLASS_DECL_RE.match(text))
            is_seq_decl = bool(SEQ_DECL_RE.match(text))
            has_class = has_class or is_class_decl
            has_seq_decl = has_seq_decl or is_seq_decl
            hint = _unsupported_body_kind(text)
            if hint and unsupported is None:
                unsupported = hint
        readings.append((line_number, bool(seq_split), bool(class_split), is_seq_decl, is_class_decl))
    if has_class and has_seq_decl:
        _fail("mixed or unknown kind")
    if unsupported and not has_class and not has_seq_decl:
        _fail(_unsupported_kind_message(unsupported))
    # A structural relationship is class even when a later plain arrow is labeled.
    if has_class or (has_class_rel and not has_seq_decl):
        kind = "class"
    elif has_seq_decl or has_seq_arrow:
        kind = "sequence"
    elif unsupported:
        _fail(_unsupported_kind_message(unsupported))
    else:
        _fail("mixed or unknown kind")
    roles: dict[int, str] = {}
    for line_number, seq_edge, class_edge, seq_decl, class_decl in readings:
        edge = seq_edge if kind == "sequence" else class_edge
        declaration = seq_decl if kind == "sequence" else class_decl
        roles[line_number] = "edge" if edge else "declaration" if declaration else "statement"
    return kind, roles


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


COLOR_TOKEN_RE = re.compile(r"^#{1,2}(?:\[[^\]]*\])?[\w:;.#/\\|-]*$")
# A participant or class reference: one quoted string, or one bare name with
# no whitespace, quotes, arrow heads, colons, brackets, or commas.
_BARE_NAME = r'[^\s"\'<>:\[\]{}|,#][^\s"\'<>:\[\]{}|,]*'
ENDPOINT_RE = re.compile(rf'^(?:"[^"]+"|{_BARE_NAME})$')
# An arrow end may declare a participant inline: `"Long Name" as L` or
# `L as "Long Name"` (code L, display "Long Name").
INLINE_DECLARATION_RE = re.compile(
    rf'^(?:"(?P<long>[^"]+)"\s*as\s+(?P<long_code>{_BARE_NAME})'
    rf'|(?P<code>{_BARE_NAME})\s+as\s*"(?P<code_long>[^"]+)")$',
    re.I,
)


def _endpoint_code(token: str, *, allow_as: bool = False) -> tuple[str, str] | None:
    """Return (code, display) for a reference, or None when it is not one name.

    PlantUML looks participants and classes up by code: a bare name, or the
    text inside quotes, exactly as written. Markup cleanup applies to the
    display label only, so `"**A**"` is its own participant, not `A`.
    """
    text = token.strip()
    if allow_as:
        inline = INLINE_DECLARATION_RE.match(text)
        if inline:
            if inline.group("long") is not None:
                return inline.group("long_code"), inline.group("long")
            return inline.group("code"), inline.group("code_long")
    if not ENDPOINT_RE.match(text):
        return None
    if text.startswith('"'):
        return text[1:-1], text[1:-1]
    return text, text
NOTE_HEAD_RE = re.compile(
    r"^note\s+(?P<position>left|right|over|across|top|bottom)\b(?P<rest>.*)$", re.I
)


def _parse_note(text: str) -> tuple[str, str, str | None] | None:
    """Return (position, targets, body) for a note; body is None for a block.

    The body starts at the first colon outside double quotes, so a quoted
    target such as `"A:B"` stays whole.
    """
    head = NOTE_HEAD_RE.match(text)
    if not head:
        return None
    rest = head.group("rest")
    in_quote = False
    for index, character in enumerate(rest):
        if character == '"':
            in_quote = not in_quote
        elif character == ":" and not in_quote:
            return head.group("position").casefold(), rest[:index].strip(), rest[index + 1 :].strip()
    return head.group("position").casefold(), rest.strip(), None


def _strip_trailing_colors(text: str) -> str:
    tokens = text.split()
    while tokens and COLOR_TOKEN_RE.match(tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


STEREOTYPE_AT = re.compile(r"<<\s*(?:\(\s*[^)]*\)\s*)?(?P<name>[^<>]*?)\s*>>")
DECLARED_NAME_AT = re.compile(r'"(?P<quoted>[^"]*)"|(?P<bare>[^\s"<>{}#]+)')


def _parse_declaration_tail(
    rest: str,
    line_number: int,
    *,
    allow_order: bool = False,
    allow_generic: bool = False,
) -> tuple[str, str, str, list[str]]:
    """The one declaration tokenizer: participants, classifiers, and packages.

    Reads, in order: a name (bare or quoted), a generic for classifiers, an
    optional `as` alias (one bare or quoted token), then styling tokens:
    `#color` / `#line:...` / `##[style]color`, `<<stereotype>>`, `order N`
    where allowed, and a final `{` (or an inline `{ ... }` body). Anything
    else is a malformed statement, so styling never becomes part of an id.

    Returns (node_id, label, stereotype, body) where body is `["{"]` for an
    opening brace, `["{}", members...]` for an inline body, or `[]`.
    """
    def malformed() -> NoReturn:
        _fail(f"malformed statement at line {line_number}")

    text = rest.strip()
    name = DECLARED_NAME_AT.match(text)
    if not name or not (name.group("quoted") or name.group("bare")):
        malformed()
    quoted_display = name.group("quoted") is not None
    display = name.group("quoted") if quoted_display else name.group("bare")
    position = name.end()
    generic = ""
    generic_at = len(text) - len(text[position:].lstrip())
    if allow_generic and not quoted_display and text.startswith("<", generic_at) and not text.startswith("<<", generic_at):
        generic, remainder = _split_generic(text[generic_at:], line_number)
        position = len(text) - len(remainder)
    node_id, label = display, display
    alias_match = re.compile(r"\s*as\s+", re.I).match(text, position)
    if alias_match:
        alias = DECLARED_NAME_AT.match(text, alias_match.end())
        if not alias or not (alias.group("quoted") or alias.group("bare")):
            malformed()
        if alias.group("quoted") is not None and not quoted_display:
            node_id, label = display, alias.group("quoted")  # `L as "Long Name"`
        else:
            node_id = alias.group("quoted") if alias.group("quoted") is not None else alias.group("bare")
        position = alias.end()
    stereotypes: list[str] = []
    body: list[str] = []
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            break
        stereo = STEREOTYPE_AT.match(text, position)
        if stereo:
            stereotypes.append(clean_label(stereo.group("name")))
            position = stereo.end()
            continue
        if text[position] == "{":
            tail = text[position:]
            if tail == "{":
                body = ["{"]
            elif tail.endswith("}") and tail.count("{") == 1 and tail.count("}") == 1:
                inner = tail[1:-1].strip()
                body = ["{}"] + ([inner] if inner else [])
            else:
                malformed()
            break
        token = re.compile(r"[^\s{]+").match(text, position)
        if token and COLOR_TOKEN_RE.match(token.group(0)):
            position = token.end()
            continue
        order = re.compile(r"order\s+-?\d+(?=\s|\{|$)", re.I).match(text, position)
        if allow_order and order:
            position = order.end()
            continue
        malformed()
    stereotype = ", ".join(item for item in stereotypes if item)
    # The generic is kept verbatim: markup cleanup would read `<T>` as a tag.
    return node_id, (clean_label(label) or node_id) + generic, stereotype, body


def _split_generic(text: str, line_number: int) -> tuple[str, str]:
    """Split a balanced ``<...>`` type parameter list from the front of *text*."""
    depth = 0
    for index, character in enumerate(text):
        if character == "<":
            depth += 1
        elif character == ">":
            depth -= 1
            if depth == 0:
                return text[: index + 1], text[index + 1 :].strip()
    _fail(f"malformed statement at line {line_number}")


def _parse_classifier_header(
    text: str, line_number: int = 0
) -> tuple[str, str, str, str, bool, list[str]] | None:
    match = re.match(
        r"^(abstract\s+class|class|interface|enum)\s+(.+)$",
        text,
        re.I,
    )
    if not match:
        return None
    kind = re.sub(r"\s+", " ", match.group(1).casefold())
    node_id, label, stereotype, body = _parse_declaration_tail(
        match.group(2).strip(), line_number, allow_generic=True
    )
    opens = body == ["{"]
    members = body[1:] if body[:1] == ["{}"] else []
    return node_id, label, CLASSIFIER_KINDS[kind], stereotype, opens, members


def _parse_participant(text: str, line_number: int = 0) -> tuple[str, str, str, str] | None:
    match = re.match(
        r"^(participant|actor|boundary|control|entity|database|collections|queue)\s+(.+)$",
        text,
        re.I,
    )
    if not match:
        return None
    kind = match.group(1).casefold()
    node_id, label, stereotype, body = _parse_declaration_tail(
        match.group(2).strip(), line_number, allow_order=True
    )
    if body:
        _fail(f"malformed statement at line {line_number}")
    return node_id, label, LIFELINE_KINDS[kind], stereotype


def _scan_arrow(text: str, kind: str) -> tuple[str, re.Match[str], str] | None:
    """Split *text* around its first whole arrow outside double quotes.

    The arrow is matched in full (``--->``, ``-[#red]->``, ``-up->``), so no
    part of it is left behind on either side to become a node name. Returns
    (left, match, right) or None when the text has no arrow.
    """
    pattern = SEQ_ARROW_AT if kind == "sequence" else CLASS_ARROW_AT
    in_quote = False
    for index, character in enumerate(text):
        if character == '"':
            in_quote = not in_quote
            continue
        if in_quote or character not in "<-.*o#x}+^":
            continue
        match = pattern.match(text, index)
        if not match:
            continue
        left_head, right_head = match.group("left"), match.group("right")
        before = text[index - 1] if index else " "
        if kind == "sequence":
            if not (left_head or right_head):
                continue
        else:
            if left_head in {"o", "x"} and not (before.isspace() or before == '"'):
                continue  # the `o` ends a name such as `Foo--Bar`
            body = len(match.group("body1")) + len(match.group("body2"))
            if not (left_head or right_head) and (
                body < 2 or not (before.isspace() or before == '"')
            ):
                continue  # a headless link needs `--` or `..` set apart from names
        return text[:index].strip(), match, text[match.end() :].strip()
    return None


def _is_structural_link(match: re.Match[str]) -> bool:
    """True for an inheritance, composition, or aggregation head, which only
    a class diagram draws (a plain `-->` is shared with sequence messages)."""
    heads = {match.group("left") or "", match.group("right") or ""}
    return bool(heads & {"<|", "|>", "^", "*", "o"})


def _partition_unquoted(text: str, separator: str) -> tuple[str, str]:
    in_quote = False
    for index, character in enumerate(text):
        if character == '"':
            in_quote = not in_quote
        elif character == separator and not in_quote:
            return text[:index], text[index + 1 :]
    return text, ""


def _split_cardinality(side: str, *, before_arrow: bool) -> tuple[str, str]:
    """Split a class name from the quoted cardinality written next to the arrow.

    PlantUML puts a cardinality between the class and the arrow
    (`A "1" --> "many" B`), so it is the last quoted string before the arrow
    and the first one after it. Reading only that position keeps a quoted
    class name such as `"My A" "1"` a name.
    """
    text = side.strip()
    if before_arrow:
        trailing = re.match(r'^(.+?)\s+"([^"]*)"$', text)
        if trailing:
            return trailing.group(1).strip(), trailing.group(2)
        return text, ""
    leading = re.match(r'^"([^"]*)"\s+(.+)$', text)
    if leading:
        return leading.group(2).strip(), leading.group(1)
    return text, ""


def _class_relationship(
    match: re.Match[str], line_number: int
) -> tuple[str, str, bool, bool, bool, bool, str]:
    """Return (arrowhead, style, reverse, bidirectional, undirected, hidden, navigable).

    The source of an edge is the child for inheritance, the whole (diamond
    side) for composition and aggregation, and the tail for an association.
    ``navigable`` is ``source`` or ``target`` in pre-swap coordinates when a
    diamond shares the arrow with a plain head, and empty when it does not.
    """
    style_hint = (match.group("style") or "").casefold()
    dashed = match.group("char") == "." or "dashed" in style_hint or "dotted" in style_hint
    style = "dashed" if dashed else "solid"
    hidden = "hidden" in style_hint
    left = CLASS_HEADS.get(match.group("left") or "", "" if not match.group("left") else None)
    right = CLASS_HEADS.get(match.group("right") or "", "" if not match.group("right") else None)
    if left is None or right is None:
        _fail(f"unsupported relationship arrow `{match.group(0)}` at line {line_number}")
    if not left and not right:
        return "association", style, False, False, True, hidden, ""
    if left == "plain" and right == "plain":
        return "association", style, False, True, False, hidden, ""
    if left and right:
        # The diamond keeps ownership; the plain head says which end is navigable.
        if left in {"composition", "aggregation"} and right == "plain":
            return left, style, False, False, False, hidden, "target"
        if right in {"composition", "aggregation"} and left == "plain":
            return right, style, True, False, False, hidden, "source"
        _fail(f"unsupported relationship arrow `{match.group(0)}` at line {line_number}")
    head = left or right
    if head == "plain":
        return "association", style, bool(left), False, False, hidden, ""
    if head == "inheritance":
        return "inheritance", style, bool(left), False, False, hidden, ""
    # Composition and aggregation: the diamond side is the source.
    return head, style, bool(right), False, False, hidden, ""


def _sequence_arrow(match: re.Match[str]) -> tuple[str, str, bool, bool]:
    """Return (style, arrowhead, reverse, bidirectional) for a sequence arrow."""
    left, right = match.group("left"), match.group("right")
    style_hint = (match.group("style") or "").casefold()
    dashes = len(match.group("body1")) + len(match.group("body2"))
    dashed = dashes >= 2 or "dashed" in style_hint or "dotted" in style_hint
    decoration = match.group("decoration")
    if decoration == "x":
        arrowhead = "lost"
    elif decoration == "o":
        arrowhead = "circle"
    elif left == "<<" or right == ">>":
        arrowhead = "async"
    else:
        arrowhead = "arrow"
    return ("dashed" if dashed else "solid"), arrowhead, bool(left and not right), bool(left and right)


ACTIVATION_SHORTCUT_RE = re.compile(
    r"^(?P<name>.+?)\s*(?P<mark>\+\+--|--\+\+|\+\+|--|\*\*|!!)?\s*"
    r"(?P<color>#{1,2}[\w:;.#-]*)?$"
)
SHORTCUT_ACTIONS = {
    "++": ("activate",),
    "--": ("deactivate",),
    "--++": ("deactivate", "activate"),
    "++--": ("activate", "deactivate"),
    "**": ("create",),
    "!!": ("destroy",),
}


def _activation_shortcut(text: str) -> tuple[str, tuple[str, ...]]:
    """Split ``B ++ #gold`` into the receiver name and its shortcut actions.

    PlantUML writes these after the second participant only. ``++``, ``**``,
    and ``!!`` act on the message receiver; ``--`` deactivates the sender.
    """
    match = ACTIVATION_SHORTCUT_RE.match(text.strip())
    if not match:
        return text.strip(), ()
    return match.group("name").strip(), SHORTCUT_ACTIONS.get(match.group("mark") or "", ())


def _is_skin(text: str) -> bool:
    if re.match(r"^(?:left|right|center)\s+(?:header|footer)\b", text, re.I):
        return True
    match = SKIN_RE.match(text)
    if not match:
        return False
    # `Scale -> Client : x` or `Show <|-- Base` uses the word as a name.
    split = _edge_split(text, "sequence") or _edge_split(text, "class")
    if split:
        left, _cardinality = _split_cardinality(split[0], before_arrow=True)
        if left.strip().casefold() == match.group(0).casefold():
            return False
    return True


class _SkinBlocks:
    """Consume multi-line styling: `skinparam x {` ... `}` and
    `legend` / `header` / `footer` ... `endlegend` / `endheader` / `endfooter`."""

    def __init__(self) -> None:
        self.brace_depth = 0
        self.text_end: str | None = None
        self.start_line = 0

    @property
    def open(self) -> bool:
        return self.brace_depth > 0 or self.text_end is not None

    def consume(self, diagram: Diagram, text: str, line_number: int) -> bool:
        """Return True when *text* is styling that the caller must skip."""
        if self.text_end is not None:
            if re.match(rf"^end\s*{self.text_end}$", text, re.I):
                self.text_end = None
            return True
        if self.brace_depth:
            if text.endswith("{"):
                self.brace_depth += 1
            elif text == "}":
                self.brace_depth -= 1
            return True
        if not _is_skin(text):
            return False
        diagram.discarded["skin"] += 1
        self.start_line = line_number
        block = TEXT_BLOCK_RE.match(text)
        if block:
            self.text_end = block.group(1).casefold()
        elif text.endswith("{"):
            self.brace_depth = 1
        return True

    def check_closed(self) -> None:
        if self.open:
            _fail(f"unterminated styling block at line {self.start_line}")


def _split_unquoted(text: str, separator: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    for character in text:
        if character == '"':
            in_quote = not in_quote
        if character == separator and not in_quote:
            parts.append("".join(current))
            current = []
            continue
        current.append(character)
    parts.append("".join(current))
    return parts


def _record_note(diagram: Diagram, placement: dict[str, Any], body: str) -> None:
    """Store a note's text plus where it sits. A note on exactly one
    participant or class is also listed in that node's fields."""
    diagram.notes.append(body)
    diagram.note_details.append({"text": body, **placement})
    if len(placement["participants"]) == 1:
        node = diagram.node_map.get(placement["participants"][0])
        if node is not None:
            node.fields.append(body)


def _parse_sequence(diagram: Diagram, lines: list[tuple[int, str]]) -> None:
    fragment_stack: list[dict[str, Any]] = []
    open_note: dict[str, Any] | None = None
    note_lines: list[str] = []
    note_start = 0
    skin = _SkinBlocks()

    def next_message() -> int:
        return len(diagram.edges) + 1

    def close_region(entry: dict[str, Any]) -> None:
        region = entry["regions"][-1]
        region["last_message"] = len(diagram.edges)
        if region["last_message"] < region["first_message"]:
            region["first_message"] = region["last_message"] = None

    def close_note() -> None:
        nonlocal open_note, note_lines
        body = clean_label("\n".join(note_lines))
        if body and open_note is not None:
            _record_note(diagram, open_note, body)
        open_note = None
        note_lines = []

    def note_participants(raw: str, line_number: int) -> list[str]:
        """Resolve every participant a note covers (`note over A, B`)."""
        text = _strip_trailing_colors(raw)
        if not text:
            return []
        resolved_ids: list[str] = []
        for token in _split_unquoted(text, ","):
            node_id = lifeline(token, f"malformed statement at line {line_number}")
            if node_id not in resolved_ids:
                resolved_ids.append(node_id)
        return resolved_ids

    def add_message(split: tuple[str, re.Match[str], str], line_number: int) -> None:
        left, arrow, right = split
        right, message = _partition_unquoted(right, ":")
        right, actions = _activation_shortcut(right)
        if left in {"[", "?"} or right in {"]", "?"}:
            _fail(f"unsupported sequence construct: boundary message at line {line_number}")
        # Both ends must be one whole name (or an inline `as` declaration).
        # Shortcuts follow the second participant only, so `A ++ -> B`
        # fails here too. Participants are created in source order.
        edge_error = f"malformed edge at line {line_number}"
        source = lifeline(left, edge_error, allow_as=True)
        target = lifeline(right, edge_error, allow_as=True)
        style, arrowhead, reverse, bidirectional = _sequence_arrow(arrow)
        if reverse:
            source, target = target, source
        diagram.add_edge(
            source,
            target,
            clean_label(message),
            style,
            arrowhead,
            bidirectional=bidirectional,
        )
        # `source` and `target` are already the sender and receiver after
        # a reverse arrow swapped them, so shortcuts follow the message.
        for action in actions:
            diagram.add_activation(source if action == "deactivate" else target, action)

    def lifeline(token: str, error: str, *, allow_as: bool = False) -> str:
        """Get or create the participant a reference names, by its code."""
        parsed = _endpoint_code(token, allow_as=allow_as)
        if parsed is None:
            _fail(error)
        code, display = parsed
        if code not in diagram.node_map:
            diagram.add_node(code, clean_label(display) or code, "lifeline")
        return code

    for line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if len(text) > MAX_STATEMENT_CHARS:
            _statement_too_long(line_number)
        lowered = text.casefold()
        if open_note is not None:
            if lowered in {"end note", "endnote"}:
                close_note()
                continue
            note_lines.append(text)
            continue
        if skin.consume(diagram, text, line_number):
            continue
        # Arrow first, with the classifier kind detection uses.
        split = _edge_split(text, "sequence")
        if split:
            diagram.parsed_roles[line_number] = "edge"
            add_message(split, line_number)
            continue
        diagram.parsed_roles[line_number] = "statement"
        title = re.match(r"^title\s+(.+)$", text, re.I)
        if title:
            diagram.title = clean_label(title.group(1))
            continue
        participant = _parse_participant(text, line_number)
        if participant:
            diagram.parsed_roles[line_number] = "declaration"
            node_id, label, shape, stereotype = participant
            diagram.add_node(node_id, label, shape, stereotype=stereotype)
            continue
        divider = re.match(r"^==+\s*(.*?)\s*==+$", text)
        if divider:
            diagram.fragments.append(
                {
                    "kind": "divider",
                    "label": clean_label(divider.group(1)),
                    "line": line_number,
                    "depth": len(fragment_stack),
                    "after_message": len(diagram.edges),
                    "regions": [],
                }
            )
            continue
        fragment = re.match(r"^(alt|opt|loop)\b\s*(.*)$", text, re.I)
        if fragment:
            label = clean_label(fragment.group(2))
            entry = {
                "kind": fragment.group(1).casefold(),
                "label": label,
                "line": line_number,
                "depth": len(fragment_stack),
                "first_message": next_message(),
                "last_message": None,
                "regions": [
                    {
                        "label": label,
                        "line": line_number,
                        "first_message": next_message(),
                        "last_message": None,
                    }
                ],
            }
            diagram.fragments.append(entry)
            fragment_stack.append(entry)
            continue
        region = re.match(r"^else\b\s*(.*)$", text, re.I)
        if region:
            if not fragment_stack:
                _fail(f"malformed statement at line {line_number}")
            close_region(fragment_stack[-1])
            fragment_stack[-1]["regions"].append(
                {
                    "label": clean_label(region.group(1)),
                    "line": line_number,
                    "first_message": next_message(),
                    "last_message": None,
                }
            )
            continue
        if lowered == "end":
            if fragment_stack:
                entry = fragment_stack.pop()
                close_region(entry)
                entry["last_message"] = len(diagram.edges)
                entry["end_line"] = line_number
                if entry["last_message"] < entry["first_message"]:
                    entry["first_message"] = entry["last_message"] = None
                continue
            _fail(f"malformed statement at line {line_number}")
        first = lowered.split(maxsplit=1)[0]
        if first in UNSUPPORTED_SEQUENCE:
            _fail(f"unsupported sequence construct: {first}")
        activate = re.match(r"^(activate|deactivate|destroy)\s+(.+)$", text, re.I)
        if activate:
            action = activate.group(1).casefold()
            # `activate A #red` colors the bar; the color is not a name.
            target = lifeline(
                _strip_trailing_colors(activate.group(2)),
                f"malformed statement at line {line_number}",
            )
            diagram.add_activation(target, action)
            continue
        note = _parse_note(text)
        if note:
            position, rest, note_body = note
            of_prefix = re.match(r"^of\b\s*(.*)$", rest, re.I)
            if of_prefix:
                rest = of_prefix.group(1)
            participants = note_participants(rest, line_number)
            message: int | None = None
            if not participants:
                if position in {"left", "right"} and not of_prefix:
                    # `note left: text` sits beside the message just sent.
                    if not diagram.edges:
                        _fail(f"malformed statement at line {line_number}")
                    message = len(diagram.edges)
                elif position != "across":
                    _fail(f"malformed statement at line {line_number}")
            elif position == "across":
                _fail(f"malformed statement at line {line_number}")
            open_note = {
                "position": position,
                "participants": participants,
                "after_message": len(diagram.edges),
                "message": message,
                "line": line_number,
            }
            if note_body is not None:
                note_lines = [note_body]
                close_note()
            else:
                note_lines = []
                note_start = line_number
            continue
        if lowered.startswith("note "):
            _fail(f"malformed statement at line {line_number}")
        if SEQ_ARROW_RE.search(text):
            _fail(f"malformed edge at line {line_number}")
        _fail(f"malformed statement at line {line_number}")
    if open_note is not None:
        _fail(f"unterminated note at line {note_start}")
    skin.check_closed()
    if fragment_stack:
        _fail(f"unterminated fragment at line {fragment_stack[-1]['line']}")


def _parse_class(diagram: Diagram, lines: list[tuple[int, str]]) -> None:
    current: Node | None = None
    current_line = 0
    # Open `{` blocks: a package id, or None for a layout-only `together`.
    blocks: list[tuple[str | None, int]] = []

    def scope() -> list[str]:
        return [block for block, _line in blocks if block is not None]

    def add_link(
        split: tuple[str, re.Match[str], str], line_number: int, link_scope: list[str]
    ) -> None:
        left, arrow, right = split
        right, label = _partition_unquoted(right, ":")
        left_name, left_card = _split_cardinality(left, before_arrow=True)
        right_name, right_card = _split_cardinality(right, before_arrow=False)
        edge_error = f"malformed edge at line {line_number}"
        source = class_ref(left_name, edge_error, link_scope)
        target = class_ref(right_name, edge_error, link_scope)
        arrowhead, style, reverse, bidirectional, undirected, hidden, navigable = _class_relationship(
            arrow, line_number
        )
        if reverse:
            source, target = target, source
            left_card, right_card = right_card, left_card
            navigable = {"source": "target", "target": "source"}.get(navigable, navigable)
        if hidden:
            # `-[hidden]-` is a layout hint with no drawn link.
            diagram.discarded["skin"] += 1
            return
        diagram.add_edge(
            source,
            target,
            clean_label(label),
            style,
            arrowhead,
            bidirectional=bidirectional,
            undirected=undirected,
            source_cardinality=clean_label(left_card),
            target_cardinality=clean_label(right_card),
            navigable=navigable,
        )

    def class_ref(token: str, error: str, link_scope: list[str] | None = None) -> str:
        """Get or create the class a reference names, by its code."""
        parsed = _endpoint_code(token)
        if parsed is None:
            _fail(error)
        code, display = parsed
        node_id = diagram.resolve(code, scope() if link_scope is None else link_scope)
        if node_id not in diagram.node_map:
            diagram.add_node(node_id, clean_label(display) or node_id, "class")
        return node_id

    # Declarations register first. A link before `class A` inside the same
    # package then resolves to that class instead of a new top-level one.
    pending_links: list[tuple[tuple[str, re.Match[str], str], int, list[str]]] = []
    skin = _SkinBlocks()
    for line_number, raw in lines:
        text = raw.strip()
        if not text:
            continue
        if len(text) > MAX_STATEMENT_CHARS:
            _statement_too_long(line_number)
        if current is not None:
            # Everything inside a class body is a member until its `}`.
            if text == "}":
                current = None
                continue
            if text in {"--", "..", "==", "__"}:
                continue
            current.fields.append(clean_label(text))
            continue
        if skin.consume(diagram, text, line_number):
            continue
        # Arrow first, with the classifier kind detection uses.
        split = _edge_split(text, "class")
        if split:
            diagram.parsed_roles[line_number] = "edge"
            pending_links.append((split, line_number, list(scope())))
            continue
        diagram.parsed_roles[line_number] = "statement"
        title = re.match(r"^title\s+(.+)$", text, re.I)
        if title:
            diagram.title = clean_label(title.group(1))
            continue
        if text == "}":
            if blocks:
                blocks.pop()
                continue
            _fail(f"malformed statement at line {line_number}")
        package = re.match(r"^(package|namespace|together)\b\s*(.*)$", text, re.I)
        if package:
            diagram.parsed_roles[line_number] = "declaration"
            rest = package.group(2).strip()
            opens = rest.endswith("{")
            if opens:
                rest = rest[:-1].strip()
            if package.group(1).casefold() == "together":
                # A layout hint that keeps classes near each other: no
                # container, and the classes keep their enclosing ids.
                if rest or not opens:
                    _fail(f"malformed statement at line {line_number}")
                blocks.append((None, line_number))
                continue
            # Same tokenizer as participants and classes: one name, one alias,
            # then color and stereotype, and nothing else.
            name, label, stereotype, body = _parse_declaration_tail(rest, line_number)
            if body not in ([], ["{}"]):
                _fail(f"malformed statement at line {line_number}")  # `package p { class A }`
            enclosing = scope()
            parent = enclosing[-1] if enclosing else None
            node_id = f"{parent}.{name}" if parent else name
            diagram.add_node(node_id, label, "container", parent, True, stereotype=stereotype)
            if opens:
                blocks.append((node_id, line_number))
            continue
        header = _parse_classifier_header(text, line_number)
        if header:
            diagram.parsed_roles[line_number] = "declaration"
            name, label, shape, stereotype, opens, members = header
            enclosing = scope()
            parent = enclosing[-1] if enclosing else None
            node_id = f"{parent}.{name}" if parent and "." not in name else name
            node = diagram.add_node(node_id, label, shape, parent, stereotype=stereotype)
            node.fields.extend(clean_label(member) for member in members)
            if node_id != name:
                diagram.bare_name(name, node_id)
            if opens:
                current = node
                current_line = line_number
            continue
        note = _parse_note(text)
        if note:
            position, rest, body = note
            of_prefix = re.match(r"^of\b\s*(.*)$", rest, re.I)
            raw_target = _strip_trailing_colors(of_prefix.group(1) if of_prefix else rest)
            if body is None or position in {"over", "across"}:
                _fail(f"malformed statement at line {line_number}")
            target = class_ref(raw_target, f"malformed statement at line {line_number}")
            cleaned = clean_label(body)
            if cleaned:
                _record_note(
                    diagram,
                    {
                        "position": position,
                        "participants": [target],
                        "after_message": None,
                        "message": None,
                        "line": line_number,
                    },
                    cleaned,
                )
            continue
        if CLASS_REL_RE.search(text) or "--" in text or ".." in text:
            _fail(f"malformed edge at line {line_number}")
        first = text.casefold().split(maxsplit=1)[0]
        if first in UNSUPPORTED_CLASS:
            _fail(f"unsupported class construct: {first}")
        _fail(f"malformed statement at line {line_number}")
    for split, line_number, link_scope in pending_links:
        add_link(split, line_number, link_scope)
    if current is not None:
        _fail(f"unterminated class body at line {current_line}")
    if blocks:
        _fail(f"unterminated package at line {blocks[-1][1]}")
    skin.check_closed()


def parse_block(block: SourceBlock) -> Diagram:
    if block.error:
        _fail(block.error)
    if block.start_kind != "uml":
        token = block.start_kind
        if token in UNSUPPORTED_STARTS or token != "uml":
            _fail(_unsupported_kind_message(token if token != "uml" else block.start_kind))
    lines = [
        (block.source_line + offset, text)
        for offset, text in enumerate(_blank_comments(block.text.splitlines()))
    ]
    # Before kind detection: a dash-only line makes the arrow scan quadratic.
    for line_number, text in lines:
        if len(text.strip()) > MAX_STATEMENT_CHARS:
            _statement_too_long(line_number)
    _refuse_includes(lines)
    kind, roles = _detect_kind(lines)
    diagram = Diagram(block.index, kind, block.source_line, direction="LR" if kind == "sequence" else "TD")
    diagram.detected_roles = roles
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


def node_ref(node: Node) -> str:
    """Name a node unambiguously: its id, plus its label when that differs.

    Two classes named `User` in different packages share a label, so every
    digest reference that points at a node carries the id the edges use.
    """
    label = node.label.replace("\n", " · ")
    if not label or label == node.id:
        return node.id
    return f"{node.id} ({label})"


def analyze(diagram: Diagram) -> dict[str, Any]:
    containers = [node for node in diagram.nodes if node.container or node.children]
    leaves = [node for node in diagram.nodes if not (node.container or node.children)]
    shapes: dict[str, int] = {}
    for node in diagram.nodes:
        family = "container" if node.shape == "container" else node.shape
        shapes[family] = shapes.get(family, 0) + 1

    def name(node: Node) -> str:
        return node_ref(node)

    hubs = [
        {
            "id": node.id,
            "label": node.label.replace("\n", " · ") or node.id,
            "ref": name(node),
            "degree": node.in_degree + node.out_degree,
        }
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


def _message_span(first: int | None, last: int | None) -> str:
    if first is None or last is None:
        return "no messages"
    return f"msg {first}" if first == last else f"msgs {first}-{last}"


def _note_summary(item: dict[str, Any]) -> str:
    text = _escape_markdown(item["text"].replace("\n", " ⏎ "))
    position = item["position"]
    if item["message"] is not None:
        return f"{position} of msg {item['message']}: {text}"
    where = position
    if item["participants"]:
        joiner = " " if position in {"over", "across"} else " of "
        where += joiner + ", ".join(_escape_markdown(name) for name in item["participants"])
    if item["after_message"] is not None:
        where += f" @{item['after_message']}"
    return f"{where}: {text}"


def _fragment_summary(item: dict[str, Any]) -> str:
    label = _escape_markdown(item["label"] or "unlabeled")
    if item["kind"] == "divider":
        return f"divider({label}) after msg {item['after_message']}"
    indent = f"depth {item['depth']}, " if item["depth"] else ""
    regions = item["regions"]
    parts = [
        f"{item['kind']}({label}) {indent}"
        f"{_message_span(regions[0]['first_message'], regions[0]['last_message'])}"
    ]
    for region in regions[1:]:
        parts.append(
            f"else({_escape_markdown(region['label'] or 'unlabeled')}) "
            f"{_message_span(region['first_message'], region['last_message'])}"
        )
    return "; ".join(parts)


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
            output.append(
                "- fragments (message numbers are the edge `#` column):"
            )
            for item in diagram.fragments:
                output.append(f"  - {_fragment_summary(item)}")
        if diagram.activations:
            output.append(
                "- activations (after message #): "
                + ", ".join(
                    f"{_escape_markdown(item['participant'])}:{item['action']}"
                    f"@{item['after_message']}"
                    for item in diagram.activations[:max_rows]
                )
                + (
                    f", +{len(diagram.activations) - max_rows} more (use --json)"
                    if len(diagram.activations) > max_rows
                    else ""
                )
            )
        if diagram.note_details:
            shown = diagram.note_details[:max_rows]
            output.append(
                "- notes (after message #): "
                + "; ".join(_note_summary(item) for item in shown)
                + (
                    f"; +{len(diagram.note_details) - len(shown)} more (use --json)"
                    if len(diagram.note_details) > len(shown)
                    else ""
                )
            )
        if info["hubs"]:
            output.append(
                "- hubs (focal candidates): "
                + ", ".join(
                    f"{_escape_markdown(hub['ref'])}({hub['degree']})"
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
                "| id | label | shape | stereotype | depth | parent | deg | fields |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for node in diagram.nodes[:max_rows]:
            output.append(
                f"| {_escape_table(node.id)} | {_escape_table(node.label)} | {node.shape} | "
                f"{_escape_table(node.stereotype) or '-'} | "
                f"{node.depth} | {_escape_table(node.parent) if node.parent else '-'} | "
                f"{node.in_degree}/{node.out_degree} | "
                f"{_escape_table('; '.join(node.fields)) or '-'} |"
            )
        if len(diagram.nodes) > max_rows:
            output.append(
                f"| … | +{len(diagram.nodes) - max_rows} more (use --json) | | | | | | |"
            )

        output.extend(
            [
                "",
                "### Edges",
                "",
                "| # | source | target | label | style |",
                "|---|---|---|---|---|",
            ]
        )
        names = {node.id: node_ref(node) for node in diagram.nodes}
        for edge in diagram.edges[:max_rows]:
            marks = [edge.style, edge.arrowhead]
            if edge.bidirectional:
                marks.append("bidir")
            if edge.undirected:
                marks.append("undirected")
            if edge.navigable:
                marks.append(f"navigable {edge.navigable}")
            if edge.source_cardinality or edge.target_cardinality:
                ends = []
                if edge.source_cardinality:
                    ends.append(f"{_escape_table(edge.source_cardinality)} (source)")
                if edge.target_cardinality:
                    ends.append(f"{_escape_table(edge.target_cardinality)} (target)")
                marks.append("cardinality " + " .. ".join(ends))
            output.append(
                f"| {edge.order} | {_escape_table(names.get(edge.source, edge.source))} | "
                f"{_escape_table(names.get(edge.target, edge.target))} | "
                f"{_escape_table(edge.label) or '-'} | {' '.join(marks)} |"
            )
        if len(diagram.edges) > max_rows:
            output.append(
                f"| … | +{len(diagram.edges) - max_rows} more (use --json) | | | |"
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
                    "note_details": diagram.note_details,
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
