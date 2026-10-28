#!/usr/bin/env python3
"""Verify ordered command, event, and read-model stages in shipped examples."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL)
KINDS = {"command": "CMD-", "event": "EVT-", "read-model": "VIEW-"}
LINKS = {"emits": ("command", "event"), "projects": ("event", "read-model")}


def visible(element: ET.Element) -> str:
    """Read SVG text while excluding metadata and hidden descendants."""
    chunks: list[str] = []

    def walk(node: ET.Element, in_text: bool = False) -> None:
        tag = node.tag.rsplit("}", 1)[-1]
        style = {
            key.strip().casefold(): value.strip().casefold()
            for key, separator, value in (
                part.partition(":") for part in node.attrib.get("style", "").split(";")
            )
            if key and separator
        }
        if (
            tag in {"defs", "title", "desc"}
            or node.attrib.get("aria-hidden") == "true"
            or "hidden" in node.attrib
            or node.attrib.get("display") == "none"
            or node.attrib.get("visibility") == "hidden"
            or node.attrib.get("opacity") in {"0", "0.0"}
            or node.attrib.get("fill") in {"none", "transparent"}
            or node.attrib.get("fill-opacity") in {"0", "0.0"}
            or style.get("display") == "none"
            or style.get("visibility") == "hidden"
            or style.get("opacity") in {"0", "0.0"}
            or style.get("fill") in {"none", "transparent"}
            or style.get("fill-opacity") in {"0", "0.0"}
        ):
            return
        in_text = in_text or tag == "text"
        if in_text and node.text:
            chunks.append(node.text)
        for child in node:
            walk(child, in_text)
            if in_text and child.tail:
                chunks.append(child.tail)

    walk(element)
    return " ".join(" ".join(chunks).split())


def check(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    match = SVG_RE.search(source)
    if not match:
        return ["missing SVG"]
    try:
        svg = ET.fromstring(match.group())
    except ET.ParseError as exc:
        return [f"invalid SVG: {exc}"]
    if svg.attrib.get("data-diagram-type") != "event-modeling":
        return ["SVG must declare data-diagram-type=event-modeling"]

    errors: list[str] = []
    stages = [element for element in svg.iter() if "data-event-stage" in element.attrib]
    if not 1 <= len(stages) <= 6:
        errors.append("expected 1 to 6 ordered stages")
    stage_ids: set[str] = set()
    global_ids: set[str] = set()
    for index, stage in enumerate(stages, 1):
        stage_id = stage.attrib["data-event-stage"]
        if not stage_id or stage_id in stage_ids:
            errors.append(f"blank or duplicate stage ID: {stage_id!r}")
        stage_ids.add(stage_id)
        if stage.attrib.get("data-stage-order") != str(index):
            errors.append(f"{stage_id}: stage order must be {index}")
        if stage.attrib.get("data-diagram-role") != "timeframe":
            errors.append(f"{stage_id}: stage role must be timeframe")
        elements = {kind: [] for kind in KINDS}
        links = {rel: [] for rel in LINKS}
        for element in stage.iter():
            kind = element.attrib.get("data-event-kind")
            if kind is not None:
                if kind not in elements:
                    errors.append(f"{stage_id}: unknown kind {kind!r}")
                    continue
                elements[kind].append(element)
                if element.attrib.get("data-diagram-role") != kind:
                    errors.append(f"{stage_id}: {kind} node role must be {kind}")
                element_id = element.attrib.get("data-event-id", "").strip()
                if not element_id.startswith(KINDS[kind]) or element_id in global_ids:
                    errors.append(f"{stage_id}: invalid or duplicate {kind} ID {element_id!r}")
                global_ids.add(element_id)
                if element_id and element_id not in visible(element):
                    errors.append(f"{stage_id}: {kind} ID {element_id!r} is not printed")
            rel = element.attrib.get("data-event-rel")
            if rel is not None:
                if rel not in links:
                    errors.append(f"{stage_id}: unknown link {rel!r}")
                else:
                    links[rel].append(element)
        for kind in KINDS:
            if len(elements[kind]) != 1:
                errors.append(f"{stage_id}: expected one {kind}")
        for rel, (from_kind, to_kind) in LINKS.items():
            found = links[rel]
            if len(found) != 1:
                errors.append(f"{stage_id}: expected one {rel} link")
                continue
            if found[0].attrib.get("data-diagram-role") != "event-link":
                errors.append(f"{stage_id}: {rel} link role must be event-link")
            if len(elements[from_kind]) != 1 or len(elements[to_kind]) != 1:
                continue
            from_id = elements[from_kind][0].attrib.get("data-event-id", "")
            to_id = elements[to_kind][0].attrib.get("data-event-id", "")
            if found[0].attrib.get("data-from") != from_id or found[0].attrib.get("data-to") != to_id:
                errors.append(f"{stage_id}: {rel} endpoints do not match the stage")
    headings = visible(svg).casefold()
    for heading in ("command", "event", "read model", "time moves left to right"):
        if heading not in headings:
            errors.append(f"missing visible {heading} label")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check shipped event-modeling examples")
    args = parser.parse_args()
    paths = sorted(ASSETS.glob("example-event-modeling*.html")) if args.all else args.paths
    if not paths:
        parser.error("provide files or --all")
    failed = False
    for path in paths:
        errors = check(path)
        if errors:
            failed = True
            for error in errors:
                print(f"{path}: {error}", file=sys.stderr)
        else:
            print(f"OK {path}")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
