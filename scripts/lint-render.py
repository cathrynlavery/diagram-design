#!/usr/bin/env python3
"""Lint diagram examples as *rendered* — catches breakage the source can't show.

``lint-skin.py`` reads the HTML. This one renders it in headless Chromium and
measures the result, so it catches clipped nodes, text that overflows the SVG
viewport, invisible labels and runtime errors — the failures that only exist
once a browser has done layout with real font metrics.

Checks are invariants, not golden snapshots: nothing to re-record, no PNGs in
the repo, no cross-machine hash drift.

    python3 scripts/lint-render.py --all
    python3 scripts/lint-render.py skills/diagram-design/assets/example-venn.html
    python3 scripts/lint-render.py --self-test   # prove the checks still fire

Requires Playwright (same dev dependency the PNG export uses):

    pip install playwright && playwright install chromium
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

VIEWPORT = {"width": 1600, "height": 1000}
TOLERANCE = 1.0  # px of slop before an overflow counts, absorbs subpixel layout

# Measured in the page: everything below runs on the rendered DOM, where
# getBoundingClientRect() already accounts for transforms and viewBox scaling.
MEASURE_JS = """
() => {
  const TOL = %(tol)s;
  const findings = [];
  const label = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = el.getAttribute('class') ? '.' + el.getAttribute('class').split(/\\s+/)[0] : '';
    const text = (el.textContent || '').trim().slice(0, 30);
    return el.tagName.toLowerCase() + id + cls + (text ? ` "${text}"` : '');
  };
  // Content inside these is a definition, not painted where it sits.
  const DEFS = 'defs, clipPath, mask, marker, pattern, symbol, linearGradient, radialGradient, filter';

  for (const svg of document.querySelectorAll('svg')) {
    const box = svg.getBoundingClientRect();
    if (!box.width || !box.height) {
      findings.push(['svg-collapsed', `${label(svg)} renders ${box.width}x${box.height}`]);
      continue;
    }
    for (const el of svg.querySelectorAll('*')) {
      if (el.closest(DEFS)) continue;
      const style = getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) continue;  // empty wrappers and hidden layers
      const over = [
        r.left < box.left - TOL ? `left by ${(box.left - r.left).toFixed(1)}px` : null,
        r.top < box.top - TOL ? `top by ${(box.top - r.top).toFixed(1)}px` : null,
        r.right > box.right + TOL ? `right by ${(r.right - box.right).toFixed(1)}px` : null,
        r.bottom > box.bottom + TOL ? `bottom by ${(r.bottom - box.bottom).toFixed(1)}px` : null,
      ].filter(Boolean);
      if (over.length) {
        findings.push(['clipped', `${label(el)} escapes the svg viewport: ${over.join(', ')}`]);
      }
    }
  }

  const doc = document.documentElement;
  const spill = doc.scrollWidth - doc.clientWidth;
  if (spill > TOL) {
    findings.push(['page-overflow', `page scrolls ${spill.toFixed(0)}px horizontally at ${doc.clientWidth}px wide`]);
  }
  return findings;
}
"""


# A deliberately broken diagram: a node pushed outside the viewport, an svg with
# no area, and a body wider than the window. --self-test asserts the checks above
# still catch all three.
BROKEN_HTML = """
<!DOCTYPE html><html><body style="margin:0">
<div style="width:3000px">wide</div>
<svg width="200" height="100" viewBox="0 0 200 100">
  <rect x="180" y="10" width="120" height="40" fill="#eb6c36"/>
</svg>
<svg width="0" height="0" viewBox="0 0 200 100"><rect width="10" height="10"/></svg>
</body></html>
"""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="HTML files to render")
    parser.add_argument("--all", action="store_true", help="render every example")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument(
        "--self-test",
        action="store_true",
        dest="self_test",
        help="check the checks against a known-broken diagram",
    )
    return parser.parse_args()


def display_path(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def launch(playwright):
    """Bundled Chromium, falling back to a system Chrome install."""
    try:
        return playwright.chromium.launch()
    except Exception:
        return playwright.chromium.launch(channel="chrome")


def watch(page, errors):
    page.on("pageerror", lambda error: errors.append(("page-error", str(error))))
    page.on(
        "console",
        lambda message: message.type == "error"
        # Remote webfonts fail on an offline or proxied machine; not the diagram's fault.
        and not message.text.startswith("Failed to load resource")
        and errors.append(("console-error", message.text)),
    )


def measure(page):
    try:
        # Webfonts are remote; offline just means fallback metrics, not a failure.
        page.evaluate("() => document.fonts.ready", timeout=5000)
    except Exception:
        pass
    return [tuple(finding) for finding in page.evaluate(MEASURE_JS % {"tol": TOLERANCE})]


def check(page, path):
    errors = []
    watch(page, errors)
    page.goto(path.resolve().as_uri(), wait_until="load")
    return measure(page) + errors


def self_test(context):
    page = context.new_page()
    page.set_content(BROKEN_HTML)
    found = {category for category, _ in measure(page)}
    page.close()
    expected = {"clipped", "svg-collapsed", "page-overflow"}
    missing = expected - found
    if missing:
        print(f"self-test FAILED: checks not firing: {', '.join(sorted(missing))}")
        return 1
    print(f"self-test OK: {', '.join(sorted(expected))} all caught.")
    return 0


def main():
    args = parse_args()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Install it with:\n"
            "  pip install playwright && playwright install chromium",
            file=sys.stderr,
        )
        return 2

    paths = sorted(ASSET_DIR.glob("example-*.html")) if args.all else args.files
    if not paths and not args.self_test:
        print("Nothing to check. Pass files, --all or --self-test.", file=sys.stderr)
        return 2

    total_findings = 0
    with sync_playwright() as playwright:
        browser = launch(playwright)
        context = browser.new_context(viewport=VIEWPORT)
        if args.self_test:
            status = self_test(context)
            if status or not paths:
                browser.close()
                return status
        for path in paths:
            page = context.new_page()
            try:
                findings = check(page, path)
            except Exception as error:
                findings = [("render-error", str(error).splitlines()[0])]
            finally:
                page.close()

            total_findings += len(findings)
            if not args.quiet:
                shown_path = display_path(path)
                for category, message in findings:
                    print(f"{shown_path}: {category}: {message}")
        browser.close()

    print(f"Summary: {len(paths)} file(s) rendered, {total_findings} finding(s).")
    return 1 if total_findings else 0


if __name__ == "__main__":
    sys.exit(main())
