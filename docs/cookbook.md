# Diagram Design cookbook

Operator recipes for this repository. The design system still lives in [`skills/diagrams-design-quind/SKILL.md`](../skills/diagrams-design-quind/SKILL.md); this file is the runbook: what to say, which files to load, and which commands to run.

Use it from an **editable clone** (this checkout). Managed marketplace installs can still follow the recipes, but do not edit `references/style-guide.md` inside a package that updates will replace — save a [client profile](../skills/diagrams-design-quind/references/profiles.md) instead.

---

## Map

| I want to… | Jump |
|---|---|
| Wire this clone into Claude, Codex, Cursor, Cline, Kiro, OpenCode, or Copilot | [R0](#r0-editable-install) |
| Confirm Python, Playwright, PNG export | [R1](#r1-doctor) |
| Draw the first diagram in a real project | [R2](#r2-first-diagram-in-a-project) |
| Match a brand | [R3](#r3-onboard-a-skin) |
| Choose type / pattern / size without rereading the whole skill | [R4](#r4-selection-cheat-sheet) |
| Browse shipped examples | [R5](#r5-gallery-and-templates) |
| Redraw draw.io, Mermaid, Excalidraw, or PlantUML | [R6](#r6-import) |
| Hand off SVG or PNG | [R7](#r7-export) |
| Check a generated HTML file | [R8](#r8-taste-and-geometry-gates) |
| Paste a request to an agent | [R9](#r9-prompt-pack) |

---

## R0. Editable install

The canonical skill root is `skills/diagrams-design-quind/` (`SKILL.md` + `references/` + `assets/`). Point skill hosts at that inner directory. Pi and the repository's native marketplace packages are the exceptions because they already resolve the `skills/` directory from the repository root.

This repository does not duplicate `SKILL.md` into host-specific loader stubs. For an editable install, symlink or junction the canonical inner directory into one discovery root used by your host.

### Host matrix

| Host | How it finds the skill | What you do |
|---|---|---|
| **Claude Code** | Marketplace plugin, `~/.claude/skills/`, or project `.claude/skills/` | Use `/plugin install` for managed updates or link the inner skill for editable work. |
| **Claude Desktop** | **Customize → Skills → Upload a skill** | Build `dist/diagrams-design-quind-claude-skill.zip` with `python3 scripts/build-claude-skill-zip.py` and upload that ZIP. The full skill tree is over the upload file limit. |
| **Codex** | Marketplace plugin or `~/.agents/skills/` | Use the marketplace for managed updates or link the inner skill for editable work. |
| **Cursor** | `~/.cursor/skills/`, `~/.agents/skills/`, project `.cursor/skills/`, or project `.agents/skills/` | Link the inner skill, then ask in Agent chat. |
| **Cline CLI / VS Code** | `~/.cline/skills/`, `~/.agents/skills/`, workspace `.cline/skills/`, or workspace `.agents/skills/` | Link the inner skill and enable it from the Skills view when needed. |
| **Kiro** | Workspace `.kiro/skills/` or global `~/.kiro/skills/` | Link the inner skill, or import its GitHub subdirectory URL; imported skills are copied and must be re-imported to update. |
| **OpenCode** | Project `.opencode/skills/` or global `~/.config/opencode/skills/` | Link or copy the inner skill; copied installs must be replaced to update. |
| **GitHub Copilot** | Marketplace plugin; project `.github/skills/`, `.agents/skills/`, or `.claude/skills/`; user `~/.copilot/skills/`, `~/.agents/skills/`, or `~/.claude/skills/` | Use the marketplace for managed updates or link the inner skill for editable work. |

Marketplace installs (Claude `/plugin`, `copilot plugin install`, `codex plugin add`, `droid plugin install`) stay the right path if you do **not** need to edit `style-guide.md` in-tree. Use profiles instead. For the hosts in the matrix that have no marketplace package, `npx skills add cathrynlavery/diagram-design` does the same job in one command - it installs the inner skill into every root you select, symlinking them to one canonical copy by default and copying independently under `--copy`. That install is standalone: it belongs to the CLI rather than to your checkout or to any marketplace, so it does not follow marketplace updates automatically. Refresh it with `npx skills update diagram-design`.

### Unix (user-global inner skill)

```bash
git clone https://github.com/cathrynlavery/diagram-design.git ~/code/diagram-design
DIAGRAM_SKILL=~/code/diagram-design/skills/diagrams-design-quind
mkdir -p ~/.claude/skills ~/.cursor/skills ~/.agents/skills ~/.cline/skills \
  ~/.kiro/skills ~/.config/opencode/skills ~/.copilot/skills
ln -s "$DIAGRAM_SKILL" ~/.claude/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.cursor/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.agents/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.cline/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.kiro/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.config/opencode/skills/diagrams-design-quind
ln -s "$DIAGRAM_SKILL" ~/.copilot/skills/diagrams-design-quind
```

Create only the destinations for the hosts you use. When a host scans both its native root and `.agents/skills/`, choose one so it does not discover the same skill twice.

### Windows (directory junction — not a file symlink)

```powershell
$src = "E:\diagram-design\skills\diagram-design"
foreach ($t in @(
  "$env:USERPROFILE\.claude\skills\diagram-design",
  "$env:USERPROFILE\.cursor\skills\diagram-design",
  "$env:USERPROFILE\.agents\skills\diagram-design",
  "$env:USERPROFILE\.cline\skills\diagram-design",
  "$env:USERPROFILE\.kiro\skills\diagram-design",
  "$env:USERPROFILE\.config\opencode\skills\diagram-design",
  "$env:USERPROFILE\.copilot\skills\diagram-design"
)) {
  $parent = Split-Path $t -Parent
  if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
  if (-not (Test-Path $t)) { cmd /c mklink /J "$t" "$src" }
}
```

Replace `E:\diagram-design` with your clone path. If a junction already exists, leave it; do not copy the skill over a managed plugin folder.

Pi still registers the **repo root**: `pi install <clone-path>`.

---

## R1. Doctor

Ask in any host: `run diagram-design doctor` or `/diagrams-design-quind:doctor` / `/doctor`.

The procedure is [`references/doctor.md`](../skills/diagrams-design-quind/references/doctor.md). It must not install packages. Typical local setup for PNG export:

```bash
python -m pip install playwright
python -m playwright install chromium
```

On Windows, `python` is the usual interpreter; the skill also accepts `python3` when that is what the host has.

---

## R2. First diagram in a project

Work in the **project that will own the HTML**, not inside `skills/diagrams-design-quind/assets/` unless you are contributing an example.

1. **Style-guide gate** ([SKILL.md §0](../skills/diagrams-design-quind/SKILL.md)). If the working copy is still shipped defaults (paper `#f5f5f5`, ink `#2d3142`, accent `#bf4520`), the agent must pause and offer onboarding, a profile, or an explicit default. Skip the gate when a valid `.diagram-design` marker selects a profile (including `profile: default`).
2. **Confirm before drawing** ([SKILL.md §3](../skills/diagrams-design-quind/SKILL.md)): visual type, optional semantic pattern, size preset, and what the complexity budget will cut.
3. **Load** the matching `references/type-*.md` before writing SVG. If a semantic pattern applies, load [`semantic-patterns.md`](../skills/diagrams-design-quind/references/semantic-patterns.md) first.
4. **Write** a self-contained HTML file in the project (for example `docs/diagrams/<name>.html`). Do not silently overwrite gallery examples.
5. **Render and look** ([SKILL.md §10](../skills/diagrams-design-quind/SKILL.md)): rasterize a scratch preview with `scripts/export_png.py`, open it, and fix overlaps or clipping before the checklist.
6. **Run** the pre-output checklist ([SKILL.md §9](../skills/diagrams-design-quind/SKILL.md)). Orthogonal connectors, 4px grid, ≤9 nodes unless you split, accent on ≤2 focals.

Marker file at the project root, entire file:

```text
profile: <slug>
```

See [`profiles.md`](../skills/diagrams-design-quind/references/profiles.md). Profiles live in `~/.diagram-design/profiles/`, not in this clone.

---

## R3. Onboard a skin

Full flow: [`onboarding.md`](../skills/diagrams-design-quind/references/onboarding.md).

Say one of:

- `Onboard diagram-design to https://example.com`
- `Extract diagram-design tokens from the local design-system folder <path>`
- `Use these tokens: paper … ink … accent …` (manual)
- `Proceed with the default skin` (optionally write `profile: default` with consent)

Then: propose the style-guide diff, wait for approval, write `references/style-guide.md` **or** save a named profile and point the project marker at it. Prefer profiles when this clone is shared or when plugin updates would clobber a customized working copy.

---

## R4. Selection cheat sheet

Do not duplicate the 40-type table here. Open [SKILL.md §3](../skills/diagrams-design-quind/SKILL.md) and pick one layout grammar.

**Behavior first** (then nearest type):

| If the story is… | Pattern → type |
|---|---|
| Fan-in, queues, bottlenecks | Fan-in queue → Data flow |
| Repeated stage slots | Stage framework → Process |
| Messy input becomes a durable artifact | Unstructured → structured → Data flow |
| Two policy traces, first divergence | Paired traces → Flowchart |
| Trust boundaries / paved road | Secure paved road → Architecture |
| Controls by enforcement layer | Governance catalog → Layer stack |
| Compensating defenses, residual risk | Compensating layers → Layer stack |

**Hard stops:** if a table or paragraph is clearer, do not draw. If you are over the [complexity budget](../skills/diagrams-design-quind/SKILL.md) (9 nodes / 12 arrows as the default ceiling), split overview + detail.

**Size** ([output-spec.md](../skills/diagrams-design-quind/references/output-spec.md)): `doc-inline` for docs, `slide-16x9` for decks, `social-og` for cards, `fit` for Figma SVG. Size changes type ramp, not just viewBox.

**Motion:** default is static. Load [`animation.md`](../skills/diagrams-design-quind/references/animation.md) only when the user asked for motion or ordered change is otherwise unclear.

---

## R5. Gallery and templates

From the clone root:

```bash
# macOS / Linux
open skills/diagrams-design-quind/assets/index.html
xdg-open skills/diagrams-design-quind/assets/index.html

# Windows
start skills/diagrams-design-quind/assets/index.html
```

Copy a scaffold, then replace the SVG:

```bash
cp skills/diagrams-design-quind/assets/template.html my-diagram.html
cp skills/diagrams-design-quind/assets/template-full.html my-diagram.html
cp skills/diagrams-design-quind/assets/template-motion.html my-diagram.html
```

Shipped examples are `assets/example-<type>.html` plus `-dark` and `-full` variants. Treat them as specimens, not scratch files.

---

## R6. Import

Load [`import-drawio.md`](../skills/diagrams-design-quind/references/import-drawio.md), [`import-mermaid.md`](../skills/diagrams-design-quind/references/import-mermaid.md), [`import-excalidraw.md`](../skills/diagrams-design-quind/references/import-excalidraw.md), or [`import-plantuml.md`](../skills/diagrams-design-quind/references/import-plantuml.md) and set the four dials **before** redrawing ([output-spec.md](../skills/diagrams-design-quind/references/output-spec.md)):

| Dial | Typical values |
|---|---|
| Format | `html` · `svg` · `png` · `html+png` |
| Size | `doc-inline` · `slide-16x9` · `social-og` · `fit` · … |
| Detail | `faithful` · `balanced` · `simplified` |
| Audience | `engineer` · `mixed` · `executive` |

Slash forms (Claude): `/diagrams-design-quind:import-drawio <file>`, `/diagrams-design-quind:import-mermaid <file-or-md>`, `/diagrams-design-quind:import-excalidraw <file>`, and `/diagrams-design-quind:import-plantuml <file>`. Always report a **fidelity ledger** (merged, collapsed, dropped). Source coordinates, source palette, Mermaid auto-layout, Excalidraw hand-drawn geometry, and PlantUML skinparams do not carry over.

Extractors in this checkout: `skills/diagrams-design-quind/scripts/drawio_extract.py`, `mermaid_extract.py`, `excalidraw_extract.py`, `plantuml_extract.py`.

---

## R7. Export

**Never export unprompted.** Procedure: [`export.md`](../skills/diagrams-design-quind/references/export.md).

- SVG: first `<svg>` only, XML-escaped Google Fonts `@import`, diagram-only (no full-page cards).
- PNG: Playwright screenshot of that SVG box, transparent background. Motion HTML: `?motion=static`, wait for `document.fonts.ready`, `data-frame="static"`.

```
/diagrams-design-quind:export-diagram path/to/diagram.html
/diagrams-design-quind:export-diagram path/to/diagram.html --png-only --scale=2
```

---

## R8. Taste and geometry gates

After generating HTML in this clone (examples or a file you are contributing):

```bash
python skills/diagrams-design-quind/scripts/self_check.py path/to/diagram.html
python scripts/lint-skin.py path/to/diagram.html
python scripts/verify-geometry.py path/to/diagram.html
```

Full contributor gates: [CONTRIBUTING.md](../CONTRIBUTING.md). Docs/routing: `python scripts/verify-docs-sync.py`.

---

## R9. Prompt pack

Copy and fill. Keep one type, one size, one destination.

**Architecture (docs):**

> Draw an architecture diagram of [system]. Nodes: [list ≤9]. Focal: [1–2]. Size `doc-inline`, format HTML. Use the diagram-design skill. Confirm type and cuts before drawing. Save to `[path].html`.

**Deck:**

> Redraw `[file].drawio` for a 16:9 slide, detail `simplified`, audience `executive`, format PNG.

**Mermaid in a README:**

> Import every Mermaid block in `[file].md`, size `doc-wide`, detail `balanced`, audience `mixed`. Report the fidelity ledger.

**Brand, then diagram:**

> Onboard diagram-design from `https://[site]`. If I approve the tokens, save profile `[slug]` and write `.diagram-design` with `profile: [slug]`. Then draw [type] of [topic].

**Do not:**

> Make it look like Mermaid / add shadows / coral every box / diagonal connectors / more than nine nodes in one figure.

---

## Pointers

| Topic | File |
|---|---|
| Philosophy, types, checklist | [`SKILL.md`](../skills/diagrams-design-quind/SKILL.md) |
| Tokens | [`style-guide.md`](../skills/diagrams-design-quind/references/style-guide.md) |
| Settled design decisions | [`docs/adr/`](adr/) |
| Maintainer validation | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
