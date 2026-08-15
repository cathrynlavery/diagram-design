# Polar / Radial Wheel

**Best for:** circular layouts where the angle is the category and the radius is the magnitude. Skill wheels and competency maps, DISC/personality profiles, cyclical or seasonal data (months, quarters, hours around a day), and "distance from center" rankings. Where a radar compares *shapes* across entities, a polar wheel reads *one category set* arranged around a hub — each sector is its own axis.

## Layout conventions

- **N sectors (2–8).** Equally spaced; sector `i` (0-indexed) sits at mid-angle `-90° + 360°·(i + 0.5) / N`, so sector 0 is centered at the top and sectors run clockwise. **Above 8 → split into two wheels or use a bar chart.**
- **Four concentric reference rings** at `0.25 / 0.5 / 0.75 / 1.0` of the outer radius `R`. Inner three at `rule` 0.10 opacity, outer ring at `rule-solid` 0.20 (a hint stronger to anchor the wheel).
- **Radial spokes** at each sector boundary (`-90° + 360°·k / N`, `k = 0..N`), center to outer ring. `rule-solid` 0.20 opacity. **No arrowheads.**
- **Sector bands** are the bars: a wedge from a common hub radius (start bars at `0.25·R` so the 25% ring reads as the baseline) out to the value radius `(value / max) · R`. Path: inner arc → outer arc, `sweep=1` going clockwise, `sweep=0` returning. Fill the series color at `0.18` opacity light / `0.22` dark, stroke the full series color `1.2` (`1.4` on the focal sector).
- **One focal sector, accent.** The focal rule holds — 1–2 accent elements total. Everything else is `series-1`…`series-5` or muted.
- **Value labels** at the bar tip (`r_value + 16` along the mid-angle): Geist Mono 8px, `muted`, horizontal, with a paper-fill mask rect behind each. Never rotate these.
- **Free points at (angle, radius):** one `<circle>` per member placed inside a sector. Paper mask circle under the dot so gridlines don't bleed through. Non-focal dots `r=5`, `muted` fill at 0.20 + `muted` stroke; a focal dot `r=6`, solid `accent`. **Dots in a few sectors, not all** — they're people or readings, not decoration.
- **Tangent-rotated rim labels** at `R + 28` along each mid-angle. Geist sans 11px weight 600, `text-anchor="middle"`. Rotation rule (keeps text upright on the bottom half):
  - top half (`sin θ ≤ 0`): `rotate(θ + 90°)`
  - bottom half (`sin θ > 0`): `rotate(θ − 90°)`
  - Result: top and bottom labels read horizontally and upright; right-side labels read down the tangent; left-side labels read up it.
- **Legend:** horizontal strip at the bottom (per the global rule). Sector swatches are 16×8 rectangles (stroke + fill like the bands, not circles), ~128px apart. A second row covers the dots: 3px circle + "team member" / accent circle + the focal meaning.
- **Drawing order:** dots-pattern bg → reference rings → spokes → non-focal sector bands → focal sector band → value labels (masked) → member dots → rim labels → legend.

## Math

For sector mid-angle `θ` (degrees, 12 o'clock = `-90°`, clockwise), value `v` on scale `max`, center `(cx, cy)`, outer radius `R`, hub radius `h = 0.25·R`:

```
θ = -90° + 360° · (i + 0.5) / N          # mid-angle of sector i
x = cx + r · cos(θ)                       # any point at (θ, r)
y = cy + r · sin(θ)
r_value = (v / max) · R                   # band tip radius
```

The bands *start* at the hub radius `h` (the 25% ring reads as the baseline) but the tip scales from the center: `r_value = (v / max) · R`. All bands share the hub, so length comparisons stay honest. Sector band path (angles in degrees, clockwise from `θ − 180/N` to `θ + 180/N`):

```svg
<!-- band from hub radius h to value radius rv, angles a1 → a2 -->
<path d="M P(a1,h) A h h 0 0 1 P(a2,h) L P(a2,rv) A rv rv 0 0 0 P(a1,rv) Z"
      fill="SERIES@0.18" stroke="SERIES" stroke-width="1.2"/>
```

Label rotation at mid-angle `θ`:

```
rotation = θ + 90°            if sin θ ≤ 0   (top half, tangent)
rotation = θ − 90°            if sin θ > 0    (bottom half, upright)
```

### Pre-computed reference (N=6, cx=500, cy=276, R=192, h=48, max=100)

| Sector | Mid-angle `θ` | Rim label pos (r=220) | Rim rotation |
|---|---|---|---|
| 0 | −90° | 500, 56 | 0° |
| 1 | −30° | 691, 166 | 60° |
| 2 | 30° | 691, 386 | −60° |
| 3 | 90° | 500, 496 | 0° |
| 4 | 150° | 309, 386 | 60° |
| 5 | 210° | 309, 166 | 300° |

For a band tip at value `v`, `r_value = (v / 100) · 192` (e.g. `v=88` → `r=169`), then place the point at `(cx + r_value·cos θ, cy + r_value·sin θ)`. **Drop coordinates as integers** — fractional pixels render fine, but integers keep the file scannable.

## Complexity budget

| Limit | Rule |
|---|---|
| Max sectors | 8 |
| Max member points | 12 |
| Max accent elements | 2 (focal sector + at most one focal dot) |

If you exceed, split into two wheels (overview + detail) or switch to a bar chart.

## Anti-patterns

- **More than 8 sectors** → the rim labels crowd and the wheel turns into a mandala. Split or use bars.
- **Accent on more than one sector.** One coral wedge; the rest of the wheel stays in the comparison palette.
- **Every sector full of dots** → bead curtain. Dots in 2–4 sectors at most; they're people or readings.
- **Bars on different baselines.** All bands must start at the shared hub radius — staggered starts (each bar starting at its own inner radius) make length comparisons dishonest.
- **Unflipped bottom labels.** A rim label on the bottom half that isn't rotated +180° from the tangent reads upside down. Apply the `sin θ > 0` flip.
- **Mono for category names.** Rim labels are Geist sans; mono is for the value labels only.
- **Rainbow palette.** Use only as many `series-*` colors as you have non-focal sectors, and don't reach for free-form colors.
- **A wheel for 2 categories** — two wedges is a pie chart argument; use a bar chart instead.

## Examples

- `assets/example-polar-wheel.html` — minimal light. Platform-team skill wheel, 6 sectors, Backend focal.
- `assets/example-polar-wheel-dark.html` — minimal dark, same data.
- `assets/example-polar-wheel-full.html` — full editorial: container framing + 3 cards (varied widths) + footer.
