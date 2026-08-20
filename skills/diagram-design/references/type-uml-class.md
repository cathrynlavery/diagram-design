# UML Class Diagram

**Best for:** the static structure of an object model — classes, what they own, what they inherit, and what they merely depend on. The distinguishing content is the **operations compartment** and the **typed relationship vocabulary** (the arrowheads carry meaning). ER cannot express either — use this type only when operations or the inheritance/composition vocabulary are the point of the diagram, and `type-er.md` when the story is entities and cardinality.

**Other UML diagrams — route elsewhere.** UML is a family; only the class diagram gets its own grammar here:

| UML diagram | Use instead |
|---|---|
| Sequence | [type-sequence.md](type-sequence.md) |
| State machine | [type-state.md](type-state.md) |
| Component | [type-architecture.md](type-architecture.md) |
| Deployment | [type-architecture.md](type-architecture.md) |
| Activity | [type-swimlane.md](type-swimlane.md) or [type-flowchart.md](type-flowchart.md) |
| Conceptual / domain ER | [type-er.md](type-er.md) |

## Layout conventions

- Each class is a **single box** (`rx=6`), divided by full-width hairlines into up to three compartments. Compartment heights follow content — never pad to a uniform height.
  1. **Name** — class name in Geist sans, 12px, weight 600, **centered**. An interface carries a Geist Mono 8px `«interface»` stereotype line above the name. An abstract class sets the name in *italic*.
  2. **Attributes** — one line each, Geist Mono 9px, left-aligned: `+ name: Type`. Visibility markers: `+` public, `-` private, `#` protected.
  3. **Operations** — one line each, Geist Mono 9px, left-aligned: `+ method(arg): Return`.
  Omit a compartment entirely when a class has no members in it (an interface with no attributes skips that compartment).
- Attribute/operation lines are a single combined string, not the two-column field/type layout ER uses — that visual distinction keeps the two types from reading the same.
- Coral (accent) is reserved for the class being implemented or extended (the focal type) — accent-tint fill, accent stroke. Its inbound inheritance/realization edges count as **one** additional accent element (treated as a group), for 2 accent elements total per diagram.

## Relationship vocabulary

Define every marker used in `<defs>` and show all six in the legend, even the ones not used in the diagram body — the legend is this type's complete grammar reference.

| Relationship | Line | Ending (at the target/owner end) |
|---|---|---|
| Inheritance (`extends`) | solid | large **hollow triangle** — `paper` fill, `ink` stroke |
| Realization (`implements`) | dashed `5,4` | same hollow triangle |
| Composition (owns, cascades) | solid | **filled diamond** at the OWNER end, `ink` fill |
| Aggregation (has, independent) | solid | **hollow diamond** at the OWNER end |
| Association | solid | plain open arrowhead, multiplicity at BOTH ends |
| Dependency (uses) | dashed `4,3` | plain open arrowhead |

Multiplicities (`1`, `0..*`, `1..*`) sit in Geist Mono 8px, 10–12px off the box edge, on an opaque mask over the line — same convention as ER cardinality labels.

## Connector rules

All six SKILL.md §6 connector rules apply in full — orthogonal rounded elbows (`r=8`), no diagonals, bridge/hop for unavoidable crossings, fanned attach points ≥12px apart when several relationships share an edge, masked labels with the 6–10px gap, connectors drawn before boxes. Prefer laying classes out so relationships resolve to straight lines or single-elbow routes; a class diagram with every edge bridging is over budget — split by package instead.

## Complexity budget

Max 7 classes, max 8 relationships, max 5 members per compartment (overflow becomes a Geist Mono `…` line), max 2 accent elements. Over budget → split by package.

Seven is the ceiling rather than the target. Three compartments per box makes a class diagram dense fast, so treat 4–5 classes as the normal size; the shipped example uses all seven only because it doubles as the legend for the full relationship vocabulary.

## Anti-patterns

- Getters and setters listed as operations — they're noise; show behavior that matters.
- Every attribute and method dumped in — a class diagram is an argument, not a header file.
- Composition and aggregation used interchangeably — the filled diamond means the part dies with the whole. Say so, or use the hollow diamond.
- Association arrows with no multiplicity.
- Drawing a class diagram when there's no inheritance and no operations — that's ER.
- Stereotype guillemets on everything, not just the interfaces/abstracts that need them.
- Boxes padded to equal height.

## Examples

- `assets/example-uml-class.html` — minimal light
- `assets/example-uml-class-dark.html` — minimal dark
- `assets/example-uml-class-full.html` — full editorial
