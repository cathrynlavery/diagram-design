# Event modeling

**Best for:** showing how commands, resulting domain events, and read models relate across ordered business stages. Use it when the supplied scenario names those elements and their links. The horizontal axis is scenario order unless timestamps or durations are supplied. An illustrative example must say so.

**Not this type:** Use [Sequence](type-sequence.md) for actor lifelines, message calls, and replies in temporal order. Use [Data flow](type-data-flow.md) for movement or transformation between systems when commands and resulting events are not the question. Use [Timeline](type-timeline.md) for dated occurrences without command and projection roles. Do not infer an event store, broker, or persistence mechanism from this view.

## Layout grammar

- Arrange numbered stages left to right. Align **Command**, **Event**, and **Read model** in three fixed horizontal lanes. Within each stage, the command sits above the resulting event, and the read model sits below it.
- A command is an intent/request, named as an imperative. An event is a fact that occurred, named in past tense. A read model is a view or projection, not another event. Show each role explicitly in text and metadata.
- Draw a directed `emits` link from command to event and a directed `projects` link from event to read model. The diagram claims these links only when supplied by the source. If a link is unknown, label the gap; do not silently connect unrelated marks.
- Stage order does not encode elapsed time. Do not space stages proportionally to time without a measured axis. If a stage branches, split the scenario or use [Flowchart](type-flowchart.md) for the decision.

### Machine-readable contract

Put `data-diagram-type="event-modeling"` on the accessible SVG. Each stage is a group with `data-event-stage="STAGE-ID"`, a unique ID, `data-stage-order` starting at `1`, and `data-diagram-role="timeframe"`. Each role node has `data-event-kind="command|event|read-model"`, a unique `data-event-id` printed in the node, and a matching `data-diagram-role`. Each link has `data-diagram-role="event-link"`, `data-event-rel="emits|projects"`, `data-from`, and `data-to` pointing to IDs in that stage. `scripts/verify-event-modeling.py` checks this structural contract for the shipped examples; it does not establish that an illustrated business event happened.

## Complexity budget

- At most six stages. The overview uses one command, one event, and one read model per stage. Split richer scenarios into overview and detail views instead of shrinking labels.
- At most two accent uses. The event and link labels must carry meaning without color.

## Anti-patterns

- Commands and events in the same lane, or an event named as a future instruction.
- A left-to-right stage layout presented as measured duration.
- A read model shown as proof of persistence, delivery guarantee, or test coverage.
- A generic producer-broker-consumer flow renamed as event modeling with no commands or projections.

## Examples

- `assets/example-event-modeling.html` — minimal light, illustrative three-stage scenario.
- `assets/example-event-modeling-dark.html` — the same scenario on the dark skin.
- `assets/example-event-modeling-full.html` — full editorial page with reading notes.
