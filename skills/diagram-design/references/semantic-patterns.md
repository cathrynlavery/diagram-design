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
| Which sub-elements a system decomposes into, each independently citable and traced to its implementation | **Traceable block decomposition** | Tree |

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

## 8. Traceable block decomposition

**Selection triggers:** A system or product must decompose into addressable, individually citable sub-elements — each with a stable identifier a reader (or a future filing) can point at directly, not a name alone. The reader needs to trace a specific block to its parent, to what it consumes and produces, and to the code that implements it. This describes *structure* (what the system is made of), not a process — for a sequence of actions, choose a pattern that routes to Flowchart or Swimlane instead.

**Required primitives:** A stable dotted ID per block (e.g. `FC3-001-02`), shown as a compact badge using the existing node-box type-tag chip (SKILL.md §6 "Node box — full pattern") — never as a separate connector-adjacent label. A noun-phrase block name — the structural element itself ("Timeline Engine"), not an action performed on it — in the node's existing name slot. Parent-child structure is Tree's own elbow connector; this pattern adds no new connector semantics or connector labels. At most one short inbound and one short outbound flow-port label per block, in the existing Geist Mono sublabel slot, shown only when both fit without crowding the name — omit by default. Every block's full record — inputs, outputs, constraints, assumptions, and an implementation path — lives in `data-block-*` attributes on the node (`data-block-id`, `data-block-parent`, `data-block-name`, and terse `data-block-input` / `-output` / `-constraint` / `-assumption` / `-impl` values) and, for anything longer than a short phrase, in the sidecar registry (see `export-registry.md`) — never as additional visible diagram text.

**Complexity budget:** Tree's own root+3-tier / 5-per-level caps and the global 9-node ceiling apply as-is — this pattern does not raise them. A hierarchy that needs more splits into a linked set of diagrams, one per subsystem, each independently traceable; the sidecar registry is the layer that reassembles the full graph across files. At most one in/out port-label pair per block when shown at all; constraints and assumptions are never rendered as visible text, only carried in metadata.

**Anti-patterns:** Four-sided ICOM boxes with Input/Control/Output/Mechanism arrows on every side — that is IDEF0's grammar, not this pattern's, and it does not fit Tree's connector rules. Drawing input/output arrows between siblings or cousins — that is a dependency graph's job; route to that type instead if cross-block flow must be drawn. Verb-phrase block names — name the structural element, not an action; if a block is genuinely an activity, it likely belongs in a companion Flowchart or Swimlane diagram, not this tree. An ID badge with no matching `data-block-id`, or a rename not mirrored in the registry. Treating the visible diagram as the complete record — it is a bounded view; the registry is the source of truth for anything not drawn. Labeling the tree connector itself with an ID or name — Tree has no connector-label convention today and this pattern must not invent one.

**Static fallback:** This pattern has no animated form — it is always static; bespoke interaction (click-to-expand, filter-by-ID) is out of this skill's scope entirely (see ADR 0001). Every ID badge, block name, and any shown port label must be legible in the single rendered frame.

**Nearest visual type:** **Tree** — Nested's single-chain containment cannot show two children of one parent; Dependency graph permits multi-parent nodes and cycles this pattern must forbid; Architecture's zones are flat, capped at 3, and explicitly route overflow to Swimlane, not to nested grouping.

**A note on provenance, not a claim of compliance:** "block," noun-phrase naming, and "flow port" are SysML Block Definition Diagram vocabulary, used because this pattern documents structure, the thing SysML's naming convention is for (IDEF0's verb-phrase convention documents *functions* instead — the wrong fit here). This is SysML-*informed* vocabulary applied to Tree's existing layout grammar, not a claim of SysML compliance: no OCL constraints, no XMI interchange, no tool-certified conformance, and no IDEF0 compliance either.

## Composition rules

- The semantic pattern may specialize status, boundary, queue, or propagation primitives; the selected type still owns page axis, connector grammar, spacing, and type-specific limits.
- Apply the stricter of the pattern budget and visual-type budget. Semantic cells/statuses are not permission to exceed the nine-node overview target.
- Use stable text for states and outcomes. Color, motion, and position reinforce meaning but never carry it alone.
- Optional animation is a presentation layer, not another pattern. Load [`animation.md`](animation.md) only when motion is requested or materially clarifies ordered change.
