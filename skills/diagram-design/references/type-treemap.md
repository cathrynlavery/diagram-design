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

## Examples

- `assets/example-treemap.html` — minimal light
- `assets/example-treemap-dark.html` — minimal dark
- `assets/example-treemap-full.html` — full editorial
