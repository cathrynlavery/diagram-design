# ADR 0002 — Semantic patterns never expand the visual-type taxonomy

**Status:** accepted (v2.3)

## Context

Auditing behavior-rich figures (queues, policy traces, trust boundaries) showed the skill could arrange boxes but not model system behavior. The obvious fix — new diagram types — would balloon the taxonomy, dilute the selection guide, and force every new behavior into a new layout grammar.

## Decision

Behavior is a separate axis. The seven semantic patterns in `references/semantic-patterns.md` each route to the **nearest existing visual type** for layout; a pattern owns semantic primitives and a tighter budget, never a second layout grammar. The visual-type count only moves when a genuinely new *layout* grammar appears (it did in v2.5 — see [ADR 0007](0007-new-layout-grammars.md), 27 → 37).

## Consequences

- The type count is a stable, verifiable claim (`verify-semantic-motion.py` and `verify-docs-sync.py` both count it).
- A new behavior costs one pattern section plus a routing-table row — not a new type reference, template set, and example triple.
- If a pattern ever needs a layout no existing type provides, that is the signal to add a type, with the full §10 shipping set.
