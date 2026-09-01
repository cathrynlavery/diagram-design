---
description: Export a diagram-design HTML file to SVG and PNG
argument-hint: "<html-file> [--svg-only|--png-only] [--scale=N] [--output=<path>] [--registry]"
---

Export diagram HTML at `$1` to `.svg` or `.png`. Locate available `diagram-design` skill using its `SKILL.md` path advertised by Pi. Read that `SKILL.md`, then read `references/export.md` relative to its directory. Treat that reference as source of truth. Do not assume the package lives under the current working directory. If `--registry` is present, also read `references/export-registry.md` relative to the same directory and follow it to emit the metadata sidecar — a separate procedure from the SVG/PNG rasterization above.

Full argument string: `$ARGUMENTS`

## Defaults

- With no format flags, or with `--svg-only`/`--png-only`/`--scale`/`--output` but no `--registry`: produce both `.svg` and `.png` next to source (for example, `diagram.html` → `diagram.svg` + `diagram.png`).
- Render PNG at `device_scale_factor=2`.
- `--registry` given alone, with neither `--svg-only` nor `--png-only` also present, produces only the registry JSON — the SVG/PNG defaults above do not apply, and Playwright is never required. Add `--svg-only` and/or `--png-only` explicitly to also get an image.

## Flags

- `--svg-only` — emit SVG only. Skip Playwright.
- `--png-only` — emit PNG only.
- `--scale=1`, `--scale=2`, or `--scale=3` — override PNG device scale factor.
- `--output=<path>` — override output base path; append format extension.
- `--registry` — emit `<basename>.registry.json`, a metadata sidecar of every block's `data-block-*` attributes. Never needs Playwright. Used alone (see Defaults) it is the only output; combine with `--svg-only` and/or `--png-only` to also produce an image.

## Required behavior

1. No source path → ask user which `.html` file to export. Do not guess.
2. Source is `assets/index.html` → refuse; ask for specific diagram file.
3. Source lacks `<svg>` → refuse; write nothing.
4. PNG requested without Playwright → show install instruction from reference verbatim; stop. Do not auto-install.
5. `--scale` outside {1, 2, 3} → reject.
6. Both `--svg-only` and `--png-only` supplied → reject them as mutually exclusive.
7. `--registry` requested but source has no `data-block-id` attributes → refuse; write nothing. Per the export-registry reference's edge-case section.
8. `--registry` is the only flag given (no `--svg-only`/`--png-only`) → emit only the registry JSON; do not also produce SVG/PNG and do not check for Playwright.

After export, report output paths plus sizes.
