# Gantt Chart

**Best for:** project plans and roadmaps — tasks with explicit start and end dates, grouped into phases. Use when the reader needs to see temporal overlap, parallel tracks, and milestone sequencing at a glance.

## Layout conventions

- **Left label column:** x=20–200 (180px). Task names in Geist sans 11px 600. Phase labels as Geist Mono 7px eyebrows above each group.
- **Timeline area:** x=200–960 (760px). Time axis runs left→right.
- **Row height:** 40px per task. Each bar occupies h=24px centered in the row (8px top padding).
- **Time axis:** Geist Mono 8px week/month labels at x=200+i×pitch, y=56 (just above first task row). A hairline separator at y=64.
- **Phase grouping:** a subtle zone rect (same pattern as architecture zone) behind each phase's rows, with an eyebrow label in the top-left margin. Use `rgba(45,49,66,0.02)` fill, `rgba(45,49,66,0.10)` stroke.
- **Focal task bar:** 1 bar in accent fill/stroke (the key deliverable or critical path task). All others: muted fill @ 0.15, muted stroke.
- **Today / milestone marker:** optional vertical dashed line in `muted` at the current week x-position.

### Task bar pattern

```svg
<!-- Non-focal task -->
<rect x="X_start" y="ROW_Y+8" width="DURATION_PX" height="24" rx="4"
      fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1"/>
<text x="X_start+8" y="ROW_Y+25" fill="#2d3142" font-size="10" font-weight="600"
      font-family="'Geist', sans-serif">Task name</text>

<!-- Focal task -->
<rect x="X_start" y="ROW_Y+8" width="DURATION_PX" height="24" rx="4"
      fill="rgba(235,108,54,0.12)" stroke="#eb6c36" stroke-width="1"/>
<text x="X_start+8" y="ROW_Y+25" fill="#eb6c36" font-size="10" font-weight="600"
      font-family="'Geist', sans-serif">Key task</text>
```

Duration in pixels: `(end_week - start_week) × pitch`. Pitch = timeline_width / total_weeks.

## Anti-patterns

- More than 12 tasks (splits into sub-plans or collapses into phase-level view).
- More than 5 parallel tracks per phase (illegible overlap).
- Dependency arrows between tasks in v1 (add only when essential; use the annotation primitive for labels).
- Start/end dates in the bar label (put them in the x-axis or tooltip comment instead).
- Equal visual weight for all bars (the focal task must stand out).

## Examples

- `assets/example-gantt.html` — minimal light
- `assets/example-gantt-dark.html` — minimal dark
- `assets/example-gantt-full.html` — full editorial
