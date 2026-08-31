---
description: Export a diagram-design HTML file to SVG and PNG
argument-hint: "<html-file> [--svg-only|--png-only] [--scale=N] [--output=<path>] [--registry]"
---

Export diagram HTML at `$1` to `.svg` or `.png`. Locate available `diagram-design` skill using its `SKILL.md` path advertised by Pi. Read that `SKILL.md`, then read `references/export.md` relative to its directory. Treat that reference as source of truth. Do not assume the package lives under the current working directory. If `--registry` is present, also read `references/export-registry.md` relative to the same directory and follow it to emit the metadata sidecar — a separate procedure from the SVG/PNG rasterization above.

Full argument string: `$ARGUMENTS`

## Defaults

- Produce both `.svg` and `.png` next to source (for example, `diagram.html` → `diagram.svg` + `diagram.png`).
- Render PNG at `device_scale_factor=2`.

## Flags

- `--svg-only` — emit SVG only. Skip Playwright.
- `--png-only` — emit PNG only.
- `--scale=1`, `--scale=2`, or `--scale=3` — override PNG device scale factor.
- `--output=<path>` — override output base path; append format extension.
- `--registry` — also emit `<basename>.registry.json`, a metadata sidecar of every block's `data-block-*` attributes. Independent of `--svg-only`/`--png-only`/`--scale`; combine with either or run alone.

## Required behavior

1. No source path → ask user which `.html` file to export. Do not guess.
2. Source is `assets/index.html` → refuse; ask for specific diagram file.
3. Source lacks `<svg>` → refuse; write nothing.
4. PNG requested without Playwright → show install instruction from reference verbatim; stop. Do not auto-install.
5. `--scale` outside {1, 2, 3} → reject.
6. Both `--svg-only` and `--png-only` supplied → reject them as mutually exclusive.
7. `--registry` requested but source has no `data-block-id` attributes → refuse; write nothing. Per the export-registry reference's edge-case section.

After export, report output paths plus sizes.
