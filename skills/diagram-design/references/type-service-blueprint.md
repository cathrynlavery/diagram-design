# Service Blueprint

**Best for:** showing how a service actually runs across a few stages — what the customer does, what they can see, and what stays hidden. The **line of visibility** is the load-bearing element: customer and frontstage actions sit above it, backstage and support sit below it, on one shared stage grid. Use it when the reader needs to see that a failure is a billing job, a queue, or a fraud check even though the customer row still looks like a simple retry.

**Not this type:**

- Sentiment across stages, no backstage → **User journey** (`type-journey.md`). A journey's load-bearing element is the feeling curve. If you cannot name a frontstage/backstage split, you are not drawing a blueprint.
- Flow with handoffs across named owners → **Swimlane** (`type-swimlane.md`). Arrows are the claim there. A blueprint is a census: stage order is the sequence, and wait times are cell text.
- Sequential nodes with data payloads → **Process** (`type-process.md`).
- One person's phases, waits, retries → **Lifecycle phase map** on State machine (`semantic-patterns.md` § 9).
- State census in columns, no visibility line → **Kanban** (`type-kanban.md`). Columns there are *states*, not narrative stages.
- Narrative backbone × release slices → **Story map** (`type-story-map.md`). The cut line is scope, not visibility.
- Abstraction bands with no stage columns → **Layer stack** (`type-layers.md`).

## Layout conventions

- **Orientation:** stages as equal columns (left → right in narrative order), layers as labeled rows (top → bottom). No connector arrows in this version — that is swimlane territory.
- **ViewBox:** `0 0 1280 720` for the minimal examples. Full editorial keeps the same SVG and adds cards.
- **Left margin:** 96px for layer labels. Geist Mono 8px, uppercase, horizontal, `text-anchor="end"` at x=88. **Never** `writing-mode: vertical`.
- **Stage grid:** 4–6 columns. The worked example is 5 × 208px with 16px gutters (`col_x = 96 + i·224`). Each header carries `data-stage` on a rect at the column origin; every cell in that column uses the same `x`.
- **Layer order, top to bottom:**
  1. Physical evidence (optional) — 48px
  2. Customer actions (required) — 64px
  3. Line of interaction (hairline)
  4. Frontstage actions — onstage staff or the visible product (required) — 64px
  5. **Line of visibility** (load-bearing; heavier than the other lines)
  6. Backstage actions (required) — 64px
  7. Line of internal interaction (hairline)
  8. Support processes (optional) — 48px
- **Hairlines:** 8px band including stroke. Interaction and internal-interaction are 1px `rule` (`data-role="interaction"` / `data-role="internal-interaction"`). Visibility is 2px `ink` at 0.55 opacity (`data-role="visibility"`), which must clear 3:1 on paper — 0.45 fails that bar on light paper, so do not go thinner.
- **Cells:** one action per stage per layer. Geist 12px, one line, centered on the column. A second muted mono line is allowed for a system or wait (`dunning-job · 4h`). Empty required cells are allowed only with an explicit `—` or `Not applicable` as `data-name` and as the printed text.
- **Fills:** customer and frontstage are paper/white with `ink` stroke. Backstage and support take a light `ink` tint so the below-the-line band reads as hidden work, not another onstage row.
- **Focal cell (≤1, optional):** the failure, wait, or handoff the figure exists to show — usually on or below the visibility line. Accent fill `rgba(235,108,54,0.12)` (dark: `rgba(240,138,89,0.18)`), accent stroke, `data-focal="true"`.
- **Legend:** horizontal strip after a hairline rule, three keys in this order — visibility line, backstage layer, focal cell.

### Machine-readable data contract

Every layer group: `data-layer="evidence|customer|frontstage|backstage|support"`.

Every cell: `data-stage="<stage-id>"` matching a header `data-stage`, plus `data-name` for the printed action.

Visibility line: `data-role="visibility"`. The two hairlines: `data-role="interaction"` and `data-role="internal-interaction"`.

Optional focal cell: `data-focal="true"` on at most one cell.

No `transform`, geometry `style`, or `<style>` rules that move marks.

`scripts/verify-service-blueprint.py` reads these and fails the build when the drawing and the declaration disagree.

### Service-blueprint element pattern

```svg
<!-- Stage header at column origin x=96; cells in this column reuse that x -->
<rect x="96" y="24" width="208" height="48" fill="none" data-stage="sign-up"/>
<text x="200" y="60" fill="#2d3142" font-size="12" font-weight="600"
      font-family="'Geist', sans-serif" text-anchor="middle">Sign up</text>

<g data-layer="customer">
  <rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142"
        stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>
  <text x="648" y="164" fill="#2d3142" font-size="12" font-family="'Geist', sans-serif"
        text-anchor="middle">Retry payment</text>
</g>

<!-- Visibility line: 2px ink @ 0.55, between frontstage bottom and backstage top -->
<line x1="96" y1="268" x2="1200" y2="268" stroke="rgba(45,49,66,0.55)" stroke-width="2"
      data-role="visibility"/>

<g data-layer="backstage">
  <rect x="544" y="272" width="208" height="64" rx="4" fill="rgba(235,108,54,0.12)"
        stroke="#eb6c36" stroke-width="1" data-stage="hit-limit"
        data-name="dunning-job timeout" data-focal="true"/>
  <text x="648" y="300" fill="#eb6c36" font-size="12" font-weight="600"
        font-family="'Geist', sans-serif" text-anchor="middle">dunning-job timeout</text>
  <text x="648" y="318" fill="#4f5d75" font-size="8" font-family="'Geist Mono', monospace"
        text-anchor="middle">dunning-job · 4h</text>
</g>
```

## Anti-patterns

- **No visibility line**, or a line that sits in the wrong gap (not between frontstage and backstage). Without the line this is just a table of rows.
- **Sentiment curve on a blueprint.** That is a journey; split the figures.
- **Arrows crossing layers.** That is a swimlane.
- **Accent on every failing cell.** One focal cell; the rest of the grid is census.
- **Empty required layers** with no `—` / `Not applicable` mark.
- **More than 6 stages**; more than two lines of cell text.
- **`writing-mode` vertical layer labels.** Horizontal only, in the left margin.

## Honesty rules

- **The grid is a census, not a flow chart.** Stage order is the sequence. Wait times and system names are cell text, not edges.
- **Required layers are complete.** Every stage has a customer cell, a frontstage cell, and a backstage cell. An empty slot still occupies its column and says so.
- **The visibility line is checkable.** It spans the plot, sits in the frontstage/backstage gap, and its stroke clears 3:1 against paper.
- **Printed text matches `data-name`.** A cell that draws "Retry payment" and declares another action is two stories.

These rules are executable: `scripts/verify-service-blueprint.py` reads the declarations and fails on layer order, visibility, grid, census, focal, budget, printed-label, contrast, or CSS-moved marks. `scripts/test-verify-service-blueprint.py` proves both polarities — the shipped examples pass, and each mutation class above fails with a named finding.

## Examples

- `assets/example-service-blueprint.html` — minimal light. *Trial to paid — what the customer never sees*, 5 stages, focal backstage `dunning-job timeout` under "Hit the limit".
- `assets/example-service-blueprint-dark.html` — minimal dark, same data.
- `assets/example-service-blueprint-full.html` — full editorial: container framing + 3 varied-width summary cards + footer.
