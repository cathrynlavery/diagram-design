# ADR 0015 — Service blueprint is a visibility-line grammar

**Status:** accepted

## Context

A journey map already shows what a person *does* and how it *feels*. The other half of the same story — what the service does in front of the customer, what stays hidden, and which support processes hold it up — had no layout grammar. ADR 0002 sets the bar for growth: a new type is justified only when a genuinely new **layout grammar** appears; a new *behavior* is a semantic pattern routed onto an existing type.

The nearest candidates were audited against that bar:

- **User journey** — the load-bearing element is a sentiment curve. No visibility line, no backstage layer, one persona's feelings.
- **Swimlane** — the load-bearing element is flow across owner lanes. Arrows are the claim. No stage census, no visibility line.
- **Process** — sequential nodes and data handoffs. No layered split of what is onstage vs offstage.
- **Kanban** — state census in columns, deliberately no connectors. Closest cousin structurally, but columns are *states*, not narrative stages, and there is no visibility line.
- **Story map** — narrative backbone × release slices. The cut line is scope, not visibility.
- **Layer stack** — abstraction bands with no stage columns.

No existing grammar forces (a) stages as equal columns, (b) required customer / frontstage / backstage rows, and (c) a visibility line that is the figure. Those three constraints *are* the figure.

## Decision

Add **Service blueprint** as visual type #45 with the full §10 shipping set: `references/type-service-blueprint.md`, the three example variants, a gallery tab, the selection-table row and frontmatter hook, a §7 budget row (6 stages, required customer/frontstage/backstage, optional evidence/support, 1 focal cell), the canonical screenshot, and an executable contract.

The grammar is declared, not inferred: each layer group states `data-layer`, each cell states `data-stage` and `data-name`, and the visibility line states `data-role="visibility"`. `scripts/verify-service-blueprint.py` fails on layer order, visibility placement and contrast, stage-grid alignment, census, focal count, budget, printed-label drift, or CSS-moved marks; `scripts/test-verify-service-blueprint.py` proves both polarities per ADR 0005.

v1 draws no connector arrows. Stage order is the sequence; wait times and system names are cell text. That is a scoped departure from swimlane, not a missing feature of it.

## Consequences

- The verifiable count moves to 45 in `verify-docs-sync.py`, `verify-semantic-motion.py`, the screenshot catalog scripts, and ADR 0002's amendment log — a conscious edit, by design.
- Native plugin descriptions pay the 500-character Cowork cap with a `blueprint` alias (and a short trim of `dependency graph` → `dependency`), matching the ADR 0014 precedent. SKILL.md frontmatter and the Codex `longDescription` keep the full name.
- `type-journey.md`, `type-swimlane.md`, and `type-process.md` each gain a one-line "Not this type" pointer so the router stays unambiguous in both directions.
