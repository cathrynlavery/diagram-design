#!/usr/bin/env python3
"""Lint NEW and CHANGED diagram examples against the current visual skin.

Pre-2.0 examples may legitimately fail because they were built against an older
skin. Use ``--all --baseline`` to skip those documented legacy files.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent.parent
STYLE_GUIDE = ROOT / "skills/diagram-design/references/style-guide.md"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
BASELINE = ROOT / "scripts/lint-skin-baseline.txt"
MOTION_TEMPLATE = ASSET_DIR / "template-motion.html"

HEX_RE = re.compile(
    r"(?<![\w-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)
RGBA_RE = re.compile(
    r"rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([^)]+)\)",
    re.IGNORECASE,
)
BLACK_RGB_RE = re.compile(r"rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)", re.IGNORECASE)
SCRIPT_OPEN_RE = re.compile(r"<script\b(?P<attrs>[^>]*)>", re.IGNORECASE | re.DOTALL)
SCRIPT_BLOCK_RE = re.compile(
    r"<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)
SRC_HTTP_RE = re.compile(r"\bsrc\s*=\s*(['\"])\s*(?:https?:)?//", re.IGNORECASE)
IMPORT_HTTP_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(?:['\"]\s*)?(?:https?:)?//", re.IGNORECASE
)
URL_HTTP_RE = re.compile(r"url\(\s*(?:['\"]\s*)?(?:https?:)?//", re.IGNORECASE)
IMPORT_ANY_RE = re.compile(r"@import\b", re.IGNORECASE)
URL_ANY_RE = re.compile(r"url\(\s*([^)]+?)\s*\)", re.IGNORECASE)
LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"\bhref\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
REL_RE = re.compile(r"\brel\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
FONT_CSS_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
FONT_ATTR_RE = re.compile(
    r"\bfont-family\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL
)

ALLOWED_FONTS = {
    "instrument serif",
    "geist",
    "geist mono",
    "hiragino sans",
    "noto sans jp",
    "yu gothic",
    "noto sans mono cjk jp",
    "apple sd gothic neo",
    "noto sans kr",
    "malgun gothic",
    "noto sans mono cjk kr",
    "system-ui",
    "sans-serif",
    "serif",
    "monospace",
    "ui-monospace",
}
CSS_FONT_KEYWORDS = {"inherit", "initial", "revert", "revert-layer", "unset"}


def normalized_controller(body):
    """Return a platform-stable representation of an inline controller."""
    return body.replace("\r\n", "\n").replace("\r", "\n").strip()


def canonical_controller_digest():
    """Hash the one reviewed controller shipped by the motion template."""
    source = MOTION_TEMPLATE.read_text(encoding="utf-8")
    blocks = list(SCRIPT_BLOCK_RE.finditer(source))
    if len(blocks) != 1:
        raise RuntimeError("template-motion.html must contain exactly one controller")
    body = normalized_controller(blocks[0].group("body"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def google_fonts_families(url):
    """Return exact families from an approved Google Fonts css2 stylesheet."""
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return set()
    if (
        parsed.scheme.casefold() != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != "fonts.googleapis.com"
        or port not in (None, 443)
        or parsed.path != "/css2"
        or parsed.fragment
    ):
        return set()
    families = set()
    for value in parse_qs(parsed.query, keep_blank_values=True).get("family", []):
        family = value.split(":", 1)[0].strip()
        if family:
            families.add(family.casefold())
    return families


class ResourceParser(HTMLParser):
    """Collect remote resource dependencies without executing the document."""

    RESOURCE_ATTRS = {
        "base": ("href",),
        "link": ("href",),
        "script": ("src",),
        "img": ("src", "srcset"),
        "iframe": ("src",),
        "object": ("data",),
        "embed": ("src",),
        "image": ("href", "xlink:href"),
        "use": ("href", "xlink:href"),
        "video": ("src", "poster"),
        "audio": ("src",),
        "source": ("src", "srcset"),
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.remote: list[tuple[int, str, str, str]] = []
        self.executable: list[tuple[int, str, str]] = []
        self.fonts: set[str] = set()

    @staticmethod
    def is_remote(value):
        try:
            parsed = urlparse(value.strip())
        except ValueError:
            return True
        return bool(parsed.scheme) or bool(parsed.netloc)

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        data = {name.casefold(): value or "" for name, value in attrs}
        line, _column = self.getpos()
        for name, value in data.items():
            compact = "".join(character for character in value if ord(character) > 32).casefold()
            if (
                name.startswith("on")
                or name == "srcdoc"
                or tag == "base"
                or compact.startswith("javascript:")
                or compact.startswith("data:text/html")
            ):
                self.executable.append((line, tag, name))
        for attr in self.RESOURCE_ATTRS.get(tag, ()):
            value = data.get(attr, "").strip()
            candidates = (
                [item.strip().split()[0] for item in value.split(",") if item.strip()]
                if attr == "srcset"
                else [value]
            )
            for candidate in candidates:
                if not candidate or not self.is_remote(candidate):
                    continue
                rel = data.get("rel", "").casefold().split()
                approved_fonts = (
                    google_fonts_families(candidate)
                    if tag == "link" and attr == "href" and "stylesheet" in rel
                    else set()
                )
                if approved_fonts:
                    self.fonts.update(approved_fonts)
                else:
                    self.remote.append((line, tag, attr, candidate))


def style_guide_families():
    """Read only the Family cells in the style guide's Typography table."""
    markdown = STYLE_GUIDE.read_text(encoding="utf-8")
    match = re.search(
        r"^## Typography\s*$.*?^\| Role \| Family \|.*?\n(?P<rows>.*?)(?=^### |^## |\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return set()
    families = set()
    for line in match.group("rows").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].startswith("`"):
            continue
        family_stack = re.sub(r"\s*\([^)]*\)\s*$", "", cells[1]).strip(" `*")
        family_stack = re.sub(r"\s+\*[^*]+\*\s*$", "", family_stack).strip()
        for family in family_stack.split(","):
            family = family.strip().strip("'\"")
            if family:
                families.add(family.casefold())
    return families


@dataclass
class SvgTextElement:
    tag: str
    element_id: str | None
    line: int
    offset: int
    text: list[str] = field(default_factory=list)


@dataclass
class SvgElement:
    attrs: dict[str, str | None]
    line: int
    offset: int
    content_depth: int
    first_child: str | None = None
    ids: set[str] = field(default_factory=set)
    bare_id_locations: list[tuple[int, int]] = field(default_factory=list)
    titles: list[SvgTextElement] = field(default_factory=list)
    descriptions: list[SvgTextElement] = field(default_factory=list)


class AccessibleSvgParser(HTMLParser):
    """Collect accessible-name data without rendering or executing HTML.

    Trust boundary: input files are untrusted source text. ``HTMLParser`` only
    tokenizes that text; this linter never evaluates scripts, fetches URLs, or
    opens referenced resources.
    """

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.line_offsets = [0]
        self.line_offsets.extend(
            match.end() for match in re.finditer(r"\n", text)
        )
        self.element_stack = []
        self.svg_stack = []
        self.svgs = []
        self.open_text = []
        self.id_locations = {}

    def source_offset(self):
        line, column = self.getpos()
        return self.line_offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        attr_map = {name.casefold(): value for name, value in attrs}
        offset = self.source_offset()
        line, _column = self.getpos()
        element_id = attr_map.get("id")
        if element_id:
            self.id_locations.setdefault(element_id, []).append((line, offset))

        if self.svg_stack:
            parent = self.svg_stack[-1]
            if len(self.element_stack) == parent.content_depth:
                if parent.first_child is None:
                    parent.first_child = tag
            if element_id:
                for svg in self.svg_stack:
                    svg.ids.add(element_id)
                    if element_id in {"title", "desc"}:
                        svg.bare_id_locations.append((line, offset))

        if tag == "svg":
            svg = SvgElement(
                attrs=attr_map,
                line=line,
                offset=offset,
                content_depth=len(self.element_stack) + 1,
            )
            self.svgs.append(svg)
            self.svg_stack.append(svg)
        elif tag in {"title", "desc"} and self.svg_stack:
            svg = self.svg_stack[-1]
            if len(self.element_stack) == svg.content_depth:
                element = SvgTextElement(
                    tag=tag,
                    element_id=attr_map.get("id"),
                    line=line,
                    offset=offset,
                )
                if tag == "title":
                    svg.titles.append(element)
                else:
                    svg.descriptions.append(element)
                self.open_text.append(element)

        self.element_stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.casefold()
        for index in range(len(self.open_text) - 1, -1, -1):
            if self.open_text[index].tag == tag:
                del self.open_text[index]
                break

        if tag == "svg" and self.svg_stack:
            self.svg_stack.pop()

        for index in range(len(self.element_stack) - 1, -1, -1):
            if self.element_stack[index] == tag:
                del self.element_stack[index:]
                break

    def handle_data(self, data):
        for element in self.open_text:
            element.text.append(data)


def lint_accessible_svgs(text, expected_slug, allow_template_placeholders=False):
    parser = AccessibleSvgParser(text)
    parser.feed(text)
    parser.close()
    findings = []

    def add(line, offset, message):
        findings.append((line, offset, "a11y", message))

    naming_ids = {
        element.element_id
        for svg in parser.svgs
        if (svg.attrs.get("aria-hidden") or "").casefold() != "true"
        for element in svg.titles + svg.descriptions
        if element.element_id
    }
    for element_id in sorted(naming_ids):
        locations = parser.id_locations[element_id]
        if len(locations) > 1:
            line, offset = locations[1]
            add(line, offset, f'duplicate accessible-name id="{element_id}" is not allowed')

    for svg in parser.svgs:
        aria_hidden = (svg.attrs.get("aria-hidden") or "").casefold()
        if aria_hidden == "true":
            continue

        if (svg.attrs.get("role") or "").casefold() != "img":
            add(svg.line, svg.offset, 'diagram <svg> must carry role="img"')

        viewbox = svg.attrs.get("viewbox")  # HTMLParser lowercases all attribute names
        if not viewbox:
            add(svg.line, svg.offset, "diagram <svg> must have a viewBox attribute")
        else:
            parts = re.split(r"[\s,]+", viewbox.strip())
            valid = False
            _svg_num_re = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")
            if len(parts) == 4 and all(_svg_num_re.match(p) for p in parts):
                try:
                    nums = [float(p) for p in parts]
                    valid = (
                        all(math.isfinite(n) for n in nums)
                        and nums[2] > 0
                        and nums[3] > 0
                    )
                except ValueError:
                    pass
            if not valid:
                add(
                    svg.line,
                    svg.offset,
                    f'viewBox "{viewbox}" is not valid (expected "min-x min-y width height" with positive size)',
                )

        labelled_by = (svg.attrs.get("aria-labelledby") or "").split()
        accessible_name_ids = labelled_by + [
            element.element_id
            for element in svg.titles + svg.descriptions
            if element.element_id
        ]
        placeholder_ids = list(
            dict.fromkeys(
                element_id
                for element_id in accessible_name_ids
                if "[" in element_id or "]" in element_id
            )
        )
        allowed_placeholders = {"[diagram-slug]-title", "[diagram-slug]-desc"}
        if placeholder_ids and (
            not allow_template_placeholders
            or not set(placeholder_ids).issubset(allowed_placeholders)
        ):
            add(
                svg.line,
                svg.offset,
                "accessible-name IDs contain unresolved placeholder(s): "
                + ", ".join(placeholder_ids),
            )
        if not labelled_by:
            add(
                svg.line,
                svg.offset,
                "aria-labelledby must name the <title> and <desc>",
            )
        else:
            missing_ids = [
                element_id for element_id in labelled_by if element_id not in svg.ids
            ]
            if missing_ids:
                add(
                    svg.line,
                    svg.offset,
                    "aria-labelledby references missing id(s): "
                    + ", ".join(missing_ids),
                )

        title = svg.titles[0] if svg.titles else None
        description = svg.descriptions[0] if svg.descriptions else None
        if title is None:
            add(svg.line, svg.offset, "diagram <svg> must contain a <title>")
        else:
            if svg.first_child != "title":
                add(
                    title.line,
                    title.offset,
                    "<title> must be the first child element of <svg>",
                )
            title_text = "".join(title.text).strip()
            if not title_text:
                add(title.line, title.offset, "<title> must not be empty")
            elif len(title_text) > 60:
                add(
                    title.line,
                    title.offset,
                    f"<title> must be 60 characters or fewer (got {len(title_text)})",
                )

        if description is None:
            add(svg.line, svg.offset, "diagram <svg> must contain a <desc>")
        elif not "".join(description.text).strip():
            add(description.line, description.offset, "<desc> must not be empty")

        title_id = title.element_id if title else None
        description_id = description.element_id if description else None
        if svg.bare_id_locations:
            line, offset = svg.bare_id_locations[0]
            add(
                line,
                offset,
                'bare id="title" and id="desc" are not allowed',
            )

        expected_title_id = f"{expected_slug}-title"
        expected_description_id = f"{expected_slug}-desc"
        if not placeholder_ids and (
            title_id != expected_title_id or description_id != expected_description_id
        ):
            add(
                svg.line,
                svg.offset,
                f'accessible-name IDs must match file slug "{expected_slug}": '
                f'expected "{expected_title_id}" / "{expected_description_id}"',
            )

        if (
            labelled_by
            and (title_id not in labelled_by or description_id not in labelled_by)
        ):
            add(
                svg.line,
                svg.offset,
                "aria-labelledby must name the <title> and <desc> IDs",
            )

    return findings


def normalize_hex(value):
    value = value.lower()
    if len(value) == 4:
        return "#" + "".join(character * 2 for character in value[1:])
    return value


def table_hexes(markdown, heading):
    """Return hex colors from the first Markdown table after *heading*."""
    start = markdown.find(heading)
    if start < 0:
        raise ValueError(f"missing {heading!r} in {STYLE_GUIDE}")

    table_started = False
    colors = set()
    for line in markdown[start:].splitlines()[1:]:
        if line.startswith("|"):
            table_started = True
            colors.update(normalize_hex(match.group()) for match in HEX_RE.finditer(line))
        elif table_started:
            break
    return colors


def allowed_colors():
    markdown = STYLE_GUIDE.read_text(encoding="utf-8")
    colors = table_hexes(markdown, "### Semantic roles")
    colors.update(table_hexes(markdown, "### Series palette"))
    colors.update(table_hexes(markdown, "### Terminal skin"))
    colors.update({"#fff", "#ffffff"})

    rgb_triplets = set()
    for color in colors:
        expanded = normalize_hex(color)
        if len(expanded) == 7:
            rgb_triplets.add(
                tuple(int(expanded[offset : offset + 2], 16) for offset in (1, 3, 5))
            )
    return colors, rgb_triplets


def line_number(text, offset):
    return text.count("\n", 0, offset) + 1


def display_path(path):
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def diagram_slug(path):
    return path.stem.removeprefix("example-")


def named_families(value, allowed_fonts):
    families = []
    for raw_family in value.split(","):
        family = raw_family.strip().strip("'\"").strip()
        lowered = family.casefold()
        if not family or lowered in CSS_FONT_KEYWORDS or lowered.startswith("var("):
            continue
        if lowered not in allowed_fonts:
            families.append(family)
    return families


def lint_text(
    text, colors, rgb_triplets, expected_slug, allow_template_placeholders=False
):
    findings = lint_accessible_svgs(
        text, expected_slug, allow_template_placeholders
    )
    allowed_fonts = ALLOWED_FONTS | style_guide_families()

    resources = ResourceParser()
    resources.feed(text)
    resources.close()
    allowed_fonts.update(resources.fonts)
    for line, tag, attr, _value in resources.remote:
        findings.append(
            (
                line,
                0,
                "external-asset",
                f"external resource in <{tag}> {attr} is not allowed",
            )
        )
    for line, tag, attr in resources.executable:
        findings.append(
            (
                line,
                0,
                "script",
                f"executable attribute {attr} on <{tag}> is not allowed",
            )
        )

    def add(offset, category, message):
        findings.append((line_number(text, offset), offset, category, message))

    for match in HEX_RE.finditer(text):
        value = match.group()
        normalized = normalize_hex(value)
        if normalized == "#000000":
            add(match.start(), "pure-black", f"pure black {value} is not allowed")
        elif normalized not in colors:
            add(match.start(), "color", f"{value} is not in the style-guide palette")

    for match in RGBA_RE.finditer(text):
        rgb = tuple(int(match.group(index)) for index in (1, 2, 3))
        if rgb not in rgb_triplets:
            add(
                match.start(),
                "color",
                f"{match.group()} is not derived from an allowed palette color",
            )

    for match in BLACK_RGB_RE.finditer(text):
        add(match.start(), "pure-black", "pure black rgb(0,0,0) is not allowed")

    script_blocks = {match.start(): match for match in SCRIPT_BLOCK_RE.finditer(text)}
    script_openings = list(SCRIPT_OPEN_RE.finditer(text))
    if len(script_openings) > 1:
        add(
            script_openings[1].start(),
            "script",
            "only one canonical motion controller is allowed",
        )
    canonical_digest = None
    for match in script_openings:
        attrs = match.group("attrs")
        block = script_blocks.get(match.start())
        canonical_attrs = attrs.strip().casefold() == "data-diagram-controls"
        if not canonical_attrs:
            add(
                match.start(),
                "script",
                "only the canonical data-diagram-controls attribute is allowed",
            )
        elif block is None:
            add(
                match.start(),
                "script",
                "motion controller must have a closing script tag",
            )
        else:
            if canonical_digest is None:
                canonical_digest = canonical_controller_digest()
            body = normalized_controller(block.group("body"))
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
            if digest != canonical_digest:
                add(
                    match.start(),
                    "script",
                    "motion controller must exactly match template-motion.html",
                )

    for match in SRC_HTTP_RE.finditer(text):
        add(match.start(), "external-asset", "external HTTP(S) src is not allowed")

    for match in IMPORT_ANY_RE.finditer(text):
        add(match.start(), "external-asset", "CSS @import is not allowed")

    for match in URL_ANY_RE.finditer(text):
        value = match.group(1).strip().strip("'\"").strip()
        if value.startswith("#"):
            continue
        add(match.start(), "external-asset", "non-fragment CSS url() is not allowed")

    for link_match in LINK_RE.finditer(text):
        href_match = HREF_RE.search(link_match.group())
        if not href_match:
            continue
        href = href_match.group(2).strip()
        approved_families = google_fonts_families(href)
        rel_match = REL_RE.search(link_match.group())
        rel_values = rel_match.group(2).casefold().split() if rel_match else []
        if approved_families and "stylesheet" in rel_values:
            allowed_fonts.update(approved_families)
            continue
        parsed_href = urlparse(href)
        if parsed_href.scheme.casefold() in {"http", "https"} or parsed_href.netloc:
            href_offset = link_match.start() + href_match.start(2)
            add(href_offset, "external-asset", "external HTTP(S) <link> is not allowed")

    for match in FONT_CSS_RE.finditer(text):
        unsupported = named_families(match.group(1), allowed_fonts)
        if unsupported:
            add(
                match.start(),
                "font-family",
                "unsupported font family: " + ", ".join(unsupported),
            )

    for match in FONT_ATTR_RE.finditer(text):
        unsupported = named_families(match.group(2), allowed_fonts)
        if unsupported:
            add(
                match.start(),
                "font-family",
                "unsupported font family: " + ", ".join(unsupported),
            )

    findings.sort(key=lambda finding: (finding[0], finding[1], finding[2]))
    return findings


def load_baseline():
    if not BASELINE.exists():
        return set()
    return {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Lint diagram examples against the colors and fonts in style-guide.md."
    )
    parser.add_argument("files", nargs="*", type=Path, help="HTML examples to lint")
    parser.add_argument(
        "--all",
        action="store_true",
        help="lint every skills/diagram-design/assets/example-*.html and template*.html file",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="under --all, skip files listed in scripts/lint-skin-baseline.txt",
    )
    parser.add_argument(
        "--quiet", action="store_true", help="print only the summary line"
    )
    args = parser.parse_args()
    if args.all == bool(args.files):
        parser.error("provide either file arguments or --all")
    return args


def main():
    args = parse_args()
    colors, rgb_triplets = allowed_colors()

    skipped = 0
    baseline = set()
    if args.all:
        paths = sorted(
            set(ASSET_DIR.glob("example-*.html"))
            | set(ASSET_DIR.glob("template*.html"))
        )
        if args.baseline:
            baseline = load_baseline()
            for path in paths:
                relative = display_path(path)
                if path.name in baseline or relative in baseline:
                    skipped += 1
    else:
        paths = args.files

    total_findings = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            relative = display_path(path)
            expected_slug = diagram_slug(path)
            allow_template_placeholders = path.name.startswith("template")
            if args.baseline and (path.name in baseline or relative in baseline):
                findings = lint_accessible_svgs(
                    text, expected_slug, allow_template_placeholders
                )
            else:
                findings = lint_text(
                    text,
                    colors,
                    rgb_triplets,
                    expected_slug,
                    allow_template_placeholders,
                )
        except OSError as error:
            findings = [(0, 0, "read-error", str(error))]

        total_findings += len(findings)
        if not args.quiet:
            shown_path = display_path(path)
            for line, _offset, category, message in findings:
                print(f"{shown_path}:{line}: {category}: {message}")

    print(
        f"Summary: {len(paths)} file(s) checked, {skipped} skipped, "
        f"{total_findings} finding(s)."
    )
    return 1 if total_findings else 0


if __name__ == "__main__":
    sys.exit(main())
