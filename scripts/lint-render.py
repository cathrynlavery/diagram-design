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
screenshot it again with ``overflow`` released, and diff the two. New ink means
paint was being cut off — ink is ink, so strokes, markers and filter bleed all
count, while clip-path, invisible and already-visible content produce no new ink.

Releases are **staged**, because a diagram can be clipped at more than one level
and each release repaints its own box:

- stage 0 releases the SVG alone, and looks for ink outside the SVG's box;
- stage *k* also releases the *k* nearest clipping ancestors, and looks for ink
  outside the outermost released box.

Without staging, releasing an ancestor masks spill just outside the SVG (its box
becomes part of the ignored area), and an SVG authored ``overflow: visible``
inside a clipping wrapper looks clean while the wrapper cuts it off.

What the diff ignores, and why:

- The outermost released box for that stage. A released element repaints itself —
  an ``overflow: hidden`` box with a ``border-radius`` loses its rounded corners —
  which is not spill.
- An ``EDGE_GUARD``-px band around it, and anything under ``MIN_DIFF_PIXELS``
  pixels past ``CHANNEL_THRESHOLD``. Releasing ``overflow`` re-antialiases
  boundary pixels by a channel step or two, which is not a clipped diagram.

Every stage runs at each of ``DIFF_SCALES``: 1x resolves spill of a few px, 0.25x
pulls spill up to four viewports wide back into frame. All geometry stays in one
coordinate system — viewport pixels, straight from ``getBoundingClientRect()``,
matching ``page.screenshot()`` — so an SVG below the fold measures the same as
one above it.

Known ceilings: spill of ~2px or less, spill past 0.25x framing, and SVGs inside
a *scrolling* ancestor, which report ``unmeasurable`` rather than passing quietly.

Every property this script mutates is snapshotted and restored verbatim in a
``finally``, and ``--self-test`` asserts the DOM is byte-identical afterwards.

Trust boundary
--------------
This renders contributor HTML in a real browser with JavaScript enabled, so treat
it like opening the file yourself. Network is cut at the resolver
(``--host-resolver-rules``), which also stops WebSockets and anything else that
does not go through Playwright's request routing, with request routing as a second
layer. ``--fonts`` excludes exactly the two Google Fonts hostnames from the
resolver block and allows them only over HTTPS on an exact hostname match.
``--self-test`` proves the isolation against a local listener.

Because the oracle is pixels, CI must pin Playwright and its bundled Chromium
rather than taking whatever is newest; see ``.github/workflows/ci.yml``.

    python3 scripts/lint-render.py --all
    python3 scripts/lint-render.py skills/diagram-design/assets/example-venn.html
    python3 scripts/lint-render.py --self-test   # proves every check still fires

Requires Playwright (same dev dependency the PNG export uses):

    pip install playwright && playwright install chromium
"""

import argparse
import base64
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

VIEWPORT = {"width": 1600, "height": 1000}
TOLERANCE = 1.0  # px of slop before page overflow counts, absorbs subpixel layout
CHANNEL_THRESHOLD = 16  # per-channel delta that counts as new ink, not antialiasing
MIN_DIFF_PIXELS = 8  # new-ink pixels needed before a clip is reported
# ponytail: 2px guard band around a released box absorbs boundary re-antialiasing;
# the cost is that a spill of 2px or less goes unreported.
EDGE_GUARD = 2
# Two passes: 1x sees spills of a few px, 0.25x pulls a spill four viewports wide
# back into frame. ponytail: anything past that stays unseen, and says so above.
DIFF_SCALES = (1, 0.25)
# Deepest ancestor chain to stage. Diagram wrappers are shallow; this only bounds
# pathological nesting. ponytail: raise it if a real example needs more.
MAX_ANCESTOR_STAGES = 4

FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
# Kill name resolution outright. Unlike request routing this also covers
# WebSockets, EventSource and anything else that opens its own connection.
RESOLVER_RULE = "MAP * ~NOTFOUND"

# Findings in these categories are reported but do not fail the run: they say
# "not checked", which is worth printing and wrong to treat as a defect.
NOTE_CATEGORIES = {"unmeasurable"}

# Per-svg facts that don't need paint: its box, whether the author already set
# overflow visible, and the chain of ancestors that clip it. A clipping ancestor
# that is currently scrolling cannot be released (its scrollbars would move and
# change the pixels), so the chain stops there and the rest is reported unchecked.
SURVEY_JS = """
() => {
  const label = (el) => {
    const id = el.id ? '#' + el.id : '';
    const cls = el.getAttribute('class') ? '.' + el.getAttribute('class').split(/\\s+/)[0] : '';
    return el.tagName.toLowerCase() + id + cls;
  };
  return [...document.querySelectorAll('svg')].map((svg, index) => {
    const box = svg.getBoundingClientRect();
    const chain = [];
    let blockedBy = null;
    for (let el = svg.parentElement; el; el = el.parentElement) {
      const overflow = getComputedStyle(el).overflow;
      if (overflow === 'visible') continue;
      const scrolls = el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1;
      if (scrolls) { blockedBy = `${label(el)} (overflow: ${overflow})`; break; }
      chain.push(`${label(el)} (overflow: ${overflow})`);
    }
    return {
      index,
      label: label(svg),
      width: box.width,
      height: box.height,
      ownOverflowVisible: getComputedStyle(svg).overflow === 'visible',
      chain,
      blockedBy,
    };
  });
}
"""

# Mutations record the exact `style` attribute they replace, so RESTORE_JS can put
# it back verbatim — including an authored inline transform, which an earlier
# version clobbered by resetting the property to ''.
REMEMBER_JS = """
  window.__lintSnapshots = window.__lintSnapshots || [];
  const remember = (el) => window.__lintSnapshots.push([el, el.getAttribute('style')]);
"""

RESTORE_JS = """
() => {
  const snapshots = window.__lintSnapshots || [];
  // Reverse order, so an element mutated twice ends on its earliest snapshot.
  for (const [el, style] of snapshots.slice().reverse()) {
    if (style === null) el.removeAttribute('style');
    else el.setAttribute('style', style);
  }
  delete window.__lintSnapshots;
}
"""

# A paint-only scale on the svg. Transforms don't reflow, so the rest of the page
# stays put and both screenshots of a pass are directly comparable. Shrinking the
# svg pulls spill that would land off-screen back into the viewport.
SET_SCALE_JS = (
    """
([index, scale]) => {
"""
    + REMEMBER_JS
    + """
  const svg = document.querySelectorAll('svg')[index];
  remember(svg);
  svg.style.setProperty('transform-origin', 'top left', 'important');
  svg.style.setProperty('transform', `scale(${scale})`, 'important');
}
"""
)

# Release overflow on the svg plus the `depth` nearest clipping ancestors, and
# return every released box in viewport coordinates, innermost first. `important`
# so a class rule can't win; the exact prior style attribute is snapshotted.
RELEASE_JS = (
    """
([index, depth]) => {
"""
    + REMEMBER_JS
    + """
  const svg = document.querySelectorAll('svg')[index];
  const targets = [svg];
  let taken = 0;
  for (let el = svg.parentElement; el && taken < depth; el = el.parentElement) {
    if (getComputedStyle(el).overflow === 'visible') continue;
    targets.push(el);
    taken++;
  }
  const rects = [];
  for (const el of targets) {
    remember(el);
    const r = el.getBoundingClientRect();
    rects.push([r.left, r.top, r.right, r.bottom]);
    el.style.setProperty('overflow', 'visible', 'important');
  }
  return rects;
}
"""
)

DOM_STATE_JS = "() => document.documentElement.outerHTML"

PAGE_OVERFLOW_JS = """
() => {
  const doc = document.documentElement;
  return [doc.scrollWidth - doc.clientWidth, doc.clientWidth];
}
"""

# Diff two screenshots of the same viewport inside the browser: no image library
# on the Python side. Only ink OUTSIDE the released box counts, so an element
# repainting its own area can't masquerade as clipping.
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


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="HTML files to render")
    parser.add_argument("--all", action="store_true", help="render every example")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument(
        "--fonts",
        action="store_true",
        help="allow exactly the Google Fonts hosts, over HTTPS, so text is measured "
        "with the real typefaces",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        dest="self_test",
        help="check the checks: detection, false flags, network isolation, DOM restore",
    )
    return parser.parse_args()


def shipped_assets():
    """Every asset that ships and renders: examples *and* the templates they are
    scaffolded from. A broken template ships broken diagrams, so leaving templates
    out of --all was a hole (thanks @greptile). index.html and icons.html are
    galleries of the others, so they add no coverage.
    """
    patterns = ("example-*.html", "template*.html")
    return sorted({path for pattern in patterns for path in ASSET_DIR.glob(pattern)})


def display_path(path):
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def resolver_rule(allow_fonts):
    """Block every hostname, minus the font hosts when they are opted in."""
    if not allow_fonts:
        return RESOLVER_RULE
    return ",".join([RESOLVER_RULE] + [f"EXCLUDE {host}" for host in FONT_HOSTS])


def launch(playwright, allow_fonts):
    """Bundled Chromium, or the channel named by DIAGRAM_LINT_BROWSER_CHANNEL.

    No silent fallback: in CI a missing bundled Chromium is a broken environment,
    and quietly using whatever browser is lying around hides that.
    """
    args = [f"--host-resolver-rules={resolver_rule(allow_fonts)}"]
    channel = os.environ.get("DIAGRAM_LINT_BROWSER_CHANNEL")
    if channel:
        print(f"Using browser channel {channel!r} (DIAGRAM_LINT_BROWSER_CHANNEL).", file=sys.stderr)
        return playwright.chromium.launch(channel=channel, args=args)
    return playwright.chromium.launch(args=args)


def block_network(context, allow_fonts):
    """Second layer behind the resolver block: local documents only.

    The font exception requires HTTPS and an exact hostname, so a URL merely
    containing "fonts.googleapis.com" (a path, a query, a lookalike host) is not
    enough to get through.
    """

    def handler(route):
        url = route.request.url
        if url.startswith(("file://", "data:", "blob:")):
            route.continue_()
            return
        parsed = urlparse(url)
        if allow_fonts and parsed.scheme == "https" and parsed.hostname in FONT_HOSTS:
            route.continue_()
            return
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
        # Remote requests are blocked by policy (resolver + routing); that is this
        # linter's doing, not the diagram's.

    page.on("requestfailed", on_request_failed)


def shoot(page):
    """The viewport, not the page: fixed dimensions, so releasing overflow can't
    resize the image, and the whole visible area is available to spill into.
    Viewport pixels are also the coordinate system every rect here uses."""
    return page.screenshot(animations="disabled")


def data_url(png_bytes):
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def compare_release(page, index, depth, scale):
    """One authored-vs-released paint comparison. Returns (diff, released_label_depth).

    Restores every mutated property before returning, whatever happens.
    """
    try:
        if scale != 1:
            page.evaluate(SET_SCALE_JS, [index, scale])
        as_authored = shoot(page)
        rects = page.evaluate(RELEASE_JS, [index, depth])
        released = shoot(page)
    finally:
        page.evaluate(RESTORE_JS)

    if not rects:
        return None
    # Outermost released box: the only area whose own repaint is expected.
    left, top, right, bottom = rects[-1]
    interior = {
        "left": round(left),
        "top": round(top),
        "right": round(right),
        "bottom": round(bottom),
    }
    return page.evaluate(
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


def clipping_findings(page, survey):
    """Staged paint comparisons per svg: the svg alone, then each clipping ancestor."""
    findings = []
    handles = page.locator("svg")
    for entry in survey:
        if not entry["width"] or not entry["height"]:
            findings.append(
                ("svg-collapsed", f"{entry['label']} renders {entry['width']}x{entry['height']}")
            )
            continue
        if entry["blockedBy"]:
            findings.append(
                (
                    "unmeasurable",
                    f"{entry['label']} sits inside scrolling {entry['blockedBy']}; "
                    "clipping cannot be measured through it",
                )
            )
        chain = entry["chain"][:MAX_ANCESTOR_STAGES]
        # Stage 0 is the svg's own overflow — skipped only when the author already
        # set it visible. Ancestor stages run regardless, since a wrapper can clip
        # an svg that does not clip itself.
        stages = [] if entry["ownOverflowVisible"] else [0]
        stages += list(range(1, len(chain) + 1))
        if not stages:
            continue

        handles.nth(entry["index"]).scroll_into_view_if_needed()
        for depth in stages:
            where = entry["label"] if depth == 0 else f"{entry['label']} inside {chain[depth - 1]}"
            worst = None
            unmeasurable = False
            for scale in DIFF_SCALES:
                diff = compare_release(page, entry["index"], depth, scale)
                if diff is None:
                    continue
                if diff.get("resized"):
                    findings.append(
                        ("unmeasurable", f"{where} changed size when overflow was released")
                    )
                    unmeasurable = True
                    break
                if diff.get("reported") and (worst is None or diff["count"] > worst[0]["count"]):
                    worst = (diff, scale)
            if unmeasurable or not worst:
                continue
            diff, scale = worst
            spills = ", ".join(
                f"{side} by {int(distance / scale)}px"
                for side, distance in sorted(diff["sides"].items())
                if distance
            )
            findings.append(
                (
                    "clipped",
                    f"{where} paints outside its box: {spills} "
                    f"({diff['count']} px of ink cut off at {scale:g}x)",
                )
            )
            # One report per svg is enough; deeper stages describe the same spill.
            break
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


# --- self-test ---------------------------------------------------------------

SVG_CASES = [
    # (name, svg markup, svg inline style, wrapper html or None, should_be_flagged)
    ("plain-overflow", '<rect x="150" y="60" width="400" height="10" fill="#000"/>', "", None, True),
    (
        "thick-stroke-spill",
        '<rect x="150" y="20" width="45" height="40" fill="none" stroke="#000" stroke-width="40"/>',
        "",
        None,
        True,
    ),
    (
        "marker-spill",
        '<defs><marker id="a" markerWidth="30" markerHeight="30" refX="0" refY="5" overflow="visible">'
        '<path d="M0,0 L30,5 L0,10 Z" fill="#000"/></marker></defs>'
        '<line x1="100" y1="50" x2="199" y2="50" stroke="#000" marker-end="url(#a)"/>',
        "",
        None,
        True,
    ),
    (
        "filter-bleed",
        '<filter id="b" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="20"/></filter>'
        '<rect x="165" y="10" width="30" height="20" fill="#000" filter="url(#b)"/>',
        "",
        None,
        True,
    ),
    (
        "clip-path-keeps-it-safe",
        '<clipPath id="c"><rect x="0" y="0" width="200" height="100"/></clipPath>'
        '<rect x="150" y="10" width="400" height="30" fill="#000" clip-path="url(#c)"/>',
        "",
        None,
        False,
    ),
    (
        "opacity-0-ancestor",
        '<g opacity="0"><rect x="150" y="10" width="400" height="10" fill="#000"/></g>',
        "",
        None,
        False,
    ),
    (
        "display-none-ancestor",
        '<g style="display:none"><rect x="150" y="10" width="400" height="10" fill="#000"/></g>',
        "",
        None,
        False,
    ),
    ("all-inside", '<rect x="10" y="10" width="100" height="40" fill="#000"/>', "", None, False),
    # The author set overflow visible: the svg itself clips nothing.
    (
        "overflow-visible-svg",
        '<rect x="150" y="60" width="400" height="10" fill="#000"/>',
        "overflow:visible",
        None,
        False,
    ),
    # ... but a wrapper still clips it, and staging must catch that.
    (
        "overflow-visible-svg-in-clipping-wrapper",
        '<rect x="150" y="60" width="400" height="10" fill="#000"/>',
        "overflow:visible",
        '<div style="overflow:hidden;width:200px;height:100px">',
        True,
    ),
    # Wrapper clipping declared inline, and via a class — both must be released.
    (
        "inline-wrapper",
        '<rect x="150" y="60" width="400" height="10" fill="#000"/>',
        "",
        '<div style="overflow:hidden;width:200px;height:100px">',
        True,
    ),
    (
        "class-wrapper",
        '<rect x="150" y="60" width="400" height="10" fill="#000"/>',
        "",
        '<style>.wrap{overflow:hidden;width:200px;height:100px}</style><div class="wrap">',
        True,
    ),
    # A rounded clipping wrapper repaints its corners when released; not spill.
    (
        "rounded-wrapper",
        '<rect x="10" y="10" width="100" height="40" fill="#000"/>',
        "background:#eee",
        '<div style="overflow:hidden;border-radius:12px;padding:40px;background:#222;width:280px">',
        False,
    ),
    # An authored inline transform must survive the scale pass untouched.
    (
        "authored-transform",
        '<rect x="150" y="60" width="400" height="10" fill="#000"/>',
        "transform:rotate(2deg)",
        None,
        True,
    ),
]

FIXTURE_PAGE = """
<!DOCTYPE html><html><body style="margin:40px">%(filler)s%(open)s
<svg width="200" height="100" viewBox="0 0 200 100" style="display:block;%(svg_style)s">%(markup)s</svg>
%(close)s</body></html>
"""

# Enough filler to push the svg below a 1000px-tall viewport, so the paired
# above/below-fold cases exercise scrolled measurement.
BELOW_FOLD_FILLER = '<div style="height:1800px;background:#eee"></div>'


def fixture_html(markup, svg_style="", wrapper=None, filler=""):
    return FIXTURE_PAGE % {
        "filler": filler,
        "open": wrapper or "",
        "close": "</div>" if wrapper else "",
        "svg_style": svg_style,
        "markup": markup,
    }


def network_isolation_failures(context):
    """Point a page at a local listener four different ways; nothing may connect.

    Request routing alone does not stop a WebSocket — verified — which is why the
    resolver block exists. This asserts the boundary rather than documenting it.
    """
    connections = []
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(8)

    def accept_loop():
        while True:
            try:
                connection, address = server.accept()
            except OSError:
                return
            connections.append(address)
            connection.close()

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()

    page = context.new_page()
    try:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "isolation.html"
            fixture.write_text(
                "<!DOCTYPE html><html><body><script>\n"
                f"  const target = '127.0.0.1:{port}';\n"
                "  try { new WebSocket('ws://' + target + '/ws'); } catch (e) {}\n"
                "  try { fetch('http://' + target + '/fetch').catch(() => {}); } catch (e) {}\n"
                "  try { new EventSource('http://' + target + '/sse'); } catch (e) {}\n"
                "  const img = new Image(); img.src = 'http://' + target + '/img.png';\n"
                "</script></body></html>",
                encoding="utf-8",
            )
            page.goto(fixture.as_uri(), wait_until="load")
            page.wait_for_timeout(1200)
    finally:
        page.close()
        server.close()

    if connections:
        return [f"network-isolation: {len(connections)} connection(s) reached a local listener"]
    return []


def gallery_mobile_failures(context, gallery_path=None):
    """Keep the wrapped gallery controls from collapsing its mobile preview."""
    gallery_path = gallery_path or ASSET_DIR / "index.html"
    failures = []
    page = context.new_page()
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        page.goto(gallery_path.as_uri(), wait_until="load")
        page.locator('[data-type="polar"]').click()
        routed_source = page.locator("#preview").get_attribute("src")
        if routed_source != "example-polar.html":
            failures.append(
                "gallery-mobile-routing: Polar routed to "
                f"{routed_source!r}, expected 'example-polar.html'"
            )
        facts = page.evaluate(
            """
            () => {
              const doc = document.documentElement;
              const preview = document.querySelector('#preview');
              const rect = preview.getBoundingClientRect();
              return {
                previewHeight: rect.height,
                pageOverflow: doc.scrollWidth - doc.clientWidth,
              };
            }
            """
        )
        if facts["previewHeight"] < 400:
            failures.append(
                "gallery-mobile-preview: iframe height "
                f"{facts['previewHeight']:.1f}px is below the 400px minimum"
            )
        if facts["pageOverflow"] > TOLERANCE:
            failures.append(
                "gallery-mobile-overflow: page extends "
                f"{facts['pageOverflow']:.1f}px past the mobile viewport"
            )
    finally:
        page.close()
    return failures


def self_test(context):
    page = context.new_page()
    failures = []
    checks = 0

    def flagged(html):
        page.set_content(html)
        return any(category == "clipped" for category, _ in measure(page))

    for name, markup, svg_style, wrapper, expected in SVG_CASES:
        checks += 1
        if flagged(fixture_html(markup, svg_style, wrapper)) != expected:
            failures.append(f"{name}: flagged={not expected}, expected={expected}")

    # Paired above/below-fold: identical spill, so a scrolled measurement that
    # mixed document and viewport coordinates would disagree with its twin.
    for label, filler in (("above-fold", ""), ("below-fold", BELOW_FOLD_FILLER)):
        checks += 1
        if not flagged(fixture_html(SVG_CASES[0][1], filler=filler)):
            failures.append(f"{label}-spill: not caught")
    checks += 1
    if flagged(fixture_html(SVG_CASES[7][1], filler=BELOW_FOLD_FILLER)):
        failures.append("below-fold-clean: false clipped finding")

    # The DOM must come back exactly as authored, including inline transforms.
    checks += 1
    page.set_content(fixture_html(SVG_CASES[0][1], svg_style="transform:rotate(2deg)"))
    before = page.evaluate(DOM_STATE_JS)
    measure(page)
    if page.evaluate(DOM_STATE_JS) != before:
        failures.append("dom-restore: markup changed after measuring")

    # A *scrolling* ancestor must be reported unmeasurable, not clean.
    checks += 1
    page.set_content(
        fixture_html(SVG_CASES[0][1], wrapper='<div style="overflow:auto;width:120px">')
    )
    if not any(category == "unmeasurable" for category, _ in measure(page)):
        failures.append("scrolling-ancestor: no unmeasurable finding")

    # Collapsed svg, and a page that scrolls sideways.
    checks += 2
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
    checks += 1
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

    checks += 1
    failures += network_isolation_failures(context)

    checks += 1
    failures += gallery_mobile_failures(context)

    # A broken route should be a targeted failure, not a delayed Playwright
    # timeout or traceback that escapes the self-test report.
    checks += 1
    with tempfile.TemporaryDirectory() as directory:
        broken_gallery = Path(directory) / "index.html"
        gallery_source = (ASSET_DIR / "index.html").read_text(encoding="utf-8")
        route_line = "const src = `example-${state.type}${state.variant}.html`;"
        if gallery_source.count(route_line) != 1:
            failures.append("gallery-mobile-routing-fixture: route source changed unexpectedly")
        else:
            broken_gallery.write_text(
                gallery_source.replace(route_line, 'const src = "wrong-example.html";'),
                encoding="utf-8",
            )
            route_failures = gallery_mobile_failures(context, broken_gallery)
            if not any(
                failure.startswith("gallery-mobile-routing:") for failure in route_failures
            ):
                failures.append("gallery-mobile-routing: broken route was not reported")

    if failures:
        print("self-test FAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"self-test OK: {checks} cases, no false flags.")
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

    paths = shipped_assets() if args.all else args.files
    if not paths and not args.self_test:
        print("Nothing to check. Pass files, --all or --self-test.", file=sys.stderr)
        return 2

    total_findings = 0
    total_notes = 0
    with sync_playwright() as playwright:
        try:
            browser = launch(playwright, args.fonts)
        except Exception as error:
            print(
                f"Could not launch a browser: {error}\n"
                "  playwright install chromium\n"
                "  (or set DIAGRAM_LINT_BROWSER_CHANNEL=chrome to use a system Chrome)",
                file=sys.stderr,
            )
            return 2
        # The oracle is pixels, so record which browser produced them.
        print(f"Chromium {browser.version}, network: {resolver_rule(args.fonts)}", file=sys.stderr)
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
