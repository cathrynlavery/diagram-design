Export a finished Diagram Design HTML file to `.svg` and `.png` beside it.

The installed skill directory is `{{SKILL_DIR}}`. `references/export.md` is the source of truth
for the procedure, and `references/export-registry.md` is the source of truth for `--registry`.
Do not reimplement either.

Resolve every `references/…` and `scripts/…` path below against the skill directory above.

Defaults

- No format flags, or any of `--svg-only` / `--png-only` / `--scale` / `--output` without
  `--registry`: produce **both** `.svg` and `.png` beside the source.
- PNG renders at `device_scale_factor=2`.
- `--registry` on its own produces **only** the registry JSON. The defaults above do not also
  apply, and Playwright is never required for a registry-only call.

Flags

- `--svg-only` — SVG only; skip Playwright entirely.
- `--png-only` — PNG only.
- `--scale=1|2|3` — override the PNG device scale factor. Default `2`.
- `--output=<path>` — override the output base path; the extension is appended.
- `--registry` — emit `<basename>.registry.json`, a sidecar of every block's `data-block-*`
  attributes, following `references/export-registry.md`.

Required behaviour

1. No source path given → ask which `.html` file to export. Do not guess.
2. Source is `assets/index.html` → refuse and ask for a specific diagram file.
3. Source has no `<svg>` block → refuse and tell the user. Write nothing.
4. PNG requested and Playwright is not installed → surface the reference's install instruction
   verbatim and stop. Do not auto-install.
5. PNG requested with `--scale` outside {1, 2, 3} → reject.
6. `--registry` requested but the source has no `data-block-id` attributes → refuse and tell the
   user. Do not emit an empty or partial registry file.
7. `--registry` as the only flag → emit only the registry JSON, and do not check for Playwright.

For SVG output prefer the packaged helper `scripts/export_svg.py`; it carries class-based CSS into
the fragment and namespaces `<defs>` IDs. After producing output, report the file paths and sizes.