# Scatter Plot

**Best for:** correlation and distribution — two continuous variables plotted against each other. Use when the relationship (or lack of one) between variables is the message, or when you need to identify clusters, outliers, and high/low performers.

## Layout conventions

- **Plot area margins:** left 80px, bottom 60px, top 40px, right 40px — inside `0 0 1000 500` viewBox.
- **Point count:** 5–30 points. Fewer → just describe the relationship in prose; more → bin into a density contour.
- **Axes:** X at y=420 (baseline), Y at x=80. Both use `arrow-label` role 8px gridline labels. Gridlines 4–6 per axis at equal intervals.
- **Point shape:** `<circle>` r=5 for standard points, r=6 for focal. Focal point in `accent` fill. Others in `muted @ 0.20` fill + `muted` stroke.
- **Labels on points (optional):** `arrow-label` role 8px next to a point. Use a paper-fill rect mask behind the label. Label at most 2–3 points; not all.
- **Trend line (optional):** `<line>` from lower-left to upper-right, stroke `ink @ 0.25` dashed 4,3. Never force a perfect fit — only add if the trend is visually obvious.
- **Quadrant dividers (optional):** light dashed lines at the median x and y to split into quadrants. Label each quadrant in the `arrow-label` role at 8px, `muted`.

### Point pattern

```svg
<!-- Non-focal point — paper mask + circle -->
<circle cx="X" cy="Y" r="5" fill="{paper}"/>
<circle cx="X" cy="Y" r="5" fill="{muted @ 0.20}" stroke="{muted}" stroke-width="1"/>

<!-- Focal point -->
<circle cx="X" cy="Y" r="6" fill="{paper}"/>
<circle cx="X" cy="Y" r="6" fill="{accent @ 0.15}" stroke="{accent}" stroke-width="1.2"/>
```

## Anti-patterns

- More than 30 points without clustering (jitter/mush).
- Forced trend line when the data is genuinely scattered — dishonest.
- Point labels on every point (label the focal and 1–2 notable outliers only).
- Bubble size encoding (use a third axis label or color instead; bubble area perception is unreliable).
- Axes that don't include zero when the absolute position matters; axes that do include zero when the range is tiny and far from zero.

## Examples

- `assets/example-scatter.html` — minimal light
- `assets/example-scatter-dark.html` — minimal dark
- `assets/example-scatter-full.html` — full editorial
