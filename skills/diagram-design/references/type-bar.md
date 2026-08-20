# Bar / Column Chart

**Best for:** comparing discrete quantities across categories or time intervals — sprint velocity, monthly revenue, feature adoption, cohort counts. Use when each category has a single numeric value and the comparison between bars is the primary message — or, in the dumbbell variant below, exactly two values whose difference is the message — or, in the histogram variant, the distribution of one continuous variable, where the *shape* is the message.

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
- **Dumbbell:** one row per category, two dots on a single shared horizontal scale joined by a hairline. Use it for a two-state comparison where the *distance* between the ends is the message — before/after, two cohorts, target vs actual. Two series only; a third dot makes the connector meaningless and the figure is a dot plot.
- **Histogram:** one continuous variable cut into equal contiguous bins, bar height = count per bin. Use it when the claim is about a distribution's shape — where the mass sits, how far the tail runs, whether one summary number can stand for the data at all. Full spec below.

### Dumbbell layout

- **Orientation:** horizontal only. Rows stack downward and the value axis runs left → right; a vertical dumbbell forces rotated category labels.
- **Plot area:** left margin 200px for row labels — this replaces the 80px margin above — so `x` 200→960, `y` 40→420 inside `0 0 1000 500`. Row labels right-aligned at x=188, Geist 11px 600 ink (the category-label size this type already uses).
- **Rows:** the 4–8 bar count cap applies. Pitch and origin are fixed per row count so the block stays inside the plot band — a 64px pitch from y=96 overflows y=420 at seven rows:

  | rows | pitch | first row `y` | last row `y` |
  | --- | --- | --- | --- |
  | 4 | 88 | 96 | 360 |
  | 5 | 64 | 96 | 352 |
  | 6 | 64 | 76 | 396 |
  | 7 | 52 | 72 | 384 |
  | 8 | 48 | 68 | 404 |

- **Gridlines:** vertical at each tick, `rgba(45,49,66,0.08)` 0.8px, spanning y 56→408. At the domain floor the axis line replaces the gridline rather than doubling it: `rgba(45,49,66,0.25)` 1px, y 40→420.
- **Tick labels:** centered under each gridline at y=440, Geist Mono 8px muted.
- **Axis title:** the value axis carries the family's axis label — Geist Mono 7px muted, `letter-spacing="0.14em"`, centered at x=580, y=456, below the tick labels and clear of the legend rule. A horizontal axis takes the un-rotated form the scatter x-axis uses, not the `rotate(-90 24 230)` form the column charts apply to their y-axis. The category axis needs no title: the row labels name themselves.
- **Dots:** r=6, positioned by value. Style by *series*: the reference end hollow (paper fill, `muted` stroke 1.5px), the focal end solid `accent` with a 1px `ink` stroke. Both marks therefore have a boundary above 3:1 even though the accent fill is not — see below. Fill weight, not hue, carries the pairing.
- **Accent marks the series, not a focal row.** The solid dot repeats on every row — the one place this variant departs from the one-accent rule above, because the two ends must be told apart in each pair. Do not additionally accent a "most changed" row; the sort order already carries rank.
- **Connector:** `rgba(45,49,66,0.55)` 1px, declared before both dots so the dots cap it. It is not the axis hairline: the connector is what says *these two dots are one row*, so it has to clear 3:1 (0.55 gives 3.19:1; the 0.25 the axis uses gives 1.60:1).
- **Endpoint positions round, they never snap.** `x = 200 + (v − floor) ÷ (ceil − floor) × 760`, with `floor` and `ceil` set by the axis rule below, rounded to the nearest integer pixel — at most 0.5px, below one rendered pixel. Data coordinates are exempt from the 4px grid; snapping them moves the data.
- **Value labels sit outside the pair, placed by geometry rather than by series.** A focal value *below* its reference reverses the dots, so derive `x_left = min(x_ref, x_focal)` and `x_right = max(x_ref, x_focal)`: left label right-anchored at `x_left − 12`, right label left-anchored at `x_right + 12`, both baseline `y + 4`, Geist Mono 8px `muted`, each still carrying its own series' value. Keying the offsets to start/end instead puts both labels *inside* the pair on every decreasing row.
- **Floor exception.** A value sitting on the domain floor lands its label at x=188, right-anchored on baseline `y + 4` — exactly the category label's anchor and baseline, so the two texts overlap. When `x_left − 12 < 200`, centre that label above its dot at baseline `y − 10` instead.
- **Legend:** two keys on the legend row — hollow dot, then solid dot, each with its series name. Circular keys centre at `cy=493`, the centre of the bar legend's 10px key rect at y=488, so both sit on the 497 text baseline. The row order goes in the legend or the source line, right-aligned on the same row.

**Why the dots differ by fill, not hue.** The focal bar pattern above (12% tint + accent stroke) does not transfer to a 6px dot: the 12% tint across a 6px-radius disc contributes roughly 14 square pixels of colour, so the mark reads as its stroke alone and the pair separates by hue only. A solid accent dot against a hollow one separates by shape, survives greyscale and colour-vision deficiency, and leaves hue as redundant encoding.

**Non-text contrast: the boundary carries it, not the fill.** Accent on paper is 2.86:1 skin-wide, under the 3:1 WCAG 1.4.11 asks of a graphical object needed to understand the content — and shape redundancy does not waive that, because the reader still has to see the mark's edge and the line joining the pair. So neither is left to the accent: the solid endpoint takes a 1px `ink` stroke (11.82:1 against paper, 4.13:1 against its own fill) and the connector takes 55% ink on light, 40% on dark (3.19:1 and 3.24:1). The hollow end already cleared it via its `muted` stroke at 6.11:1 light and 7.07:1 dark. `scripts/verify-dumbbell.py` asserts all four, so a later tint change cannot quietly drop one under the line. The hollow/solid shape difference stays as redundant encoding for greyscale and colour-vision deficiency — do not collapse the two dots to a single fill.

**Minimum drawn gap — never clamp it.** Both dots carry `r="6"`; the hollow one paints out to 6.75 because its 1.5px stroke straddles the path, so the marks touch at 12.75px of centre separation and below about 16px the pair reads as one blob — on a 0–100 domain across 760px, a data gap of 2.1 units. Do **not** widen the separation to clear it: moving a dot off its scaled position breaks the shared-scale rule below. Keep the true positions and shrink both marks (r=4 touches at 8.75px), or print the two values and mark the row as too close to resolve.

### Dumbbell element pattern

```svg
<!-- One row. Connector first so the dots cap it; labels outside the pair. -->
<line x1="458" y1="96" x2="740" y2="96" stroke="rgba(45,49,66,0.55)" stroke-width="1"/>
<circle cx="458" cy="96" r="6" fill="#f5f5f5" stroke="#4f5d75" stroke-width="1.5"/>
<circle cx="740" cy="96" r="6" fill="#eb6c36" stroke="#2d3142" stroke-width="1"/>
<text x="446" y="100" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="end">34</text>
<text x="752" y="100" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace">71</text>
<text x="188" y="100" fill="#2d3142" font-size="11" font-weight="600" font-family="'Geist', sans-serif" text-anchor="end">Platform</text>
```

Values 34 and 71 on a 0–100 domain compute to 458.4 and 739.6, rounded to 458 and 740. Had this row fallen instead, the accent dot would sit on the left; the two anchors stay tied to left and right, and each label carries its own series' value.

**Dark theme.** Dots and labels swap as expected — hollow fill `#2d3142` with `#bfc0c0` stroke, solid `#f08a59` with an `#f5f5f5` stroke, labels `#bfc0c0`. **The hairlines must invert too:** gridlines `rgba(245,245,245,0.08)`, axis `rgba(245,245,245,0.20)`, connector `rgba(245,245,245,0.40)` — the connector again heavier than the axis, for the same 3:1 reason. `rgba(45,49,66,…)` *is* the dark paper colour at every alpha value, so a connector, gridline, or axis carried over from light composites to exactly 1.000:1 — the gap encoding and the scale both vanish.

### Dumbbell honesty rules

- **Never truncate the value axis.** `floor` and `ceil` follow the data's range, never its observed extremes — taking `min` and `max` as the bounds *is* the truncation. With `lo` and `hi` the smallest and largest values, the four cases are exhaustive: `lo >= 0` anchors `floor = 0` and rounds `ceil` up past `hi`; `hi <= 0` anchors `ceil = 0` and rounds `floor` down past `lo`; `lo < 0 < hi` brackets both sides, and zero then falls inside the plot — give it a line at its scaled position in the axis-line weight, since it is what every gap is read against. The fourth case is the one a sign-based rule drops: **when every value is zero**, `lo == hi == 0` would make `ceil - floor` zero and the position formula divide by zero, so take a finite fallback span (`floor = 0`, `ceil = 1` in the data's unit) and let every dot sit on the floor, which is the truth. Data that merely *touches* zero is covered by the first two cases, not a special one. `scripts/verify-dumbbell.py` implements this and proves finite coordinates for all four. The plot width is fixed, so narrowing the domain raises px-per-unit and draws every gap wider: across the same 760px, an 8-point gap is 61px on a 0–100 axis and 152px on a 40–80 axis. Ratios *between* rows survive the zoom — what inflates is each gap's size against the frame, which is how a reader judges whether a gap is large. The gap is the entire claim, which makes this the most common way a dumbbell lies.
- **Both dots share one scale and one unit.** Label both endpoints with their real values. Labelling only the focal end asks the reader to take the geometry on trust.
- **The connector is a gap, not a trajectory.** It encodes the distance between two values and nothing about what lies between them — no intermediate points, no rate, no guarantee the change was monotonic. Do not narrate it as movement.
- **State the row order** in the legend or source line: by one endpoint, by signed change, by absolute change, or by an order the subject supplies (chronological, geographic, ordinal). "By gap" alone is ambiguous — say signed or absolute. What is not allowed is an unstated order, which reads as arbitrary.
- **A row missing an endpoint is disclosed, never imputed and never silently dropped.** Removing incomplete categories without saying so changes the population being compared. Either draw the known end and name the missing value, or drop the row *and* record which rows went and why — a lone dot is otherwise indistinguishable from two coincident dots, which is to say from a genuine zero gap.

Two of these rules live in a formula rather than a drawing, so they are executable: `scripts/verify-dumbbell.py` resolves the domain over every sign case and asserts finite coordinates and 3:1 marks, and `scripts/test-verify-dumbbell.py` exercises both polarities — including all-zero and zero-touching data, and the sub-3:1 treatments this replaced. The checker reads the tokens out of this file, so prose and thresholds cannot drift apart. A shipped dumbbell example would additionally owe a check of drawn positions against the values printed at them.

### Histogram

**Best for:** the distribution of one continuous variable — response times, order values, session lengths, sensor readings. The reading is the *shape*: where the mass sits (mode), how far the tail runs (skew), and whether the mean a report would quote actually describes a typical value. It answers the question the SKILL.md router had no row for: scatter needs two variables, and the parent chart needs categories.

Not for: discrete categories (the parent chart — its gaps are the point there); two variables (**scatter plot**); change over time (**line chart**); comparing two distributions (small multiples of this figure, never two interleaved histograms — interleaving breaks the contiguity that makes the type readable); or fewer than ~30 underlying values, where the sentence "n=12, ranging 80–410ms" says more than any binning of 12 points can. Note the boundary with the scatter reference's overplotting advice ("more → bin into a density contour"): that is binning applied to *two* variables to rescue a relationship plot. Binning one variable is not a rescue — it is this figure, and it answers a different question (shape, not relationship).

#### Layout conventions

- **Same frame as the parent chart:** `0 0 1000 500` viewBox, plot `x` 80 → 960, baseline `y` 420, top `y` 40, rotated count-axis caption at `x=24`, legend rhythm at `y=462/478/488`. A reader of bar, line, or treemap finds everything where they expect it.
- **Bins: 6–12, equal width, contiguous.** Adjacent bars share an edge — gap exactly 0. The missing gap is the entire visual grammar: contiguous bars say "one continuous axis, intervals", gapped bars say "separate categories". At 10 bins each bar is 88px across the 880px plot; below 6 bins the shape disappears, above 12 the counts get too thin to label.
- **6–12 is deliberately more than the parent chart's 4–8 cap.** That cap exists because categorical bars are read one at a time — each wants a name, a value, and a comparison against every other. Histogram bars are not read individually; the *silhouette* is read, and a shape needs more segments than a comparison needs bars. What sets the ceiling here is the count labels thinning out, not the bar count. The floor is higher too: 4 bins cannot show a tail.
- **Paint every paper mask before any bar body.** The parent chart interleaves mask and body per bar, which is safe with gaps. With shared edges it is not: a neighbour's opaque mask painted *after* this bar's body erases the outer half of the shared 1px stroke, thinning the one boundary this variant exists to keep. All masks first, then all bodies.
- **Label edges, not centres.** X-axis tick numerals sit at the bin *boundaries* (Geist Mono 8px muted, centred on the edge), because the numbers name interval boundaries, not category names. There are `bins + 1` of them. The parent chart's 11px category labels have no equivalent here.
- **Count axis starts at 0, always.** The parent chart forbids truncation as an anti-pattern; here it is structural — a histogram reads mass by area, and a truncated count axis subtracts the same lie from every bin. Print the `0` tick.
- **Count labels** above each bar, Geist Mono 8px — muted on ordinary bins, accent 600 on the focal bin. Bars near zero height still get their number; the label is what separates "3" from "none".
- **Focal bin: 1 max**, in accent fill/stroke, same treatment as the parent's focal bar. The natural focal is the modal bin or the bin a threshold cuts through — a bin chosen because it flatters is an accent spent on nothing.
- **One optional reference marker:** a vertical dashed line (1px, dasharray `4 3`, ink at 55% on light / 40% on dark — the same weights the dumbbell connector uses, for the same 3:1 reason) at a stated statistic, labelled in Geist Mono 8px 600 ink. One marker; a second (mean *and* median *and* p95) turns the figure into a annotated argument the cards should be making instead.
- **4px grid** applies to the designed constants — plot edges, gridlines, legend rhythm. Bar heights, the marker's x, and the bin edges are data-scaled and exempt for the dumbbell's reason: snapping them moves the data. Bin edges land where the range division puts them — at 10 bins over 880px they happen to be 4px multiples, at 6 or 12 they are not, and rounding an edge to the grid would silently move a bin boundary.
- **Dark theme:** background and masks `#2d3142`, bars `rgba(191,192,192,0.15)` stroked `#bfc0c0`, focal `rgba(240,138,89,0.14)` stroked `#f08a59`, hairlines inverted to `rgba(245,245,245,…)` — `rgba(45,49,66,…)` *is* the dark paper at every alpha, so any hairline carried over from light composites to 1.000:1 and vanishes.

#### Histogram honesty rules

Every one of these renders perfectly when broken, which is why `scripts/verify-histogram.py` exists and gates all of them.

- **Equal bin widths, no exceptions.** Height is proportional to count only while every bin spans the same interval; widen one bin and its bar rises without a single observation moving. This is the histogram's signature lie — the density-normalized unequal-bin variant is a real statistical tool, but its heights stop being counts, and a figure whose y-axis says "requests" while its bars encode "requests per unit" is exactly the ambiguity this skill exists to remove. Equal bins or a different figure.
- **Bins tile the range.** Bin k's end is bin k+1's start, in the declared values and in the pixels. An omitted interior bin doesn't read as "empty" — it reads as a narrower distribution than the data has. An empty bin ships as height 0 with its count label.
- **The baseline is zero and the count scale is linear.** One px-per-count factor for every bin and every tick. A log count axis makes the shape unreadable as mass; if the tail needs a log axis, the figure wants a table or a percentile list instead.
- **`n` is printed and equals the sum of the bins.** A histogram whose bins sum to less than its stated n has silently dropped data — usually the outliers, which are usually the story. Values beyond the last edge get a final bin or an explicit disclosure, never a quiet trim.
- **A stated statistic must be computed from what is shown.** The marker's value is checked two ways: its x must sit where the scale puts its printed value, and a marker claiming to be the mean must lie within half a bin of the mean of the binned data — a "mean" placed by eye where it looks balanced is the annotated version of the jitter the slopegraph gate exists for.
- **No smoothing.** A density curve over the bars answers a different question with a bandwidth parameter that is a second lie surface. If the shape needs smoothing to be visible, the binning is wrong or the data is too thin for the figure.
- **Round once, then draw from the rounded number** — the declared count, the printed label, and the drawn height are three statements of one number, not three chances to disagree.

#### Declaring the values

Same contract as the slopegraph: **every visible string that carries meaning is bound to an attribute stating the same thing**, and the geometry is verified from the declarations, never from the rendered text.

```svg
<!-- A bin: the stroked rect declares its interval and count; the paper mask
     beneath it stays unbound. The count label re-states the count and names
     its bin, so the two can be cross-checked. -->
<rect x="256" y="49.5" width="88" height="370.5" fill="#f5f5f5"/>
<rect data-bin-start="200" data-bin-end="300" data-count="156" x="256" y="49.5" width="88" height="370.5" fill="rgba(235,108,54,0.12)" stroke="#eb6c36" stroke-width="1"/>
<text data-bin-start="200" data-role="count" x="300" y="41.5" fill="#eb6c36" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle" font-weight="600">156</text>

<!-- Edge ticks and count ticks bind the numeral they print -->
<text data-edge="300" x="344" y="436" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle">300</text>
<text data-count-tick="0" x="72" y="424" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="end">0</text>

<!-- The marker declares its statistic and value; n declares the total -->
<line data-marker="mean" data-value="319" x1="360.72" y1="56" x2="360.72" y2="420" stroke="rgba(45,49,66,0.55)" stroke-width="1" stroke-dasharray="4 3"/>
<text data-marker-label="mean" data-value="319" x="366.72" y="50" fill="#2d3142" font-size="8" font-weight="600" font-family="'Geist Mono', monospace">MEAN 319ms</text>
<text data-role="n" data-value="550" x="960" y="497" fill="#4f5d75" font-size="8.5" font-family="'Geist Mono', monospace" text-anchor="end">n = 550</text>
```

**No `transform` on any verified geometry or bound label, including ancestors** — the checker reads raw attributes, so a transform moves the rendered mark away from the number that was verified. Bake offsets into coordinates. The rotated axis caption is fine; it is neither verified geometry nor a bound label.

`scripts/verify-histogram.py --all` gates the shipped examples: equal declared and drawn widths, tiled edges, a shared baseline that the `0` tick sits on, one linear count scale across bars *and* ticks, every printed numeral matching its binding, n equal to the sum, and the marker at its declared value — within half a bin of the binned mean when it claims to be one. `scripts/test-verify-histogram.py` holds the checker itself to both polarities.

#### Anti-patterns

- Unequal bin widths, or a gap between adjacent bars — the first lies, the second claims the axis is categorical.
- A count axis that starts above zero, or a log count axis.
- Bin counts that don't sum to the printed n.
- A smoothed density curve over the bars.
- Two interleaved histograms — small multiples, one distribution each.
- More than one reference marker, or a marker whose statistic is not stated.
- Rotated edge labels; if the numerals collide, print every second edge.

## Examples

- `assets/example-bar.html` — minimal light
- `assets/example-bar-dark.html` — minimal dark
- `assets/example-bar-full.html` — full editorial
- `assets/example-histogram.html` — histogram variant, minimal light
- `assets/example-histogram-dark.html` — histogram variant, minimal dark
- `assets/example-histogram-full.html` — histogram variant, full editorial
