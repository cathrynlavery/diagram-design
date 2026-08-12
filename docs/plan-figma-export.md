# Plan: Send a diagram to Figma (Code to Canvas)
**Status:** draft for review · **Target version:** 2.3.0 · **Date:** 2026-08-12

Add a first-class "send this diagram to Figma" path to the diagram-design plugin:

- "Send this diagram to Figma." / "Send this diagram to `<Figma file URL>`."
  
- `/diagram-design:figma path/to/diagram.html`
  
- Targets: new Figma draft (default), existing Figma Design file, clipboard.
  
- SVG export fallback (existing `references/export.md`) whenever Figma MCP is unavailable, unauthenticated, or under-permissioned.
  

* * *
## 1. What the research changed
I researched Figma's official MCP docs, the launch/help-center material, and hands-on engineering reports. Four findings materially change the original sketch:
### 1.1 Code to Canvas is a live-page DOM capture, not an HTML upload
`generate_figma_design` (the Code to Canvas tool, confirmed current name) does **not** accept HTML as a parameter. The documented mechanics:

1. The agent calls `generate_figma_design` on the **remote** Figma MCP server (`https://mcp.figma.com/mcp` — the tool does not exist on the desktop MCP server) and receives a capture ID.
  
2. A **real browser** must load the page from a **running local HTTP server** (`file://` URLs are not supported), with Figma-supplied hash params (`#figmacapture=<id>&figmaendpoint=<url>`).
  
3. A capture script runs in the page, serializes the rendered DOM, and POSTs it to Figma; the agent polls until the layers land.
  

Consequences for us:

- We must **serve** the capture page over `127.0.0.1`, not just write a temp file.
  
- The flow is **browser-in-the-loop** — there is no headless path. The agent opens the capture URL in the user's browser (`open <url>` on macOS) as part of the flow.
  
- **Capture is viewport-only.** Off-screen content is silently dropped. Our capture page must size the viewport/body exactly to the diagram's `viewBox` so nothing scrolls out of frame. (This is documented as a real failure mode: mid-scroll sections of a page simply vanish.)
  
### 1.2 Inline-SVG fidelity is undocumented — this needs a spike before we build
No source states how Code to Canvas handles inline SVG paths, markers, dash arrays, opacity stops, `<title>`/`<desc>`, or web fonts. Known adjacent signals are worrying:

- CSS effects with no Figma-primitive equivalent degrade (confirmed: `background-clip: text` gradients flatten to plain colored text).
  
- A confirmed SVG bounding-box bug exists in the adjacent `get_design_context` tool.
  
- For the separate Write to Canvas tool, custom fonts are explicitly unsupported; for Code to Canvas, fonts are undocumented either way.
  

Meanwhile our deliverable is _pure inline SVG_ — and Figma's plain **SVG paste** has been a high-fidelity vector import path for years. It is genuinely possible that our existing SVG export pasted into Figma beats Code to Canvas on fidelity for this content, with Code to Canvas winning only on ergonomics (agent-drivable, returns a link, auto variable binding).

**So Phase 0 is a decision gate, not a formality** (§3).
### 1.3 Permissions and targets (confirmed)
| Target | Requirement |
| --- | --- |
| New file in **drafts** | Any seat |
| **Existing file outside drafts** | Full seat **and** edit permission |
| **Clipboard** | Any seat |

`generate_figma_design` is exempt from the MCP read-tool rate limits (the ~6-calls/month Starter-seat cap applies to `get_design_context` etc., not to this tool). Auth is OAuth only — no PAT support.
### 1.4 Setup differs per agent
- **Claude Code:** `claude mcp add --transport http figma https://mcp.figma.com/mcp` (or the official plugin), restart, OAuth in browser.
  
- **Codex CLI:** `codex mcp add figma --url https://mcp.figma.com/mcp`; older builds need a `~/.codex/config.toml` entry plus the `rmcp_client` feature flag.
  
- **Pi:** no Figma MCP → SVG fallback path, as originally proposed.
  
- Desktop app is **not** required (remote server), but a browser is.
  
### 1.5 Explicitly out of scope (confirmed by research)
- **Write to Canvas (**`use_figma`**)** — explicitly beta ("output may need manual review"), 20KB per-call output limit, no image/asset support, no custom fonts. Matches the original scope boundary; a later version could revisit.
  
- **Code Layers** (Config 2026) — different feature (live code components on canvas), early-access only, Full seat. Do not conflate.
  
- **html.to.design** — third-party MCP alternative with a longer HTML→Figma track record. We won't depend on it, but it's a useful comparator in the Phase 0 bake-off if Code to Canvas underperforms.
  

* * *
## 2. The contract
Documented at the top of `references/figma.md` (source of truth), mirrored briefly in README.

- **Accepted sources:** a single diagram-design HTML file (any variant: light, dark, full, terminal, sketchy, imported). Same edge-case rules as `export.md`: gallery (`assets/index.html` or any multi-diagram page) → refuse and ask which diagram; no `<svg>` → refuse; the **source HTML is never modified**.
  
- **Targets:** `draft` (default) · `file <Figma URL>` · `clipboard`. A pasted Figma URL implies `file`.
  
- **Permissions:** surfaced before attempting — existing-file target warns it needs a Full seat + edit access, and on failure offers `draft` or `clipboard` instead.
  
- **Fallback:** if Figma MCP is missing / unauthenticated / denied / capture fails → run the existing `export.md` SVG procedure, hand the user the `.svg`, and explain the trade-off in one sentence (editable vectors either way; Code to Canvas adds structured layers + variable binding; SVG paste is manual but dependable).
  
- **Trigger:** manual only, like export — never send to Figma unprompted.
  
- **Security:** temp server binds `127.0.0.1` on an ephemeral port, serves only the capture temp dir, and is shut down and deleted afterward. Source content is never fetched or executed; no OAuth tokens or Figma state ever land in generated artifacts.
  

* * *
## 3. Phase 0 — fidelity spike (decision gate)
Timeboxed, before any real implementation. In a Claude Code session with Figma MCP connected:

1. Hand-build a minimal capture page from `assets/example-architecture.html` (head + fonts + the one `<svg>`, body sized to `viewBox`), serve it with `python3 -m http.server --bind 127.0.0.1`, run `generate_figma_design` → new draft.
  
2. In the same Figma file, paste the existing `export.md` SVG output of the same diagram.
  
3. Compare side by side: path geometry, arrow markers, dashed strokes, label masks, fonts (Instrument Serif / Geist / Geist Mono), text editability, layer structure, `<title>`/`<desc>` survival.
  
4. Repeat once with a dark variant (CSS-variable-heavy) and once with the terminal variant.
  

Also resolve the one open mechanical question: **does a zero-JS static page served by** `http.server` **capture at all**, or does the capture script injection assume a dev server? If static serving fails, the capture page embeds Figma's capture snippet itself (the temp page is ephemeral tooling, so the "no JS in deliverables" rule is untouched).

**Decision:**

- **Code to Canvas ≥ SVG paste on fidelity** → build as planned; SVG stays the fallback.
  
- **Code to Canvas < SVG paste** → invert the design: `/figma` becomes a _Figma handoff_ command whose primary path is the SVG export plus guided paste (and optionally still offers Code to Canvas with a fidelity warning). Same files, same verification, different default — so the spike outcome changes wording, not architecture.
  

Record spike results (screenshots + a short fidelity ledger) in the PR description.

* * *
## 4. File map
New files follow the existing pattern exactly (reference = source of truth; commands/prompts are thin wrappers; one verify script per feature wired into CI):

| File | Role |
|---|---|
| `skills/diagram-design/scripts/figma_capture.py` | Deterministic capture-page builder + local server (§5) |
| `skills/diagram-design/references/figma.md` | Source-of-truth procedure: contract, MCP detection, serve → capture → target → link → cleanup, permission/error UX, fallback rules, Claude/Codex/Pi setup notes |
| `commands/figma.md` | Claude Code / Codex slash command `/diagram-design:figma <html-file> [--target=draft\|clipboard\|<url>]` — delegates to the reference |
| `prompts/figma.md` | Pi prompt — routes to the SVG fallback until Pi supports the MCP flow |
| `scripts/verify-figma-export.py` | CI verification gate (§7) |

Edits: `SKILL.md` (§12 gains a "Sending to Figma" routing paragraph next to the export one, plus natural-language triggers), `README.md`, `CONTRIBUTING.md` (validation-gates list), `.github/workflows/ci.yml` (new step + summary row), both plugin manifests → `2.3.0`.

* * *
## 5. `figma_capture.py` design
One script, three modes, stdlib only (matches `drawio_extract.py` / `mermaid_extract.py` conventions: no third-party deps, JSON-ish digest output, treats all source content as untrusted data).

```
figma_capture.py check  <src.html>            # validate only, exit 0/1 + reasons
figma_capture.py build  <src.html> [--out DIR] # write capture page, print manifest JSON
figma_capture.py serve  <capture-dir>          # 127.0.0.1, port 0 (ephemeral), prints URL, serves until killed
```

`build` **steps:**

1. Validate: file exists, parses, contains ≥1 `<svg>`; refuse the gallery (`assets/index.html` or multiple sibling diagram SVGs); never fetch or execute anything from the source.
  
2. Isolate the **first** `<svg>` block (same regex-anchored extraction as `export.md`).
  
3. Emit a capture page into a fresh `mktemp -d`:
  
  - Source `<head>` styles and Google Fonts `<link>` carried over so CSS variables, classes, and typography resolve identically.
    
  - `<body>` contains **only** the diagram SVG; `margin: 0`; body and page sized exactly to the `viewBox` (viewport-only capture, §1.1).
    
  - `<title>`, `<desc>`, `role="img"`, `aria-labelledby` preserved verbatim.
    
  - No scripts (unless the Phase 0 spike proves the Figma capture snippet must be embedded — then it's added here, in the temp page only).
    
4. Print a manifest: temp dir, capture file path, width × height, source SHA-256 (so verification can prove the source is untouched).
  

`serve` wraps `http.server` bound to `127.0.0.1`, port 0, rooted at the capture dir only. The agent runs it in the background, opens the Figma-provided capture URL, and kills it (and removes the temp dir) after the capture completes or fails.

**The agent workflow in** `references/figma.md`**:**

1. Detect Figma MCP (is `generate_figma_design` callable?). Missing → print per-agent setup instructions + offer SVG fallback.
  
2. `check` → `build` → `serve`.
  
3. Call `generate_figma_design` with the local URL and the chosen target; open the capture URL in the browser; poll.
  
4. Report the resulting Figma link (or "pasteable from clipboard").
  
5. Always: kill server, delete temp dir — including on error paths.
  
6. Any failure after step 1 → offer the SVG fallback rather than dead-ending.
  

* * *
## 6. Error and permission UX
| Situation | Behavior |
| --- | --- |
| Figma MCP not configured | Show the one-line setup command for the current agent; offer SVG fallback now |
| OAuth expired / unauthenticated | Say so plainly; offer re-auth or SVG fallback |
| Existing-file target, no Full seat / no edit access | Explain the seat rule; offer draft or clipboard |
| Capture times out / errors | One retry, then SVG fallback with the error surfaced |
| Gallery / no-SVG / malformed source | Refuse with the same wording family as export.md; write nothing |
| MCP response exceeds client token cap | Surface the `MAX_MCP_OUTPUT_TOKENS` remedy from Figma's known-issues doc |

* * *
## 7. `scripts/verify-figma-export.py` (CI gate)
Same shape as `verify-drawio-import.py`: drives the real shipped artifacts, exits non-zero on any failure, added to `ci.yml` (all-OS × Python 3.11/3.12 matrix) and the summary table. No live Figma in CI — everything below is structural:

- **Capture correctness:** CSS-variable diagram, inline-style diagram, light / dark / full / terminal variants each produce a capture page whose SVG is byte-identical to the source's first SVG, with styles + fonts present and body sized to the `viewBox`.
  
- **Rejections:** missing SVG, gallery file, malformed HTML → non-zero exit, nothing written.
  
- **Path robustness:** spaces (and unicode) in source paths.
  
- **Source integrity:** source SHA-256 identical before/after every mode.
  
- **Accessibility:** `<title>`, `<desc>`, `role`, `aria-labelledby` survive into the capture page.
  
- **Hygiene:** no credentials/token patterns, no user-absolute paths in any generated artifact; `serve` binds only `127.0.0.1` (assert on the bound socket) and refuses to serve outside the capture dir.
  
- **Doc sync:** `commands/figma.md`, `prompts/figma.md`, `references/figma.md`, and `SKILL.md` cross-reference each other consistently (flag names, target names, fallback wording) — same technique the draw.io verifier uses.
  

* * *
## 8. Docs and packaging
- **README:** new "Send to Figma" section after "Export to PNG / SVG" — the three invocations, target table with seat requirements, fallback sentence.
  
- **SKILL.md:** routing paragraph in §12 + version bump to 2.3.
  
- **CONTRIBUTING:** add the new gate to the validation list.
  
- **Manifests:** `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` → `2.3.0`; description gains "send to Figma"; keyword `figma`.
  

* * *
## 9. Live acceptance matrix (pre-release)
Fresh Claude Code and Codex sessions, real Figma account:

| #   | Scenario | Pass criterion |
| --- | --- | --- |
| 1   | New draft, architecture example | Editable layers in a new draft; link returned; temp server gone |
| 2   | Existing editable file via URL | Layers land in that file |
| 3   | Clipboard target | Paste into any file works |
| 4   | MCP missing | Setup instructions + working SVG fallback |
| 5   | Unauthenticated MCP | Clean message + fallback offer |
| 6   | Existing file without Full seat | Seat explanation + draft/clipboard offer |
| 7   | Fonts unavailable in Figma | Substitution reported honestly |
| 8   | Process diagram (second representative type) | Same as #1 |
| 9   | Source hash check after every run | Unchanged |

Codex runs at least #1 and #4. Pi runs the SVG-fallback path once.

* * *
## 10. Release and fleet install
After review, green CI, and Greptile 5/5 with resolved comments:

1. Merge, tag, release 2.3.0.
  
2. Install on this machine plus studio, ronan, and knox — **preserving each machine's customized** `style-guide.md` (the install must not clobber onboarded skins; verify the accent token survives on each machine).
  
3. Final live check per machine: generate one diagram, send to a Figma draft, open it, edit a node. Anything short of that is reported as "unverified", not done.
  

* * *
## 11. Risks and open questions
| Risk | Mitigation |
| --- | --- |
| Code to Canvas mangles inline SVG (undocumented) | Phase 0 spike is a hard gate; SVG-first inversion is pre-designed (§3) |
| Static zero-JS page may not trigger capture | Spike tests it; embedding the capture snippet in the temp page is the pre-approved plan B |
| Fonts (Instrument Serif / Geist) unsupported in capture | Spike measures it; if fonts flatten, the reference documents it and recommends matching fonts installed in Figma |
| Browser-in-the-loop step surprises users | The reference scripts the exact wording: "your browser will open briefly so Figma can capture the page" |
| Figma renames/re-scopes the tool (product moving fast in 2026) | Detection is by tool availability at runtime, not hardcoded assumptions; failure path always lands on the SVG fallback |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ABSORBED | 14 findings, 7 substantive tensions, all resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 15 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** Outside voice found 14 problems; 2 verified against shipped files (nested-SVG truncation in 9 examples; Codex plugin ships no commands). All 7 substantive tensions accepted: parser-based extraction + active-content rejection (T1), owned-dir-only cleanup, `--out` dropped (T2), reconcile-before-retry + destination postcondition (T3), Codex = NL routing + dual-client spike (T4), user-done completion boundary + font preloads (T5), SVG-first losing branch ships extract-only (T6), editorial batch (T7).

**CROSS-MODEL:** Claude review hardened lifecycle/coverage (1A–8A); Codex caught extraction correctness, cleanup data-loss, capture idempotency, packaging honesty. No unresolved disagreements — Codex sharpened five Claude decisions rather than reversing any.

**VERDICT:** ENG CLEARED (15/15 findings folded) — ready for plan formalization and spike.

NO UNRESOLVED DECISIONS
