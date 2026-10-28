# ADR 0014: Axonometric plan is a site and floor grammar

**Status:** accepted

## Context

ADR 0013 admitted the exploded axonometric: one object, parts lifted apart along an axis. The same projection also draws a figure the skill could not: one floor or one site seen from above at an angle, with rooms, furniture, buildings, and roads standing on it. ADR 0002 admits a new type only for a new layout grammar, so the nearest existing grammars were audited:

- **Exploded axonometric** lifts parts of one object apart and labels them in a leader column. A plan has a single plate, nothing moves apart, and its labels belong on the rooms and roofs they name.
- **Nested** shows containment. It has no geography: two rooms side by side and two rooms at opposite ends of a floor draw the same.
- **Deployment** places software on hosts in a logical topology.
- **Quadrant** and **Wardley map** place items on abstract axes, not on a floor.

None of them draws boxes standing on a shared ground plane in their real positions, painted back to front, with tags on the things they name.

## Decision

Add **Axonometric plan** as visual type #44 with the full §10 shipping set: `references/type-axonometric-plan.md`, an office floor plan triple, a campus site plan triple, an animated campus, gallery tabs, the selection-table row and frontmatter hook, a budget row (8 tagged rooms or buildings, 40 boxes, 1 focal), the canonical screenshot, and an executable contract.

Every element declares its geometry. The plate and each box state their footprint and height, and each tag states the plan point it sits on. `scripts/verify-axonometric-plan.py` reprojects every silhouette with the projection already independent of the builders (it reuses the functions in `verify-exploded.py`), and fails on projection drift, a box off the plate or floating above it, two footprints sharing floor, a box painted after one in front of it, a tag off its point or standing on a room or roof it does not name, overlapping or doubled tags, a room or building with no tag, more than one focal element, and any transform or style. `scripts/test-verify-axonometric-plan.py` proves both polarities per ADR 0005.

Two scoped decisions:

- **Depth order is topological.** Boxes on a plate paint back to front by a sort over footprints: A before B when A lies entirely behind B and their screen outlines overlap. A sort on `x + y` draws a long wall over the desk in front of it, so the verifier checks the order.
- **Tags on the things they name.** A floor plan has too many named things in too many places for one leader column, and horizontal leaders would cross walls. Tags sit on the floor or roof they name, paint last, and must not overlap.

The projection helpers both builders use now live in `scripts/axonometry.py`. The exploded examples rebuild byte for byte after the move.

## Consequences

- The verifiable type count moves to 44. ADR 0002 is amended in the same change.
- The plugin manifest descriptions were at the 500-character limit again. They now read "exploded/plan" for the two axonometric types and list user journey as "journey", with matching `DESCRIPTION_ALIASES` entries. The Codex `longDescription` keeps the full names.
- The phased campus reveal moves each building 16px, inside the 24px limit, so it needs no motion exception.
