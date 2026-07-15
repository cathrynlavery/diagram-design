# Bar / Column Chart

**Best for:** comparing discrete quantities across categories or time intervals — sprint velocity, monthly revenue, feature adoption, cohort counts. Use when each category has a single numeric value and the comparison between bars is the primary message.

## Layout conventions

- **Orientation:** Vertical bars (columns) are default. Horizontal bars are appropriate when category labels are long or you have more than 8 categories.
- **Plot area margins:** left 80px (y-axis labels), bottom 60px (x-axis labels), top 40px, right 40px — inside a `0 0 1000 500` viewBox.
- **Bar count cap:** 4–8 bars. More than 8 → group into periods or split into two charts.
- **Bar width:** ≥ 50% of the column pitch (the gap should never exceed the bar). Typical: pitch=110px, bar=72px.
- **Y-axis gridlines:** 4–6 horizontal lines at regular intervals. Stroke `rgba(45,49,66,0.08)` (very faint), 0.8px. X-axis baseline at `rgba(45,49,66,0.25)`, 1px.
- **Y-axis labels:** right-aligned Geist Mono 8px muted, at x=72 (8px left of the plot area).
- **X-axis labels:** centered below each bar, Geist sans 11px 600 for category names.
- **Value labels:** Geist Mono 8px above each bar. Focal bar label in accent; others in muted.
- **Focal bar:** 1 bar max in accent fill/stroke. All others in `muted @ 0.15` fill + `muted` stroke.
- **Y-axis line:** thin vertical `<line>` at x=80 from y=40 to y=420.

### Bar element pattern

```svg
<!-- Opaque paper mask prevents bleed from background -->
<rect x="X" y="Y" width="W" height="H" fill="#f5f5f5"/>
<!-- Bar body -->
<rect x="X" y="Y" width="W" height="H" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1"/>
<!-- Value label above bar -->
<text x="X+W/2" y="Y-8" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle">VALUE</text>
```

Focal bar: replace fill with `rgba(235,108,54,0.12)`, stroke with `#eb6c36`, label fill with `#eb6c36`.

## Anti-patterns

- More than 8 bars without grouping (illegible at normal scale).
- Truncated y-axis (not starting at 0) — distorts the magnitude comparison.
- Accent on more than 1 bar ("everything is important" = nothing is).
- 3-D bar extrusion — no shadows, no depth.
- Category labels rotated more than 45°; prefer short labels or horizontal chart instead.

## Variants

- **Grouped bars:** two bars per category, side by side. Use `accent` for the primary series and `series-1` for the secondary. Max 2 groups.
- **Stacked bars:** segments stacked to total. Use `accent` for the focal segment; muted tints for others. Document the total at the top of each stack.

## Examples

- `assets/example-bar.html` — minimal light
- `assets/example-bar-dark.html` — minimal dark
- `assets/example-bar-full.html` — full editorial
