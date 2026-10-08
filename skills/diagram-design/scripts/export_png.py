#!/usr/bin/env python3
"""Rasterize the first SVG in a diagram HTML file with Playwright."""

from __future__ import annotations

import argparse
import math
import pathlib
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

NETWORK_IDLE_TIMEOUT_MS = 15_000
FALLBACK_SETTLE_MS = 4_000


def exact_size_scale(value: str) -> float:
    try:
        scale = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("scale must be a number") from exc
    if not math.isfinite(scale) or not 1 <= scale <= 4:
        raise argparse.ArgumentTypeError("scale must be between 1 and 4")
    return scale


def rasterize(
    src: pathlib.Path,
    out: pathlib.Path,
    scale: float = 2,
    *,
    network_idle_timeout_ms: int = NETWORK_IDLE_TIMEOUT_MS,
    fallback_settle_ms: int = FALLBACK_SETTLE_MS,
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(device_scale_factor=scale)
            page.goto(src.resolve().as_uri(), wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=network_idle_timeout_ms)
            except PlaywrightTimeoutError:
                # Proxied networks may stall webfont subrequests past any deadline.
                # Cancel the outstanding load so capture cannot block on it again.
                page.evaluate("window.stop()")
                page.wait_for_timeout(fallback_settle_ms)
                print(
                    "warning: webfont request stalled - captured with fallback "
                    "typography; the PNG may not match the intended fonts",
                    file=sys.stderr,
                )
            svg = page.locator("svg").first
            # Release every clipping ancestor so a wide SVG is captured whole.
            svg.evaluate(
                "el => { for (let a = el.parentElement; a; a = a.parentElement) "
                "a.style.setProperty('overflow', 'visible', 'important'); }"
            )
            svg.screenshot(path=out, omit_background=True)
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=pathlib.Path, help="diagram HTML input")
    parser.add_argument("out", type=pathlib.Path, help="PNG output")
    parser.add_argument("scale", nargs="?", type=exact_size_scale, default=2)
    args = parser.parse_args()
    rasterize(args.src, args.out, args.scale)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
