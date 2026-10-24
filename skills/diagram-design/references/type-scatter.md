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

- More than 30 points without clustering (jitter/mush) — when the crowd itself is the story, hand it to the **beeswarm variant** below, which packs instead of jittering.
- Forced trend line when the data is genuinely scattered — dishonest.
- Point labels on every point (label the focal and 1–2 notable outliers only).
- Ad-hoc bubble size encoding on a plain scatter. Size perception is unreliable enough that it earns its own contract: when the third value genuinely matters, use the **bubble variant** below, which pins area to the value and gates it with `scripts/verify-bubble.py`; when it doesn't, a third axis label or a focal choice says it cheaper.
- Axes that don't include zero when the absolute position matters; axes that do include zero when the range is tiny and far from zero.

### Bubble

**Best for:** three quantities per item — x, y, and a magnitude — where the *joint* reading is the story: which items combine a bad position with a big footprint. The shipped example plots services by p95 latency and error rate with area as request volume, and the point of the figure is exactly the multiplication a two-variable scatter cannot do — the slowest service barely matters and the risky one is not the slowest.

Not for: a third value that is really a category (use the focal accent or facet it); two variables (that is the parent scatter — size on everything is decoration); or magnitudes spanning several orders (the small bubbles vanish; bin, or plot the magnitude on an axis of its own).

#### Layout conventions

- **Same plot frame as the parent:** margins left 80, bottom 60, top 40, right 40 inside `0 0 1000 500`; X rule at `y=420`, Y rule at `x=80`; gridlines at the parent's positions; legend on the house rhythm (rule `y=462`, `LEGEND` at `478`, keys at `490`).
- **Item count:** 5–15. Below 5 the leave-one-out scale check has nothing to hold onto and a table says it better; above 15 the areas start stacking and the reading degrades to a density cloud — which is the parent's contour territory, not this.
- **Radius from area:** `r = K·√value` for one constant K across the figure, sized so the largest bubble stays inside the plot (the shipped example uses `K = 1.4` on requests-per-second, giving 10.8–42px). State the area scale in the source line.
- **Bound axis ticks:** every tick carries `data-tick` (axis) and `data-value` (the number it prints). 4–6 per axis at equal intervals, `arrow-label` role 8px, same placement as the parent.
- **Paper underlay per bubble**, same radius, painted immediately beneath — the translucent fill must not show gridlines through itself, because the fill's job is to read as one solid area.
- **Draw order: largest first.** A small bubble painted early is buried under a later giant and its area is unreadable. `verify-bubble.py` checks paint order on every overlapping pair.
- **Labels:** the focal bubble plus at most 2–3 outliers a reader will look for, `arrow-label` role 8px small-caps on a paper mask, each bound to its bubble with `data-name`. Never all of them.
- **4px grid** applies to the designed constants — axis rules, gridlines, tick baselines, legend rows. Bubble centres and radii are data-scaled and exempt; snapping them would move the data.

#### Colour

- **One accent bubble, and an `ink` opacity ramp for everything else** — never a hue per item. Every labelled bubble is named where it sits, so hue would re-encode what the labels already carry.
- **The accent marks the editorially focal item, not the biggest or the worst single number.** In the shipped example it marks the service whose *combination* is the risk: near-peak volume on the worst error rate.
- **The ramp runs faintest-on-largest** (0.14 on the largest fill up to 0.35 on the smallest in the shipped example). This is ink-mass compensation, not an encoding: a giant bubble at the same opacity as a small one dominates the page by area alone, so opacity scales down as area scales up and every bubble ends up with comparable visual weight. Tone is **not** a fourth variable — the legend must say which end of the ramp is which, in skin-neutral terms ("faintest fill is the largest bubble" survives both skins; "darkest" ships false on one of them).
- **Every bubble keeps a `muted` stroke** (6.11:1 on light paper, 7.07:1 on dark) — the fills sit at opacities well under 3:1, so the stroke is what carries WCAG 1.4.11 for the mark's edge. The focal bubble's accent stroke measures 4.71:1 on light paper with the default skin and may measure less on an onboarded one; as with the focal bar, line and slopegraph, its data is carried redundantly — position, label, and the legend naming it in words — and the accent adds only *which bubble is focal*.
- **Labels stay `ink` or `muted`**, including the focal one. Accent text at 8px misses AA on light paper.

#### Honest-data rule

**Area encodes the third value — never radius.** Radius-proportional sizing squares the claim: a 6× value reads as 36× the ink. `scripts/verify-bubble.py` gates it, along with the two axis scales.

- **One finite, nonzero linear scale per axis, every bubble on it.** A bubble nudged aside because two crowd each other reads as a different number; crowded bubbles are data, and the honest fixes are a hairline of separation (which the largest-first rule provides) or fewer items — never a moved centre.
- **Axes include zero, or the source line states the bounds.** A bubble's position is read against the origin in a way a slopegraph's is not. No log scale without saying so — and area next to a log axis is a reading most audiences get wrong, so prefer not at all.
- **Omitted items are counted in the footnote.** A bubble chart with the inconvenient giant quietly missing is the same lie as a truncated axis.
- **A non-positive magnitude cannot be a bubble.** Area has no sign; omit the item and say so.
- **Round once, then draw from the rounded number**, so the declared value and the drawn geometry are two statements of one number rather than two chances to disagree.

#### Declaring the values

**Every drawn quantity is bound to an attribute stating the value it encodes.** A zero-slope value axis collapses distinct values to one position and is rejected, including in the beeswarm variant. The data circle carries all three values; the paper underlay is scenery and carries nothing.

```svg
<!-- A bubble: position from two shared linear scales, area from the size.
     x = 80 + 1.76·ms, y = 420 - 95·pct, r = 1.4·√(req/s) -->
<circle cx="537.6" cy="154" r="38.6" fill="{paper}"/>
<circle data-name="Payments" data-x="260" data-y="2.8" data-size="760"
        cx="537.6" cy="154" r="38.6"
        fill="{accent @ 0.15}" stroke="{accent}" stroke-width="1.2"/>

<!-- Its label, bound to the bubble it names -->
<text data-name="Payments" data-role="label" x="538" y="108" fill="{ink}" font-size="8" font-family="{arrow-label}" text-anchor="middle" letter-spacing="0.06em">PAYMENTS</text>

<!-- An axis tick, bound to the number it prints -->
<text data-tick="x" data-value="300" x="608" y="440" fill="{muted}" font-size="8" font-family="{arrow-label}" text-anchor="middle">300</text>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-x` / `data-y` on the circle | A nudged centre could not be caught — the drawn position would be the only statement of the value. |
| `data-size` on the circle | Nothing pins area to the value, and radius-proportional sizing renders identically plausible. |
| `data-name` on the circle | An unnamed bubble cannot be labelled or cross-checked, and drops out of every comparison silently. |
| `data-name` on a label | Two labels could be exchanged between bubbles, renaming both, with every number still correct in isolation. |
| `data-tick` / `data-value` on a tick | The printed axis could be relabelled wholesale — every bubble honestly placed on a scale the axis lies about. |

`scripts/verify-bubble.py` derives both axis scales and the area constant from the set itself (Theil–Sen, leave-one-out, so one dishonest bubble cannot drag the line it is measured against), requires at most one accent bubble, checks paint order on overlaps, and holds every bound label and tick against the mark it describes. Deliberately **not** `data-series`: that attribute is the slopegraph contract, and using it here would put every bubble file inside `verify-slopegraph.py`'s scope.

**No `transform` on any of it.** The checker reads raw `cx`/`cy`/`r` and `x`/`y` attributes, so a transform on a bubble, a bound label, an ancestor `<g>`, or in a CSS rule moves the rendered mark away from the number that was verified. Bake the offset into the coordinates. The rotated value-axis caption is fine — it is neither verified geometry nor a bound label.

#### Anti-patterns

- Radius proportional to the value — the type's one unforgivable error.
- Moving a bubble to stop it overlapping a neighbour, or drawing a small bubble under a large one.
- A hue per item instead of the ink ramp plus a single accent, or a legend that reads the ramp as data.
- A log axis the source line never states, or a truncated axis with no stated bounds.
- Labelling every bubble (the focal plus 2–3 outliers, no more).
- A `transform` on a bubble, a bound label, an ancestor group, or in CSS.
- An unbound visible string: a label or an axis tick with no attribute stating the same thing.
- Size on a value nobody will read — if the areas do not change the story, this is the parent scatter wearing a costume.

### Beeswarm

**Best for:** a full distribution where every unit deserves its own mark — one dot per item on a single shared value axis, dodged perpendicular so nothing overlaps. Use when the *shape* of the crowd and its outliers are the story a summary number would hide: the shipped example plots 138 per-request latency samples for one endpoint, and the point of the figure is that a healthy median and an ugly p99 are the same dataset.

Not for: two variables (that is the parent scatter); comparing distributions across many groups (facet, a ridgeline, or the **box plot variant** below); more than ~300 items (the packing outgrows the band — bin into a histogram); or a handful of values (below 20 there is no distribution to swarm, and a table says it shorter).

#### Layout conventions

- **One value axis, horizontal, at the parent's baseline** (`y=420` inside `0 0 1000 500`, plot margins left 80, right 40), with 4–6 bound ticks at equal intervals in the `arrow-label` role at 8px and **vertical gridlines only** — the swarm axis has no scale to grid, and a horizontal rule through the band would invite reading the packing offsets as values.
- **Dot count: 20–300**, one dot per item, all at one radius (the shipped example uses `r=4`). Both ends of the budget are enforced by `scripts/verify-beeswarm.py`.
- **Greedy dodge around a midline** (`y=230` in the shipped example): each dot takes the first free slot alternating above/below at a fixed pitch of `2r+2`. The dodge is packing, not data — any collision-free arrangement is legitimate, and the algorithm is not part of the contract.
- **Labels: the focal dot plus the outliers a reader will look for, at most 6.** `arrow-label` role 8px small-caps on a paper mask, one tier per label, alternating sides of the band, each tied to its dot by an unbound hairline leader and bound to it with `data-name`.
- **4px grid** applies to the designed constants — the axis rule, gridlines, tick baselines, legend rows. Dot positions are data-scaled on the value axis and packing-scaled on the swarm axis, and both are exempt; snapping them would move the data.

#### Colour

- **One ink fill for every non-focal dot** (`ink` at 0.55 in the shipped example) plus a `muted` stroke for the mark's edge, and **at most one accent dot**. Density must read as swarm *thickness*, never as tone: opacity as a value encoding while also dodging says one thing twice in two different lies, so `verify-beeswarm.py` requires the non-focal fill to be literally identical across the swarm.
- **The accent marks the editorially focal item** — in the shipped example the single slowest request, the one the title is about — never a hue per group. Groups are a facet decision, not a palette decision.
- **The focal dot keeps the shared radius.** Its cues are the accent fill and stroke, its label, and the legend naming it in words; a bigger focal dot is a second encoding and breaks the packing.

#### Honest-data rule

**The value axis is exact and shared; the swarm axis carries no meaning — and says so.** The legend or source line states that the vertical spread is packing, states the axis bounds, and counts anything omitted. `scripts/verify-beeswarm.py` gates the geometry half.

- **No dot is dropped, binned, or jittered off its true value.** One dot = one item at exactly its value on one linear scale derived from the set itself (Theil-Sen, leave-one-out, so one dishonest dot cannot drag the line it is measured against).
- **Overlap is resolved by the perpendicular dodge, never by moving a dot along the value axis.** Two items with one value share a position and dodge apart; crowding is data, and the honest rendering of a crowd is thickness.
- **No two dots overprint.** A dot painted over another turns density into darkness, which the eye reads as a value nobody declared.
- **Linear scale only in the shipped grammar.** A log axis needs its own declaration before the checker could hold it to anything, so it is refused rather than half-trusted; if the spread demands log, say so in the source line and expect the gate to disagree until the grammar grows the declaration.

#### Declaring the values

**Every dot is bound to the value it encodes.** `data-value` on a `<circle>` is the beeswarm contract — deliberately not `data-series` (slopegraph), `data-ranks` (bump) or `data-size` (bubble), so no sibling checker claims a beeswarm file and this one claims none of theirs. Detection is element-scoped: `data-value` also appears on `<text>` axis ticks in the bubble contract, so only a `<circle>` binding it puts a file inside this gate. The paper underlay beneath each dot is scenery and carries nothing.

```svg
<!-- A dot: position on the shared value scale, x = 80 + 2·ms. The cy is
     packing only. -->
<circle data-value="90" cx="260" cy="250" r="4" fill="{ink @ 0.55}" stroke="{muted}" stroke-width="0.75"/>

<!-- The focal dot — named, accented, same radius as everyone -->
<circle data-value="431" data-name="req-4c1f" cx="942" cy="230" r="4" fill="{accent @ 0.55}" stroke="{accent}" stroke-width="1.2"/>

<!-- Its label, bound to the dot it names -->
<text data-name="req-4c1f" data-role="label" x="942" y="120" fill="{ink}" font-size="8" font-family="{arrow-label}" text-anchor="middle" letter-spacing="0.06em">REQ-4C1F</text>

<!-- An axis tick, bound to the number it prints -->
<text data-tick="x" data-value="200" x="480" y="440" fill="{muted}" font-size="8" font-family="{arrow-label}" text-anchor="middle">200</text>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-value` on the circle | A dot nudged along the value axis could not be caught — the drawn position would be the only statement of the value. |
| `data-name` on the focal/outlier circles | An unnamed outlier cannot be labelled or cross-checked, and two swapped labels rename both dots silently. The name must be non-empty and unique to one dot: two dots sharing a name collapse into one entry, so a single label satisfies both. |
| `data-name` on a label | The label floats free — it could name a dot that is not there, or drift to a neighbour. |
| `data-tick` / `data-value` on a tick | The printed axis could be relabelled wholesale — every dot honestly placed on a scale the axis lies about. |

`scripts/verify-beeswarm.py` derives the value scale from the dots themselves, requires dots sharing a value to share a position, refuses any overprinted pair, holds every dot to one radius and every non-focal dot to one fill, caps the accent at one dot and the labels at six, requires every `data-name` to be non-empty and unique, and checks every bound label and tick against the mark it describes; `scripts/test-verify-beeswarm.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `cx`/`cy`/`r` and `x`/`y`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a dot, on a bound label or tick, or on an ancestor `<g>`/`<svg>`. So is every positioning property, not just `transform`: the Level 2 individual properties `translate`/`rotate`/`scale`, the SVG geometry properties `cx`/`cy`/`r`/`x`/`y` (CSS beats the presentation attribute), and CSS motion path. Bake the offset into the coordinates. `line-height`, `color` and font declarations are untouched — they do not move anything.

#### Anti-patterns

- Moving a dot along the value axis to open up space — the type's one unforgivable error.
- Binning or averaging before plotting (that is a histogram wearing a costume), or quietly dropping the inconvenient outlier.
- Dot size as a second encoding (that is the **bubble variant**), or opacity as a value encoding while also dodging.
- Meaning smuggled into the swarm axis: sorting the dodge by a second variable, or a midline drawn as if it were a scale.
- A hue per group instead of one ink plus a single accent.
- Labelling more than the focal dot and a handful of outliers.
- Positioning a dot, a bound label, a tick or an ancestor group from CSS — `transform`, `translate`, `rotate`, `scale`, a geometry property (`cx`/`cy`/`r`/`x`/`y`) or a motion path — whether as an attribute, an inline `style`, or a rule in a `<style>` block.
- Two dots wearing the same `data-name`, or an empty one: a name that identifies two marks identifies neither.
- An unbound visible string: a label or an axis tick with no attribute stating the same thing.

### Box plot

**Best for:** comparing the *shape* of a few distributions when the five-number summary is the story — one box per group on a single shared value axis. Use it when a median would hide the spread, and when drawing every unit (the beeswarm) would hide the comparison: the shipped example plots per-request latency for five services, and the point of the figure is that Checkout's median still looks survivable while its box already runs 80–200 ms.

Not for: two continuous variables (that is the parent scatter); one distribution of individuals (that is the **beeswarm variant**); the silhouette of many distributions (that is the **ridgeline** on Line); a single number per category (that is a bar).

#### Layout conventions

- **Orientation:** horizontal only. Rows stack downward and the value axis runs left → right; a vertical box plot forces rotated category labels, which this variant does not.
- **Same plot frame as the parent:** value axis at `y=420` inside `0 0 1000 500`. Category labels take a 160px left margin (right-aligned at `x=148`, `node-name` role 11px 600), so the scale starts at `x=160`. The shipped example uses `x = 160 + 2·ms` on a 0–400 domain.
- **Series count: 3–8.** Below 3 a table says it shorter; above 8 split an overview from per-series detail.
- **One box per series**, height 32px, centred on the row. Paper underlay immediately beneath so gridlines do not show through the translucent fill.
- **Tukey fences, not the theoretical fence:** whiskers run to the last inlier (`data-wlo` / `data-whi`) inside `q1 - 1.5·IQR` and `q3 + 1.5·IQR`, with 16px caps. Outliers are `r=4` dots strictly outside those whiskers and fences, bound with `data-x` on the circle — never `data-value`, which is the beeswarm contract.
- **Median** is a vertical `ink` line through the box at `data-q2`, 1.5px. It is the only mark that may sit on the `ink` token at full strength; the box fill stays a tint.
- **Labels:** the category name at the left of its row, bound with `data-name`. Value-axis ticks are bound with `data-tick="x"` and `data-value`. The category axis has no scale to tick.
- **4px grid** applies to the designed constants — axis rule, gridlines, tick baselines, legend rows, box height, row centres. Positions on the value axis are data-scaled and exempt.

#### Colour

- **One accent series, and one muted treatment for everyone else.** The shipped example accents Checkout — the IQR that will page — not the series with the most outliers.
- **Fill weight, not hue, carries the pairing.** Non-focal boxes use `muted @ 0.15` fill + `muted` stroke; the focal box uses `accent @ 0.12` fill + `accent` stroke. Outliers inherit their series' stroke. The median stays `ink` on every row so it does not compete with the focal fill.
- **The value axis is exact and shared.** Crowded boxes mean the summaries really are close; never nudge a box along the value axis to open up space.

#### Honest-data rule

**The five-number summary is ordered, and every mark sits on one linear scale.** `scripts/verify-box-plot.py` gates it.

- **`wlo ≤ q1 ≤ q2 ≤ q3 ≤ whi`.** A median outside its box, or a whisker that grows inward, is not a five-number summary.
- **Box left is q1, box right is q3, median is q2, whiskers are wlo/whi.** Width encodes the IQR — never pad a box to fit a label.
- **Outliers sit strictly outside the whiskers and the Tukey fences.** Drawing an inlier as a dot, or parking an outlier on the fence, hides the tail.
- **Linear scale only, from a stated floor.** The shipped example includes zero. A truncated axis inflates every box the same way a truncated bar does.
- **Round once, then draw from the rounded number**, so the declared value and the drawn geometry are two statements of one number.

#### Declaring the values

**Every series is bound to the five numbers it encodes.** `data-q1` on a `<g>` is the box-plot contract — deliberately not `data-value` on a `<circle>` (beeswarm), `data-size` (bubble), `data-series` (slopegraph) or `data-ranks` (bump), so no sibling checker claims a box-plot file and this one claims none of theirs.

```svg
<!-- One series. x = 160 + 2·ms. Category y is a label rail. -->
<g data-name="Checkout" data-q1="80" data-q2="120" data-q3="200"
   data-wlo="40" data-whi="280">
  <line data-role="whisker-lo" x1="240" y1="216" x2="320" y2="216"/>
  <line data-role="whisker-hi" x1="560" y1="216" x2="720" y2="216"/>
  <rect data-role="box" x="320" y="200" width="240" height="32" rx="2"
        fill="{accent @ 0.12}" stroke="{accent}" stroke-width="1.2"/>
  <line data-role="median" x1="400" y1="200" x2="400" y2="232"/>
  <circle data-outlier="Checkout" data-x="388" cx="936" cy="216" r="4"/>
</g>
<text data-tick="x" data-value="200" x="560" y="440">200</text>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-q1` / `data-q2` / `data-q3` / `data-wlo` / `data-whi` on the group | A nudged box could not be caught — the drawn geometry would be the only statement of the summary. |
| `data-role="box"` / `"median"` / `"whisker-lo"` / `"whisker-hi"` | The checker could not tell a gridline from a whisker, or a paper underlay from the IQR. |
| `data-x` on an outlier circle | `data-value` on a circle is the beeswarm contract; using it here would put every box-plot file inside `verify-beeswarm.py`. |
| `data-name` on the group and its category label | Two labels exchanged between rows rename both series, with every number still correct in isolation. |
| `data-tick` / `data-value` on a tick | The printed axis could be relabelled wholesale — every box honestly placed on a scale the axis lies about. |

`scripts/verify-box-plot.py` derives the value scale from the summaries themselves, requires the five-number order, holds every box, median, whisker and outlier to that scale, refuses an outlier inside the whiskers, caps the accent at one series, and checks every bound tick against the mark it describes; `scripts/test-verify-box-plot.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `x`/`width`/`x1`/`cx` and `y`/`cy`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a series group, on a box, on a bound label or tick, or on an ancestor `<g>`/`<svg>`. Bake the offset into the coordinates.

#### Anti-patterns

- Moving a box along the value axis to open up space — the type's one unforgivable error.
- A median outside its box, or whiskers that grow inward.
- Parking an outlier on the fence, or drawing an inlier as a dot.
- A hue per series instead of one muted treatment plus a single accent.
- `data-value` on an outlier circle (that is the beeswarm contract).
- Positioning a mark, a bound label, a tick or an ancestor group from CSS.
- Two series wearing the same `data-name`, or an empty one.
- An unbound visible string: a category label or an axis tick with no attribute stating the same thing.

## Examples

- `assets/example-scatter.html` — minimal light
- `assets/example-scatter-dark.html` — minimal dark
- `assets/example-scatter-full.html` — full editorial
- `assets/example-bubble.html` — bubble, minimal light
- `assets/example-bubble-dark.html` — bubble, minimal dark
- `assets/example-bubble-full.html` — bubble, full editorial
- `assets/example-beeswarm.html` — beeswarm, minimal light
- `assets/example-beeswarm-dark.html` — beeswarm, minimal dark
- `assets/example-beeswarm-full.html` — beeswarm, full editorial
- `assets/example-box-plot.html` — box plot, minimal light
- `assets/example-box-plot-dark.html` — box plot, minimal dark
- `assets/example-box-plot-full.html` — box plot, full editorial
