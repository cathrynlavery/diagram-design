#!/usr/bin/env python3
"""Lint diagram examples as *rendered* — catches breakage the source can't show.

``lint-skin.py`` reads the HTML. This one renders it in headless Chromium and
asks the browser what actually got painted, so it catches content cut off by the
SVG viewport, collapsed SVGs, sideways page overflow and runtime errors.

How the clipping check works
---------------------------
Chromium's ``getBoundingClientRect()`` on an SVG child reports *geometry*, not
paint: it excludes stroke width, markers and filter bleed (so a 40px stroke
spilling past the viewport measures as inside), and it ignores ``clip-path``,
``opacity: 0`` ancestors and ``overflow: visible`` (so safe content measures as
outside). Both directions were reproduced in Chromium, so no geometry model is
used here.

Instead the browser is the oracle: screenshot the viewport as authored,
screenshot it again with ``overflow: visible`` on that SVG, and diff the two.
New ink outside the SVG means paint was being cut off — ink is ink, so strokes,
markers and filter bleed all count, while clip-path, invisible and
already-visible content produce no new ink. Verified against all of those cases
in ``--self-test``.

What the diff ignores, and why:

- The SVG's own area, plus that of any ancestor whose ``overflow`` had to be
  released with it. A released ancestor repaints itself — an ``overflow: hidden``
  box with a ``border-radius`` loses its rounded corners — which is not spill.
- A ``EDGE_GUARD``-px band around that area, and anything under
  ``MIN_DIFF_PIXELS`` pixels past ``CHANNEL_THRESHOLD``. Releasing ``overflow``
  re-antialiases boundary pixels by a channel step or two, which is not a
  clipped diagram.

Each SVG is measured twice, at ``DIFF_SCALES``: 1x resolves spill of a few px,
0.25x pulls spill up to four viewports wide back into frame. Known ceilings —
spill of ~2px or less, spill past 0.25x framing, and SVGs inside a *scrolling*
ancestor (reported as ``unmeasurable`` rather than passed silently).

Trust boundary
--------------
This renders contributor HTML in a real browser with JavaScript enabled, so
treat it like opening the file yourself. Network is blocked outright by default
— nothing loads but the local file — which also makes font metrics deterministic
across machines. ``--fonts`` opts into the two Google Fonts hosts (and nothing
else) when you want to measure with the real typefaces.

    python3 scripts/lint-render.py --all
    python3 scripts/lint-render.py skills/diagram-design/assets/example-venn.html
    python3 scripts/lint-render.py --self-test   # proves every check still fires

Requires Playwright (same dev dependency the PNG export uses):

    pip install playwright && playwright install chromium
"""

import argparse
import base64
import os
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

VIEWPORT = {"width": 1600, "height": 1000}
TOLERANCE = 1.0  # px of slop before page overflow counts, absorbs subpixel layout
CHANNEL_THRESHOLD = 16  # per-channel delta that counts as new ink, not antialiasing
MIN_DIFF_PIXELS = 8  # new-ink pixels needed before a clip is reported
# ponytail: 2px guard band around the svg edge absorbs boundary re-antialiasing;
# the cost is that a spill of 2px or less goes unreported.
EDGE_GUARD = 2
# Two passes: 1x sees spills of a few px, 0.25x pulls a spill four viewports wide
# back into frame. ponytail: anything past that stays unseen, and says so in the docstring.
DIFF_SCALES = (1, 0.25)
FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
# Findings in these categories are reported but do not fail the run: they say
# "not checked", which is worth printing and wrong to treat as a defect.
NOTE_CATEGORIES = {"unmeasurable"}

# Per-svg facts that don't need paint: size, and which ancestors would swallow
# the spill the clipping check looks for. An ancestor that clips but isn't
# currently scrolling can be released along with the svg (layout-neutral, since
# no scrollbar comes or goes); one that IS scrolling cannot, and gets a note.
SURVEY_JS = """
() => {
  const label = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = el.getAttribute('class') ? '.' + el.getAttribute('class').split(/\\s+/)[0] : '';
    return el.tagName.toLowerCase() + id + cls;
  };
  return [...document.querySelectorAll('svg')].map((svg, index) => {
    const box = svg.getBoundingClientRect();
    const releasable = [];
    const blocking = [];
    for (let el = svg.parentElement; el; el = el.parentElement) {
      if (getComputedStyle(el).overflow === 'visible') continue;
      const scrolls = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
      const described = `${label(el)} (overflow: ${getComputedStyle(el).overflow})`;
      (scrolls ? blocking : releasable).push(described);
    }
    return {
      index,
      label: label(svg),
      rect: [box.x, box.y, box.width, box.height],
      width: box.width,
      height: box.height,
      alreadyVisible: getComputedStyle(svg).overflow === 'visible',
      releasable,
      blocking,
    };
  });
}
"""

# A paint-only scale on the svg. Transforms don't reflow, so the rest of the page
# stays put and both screenshots of a pass are directly comparable. Shrinking the
# svg pulls spill that would land off-screen back into the viewport.
SET_SCALE_JS = """
([index, scale]) => {
  const svg = document.querySelectorAll('svg')[index];
  svg.style.transformOrigin = 'top left';
  svg.style.transform = scale === 1 ? '' : `scale(${scale})`;
}
"""

# Release the svg's own overflow plus every non-scrolling ancestor that would
# otherwise clip the spill, then put it all back. Returns the released elements'
# boxes: a released ancestor repaints itself too (an `overflow: hidden` box with
# a border-radius loses its rounded corners), so its area can't count as spill.
SET_OVERFLOW_JS = """
([index, release]) => {
  if (!release) {
    for (const el of document.querySelectorAll('[data-lint-released]')) {
      el.style.overflow = '';
      delete el.dataset.lintReleased;
    }
    return [];
  }
  const svg = document.querySelectorAll('svg')[index];
  const targets = [svg];
  for (let el = svg.parentElement; el; el = el.parentElement) {
    if (getComputedStyle(el).overflow !== 'visible') targets.push(el);
  }
  const boxes = [];
  for (const el of targets) {
    const r = el.getBoundingClientRect();
    boxes.push([r.left, r.top, r.right, r.bottom]);
    el.dataset.lintReleased = '1';
    el.style.overflow = 'visible';
  }
  return boxes;
}
"""

# Diff two screenshots of the same region inside the browser: no image library
# on the Python side. Only ink OUTSIDE the svg's own box counts, so antialiasing
# changes within the diagram can't masquerade as clipping.
DIFF_JS = """
async ({a, b, interior, threshold, minPixels, guard}) => {
  const load = async (src) => {
    const bitmap = await createImageBitmap(await (await fetch(src)).blob());
    const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    canvas.getContext('2d').drawImage(bitmap, 0, 0);
    return canvas.getContext('2d').getImageData(0, 0, bitmap.width, bitmap.height);
  };
  const [before, after] = await Promise.all([load(a), load(b)]);
  if (before.width !== after.width || before.height !== after.height) {
    return {count: 0, resized: true, sides: {}};
  }
  const sides = {left: 0, top: 0, right: 0, bottom: 0};
  let count = 0;
  // Guard band: the svg's own edge pixels straddle the boundary at fractional
  // positions, so releasing overflow re-antialiases them. Ink that far out is
  // the diagram's own border, not content spilling past it.
  const g = guard;
  for (let y = 0; y < before.height; y++) {
    for (let x = 0; x < before.width; x++) {
      if (x >= interior.left - g && x < interior.right + g &&
          y >= interior.top - g && y < interior.bottom + g) continue;
      const i = (y * before.width + x) * 4;
      const delta = Math.max(
        Math.abs(before.data[i] - after.data[i]),
        Math.abs(before.data[i + 1] - after.data[i + 1]),
        Math.abs(before.data[i + 2] - after.data[i + 2]),
        Math.abs(before.data[i + 3] - after.data[i + 3]),
      );
      if (delta <= threshold) continue;
      count++;
      if (x < interior.left) sides.left = Math.max(sides.left, interior.left - x);
      if (x >= interior.right) sides.right = Math.max(sides.right, x - interior.right + 1);
      if (y < interior.top) sides.top = Math.max(sides.top, interior.top - y);
      if (y >= interior.bottom) sides.bottom = Math.max(sides.bottom, y - interior.bottom + 1);
    }
  }
  return {count, resized: false, sides, reported: count >= minPixels};
}
"""

PAGE_OVERFLOW_JS = """
() => {
  const doc = document.documentElement;
  return [doc.scrollWidth - doc.clientWidth, doc.clientWidth];
}
"""

# Each case is (name, svg markup, should_be_flagged). The false-flag half matters
# as much as the true-flag half: a linter that cries wolf gets switched off.
SELF_TEST_CASES = [
    ("plain-overflow", '<rect x="150" y="60" width="400" height="10" fill="#000"/>', True),
    (
        "thick-stroke-spill",
        '<rect x="150" y="20" width="45" height="40" fill="none" stroke="#000" stroke-width="40"/>',
        True,
    ),
    (
        "marker-spill",
        '<defs><marker id="a" markerWidth="30" markerHeight="30" refX="0" refY="5" overflow="visible">'
        '<path d="M0,0 L30,5 L0,10 Z" fill="#000"/></marker></defs>'
        '<line x1="100" y1="50" x2="199" y2="50" stroke="#000" marker-end="url(#a)"/>',
        True,
    ),
    (
        "filter-bleed",
        '<filter id="b" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="20"/></filter>'
        '<rect x="165" y="10" width="30" height="20" fill="#000" filter="url(#b)"/>',
        True,
    ),
    (
        "clip-path-keeps-it-safe",
        '<clipPath id="c"><rect x="0" y="0" width="200" height="100"/></clipPath>'
        '<rect x="150" y="10" width="400" height="30" fill="#000" clip-path="url(#c)"/>',
        False,
    ),
    (
        "opacity-0-ancestor",
        '<g opacity="0"><rect x="150" y="10" width="400" height="10" fill="#000"/></g>',
        False,
    ),
    (
        "display-none-ancestor",
        '<g style="display:none"><rect x="150" y="10" width="400" height="10" fill="#000"/></g>',
        False,
    ),
    ("all-inside", '<rect x="10" y="10" width="100" height="40" fill="#000"/>', False),
]

SELF_TEST_PAGE = """
<!DOCTYPE html><html><body style="margin:40px">
<svg width="200" height="100" viewBox="0 0 200 100" style="display:block;%(svg_style)s">%(markup)s</svg>
</body></html>
"""


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="HTML files to render")
    parser.add_argument("--all", action="store_true", help="render every example")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument(
        "--fonts",
        action="store_true",
        help="allow the Google Fonts hosts so text is measured with the real typefaces",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        dest="self_test",
        help="check the checks against known-broken and known-safe diagrams",
    )
    return parser.parse_args()


def display_path(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def launch(playwright):
    """Bundled Chromium, or the channel named by DIAGRAM_LINT_BROWSER_CHANNEL.

    No silent fallback: in CI a missing bundled Chromium is a broken environment,
    and quietly using whatever browser is lying around hides that.
    """
    channel = os.environ.get("DIAGRAM_LINT_BROWSER_CHANNEL")
    if channel:
        print(f"Using browser channel {channel!r} (DIAGRAM_LINT_BROWSER_CHANNEL).", file=sys.stderr)
        return playwright.chromium.launch(channel=channel)
    return playwright.chromium.launch()


def block_network(context, allow_fonts):
    """Local files only. With --fonts, the two font hosts as well — nothing else."""

    def handler(route):
        url = route.request.url
        if url.startswith("file://") or url.startswith("data:") or url.startswith("blob:"):
            route.continue_()
        elif allow_fonts and any(host in url for host in FONT_HOSTS):
            route.continue_()
        else:
            route.abort()

    context.route("**/*", handler)


def watch(page, findings):
    """Runtime failures. Local assets are reported precisely, via requestfailed."""
    page.on("pageerror", lambda error: findings.append(("page-error", str(error))))
    page.on(
        "console",
        lambda message: message.type == "error"
        # Resource failures arrive on requestfailed with a URL, which is where they
        # get judged. This drops the duplicate, not the signal.
        and not message.text.startswith("Failed to load resource")
        and findings.append(("console-error", message.text)),
    )

    def on_request_failed(request):
        if request.url.startswith("file://"):
            findings.append(("missing-asset", f"{request.url} failed to load"))
        # Remote requests are blocked by policy (see block_network) or offline;
        # either way that is this linter's doing, not the diagram's.

    page.on("requestfailed", on_request_failed)


def shoot(page):
    """The viewport, not the page: fixed dimensions, so releasing overflow can't
    resize the image, and the whole visible area is available to spill into."""
    return page.screenshot(animations="disabled")


def data_url(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def clipping_findings(page, survey):
    """One paint comparison per svg: as authored vs. with its overflow released."""
    findings = []
    handles = page.locator("svg")
    for entry in survey:
        if not entry["width"] or not entry["height"]:
            findings.append(
                ("svg-collapsed", f"{entry['label']} renders {entry['width']}x{entry['height']}")
            )
            continue
        if entry["alreadyVisible"]:
            # Nothing is being cut off, so there is nothing to compare.
            continue
        if entry["blocking"]:
            # Say so rather than report a clean bill: a scrolling ancestor eats the
            # spill, and releasing it would move scrollbars and change the pixels.
            findings.append(
                (
                    "unmeasurable",
                    f"{entry['label']} sits inside scrolling {entry['blocking'][0]}; "
                    "clipping cannot be measured through it",
                )
            )
            continue
        handle = handles.nth(entry["index"])
        handle.scroll_into_view_if_needed()
        if handle.bounding_box() is None:
            continue

        worst = None
        for scale in DIFF_SCALES:
            page.evaluate(SET_SCALE_JS, [entry["index"], scale])
            box = handle.bounding_box()
            origin = page.evaluate("() => [window.scrollX, window.scrollY]")
            as_authored = shoot(page)
            released_boxes = page.evaluate(SET_OVERFLOW_JS, [entry["index"], True])
            released = shoot(page)
            page.evaluate(SET_OVERFLOW_JS, [entry["index"], False])
            page.evaluate(SET_SCALE_JS, [entry["index"], 1])
            if box is None:
                continue

            # Viewport-space area that is allowed to repaint: the svg itself plus
            # any ancestor whose overflow was released. Ink outside all of it is
            # content that was being cut off.
            interior = {
                "left": round(box["x"] - origin[0]),
                "top": round(box["y"] - origin[1]),
                "right": round(box["x"] - origin[0] + box["width"]),
                "bottom": round(box["y"] - origin[1] + box["height"]),
            }
            for left, top, right, bottom in released_boxes:
                interior["left"] = min(interior["left"], round(left))
                interior["top"] = min(interior["top"], round(top))
                interior["right"] = max(interior["right"], round(right))
                interior["bottom"] = max(interior["bottom"], round(bottom))
            diff = page.evaluate(
                DIFF_JS,
                {
                    "a": data_url(as_authored),
                    "b": data_url(released),
                    "interior": interior,
                    "threshold": CHANNEL_THRESHOLD,
                    "minPixels": MIN_DIFF_PIXELS,
                    "guard": EDGE_GUARD,
                },
            )
            if diff.get("resized"):
                findings.append(
                    ("unmeasurable", f"{entry['label']} changed size when overflow was released")
                )
                worst = None
                break
            if diff.get("reported") and (worst is None or diff["count"] > worst[0]["count"]):
                worst = (diff, scale)

        if worst:
            diff, scale = worst
            spills = ", ".join(
                f"{side} by {int(distance / scale)}px"
                for side, distance in sorted(diff["sides"].items())
                if distance
            )
            findings.append(
                (
                    "clipped",
                    f"{entry['label']} paints outside its viewport: {spills} "
                    f"({diff['count']} px of ink cut off at {scale:g}x)",
                )
            )
    return findings


def measure(page):
    findings = []
    # Playwright awaits a returned promise; no timeout kwarg exists on evaluate.
    page.evaluate("() => document.fonts.ready")
    survey = page.evaluate(SURVEY_JS)
    findings.extend(clipping_findings(page, survey))
    spill, client_width = page.evaluate(PAGE_OVERFLOW_JS)
    if spill > TOLERANCE:
        findings.append(
            ("page-overflow", f"page scrolls {spill:.0f}px horizontally at {client_width}px wide")
        )
    return findings


def check(page, path):
    findings = []
    watch(page, findings)
    page.goto(path.resolve().as_uri(), wait_until="load")
    return measure(page) + findings


def self_test(context):
    page = context.new_page()
    failures = []
    for name, markup, expected in SELF_TEST_CASES:
        page.set_content(SELF_TEST_PAGE % {"markup": markup, "svg_style": ""})
        flagged = any(category == "clipped" for category, _ in measure(page))
        if flagged != expected:
            failures.append(f"{name}: flagged={flagged}, expected={expected}")

    # An svg the author explicitly set to overflow:visible is not being cut off.
    page.set_content(
        SELF_TEST_PAGE % {"markup": SELF_TEST_CASES[0][1], "svg_style": "overflow:visible"}
    )
    if any(category == "clipped" for category, _ in measure(page)):
        failures.append("overflow-visible-svg: flagged=True, expected=False")

    # A *scrolling* ancestor must be reported as unmeasurable, not as clean: its
    # scrollbars would move if released, so the paint comparison can't run.
    page.set_content(
        '<!DOCTYPE html><html><body style="margin:40px"><div style="overflow:auto;width:120px">'
        '<svg width="200" height="100" viewBox="0 0 200 100" style="display:block">'
        '<rect x="150" y="60" width="400" height="10" fill="#000"/></svg></div></body></html>'
    )
    if not any(category == "unmeasurable" for category, _ in measure(page)):
        failures.append("scrolling-ancestor: no unmeasurable finding")

    # An `overflow: hidden` ancestor with rounded corners loses them when released,
    # which repaints its own corner pixels. That is not the diagram spilling.
    page.set_content(
        '<!DOCTYPE html><html><body style="margin:40px">'
        '<div style="overflow:hidden;border-radius:12px;padding:40px;background:#222;width:280px">'
        '<svg width="200" height="100" viewBox="0 0 200 100" style="display:block;background:#eee">'
        '<rect x="10" y="10" width="100" height="40" fill="#000"/></svg></div></body></html>'
    )
    if any(category == "clipped" for category, _ in measure(page)):
        failures.append("rounded-ancestor: false clipped finding")

    # A non-scrolling clipping ancestor is released along with the svg, so the
    # spill behind it still gets caught rather than silently skipped.
    page.set_content(
        '<!DOCTYPE html><html><body style="margin:40px"><div style="overflow:hidden;width:200px;height:100px">'
        '<svg width="200" height="100" viewBox="0 0 200 100" style="display:block">'
        '<rect x="150" y="60" width="400" height="10" fill="#000"/></svg></div></body></html>'
    )
    if not any(category == "clipped" for category, _ in measure(page)):
        failures.append("non-scrolling-ancestor: spill not caught through it")

    # Collapsed svg, and a page that scrolls sideways.
    page.set_content(
        '<!DOCTYPE html><html><body style="margin:0"><div style="width:3000px">wide</div>'
        '<svg width="0" height="0" viewBox="0 0 200 100"><rect width="10" height="10"/></svg></body></html>'
    )
    categories = {category for category, _ in measure(page)}
    for expected_category in ("svg-collapsed", "page-overflow"):
        if expected_category not in categories:
            failures.append(f"{expected_category}: check did not fire")

    page.close()

    # A missing local asset must surface, not be swallowed with the remote noise.
    # Needs a real file:// document, so relative URLs resolve to local paths.
    asset_page = context.new_page()
    asset_findings = []
    watch(asset_page, asset_findings)
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory) / "missing-asset.html"
        fixture.write_text('<img src="does-not-exist-12345.png">', encoding="utf-8")
        asset_page.goto(fixture.as_uri(), wait_until="load")
        asset_page.wait_for_timeout(300)
    asset_page.close()
    if not any(category == "missing-asset" for category, _ in asset_findings):
        failures.append("missing-asset: check did not fire")
    if failures:
        print("self-test FAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"self-test OK: {len(SELF_TEST_CASES) + 7} cases, no false flags.")
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
    total_notes = 0
    with sync_playwright() as playwright:
        try:
            browser = launch(playwright)
        except Exception as error:
            print(
                f"Could not launch a browser: {error}\n"
                "  playwright install chromium\n"
                "  (or set DIAGRAM_LINT_BROWSER_CHANNEL=chrome to use a system Chrome)",
                file=sys.stderr,
            )
            return 2
        context = browser.new_context(viewport=VIEWPORT)
        block_network(context, args.fonts)
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

            findings.sort()
            total_findings += sum(1 for category, _ in findings if category not in NOTE_CATEGORIES)
            total_notes += sum(1 for category, _ in findings if category in NOTE_CATEGORIES)
            if not args.quiet:
                shown_path = display_path(path)
                for category, message in findings:
                    print(f"{shown_path}: {category}: {message}")
        browser.close()

    print(
        f"Summary: {len(paths)} file(s) rendered, {total_findings} finding(s), "
        f"{total_notes} note(s) (not checked, not failed)."
    )
    return 1 if total_findings else 0


if __name__ == "__main__":
    sys.exit(main())
