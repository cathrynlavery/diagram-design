#!/usr/bin/env python3
"""Self-check a generated diagram HTML file, with no third-party deps.

Ships inside the skill so an installed agent can verify its own output:

    python3 <skill-dir>/scripts/self_check.py my-diagram.html

Checks the accessible-SVG contract, the single-file safety rules (no remote
assets beyond the approved Google Fonts stylesheet, no executable attributes,
no scripts other than the one canonical motion controller), document
completeness (a truncated or mojibake file is rejected rather than passed),
painted content
staying inside each SVG's viewBox, and — when motion markup is present — the
structural motion contract. This is a distilled
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
VIEWBOX_TOLERANCE = 2.0
SVG_NUMBER = r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?"
SVG_NUMBER_RE = re.compile(SVG_NUMBER)
SVG_PLAIN_NUMBER_RE = re.compile(rf"^\s*{SVG_NUMBER}\s*$")
TRANSLATE_RE = re.compile(rf"^\s*translate\(\s*({SVG_NUMBER})(?:[\s,]+({SVG_NUMBER}))?\s*\)\s*$")
REPLACEMENT_CHAR = "\ufffd"
# Container elements whose end tag HTML requires, so an unmatched count is real damage: a
# file that stops mid-element, a dropped </text>, a stray </span>. Void elements and the
# optional-end-tag elements (html, head, body, p, li, ...) stay out, so valid HTML cannot
# trip the count; the closing </html> of the generated shell is checked separately.
PAIRED_CONTAINER_TAGS = (
    "title",
    "desc",
    "div",
    "section",
    "main",
    "article",
    "header",
    "footer",
    "figure",
    "figcaption",
    "svg",
    "g",
    "defs",
    "pattern",
    "marker",
    "style",
    "script",
    "span",
    "text",
    "tspan",
)
# Their children are not painted where they are declared, or use another coordinate system.
UNPAINTED_TAGS = {
    "defs",
    "symbol",
    "marker",
    "pattern",
    "clippath",
    "mask",
    "foreignobject",
    "svg",
}
# CSS that can move, hide or clip an element, so its painted position is not its attributes.
UNSTATIC_CSS_PROPERTIES = {
    "transform",
    "translate",
    "rotate",
    "scale",
    "display",
    "visibility",
    "x",
    "y",
    "cx",
    "cy",
    "r",
    "rx",
    "ry",
    "width",
    "height",
}
UNSTATIC_CSS_PREFIXES = ("animation", "offset", "clip", "mask")
CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_KEYFRAMES_RE = re.compile(
    r"@(?:-[a-z]+-)?keyframes[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}", re.IGNORECASE
)
CSS_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_STRING_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
CSS_PARENS_RE = re.compile(r"\([^()]*\)")
CSS_COMBINATOR_RE = re.compile(r"\s*[>+~]\s*|\s+")
CSS_TAG_RE = re.compile(r"^[a-zA-Z][\w-]*")
CSS_CLASS_RE = re.compile(r"\.([\w-]+)")
CSS_ID_RE = re.compile(r"#([\w-]+)")
CSS_ATTRIBUTE_RE = re.compile(r"\[\s*([\w:-]+)")
GEOMETRY_ATTRS = {
    "rect": ("x", "y", "width", "height"),
    "line": ("x1", "y1", "x2", "y2"),
    "circle": ("cx", "cy", "r"),
    "ellipse": ("cx", "cy", "rx", "ry"),
    "polygon": ("points",),
    "polyline": ("points",),
    "text": ("x", "y"),
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
        self.ids: Counter[str] = Counter()
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
        if data.get("id"):
            self.ids[data["id"]] += 1
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


class SvgExtent:
    def __init__(self, attrs: dict[str, str]) -> None:
        self.attrs = attrs
        self.points: list[tuple[float, float, str]] = []


def svg_length(attrs: dict[str, str], name: str, default: float | None = None) -> float | None:
    value = attrs.get(name)
    if value is None:
        return default
    return float(value) if SVG_PLAIN_NUMBER_RE.match(value) else None


def painted_points(tag: str, attrs: dict[str, str]) -> list[tuple[float, float]]:
    if tag == "rect":
        x, y = svg_length(attrs, "x", 0.0), svg_length(attrs, "y", 0.0)
        width, height = svg_length(attrs, "width"), svg_length(attrs, "height")
        if x is None or y is None or width is None or height is None:
            return []
        if width <= 0 or height <= 0:
            return []
        return [(x, y), (x + width, y + height)]
    if tag == "line":
        ends = [
            (svg_length(attrs, "x1", 0.0), svg_length(attrs, "y1", 0.0)),
            (svg_length(attrs, "x2", 0.0), svg_length(attrs, "y2", 0.0)),
        ]
        return [(x, y) for x, y in ends if x is not None and y is not None]
    if tag in {"circle", "ellipse"}:
        cx, cy = svg_length(attrs, "cx", 0.0), svg_length(attrs, "cy", 0.0)
        rx = svg_length(attrs, "r" if tag == "circle" else "rx")
        ry = svg_length(attrs, "r" if tag == "circle" else "ry")
        if cx is None or cy is None or rx is None or ry is None:
            return []
        if rx <= 0 or ry <= 0:
            return []
        return [(cx - rx, cy - ry), (cx + rx, cy + ry)]
    if tag in {"polygon", "polyline"}:
        numbers = [float(value) for value in SVG_NUMBER_RE.findall(attrs.get("points", ""))]
        return list(zip(numbers[0::2], numbers[1::2]))
    if tag == "text":
        x, y = svg_length(attrs, "x"), svg_length(attrs, "y")
        return [] if x is None or y is None else [(x, y)]
    return []


def declares_unstatic_css(declarations: str) -> bool:
    for declaration in declarations.split(";"):
        name = declaration.split(":", 1)[0].strip().casefold()
        if name in UNSTATIC_CSS_PROPERTIES or name.startswith(UNSTATIC_CSS_PREFIXES):
            return True
    return False


def selector_subjects(selector: str) -> list[tuple[str, set[str], set[str], set[str]]]:
    """Tag, classes, IDs and attribute names a selector's last compound requires."""
    subjects = []
    for alternative in CSS_PARENS_RE.sub("", CSS_STRING_RE.sub("", selector)).split(","):
        parts = [part for part in CSS_COMBINATOR_RE.split(alternative.strip()) if part]
        if not parts:
            continue
        compound = parts[-1].split("::", 1)[0]
        tag = CSS_TAG_RE.match(compound)
        subjects.append((
            tag.group(0).casefold() if tag else "",
            set(CSS_CLASS_RE.findall(compound)),
            set(CSS_ID_RE.findall(compound)),
            {name.casefold() for name in CSS_ATTRIBUTE_RE.findall(compound)},
        ))
    return subjects


def unstatic_css_subjects(source: str) -> list[tuple[str, set[str], set[str], set[str]]]:
    """Selector subjects of stylesheet rules that move, hide or clip what they match.

    Matching keeps only the last compound and drops pseudo-classes, so it can match more
    elements than the browser does. That only skips checks; it never adds a finding.
    """
    styles = re.findall(r"<style\b[^>]*>(.*?)</style\s*>", source, re.IGNORECASE | re.DOTALL)
    sheet = CSS_KEYFRAMES_RE.sub("", CSS_COMMENT_RE.sub("", "\n".join(styles)))
    subjects = []
    for selector, declarations in CSS_RULE_RE.findall(sheet):
        if declares_unstatic_css(declarations):
            subjects.extend(selector_subjects(selector))
    return subjects


def matches_subject(
    tag: str, attrs: dict[str, str], subject: tuple[str, set[str], set[str], set[str]]
) -> bool:
    subject_tag, classes, ids, attribute_names = subject
    if subject_tag not in {"", "*", tag}:
        return False
    if not classes <= set(attrs.get("class", "").split()):
        return False
    if not ids <= {attrs.get("id", "")}:
        return False
    return attribute_names <= set(attrs)


def child_offset(
    tag: str,
    attrs: dict[str, str],
    parent: tuple[float, float] | None,
    css_subjects: list[tuple[str, set[str], set[str], set[str]]],
) -> tuple[float, float] | None:
    """Offset of an element in viewBox units, or None when its paint is not static."""
    if parent is None or tag in UNPAINTED_TAGS:
        return None
    if declares_unstatic_css(attrs.get("style", "")):
        return None
    if attrs.get("display", "").strip().casefold() == "none":
        return None
    if attrs.get("visibility", "").strip().casefold() in {"hidden", "collapse"}:
        return None
    if attrs.get("clip-path", "none").strip().casefold() != "none":
        return None
    if attrs.get("mask", "none").strip().casefold() != "none":
        return None
    if any(matches_subject(tag, attrs, subject) for subject in css_subjects):
        return None
    transform = attrs.get("transform")
    if transform is None:
        return parent
    match = TRANSLATE_RE.match(transform)
    if match is None:
        return None
    return parent[0] + float(match.group(1)), parent[1] + float(match.group(2) or 0)


class ViewBoxParser(HTMLParser):
    def __init__(self, css_subjects: list[tuple[str, set[str], set[str], set[str]]]) -> None:
        super().__init__(convert_charrefs=True)
        self.svgs: list[SvgExtent] = []
        self._css_subjects = css_subjects
        self._frames: list[tuple[str, tuple[float, float] | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = {key.casefold(): value or "" for key, value in attrs}
        if not self._frames:
            if tag == "svg":
                self.svgs.append(SvgExtent(data))
                self._frames.append((tag, (0.0, 0.0)))
            return
        offset = child_offset(tag, data, self._frames[-1][1], self._css_subjects)
        self._frames.append((tag, offset))
        if offset is None:
            return
        label = " ".join(
            [f"<{tag}"]
            + [f'{name}="{data[name]}"' for name in GEOMETRY_ATTRS.get(tag, ()) if name in data]
        ) + ">"
        for x, y in painted_points(tag, data):
            self.svgs[-1].points.append((x + offset[0], y + offset[1], label))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        for index in range(len(self._frames) - 1, -1, -1):
            if self._frames[index][0] == tag:
                del self._frames[index:]
                return


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


class BalanceParser(HTMLParser):
    """Counts start and end tags as parsed, so attribute values and CDATA stay opaque.

    Reading the raw source with a regular expression instead would count tag-like text
    inside a quoted attribute or a stylesheet as markup, and report an imbalance the
    document does not have. A self-closing tag arrives as both a start and an end tag,
    so it balances itself.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.opens: Counter[str] = Counter()
        self.closes: Counter[str] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.opens[tag] += 1

    def handle_endtag(self, tag: str) -> None:
        self.closes[tag] += 1


def check_document_completeness(source: str, errors: list[str]) -> None:
    """Reject a document that is not whole: truncation, mojibake, unbalanced markup.

    The other checks read a document's contents; none of them notices that the document
    stopped early. A generated file that was cut off mid-write still satisfies the
    accessible-SVG contract for the part that survived, so this check reads the shape of
    the whole file instead.
    """
    if not source.casefold().rstrip().endswith("</html>"):
        errors.append("document does not end with </html>; the file looks truncated")

    replacements = source.count(REPLACEMENT_CHAR)
    if replacements:
        line = source[: source.index(REPLACEMENT_CHAR)].count("\n") + 1
        errors.append(
            f"contains {replacements} U+FFFD replacement character(s), first on line {line}:"
            " the file has mojibake or a truncated multi-byte character"
        )

    parser = BalanceParser()
    parser.feed(source)
    parser.close()
    for tag in PAIRED_CONTAINER_TAGS:
        opens, closes = parser.opens[tag], parser.closes[tag]
        if opens != closes:
            errors.append(
                f"<{tag}> opens {opens} time(s) and closes {closes} time(s);"
                " the document is not balanced"
            )


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
        for naming_id in dict.fromkeys((title_id, desc_id)):
            if parser.ids[naming_id] > 1:
                errors.append(f"duplicate accessible SVG naming ID {naming_id!r}")
        if labelled != [title_id, desc_id]:
            errors.append(f"svg {number} aria-labelledby must name title then desc")


def check_viewbox(source: str, errors: list[str]) -> None:
    parser = ViewBoxParser(unstatic_css_subjects(source))
    parser.feed(source)
    parser.close()
    checkable = [
        svg for svg in parser.svgs if svg.attrs.get("aria-hidden", "").casefold() != "true"
    ]
    for number, svg in enumerate(checkable, 1):
        box = [float(value) for value in SVG_NUMBER_RE.findall(svg.attrs.get("viewbox", ""))]
        if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
            continue
        left, top, width, height = box
        worst: dict[str, tuple[float, str]] = {}
        for x, y, label in svg.points:
            for side, overshoot in (
                ("left", left - x),
                ("top", top - y),
                ("right", x - (left + width)),
                ("bottom", y - (top + height)),
            ):
                if overshoot > VIEWBOX_TOLERANCE and overshoot > worst.get(side, (0.0, ""))[0]:
                    worst[side] = (overshoot, label)
        for side, (overshoot, label) in worst.items():
            errors.append(
                f"svg {number}: {label} paints {overshoot:g}px past the viewBox {side} edge "
                "and is clipped; grow the viewBox or move the content inside it"
            )


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


def verify(path: Path, offline: bool = False) -> list[str]:
    source = path.read_text(encoding="utf-8")
    parser = parsed_document(source)
    errors: list[str] = []
    errors.extend(parser.unsafe)
    check_document_completeness(source, errors)
    check_css_references(parser, errors)
    for tag, rel, value in parser.references:
        finding = reference_error(tag, rel, value)
        if finding:
            errors.append(finding)
        elif offline and is_approved_google_fonts_stylesheet(value.strip()):
            errors.append(
                "offline: file loads Google Fonts; remove the font <link> to use system fonts"
            )
    check_svgs(parser, errors)
    check_viewbox(source, errors)
    check_scripts(parser, errors)
    check_motion(parser, source, errors)
    return errors


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("files", nargs="+", type=Path)
    argument_parser.add_argument(
        "--offline",
        action="store_true",
        help="also fail on the Google Fonts link, for system-font output that makes no network requests",
    )
    args = argument_parser.parse_args()
    failed = False
    for path in args.files:
        try:
            errors = verify(path, offline=args.offline)
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
