# Fishbone / Ishikawa (root-cause)

**Best for:** structured root-cause analysis. One observed effect, causes grouped by category, sub-causes hanging off each category. The standard artefact of an incident post-mortem — use it when a reader needs to see *what was investigated*, not just the conclusion.

## Layout conventions

- **Spine.** A horizontal line (`ink`, 1.2px) runs left→right at the vertical centre `CY`, terminating with an arrowhead into an **effect box** at the right head — the node-box pattern from SKILL.md §6, the observed-effect statement inside.
- **Bones.** Category lines are straight diagonals at a fixed **60°** to the spine, alternating above and below, evenly spaced along it. Each bone carries its category name at the outer end in a small tag-style box (`rx=4`, not a pill) — Geist sans 12px weight 600.
- **Sub-causes.** Short horizontal ticks (32px, `soft`) branch off each bone at fixed points along its length, each with a sub-cause label in Geist Mono 9px sitting past the open end of the tick.
- **Diagonal exemption.** SKILL.md §6 rule 1 (mandatory rounded right-angle elbows) does not apply to the 60° bones — they are this type's defining grammar. The exemption covers **bones and sub-cause ticks only**; any other connector in a fishbone diagram (e.g. a callout leader, a cross-reference arrow) still uses rounded right-angle elbows.
- **Focal rule.** Exactly one bone is the confirmed root cause: its line is `accent`, and its category tag uses `accent-tint` fill + `accent` stroke. The effect box is styled the same way (`accent-tint` fill, `accent` stroke) since it's the diagram's headline. That pair — root-cause bone and effect box — is the full 2-accent budget; every other bone, tag, and tick stays `ink` / `muted` / `soft`.
- **Drawing order:** background → spine → bones → sub-cause ticks → category tag boxes → effect box → legend. Lines before boxes, so box fills cap the line ends cleanly.

## Math

For a spine at `y = CY` with the effect box's left edge at `x = HEAD`, bone `k` (1-indexed, k = 1..6) attaches to the spine at:

```
attach_x(k) = HEAD - 160 - k * 160
```

Bones alternate above (`k` odd) and below (`k` even) the spine. A bone's far endpoint — where the category tag sits — is the integer-rounded 60° offset from its attach point:

```
dx = -96
dy = ∓168        (minus = above, plus = below)
far_x(k) = attach_x(k) + dx
far_y(k) = CY ∓ 168
```

### Pre-computed reference (5-bone layout, HEAD=1200, CY=320)

| Bone `k` | Category slot | Side | `attach_x` | `far_x, far_y` |
|---|---|---|---|---|
| 1 | first | above | 880 | 784, 152 |
| 2 | second | below | 720 | 624, 488 |
| 3 | third | above | 560 | 464, 152 |
| 4 | fourth | below | 400 | 304, 488 |
| 5 | fifth | above | 240 | 144, 152 |

A 6th bone (below) would attach at `x=80`, far endpoint `(-16, 488)`, and its category tag would run from `x=-76` to `x=44` against a viewBox that starts at `x=-40`. It clips. **Five is the ceiling at `HEAD=1200`**: to draw a 6th, widen `HEAD` *and* the viewBox width by at least 160 each, keeping the viewBox origin at `-40`. Both have to move together — widening `HEAD` alone pushes the 200px effect box to `1360..1560` past the `1440` right edge, trading a clipped tag on the left for a clipped effect on the right. Or drop a category.

**Sub-cause ticks** sit at fractions `m/6` along the bone (`m = 2, 4` for two ticks; `m = 3` for one), so their coordinates stay on the 4px grid:

```
tick_x(k, m) = attach_x(k) - 16 * m
tick_y(k, m) = CY ∓ 28 * m
```

The tick itself is a 32px horizontal line from `(tick_x, tick_y)` to `(tick_x - 32, tick_y)`; the label sits past its open end, `text-anchor="end"` at `x = tick_x - 36`, `y = tick_y - 4` (above-bones) or `tick_y + 12` (below-bones).

## Complexity budget

| Limit | Rule |
|---|---|
| Max categories (bones) | 5 at `HEAD=1200`. A 6th requires a widened canvas — see Geometry |
| Max sub-causes per bone | 3 |
| Max sub-causes total | 18 |
| Max accent elements | 2 (root-cause bone+tag, effect box) |

## Anti-patterns

- **More than 5 bones on the default canvas.** The 6th tag clips the viewBox. Widen `HEAD` and the viewBox width together and deliberately, or split by subsystem into two fishbones.
- **Sub-causes that restate the category.** A "Deploy" bone with a sub-cause labeled "deployment issue" adds a node without adding information.
- **A bone with zero sub-causes.** An empty category is a placeholder, not a finding — delete the bone or don't draw it until there's something under it.
- **Accenting more than one root cause.** If two categories are both confirmed, that's two diagrams (or a merged cause) — not two accent bones. The 2-accent budget is load-bearing for the "this is the answer" signal.
- **Using fishbone for a sequence of failures.** A chain of things that happened in order is a timeline or sequence diagram — fishbone is for causes of *one* effect, not a chronology.
- **Pasting in the classic 6M template (Man/Machine/Material/Method/Measurement/Environment) with empty categories.** Name categories from the actual investigation, not a generic checklist waiting to be filled in later.
- **Effect box phrased as a solution.** "Add a p99 alert" is a fix, not an observed effect. The box states what was seen — a symptom, a measurement, an incident — never the remedy.

## Examples

- `assets/example-fishbone.html` — minimal light. Checkout p99 latency incident, 5 categories, Data confirmed as root cause.
- `assets/example-fishbone-dark.html` — minimal dark, same data.
- `assets/example-fishbone-full.html` — full editorial: container framing + 3 summary cards of varied widths + footer.
