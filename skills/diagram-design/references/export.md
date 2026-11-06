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
python3 scripts/export_svg.py <html-file> [<out.svg>] [--system-fonts]
```

`--system-fonts` skips the Google Fonts `@import` and carried `@font-face` declarations (step 5) so the SVG makes no network request; use it when the skin's font source is `system` (see [style-guide.md § Font source](style-guide.md#font-source)). The diagram CSS still carries over.

Source read and output write failures return exit 2 with an error diagnostic. The viewport must contain four finite SVG numbers with positive width and height; empty or disabled viewports are refused. The class-without-style gate inspects nonempty actual `class` attributes; comments, visible text, empty class values, and `data-class` metadata do not require a stylesheet. Export selects a live SVG and carries live style blocks; HTML comments and script literals do not contribute diagrams or CSS. The selected SVG ends at its own closing tag, so nested icon `<svg>` elements stay inside it. Comments inside the selected SVG remain intact, except that XML forbids `--` inside a comment and a comment ending in `-`: each `--` becomes `- -` and a trailing `-` gets a space. That script is the source of truth for the transform below (CSS carry-forward, defs ID namespacing, rgba normalization, and the class-without-style gate). Reimplement only when the helper is unavailable; keep the behaviour identical.

### Manual algorithm (what the helper does)

1. Read the source HTML file.
2. Extract the **first** top-level `<svg ...>...</svg>` element. Skip HTML comments, `<script>` and `<style>` content, then count `<svg` openings and `</svg>` closings (a self-closing `<svg .../>` does not open one) and stop when the count returns to zero. Read quoted attribute values whole so a `>` or `/>` inside one does not end the tag. A non-greedy regex stops at a nested icon's `</svg>` and truncates the diagram. Most generated diagrams have only one top-level SVG; if there are multiple, the first is the diagram (gallery files are an exception — see *Edge cases*).
3. Make it standalone:
   - Ensure the opening tag has `xmlns="http://www.w3.org/2000/svg"`. Add it if missing. The SVG namespace must belong to the root SVG element; a namespace on a descendant does not satisfy it. An explicit incompatible root namespace is refused.
   - Ensure a `viewBox` is present. The skill's templates always include one; warn the user if absent rather than guessing.
   - Preserve `role="img"`, `aria-labelledby`, and the first-child `<title>` / `<desc>` exactly as authored.
   - Rewrite HTML-only attribute syntax as XML: a valueless attribute (`<g data-motion-item>`) becomes `data-motion-item=""`, and an unquoted value gets double quotes. Known named HTML character references in labels and attributes become equivalent XML-safe text (for example, `&nbsp;` becomes a nonbreaking space). HTML's legacy names such as `&copy` and `&nbsp` also decode without the semicolon, except inside an attribute value when the next character is a letter, digit, or `=`, as browsers do. Decode once and escape XML delimiters; already escaped references remain escaped. Comments, CDATA and raw style/script content stay as written; style/script opening-tag attributes follow the same reference conversion as other attributes.
   - Make comments valid XML. Inside each `<!-- ... -->` outside CDATA, turn every `--` into `- -` and add a space after a body that ends in `-`. Refuse a comment that a browser closes before the next `-->` (`<!-->`, `<!--->`, or one containing `--!>`): the markup after it is live, and rewriting the comment would hide it.
   - Set `id="<slug>-root"` on the opening `<svg>` tag, where `<slug>` is the source basename without extension (e.g. `example-loop.html` → `example-loop`). This ID scopes carried CSS so several inlined figures do not leak rules into each other. When replacing an existing SVG root ID, retarget whole CSS ID tokens for that root in the carried CSS, including escaped identifier spellings; compound selectors such as `.diagram#original` remain bound to the root without adding another ancestor. Descendant IDs and quoted selector values remain unchanged; an unescaped dot belongs to a class selector, not to the ID token.
4. **Carry page CSS into the SVG.** Class-styled diagrams (the loop family, process, medallion, data-flow, and others) declare fills and type in the page `<style>` block — `.station`, `.hub`, `.node-name`, and so on. Extracting the bare `<svg>` without those rules yields black boxes. Copy the page's diagram rules into a `<style>` inside `<defs>`, then:
   - Unwrap CDATA sections in SVG stylesheet text before parsing rules, then strip real CSS comments, so neither XML delimiters nor a comment becomes part of a selector. Preserve comment-looking text inside quoted strings and escapes: `[data-label="net/*retained*/revenue"]` must still match the original attribute value. Keep CDATA content as raw text rather than XML-decoding it; the carried copy is XML-escaped below. The original embedded stylesheet stays in the SVG. CDATA-looking text in an HTML stylesheet remains literal, including inside SVG `foreignObject`, `desc`, or `title` elements. A nested `<svg>` inside HTML switches back to SVG stylesheet handling.
   - Keep diagram rules inside their original `@media` conditions, including nested conditions; print-only paint must not become screen paint. Keyframe bodies remain intact; ordinary identifier names (also quoted) and matching stylesheet/inline `animation` or `animation-name` bindings are prefixed with the SVG root ID so inlined figures cannot share an animation name. Inline style character references are decoded once before inspecting CSS names and escaped once when written as XML; declaration comments are preserved. A custom property's `{ … }` value is token data and stays literal, including any `animation` text inside it. Duration variables with a literal animation name remain supported. Escaped/complex names, unresolved variable animation names, ambiguous shorthand keyword names, SVG-local animation stylesheets, and nested ordinary-rule animation declarations bound to renamed keyframes are refused explicitly rather than silently retargeted. These unsupported animation cases return exit 2 without writing an SVG. Block at-rules containing ordinary rules, including `@layer` and `@container`, retain their grouping and scoped paint. Unsupported declaration-only blocks are dropped with a warning; stray closing braces between rules are ignored, matching browser CSS recovery.
   - Re-scope `:root { … }` custom properties onto `#<slug>-root` so the figure keeps its own tokens.
   - Start selectors that begin at the `<svg>` element at the root instead: `svg .zone` becomes `#<slug>-root .zone` and `svg text` becomes `#<slug>-root text`. The exported root element is the `<svg>` itself, so `#<slug>-root svg .zone` would match nothing.
   - Split selector lists only at top-level commas. Preserve quoted and escaped attribute values, function arguments, and meaningful whitespace while scoping.
   - Prefix every other kept selector with `#<slug>-root ` (e.g. `.station` → `#example-loop-root .station`).
   - **Drop** page chrome: `*`, `html`, `body`, `main`, `h1`/`h2`/`h3`, `p`, `.frame`, `.eyebrow`, `.summary`, `.card(s)`, `.footer`, `.header`, and the bare `svg { min-width: … }` layout rule. Only the bare `svg` selector is layout; `svg .zone` and `svg text` are diagram rules (see above). Those must not follow a fragment.
   - Carry `color` and `font-family` from the dropped `body` rule onto `#<slug>-root`. SVG content inherits both: `stroke="currentColor"` reads `color`, and text without its own font rule reads `font-family`.
   - **XML-escape** the carried CSS text (`&` → `&amp;`, `<` → `&lt;`) before inserting it into the SVG. Rule bodies can contain XML-sensitive characters (e.g. `content: "R&D"`); a bare `&` makes the standalone file fail to parse.
5. Inject Google Fonts `@import` so the SVG renders with correct typography in a browser. **XML-escape the `&` separators as `&amp;`** — a standalone `.svg` is parsed as strict XML, where a bare `&` starts an entity reference and makes the whole file fail to parse. (Don't copy the raw URL from the HTML `<link href>`; that ampersand form is only valid in HTML.) Merge into the same `<defs>` `<style>` as the carried rules (don't add a second `<defs>`). If a new `<defs>` is needed, insert it after the existing leading `<title>` and `<desc>` so the first-child accessible-title contract is preserved:
     ```svg
     <defs>
      <style>@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&amp;family=Geist:wght@400;500;600&amp;family=Geist+Mono:wght@400;500;600&amp;family=Noto+Serif:ital@0;1&amp;family=Noto+Sans+KR:wght@400;500;600&amp;family=Noto+Serif+KR:wght@400&amp;family=Noto+Sans+TC:wght@400;500;600&amp;family=Noto+Serif+TC:wght@400&amp;family=Noto+Sans+SC:wght@400;500;600&amp;family=Noto+Serif+SC:wght@400&amp;display=swap');
       /* …scoped diagram rules… */
       </style>
       <!-- existing markers / patterns stay here -->
     </defs>
     ```
6. **Namespace `<defs>` IDs.** Prefix every referenceable defs ID — on `marker`, `pattern`, `linearGradient`, `radialGradient`, `filter`, `clipPath`, `mask`, `symbol`, and reusable graphics (`g`, `path`, `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `text`, `image`, and `use`) — with `<slug>-`, and rewrite matching `url(#…)` and `href="#…"` / `xlink:href="#…"` references. Compare ID and fragment values after XML character-reference decoding, so equivalent named and numeric references stay connected. For recognized local CSS URL forms (literal `url(...)`, case-insensitive) in paint/reference attributes, inline styles, and stylesheets, decode hex escapes before comparing fragment identity, and preserve the original escape spelling when adding the prefix; `url(#\70 aint)` must stay connected to the namespaced `paint` definition. URL-looking metadata and quoted CSS string contents remain literal. Retarget ID selectors in embedded style rules while leaving declaration colors and unrelated IDs unchanged. Preserve URL quotes and match fragment IDs case-sensitively (the CSS `url` keyword remains case-insensitive). Rewrite **longest-id-first** so `arrow-accent` is not clipped by a shorter `arrow` rule. Quoted local URLs (`url("#arrow")`, `url('#arrow')`, including XML-escaped quotes in attributes) follow the same rewrite as unquoted URLs. Unrelated fragment IDs and non-local URLs remain unchanged. Example: `id="arrow"` in `example-loop.html` becomes `id="example-loop-arrow"` with `marker-end="url(#example-loop-arrow)"`.
7. Normalize colors for strict SVG 1.1 consumers. This design system's tokens are authored as `rgba(...)` (see `style-guide.md`) and render correctly wherever colors are read as CSS — browsers, Figma, Illustrator. PowerPoint's SVG importer does not: it treats `rgba(...)` and `transparent` as unrecognized and paints them **opaque black**, turning a barely-there tint into a solid block that swallows the label inside it. Normalize presentation paint only when its alpha can be preserved: combine a local presentation opacity, but retain RGBA when a CSS or inherited opacity, or a paint override on the element or its children, makes splitting unsafe. An unrelated simple CSS rule does not prevent normalization. Apply this full recipe before writing the file:

   ```python
   import re
   import math
   import html as html_entities
   import xml.etree.ElementTree as ET
   from typing import Callable


   CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)


   XML_OPAQUE_OPEN_RE = re.compile(r"<!--|<!\[CDATA\[")


   START_TAG_RE = re.compile(
       r"<([A-Za-z][\w:.-]*)"
       r"((?:\s+[^\s\"'<>/=]+(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?)*)"
       r"(\s*/?)>"
   )


   TAG_ATTR_RE = re.compile(
       r"(\s+)([^\s\"'<>/=]+)(?:(\s*=\s*)(\"[^\"]*\"|'[^']*'|[^\s\"'=<>`]+))?"
   )


   STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>(.*?)</style\s*>", re.IGNORECASE | re.DOTALL)


   CSS_RULE_ATOM = r'''(?:/\*(?:[^*]|\*(?!/))*\*/|\\[\s\S]|"(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*'|/(?!\*)|[^{}"'\\/])'''


   RULE_RE = re.compile(rf"({CSS_RULE_ATOM}+)\{{({CSS_RULE_ATOM}*)\}}", re.DOTALL)


   RGBA_ATTR_RE = re.compile(
       r'(fill|stroke)="rgba\(\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*,\s*([+-]?\d*\.?\d+)\s*\)"'
   )


   def _rewrite_start_tags(svg: str, transform: Callable[[re.Match[str]], str]) -> str:
       """Transform actual start tags, preserving comments and CDATA sections."""
       out: list[str] = []
       pos = 0
       while True:
           opener = XML_OPAQUE_OPEN_RE.search(svg, pos)
           text_end = opener.start() if opener else len(svg)
           out.append(START_TAG_RE.sub(transform, svg[pos:text_end]))
           if opener is None:
               break
           closer = "-->" if opener.group(0) == "<!--" else "]]>"
           close_at = svg.find(closer, opener.end())
           stop = len(svg) if close_at == -1 else close_at + len(closer)
           out.append(svg[opener.start() : stop])
           pos = stop
           if close_at == -1:
               break
       return "".join(out)


   def _decoded_css_property_text(style: str) -> str:
       """Read opacity spellings conservatively without changing carried CSS."""
       style = CSS_COMMENT_RE.sub("", html_entities.unescape(style))

       def escape(match: re.Match[str]) -> str:
           hexadecimal, literal = match.groups()
           if hexadecimal is not None:
               value = int(hexadecimal, 16)
               return chr(value) if 0 < value <= 0x10FFFF and not 0xD800 <= value <= 0xDFFF else "\ufffd"
           return "" if literal in "\r\n\f" else literal

       return re.sub(r"\\(?:([0-9a-fA-F]{1,6})(?:\r\n|[ \t\r\n\f])?|([\s\S]))", escape, style)


   def _css_paint_may_target_descendants(selector: str, children: list[ET.Element]) -> bool:
       """Exclude provably unrelated simple selectors; preserve unknown CSS cascades."""
       for branch in selector.split(","):
           terminal = re.split(r"[\s>+~]+", branch.strip())[-1]
           # Unsupported selectors remain conservative, including escaped names,
           # attribute selectors and pseudo-classes that can affect descendant paint.
           if not re.fullmatch(r"(?:[A-Za-z][\w-]*|\*)?(?:[.#][\w-]+)*", terminal) or not terminal:
               return True
           tag = re.match(r"^[A-Za-z][\w-]*", terminal)
           classes = re.findall(r"\.([\w-]+)", terminal)
           ids = re.findall(r"#([\w-]+)", terminal)
           for child in children:
               if tag and child.tag.rsplit("}", 1)[-1] != tag.group(0):
                   continue
               if all(name in child.get("class", "").split() for name in classes) and all(
                   name == child.get("id") for name in ids
               ):
                   return True
       return False


   def normalize_rgba_presentation_attrs(svg: str) -> str:
       """Split rgba paint and combine its alpha with existing presentation opacity."""

       # A parent's paint and opacity may be inherited independently. Converting
       # its color alpha into opacity would also change children overriding paint.
       try:
           elements = list(ET.fromstring(svg).iter())
           descendants = {
               index: list(element.iter())[1:]
               for index, element in enumerate(elements) if len(element)
           }
       except ET.ParseError:
           return svg  # The existing final XML validator supplies the public error.
       opacity_counts = {"fill-opacity": 0, "stroke-opacity": 0}
       styles = list(STYLE_BLOCK_RE.findall(svg))

       def collect_opacity_context(match: re.Match[str]) -> str:
           for attr in TAG_ATTR_RE.finditer(match.group(2)):
               key, value = attr.group(2), attr.group(4)
               if key in opacity_counts:
                   opacity_counts[key] += 1
               elif key == "style" and value is not None:
                   styles.append(value[1:-1])
           return match.group(0)

       _rewrite_start_tags(svg, collect_opacity_context)
       css_opacity = {
           key for key in opacity_counts
           if any(re.search(rf"(?:^|[;{{])\s*{key}\s*:", _decoded_css_property_text(style), re.IGNORECASE)
                  for style in styles)
       }

       position = 0

       def normalize_tag(match: re.Match[str]) -> str:
           nonlocal position
           children = descendants.get(position, [])
           element = elements[position]
           position += 1
           name, attrs, end = match.groups()
           values = {
               attr.group(2): attr.group(4)[1:-1]
               for attr in TAG_ATTR_RE.finditer(attrs)
               if attr.group(4) is not None
           }
           updates: dict[str, str] = {}
           additions: list[str] = []
           for prop in ("fill", "stroke"):
               value = values.get(prop, "")
               if value == "transparent":
                   updates[prop] = "none"
                   continue
               rgba = RGBA_ATTR_RE.fullmatch(f'{prop}="{value}"')
               if rgba is None:
                   continue
               _, r, g, b, alpha = rgba.groups()
               opacity_name = f"{prop}-opacity"
               # Presentation opacity may be overridden by CSS or inherited from
               # another element. Preserve the color alpha when that cascade is
               # unresolved instead of replacing it with opaque RGB.
               # Converting a parent is safe when descendants inherit its paint.
               # Preserve alpha if a descendant overrides that paint, including
               # a conservatively detected stylesheet or inline declaration.
               inline_paint = re.search(
                   rf"(?:^|[;{{])\s*{prop}\s*:",
                   _decoded_css_property_text(element.get("style", "")), re.I,
               )
               descendant_paint = any(
                   prop in child.attrib
                   or re.search(rf"(?:^|[;{{])\s*{prop}\s*:",
                                _decoded_css_property_text(child.get("style", "")), re.I)
                   for child in children
               )
               stylesheet_paint = any(
                   re.search(rf"(?:^|[;{{])\s*{prop}\s*:", _decoded_css_property_text(rule.group(2)), re.I)
                   and _css_paint_may_target_descendants(rule.group(1), [element] + children)
                   for style in STYLE_BLOCK_RE.findall(svg)
                   for rule in RULE_RE.finditer(CSS_COMMENT_RE.sub("", style))
               )
               if inline_paint or descendant_paint or stylesheet_paint or opacity_name in css_opacity or opacity_counts[opacity_name] > int(opacity_name in values):
                   continue
               opacity = alpha if 0 <= float(alpha) <= 1 else "0" if float(alpha) < 0 else "1"
               if opacity_name in values:
                   try:
                       original = values[opacity_name].strip()
                       amount = float(original.rstrip("%")) / (100 if original.endswith("%") else 1)
                   except ValueError:
                       continue  # Keep paint intact when the opacity cannot be resolved here.
                   if not math.isfinite(amount):
                       continue
                   opacity = format(min(1, max(0, amount)) * max(0, min(1, float(alpha))), ".12g")
                   updates[opacity_name] = opacity
               else:
                   additions.append(f' {opacity_name}="{opacity}"')
               updates[prop] = "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(c))) for c in (r, g, b)))

           def replace_attr(attr: re.Match[str]) -> str:
               space, key, _equals, _value = attr.groups()
               return f'{space}{key}="{updates[key]}"' if key in updates else attr.group(0)

           return f"<{name}{TAG_ATTR_RE.sub(replace_attr, attrs)}{''.join(additions)}{end}>"

       return _rewrite_start_tags(svg, normalize_tag)


   svg = normalize_rgba_presentation_attrs(svg)
   ```

   Channels and alpha are clamped to the CSS ranges 0–255 and 0–1 so out-of-range rgba values retain their browser paint when converted. The `\s*` around each channel tolerates a spaced `rgba(45, 49, 66, 0.03)` as well as the compact `rgba(45,49,66,0.03)` the templates normally use; `\d*\.?\d+` accepts an alpha value with or without a leading zero (both `0.03` and `.03` appear in shipped tokens). Matching is scoped to the `fill="..."` / `stroke="..."` presentation attribute. Class-styled diagrams may still carry `rgba(...)` inside the embedded `<style>` block via custom properties (e.g. `--accent-tint`); that form is correct in browsers and in Figma/Illustrator, and is out of scope for this presentation-attribute pass. (A brand's onboarded palette in `style-guide.md` could in principle add a third notation such as `hsl()`; none exists in any shipped token today, so this pass doesn't handle it — extend the regex if one is ever introduced.)
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

Keep the user's project directory as the working directory so relative input and
output paths still resolve there. Invoke the packaged renderer by its absolute
path under the resolved skill directory with the interpreter that passed
detection: `python3 <skill-dir>/scripts/export_png.py <src.html> <out.png> [scale]`
or `python <skill-dir>/scripts/export_png.py <src.html> <out.png> [scale]`.

If the `networkidle` wait times out (a stalled font or stylesheet behind a proxy), the helper cancels the outstanding load with `window.stop()` and captures with fallback typography, printing a warning to stderr — pass that warning on to the user. Any other error propagates and fails the export normally. The helper requests the complete static motion frame, waits for font readiness, and rejects a motion root that has not reached `data-frame="static"`; ordinary script-free diagrams need no motion root.

Default `device_scale_factor=2` for crisp output. Accept `1` for compact assets or `3` for print/retina hero use, passed as a third CLI arg. Fractional scales such as `1.25` are also accepted within the documented 1–4 range for exact pixel sizes.

The helper's overflow release matters for the wide presets. `min-width` equals the viewBox width (see [`output-spec.md`](output-spec.md)), so a `doc-wide` or `slide-16x9` SVG is 1280px inside a 1200px frame, and its `.diagram-container` scroller clips the last 80px on screen. The screenshot covers the SVG's box but not what an ancestor clipped, so without the release the PNG comes out full size with a blank right edge. This is the screen-side counterpart of the templates' `@media print` rule.

### Output naming

`example-architecture.html` → `example-architecture.png`, written next to the source. Honour explicit user-provided paths. The rasterizer encodes the absolute source path as a file URI, so literal `#` and `%` characters in filenames remain filename content.

## Sizing the export

The PNG's pixel dimensions are the SVG's `viewBox` × `device_scale_factor`. The rasterizer establishes the capture viewport from the finite, nonzero viewBox dimensions so page CSS cannot enlarge or shrink the promised output. So the size decision was already made when the diagram was drawn — see [`output-spec.md` §2](output-spec.md) for the presets. Export only picks the multiplier.

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

The exporter preserves `@font-face` and scopes ordinary rules within block at-rules such as `@supports`, `@media`, `@layer`, and `@container` without flattening their conditions. Groups containing only keyframes or font faces are also retained, including nested groups, so references outside the group keep their definitions. Declaration-only unsupported blocks are dropped with a warning rather than aborting the export. System-font mode continues to omit custom font-face declarations. Semicolons inside parenthesized CSS functions, including unquoted data URLs, remain value text instead of ending a statement.

CSS grouping rules are scanned once and preserved without recursively rescanning nested bodies. Exports deeper than 1,024 nested CSS blocks fail with a clear diagnostic (CLI exit 2) before writing output.

`@scope` groups containing ordinary paint rules are refused with a clear exit-2 diagnostic before output is written; definition-only scopes retain their keyframes and font faces. `@layer` order statements remain in source order with their layer blocks, including inside grouping rules, so cascade priority is preserved.
The exporter keeps optional defs in comments namespaced so they can be uncommented later. Only referenceable defs element types have their IDs renamed; live titles and other elements retain their IDs and accessibility references.

Animation property names are compared after CSS escape decoding, while their authored spelling is preserved. Page styles and inline attributes keep their binding to namespaced keyframes, including `anim\61 tion` and vendor-prefixed properties. Nested animation declarations and SVG-local animation stylesheets remain unsupported and fail clearly, including escaped property names.
