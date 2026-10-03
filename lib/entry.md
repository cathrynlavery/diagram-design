# Diagram Design — DeepSeek Harness entry

This is a router, not the specification. The full `SKILL.md` in this skill's base
directory is about 29 KB, so it is not inlined here — inlining it would spend
roughly 7,400 tokens on every load for a document that mostly points at the
reference files below. Read the parts you need with the `read` tool before
drawing anything.

## Read first

1. `SKILL.md` section 0 — the first-time style-guide gate. Skipping it ships
   default-skinned diagrams into a branded project.
2. `SKILL.md` section 3 — the selection tables: semantic pattern first, then the
   visual type. Reuse the nearest existing type rather than inventing one.
3. `SKILL.md` section 9 — the pre-output checklist. It is the taste gate.

## Read by need

| The request | Read |
|---|---|
| A specific diagram type | `references/type-flowchart.md`, or the sibling `references/type-*.md` for the type asked for |
| Colors, type ramp, fonts | `references/style-guide.md` |
| Node boxes, arrow markers, connector rules | `references/primitives-core.md` |
| Grid, per-type complexity budgets, page layout | `references/layout-budget.md` |
| Behavior patterns independent of layout | `references/semantic-patterns.md` |
| Optional motion and its accessibility contract | `references/animation.md` |
| Importing draw.io | `references/import-drawio.md`, then run `scripts/drawio_extract.py` |
| Importing Mermaid | `references/import-mermaid.md`, then run `scripts/mermaid_extract.py` |
| Importing Excalidraw | `references/import-excalidraw.md`, then run `scripts/excalidraw_extract.py` |
| Export to SVG or PNG | `references/export.md`, then run `scripts/export_svg.py` |
| Saving or loading a client profile | `references/profiles.md` |
| First run in a project | `references/onboarding.md` |
| Checking the environment | `references/doctor.md` |

## Output

One self-contained HTML file with inline SVG. `assets/` holds a worked light,
dark and full example of every diagram type; use them as the reference for how
finished output should look.

## Prerequisites

`python3` must be on `PATH` — the import and export helpers are Python scripts.
Run `scripts/self_check.py` against a finished file before handing it over.