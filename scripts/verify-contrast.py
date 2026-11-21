#!/usr/bin/env python3
"""Verify the skin tokens in style-guide.md against the contrast contract.

`lint-skin.py` checks that a diagram only uses palette colors. It never asks
whether those colors can be read. This gate does: it parses the
`### Semantic roles` table, takes each token's light and dark value, and
computes the WCAG 2.x contrast ratio against the background that role sits on,
at the threshold for every use the role has (see style-guide.md, "Contrast
contract"):

- regular text: 4.5:1
- large text: 3:1
- essential non-text marks (lines, arrows, borders, data points): 3:1
- decorative rules and translucent tints: no minimum

A token used in several roles must pass each one, so `accent` is held to the
text bar even though most of its uses are strokes. Translucent values
(`rgba(...)`) are composited over `paper` before they are measured.

Every row in the table must be classified below. A role this file does not
know, a role it expects that is missing, or a value it cannot parse is a
finding, so a new token cannot slip past the gate unmeasured.

Usage:
    python3 scripts/verify-contrast.py
    python3 scripts/verify-contrast.py --style-guide path/to/style-guide.md
    python3 scripts/verify-contrast.py --all-presets

Exit: 0 every token clears its bar, 1 a finding.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE_GUIDE = ROOT / "skills/diagram-design/references/style-guide.md"
PRESETS_DIR = ROOT / "skills/diagram-design/references/presets"
REQUIRED_PRESET_SLUGS = ("blueprint", "mono-print", "graphite")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

SKINS = ("light", "dark")

THRESHOLDS = {
    "text": 4.5,
    "large-text": 3.0,
    "non-text": 3.0,
}

# Every use each role has in the shipped skin. "decorative" has no minimum.
ROLE_USES = {
    "paper": ("background",),
    "paper-2": ("decorative",),
    "ink": ("text", "non-text"),
    "ink-strong": ("text",),
    "muted": ("text", "non-text"),
    "soft": ("text",),
    "rule": ("decorative",),
    "rule-solid": ("decorative",),
    "accent": ("text", "non-text"),
    "accent-tint": ("decorative",),
    "link": ("text", "non-text"),
}

# Roles measured against something other than plain paper, as (role, alpha).
# `ink-strong` is the label color on dense accent fills; the heaviest such fill
# the skin ships under text is the heatmap focal cell, accent at 0.85.
BACKGROUNDS = {
    "ink-strong": ("accent", 0.85),
}

HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
RGBA_RE = re.compile(
    r"rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d*\.?\d+)\s*\)",
    re.IGNORECASE,
)
ROW_RE = re.compile(r"^\|\s*`([a-z0-9-]+)`\s*\|")


class ColorError(ValueError):
    """A table cell holds no color this gate can measure."""


def parse_color(cell: str) -> tuple[tuple[int, int, int], float]:
    """Return ((r, g, b), alpha) for the first hex or rgba() color in *cell*."""
    hex_match = HEX_RE.search(cell)
    rgba_match = RGBA_RE.search(cell)
    if hex_match and (not rgba_match or hex_match.start() < rgba_match.start()):
        value = hex_match.group(1)
        if len(value) == 3:
            value = "".join(character * 2 for character in value)
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4)), 1.0
    if rgba_match:
        channels = tuple(int(rgba_match.group(i)) for i in (1, 2, 3))
        alpha = float(rgba_match.group(4))
        if any(channel > 255 for channel in channels) or not 0.0 <= alpha <= 1.0:
            raise ColorError(f"out-of-range color {rgba_match.group(0)!r}")
        return channels, alpha
    raise ColorError(f"no hex or rgba() color in {cell.strip()!r}")


def parse_tokens(markdown: str) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Return ({skin: {role: raw cell}}, findings) from the Semantic roles table."""
    findings: list[str] = []
    tokens: dict[str, dict[str, str]] = {skin: {} for skin in SKINS}
    start = markdown.find("### Semantic roles")
    if start < 0:
        return tokens, ["style guide has no '### Semantic roles' table"]

    table_started = False
    for line in markdown[start:].splitlines()[1:]:
        if not line.startswith("|"):
            if table_started:
                break
            continue
        table_started = True
        match = ROW_RE.match(line)
        if not match:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            findings.append(f"row `{match.group(1)}` does not have light and dark columns")
            continue
        role = match.group(1)
        tokens["light"][role] = cells[-2]
        tokens["dark"][role] = cells[-1]
    if not table_started:
        findings.append("'### Semantic roles' has no table")
    return tokens, findings


def _channel(value: float) -> float:
    fraction = value / 255
    if fraction <= 0.04045:
        return fraction / 12.92
    return ((fraction + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    red, green, blue = (_channel(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    one, two = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(one, two), min(one, two)
    return (lighter + 0.05) / (darker + 0.05)


def composite(rgb, alpha: float, background) -> tuple[float, float, float]:
    """Flatten a translucent color onto an opaque background (no rounding)."""
    return tuple(rgb[i] * alpha + background[i] * (1 - alpha) for i in range(3))


def measure(tokens: dict[str, dict[str, str]]) -> tuple[list[tuple], list[str]]:
    """Return (rows, findings). Each row is (skin, role, use, ratio, threshold, ok)."""
    rows: list[tuple] = []
    findings: list[str] = []

    for skin in SKINS:
        table = tokens.get(skin, {})
        for role in table:
            if role not in ROLE_USES:
                findings.append(
                    f"{skin}: role `{role}` has no contrast classification in verify-contrast.py"
                )
        for role in ROLE_USES:
            if role not in table:
                findings.append(f"{skin}: role `{role}` is missing from the Semantic roles table")

        parsed = {}
        for role, cell in table.items():
            try:
                parsed[role] = parse_color(cell)
            except ColorError as error:
                findings.append(f"{skin}: `{role}` {error}")
        if "paper" not in parsed:
            continue
        paper_rgb, paper_alpha = parsed["paper"]
        if paper_alpha < 1.0:
            findings.append(f"{skin}: `paper` must be opaque to anchor every ratio")
            continue

        for role, uses in ROLE_USES.items():
            if role not in parsed or "background" in uses:
                continue
            measured = [use for use in uses if use in THRESHOLDS]
            if not measured:
                continue
            background = paper_rgb
            if role in BACKGROUNDS:
                base, alpha = BACKGROUNDS[role]
                if base not in parsed:
                    continue
                base_rgb, base_alpha = parsed[base]
                background = composite(base_rgb, base_alpha * alpha, paper_rgb)
            rgb, alpha = parsed[role]
            foreground = composite(rgb, alpha, background)
            ratio = contrast(foreground, background)
            for use in measured:
                threshold = THRESHOLDS[use]
                passed = ratio >= threshold
                rows.append((skin, role, use, ratio, threshold, passed))
                if not passed:
                    findings.append(
                        f"{skin}: `{role}` as {use} is {ratio:.2f}:1, below {threshold:g}:1"
                    )
    return rows, findings


def check(markdown: str) -> tuple[list[tuple], list[str]]:
    tokens, findings = parse_tokens(markdown)
    rows, measured = measure(tokens)
    return rows, findings + measured


def shipped_preset_paths() -> list[Path]:
    """Return `references/presets/<slug>.md` files whose stem is a valid slug."""
    if not PRESETS_DIR.is_dir():
        return []
    return sorted(
        path for path in PRESETS_DIR.glob("*.md") if SLUG_RE.fullmatch(path.stem)
    )


def report(rows: list[tuple], findings: list[str], quiet: bool, label: str | None = None) -> int:
    """Print one file's measurements. Return 0 when every measured use passed."""
    prefix = f"{label}: " if label else ""
    if not quiet:
        for skin, role, use, ratio, threshold, passed in rows:
            mark = "ok  " if passed else "FAIL"
            print(f"{mark} {prefix}{skin:5} {role:11} {use:10} {ratio:5.2f}:1 (min {threshold:g}:1)")
    for finding in findings:
        print(f"FAIL: {prefix}{finding}")
    if findings or not rows:
        if not rows:
            print(f"FAIL: {prefix}no token was measured")
        print(f"\n{len(findings)} contrast finding(s){f' in {label}' if label else ''}.")
        return 1
    print(
        f"\nOK verify-contrast{f' {label}' if label else ''}: "
        f"{len(rows)} role checks clear their thresholds in both skins"
    )
    return 0


def check_path(path: Path) -> tuple[list[tuple], list[str], str | None]:
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as error:
        return [], [], f"cannot read {path}: {error}"
    rows, findings = check(markdown)
    return rows, findings, None


def check_all_presets(quiet: bool) -> int:
    """Measure every shipped preset. Fail closed if a required slug is missing."""
    if not PRESETS_DIR.is_dir():
        print(f"FAIL: shipped presets directory is missing: {PRESETS_DIR}")
        return 1
    extras = sorted(
        path.name for path in PRESETS_DIR.glob("*.md") if not SLUG_RE.fullmatch(path.stem)
    )
    paths = shipped_preset_paths()
    found = {path.stem for path in paths}
    missing = [slug for slug in REQUIRED_PRESET_SLUGS if slug not in found]
    findings: list[str] = []
    if extras:
        findings.append(
            "presets directory has files whose names are not valid slugs: "
            + ", ".join(extras)
        )
    if missing:
        findings.append(
            "missing required shipped preset(s): " + ", ".join(missing)
        )
    if not paths and not extras:
        findings.append("presets directory has no .md files")
    if findings and not paths:
        for finding in findings:
            print(f"FAIL: {finding}")
        print(f"\n{len(findings)} contrast finding(s).")
        return 1

    failed = 0
    total_rows = 0
    for path in paths:
        rows, measured, error = check_path(path)
        if error:
            print(f"FAIL: {error}")
            failed += 1
            continue
        total_rows += len(rows)
        failed += report(rows, measured, quiet, label=path.stem)
    for finding in findings:
        print(f"FAIL: {finding}")
        failed += 1
    if failed:
        print(f"\n{failed} preset check(s) failed.")
        return 1
    print(
        f"\nOK verify-contrast --all-presets: {len(paths)} presets, "
        f"{total_rows} role checks clear their thresholds"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--style-guide", type=Path, default=None)
    parser.add_argument(
        "--all-presets",
        action="store_true",
        help="check every shipped preset in references/presets/",
    )
    parser.add_argument("--quiet", action="store_true", help="print only findings and the summary")
    args = parser.parse_args(argv)

    if args.all_presets:
        if args.style_guide is not None:
            print("FAIL: --all-presets and --style-guide cannot be combined")
            return 1
        return check_all_presets(args.quiet)

    style_guide = args.style_guide if args.style_guide is not None else STYLE_GUIDE
    rows, findings, error = check_path(style_guide)
    if error:
        print(f"FAIL: {error}")
        return 1
    return report(rows, findings, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
