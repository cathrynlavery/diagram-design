# ER / Data Model

**Best for:** database schemas, API resource relationships, domain models.

## Layout conventions
- Each entity is a two-section box:
  - **Header**: type tag (`ENTITY`) + entity name in the `node-name` role.
  - **Body**: field list in the `sublabel` role, one per line. PK prefixed with `#`, FK prefixed with `→`.
- Relationships: lines between entities with cardinality at each end:
  - `1`, `N`, `0..1`, `1..*` in the `arrow-label` role, 8px, placed 10–12px from the entity edge.
  - Optional relationship label ("has", "belongs to") centered on the line.
- Group related entities close; lay out so most relationships are straight lines, not tangles.
- Coral on the aggregate root or central entity of the model.

## Anti-patterns
- Drawing an arrow for every FK on a model with dozens — lay out by cluster instead.
- Inconsistent cardinality notation between ends of the same relationship.
- Fields padded to equal-height boxes — natural height by content is fine.

## Examples
- `assets/example-er.html` — minimal light
- `assets/example-er-dark.html` — minimal dark
- `assets/example-er-full.html` — full editorial
