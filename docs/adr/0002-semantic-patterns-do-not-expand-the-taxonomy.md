# ADR 0002 — Semantic patterns never expand the 27-type taxonomy

**Status:** accepted (v2.3)

## Context

Auditing behavior-rich figures (queues, policy traces, trust boundaries) showed the skill could arrange boxes but not model system behavior. The obvious fix — new diagram types — would balloon the taxonomy, dilute the selection guide, and force every new behavior into a new layout grammar.

## Decision

Behavior is a separate axis. The seven semantic patterns in `references/semantic-patterns.md` each route to the **nearest existing visual type** for layout; a pattern owns semantic primitives and a tighter budget, never a second layout grammar. The visual-type count stays at 27 unless a genuinely new *layout* grammar appears.

## Consequences

- The visual-type count is a stable, verifiable claim (`verify-semantic-motion.py` and `verify-docs-sync.py` both count it) — 27 when this record was accepted; see Amendments for the current figure.
- A new behavior costs one pattern section plus a routing-table row — not a new type reference, template set, and example triple.
- If a pattern ever needs a layout no existing type provides, that is the signal to add a type, with the full §10 shipping set.

## Amendments

**2026-08-18 — the count is 28.** Treemap was admitted under the escape clause above: recursive area subdivision is a layout grammar no existing type provides (bar encodes with length, nested with containment and no quantity, pyramid with rank). It shipped the full §10 set, and the counters named above moved 27 → 28 together with the prose.

The decision itself is unchanged — semantic patterns still never add a type, and the count still moves only for a new *layout* grammar. What this amendment records is the procedure: the two counters are this ADR's enforcement, so a PR that edits them without amending this file has quietly made itself the authority. Amend here in the same PR, or the number in the test is just whatever the last contributor typed.

**2026-08-18 — the count is 29.** Kanban was admitted under the escape clause above; the
grammar argument is in the pull request that adds it. It ships the full §10 set — reference, three
static variants, gallery entry — and the two counters moved 28 → 29 together with the prose.

This is one of several grammars proposed together in #78 and split into one pull request each at the
maintainer's request, so each gets an independent decision. Whichever lands first takes 29; the rest
renumber against main rather than assuming an order.
