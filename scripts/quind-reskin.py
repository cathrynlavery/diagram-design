#!/usr/bin/env python3
"""Re-skin upstream Diagram Design files to the QUIND skin.

Upstream (cathrynlavery/diagram-design) inlines its default palette and fonts
as literals in every template, example, and a few reference snippets. This
script maps those literals to the QUIND tokens in
``skills/diagrams-design-quind/references/style-guide.md`` so a merge from
upstream can be re-skinned in one command instead of by hand.

It is idempotent: QUIND values are never the source of a mapping, so running
it twice changes nothing. The terminal skin (``*-terminal.html``) is a fixed
alternate skin and is left alone.

Usage:
    python3 scripts/quind-reskin.py                 # every asset and reference
    python3 scripts/quind-reskin.py path/to/file.html [...]
    python3 scripts/quind-reskin.py --check         # exit 1 if a file would change
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "diagrams-design-quind"

# --- colors ---------------------------------------------------------------
# upstream literal -> QUIND token value. Same hex on both polarities unless
# listed in DARK_ONLY / LIGHT_ONLY below.
HEX = {
    "#2d3142": "#0e1920",  # ink (light) / paper (dark)
    "#f5f5f5": "#ffffff",  # paper (light) / ink (dark)
    "#ececec": "#f3f6f8",  # paper-2 (light)
    "#393e53": "#16242c",  # paper-2 (dark)
    "#4f5d75": "#5b6770",  # muted (light)
    "#5a6580": "#66727c",  # soft (light)
    "#949eb2": "#8695a0",  # soft (dark)
    "#bf4520": "#cc3b10",  # accent (light)
    "#f08a59": "#ff8a5c",  # accent (dark)
    "#2e5aa8": "#0b6e80",  # link (light)
    "#739fdf": "#5fd6ec",  # link (dark)
    "#3d4460": "#22313a",  # dark hairline fill
    "#4a5270": "#2a3a44",  # dark hairline stroke
    # series palette, light
    "#7c8f6f": "#2fa36b",
    "#5e7a9b": "#0b6e80",
    "#b8915a": "#9a6400",
    "#9c6b50": "#7a8791",
    "#6e6479": "#24323c",
    # series palette, dark
    "#9caf8f": "#6fd3a0",
    "#82a0c0": "#5fd6ec",
    "#d3ad7a": "#ffc85a",
    "#b88670": "#6c7b85",
    "#8d8298": "#b8c2ca",
}
# #bfc0c0 is rule-solid on light paper and muted on dark paper upstream.
HEX_BY_POLARITY = {
    "#bfc0c0": {"light": "#c9d1d8", "dark": "#9ba9b2"},
}

RGB = {
    (45, 49, 66): (14, 25, 32),
    (245, 245, 245): (255, 255, 255),
    (191, 69, 32): (204, 59, 16),
    (240, 138, 89): (255, 138, 92),
    (79, 93, 117): (91, 103, 112),
    (90, 101, 128): (102, 114, 124),
    (148, 158, 178): (134, 149, 160),
    (46, 90, 168): (11, 110, 128),
    (115, 159, 223): (95, 214, 236),
    (124, 143, 111): (47, 163, 107),
    (94, 122, 155): (11, 110, 128),
    (184, 145, 90): (154, 100, 0),
    (156, 107, 80): (122, 135, 145),
    (110, 100, 121): (36, 50, 60),
    (156, 175, 143): (111, 211, 160),
    (130, 160, 192): (95, 214, 236),
    (211, 173, 122): (255, 200, 90),
    (184, 134, 112): (108, 123, 133),
    (141, 130, 152): (184, 194, 202),
}
RGB_BY_POLARITY = {
    (191, 192, 192): {"light": (201, 209, 216), "dark": (155, 169, 178)},
}

HEX_RE = re.compile(r"#[0-9a-fA-F]{6}(?![0-9a-fA-F])")
RGB_RE = re.compile(r"(rgba?\(\s*)(\d{1,3})(\s*,\s*)(\d{1,3})(\s*,\s*)(\d{1,3})")

# --- fonts ----------------------------------------------------------------
TITLE_STACK = "'Poppins', 'Inter', system-ui, sans-serif"
TITLE_STACK_BARE = "Poppins,Inter,system-ui,sans-serif"

GEIST_MONO_RE = re.compile(r"Geist Mono")
GEIST_RE = re.compile(r"Geist(?! Mono)")
# A CSS custom property holding the title family.
SERIF_VAR_RE = re.compile(r"(--(?:font-)?serif\s*:\s*)[^;}]*Instrument Serif[^;}]*")
# A quoted or bare font stack that starts with Instrument Serif.
SERIF_QUOTED_STACK_RE = re.compile(r"'Instrument Serif'(?:\s*,\s*(?:'[^']+'|[a-z-]+))*")
SERIF_BARE_STACK_RE = re.compile(r"Instrument Serif(?:\s*,\s*[A-Za-z -]+)*")

LINK_RE = re.compile(r"https://fonts\.googleapis\.com/css2\?[^\"'\s)]+")


def reskin_font_link(url: str) -> str:
    amp = "&amp;" if "&amp;" in url else "&"
    base, _, query = url.partition("?")
    params = query.split(amp)
    out: list[str] = []
    for param in params:
        if param.startswith("family=Instrument+Serif"):
            param = "family=Poppins:wght@400;500;600;700"
        elif param.startswith("family=Geist+Mono"):
            param = param.replace("Geist+Mono", "Roboto+Mono")
        elif param.startswith("family=Geist"):
            weights = sorted(set(re.findall(r"\d{3}", param))) or ["400", "500", "600"]
            tuples = [f"0,{w}" for w in weights] + ["1,400"]
            param = "family=Inter:ital,wght@" + ";".join(tuples)
        elif param.startswith("family=Noto+Serif"):
            continue  # the title family is a sans now; Inter covers Cyrillic
        if param not in out:
            out.append(param)
    return base + "?" + amp.join(out)


def _serif_context_is_italic(text: str, start: int) -> bool:
    """True when the tag or CSS rule holding ``start`` also sets italic."""
    tag_open = text.rfind("<", 0, start)
    tag_close = text.rfind(">", 0, start)
    if tag_open > tag_close:  # inside a tag
        end = text.find(">", start)
        return "italic" in text[tag_open : end if end != -1 else start]
    rule_open = text.rfind("{", 0, start)
    rule_close = text.rfind("}", 0, start)
    if rule_open > rule_close:  # inside a CSS rule
        end = text.find("}", start)
        return "italic" in text[rule_open : end if end != -1 else start]
    return False


def reskin_fonts(text: str) -> str:
    text = LINK_RE.sub(lambda m: reskin_font_link(m.group(0)), text)
    text = SERIF_VAR_RE.sub(lambda m: m.group(1) + TITLE_STACK, text)

    def stack(match: re.Match, bare: bool) -> str:
        if _serif_context_is_italic(match.string, match.start()):
            return "Inter,system-ui,sans-serif" if bare else "'Inter', system-ui, sans-serif"
        return TITLE_STACK_BARE if bare else TITLE_STACK

    text = SERIF_QUOTED_STACK_RE.sub(lambda m: stack(m, False), text)
    text = SERIF_BARE_STACK_RE.sub(lambda m: stack(m, True), text)
    text = GEIST_MONO_RE.sub("Roboto Mono", text)
    text = GEIST_RE.sub("Inter", text)
    return text


# An italic rule that takes the title family through the variable: callouts
# read as body-face italics in the QUIND skin, not as titles.
ITALIC_VAR_RULE_RE = re.compile(r"\{[^{}]*\}")


def reskin_italic_rules(text: str) -> str:
    def rule(match: re.Match) -> str:
        body = match.group(0)
        if "italic" not in body:
            return body
        body = re.sub(r"var\(--font-serif\)", "var(--font-sans)", body)
        return re.sub(r"var\(--serif\)", "var(--sans)", body)

    return ITALIC_VAR_RULE_RE.sub(rule, text)


# The page title: Poppins carries the hierarchy at 600, not at the serif's 400.
H1_RULE_RE = re.compile(r"(\bh1\s*\{[^{}]*?font-weight\s*:\s*)400")


def reskin_colors(text: str, polarity: str) -> str:
    def hex_sub(match: re.Match) -> str:
        value = match.group(0)
        key = value.lower()
        if key in HEX:
            return HEX[key]
        if key in HEX_BY_POLARITY:
            return HEX_BY_POLARITY[key][polarity]
        return value

    def rgb_sub(match: re.Match) -> str:
        triple = (int(match.group(2)), int(match.group(4)), int(match.group(6)))
        target = RGB.get(triple)
        if target is None and triple in RGB_BY_POLARITY:
            target = RGB_BY_POLARITY[triple][polarity]
        if target is None:
            return match.group(0)
        return (
            f"{match.group(1)}{target[0]}{match.group(3)}"
            f"{target[1]}{match.group(5)}{target[2]}"
        )

    return RGB_RE.sub(rgb_sub, HEX_RE.sub(hex_sub, text))


def polarity_of(path: Path) -> str:
    return "dark" if "-dark" in path.stem else "light"


def reskin(path: Path, text: str) -> str:
    if "terminal" in path.stem:
        return text
    text = reskin_colors(text, polarity_of(path))
    if path.suffix == ".html":
        text = reskin_fonts(text)
        text = reskin_italic_rules(text)
        text = H1_RULE_RE.sub(r"\g<1>600", text)
    return text


# References whose hex literals are data about other tools or other skins,
# not QUIND skin values.
SKIP_REFERENCES = {
    "style-guide.md",   # the source of truth, written by hand
    "onboarding.md",    # sample diffs for other brands
    "import-drawio.md", # draw.io source colors
    "primitive-terminal.md",
    "primitive-icons.md",
}


def default_targets() -> list[Path]:
    targets = sorted((SKILL / "assets").glob("*.html"))
    targets += [
        p for p in sorted((SKILL / "references").glob("*.md")) if p.name not in SKIP_REFERENCES
    ]
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    changed = 0
    for path in args.paths or default_targets():
        before = path.read_text(encoding="utf-8")
        after = reskin(path, before)
        if after != before:
            changed += 1
            if args.check:
                print(f"would change: {path}")
            else:
                path.write_text(after, encoding="utf-8")
    verb = "would change" if args.check else "changed"
    print(f"{changed} file(s) {verb}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
