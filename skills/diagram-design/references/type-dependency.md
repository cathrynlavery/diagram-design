# Dependency Graph

**Best for:** what depends on what, across packages, modules, or services — specifically to show two things a **tree** cannot structurally express: (a) a node with **more than one parent** (a shared dependency that several things converge on), and (b) a **cycle**. If neither appears in the data — every node has exactly one parent and nothing points backward — use [Tree](type-tree.md) instead; say so explicitly rather than forcing a graph layout on tree-shaped data.

## Layout conventions

- **Ranked layers.** Nodes sit in horizontal rank rows by dependency depth: rank 0 (entry points nothing depends on) at the top, deeper ranks below. Forward edges point downward across ranks, or run horizontal within a single rank row when a dependency compresses to the same depth as its dependent (e.g. a shallow sibling dependency) — never upward outside the one marked cycle. Rank rows are 120px apart.
- Nodes are the standard node-box pattern (§6): `rx=6`, 160px wide, 56px tall.
- **Fan-in badge.** Every node carries a Geist Mono 8px badge in its top-right corner, inside a small `rx=2` box, showing how many nodes depend on it (`4 in`). A mask fully inside a node is a badge chip, not a label — legitimate under §6 rule 6. The node with the highest fan-in is the diagram's structural story; size nothing else to compete with it.
- **Node treatments** (§5 Node type → treatment):
  - Internal package/service → white fill + `ink` stroke.
  - External / third-party → `ink @ 0.03` fill + `ink @ 0.30` stroke (the External/Cloud treatment).
  - Leaf with no outgoing edges → `ink @ 0.05` fill + `muted` stroke.
- **The cycle.** At most one back-edge points upward against rank order. It is the editorial point of the diagram: `accent` stroke, dashed `5,4`, `marker-end="url(#arrow-accent)"`, routed **around the outside** of the node stack — never straight through the middle, and never behind a node it doesn't connect to — with a masked Geist Mono 8px `CYCLE` label at its visible end. The two nodes the cycle touches stay in their normal node treatment (§5) — no accent stroke or fill on the nodes themselves, or the 2-accent budget is blown on the wrong elements.
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
- Unlabelled external dependencies — version or registry belongs in the Geist Mono sublabel (`v3.23 · npm`), not left implicit.
- Highlighting more than one cycle in a single diagram — pick the one that matters editorially; a second cycle competes with the first and neither reads.
- Omitting the fan-in badges — without them the reader can't see at a glance where dependencies concentrate, which is the entire reason this type exists over a plain tree.

## Examples

- `assets/example-dependency.html` — minimal light
- `assets/example-dependency-dark.html` — minimal dark
- `assets/example-dependency-full.html` — full editorial
