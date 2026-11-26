---
description: Export a diagram-design HTML file to .svg, .png, and optionally .pdf next to the source
argument-hint: <html-file> [--svg-only|--png-only|--pdf-only] [--pdf] [--page-size=a4|a3|letter] [--full-page] [--scale=N] [--output=<path>] [--registry]
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
---

Export the diagram HTML at `$1` to `.svg`, `.png`, and/or `.pdf`, following the procedure documented in [`skills/diagram-design/references/export.md`](../skills/diagram-design/references/export.md). Treat that reference as the source of truth — don't reimplement the logic here. Run the packaged `skills/diagram-design/scripts/export_svg.py`, `skills/diagram-design/scripts/export_png.py`, and `skills/diagram-design/scripts/export_pdf.py` helpers for the requested formats. If `--registry` is present, also follow [`skills/diagram-design/references/export-registry.md`](../skills/diagram-design/references/export-registry.md) to emit the metadata sidecar — a separate procedure from the SVG/PNG/PDF export above.

Full argument string: `$ARGUMENTS`

## Defaults

- **With no format flag (nothing, or only `--scale`/`--output`) and no `--registry`:** produce **both** `.svg` and `.png` next to the source (e.g. `diagram.html` → `diagram.svg` + `diagram.png`). `--svg-only`, `--png-only`, or `--pdf-only` restricts the image/document output to that one format. Pass `--pdf` to emit `.pdf` alongside the default or chosen format(s).
- PNG renders at `device_scale_factor=2`.
- **`--registry` given by itself, with none of `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` also present, produces *only* the registry JSON.** The SVG/PNG defaults above do not also apply, and Playwright is never required for a registry-only call. To get an image or PDF alongside the registry, add `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` explicitly.

## Flags

- `--svg-only` — emit only the SVG. Skip Playwright entirely.
- `--png-only` — emit only the PNG.
- `--pdf` — also emit a print-ready vector `.pdf` via `scripts/export_pdf.py` (exact viewBox bounds by default). Requires Playwright.
- `--pdf-only` — emit only the vector `.pdf`. Requires Playwright.
- `--page-size=a4|a3|letter` — fit PDF output onto a landscape A4, A3, or US Letter sheet instead of exact viewBox bounds.
- `--full-page` — include the editorial wrapper (header, cards, footer) in PDF output instead of diagram-only SVG.
- `--scale=N` — override the PNG device scale factor with a finite number from `1` to `4`, including fractional values such as `1.25`. Default `2`.
- `--output=<path>` — override the output base path; the format extension is appended. Applies to all produced formats.
- `--registry` — emit `<basename>.registry.json`, a metadata sidecar of every block's `data-block-*` attributes. Follows [`skills/diagram-design/references/export-registry.md`](../skills/diagram-design/references/export-registry.md), a procedure independent of the SVG/PNG/PDF export above — it never needs Playwright. Used alone (see Defaults), it is the *only* output produced. Combine with `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` to also produce an image or PDF in the same call.

## Required behaviour

1. **No source path provided** → ask the user which `.html` file to export. Don't guess.
2. **Source is `assets/index.html`** (the gallery, multiple SVGs in one file) → refuse and ask which specific diagram file. Per the reference's edge-case section.
3. **Source has no `<svg>` block** → refuse and tell the user; don't write anything.
4. **PNG or PDF requested but Playwright not installed** → surface the install instruction from the reference verbatim and stop. Do **not** auto-install.
5. **PNG requested with a non-numeric or non-finite `--scale`, or a value outside the inclusive 1–4 range** → reject. Fractional values within that range are valid.
6. **More than one of `--svg-only`, `--png-only`, or `--pdf-only` supplied** → reject them as mutually exclusive.
7. **`--registry` requested but source has no `data-block-id` attributes** → refuse and tell the user; don't emit an empty or partial registry file. Per the export-registry reference's edge-case section.
8. **`--registry` is the only flag given** (no `--svg-only`/`--png-only`/`--pdf`/`--pdf-only`) → emit only the registry JSON. Do not also produce SVG/PNG/PDF, and do not check for Playwright — a registry-only call must succeed on a host that doesn't have it installed at all.

After producing the outputs, report the file paths and sizes back to the user.
