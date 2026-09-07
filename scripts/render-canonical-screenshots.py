#!/usr/bin/env python3
"""Render the 39 canonical minimal-light examples and record their digests."""

from __future__ import annotations

import json

from playwright.sync_api import sync_playwright

from screenshot_catalog import (
    MANIFEST,
    ROOT,
    SCREENSHOT_DIR,
    canonical_slugs,
    png_dimensions,
    screenshot_path,
    sha256,
    source_path,
)


def main() -> int:
    slugs = canonical_slugs()
    if len(slugs) != 39 or len(slugs) != len(set(slugs)):
        raise SystemExit(f"expected 39 unique canonical types; found {len(slugs)}")

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1440, "height": 1000},
            device_scale_factor=2,
        )
        for index, slug in enumerate(slugs, 1):
            source = source_path(slug)
            output = screenshot_path(slug)
            if not source.is_file():
                raise SystemExit(f"missing canonical example: {source.relative_to(ROOT)}")

            page.goto(source.resolve().as_uri(), wait_until="networkidle")
            page.evaluate("() => document.fonts.ready")
            svg = page.locator("svg").first
            if svg.count() != 1:
                raise SystemExit(f"no first SVG found in {source.relative_to(ROOT)}")
            svg.screenshot(path=str(output), omit_background=True)
            width, height = png_dimensions(output)
            entries.append(
                {
                    "slug": slug,
                    "source": source.relative_to(ROOT).as_posix(),
                    "screenshot": output.relative_to(ROOT).as_posix(),
                    "source_sha256": sha256(source),
                    "screenshot_sha256": sha256(output),
                    "width": width,
                    "height": height,
                }
            )
            print(f"[{index:02d}/39] {slug}: {width}x{height}")
        browser.close()

    payload = {
        "schema_version": 1,
        "renderer": {
            "engine": "playwright-chromium",
            "scale": 2.0,
            "viewport": [1440, 1000],
            "capture": "first-svg",
            "font_gate": "document.fonts.ready",
        },
        "entries": entries,
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
