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

Parsing goes through the stdlib html.parser.HTMLParser rather than a regex,
so a block is recognized exactly when a browser would recognize its
data-block-* attributes: unquoted values, whitespace around `=`, and
case-insensitive attribute names all parse the same as their canonical form,
a comment's contents are never scanned as live markup (HTMLParser routes
`<!-- ... -->` to handle_comment, never to handle_starttag), and a repeated
attribute name keeps its first value, matching how a browser resolves a
duplicate attribute in one tag. A blank or boolean attribute (data-block-id
present with no value at all) still counts as the attribute being present --
with an empty string -- so it is reported as a blank id or blank name
finding rather than silently making the whole block invisible to the scan.
The prior regex scanner's quoted-`>` fix is superseded by this: a real regex
tag matcher cannot separate "not yet closed" from "attribute value contains
a literal `>`" for every valid quoting and spacing HTML allows, and each
such gap was the same failure shape -- a real block silently vanishing from
the scan, CI green as if the file had none.

Usage:
    python3 scripts/verify-block-registry.py --all
    python3 scripts/verify-block-registry.py skills/diagram-design/assets/example-x.html
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

DATA_BLOCK_PREFIX = "data-block-"


@dataclass
class Block:
    id: str
    parent: str | None
    name: str | None
    line: int


class _BlockScanner(HTMLParser):
    """Collect one Block per start tag carrying a data-block-id attribute.

    HTMLParser already lowercases tag/attribute names, tolerates unquoted
    values and whitespace around `=`, and never invokes handle_starttag for
    tag-like text inside a comment or inside <script>/<style> raw text --
    each of those is exactly a case the previous regex scanner mishandled.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A repeated attribute name keeps its first value, matching how a
        # browser resolves a duplicate attribute within one start tag.
        seen: dict[str, str | None] = {}
        for name, value in attrs:
            seen.setdefault(name, value)

        block_attrs: dict[str, str] = {}
        for name, value in seen.items():
            if name.startswith(DATA_BLOCK_PREFIX):
                # A present-but-valueless (boolean) attribute is a blank
                # value, not an absent attribute -- data-block-id alone
                # must still register as a block with a blank id.
                block_attrs[name[len(DATA_BLOCK_PREFIX) :]] = value if value is not None else ""

        if "id" not in block_attrs:
            return
        self.blocks.append(
            Block(
                id=block_attrs["id"],
                parent=block_attrs.get("parent"),
                name=block_attrs.get("name"),
                line=self.getpos()[0],
            )
        )


def parse_blocks(source: str) -> list[Block]:
    scanner = _BlockScanner()
    scanner.feed(source)
    scanner.close()
    return scanner.blocks


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
