# Radar / Spider

**Best for:** comparing 3–5 entities across 3–5 quantitative criteria on a single normalized 0–N scale. Capability matrices, product or backend evaluations, framework/team scorecards. Where a comparison table starts running out of horizontal room, radar makes the shape of each option legible at a glance.

## Layout conventions

- **N axes (3–5).** Equally spaced on a regular polygon-N. First axis at the top (`-90°`), going clockwise. **Above 5 → split or use a comparison table.**
- **Five concentric grid rings** at fractions `0.2 / 0.4 / 0.6 / 0.8 / 1.0` of the radius. Drawn as closed polygons connecting the axis vertices at that fraction. Inner four at `rule` 0.10 opacity, outer ring at `rule-solid` 0.20 (a hint stronger to anchor the chart).
- **Axis spokes** from center to each outer vertex. `rule-solid` 0.20 opacity. **No arrowheads.**
- **Axis labels:** one word per spoke (Jobs-minimal). Geist sans 11px weight 600. Place 16px outside the outer ring along the axis vector. Top/bottom = `text-anchor="middle"`; right side = `start`; left side = `end`.
- **Scale ticks** (e.g. `2 4 6 8 10`) only on the **first (top) axis** — putting numbers on every spoke clutters the chart fast. Geist Mono 8px, `muted`, anchored end at `cx − 6`.
- **Series polygon:** stroke 1.5px at the series color, fill the same color at `0.18` opacity (`0.22` in dark). Stroke 1.8px on the focal series — a subtle weight bump.
- **Vertex dots:** **only on the focal series**, `r=4` filled with the series color. Non-focal series are stroke-and-fill only. This is the load-bearing rule that keeps the chart readable at 4–5 series.
- **Drawing order:** dots-pattern bg → grid rings → axis spokes → axis labels → scale ticks → non-focal series (smallest area first) → focal series → focal vertex dots → legend.
- **Legend:** horizontal strip at the bottom (per the global rule). Swatch is a 16×8 rectangle (matches the polygon stroke+fill, not a circle), then the entity name. ~140px between entries. Optional italic tail on the right with the rationale (`"One coral. Position is the signal — color reserved for the recommended option."`).

## Math

For axis `i` (0-indexed) of `N`, value `v` on scale `S`, center `(cx, cy)`, outer radius `R`:

```
angle = -π/2 + 2π · i / N
x = cx + (v / S) · R · cos(angle)
y = cy + (v / S) · R · sin(angle)
```

A series with values `[v0, v1, ..., v(N-1)]` becomes a `<polygon>` with `points="x0,y0 x1,y1 ..."`.

### Pre-computed reference (N=5, cx=500, cy=240, R=160, S=10, integer-rounded)

| Fraction `f` | i=0 (top) | i=1 | i=2 | i=3 | i=4 |
|---|---|---|---|---|---|
| 0.2 | 500,208 | 530,230 | 519,266 | 481,266 | 470,230 |
| 0.4 | 500,176 | 561,220 | 538,292 | 462,292 | 439,220 |
| 0.6 | 500,144 | 591,211 | 556,317 | 444,317 | 409,211 |
| 0.8 | 500,112 | 622,201 | 575,343 | 425,343 | 378,201 |
| 1.0 | 500,80  | 652,191 | 594,369 | 406,369 | 348,191 |

For an arbitrary value `v` on axis `i`, take the unit offset from the row above for that axis (e.g. axis 1: offset `(152, -49)` from center) and scale by `v/S`. **Drop coords as integers — fractional pixels in SVG render fine, but integers keep the file scannable.**

### Worked example (N=5)

Series `[9, 8, 9, 9, 9]` on a 0–10 scale becomes:

```svg
<polygon points="500,96 622,201 585,356 415,356 363,196"
         fill="rgba(235,108,54,0.18)" stroke="#eb6c36" stroke-width="1.8"/>
```

Each vertex: `center + (v/10) · (outer_i − center)`, rounded to the nearest pixel.

## Series palette

The skill's "1-focal" rule still holds: `accent` is reserved for the focal series, and a small editorial palette (`series-1` through `series-5`, defined in [`style-guide.md`](style-guide.md)) covers the non-focal series. Don't reach for free-form colors.

| Slot | Token | Light | Dark |
|---|---|---|---|
| Focal | `accent` | `#eb6c36` | `#f08a59` |
| 1 | `series-1` (sage) | `#7c8f6f` | `#9caf8f` |
| 2 | `series-2` (dusty-blue) | `#5e7a9b` | `#82a0c0` |
| 3 | `series-3` (mustard) | `#b8915a` | `#d3ad7a` |
| 4 | `series-4` (rust-brown) | `#9c6b50` | `#b88670` |
| 5 | `series-5` (slate) | `#6e6479` | `#8d8298` |

## Anti-patterns

- **More than 5 series** → mush. Split into two charts (e.g. "best by latency" + "best by ops") or switch to a comparison table.
- **Axes on inconsistent native scales** (one 0–100, another 0–1) without normalization. **Always normalize to 0–N first** — radar polygons compare *shapes*, not absolute values.
- **Zero-baseline tricks** — starting the inner ring at v=5 to amplify differences. The grid starts at 0; if differences look small, that's the truthful reading.
- **Dots on every series.** Only the focal carries dots. Adding them to all 4–5 series turns the chart into a bead curtain.
- **Radar with 2 series** — a comparison bar chart or a 2-row table is clearer.
- **Non-quantitative axes.** All axes must be measurable on the same normalized scale. "Speed" + "color" + "year" mixes don't belong on a radar.
- **Mono-font axis labels.** Names go in Geist sans (the global rule). Mono is for technical sublabels only.
- **Rainbow palette.** Even with the new `series-*` tokens, you don't need all 5 in one chart — use only as many as you have non-focal entities.

## Examples

- `assets/example-radar.html` — minimal light. 4 storage backends × 5 workload dimensions, MinIO focal.
- `assets/example-radar-dark.html` — minimal dark, same data.
- `assets/example-radar-full.html` — full editorial: container framing + 4 cards (one per backend) with varied widths + footer.
