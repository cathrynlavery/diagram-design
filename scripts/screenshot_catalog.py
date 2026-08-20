"""Shared helpers for the canonical README screenshot catalog."""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/diagram-design/SKILL.md"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
SCREENSHOT_DIR = ROOT / "docs/screenshots"
MANIFEST = SCREENSHOT_DIR / "manifest.json"


def canonical_slugs() -> list[str]:
    """Return the visual-type order declared by SKILL.md's selection table."""

    markdown = SKILL.read_text(encoding="utf-8")
    start = markdown.find("### Visual-type guide")
    end = markdown.find("Rules of thumb", start)
    if start < 0 or end < 0:
        raise ValueError("SKILL.md visual-type guide is missing")
    return re.findall(
        r"^\|[^\n]*\]\(references/type-([a-z0-9-]+)\.md\)\s*\|$",
        markdown[start:end],
        re.MULTILINE,
    )


def source_path(slug: str) -> Path:
    return ASSET_DIR / f"example-{slug}.html"


def screenshot_path(slug: str) -> Path:
    return SCREENSHOT_DIR / f"{slug}.png"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"not a PNG: {path}")
    return struct.unpack(">II", header[16:24])
