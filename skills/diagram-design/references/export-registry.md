# Export block registry (`--registry`)

Emit a machine-readable `.registry.json` sidecar of a Traceable block decomposition diagram's `data-block-*` metadata. **Manual only — never run unprompted, and only on `--registry`.**

## Trigger

Load this file when:

- The user invokes `/diagram-design:export-diagram <html-file> --registry` (alone or combined with `--svg-only`/`--png-only`/`--scale`/`--output`).
- The user asks in natural language for the block metadata, ID list, registry, or traceability data behind a Traceable block decomposition diagram (see [`semantic-patterns.md` § 8](semantic-patterns.md)) as structured data rather than a picture.

This reference governs `--registry` only. SVG/PNG rasterization is a separate procedure — see [`export.md`](export.md). The two can run in the same command invocation but share no logic; treat this as independent, not an extension of that one.

## Scope

The registry captures exactly what's already authored in the source HTML's `data-block-*` attributes (defined in [`semantic-patterns.md` § 8](semantic-patterns.md)) — nothing more. It is a **projection, not a second source of truth**: every value in the JSON must trace back to an attribute value literally present in the file. This procedure never infers, summarizes, or supplements a block's record from diagram text, node position, or its own judgment.

Applies only to diagrams using the Traceable block decomposition pattern (Tree nodes carrying `data-block-id`). Any other diagram — including a plain Tree diagram not using the pattern — has no blocks to extract; see *Edge cases*.

## JSON schema

```json
{
  "source": "example-tree-block-decomposition.html",
  "blocks": [
    {
      "id": "PAY-001",
      "name": "Payment Gateway",
      "output": "Settled transaction record",
      "constraint": "Every transaction reaches exactly one terminal state",
      "impl": "src/payments/gateway/"
    },
    {
      "id": "PAY-001-01",
      "parent": "PAY-001",
      "name": "Card Authorization",
      "input": "Raw card details from checkout",
      "output": "Authorization token or decline",
      "constraint": "Never persists a raw card number",
      "assumption": "Runs behind the PCI-scoped boundary",
      "impl": "src/payments/authorization/"
    }
  ]
}
```

- `source` — basename of the HTML file the registry was generated from.
- `blocks` — one entry per node carrying `data-block-id`, in document order: the order the matched nodes appear in the source file, never re-sorted by parent. A tree authored row by row (every Tier 1 node, then every Tier 2 node) exports in that row order; only a tree authored depth-first exports depth-first.
- `id`, `name` — always present; every block in the pattern requires both attributes.
- `parent` — present only for non-root blocks, mirroring `data-block-parent`'s own absent-means-root convention. Omitted, never `null`, for a root block.
- `input`, `output`, `constraint`, `assumption`, `impl` — present only when the matching `data-block-*` attribute is present on that node. Omit the key entirely rather than writing an empty string.

No other keys, and no generation timestamp: the registry is meant to be regenerated on demand and diffed in version control, and a live-clock field would make two runs over identical source produce different output. Provenance and dating come from git history, not the file's own content.

## Procedure

1. Read the source HTML file.
2. Find every element carrying a `data-block-id` attribute. Nodes without it aren't part of the pattern — skip them silently, including in a diagram that mixes pattern and non-pattern Tree nodes.
3. For each matched node, read `data-block-id`, `data-block-parent`, `data-block-name`, `data-block-input`, `data-block-output`, `data-block-constraint`, `data-block-assumption`, `data-block-impl` — whichever are present. Map `data-block-name` to the JSON key `name`; map the rest by dropping the `data-block-` prefix.
4. Preserve attribute values verbatim — no trimming beyond surrounding whitespace, no case changes, no re-formatting of the `impl` path.
5. Assemble the `blocks` array in document order, as defined under *JSON schema* above.
6. Write to `<basename>.registry.json` next to the source (e.g. `example-tree-block-decomposition.html` → `example-tree-block-decomposition.registry.json`). Honour an explicit `--output` path if the user provided one to the parent export command.

## Edge cases

- **No `data-block-id` attributes anywhere in the source**: refuse and tell the user; don't write an empty `{"blocks": []}` file. This is very likely `--registry` requested on a diagram that doesn't use the pattern at all — say so.
- **Duplicate `data-block-id` values**: emit every matching entry in document order; don't deduplicate or pick one. A duplicate ID is a correctness problem for `scripts/verify-block-registry.py` to catch, not for export to silently resolve.
- **`data-block-parent` pointing at an ID absent from the file, or a parent cycle**: emit the data exactly as authored, including the broken or cyclic reference. Same reasoning as duplicates — export mirrors the source; `scripts/verify-block-registry.py` is the structural check, and running it is a separate, explicit step, not implied by `--registry` itself.
- **Source is `assets/index.html`** (the gallery): refuse, same as the SVG/PNG path — ask which specific diagram file.
- **`--registry` combined with `--svg-only` or `--png-only`**: independent outputs — produce the registry JSON in addition to whichever raster/vector format was requested. `--registry` has no interaction with `--scale`; it produces no image.

## What this never does

- Validates ID uniqueness, parent resolution, or cycles. That's `scripts/verify-block-registry.py` — run it as its own step, not implied by export.
- Correlates a block's metadata against its drawn position or connector geometry. Out of scope for the registry entirely, not just deferred — the JSON is a metadata projection, not a geometry audit.
- Writes a generation timestamp, tool version, or any field not literally sourced from a `data-block-*` attribute.
- Modifies the source HTML.
- Auto-emits `.registry.json` without `--registry` explicitly passed. Manual on every call, same as SVG/PNG export.
