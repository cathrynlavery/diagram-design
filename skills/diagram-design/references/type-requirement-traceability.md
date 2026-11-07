# Requirement traceability

**Best for:** answering which identified requirements come from a source, have a design element that satisfies them, and have a test or inspection that verifies them. The fixed source × requirement × design × verification trace makes an absent link visible. Use it only when the IDs and relationships come from supplied sources. An illustrative example must say so.

**Not this type:** A generic package dependency graph has no required requirement or verification column; use [Dependency graph](type-dependency.md) for that. Use [Heatmap](type-heatmap.md) when each cell encodes a value rather than a cited element ID and a typed relationship. Use [UML class](type-uml-class.md) for type structure and inheritance.

## Layout conventions

- One row per requirement, in a stable source order. Four fixed columns: **Source**, **Requirement**, **Satisfied by**, **Verified by**. The latter two headings state the relationship direction without relying on arrow placement.
- Each source cell prints a source ID and citation. Each requirement cell prints a stable ID and short statement. Each linked cell prints its element ID and short name. Its relationship type is visible in the column heading and in the cell label.
- Keep the three cells on the same horizontal row. Separate rows with a solid neutral rule. Do not draw links across rows or rely on color alone to imply coverage.
- If a relationship is absent in real input, show `No linked element` or `No verification` in its cell. Do not invent a link or turn a missing relationship into an empty box.
- Preserve one focal row at most. Accent may mark a coverage gap or an important requirement, but the text must name the condition.

### Machine-readable contract

Each row is a `<g data-trace-row="REQ-ID" data-trace-source="source reference">` containing:

- one source and one requirement with `data-trace-kind`, unique `data-trace-id`, and a visible matching ID;
- an optional design and test element with the same kind and ID attributes;
- one `derives` relationship from source to requirement;
- one `satisfies` relationship from design to requirement, or an explicit missing relationship;
- one `verifies` relationship from test to requirement, or an explicit missing relationship.

Relationships use `data-trace-rel`, `data-trace-from`, and `data-trace-to`. A missing relationship uses `data-trace-missing="true"` and `data-trace-to` with no `data-trace-from`. The row ID and printed ID must agree. Every endpoint must be an authored ID in the same SVG. An ID is not evidence that the relationship is true; the source reference and visible label are still required. `scripts/verify-requirement-traceability.py` checks the structural contract for the shipped examples.

## Complexity budget

- At most 6 requirement rows, each with one primary design link and one primary verification link in this overview. Split complex many-to-many trace data into an overview and a detail or use a table.
- At most one focal row. Do not shrink text to fit more rows.

## Anti-patterns

- Anonymous boxes, untyped lines, or a design-to-test arrow presented as proof that a test verifies the requirement.
- A green status that hides a missing test ID or source reference.
- Repeating one test across requirements without checking that it actually verifies each requirement.
- Treating an illustrative specimen as evidence of a real system's compliance.

## Examples

- `assets/example-requirement-traceability.html` — minimal light, illustrative account-access requirements.
- `assets/example-requirement-traceability-dark.html` — the same illustrative trace on the dark skin.
- `assets/example-requirement-traceability-full.html` — full editorial page with reading notes.
