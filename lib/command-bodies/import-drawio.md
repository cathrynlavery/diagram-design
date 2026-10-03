Redraw a draw.io file as a Diagram Design diagram.

The installed skill directory is `{{SKILL_DIR}}`. `references/import-drawio.md` is the source of
truth for the import procedure, and `references/output-spec.md` is the source of truth for
format, size, detail and audience. Do not reimplement their logic.

Resolve every `references/…` and `scripts/…` path below against the skill directory above.

Accepts `.drawio`, `.drawio.xml`, `.xml`, `.drawio.png`, and `.drawio.svg`.

Defaults

- `--format=html` — a self-contained HTML file beside the source.
- `--size=doc-inline` — `viewBox 0 0 960 600`.
- `--detail=balanced`, `--audience=mixed`, `--variant=light`.
- A single-page file selects its only page; a multi-page file lists the pages and asks which to use.
- The diagram type comes from the extracted structure; `--type` forces one of the visual types
  listed in `SKILL.md` §3.

Flags: `--format`, `--size`, `--detail`, `--audience`, `--type`, `--page`, `--variant`,
`--output`. Their values and the size presets are in `references/output-spec.md`.

Required behaviour

1. No file given → ask which `.drawio` file. Do not guess.
2. Always run `scripts/drawio_extract.py` from the skill directory first. Never assume the skill
   sits under the current working directory, and never read a `.drawio` file directly — most are
   compressed and the raw XML is noise.
3. Extractor exits non-zero → report its message verbatim and stop.
4. Digest shows 0 nodes → the source is image-only or encrypted. Say so and ask for the original
   file. Do not invent content.
5. Multi-page file with no `--page` → list the pages with their node and edge counts and ask which.
6. Requested detail is impossible at the requested size → say so before drawing and propose an
   overview plus per-zone detail.
7. `--detail=faithful` above 9 nodes → zone the layout; above 24 nodes → split into an overview
   plus detail files.
8. Never carry over source coordinates, colors, or fonts. The output is a redraw in the project's
   `references/style-guide.md` skin.
9. Run the `SKILL.md` §9 taste gate and the `references/output-spec.md` §6 checklist before writing.

After writing, report the paths, the sizes, the four dials used, and the fidelity ledger: what was
merged, collapsed, or dropped.