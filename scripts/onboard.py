#!/usr/bin/env python3
"""Automated Brand Onboarding CLI Tool for diagram-design.

Extracts brand colors from a website URL, local CSS folder, or design tokens,
validates WCAG AA contrast compliance, computes light/dark semantic role mappings,
and updates skills/diagram-design/references/style-guide.md.

Usage:
    python scripts/onboard.py --url https://example.com
    python scripts/onboard.py --folder ./my-design-tokens
    python scripts/onboard.py --url https://example.com --dry-run
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request
from typing import NamedTuple
from urllib.parse import urlparse

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_STYLE_GUIDE = REPO / "skills" / "diagram-design" / "references" / "style-guide.md"

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
VAR_RE = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")


class Color(NamedTuple):
    r: int
    g: int
    b: int

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        hex_clean = hex_str.lstrip("#")
        if len(hex_clean) == 3:
            hex_clean = "".join(c * 2 for c in hex_clean)
        val = int(hex_clean, 16)
        return cls((val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF)

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def luminance(self) -> float:
        """Calculate relative luminance for WCAG contrast calculation."""
        def channel_lum(c: int) -> float:
            s = c / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        return 0.2126 * channel_lum(self.r) + 0.7152 * channel_lum(self.g) + 0.0722 * channel_lum(self.b)


def contrast_ratio(c1: Color, c2: Color) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    l1 = c1.luminance()
    l2 = c2.luminance()
    bright = max(l1, l2)
    dark = min(l1, l2)
    return (bright + 0.05) / (dark + 0.05)


def ensure_contrast(foreground: Color, background: Color, min_ratio: float = 4.5) -> tuple[Color, str | None]:
    """Adjust foreground color lightness to guarantee minimum WCAG contrast against background."""
    ratio = contrast_ratio(foreground, background)
    if ratio >= min_ratio:
        return foreground, None

    orig_hex = foreground.to_hex()
    bg_lum = background.luminance()
    make_darker = bg_lum > 0.5
    factor = 0.9 if make_darker else 1.1

    curr_r, curr_g, curr_b = foreground.r, foreground.g, foreground.b
    for _ in range(30):
        if make_darker:
            curr_r = max(0, int(curr_r * factor))
            curr_g = max(0, int(curr_g * factor))
            curr_b = max(0, int(curr_b * factor))
        else:
            curr_r = min(255, max(1, int(curr_r * factor)))
            curr_g = min(255, max(1, int(curr_g * factor)))
            curr_b = min(255, max(1, int(curr_b * factor)))

        adjusted = Color(curr_r, curr_g, curr_b)
        new_ratio = contrast_ratio(adjusted, background)
        if new_ratio >= min_ratio:
            note = f"Adjusted {orig_hex} -> {adjusted.to_hex()} (WCAG AA contrast {new_ratio:.1f}:1 on {background.to_hex()})"
            return adjusted, note

    final_c = Color(0, 0, 0) if make_darker else Color(255, 255, 255)
    final_ratio = contrast_ratio(final_c, background)
    note = f"Adjusted {orig_hex} -> {final_c.to_hex()} (WCAG AA contrast {final_ratio:.1f}:1 on {background.to_hex()})"
    return final_c, note


def fetch_url_content(url: str, max_bytes: int = 5 * 1024 * 1024) -> str:
    """Fetch website content enforcing http/https schemes and response size cap."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{parsed.scheme}': only http and https are permitted.")

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        content_bytes = resp.read(max_bytes + 1)
        if len(content_bytes) > max_bytes:
            raise ValueError(f"Response size exceeds maximum permitted cap of {max_bytes // (1024*1024)}MB.")
        return content_bytes.decode("utf-8", errors="ignore")


def extract_css_from_folder(folder_path: pathlib.Path) -> str:
    """Read and concatenate CSS, JSON, and HTML files from a local folder."""
    chunks = []
    exts = {".css", ".json", ".html", ".md"}
    for root, _, files in os.walk(folder_path):
        for file in files:
            p = pathlib.Path(root) / file
            if p.suffix.lower() in exts:
                try:
                    chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    pass
    return "\n".join(chunks)


def extract_tokens(text: str) -> tuple[dict[str, str], list[str]]:
    """Extract colors and variables from text content."""
    warnings: list[str] = []
    vars_found: dict[str, str] = {}
    for match in VAR_RE.finditer(text):
        name, val = match.group(1).lower(), match.group(2).strip()
        hex_match = HEX_RE.search(val)
        if hex_match:
            vars_found[name] = hex_match.group(0).lower()

    hexes = [m.lower() for m in HEX_RE.findall(text)]

    # Map semantic roles using name heuristics or frequency
    paper_hex = "#f5f5f5"
    ink_hex = "#2d3142"
    accent_hex = "#eb6c36"
    muted_hex = "#4f5d75"

    for name, val in vars_found.items():
        if any(k in name for k in ("bg", "background", "paper", "surface")):
            paper_hex = val
        elif any(k in name for k in ("text", "ink", "foreground", "body")):
            ink_hex = val
        elif any(k in name for k in ("accent", "brand", "primary", "cta")):
            accent_hex = val
        elif any(k in name for k in ("muted", "secondary", "caption")):
            muted_hex = val

    # Fallback to frequency if custom properties were missing
    if not vars_found and hexes:
        warnings.append("Warning: No CSS custom properties found; falling back to hex frequency ranking.")
        counts = {}
        for h in hexes:
            counts[h] = counts.get(h, 0) + 1
        sorted_colors = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        if sorted_colors:
            paper_hex = sorted_colors[0][0]
        if len(sorted_colors) > 1:
            ink_hex = sorted_colors[1][0]
        if len(sorted_colors) > 2:
            accent_hex = sorted_colors[2][0]

    tokens = {
        "paper": paper_hex,
        "ink": ink_hex,
        "accent": accent_hex,
        "muted": muted_hex,
    }
    return tokens, warnings


def compute_derived_roles(tokens: dict[str, str]) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Compute light and dark variants for all 9 semantic roles with contrast enforcement."""
    contrast_notes: list[str] = []
    paper_c = Color.from_hex(tokens["paper"])
    ink_c = Color.from_hex(tokens["ink"])
    accent_c = Color.from_hex(tokens["accent"])
    muted_c = Color.from_hex(tokens["muted"])

    # Enforce WCAG AA contrast on ink and muted against paper
    ink_c, note_ink = ensure_contrast(ink_c, paper_c, 4.5)
    if note_ink:
        contrast_notes.append(note_ink)

    muted_c, note_muted = ensure_contrast(muted_c, paper_c, 4.5)
    if note_muted:
        contrast_notes.append(note_muted)

    # Derived light values
    paper_2_c = Color(
        max(0, paper_c.r - 9),
        max(0, paper_c.g - 9),
        max(0, paper_c.b - 9)
    )
    soft_c = Color(
        int(ink_c.r * 0.4 + muted_c.r * 0.6),
        int(ink_c.g * 0.4 + muted_c.g * 0.6),
        int(ink_c.b * 0.4 + muted_c.b * 0.6)
    )
    rule_str = f"rgba({ink_c.r},{ink_c.g},{ink_c.b},0.12)"
    rule_solid_c = Color(191, 192, 192)
    accent_tint_str = f"rgba({accent_c.r},{accent_c.g},{accent_c.b},0.08)"
    link_c = Color(46, 90, 168)

    # Dark mode dynamic brand inversion
    paper_dark = Color(
        max(0, 255 - paper_c.r),
        max(0, 255 - paper_c.g),
        max(0, 255 - paper_c.b)
    )
    ink_dark = Color(
        min(255, 255 - ink_c.r),
        min(255, 255 - ink_c.g),
        min(255, 255 - ink_c.b)
    )
    accent_dark = Color(
        min(255, accent_c.r + 15),
        min(255, accent_c.g + 18),
        min(255, accent_c.b + 20)
    )
    paper_2_dark = Color(
        min(255, paper_dark.r + 12),
        min(255, paper_dark.g + 12),
        min(255, paper_dark.b + 12)
    )
    muted_dark = Color(
        min(255, 255 - muted_c.r),
        min(255, 255 - muted_c.g),
        min(255, 255 - muted_c.b)
    )
    soft_dark = Color(
        min(255, 255 - soft_c.r),
        min(255, 255 - soft_c.g),
        min(255, 255 - soft_c.b)
    )
    rule_dark_str = f"rgba({ink_dark.r},{ink_dark.g},{ink_dark.b},0.12)"
    rule_solid_dark_str = f"rgba({ink_dark.r},{ink_dark.g},{ink_dark.b},0.25)"
    accent_tint_dark_str = f"rgba({accent_dark.r},{accent_dark.g},{accent_dark.b},0.10)"
    link_dark = Color(
        min(255, link_c.r + 60),
        min(255, link_c.g + 60),
        min(255, link_c.b + 60)
    )

    roles = {
        "paper":       {"light": paper_c.to_hex(), "dark": paper_dark.to_hex()},
        "paper-2":     {"light": paper_2_c.to_hex(), "dark": paper_2_dark.to_hex()},
        "ink":         {"light": ink_c.to_hex(), "dark": ink_dark.to_hex()},
        "muted":       {"light": muted_c.to_hex(), "dark": muted_dark.to_hex()},
        "soft":        {"light": soft_c.to_hex(), "dark": soft_dark.to_hex()},
        "rule":        {"light": rule_str, "dark": rule_dark_str},
        "rule-solid":  {"light": rule_solid_c.to_hex(), "dark": rule_solid_dark_str},
        "accent":      {"light": accent_c.to_hex(), "dark": accent_dark.to_hex()},
        "accent-tint": {"light": accent_tint_str, "dark": accent_tint_dark_str},
        "link":        {"light": link_c.to_hex(), "dark": link_dark.to_hex()},
    }
    return roles, contrast_notes


def update_style_guide(roles: dict[str, dict[str, str]], style_guide_path: pathlib.Path, dry_run: bool = False) -> str:
    """Generate Markdown tokens table and update style-guide.md."""
    lines = [
        "| Role | Purpose | Default (light) | Default (dark) |",
        "|---|---|---|---|",
        f"| `paper` | Page background, default node fill | `{roles['paper']['light']}` | `{roles['paper']['dark']}` |",
        f"| `paper-2` | Diagram container bg, secondary fill | `{roles['paper-2']['light']}` | `{roles['paper-2']['dark']}` |",
        f"| `ink` | Primary text, primary stroke | `{roles['ink']['light']}` | `{roles['ink']['dark']}` |",
        f"| `muted` | Secondary text, default arrow stroke | `{roles['muted']['light']}` | `{roles['muted']['dark']}` |",
        f"| `soft` | Sublabels, boundary labels | `{roles['soft']['light']}` | `{roles['soft']['dark']}` |",
        f"| `rule` | Hairline borders | `{roles['rule']['light']}` | `{roles['rule']['dark']}` |",
        f"| `rule-solid` | Stronger borders, baselines | `{roles['rule-solid']['light']}` | `{roles['rule-solid']['dark']}` |",
        f"| `accent` | Focal / 1–2 max per diagram | `{roles['accent']['light']}` | `{roles['accent']['dark']}` |",
        f"| `accent-tint` | Fill for accent-bordered boxes | `{roles['accent-tint']['light']}` | `{roles['accent-tint']['dark']}` |",
        f"| `link` | HTTP/API calls, external arrows | `{roles['link']['light']}` | `{roles['link']['dark']}` |",
    ]
    table_text = "\n".join(lines)

    if not dry_run and style_guide_path.exists():
        content = style_guide_path.read_text(encoding="utf-8")
        table_pattern = re.compile(r"\| Role \| Purpose \| Default \(light\) \| Default \(dark\) \|.*?\n(?:\|.*?\|\n)+", re.DOTALL)
        if table_pattern.search(content):
            updated_content = table_pattern.sub(table_text + "\n", content, count=1)
            style_guide_path.write_text(updated_content, encoding="utf-8")

    return table_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated Brand Onboarding CLI Tool for diagram-design.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Website URL to extract brand tokens from")
    group.add_argument("--folder", help="Local directory path containing CSS/JSON design tokens")
    parser.add_argument("--dry-run", action="store_true", help="Preview proposed diff without writing to style-guide.md")
    parser.add_argument("--out", help="Path to style-guide.md (default: skills/diagram-design/references/style-guide.md)")

    args = parser.parse_args()
    style_guide_path = pathlib.Path(args.out) if args.out else DEFAULT_STYLE_GUIDE

    print("Onboarding diagram-design skin...")
    try:
        if args.url:
            print(f"Fetching website: {args.url}")
            content = fetch_url_content(args.url)
        else:
            folder_path = pathlib.Path(args.folder)
            if not folder_path.exists():
                print(f"Error: folder path does not exist: {folder_path}", file=sys.stderr)
                return 1
            print(f"Reading local folder: {folder_path}")
            content = extract_css_from_folder(folder_path)
    except Exception as e:
        print(f"Error reading source content: {e}", file=sys.stderr)
        return 1

    raw_tokens, warnings = extract_tokens(content)
    for warn in warnings:
        print(warn, file=sys.stderr)
    print(f"Extracted Raw Tokens: {raw_tokens}")

    roles, contrast_notes = compute_derived_roles(raw_tokens)
    for note in contrast_notes:
        print(f"[WCAG AA] {note}")

    table_output = update_style_guide(roles, style_guide_path, dry_run=args.dry_run)

    print("\n--- Proposed Tokens Table ---")
    print(table_output)

    if args.dry_run:
        print("\n[Dry-run mode] No changes were written to style-guide.md.")
    else:
        print(f"\nSuccessfully updated {style_guide_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
