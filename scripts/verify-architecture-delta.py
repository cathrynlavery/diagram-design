#!/usr/bin/env python3
"""Verify the public Architecture delta HTML contract using only the stdlib.

Checks identity, snapshot membership, shared local grids, declared semantic and
geometric changes, relationship endpoints, and exact ledger coverage. Panel
translations are excluded from movement; object transforms and CSS geometry
overrides are refused. This verifies authored declarations, not whether their
semantic signatures accurately describe an external system.

Usage: python3 scripts/verify-architecture-delta.py [--all | FILE ...]
No arguments and --all check every shipped architecture-delta example.
Exit: 0 clean, 1 contract findings, 2 unreadable input/usage.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
NUMBER = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NUMBER_RE = re.compile(NUMBER)
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]*\Z")
TRANSLATE_RE = re.compile(rf"translate\(\s*({NUMBER})[\s,]+({NUMBER})\s*\)\Z")
OBJECT_ATTRS = {"data-kind", "data-object-id", "data-status", "data-signature", "data-from", "data-to"}
LEDGER_ATTRS = {"data-change", "data-target"}
STATUSES = {"unchanged", "added", "removed", "changed", "moved", "rewired"}
CSS_MOVES = re.compile(
    r"(?:^|[;{])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?:transform|translate|rotate|scale|x|y|cx|cy|r|rx|ry|d|"
    r"offset(?:-(?:path|distance|position|anchor|rotate))?)\s*:", re.I)
CSS_SIZE = re.compile(r"(?:^|[;{])\s*(?:width|height)\s*:", re.I)
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
EPS = 1e-6
ENDPOINT_TOLERANCE = 2.0
MAX_COORDINATE = 1e7
NONRENDERING = {"defs", "symbol", "clippath", "mask", "pattern", "marker", "template", "script", "style", "title", "desc", "metadata"}


@dataclass(eq=False)
class Node:
    tag: str
    attrs: dict[str, str]
    line: int
    parent: Node | None = None
    children: list[Node] = field(default_factory=list)
    content: list[str | Node] = field(default_factory=list)
    duplicates: set[str] = field(default_factory=set)

    def text(self) -> str:
        return "".join(part.text() if isinstance(part, Node) else part for part in self.content)

    def ancestors(self):
        parent = self.parent
        while parent is not None:
            yield parent
            parent = parent.parent


class Scanner(HTMLParser):
    """HTML parsing honors unquoted attrs, entities, comments and raw style text.

    SVG must be properly nested; silently repairing malformed SVG would assign
    objects to snapshots differently from a browser. Repeated attributes are
    retained first (browser semantics) and additionally rejected.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document", {}, 1)
        self.stack = [self.root]
        self.nodes: list[Node] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {}
        duplicates = set()
        for name, value in attrs:
            if name in values:
                duplicates.add(name)
            values.setdefault(name, value or "")
        node = Node(tag, values, self.getpos()[0], self.stack[-1], duplicates=duplicates)
        self.stack[-1].children.append(node)
        self.stack[-1].content.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        indexes = [i for i, node in enumerate(self.stack) if node.tag == tag]
        in_svg = any(node.tag == "svg" for node in self.stack)
        if not indexes:
            if in_svg:
                self.errors.append(f"line {self.getpos()[0]}: malformed SVG closing tag {tag}")
            return
        index = indexes[-1]
        if in_svg and index != len(self.stack) - 1:
            self.errors.append(f"line {self.getpos()[0]}: malformed SVG nesting at {tag}")
        del self.stack[index:]

    def handle_data(self, data):
        self.stack[-1].content.append(data)

    def finish(self, source):
        self.feed(source)
        self.close()
        if any(node.tag == "svg" for node in self.stack):
            self.errors.append("unclosed SVG or snapshot")


def number(raw: str) -> float:
    if not NUMBER_RE.fullmatch(raw.strip()):
        raise ValueError("missing, malformed or non-finite number")
    value = float(raw)
    if not math.isfinite(value) or abs(value) > MAX_COORDINATE:
        raise ValueError("number must be finite and within 10,000,000 units")
    return value


def numbers(raw: str, count: int) -> tuple[float, ...]:
    parts = raw.split()
    if len(parts) != count:
        raise ValueError(f"expected {count} space-separated numbers")
    return tuple(number(part) for part in parts)


def on_grid(value: float, pitch: float) -> bool:
    ratio = value / pitch
    return math.isfinite(ratio) and abs(ratio - round(ratio)) <= EPS


def within(node: Node, ancestor: Node) -> bool:
    return node is ancestor or ancestor in node.ancestors()


def clean_css(raw: str) -> str:
    return re.sub(r"/\*.*?\*/", "", raw, flags=re.S)


def hiding_values(values: dict[str, str]) -> bool:
    values = {key: re.sub(r"\s*!important\s*$", "", value, flags=re.I).strip().lower()
              for key, value in values.items()}
    if values.get("display") == "none" or values.get("visibility") in {"hidden", "collapse"}:
        return True
    if values.get("content-visibility") == "hidden":
        return True
    opacity = values.get("opacity", "").removesuffix("%")
    return bool(NUMBER_RE.fullmatch(opacity) and float(opacity) <= 0)


def css_hides(raw: str) -> bool:
    # Treat any explicit hiding declaration as a finding. This conservative
    # rule does not need to implement the CSS cascade or !important priority.
    return any(hiding_values({match.group(1).lower(): match.group(2)})
               for match in re.finditer(r"(?:^|;)\s*([\w-]+)\s*:\s*([^;]*)", clean_css(raw)))


def path_points(raw: str) -> list[tuple[float, float]]:
    """Absolute, open M/L/H/V/Q/C paths; include control points for grid bounds.

    A single M is required. Implicit argument groups are supported (the SVG
    number grammar includes exponents and sign-delimited numbers). Closing or
    relative commands cannot silently change the endpoint we verify.
    """
    tokens = re.findall(rf"{NUMBER}|[A-Za-z]", raw)
    residue = re.sub(rf"{NUMBER}|[A-Za-z]|[\s,]", "", raw)
    if (re.search(r",\s*,|[A-Za-z]\s*,|,\s*[A-Za-z]", raw)
            or raw.strip().startswith(",") or raw.strip().endswith(",")):
        raise ValueError("relationship path has malformed coordinate separators")
    if residue or not tokens or tokens[0] != "M":
        raise ValueError("relationship path must start with absolute M")
    points = []
    index, command = 0, ""
    current = (0.0, 0.0)
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "Q": 4, "C": 6}
    while index < len(tokens):
        if tokens[index].isalpha():
            command = tokens[index]
            index += 1
            if command not in arity or (command == "M" and points):
                raise ValueError("relationship path supports one M followed by absolute L/H/V/Q/C only")
        if not command:
            raise ValueError("relationship path has no command")
        count = arity[command]
        if index + count > len(tokens):
            raise ValueError("relationship path has incomplete coordinates")
        values = [number(token) for token in tokens[index:index + count]]
        index += count
        if command == "H":
            current = (values[0], current[1])
            points.append(current)
        elif command == "V":
            current = (current[0], values[0])
            points.append(current)
        else:
            pairs = list(zip(values[::2], values[1::2]))
            points.extend(pairs)
            current = pairs[-1]
        if command == "M":
            command = "L"
    if len(points) < 2:
        raise ValueError("relationship path requires a drawn segment")
    return points


def on_perimeter(point, bounds):
    x, y = point
    left, top, width, height = bounds
    right, bottom = left + width, top + height
    t = ENDPOINT_TOLERANCE
    return ((left - t <= x <= right + t and min(abs(y - top), abs(y - bottom)) <= t)
            or (top - t <= y <= bottom + t and min(abs(x - left), abs(x - right)) <= t))


def selector_may_match(selector: str, node: Node) -> bool:
    """Conservative last-compound filter for CSS width/height on SVG objects.

    Responsive `svg {width:100%}` and ordinary HTML sizing remain legal; rules
    that might size a verified shape, including pseudo classes, are rejected.
    """
    last = re.split(r"\s+|[>+~]", selector.strip())[-1]
    if not last:
        return True
    # Functional pseudo-classes can contain arbitrary selectors. Fail closed.
    if ":" in last or "\\" in last or "[" in last:
        return True
    tag = re.match(r"^[\w|-]+", last)
    if tag and tag.group().split("|")[-1] != node.tag:
        return False
    ids = re.findall(r"#([\w-]+)", last)
    classes = re.findall(r"\.([\w-]+)", last)
    return (all(value == node.attrs.get("id") for value in ids)
            and set(classes) <= set(node.attrs.get("class", "").split()))


@dataclass
class Object:
    node: Node
    kind: str
    id: str
    status: set[str]
    signature: str
    bounds: tuple[float, ...] | None = None
    endpoints: tuple[str, str] | None = None
    points: list[tuple[float, float]] | None = None


def check_source(path: Path, source: str) -> list[str]:
    scanner = Scanner()
    scanner.finish(source)
    findings = []

    def fail(node, message):
        findings.append(f"{path.name}:{node.line}: {message}")

    roots = [node for node in scanner.nodes if node.attrs.get("data-diagram") == "architecture-delta"]
    if len(roots) != 1 or roots[0].tag != "svg":
        fail(scanner.root, 'require exactly one svg data-diagram="architecture-delta"')
        return findings
    root = roots[0]
    findings.extend(f"{path.name}: {error}" for error in scanner.errors)
    for node in scanner.nodes:
        if within(node, root) and node.duplicates:
            fail(node, f"duplicate attributes: {', '.join(sorted(node.duplicates))}")
    # An ancestor transform changes both panel scale and the measured local
    # geometry. Only each snapshot's one translation is part of this grammar.
    snapshots = [node for node in scanner.nodes if "data-snapshot" in node.attrs]
    states = [node.attrs["data-snapshot"] for node in snapshots]
    if sorted(states) != ["after", "before"]:
        fail(root, "require exactly two snapshots named before and after")
    grids = {}
    origins = {}
    by_snapshot = {}
    for snapshot in snapshots:
        state = snapshot.attrs["data-snapshot"]
        if snapshot.tag != "g" or snapshot.parent is not root:
            fail(snapshot, "snapshot must be a direct g child of the diagram SVG")
        try:
            grid = numbers(snapshot.attrs.get("data-grid", ""), 3)
            if min(grid) <= 0 or grid[2] > min(grid[:2]):
                raise ValueError("grid width, height and pitch must be positive")
            if not all(on_grid(value, grid[2]) for value in grid[:2]):
                raise ValueError("grid dimensions must be multiples of pitch")
            grids[state] = grid
        except ValueError as error:
            fail(snapshot, f"invalid data-grid: {error}")
        match = TRANSLATE_RE.fullmatch(snapshot.attrs.get("transform", "").strip())
        if match is None:
            fail(snapshot, "snapshot transform must be one translate(x y)")
        else:
            try:
                origins[state] = tuple(number(part) for part in match.groups())
            except ValueError as error:
                fail(snapshot, f"invalid panel translation: {error}")
        by_snapshot[snapshot] = {}
    if len(grids) == 2 and grids.get("before") != grids.get("after"):
        fail(root, "snapshot grids must match in width, height and pitch")
    if len(origins) == 2 and "before" in grids and "after" in grids:
        before, after = origins.get("before"), origins.get("after")
        if before and after and (after[0] < before[0] + grids["before"][0] or before[1] != after[1]):
            fail(root, "Before and After panels must be separated left-to-right on one baseline")

    protected = [node for node in scanner.nodes if within(node, root)] + list(root.ancestors())
    visible = set()
    for node in scanner.nodes:
        if (OBJECT_ATTRS | LEDGER_ATTRS | {"data-snapshot"}).intersection(node.attrs) or node.attrs.get("data-role") == "bounds":
            visible.add(node)
            visible.update(node.ancestors())
    for node in protected:
        if "transform" in node.attrs and node not in snapshots:
            fail(node, "only snapshot translations may transform verified geometry")
        inline = clean_css(node.attrs.get("style", ""))
        if "\\" in inline or CSS_MOVES.search(inline):
            fail(node, "CSS geometry overrides or escaped inline CSS are unsupported")
        if node.tag in {"animate", "animatemotion", "animatetransform", "set", "use", "foreignobject"}:
            fail(node, f"{node.tag} is unsupported in a static architecture delta")
        if node.tag == "svg" and node is not root and within(node, root):
            fail(node, "nested SVG viewports are unsupported")
    for node in visible:
        if node.tag in NONRENDERING:
            fail(node, "snapshot objects and ledger cannot be placed in nonrendering containers")
        if "hidden" in node.attrs or node.attrs.get("aria-hidden", "").lower() == "true" or hiding_values(node.attrs) or css_hides(node.attrs.get("style", "")):
            fail(node, "snapshot objects and ledger must not be hidden")
    bounds_nodes = [node for node in scanner.nodes if within(node, root) and node.attrs.get("data-role") == "bounds"]
    for node in bounds_nodes:
        if node.parent is None or node.parent.attrs.get("data-kind") != "component":
            fail(node, "bounds rect must be a direct child of a component")
        if CSS_SIZE.search(clean_css(node.attrs.get("style", ""))):
            fail(node, "CSS geometry overrides are unsupported on bounds")
    for style in [node for node in scanner.nodes if node.tag == "style"]:
        css = clean_css(style.text())
        # CSS escapes could disguise transform or geometry property names.
        if "\\" in css or CSS_MOVES.search(css):
            fail(style, "CSS geometry overrides or escaped CSS are unsupported")
        for selectors, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            if css_hides(declarations) and any(
                selector_may_match(selector, node)
                for selector in selectors.split(",") for node in visible
            ):
                fail(style, "CSS must not hide snapshot objects or ledger")
            if CSS_SIZE.search(declarations) and any(
                selector_may_match(selector, bound)
                for selector in selectors.split(",") for bound in bounds_nodes
            ):
                fail(style, "CSS geometry overrides are unsupported on bounds")

    objects = []
    for node in scanner.nodes:
        if (node.tag == "path" and any(within(node, snapshot) for snapshot in snapshots)
                and not any(ancestor.attrs.get("data-kind") == "component" or ancestor.tag in NONRENDERING
                            for ancestor in node.ancestors())
                and node.attrs.get("data-kind") != "relationship"):
            fail(node, "snapshot connector path is missing relationship metadata")
        if not OBJECT_ATTRS.intersection(node.attrs):
            continue
        owners = [snapshot for snapshot in snapshots if within(node, snapshot)]
        if len(owners) != 1 or not within(node, root):
            fail(node, "object must belong to exactly one snapshot")
            continue
        owner = owners[0]
        if any(OBJECT_ATTRS.intersection(ancestor.attrs) for ancestor in node.ancestors() if ancestor is not node):
            fail(node, "objects cannot be nested inside another object")
        kind = node.attrs.get("data-kind", "")
        identity = node.attrs.get("data-object-id", "")
        raw_status = node.attrs.get("data-status", "").split()
        status = set(raw_status)
        signature = node.attrs.get("data-signature", "")
        if kind not in {"component", "relationship"} or node.tag != {"component": "g", "relationship": "path"}.get(kind):
            fail(node, "data-kind must be component on g or relationship on path")
        if not ID_RE.fullmatch(identity):
            fail(node, "missing or malformed data-object-id")
        allowed = STATUSES - ({"rewired"} if kind == "component" else {"moved"})
        if not status or not status <= allowed or len(status) != len(raw_status):
            fail(node, "missing, duplicate or invalid data-status tokens")
        if len(status) > 1 and status.intersection({"unchanged", "added", "removed"}):
            fail(node, "unchanged, added and removed statuses must be exclusive")
        if not signature.strip():
            fail(node, "missing or blank data-signature")
        if identity in by_snapshot[owner]:
            fail(node, f"duplicate object ID {identity!r} within snapshot")
        obj = Object(node, kind, identity, status, signature)
        by_snapshot[owner][identity] = obj
        objects.append(obj)
        grid = grids.get(owner.attrs["data-snapshot"])
        if kind == "component":
            bounds = [child for child in node.children if child.attrs.get("data-role") == "bounds"]
            if len(bounds) != 1 or bounds[0].tag != "rect":
                fail(node, "component requires exactly one direct rect data-role=bounds")
            else:
                try:
                    obj.bounds = tuple(number(bounds[0].attrs.get(key, "")) for key in ("x", "y", "width", "height"))
                    x, y, width, height = obj.bounds
                    if width <= 0 or height <= 0 or min(x, y) < 0:
                        raise ValueError("bounds must have nonnegative position and positive size")
                    if grid:
                        if x + width > grid[0] + EPS or y + height > grid[1] + EPS:
                            raise ValueError("bounds exceed local grid")
                        if not all(on_grid(value, grid[2]) for value in obj.bounds):
                            raise ValueError("bounds must align to grid pitch")
                except ValueError as error:
                    fail(node, f"invalid component bounds: {error}")
            if "data-from" in node.attrs or "data-to" in node.attrs:
                fail(node, "components cannot declare relationship endpoints")
        elif kind == "relationship":
            obj.endpoints = (node.attrs.get("data-from", ""), node.attrs.get("data-to", ""))
            if not all(ID_RE.fullmatch(value) for value in obj.endpoints):
                fail(node, "missing or malformed relationship endpoint ID")
            try:
                obj.points = path_points(node.attrs.get("d", ""))
                if grid and any(not (-EPS <= x <= grid[0] + EPS and -EPS <= y <= grid[1] + EPS) for x, y in obj.points):
                    raise ValueError("relationship path exceeds local grid")
            except ValueError as error:
                fail(node, f"invalid relationship geometry: {error}")

    for snapshot, members in by_snapshot.items():
        if not any(obj.kind == "component" for obj in members.values()):
            fail(snapshot, "snapshot must contain at least one component")
        for obj in members.values():
            if obj.kind != "relationship" or obj.endpoints is None:
                continue
            for index, identity in enumerate(obj.endpoints):
                endpoint = members.get(identity)
                if endpoint is None or endpoint.kind != "component":
                    fail(obj.node, f"dangling relationship endpoint {identity!r}: must resolve to a component in this snapshot")
                elif endpoint.bounds and obj.points and not on_perimeter(obj.points[0 if index == 0 else -1], endpoint.bounds):
                    fail(obj.node, f"drawn relationship endpoint does not meet component {identity!r} perimeter")

    before = next((members for snapshot, members in by_snapshot.items() if snapshot.attrs["data-snapshot"] == "before"), {})
    after = next((members for snapshot, members in by_snapshot.items() if snapshot.attrs["data-snapshot"] == "after"), {})
    expected = set()
    for identity in before.keys() | after.keys():
        old, new = before.get(identity), after.get(identity)
        obj = new or old
        if old is None:
            if new.status != {"added"}:
                fail(new.node, f"after-only object {identity!r} must be added")
        elif new is None:
            if old.status != {"removed"}:
                fail(old.node, f"before-only object {identity!r} must be removed")
        else:
            if old.kind != new.kind:
                fail(new.node, f"retained object {identity!r} changed kind")
            if old.status != new.status or old.status.intersection({"added", "removed"}):
                fail(new.node, f"retained object {identity!r} must have matching retained statuses")
            if (old.signature != new.signature) != ("changed" in new.status):
                fail(new.node, f"CHANGED signature mismatch for {identity!r}: signatures differ iff changed")
            if old.kind == new.kind == "component" and old.bounds and new.bounds:
                if (old.bounds[:2] != new.bounds[:2]) != ("moved" in new.status):
                    fail(new.node, f"MOVED position mismatch for {identity!r}: local positions differ iff moved")
                if old.bounds[2:] != new.bounds[2:] and "changed" not in new.status:
                    fail(new.node, f"component size changed without CHANGED for {identity!r}")
            if old.kind == new.kind == "relationship" and (old.endpoints != new.endpoints) != ("rewired" in new.status):
                fail(new.node, f"REWIRED endpoints mismatch for {identity!r}: endpoints differ iff rewired")
        expected.update((identity, status.upper()) for status in obj.status - {"unchanged"})
    component_ids = {obj.id for obj in objects if obj.kind == "component"}
    relationship_ids = {obj.id for obj in objects if obj.kind == "relationship"}
    if len(component_ids) > 8:
        fail(root, "component budget exceeded: maximum 8 unique components")
    if len(relationship_ids) > 10:
        fail(root, "relationship budget exceeded: maximum 10 unique relationships")
    if not relationship_ids:
        fail(root, "architecture delta requires at least one relationship")

    entries = [node for node in scanner.nodes if LEDGER_ATTRS.intersection(node.attrs)]
    actual = set()
    for entry in entries:
        change, target = entry.attrs.get("data-change", ""), entry.attrs.get("data-target", "")
        if entry.tag != "text" or not within(entry, root) or any(within(entry, snapshot) for snapshot in snapshots):
            fail(entry, "ledger entry must be text in the diagram, outside both snapshots")
        if change not in {"ADDED", "REMOVED", "CHANGED", "MOVED", "REWIRED"} or not ID_RE.fullmatch(target):
            fail(entry, "invalid ledger change or single target ID")
        if not re.match(rf"^{re.escape(change)}\b", entry.text().strip()) or entry.text().strip() == change:
            fail(entry, "ledger text must begin with its uppercase change and explain it")
        key = (target, change)
        if key in actual:
            fail(entry, f"duplicate ledger entry {change} {target}")
        actual.add(key)
    if not entries or len(entries) > 8:
        fail(root, "ledger budget requires 1-8 entries")
    for target, change in sorted(expected - actual):
        fail(root, f"missing ledger coverage: {change} {target}")
    for target, change in sorted(actual - expected):
        fail(root, f"unexpected ledger coverage: {change} {target}")
    return findings


def looks_like_delta(path: Path, source: str) -> bool:
    scanner = Scanner()
    scanner.finish(source)
    return ("architecture-delta" in path.stem.lower()
            or any(node.attrs.get("data-diagram") == "architecture-delta"
                   or "data-snapshot" in node.attrs or "data-object-id" in node.attrs
                   for node in scanner.nodes))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped architecture delta")
    args = parser.parse_args()
    if args.all and args.paths:
        parser.error("use --all or explicit paths, not both")
    targets = sorted(ASSET_DIR.glob("example-*.html")) if args.all or not args.paths else [Path(value) for value in args.paths]
    checked, findings = 0, []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"error: cannot read {path}: {error}", file=sys.stderr)
            return 2
        if not looks_like_delta(path, source):
            continue
        checked += 1
        findings.extend(check_source(path, source))
    if not checked:
        print("error: no architecture delta diagrams found", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding)
    if findings:
        print(f"{len(findings)} architecture delta finding(s) across {checked} file(s).")
        return 1
    print(f"OK architecture delta: {checked} file(s); identities, grids, changes, endpoints and ledger coverage agree.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
