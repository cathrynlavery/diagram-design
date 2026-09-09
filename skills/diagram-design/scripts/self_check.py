#!/usr/bin/env python3
"""Self-check a generated diagram HTML file, with no third-party deps.

Ships inside the skill so an installed agent can verify its own output:

    python3 <skill-dir>/scripts/self_check.py my-diagram.html

Checks the accessible-SVG contract, the single-file safety rules (no remote
assets beyond the approved Google Fonts stylesheet, no executable attributes,
no scripts other than the one canonical motion controller), and — when motion
markup is present — the structural motion contract. This is a distilled
subset of the repository gates (`lint-skin.py`, `verify-motion.py`), which
remain the authority for contributions to the repository itself.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
MOTION_TEMPLATE = SKILL_DIR / "assets" / "template-motion.html"
MODES = {"none", "reveal", "step", "loop"}
ACTIONS = {"play", "pause", "replay", "prev", "next"}
ASCII_DECIMAL_RE = re.compile(r"^[0-9]+$")
CSS_ESCAPE_RE = re.compile(
    r"\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|(.))", re.DOTALL
)
CSS_IMPORT_RE = re.compile(r"@import\b", re.IGNORECASE)
CSS_URL_RE = re.compile(r"url\(\s*([^)]+?)\s*\)", re.IGNORECASE)
CSS_IMAGE_SET_RE = re.compile(r"(?:-webkit-)?image-set\s*\(", re.IGNORECASE)
CSS_REMOTE_RE = re.compile(r"(?:https?:)?//", re.IGNORECASE)
CSS_REFERENCE_ATTRS = {
    "style",
    "fill",
    "stroke",
    "filter",
    "clip-path",
    "mask",
    "marker",
    "marker-start",
    "marker-mid",
    "marker-end",
    "cursor",
}
REFERENCE_ATTRS = {
    "src",
    "href",
    "xlink:href",
    "poster",
    "srcset",
    "action",
    "formaction",
}


class DiagramParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roots: list[dict[str, str]] = []
        self.items: list[dict[str, str]] = []
        self.actions: set[str] = set()
        self.controls = 0
        self.statuses: list[dict[str, str]] = []
        self.statuses_in_controls = 0
        self.scripts: list[dict[str, object]] = []
        self.styles: list[str] = []
        self.css_attributes: list[str] = []
        self.svgs: list[dict[str, object]] = []
        self.unsafe: list[str] = []
        self.references: list[tuple[str, str, str]] = []
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._capture: str | None = None
        self._current_script: dict[str, object] | None = None
        self._in_style = False
        self._element_stack: list[str] = []
        self._motion_root_depth: int | None = None
        self._controls_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        normalized_attrs = [(key.casefold(), value or "") for key, value in attrs]
        data: dict[str, str] = {}
        for key, value in normalized_attrs:
            data.setdefault(key, value)
        if tag in {"base", "embed", "object", "iframe"}:
            self.unsafe.append(f"<{tag}> is not allowed in a diagram file")
        for key, value in normalized_attrs:
            if key.startswith("on"):
                self.unsafe.append(f"executable attribute {key} on <{tag}>")
            if key == "srcdoc":
                self.unsafe.append(f"srcdoc attribute on <{tag}>")
            if key in REFERENCE_ATTRS:
                self.references.append((tag, data.get("rel", ""), value))
            if key in CSS_REFERENCE_ATTRS:
                self.css_attributes.append(value)
        if "data-motion-root" in data:
            self.roots.append(data)
            if self._motion_root_depth is None:
                self._motion_root_depth = len(self._element_stack)
        if self._motion_root_depth is not None:
            if "data-motion-item" in data:
                self.items.append(data)
            if "data-motion-action" in data:
                self.actions.add(data["data-motion-action"])
            if "data-motion-controls" in data:
                self.controls += 1
                if self._controls_depth is None:
                    self._controls_depth = len(self._element_stack)
            if "data-motion-status" in data:
                self.statuses.append(data)
                if self._controls_depth is not None:
                    self.statuses_in_controls += 1
        if tag == "script":
            self._current_script = {
                "attrs": data,
                "attr_names": [name for name, _value in normalized_attrs],
                "body": [],
                "closed": False,
            }
            self.scripts.append(self._current_script)
        if tag == "style":
            self._in_style = True
        self._element_stack.append(tag)
        if tag == "svg" and self._svg_depth == 0:
            self._svg_depth = 1
            self._current_svg = {"attrs": data, "first": None, "title": {}, "desc": {}}
            self.svgs.append(self._current_svg)
            return
        if self._svg_depth:
            self._svg_depth += 1
            assert self._current_svg is not None
            if self._svg_depth == 2 and self._current_svg["first"] is None:
                self._current_svg["first"] = tag
            if self._svg_depth == 2 and tag in {"title", "desc"}:
                self._current_svg[tag] = {"attrs": data, "text": ""}
                self._capture = tag

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "script" and self._current_script is not None:
            self._current_script["closed"] = True
            self._current_script = None
        if tag == "style":
            self._in_style = False
        if self._svg_depth:
            if tag in {"title", "desc"}:
                self._capture = None
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index] == tag:
                del self._element_stack[index:]
                break
        if (
            self._motion_root_depth is not None
            and len(self._element_stack) <= self._motion_root_depth
        ):
            self._motion_root_depth = None
        if (
            self._controls_depth is not None
            and len(self._element_stack) <= self._controls_depth
        ):
            self._controls_depth = None

    def handle_data(self, data: str) -> None:
        if self._current_script is not None:
            body = self._current_script["body"]
            assert isinstance(body, list)
            body.append(data)
        if self._in_style:
            self.styles.append(data)
        if self._capture and self._current_svg:
            node = self._current_svg[self._capture]
            assert isinstance(node, dict)
            node["text"] = str(node.get("text", "")) + data


def normalized_controller(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def parsed_document(source: str) -> DiagramParser:
    parser = DiagramParser()
    parser.feed(source)
    parser.close()
    return parser


def is_approved_google_fonts_stylesheet(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == "fonts.googleapis.com"
        and parsed.port is None
        and parsed.path == "/css2"
        and not parsed.fragment
    )


def reference_error(tag: str, rel: str, value: str) -> str | None:
    stripped = value.strip()
    lowered = stripped.casefold()
    if not stripped or stripped.startswith("#"):
        return None
    if lowered.startswith("javascript:") or lowered.startswith("data:text/html"):
        return f"executable URL on <{tag}>: {stripped[:80]}"
    remote = lowered.startswith(("http://", "https://", "//")) or (
        ":" in stripped.split("/", 1)[0] and not lowered.startswith("data:")
    )
    if not remote:
        if lowered.startswith("data:") and not lowered.startswith("data:image/"):
            return f"non-image data URL on <{tag}>: {stripped[:80]}"
        return None
    if tag == "link" and "stylesheet" in rel.casefold().split():
        if is_approved_google_fonts_stylesheet(stripped):
            return None
        return f"remote stylesheet is not the approved Google Fonts /css2 URL: {stripped[:80]}"
    return f"remote reference on <{tag}>: {stripped[:80]}"


def normalize_css_escapes(source: str) -> str:
    source = source.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")

    def replace(match: re.Match[str]) -> str:
        if match.group(1) is None:
            escaped = match.group(2)
            return "" if escaped == "\n" else escaped
        codepoint = int(match.group(1), 16)
        if codepoint == 0 or codepoint > 0x10FFFF:
            return "\N{REPLACEMENT CHARACTER}"
        return chr(codepoint)

    return CSS_ESCAPE_RE.sub(replace, source)


def check_css_references(parser: DiagramParser, errors: list[str]) -> None:
    # Match the repository linter's fail-closed treatment of CSS loader syntax.
    source = normalize_css_escapes("\n".join(parser.styles + parser.css_attributes))
    found_loader = False
    if CSS_IMPORT_RE.search(source):
        errors.append("CSS @import is not allowed")
        found_loader = True
    for match in CSS_URL_RE.finditer(source):
        value = match.group(1).strip().strip("'\"").strip()
        if not value.startswith("#"):
            errors.append("non-fragment CSS url() is not allowed")
            found_loader = True
    if CSS_IMAGE_SET_RE.search(source):
        errors.append("CSS image-set() is not allowed")
        found_loader = True
    if CSS_REMOTE_RE.search(source) and not found_loader:
        errors.append("remote reference in CSS is not allowed")


def canonical_controller() -> str:
    if not MOTION_TEMPLATE.is_file():
        raise RuntimeError(
            f"cannot find the canonical controller at {MOTION_TEMPLATE}; "
            "run self_check.py from its shipped location inside the skill"
        )
    parser = parsed_document(MOTION_TEMPLATE.read_text(encoding="utf-8"))
    if len(parser.scripts) != 1 or not parser.scripts[0]["closed"]:
        raise RuntimeError("template-motion.html must contain one closed controller")
    body = parser.scripts[0]["body"]
    assert isinstance(body, list)
    return normalized_controller("".join(body))


def check_svgs(parser: DiagramParser, errors: list[str]) -> None:
    checkable = [
        svg
        for svg in parser.svgs
        if isinstance(svg["attrs"], dict)
        and str(svg["attrs"].get("aria-hidden", "")).casefold() != "true"
    ]
    if not checkable:
        errors.append("diagram file needs at least one accessible (non-aria-hidden) SVG")
    for number, svg in enumerate(checkable, 1):
        attrs = svg["attrs"]
        assert isinstance(attrs, dict)
        if attrs.get("role") != "img":
            errors.append(f"svg {number} needs role=img")
        labelled = attrs.get("aria-labelledby", "").split()
        title = svg["title"]
        desc = svg["desc"]
        assert isinstance(title, dict) and isinstance(desc, dict)
        title_attrs = title.get("attrs", {})
        desc_attrs = desc.get("attrs", {})
        assert isinstance(title_attrs, dict) and isinstance(desc_attrs, dict)
        if svg["first"] != "title":
            errors.append(f"svg {number} title must be its first child")
        if not str(title.get("text", "")).strip() or not str(desc.get("text", "")).strip():
            errors.append(f"svg {number} needs non-empty title and desc")
        title_id = title_attrs.get("id", "")
        desc_id = desc_attrs.get("id", "")
        if title_id in {"", "title"} or desc_id in {"", "desc"}:
            errors.append(f"svg {number} title/desc IDs must be diagram-prefixed, never bare")
        if labelled != [title_id, desc_id]:
            errors.append(f"svg {number} aria-labelledby must name title then desc")


def check_scripts(parser: DiagramParser, errors: list[str]) -> None:
    if not parser.scripts:
        return
    if len(parser.scripts) > 1:
        errors.append(f"at most one script is allowed; found {len(parser.scripts)}")
    for number, script in enumerate(parser.scripts, 1):
        attrs = script["attrs"]
        attr_names = script["attr_names"]
        body = script["body"]
        assert isinstance(attrs, dict) and isinstance(attr_names, list) and isinstance(body, list)
        if not script["closed"]:
            errors.append(f"script {number} must have a closing script tag")
        if attr_names != ["data-diagram-controls"] or attrs.get("data-diagram-controls") != "":
            errors.append(f"script {number} must carry only the canonical data-diagram-controls attribute")
            continue
        try:
            if normalized_controller("".join(body)) != canonical_controller():
                errors.append(f"script {number} must exactly match the controller in template-motion.html")
        except RuntimeError as exc:
            errors.append(str(exc))


def check_motion(parser: DiagramParser, source: str, errors: list[str]) -> None:
    has_motion_markup = bool(parser.roots or parser.items or parser.scripts)
    if not has_motion_markup:
        return
    if len(parser.roots) != 1:
        errors.append(f"expected exactly one data-motion-root; found {len(parser.roots)}")
        return
    root = parser.roots[0]
    mode = root.get("data-motion-mode", "")
    if mode not in MODES:
        errors.append(f"data-motion-mode must be one of {sorted(MODES)}; got {mode!r}")
    raw_count = root.get("data-step-count", "")
    if not ASCII_DECIMAL_RE.fullmatch(raw_count):
        count = -1
        errors.append("data-step-count must be an ASCII decimal integer")
    else:
        count = int(raw_count)
    minimum_count = 0 if mode == "none" else 1
    if count < minimum_count or count > 8:
        errors.append(f"semantic step count must be {minimum_count}..8; got {count}")

    if len(parser.items) > 12:
        errors.append(f"motion item budget is 12; found {len(parser.items)}")
    semantic_steps: list[int] = []
    for index, item in enumerate(parser.items, 1):
        raw_step = item.get("data-step", "")
        if not ASCII_DECIMAL_RE.fullmatch(raw_step):
            errors.append(f"motion item {index} has a non-ASCII-decimal data-step")
            continue
        step = int(raw_step)
        decorative = "data-motion-decorative" in item
        if not decorative:
            semantic_steps.append(step)
            if not item.get("aria-label", "").strip():
                errors.append(f"semantic motion item {index} needs a non-color aria-label")
        elif item.get("aria-hidden") != "true" or item.get("focusable") != "false":
            errors.append(f"decorative motion item {index} needs aria-hidden=true and focusable=false")
        inline = item.get("style", "").replace(" ", "").lower()
        if any(token in inline for token in ("display:none", "visibility:hidden", "opacity:0")):
            errors.append(f"motion item {index} is hidden in source; the fallback must be visible")

    expected = set(range(1, count + 1)) if count > 0 else set()
    if set(semantic_steps) != expected:
        errors.append(f"semantic steps must be contiguous 1..{count}; found {sorted(set(semantic_steps))}")
    crowded = {step: n for step, n in Counter(semantic_steps).items() if n > 2}
    if crowded:
        errors.append(f"no more than two semantic items may share a step; found {crowded}")

    if mode in {"none", "loop"} and parser.scripts:
        errors.append(f"{mode} mode must be script-free")
    if mode in {"none", "loop"} and (parser.controls or parser.actions or parser.statuses):
        errors.append(f"{mode} mode must not expose playback controls or live status")
    controlled = mode == "step" or (mode == "reveal" and bool(parser.scripts))
    if controlled:
        if parser.controls != 1:
            errors.append(f"controlled mode needs one in-root control group; found {parser.controls}")
        missing = ACTIONS - parser.actions
        if missing:
            errors.append(f"controlled mode is missing actions: {', '.join(sorted(missing))}")
        if not parser.statuses:
            errors.append("controlled mode needs data-motion-status")
        else:
            status = parser.statuses[0]
            if (
                status.get("role") != "status"
                or status.get("aria-live") != "polite"
                or status.get("aria-atomic") != "true"
            ):
                errors.append("motion status needs role=status, aria-live=polite, aria-atomic=true")
            if parser.statuses_in_controls:
                errors.append("motion status must sit outside data-motion-controls")
        if not parser.scripts:
            errors.append("controlled mode needs the scoped control script")

    style_source = "".join(parser.styles)
    if parser.scripts:
        if re.search(r"prefers-reduced-motion\s*:\s*reduce", style_source, re.IGNORECASE) is None:
            errors.append("missing reduced-motion CSS fallback (prefers-reduced-motion)")
        if re.search(r"@media\s+print\b", style_source, re.IGNORECASE) is None:
            errors.append("missing print CSS fallback (@media print)")
        if "<noscript" not in source.casefold():
            errors.append("motion file needs a <noscript> explanation of the complete static frame")


def verify(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    parser = parsed_document(source)
    errors: list[str] = []
    errors.extend(parser.unsafe)
    check_css_references(parser, errors)
    for tag, rel, value in parser.references:
        finding = reference_error(tag, rel, value)
        if finding:
            errors.append(finding)
    check_svgs(parser, errors)
    check_scripts(parser, errors)
    check_motion(parser, source, errors)
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("files", nargs="+", type=Path)
    args = argument_parser.parse_args()
    failed = False
    for path in args.files:
        try:
            errors = verify(path)
        except (OSError, UnicodeError) as exc:
            errors = [str(exc)]
        if errors:
            failed = True
            print(f"FAIL {path}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"OK {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
