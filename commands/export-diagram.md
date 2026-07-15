---
description: Export a diagram-design HTML file to .svg and .png next to the source
argument-hint: <html-file> [--svg-only|--png-only] [--scale=N] [--output=<path>]
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
---

Export the diagram HTML at `$1` to `.svg` and/or `.png`, following the procedure documented in [`skills/diagram-design/references/export.md`](../skills/diagram-design/references/export.md). Treat that reference as the source of truth — don't reimplement the logic here.

Full argument string: `$ARGUMENTS`

## Defaults

- Produce **both** `.svg` and `.png` next to the source (e.g. `diagram.html` → `diagram.svg` + `diagram.png`).
- PNG renders at `device_scale_factor=2`.

## Flags

- `--svg-only` — emit only the SVG. Skip Playwright entirely.
- `--png-only` — emit only the PNG.
- `--scale=1` / `--scale=2` / `--scale=3` — override the PNG device scale factor. Default `2`.
- `--output=<path>` — override the output base path; the format extension is appended. Applies to both formats when both are produced.

## Required behaviour

1. **No source path provided** → ask the user which `.html` file to export. Don't guess.
2. **Source is `assets/index.html`** (the gallery, multiple SVGs in one file) → refuse and ask which specific diagram file. Per the reference's edge-case section.
3. **Source has no `<svg>` block** → refuse and tell the user; don't write anything.
4. **PNG requested but Playwright not installed** → surface the install instruction from the reference verbatim and stop. Do **not** auto-install.
5. **PNG requested with `--scale` outside {1,2,3}** → reject; valid values are 1, 2, 3.

After producing the outputs, report the file paths and sizes back to the user.
