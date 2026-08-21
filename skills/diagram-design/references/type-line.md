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

## Variants

- **Slopegraph:** exactly two states, several series, read as slope and rank change. Full spec below.
- **Ridgeline:** one distribution per series, stacked with deliberate overlap on one shared amplitude. Full spec below.

### Slopegraph

**Best for:** change between exactly **two** comparable states across several series — two years, before and after, two cohorts, two scenarios. The reading is threefold and no other type gives all three at once: direction (up or down), steepness (how fast), and **crossings** (who overtook whom). Tufte's original (*The Visual Display of Quantitative Information*, 1983) is a table whose rows have been given an angle — every number is still printed, which is why both endpoints keep their labels here.

Not for: three or more states (that is the **line chart** above, or a bump chart); a single series (write the sentence instead); ranking at one moment with no change (use a **bar chart**); or two variables measured in different units (use a **scatter plot** — a slope between unlike units means nothing).

#### Layout conventions

- **Two vertical axis rules**, `y` 40 → 420 inside a `0 0 1000 500` viewBox, at `x` 320 and `x` 680. The plot sits inside `x` 40 → 956 with the rotated value-axis caption at `x=24`, as in the parent chart, and the legend keeps the house rhythm (rule at `y=462`, `LEGEND` at `478`, key swatches at `492` with their text at `496`), so a reader of bar, line or treemap finds it where they expect.
- **Keep the run narrower than the plot is tall.** The 360px run against a 380px height puts the steepest shipped slope at 35° and the flattest at 4° — the spread you need before "halved" and "barely moved" look like different claims. Widening the run flattens every slope toward horizontal and throws away the comparison the type exists to make; the leftover width belongs to the label gutters, which need it.
- **Label gutters:** on the left, names right-aligned ending at `x=272` and values right-aligned ending at `x=304`; mirrored on the right from `x=696` (values) and `x=728` (names). Size the gutter to the longest name — a name that collides with the axis is the one thing here you cannot fix by moving a coordinate.
- **State captions** in Geist Mono 9px, centred under each axis at `y=440`, tracked `0.14em`.
- **Series count:** 4–10 — deliberately more than the parent chart's cap of 5. That cap exists because eight-vertex polylines tangle in mid-plot; a slopegraph has no mid-plot, so what sets the ceiling here is endpoint labels colliding, not the lines. Below 4 a sentence or a pair of bars says it better.
- **No gridlines.** Every endpoint prints its own value, so a gridline carries nothing the figure has not already said; the two axis rules *are* the scale. This is a real departure from the parent line chart, where the gridlines do the reading.
- **Domain:** pick round bounds that contain the data and state them in the source line. The shipped example runs 100–550ms over `y` 420 → 40, i.e. 0.84px per millisecond. The parent chart's include-zero rule does not bind here: a slope is unchanged by moving the origin, provided *both* axes move together. What a tight domain does do is magnify every slope equally, so state the bounds and let the reader calibrate.
- **Legend keys are a 24px line plus its dot**, not the 16×8 rect the parent section specifies — which is also what `example-line.html` actually ships, the parent prose being stale on this point. A slopegraph key has to show stroke weight, because weight is what marks the focal series.
- **Dots at both endpoints** — `r=3` non-focal, `r=4` focal. Also a departure: the line chart puts dots on the focal series only, because it has eight vertices per series and dots everywhere would be mush. A slopegraph has exactly two per series and both are where a value is read.
- **4px grid** applies to the designed constants — axis positions, gutter edges, state-caption baselines. Endpoint `y` values are data-scaled and exempt; snapping them would move the data. Two inherited constants are also off-grid and stay that way: the legend rule at `y=462` and the `LEGEND`/source baseline at `478`, which every chart type in `assets/` shares. Matching the house rhythm beats matching the grid here — moving them 4px would misalign this variant against bar, line, scatter and treemap to satisfy a rule none of them satisfies either.

#### Colour

- **One accent, and an `ink` opacity ramp for everything else** — not the series palette. In a line chart hue is the only way to follow a series across eight x-positions, so `series-1`…`series-4` earn their place. Here every series is named at both ends, so hue would be a second encoding of something the labels already carry, and it would spend the one-accent rule for nothing.
- **The ramp runs 0.80 → 0.62**, ordered by the left-hand value. The hard floor is **0.53** — that is where an `ink` stroke crosses 3:1 against light paper (0.53 measures 3.03:1, 0.52 measures 2.95:1), and every line in this figure is data, not decoration. The shipped ramp bottoms out at 0.62 (3.84:1) rather than hugging the floor, because a ramp whose lightest member is only just legible has no room left to add a series.
- **Note what the ramp does not buy you.** It separates the ends of the range, not adjacent members — 0.80 and 0.74 are not distinguishable at 1.2px, as the shipped example shows. It is there to help trace one line through a crossing. It must never be the only way to tell two series apart; that is the labels' job.
- **The accent marks the editorially focal series, not the best or the biggest.** In the shipped example it marks the one service that got *worse*.
- **Focus is carried by stroke weight, not tone** — 2.4px focal against 1.2px. Check the token you actually ship: `accent` measures **2.86:1 on light paper** and 5.21:1 on dark, so on light paper the focal line has *less* contrast than the ink ramp it is meant to dominate, and weight is the only cue that survives both skins and greyscale.
- **Be honest about what that leaves.** 2.86:1 is below WCAG 1.4.11's 3:1 floor for a graphical object, and a heavier stroke does not raise a contrast ratio — it only makes the mark easier to find. The focal line clears the bar on redundancy rather than on contrast: its position and its two endpoint labels (`ink` at 11.8:1, `muted` at 6.1:1) carry the data, and its accent adds only *which series is focal*, which the legend states in words and the stroke weight repeats. Nothing here rests on the accent alone. This is a property of the skin's accent token on light paper, not of this variant — the focal bar, the focal line and the focal treemap cell inherit it too, so fixing it properly means changing `accent` in style-guide.md.
- **Labels stay `ink` (names) and `muted` (values) on every series, including the focal one.** Accent text at 9–11px misses AA on light paper at that same 2.86:1. A focal value label in accent is the most common way to make a slopegraph fail contrast while looking deliberate.
- **Legend wording must be skin-neutral: "strongest tone", never "darkest".** The ramp is ink-at-opacity, so the top of it is the darkest line on light paper and the *lightest* on dark. A legend that says "darker is higher" ships false in one of the two variants — and it renders perfectly in both, so only reading the dark file catches it.

#### Honest-data rule

**Both axes must carry the same scale and the same units.** That is the entire claim of the type: if the scales differ, the angle of every line is fiction. `scripts/verify-slopegraph.py` gates it.

- **The two axes must never differ from each other** — not in scale, not in origin, not in transform. A shared *origin* matters as much as a shared scale: shifting one axis tilts every slope by the same amount, so the series still rank correctly against each other while every rate is wrong. That is the harder version to spot by eye, which is why the checker tests slope and origin separately.
- **A domain tighter than zero is fine; an undisclosed one is not.** Both axes sharing a 100–550 window is legitimate, because moving the origin leaves every slope unchanged when both axes move together — this is exactly where a slopegraph differs from a bar chart, whose truncated baseline distorts the ratio between bars. What a tight window does do is magnify all slopes equally, so the bounds go in the source line and the reader calibrates. Log-scaling is a different matter and stays out: it makes the angle mean nothing.
- **Label both endpoints with actual values.** A slope with no magnitudes is a mood.
- **Round once, then draw from the rounded number**, so the printed label, the declared metadata and the drawn `y` are three statements of one number rather than three chances to disagree.
- **If a series is missing an endpoint, drop it and say so.** Never interpolate to complete a line.
- **Crowded endpoint labels are data.** When two series sit a few tenths apart their labels crowd *because the values are close*. Moving a point to open up space converts a legibility problem into a false statement — and it is invisible afterwards, because the label you moved it for now sits comfortably beside the wrong position. This is the specific defect the gate exists for.
- **Two series that coincide at both endpoints cannot be separated at all.** Merge them into one labelled line, or drop one and name the omission in the source line. What you must not do is nudge them apart, which is the same defect as above wearing a better excuse.
- **The straight line is a connector, not a trajectory.** Two endpoints say nothing about the path between them: the underlying series may have dipped, spiked, or crossed three times. So never read an intermediate value off a slope, and never annotate a crossing with a date. In the shipped example one service regresses while four improve, so its line crosses three others; none of the three crossings is annotated, and the card beside the figure says why.

#### Declaring the values

**Every visible string that carries meaning is bound to an attribute stating the same thing.** That is the whole contract, and it exists because each unbound string is a place the figure can be made to lie while every geometric check stays green.

```svg
<!-- State captions: data-axis names the axis, data-state binds the text -->
<text data-axis="from" data-state="BEFORE" x="320" y="440" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" letter-spacing="0.14em" text-anchor="middle">BEFORE</text>
<text data-axis="to" data-state="AFTER" x="680" y="440" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" letter-spacing="0.14em" text-anchor="middle">AFTER</text>

<!-- A series: the line declares its two values, and each of its four labels
     declares which series and which end it belongs to -->
<line data-series="Recommender" data-from="238" data-to="431"
      x1="320" y1="303.5" x2="680" y2="140.5" stroke="#eb6c36" stroke-width="2.4"/>
<circle cx="320" cy="303.5" r="4" fill="#eb6c36"/>
<circle cx="680" cy="140.5" r="4" fill="#eb6c36"/>
<text data-series="Recommender" data-end="from" data-role="name" x="272" y="307" fill="#2d3142" font-size="11" font-weight="600" font-family="'Geist', sans-serif" text-anchor="end">Recommender</text>
<text data-series="Recommender" data-end="from" x="304" y="307" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" text-anchor="end">238</text>
<text data-series="Recommender" data-end="to" x="696" y="144" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace">431</text>
<text data-series="Recommender" data-end="to" data-role="name" x="728" y="144" fill="#2d3142" font-size="11" font-weight="600" font-family="'Geist', sans-serif">Recommender</text>
```

Non-focal series: `stroke="rgba(45,49,66,0.68)"` at `stroke-width="1.2"`, dots `r=3`, names at `font-weight="500"`.

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-from` / `data-to` on the line | The checker would have to read the labels, and a series whose label went missing would drop silently out of the verified set — the exact hole that let a treemap cell ship 50% oversized. |
| `data-end` on a value label | A printed number could not be cross-checked against the value it claims to state. |
| `data-role="name"` on a name label | Two series names could be exchanged between rows, renaming both lines, with every number still correct in isolation. |
| `data-axis` on a state caption | The captions could be swapped, reversing the direction every slope is read in. |
| `data-state` on a state caption | Swapping just the two visible strings leaves both captions in place and reverses the figure anyway. |

`scripts/verify-slopegraph.py` requires all of them, cross-checks each visible string against its binding, and reports any label drawn nearer another series' endpoint than its own — a label on the wrong row renames the line.

**No `transform` on any of it.** The checker reads raw `x`/`y` attributes, so a `transform` on a series line, on a bound label, on an ancestor `<g>`, or in a CSS rule moves the rendered mark away from the number that was verified — `transform="translate(0 80)"` on one line slid its endpoint 80px past every green check. Transforms are rejected rather than resolved: a partial implementation of the SVG transform stack looks like coverage without being it. Bake the offset into the coordinates. The rotated value-axis caption is fine — it is neither verified geometry nor a bound label.

**Print one complete number per value label.** A unit suffix is fine (`208ms`); a thousands separator that changes the value is not, and neither is a second number in the same label. Reading only the first numeric fragment let the label `512,000` agree with metadata that said `512`.

#### Anti-patterns

- Different scales, different units, or different origins on the two axes — the type's one unforgivable error.
- A value axis whose two halves disagree, or a tight domain the source line never states.
- Moving an endpoint to make room for its label.
- More than 10 series (labels collide) or fewer than 4 (a sentence is shorter).
- Three or more state columns — that is the parent line chart, or a bump chart, not this.
- One hue per series instead of the ink ramp plus a single accent.
- A value label in `accent`, or any text in `soft` (3.48:1 on paper).
- Gridlines, or a value axis that repeats numbers the endpoints already print.
- Annotating the crossing with a date, or reading any intermediate value off a slope.
- A `transform` on a series line, a bound label, an ancestor group, or in CSS — it moves the mark away from the checked coordinate.
- An unbound visible string: a name, a value or a state caption with no attribute stating the same thing.
- Curving the connector. There is nothing between the two points to curve through.

### Ridgeline

**Best for:** one **distribution** per series, stacked at a fixed pitch with deliberate overlap, when the shape of each distribution is the story and the series are directly comparable — request latency per service, build duration per pipeline, session length per cohort. The line chart above plots one value per x; a ridgeline plots a whole distribution per row, and the reading is the silhouette: where the mass sits, how tight it is, whether there is a second peak. A p50/p99 pair cannot show a bimodal service, and a box plot flattens it to a rectangle.

Not for: a single distribution (that is a histogram — one ridge is a ridgeline with the comparison removed); series measured in different units or on different x-ranges, which cannot share the one x-scale the type requires; time series, where each row is one value per moment rather than one distribution; or distributions so similar that the ridges are five copies of one shape, which a table of percentiles says shorter.

#### Layout conventions

- **One baseline per ridge at a fixed pitch**, inside the `0 0 1000 500` viewBox the other Line variants use. The shipped example runs five baselines at `y` 152/208/264/320/376, a 56px pitch.
- **The x-run is the slopegraph's**, `x` 320 → 680, sampled at 13 bins 30px apart. The gutters are symmetric about it: names right-aligned ending at `x=304`, ranges starting at `x=696`, both 16px clear of the plot.
- **Name left of the baseline, range right of it**, each on its ridge's own row (`y = baseline + 3.5`). The range is the span of the ridge's nonzero mass in x-axis units, which is the number a silhouette cannot give you.
- **Bin ticks** in Geist Mono 9px at `y=400`, centred on bin positions and tracked `0.14em`, with the x-axis caption at `y=424`. The rotated amplitude caption sits at `x=24`, as in the parent chart.
- **Ridge count 3–12, bins 8–40.** Below three ridges there is no family of shapes to compare and two distributions are a pair of small multiples; past twelve the stack is taller than a reader can hold one silhouette in mind across. Below eight bins the outline is a histogram wearing a curve's clothes; past forty the bins are narrower than the noise in them.
- **Straight segments between bins, closed with `Z`.** Not splines: the source line states the drawing is unsmoothed, and a curve through binned counts puts extrema between bins that the sample never measured. The draft this variant came from permits Catmull-Rom with vertices on true values; the shipped grammar does not use it, because unsmoothed bins need no footnote about what the curve is allowed to invent.
- **No gridlines.** The baselines are the rules, and every ridge prints its own range.

#### Colour

The slopegraph's colour section holds here unchanged, with one addition for the fill. One accent on the editorially focal ridge (stroke `accent`, fill the accent at `0.16`), an `ink` opacity ramp for the rest (`0.80 → 0.62`, floor `0.53`) ordered top row to bottom, and focus carried by stroke weight — 2.4px against 1.2px — rather than tone. Labels stay `ink` (names) and `muted` (ranges) on every ridge including the focal one.

- **Fill `ink` at `0.12` on every non-focal ridge**, low enough that two overlapping ridges read as depth rather than as a third tone. This is the one place the type needs a fill at all: the outline alone does not say which side of the curve is mass.
- **Legend wording stays skin-neutral** — "strongest tone", never "darkest". The ramp is ink-at-opacity, so its top is the darkest line on light paper and the lightest on dark, and a legend that says "darker" ships false in one of the two skins while rendering perfectly in both.
- **The accent marks the ridge the story is about, not the worst performer.** In the shipped example it marks the service whose *shape* is unusual, not the slowest one.

#### Honest-data rule

**One amplitude on every ridge, stated in the source line.** That is the entire claim of the type: the ridges are stacked so their silhouettes can be compared, and per-ridge normalisation destroys exactly that while rendering beautifully — a rare, flat distribution given its own scale wears the same shape as a tight one. `scripts/verify-ridgeline.py` derives the figure's single amplitude and holds every vertex of every ridge to it.

- **The baseline never lies.** Each ridge declares the row it rises from, and that row must sit on the stack's fixed pitch with its rule drawn across the full bin run. A baseline nudged up to give one ridge headroom is the same falsification as a private amplitude, told with different arithmetic — and it is the harder one to see, because the silhouette above it is untouched.
- **Every ridge shares one x-scale.** A peak at one x means one latency on every row, or the column comparison the type exists for is fiction.
- **State the overlap, and keep it overlap.** Ridges are meant to intrude on the row above — that is how the stack reads as depth. A peak that reaches the row *two* above is occluded by the peaks it passes, and the fix is more pitch, never a smaller amplitude on one ridge. The checker enforces the ceiling; the source line states the amplitude so the reader can convert a height back into a number.
- **A ridge starts and ends on its own baseline.** The first and last bins are zero, so the outline closes along the baseline. A distribution clipped mid-mass draws a cliff, and a cliff reads as data.
- **No smoothing beyond what the footnote states.** The shipped grammar smooths nothing at all. If a figure ever does smooth, the footnote names the method and the vertices stay on true values — a spline that invents a second peak is indistinguishable, on the page, from a service that has one.
- **Height is share, not volume.** Each ridge is normalised to its own series' count before the shared amplitude is applied, so the tallest ridge is the most concentrated, not the busiest. Say so in the source line; a reader who assumes height is traffic reads the figure exactly backwards.

#### Declaring the values

The binding contract is the slopegraph's, applied to areas: the outline declares its bins and its baseline, and every visible string is bound to what it describes.

```svg
<line data-ridge="checkout-api" data-role="baseline" x1="320" y1="320" x2="680" y2="320" stroke="rgba(45,49,66,0.25)" stroke-width="1"/>
<path data-ridge="checkout-api" data-baseline="320" data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0" d="M320,320 L350,317.6 L380,305.6 L410,279.2 L440,269.6 L470,286.4 L500,300.8 L530,305.6 L560,303.2 L590,298.4 L620,303.2 L650,310.4 L680,320 Z" fill="rgba(235,108,54,0.16)" stroke="#eb6c36" stroke-width="2.4" stroke-linejoin="round"/>
<text data-ridge="checkout-api" data-role="name" x="304" y="323.5" fill="#2d3142" font-size="11" font-weight="600" font-family="'Geist', sans-serif" text-anchor="end">checkout-api</text>
<text data-ridge="checkout-api" data-role="range" x="696" y="323.5" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace">40–440 ms</text>
<text data-tick="2" data-bin="240" x="500" y="400" fill="#4f5d75" font-size="9" font-family="'Geist Mono', monospace" letter-spacing="0.14em" text-anchor="middle">240</text>
```

`data-bins` is the basis of every geometric check, and it is this contract's own vocabulary: the slopegraph above binds `data-series` on a `<line>`, this variant binds `data-bins` on a `<path>`, and neither gate reads the other's attribute, so neither claims the other's file. Any further Line variant should take its own attribute for the same reason — a shared name means two checkers holding one figure to two contracts, and the one that loses rejects it for lacking elements it never said it had. `data-baseline` is what makes a moved row detectable; without it the checker would have to infer the zero from the drawing, which is the very thing being falsified. The printed range is cross-checked against the first and last nonzero bin through the figure's own tick scale, so a range widened by a word is a finding. `scripts/verify-ridgeline.py` covers the amplitude, the pitch, the baseline rules, the shared bins, the segment grammar, the overlap ceiling, the focus pairing and every label binding; `scripts/test-verify-ridgeline.py` proves each check in both polarities and pins the scope treaty with the sibling gates.

**No `transform` on any of it**, for the reason the slopegraph section gives: the checker reads raw coordinates, so a transform on an outline, a baseline rule, a bound label, an ancestor `<g>` or a CSS rule moves the rendered mark away from the bin that was verified. The rotated amplitude caption is fine — it is neither verified geometry nor a bound label.

#### Anti-patterns

- Per-ridge normalisation, or any second amplitude anywhere in the figure — the type's one unforgivable error.
- A baseline moved off the pitch to buy one ridge headroom, or a baseline rule drawn somewhere other than the row its ridge declares.
- Ridges sampled on different x-ranges, or an x-scale that is not printed at all.
- Smoothing that puts a peak between two bins, and any spline in a figure whose footnote says the drawing is unsmoothed.
- A ridge clipped mid-mass so the outline closes as a cliff.
- Pitch so tight that peaks hide behind peaks — increase the pitch, never shrink one ridge.
- One hue per ridge instead of the ink ramp plus a single accent.
- A legend that says "darker is faster", which is false on one of the two skins.
- Fewer than 3 ridges (that is a histogram or a pair of small multiples) or more than 12.
- Reading traffic off ridge height, or shipping a figure whose source line lets a reader do so.

## Examples

- `assets/example-line.html` — minimal light
- `assets/example-line-dark.html` — minimal dark
- `assets/example-line-full.html` — full editorial
- `assets/example-slopegraph.html` — slopegraph, minimal light
- `assets/example-slopegraph-dark.html` — slopegraph, minimal dark
- `assets/example-slopegraph-full.html` — slopegraph, full editorial
- `assets/example-ridgeline.html` — ridgeline, minimal light
- `assets/example-ridgeline-dark.html` — ridgeline, minimal dark
- `assets/example-ridgeline-full.html` — ridgeline, full editorial
