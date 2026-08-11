# Diagram Design — GitHub Copilot Instructions

This repository ships a diagram design skill for creating editorial-quality technical and product diagrams as self-contained HTML files with inline SVG.

## Skill location

The full skill lives at [`skills/diagram-design/SKILL.md`](../skills/diagram-design/SKILL.md). **Read it before generating any diagram.** It contains the philosophy, type-selection guide, design system rules, and anti-pattern checklist. Type-specific conventions live in `skills/diagram-design/references/` — load only the reference for the type you're building.

## What this skill does

27 diagram types rendered as standalone HTML with inline SVG, skinnable to any brand. Types include: architecture, flowchart, sequence, state machine, ER / data model, timeline, swimlane, quadrant, radar, loop / flywheel, nested, tree, org chart, layer stack, venn, pyramid / funnel, bar, line, Gantt, scatter, high-level, process, medallion, data flow, DP integration, DP security matrix.

## First-time setup

On first use in a project, check whether `skills/diagram-design/references/style-guide.md` has been customized (look for a non-default `accent` value — default is `#b5523a`). If not, pause and ask the user whether they want to run onboarding (pull tokens from a URL, installed skill, local folder, or paste manually) before proceeding.

## Export

To export a diagram HTML to SVG or PNG, use the `/export-diagram` prompt (`.github/prompts/export-diagram.prompt.md`) or ask in natural language. The full procedure is in [`skills/diagram-design/references/export.md`](../skills/diagram-design/references/export.md).

## Key rules

- Read `SKILL.md` before any diagram task — it has the type picker and checklist.
- Load only the relevant `references/type-*.md`, not all of them.
- Target density: 4/10. Every node earns its place.
- Accent color on 1–2 focal nodes only — never decorative.
- All coordinates, widths, and gaps must be divisible by 4.
- Run `python3 scripts/lint-skin.py <file>` before committing new example HTML.
