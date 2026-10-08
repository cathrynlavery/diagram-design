# Export to PNG / SVG

Convert a generated diagram HTML file into a portable `.svg` and/or `.png` next to it. **Manual only — never run unprompted.**

## Trigger

Load this file when:

- The user invokes `/diagram-design:export-diagram <html-file>` (the plugin's slash command — defined in `commands/export-diagram.md` at the repo root).
- The user asks in natural language to export, save, rasterize, convert, or download a diagram in `.svg` or `.png` form. Typical phrasings:
  - "export this as PNG"
  - "save as SVG"
  - "give me a PNG of that diagram"
  - "rasterize it"
  - "convert to png and svg"

The slash command is a thin wrapper that delegates here — both paths run the same procedure below.

## Scope

Both formats are **diagram-only** — just the `<svg>` node. Editorial wrappers (header, summary cards, footer in `-full` variants) are intentionally dropped: the export deliverable is the diagram itself, suitable for Figma, slides, social cards, or blog images.

The SVG-only export keeps the source `<title>` and `<desc>` with the diagram. Their per-diagram and per-variant prefixed IDs keep accessible names unique when several figures share a page.

Inlining several exported SVGs in one host document also requires namespaced `<defs>` IDs (markers, patterns, gradients, filters, clip paths, masks, symbols). The export procedure prefixes those IDs with the source file slug and rewrites matching `url(#…)` / `href="#…"` references, so a light figure next to its `-dark` twin does not silently share arrowheads. The accessible-name guarantee alone is not enough.

If the user explicitly asks for "a screenshot of the whole page including the cards", that's a different request — fall back to a normal full-page screenshot via the user's OS or browser.

## SVG export procedure

**Prefer the packaged helper.** From this skill's directory run:

```
python3 scripts/export_svg.py <html-file> [<out.svg>]
```

That script is the source of truth for the transform below (CSS carry-forward, defs ID namespacing, rgba normalization, and the class-without-style gate). Reimplement only when the helper is unavailable; keep the behaviour identical.

### Manual algorithm (what the helper does)

1. Read the source HTML file.
2. Extract the **first** `<svg ...>...</svg>` block. Use a multiline regex anchored on `<svg` and `</svg>`. Most generated diagrams have only one SVG; if there are multiple, the first is the diagram (gallery files are an exception — see *Edge cases*).
3. Make it standalone:
   - Ensure the opening tag has `xmlns="http://www.w3.org/2000/svg"`. Add it if missing.
   - Ensure a `viewBox` is present. The skill's templates always include one; warn the user if absent rather than guessing.
   - Preserve `role="img"`, `aria-labelledby`, and the first-child `<title>` / `<desc>` exactly as authored.
   - Rewrite HTML-only attribute syntax as XML: a valueless attribute (`<g data-motion-item>`) becomes `data-motion-item=""`, and an unquoted value gets double quotes. Known named HTML character references in labels and attributes become equivalent XML-safe text (for example, `&nbsp;` becomes a nonbreaking space). HTML's legacy names such as `&copy` and `&nbsp` also decode without the semicolon, except inside an attribute value when the next character is a letter, digit, or `=`, as browsers do. Decode once and escape XML delimiters; already escaped references remain escaped. Comments, CDATA and raw style/script content stay as written; style/script opening-tag attributes follow the same reference conversion as other attributes.
   - Set `id="<slug>-root"` on the opening `<svg>` tag, where `<slug>` is the source basename without extension (e.g. `example-loop.html` → `example-loop`). This ID scopes carried CSS so several inlined figures do not leak rules into each other. When replacing an existing SVG root ID, retarget whole CSS ID tokens for that root in the carried CSS, including escaped identifier spellings; compound selectors such as `.diagram#original` remain bound to the root without adding another ancestor. Descendant IDs and quoted selector values remain unchanged; an unescaped dot belongs to a class selector, not to the ID token.
4. **Carry page CSS into the SVG.** Class-styled diagrams (the loop family, process, medallion, data-flow, and others) declare fills and type in the page `<style>` block — `.station`, `.hub`, `.node-name`, and so on. Extracting the bare `<svg>` without those rules yields black boxes. Copy the page's diagram rules into a `<style>` inside `<defs>`, then:
   - Strip CSS comments first, so a comment in front of a rule does not become part of its selector.
   - Re-scope `:root { … }` custom properties onto `#<slug>-root` so the figure keeps its own tokens.
   - Start selectors that begin at the `<svg>` element at the root instead: `svg .zone` becomes `#<slug>-root .zone` and `svg text` becomes `#<slug>-root text`. The exported root element is the `<svg>` itself, so `#<slug>-root svg .zone` would match nothing.
   - Prefix every other kept selector with `#<slug>-root ` (e.g. `.station` → `#example-loop-root .station`).
   - **Drop** page chrome: `*`, `html`, `body`, `main`, `h1`/`h2`/`h3`, `p`, `.frame`, `.eyebrow`, `.summary`, `.card(s)`, `.footer`, `.header`, and the bare `svg { min-width: … }` layout rule. Only the bare `svg` selector is layout; `svg .zone` and `svg text` are diagram rules (see above). Those must not follow a fragment.
   - Carry `color` and `font-family` from the dropped `body` rule onto `#<slug>-root`. SVG content inherits both: `stroke="currentColor"` reads `color`, and text without its own font rule reads `font-family`.
   - **XML-escape** the carried CSS text (`&` → `&amp;`, `<` → `&lt;`) before inserting it into the SVG. Rule bodies can contain XML-sensitive characters (e.g. `content: "R&D"`); a bare `&` makes the standalone file fail to parse.
5. Inject Google Fonts `@import` so the SVG renders with correct typography in a browser. **XML-escape the `&` separators as `&amp;`** — a standalone `.svg` is parsed as strict XML, where a bare `&` starts an entity reference and makes the whole file fail to parse. (Don't copy the raw URL from the HTML `<link href>`; that ampersand form is only valid in HTML.) Merge into the same `<defs>` `<style>` as the carried rules (don't add a second `<defs>`). If a new `<defs>` is needed, insert it after the existing leading `<title>` and `<desc>` so the first-child accessible-title contract is preserved:
     ```svg
     <defs>
       <style>@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600&amp;family=Noto+Serif:ital@0;1&amp;family=Noto+Sans+KR:wght@400;500;600&amp;family=Noto+Serif+KR:wght@400&amp;family=Noto+Sans+TC:wght@400;500;600&amp;family=Noto+Serif+TC:wght@400&amp;display=swap');
       /* …scoped diagram rules… */
       </style>
       <!-- existing markers / patterns stay here -->
     </defs>
     ```
6. **Namespace `<defs>` IDs.** Prefix every referenceable defs ID — on `marker`, `pattern`, `linearGradient`, `radialGradient`, `filter`, `clipPath`, `mask`, and `symbol` — with `<slug>-`, and rewrite matching `url(#…)` and `href="#…"` / `xlink:href="#…"` references. Preserve URL quotes and match fragment IDs case-sensitively (the CSS `url` keyword remains case-insensitive). Rewrite **longest-id-first** so `arrow-accent` is not clipped by a shorter `arrow` rule. Quoted local URLs (`url("#arrow")`, `url('#arrow')`, including XML-escaped quotes in attributes) follow the same rewrite as unquoted URLs. Unrelated fragment IDs and non-local URLs remain unchanged. Example: `id="arrow"` in `example-loop.html` becomes `id="example-loop-arrow"` with `marker-end="url(#example-loop-arrow)"`.
7. Normalize colors for strict SVG 1.1 consumers. This design system's tokens are authored as `rgba(...)` (see `style-guide.md`) and render correctly wherever colors are read as CSS — browsers, Figma, Illustrator. PowerPoint's SVG importer does not: it treats `rgba(...)` and `transparent` as unrecognized and paints them **opaque black**, turning a barely-there tint into a solid block that swallows the label inside it. The transform is lossless (every replacement renders identically to the original in a browser), so apply it to presentation attributes before writing the file:

   ```python
   import re

   svg = re.sub(
       r'(fill|stroke)="rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d*\.?\d+)\s*\)"',
       lambda m: '{0}="#{1:02x}{2:02x}{3:02x}" {0}-opacity="{4}"'.format(
           m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)), m.group(5)
       ),
       svg,
   )
   svg = re.sub(r'(fill|stroke)="transparent"', r'\1="none"', svg)
   ```

   The `\s*` around each channel tolerates a spaced `rgba(45, 49, 66, 0.03)` as well as the compact `rgba(45,49,66,0.03)` the templates normally use; `\d*\.?\d+` accepts an alpha value with or without a leading zero (both `0.03` and `.03` appear in shipped tokens). Matching is scoped to the `fill="..."` / `stroke="..."` presentation attribute. Class-styled diagrams may still carry `rgba(...)` inside the embedded `<style>` block via custom properties (e.g. `--accent-tint`); that form is correct in browsers and in Figma/Illustrator, and is out of scope for this presentation-attribute pass. (A brand's onboarded palette in `style-guide.md` could in principle add a third notation such as `hsl()`; none exists in any shipped token today, so this pass doesn't handle it — extend the regex if one is ever introduced.)
8. **Gate:** if the exported SVG still contains `class=` but no diagram CSS rules, stop and fix the CSS carry step — that fragment will render as black boxes. A fonts-only `<style>` (Google Fonts `@import` with no rules) does **not** satisfy the gate.
9. Prepend `<?xml version="1.0" encoding="UTF-8"?>\n` so the file is well-formed XML.
10. Write to `<basename>.svg` next to the source (e.g. `example-architecture.html` → `example-architecture.svg`). Honour an explicit output path if the user provides one.

### Caveat to surface to the user

Tools that don't fetch remote fonts at import time (offline Illustrator, some Figma import paths, older SVG viewers) will substitute typography. The SVG renders correctly in any modern browser. For pixel-perfect portability, recommend the PNG export.

## PNG export procedure

Render **the original HTML** (not the extracted SVG) and screenshot only the `<svg>` element's bounding box. This keeps font loading reliable (already wired in the source HTML) while satisfying the "diagram only" rule. The PNG always has a **transparent background** (`omit_background=True`) so it can be placed on any slide or doc colour without a white halo. For motion-enabled HTML, append `?motion=static`, await `document.fonts.ready`, and assert the motion root has `data-frame="static"` before capture; never export at an arbitrary wall-clock delay.

### Detection

Before running anything, verify Playwright is installed in the Python interpreter
you will use for the export. Try:

```
python3 -c "import playwright"
```

If that fails, try `python -c "import playwright"` (the usual command on
Windows). Use whichever interpreter passes the import for the rasterization
command below. If both imports fail, surface this exact instruction to the user
and stop:

> Playwright is not available. PNG export requires an approved Playwright
> installation and a compatible browser to be provisioned by the host
> environment; the skill never installs runtime dependencies automatically.
> Then ask me to export again.

Don't auto-install. The user asked for one feature, not a system change.

### Rasterize

Write the snippet below to a temp file and run it with the interpreter that
passed detection: `python3 <tmp.py> <src.html> <out.png>` or
`python <tmp.py> <src.html> <out.png>`:

```python
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright
import sys, pathlib
from urllib.parse import urlsplit, urlunsplit

src, out = pathlib.Path(sys.argv[1]), sys.argv[2]
scale = int(sys.argv[3]) if len(sys.argv) > 3 else 2
source_uri = src.resolve().as_uri()

def request_allowed(request):
    url, kind = urlsplit(request.url), request.resource_type
    if url.scheme == "file":
        return urlunsplit(url._replace(query="", fragment="")) == source_uri
    if url.scheme in ("data", "blob"):
        return True
    try:
        tls = url.port in (None, 443) and url.username is None and url.password is None
    except ValueError:
        return False
    return tls and ((
        kind == "stylesheet" and url.scheme == "https"
        and url.hostname == "fonts.googleapis.com" and url.path == "/css2"
    ) or (
        kind == "font" and url.scheme == "https"
        and url.hostname == "fonts.gstatic.com" and url.path.endswith(".woff2")
    ))

with sync_playwright() as p:
    browser = p.chromium.launch(
        chromium_sandbox=True,
        args=["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE fonts.googleapis.com, EXCLUDE fonts.gstatic.com"],
    )
    context = browser.new_context(
        accept_downloads=False, bypass_csp=False, device_scale_factor=scale,
        ignore_https_errors=False, java_script_enabled=True, permissions=[],
        service_workers="block",
    )
    context.route("**/*", lambda route: route.continue_() if request_allowed(route.request) else route.abort())
    page = context.new_page()
    page.goto(source_uri + "?motion=static", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except PlaywrightTimeoutError:
        # proxied networks may stall webfont subrequests past any deadline;
        # cancel the outstanding load so the capture below can't block on it again
        page.evaluate("window.stop()")
        page.wait_for_timeout(4000)
        print("warning: webfont request stalled - captured with fallback typography; the PNG may not match the intended fonts", file=sys.stderr)
    page.evaluate("document.fonts.ready")
    if not page.locator("[data-motion-root]").evaluate_all(
        "roots => roots.every(root => root.dataset.frame === 'static')"
    ):
        raise RuntimeError("motion export requires a complete static frame")
    svg = page.locator("svg").first
    # Release every clipping ancestor (local scroller, overflow:hidden chrome)
    # so an SVG wider than its frame is captured whole.
    svg.evaluate("el => { for (let a = el.parentElement; a; a = a.parentElement) a.style.setProperty('overflow', 'visible', 'important'); }")
    svg.screenshot(path=out, omit_background=True)
    browser.close()
```

If the `networkidle` wait times out (an allowed Google Fonts request stalled behind a proxy), the snippet cancels the outstanding load with `window.stop()` and captures with fallback typography, printing a warning to stderr — pass that warning on to the user. Any other error propagates and fails the export normally. The URL requests the complete static motion frame, waits for font readiness, and rejects a motion root that has not reached `data-frame="static"`; ordinary script-free diagrams need no motion root.

The snippet still executes the source's inline controller JavaScript. Its browser launch therefore enables Chromium sandboxing explicitly, blocks service workers, downloads, permissions, CSP bypass and invalid TLS, and denies every request except the source document, embedded `data:` / `blob:` resources, and Google Fonts CSS/font files over HTTPS. Do not weaken those controls to render external assets; diagram HTML is required to remain self-contained apart from its declared Google Fonts.

Default `device_scale_factor=2` for crisp output. Accept `1` for compact assets or `3` for print/retina hero use, passed as a third CLI arg.

The overflow release matters for the wide presets. `min-width` equals the viewBox width (see [`output-spec.md`](output-spec.md)), so a `doc-wide` or `slide-16x9` SVG is 1280px inside a 1200px frame, and its `.diagram-container` scroller clips the last 80px on screen. The screenshot covers the SVG's box but not what an ancestor clipped, so without the release the PNG comes out full size with a blank right edge. This is the screen-side counterpart of the templates' `@media print` rule.

### Output naming

`example-architecture.html` → `example-architecture.png`, written next to the source. Honour explicit user-provided paths. The rasterizer encodes the absolute source path as a file URI, so literal `#` and `%` characters in filenames remain filename content.

## Sizing the export

The PNG's pixel dimensions are the SVG's `viewBox` × `device_scale_factor`. So the size decision was already made when the diagram was drawn — see [`output-spec.md` §2](output-spec.md) for the presets. Export only picks the multiplier.

| Destination | Scale | Result from a 1280×720 `viewBox` |
|---|---|---|
| Docs, README, wiki | 2 | 2560×1440 |
| Slide deck (projected) | 2 | 2560×1440 |
| Print / PDF handout | 3 | 3840×2160 |
| Inline thumbnail, email | 1 | 1280×720 |

### Hitting an exact pixel size

When the user needs specific dimensions (an OG card at exactly 1200×630, a slide image at 1920×1080), compute the scale factor instead of guessing — Playwright accepts fractional values:

```
scale = target_width / viewBox_width
```

A 960-wide `viewBox` at a 1200px target is `scale=1.25`. Two rules:

- **Never scale below 1** to hit a small target — that soft-focuses the type. Redraw at a smaller preset instead.
- **Never scale past 4** — beyond that you're upscaling a layout that was designed for a smaller canvas; redraw at `slide-16x9` or a print preset.

If the target aspect ratio doesn't match the `viewBox` aspect ratio, say so and offer to redraw at the matching preset. Padding or cropping a finished diagram to fit a frame is not an export operation — it breaks the 40px safe margin.

## Edge cases

- **Source is `assets/index.html`** (the gallery, multiple SVGs in one file): refuse the export and ask the user which specific diagram file they meant. Don't guess.
- **No `<svg>` block found**: the source isn't a diagram file. Tell the user; don't write anything.
- **Surrounding HTML matters to the user**: they want cards/header in the image. Tell them this skill exports diagrams only, and recommend a browser-based full-page screenshot (or a separate PDF print).
- **Source is missing fonts at runtime**: Playwright will substitute, the screenshot will look off. Check that the source HTML has the `<link href="...fonts.googleapis.com...">` tag in `<head>`. If absent, the file isn't from a current template — fix the source rather than working around it in export.

## What this command never does

- Modifies the source HTML.
- Adds export buttons or `<script>` tags. Static diagrams remain script-free; an already motion-enabled source may retain the scoped controller from [`animation.md`](animation.md), but export never injects another controller.
- Auto-emits `.svg` or `.png` alongside HTML generation. Manual on every call.
- Embeds an HTML wrapper (cards, headers) into the SVG via `foreignObject`. Too fragile across renderers.
