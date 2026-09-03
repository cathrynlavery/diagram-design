# ADR 0002 — Semantic patterns never expand the visual-type taxonomy

**Status:** accepted (v2.3; amended v2.6)

## Context

Auditing behavior-rich figures (queues, policy traces, trust boundaries) showed the skill could arrange boxes but not model system behavior. The obvious fix — new diagram types — would balloon the taxonomy, dilute the selection guide, and force every new behavior into a new layout grammar.

## Decision

Behavior is a separate axis. The semantic patterns in `references/semantic-patterns.md` (eight as of this writing; see Amendments) each route to the **nearest existing visual type** for layout; a pattern owns semantic primitives and a tighter budget, never a second layout grammar. The visual-type count only moves when a genuinely new *layout* grammar appears (it did in v2.5.10 — see [ADR 0007](0007-new-layout-grammars.md), 28 → 38 — and again for Polar, 38 → 39).

## Consequences

- The visual-type count is a stable, verifiable claim (`verify-semantic-motion.py` and `verify-docs-sync.py` both count it) — 27 when this record was accepted; see Amendments for the current figure.
- A new behavior costs one pattern section plus a routing-table row — not a new type reference, template set, and example triple.
- If a pattern ever needs a layout no existing type provides, that is the signal to add a type, with the full §10 shipping set.

## Amendments

**2026-08-18 — the count is 28.** Treemap was admitted under the escape clause above: recursive area subdivision is a layout grammar no existing type provides (bar encodes with length, nested with containment and no quantity, pyramid with rank). It shipped the full §10 set, and the counters named above moved 27 → 28 together with the prose.

**2026-08-19 — the count is 38.** Ten additional visual grammars were admitted under the same escape clause: Sankey, fishbone, Wardley map, kanban, user journey, deployment, dependency graph, UML class, story map, and database schema. The per-type argument is in [ADR 0007](0007-new-layout-grammars.md); each ships the full §10 set, and the two counters move 28 → 38 together with the prose.

**2026-08-20 — the count is 39.** Polar was admitted under the same escape clause: angle encodes ordered cyclic categories and linear radius encodes one quantitative series, a layout grammar no existing type provides. It shipped the full §10 set, and the counters named above moved 38 → 39 together with the prose.

**2026-08-31 — the pattern count is eight.** Traceable block decomposition was added: hierarchical, ID-addressable block decomposition with per-block I/O, constraints, and an implementation-code link, for compliance, audit, or IP-style documentation. It routes to the existing Tree type — SysML-informed vocabulary (block, noun-phrase naming, flow port) applied to Tree's existing layout grammar, not a new grammar and not a claim of SysML or IDEF0 conformance. This is the first amendment to the *pattern* count specifically (every prior amendment above moved the *type* count); the mechanism is the same one-line-plus-routing-row cost this ADR's Decision describes, and `verify-semantic-motion.py`'s `PATTERN_NAMES` list is its enforcement, the same way the type counters enforce the type count. See [ADR 0009](0009-block-registry-metadata-contract.md).

The decision itself is unchanged — semantic patterns still never add a type, and the count still moves only for a new *layout* grammar. What this amendment records is the procedure: the two counters are this ADR's enforcement, so a PR that edits them without amending this file has quietly made itself the authority. Amend here in the same PR, or the number in the test is just whatever the last contributor typed.
