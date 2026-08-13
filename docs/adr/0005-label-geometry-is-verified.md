# ADR 0005 — Label placement is verified geometrically, not by review

**Status:** accepted (v2.3)

## Context

SKILL.md §6 rule 2 keeps an arrow label 6–10px clear of its own connector, and rule 5 keeps
connectors from passing behind non-endpoint boxes. Neither rule constrains a label against a
*node*. Because §5 fixes the paint order as background → zones → arrows → labels → nodes, a
label mask that lands partly inside a node is covered by the node fill: the text renders as a
fragment sitting on the node border.

Nine shipped examples across two types (architecture, swimlane) had shipped this way. Every
existing gate passed on all of them — `lint-skin.py` checks colors, fonts, and the accessible
SVG contract; `self_check.py` checks DOM structure and the motion contract; neither reads
coordinates. The defect is only visible when the file is rendered, so it survived review in
three variants at a time.

## Decision

1. Label placement gets an explicit rule (SKILL.md §6 rule 6) rather than being left to the
   author's eye.
2. The rule is enforced by `scripts/verify-geometry.py`, which parses `<rect>` coordinates and
   reports a mask that overlaps a node **declared later in the document**. Document order is
   the criterion, not overlap alone: a mask over an earlier-painted zone container stays on
   top and is legal, and a mask fully inside a node is a badge chip.
3. The checker carries adversarial tests (`scripts/test-verify-geometry.py`) covering both
   polarities — a clipped mask must be reported, and the legal cases must not be.

## Consequences

- Geometric contracts in this repo are expressed as checkers with fixtures, in line with how
  the import extractors are verified. A rule that only lives in prose is a rule that ships
  broken examples.
- The heuristics are shape-based (node ≥ 60×40, mask 20–120 × 8–14) and match the shipped
  templates. A future type with markedly different proportions may need the thresholds
  revisited — widen them in the checker, and add the case to the adversarial tests.
- The checker does not evaluate the 6–10px connector gap from rule 2, which needs stroke
  geometry rather than rectangles. That rule remains a checklist item.
