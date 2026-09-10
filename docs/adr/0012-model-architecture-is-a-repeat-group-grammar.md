# ADR 0012 — Model architecture is a repeat-group grammar (40 → 41 visual types)

**Status:** accepted

## Context

The request that prompted this was concrete: reproduce the kind of figure a model paper opens with — a transformer drawn as a stack of layer blocks where `×2`, `×3` and `×5` multipliers stand in for forty layers, two stage panels sit side by side, and side modules reach into named layers inside a repeat.

ADR 0002 sets the bar: a new type is justified only by a **new layout grammar**, never by a new subject matter. "Neural network" is a subject. The grammar question is narrower — is there an arrangement here that no existing type can express?

## Decision

Add **Model architecture** (`type-model-arch.md`), with the full §10 shipping set.

The grammar that did not exist is the **repeat group**: a dashed container around a contiguous run of blocks, labelled `×N`, nestable one level, where the multiplier is the load-bearing content. Everything else in the figure is ordinary — boxes, a spine, a panel. The multiplier is not.

Measured against the nearest candidates:

| Nearest type | Why it fails |
|---|---|
| **Layer stack** | Full-width horizontal bands, no connectors, capped at 6 layers, and no way to say a band repeats. It is the closest name and the furthest grammar. |
| **Architecture** | Logical components and relations. Depth is not one of its axes; there is no run-length operator and no ordered spine. |
| **Nested** | Containment encodes scope: "B is inside A". A repeat group encodes multiplicity: "this pair happens five times". A nested diagram cannot say the second thing. |
| **Data flow** | Ordered stages, one each. If every group in a model diagram is `×1`, data flow is the right answer — which is exactly the boundary. |
| **Process / swimlane** | Actors and handoffs; nothing repeats. |
| **Tree / dependency** | Branching, not a linear stack with a multiplier. |

Because ADR 0007 explicitly reserved the right to reject a subject dressed as a grammar, note what is *not* being admitted with it: "RAG architecture", "agent architecture", "training pipeline" and "MLOps diagram" remain architecture, data flow, or process. They are subjects. Depth-with-repetition is a grammar.

## The multiplier has to be checked, not drawn

A `×5` is arithmetic presented as decoration. It is the one element of the figure a reader cannot verify and a reviewer will not notice: a group nudged during layout, a chip that says `×4` over a group meaning five, or a plan transcribed one repeat short all render as a clean, confident diagram of a network that does not exist. Every other error this repository guards against is visible; this one is not.

So the type carries a metadata contract in the same spirit as ADR 0010's block registry, and `scripts/verify-model-arch.py` recomputes the census in CI:

- each counted block contributes the product of `data-repeat` along its group ancestry;
- the sum must equal the stage panel's `data-depth`;
- `data-depth` must equal the span of `data-layer-range`;
- every `×N` chip's text must equal the `data-repeat` of the group it labels.

Following ADR 0010's split, the verifier never inspects geometry: a group rect that does not visually enclose the blocks claiming it is a layout bug for `verify-geometry.py` and for the eye. `scripts/test-verify-model-arch.py` mutates a sound plan twenty-two ways — each mutation still renders correctly — and requires every one to be caught.

## Consequences

- The verifiable count moves to 41, in `verify-docs-sync.py`, `verify-semantic-motion.py`, `verify-screenshot-freshness.py` and `render-canonical-screenshots.py`, together with the prose in SKILL.md, README, CONTRIBUTING and the cookbook. ADR 0002 is amended in the same change, as its own enforcement procedure requires.
- **A scoped exception to the one-to-two-accent rule.** Layer variants are a categorical encoding of *how much work a layer does*, and up to four of them may be coloured, from the style guide's existing `series` tokens. This does not loosen the focal rule: `accent` still marks exactly one block, and a variant never uses it. The cap is four because the fifth colour is where a legend stops being readable — the same argument the chart types already make for series count.
- **The uniform element stays uncoloured.** An `MoE` or `FFN` block that appears in all forty layers carries no signal; tinting it would spend a colour on zero information. It is drawn only so a repeat group encloses a whole layer instead of half of one.
- The per-stack block budget (10) is the highest in the skill. That is a consequence of the grammar, not a relaxation of §7: an attention/FFN pair per row doubles the count, and the repeat groups are the only reason the figure is nine rows instead of forty.
- The ADR 0004 byte cap stayed binding. The routing row, budget row and description hook were paid for by trimming SKILL.md body prose that restated rules given in full elsewhere: the §7 "quick check" restatement of the 4px rule, the §6 dot-pattern caveat, and the §5 parenthetical listing the default palette that `style-guide.md` already tabulates. `SKILL.md` lands at 39,913 bytes.
