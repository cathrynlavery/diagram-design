#!/usr/bin/env python3
"""Verify a Traceable block decomposition diagram's data-block-* metadata.

semantic-patterns.md § 8 requires every block to carry a stable, unique,
non-blank data-block-id, a non-blank data-block-name, and (when present) a
data-block-parent that resolves to another block's id in the same file, with
no cycles in the parent chain -- the same "no orphan blocks, no cycles" shape
Tree's own layout already assumes. Nothing in the SVG grammar enforces that
on its own: a copy-pasted node keeps its sibling's id, a renamed block leaves
its children pointing at an id that no longer exists, an empty id="" passes
as a real identifier, and all of them render as an ordinary,
unremarkable-looking diagram.

This does not correlate a block's metadata against its drawn position or
connector geometry -- see export-registry.md "What this never does". It is a
metadata-only structural check, not a visual layout check, and it is
independent of verify-geometry.py: that script catches a label mask clipped
by a node painted after it, this one catches a block registry that does not
cohere as a tree.

The tag matcher treats a quoted attribute value (single or double) as one
unit rather than stopping at the first literal `>`, and the attribute matcher
accepts either quote style. A naive `[^>]*` tag match truncates silently on a
value like `data-block-constraint="output > input"` -- valid HTML, and if
that attribute happens to sit before data-block-id in the tag, the entire
block vanishes from the scan with no error, which is worse than a crash: a
file with a real block passes CI as if it had none.

Usage:
    python3 scripts/verify-block-registry.py --all
    python3 scripts/verify-block-registry.py skills/diagram-design/assets/example-x.html
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

TAG_RE = re.compile(
    r"""<[a-zA-Z][\w:-]*\b((?:"[^"]*"|'[^']*'|[^>"'])*)>""",
    re.DOTALL,
)
ATTR_RE = re.compile(r"""\bdata-block-([a-z-]+)=(?:"([^"]*)"|'([^']*)')""")


@dataclass
class Block:
    id: str
    parent: str | None
    name: str | None
    line: int


def parse_blocks(source: str) -> list[Block]:
    blocks: list[Block] = []
    for tag in TAG_RE.finditer(source):
        attrs: dict[str, str] = {}
        for attr in ATTR_RE.finditer(tag.group(1)):
            name, double_quoted, single_quoted = attr.groups()
            attrs[name] = double_quoted if double_quoted is not None else single_quoted
        if "id" not in attrs:
            continue
        blocks.append(
            Block(
                id=attrs["id"],
                parent=attrs.get("parent"),
                name=attrs.get("name"),
                line=source.count("\n", 0, tag.start()) + 1,
            )
        )
    return blocks


def find_blank_ids(path: Path, blocks: list[Block]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if not block.id.strip():
            findings.append(
                f"{path.name}:{block.line}: block has a blank data-block-id"
            )
    return findings


def find_duplicates(path: Path, blocks: list[Block]) -> list[str]:
    by_id: dict[str, list[Block]] = {}
    for block in blocks:
        by_id.setdefault(block.id, []).append(block)

    findings: list[str] = []
    for block_id, group in by_id.items():
        if len(group) > 1:
            lines = ", ".join(str(b.line) for b in group)
            findings.append(
                f'{path.name}: duplicate data-block-id "{block_id}" at lines {lines}'
            )
    return findings


def find_orphan_parents(path: Path, blocks: list[Block], known_ids: set[str]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if block.parent is not None and block.parent not in known_ids:
            findings.append(
                f'{path.name}:{block.line}: data-block-parent "{block.parent}" on block '
                f'"{block.id}" does not match any data-block-id in this file'
            )
    return findings


def find_missing_names(path: Path, blocks: list[Block]) -> list[str]:
    findings: list[str] = []
    for block in blocks:
        if not block.name or not block.name.strip():
            findings.append(
                f'{path.name}:{block.line}: block "{block.id}" has a missing or blank data-block-name'
            )
    return findings


def find_cycles(path: Path, blocks: list[Block], known_ids: set[str]) -> list[str]:
    parent_of = {block.id: block.parent for block in blocks}
    findings: list[str] = []
    reported: set[str] = set()

    for block in blocks:
        if block.id in reported:
            continue
        chain: list[str] = []
        current: str | None = block.id
        while current is not None:
            if current in chain:
                cycle = chain[chain.index(current) :] + [current]
                reported.update(cycle)
                findings.append(f'{path.name}: parent cycle: {" -> ".join(cycle)}')
                break
            chain.append(current)
            if current not in known_ids:
                break  # broken parent reference; already reported by find_orphan_parents
            current = parent_of.get(current)
    return findings


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    blocks = parse_blocks(source)
    if not blocks:
        return []  # not every diagram uses the pattern; that's legal

    # A blank id is never a resolvable target: a blank data-block-parent must
    # report as unresolved, not quietly match a block whose id is also blank.
    known_ids = {block.id for block in blocks if block.id.strip()}
    findings: list[str] = []
    findings.extend(find_blank_ids(path, blocks))
    findings.extend(find_duplicates(path, blocks))
    findings.extend(find_orphan_parents(path, blocks, known_ids))
    findings.extend(find_missing_names(path, blocks))
    findings.extend(find_cycles(path, blocks, known_ids))
    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    for path in paths:
        if not path.exists():
            findings.append(f"{path}: file not found")
            continue
        findings.extend(check(path))

    for finding in findings:
        print(finding)
    print(f"Summary: {len(paths)} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
