#!/usr/bin/env python3
"""Rendered diagram layout validator for diagram-design.

Renders HTML diagrams in headless Chromium via Playwright and measures laid-out geometries to catch:
  - clipped: elements escaping their <svg> viewport boundaries
  - svg-collapsed: <svg> elements rendering with zero width or height
  - page-overflow: horizontal document scrolling at export width (1600px)
  - page-error / console-error: JavaScript runtime exceptions or asset errors

Usage:
    python scripts/lint-render.py --all
    python scripts/lint-render.py skills/diagram-design/assets/example-venn.html
    python scripts/lint-render.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

REPO = pathlib.Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO / "skills" / "diagram-design" / "assets"
FIXTURES_DIR = REPO / "scripts" / "fixtures"


def check_playwright() -> Any:
    """Check if Playwright is installed; exit 2 with install guide if missing."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print(
            "Playwright missing. Install required dependencies:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        sys.exit(2)


# JS snippet evaluated in browser to measure rendered geometries & check overflow
JS_MEASURE_LAYOUT = """
() => {
    const findings = [];
    const SKIP_TAGS = new Set(['defs', 'clippath', 'mask', 'marker', 'pattern', 'symbol', 'style', 'script']);

    function isInsideSkipContainer(el) {
        let parent = el.parentElement;
        while (parent && parent.nodeName) {
            if (SKIP_TAGS.has(parent.nodeName.toLowerCase())) return true;
            parent = parent.parentElement;
        }
        return false;
    }

    // 1. Check for horizontal page overflow at 1600px
    if (document.documentElement.scrollWidth > 1600 + 4) {
        findings.push({
            category: 'page-overflow',
            message: `document scrolls horizontally at 1600px: scrollWidth = ${document.documentElement.scrollWidth}px`
        });
    }

    // 2. Check each <svg> container
    const svgs = Array.from(document.querySelectorAll('svg'));
    svgs.forEach((svg, idx) => {
        const svgRect = svg.getBoundingClientRect();
        if (svgRect.width <= 0 || svgRect.height <= 0) {
            findings.push({
                category: 'svg-collapsed',
                message: `<svg #${svg.id || idx}> rendered with zero dimensions: ${svgRect.width}x${svgRect.height}`
            });
            return;
        }

        // Check painted child elements for viewport escape
        const elements = Array.from(svg.querySelectorAll('*'));
        elements.forEach(el => {
            const tag = el.nodeName.toLowerCase();
            if (SKIP_TAGS.has(tag) || isInsideSkipContainer(el)) return;

            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return;

            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 && rect.height <= 0) return;

            const rightEscape = rect.right - svgRect.right;
            const bottomEscape = rect.bottom - svgRect.bottom;
            const leftEscape = svgRect.left - rect.left;
            const topEscape = svgRect.top - rect.top;

            const maxEscape = Math.max(rightEscape, bottomEscape, leftEscape, topEscape);
            if (maxEscape > 2.0) {
                findings.push({
                    category: 'clipped',
                    message: `<${tag}> escapes svg viewport boundary by ${maxEscape.toFixed(1)}px`
                });
            }
        });
    });

    return findings;
}
"""


def lint_file(page: Any, html_path: pathlib.Path) -> list[dict[str, str]]:
    """Render a single HTML file in Playwright and measure layout invariants."""
    findings: list[dict[str, str]] = []
    console_errors: list[str] = []

    def on_console(msg: Any) -> None:
        if msg.type == "error":
            text = msg.text
            # Filter remote Google WebFont network timeouts when running offline/proxied
            if any(domain in text for domain in ("fonts.googleapis.com", "fonts.gstatic.com")):
                return
            console_errors.append(text)

    page.on("console", on_console)
    file_url = html_path.as_uri()

    try:
        page.goto(file_url, wait_until="load", timeout=10000)

        # Wait for webfonts to finish loading (resolving TypeError in evaluate calls)
        try:
            page.wait_for_function("document.fonts.status === 'loaded'", timeout=3000)
        except Exception:
            pass

        res = page.evaluate(JS_MEASURE_LAYOUT)
        if isinstance(res, list):
            for item in res:
                findings.append({"file": str(html_path), "category": item["category"], "message": item["message"]})

        for err in console_errors:
            findings.append({"file": str(html_path), "category": "console-error", "message": err})

    except Exception as e:
        findings.append({"file": str(html_path), "category": "page-error", "message": str(e)})

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Rendered diagram layout validator.")
    parser.add_argument("file", nargs="?", help="Path to specific HTML diagram file to lint")
    parser.add_argument("--all", action="store_true", help="Lint all HTML files in skills/diagram-design/assets/")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")

    args = parser.parse_args()
    sync_playwright = check_playwright()

    files_to_lint: list[pathlib.Path] = []
    if args.file:
        p = pathlib.Path(args.file)
        if p.exists():
            files_to_lint.append(p)
    elif args.all:
        files_to_lint = list(ASSETS_DIR.glob("*.html"))

    if not files_to_lint:
        parser.print_help()
        return 0

    all_findings: list[dict[str, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1600, "height": 1200})
        page = context.new_page()

        for html_file in files_to_lint:
            findings = lint_file(page, html_file)
            all_findings.extend(findings)

        browser.close()

    if all_findings:
        for f in all_findings:
            print(f"{f['category']}: {f['file']}: {f['message']}")
        return 1

    if not args.quiet:
        print(f"OK: {len(files_to_lint)} file(s) rendered, 0 finding(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
