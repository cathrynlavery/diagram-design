# ADR 0004 — SKILL.md byte cap and the trigger-rich description

**Status:** accepted (v2.3, cap raised after review)

## Context

`SKILL.md` loads into an agent's context on every skill invocation, so it must stay lean; a byte cap keeps growth honest. But v2.3 initially set the cap at 35,000 bytes and slimmed the frontmatter `description` to fit — deleting all 27 type names. The description is the only text an agent sees *before* deciding to load the skill: removing "flowchart", "Gantt", "org chart" from it removes the lexical hooks that make "make me a flowchart" invoke the skill at all.

## Decision

Two rules, in priority order:

1. The frontmatter `description` must name every visual type in the selection table (enforced by `scripts/verify-docs-sync.py`) plus the import formats and major feature vocabulary. Routing surface is never traded for body prose.
2. `MAX_SKILL_BYTES` is 40,000 (enforced by `scripts/verify-semantic-motion.py`). When the file approaches the cap, cut body prose or move detail into `references/` — never the description.

## Consequences

- Adding a visual type requires touching the description; CI fails otherwise, by design.
- `.gitattributes` pins SKILL.md to LF in the repository and in every checkout, and the cap counts LF-normalized bytes, so a checkout with `core.autocrlf=true` measures the committed size ([#246](https://github.com/cathrynlavery/diagram-design/issues/246)). Normalization never loosens the cap: 40,001 LF bytes still fail, and the gate fails if the pin is removed.

## Amendments

**2026-09-27: SKILL.md is a router; detail loads from two routed references.** SKILL.md loads on every invocation, and at 39,530 bytes it had 470 bytes of headroom. It is now 28,869 bytes. The frontmatter `description` is unchanged, the §0 to §12 numbering is unchanged, and SKILL.md keeps what every run needs: the setup gate, the §3 routing tables, the anti-patterns, the semantic roles and focal rule, the six connector rules as one line each with their numbers, the universal complexity limits and split rule, the §9 gate, §11, and a one-line-per-point accessible-SVG contract. Everything else moved, verbatim or to an equivalent that already existed:

- `references/primitives-core.md` (new): background and dotted variant, arrow markers and the arrow table, the full text of the six connector rules, the node box, arrow label and legend markup, and the long form of the accessible-SVG contract.
- `references/layout-budget.md` (new): the 4px grid table, every per-type complexity budget row, page layout, and the summary card pattern.
- `references/style-guide.md` (existing): it already held the node type to treatment table, the typography table, and the Google Fonts `<link>` that SKILL.md repeated, so SKILL.md now links those sections instead of copying them.

The checks follow the content. `verify-docs-sync.py` runs the grid rule against `layout-budget.md` and the type-ramp font-size rule against SKILL.md, `primitives-core.md`, and `layout-budget.md`. Font-link parity no longer requires a copy in SKILL.md, and now also checks any css2 copy found in SKILL.md or any reference. A new split-routing check fails when a thinned SKILL.md section (§5, §6, §7, §8, §12) drops the exact link to any block it moved out. The 40,000-byte cap and rule 1 are unchanged.

A new type's budget row goes in `layout-budget.md`. ADR 0007 kept the rows in SKILL.md because several older type references state no limits of their own; that reason still holds, which is why the rows moved together into one table rather than into the type references.
