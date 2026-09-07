# Database Schema

**Best for:** the *physical* schema — real tables, real SQL types, real constraints, real indexes, and foreign keys that connect one column to another column. It's the DDL made legible: migrations, review of a real database, and anything where the column type or the `ON DELETE` behavior is the point.

**Not for domain modeling.** [ER / data model](type-er.md) is entity-level: relationship lines join *boxes* and carry cardinality, fields are a plain list, and it's the right tool for a conceptual or domain conversation. Database schema is column-level: the FK connector anchors to the specific column row on both ends — the one capability ER doesn't have, and the reason this type exists. If you're discussing what an Order *is*, use ER. If you're discussing what happens when a row is deleted, use this.

## Layout conventions

### Table box

- **Header band** — `schema.table` (e.g. `public.orders`) in Geist sans 12px weight 600, with a rectangular type tag (`rx=2`, NOT a pill) reading `TABLE`. A hairline separates it from the body.
- **Column rows** — fixed 24px row height so connectors can anchor predictably. Each row: column name in Geist sans 12px anchored left, SQL type in Geist Mono 9px `muted` anchored right (`uuid`, `text`, `numeric(12,2)`, `timestamptz`), and constraint chips between them as small `rx=2` tags in Geist Mono 8px: `PK`, `FK`, `UQ`, `NN`. Alternate row background `ink @ 0.02` on even rows for scannability.
- **Overflow row** — when a table has more columns than the budget allows, the last row is a Geist Mono 9px `muted` line: `+ N more columns`. Never silently truncate a table without saying so.
- **Index compartment** — an optional final compartment separated by a hairline, labelled with a Geist Mono 8px uppercase `INDEXES` eyebrow, listing index names in Geist Mono 9px (`idx_orders_customer_id`, `uq_products_sku`). List only the indexes that matter to the story, not every index on the table.

### Foreign-key connectors — the defining rule

Each FK edge starts at the **vertical centre of its source column row** and ends at the **vertical centre of the referenced column row**, routed with orthogonal rounded elbows (see SKILL.md §6 and [type-architecture.md](type-architecture.md) for the elbow formula and bridge/hop primitive). Label each edge in Geist Mono 8px with its referential action — `ON DELETE CASCADE`, `ON DELETE RESTRICT`, `ON DELETE SET NULL` — masked with the standard 6–10px gap. Fixed 24px row height guarantees ≥12px separation only when two FKs attach to *different* rows on the same table edge — the row spacing itself is the fan. When two or more FKs attach to the *same* row on the same edge (e.g. two child tables both referencing the same parent's primary key), anchoring all of them at the exact row centre would collide at a single point, which SKILL.md §6 rule 4 forbids. Offset each attach point symmetrically around the row's vertical centre instead — ±8px for two edges, keeping every point inside the row's 24px band and ≥12px from its neighbor — so each connector still reads as attaching to that row while remaining independently traceable.

### Schema grouping

Tables in a non-default schema sit inside a containment rect (`rx=8`, `ink @ 0.02` fill, `ink @ 0.20` stroke dashed `4,4`) with a Geist Mono 8px uppercase tracked schema label in its top-left corner. Draw the group rect first so tables paint over it.

### Focal rule

The 2 accent elements are: (1) the one destructive FK (`ON DELETE CASCADE`) — the edge and its label count together, since a labelled edge is one thing; and (2) the table that FK cascades into, carrying `accent-tint` on its **header band only**, never on the whole box. Nothing else on the diagram is `accent`.

If a schema has no destructive FK, it has no focal element. Leave it unaccented rather than promoting an arbitrary table.

## Complexity budget

Max 5 tables, max 8 column rows shown per table, max 6 FK edges, max 2 accent elements. Over budget → show the subsystem, not the database, and say so in a caption.

## Anti-patterns

- Drawing every column of every table — a schema diagram is an argument about a subsystem, not a `\d+` dump.
- FK lines that connect box to box instead of column to column — that's ER, use ER instead.
- Missing SQL types — the type is half the content.
- Unlabelled FK edges — the `ON DELETE` behavior is what a reviewer is looking for.
- Constraint chips on every row until the chips are the noise.
- Index compartments listing every index rather than the ones that matter to the story.
- Mixing conceptual entity names with physical table names in one diagram.

## Examples

- `assets/example-db-schema.html` — minimal light
- `assets/example-db-schema-dark.html` — minimal dark
- `assets/example-db-schema-full.html` — full editorial
