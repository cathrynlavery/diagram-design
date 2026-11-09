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
STYLE_RE = re.compile(
    r"<!--.*?(?:-->|$)|<style\b[^>]*>(?P<body>.*?)</style\s*>", re.IGNORECASE | re.DOTALL
)
CSS_COMMENT_OR_STRING_RE = re.compile(
    r"""/\*.*?(?:\*/|$)|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'""", re.DOTALL
)
CSS_ESCAPE = r"\\(?:[0-9a-fA-F]{1,6}(?:\r\n|[ \t\r\n\f])?|[^\r\n\f])"
CSS_ESCAPE_RE = re.compile(CSS_ESCAPE)
CSS_IDENTIFIER = rf"(?:[\w-]|{CSS_ESCAPE})+"
CSS_ATTRIBUTE_RE = re.compile(
    rf"{CSS_ESCAPE}|\[\s*(?:(?:{CSS_IDENTIFIER}|\*)?\|)?"
    rf"(?P<name>{CSS_IDENTIFIER})\s*(?:[~|^$*]?=|\])"
)
KINDS = {"command": "CMD-", "event": "EVT-", "read-model": "VIEW-"}
LINKS = {"emits": ("command", "event"), "projects": ("event", "read-model")}


def decode_css_escape(match: re.Match[str]) -> str:
    token = match[0][1:]
    if token[0] not in "0123456789abcdefABCDEF":
        return token
    codepoint = int(token.strip(), 16)
    if 0 < codepoint <= 0x10FFFF and not 0xD800 <= codepoint <= 0xDFFF:
        return chr(codepoint)
    return "\ufffd"


def inline_style(node: ET.Element) -> dict[str, str]:
    declarations = CSS_COMMENT_OR_STRING_RE.sub(" ", node.attrib.get("style", ""))
    return {
        CSS_ESCAPE_RE.sub(decode_css_escape, key.strip()).casefold(): value.strip().casefold()
        for key, separator, value in (
            part.partition(":") for part in declarations.split(";")
        )
        if key and separator
    }


def hidden(node: ET.Element) -> bool:
    tag = node.tag.rsplit("}", 1)[-1]
    style = inline_style(node)
    return (
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
    )


def visible(element: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    """Read SVG text outside hidden and non-rendering subtrees."""
    ancestor = parents.get(element)
    while ancestor is not None:
        if hidden(ancestor):
            return ""
        ancestor = parents.get(ancestor)

    chunks: list[str] = []

    def walk(node: ET.Element, in_text: bool = False) -> None:
        if hidden(node):
            return
        in_text = in_text or node.tag.rsplit("}", 1)[-1] == "text"
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
    # Rules targeting structural groups can override the attributes checked below.
    for style in STYLE_RE.finditer(source):
        body = style.group("body")
        if body is None:
            continue
        css = CSS_COMMENT_OR_STRING_RE.sub(" ", body)
        selectors = re.findall(r"([^{}]+)\{", css)
        if any(
            CSS_ESCAPE_RE.sub(decode_css_escape, name).casefold() == "data-event-stage"
            for selector in selectors
            for match in CSS_ATTRIBUTE_RE.finditer(selector)
            if (name := match.group("name")) is not None
        ):
            errors.append("stylesheet must not select data-event-stage")
            break

    parents = {child: parent for parent in svg.iter() for child in parent}
    stages = [element for element in svg.iter() if "data-event-stage" in element.attrib]
    if not 1 <= len(stages) <= 6:
        errors.append("expected 1 to 6 ordered stages")
    stage_ids: set[str] = set()
    global_ids: set[str] = set()
    for index, stage in enumerate(stages, 1):
        stage_id = stage.attrib["data-event-stage"]
        if "transform" in stage.attrib or {"transform", "translate", "rotate", "scale"} & inline_style(stage).keys():
            errors.append(f"{stage_id}: event stage must not use transform")
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
                if element_id and element_id not in visible(element, parents):
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
    headings = visible(svg, parents).casefold()
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
