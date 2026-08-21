# Pre-Output Checklist (Taste Gate)

Run this once, after the diagram is drawn and before it is written out. Section numbers below refer to `SKILL.md`.

## Type fit

- [ ] If behavior matters, did I choose one semantic pattern before the visual type and load [`semantic-patterns.md`](semantic-patterns.md)?
- [ ] Right visual type for the layout? (§3 visual-type guide)
- [ ] Stated type, pattern, size preset, and planned cuts before drawing — confirmed, or assumptions noted? (§3)
- [ ] Would a table / paragraph do the same job? (If yes — don't draw.)
- [ ] Loaded the matching type reference linked in the visual-type guide?
- [ ] If this is an import — format, size, detail level, and audience set? `viewBox` and type ramp match the size preset? (§11, [output-spec.md §6](output-spec.md))
- [ ] If this is an import — fidelity ledger ready to report? (§11)

## Remove test

- [ ] Can I remove any node? (Would a reader still understand?)
- [ ] Can I merge any two nodes? (Do they always travel together?)
- [ ] Can I remove any arrow? (Is the relationship obvious from layout?)
- [ ] Can I remove any label? (Does color or shape already signal it?)

## Signal

- [ ] Coral used on ≤2 elements? If more, which actually deserve focal status?
- [ ] Legend covers every type used — and nothing extra?
- [ ] Within the type's complexity budget (§7)?

## Technical

- [ ] Diagram `<svg>` has `role="img"` and `aria-labelledby` resolving to its `<title>` and `<desc>`?
- [ ] `<title>` is the first child of `<svg>` (before `<defs>`) and both `<title>` and `<desc>` are filled in?
- [ ] `<title>` / `<desc>` IDs are prefixed for this diagram and variant — never bare `title` / `desc`?
- [ ] Arrows drawn before boxes?
- [ ] **Every connector between off-axis nodes uses a rounded right-angle elbow (`r=8`)? No diagonal `<line>` slants?**
- [ ] **Every arrow label has a visible 6–10px gap above its connector? (Mask rect not touching the stroke.)**
- [ ] **No two connectors overlap, share a stroke path, or run on top of each other? Crossings use the bridge/hop primitive?**
- [ ] **When several connectors enter or exit the same edge of a box, each has its own attach point (≥12px apart)? No connector hides another?**
- [ ] **No connector passes behind a non-endpoint box, except the unavoidable-intervening-box case (§6 rule 5) — and in that case, the stroke is dashed and the label sits at the visible end?**
- [ ] **No label mask overlaps a node drawn after it? (Node fill would clip the text — §6 rule 6. From a repository checkout, run `python3 <repo-root>/scripts/verify-geometry.py <file>`.)**
- [ ] Every arrow label has an opaque `fill="#f5f5f5"` rect behind it?
- [ ] Legend is a horizontal bottom strip, not floating?
- [ ] No vertical `writing-mode` text?
- [ ] `viewBox` expanded for the legend strip (~60px)?
- [ ] Every font size, coord, width, height, gap divisible by 4?
- [ ] From the installed skill directory, did `python3 scripts/self_check.py <file>` pass? (Accessible-SVG contract, single-file safety, motion basics; ships with the skill.)
- [ ] If animated, does the complete static/no-JS frame work, does reduced motion hide/disable playback, and is the controller copied verbatim from `assets/template-motion.html`? From a repository checkout, also run `python3 <repo-root>/scripts/verify-motion.py path/to/generated.html` plus the skin linter; from an installed skill, manually check print and static-query states on top of the self-check.

## Typography

- [ ] Brand match uses exact public families/weights, verified via `getComputedStyle`; fallbacks disclosed?
- [ ] Human-readable names in Geist sans, not Geist Mono?
- [ ] Technical sublabels (ports, commands, URLs) in Geist Mono?
- [ ] Page title in Instrument Serif?
- [ ] Annotation callouts (if any) in *italic* Instrument Serif? (see [primitive-annotation.md](primitive-annotation.md))
- [ ] No JetBrains Mono anywhere?
