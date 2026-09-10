#!/usr/bin/env python3
"""Verify a Model architecture diagram's layer census.

type-model-arch.md's whole reason to exist is the repeat group: a `x5` chip
standing in for five layers nobody wants drawn. That makes the multipliers
load-bearing arithmetic presented as decoration, and it is the one thing a
reader cannot check and a reviewer will not notice. A group nudged during
layout, a chip that says `x4` over a group declaring `data-repeat="5"`, or a
plan transcribed as `2 + 3*(1+5)` when the source says `2 + 3*(1+6)` all
render as a clean, confident diagram that adds up to the wrong network.

So the plan is recorded in the markup and recomputed here:

  * every counted block contributes the product of `data-repeat` along its
    group ancestry;
  * that sum must equal the stack panel's `data-depth`;
  * `data-depth` must equal the span of `data-layer-range` ("0-19" -> 20);
  * every `x N` chip's text must equal its group's `data-repeat`.

What this never does: it does not look at where anything is drawn. A group
whose rect does not visually enclose the blocks claiming it is a layout bug
for verify-geometry.py and the eye, not for this script -- the same split
verify-block-registry.py draws between a metadata contract and a picture.

Parsing goes through the stdlib html.parser so an attribute is recognized
exactly when a browser would recognize it: unquoted values, whitespace
around `=`, case-insensitive names, and a duplicate attribute keeping its
first value all resolve the way the rendered page resolves them, and markup
inside a comment is never scanned as live markup.

Usage:
    python3 scripts/verify-model-arch.py --all
    python3 scripts/verify-model-arch.py skills/diagram-design/assets/example-model-arch.html
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

# Roles that are a layer of the network. `ffn` is part of a layer and `io`
# sits outside the stack, so neither adds to the count -- but both are still
# validated as spelled, to catch `data-layer-kind="fnn"` silently vanishing
# from the census.
COUNTED_KINDS = frozenset({"full", "reindex", "reuse", "local", "attention", "block"})
UNCOUNTED_KINDS = frozenset({"ffn", "io"})
RANGE_RE = re.compile(r"^(\d+)-(\d+)$")
CHIP_RE = re.compile(r"^\s*[x×✕✖*]\s*(\d+)\s*$", re.IGNORECASE)
MAX_NESTING = 1  # one level: a group may have a parent, but not a grandparent


@dataclass
class Stack:
    name: str
    depth: str
    layer_range: str
    line: int


@dataclass
class Group:
    gid: str
    repeat: str
    parent: str
    line: int


@dataclass
class Layer:
    kind: str
    stack: str
    group: str
    line: int


@dataclass
class Chip:
    gid: str
    text: str
    line: int
    parts: list[str] = field(default_factory=list)


class _Scanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stacks: list[Stack] = []
        self.groups: list[Group] = []
        self.layers: list[Layer] = []
        self.chips: list[Chip] = []
        self._chip: Chip | None = None

    @staticmethod
    def _flatten(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        seen: dict[str, str] = {}
        for name, value in attrs:
            if name not in seen:
                seen[name] = value if value is not None else ""
        return seen

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = self._flatten(attrs)
        line = self.getpos()[0]

        if "data-stack" in a:
            self.stacks.append(
                Stack(a["data-stack"], a.get("data-depth", ""), a.get("data-layer-range", ""), line)
            )
        if "data-group-id" in a:
            self.groups.append(
                Group(a["data-group-id"], a.get("data-repeat", ""), a.get("data-group-parent", ""), line)
            )
        if "data-layer-kind" in a:
            self.layers.append(
                Layer(a["data-layer-kind"], a.get("data-layer-stack", ""), a.get("data-layer-group", ""), line)
            )
        if "data-repeat-for" in a:
            self._chip = Chip(a["data-repeat-for"], "", line)
            self.chips.append(self._chip)

    def handle_data(self, data: str) -> None:
        # A chip's text may be split across tspans; keep every run so the
        # comparison sees "x3", not just the "x".
        if self._chip is not None:
            self._chip.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._chip is not None and tag == "text":
            self._chip.text = "".join(self._chip.parts)
            self._chip = None


def parse(source: str) -> _Scanner:
    scanner = _Scanner()
    scanner.feed(source)
    scanner.close()
    for chip in scanner.chips:
        if not chip.text:
            chip.text = "".join(chip.parts)
    return scanner


def positive_int(raw: str) -> int | None:
    """Accept only a plain positive decimal. `03`, ` 3 `, `3.0` and `-3` are
    all rejected rather than coerced -- a repeat that needed normalising is a
    repeat nobody checked."""
    if not re.fullmatch(r"[1-9]\d*", raw):
        return None
    return int(raw)


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    doc = parse(source)
    if not doc.stacks and not doc.layers and not doc.groups:
        return []  # not a model-architecture diagram

    name = path.name
    findings: list[str] = []

    # ── groups ──────────────────────────────────────────────────────────
    by_gid: dict[str, Group] = {}
    for group in doc.groups:
        if not group.gid.strip():
            findings.append(f"{name}:{group.line}: repeat group has a blank data-group-id")
            continue
        if group.gid in by_gid:
            findings.append(
                f'{name}:{group.line}: duplicate data-group-id "{group.gid}" '
                f"(first seen at line {by_gid[group.gid].line})"
            )
            continue
        by_gid[group.gid] = group

    for gid, group in by_gid.items():
        if positive_int(group.repeat) is None:
            findings.append(
                f'{name}:{group.line}: group "{gid}" has data-repeat="{group.repeat}"; '
                "expected a positive whole number"
            )
        if group.parent and group.parent not in by_gid:
            findings.append(
                f'{name}:{group.line}: group "{gid}" declares data-group-parent '
                f'"{group.parent}", which is not a data-group-id in this file'
            )

    def ancestry(gid: str) -> tuple[list[Group], str | None]:
        """Walk gid up to its root. Returns the chain and an error, if any."""
        chain: list[Group] = []
        seen: set[str] = set()
        current = gid
        while current:
            if current in seen:
                return chain, f'group cycle through "{current}"'
            if current not in by_gid:
                return chain, f'unresolved group "{current}"'
            seen.add(current)
            group = by_gid[current]
            chain.append(group)
            current = group.parent
        return chain, None

    for gid in by_gid:
        chain, error = ancestry(gid)
        if error:
            findings.append(f"{name}:{by_gid[gid].line}: {error}")
        elif len(chain) > MAX_NESTING + 1:
            findings.append(
                f'{name}:{by_gid[gid].line}: group "{gid}" nests '
                f"{len(chain) - 1} levels deep; type-model-arch.md allows {MAX_NESTING}"
            )

    # ── stacks ──────────────────────────────────────────────────────────
    by_stack: dict[str, Stack] = {}
    for stack in doc.stacks:
        if not stack.name.strip():
            findings.append(f"{name}:{stack.line}: stage panel has a blank data-stack")
            continue
        if stack.name in by_stack:
            findings.append(
                f'{name}:{stack.line}: duplicate data-stack "{stack.name}" '
                f"(first seen at line {by_stack[stack.name].line})"
            )
            continue
        by_stack[stack.name] = stack

    declared: dict[str, int] = {}
    for sname, stack in by_stack.items():
        depth = positive_int(stack.depth)
        if depth is None:
            findings.append(
                f'{name}:{stack.line}: stack "{sname}" has data-depth="{stack.depth}"; '
                "expected a positive whole number"
            )
        else:
            declared[sname] = depth

        match = RANGE_RE.fullmatch(stack.layer_range.strip())
        if not match:
            findings.append(
                f'{name}:{stack.line}: stack "{sname}" has '
                f'data-layer-range="{stack.layer_range}"; expected "first-last"'
            )
            continue
        first, last = int(match.group(1)), int(match.group(2))
        if last < first:
            findings.append(
                f'{name}:{stack.line}: stack "{sname}" has data-layer-range '
                f'"{stack.layer_range}" running backwards'
            )
        elif depth is not None and last - first + 1 != depth:
            findings.append(
                f'{name}:{stack.line}: stack "{sname}" spans {last - first + 1} layers '
                f'("{stack.layer_range}") but declares data-depth="{depth}"'
            )

    # ── the census ──────────────────────────────────────────────────────
    counted: dict[str, int] = {sname: 0 for sname in by_stack}
    for layer in doc.layers:
        kind = layer.kind.strip().lower()
        if kind not in COUNTED_KINDS and kind not in UNCOUNTED_KINDS:
            findings.append(
                f'{name}:{layer.line}: data-layer-kind="{layer.kind}" is not one of '
                f"{sorted(COUNTED_KINDS | UNCOUNTED_KINDS)}"
            )
            continue
        if not layer.stack.strip():
            findings.append(f"{name}:{layer.line}: block has a blank data-layer-stack")
            continue
        if layer.stack not in by_stack:
            findings.append(
                f'{name}:{layer.line}: block claims data-layer-stack "{layer.stack}", '
                "which has no stage panel carrying that data-stack"
            )
            continue
        if kind in UNCOUNTED_KINDS:
            continue

        multiplier = 1
        if layer.group.strip():
            chain, error = ancestry(layer.group)
            if error:
                findings.append(
                    f'{name}:{layer.line}: block in data-layer-group "{layer.group}": {error}'
                )
                continue
            for group in chain:
                value = positive_int(group.repeat)
                if value is None:
                    multiplier = 0  # already reported above; do not double-count
                    break
                multiplier *= value
        counted[layer.stack] += multiplier

    for sname, total in counted.items():
        if sname not in declared:
            continue
        if total != declared[sname]:
            findings.append(
                f'{name}:{by_stack[sname].line}: stack "{sname}" expands to {total} layers '
                f"but declares data-depth={declared[sname]}; check the ×N multipliers"
            )

    # ── chips ───────────────────────────────────────────────────────────
    labelled: set[str] = set()
    for chip in doc.chips:
        if chip.gid not in by_gid:
            findings.append(
                f'{name}:{chip.line}: ×N chip points at data-repeat-for "{chip.gid}", '
                "which is not a data-group-id in this file"
            )
            continue
        labelled.add(chip.gid)
        match = CHIP_RE.fullmatch(chip.text)
        if not match:
            findings.append(
                f'{name}:{chip.line}: ×N chip for "{chip.gid}" reads '
                f'"{chip.text.strip()}"; expected a multiplier such as ×3'
            )
            continue
        if match.group(1) != by_gid[chip.gid].repeat:
            findings.append(
                f'{name}:{chip.line}: ×N chip for "{chip.gid}" reads '
                f'"{chip.text.strip()}" but the group declares '
                f'data-repeat="{by_gid[chip.gid].repeat}"'
            )

    for gid, group in by_gid.items():
        if gid not in labelled:
            findings.append(
                f'{name}:{group.line}: group "{gid}" has no ×N chip; '
                "an unlabelled repeat group is invisible depth"
            )

    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify model-architecture layer censuses.")
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
