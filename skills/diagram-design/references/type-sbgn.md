# SBGN

**Best for:** a biological process as a bipartite species/process graph — carotenoid cleavage, a signalling cascade, a metabolic map — where each reaction is a process node, each molecule is a species node, and every arc has a role (consumption, production, reversible, modulation). Use when the reader must see *what is consumed, what is produced, and inside which compartment*.

**Not this type:**

- Boxes and arrows of a runtime system → **Architecture** (`type-architecture.md`). Architecture has no species/process bipartition and no role-typed arcs.
- Decision logic with branches → **Flowchart** (`type-flowchart.md`).
- Containment without reactions → **Nested** (`type-nested.md`). Nested shows scope; it does not host process nodes or consumption/production.
- A quantity splitting across stages → **Sankey** (`type-sankey.md`). Sankey conserves width, not stoichiometry.

Authoring-only: the model arrives as text in the prompt. This type does not import SBML or SBGN-ML.

## Layout conventions

- **Bipartite.** Every reaction is a **process** glyph (a 32×32 square). Every molecule is a **macromolecule** (a rounded rectangle). Never attach two species directly; never attach two processes directly.
- **Compartment first.** Draw the enclosing compartment (cytosol, chloroplast, nucleus) as a zone rect before arrows and nodes. One compartment in the canonical budget. Label it on a paper mask on the top edge.
- **Primary flow left → right:** substrates, then processes, then products. Fan-in to a shared product uses a dedicated vertical trunk; do not stack two productions on one y.
- **Orthogonal connectors** with `r=8` elbows (SKILL.md §6). Consumption and production take the filled arrow marker. A reversible pair is two-headed. Modulation takes the open-circle marker.
- **1 coral focal:** the species or process the figure exists to show. In the worked fixture that is beta-carotene.
- **House style, SBGN shapes.** Monochrome ink/muted, one accent. Keep SBGN's shape semantics (square process, rounded macromolecule, empty-set source/sink, circle-headed modulation) rather than colour-coding roles.

### Glyphs (PD subset)

| Kind | Shape | `data-kind` |
|---|---|---|
| Macromolecule | Rounded rect, `rx=16`, 144×64 (or 160×64) | `macromolecule` |
| Process | Square 32×32, `rx=2` | `process` |
| Compartment | Zone rect, `rx=8`, paper-mask label | `compartment` |
| Source / sink | Empty-set: circle r=12 plus a diagonal | `source-sink` |
| Consumption | Filled arrow, species → process | `consumption` |
| Production | Filled arrow, process → species | `production` |
| Reversible | Two-headed, species ↔ process | `reversible` |
| Modulation | Open-circle head, species → process | `modulation` |

```svg
<!-- Macromolecule -->
<g data-kind="macromolecule" data-entity-id="bcar" data-compartment="cyt">
  <rect data-role="bounds" x="80" y="80" width="144" height="64" rx="16" fill="#f5f5f5"/>
  <rect x="80" y="80" width="144" height="64" rx="16"
        fill="rgba(191,69,32,0.08)" stroke="#bf4520" stroke-width="1"/>
  <text x="152" y="108" …>B-carotene</text>
</g>

<!-- Process -->
<g data-kind="process" data-process-id="v1" data-compartment="cyt">
  <rect data-role="bounds" x="280" y="96" width="32" height="32" rx="2"
        fill="#f5f5f5" stroke="#2d3142" stroke-width="1"/>
</g>

<!-- Consumption / production -->
<path data-kind="consumption" data-from="bcar" data-to="v1"
      d="M 224,112 H 280" fill="none" stroke="#4f5d75" stroke-width="1.2"
      marker-end="url(#arrow)"/>
<path data-kind="production" data-from="v1" data-to="b10"
      d="M 312,112 H 480" fill="none" stroke="#4f5d75" stroke-width="1.2"
      marker-end="url(#arrow)"/>
```

The file has exactly one `<svg data-diagram="sbgn">`. Process squares are 32×32 so they stay below the geometry-checker's 60×40 node floor; macromolecules are the nodes the connector rules attach to. Source/sink circles are decoration-sized and also below that floor.

**Machine-readable contract.** Species, processes, and the compartment carry stable IDs. Every arc declares `data-kind`, `data-from`, and `data-to`. `scripts/verify-sbgn.py` fails duplicate IDs, unresolved endpoints, an arc whose `data-kind` is missing or unknown, an arc that skips the bipartite rule, a macromolecule drawn outside its compartment, a glyph or arc moved by a `transform` or positional CSS, and a figure over the Bruno ceiling. Place glyphs with `x`, `y`, `width`, and `height` only, and draw arcs in map coordinates with path data only. Every other `<path>`, `<line>`, `<polyline>`, `<polygon>`, or `<use>` in the map must be a declared arc; legend samples go inside `<g data-role="legend">`, use only `<line>`, `<rect>`, `<circle>`, and `<text>`, and stay clear of every glyph. Arcs never cross, touch, stack, or end on one another, measured on the drawn stroke including curves and corners; two arcs may share only a port on a glyph's edge. Route around first, and where the layout forces a single crossing, bridge it with the hop from [type-architecture.md](type-architecture.md#crossing-arrows--bridge--hop). The shipped map has one, where v3's product route hops v4's.

## Budget

≤7 macromolecules, ≤6 processes, ≤1 compartment, ≤2 source/sink glyphs, ≤16 arcs, 2 accent elements. This ceiling replaces SKILL.md §7's 9 nodes and 12 arrows rows for SBGN only (see [layout-budget.md](layout-budget.md#complexity-budget-per-diagram)); the other universal rows still apply. That ceiling is the [Bruno_JExpBot2016](https://github.com/Benchmarking-Initiative/Benchmark-Models-PEtab) fixture: seven carotenoid species, six cleavage reactions, one cytosol. More species → split the map (overview of the pools, then one cleavage family).

## Anti-patterns

- A species–species arrow with no process node — that is a flowchart, and it hides the reaction.
- A database or architecture box used as a macromolecule.
- Colour as the only distinction between consumption and modulation — the markers must differ, because greyscale still has to tell them apart.
- Importing SBML or SBGN-ML in this skill — author from the prompt; an extractor is a later, separate surface.
- Flattening the compartment into a caption (`all of this is cytosol`) — the compartment is a glyph.

## Examples

- `assets/example-sbgn.html` — Bruno carotenoid cleavage, minimal light
- `assets/example-sbgn-dark.html` — identical IDs, topology, and coordinates, dark
- `assets/example-sbgn-full.html` — full editorial treatment of the same map
