# Local agent — Diagram Design with LM Studio, fully offline

Run the Diagram Design skill against a model served by [LM Studio](https://lmstudio.ai) on your own machine. No hosted host (Claude Code, Codex, Pi), no API key, no `ANTHROPIC_*` variables, and — after a one-time bootstrap — no network at all. Output is the same as the hosted skill's: a self-contained `.html`, plus a standalone `.svg` and a `.png`.

The runner does not paraphrase the skill. The model reads the same `SKILL.md` sections, `style-guide.md`, `type-<name>.md`, template and example file a hosted agent loads; the runner only decides which of those fit the model's context window, checks the result with the repository's own gates, and sends failures back for repair.

## One-time setup (online)

```bash
python local-agent/bootstrap.py --playwright
```

This does three things, each only once:

| Step | What it downloads | Where it goes |
|---|---|---|
| Fonts | every Google Fonts slice of Instrument Serif, Geist, Geist Mono and Noto Serif the templates request (~1 MB) | `local-agent/fonts/` (git-ignored) |
| `--playwright` | the `playwright` package and a headless Chromium build (~115 MB) | your Python environment and `~/AppData/Local/ms-playwright` (or `~/.cache/ms-playwright`) |
| Check | nothing | prints `OK offline-ready` when both are in place |

Add `--cjk` to also vendor Noto Sans/Serif KR and TC for Korean or Chinese labels (about 1,000 slices). Re-run `python local-agent/bootstrap.py --check` at any time, offline, to confirm nothing is missing.

In LM Studio: download a model, open **Developer → Start Server** (default port 1234), and set the model's context length to **at least 32k**; 64k lets the runner send the full style guide as well. Note the model id shown by `lms ls` or `GET /v1/models`.

## Generate a diagram

```bash
python local-agent/agent.py --model qwen/qwen3.8-27b "Flowchart for handling an incoming order: validate payment, check stock, offer backorder or refund when out of stock, otherwise pick, pack and ship."
```

Output lands in `diagrams/<slug>.html`, `.svg` and `.png`. Steer it with:

| Flag | Effect |
|---|---|
| `--type flowchart` | skip type selection (any of the 41 `references/type-*.md` slugs) |
| `--variant light\|dark\|full` | which template to start from |
| `--size doc-inline\|doc-wide\|slide-16x9\|…` | size preset from `references/output-spec.md` §2 |
| `--title "…"` | with `--type`, skips the planning call entirely |
| `--out path.html` | where to write; `.svg` / `.png` go next to it |
| `--prompt-file brief.md` | read a longer request from a file |
| `--profile full\|lean` | how much of the skill to send (auto-picks `lean` under a 48k window) |
| `--style-guide path` | a customised `style-guide.md` (see the onboarding flow in the main README) |
| `--max-repairs N` | verify→repair rounds after the first draw (default 2) |
| `--no-png` / `--no-svg` | skip an export |

What one run does:

1. **plan** — a small call chooses the visual type, variant, size, title, slug, the ≤9 nodes it will draw and what it cuts, using the skill's visual-type guide.
2. **draw** — one call with the design rules, type reference, template and example in context returns the whole HTML file.
3. **verify** — `skills/diagram-design/scripts/self_check.py`, `scripts/verify-geometry.py`, structural checks (placeholders, viewBox vs preset, stray scripts) and layout checks a small model most often gets wrong: a node outside the canvas, a label wider than its box, an arrow that ends where no node is. A reply that is prose instead of a file ("I'll start by checking…") is saved next to the output and the model is asked again.
4. **repair** — findings go back to the model, up to `--max-repairs` times.
5. **finish** — the Google Fonts `<link>` is replaced by embedded `@font-face` data, the file is written, and `.svg` + `.png` are exported.

The exit code is `0` when every gate passed, `2` when the file was written with open findings (they are printed), `1` when nothing usable came back.

## Export an existing file

```bash
python local-agent/export.py path/to/diagram.html
python local-agent/export.py path/to/diagram.html --svg-only
python local-agent/export.py path/to/diagram.html --png-only --scale 3
```

Same procedure as `references/export.md`, with one substitution: the standalone `.svg` embeds the vendored `@font-face` slices instead of a Google Fonts `@import`, so it renders with the right type on a machine with no network. The PNG is rendered in the local Chromium with every `http(s)` request blocked — if it looks right, it is offline by construction. A file that still carries a Google Fonts `<link>` (one made by a hosted agent, say) is rendered through a temporary font-embedded twin.

## What is and isn't offline

| Concern | Offline? | Notes |
|---|---|---|
| Model inference | yes | LM Studio on `localhost:1234` |
| Skill rules, templates, examples | yes | read from this checkout |
| Fonts in `.html` / `.svg` / `.png` | yes | embedded from `local-agent/fonts/` |
| Verification gates | yes | pure Python, no dependencies |
| PNG rasterisation | yes | local Chromium via Playwright |
| Brand onboarding from a website URL | no | it fetches the site by definition; use `--style-guide` with tokens you wrote by hand, or the folder/skill onboarding paths |
| draw.io / Mermaid / Excalidraw import | yes, but not wired here | the extractors in `skills/diagram-design/scripts/` run offline; feed their digest into the request text |

A generated file is a few hundred KB larger than a hosted one because the fonts ride inside it. Only the slices whose `unicode-range` matches the document's text are embedded (Latin always), so an English diagram carries about ten faces.

## Expectations for a 27B model

The skill's quality comes from the model following ~40 KB of geometry and restraint rules while hand-writing SVG. A local 27B model does this well for flowcharts, sequences, layer stacks and similar bounded types; it is less reliable on dense types (Sankey, treemap, heatmap) and on the `full` editorial variant. The repair loop catches contract violations and the coarse layout faults above, not taste: an arrow that stops at a zone edge instead of the box inside it, or a node that strays out of its zone, still passes. When a result is off:

- give it fewer nodes in the request, or name the cuts yourself;
- pin `--type`, `--size` and `--variant` instead of letting the plan choose;
- raise the context length in LM Studio and run with `--profile full`;
- lower `--temperature` (default 0.2) for stricter template adherence.

Tests: `python scripts/test-local-agent.py` (uses an in-process fake of LM Studio; no model or fonts required).
