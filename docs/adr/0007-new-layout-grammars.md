# ADR 0007 — Ten new layout grammars (28 → 38 visual types)

**Status:** accepted (v2.5.10)

## Context

ADR 0002 fixed the taxonomy at 27 and set the bar for growth: a new type is justified only when a **genuinely new layout grammar** appears, not when a new *behavior* does — behavior is a semantic pattern routed onto an existing type.

Three coverage audits ran against that bar. The first compared the skill to the Mermaid 2026 taxonomy (29 diagram types) plus current practitioner writing. The second worked through a 20-item request list covering architecture, flows, API/integration, database, and process figures. The third covered UML, story mapping, and physical database diagrams. Between them, ten figures turned out to be undrawable with any existing grammar.

## Decision

Add ten types, each with the full §10 shipping set (type reference + light/dark/full examples + gallery tab + routing row + budget row):

| Type | The grammar that did not exist | Nearest existing type, and why it fails |
|---|---|---|
| **Sankey** | Band width encodes a quantity that splits and merges | Pyramid shows drop-off but not splits/merges; process shows steps, not amounts |
| **Fishbone** | Angled category bones converging on one effect | Tree is parent→children, not cause→effect at a fixed angle with sub-cause ticks |
| **Wardley map** | Two ordinal axes (value chain × evolution) with dependency links and movement | Quadrant positions items but has no dependency chain and no evolution bands |
| **Kanban** | State census in columns with WIP limits and **no connectors** | Swimlane is lanes plus a flow crossing them; a board deliberately has no flow |
| **User journey** | Stage grid plus a sentiment curve as the load-bearing element | Timeline places events on an axis; line charts plot data, neither carries per-stage rows |
| **Deployment** | Physical placement: zones containing hosts containing versioned artifacts, with replica counts and protocol:port paths | Architecture is logical components and relations; high-level is one fixed stack shape, not an arbitrary environment topology |
| **Dependency graph** | Ranked DAG where a node has **many parents** and a **cycle** is representable | Tree structurally forbids both — a single parent per node, and no back-edges |
| **UML class** | Three-compartment boxes with an operations list, plus the typed relationship vocabulary where the arrowhead carries the meaning (triangle, filled diamond, hollow diamond) | ER has no operations compartment and no inheritance or ownership semantics |
| **Story map** | Narrative-ordered backbone crossed by release slices, with a release cut line | Kanban's columns are state, not narrative order, and it does not slice; journey carries sentiment, not scope |
| **Database schema** | Foreign keys that anchor **column row to column row**, with SQL types, constraint chips, and index compartments | ER joins *boxes* and stops at cardinality — it cannot point at a column |

## Rejected, with reason

Kept out on purpose, so the next audit does not relitigate them.

**Already covered by an existing type — the request names a use case, not a grammar:**

| Requested | Covered by |
|---|---|
| System context, component, API interaction | **Architecture** (a boundary or a zoom level, not a new grammar) |
| UML sequence, request lifecycle, sequence/state combination | **Sequence** |
| UML state machine | **State** |
| UML activity, activity diagram | **Swimlane** + **flowchart** — the fork/join bar alone does not earn a type |
| UML component, UML deployment | **Architecture**, **deployment** |
| Data flow diagram (DFD) | **Data flow** |
| Event flow (producer → broker → consumers) | **Data flow** via the fan-in queue / bottleneck semantic pattern (ADR 0002) |
| Integration diagram | **DP integration** |
| Data model, conceptual ER | **ER** |
| Decision tree | **Flowchart** |

**Rejected on the ADR 0002 bar or on editorial fit:**

- **C4 (context / container / component)** — a zoom-level convention over the architecture grammar, not a new one. Semantic-pattern territory.
- **AI-agent / RAG architecture** — same: boxes and arrows with a decision loop. A pattern over architecture, not a layout.
- **Mindmap** — radial restatement of tree. Same information, same grammar, different projection.
- **UML use case** — stick-figure actors and ovals inside a system boundary. A real grammar, but the ovals carry no structure and the figure rarely survives an editorial cut.
- **Pie / donut** — the repository's own rule ("lists of anything → a table") already rejects it.
- **Git graph and packet / bit-field** — real grammars, but narrow audiences and weak editorial fit. Revisit only on demand.
- **Treemap** — originally rejected here, then overtaken by the implementation admitted in #87 under ADR 0002's escape clause. The 28 → 38 count includes it.

## Consequences

- The verifiable count moves to 38. `verify-docs-sync.py` and `verify-semantic-motion.py` both hardcode it, by design: adding a type must be a conscious edit, not a silent drift.
- Four of the ten carry a documented, narrow exemption from §6 rule 1 (orthogonal elbows): sankey ribbons, fishbone bones, wardley dependency links, journey sentiment curves. Each exemption is scoped in its own type reference and covers that element only. The other six obey §6 in full; kanban and story map simply have no connectors.
- **ER's scope was narrowed, not duplicated.** `type-er.md` now states that it is entity-level and points at `type-db-schema.md` for the physical schema. Without that edit the two types would have overlapping "Best for" claims and the router would be ambiguous.
- The ADR 0004 byte cap became binding. Adding these types required trimming SKILL.md body prose: the §11 import consequences were compressed, the terminal-variant and typography paragraphs were tightened, and §4's six connector anti-pattern rows collapsed into one row pointing at §6 — that table was the third statement of rules already given in full in §6 and checked one by one in §9. `SKILL.md` sits at ~39.2 KB against the 40 KB cap. The next type must be paid for the same way, never by trimming the frontmatter description.
- Per-type budget rows stayed in SKILL.md §7 rather than moving into the type references, because several older references (venn, pyramid, layers, ER, swimlane, timeline) do not state their own limits. Moving the rows out would have lost those numbers.
- At acceptance time, `docs/screenshots/` had no PNGs for the new types; README listed them in a text table pending generation.

## Amendment — canonical screenshots shipped

The ten types now have canonical PNGs, image-grid entries in README, and source/screenshot digests in `docs/screenshots/manifest.json`. Polar was admitted separately afterward and moved the repository-wide count from 38 to 39; this ADR still records the ten-type 28 → 38 decision.
