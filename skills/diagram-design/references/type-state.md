# State Machine

**Best for:** finite state logic — order status, auth state, connection lifecycle, form wizard, job queue status.

## Layout conventions
- States are rounded rectangles (`rx=8`), labeled in the `node-name` role.
- **Start**: filled ink dot (`r=6`). **End**: ringed dot (outer `r=8` outline, inner filled `r=5`).
- Transitions: curved arrows labeled in the `arrow-label` role as `event [guard] / action` (omit sections you don't need).
- Self-loops curve above the state.
- Orient along the dominant flow direction (left→right or top→down); rearrange before crossing transitions.
- Coral on the state the reader should notice — typically the error state, or "happy completion".

## Anti-patterns
- More transitions than states × 2 → likely two state machines.
- "From any state" transitions drawn from every state — use a single annotation (`* → Error on timeout`) instead.
- Unlabeled transitions (the whole point is *what triggers this*).

## Examples
- `assets/example-state.html` — minimal light
- `assets/example-state-dark.html` — minimal dark
- `assets/example-state-full.html` — full editorial
