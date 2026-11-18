# ADR 0016 — SBGN is a bipartite process grammar

**Status:** accepted

## Context

Issue #130 asked for process-description maps of biological reactions: species as one class of node, reactions as another, every arc carrying a role (consumption, production, reversible, modulation), and an enclosing compartment. ADR 0002 sets the bar for growth: a new type is justified only when a genuinely new **layout grammar** appears; a new *behavior* is a semantic pattern routed onto an existing type.

The nearest candidates were audited against that bar:

- **Architecture** joins runtime components with untyped connectors. It has no species/process bipartition and no role-typed arcs.
- **Flowchart** draws decision branches. A reaction is not a branch.
- **Nested** shows containment. Two molecules in one cytosol and two molecules in two compartments would draw the same if the only grammar is nesting.
- **Sankey** conserves a quantity that splits and merges; it does not host process nodes or stoichiometry.
- **State machine** names states and guarded transitions of one subject, not a bipartite reaction graph.

No existing grammar forces (a) a bipartite species/process graph, (b) role-typed arcs, and (c) compartment containment as a glyph. Those three constraints *are* the figure.

## Decision

Add **SBGN** as visual type #46 with the full §10 shipping set: `references/type-sbgn.md`, the three Bruno carotenoid-cleavage example variants, a gallery tab, the selection-table row and frontmatter hook, a §7 budget row (7 macromolecules, 6 processes, 1 compartment, 2 source/sink, 16 arcs) that replaces the universal 9 node and 12 arrow rows for this type only, the canonical screenshot, and an executable contract.

The grammar is declared, not inferred: every species, process, and compartment carries a stable ID; every arc states `data-kind`, `data-from`, and `data-to`. `scripts/verify-sbgn.py` fails duplicate IDs, unresolved endpoints, an arc that skips the bipartite rule, a macromolecule drawn outside its compartment, off-grid structural geometry, and a figure over the Bruno ceiling; `scripts/test-verify-sbgn.py` proves both polarities per ADR 0005.

Two scoped decisions:

- **Authoring-only.** The model arrives as text in the prompt. This type does not import SBML or SBGN-ML; an extractor is a later, separate surface.
- **PD subset.** Process, macromolecule, compartment, source/sink, consumption, production, reversible, and modulation. No entity-relationship or activity-flow profiles. Glyphs keep SBGN's shape semantics (square process, rounded macromolecule, empty-set source/sink, circle-headed modulation) and the house palette (monochrome ink/muted, one accent).

Process squares are 32×32 so they stay below the geometry-checker's 60×40 node floor; macromolecules are the nodes the connector rules attach to.

## Consequences

- The verifiable count moves to 46 in `verify-docs-sync.py`, `verify-semantic-motion.py`, the screenshot catalog scripts, and ADR 0002's amendment log — a conscious edit, by design.
- The plugin native descriptions were at the 500-character limit. They now name SBGN, keep a distinct Architecture token so Architecture delta stays independently discoverable, and the Codex `longDescription` keeps the full names. To stay under the limit once Service blueprint landed, the native descriptions write `UML class` as `UML`, registered in `verify-docs-sync.py`'s `DESCRIPTION_ALIASES` the same way `dependency graph` and `service blueprint` already are.
- Architecture, Nested, Flowchart, and Sankey needed no scope edit: `type-sbgn.md` routes those cases back to them, so the router stays unambiguous.
