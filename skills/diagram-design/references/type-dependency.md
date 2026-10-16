# Dependency Graph

**Best for:** what depends on what, across packages, modules, or services — specifically to show two things a **tree** cannot structurally express: (a) a node with **more than one parent** (a shared dependency that several things converge on), and (b) a **cycle**. If neither appears in the data — every node has exactly one parent and nothing points backward — use [Tree](type-tree.md) instead; say so explicitly rather than forcing a graph layout on tree-shaped data.

## Layout conventions

- **Ranked layers.** Nodes sit in horizontal rank rows by dependency depth: rank 0 (entry points nothing depends on) at the top, deeper ranks below. Forward edges point downward across ranks, or run horizontal within a single rank row when a dependency compresses to the same depth as its dependent (e.g. a shallow sibling dependency) — never upward outside the one marked cycle. Rank rows are 120px apart.
- Nodes are the standard node-box pattern (§6, [primitives-core.md](primitives-core.md#node-box--full-pattern)): `rx=6`, 160px wide, 56px tall.
- **Fan-in badge.** Every node carries an `eyebrow`-role 8px badge in its top-right corner, inside a small `rx=2` box, showing how many nodes depend on it (`4 in`). A mask fully inside a node is a badge chip, not a label — legitimate under §6 rule 6. The node with the highest fan-in is the diagram's structural story; size nothing else to compete with it.
- **Node treatments** ([style-guide.md § Node type → treatment](style-guide.md#node-type--treatment)):
  - Internal package/service → white fill + `ink` stroke.
  - External / third-party → `ink @ 0.03` fill + `ink @ 0.30` stroke (the External/Cloud treatment).
  - Leaf with no outgoing edges → `ink @ 0.05` fill + `muted` stroke.
- **The cycle.** At most one back-edge points upward against rank order. It is the editorial point of the diagram: `accent` stroke, dashed `5,4`, `marker-end="url(#arrow-accent)"`, routed **around the outside** of the node stack — never straight through the middle, and never behind a node it doesn't connect to — with a masked `arrow-label`-role 8px `CYCLE` label at its visible end. The two nodes the cycle touches stay in their normal node treatment (§5) — no accent stroke or fill on the nodes themselves, or the 2-accent budget is blown on the wrong elements.
- **Focal rule:** the 2 accent elements permitted per diagram are the back-edge and its `CYCLE` label. Nothing else in a dependency graph is accent.
- All six §6 Mandatory connector rules apply in full, no exemptions: rounded right-angle elbows (`r=8`) between off-axis nodes, 6–10px label-margin, no overlapping connectors (bridge/hop at crossings), fanned attach points (≥12px apart) where multiple edges share a box edge, no connector passing behind a non-endpoint box, no label mask clipped by a later-painted node.

## Complexity budget

| Limit | Rule |
|---|---|
| Max nodes | 9 |
| Max edges | 14 |
| Max rank layers | 4 |
| Max highlighted cycles | 1 |
| Max accent elements | 2 |

Over budget: collapse a leaf cluster into one aggregate node labelled with its count (e.g. `+6 leaves`), and say so in a caption — don't silently drop nodes.

## Anti-patterns

- Drawing a dependency graph when the data is actually a tree (single parent everywhere, no cycles) — use Tree instead.
- Forward edges that point upward without being the one marked cycle.
- A hairball layout with no rank ordering — rank first, always; ranking is what makes the graph readable, not an optional polish pass.
- One node per file instead of per package/module/service — the graph is about dependency structure, not the filesystem.
- Unlabelled external dependencies — version or registry belongs in the `sublabel` (`v3.23 · npm`), not left implicit.
- Highlighting more than one cycle in a single diagram — pick the one that matters editorially; a second cycle competes with the first and neither reads.
- Omitting the fan-in badges — without them the reader can't see at a glance where dependencies concentrate, which is the entire reason this type exists over a plain tree.

### Arc diagram

**Best for:** pairwise imports among a handful of packages when the *skip* is the story — nodes on one baseline, each edge a rising semicircle whose height is how many seats it jumps. Use it when a ranked dependency graph would bury a skip-layer import inside the hairball: the shipped example lines seven packages left to right, and Checkout still importing Auth is the tallest arc.

Not for: a node with many parents that need rank rows (that is the parent dependency graph); a tree (every node has one parent — use Tree); a cycle that has to be routed around the stack (the parent marks that with one dashed back-edge). An arc diagram has no ranks and no back-edge grammar.

#### Layout conventions

- **One rail, left to right.** Nodes are `r=6` dots on a shared baseline at `y=400` inside `0 0 1000 500`, equally spaced (the shipped example uses a 140px pitch from `x=80`). Labels sit under the dots, `text-anchor="middle"`.
- **Node count: 4–9.** Below 4 there is no rail to skip along; above 9 split an overview from a cluster.
- **Rising semicircles only.** Each import is `M x1,y A r,r 0 0 1 x2,y` with `fill="none"`. Sweep 1 rises in SVG coordinates; sweep 0 would draw the import under the seats. `r` is half the endpoint distance, so height equals span × pitch / 2 — a neighbour cannot wear a skip's arc.
- **Span is the seat count.** `data-span` is `|i−j|` on the rail. A five-seat skip is five times a neighbour, not a decorative taller curve.
- **Paint back to front:** longer arcs first, neighbours next, the focal skip last so it is the stroke the eye hits.
- **4px grid** applies to the designed constants — baseline, label baseline, legend rows, node radius. Positions on the rail are pitch-scaled and exempt.

#### Colour

- **One accent arc, and one muted treatment for everyone else.** The shipped example accents Checkout → Auth — the skip that will hurt a split — not the package with the most edges.
- **Stroke, not fill.** An arc is a line. Filling it turns a skip into a wedge.
- **The nodes stay ink.** Accent lives on the skip, matching the parent's rule that the cycle is the accent and the nodes it touches are not.

#### Honest-data rule

**Arc height is the seat count, on one shared pitch.** `scripts/verify-arc-diagram.py` gates it.

- **One baseline, one pitch.** A node off the rail, or a seat that is a different width from its neighbours, makes two spans of the same count draw at two heights.
- **`data-span` equals `|i−j|`.** Declaring 2 for a five-seat skip, or drawing a neighbour at a skip's radius, is the type's unforgivable error.
- **Endpoints are the named nodes.** A path that names Auth and Checkout but lands on Catalog is a different import.

#### Declaring the values

**Every arc is bound to the two nodes it joins and the span it encodes.** `data-span` on a `<path>` is the arc-diagram contract — deliberately not `data-value` on a `<circle>` (beeswarm), `data-size` (bubble), `data-series` (slopegraph) or `data-ranks` (bump), so no sibling checker claims an arc-diagram file and this one claims none of theirs.

```svg
<!-- Seat rail at y=400, pitch 140. Auth is seat 1, Checkout is seat 6. -->
<circle data-name="Auth" cx="220" cy="400" r="6"/>
<circle data-name="Checkout" cx="920" cy="400" r="6"/>
<path data-from="Checkout" data-to="Auth" data-span="5"
      d="M 220,400 A 350,350 0 0 1 920,400"
      fill="none" stroke="{accent}" stroke-width="1.6"/>
```

What each binding buys, and what it costs to omit:

| Binding | Without it |
|---|---|
| `data-span` on the path | A decorative tall arc on a neighbour could not be caught — the drawn radius would be the only statement of the skip. |
| `data-from` / `data-to` | A path that names two packages but lands on two others still looks like their import. |
| `data-name` on the node circle and its label | Two labels exchanged along the rail rename both packages, with every span still correct in isolation. |

`scripts/verify-arc-diagram.py` derives the pitch from the nodes, requires a rising semicircle whose radius matches both the endpoint distance and `pitch · span / 2`, refuses a second accent arc, and checks every bound label against the node it names; `scripts/test-verify-arc-diagram.py` proves each check in both polarities and pins the sibling scope treaty in both directions.

**Nothing may position a mark except its own attributes.** The checker reads raw `cx`/`d`/`x`, so anything applied afterwards invalidates the check that passed. Every carrier is refused — the `transform` attribute, an inline `style="…"`, and a rule in a `<style>` block — on a node, on an arc, on a bound label, or on an ancestor `<g>`/`<svg>`. Bake the offset into the coordinates.

#### Anti-patterns

- Drawing a neighbour at a skip's height — the type's one unforgivable error.
- A ranked layout, a cycle routed around the stack, or fan-in badges (those are the parent).
- Filling an arc, or using sweep 0 so the import hangs under the seats.
- Uneven spacing so that height no longer equals span.
- A hue per edge instead of one muted treatment plus a single accent.
- Positioning a mark, a bound label or an ancestor group from CSS.

## Examples

- `assets/example-dependency.html` — minimal light
- `assets/example-dependency-dark.html` — minimal dark
- `assets/example-dependency-full.html` — full editorial
- `assets/example-arc-diagram.html` — arc diagram, minimal light
- `assets/example-arc-diagram-dark.html` — arc diagram, minimal dark
- `assets/example-arc-diagram-full.html` — arc diagram, full editorial
