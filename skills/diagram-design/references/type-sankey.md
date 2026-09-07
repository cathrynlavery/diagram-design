# Sankey / Flow-Quantity

**Best for:** showing where a *quantity* goes as it splits and merges across a small number of stages — CI compute budgets, funnel-adjacent volume flows, cost or headcount allocation. This is the one type where band **thickness carries data**; if the reader doesn't need to compare magnitudes, use process or pyramid instead.

## Layout conventions

- **Exactly 3 stage columns**, left → right. No more, no less — above 3 stages, split into two linked diagrams.
- **Nodes are vertical bars**, `width=12`, solid `ink` fill, no stroke. Height is proportional to the quantity passing through, rounded to the nearest 4px so it stays on-grid — the rounding is a rendering step, not a data change; the true value still prints in the quantity sublabel.
- **Flows are filled ribbons**, not stroked lines: a single closed `<path>` per flow. Top edge is a cubic Bézier from the source node's top-offset to the target node's top-offset; bottom edge is the same curve run in reverse from target-bottom back to source-bottom. **Both** control points sit at the horizontal midpoint between the two columns, each at the y of the end it belongs to: `C midX,y0 midX,y1 targetX,y1`. That is what makes the band leave and arrive **horizontally**, so it plugs into each bar square-on. Putting the second control on the target's x instead (`C midX,y0 targetX,y1 targetX,y1`) collapses it onto the endpoint, the arrival tangent degenerates, and every ribbon meets its bar at a visible slant — it looks like the band is not attached.
- **No arrowheads, ever.** Direction is implied by the left-to-right column order. This is a deliberate, explicit exemption from SKILL.md §6's orthogonal-elbow-and-arrowhead rule: ribbons are area encodings, not connectors, and a marker on a filled band reads as clutter, not information.
- **Ribbon fill:** `muted` at `0.18` opacity for ordinary flows. The one editorial focal path (see below) uses `accent` at `0.28` opacity. A focal path may span more than one ribbon segment (e.g. two flows that both feed the same downstream node as halves of one story) — accenting every ribbon that belongs to that single path still counts as **one** focal element, not one per ribbon. Never per-flow rainbow coloring — color is reserved for the one path that deserves attention.
- **Node ordering minimizes crossings.** Order nodes within each column so that flows converging on (or diverging from) the same node stay in a consistent top-to-bottom sequence across columns. If two ribbons still cross more than once, reorder the nodes — don't let them tangle.
- **Labels:** node name in Geist sans 12px 600, quantity directly under it in Geist Mono 9px `muted`. Placement is column-specific: column 1 sits outside the bar, `text-anchor="end"`; column 2 sits in the gutter above its bar, `text-anchor="middle"`, **vertically centred in that gutter** rather than flush to the top, or the cap line grazes the bar above; column 3 sits outside the bar, `text-anchor="start"`.

  Centring the column-2 label in its gutter is what makes it legible: the gutter is the gap the bands themselves leave between two nodes, so a centred label sits on clean paper and needs no backing at all. Don't reach for a mask rect here — over a filled band it reads as a hole punched in the diagram, and if the label already sits on paper it is solving nothing. If a label genuinely has nowhere clear to sit, the column is over budget: drop a node or split the diagram.
- **Column headers:** Geist Mono 8px, uppercase, tracked, centered above each column — "CI COMPUTE BUDGET / TEST STAGE / OUTCOME" style eyebrows, not full sentences.
- **Drawing order:** background → column headers → ordinary ribbons → the accent path's ribbon(s) (painted last among ribbons so they read on top) → node bars → node labels → legend.
- **Legend:** horizontal strip at the bottom per the global rule, viewBox extended ~60–100px to fit it (a Sankey's ribbons need more bottom clearance than a typical diagram because node stacks run tall). Swatches are 16×8 rectangles matching each ribbon treatment, plus an optional italic aside stating the editorial read.

## Scale rule

Pick **one px-per-unit constant `k`** for the whole diagram and apply it to every node and ribbon thickness — never a different scale per column. Round each resulting thickness to the nearest 4px (grid compliance) and reconcile the rounding at the node level, not the flow level, so a node's outgoing ribbons still sum exactly to its (rounded) height.

**When you control the numbers, choose ones that land on the grid.** At `k`, a 4px step is `4/k` units; pick quantities that are whole multiples of it and the drawn area is then exactly the printed number. Rounding is the fallback for real data you cannot choose, and it is a real cost: at `k = 0.02` a 4px step is 200 minutes, so a rounded bar can misstate its own label by up to 100. In a chart whose entire premise is that area encodes quantity, a bar that disagrees with the number printed beside it spends credibility to buy grid compliance. Never let the rounding exceed one 4px step, and never round a flow so far that a node's ribbons no longer sum to its bar.

**Minimum rendered ribbon thickness: 4px.** Anything that would round to less gets folded into an "other" band rather than drawn as an invisible hairline — a Sankey ribbon the reader can't see isn't communicating anything.

### Worked reference (k = 0.02 px/unit, budget = 12,000 CI minutes)

| Node | Quantity | Height (px) |
|---|---|---|
| CI minutes (col 1) | 12,000 | 240 |
| Unit tests | 5,200 | 104 |
| E2E | 4,000 | 80 |
| Build | 2,000 | 40 |
| Lint | 800 | 16 |
| Passed | 9,400 | 188 |
| Failed | 1,600 | 32 |
| Flaked | 1,000 | 20 |

Each column's node heights sum to the same 240px total — that invariant (total-in equals total-out) is what makes the diagram trustworthy at a glance. If your columns don't sum to the same total, the data has a leak or the layout has a bug.

## Complexity budget

| Limit | Rule |
|---|---|
| Max stage columns | 3 |
| Max nodes | 8 |
| Max flows (ribbons) | 12 |
| Max accent elements | 2 (a focal path's ribbons count as one, regardless of how many segments it spans) |

Over budget → split into two linked Sankeys (e.g. an overview stage-1→stage-2 diagram plus a detail stage-2→stage-3 diagram) rather than cramming a fourth column or a ninth node into one canvas.

## Anti-patterns

- **Ribbons that meet the bar at a slant.** The single most common way to get this type wrong, and it is a control-point mistake, not a layout one: both controls belong on the midpoint x. A band arriving at an angle reads as detached from its node, which undermines the one thing the diagram is asserting — that this quantity flows into that node.
- **An opaque mask rect behind a column-2 label.** Over a filled band it reads as a hole punched in the diagram, and it erases any bar it overlaps. Centre the label in the gutter instead, where it sits on clean paper and needs nothing behind it.
- **Column-2 labels flush to the top of their gutter.** Centre them, or the cap line touches the bar above and the label looks like it belongs to the wrong node.
- **A bar whose height disagrees with the number printed beside it.** See the scale rule: choose grid-friendly quantities when the data is yours to choose.
- **Ribbons crossing more than once.** Reorder the nodes in the offending column; a Sankey with a tangle in the middle is unreadable.
- **Ribbons thinner than 4px.** Merge them into an "other" band instead of drawing a sliver no one can see.
- **Per-flow rainbow coloring.** One `muted` treatment for ordinary flows, one `accent` treatment for the flow that carries the editorial point — never a distinct hue per ribbon.
- **Using Sankey for a simple funnel.** A single narrowing quantity with no splits or merges is a pyramid/funnel, not a Sankey.
- **Using Sankey for a plain step sequence.** If nothing splits, merges, or varies in thickness, it's a process diagram — the whole point of Sankey is quantity that branches.
- **Stacking two flows at the same node-edge offset.** Every flow gets its own offset range within the node's height, in a consistent top-to-bottom order — never two ribbons overlapping at the same attach point.
- **Percentages or quantities that don't sum to the source total.** Every node's outgoing (or incoming) flows must sum to that node's own height. A Sankey that doesn't balance reads as an error, not a design choice.

## Examples

- `assets/example-sankey.html` — minimal light. A month of CI compute (12,000 minutes) splitting into test/build/lint stages, merging into passed/failed/flaked outcomes; the flaky-rerun path is the one accent flow.
- `assets/example-sankey-dark.html` — minimal dark, same data.
- `assets/example-sankey-full.html` — full editorial: container framing + 3 summary cards of varied widths + footer.
