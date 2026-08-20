# User Journey Map

**Best for:** what a person does across the stages of an experience and how it *feels* at each one. The sentiment curve is the load-bearing element — without it this is just a process diagram with extra rows, so if you can't name a sentiment for every stage, use **Process** or **Timeline** instead.

## Layout conventions

Vertical stack, top to bottom, for one persona:

- **Stage headers** — 5 equal columns, 200px wide, 24px gutters (max 6 stages). Each column: a Geist Mono 8px uppercase tracked eyebrow (`STAGE 1` … `STAGE 5`) over the stage name in Geist sans 12px weight 600, both centered on the column.
- **Sentiment band (the differentiator)** — a 160px-tall plot area directly under the headers. 3 horizontal reference hairlines at `rule` 0.10 opacity mark the levels `HIGH` / `NEUTRAL` / `LOW` — Geist Mono 8px `muted`, anchored `end` in a 64px left margin. **Never emoji, never `writing-mode` vertical text for these labels.** A smooth `muted` 1.5px polyline runs through one `r=5` dot per stage, each value snapped to one of five ordinal levels (`HIGH`, `MED-HIGH`, `NEUTRAL`, `MED-LOW`, `LOW`) — only the three that are actually used need a labeled hairline. The trough stage's dot and its incoming segment are `accent`; everything else on the curve is `muted`.
- **Content rows** — up to 3 labelled bands below the sentiment band, each with a Geist Mono 8px uppercase row label sitting in the left margin (same column as the sentiment level labels, never rotated):
  - `ACTIONS` — what the user does, Geist sans 12px, one short line per stage.
  - `TOUCHPOINTS` — the surface the action happens on (email, app, docs…), Geist Mono 9px `muted`.
  - An optional third row for a metric or owner, same treatment as touchpoints.
  Rows are separated by hairlines that span the full plot width (from the left margin edge to the last stage's right edge).
- **Pain markers** — on stages where sentiment drops, a small dashed-stroke tag box (`rx=2`, `accent @ 0.50` stroke dashed `3,3`, no fill or a faint accent tint) sits under that stage's actions cell, with a Geist Mono 8px label naming the friction. Max 2 per diagram, and only on the trough — tagging every stage erases the signal.
- **Legend** — horizontal strip at the bottom per the global rule (hairline separator above, 160–180px between entries): three keys, in order — the sentiment line, the trough-stage highlight, and the pain-marker tag. The trough key is not optional: the dip is the finding, so the reader needs the highlight named.

## Connector note

The sentiment polyline is a **data curve**, not a connector between nodes — §6 rule 1 (mandatory orthogonal elbows) does not apply to it. This exemption covers the sentiment curve **only**; any other connector in a journey map (there normally are none) still follows the standard connector rules.

## Geometry

- Stage grid: left margin 64px, then 5 columns of 200px with 24px gutters (`col_left = 64 + i·224`).
- Sentiment band: 160px tall. Hairlines at the top (`HIGH`), middle (`NEUTRAL`), and bottom (`LOW`) of the band, 80px apart.
- Dot x = the horizontal center of its stage column. Dot y = the snapped level's hairline y (or the interpolated position for an unlabeled level).
- Row height: enough for one line of text plus, in the `ACTIONS` row only, up to two stacked 16px-tall pain-marker boxes.

## Focal rule

Exactly 2 accent elements: the trough dot + its incoming curve segment (counts as one), and its pain marker(s) (counts as the other). Nothing else on the map is `accent`.

## Complexity budget

Max 6 stages · max 3 content rows · 5 sentiment levels (ordinal, named — never numeric) · max 2 pain markers · max 2 accent elements.

## Anti-patterns

- **No sentiment curve.** If every stage feels the same, or you can't name a feeling, you're drawing a process — use **Process** or **Timeline**.
- **More than 6 stages.** Split into two journeys (e.g. acquisition and retention) rather than cramming a wide funnel into one map.
- **Numeric sentiment axis** (a 0–100 score). Sentiment here is ordinal — five named levels, not a chart of a continuous metric.
- **Emoji as sentiment markers.** Use the named levels and hairlines; emoji don't localize, print, or hold up at small sizes.
- **Multiple personas on one map.** Overlaying two sentiment curves erases both. One map per persona.
- **Pain markers on every stage.** If nothing is un-marked, nothing is focal.
- **`writing-mode` vertical row labels.** Horizontal only, in the left margin — same rule as every other type in this skill.
- **Using it for an internal system flow with no human in it.** No person, no sentiment, no journey map — that's an architecture or data-flow diagram.

## Examples

- `assets/example-journey.html` — minimal light. *Trial to paid: the first week*, 5 stages, trough at "Hit the limit".
- `assets/example-journey-dark.html` — minimal dark, same data.
- `assets/example-journey-full.html` — full editorial: container framing + 3 varied-width summary cards + footer.
