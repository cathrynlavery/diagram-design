# ADR 0011 — Waterfall is a running-total grammar, not a bar variant

**Status:** accepted

## Context

Issue #187 asked for signed contribution bridges — a budget P&L walk, headcount deltas, conversion leak/gain — where a reader sees how a start total becomes an end total. ADR 0002 sets the bar for growth: a new type is justified only when a genuinely new **layout grammar** appears; a new *behavior* is a semantic pattern routed onto an existing type.

The nearest candidates were audited against that bar:

- **Bar** compares independent categories against one baseline; nothing forces the bars to reconcile.
- **Dumbbell** (a Bar variant) states exactly two endpoints and the distance between them — it deliberately hides what happened in between. Its own reference says the connector "encodes the distance between two values and nothing about what lies between them."
- **Pyramid / funnel** ranks a monotonic drop-off; a waterfall's contributions change sign.
- **Sankey** conserves a quantity that splits and merges across stages; a waterfall is strictly sequential, one running scalar, no branching.
- A **stacked bar** shows parts of one total at one moment; it cannot state a path.

No existing grammar forces (a) totals anchored at the domain floor, (b) bridge bars floating between two running levels, and (c) the running total carried across every gap. Those three constraints *are* the figure.

## Decision

Add **Waterfall** as visual type #40 with the full §10 shipping set: `references/type-waterfall.md`, the three example variants, a gallery tab, the selection-table row and frontmatter hook, a §7 budget row (8 bars including both totals, at most 1 subtotal), the canonical screenshot, and an executable contract.

The grammar is declared, not inferred: each bar states `data-role` (`total` / `delta` / `subtotal`), a signed `data-value`, and `data-name`; each connector states the running total it transports in `data-carry`. `scripts/verify-waterfall.py` recomputes the walk from the declarations and fails on conservation, scale, bridge-geometry, carry, printed-label, or sign-treatment drift; `scripts/test-verify-waterfall.py` proves both polarities per ADR 0005.

Two scoped departures, mirroring the dumbbell's precedents:

- **Sign is encoded by fill weight, not hue** — increases take the bar family's default tint, decreases are hollow — so direction survives greyscale and colour-vision deficiency, and the accent stays editorial (≤1 focal bridge).
- **Data coordinates round to the nearest pixel and are exempt from the 4px layout grid**; snapping a running level moves money that does not exist.

## Consequences

- The verifiable count moves to 40 in `verify-docs-sync.py`, `verify-semantic-motion.py`, the screenshot catalog scripts, and ADR 0002's amendment log — a conscious edit, by design.
- The ADR 0004 byte cap was paid the ADR 0007 way, by trimming SKILL.md body prose (an illustrative §6 rule-5 example clause and the §10 consultant-row detail, both of which live in full in their routed references) — never the frontmatter description.
- `type-bar.md` needed no scope edit: its dumbbell section already disclaims the in-between path, and `type-waterfall.md` routes the two-endpoint case back to it, so the router stays unambiguous in both directions.
- Waterfall obeys §6 in full; its horizontal carries connect bars that share a y-level, which is the case plain straight lines are reserved for.
