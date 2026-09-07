#!/usr/bin/env python3
"""Fail when a canonical example or committed screenshot drifts from its manifest."""

from __future__ import annotations

import json
import sys

from screenshot_catalog import (
    MANIFEST,
    ROOT,
    canonical_slugs,
    png_dimensions,
    screenshot_path,
    sha256,
    source_path,
)


def main() -> int:
    errors: list[str] = []
    slugs = canonical_slugs()
    if len(slugs) != 39 or len(slugs) != len(set(slugs)):
        errors.append(f"expected 39 unique canonical types; found {len(slugs)}")

    if not MANIFEST.is_file():
        errors.append("docs/screenshots/manifest.json is missing")
        payload: dict[str, object] = {}
    else:
        try:
            payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"cannot read screenshot manifest: {exc}")
            payload = {}

    if payload.get("schema_version") != 1:
        errors.append("screenshot manifest schema_version must be 1")
    renderer = payload.get("renderer")
    expected_renderer = {
        "engine": "playwright-chromium",
        "scale": 2.0,
        "viewport": [1440, 1000],
        "capture": "first-svg",
        "font_gate": "document.fonts.ready",
    }
    if renderer != expected_renderer:
        errors.append("screenshot manifest must use the canonical 1440x1000, 2x SVG renderer")

    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        errors.append("screenshot manifest entries must be a list")
        entries = []
    manifest_slugs = [entry.get("slug") for entry in entries if isinstance(entry, dict)]
    if manifest_slugs != slugs:
        errors.append("screenshot manifest order does not match SKILL.md's canonical type order")

    by_slug = {
        entry.get("slug"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("slug"), str)
    }
    for slug in slugs:
        source = source_path(slug)
        screenshot = screenshot_path(slug)
        entry = by_slug.get(slug)
        if not source.is_file():
            errors.append(f"missing canonical example: {source.relative_to(ROOT)}")
            continue
        if not screenshot.is_file():
            errors.append(f"missing canonical screenshot: {screenshot.relative_to(ROOT)}")
            continue
        if not entry:
            errors.append(f"manifest has no entry for {slug}")
            continue

        expected_source = source.relative_to(ROOT).as_posix()
        expected_screenshot = screenshot.relative_to(ROOT).as_posix()
        if entry.get("source") != expected_source:
            errors.append(f"{slug}: manifest source must be {expected_source}")
        if entry.get("screenshot") != expected_screenshot:
            errors.append(f"{slug}: manifest screenshot must be {expected_screenshot}")
        if entry.get("source_sha256") != sha256(source):
            errors.append(f"{slug}: source changed; rerun scripts/render-canonical-screenshots.py")
        if entry.get("screenshot_sha256") != sha256(screenshot):
            errors.append(f"{slug}: screenshot changed without a matching manifest refresh")
        try:
            width, height = png_dimensions(screenshot)
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if [entry.get("width"), entry.get("height")] != [width, height]:
                errors.append(f"{slug}: manifest dimensions do not match the PNG")

    if errors:
        print("FAIL screenshot freshness")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("OK screenshot freshness: 39 canonical sources and PNG digests match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
