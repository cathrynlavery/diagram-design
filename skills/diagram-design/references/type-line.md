# Line Chart

**Best for:** continuous trends over time or a sequential index — signups over weeks, revenue by month, latency over releases. Use when the direction and rate of change between points is the primary message.

## Layout conventions

- **Plot area margins:** left 80px, bottom 60px, top 40px, right 40px — inside `0 0 1000 500` viewBox.
- **Points:** 4–12 data points. Fewer → consider a summary stat; more → aggregate into periods.
- **X-axis:** evenly spaced time/index labels below the plot. Use Geist Mono 8px, centered on each point x.
- **Y-axis gridlines:** 4–6 horizontals at regular intervals. Same faint treatment as bar chart.
- **Lines:** `<polyline>` with `fill="none"`. Focal series `stroke-width="1.8"`, others `"1.2"`.
- **Vertex dots:** only on the focal series (`r=4`, filled). Other series: line only.
- **Area fill (optional):** `<polygon>` closing back to `y=420` (x-axis baseline) at 0.08 opacity. Use for the focal series only when the area meaning is important.
- **Multi-series:** up to 5 series. Focal = `accent`. Others = `series-1`, `series-2`, `series-3`, `series-4` from style-guide.md. Apply series palette in order — don't skip.
- **Legend:** horizontal strip at the bottom. Swatch = 16×8px rect with the series fill/stroke. One entry per series.

### Polyline pattern

```svg
<!-- Focal series -->
<polyline points="x0,y0 x1,y1 x2,y2 ..."
          fill="none" stroke="#eb6c36" stroke-width="1.8" stroke-linejoin="round"/>
<!-- Dots at each point (focal only) -->
<circle cx="x0" cy="y0" r="4" fill="#eb6c36"/>

<!-- Non-focal series -->
<polyline points="x0,y0 x1,y1 ..."
          fill="none" stroke="#7c8f6f" stroke-width="1.2" stroke-linejoin="round"/>
```

## Anti-patterns

- More than 5 series (visual mush — reduce or split).
- Lines that don't start at a shared zero baseline unless explicitly annotated.
- Smoothed/spline curves when the underlying data is sampled — polyline is honest.
- Dots on every series when there are 4+ series (only focal gets dots).
- Y-axis that doesn't include zero when the absolute magnitude matters.
- Connecting discontinuous data segments without a visual gap.

## Examples

- `assets/example-line.html` — minimal light
- `assets/example-line-dark.html` — minimal dark
- `assets/example-line-full.html` — full editorial
