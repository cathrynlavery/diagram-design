#!/usr/bin/env python3
"""Rasterize a generated diagram's <svg> to a transparent PNG.

Usage: python export_png.py <src.html> <out.png> [scale]

Uses the first Playwright engine that is actually installed (WebKit,
Chromium, then Firefox) — nothing in this path is engine-specific, it loads
a local HTML file and screenshots one element. Only the expected
"Executable doesn't exist" launch failure advances the fallback; any other
launch error (crash, permissions, misconfiguration) propagates with its
real message so it is never misreported as a missing browser.
"""

from __future__ import annotations

import pathlib
import sys


ENGINE_ORDER = ("webkit", "chromium", "firefox")


def is_missing_executable(exc: Exception) -> bool:
    """True only for Playwright's browser-not-installed launch failure."""
    return "executable doesn't exist" in str(exc).lower()


def pick_engine(launchers):
    """Launch the first available engine from (name, launch_callable) pairs.

    Skips engines whose executable is not installed, recording each skip.
    Any other launch failure is re-raised immediately — a crash or a
    permission error must never be reported as "no engine installed".
    Returns (name, browser). Raises SystemExit listing every engine tried
    when none is installed.
    """
    skipped = []
    for name, launch in launchers:
        try:
            return name, launch()
        except Exception as exc:  # noqa: BLE001 — filtered immediately below
            if is_missing_executable(exc):
                skipped.append(f"{name}: not installed")
                continue
            raise
    tried = "; ".join(skipped) if skipped else "none attempted"
    raise SystemExit(
        "No Playwright browser engine is installed ({}).\n"
        "Install any one of them, e.g.: playwright install webkit".format(tried)
    )


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    src, out = argv[1], argv[2]
    scale = float(argv[3]) if len(argv) > 3 else 2

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        name, browser = pick_engine(
            [(engine, getattr(p, engine).launch) for engine in ENGINE_ORDER]
        )
        page = browser.new_page(device_scale_factor=scale)
        page.goto(f"file://{pathlib.Path(src).resolve()}")
        page.wait_for_load_state("networkidle")
        page.locator("svg").first.screenshot(path=out, omit_background=True)
        browser.close()
    print(f"ok: engine={name} scale={scale} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
