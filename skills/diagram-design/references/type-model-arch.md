# Model Architecture

**Best for:** the figure a model paper opens with — a neural network drawn as a stack of layer blocks, where a `×N` multiplier stands in for depth the reader would never count. Transformer stacks (encoder/decoder, attention + FFN, MoE), CNN and U-Net stages, diffusion backbones, any network described as *"two of these, then three repeats of one of those and five of the other"*.

The distinguishing element is the **repeat group**: a dashed container holding a contiguous run of blocks, labelled `×N`, and nestable one level. That is what no other type has. Layer stack is full-width horizontal bands with no connectors and no repetition; architecture draws logical components with no depth; nested encodes containment, not a run length. Without the multiplier a 40-layer network is either 40 boxes or a lie.

**Route elsewhere when:**

| The subject | Use instead |
|---|---|
| Abstraction levels (OSI, tech stack, memory hierarchy) | [type-layers.md](type-layers.md) |
| Services and their connections, no depth | [type-architecture.md](type-architecture.md) |
| Tensor shapes through a pipeline, no repetition | [type-data-flow.md](type-data-flow.md) |
| Training loop or inference request order | [type-sequence.md](type-sequence.md) |
| Where the model runs — GPUs, replicas, ports | [type-deployment.md](type-deployment.md) |

## Write the layer plan first

Requests arrive as prose (*"two SWA layers, then three repeats of one full and five reuse"*, or a named model). Turn that into a plan **before** any geometry, and state it in the §3 confirm-before-drawing message. The plan is the diagram's contract; the drawing is a rendering of it.

```
stack encoder depth 20 layers 0-19
  2 × [ local(w=128) + moe ]
  3 × [ full(r=2) + moe , 5 × [ reuse(r=2) + moe ] ]

stack decoder depth 20 layers 20-39
  1 × [ full(r=1) + moe ]
  3 × [ reuse(r=1) + moe ]
  4 × [ reindex(r=1) + moe , 3 × [ reuse(r=1) + moe ] ]

io    encoder.bottom Embedding (d=4,096) · encoder.top Encoder output
      decoder.top Draft head
side  N-gram memory → encoder.local, encoder.full
      decoder.full → Candidate pool → decoder.reindex
focal encoder.top
```

Then **expand and check the census** before drawing: `2 + 3×(1 + 5) = 20` and `1 + 3 + 4×(1 + 3) = 20`. If the arithmetic does not land on the declared depth, the plan is wrong — not the multiplier placement. Fix the plan.

When the source is a paper or a report, every multiplier, ratio and window size is a claim about that source. Carry it across verbatim or leave it out; do not round a `5×` to a `4×` because it fits the canvas better.

## Layout conventions

- **Flow bottom → top**, the convention model papers use: input at the bottom, output above the stack. One vertical spine per stack at the block centre, so every spine segment is a plain vertical `<line>`/`V` path with no elbow.
- **Block**: `w=168`, `h=36`, `rx=4`, pitch 56 (36 + 20 gap). Name in Geist 12px/600 centred; technical sublabel in Geist Mono 9px underneath (`full · r=2`, `w = 128`). A block with no sublabel centres its name.
- **Stage panel**: one rounded rect per stack (`rx=8`, `w=384`, fill `ink @ 0.04`, **no stroke** — the fill alone separates it from the page). Its name sits **inside, top-right**, Geist 12px/600. Two stacks sit 96px apart; both panels share the same `y` and height so the reader can compare rows across them.
- **Row ladder.** Both stacks use one shared list of row `y` values. When one stack has fewer rows than the other, leave the gap — do not re-space one column, or the encoder's third group stops lining up with the decoder's and the comparison is gone.
- **I/O blocks sit outside the panel**: the embedding below, the output above. The multi-sheet treatment (2 extra rects offset `+4,-4` each, drawn first) marks a tensor carried as several residual streams; use it only where that is true.
- **Side modules** live outside the panels entirely, at the height of the layer they feed, and reach in with orthogonal connectors — one attach point per connector, per §6 rule 4.
- **The `×N` chip** is Geist Mono 11px, `ink`, sitting in the margin to the **right of its own group rect and inside its parent's**. Nested groups therefore need asymmetric padding: outer `x` pad 16 left / 72 right, inner 16 / 16. A chip drawn inside its own group reads as a block label.

## Variant palette

Layer variants are a **categorical** encoding, and the only place in this skill where more than two colours are on purpose. Take them from the style guide's `series` tokens at a 0.16 tint fill with the solid token as stroke, and cap it at **four**:

| Variant | Token | Reads as |
|---|---|---|
| Full / heaviest | `series-1` sage | computes and stores its own state |
| Reindex / partial | `series-2` dusty-blue | inherits state, recomputes its own selection |
| Reuse / lightest | `series-3` mustard | inherits both, adds no new state |
| Local / windowed | `series-5` slate | never touches the global state |

Two more treatments, both uncoloured on purpose:

- **The uniform element** (`MoE`, `FFN`, `Conv`) — the one that appears in every layer and therefore carries no signal: `paper` fill, `rule-solid` silver stroke. It is present so the repeat group encloses a *layer*, not half of one.
- **I/O and side modules** — `paper` fill, `muted` stroke.

`accent` stays what it always is: **one** focal block, the hand-off the figure exists to argue. Never a fifth variant colour.

## Repeat groups

- Dashed `ink @ 0.30`, `stroke-dasharray="5,4"`, `rx=8`, **no fill** — the panel is the only filled container, so nesting reads by stroke, not by stacked tints.
- **One level of nesting.** `A ×3 [ x, ×5 [ y ] ]` is legible; a third level is a table.
- A group encloses whole layers. Splitting a group boundary between an attention block and its FFN says the FFN repeats without the attention, which is false.
- Groups are painted after the panel and before the connectors, so a connector may cross a group edge — that is how a side module reaches a layer inside a repeat.

## The census invariant

Every block that is part of a stack carries its role and its group:

```svg
<rect ... data-layer-kind="full" data-layer-stack="encoder" data-layer-group="enc-outer"/>
<rect ... data-group-id="enc-outer" data-repeat="3" data-group-parent=""/>
<rect ... data-stack="encoder" data-depth="20" data-layer-range="0-19"/>
<text ... data-repeat-for="enc-outer">×3</text>
```

`data-layer-kind` is one of `full`, `reindex`, `reuse`, `local` (counted), `ffn` (part of a layer, not a layer) or `io` (not counted). A stack's depth is then

> Σ over counted blocks of ∏ `data-repeat` along the block's group ancestry

and it must equal the panel's `data-depth`, which must equal the span of `data-layer-range`, and each `×N` chip's text must equal its group's `data-repeat`. From a repository checkout, `python3 <repo-root>/scripts/verify-model-arch.py <file>` recomputes all four. This is the type's characteristic failure: a `×4` that should read `×5`, or a group moved during layout, produces a diagram that looks right and adds up to 36 layers.

## Complexity budget

Max 2 stacks, max 10 blocks per stack, max 3 repeat groups per stack, **1 level of nesting**, max 4 variant colours, max 3 side modules, max 2 cross-stack links, 1 accent block. Over budget → draw the stage overview at one block per stage, and a second diagram for the one stage that matters.

Note that the block count is high for this skill on purpose: an attention/FFN pair per row doubles it, and the repeat groups are what keep it at ~9 rows instead of the network's real depth. If the multipliers are all `×1`, this is the wrong type — you have a data flow.

## Anti-patterns

- **Drawing every layer.** If a group would be `×1`, it is not a group; if you are drawing 40 boxes, you have not found the repeat.
- **A multiplier that does not reconcile.** The census exists because this is the failure that ships.
- **Colour without a legend entry**, or a fifth variant colour. Four is the cap; past that, the variants are not the story.
- **Colouring the uniform element.** If `MoE` is in all 40 layers, tinting it spends a colour on zero information.
- **Two stacks on independent row ladders** — the panels stop aligning and the diagram becomes two diagrams.
- **A side module wired into "the encoder"** rather than into the specific layers it feeds. If it feeds all of them, it belongs in the panel's subtitle, not in a box.
- Hyperparameters as a wall of sublabels. One number per block, the one the reader needs.
- Diagonal connectors from a side module to a block inside a group — §6 rule 1 holds here as everywhere.

## Examples

- `assets/example-model-arch.html` — minimal light
- `assets/example-model-arch-dark.html` — minimal dark
- `assets/example-model-arch-full.html` — full editorial
