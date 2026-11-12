# Steps

**Best for:** a short, ordered sequence of stages where the order is the claim and each stage needs a number, a compact visual cue, a title, and one brief explanation. Use it for methods, playbooks, onboarding paths, launch checklists, and “how it works” explainers.

Prefer **Timeline** when spacing encodes real elapsed time, **Flowchart** when the route branches, **Swimlane** when ownership and handoffs matter, and **Process** when each stage must expose actors, tools, or input/output payloads. Steps has one rail, no branches, no time scale, and no actor lanes.

---

## 1. Inputs

```yaml
steps:                         # 3..7, left to right
  - number: "01"
    title: "Frame"
    description: ["Define the decision", "and its success signal"]
    icon: file                 # optional; from primitive-icons.md
  - number: "02"
    title: "Research"
    description: ["Gather evidence from", "customers and operators"]
    icon: users
  - number: "03"
    title: "Synthesize"
    description: ["Turn observations into", "one testable direction"]
    icon: search
    focal: true
  - number: "04"
    title: "Decide"
    description: ["Commit the scope and", "name the trade-offs"]
    icon: database
  - number: "05"
    title: "Ship"
    description: ["Release, measure, and", "feed learning forward"]
    icon: container
dark: false
```

Rules:

- `steps` contains 3–7 entries. Fewer than three is a list; more than seven needs grouping or a second diagram.
- Exactly one step is `focal: true`. It is the decision, transformation, or risk the figure exists to emphasize.
- `number` is two digits for fewer than 100 steps (`01`, `02`, …) so the rail scans evenly.
- `description` is one or two short lines, each no longer than 26 characters at the standard ramp. Rewrite rather than shrink.
- `icon` is optional and must come from [`primitive-icons.md`](primitive-icons.md). Omit icons from every step if a coherent set is unavailable; never mix line icons, emoji, and brand marks.

---

## 2. Layout grammar

The canonical `doc-wide` canvas is `1280×720`. All structural coordinates sit on the 4px grid.

```text
outer_x          = 80
rail_y           = 240
rail_h           = 48
n                = len(steps)
usable_w         = 1280 - 2 * outer_x
stage_w          = min(224, 4 * floor(usable_w / (4 * n)))
content_w        = n * stage_w
start_x          = (1280 - content_w) / 2
stage_x(i)       = start_x + i * stage_w
stage_cx(i)      = stage_x(i) + stage_w / 2
medallion_cy     = rail_y + rail_h / 2
medallion_r      = 36
number_y         = 164
number_rule_y    = 184..220
title_y          = 360
description_y    = 388, 408
legend_rule_y    = 600
legend_y         = 636
```

This yields a 224px stage for 3–5 steps, 184px for 6, and 160px for 7. Keep `stage_w` on the 4px grid, center the combined rail, and preserve at least 24px between description columns. If copy does not fit the narrower six- or seven-stage columns, widen the canvas or rewrite the copy; do not reduce the type ramp.

### Rail

- Draw one contiguous horizontal rail from `stage_x(0)` to `stage_x(n-1) + stage_w`.
- Each stage owns one `stage_w × 48` segment. Alternate `ink @ 0.05` and `ink @ 0.09` fills to make the segmentation visible without introducing a series palette.
- The focal segment uses `accent-tint` with a 1px `accent` top and bottom rule.
- The rail itself expresses order. Do not add arrows between adjacent stages; they duplicate the layout.

### Number and guide

- Number: `{eyebrow}` role, 8px, weight 600, letter-spacing `0.14em`, centered at `stage_cx(i)`.
- Guide: 1px vertical rule from `y=184` to `y=220`, `rule-solid`; focal guide uses `accent`.
- The number is `muted` by default and `accent` for the focal step.

### Icon medallion

- Circle center `(stage_cx(i), 264)`, radius 36.
- Draw an opaque `paper` circle first so the rail does not show through, then a 1px outline.
- Default outline and icon use `ink`; focal outline and icon use `accent` and the circle may use `accent-tint`.
- Place one 24×24 primitive at `(stage_cx(i)-12, 252)`. Icons are decorative (`aria-hidden="true"`); the accessible name comes from the SVG title and description.

### Copy block

- Title: `{node-name}` role, 12px, weight 600, centered at `y=360`.
- Description: `{sublabel}` role, 9px, centered, at most two lines at `y=388` and `y=408`.
- Titles use `ink`; descriptions use `muted`. The focal title may use `accent`; the description remains `muted`.

---

## 3. Focal and color rules

One step is focal. Treat its number, guide, rail segment, medallion outline/icon, and title as one visual unit. All remaining steps stay neutral.

Do not assign a different hue to every step. The familiar five-color infographic treatment turns sequence into a legend-reading task and conflicts with the global 1–2 accent rule. If stages genuinely encode categories rather than order, use a chart or another type whose color carries data.

---

## 4. Legend

Use a bottom strip only when the focal state needs explanation. The canonical examples show:

- neutral outlined medallion — `Stage`
- accent outlined medallion — `Focal stage`
- italic note — `Equal spacing shows order, not elapsed time.`

If the title or subtitle already names the focal stage and the distinction is obvious, remove the legend.

---

## 5. Reproducibility checklist

1. Step count is 3–7 and exactly one entry is focal.
2. Step origins, segment widths, medallion centers, and copy anchors derive from §2.
3. The rail is contiguous; there are no gaps, arrowheads, or diagonal connectors.
4. Every medallion has an opaque paper mask beneath its outline.
5. Every step either has one icon from `primitive-icons.md` or all icons are omitted.
6. Titles stay at 12px and descriptions at 9px; long copy is rewritten, not shrunk.
7. The focal step is the only accent-bearing stage.
8. The SVG uses the accessible SVG contract and the wrapper owns horizontal scrolling.

---

## 6. What `verify-steps.py` requires

The checker reads attributes, so every mark binds itself to its stage and draws exactly what it states.

- **Bindings.** Each stage has one rail `<rect data-role="rail">`, one medallion `<circle data-role="medallion">` and one number `<text data-role="number">`, all with the same unique `data-step`. Rails also carry `data-index` 1..n in left-to-right order. Exactly one rail and its medallion carry `data-focal="true"`.
- **Geometry.** Rails share `y`, `width` and `height` and touch end to end. Medallions are centered on their segment with one shared radius; numbers are centered on it at `x` and print the two-digit index. Every mark stays inside the viewBox.
- **Allowed attributes.** A rail may carry only `x y width height fill fill-opacity`, a medallion only `cx cy r fill stroke stroke-width`, a number only `x y fill font-size font-weight font-family text-anchor`, plus their `data-*` bindings. No `style`, `class`, `id`, `transform`, `dx`/`dy`, `opacity` or anything else. A number contains only its text.
- **Groups.** Marks sit only inside plain `<g>` groups of the one root `<svg>`, never inside `defs`, a nested `svg` or any other element. A group above a mark may carry only `aria-hidden fill stroke stroke-width stroke-linecap stroke-linejoin font-family font-size font-weight letter-spacing text-anchor`. No attribute may appear twice on any element.
- **Paint and type.** The first `<rect>` in the SVG is the paper (`#f5f5f5` light, `#2d3142` dark). Rails fill with a non-paper house ink above zero alpha. Medallion outlines and numbers use a house ink at 0.4 alpha or more. Numbers resolve to font-size 8 or more, a font family starting with Geist, Geist Mono or Instrument Serif, and `text-anchor="middle"`. Strokes are at most 4 wide.
- **Page and CSS.** Style marks with presentation attributes. Stylesheet rules that can reach the SVG may set only `box-sizing`, `margin`, `padding` and custom properties; nothing may move or hide the diagram. CONTRIBUTING.md lists the page rules in full.

A minimal three-stage figure that passes, with the second stage focal:

```html
<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="steps-min-title steps-min-desc">
  <title id="steps-min-title">Plan, build, ship</title>
  <desc id="steps-min-desc">Three equal stages on one rail; build is the focal stage.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <g aria-hidden="true">
    <rect x="304" y="240" width="224" height="48" fill="rgba(45,49,66,0.05)" data-role="rail" data-step="plan" data-index="1"/>
    <rect x="528" y="240" width="224" height="48" fill="rgba(191,69,32,0.08)" data-role="rail" data-step="build" data-index="2" data-focal="true"/>
    <rect x="752" y="240" width="224" height="48" fill="rgba(45,49,66,0.05)" data-role="rail" data-step="ship" data-index="3"/>
  </g>
  <g font-family="'Geist Mono', monospace" font-size="8" font-weight="600" letter-spacing="0.14em" text-anchor="middle">
    <text x="416" y="164" fill="#4f5d75" data-role="number" data-step="plan">01</text>
    <text x="640" y="164" fill="#bf4520" data-role="number" data-step="build">02</text>
    <text x="864" y="164" fill="#4f5d75" data-role="number" data-step="ship">03</text>
  </g>
  <g aria-hidden="true" fill="#f5f5f5" stroke-width="1">
    <circle cx="416" cy="264" r="36" stroke="#2d3142" data-role="medallion" data-step="plan"/>
    <circle cx="640" cy="264" r="36" stroke="none"/>
    <circle cx="640" cy="264" r="36" fill="rgba(191,69,32,0.08)" stroke="#bf4520" data-role="medallion" data-step="build" data-focal="true"/>
    <circle cx="864" cy="264" r="36" stroke="#2d3142" data-role="medallion" data-step="ship"/>
  </g>
</svg>
```

---

## 7. Anti-patterns

- Rainbow stage bands with no categorical meaning.
- Using Steps for dated events, branching decisions, actor handoffs, or feedback loops.
- Paragraphs under each stage; two short lines is the ceiling.
- A different icon style per stage, emoji mixed with line icons, or icons that repeat the title without adding recognition.
- Arrowheads between every adjacent segment. The left-to-right rail already says “next.”
