# Kanban Board

**Best for:** a snapshot of work-in-progress by state — what is queued, what is moving, what is stuck, and where the WIP limit is being breached. This is a *state census*, not a flow: a kanban board has **no connectors at all**. That is exactly what separates it from swimlane (lanes plus a flow crossing them, with handoffs as the load-bearing edges) and from process (ordered steps with directional handoffs). If the diagram needs an arrow anywhere, it isn't a kanban board anymore — reach for swimlane or process instead.

## Layout conventions

- **Up to 5 vertical columns of equal width (240px), 32px gutters.** Column background is `ink @ 0.02`; no column border.
- **Header band per column:** column name in Geist sans 12px weight 600, anchored left. A right-anchored **WIP chip** — a rectangular tag (`rx=2`, **never** a pill) holding `n/limit` in Geist Mono 8px — or bare `n` on a queue or terminal column, which carries no limit. Every in-process column states one. A hairline `rule` separator sits directly under the header band, full column width.
- **Cards:** the §6 node-box pattern at `rx=6`, column width minus 16px padding on each side, 56px tall, 12px vertical gap between cards. Content: title in Geist sans 12px weight 600, and a Geist Mono 9px `muted` sublabel line for `TICKET-ID · owner` (e.g. `AVA-214 · nadia`).
- **Drawing order:** background → column fills → header text + WIP chips → header rules → cards (each: box, then left accent bar if blocked, then title, then sublabel) → legend.

## Card states — the type's semantic vocabulary

Every card renders in exactly one of four states. Document and use all four when the board has enough cards to show them:

| State | Fill | Stroke | Extra |
|---|---|---|---|
| `default` | white | `ink` | — |
| `blocked` | `accent @ 0.05` | `accent` (full opacity) dashed `4,4` | 4px `accent` bar on the card's left edge |
| `waiting / external` | `ink @ 0.02` | `ink @ 0.20` dashed `4,3` | — |
| `done` | `ink @ 0.05` | `muted` | — |

These map directly onto the SKILL.md §5 node-treatment table (`security` → blocked, `optional` → waiting/external, `store` → done) — the board reuses the system's existing semantic fills rather than inventing new ones.

## Over-limit column

When a column's card count `n` exceeds its stated `limit`, the WIP chip's stroke and text go `accent`. That plus one blocked card is the full 2-accent budget for the diagram — don't spend the budget anywhere else.

## Complexity budget

- Max 5 columns, max 4 cards per column, max 12 cards total.
- Max 2 accent elements (the over-limit chip counts as one; a blocked card counts as one).
- Over budget on a single column → aggregate the backlog into one count card (`+14 more`) rather than listing every item.

## Anti-patterns

- **Drawing arrows between cards.** A board shows state, not flow — if the flow itself needs to be visible, use swimlane or process instead.
- **More than 4 cards in a column.** Aggregate into a count card; don't let a column scroll off the canvas.
- **One card per person.** That's an org chart wearing a kanban skin.
- **In-process columns without WIP limits.** The limit is half the point of the type — a column work flows *through* with no stated limit can't show that it's over budget. The entry queue and the terminal column are the exception: nothing is constrained by holding more done work, so they show a bare count.
- **Accenting every blocked card.** One or two blocked cards read as signal; a column full of accent reads as noise and erases the focal rule.
- **A "Done" column that grows without bound.** Cap it and note the archive point in the sublabel or a footnote — an unbounded Done column just becomes a second Backlog.
- **Pill-shaped WIP tags.** The chip is a rectangle at `rx=2`, matching the type-tag primitive in §6 — pills read as status badges from an unrelated design language.

## Examples

- `assets/example-kanban.html` — minimal light. Platform-team board: Backlog (3), In progress (4/3, over limit), Review (2/3), Done (2), one blocked card.
- `assets/example-kanban-dark.html` — minimal dark, same data.
- `assets/example-kanban-full.html` — full editorial: container framing + 3 summary cards of varied widths + footer.
