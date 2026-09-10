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
- Every cell is a `<rect>` with `data-unit-cell="filled"` or `data-unit-cell="empty"` and a unique `data-unit-index` from 0 through 99. `scripts/verify-unit-grid.py` checks count, geometry, indices, and the declared filled value.
- Use one ink fill for completed cells, a quieter paper-relative fill for remaining cells, and no more than one accent completed cell. The count, not color, carries the value.
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
