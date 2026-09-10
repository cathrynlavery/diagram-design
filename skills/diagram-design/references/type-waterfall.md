# Waterfall Chart

**Best for:** showing how a start total becomes an end total through signed contributions — a budget bridge (FY25 baseline → FY26 plan), headcount deltas (starting roster ± hires ± attrition), conversion leak/gain, P&L walk. Use when the running total is the story: every bar either anchors the total or bridges one running level to the next, and the reader traces the path from start to end.

**Not this type:**

- Two endpoints where only the *gap* matters → **dumbbell** (a Bar variant, `type-bar.md`). A dumbbell states two values and their distance; a waterfall states a path of signed steps that must reconcile. The types look adjacent but make opposite claims: the dumbbell hides what happened in between, the waterfall *is* what happened in between.
- Independent category comparisons → **bar** (`type-bar.md`).
- One quantity splitting and merging across stages → **Sankey** (`type-sankey.md`). A waterfall is strictly sequential and one-dimensional; the bars never branch.
- Ordered drop-off through stages of one funnel → **pyramid / funnel** (`type-pyramid.md`).

## Layout conventions

- **Orientation:** vertical columns only, left → right in narrative order: start total, then each signed bridge, optional subtotal, end total. A horizontal waterfall reads as a Gantt.
- **Plot area:** left 80px (y-axis labels), bottom 60px (category labels), top 40px, right 40px — inside a `0 0 1000 500` viewBox, same frame as the bar chart. Plot band x 80→960, y 40→420.
- **Bar count:** 3–8 bars total, including both totals and at most one subtotal. More contributions than that → merge the tail into one named "Other" bridge (disclose what it contains) or split the walk into two charts.
- **Bar width / pitch:** equal-width bars on an even pitch, bar ≥ 50% of the pitch. Six bars fit as width=96 on a 144px pitch starting at x=112.
- **Totals anchor, bridges float.** The start total, any subtotal, and the end total are drawn from the domain floor (the x-axis baseline) up to their value. Bridge bars span exactly the running total before and after their contribution — an increase rises from the previous level, a decrease falls from it.
- **Carry rules (the bridge grammar).** A horizontal connector line carries the running total across each gap between adjacent bars, drawn at the shared level: from the right edge of one bar to the left edge of the next, `rgba(45,49,66,0.55)` at 1px on light paper (`rgba(245,245,245,0.40)` dark) — the dumbbell's connector weight, because the carry is load-bearing and must clear 3:1, not the 0.25 axis hairline. Each carry declares the running total it transports in `data-carry`.
- **Machine-readable data contract.** Every bar rect declares `data-role` (`total`, `delta`, or `subtotal`), `data-value` (totals unsigned, deltas explicitly signed `+`/`-`), and `data-name`. `scripts/verify-waterfall.py` reads these and fails the build when the drawing and the declaration disagree — see the honesty rules below.
- **Sign is encoded by fill weight, not hue.** Increases take the bar family's default tint (`rgba(79,93,117,0.15)` fill, `muted` stroke). Decreases are hollow — paper fill, same `muted` stroke — so the two directions survive greyscale and colour-vision deficiency without leaning on the accent. The geometry (which end of the bar meets the carry) and the signed printed value are the second and third encodings of the same fact.
- **Totals are the heaviest marks:** `rgba(45,49,66,0.08)` fill with a 1px `ink` stroke. The reader's eye should land on the two anchors first, then walk the bridges.
- **Focal bridge (≤1, optional):** the one contribution the chart exists to show gets the bar family's focal treatment — `rgba(235,108,54,0.12)` fill, `accent` stroke, accent value label. It replaces that bar's sign fill; the signed label and geometry still carry the direction.
- **Value labels:** Geist Mono 8px. Totals and increases print above the bar top (baseline `top − 8`); decreases print below the bar bottom (baseline `bottom + 12`), because the space above a decrease is where its carry arrives. Deltas print with an explicit sign (`+64`, `−38`); totals print unsigned.
- **Gridlines / axes:** identical to the bar chart — 4–6 faint horizontal gridlines `rgba(45,49,66,0.08)` 0.8px, y-axis line and x-axis baseline `rgba(45,49,66,0.25)` 1px, tick labels Geist Mono 8px muted right-aligned at x=72, rotated y-axis title Geist Mono 7px tracked.
- **Category labels:** centered under each bar at y=440, Geist 11px 600 ink; the focal bar's label may take accent.
- **Legend:** horizontal bottom strip after a hairline rule, one key per treatment used: total, increase, decrease, focal.

### Waterfall element pattern

```svg
<!-- Start total: anchored at the baseline (y=420), value 240 on a 0–400 domain, k=0.95 px/unit -->
<rect x="112" y="192" width="96" height="228" fill="#f5f5f5"/>
<rect x="112" y="192" width="96" height="228" fill="rgba(45,49,66,0.08)" stroke="#2d3142" stroke-width="1"
      data-role="total" data-value="240" data-name="FY25 base"/>
<text x="160" y="184" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle">240</text>

<!-- Carry: the running total (240) crosses the gap at its own level -->
<line x1="208" y1="192" x2="256" y2="192" stroke="rgba(45,49,66,0.55)" stroke-width="1" data-carry="240"/>

<!-- Increase bridge: +64 rises from 240 to 304 -->
<rect x="256" y="131" width="96" height="61" fill="#f5f5f5"/>
<rect x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1"
      data-role="delta" data-value="+64" data-name="Headcount"/>
<text x="304" y="123" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace" text-anchor="middle">+64</text>
```

Endpoint positions round to the nearest integer pixel and never snap to the 4px grid — data coordinates are exempt, exactly as in the dumbbell. Bar x-positions and widths are layout, so they stay on the grid.

## Anti-patterns

- **A floating bar with no carry.** The connector is the claim that the total is conserved across the gap; without it the chart is bars at odd heights.
- **Sign by hue alone** (green up / red down, or accent on every decrease). Hue is the one channel that does not survive greyscale or CVD; fill weight and geometry carry the sign here, and the accent stays editorial.
- **A truncated value axis.** The domain follows the data's range, never its observed extremes — the same rule, cases, and all-zero fallback as the dumbbell (`type-bar.md` § Dumbbell honesty rules). A waterfall on a clipped domain inflates every bridge.
- **More than one subtotal.** A walk that needs several resting points is two walks; split it.
- **Mixing units mid-walk.** Every bar is in the start total's unit or the reconciliation is fiction.
- **3-D, shadows, rounded bridge bars** — same editorial rules as every chart here.

## Waterfall honesty rules

- **The running total must conserve.** Start + every signed bridge = each subtotal and the end total, exactly — the declared `data-value`s must reconcile before geometry is even considered. A waterfall that doesn't add up is not approximately right, it is wrong.
- **Bridges span exactly their two running levels.** Each bar's drawn top and bottom must sit where the shared scale puts the running totals before and after it (±0.75px for integer rounding). Stretching one bridge "for legibility" moves money that doesn't exist.
- **Every carry sits at the level it transports,** spanning its full gap, and declares that value. A carry drawn at the wrong height reconnects the walk to a different total.
- **Every bar prints its value, deltas with an explicit sign.** An unsigned bridge asks the reader to infer direction from geometry alone; print `+`/`−`.
- **Zero bridges are dropped, never drawn.** A zero-height bar is invisible ink that still occupies a column; state it in prose or the source line instead.
- **A degenerate start (zero or negative total) is a named failure,** not a silently rescaled chart — the scale is derived from the start anchor.

These rules are executable: `scripts/verify-waterfall.py` reads each bar's declaration, recomputes the running totals, refits the shared scale from the start anchor, and fails on any conservation, geometry, carry, label, or sign-treatment drift. `scripts/test-verify-waterfall.py` proves both polarities — the shipped examples pass, and each mutation class above fails with a named finding.

## Examples

- `assets/example-waterfall.html` — minimal light
- `assets/example-waterfall-dark.html` — minimal dark
- `assets/example-waterfall-full.html` — full editorial
