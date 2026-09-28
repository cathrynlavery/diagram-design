#!/usr/bin/env python3
"""Verify the optional diagram-motion contract with no third-party deps."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
MOTION_TEMPLATE = ASSET_DIR / "template-motion.html"
MODES = {"none", "reveal", "step", "loop"}
ACTIONS = {"play", "pause", "replay", "prev", "next"}
ASCII_DECIMAL_RE = re.compile(r"^[0-9]+$")


class MotionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.roots: list[dict[str, str]] = []
        self.items: list[dict[str, str]] = []
        self.actions: set[str] = set()
        self.controls = 0
        self.statuses: list[dict[str, str]] = []
        self.statuses_in_controls = 0
        self.scripts: list[dict[str, object]] = []
        self.styles: list[dict[str, object]] = []
        self.svgs: list[dict[str, object]] = []
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._capture: str | None = None
        self._current_script: dict[str, object] | None = None
        self._current_style: dict[str, object] | None = None
        self._element_stack: list[str] = []
        self._motion_root_depth: int | None = None
        self._controls_depth: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        normalized_attrs = [(key.casefold(), value or "") for key, value in attrs]
        data = {key: value for key, value in normalized_attrs}
        if "data-motion-root" in data:
            self.roots.append(data)
            if self._motion_root_depth is None:
                self._motion_root_depth = len(self._element_stack)
        in_motion_root = self._motion_root_depth is not None
        if in_motion_root:
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
            self._current_style = {"body": [], "closed": False}
            self.styles.append(self._current_style)
        self._element_stack.append(tag)
        # Match self_check.py: a nested <svg> (such as an icon) belongs to the
        # root diagram, and only the root's direct <title>/<desc> name it.
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
        if tag == "style" and self._current_style is not None:
            self._current_style["closed"] = True
            self._current_style = None
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
        if self._current_style is not None:
            body = self._current_style["body"]
            assert isinstance(body, list)
            body.append(data)
        if self._capture and self._current_svg:
            node = self._current_svg[self._capture]
            assert isinstance(node, dict)
            node["text"] = str(node.get("text", "")) + data


def normalized_controller(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def parsed_document(source: str) -> MotionParser:
    parser = MotionParser()
    parser.feed(source)
    parser.close()
    return parser


def without_comments(source: str) -> str:
    """Remove JS/CSS comments while preserving quoted strings and regex literals."""
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(source):
        character = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if quote is not None:
            output.append(character)
            if character == "\\" and index + 1 < len(source):
                index += 1
                output.append(source[index])
            elif character == quote:
                quote = None
        elif character in {"'", '"', "`"}:
            quote = character
            output.append(character)
        elif character == "/" and following == "*":
            index += 2
            while index < len(source) - 1 and source[index : index + 2] != "*/":
                if source[index] in "\r\n":
                    output.append(source[index])
                index += 1
            index += 1
        elif character == "/" and following == "/":
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            if index < len(source):
                output.append(source[index])
        else:
            output.append(character)
        index += 1
    return "".join(output)


def parsed_bodies(blocks: list[dict[str, object]]) -> str:
    bodies = []
    for block in blocks:
        body = block["body"]
        assert isinstance(body, list)
        bodies.append("".join(body))
    return without_comments("\n".join(bodies))


def css_at_rule_blocks(source: str, header_pattern: str) -> list[str]:
    """Return balanced bodies for CSS at-rules whose headers match a pattern."""
    blocks: list[str] = []
    for match in re.finditer(header_pattern + r"\s*\{", source, re.IGNORECASE):
        depth = 1
        index = match.end()
        start = index
        while index < len(source) and depth:
            if source[index] == "{":
                depth += 1
            elif source[index] == "}":
                depth -= 1
            index += 1
        if depth == 0:
            blocks.append(source[start : index - 1])
    return blocks


def hidden_unscoped_motion_selectors(source: str) -> list[str]:
    """Find selectors that hide motion items before progressive enhancement."""
    hidden_declaration = re.compile(
        r"(?:opacity\s*:\s*(?:0+(?:\.0*)?|\.0+)\b|"
        r"visibility\s*:\s*hidden\b|display\s*:\s*none\b)",
        re.IGNORECASE,
    )
    findings: list[str] = []
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", source, re.DOTALL):
        if not hidden_declaration.search(rule.group(2)):
            continue
        for selector in rule.group(1).split(","):
            item = re.search(r"\[\s*data-motion-item\s*\]", selector, re.IGNORECASE)
            if item is None:
                continue
            if ".motion-ready" not in selector[: item.start()]:
                findings.append(" ".join(selector.split()))
    return findings


def infinite_unscoped_selectors(source: str) -> list[str]:
    """Find infinite animation rules that are not limited to loop mode."""
    infinite_declaration = re.compile(
        r"(?:animation\s*:[^;}]*\binfinite\b|"
        r"animation-iteration-count\s*:\s*infinite\b)",
        re.IGNORECASE,
    )
    loop_scope = re.compile(
        r"\[\s*data-motion-mode\s*=\s*['\"]loop['\"]\s*\]",
        re.IGNORECASE,
    )
    findings: list[str] = []
    for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", source, re.DOTALL):
        if not infinite_declaration.search(rule.group(2)):
            continue
        for selector in rule.group(1).split(","):
            if loop_scope.search(selector) is None:
                findings.append(" ".join(selector.split()))
    return findings


def canonical_controller() -> str:
    parser = parsed_document(MOTION_TEMPLATE.read_text(encoding="utf-8"))
    if len(parser.scripts) != 1 or not parser.scripts[0]["closed"]:
        raise RuntimeError("template-motion.html must contain one closed controller")
    body = parser.scripts[0]["body"]
    assert isinstance(body, list)
    return normalized_controller("".join(body))


def shipped_motion_files() -> list[Path]:
    """Enumerate named and parsed motion HTML assets deterministically."""
    named = set(ASSET_DIR.glob("template-motion*.html"))
    named.update(ASSET_DIR.glob("example-*-animated*.html"))
    parsed = set()
    for path in ASSET_DIR.glob("*.html"):
        try:
            document = parsed_document(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        has_motion_controller = any(
            isinstance(script["attrs"], dict)
            and "data-diagram-controls" in script["attrs"]
            for script in document.scripts
        )
        if document.roots or has_motion_controller:
            parsed.add(path)
    return sorted(named | parsed, key=lambda path: path.as_posix())


def verify(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    parser = parsed_document(source)
    errors: list[str] = []

    if len(parser.roots) != 1:
        errors.append(f"expected exactly one data-motion-root; found {len(parser.roots)}")
        return errors

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
    steps: list[int] = []
    semantic_steps: list[int] = []
    for index, item in enumerate(parser.items, 1):
        raw_step = item.get("data-step", "")
        if not ASCII_DECIMAL_RE.fullmatch(raw_step):
            errors.append(
                f"motion item {index} has a non-ASCII-decimal data-step"
            )
            continue
        step = int(raw_step)
        steps.append(step)
        decorative = "data-motion-decorative" in item
        if not decorative:
            semantic_steps.append(step)
            if not item.get("aria-label", "").strip():
                errors.append(f"semantic motion item {index} needs a non-color aria-label")
        else:
            if item.get("aria-hidden") != "true" or item.get("focusable") != "false":
                errors.append(f"decorative motion item {index} needs aria-hidden=true and focusable=false")
        inline = item.get("style", "").replace(" ", "").lower()
        if any(token in inline for token in ("display:none", "visibility:hidden", "opacity:0")):
            errors.append(f"motion item {index} is hidden in source; fallback must be visible")

    expected = set(range(1, count + 1)) if count > 0 else set()
    if set(semantic_steps) != expected:
        errors.append(f"semantic steps must be contiguous 1..{count}; found {sorted(set(semantic_steps))}")
    crowded = {step: number for step, number in Counter(semantic_steps).items() if number > 2}
    if crowded:
        errors.append(f"no more than two semantic items may share a step; found {crowded}")
    if steps and (min(steps) < 1 or (count > 0 and max(steps) > count)):
        errors.append("motion item data-step falls outside declared step count")

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
            if status.get("role") != "status" or status.get("aria-live") != "polite" or status.get("aria-atomic") != "true":
                errors.append("motion status needs role=status, aria-live=polite, aria-atomic=true")
            if parser.statuses_in_controls:
                errors.append(
                    "motion status must be outside data-motion-controls so hidden controls do not hide live announcements"
                )
        if not parser.scripts:
            errors.append("controlled mode needs the scoped control script")

    if mode in {"none", "loop"} and parser.scripts:
        errors.append(f"{mode} mode must be script-free")
    if mode in {"none", "loop"} and (parser.controls or parser.actions or parser.statuses):
        errors.append(f"{mode} mode must not expose playback controls or live status")
    if mode == "loop":
        semantic_count = sum(
            1 for item in parser.items if "data-motion-decorative" not in item
        )
        decorative_count = len(parser.items) - semantic_count
        if semantic_count > 1 or decorative_count > 1:
            errors.append(
                "loop mode allows at most one semantic item and one decorative token"
            )
    if len(parser.scripts) > 1:
        errors.append(f"motion document may contain at most one script; found {len(parser.scripts)}")
    for number, script in enumerate(parser.scripts, 1):
        attrs = script["attrs"]
        attr_names = script["attr_names"]
        body = script["body"]
        assert isinstance(attrs, dict) and isinstance(attr_names, list) and isinstance(body, list)
        if not script["closed"]:
            errors.append(f"script {number} must have a closing script tag")
        if attr_names != ["data-diagram-controls"] or attrs.get("data-diagram-controls") != "":
            errors.append(
                f"script {number} must carry only the canonical data-diagram-controls attribute"
            )
        if normalized_controller("".join(body)) != canonical_controller():
            errors.append(
                f"script {number} must exactly match the controller in template-motion.html"
            )

    script_source = parsed_bodies(parser.scripts)
    style_source = parsed_bodies(parser.styles)
    reduced_motion_css = "\n".join(
        css_at_rule_blocks(
            style_source,
            r"@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)",
        )
    )
    print_css = css_at_rule_blocks(style_source, r"@media\s+print\b")

    if not reduced_motion_css:
        errors.append("missing reduced-motion CSS fallback (prefers-reduced-motion)")
    if not print_css:
        errors.append("missing print CSS fallback (@media print)")

    required_css = {
        r"\[data-motion-controls\]\s*\{[^{}]*display\s*:\s*none\s*!important": (
            reduced_motion_css,
            "reduced-motion hidden controls",
            "[data-motion-controls] { display: none !important; }",
        ),
        r"\[data-motion-controls\]\[hidden\]\s*\{[^{}]*display\s*:\s*none\s*!important": (
            style_source,
            "hidden control override",
            "[data-motion-controls][hidden] { display: none !important; }",
        ),
        r"html\[data-motion\s*=\s*['\"]static['\"]\]": (
            style_source,
            "deterministic static override",
            'data-motion="static"',
        ),
    }
    if parser.scripts:
        for pattern, (scope, label, example) in required_css.items():
            if re.search(pattern, scope, re.IGNORECASE | re.DOTALL) is None:
                errors.append(f"missing {label} ({example})")

    required_script: dict[str, str] = {}
    if parser.scripts:
        required_script.update(
            {
                "motion') === 'step'": "deterministic step override",
                "document.fonts": "font-stable screenshot hook",
                "visibilitychange": "background-tab pause",
                "ArrowRight": "keyboard stepping",
                "!event.ctrlKey && !event.metaKey && !event.altKey": "modified-shortcut guard",
                "motion-ready": "progressive enhancement class",
                "requestedStep !== null": "non-null test frame validation",
                "/^\\d+$/.test(requestedStep)": "non-negative decimal test frame validation",
                "Number.isSafeInteger(parsedStep)": "integer test frame validation",
                "parsedStep <= count": "bounded test frame validation",
                "if (step >= count) { finish(); return; }": "immediate final-step stop",
                "playback controls unavailable": "static/reduced-motion status",
            }
        )
    for needle, label in required_script.items():
        if needle not in script_source:
            errors.append(f"missing {label} ({needle})")
    ready_position = script_source.find("root.classList.add('motion-ready');")
    initialization_position = script_source.find("if (staticOverride)")
    if (
        parser.scripts
        and ready_position >= 0
        and initialization_position >= 0
        and ready_position < initialization_position
    ):
        errors.append("motion-ready must be added only after the initial render succeeds")

    unscoped_selectors = hidden_unscoped_motion_selectors(style_source)
    if unscoped_selectors:
        errors.append(
            "unscoped data-motion-item hiding breaks the no-JS fallback: "
            + ", ".join(unscoped_selectors)
        )
    infinite_selectors = infinite_unscoped_selectors(style_source)
    if infinite_selectors:
        errors.append(
            "infinite animation must be scoped to data-motion-mode=loop: "
            + ", ".join(infinite_selectors)
        )
    if mode == "loop" and len(parser.items) > 2:
        errors.append("loop mode may contain at most one semantic item and one decorative token")

    if not parser.svgs:
        errors.append("motion document needs an accessible SVG")
    for number, svg in enumerate(parser.svgs, 1):
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
        if svg["first"] != "title":
            errors.append(f"svg {number} title must be its first child")
        if not str(title.get("text", "")).strip() or not str(desc.get("text", "")).strip():
            errors.append(f"svg {number} needs non-empty title and desc")
        if not isinstance(title_attrs, dict) or not isinstance(desc_attrs, dict) or labelled != [title_attrs.get("id"), desc_attrs.get("id")]:
            errors.append(f"svg {number} aria-labelledby must name title then desc")

    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("files", nargs="*", type=Path)
    argument_parser.add_argument(
        "--shipped",
        action="store_true",
        help="verify every named or parsed motion HTML asset shipped by the repository",
    )
    args = argument_parser.parse_args()
    files = list(args.files)
    if args.shipped:
        files.extend(shipped_motion_files())
    files = list(dict.fromkeys(files))
    if not files:
        argument_parser.error("provide files or use --shipped")
    failed = False
    for path in files:
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
