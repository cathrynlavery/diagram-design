# Venn / Set Overlap

**Best for:** intersection of concepts/domains, shared attributes between categories, "where A meets B", ikigai-style frames (desirable × feasible × viable).

## Layout conventions
- **Prefer 2 or 3 circles.** Avoid 4+ (unreadable — use a matrix instead).
- Circle stroke: 1px hairline, color per-set (ink, muted, soft).
- Circle fill: very low-opacity tint — `ink @ 0.04` for the ink set, `muted @ 0.05` for the muted one. Tints compound naturally in overlap regions.
- Radii: equal when sets are comparable in size; proportional when sets are meaningfully different. Don't fake equal sizes for aesthetics.
- **Set labels** placed outside the circle, NEVER crossing the stroke. `node-name` role 12–14px 600 for the set name, optional `sublabel` role 9px.
- **Intersection labels** placed inside the overlap region, `node-name` role 12px 600, centered. For small overlaps, use a leader line to a label in clear space.
- **Coral accent** on the ONE focal intersection — the "sweet spot". Either an `accent` label stroke OR a clipPath-bounded `accent @ 0.10` fill tint.
- Circle centers and radii divisible by 4.

## Anti-patterns
- Unlabeled regions — reader can't tell which set is which.
- Circles that don't overlap when overlap is the point.
- Equal-sized circles when sets are obviously different (dishonest).
- Coral on multiple overlap regions (focal signal dies).
- Labels sitting on top of circle strokes (illegible).
- 4+ circles where 2–3 would do.

## Examples
- `assets/example-venn.html` — minimal light
- `assets/example-venn-dark.html` — minimal dark
- `assets/example-venn-full.html` — full editorial
