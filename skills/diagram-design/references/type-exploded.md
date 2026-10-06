# Exploded axonometric

**Best for:** one object or system drawn in parallel projection with its parts pulled apart along one axis and labelled. A device teardown (what is inside a phone), an unboxing (lid, product, insert, box), assembly order, or the layers of a stack when the reader should see them as physical parts of one thing.

**Not this type:**

- Ordered abstraction levels with a note on each row → **layer stack** (`type-layers.md`). A layer stack is flat bands of text; an exploded view is the parts of one object. If nothing in the figure has a footprint or a thickness, use the layer stack.
- Components and the connections between them → **architecture** (`type-architecture.md`). An exploded view has no arrows; position along the axis is the only relationship.
- Containment without an order → **nested** (`type-nested.md`).
- Where software runs → **deployment** (`type-deployment.md`).

## Projection

2:1 dimetric. The ground axes run at 26.565 degrees, so every edge lands on whole pixels when model units are multiples of 4. World x runs right and down, y runs left and down, z runs up. Project every point with one function and never place a coordinate by hand:

```python
from math import sqrt

def iso(x, y, z, ox, oy):
    """Model point to SVG point. (ox, oy) is where model (0, 0, 0) lands."""
    return ox + x - y, oy + (x + y) / 2 - z
```

A rounded-rectangle footprint of corner radius `r` projects to straight edges joined by quarter arcs of one ellipse with `rx = r * sqrt(2)` and `ry = r / sqrt(2)`. Use that one shape for everything: `r = 0` is a box or slab, a small `r` is a product corner, and `r = w / 2 = d / 2` is a cylinder. Corner centres stay fixed when you inset an outline, so an inner rim is the same four centres at a smaller radius.

Draw faces as plain SVG `<path>` and `<polygon>` elements with the projected points written in. No CSS 3D, no canvas, no WebGL, and no `transform` to place geometry. If content ever has to sit flat on a face, the matrices that agree with `iso()` are `matrix(1,0.5,-1,0.5,tx,ty)` for the top face, `matrix(1,0.5,0,-1,tx,ty)` for the left face, and `matrix(-1,0.5,0,-1,tx,ty)` for the right face. Labels never use them: labels stay horizontal.

`scripts/build-exploded-examples.py` in the repository builds every shipped example from this function and is the worked reference for the helpers below.

## Layout conventions

- **Parts:** 2 to 5, listed bottom to top. Each part is a rounded prism (`rect`, thickness `t`) plus at most two levels of detail on its top face, because the top face is the one the reader sees.
- **Explode axis:** Vertical by default. Parts move straight up, nothing rotates, and the bottom part stays at `z = 0`.
- **Levels:** Parts that sit side by side in the assembled object share a level and explode together. A phone's logic board and battery sit next to each other inside the housing, so they lift as one level instead of stacking two gaps apart.
- **Gap:** One gap between every pair of levels, `gap = max(k x top-face height, 3 x thickness of the thickest solid part)`, rounded up to a multiple of 4. `k = 0.5` is the floor; raise it to `0.75` when a tall part would hide the focal part below it. Top-face height is `(w + d) / 2` of the largest footprint. Containers (a housing, a box) do not count toward thickness.
- **Clearance:** If a leader would cross another part, or two labels would sit closer than 36px, raise the gap in steps of 4 until neither happens. Two parts on one level that collide cannot be fixed by the gap: move one of them in plan.
- **Paint order:** Bottom level first. Inside a level, parts farther back (smaller `x + y`) paint first. A container is split: its back half (silhouette, rim, cavity, floor) paints before the parts that sit inside it, and its outer walls and front rim paint after them. This is the only way an assembled frame shows the parts inside a tray correctly, and it stays correct throughout an explode.
- **Frame:** The canvas is 1000 wide. The object and a 240px label column are centred together; the viewBox height follows the exploded object plus a 40px top margin. Nothing is clipped at the closed frame either, because the closed object fits inside the exploded one.

### Faces and lines

| Element | Light | Dark |
|---|---|---|
| Face base (opaque, under every face) | `#ffffff` | `paper-2` `#393e53` |
| Top face | base | base + `rgba(245,245,245,0.10)` |
| Left face (lit side) | base + `rgba(45,49,66,0.07)` | base |
| Right face (shade side) | base + `rgba(45,49,66,0.15)` | base + `rgba(45,49,66,0.45)` |
| Focal part, top / left / right | `accent` at 0.10 / 0.20 / 0.32 over base | `accent` at 0.18 top, neutral sides |
| Silhouette | `ink`, 1.2 (`stroke-strong`) | `ink`, 1.2 |
| Inner edges (top-front rim, front corner) | `ink` at 0.55, 0.8 (`stroke-thin`) | `ink` at 0.45, 0.8 |
| Detail lines on a face | `ink` at 0.55, 0.6 to 0.8 | same |
| Trace lines | `ink` at 0.30, 0.8, dashed `4,3` | `ink` at 0.30, 0.8, dashed `4,3` |

Light comes from the top left, so the left face is lighter than the right. Always shade: an outline-only box flips between two readings like a Necker cube. Faces are an opaque base plus an `ink` overlay, never a translucent fill on its own, so parts behind never show through. Trace lines run straight up through the left and right extremes of the bottom part's outline to the underside of the top part, and paint before every part so the parts cover them.

### Labels

- One label per part, in one column to the right of the object. A label is the part name (Geist 600, 16px, one or two words) above a technical sublabel (Geist Mono 10px, `muted`, tracked 0.08em).
- A horizontal leader (0.8px, `ink` at 0.40) runs from 6px right of a 2px dot on the part's right extreme, at mid-thickness, to 12px left of the column. Leaders never bend, never cross a part, and never cross each other; horizontal leaders from distinct heights cannot cross each other, and the gap rule above keeps them clear of parts.
- The focal part's dot, leader, and sublabel take the accent. Its name stays `ink`.
- No numbered callouts and no legend. The label is on the part it names.

### Detail

Three levels at most: the form (the rounded prism), insets on its top face (a screen, a cell outline, a moulded well), and micro detail (chips, lenses, a logo mark). A part made of many identical pieces, such as keycaps or switches, declares the envelope of its grid as its box and paints one small prism per piece instead of the envelope; the silhouette path is still there for the verifier, with no fill. Clip any inset that could reach a face edge to that face, keep it 4 units or more inside the edge, and stop at three levels. No contact shadow: shadows are out in this skin (SKILL.md §4). If the object needs grounding, the bottom part already provides it.

### Focal part

One part at most wears the accent, under the SKILL.md rule of 1 to 2 focal elements. The other parts stay neutral; do not fade them with opacity, because a translucent part shows the edges behind it.

## Optional motion

An exploded view may open as the assembled object and explode once, because watching the parts lift shows how they fit together. Use the pinned controller from `assets/template-motion.html` in `reveal` mode, per `animation.md`:

- The source file is the exploded frame. Every part group carries `data-motion-item`, a `data-step` counted from the top level down (top level lifts first), and `style="--lift:Npx"` where `N` is the part's exploded `z` minus its assembled `z`. In this projection a straight-up move in model space is a straight-up move on screen, so one `translateY(var(--lift))` is the whole explode.
- The bottom level does not move. Its label and the trace lines arrive together as the last step.
- Each part's label hides at the closed frame and fades in after its part settles. Hide instantly and delay only the reveal, or labels pile up on the closed object for the first half second.
- No JavaScript, `prefers-reduced-motion: reduce`, print, `?motion=static`, and export all show the exploded frame.
- The lift is the one scoped exception to the 24px translation limit in `animation.md`, recorded in the repository as ADR 0013. Nothing else in the figure moves.

## Metadata contract

`scripts/verify-exploded.py` reprojects each part from what it declares:

- The figure: one `<g data-exploded data-origin="ox oy" data-gap="g">` wrapping every part.
- Each part: a `<g>` with `data-part` (key), `data-name` (the label text), `data-rect="x0 y0 x1 y1 r"`, `data-z`, `data-t`, `data-level`, optional `data-kind="housing"` for a container and `data-focal` for the focal part. Animated parts add `data-closed-z`.
- Inside each part: the first `<path data-role="silhouette">` is the part's outline at its declared box, and a `<g data-role="label">` holds a `<line data-role="leader">` and a `<text data-role="name">`.
- Trace lines carry `data-role="trace"`.

## Anti-patterns

- Hand-placed coordinates, or a CSS `transform` standing in for geometry.
- Outline-only parts with no face shading.
- Parts that rotate, slide sideways, or explode along two axes in one figure.
- Unequal gaps, or a gap shrunk to fit the canvas. Raise `k` or cut a part.
- Labels on the parts, angled with a face, or spread across two columns.
- Numbered callouts with a key underneath.
- More than one part in the accent, or the other parts faded to show which one matters.
- Blurred contact shadows, gradients on solid faces, or glow.
- An exploded view of something with no physical sense of parts. If the layers are just a list, use the layer stack.

## Examples

- `assets/example-exploded.html`: app stack, minimal light
- `assets/example-exploded-dark.html`: app stack, minimal dark
- `assets/example-exploded-full.html`: app stack, full editorial
- `assets/example-exploded-phone.html`, `-dark`, `-full`: phone teardown with a housing, a shared board and battery level, and a display
- `assets/example-exploded-unboxing.html`, `-dark`, `-full`: packaging with a telescoping lid, a product and cable on one level, an insert, and a box
- `assets/example-exploded-ai-stack.html`, `-dark`, `-full`: an AI agent stack with a secrets vault, tools, skills as small cards on one layer, the agent harness around the model, and the interface
- `assets/example-exploded-keyboard.html`, `-dark`, `-full`: a mechanical keyboard with a case tray, PCB, plate, a grid of switches, and a grid of keycaps
- `assets/example-exploded-phone-animated.html`: the phone assembled, then exploded once
- `assets/example-exploded-unboxing-animated.html`: the box closed, then unpacked once
- `assets/example-exploded-ai-stack-animated.html`, `assets/example-exploded-keyboard-animated.html`: the stack and the keyboard assembled, then exploded once
