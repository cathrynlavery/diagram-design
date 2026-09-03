---
description: Export a diagram-design HTML file to .svg and .png next to the source
argument-hint: <html-file> [--svg-only|--png-only] [--scale=N] [--output=<path>] [--registry]
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
---

Export the diagram HTML at `$1` to `.svg` and/or `.png`, following the procedure documented in [`skills/diagram-design/references/export.md`](../skills/diagram-design/references/export.md). Treat that reference as the source of truth — don't reimplement the logic here. If `--registry` is present, also follow [`skills/diagram-design/references/export-registry.md`](../skills/diagram-design/references/export-registry.md) to emit the metadata sidecar — a separate procedure from the SVG/PNG rasterization above.

Full argument string: `$ARGUMENTS`

## Defaults

- **With no format flags, or with `--svg-only`/`--png-only`/`--scale`/`--output` but no `--registry`:** produce **both** `.svg` and `.png` next to the source (e.g. `diagram.html` → `diagram.svg` + `diagram.png`).
- PNG renders at `device_scale_factor=2`.
- **`--registry` given by itself, with neither `--svg-only` nor `--png-only` also present, produces *only* the registry JSON.** The SVG/PNG defaults above do not also apply, and Playwright is never required for a registry-only call. To get an image alongside the registry, add `--svg-only` and/or `--png-only` explicitly.

## Flags

- `--svg-only` — emit only the SVG. Skip Playwright entirely.
- `--png-only` — emit only the PNG.
- `--scale=1` / `--scale=2` / `--scale=3` — override the PNG device scale factor. Default `2`.
- `--output=<path>` — override the output base path; the format extension is appended. Applies to both formats when both are produced.
- `--registry` — emit `<basename>.registry.json`, a metadata sidecar of every block's `data-block-*` attributes. Follows [`skills/diagram-design/references/export-registry.md`](../skills/diagram-design/references/export-registry.md), a procedure independent of the SVG/PNG rasterization above — it never needs Playwright. Used alone (see Defaults), it is the *only* output produced. Combine with `--svg-only` and/or `--png-only` to also produce an image in the same call.

## Required behaviour

1. **No source path provided** → ask the user which `.html` file to export. Don't guess.
2. **Source is `assets/index.html`** (the gallery, multiple SVGs in one file) → refuse and ask which specific diagram file. Per the reference's edge-case section.
3. **Source has no `<svg>` block** → refuse and tell the user; don't write anything.
4. **PNG requested but Playwright not installed** → surface the install instruction from the reference verbatim and stop. Do **not** auto-install.
5. **PNG requested with `--scale` outside {1,2,3}** → reject; valid values are 1, 2, 3.
6. **`--registry` requested but source has no `data-block-id` attributes** → refuse and tell the user; don't emit an empty or partial registry file. Per the export-registry reference's edge-case section.
7. **`--registry` is the only flag given** (no `--svg-only`/`--png-only`) → emit only the registry JSON. Do not also produce SVG/PNG, and do not check for Playwright — a registry-only call must succeed on a host that doesn't have it installed at all.

After producing the outputs, report the file paths and sizes back to the user.
