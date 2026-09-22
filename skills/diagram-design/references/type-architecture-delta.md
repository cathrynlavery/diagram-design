# Architecture delta

**Best for:** explaining a system migration, service extraction, infrastructure redesign, or integration change through two synchronized topology snapshots. Show which components and relationships survive, appear, disappear, change their properties, move, or reconnect.

**Not this type:**

- One system snapshot → **Architecture** (`type-architecture.md`).
- Attribute-only differences without a topology story → a **comparison table**. Two versions of a configuration do not need two node maps.
- Requests over time → **Sequence** (`type-sequence.md`); deployment phases → **Timeline** (`type-timeline.md`). A delta has exactly two states and does not establish migration order, downtime, or causality.
- Host/container placement in one environment → **Deployment** (`type-deployment.md`).

## Layout conventions

- **Three panels, one reading order: Before · Changes · After.** Both topology panels use the same width, height, and internal grid pitch. The center panel is a short change ledger, not a third topology. Name the two snapshots with meaningful versions or dates.
- **Keep the mental map stable.** Start by copying the Before coordinates into After. Move a retained component only when its movement is part of the story and receives a `MOVED` entry. Do not independently run a layout algorithm on each panel.
- **Panel positions are not component positions.** Put each snapshot in one SVG `<g transform="translate(x y)">`; write component bounds and relationship paths in local coordinates. The Before and After origins share one y-coordinate, with the ledger occupying the horizontal gap.
- **Shared grid:** use a 4px pitch by default. Every component's local x, y, width, and height is a multiple of that pitch. The shipped example uses two `336 480 4` grids; scale the overall SVG responsively without changing their local geometry.
- **Budget:** at most **8 unique components**, **10 unique relationships**, and **8 ledger entries** across the complete comparison. A retained ID counts once, not once per snapshot. A component that is both changed and moved consumes two ledger entries. Split larger migrations into named subsystems or phases; never drop edges to fit.
- **Connectors:** use Architecture's rounded orthogonal routing and port rules. In this type, even straight connectors are `<path>` elements so relationship identity and endpoints have one grammar. Draw paths before components. A stable relationship may take a different route to meet a moved component without becoming `REWIRED`.
- **Nodes:** print the same stable ID in both states along with the human-readable name. Treat names, responsibilities, implementation versions, and protocols as semantic attributes; identities survive a rename when the underlying object survives.
- **Ledger:** one brief entry per `(object ID, change)` pair. Begin with the uppercase change word, name the object, and state the actual difference. Do not describe unchanged objects in the ledger. Keep a readable text measure, with wrapped `<tspan>` lines when needed.
- **Responsive presentation:** preserve the three-panel comparison on small screens with an accessible horizontal scroll region and a visible scroll hint. Do not compress labels until they become illegible or stack snapshots into independently scaled pictures. Print and export keep the whole comparison.

## Change vocabulary and redundant encoding

Color is secondary. Every change is readable from text plus a shape or line treatment; unchanged objects remain quiet context. Use the existing skin tokens and reserve the accent for the editorial focus, rather than assigning five status colors.

| State | Meaning | Non-color treatment |
|---|---|---|
| `unchanged` | Same identity, semantics, position, and endpoints | Plain solid outline; no ledger entry |
| `added` / **ADDED** | Present only in After | `+` badge or plus-shaped marker; solid outline |
| `removed` / **REMOVED** | Present only in Before | `−` badge and dashed outline/path |
| `changed` / **CHANGED** | Retained object whose semantic signature differs | `Δ` badge or inset rule, plus an explicit old → new ledger description |
| `moved` / **MOVED** | Retained component whose local x or y differs | Direction/position marker and a ledger entry naming the relocation |
| `rewired` / **REWIRED** | Retained relationship whose ordered source/target IDs differ | Distinct dash treatment or endpoint marker, with old → new endpoints written in the ledger |

Do not use a missing After node to stand for a removal without a `REMOVED` entry. Do not substitute an `ADDED` edge for a `REWIRED` edge just to avoid explaining endpoint identity. A replacement component gets a new stable ID and separate removal/addition entries; its location alone cannot establish continuity.

## Public HTML metadata contract

This is the authoring and validation surface, not a serialization inferred from visible labels. All attributes below are required where applicable; empty, boolean, duplicate, or malformed declarations are findings. IDs are case-sensitive and match `[A-Za-z][A-Za-z0-9_.:-]*`; they contain no whitespace.

### Diagram and snapshots

The file has exactly one `<svg data-diagram="architecture-delta">`. Keep the standard accessible SVG title/description contract. Two direct child `<g>` elements declare `data-snapshot="before"` and `data-snapshot="after"`. Each has:

- `data-grid="<width> <height> <pitch>"`: the same three positive finite numbers in both panels. Width and height are multiples of pitch.
- `transform="translate(<x> <y>)"`: exactly one finite two-number translation, solely for the panel origin. Comma-separated translations are also accepted.

Snapshot membership is inherited from the enclosing group. An object cannot be outside both snapshots, in nested snapshots, or nested inside another object. Other geometry transforms, nested SVG viewports, SVG animation, `<use>`, and foreign objects are outside this static grammar. Do not put objects or ledger entries in `<defs>`, `<symbol>`, templates, or other nonrendering containers.

### Components

Each component is a `<g>` declaring:

| Attribute | Contract |
|---|---|
| `data-kind="component"` | Identifies a component group |
| `data-object-id` | Stable object identity, unique within each snapshot |
| `data-status` | One lowercase state or the space-separated combination `changed moved` |
| `data-signature` | Nonempty semantic signature; see the signature rules below |

The group contains exactly one **direct** `<rect data-role="bounds">` with explicit finite numeric `x`, `y`, `width`, and `height`. Position is nonnegative, size is positive, and the rectangle stays inside its local grid. All four values align with grid pitch. These are the actual drawn node bounds, not a hidden proxy rectangle.

### Relationships

Each relationship is a `<path>` with `data-kind="relationship"`, `data-object-id`, `data-status`, `data-signature`, and `data-from` / `data-to`. Its stable ID is separate from component IDs. Both endpoints resolve to component IDs in the **same snapshot**. Endpoint order is directional: swapping source and target is a rewire.

Every path inside a snapshot and outside a component is a relationship and must carry the complete metadata. Decorative paths belong inside their component, or outside the snapshot for panel rules and ledger separators. Deleting all metadata from a connector must not make it disappear from validation.

Relationship statuses are `unchanged`, `added`, `removed`, `changed`, `rewired`, or the combination `changed rewired`. `moved` applies to components only; `rewired` applies to relationships only. `unchanged`, `added`, and `removed` cannot be combined with any other token.

The `d` attribute is one absolute `M` followed by absolute `L`, `H`, `V`, `Q`, or `C` segments. Implicit repeated coordinate groups are accepted. Relative commands, additional subpaths, closed paths, arcs, missing coordinates, and non-finite coordinates fail closed. Use orthogonal lines and quadratic corners for the standard layout; cubic segments are available for a small crossing bridge. Endpoints and control points remain inside the local grid. The path's start meets the source rectangle's perimeter and its end meets the target's perimeter, within 2px for stroke/arrow-cap rounding.

### Status and signature rules

- An ID present only in Before is exactly `removed`; an ID present only in After is exactly `added`.
- A retained ID keeps its kind and the same status set in both snapshots. Never recycle a component ID for a relationship or vice versa.
- A signature differs **if and only if** the retained object is `changed`. Construct it deterministically from the semantic attributes you want to compare, such as `orders-api:v2;mode=enqueue` or `protocol=https;operation=create-order`. Include a changed display name if renaming is part of the story. Preserve attribute order and spelling when values are unchanged.
- Signatures exclude the object ID, snapshot, status, coordinates, visual styles, and relationship endpoints. These have their own checks. A movement or rewire alone must not change the signature.
- A retained component's local `(x,y)` differs **if and only if** it is `moved`. A width/height change additionally requires `changed` and a changed signature. A changed signature alone does not require different bounds.
- A retained relationship's ordered `(data-from,data-to)` pair differs **if and only if** it is `rewired`. Its path may reroute while that pair stays the same, for example when an endpoint component moves.
- Numeric declarations are finite and have absolute values no larger than 10,000,000; unit suffixes, percentages, and CSS calculations are not coordinate declarations.

### Ledger

Each entry is a visible SVG `<text>` outside both snapshots, with `data-change="ADDED|REMOVED|CHANGED|MOVED|REWIRED"` and `data-target="<one object ID>"`. Its rendered text begins with the same uppercase word and continues with an explanation. Descendant `<tspan>` text is included when checking the wording; put the metadata on the outer `<text>` only.

The ledger is an exact set of `(target, change)` pairs implied by object statuses. There are no missing entries, duplicate pairs, unknown targets, or entries for unchanged objects. The same target can have two entries only when it declares two changes. Every diagram contains at least one ledger entry, at least one component in each snapshot, and at least one relationship overall.

### Worked metadata pattern

This excerpt shows one changed component; a complete diagram also needs its other components, relationships, and accessible SVG title/description.

```svg
<svg data-diagram="architecture-delta" viewBox="0 0 1000 400">
  <g data-snapshot="before" data-grid="320 320 4" transform="translate(24 64)">
    <g data-kind="component" data-object-id="orders" data-status="changed"
       data-signature="orders-api:v1;mode=dispatch">
      <rect data-role="bounds" x="80" y="96" width="144" height="64"/>
      <text x="96" y="120">orders · direct dispatch</text>
    </g>
  </g>
  <g data-snapshot="after" data-grid="320 320 4" transform="translate(656 64)">
    <g data-kind="component" data-object-id="orders" data-status="changed"
       data-signature="orders-api:v2;mode=enqueue">
      <rect data-role="bounds" x="80" y="96" width="144" height="64"/>
      <text x="96" y="120">orders · enqueue</text>
    </g>
  </g>
  <text data-change="CHANGED" data-target="orders" x="376" y="176">
    <tspan>CHANGED orders</tspan>
    <tspan x="376" dy="20">Direct dispatch → enqueue</tspan>
  </text>
</svg>
```

## Verification and its boundaries

Run `python3 scripts/verify-architecture-delta.py --all` (or pass explicit HTML paths) and `python3 scripts/test-verify-architecture-delta.py`. No arguments also checks shipped examples. The stdlib HTML parser reads real attributes, including unquoted values and entities, ignores comments, and rejects malformed SVG nesting. Synthetic fixtures prove both legal cases and adversarial changes independently of the shipped coordinates; the light, dark, and full variants are checked too.

The verifier enforces the declared structure, differential semantics, grid/bounds geometry, drawn relationship endpoints, budgets, and exact ledger coverage. It rejects CSS transforms/position overrides, CSS sizing that could change bounds, escaped CSS declarations, explicit hidden objects/ledger, and common CSS hiding rules. Ordinary responsive sizing of the outer SVG remains legal.

It is **not** a browser renderer or a proof of the source system. Authors remain responsible for honest signatures, labels matching those signatures, readable shape/dash treatments, and an accurate migration story. Exotic CSS cascade/variable effects, clipping and occlusion, connector crossings, intermediate segment clearance, ledger placement, and screen-reader quality still require the normal skin, accessibility, geometry, and rendered-layout gates plus desktop/mobile visual review. Keep semantic geometry in the SVG attributes instead of making CSS part of the data model.

## Anti-patterns

- Two independently arranged snapshots that manufacture apparent movement.
- A center ledger that says only “updated” without naming the object and difference.
- Color-only statuses or a separate bright color for every kind of change.
- Unchanged node positions drifting to make room, with no `MOVED` entry.
- Semantic edits hidden behind an unchanged signature, or all signatures regenerated just because the snapshot changed.
- Redrawing an edge to a different component while keeping its endpoint metadata unchanged.
- Counting retained objects twice to justify dropping other objects from the comparison.
- Treating this comparison as an executable migration plan. Ordering, rollback, availability, and data consistency need their own explanation.

## Examples

- `assets/example-architecture-delta.html` — minimal light order-fulfilment migration; all five change kinds.
- `assets/example-architecture-delta-dark.html` — minimal dark, identical IDs, signatures, topology, and coordinates.
- `assets/example-architecture-delta-full.html` — full editorial treatment of the same migration.

The example retains the storefront and order store, changes the order API to enqueue work, removes the legacy dispatcher, adds a durable order queue, moves the fulfilment worker, and rewires order submission. Stable relationships follow the worker's new location while preserving their IDs and endpoint semantics.
