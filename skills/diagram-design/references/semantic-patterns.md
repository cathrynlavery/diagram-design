# Semantic patterns

Semantic patterns describe **what a system does**; the 39 visual types describe **how information is arranged**. Choose a pattern first when behavior, state, enforcement, or risk is load-bearing, then use its nearest visual type as the layout grammar. If no pattern matches, choose a visual type directly.

Use one primary pattern per figure. A second pattern may supply at most one supporting primitive; if both need full treatment, split overview and detail. Labels and outcomes must remain complete in a static frame.

## Routing table

| The reader must understand… | Semantic pattern | Nearest visual type |
|---|---|---|
| Many arrivals competing for finite service capacity | **Fan-in queue / bottleneck** | Data flow |
| Repeated questions, inputs, controls, and outputs across stages | **Stage framework with semantic slots** | Process |
| A loose conversation becoming a durable structured record | **Unstructured input → structured artifact** | Data flow |
| Why two policy decisions differ and where they first diverge | **Paired policy-evaluation traces** | Flowchart |
| Which routes cross a trust boundary and which routes are blocked | **Secure paved road** | Architecture |
| Which controls apply at each enforcement surface | **Governance / control catalog** | Layer stack |
| How defenses reduce risk and what risk remains | **Compensating security layers** | Layer stack |

## 1. Fan-in queue / bottleneck

**Selection triggers:** Several producers converge on one reviewer, service, gate, or constrained resource; the story depends on arrival rate, queue depth, wait, capacity, or backpressure.

**Required primitives:** Distinct sources; fanned ingress; an ordered queue with visible slots and count; a capacity/service-rate label; one constrained service point; admitted and deferred/rejected outcomes. Label units (`8/hour`, `3 slots`), not just “high.”

**Complexity budget:** ≤5 sources, ≤5 queue slots, one bottleneck, two outcomes, and ≤9 primary nodes. Aggregate excess sources as a named cohort.

**Anti-patterns:** Equal-width pipeline that hides contention; arrows merged before they can be traced; capacity implied only by box size; decorative pile-up; animation that changes item order; red alone meaning overloaded.

**Static fallback:** Show the representative final queue, numeric count/capacity, bottleneck label, and both outcome paths. A still must reveal why work waits.

**Nearest visual type:** **Data flow** by default; use **Process** when service stages, rather than sources, dominate.

## 2. Stage framework with semantic slots

**Selection triggers:** A lifecycle or operating model repeats the same semantic questions across stages, commonly Question, Input, Governance, and Output. Cross-stage comparability matters more than message timing.

**Required primitives:** Ordered stage headers; a consistent slot grid; explicit empty/not-applicable slots; stage-to-stage handoff; stable slot labels; one primary output per stage. Preserve slot order in every stage.

**Complexity budget:** 3–6 stages, 3–4 slot kinds, ≤20 populated cells, ≤2 lines per cell. Split detail when a cell needs prose.

**Anti-patterns:** Each stage invents a different internal layout; slot meaning encoded by position with no labels; fake precision from dozens of cells; confusing stage order with ownership lanes; shrinking text to keep one canvas.

**Static fallback:** Render the full stage × slot matrix with handoffs and explicit `—` or `Not applicable` entries. Do not depend on staged reveal to teach the schema.

**Nearest visual type:** **Process**; use **Swimlane** only when the repeated rows represent owners rather than semantic slots.

## 3. Unstructured input → structured artifact

**Selection triggers:** Dialogue, notes, prompts, or a rambling request are elicited, normalized, and written into a durable brief, ticket, record, schema, or other structured artifact.

**Required primitives:** Source utterance(s); clarifying questions; extracted field/value pairs; a named transformation; the durable artifact boundary; provenance links from representative statements to fields; missing/unknown state.

**Complexity budget:** ≤4 exchanges, ≤6 artifact fields, one transformation, and ≤3 provenance links. Show representative content, not a transcript.

**Anti-patterns:** “AI magic” sparkle between two boxes; artifact shown as another chat bubble; fields appearing without sources; inventing certainty for missing facts; typing animation as the only readable copy.

**Static fallback:** Show a short source excerpt beside the completed labeled artifact, with at least one provenance mapping and any unknown fields visible.

**Nearest visual type:** **Data flow**; use **Process** when elicitation has several ordered gates.

## 4. Paired policy-evaluation traces

**Selection triggers:** Two otherwise similar requests reach different outcomes; the reader needs rule-by-rule `PASS`, `FAIL`, `SKIPPED`, or `NOT REACHED` state and the first divergence.

**Required primitives:** The same ordered rules on both traces; explicit status text plus symbol/shape; inputs that differ; final outcomes; a labeled first-divergence marker; a distinction between `SKIPPED` (applicable flow intentionally bypassed) and `NOT REACHED` (evaluation stopped earlier).

**Complexity budget:** Exactly 2 traces, 3–6 rules, one first divergence, ≤12 status cells, and one outcome per trace. Move rule prose to notes if labels exceed one line.

**Anti-patterns:** Comparing two independently ordered flows; green/red dots without words; treating skipped and not-reached as synonyms; highlighting every difference; continuing a denied trace as if downstream rules ran.

**Static fallback:** Show all rule states and both outcomes at once; use a persistent bracket/line and label for the first divergence.

**Nearest visual type:** **Flowchart** for ordered decision logic; use **Sequence** only when messages between actors and time are also load-bearing.

## 5. Secure paved road

**Selection triggers:** A supported architecture creates a bounded route from intake/build to deployment; trust boundaries, privileged moments, permitted ingress, forbidden ingress, and approved versus blocked deploy paths are the point.

**Required primitives:** Labeled trust boundaries; actors and identities; permitted ingress with a positive text label; forbidden ingress terminating at the boundary; approved deployment path; blocked bypass path; privileged gate; isolated runtime; audit destination. Use different line styles and stop symbols in addition to color.

**Complexity budget:** ≤3 trust zones, ≤8 components, ≤10 paths, ≤2 forbidden paths, and one privileged gate. Split control detail into a catalog figure.

**Anti-patterns:** Dashed box called “security” with no route semantics; forbidden arrow crossing into the protected zone; secrets or identity implied but unlabeled; every component styled as trusted; a bypass path that visually rejoins the approved route.

**Static fallback:** Render every boundary and both permitted/forbidden routes. Blocked paths must visibly stop before entry or deployment.

**Nearest visual type:** **Architecture**.

## 6. Governance / control catalog

**Selection triggers:** A control inventory must be understood by where it is enforced: authoring, workspace, merge/CI, deploy/runtime, or another named surface. A single checklist would hide those enforcement points.

**Required primitives:** Enforcement-surface groups; named controls; enforcement actor (`code`, `platform`, `human`); timing (`write`, `merge`, `deploy`, `run`); bypassability or exception route; coverage/gap notation.

**Complexity budget:** 3–5 surfaces, 3–7 controls per surface, ≤24 controls total, and ≤3 attributes per control. Summarize counts only when the item list exists elsewhere.

**Anti-patterns:** 35 tiny pills; grouping by vague themes instead of enforcement point; mixing aspirations with enforced controls; icons without control names; claiming defense-in-depth without showing surface coverage.

**Static fallback:** Show the complete grouped catalog with surface headers and text labels for actor and enforcement timing; preserve gaps and exceptions.

**Nearest visual type:** **Layer stack**; use **DP security matrix** when role permissions, not enforcement surfaces, are the dominant comparison.

## 7. Compensating security layers

**Selection triggers:** No layer is perfect; each defense covers a failure left by the previous layer, and residual risk must visibly narrow, transfer, or remain through the stack.

**Required primitives:** Ordered threat/risk input; named defensive layers; each layer's mitigation; explicit limitation or escape; residual-risk carrier between layers; final residual risk and consequence/response. Use labels or decreasing measures, never area alone.

**Complexity budget:** 3–5 layers, one primary risk thread, ≤2 mitigations per layer, and one final residual-risk statement. Split multiple unrelated threats into separate figures.

**Anti-patterns:** Implying the final layer makes risk zero; equal opaque slabs with no propagation; treating audit as prevention; shrinking shapes without numeric or verbal meaning; reversing prevention/detection/recovery order without explanation.

**Static fallback:** Show the complete propagation chain: initial risk → mitigation → escaped risk at every layer → final residual risk and response.

**Nearest visual type:** **Layer stack**; use **Nested** when containment boundaries, rather than ordered compensation, carry the meaning.

## Composition rules

- The semantic pattern may specialize status, boundary, queue, or propagation primitives; the selected type still owns page axis, connector grammar, spacing, and type-specific limits.
- Apply the stricter of the pattern budget and visual-type budget. Semantic cells/statuses are not permission to exceed the nine-node overview target.
- Use stable text for states and outcomes. Color, motion, and position reinforce meaning but never carry it alone.
- Optional animation is a presentation layer, not another pattern. Load [`animation.md`](animation.md) only when motion is requested or materially clarifies ordered change.
