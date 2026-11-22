#!/usr/bin/env python3
"""Export a diagram-design HTML file to a print-ready vector PDF with Playwright."""

from __future__ import annotations

import argparse
import pathlib
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

NETWORK_IDLE_TIMEOUT_MS = 15_000
FALLBACK_SETTLE_MS = 4_000

# Margin on every side of a --page-size sheet.
PAGE_MARGIN_MM = 10

# Standard landscape sheet dimensions (width, height) in inches.
PAGE_SIZES: dict[str, tuple[str, str]] = {
    "a4": ("11.69in", "8.27in"),
    "a3": ("16.54in", "11.69in"),
    "letter": ("11in", "8.5in"),
}


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def export_pdf(
    src: pathlib.Path,
    out: pathlib.Path,
    *,
    page_size: str | None = None,
    full_page: bool = False,
    network_idle_timeout_ms: int = NETWORK_IDLE_TIMEOUT_MS,
    fallback_settle_ms: int = FALLBACK_SETTLE_MS,
) -> None:
    if not src.is_file():
        _fail(f"source file not found: {src}")
    if page_size is not None and page_size not in PAGE_SIZES:
        _fail(f"unsupported page size {page_size!r}; choose from {', '.join(sorted(PAGE_SIZES))}")

    resolved = src.resolve()
    if resolved.name == "index.html" and resolved.parent.name == "assets":
        _fail("refusing to export gallery assets/index.html; specify a single diagram HTML file")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(
                resolved.as_uri() + "?motion=static",
                wait_until="domcontentloaded",
            )
            try:
                page.wait_for_load_state("networkidle", timeout=network_idle_timeout_ms)
            except PlaywrightTimeoutError:
                # Proxied networks may stall webfont subrequests past any deadline.
                # Cancel the outstanding load so capture cannot block on it again.
                page.evaluate("window.stop()")
                page.wait_for_timeout(fallback_settle_ms)
                print(
                    "warning: webfont request stalled - captured with fallback "
                    "typography; the PDF may not match the intended fonts",
                    file=sys.stderr,
                )
            page.evaluate("document.fonts.ready")
            if not page.locator("[data-motion-root]").evaluate_all(
                "roots => roots.every(root => root.dataset.frame === 'static')"
            ):
                raise RuntimeError("motion export requires a complete static frame")

            if page.locator("svg").count() == 0:
                _fail(f"no <svg> element found in {src}")

            svg = page.locator("svg").first
            dims = svg.evaluate(
                """el => {
                    const box = el.viewBox && el.viewBox.baseVal;
                    if (!box || ![box.width, box.height].every(n => Number.isFinite(n) && n > 0)) {
                        return null;
                    }
                    return { width: box.width, height: box.height };
                }"""
            )
            if dims is None:
                _fail("PDF export requires a nonzero finite viewBox on the root <svg>")

            if page_size is not None:
                page.emulate_media(media="print")
                if not full_page:
                    sheet_w, sheet_h = PAGE_SIZES[page_size]
                    page.evaluate(
                        """({sheetW, sheetH, marginMm}) => {
                            const svg = document.querySelector('svg');
                            if (!svg) return;
                            const bg = getComputedStyle(document.body).backgroundColor || '#ffffff';
                            document.documentElement.style.background = bg;
                            document.body.innerHTML = '';
                            document.body.style.margin = '0';
                            document.body.style.padding = '0';
                            document.body.style.minHeight = '0';
                            document.body.style.display = 'flex';
                            document.body.style.alignItems = 'center';
                            document.body.style.justifyContent = 'center';
                            document.body.style.background = bg;
                            // Fit the viewBox inside the printable area on both axes, so a
                            // diagram taller than the sheet's aspect is not cut off.
                            const px = inches => parseFloat(inches) * 96;
                            const margin = (marginMm / 25.4) * 96;
                            const availW = px(sheetW) - 2 * margin;
                            const availH = px(sheetH) - 2 * margin;
                            const vb = svg.viewBox.baseVal;
                            const scale = Math.min(availW / vb.width, availH / vb.height);
                            const w = Math.floor(vb.width * scale);
                            const h = Math.floor(vb.height * scale);
                            document.body.style.height = `${Math.floor(availH)}px`;
                            svg.style.setProperty('width', `${w}px`, 'important');
                            svg.style.setProperty('height', `${h}px`, 'important');
                            svg.style.setProperty('min-width', '0', 'important');
                            svg.style.setProperty('max-width', 'none', 'important');
                            svg.style.setProperty('display', 'block', 'important');
                            document.body.appendChild(svg);
                        }""",
                        {"sheetW": sheet_w, "sheetH": sheet_h, "marginMm": PAGE_MARGIN_MM},
                    )
                else:
                    page.evaluate(
                        """() => {
                            document.querySelectorAll('[data-motion-controls], [data-motion-decorative]')
                                .forEach(el => el.remove());
                        }"""
                    )
                width, height = PAGE_SIZES[page_size]
                page.pdf(
                    path=str(out),
                    width=width,
                    height=height,
                    print_background=True,
                    margin={side: f"{PAGE_MARGIN_MM}mm" for side in ("top", "right", "bottom", "left")},
                )
            elif full_page:
                page.emulate_media(media="screen")
                page.evaluate(
                    """() => {
                        document.querySelectorAll('[data-motion-controls], [data-motion-decorative]')
                            .forEach(el => el.remove());
                        document.querySelectorAll('.diagram-container').forEach(el => {
                            el.style.setProperty('overflow', 'visible', 'important');
                        });
                    }"""
                )
                body_box = page.evaluate(
                    """() => {
                        const rect = document.documentElement.getBoundingClientRect();
                        return {
                            width: Math.max(Math.ceil(document.documentElement.scrollWidth), Math.ceil(rect.width)),
                            height: Math.max(Math.ceil(document.documentElement.scrollHeight), Math.ceil(rect.height)),
                        };
                    }"""
                )
                page.pdf(
                    path=str(out),
                    width=f"{body_box['width']}px",
                    height=f"{body_box['height']}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
            else:
                # Diagram-only exact-bounds vector PDF: preserve screen palette (dark/light)
                # and size the page to exactly 1 CSS px per viewBox unit.
                page.emulate_media(media="screen")
                page.evaluate(
                    """({width, height}) => {
                        const svg = document.querySelector('svg');
                        if (!svg) return;
                        const bg = getComputedStyle(document.body).backgroundColor || '#ffffff';
                        const style = document.createElement('style');
                        style.textContent = `@page { size: ${width}px ${height}px; margin: 0; }`;
                        document.head.appendChild(style);
                        document.documentElement.style.margin = '0';
                        document.documentElement.style.padding = '0';
                        document.documentElement.style.background = bg;
                        document.body.innerHTML = '';
                        document.body.style.margin = '0';
                        document.body.style.padding = '0';
                        document.body.style.minHeight = '0';
                        document.body.style.width = `${width}px`;
                        document.body.style.height = `${height}px`;
                        document.body.style.overflow = 'hidden';
                        document.body.style.background = bg;
                        for (const [axis, size] of [['width', width], ['height', height]]) {
                            for (const prefix of ['', 'min-', 'max-']) {
                                svg.style.setProperty(prefix + axis, `${size}px`, 'important');
                            }
                        }
                        svg.style.setProperty('display', 'block', 'important');
                        document.body.appendChild(svg);
                    }""",
                    dims,
                )
                page.pdf(
                    path=str(out),
                    width=f"{dims['width']}px",
                    height=f"{dims['height']}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=pathlib.Path, help="diagram HTML input")
    parser.add_argument("out", nargs="?", type=pathlib.Path, default=None, help="PDF output (default: <src>.pdf)")
    parser.add_argument(
        "--page-size",
        choices=sorted(PAGE_SIZES),
        default=None,
        help="fit onto a landscape sheet (a4, a3, letter) instead of exact viewBox bounds",
    )
    parser.add_argument(
        "--full-page",
        action="store_true",
        help="include editorial header, cards, and footer instead of diagram-only SVG",
    )
    args = parser.parse_args(argv)
    out = args.out if args.out is not None else args.src.with_suffix(".pdf")
    export_pdf(args.src, out, page_size=args.page_size, full_page=args.full_page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
