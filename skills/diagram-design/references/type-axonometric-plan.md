# Axonometric plan

**Best for:** one floor or one site seen from above at an angle, with what stands on it. An office floor with its rooms and furniture, a campus with its buildings and roads, a warehouse with its zones, a store layout. Use it when the reader needs to see rooms or buildings in relation to each other and how they are used, in a single view.

**Not this type:**

- Parts of one object pulled apart along an axis → **exploded axonometric** (`type-exploded.md`). A plan has one plate and nothing explodes.
- Containment without geography → **nested** (`type-nested.md`).
- Where software runs → **deployment** (`type-deployment.md`).
- A list of rooms and capacities → a table.

## Projection

The same 2:1 dimetric projection as the exploded axonometric, from one function:

```python
def iso(x, y, z, ox, oy):
    """Model point to SVG point. (ox, oy) is where model (0, 0, 0) lands."""
    return ox + x - y, oy + (x + y) / 2 - z
```

Every element is a rounded prism standing on the plate: `r = 0` for walls, furniture, and buildings, `r = w / 2` for a tree canopy. `type-exploded.md` § Projection covers the corner ellipse and the face matrices; `scripts/build-axonometric-plan-examples.py` in the repository builds every shipped example from the same helpers.

## Layout conventions

- **Plate:** One floor slab (6 units) or one site (8 units, small corner radius). Everything stands on it, and nothing extends past its edge.
- **Walls:** 6 units thick and cut at desk height, about 22 units, so no wall hides a room. Doors are gaps in a wall. Walls meet without overlapping: run one wall through a junction and stop the other at its face.
- **Furniture and buildings:** Boxes on the plate with the house face shading (`type-exploded.md` § Faces and lines). Heights are to scale with each other. Two footprints never overlap.
- **Flat marks:** Roads, paths, and floor tints sit on the plate's top face as flat fills (`ink` at 0.07) with no thickness. A dashed centre line (`ink` at 0.25, `6,5`) may mark a road.
- **Racks:** Tall shelving is a box of kind `rack` with the house shading, a shelf line every 14 units, and an upright every 30. Run rack rows along x so the reader sees the lit face and the aisles between rows.
- **Trees:** A canopy cylinder 8 units up on a short trunk, canopy top in `rule-solid` light (`#bfc0c0`) or `soft` dark (`#8e98ac`). Trees are planting, so keep them small and off every footprint.
- **Paint order:** The plate first, then flat marks, then every box back to front. Sort with a topological order: box A paints before box B when A lies entirely behind B (`A.x1 <= B.x0` or `A.y1 <= B.y0`) and their screen outlines overlap. A plain `x + y` sort fails on long walls.
- **Frame:** The canvas is 1000 wide and the plate is centred. The viewBox height follows the plate and its tallest box plus a 48px top margin.

### Tags

- Rooms and buildings are named by a horizontal tag: the name in Geist 600 12px above a sublabel in Geist Mono 8px, on an opaque `paper` backing with a `rule` hairline, 32px tall, width rounded up to a multiple of 4.
- A room's tag sits on open floor inside the room. A building's tag sits on its roof. Tags paint after every box so walls never cut them.
- Tags never overlap each other. Move a tag to open floor before you shorten its name.
- One or two words per name. No leader lines and no numbered key.

### Focal element

One room or one building wears the accent. A focal room gets an `accent` tint on its floor and an accent tag; a focal building gets the accent face ramp and an accent tag. Furniture inside a focal room stays neutral, so the accent marks one thing.

## Optional motion

A site that is built in phases can reveal its buildings phase by phase with the pinned controller from `assets/template-motion.html` in `reveal` mode. Each building and its tag form one `data-motion-item` whose `data-step` is its phase, at most two per step. Buildings drop 16px into place and fade in, inside the 24px limit in `animation.md`.

A floor plan can reveal by zone the same way. Give each zone's furniture a `step`, and the builder paints each phase as one contiguous group of boxes (it contracts a phase to one node in the depth sort, so a phase that would have to paint on both sides of a static wall fails the build) plus one group of that phase's room tags after every box. That is two motion items per phase, inside the limit of two per step. Walls and unphased rooms stay static. The static, no-JavaScript, reduced-motion, print, and export states show the finished site.

## Metadata contract

`scripts/verify-axonometric-plan.py` reprojects each element from what it declares:

- The figure: one `<g data-axo-plan data-origin="ox oy">`.
- The plate: one `<g data-plate data-rect="x0 y0 x1 y1 r" data-z="0" data-t="t">`.
- Each box: a `<g data-box>` with `data-rect`, `data-z` (the plate top, or 8 above it for a tree canopy), `data-h`, `data-kind` (`wall`, `furniture`, `building`, `tree`, `rack`), and for a building `data-name`. Its first path is `data-role="silhouette"`.
- Each room: a `<g data-room data-name data-rect>`.
- Each tag: a `<g data-role="tag" data-name data-at="x y z">` with a backing `<rect>` and a `<text data-role="name">`. Its complete text, including inline `<tspan>` descendants, must match the tag's `data-name`. The point sits inside the room it names at the plate top, or on the building's roof.
- The focal room or building carries `data-focal`.

## Anti-patterns

- Full-height walls that hide the rooms behind them.
- Boxes that overlap on the plate, or a box hanging past the plate edge.
- Painting by `x + y` alone, which draws long walls over the furniture in front of them.
- Tags tilted onto the floor plane, tags that overlap, or a numbered key under the figure.
- Accent on the focal room and on its furniture as well.
- Gradients, shadows, or glow on the plate or the boxes.

## Examples

- `assets/example-axonometric-plan.html`: office floor, minimal light
- `assets/example-axonometric-plan-dark.html`: office floor, minimal dark
- `assets/example-axonometric-plan-full.html`: office floor, full editorial
- `assets/example-axonometric-plan-campus.html`, `-dark`, `-full`: campus site plan with roads, trees, and buildings tagged by phase
- `assets/example-axonometric-plan-coffee-shop.html`, `-dark`, `-full`: a coffee shop with an entrance and queue posts, an espresso bar, round tables, a kitchen, and a restroom
- `assets/example-axonometric-plan-warehouse.html`, `-dark`, `-full`: a fulfillment floor with dock doors, tall storage racks, a pick zone, packing stations, and shipping docks
- `assets/example-axonometric-plan-campus-animated.html`: the campus built phase by phase
- `assets/example-axonometric-plan-coffee-shop-animated.html`, `assets/example-axonometric-plan-warehouse-animated.html`: each floor revealed zone by zone in three phases
