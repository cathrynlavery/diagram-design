# ADR 0018: Steps is an ordered-stage rail grammar

**Status:** Proposed  
**Date:** 2026-10-18

## Context

Diagram Design can show dated milestones, branching logic, cross-functional handoffs, and rich actor/payload processes. It does not have a compact grammar for the familiar “three to seven steps” explainer: numbered stages on one rail, each with an optional icon, a short title, and a brief explanation.

Forcing that content into Timeline invents elapsed-time semantics. Process and Swimlane add actors and handoffs the source does not claim. Flowchart adds connectors and branch affordances where left-to-right order is sufficient.

## Decision

Add **Steps** as visual type #49.

Its load-bearing primitive is one contiguous equal-width rail with numbered icon medallions. Equal spacing encodes order only. Exactly one stage is focal; all others stay neutral. The grammar allows 3–7 stages, no branches, no actor lanes, and no time scale.

The shipping set includes `references/type-steps.md`, three static example variants, the gallery and README entries, a complexity-budget row, a canonical screenshot, and the standard accessibility, skin, render, geometry, and documentation gates.

## Consequences

- “How it works,” methods, onboarding paths, and short playbooks no longer need to masquerade as timelines or processes.
- Rainbow infographic styling is explicitly rejected; sequence comes from position and numbering, with accent reserved for one focal stage.
- Requests involving dates, branching, responsibility, or payload handoffs continue to route to Timeline, Flowchart, Swimlane, or Process.
