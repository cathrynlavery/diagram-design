#!/usr/bin/env python3
"""Vendored web fonts for fully offline diagram output.

The shipped templates load Instrument Serif, Geist, Geist Mono and the Noto
fallbacks from Google Fonts at render time. Offline, that `<link>` silently
degrades to system fonts and a PNG export rasterises the wrong typography.

`bootstrap.py` downloads every `@font-face` slice Google serves for those
families once, into `local-agent/fonts/`, next to a `fonts.json` manifest.
This module then embeds the slices a document actually needs as base64
`@font-face` rules, so a generated `.html` or exported `.svg` stays a single
self-contained file that renders identically with the network unplugged.

Only the slices whose `unicode-range` intersects the document's text are
embedded (Latin always), so an English diagram carries ~10 faces rather than
the full Cyrillic/Greek/Vietnamese set, and a Korean one picks up the KR
slices automatically when they have been vendored with `bootstrap.py --cjk`.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "fonts"
MANIFEST = FONT_DIR / "fonts.json"

# The families assets/template.html requests, in the same order.
CORE_FAMILIES: tuple[tuple[str, str], ...] = (
    ("Instrument Serif", "ital@0;1"),
    ("Geist", "wght@400;500;600"),
    ("Geist Mono", "wght@400;500;600"),
    ("Noto Serif", "ital@0;1"),
)
# Requested by the template for CJK labels; ~1000 slices, so opt-in.
CJK_FAMILIES: tuple[tuple[str, str], ...] = (
    ("Noto Sans KR", "wght@400;500;600"),
    ("Noto Serif KR", "wght@400"),
    ("Noto Sans TC", "wght@400;500;600"),
    ("Noto Serif TC", "wght@400"),
)
# template-terminal.html asks for a bold Geist Mono the others do not.
TERMINAL_FAMILIES: tuple[tuple[str, str], ...] = (("Geist Mono", "wght@400;500;600;700"),)

GOOGLE_LINK_RE = re.compile(
    r"""<link\b[^>]*\bhref\s*=\s*["']https://fonts\.googleapis\.com/css2\?[^"']*["'][^>]*>""",
    re.IGNORECASE,
)
FACE_BLOCK_RE = re.compile(
    r"/\*\s*(?P<subset>[^*]+?)\s*\*/\s*@font-face\s*\{(?P<body>.*?)\}", re.DOTALL
)
DECL_RE = re.compile(r"([a-z-]+)\s*:\s*([^;]+);")
RANGE_RE = re.compile(r"U\+([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?")


@dataclass(frozen=True)
class Face:
    family: str
    style: str
    weight: str
    subset: str
    unicode_range: str
    file: str

    @property
    def ranges(self) -> list[tuple[int, int]]:
        out = []
        for lo, hi in RANGE_RE.findall(self.unicode_range):
            start = int(lo, 16)
            out.append((start, int(hi, 16) if hi else start))
        return out

    def covers(self, codepoints: set[int]) -> bool:
        return any(lo <= cp <= hi for lo, hi in self.ranges for cp in codepoints)

    def slug(self) -> str:
        fam = re.sub(r"[^a-z0-9]+", "-", self.family.casefold()).strip("-")
        sub = re.sub(r"[^a-z0-9]+", "-", self.subset.casefold()).strip("-")
        return f"{fam}-{self.weight}-{self.style}-{sub}.woff2"


def parse_css2(css: str) -> list[tuple[Face, str]]:
    """Parse a Google Fonts css2 stylesheet into (face, remote url) pairs."""
    faces: list[tuple[Face, str]] = []
    for match in FACE_BLOCK_RE.finditer(css):
        decls = {k.strip(): v.strip() for k, v in DECL_RE.findall(match.group("body"))}
        src = re.search(r"url\(([^)]+)\)", decls.get("src", ""))
        if not src:
            continue
        family = decls.get("font-family", "").strip("'\"")
        face = Face(
            family=family,
            style=decls.get("font-style", "normal"),
            weight=decls.get("font-weight", "400"),
            subset=match.group("subset"),
            unicode_range=decls.get("unicode-range", ""),
            file="",
        )
        faces.append((Face(**{**face.__dict__, "file": face.slug()}), src.group(1).strip("'\"")))
    return faces


def css2_url(families: tuple[tuple[str, str], ...]) -> str:
    query = "&".join(f"family={name.replace(' ', '+')}:{axes}" for name, axes in families)
    return f"https://fonts.googleapis.com/css2?{query}&display=swap"


def load_manifest(manifest: Path | None = None) -> list[Face]:
    manifest = manifest or MANIFEST
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text(encoding="utf-8"))
    return [Face(**entry) for entry in data.get("faces", [])]


def available_families(faces: list[Face] | None = None) -> list[str]:
    faces = load_manifest() if faces is None else faces
    seen: dict[str, None] = {}
    for face in faces:
        seen.setdefault(face.family, None)
    return list(seen)


def document_families(text: str, faces: list[Face]) -> list[str]:
    """Families the document names anywhere (CSS stack or SVG attribute)."""
    return [family for family in available_families(faces) if family in text]


def document_codepoints(text: str) -> set[int]:
    return {ord(char) for char in text if ord(char) > 0x7F}


def select_faces(text: str, faces: list[Face] | None = None) -> list[Face]:
    """The vendored faces a document needs: its families, its scripts."""
    faces = load_manifest() if faces is None else faces
    families = set(document_families(text, faces))
    codepoints = document_codepoints(text)
    chosen = []
    for face in faces:
        if face.family not in families:
            continue
        if face.subset == "latin" or face.covers(codepoints):
            chosen.append(face)
    return chosen


def face_css(face: Face, font_dir: Path | None = None) -> str:
    font_dir = font_dir or FONT_DIR
    payload = base64.b64encode((font_dir / face.file).read_bytes()).decode("ascii")
    return (
        "@font-face{"
        f"font-family:'{face.family}';"
        f"font-style:{face.style};"
        f"font-weight:{face.weight};"
        "font-display:swap;"
        f"src:url(data:font/woff2;base64,{payload}) format('woff2');"
        f"unicode-range:{face.unicode_range};"
        "}"
    )


def embedded_css(text: str, faces: list[Face] | None = None, font_dir: Path | None = None) -> str:
    chosen = select_faces(text, faces)
    if not chosen:
        return ""
    lines = ["/* vendored fonts — embedded for offline rendering */"]
    lines.extend(face_css(face, font_dir) for face in chosen)
    return "\n".join(lines)


def inline_html_fonts(html: str, faces: list[Face] | None = None, font_dir: Path | None = None) -> str:
    """Replace the Google Fonts <link> with embedded @font-face rules.

    A document with no Google link is returned unchanged: it is either already
    inlined or does not use web fonts.
    """
    match = GOOGLE_LINK_RE.search(html)
    if not match:
        return html
    css = embedded_css(html, faces, font_dir)
    if not css:
        raise RuntimeError(
            "no vendored fonts found; run `python local-agent/bootstrap.py` once while online"
        )
    return html[: match.start()] + f"<style>\n{css}\n  </style>" + html[match.end() :]


def is_inlined(html: str) -> bool:
    return "vendored fonts" in html and not GOOGLE_LINK_RE.search(html)
