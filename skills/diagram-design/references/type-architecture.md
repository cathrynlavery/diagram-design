# Architecture

**Best for:** system overviews, data-flow diagrams, integration maps, infra topology.

## Layout conventions
- Group components by tier or trust boundary (frontend → backend → data; public → private).
- Primary flow runs left→right or top→down. Pick one and hold it.
- Draw arrows before boxes so z-order puts connections behind components.
- 1–2 coral focal nodes: the primary integration point, the primary data store, or the key decision node.
- Dashed boundary rectangles mark regions (VPC, security group, trust zone); labels sit on a paper-colored mask over the boundary line.

## Connector style

**Rounded right-angle (orthogonal) connectors are MANDATORY** for all non-horizontal/vertical connections — diagonal `<line>` between off-axis nodes is a hard fail (see SKILL.md §6 Mandatory connector rules). Two-bend elbow path with `r=8`:

```svg
<!-- right+down: from (x1,y1) to (x2,y2), mid = (x1+x2)/2 -->
<path d="M x1,y1 H mid-8 Q mid,y1 mid,y1+8 V y2-8 Q mid,y2 mid+8,y2 H x2"
      fill="none" stroke="…" stroke-width="1.2" marker-end="url(#arrow)"/>
```

Flip the vertical signs for right+up. Use a plain `<line>` only when endpoints share the same x or y. Arrow labels sit on the vertical segment, centered horizontally on `mid` and vertically between the two corners.

**Port selection — use top/bottom for vertical connectors.** When the destination is noticeably above or below the source, exit the source's top/bottom edge and enter the destination's top/bottom edge. Use a single-bend L-path (horizontal → corner → vertical into the node), not a left/right side port:

```svg
<!-- entering a node from its bottom (destination above source) -->
<path d="M x1,y_src H x2-8 Q x2,y_src x2,y_src-8 V y_dst"
      fill="none" stroke="…" stroke-width="1.2" marker-end="url(#arrow)"/>
```

Reserve left/right ports for connections that travel primarily horizontally. Entering a node from the side on a mainly-vertical path looks like the arrow punctures the node face rather than arriving from above or below.

**Dashed paths — same routing rules.** Optional, return, async, and passive flows use `stroke-dasharray="4,3"` and a lighter stroke weight (`stroke-width="1"`). Apply the **same orthogonal routing, port-selection, and bridge/hop rules** as solid paths — the dash pattern only communicates semantic weight, not a different routing grammar. When a dashed path and a solid path must cross, bridge the dashed one (it is by definition the less important connection).

**Zone label margin.** Leave ≥16px between the bottom of the zone eyebrow label and the top of the first enclosed node. Size the zone rect tall enough to contain this header gap (zone `y` = node_top − 32; label mask `y` = zone_y + 4).

## Crossing arrows — bridge / hop

When two orthogonal arrows must cross, add a small arc (hop/bridge) on the **less important** arrow at the crossing point. The more important arrow is drawn uninterrupted.

```svg
<!-- Horizontal hop over a vertical crossing at x=cx, on a line at y -->
<path d="M x1,y H cx-8 a 8,8 0 0,1 16,0 H x2"
      fill="none" stroke="…" stroke-width="1.2" marker-end="url(#arrow)"/>
```

`a 8,8 0 0,1 16,0` is an SVG arc: rx=ry=8, large-arc=0, sweep=1 (curves visually upward), advancing 16px right — creating an 8px-radius semicircular bump over the crossing. For a vertical hop over a horizontal, use `a 8,8 0 0,0 0,16` on the vertical path.

Decide which arrow to bridge: bridge the one that is less semantically important (passive, secondary, write-back), or the one with lighter stroke weight (dashed, muted). Never bridge both.

## Zone grouping

Group 2+ nodes that serve the same tier or trust boundary with a zone rect — drawn **before** arrows and nodes (z-order: bg → zones → arrows → nodes):

```svg
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8"
      fill="rgba(45,49,66,0.02)" stroke="rgba(45,49,66,0.10)" stroke-width="0.8"/>
<rect x="{label_x}" y="{y+4}" width="{label_w}" height="12" rx="2" fill="{paper}"/>
<text x="{label_cx}" y="{y+13}" fill="rgba(45,49,66,0.40)" font-size="7"
      font-family="'Geist Mono', monospace" text-anchor="middle" letter-spacing="0.14em">LAYER</text>
```

Rules:
- Leave 12–16px above the first enclosed node — the eyebrow label sits in this margin.
- Zone fill: `rgba(45,49,66,0.02)` (2% ink wash). Any stronger competes with node fills.
- Max 3 zones per diagram. More and it reads like a swimlane (use that type instead).
- Dark mode: swap `rgba(45,49,66,…)` → `rgba(245,245,245,…)` same opacities; label mask fill = `paper` (dark).

## Anti-patterns
- Every box in coral ("this is important too") — hierarchy collapses.
- Bidirectional arrow when one direction is obvious from context.
- Legend floating inside the diagram area.

## Examples
- `assets/example-architecture.html` — minimal light
- `assets/example-architecture-dark.html` — minimal dark
- `assets/example-architecture-full.html` — full editorial
