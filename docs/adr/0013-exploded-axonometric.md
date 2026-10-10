# ADR 0013: Exploded axonometric is a projection grammar

**Status:** accepted

## Context

Some figures the skill could only flatten: what is inside a phone, what comes out of the box in what order, and the layers of a product drawn as parts of one object. ADR 0002 admits a new type only when a genuinely new layout grammar appears. The nearest existing grammars were audited against that bar:

- **Layer stack** stacks full-width bands of text. A band has no footprint, no thickness, and no relationship to the object it belongs to.
- **Architecture** joins boxes with connectors; position carries no meaning of its own.
- **Nested** shows containment without order or a physical axis.
- **Deployment** places software on hosts in a logical topology with no physical object.

None of them projects a three-dimensional model, orders parts along a physical axis, or shows that two parts sit side by side inside a third. An exploded view needs all three.

## Decision

Add **Exploded axonometric** as visual type #43 with the full §10 shipping set: `references/type-exploded.md`, three example triples (app stack, phone, unboxing), two animated examples, gallery tabs, the selection-table row and frontmatter hook, a budget row (5 parts, 5 levels, 1 focal part, three detail levels), the canonical screenshot, and an executable contract.

Every part declares its geometry. It states its model box (`data-rect`, `data-z`, `data-t`) and level, and the figure states its origin and gap. `scripts/verify-exploded.py` reprojects each silhouette with one 2:1 dimetric function and fails on projection drift, unequal gaps, a gap under its floor, a level split across heights, leaders that bend, start off the part, or cross another part, crowded or multi-column labels, more than one focal part, trace lines that lean, and animated lifts that disagree with the geometry. `scripts/test-verify-exploded.py` proves both polarities per ADR 0005. `scripts/build-exploded-examples.py` builds every shipped example from the same projection, so no example coordinate is placed by hand.

Three scoped decisions:

- **One primitive.** Slab, box, and cylinder are the same rounded prism at different corner radii, and a container is that prism with a cavity. One silhouette algorithm covers every shipped part, which is what makes the verifier short enough to trust.
- **Parts can share a level.** Parts that sit side by side in the assembled object explode together. Without this a phone's board and battery stack a full gap apart, which misdescribes the object and wastes the canvas.
- **No contact shadow.** Shadows are an anti-pattern in this skin (SKILL.md §4), so the bottom part grounds the object instead.

## Motion exception

`animation.md` caps translation at 24px. An exploded view that opens as the assembled object and lifts apart needs its parts to travel their full explode distance, often hundreds of pixels, because the travel is what the figure explains. The exception is scoped to exactly that: a part may translate straight up by its declared `--lift`, which must equal its exploded `z` minus its assembled `z`, and the verifier checks the equality. Nothing else in the figure moves further than 24px, the controller stays the pinned one from `template-motion.html` (ADR 0001), the run happens once on load (ADR 0003), and the static, no-JavaScript, reduced-motion, print, and export states all show the exploded frame.

Canonical examples stay static, because the screenshot catalog captures the first SVG as soon as fonts load and an autoplaying example would be photographed mid-run. Animated versions ship as separate `-animated` files.

## Consequences

- The verifiable type count moves to 43. ADR 0002 is amended in the same change.
- The plugin manifest descriptions were already at the 500-character Cowork limit, so adding the type's lexical hook cost words elsewhere in each description.
- An axonometric site or floor plan (buildings on a plate, walls cut at desk height) uses the same projection without an explode. It is a different grammar with its own label rule (tags on roofs and floors instead of a leader column), so it is proposed as its own type.
