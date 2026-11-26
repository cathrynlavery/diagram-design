---
description: Export a diagram-design HTML file to SVG, PNG, and optionally vector PDF
argument-hint: "<html-file> [--svg-only|--png-only|--pdf-only] [--pdf] [--page-size=a4|a3|letter] [--full-page] [--scale=N] [--output=<path>] [--registry]"
---

Export diagram HTML at `$1` to `.svg`, `.png`, or `.pdf`. Locate available `diagram-design` skill using its `SKILL.md` path advertised by Pi. Read that `SKILL.md`, then read `references/export.md` relative to its directory. Treat that reference as source of truth. Run `scripts/export_svg.py`, `scripts/export_png.py`, and `scripts/export_pdf.py` relative to the skill directory for the requested formats. Do not assume the package lives under the current working directory. If `--registry` is present, also read `references/export-registry.md` relative to the same directory and follow it to emit the metadata sidecar — a separate procedure from the SVG/PNG/PDF export above.

Full argument string: `$ARGUMENTS`

## Defaults

- With no format flag (nothing, or only `--scale`/`--output`) and no `--registry`: produce both `.svg` and `.png` next to source (for example, `diagram.html` → `diagram.svg` + `diagram.png`). `--svg-only`, `--png-only`, or `--pdf-only` restricts output to that one format; `--pdf` adds `.pdf` alongside the default or chosen format(s).
- Render PNG at `device_scale_factor=2`.
- `--registry` given alone, with none of `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` also present, produces only the registry JSON — the SVG/PNG defaults above do not apply, and Playwright is never required. Add `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` explicitly to also get an image or PDF.

## Flags

- `--svg-only` — emit SVG only. Skip Playwright.
- `--png-only` — emit PNG only.
- `--pdf` — also emit a vector `.pdf` via `scripts/export_pdf.py`. Requires Playwright.
- `--pdf-only` — emit vector PDF only. Requires Playwright.
- `--page-size=a4|a3|letter` — fit PDF onto a landscape A4, A3, or US Letter sheet.
- `--full-page` — include the editorial wrapper in PDF output instead of diagram-only SVG.
- `--scale=N` — override PNG device scale factor with a finite number from `1` to `4`, including fractional values such as `1.25`. Default `2`.
- `--output=<path>` — override output base path; append format extension.
- `--registry` — emit `<basename>.registry.json`, a metadata sidecar of every block's `data-block-*` attributes. Never needs Playwright. Used alone (see Defaults) it is the only output; combine with `--svg-only`, `--png-only`, `--pdf`, or `--pdf-only` to also produce an image or PDF.

## Required behavior

1. No source path → ask user which `.html` file to export. Do not guess.
2. Source is `assets/index.html` → refuse; ask for specific diagram file.
3. Source lacks `<svg>` → refuse; write nothing.
4. PNG or PDF requested without Playwright → show install instruction from reference verbatim; stop. Do not auto-install.
5. PNG requested with a non-numeric or non-finite `--scale`, or a value outside the inclusive 1–4 range → reject. Fractional values within that range are valid.
6. More than one of `--svg-only`, `--png-only`, or `--pdf-only` supplied → reject them as mutually exclusive.
7. `--registry` requested but source has no `data-block-id` attributes → refuse; write nothing. Per the export-registry reference's edge-case section.
8. `--registry` is the only flag given (no `--svg-only`/`--png-only`/`--pdf`/`--pdf-only`) → emit only the registry JSON; do not also produce SVG/PNG/PDF and do not check for Playwright.

After export, report output paths plus sizes.
