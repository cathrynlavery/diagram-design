#!/usr/bin/env python3
"""Verify RTL and Arabic typography, bidi rules, and layout contracts.

Ensures that diagrams containing Arabic text or RTL layout adhere to the
guidelines in style-guide.md:
1. Root direction: <html> has dir="rtl" or <svg> has direction="rtl".
2. Font stack: Arabic text uses an approved font family (Cairo, Noto Naskh Arabic).
3. Font size floor: Arabic text maintains at least 11px font size (no 7-8px mono slots).
4. Text anchor: Right-inset alignment in RTL uses text-anchor="start", not text-anchor="end".
5. Invariant viewBox: viewBox is not mirrored or inverted.
6. Mask height: Label masks for Arabic text are at least 16px tall.
7. Bidi isolation: Mixed Latin code identifiers are isolated in separate <text> elements.

Usage:
    python3 scripts/verify-rtl.py [--all] [files ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
APPROVED_ARABIC_FONTS = {"cairo", "noto naskh arabic", "segoe ui", "geeza pro", "amiri"}
LATIN_CODE_RE = re.compile(r"\b[A-Z][A-Z0-9_/-]{2,}\b")

VIEWBOX_RE = re.compile(r'\bviewBox="(?P<vx>[^"]+)"', re.IGNORECASE)
TEXT_TAG_RE = re.compile(
    r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>",
    re.IGNORECASE | re.DOTALL,
)
RECT_RE = re.compile(
    r"<rect\b(?P<attrs>[^>]*?)\bheight=\"(?P<h>[\d.]+)\"[^>]*>",
    re.IGNORECASE,
)


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def check(path: Path) -> list[str]:
    """Check a single diagram file for RTL / Arabic contract compliance."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as err:
        return [f"{path}: read error: {err}"]

    has_arabic = bool(ARABIC_RE.search(source))
    is_rtl = 'dir="rtl"' in source or 'direction="rtl"' in source

    if not has_arabic and not is_rtl:
        return []

    findings: list[str] = []

    # 1. Root direction contract
    if has_arabic and not is_rtl:
        findings.append(
            f"{path}: Arabic text found but neither <html> nor <svg> specifies RTL direction "
            "(dir='rtl' or direction='rtl')"
        )

    # 2. Invariant viewBox contract
    for vb_match in VIEWBOX_RE.finditer(source):
        parts = vb_match.group("vx").strip().split()
        if len(parts) == 4:
            try:
                min_x, min_y, w, h = (float(v) for v in parts)
                if w < 0 or h < 0:
                    findings.append(
                        f"{path}: line {line_number(source, vb_match.start())}: SVG viewBox must "
                        "not use negative width/height; RTL flow is a coordinate layout decision"
                    )
            except ValueError:
                pass

    # 3. Text element checks (font-family, floor, text-anchor, bidi isolation)
    for match in TEXT_TAG_RE.finditer(source):
        attrs = match.group("attrs")
        body = match.group("body")
        offset = match.start()
        line = line_number(source, offset)

        has_arabic_text = bool(ARABIC_RE.search(body))

        # Check text-anchor="end" in RTL context
        if is_rtl or 'direction="rtl"' in attrs:
            if 'text-anchor="end"' in attrs.lower():
                findings.append(
                    f"{path}: line {line}: RTL text uses text-anchor='end'; right-edge alignment "
                    "in RTL requires text-anchor='start' (start anchors at logical right edge)"
                )

        if has_arabic_text:
            # Check font-size floor (11px)
            fs_match = re.search(r'\bfont-size="(?P<size>[\d.]+)"', attrs, re.IGNORECASE)
            if not fs_match:
                fs_match = re.search(r'font-size:\s*(?P<size>[\d.]+)px', attrs, re.IGNORECASE)
            if fs_match:
                try:
                    size = float(fs_match.group("size"))
                    if size < 11.0:
                        findings.append(
                            f"{path}: line {line}: Arabic text font-size {size:g}px is below "
                            "the 11px rendering floor"
                        )
                except ValueError:
                    pass

            # Check font-family stack
            ff_match = re.search(r'\bfont-family="(?P<ff>[^"]+)"', attrs, re.IGNORECASE)
            if not ff_match:
                ff_match = re.search(r'font-family:\s*([^;"]+)', attrs, re.IGNORECASE)
            if ff_match:
                declared_ff = ff_match.group(1).lower()
                if not any(approved in declared_ff for approved in APPROVED_ARABIC_FONTS) and "var(--font-sans)" not in declared_ff and "var(--font-serif)" not in declared_ff:
                    findings.append(
                        f"{path}: line {line}: Arabic <text> lacks an approved Arabic font family "
                        "(Cairo, Noto Naskh Arabic) in its font-family stack"
                    )

            # Check bidi isolation: inline Latin code token inside Arabic string
            latin_matches = LATIN_CODE_RE.findall(body)
            if latin_matches and len(body.strip()) > len(latin_matches[0]):
                # Latin code identifier embedded in an Arabic text node
                for code in latin_matches:
                    findings.append(
                        f"{path}: line {line}: mixed Latin code identifier {code!r} inline in "
                        "Arabic text; must be on its own <text> element in Geist Mono to prevent "
                        "bidi layout corruption"
                    )

    # 4. Mask height contract for Arabic label masks
    # Look for label masks (small rects near text)
    if has_arabic:
        for match in RECT_RE.finditer(source):
            height = float(match.group("h"))
            # Eyebrow / arrow label mask rects typically have height 8..15px in Latin diagrams
            if 6.0 <= height < 16.0:
                # Check if this rect is used near Arabic text or in an RTL diagram template
                line = line_number(source, match.start())
                findings.append(
                    f"{path}: line {line}: label mask rect height {height:g}px is below the 16px "
                    "requirement for 11px Arabic text"
                )

    return findings


def targets(args: argparse.Namespace) -> list[Path]:
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(p) for p in args.files]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="HTML diagrams to check")
    parser.add_argument("--all", action="store_true", help="check all assets in assets/")
    args = parser.parse_args()

    paths = targets(args)
    if not paths:
        parser.error("pass one or more files, or --all")

    findings: list[str] = []
    checked = 0
    for path in paths:
        if not path.is_file():
            continue
        checked += 1
        findings.extend(check(path))

    for finding in findings:
        print(finding)

    print(f"Summary: {checked} file(s) checked, {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
