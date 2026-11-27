# Loop

**Best for:** reinforcing cycles, flywheels, feedback loops, and operating loops — anything where the last step feeds the first and a shared hub accumulates state. Use Loop when the reader must see both motions at once: work advances clockwise around the ring, while each pass writes durable state back to one common center.

Prefer **Flowchart** when the path ends, branches toward an outcome, or never truly returns to its first step. Prefer **Cycle** when the center does not accumulate shared state. The dashed write-back spokes are the defining signal here: remove them and the figure is only a circular process.

This type is **parametric**. The inputs in §1 determine station count, angles, edge intersections, connector paths, and viewBox bounds. Identical inputs should produce identical geometry.

---

## 1. Inputs — the parameter contract

```yaml
title: "The self-improving loop"
subtitle: "Every pass improves the shared operating record"

hub:                                  # exactly one
  name: "Shared memory"
  sublabel: "one record, every loop"

stations:                             # 5..8, clockwise from top
  - { name: "Capture",  sublabel: "signals in",       spoke_label: "SIGNALS" }
  - { name: "Research", sublabel: "evidence pulled" }
  - { name: "Decide",   sublabel: "human approves",   focal: true }
  - { name: "Act",      sublabel: "work ships",        spoke_label: "OUTCOMES" }
  - { name: "Measure",  sublabel: "outcomes logged" }
  - { name: "Learn",    sublabel: "playbook updated" }

station_w: 160
station_h: 64
hub_w: 200
hub_h: 104
radius: 240
margin: 64
dark: false
```

**Budget (hard):** **5–8 stations plus exactly one hub.** Above 8 stations, split the subject into an overview Loop and one or more detail diagrams. Exactly one hub — a loop with two hubs is two diagrams. At most one station may set `focal: true`; zero is allowed when no editorial gate deserves emphasis.

Station order is semantic. `stations[0]` is the top station, then entries proceed clockwise. The last station always connects back to station 0; if that return would be false, use a Flowchart instead.

---

## 2. Layout math — deterministic geometry

Use SVG coordinates, where positive y points downward. Let the hub center be `C = (cx, cy)`, station count be `N`, station ring radius be `R`, station half-size be `a = station_w/2`, `b = station_h/2`, and hub half-size be `A = hub_w/2`, `B = hub_h/2`.

### 2.1 Station centers

For zero-indexed station `k`:

```text
theta_k = -90deg + k * (360deg / N)
u_k     = (cos(theta_k), sin(theta_k))
P_k     = C + R * u_k

station_center_x(k) = cx + R * cos(theta_k)
station_center_y(k) = cy + R * sin(theta_k)
station_x(k)        = station_center_x(k) - station_w/2
station_y(k)        = station_center_y(k) - station_h/2
```

Thus station 0 sits at the top, and increasing `k` moves clockwise. Round station rectangles to the nearest 4px grid point after computing the ideal geometry; preserve symmetry when rounding paired stations. Keep ring-circle intersection points to three decimal places so every arc remains on the same circle.

### 2.2 Solid ring-flow endpoints

Ring connectors travel from station `k` to station `j = (k + 1) mod N` as circular SVG arcs on the station circle itself. Every segment uses the same center `C`, radius `R`, and clockwise sweep. The station boxes interrupt the circle; connectors begin at the circle's clockwise exit from the source box and end just before its counterclockwise entry into the destination box, so the marker tip lands on the destination stroke.

Find the circle/rectangle intersections against all four edges of station `k`. For vertical edge `x = x_e`:

```text
y = cy +/- sqrt(R^2 - (x_e - cx)^2)
```

Keep only candidates whose `y` lies within the edge. For horizontal edge `y = y_e`:

```text
x = cx +/- sqrt(R^2 - (y_e - cy)^2)
```

Keep only candidates whose `x` lies within the edge. The two surviving points are classified by their normalized polar angles around `C`:

```text
q_entry(k) = circle/box intersection immediately before theta_k clockwise
q_exit(k)  = circle/box intersection immediately after  theta_k clockwise
```

Compensate for the marker tip before emitting the destination endpoint. With the canonical marker (`refX=7`, polygon tip at `x=8`) and ring stroke width `1.2`, `marker_overhang = 1.2`:

```text
phi_entry = atan2(q_entry(j).y - cy, q_entry(j).x - cx)
phi_end   = phi_entry - marker_overhang / R
q_end     = C + R * (cos(phi_end), sin(phi_end))

M q_exit(k).x q_exit(k).y
A R R 0 0 1 q_end.x q_end.y
```

The large-arc flag is `0` because adjacent-station gaps are less than 180 degrees; the sweep flag is always `1` for clockwise motion in SVG coordinates. The arrowhead overhang completes the final 1.2px to `q_entry(j)`, landing on the box edge without crossing its stroke. The closing connector from station `N-1` to station 0 uses the identical formula.

Loop's circular ring arcs are a documented type-specific exception to SKILL.md §6 rule 1, following the same precedent as Medallion's promotion arcs. A Loop never mixes cubic, straight, or rounded-orthogonal segments into its ring: the six visible gaps must read as pieces of one continuous circle.

### 2.3 Dashed write-back spoke endpoints

Each spoke runs inward from the station edge toward the hub. Use the same ray/box intersection formula, now on the radial vector `u_k`:

```text
box_distance(v, half_w, half_h) = min(half_w / abs(v.x), half_h / abs(v.y))
                                        # ignore a term whose denominator is zero

d_station = box_distance(u_k, a, b)
d_hub     = box_distance(u_k, A, B)
marker_gap = 6                         # 4..8px; 6px canonical

spoke_start(k) = P_k - d_station * u_k
hub_edge(k)    = C   + d_hub     * u_k
spoke_end(k)   = C   + (d_hub + marker_gap) * u_k
```

Because the arrow travels from the station toward `C`, adding `marker_gap` leaves the endpoint just outside the hub boundary. The lighter arrowhead stops before the hub stroke instead of colliding with it. Radial spokes are the type-specific exception to the general ban on slanted straight connectors; they must remain true radii, must not cross one another, and may touch only their source station and the hub.

Labels are optional when the station sublabel already names the write-back. When used, they follow the `arrow-label` role, stay to one side of the spoke, and receive an opaque `paper` mask with a visible 6–10px gap from the stroke. Label a curated subset rather than forcing six labels into the hub halo.

### 2.4 ViewBox sizing

The viewBox must include the full station rectangles, outer ring curves, arrowheads, and at least `margin` breathing room:

```text
left   <= cx - R - station_w/2 - margin
right  >= cx + R + station_w/2 + margin
top    <= cy - R - station_h/2 - margin
bottom >= cy + R + station_h/2 + margin

viewBox_w = right - left
viewBox_h = bottom - top
```

Include the full circle extrema `cx +/- R`, `cy +/- R` plus station bounds and marker clearance when checking these limits. Never shrink the canvas until a station stroke, marker, or ring arc clips. For the six-station canonical example, `viewBox="0 0 1040 680"`, `C=(520,340)`, `R=240`, station size `160×64`, and hub size `200×104` leave generous outer clearance.

---

## 3. Visual grammar

| Element | Treatment |
|---|---|
| Station | Standard node: `paper` fill, `ink` stroke, `radius-md`; name in `node-name`, sublabel in `sublabel` |
| Hub | The one dark element: `ink` fill, `paper` text; slightly larger than a station |
| Focal station | At most one: `accent-tint` fill, `accent` stroke; station name may use `accent` |
| Ring flow | Circular `A R R 0 0 1` arcs on the station circle, solid `muted` stroke, default arrowhead at the destination; clockwise only |
| Write-back spoke | Dashed `soft` stroke at reduced emphasis, `stroke-dasharray="5,4"`, with a `soft` arrowhead |
| Spoke label | `arrow-label` role, `soft`, uppercase, paper mask, 6–10px clear of the connector |

Draw in this order: paper or optional dot grid → ring arrows → dashed spokes → spoke-label masks and labels → station boxes → hub → text. The nodes mask microscopic connector overshoot, while every intended endpoint still lands on an edge.

The hub is not a seventh process step. It is accumulated state: memory, standards, evidence, policy, or a shared operating record. Keep its copy to one name plus one short sublabel.

---

## 4. Connector rules (mandatory)

SKILL.md §6 applies in full except for the two Loop-specific connector primitives: circular ring arcs (§2.2) and straight radial spokes (§2.3). Like Medallion's promotion arcs, these replace §6 rule 1 for this diagram type:

- Ring arrows are same-radius circular arcs, solid, and clockwise. Every path uses `A R R 0 0 1`; destination markers land on station edges and no connector ends at a center point.
- Spokes are dashed and point inward. A solid spoke destroys the visual distinction between operating flow and write-back.
- Labels use opaque masks and maintain a visible 6–10px connector gap. Never place text on the stroke.
- No ring connector or spoke may overlap another connector. Ring paths remain outside the hub; spokes occupy distinct radial routes.
- When two spokes must leave the same station edge, fan their attach points by the §6 formula with at least 12px separation. The normal Loop has one spoke per station; use a second only when the semantics cannot be merged.
- If a ring route would cross the hub, increase `R` or split the diagram. Do not thread flow through shared state or substitute an orthogonal route.

---

## 5. Dark variant — token swap

Apply the style-guide inversion rule; do not invent a second palette.

| Role | Light | Dark |
|---|---|---|
| Canvas and station fill | `paper` | dark `paper` |
| Primary text and station stroke | `ink` | inverted `ink` |
| Hub fill / hub text | `ink` / `paper` | inverted `ink` / dark `paper` |
| Ring flow | `muted` | dark `muted` |
| Write-back spokes and labels | `soft` | dark `soft` |
| Focal fill / stroke | `accent-tint` / `accent` | dark `accent-tint` / brighter dark `accent` |
| Rule and dot grid | `rule` | inverted `rule` at the same opacity |

The semantic relationship stays unchanged in dark mode: one `ink`-filled hub, one optional `accent` station, neutral solid ring arrows, and lighter dashed write-backs.

---

## 6. Reproducibility checklist

1. Station count is 5–8 and hub count is exactly one.
2. Station 0 is at `-90deg`; all others use equal `360/N` steps clockwise.
3. Every solid ring arrow connects adjacent stations with `A R R 0 0 1`, using the same `R`; the last returns to the first.
4. Every ring marker lands on a station edge, not its center.
5. Every dashed spoke begins on a station's inner edge and stops `marker_gap` before the hub stroke.
6. Ring connectors stay outside the hub; spokes do not cross or overlap.
7. At most one station uses `accent-tint` + `accent`; the hub alone uses the dark `ink` fill.
8. Spoke labels, if present, use `arrow-label`, an opaque mask, and a 6–10px gap.
9. The viewBox includes station boxes, strokes, curves, markers, and margins without clipping.

---

## 7. Anti-patterns

| Anti-pattern | Why it fails / correction |
|---|---|
| Two hubs | Two accumulated states create two systems. Draw two diagrams. |
| Solid spokes | They look like primary flow and kill the dashed return signal. Use dashed `soft` write-backs. |
| Stations at uneven angles without reason | The ring stops reading as one operating cadence. Use equal `360/N` spacing unless a documented phase grouping requires a deliberate gap. |
| Mixed arc + orthogonal ring segments | The ring becomes a rounded rectangle. Every segment must be a circular arc of the same radius so the ring reads as one continuous circle. |
| Connectors crossing the hub | Flow becomes confused with state. Route the ring outside or enlarge the radius. |
| Accent on multiple stations | The editorial gate disappears. Keep one focal station at most. |
| More than 8 stations | Labels and spokes crowd the hub. Split into overview + detail. |
| A cycle that never actually returns | That is a Flowchart arranged in a circle. Use Flowchart and show the real endpoint. |

---

## 8. Examples

- `assets/example-loop.html` — minimal light: six-station self-improving operating loop.
- `assets/example-loop-dark.html` — the same geometry under the dark token inversion.
- `assets/example-loop-full.html` — editorial page with the flagship loop, three summary cards, and colophon.
