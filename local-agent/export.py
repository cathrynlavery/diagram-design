#!/usr/bin/env python3
"""Offline SVG and PNG export for a generated diagram HTML file.

    python local-agent/export.py diagram.html            # diagram.svg + diagram.png
    python local-agent/export.py diagram.html --svg-only
    python local-agent/export.py diagram.html --png-only --scale 3

Follows skills/diagram-design/references/export.md step for step, with one
substitution: where that procedure injects a Google Fonts ``@import`` into
the standalone SVG, this one embeds the vendored ``@font-face`` slices, so
the .svg carries its own typography. The PNG renders the HTML in a local
Chromium with every network request blocked — if it looks right, it is
provably offline.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fonts  # noqa: E402

SVG_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
RGBA_RE = re.compile(
    r'(fill|stroke)="rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d*\.?\d+)\s*\)"'
)
PLAYWRIGHT_HINT = (
    "Playwright isn't installed. To enable PNG export, run once while online:\n"
    "    python local-agent/bootstrap.py --playwright"
)


class ExportError(RuntimeError):
    pass


def extract_svg(html: str, name: str = "") -> str:
    if name == "index.html":
        raise ExportError("this is the gallery; pass a single diagram file")
    matches = [m for m in SVG_RE.findall(html) if 'aria-hidden="true"' not in m[:200]]
    if not matches:
        raise ExportError("no <svg> block found; this is not a diagram file")
    if len(matches) > 1:
        print(f"warning: {len(matches)} SVGs found; exporting the first", file=sys.stderr)
    return matches[0]


def normalize_colors(svg: str) -> str:
    """Lossless rgba()/transparent rewrite for strict SVG 1.1 importers."""
    svg = RGBA_RE.sub(
        lambda m: '{0}="#{1:02x}{2:02x}{3:02x}" {0}-opacity="{4}"'.format(
            m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
        ),
        svg,
    )
    return re.sub(r'(fill|stroke)="transparent"', r'\1="none"', svg)


def inject_style(svg: str, css: str) -> str:
    style = f"<style>{css}</style>"
    if "<defs>" in svg:
        return svg.replace("<defs>", f"<defs>{style}", 1)
    # After <title> and <desc>, which must stay the first children.
    match = re.search(r"</desc>\s*", svg)
    if match:
        return svg[: match.end()] + f"<defs>{style}</defs>" + svg[match.end() :]
    open_end = svg.index(">") + 1
    return svg[:open_end] + f"<defs>{style}</defs>" + svg[open_end:]


def standalone_svg(html: str, faces: list[fonts.Face] | None = None, font_dir: Path | None = None, name: str = "") -> str:
    svg = extract_svg(html, name)
    open_tag_end = svg.index(">")
    if "xmlns=" not in svg[:open_tag_end]:
        svg = svg[:4] + ' xmlns="http://www.w3.org/2000/svg"' + svg[4:]
    if "viewBox=" not in svg[:open_tag_end + 40]:
        print("warning: <svg> has no viewBox; consumers will size it unpredictably", file=sys.stderr)
    css = fonts.embedded_css(svg, faces, font_dir)
    if css:
        if "<" in css or "&" in css:
            raise ExportError("embedded font CSS contains XML-significant characters")
        svg = inject_style(svg, css)
    svg = normalize_colors(svg)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + svg + "\n"


def export_svg(source: Path, target: Path | None = None) -> Path:
    html = source.read_text(encoding="utf-8")
    target = target or source.with_suffix(".svg")
    target.write_text(standalone_svg(html, name=source.name), encoding="utf-8")
    return target


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    return True


def export_png(source: Path, target: Path | None = None, scale: float = 2.0) -> Path:
    if not playwright_available():
        raise ExportError(PLAYWRIGHT_HINT)
    from playwright.sync_api import sync_playwright

    html = source.read_text(encoding="utf-8")
    if not fonts.is_inlined(html) and fonts.GOOGLE_LINK_RE.search(html):
        # Render a font-embedded twin so the rasteriser needs no network.
        render_source = source.with_name(source.stem + ".offline-render.html")
        render_source.write_text(fonts.inline_html_fonts(html), encoding="utf-8")
        cleanup = True
    else:
        render_source = source
        cleanup = False
    target = target or source.with_suffix(".png")
    url = render_source.resolve().as_uri()
    if "data-motion-mode" in html:
        url += "?motion=static"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(device_scale_factor=scale)
            page.route(re.compile(r"^https?://"), lambda route: route.abort())
            page.goto(url)
            page.evaluate("document.fonts.ready")
            if "data-motion-mode" in html:
                page.wait_for_selector('[data-motion-mode][data-frame="static"]', timeout=5000)
            page.locator("svg").first.screenshot(path=str(target), omit_background=True)
            browser.close()
    finally:
        if cleanup:
            render_source.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="diagram HTML file")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--svg-only", action="store_true")
    group.add_argument("--png-only", action="store_true")
    parser.add_argument("--scale", type=float, default=2.0, help="PNG device scale factor (default 2)")
    parser.add_argument("--output", type=Path, help="output base path; the extension is appended")
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"FAIL no such file: {args.source}")
        return 1
    if not 1 <= args.scale <= 4:
        print("FAIL --scale must be between 1 and 4 (see references/export.md § Sizing)")
        return 1
    base = args.output
    status = 0
    try:
        if not args.png_only:
            print(f"svg: {export_svg(args.source, base.with_suffix('.svg') if base else None)}")
        if not args.svg_only:
            try:
                print(f"png: {export_png(args.source, base.with_suffix('.png') if base else None, args.scale)}")
            except ExportError as exc:
                print(f"png: skipped — {exc}")
                status = 2
    except ExportError as exc:
        print(f"FAIL {exc}")
        return 1
    return status


if __name__ == "__main__":
    sys.exit(main())
