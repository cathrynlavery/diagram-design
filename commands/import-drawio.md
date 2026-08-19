---
description: Redraw a draw.io file as an editorial diagram at a chosen format, size, and detail level
argument-hint: <drawio-file> [--format=html|svg|png|html+png] [--size=<preset>] [--detail=faithful|balanced|simplified] [--audience=engineer|mixed|executive] [--type=<diagram-type>] [--page=N|NAME|all] [--variant=light|dark|full] [--output=<path>]
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
---

Redraw the draw.io file at `$1` as a diagram in this skill's design system, following [`skills/diagram-design/references/import-drawio.md`](../skills/diagram-design/references/import-drawio.md) and [`skills/diagram-design/references/output-spec.md`](../skills/diagram-design/references/output-spec.md). Treat those references as the source of truth — don't reimplement the logic here.

Full argument string: `$ARGUMENTS`

Accepts `.drawio`, `.drawio.xml`, `.xml`, `.drawio.png`, and `.drawio.svg`.

## Defaults

- `--format=html` — a self-contained HTML file next to the source.
- `--size=doc-inline` — `viewBox 0 0 960 600`.
- `--detail=balanced` · `--audience=mixed`.
- `--variant=light` — the minimal light template.
- A single-page file selects its only page; a multi-page file lists pages and asks which to use.
- Type is chosen from the extracted structure; `--type` forces one of the visual types in
  [`SKILL.md` §3](../skills/diagram-design/SKILL.md).

## Flags

- `--format` — `html` (default), `svg`, `png`, or `html+png`. Non-HTML formats are produced from the HTML via `references/export.md`, never hand-authored.
- `--size` — any preset in `output-spec.md` §2: `doc-inline`, `doc-wide`, `slide-16x9`, `slide-4x3`, `social-og`, `social-square`, `print-a4-landscape`, `print-letter-landscape`, `fit`.
- `--detail` — `faithful` (≤24 nodes, zoned), `balanced` (≤12), `simplified` (≤7).
- `--audience` — `engineer`, `mixed`, `executive`. Governs wording, not element count.
- `--type` — force a diagram type instead of inferring it.
- `--page` — page index, page name, or `all` (one file per page).
- `--variant` — `light`, `dark`, or `full` editorial template.
- `--output` — output base path; the extension is appended per format.

## Required behaviour

1. **No file provided** → ask which `.drawio` file. Don't guess.
2. **Always locate the installed skill and run `<skill-dir>/scripts/drawio_extract.py` first.** Never assume the skill is under the current working directory, and never read a `.drawio` file directly — most are compressed, and the raw XML is noise.
3. **Extractor exits non-zero** → report its message verbatim and stop.
4. **Digest shows 0 nodes** → the source is image-only or encrypted. Say so; ask for the original file. Don't invent content.
5. **Multi-page file with no `--page`** → list the pages with their node/edge counts and ask which one.
6. **Requested detail level is impossible at the requested size** (e.g. `faithful` on a 40-node source at `slide-16x9`) → say so before drawing and propose overview + per-zone detail.
7. **`--detail=faithful` above 9 nodes** → zone the layout; above 24 nodes, split into overview + detail files.
8. **Never carry over source coordinates, colors, or fonts.** The output is a redraw in the project's `style-guide.md` skin.
9. Run the SKILL.md §9 taste gate and the `output-spec.md` §6 checklist before writing.

After writing the files, report the paths, sizes, the four dials used, and the fidelity ledger (what was merged, collapsed, or dropped).
