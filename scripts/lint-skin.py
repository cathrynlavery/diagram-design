#!/usr/bin/env python3
"""Lint NEW and CHANGED diagram examples against the current visual skin.

Pre-2.0 examples may legitimately fail because they were built against an older
skin. Use ``--all --baseline`` to skip those documented legacy files.
"""

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STYLE_GUIDE = ROOT / "skills/diagram-design/references/style-guide.md"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
BASELINE = ROOT / "scripts/lint-skin-baseline.txt"

HEX_RE = re.compile(
    r"(?<![\w-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)
RGBA_RE = re.compile(
    r"rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*([^)]+)\)",
    re.IGNORECASE,
)
BLACK_RGB_RE = re.compile(r"rgb\(\s*0\s*,\s*0\s*,\s*0\s*\)", re.IGNORECASE)
SCRIPT_RE = re.compile(r"<script\b", re.IGNORECASE)
SRC_HTTP_RE = re.compile(r"\bsrc\s*=\s*(['\"])\s*https?://", re.IGNORECASE)
IMPORT_HTTP_RE = re.compile(
    r"@import\s+(?:url\(\s*)?(?:['\"]\s*)?https?://", re.IGNORECASE
)
URL_HTTP_RE = re.compile(r"url\(\s*(?:['\"]\s*)?https?://", re.IGNORECASE)
LINK_RE = re.compile(r"<link\b[^>]*>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"\bhref\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL)
FONT_CSS_RE = re.compile(r"font-family\s*:\s*([^;}]+)", re.IGNORECASE)
FONT_ATTR_RE = re.compile(
    r"\bfont-family\s*=\s*(['\"])(.*?)\1", re.IGNORECASE | re.DOTALL
)

ALLOWED_FONTS = {
    "instrument serif",
    "geist",
    "geist mono",
    "system-ui",
    "sans-serif",
    "serif",
    "monospace",
    "ui-monospace",
}
CSS_FONT_KEYWORDS = {"inherit", "initial", "revert", "revert-layer", "unset"}


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


def named_families(value):
    families = []
    for raw_family in value.split(","):
        family = raw_family.strip().strip("'\"").strip()
        lowered = family.casefold()
        if not family or lowered in CSS_FONT_KEYWORDS or lowered.startswith("var("):
            continue
        if lowered not in ALLOWED_FONTS:
            families.append(family)
    return families


def lint_text(text, colors, rgb_triplets):
    findings = []

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

    for match in SCRIPT_RE.finditer(text):
        add(match.start(), "script", "<script> tags are not allowed")

    for match in SRC_HTTP_RE.finditer(text):
        add(match.start(), "external-asset", "external HTTP(S) src is not allowed")

    import_spans = []
    for match in IMPORT_HTTP_RE.finditer(text):
        import_spans.append(match.span())
        add(match.start(), "external-asset", "external HTTP(S) @import is not allowed")

    for match in URL_HTTP_RE.finditer(text):
        if any(start <= match.start() < end for start, end in import_spans):
            continue
        add(match.start(), "external-asset", "external HTTP(S) url() is not allowed")

    for link_match in LINK_RE.finditer(text):
        href_match = HREF_RE.search(link_match.group())
        if not href_match:
            continue
        href = href_match.group(2).strip()
        if href.lower().startswith("https://fonts.googleapis.com"):
            continue
        if href.lower().startswith(("http://", "https://")):
            href_offset = link_match.start() + href_match.start(2)
            add(href_offset, "external-asset", "external HTTP(S) <link> is not allowed")

    for match in FONT_CSS_RE.finditer(text):
        unsupported = named_families(match.group(1))
        if unsupported:
            add(
                match.start(),
                "font-family",
                "unsupported font family: " + ", ".join(unsupported),
            )

    for match in FONT_ATTR_RE.finditer(text):
        unsupported = named_families(match.group(2))
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
        help="lint every skills/diagram-design/assets/example-*.html file",
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
    if args.all:
        paths = sorted(ASSET_DIR.glob("example-*.html"))
        if args.baseline:
            baseline = load_baseline()
            selected = []
            for path in paths:
                relative = display_path(path)
                if path.name in baseline or relative in baseline:
                    skipped += 1
                else:
                    selected.append(path)
            paths = selected
    else:
        paths = args.files

    total_findings = 0
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
            findings = lint_text(text, colors, rgb_triplets)
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
