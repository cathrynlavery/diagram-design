# Unit Grid

**Best for:** one bounded whole expressed as equal, discrete units: completion, capacity, survey responses, inventory, or a checklist. Use the canonical waffle form when the reader needs to see an exact count out of 100.

Not for: category-by-category comparison (use a **bar chart**), a part-of-whole with unequal pieces (use a **treemap**), continuous change (use a **line chart**), or a matrix where row and column positions carry meaning (the future punch-card variant).

## Input contract

```yaml
title: "Release readiness"
total: 100
filled: 64
unit_label: "release check"
focal_index: 63
source_note: "Illustrative checklist"
```

Validation rules:

1. Version 1 is a 10 by 10 grid with exactly 100 cells.
2. `total` is exactly `100`; `filled` is an integer from `0` through `100`.
3. Every cell represents one unit. Do not use fractional cells, scaled cells, or merged cells.
4. At most one completed cell is focal. Accent is editorial emphasis, never a larger unit.
5. Cells fill in reading order, left to right and top to bottom. A different order needs an explicit future variant.
6. Rows and columns carry no category meaning in the canonical waffle form.

## Layout conventions

- Use a 10 by 10 grid of equal 20px cells with a 4px gutter. The shipped examples begin at `(382, 86)`, making the grid 236px square inside a `1000 × 390` viewBox.
- Every chart root carries `data-unit-grid="true"`, `data-unit-total="100"`, `data-unit-filled`, `data-unit-rows="10"`, and `data-unit-columns="10"`.
- Every cell is a `<rect>` with `data-unit-cell="filled"` or `data-unit-cell="empty"` and a unique `data-unit-index` from 0 through 99. `scripts/verify-unit-grid.py` checks count, geometry, indices, the declared filled value, and printed labels.
- Use one ink fill for completed cells, a quieter paper-relative fill for remaining cells, and no more than one accent completed cell. The count, not color, carries the value. Set each cell's literal fill on the `<rect>` (or a parent `<g>`): completed cells must match the page's `:root` `--ink` or `--accent`, and remaining cells share one other fill well away from both. Cells sit directly in the chart `<svg>` or in plain `<g>`/`<a>` groups with no `style`, `transform` or conditional attributes; cell strokes stay at or under 2px and corner radii at or under a quarter of the cell. The verifier rejects opacity, visibility, display, filter, mask, clip-path, paint-order and mix-blend-mode on cells or their ancestors, paint, stroke or hiding rules in `<style>` (after decoding escapes), `@import`, any linked stylesheet but Google Fonts, SMIL animation, and any element drawn after the first cell whose box touches the grid or cannot be computed from plain numeric attributes. It does not see HTML wrappers around the SVG or scripts.
- Mark the percentage text with `data-unit-percent="true"` and the count text with `data-unit-count="true"`. They must read `64%` and `64 complete · 36 remaining` for `filled: 64`; both are checked against `data-unit-filled`. Each label is plain visible `<text>` inside the chart SVG (no child elements, no hiding or `style` attributes), painted `--ink` or `--muted`, at least 8px, and inside the viewBox.
- Do not apply transforms to cells or their SVG/group ancestors, or move geometry through CSS. Bake movement into the coordinates so the verifier checks the rendered positions.
- Put the exact count in text near the grid and state the unit in the source line. The grid must remain understandable in grayscale.
- Keep the legend block below the grid. Label the focal cell as editorial emphasis, so it cannot be mistaken for a special unit.

## Honest-data rule

A unit grid claims that one mark equals one unit. Never round a 63.4% result to 64 filled cells without saying that the display is rounded. Never use a partial fill, larger focal cell, gradient, or area-sized mark to recover precision. If the denominator is not naturally bounded to 100, choose a number of whole cells that makes the unit honest or choose a different chart.

## Complexity budget

- Exactly 100 cells in a 10 by 10 grid.
- One count and one optional focal completed cell.
- One legend and one source note.
- Static output only.
- No categorical row or column axes in version 1.

## Anti-patterns

- Partial, merged, oversized, or differently shaped cells.
- Rainbow status fills or multiple accent cells.
- Using the grid for a denominator other than 100 without an explicit future variant.
- Treating rows and columns as categories. That is the later punch-card variant, not this canonical waffle form.
- Gradients, heatmap ramps, 3-D treatments, or shadows.
- Filling in a non-reading order without explaining that order.

## Examples

- `assets/example-unit-grid.html` - minimal light.
- `assets/example-unit-grid-dark.html` - minimal dark with the same dataset and geometry.
- `assets/example-unit-grid-full.html` - full editorial with unchanged grid geometry.
