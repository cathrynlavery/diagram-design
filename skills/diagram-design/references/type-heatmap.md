# Heatmap

**Best for:** cross-tabulated data where *which row × column combination stands out* is the story. Use when the reader needs to scan a full matrix at once — not compare individual bars or trace a trend line — and one cell (or a cluster of cells) is editorially distinct from the field. Common uses: CI failure rate by service and sprint, support ticket volume by team and week, confusion matrix for a classifier, correlation coefficients across many variables.

## Layout conventions

- **Plot area:** left 160px (row labels), top 64px (column labels), right 40px, bottom 120px (legend area); inside `0 0 1000 500` viewBox.
- **Cell size:** 116px wide × 56px tall, gap 4px. Maximum grid: 6 columns × 5 rows within the viewBox; smaller grids scale the cells up to fill the space.
- **Row count:** 3–7. Fewer → a table says it with less ink; more → the cells shrink below readability at the minimum viewBox width.
- **Column count:** 3–8. Same constraint: 8 × 116 = 928px exceeds the available 800px at this viewBox, so either reduce columns or reduce cell width proportionally (minimum cell width 80px).
- **Axes:** row labels right-aligned in the left gutter (Geist Mono 9px, `text-anchor="end"`, x=148); column labels centered above each column (Geist Mono 9px, `text-anchor="middle"`); axis titles in Geist Mono 7px small-caps rotated/positioned in the margins.
- **Value text (optional):** Geist Mono 8px centered inside each cell. Flip text color to paper when fill opacity ≥ 0.40 (the ink ramp becomes dark enough to carry white); keep ink text below that threshold.

### Cell pattern

Every cell is two overlapping `<rect>` elements: a paper-fill underlay (no data attributes, paints the background), then the data rect with all three data bindings.

```svg
<!-- Paper underlay — no data attributes, scenery only -->
<rect x="160" y="64" width="116" height="56" fill="#f5f5f5"/>

<!-- Data cell — all three bindings required -->
<rect data-row="auth" data-col="S1" data-value="4"
      x="160" y="64" width="116" height="56"
      fill="rgba(45,49,66,0.29)"/>

<!-- Focal cell — data-focal="true" required, uses accent fill -->
<rect x="520" y="124" width="116" height="56" fill="#f5f5f5"/>
<rect data-row="payments" data-col="S4" data-value="47" data-focal="true"
      x="520" y="124" width="116" height="56"
      fill="rgba(235,108,54,0.85)" stroke="#eb6c36" stroke-width="1.2"/>
```

## The fill ramp

**One ink ramp, one accent.** Non-focal cells use a single tonal ramp: `rgba(INK, opacity)` where opacity is a non-decreasing function of the data value. The shipped example uses `opacity = max(0.07, value / max_non_focal × 0.65)`. Any monotone formula (linear, sqrt, log) passes the verifier as long as opacity never decreases with value.

**One focal cell only.** The accent marks the editorially focal cell — the one whose combination of row and column is the figure's argument. It is not the automatically highest value; choose the cell whose story the title is about. `data-focal="true"` is required; `scripts/verify-heatmap.py` counts all accent-fill and `data-focal` cells and fails if more than one is found.

**Ramp bounds:** the lowest-value non-focal cell should land at ≥ 0.05 opacity (the cell must be visually distinct from the paper background) and the highest-value non-focal cell at ≤ 0.70 (the ramp must not bleed into the focal accent's territory).

## Anti-patterns

- A hue per row or per column — hue is not a continuous variable; it maps "which series" (slopegraph contract), not "how much". The ramp carries quantity; the label carries category identity.
- A multi-hue diverging ramp (e.g. blue–white–red) — these read as two variables (negative and positive deviation from center) and are only honest when the data is signed and the center is meaningful. For unsigned rates or counts, the single ink ramp is the honest encoding.
- Focal accent on more than one cell — if two cells are both focal the figure needs a different title; hue-coding two things is a palette decision masquerading as an editorial one.
- A value axis (color bar with a continuous legend) instead of a discrete ramp strip — the ink ramp is not a gradient legend; it encodes comparative reading ("S4 is much darker than S3"), not precise magnitude retrieval. If readers need the exact value, the number printed inside the cell carries it.
- Rows or columns dropped because they made the pattern less clean — omitted rows and columns are invisible to the reader and look like "the services that didn't have this problem". Name everything included and say in the footnote if anything is excluded.
- A transform on a cell, its underlay, or an ancestor `<g>`. The verifier reads raw `x`/`y`/`width`/`height` attributes; a transform silently moves the rendered mark off the verified position.

## Honest-data rule

**Row × column labels are complete and stated.** A heatmap that quietly drops a service with a high rate is a filtered view the reader cannot see. State every included row and column; note any exclusions in the footnote or source line.

**The ramp scale is declared.** The legend strip shows the range the ramp covers for non-focal cells, stated as "LOW" to "HIGH" rather than a continuous scale — because the ramp's job is comparative, not absolute. If the footnote states bounds, those bounds must match the actual minimum and maximum non-focal values in the figure.

**The focal cell is excluded from the ramp's scale.** Its value (often an outlier) would collapse every other cell into near-identical opacity if included. The footnote must state the focal cell's value explicitly. `scripts/verify-heatmap.py` checks that the focal cell carries `data-focal="true"` and that no non-focal cell uses accent fill.

## Declaring the values

**Every drawn cell is bound to its row, column, and value.** The paper underlay carries nothing. The data rect carries all three.

| Binding | Without it |
|---|---|
| `data-row` on the data rect | A row cannot be identified during verification; a swapped row passes silently. |
| `data-col` on the data rect | A column cannot be identified; a shuffled column is invisible to the verifier. |
| `data-value` on the data rect | The fill cannot be verified as monotone; any opacity passes. |
| `data-focal="true"` on the focal rect | The focal cell is counted as a non-focal cell with an unexplained accent fill. |

`scripts/verify-heatmap.py` enforces the complete `rows × cols` grid, the monotone fill ramp on non-focal cells, and at most one focal cell. It does **not** verify cell geometry (position, width, height) because both axes are categorical — position encodes "which row/column", and that is carried by the label, not by a scale the checker can measure against.

**No `transform` on any verified element.** Bake any coordinate offsets directly into `x`/`y` attributes.
