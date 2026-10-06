# ADR 0012 — Architecture delta synchronizes two topologies and their change ledger

**Status:** accepted

## Context

[Issue #227](https://github.com/cathrynlavery/diagram-design/issues/227) asks for structural change between two system snapshots: added, removed, changed, moved, and rewired objects. ADR 0002 permits a new visual type only when its layout grammar is new.

Architecture arranges one topology; it has no rule preserving identity or coordinates across two states. A comparison table aligns attributes but does not constrain nodes and relationships. Sequence and Timeline explain order in time rather than two matched topologies. A semantic overlay on any one of these would leave the essential synchronization unspecified.

The new grammar is **Before · Changes · After**: two equal local grids joined by an exact, object-addressable change ledger. The unchanged positions and stable identities are part of what the drawing asserts, rather than optional editorial choices.

## Decision

Add **Architecture delta** as a canonical visual type with a routed reference, three order-fulfilment example variants, gallery entry, selection and budget rows, discovery hooks, canonical screenshot and thumbnail, and an executable public HTML contract. Counts move together with the current canonical catalog. The issue's requested merge sequencing behind Heatmap #164 and Unit grid #198 remains a release-integration concern; this decision does not claim those types have already landed or reserve their ordinal positions.

The contract uses one `svg[data-diagram="architecture-delta"]`, two `g[data-snapshot]` groups, and matching `data-grid` declarations. Only snapshot groups may translate geometry, establishing panel origins while preserving directly comparable local component positions. Every component group and relationship path carries a stable `data-object-id`, a `data-kind`, a nonempty `data-signature`, and explicit `data-status` tokens. Components expose their actual rectangle through `data-role="bounds"`; relationships declare ordered `data-from` / `data-to` IDs and draw endpoints on those components' perimeters.

Status describes a difference, not an author-selected decoration:

- **ADDED** and **REMOVED** follow actual membership in After and Before respectively.
- **CHANGED** requires different semantic signatures on the retained ID.
- **MOVED** requires different local x/y coordinates on a retained component.
- **REWIRED** requires a different ordered endpoint pair on a retained relationship.
- **Unchanged** preserves the applicable semantic and geometric values. A path may reroute to follow a moved endpoint component without changing relationship identity or connectivity.

A retained object uses the same status set in both snapshots. `changed moved` and `changed rewired` are permitted combinations; presence/absence states and `unchanged` are exclusive. Each declared difference has exactly one visible ledger text entry keyed by `(data-target, data-change)`. A two-change object has two ledger entries. The budget is eight unique components, ten unique relationships, and eight ledger entries across the entire comparison.

Text plus shape/dash differences carries each state; color is secondary and the existing skin's accent remains editorial. No new status palette or exceptions to the accessible SVG contract are introduced.

`scripts/verify-architecture-delta.py` enforces the contract with the stdlib HTML parser. The parser recognizes real attributes and inherited snapshot membership rather than searching tag strings. It fails closed on malformed/empty declarations, ambiguous membership, duplicate identity or metadata, unsupported transforms, non-finite geometry, hidden/nonrendering metadata carriers, missing or extra ledger coverage, and inconsistent signatures, positions, or endpoints. `scripts/test-verify-architecture-delta.py` includes valid alternate grids and panel origins, composite changes, all three shipped variants, and adversarial cases for every differential rule, in the spirit of ADR 0005.

## Consequences

- Adding this grammar requires the complete new-type shipping set and synchronized catalog/count changes; it does not expand the semantic-pattern count.
- Matching positions mean an author cannot independently tidy either topology after comparison. A real relocation needs an explicit `MOVED` record.
- A semantic signature is an authored canonical description, not a hash of SVG markup. It excludes layout, styling, snapshot, status, identity, and endpoints so that separate change categories remain meaningful.
- The verifier establishes internal agreement, not the truth of an external system. It cannot infer whether an author omitted a real component or lied in a signature. Labels, redundant status treatments, intermediate connector clearance, complex CSS/rendering behavior, and desktop/mobile readability still need the existing lint/render gates and visual review.
- The SKILL.md byte cap remains 40,000 bytes with at least 500 bytes of headroom for this addition. Detailed contract prose belongs in the routed reference, preserving trigger vocabulary in the index.
- Manifest versions stay untouched; the eventual release uses the existing automated release process. No dependency's unmerged ordinal or version is fabricated to make this addition appear integrated ahead of its requested sequence.
