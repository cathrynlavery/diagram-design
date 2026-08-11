---
mode: agent
description: Export a diagram-design HTML file to SVG and PNG
tools:
  - read_file
  - write_file
  - run_terminal_command
---

Export the diagram HTML at `${input:html-file}` to `.svg` and/or `.png`, following the procedure in [`skills/diagram-design/references/export.md`](../skills/diagram-design/references/export.md). Read that reference first — treat it as the source of truth.

## Defaults

- Produce **both** `.svg` and `.png` next to the source file.
- PNG renders at `device_scale_factor=2`.

## Flags (append to the file path if needed)

- `--svg-only` — emit only SVG, skip Playwright.
- `--png-only` — emit only PNG.
- `--scale=1|2|3` — override PNG device scale factor (default `2`).
- `--output=<path>` — override output base path; format extension is appended.

## Required behaviour

1. **No source path** → ask the user which `.html` file to export. Don't guess.
2. **Source is `assets/index.html`** (the gallery) → refuse; ask for a specific diagram file.
3. **Source has no `<svg>` block** → refuse and explain; write nothing.
4. **PNG requested but Playwright not installed** → show the install instruction from the reference verbatim; stop. Do not auto-install.
5. **`--scale` outside {1,2,3}** → reject with valid values.

After export, report the output file paths and sizes.
