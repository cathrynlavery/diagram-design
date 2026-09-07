# Wardley Map

**Best for:** positioning the components of a value chain against how evolved (commoditised) each one is, so a reader can see what to build, what to buy, and what is about to move. A strategy artefact, not an architecture diagram — it says nothing about how components connect at runtime, only where each one sits on the genesis-to-commodity curve.

## Layout conventions

- **Y axis — value chain.** `Visible to the user` at the top, down to `Invisible` at the bottom. Label the axis as stacked separate `<text>` lines flanking the axis endpoints — **never `writing-mode`** to rotate a label vertically. Axis line `rule-solid` at `0.20` opacity.
- **X axis — evolution.** Four bands separated by three vertical hairlines: `Genesis | Custom-built | Product | Commodity`. Band separators are `rule` at `0.10` opacity, dashed `4,4`. Band labels sit along the bottom axis: Geist Mono 8px, uppercase, tracked, `muted`. Axis line `rule-solid` at `0.20` opacity.
- **Components** are a small circle `r=6`, filled `paper` with an `ink` 1px stroke. Label in Geist sans 12px weight 600, placed 12px above the dot, `text-anchor="middle"`. An optional Geist Mono 9px `muted` sublabel can sit under the dot for a technical qualifier — use sparingly.
- **Dependency links** are thin `muted` 0.8px straight lines from a component down to the component it depends on. **These are the one documented exemption from §6 rule 1 (mandatory orthogonal elbows) — dependency links only.** A component's y/x position on this map *is* the data; forcing it onto an axis to make an elbow route work would misplace it. No arrowhead — the line itself states the dependency.
- **Movement** — a component that is evolving carries a short right-pointing arrow: `accent`, dashed `5,4`, `marker-end="url(#arrow-accent)"`, running from the dot's edge toward the next band. The arrow needs no on-arrow text label: the legend's "Evolving" swatch (accent dot + dashed accent arrow) already names what accent + dashes mean, and since arrows on this map can only ever point right (see Anti-patterns — a left-pointing movement arrow is a contradiction, not a design choice), the direction itself already says "toward commodity." A bare word like `COMMODITISING` restates what shape and color already signal — apply §1's remove test: can I remove this label, does color or shape already carry it? Here it does, so the label is the thing that goes, not its position.
  An on-arrow label is legitimate only when it qualifies something the arrow *can't* express on its own — a timeframe (`BY Q3`), a driver (`VENDOR LOCK-IN`) — never a restatement of direction. If you add one, mask it Geist Mono 8px, 6–10px clear of the stroke, same masking rule as any arrow label (§6 rule 2), and confirm there's runway for the mask first: the space directly around a component's dot is usually the most congested spot on the map, because that's also where its own dependency links fan out. Worked example — the moving component in `example-wardley.html` sits at `(420,156)` with links fanning to `(620,220)` and `(680,252)`; at the mandatory 6–10px gap band below the arrow (`y=164–176`), those two lines cross at `x=441.7–482.5` and `x=445–482.5` respectively — almost the full width of the arrow's own span (`x=428–504`), leaving no clear pocket wide enough for a label. Above the dot is no better: the component's own name label already occupies that band per the 12px-above-dot convention. Check both bands for interference before adding a movement label; if neither is clear, don't add one — the legend already covers it.
- **Focal rule:** the 2 accent elements on this type are the moving component's dot (`accent-tint` fill, `accent` stroke) and its movement arrow — or two moving components sharing those 2 accent slots with no other accent anywhere else on the map.
- **Legend:** horizontal strip at the bottom, hairline separator above it, viewBox extended ~60px — same as every other type.

## Complexity budget

| Limit | Rule |
|---|---|
| Max components | 9 |
| Max dependency links | 12 |
| Max movement arrows | 2 |
| Max accent elements | 2 |

## Anti-patterns

- **Treating the x axis as a maturity score.** Evolution is four qualitative bands (genesis / custom-built / product / commodity), not a 0–10 slider. Don't plot a component at "6.5" — place it in a band.
- **A component with no dependency link.** If nothing in the value chain depends on it and it depends on nothing, it isn't part of the chain — delete it or wire it in.
- **Arrows drawn right-to-left.** Evolution only moves toward commodity. A left-pointing movement arrow is a contradiction, not a design choice.
- **Using the map as an architecture diagram.** No request/response direction, no protocols, no runtime topology — that's the architecture type. This type answers "what's worth building vs. buying," not "how does traffic flow."
- **Numbering the y axis.** Value-chain visibility is ordinal (more visible to the user, less visible), not a quantity. Numeric ticks imply a measurement that doesn't exist.
- **More than 2 movement arrows.** Beyond that the map stops making a single point and turns into a forecast nobody can act on.
- **`writing-mode` vertical axis text.** Stack the words as separate horizontal `<text>` lines instead — see Layout conventions above.

## Examples

- `assets/example-wardley.html` — minimal light. AI assistant product, agent orchestration commoditising toward Product.
- `assets/example-wardley-dark.html` — minimal dark, same map.
- `assets/example-wardley-full.html` — full editorial: framed container + 3 varied-width cards (the moving component, a genesis-stage build, and the commodity base).
