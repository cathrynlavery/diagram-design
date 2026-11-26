# ADR 0019: Hidden-by-default disclosure is out of scope

**Status:** Accepted  
**Date:** 2026-11-24

## Context

Issue #162 showed that CSS-only disclosure techniques (`:target` panels and scoped `:hover` overlays) pass `self_check.py`'s no-JavaScript check, while `SKILL.md` and `references/animation.md` neither permitted nor forbade them. Leaving the behavior undocumented produces inconsistent diagrams.

## Decision

Hidden-by-default disclosure (`:hover` or `:target` panels that conceal diagram content until interaction) is out of scope and documented as an anti-pattern in `SKILL.md` §4 and `references/animation.md`.

The deciding principle is static-frame completeness (ADR 0003): the default, no-interaction frame must carry every fact, because PNG export, print, and embeds capture only that frame. Allowing "strictly redundant" hidden panels is rejected because diagram rules in this repository are machine-verified rather than reviewer-checked (ADR 0005), and no verifier can check semantic redundancy. When a diagram exceeds the §7 complexity budget, split it into overview and detail diagrams (`SKILL.md` §7).

One carve-out: a nested `<title>` inside a node group (the native tooltip) may carry a short elaboration of something the diagram already labels, because it degrades to nothing rather than to missing meaning.

## Consequences

- `SKILL.md` §4 and `references/animation.md` reject `:hover` and `:target` disclosure panels while preserving the nested `<title>` allowance.
- Both `self_check.py` and `verify-motion.py` only capture direct-child `<title>` and `<desc>` elements (`_svg_depth == 2`), so nested `<title>` tooltips pass without script changes.
- No `plugin.json` version changes.
