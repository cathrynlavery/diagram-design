# Schedule network

**Best for:** which precedence chain determines completion, and where the slack is.
Use activity-on-node boxes when task durations and finish-to-start dependencies
are supplied. Use [Gantt](type-gantt.md) for dates and calendar overlap, or
[Dependency graph](type-dependency.md) for undated package/service dependencies
and cycles. A schedule network's box grid carries computed timings, not fan-in.

## Input and calculation

The initial contract is a connected DAG of 2–8 tasks, at most 12 directed links
and five precedence ranks. Durations are positive decimals, with at most nine
integer digits and six fractional digits; one lowercase unit of 1–8 letters is
explicit. No calendars, resource constraints, deadlines, lag/lead, probabilistic
PERT estimates or zero-duration milestones. Reject these rather than guessing.
A task's name has at most 18 ASCII letters/digits/spaces/hyphens; split a dense
view rather than abbreviate evidence silently.

Time starts at zero. For every task:

- `ES = max(predecessors' EF)`, or 0 at a start; `EF = ES + duration`.
- Project finish is the maximum terminal EF.
- `LF = min(successors' LS)`, or project finish at an end; `LS = LF − duration`.
- Total float `TF = LS − ES`. All and only zero-float tasks are critical.
- An edge is critical only if both endpoints are critical and
  `EF(source) = ES(target)`. A shortcut between critical tasks is not necessarily
  a critical edge. Preserve every tied critical branch, not just one path.

`scripts/verify-schedule-network.py` recomputes these with exact decimal
arithmetic. This checks consistency of the supplied graph, not whether durations
are credible, dependencies complete or a real project feasible.

## Layout grammar

Use an accessible SVG with `viewBox="0 0 1200 H"`, H between 368 and 1248, using
the shared static page shell shown by the examples. Tasks of one precedence rank
share x; rank is the longest predecessor chain, increasing left to right. Rank
spacing is at least box width plus 40px. Multiple starts/ends are valid.

Task and precedence groups must be direct children of the root SVG. Every task
has one paper rectangle, first in its group: width 192–240px (equal
across the view), height 176px, `rx="4"`. Text uses explicit house ink and
`Roboto Mono, monospace`. The repeated labelled schedule grid is:

| Field | Text | Position relative to task origin | Size |
|---|---|---|---|
| name | `A: Scope` | 16,24 | 12 |
| duration | `DUR 2 days` | 16,48 | 12 |
| es / ef | `ES 0` / `EF 2` | 16,76 / width÷2+8,76 | 12 |
| ls / lf | `LS 0` / `LF 2` | 16,104 / width÷2+8,104 | 12 |
| tf | `TF 0` | 16,132 | 12 |
| status | `CRITICAL` or `FLOAT` | 16,156 | 12 |

Do not add sub-elements to a bound text node. Values must fit the bounded cell;
no shrinking or rounding to make a claim fit. Critical boxes use 2px ink borders;
others 1px ink. Critical arrows use 2px ink, others 1px muted. This identifies the
whole critical set without spending an accent on each task. Keep the normal
accent budget for page hierarchy; colour is not the sole encoding.

Links attach to the source's right edge and target's left edge, at least 16px
from corners. Fan ports at least 12px apart. Use explicit absolute M/H/V/L paths,
with Q for perpendicular 8px rounded elbows, and avoid task interiors. A shaft
ends 12px before the target. Its open arrowhead has points `(tipX−8,tipY−6)`,
`(tipX,tipY)`, `(tipX−8,tipY+6)`; the tip lands on the target border. The Schedule network checker
verifies this geometry locally, including perpendicular departure/arrival, port
spacing and no border runs, crossings or stacked shafts. The common geometry
gate remains required for its other layout checks; its marker-based arrow
scanner does not claim these open-head groups.

## Machine-readable and printed bindings

```svg
<svg viewBox="0 0 1200 720" role="img" aria-labelledby="schedule-title schedule-desc"
     data-diagram-type="schedule-network" data-time-unit="days"
     data-project-duration="9" data-schedule-origin="0">
  <!-- Resolving title/desc and full-paper backdrop precede the marks. -->
  <g data-task-id="A" data-task-name="Scope" data-duration="2"
     data-critical="true" data-rank="0" data-diagram-role="task">
    <!-- One paper rectangle, then eight individually bound text nodes. -->
    <text data-schedule-field="es" x="64" y="316" fill="#0e1920"
          font-size="12" font-family="Roboto Mono, monospace">ES 0</text>
  </g>
</svg>
```

The fragment illustrates bindings, not a complete valid page. All eight fields
above are required once per task, with `data-schedule-field` equal to the field
name. IDs are unique uppercase identifiers of 1–6 letters/digits/hyphens, starting
with a letter. Each link is a `g` with `data-schedule-link="finish-to-start"`,
`data-from`, `data-to`, recomputed `data-critical="true|false"` and
`data-diagram-role="precedence"`, containing exactly the shaft and open head.

Three visible root-level text bindings are required:

- `data-schedule-summary="finish"`: `PROJECT FINISH 9 days`.
- `data-schedule-summary="assumptions"`:
  `ILLUSTRATIVE SCHEDULE · days · ORIGIN 0 · FINISH-TO-START · ZERO LAG`.
- `data-schedule-summary="scale"`:
  `Task widths and spacing are not proportional to time.`

The finish summary sits at 48,48 in 16px mono; assumptions at 48,660 and scale
at 48,688 in 12px mono. Keep all three start-anchored, in explicit house ink,
clear of every task box and within the viewport. Other unbound SVG text is
refused. Project finish allows ten integer digits to accommodate sums of
individual task durations.

Substitute the supplied unit and recomputed finish. Task width and spacing never
encode elapsed time; there is no time axis. A task's TF is total float, not free
float. The example's durations are illustrative, not a measured project plan.

## Verification boundary

Run `python3 scripts/verify-schedule-network.py --all` and
`python3 scripts/test-verify-schedule-network.py`. The common skin, accessibility,
render and geometry gates still apply. The new checker only claims Schedule
network files; sibling visual types retain their own checks.

Task border strokes must remain visible, including their effective stroke
opacity. The Schedule network subset has no standalone `<line>` marks; use
only the two explicitly typed arrow paths per precedence link. Extra lines
cannot be used to paint over a summary or task.

The bounded static subset refuses duplicate attributes, SVG CSS/class/inline-style
overrides, transforms, hidden/faint content, clips, masks, animation, nested SVGs
and namespace-prefixed tags
and unsupported scheduling metadata. Use the existing example page shell; this
is intentionally not a general browser CSS evaluator. Rounded shafts are checked
independently, then their orthogonal control hulls are used by the unchanged
shared visibility checker. Displayed text, project finish, critical status and
named arrow endpoints must match recomputed values. Arbitrary HTML prose outside
these bound SVG fields and the truth of input estimates are not certified.

## Anti-patterns

- A generic dependency graph called a critical path without duration/float cells.
- Correct hidden values next to incorrect visible labels.
- Treating every edge between critical tasks as critical, or hiding tied paths.
- Calendar dates derived from elapsed durations without actual calendar rules.
- A pseudo-time axis, proportional task-box widths or more data than the budget.
- Confusing total float with free float or a positive-duration task with a milestone.

## Examples

- `assets/example-schedule-network.html` — minimal light; finish 9 days, C float 1.
- `assets/example-schedule-network-dark.html` — the same task graph on dark paper.
- `assets/example-schedule-network-full.html` — the same graph with reading notes.
