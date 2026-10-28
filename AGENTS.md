# Notes for coding agents

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing anything. It has the gate suite and the rules for each kind of change. This file covers the parts of adding a diagram that agents keep missing.

## Adding a diagram type or variant

Follow "Adding a new diagram type" in CONTRIBUTING.md. The suite fails until these are done:

- **Gallery.** Register every example in `skills/diagram-design/assets/index.html`. A new type gets the next number. Any other example of an existing type is a lettered variant: it goes directly after its parent with `data-parent-type` and a lettered eyebrow (`28c`). GitHub Pages publishes `skills/diagram-design/assets/` when the PR merges, so the live gallery needs no separate step.
- **Type count (new type).** Raise `VISUAL_TYPE_COUNT` in `scripts/verify-docs-sync.py` and `scripts/verify-semantic-motion.py`, and the hardcoded count in `scripts/verify-screenshot-freshness.py` and `scripts/render-canonical-screenshots.py`. Then fix every count the suite reports: the README, SKILL.md, CONTRIBUTING, `onboarding.md` and `semantic-patterns.md`, plus a new amendment in ADR 0002.
- **Plugin manifests.** Keep `description` and `keywords` identical across `.claude-plugin`, `.codex-plugin`, `.factory-plugin` and `.qoder-plugin`. A type whose selection-table name differs from the word used in the descriptions needs a `DESCRIPTION_ALIASES` entry in `verify-docs-sync.py`. Leave `version` alone; main bumps it after merge (ADR 0009).

Nothing checks these, so do them in the same PR:

- **README thumbnail (new type).** Run `scripts/render-canonical-screenshots.py`, add the cell with its full-size PNG link to the grid under "What it makes", then run `scripts/build-readme-thumbs.py`; it only builds thumbnails for PNGs the README already links. Update "01 to N" in the gallery sentence below the grid.
- **README named variants.** Line, Scatter and Treemap have named variants (slopegraph, bubble, marimekko and others). A new one goes in the "Several types have named variants" line.
- **README file tree (new type).** Add the new `type-*.md` to the tree under "Architecture", sorted by type name.
- **Layout budget (new type).** Add the type's row to the complexity budget table in `skills/diagram-design/references/layout-budget.md`.

Run every command in `gates.local_commands` of `.maintainer-policy.json` before you push.

## After a new type merges

The type count also appears in three places outside this repo: the GitHub About description, Cathryn's profile README (`cathrynlavery/cathrynlavery`) and diagramdesign.dev. No check covers them. If you are working for the maintainer, tell her the new count so she can update all three.
