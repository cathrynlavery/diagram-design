#!/usr/bin/env python3
"""Automated Brand Onboarding CLI Tool for diagram-design.

Extracts brand colors from website URLs, local folders, CSS/SCSS files, JSON design tokens, or Markdown docs,
validates WCAG AA contrast compliance for light and dark modes, computes semantic role mappings,
and safely updates skills/diagram-design/references/style-guide.md with atomic backups.

Usage:
    python scripts/onboard.py --url https://example.com
    python scripts/onboard.py --folder ./my-design-tokens
    python scripts/onboard.py --url https://example.com --apply
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import tempfile
import urllib.error
import urllib.request
from typing import NamedTuple
from urllib.parse import urlparse

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_STYLE_GUIDE = REPO / "skills" / "diagram-design" / "references" / "style-guide.md"

HEX_RE = re.compile(r"#(?:[0-9a-fA-F]{3}){1,2}\b")
VAR_RE = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")
SCSS_VAR_RE = re.compile(r"\$([\w-]+)\s*:\s*([^;]+);")


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
    """Adjust foreground color lightness to guarantee minimum WCAG contrast against background for light and medium backgrounds."""
    ratio = contrast_ratio(foreground, background)
    if ratio >= min_ratio:
        return foreground, None

    orig_hex = foreground.to_hex()

    # Try both darkening and lightening candidates to choose the optimal direction for medium backgrounds
    darker_c = foreground
    r_dark = ratio
    curr_r, curr_g, curr_b = foreground.r, foreground.g, foreground.b
    for _ in range(40):
        curr_r = max(0, int(curr_r * 0.88))
        curr_g = max(0, int(curr_g * 0.88))
        curr_b = max(0, int(curr_b * 0.88))
        cand = Color(curr_r, curr_g, curr_b)
        r_cand = contrast_ratio(cand, background)
        if r_cand >= min_ratio:
            darker_c = cand
            r_dark = r_cand
            break

    lighter_c = foreground
    r_light = ratio
    curr_r, curr_g, curr_b = foreground.r, foreground.g, foreground.b
    for _ in range(40):
        curr_r = min(255, max(1, int(curr_r * 1.12)))
        curr_g = min(255, max(1, int(curr_g * 1.12)))
        curr_b = min(255, max(1, int(curr_b * 1.12)))
        cand = Color(curr_r, curr_g, curr_b)
        r_cand = contrast_ratio(cand, background)
        if r_cand >= min_ratio:
            lighter_c = cand
            r_light = r_cand
            break

    best_c = foreground
    best_ratio = ratio
    if r_dark >= min_ratio and r_light >= min_ratio:
        best_c = darker_c if background.luminance() > 0.4 else lighter_c
        best_ratio = max(r_dark, r_light)
    elif r_dark >= min_ratio:
        best_c = darker_c
        best_ratio = r_dark
    elif r_light >= min_ratio:
        best_c = lighter_c
        best_ratio = r_light
    else:
        # Pure black or white fallback
        black_c = Color(0, 0, 0)
        white_c = Color(255, 255, 255)
        if contrast_ratio(black_c, background) >= contrast_ratio(white_c, background):
            best_c = black_c
            best_ratio = contrast_ratio(black_c, background)
        else:
            best_c = white_c
            best_ratio = contrast_ratio(white_c, background)

    note = f"Adjusted {orig_hex} -> {best_c.to_hex()} (WCAG AA contrast {best_ratio:.1f}:1 on {background.to_hex()})"
    return best_c, note


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
    """Read and concatenate CSS, SCSS, JSON, and HTML files from a local folder."""
    chunks = []
    exts = {".css", ".scss", ".json", ".html", ".md"}
    for root, _, files in os.walk(folder_path):
        for file in files:
            p = pathlib.Path(root) / file
            if p.suffix.lower() in exts:
                try:
                    chunks.append(p.read_text(encoding="utf-8", errors="ignore"))
                except Exception:
                    pass
    return "\n".join(chunks)


def extract_json_tokens(text: str) -> dict[str, str]:
    """Format-aware JSON design token parser for nested token objects."""
    found: dict[str, str] = {}

    def walk_json(obj: object, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_path = f"{path}.{k}" if path else str(k)
                if isinstance(v, str):
                    m = HEX_RE.search(v)
                    if m:
                        found[new_path.lower()] = m.group(0).lower()
                else:
                    walk_json(v, new_path)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk_json(item, f"{path}[{i}]")

    # Try parsing text blocks as JSON
    for block in re.findall(r"\{[^{}]+\}", text):
        try:
            data = json.loads(block)
            walk_json(data)
        except Exception:
            pass

    return found


def extract_tokens(text: str) -> tuple[dict[str, str], list[str]]:
    """Format-aware token parser for CSS, SCSS, JSON, and raw hexes with zero-confidence guard."""
    warnings: list[str] = []
    vars_found: dict[str, str] = {}

    # 1. CSS Custom Properties (--variable: #hex;)
    for match in VAR_RE.finditer(text):
        name, val = match.group(1).lower(), match.group(2).strip()
        hex_match = HEX_RE.search(val)
        if hex_match:
            vars_found[name] = hex_match.group(0).lower()

    # 2. SCSS Variables ($variable: #hex;)
    for match in SCSS_VAR_RE.finditer(text):
        name, val = match.group(1).lower(), match.group(2).strip()
        hex_match = HEX_RE.search(val)
        if hex_match:
            vars_found[name] = hex_match.group(0).lower()

    # 3. JSON Design Tokens
    json_vars = extract_json_tokens(text)
    vars_found.update(json_vars)

    hexes = [m.lower() for m in HEX_RE.findall(text)]

    # Zero-Confidence Guard: if no hexes or variables found, fail without modifying style guide
    if not vars_found and not hexes:
        raise ValueError("Zero-confidence extraction: no valid hex colors or design tokens found in source.")

    paper_hex: str | None = None
    ink_hex: str | None = None
    accent_hex: str | None = None
    muted_hex: str | None = None

    for name, val in vars_found.items():
        if not paper_hex and any(k in name for k in ("bg", "background", "paper", "surface")):
            paper_hex = val
        elif not ink_hex and any(k in name for k in ("text", "ink", "foreground", "body")):
            ink_hex = val
        elif not accent_hex and any(k in name for k in ("accent", "brand", "primary", "cta")):
            accent_hex = val
        elif not muted_hex and any(k in name for k in ("muted", "secondary", "caption")):
            muted_hex = val

    # Fallback to frequency ranking if variables were incomplete
    if (not paper_hex or not ink_hex or not accent_hex) and hexes:
        if vars_found:
            warnings.append("Warning: Partially missing semantic CSS/JSON properties; using frequency ranking for unmapped roles.")
        else:
            warnings.append("Warning: No CSS/JSON custom properties found; falling back to hex frequency ranking.")

        counts: dict[str, int] = {}
        for h in hexes:
            counts[h] = counts.get(h, 0) + 1
        sorted_colors = sorted(counts.items(), key=lambda x: x[1], reverse=True)

        if not paper_hex and sorted_colors:
            paper_hex = sorted_colors[0][0]
        if not ink_hex and len(sorted_colors) > 1:
            ink_hex = sorted_colors[1][0]
        if not accent_hex and len(sorted_colors) > 2:
            accent_hex = sorted_colors[2][0]

    paper_final = paper_hex or "#f5f5f5"
    ink_final = ink_hex or "#2d3142"
    accent_final = accent_hex or "#eb6c36"
    muted_final = muted_hex or "#4f5d75"

    tokens = {
        "paper": paper_final,
        "ink": ink_final,
        "accent": accent_final,
        "muted": muted_final,
    }
    return tokens, warnings


def compute_derived_roles(tokens: dict[str, str]) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Compute light and dark variants for all 9 semantic roles with double-ended WCAG contrast enforcement."""
    contrast_notes: list[str] = []
    paper_c = Color.from_hex(tokens["paper"])
    ink_c = Color.from_hex(tokens["ink"])
    accent_c = Color.from_hex(tokens["accent"])
    muted_c = Color.from_hex(tokens["muted"])

    # Enforce WCAG AA contrast for Light Mode pairs
    ink_c, note_ink = ensure_contrast(ink_c, paper_c, 4.5)
    if note_ink:
        contrast_notes.append(f"[Light Mode] {note_ink}")

    muted_c, note_muted = ensure_contrast(muted_c, paper_c, 4.5)
    if note_muted:
        contrast_notes.append(f"[Light Mode] {note_muted}")

    # Derived light values
    paper_2_c = Color(max(0, paper_c.r - 9), max(0, paper_c.g - 9), max(0, paper_c.b - 9))
    soft_c = Color(
        int(ink_c.r * 0.4 + muted_c.r * 0.6),
        int(ink_c.g * 0.4 + muted_c.g * 0.6),
        int(ink_c.b * 0.4 + muted_c.b * 0.6)
    )
    rule_str = f"rgba({ink_c.r},{ink_c.g},{ink_c.b},0.12)"
    rule_solid_c = Color(191, 192, 192)
    accent_tint_str = f"rgba({accent_c.r},{accent_c.g},{accent_c.b},0.08)"
    link_c = Color(46, 90, 168)

    # Dark mode dynamic brand inversion with independent numerical validation
    paper_dark = Color(max(0, 255 - paper_c.r), max(0, 255 - paper_c.g), max(0, 255 - paper_c.b))
    ink_dark_cand = Color(min(255, 255 - ink_c.r), min(255, 255 - ink_c.g), min(255, 255 - ink_c.b))
    accent_dark = Color(min(255, accent_c.r + 15), min(255, accent_c.g + 18), min(255, accent_c.b + 20))
    paper_2_dark = Color(min(255, paper_dark.r + 12), min(255, paper_dark.g + 12), min(255, paper_dark.b + 12))
    muted_dark_cand = Color(min(255, 255 - muted_c.r), min(255, 255 - muted_c.g), min(255, 255 - muted_c.b))
    soft_dark = Color(min(255, 255 - soft_c.r), min(255, 255 - soft_c.g), min(255, 255 - soft_c.b))

    # Numerical WCAG AA validation on Dark Mode pairs
    ink_dark, note_ink_dark = ensure_contrast(ink_dark_cand, paper_dark, 4.5)
    if note_ink_dark:
        contrast_notes.append(f"[Dark Mode] {note_ink_dark}")

    muted_dark, note_muted_dark = ensure_contrast(muted_dark_cand, paper_dark, 4.5)
    if note_muted_dark:
        contrast_notes.append(f"[Dark Mode] {note_muted_dark}")

    rule_dark_str = f"rgba({ink_dark.r},{ink_dark.g},{ink_dark.b},0.12)"
    rule_solid_dark_str = f"rgba({ink_dark.r},{ink_dark.g},{ink_dark.b},0.25)"
    accent_tint_dark_str = f"rgba({accent_dark.r},{accent_dark.g},{accent_dark.b},0.10)"
    link_dark = Color(min(255, link_c.r + 60), min(255, link_c.g + 60), min(255, link_c.b + 60))

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


def update_style_guide(roles: dict[str, dict[str, str]], style_guide_path: pathlib.Path, apply_changes: bool = False) -> str:
    """Generate Markdown tokens table and perform atomic write with recoverable backup if apply_changes is True."""
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

    if apply_changes:
        if not style_guide_path.parent.exists():
            raise FileNotFoundError(f"Target directory does not exist: {style_guide_path.parent}")

        if not style_guide_path.exists():
            raise FileNotFoundError(f"Target style guide file does not exist: {style_guide_path}")

        content = style_guide_path.read_text(encoding="utf-8")
        table_pattern = re.compile(r"\| Role \| Purpose \| Default \(light\) \| Default \(dark\) \|.*?\n(?:\|.*?\|\n)+", re.DOTALL)
        if not table_pattern.search(content):
            raise ValueError(f"Could not locate semantic roles table pattern in {style_guide_path}")

        updated_content = table_pattern.sub(table_text + "\n", content, count=1)

        # Atomic write using backup file (.bak) and temp file
        backup_path = style_guide_path.with_name(style_guide_path.name + ".bak")
        style_guide_path.replace(backup_path)

        try:
            temp_file = style_guide_path.with_name(style_guide_path.name + ".tmp")
            temp_file.write_text(updated_content, encoding="utf-8")
            temp_file.replace(style_guide_path)
            # Remove temporary backup upon successful write
            if backup_path.exists():
                backup_path.unlink()
        except Exception as e:
            # Restore from backup in case of write failure
            if backup_path.exists():
                backup_path.replace(style_guide_path)
            raise IOError(f"Atomic write to style guide failed: {e}") from e

    return table_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Automated Brand Onboarding CLI Tool for diagram-design.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Website URL to extract brand tokens from")
    group.add_argument("--folder", help="Local directory path containing CSS/SCSS/JSON design tokens")
    parser.add_argument("--apply", action="store_true", help="Explicitly write updated tokens table to style-guide.md (default is preview mode)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit preview mode (default behavior)")
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

        raw_tokens, warnings = extract_tokens(content)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    for warn in warnings:
        print(warn, file=sys.stderr)
    print(f"Extracted Raw Tokens: {raw_tokens}")

    roles, contrast_notes = compute_derived_roles(raw_tokens)
    for note in contrast_notes:
        print(f"[WCAG AA] {note}")

    try:
        table_output = update_style_guide(roles, style_guide_path, apply_changes=args.apply)
    except Exception as e:
        print(f"Error updating style guide: {e}", file=sys.stderr)
        return 1

    print("\n--- Proposed Tokens Table ---")
    print(table_output)

    if args.apply:
        print(f"\n[Apply mode] Successfully updated {style_guide_path}")
    else:
        print("\n[Preview mode] No changes were written to style-guide.md. Use --apply to commit changes.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
