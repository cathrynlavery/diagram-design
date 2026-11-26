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

**Port selection for vertical connectors.** When the destination is noticeably above or below the source, enter the destination through its top or bottom edge. Use a single-bend L-path: leave the source through the side edge that faces the destination's column, run horizontally, turn once, and run vertically into the destination:

```svg
<!-- destination above source: leave the source's right edge at (x_right, y_port), enter the destination's bottom edge at x2 -->
<path d="M x_right,y_port H x2-8 Q x2,y_port x2,y_port-8 V y_dst"
      fill="none" stroke="…" stroke-width="1.2" marker-end="url(#arrow)"/>
```

Every segment leaves its box perpendicular to the edge it starts on. Never start a horizontal segment on a top or bottom edge: it runs along the border, hidden behind the node fill, and the arrow looks like it grows out of the corner. When two of these connectors leave the same side edge, fan their ports (primitives-core.md rule 4) and keep each port at least 8px from a corner so it never lands on the corner radius.

Reserve left/right ports on the destination for connections that travel primarily horizontally. Entering a node from the side on a mainly-vertical path looks like the arrow punctures the node face rather than arriving from above or below.

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
      fill="{ink @ 0.02}" stroke="{ink @ 0.10}" stroke-width="0.8"/>
<rect x="{label_x}" y="{y+4}" width="{label_w}" height="12" rx="2" fill="{paper}"/>
<text x="{label_cx}" y="{y+13}" fill="{soft}" font-size="7"
      font-family="{eyebrow}" text-anchor="middle" letter-spacing="0.14em">LAYER</text>
```

Rules:
- Leave 12–16px above the first enclosed node — the eyebrow label sits in this margin.
- Zone fill: `ink @ 0.02` (2% ink wash). Any stronger competes with node fills.
- **Zone label: `soft`, never ink at an opacity.** A zone eyebrow is a boundary label, and `soft` is the boundary-label role in [`style-guide.md`](style-guide.md). An opacity such as `ink @ 0.40` composites differently on every `paper`; on a light warm paper it falls near 2.2:1, unreadable at 7px. The role carries its own contrast contract under any skin.
- Max 3 **flat** zones per diagram. More and it reads like a swimlane (use that type instead). Nested administrative and traffic scopes under **Containment** below are not this cap — they nest, so the cap is sibling traffic scopes at one level.
- Dark mode: the roles invert with the skin, so nothing is swapped by hand. Take `ink`, `soft`, and `paper` from the dark column in [`style-guide.md`](style-guide.md); opacities stay the same.

## Containment

Use this section when **the network hierarchy itself carries the meaning** — the reader must see what sits inside which scope, and a flattened zone label (`VNET · SNET-APP`) would lie about that hierarchy. Connectors stay Architecture; containment geometry comes from Nested (consistent insets, eyebrow per level, fills stepping up inward). This is a variant of Architecture, not a new type and not a provider-specific grammar.

Two scope kinds, never interchangeable:

| Kind | What it is | Shape | `data-scope-kind` |
|---|---|---|---|
| **Administrative** | Billing, permissions, lifecycle. Holds no traffic. | Horizontal **band** — a full-width containment rect with a 24px header | `admin` |
| **Traffic** | A boundary packets do not cross without an explicit rule. | **Box** — the existing zone rect (`rx=8`) | `traffic` |

Provider-neutral metadata (no vendor prefix):

- `data-grammar="architecture-containment"` on the root `<svg>` — files without it are ordinary Architecture and this contract does not apply.
- `data-scope-id` + `data-scope-kind` on every scope's bounds rect (`data-role="bounds"`). Bounds are always a `<rect>`, for scopes and nodes alike.
- `data-parent` on every nested scope and every node, naming the innermost enclosing `data-scope-id`. Only the outermost scope, which no other scope encloses, may omit it.
- Nodes: `data-node-id`, `data-kind` of `compute` (workloads inside a traffic scope), `endpoint` (private endpoint inside a traffic scope), or `managed` (PaaS that belongs to an administrative scope).
- An `endpoint` carries `data-target` naming the `managed` node it reaches.
- A peering path carries `data-peering`, `data-from`, and `data-to` naming the two traffic scopes it joins.

**PaaS placement (normative).** A managed service is never inside a traffic scope. It sits in the administrative band that owns it. What lives in the subnet is its private endpoint. Drawing a database inside a subnet tells the reader it sits behind that subnet's security rules, which it does not. `scripts/verify-architecture-containment.py` fails a `managed` node whose bounds fall inside any `traffic` scope, and an `endpoint` that is not inside one.

**Sibling axis.** Sibling traffic scopes at one level share one axis. Directly under an administrative band the parent's aspect chooses it: wider than tall (or square) → a row sharing one `y`; taller than wide → a column sharing one `x`. Nested children take the perpendicular axis: siblings inside a traffic scope that sits in a row form a column, and their own children form a row again. Do not mix axes at one level.

**Budget** (tightens Architecture's flat 3-zone cap; see `layout-budget.md`): ≤2 administrative bands, ≤4 traffic scopes, ≤8 nodes, 2 accent elements. Split per subscription when a figure exceeds that.

**Draw scopes in place.** Containment is read from each bounds rect's own `x`, `y`, `width`, and `height`. Do not position a scope or node with a `transform` attribute, a moving inline style (`transform`, `translate`, `x`, `y`, `position`, `margin`, and similar), a nested `<svg>`, a `<style>` rule, or an animation, on the element or any group around it. The checker fails each of those. It does not evaluate external stylesheets or script, so keep containment geometry out of both.

`scripts/verify-architecture-containment.py` checks unique IDs, resolving innermost parents, geometric containment, `<rect>` bounds, the admin-band vs traffic-box shapes (with `stroke-dasharray` resolved as rendered, so `none` or all-zero dashes count as solid), PaaS placement, endpoint targets, sibling axes, declared peerings, and the moved-geometry rule above. Files without `data-grammar="architecture-containment"` are skipped.

## Anti-patterns
- Every box in coral ("this is important too") — hierarchy collapses.
- Bidirectional arrow when one direction is obvious from context.
- Legend floating inside the diagram area.
- Flattening two containment levels into one zone eyebrow (`VNET · SNET-APP`) — the hierarchy is the claim.
- A managed PaaS box drawn inside a subnet or VPC — only its private endpoint belongs there.
- Colour as the only distinction between an administrative band and a traffic box — the shapes must differ, because greyscale still has to tell them apart.

## Examples
- `assets/example-architecture.html` — minimal light
- `assets/example-architecture-dark.html` — minimal dark
- `assets/example-architecture-full.html` — full editorial
- `assets/example-architecture-containment.html` — nested admin/traffic scopes, light
- `assets/example-architecture-containment-dark.html` — nested admin/traffic scopes, dark
- `assets/example-architecture-containment-full.html` — nested admin/traffic scopes, full editorial
