# User Story Map

**Best for:** the Jeff Patton user story map — it answers "what is the whole story, and where do we cut the first release?" Narrative order runs left to right; priority runs top to bottom. The **release cut** is the editorial point of the diagram: a map without one is just a backlog in a grid.

This is neither **Kanban** nor **User journey**, and the distinction is load-bearing:

- **Kanban** shows *state* — columns are Todo/Doing/Done, there is no narrative order and nothing to slice.
- **User journey** shows *one persona's feelings* across stages via a sentiment curve.
- A **story map** has neither state nor sentiment. Its columns are **narrative order** and its rows are **release slices**. If you aren't slicing releases, use one of those two instead.

## Layout conventions

Vertical stack, top to bottom:

1. **Backbone** — up to 5 activities in left-to-right narrative order, as wide header cards (200px, `rx=6`, `ink @ 0.05` fill, `muted` stroke). Each card: the activity name in Geist sans 12px weight 600, above a Geist Mono 8px uppercase tracked eyebrow (`ACTIVITY 1` … `ACTIVITY 5`). 24px gutters between cards.
2. **Walking skeleton row** — directly under each activity, its user *steps* as smaller cards (`rx=4`, 32px tall, white fill, `ink` stroke), Geist sans 12px. One or two per activity; reserve room for two so every activity's row bottom aligns even when it only has one step.
3. **Release slices** — horizontal bands below the skeleton row, each a full-width lane with a Geist Mono 8px uppercase tracked label (`MVP`, `RELEASE 2`, `LATER`) sitting in a 96px left margin. Band background alternates `ink @ 0.02` / none. Inside each band, story cards (`rx=4`, 48px tall) sit in their activity's column: story title in Geist sans 12px weight 600, plus a Geist Mono 9px estimate/ticket sublabel (e.g. `RPT-114 · 3pt`). Whenever any slice has a gap (an activity with no card in that row), add `rule` hairline column separators (0.8px, dashed `4,4`, 0.10 opacity) running from just under the backbone down to the bottom of the last slice, drawn before the cards — without them, a gappy grid reads as scattered rather than mapped to its activity.
4. **The release cut line** — a full-width horizontal `accent` rule (1.5px) immediately under the MVP band, with a masked Geist Mono 8px label `RELEASE CUT` at its right end. This is accent element one.
5. **Legend** — horizontal strip at the bottom per the global rule (hairline separator above): one swatch for the default story card, one for the highest-risk treatment, one for the release-cut line.

## Focal rule

Exactly 2 accent elements: the release cut line with its `RELEASE CUT` label (counts as one), and the single riskiest story card — drawn with `accent @ 0.05` fill, `accent` dashed `4,4` stroke, and a small rectangular `RISK` tag (`rx=2`, matching the type-tag primitive) — counts as the other. Nothing else on the map is `accent`.

## Complexity budget

- Max 5 activities, max 3 release slices, max 12 story cards total, max 4 cards per slice.
- Max 2 accent elements (the release cut counts as one; the riskiest card counts as the other).
- Over budget on a single activity or slice → split into one map per activity, or collapse a slice into a count card rather than listing every item.

## Anti-patterns

- **No release cut.** A map with no cut line is a backlog in a grid, not a map — the cut is the whole point.
- **Columns ordered by priority instead of narrative sequence.** The backbone is a story, left to right, in the order the user experiences it — not a ranked list.
- **Story cards that are features, not user-visible outcomes.** "Add a chart" is a story; "Refactor the charting service" is not — it belongs in a backlog ticket, not the map.
- **Slices named by date instead of by outcome.** `MVP` / `RELEASE 2` / `LATER` describe scope; `Q3` / `Q4` describe a calendar and drift the moment the schedule slips.
- **More than 3 slices.** Beyond MVP, next, and later, nobody believes the ordering — collapse the tail into "Later."
- **Mixing two personas in one map.** One map per persona, same as user journey.
- **Adding state columns.** That turns it into a kanban board — this type has no state.
- **Adding a sentiment curve.** That turns it into a user journey — this type has no feelings axis.

## Examples

- `assets/example-story-map.html` — minimal light. *Reporting, first release*: four activities (`Find the data`, `Build the report`, `Share it`, `Trust it`), MVP/Release 2/Later slices, release cut under MVP, `Row-level permissions` flagged as the riskiest story.
- `assets/example-story-map-dark.html` — minimal dark, same data.
- `assets/example-story-map-full.html` — full editorial: container framing + 3 summary cards of varied widths + footer.
