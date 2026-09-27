# Treemap

**Best for:** part-of-whole where the *relative sizes are the story* — disk and bundle usage, budget or spend breakdowns, market share, population, time allocation. Use when a single total decomposes into parts and the reader's question is "what dominates, and by how much?"

Not for: ranked lists where exact values matter more than proportion (use a **bar chart**), containment or scope relationships with no quantity (use **nested**), or a hierarchy you need to trace parent-to-child (use a **tree**).

## Layout conventions

- **Plot area:** `x` 40 → 956, `y` 40 → 420 inside a `0 0 1000 500` viewBox — the same vertical rhythm as bar, line and scatter, so the legend block sits where a reader of those types already expects it (rule at `y=462`, `LEGEND` at `478`, keys at `488`).
- **Squarified layout** (Bruls et al., 2000): sort descending, lay each row against the *shorter* side of the remaining rectangle. Aspect ratios stay near 1, which is what makes two areas comparable by eye. Never lay cells out in simple stripes — long thin cells cannot be compared.
- **Cell count:** 4–8. Past 8, the tail becomes unlabelable slivers — group the tail into a single explicit "Other" cell and name what it contains in the source line.
- **4px grid:** cell edges snap to the grid like everything else, with a 4px gutter between cells. Snapping and gutters both move area, so check the result — and check it as **relative** error (`(drawn − true) ÷ true`), not percentage points. A 0.1pp slip is nothing on a 59% cell and a quarter of a 0.5% cell; absolute error hides exactly the mistake you need to catch. Keep every cell within a few percent of its true share — the shipped example is within 2.7%, its worst case being the sliver, where the grid cannot do better — and state the encoding in the source line (`AREA = POPULATION`). `scripts/verify-treemap.py` gates this.
- **Fill:** a rank-ordered `ink` opacity ramp (e.g. `0.16 → 0.04`), so the non-focal order survives greyscale printing and colour-blind readers. One accent cell only — the editorially focal one, not automatically the largest. Note what this does *not* buy you: the focal cell is painted off-ramp, so in greyscale it lands wherever its tint happens to fall, not at its rank. Identify it by the accent stroke, and never let tone carry meaning the area doesn't already carry. `ink` is a role, not a colour: it resolves near-black on light paper and near-white on dark, so one ramp of opacities composites *darker* as it strengthens in the light skin and *lighter* in the dark one. The opacities are identical in both; only their lightness flips.
- **Stroke:** 1px `ink @ 0.30` hairline on every cell; the focal cell takes a 1.5px `accent` stroke.
- **Labels sit inside the cell**, top-left, 16px in from the edge: name in Geist 12–14px 600, value in Geist Mono 9px on the next line. Three tiers by cell size:
  - large — name + value + share (`4.78B · 59% of world`)
  - medium — name + value
  - small — a 3-letter mono abbreviation, if one reads honestly
  - sliver — **no text.** When the cell is at least 12×12px, use a filled `ink` disc, `r=5`, centred in the cell, carrying a paper-coloured `i`, with the cell's name and share spelled out in the legend. Below 12px on either axis, omit the in-cell mark and identify the sliver by position in the legend; a fixed-size disc must never cross the cell boundary. `scripts/verify-treemap.py` checks marker containment. Resist rotating a label to make it fit: a single sideways word among five upright ones reads as a mistake before it reads as data, and its centring is a trap — `text-anchor="middle"` centres along the *baseline*, which a quarter-turn maps to the cell's long axis, leaving nothing centring the cap-height band across the narrow one.
  - Never shrink a cell to fit its label. The cell size is the data; the label is commentary.
- **Contrast:** compute the ceiling against the token you actually ship. The 9px value line is `muted`, not `ink`, and `muted` needs a lighter cell than `ink` does: measured against the composited fill, the top of the ramp can go to **0.16 on light paper and 0.14 on dark** before it drops under 4.5:1. (`ink` would tolerate 0.20 — which is exactly the number you will write down if you check the wrong token.) A mid-tone fill — solid accent, or 50% ink — fails against both light and dark text; use the tint-plus-stroke pattern instead. The source line takes `muted` too: `soft` measures 3.48:1 on paper and never reaches AA anywhere on this ramp.
- **Legend:** the house block (rule, `LEGEND`, keys), naming the focal cell, the direction of the ink ramp, and any cell carrying an info mark. **Name that direction by contrast against the paper — `stronger contrast is larger` — never by lightness.** `darker is larger` is true only on light paper; ship it in the dark variant and the legend states the opposite of what the reader sees, because the ramp's lightness inverts with the skin while its opacity does not. Named by contrast, one sentence serves all three variants and cannot rot apart. `scripts/verify-skin-polarity.py` gates this, checking every directional tone claim against the ramp composited on that file's own paper. The source line rides the same row as `LEGEND`, right-aligned in mono 8px, stating what area encodes plus the dataset and its date.

### Declaring the share

**Every cell carries `data-share` — including cells too small to label.** It is the cell's percentage of the whole, and it is what makes the area checkable:

```svg
<rect x="X" y="Y" width="W" height="H" rx="2" data-share="18.29" fill="…" stroke="…"/>
```

Without it, a verifier has to infer the intended share from the text inside the cell, which quietly exempts the one cell that has no text — and that is the sliver, the cell the 4px grid distorts most. A shipped treemap once had its smallest cell drawn 50% oversized with every gate green for exactly this reason. `scripts/verify-treemap.py` now fails closed on any cell without it, and cross-checks `data-share` against the percentage the label prints, because a label and the metadata are two statements of one fact.

### Cell element pattern

```svg
<!-- Opaque paper mask prevents the dot pattern showing through the tint -->
<rect x="X" y="Y" width="W" height="H" rx="2" fill="#f5f5f5"/>
<!-- Cell body -->
<rect x="X" y="Y" width="W" height="H" rx="2" data-share="18.29" fill="rgba(45,49,66,0.16)" stroke="rgba(45,49,66,0.30)" stroke-width="1"/>
<text x="X+16" y="Y+28" fill="#2d3142" font-size="13" font-weight="600" font-family="'Geist', sans-serif">NAME</text>
<text x="X+16" y="Y+46" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace">VALUE · SHARE</text>
```

Focal cell: replace the fill with `rgba(235,108,54,0.16)` and the stroke with `#eb6c36` at 1.5px.

## Honest-data rule

**Area is the only encoding.** Never clip, floor, or log-scale a cell to make it visible, and never drop a cell because it is small — a treemap claims to show a whole, so an omitted part makes the picture a lie. A part too small to label gets a legend entry and, only when the cell can contain it, an info mark; parts too small to draw get merged into one honest, named "Other". If several cells are invisible at the target size, the data wants a bar chart.

Watch the smallest cell hardest: it is the one that grid snapping and gutters distort most, and the one nobody checks. Beware, too, the rounding you *display*: six values each rounded up can sum past the total you printed underneath them. Either carry enough precision that the parts reconcile, or say plainly in the source line that they don't (`PARTS ROUNDED, MAY NOT SUM`).

## Anti-patterns

- More than 8 cells without an "Other" bucket (unlabelable slivers).
- A stated total the cells contradict by more than display rounding — or rounding that is never disclosed. Rounded parts that miss the total by a hair are honest once the source line says so; silently printing figures that don't reconcile is not.
- Stripe layout instead of squarified — defeats area comparison.
- Rainbow fills: one hue per cell destroys the rank reading and the one-accent rule.
- Nesting more than two levels deep in a static diagram; a second level needs a heavier border and its own label tier, and a third is unreadable without interaction.
- 3-D or shadowed cells — area is already the message.

## Variants

- **Marimekko:** the same area encoding on a grid — column width is the category's share, segment height is the series' share within it, so area is the joint share. Full spec below.

### Marimekko

**Best for:** a **two-way part-of-whole** where both splits matter and the reader's question is "which cell of the cross-tab dominates?" — CI minutes by pipeline × runner OS, bundle bytes by package × chunk, spend by team × vendor, incidents by service × severity. The treemap above answers one question (what dominates the whole); a marimekko answers three at once: read across for the category mix, down for the series mix within a category, and by area for the joint share. A stacked bar with equal-width bars shows the within-category mix and throws the category sizes away; a treemap shows the joint sizes and throws the grid away.

Not for: a one-way split (that is the parent treemap, and a marimekko with one series is a bar chart); more than ~5 series or ~8 categories, past which the small cells become unlabelable slivers in *both* directions; series measured in different units, which cannot share one column; or a comparison of the series' totals across categories, which the height encoding deliberately hides — if that is the reading, the data wants a grouped bar.

#### Layout conventions

- **Plot area:** the treemap's — `x` 40 → 956, `y` 40 → 420 inside a `0 0 1000 500` viewBox, legend block at `y=462`/`478`/`488`. Column captions sit under the plot at `y=438`, Geist Mono 9px, centred on their column. The shipped example spends 900px of column width across five columns with four 4px gutters.
- **Column width is category share** of the whole, over the sum of column widths. Column edges snap to the 4px grid, so the gutters do; keep the gutter constant — a widened gap reads as a narrower column.
- **Every column is the full plot height**, and its segments tile it top to bottom with no gaps and no gutters, separated by the hairline stroke alone. **Segment height is the series' share within its column**, so the same height means the same within-category share whatever the column's width. Segment boundaries are data and land on whole pixels, exempt from the 4px grid as the waterfall's bar tops are.
- **One series order, top to bottom, in every column** — the order of the series' overall totals, largest at the top. A series absent from a category is omitted from that column, never drawn at zero height; the rows do not align across columns and are not meant to, which is why every segment prints its own share.
- **Column and series budgets:** 3–8 columns, 2–5 series. Widths under ~24px cannot hold a label in either direction and take the treemap's information mark instead.
- **Labels sit inside the segment**, top-left, 16px in, in the treemap's tiers by height: 56px and above takes the name in Geist 12px 600 with the amount and within-column share in Geist Mono 9px on the next line (`2,140 min · 68%`); 32–55px takes the same pair at 11px/9px on a tighter pitch; below that, the mark or nothing. The focal segment may add what its share is *of* (`83% of mobile`) because that is the one number a reader is most likely to misread as a share of the whole. Never shrink or widen a segment to fit a label.
- **Column captions** print the column's name and its share of the whole (`web · 31%`), so the width can be read as a number without a ruler.
- **Hold the 760px canvas on narrow screens.** The SVG keeps `min-width: 760px` so its 9px labels stay readable, and sits inside a local `overflow-x: auto` wrapper (`.diagram-container`) so a phone scrolls the chart, not the page. `scripts/lint-render.py --all` renders every marimekko at 390px and fails on page-level overflow, a shrunken canvas, or a missing local scroller.

#### Colour

The treemap's colour section holds here with one change: the ramp runs **per series, not per cell**. Every segment of one series takes one `ink` opacity — strongest on the series with the largest overall total (`0.16 → 0.10 → 0.05` on light paper, `0.14 → 0.09 → 0.04` on dark) — so a row reads as one thing across the figure and the legend needs one key per series, not a direction word. One accent segment, marked by its `accent` stroke at 1.5px and the accent tint, on the editorially focal cell. Labels stay `ink` (names) and `muted` (amounts) everywhere, and the top of the ramp stays at the treemap's contrast ceiling for the same reason.

#### Honest-data rule

**Width, height and area are three statements of one table, and every one of them is checked.** A column widened to fit its label lies about the category; a segment padded for headroom lies about the series; either lies about the joint share, which is the reading the type exists to give. `scripts/verify-marimekko.py` recomputes all three from the amount every segment declares, as relative error, so the narrow column and the thin segment are held to the same standard as the giants.

- **Never drop a category or a series to tidy the grid.** A marimekko claims to show a whole; a missing column makes every other width a lie, and a missing segment makes every other height in its column one. Merge the tail into a named "Other" column or series instead.
- **A series absent from a category is omitted, not drawn at zero.** A zero-height rect is a cell that claims to exist; an omitted one is a gap the legend can explain.
- **Say what the amounts are** in the source line — the unit, the period, the total — and say when they are illustrative. The checker verifies internal consistency only; a figure wrong by the same factor everywhere is self-consistent.

#### Declaring the values

Every segment is one `<rect>` (over its paper mask, as in the parent) carrying the category, the series and the amount. Every visible string is bound to what it describes.

```svg
<rect x="580" y="106" width="216" height="314" rx="2" data-column="mobile" data-segment="macOS" data-amount="1980" fill="rgba(235,108,54,0.16)" stroke="#eb6c36" stroke-width="1.5"/>
<text data-column="mobile" data-segment="macOS" data-role="label" x="596" y="152" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace">1,980 min · 83% of mobile</text>
<text data-column="mobile" data-role="caption" x="688" y="438" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" text-anchor="middle">mobile · 24%</text>
<text data-segment="macOS" data-role="key" x="344" y="497" fill="#4f5d75" font-size="8.5" font-family="'Geist', sans-serif">macOS</text>
```

`data-amount` is the basis of every geometric check, and `data-segment` on a `<rect>` is this contract's scope key: the parent binds `data-share` on a `<rect>` and reads only files named for it, slopegraph binds `data-series` on a `<line>`, bump `data-ranks` and ridgeline `data-bins` on a `<path>`, bubble `data-size` and beeswarm `data-value` on a `<circle>`. No two gates read one attribute, so no two gates claim one file. A label prints the segment's amount and its within-column share and nothing else numeric; a caption prints its column's name and share of the whole; a key names its series. `scripts/verify-marimekko.py` covers the shared plot, the constant gutter, the width, height and area shares, the tiling, the series order, the accent count, every binding and the marker fit; `scripts/test-verify-marimekko.py` proves each check in both polarities and pins the scope treaty with the parent and the sibling gates.

**No `transform` on any of it**, by any carrier — the `transform` attribute, an inline `style`, or a `<style>` rule — on a segment, a bound label, or an ancestor `<g>`. The checker reads raw coordinates, and a transform moves the rendered mark away from the number that was verified.

#### Anti-patterns

- Equal-width columns — that is a 100% stacked bar, and the category sizes are gone.
- Columns of different heights, or a gutter between segments — height stops being a share of anything.
- A series in a different order in one column, or one drawn at zero height where it is absent.
- One hue per series instead of the ink ramp plus a single accent; a legend that names the ramp by tone instead of by series.
- A column widened, or a segment padded, to fit its label.
- A category or series silently dropped from the grid.
- More than 5 series or 8 categories without an "Other".
- A stated total the segments contradict by more than display rounding.

## Examples

- `assets/example-treemap.html` — minimal light
- `assets/example-treemap-dark.html` — minimal dark
- `assets/example-treemap-full.html` — full editorial
- `assets/example-marimekko.html` — marimekko, minimal light
- `assets/example-marimekko-dark.html` — marimekko, minimal dark
- `assets/example-marimekko-full.html` — marimekko, full editorial
