# Sequence

**Best for:** request/response flows, protocol exchanges, multi-actor interactions over time, API call traces, incident reconstructions, auth/token refresh paths with branching.

## Layout conventions
- Actors as boxes in a horizontal row at the top.
- **Lifelines**: dashed vertical lines descending from each actor to the bottom.
- Messages: horizontal arrows between lifelines; time flows top→down.
- **Activation bar**: narrow rectangle (`w=8`, muted fill, 0.8 hairline stroke) on a lifeline spanning the interval that actor holds control. Stack for nested calls.
- Self-messages: short U-shaped loop returning to the same lifeline; label right of the loop.
- Return messages: **dashed** stroke + **filled** marker (never open). Prefer muted; optionally match the originating call color when pairing multi-hop stacks. Headline success may use solid coral (see Message kinds).
- Coral on the primary success response or headline message — one, maybe two. Actor focal strokes do not count toward the coral message budget.
- When the flow **branches** (valid vs invalid token, retry, optional step), draw a **combined fragment** frame — do not invent free-floating if/else arrow clusters.

## Message kinds

| Kind | Stroke | Marker | When |
|---|---|---|---|
| Call (sync) | solid muted or link-blue | filled | Request that expects a reply |
| Return | **dashed** muted (or match call color) | filled | Reply to a sync call — never solid |
| Async / fire-and-forget | dashed muted | **open** arrowhead | Beacons, events, one-way notify |
| Headline success | solid accent (≤1–2 messages) | accent filled | Primary happy-path response only |

### Open arrowhead (async)

Define once in `<defs>` and use for fire-and-forget only:

```svg
<marker id="arrow-open" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
  <polyline points="0 0, 8 3, 0 6" fill="none" stroke="#4f5d75" stroke-width="1.2"/>
</marker>
```

Dark mode: stroke `#bfc0c0` (muted on dark paper). Do not fill the open marker — the hollow head is the async signal. Return messages keep the **filled** marker even when dashed.

## Combined fragments (`alt` / `opt` / `loop`)

Use a rectangular **frame** that spans only the lifelines participating in the branch. Operator label is Geist Mono, uppercase, in a small tab at the top-left of the frame. Time still flows top→down inside the frame.

### Frame primitive (shared)

```svg
<!-- Frame: light ink wash + hairline. Label tab top-left. -->
<rect x="X" y="Y" width="W" height="H" rx="4"
      fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.22)" stroke-width="1"/>
<!-- Operator tab -->
<rect x="X" y="Y" width="40" height="16" rx="2"
      fill="#f5f5f5" stroke="rgba(45,49,66,0.22)" stroke-width="1"/>
<text x="X+20" y="Y+12" fill="#4f5d75" font-size="8"
      font-family="'Geist Mono', monospace" text-anchor="middle"
      letter-spacing="0.12em">ALT</text>
```

Dark mode: frame fill `rgba(245,245,245,0.04)`, stroke `rgba(245,245,245,0.22)`, tab fill = dark `paper` (`#2d3142`), tab text = dark `muted` (`#bfc0c0`).

### Operators

| Operator | Regions | Divider | Guard label |
|---|---|---|---|
| `opt` | 1 | none | `[if condition]` under the tab (Geist Mono 8px) |
| `alt` | **2 max** | dashed horizontal hairline across the frame | `[guard]` on region 1; `[else]` (or a second guard) on region 2 |
| `loop` | 1 | none | `[for each item]` or `[retry ≤ 3]` under the tab |

### Guard + divider primitives

```svg
<!-- Guard: left-aligned inside the frame, mono -->
<text x="X+12" y="GUARD_Y" fill="#4f5d75" font-size="8"
      font-family="'Geist Mono', monospace" letter-spacing="0.04em">[token valid]</text>

<!-- alt region divider -->
<line x1="X+8" y1="DIV_Y" x2="X+W-8" y2="DIV_Y"
      stroke="rgba(45,49,66,0.20)" stroke-width="1" stroke-dasharray="4,3"/>
```

### Fragment layout rules
- Frame left/right inset ≥12px from the outermost participating lifeline centers (so activation bars stay inside the frame).
- ≥24px between consecutive message y-levels inside a region (4px grid).
- Guard sits in the first ~20px under the tab; first message in that region is ≥24px below the guard baseline.
- Divider y on the 4px grid; ≥16px clear of messages above and below.
- Nested fragments: **max 1 level**. Prefer two separate diagrams over deep nesting.
- Default: **one** fragment per diagram. A second only if both stay under the complexity budget.
- Coral stays on **one** headline success message across the whole diagram (usually the happy-path return inside the first `alt` region, or the final success outside a loop). Do not coral both `alt` branches.

### Out of scope (do not invent)
- `par`, `critical`, `break`, `ref`, and other UML operators — second PR if needed.
- Participant create/destroy, found/lost messages, duration timing bars.

## Complexity budget (sequence-specific)
- Max lifelines: 5 (same as SKILL.md §7).
- Max messages (arrows): 12.
- Max combined fragments: 1 (hard default); 2 only if each is a single-region `opt`/`loop`.
- Max `alt` regions: 2.
- Max fragment nesting depth: 1.
- Max coral elements: 2 (prefer 1 for fragment diagrams).

If you exceed, split: overview (happy path) + detail (failure / refresh path).

## Lifeline primitive
```svg
<line x1="CX" y1="TOP" x2="CX" y2="BOTTOM"
      stroke="rgba(45,49,66,0.20)" stroke-width="1" stroke-dasharray="3,3"/>
```

## Activation bar primitive
```svg
<rect x="CX-4" y="TOP" width="8" height="H"
      fill="rgba(45,49,66,0.06)" stroke="#4f5d75" stroke-width="0.8"/>
```

## Anti-patterns
- Message arrow pointing *upward* (reverses time — never).
- Activation bars that never close.
- Labels sitting over another lifeline — shorten or shift y into a gap.
- Swimlane-style lanes instead of lifelines (different grammar).
- Drawing `if/else` as two free-floating arrow clusters with **no** fragment frame.
- Nested `alt` inside `alt` (split into two diagrams).
- Fragment operator label in Geist sans — must be mono: `ALT` / `OPT` / `LOOP`.
- Coral on both `alt` branches.
- Frame that covers actors with no messages inside the fragment.
- Filled arrowhead on async fire-and-forget (use open marker).
- Open arrowhead on return messages (returns stay filled + dashed).

## Examples
- `assets/example-sequence.html` — minimal light (cold-cache happy path)
- `assets/example-sequence-dark.html` — minimal dark
- `assets/example-sequence-full.html` — full editorial
- `assets/example-sequence-oauth.html` — special: bearer call + `alt` refresh (light)
- `assets/example-sequence-oauth-dark.html` — same special, dark
- `assets/example-sequence-oauth-full.html` — same special, full editorial
