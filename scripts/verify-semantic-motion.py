#!/usr/bin/env python3
"""Verify semantic-pattern routing and the animated example contract.

Uses only the Python standard library and never executes example JavaScript.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/diagram-design/SKILL.md"
PATTERNS = ROOT / "skills/diagram-design/references/semantic-patterns.md"
ANIMATION = ROOT / "skills/diagram-design/references/animation.md"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-policy-trace-animated.html"
MAX_SKILL_BYTES = 40_000
VISUAL_TYPE_COUNT = 39

PATTERN_NAMES = (
    "Fan-in queue / bottleneck",
    "Stage framework with semantic slots",
    "Unstructured input → structured artifact",
    "Paired policy-evaluation traces",
    "Secure paved road",
    "Governance / control catalog",
    "Compensating security layers",
)
PATTERN_FIELDS = (
    "Selection triggers:",
    "Required primitives:",
    "Complexity budget:",
    "Anti-patterns:",
    "Static fallback:",
    "Nearest visual type:",
)
MOTION_MODES = ("none", "reveal", "step", "loop")
MOTION_PRIMITIVES = (
    "Path draw",
    "Staggered reveal",
    "Queue counter",
    "Typing / field population",
    "Policy evaluation",
    "Flow token",
    "Containment",
    "Audit append",
)
CONTROL_ACTIONS = {"play", "pause", "replay", "prev", "next"}


def is_approved_google_fonts_stylesheet(value: str) -> bool:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.casefold() == "https"
        and parsed.hostname is not None
        and parsed.hostname.casefold() == "fonts.googleapis.com"
        and port in (None, 443)
        and parsed.path == "/css2"
        and not parsed.fragment
        and any(
            family.strip()
            for family in parse_qs(parsed.query, keep_blank_values=True).get("family", [])
        )
    )


class ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.controls: set[str] = set()
        self.motion_roots: list[dict[str, str]] = []
        self.motion_items: list[dict[str, str]] = []
        self.statuses: list[dict[str, str]] = []
        self.scripts: list[dict[str, str]] = []
        self.remote_assets: list[tuple[str, str]] = []
        self.trace_connectors: list[dict[str, str]] = []
        self.trace_b_terminals: list[dict[str, str]] = []
        self.trace_b_not_reached: list[dict[str, str]] = []
        self.trace_b_outcomes: list[dict[str, str]] = []
        self.svg_lines: list[dict[str, str]] = []
        self.noscript_count = 0
        self.svgs: list[dict[str, object]] = []
        self._svg_depth = 0
        self._current_svg: dict[str, object] | None = None
        self._capture: str | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        data = {name.casefold(): value or "" for name, value in attrs}
        if data.get("id"):
            self.ids.append(data["id"])
        if "data-motion-root" in data:
            self.motion_roots.append(data)
        if "data-motion-item" in data:
            self.motion_items.append(data)
        if data.get("data-motion-action"):
            self.controls.add(data["data-motion-action"])
        if data.get("role") == "status":
            self.statuses.append(data)
        if tag == "script":
            self.scripts.append(data)
        if tag == "noscript":
            self.noscript_count += 1
        if data.get("data-trace-connector") == "trace-b":
            self.trace_connectors.append(data)
        if data.get("data-trace-b-terminal") == "fail":
            self.trace_b_terminals.append(data)
        if data.get("data-trace-b-state") == "not-reached":
            self.trace_b_not_reached.append(data)
        if data.get("data-trace-b-outcome") == "denied":
            self.trace_b_outcomes.append(data)
        if tag == "line":
            self.svg_lines.append(data)

        for attr in ("src", "href"):
            value = data.get(attr, "").strip()
            try:
                parsed_value = urlparse(value)
                remote = parsed_value.scheme.casefold() in {"http", "https"} or bool(parsed_value.netloc)
            except ValueError:
                remote = True
            if value and remote:
                allowed_font = tag == "link" and attr == "href" and is_approved_google_fonts_stylesheet(value)
                if not allowed_font:
                    self.remote_assets.append((tag, value))

        if tag == "svg":
            self._svg_depth = 1
            self._current_svg = {
                "attrs": data,
                "first_child": None,
                "title": {"attrs": {}, "text": ""},
                "desc": {"attrs": {}, "text": ""},
            }
            self.svgs.append(self._current_svg)
            return
        if self._svg_depth:
            self._svg_depth += 1
            assert self._current_svg is not None
            if self._svg_depth == 2 and self._current_svg["first_child"] is None:
                self._current_svg["first_child"] = tag
            if tag in {"title", "desc"} and self._svg_depth == 2:
                self._current_svg[tag] = {"attrs": data, "text": ""}
                self._capture = tag

    def handle_endtag(self, tag: str) -> None:
        if self._svg_depth:
            if tag in {"title", "desc"}:
                self._capture = None
            self._svg_depth -= 1
            if self._svg_depth == 0:
                self._current_svg = None

    def handle_data(self, data: str) -> None:
        if self._capture and self._current_svg:
            node = self._current_svg[self._capture]
            assert isinstance(node, dict)
            node["text"] = str(node.get("text", "")) + data


def section(markdown: str, heading: str, next_heading: str | None) -> str:
    start = markdown.find(heading)
    if start < 0:
        return ""
    end = markdown.find(next_heading, start + len(heading)) if next_heading else -1
    return markdown[start:] if end < 0 else markdown[start:end]


def verify_markdown() -> list[str]:
    errors: list[str] = []
    skill_bytes = SKILL.read_bytes()
    skill = skill_bytes.decode("utf-8")
    patterns = PATTERNS.read_text(encoding="utf-8")
    animation = ANIMATION.read_text(encoding="utf-8")

    if len(skill_bytes) > MAX_SKILL_BYTES:
        errors.append(
            f"SKILL.md exceeds {MAX_SKILL_BYTES} bytes: {len(skill_bytes)} bytes"
        )
    if "Selection: semantic pattern, then visual type" not in skill:
        errors.append("SKILL.md must choose semantic pattern before visual type")
    router_position = skill.find("semantic-patterns.md")
    guide_heading = f"### Visual-type guide ({VISUAL_TYPE_COUNT})"
    guide_position = skill.find(guide_heading)
    if router_position < 0:
        errors.append("SKILL.md must link to semantic-patterns.md")
    if guide_position < 0:
        errors.append(
            f"SKILL.md must contain the {VISUAL_TYPE_COUNT}-row visual-type guide"
        )
    if router_position >= 0 and guide_position >= 0 and router_position > guide_position:
        errors.append("semantic-pattern router must precede the visual-type guide")

    visual_guide = section(skill, guide_heading, "Rules of thumb:")
    visual_rows = re.findall(r"^\|.*\[type-[^)]+\.md\]", visual_guide, re.MULTILINE)
    if len(visual_rows) != VISUAL_TYPE_COUNT:
        errors.append(
            f"visual-type guide must preserve {VISUAL_TYPE_COUNT} rows; found {len(visual_rows)}"
        )

    for index, name in enumerate(PATTERN_NAMES, 1):
        if name not in skill:
            errors.append(f"SKILL.md does not route semantic pattern: {name}")
        next_heading = f"## {index + 1}." if index < len(PATTERN_NAMES) else "## Composition rules"
        block = section(patterns, f"## {index}. {name}", next_heading)
        if not block:
            errors.append(f"semantic-patterns.md is missing section {index}: {name}")
            continue
        for field in PATTERN_FIELDS:
            if f"**{field}**" not in block:
                errors.append(f"{name} is missing required field {field}")

    for mode in MOTION_MODES:
        if f"`{mode}`" not in animation:
            errors.append(f"animation.md is missing mode {mode}")
    for primitive in MOTION_PRIMITIVES:
        if f"**{primitive}**" not in animation:
            errors.append(f"animation.md is missing primitive {primitive}")

    required_animation_terms = (
        "prefers-reduced-motion",
        "CSS-only",
        "inline JavaScript",
        "Play, Pause, Replay, Previous, and Next",
        "deterministic",
        "static",
        "color-only",
        "screenshot",
        "export",
    )
    for term in required_animation_terms:
        if term not in animation:
            errors.append(f"animation.md is missing contract term {term!r}")
    return errors


def verify_example(path: Path = EXAMPLE) -> list[str]:
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    parser = ContractParser()
    parser.feed(source)
    parser.close()

    duplicates = sorted(name for name, count in Counter(parser.ids).items() if count > 1)
    if duplicates:
        errors.append("duplicate HTML/SVG IDs: " + ", ".join(duplicates))
    if parser.remote_assets:
        errors.append(f"remote dependencies other than allowed fonts: {parser.remote_assets}")
    if len(parser.scripts) != 1:
        errors.append(f"expected one minimal inline control script; found {len(parser.scripts)}")
    else:
        script = parser.scripts[0]
        if script.get("src"):
            errors.append("remote or file-based scripts are forbidden")
        if "data-diagram-controls" not in script:
            errors.append("inline script must be scoped with data-diagram-controls")

    if len(parser.motion_roots) != 1:
        errors.append(f"expected one motion root; found {len(parser.motion_roots)}")
    else:
        root = parser.motion_roots[0]
        if root.get("data-motion-mode") != "step":
            errors.append("working example must use step mode")
        if root.get("data-static-frame") != "complete":
            errors.append("motion root must declare a complete static fallback")
        if root.get("data-frame") != "static":
            errors.append("source first frame must be static")

    missing_controls = CONTROL_ACTIONS - parser.controls
    if missing_controls:
        errors.append("missing controls: " + ", ".join(sorted(missing_controls)))
    if not parser.statuses:
        errors.append("interactive example needs accessible status text")
    else:
        status = parser.statuses[0]
        if status.get("aria-live") != "polite" or status.get("aria-atomic") != "true":
            errors.append("status needs aria-live=polite and aria-atomic=true")
    if parser.noscript_count != 1:
        errors.append("example needs one explicit no-JavaScript fallback")

    if (
        len(parser.trace_connectors) != 1
        or len(parser.trace_b_terminals) != 1
        or len(parser.trace_b_not_reached) != 2
        or len(parser.trace_b_outcomes) != 1
    ):
        errors.append(
            "Trace B needs one persistent connector, one terminal FAIL, "
            "two NOT REACHED rows, and one denied outcome"
        )
    else:
        connector = parser.trace_connectors[0]
        terminal = parser.trace_b_terminals[0]
        not_reached = parser.trace_b_not_reached
        outcome = parser.trace_b_outcomes[0]
        try:
            connector_end = float(connector["y2"])
            fail_end = float(terminal["y"]) + float(terminal["height"])
            later_starts = [float(node["y"]) for node in not_reached] + [float(outcome["y"])]
            connector_x = float(connector["x1"])
            vertical = connector_x == float(connector["x2"])
            continuations = [
                line
                for line in parser.svg_lines
                if line is not connector
                and float(line.get("x1", "nan")) == connector_x
                and float(line.get("x2", "nan")) == connector_x
                and max(float(line.get("y1", "nan")), float(line.get("y2", "nan"))) > fail_end
            ]
        except (KeyError, ValueError):
            errors.append("Trace B structural coordinates must be numeric")
        else:
            if (
                not vertical
                or connector_end != fail_end
                or any(connector_end >= start for start in later_starts)
                or continuations
            ):
                errors.append(
                    "Trace B persistent connector must terminate at the first FAIL "
                    "before NOT REACHED rows and the denied outcome"
                )

    steps: list[int] = []
    for item in parser.motion_items:
        try:
            step = int(item.get("data-step", ""))
        except ValueError:
            errors.append("every motion item needs an integer data-step")
            continue
        if "data-motion-decorative" in item:
            if item.get("aria-hidden") != "true" or item.get("focusable") != "false":
                errors.append(
                    "decorative motion items need aria-hidden=true and focusable=false"
                )
            continue
        steps.append(step)
        if not item.get("aria-label", "").strip():
            errors.append("every semantic motion item needs an aria-label")
    if steps != [1, 2, 3, 4, 5]:
        errors.append(f"policy steps must be exactly [1, 2, 3, 4, 5]; found {steps}")

    if len(parser.svgs) != 1:
        errors.append(f"expected one SVG; found {len(parser.svgs)}")
    else:
        svg = parser.svgs[0]
        attrs = svg["attrs"]
        title = svg["title"]
        desc = svg["desc"]
        assert isinstance(attrs, dict) and isinstance(title, dict) and isinstance(desc, dict)
        title_attrs = title.get("attrs", {})
        desc_attrs = desc.get("attrs", {})
        labelled = attrs.get("aria-labelledby", "").split()
        if attrs.get("role") != "img" or svg["first_child"] != "title":
            errors.append("SVG needs role=img and title as first child")
        if not str(title.get("text", "")).strip() or not str(desc.get("text", "")).strip():
            errors.append("SVG title and description must be non-empty")
        if not isinstance(title_attrs, dict) or not isinstance(desc_attrs, dict):
            errors.append("SVG title/description attributes could not be parsed")
        elif labelled != [title_attrs.get("id"), desc_attrs.get("id")]:
            errors.append("SVG aria-labelledby must resolve to title then description")

    required_source = {
        "@media (prefers-reduced-motion: reduce)": "reduced-motion fallback",
        "@media print": "print/static fallback",
        'data-static-frame="complete"': "complete source fallback",
        "?motion=static": "static query documentation",
        "params.get('motion') === 'static'": "static screenshot path",
        "document.fonts.ready": "font-stable screenshot hook",
        "visibilitychange": "background pause",
        "ArrowRight": "right-arrow keyboard path",
        "ArrowLeft": "left-arrow keyboard path",
        "event.code === 'Space'": "space play/pause path",
        "Home": "home/reset keyboard path",
        "toLowerCase() === 'r'": "replay keyboard path",
        "window.setTimeout": "deterministic timer",
        "requestedStep !== null": "non-null test-step validation",
        "Number.isSafeInteger(parsedStep)": "integer test-step validation",
        "parsedStep <= count": "bounded test-step validation",
        "playback controls unavailable": "static/reduced-motion browser status",
        "PASS": "pass text state",
        "FAIL": "fail text state",
        "SKIPPED": "skipped text state",
        "NOT REACHED": "not-reached text state",
        "FIRST DIVERGENCE": "first-divergence marker",
    }
    for needle, label in required_source.items():
        if needle not in source:
            errors.append(f"missing {label}: {needle}")
    if "setInterval" in source or "Math.random" in source:
        errors.append("motion timing must not use setInterval or randomness")
    if re.search(r"<script\b[^>]*\bsrc\s*=", source, re.IGNORECASE):
        errors.append("example must not load any remote script")
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    group = argument_parser.add_mutually_exclusive_group()
    group.add_argument("--markdown-only", action="store_true")
    group.add_argument("--example-only", action="store_true")
    args = argument_parser.parse_args()
    errors = (
        verify_markdown()
        if args.markdown_only
        else verify_example()
        if args.example_only
        else verify_markdown() + verify_example()
    )
    if errors:
        print("Semantic/motion verification failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    if not args.example_only:
        print(
            f"OK: 7 semantic patterns route independently to the preserved "
            f"{VISUAL_TYPE_COUNT} visual types"
        )
        print("OK: animation modes, primitives, static fallback, and accessibility contract")
    if not args.markdown_only:
        print("OK: policy-trace example controls, structure, reduced motion, and unique IDs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
