---
title: "feat: Send diagrams to Figma via Code to Canvas"
type: feat
status: active
date: 2026-08-12
---

# feat: Send diagrams to Figma via Code to Canvas

## Summary

Add a manual "send this diagram to Figma" capability to the diagram-design plugin: a spike-gated Figma MCP Code to Canvas flow (capture page + loopback server + `generate_figma_design`), a shared SVG-extraction subcommand that also becomes the export path's single implementation, and the existing SVG export as the universal fallback. Every design decision below was locked in an engineering review plus a cross-model outside-voice pass on 2026-08-12 (15 findings, all resolved — see the review report at the end).

---

## Problem Frame

Diagrams ship as standalone HTML with inline SVG. Getting one into Figma today means manually exporting an SVG and pasting it — no agent-drivable path, no returned link, no targeting of a specific file. Figma's Code to Canvas (Feb 2026) promises editable layers from a live page, but its fidelity on pure inline SVG is undocumented, so the feature must be built behind a decision gate rather than on faith.

---

## Requirements

- R1. "Send this diagram to Figma" works as natural language, with a Figma file URL, and as `/diagram-design:figma <html-file>` (slash command: Claude Code; Codex via natural-language routing).
- R2. *(Conditional on the Code to Canvas branch winning U1 — see T6 for the extract-only contract.)* Targets: new Figma draft (default), existing Figma Design file by URL, clipboard — with seat/permission rules surfaced before attempting.
- R3. The source HTML is never modified; a byte-hash proves it after every operation.
- R4. Every failure (MCP missing, unauthenticated, under-permissioned, capture failure, headless session) lands on the existing `references/export.md` SVG fallback with an honest one-line explanation — never a dead end.
- R5. Manual trigger only — never send to Figma unprompted.
- R6. A CI verification gate pins all shipped behaviors on the existing 3-OS × 2-Python matrix; no live Figma in CI.
- R7. The Phase 0 spike is a hard decision gate: mechanics first, then fidelity vs plain SVG paste; the losing branch for Code to Canvas ships extract-only.
- R8. Documentation surfaces (reference, command, prompt, SKILL.md, README) stay synchronized and claim only verified behavior.

---

## Scope Boundaries

- No Write to Canvas (`use_figma`): beta quality, 20KB/call, no assets or custom fonts.
- No Code Layers (early-access, different capability).
- No html.to.design dependency (spike comparator only).
- No custom Figma plugin or native SVG→Figma translator in v1.
- No headless capture — doesn't exist in Figma's architecture; headless sessions pre-flight to the SVG fallback.
- No Pi MCP flow — Pi ships the SVG-fallback prompt until it supports Figma MCP.

### Deferred to Follow-Up Work

- **Codex slash-command packaging** — `.codex-plugin/plugin.json` ships only `skills`; commands can't reach Codex installs today. Revisit when the Codex plugin format supports commands. Until then Codex uses natural-language routing (review decision T4).
- **Automated post-capture font verification** — inspect the resulting Figma file (REST API) for font substitution instead of visual checks. Contingent on Code to Canvas winning the spike (review decision T5).
- **Write to Canvas semantic frames / components / bound variables** — future version, once that API leaves beta.

---

## Context & Research

### Relevant Code and Patterns

- `skills/diagram-design/references/export.md` — existing SVG/PNG export procedure; the fallback path, and (per decision 4A) the consumer of the new shared `extract` subcommand.
- `skills/diagram-design/scripts/drawio_extract.py`, `mermaid_extract.py` — stdlib-only script conventions: untrusted-input posture, structured digest output.
- `scripts/verify-drawio-import.py` — the verify-gate shape to mirror (drives real artifacts, doc-sync checks, exit 0 only when all gates pass).
- `commands/export-diagram.md`, `prompts/export-diagram.md` — thin-wrapper convention: reference file is the source of truth.
- `.github/workflows/ci.yml` — one step per verify gate + summary-table row.
- Nested-SVG examples: `skills/diagram-design/assets/example-datalake*.html`, `example-high-level*.html` (9 files) embed icon `<svg>` elements inside the diagram SVG — the fixture class that kills naive regex extraction.

### External References

- Figma Code to Canvas docs: https://developers.figma.com/docs/figma-mcp-server/code-to-canvas/ — tool `generate_figma_design` (remote MCP only), destinations, seat rules, variable binding, URL-fallback-to-new-file behavior.
- Remote server setup: https://developers.figma.com/docs/figma-mcp-server/remote-server-installation/ — Claude Code / Codex setup, OAuth-only auth.
- Write to Canvas limitations: https://developers.figma.com/docs/figma-mcp-server/write-to-canvas/ — grounds the scope boundary.
- Codeminer42 hands-on postmortem — capture-ID/injected-script/DOM-capture mechanics, viewport-only capture, CSS degradation.

### Key facts that shaped the design

1. Code to Canvas is a **live-page DOM capture**: real browser + local HTTP server (no `file://`), capture script POSTs the rendered DOM to Figma; browser-in-the-loop, no headless path.
2. Capture is **viewport-only** — off-screen content silently drops.
3. Inline-SVG fidelity is **undocumented**; plain SVG paste is a proven high-fidelity path. Hence the spike gate (R7).
4. Seats: any seat for drafts/clipboard; Full seat + edit access for existing files outside drafts. OAuth only.
5. A target URL that isn't a Design file **silently creates a new file** — a postcondition check is mandatory.
6. The Figma session is **interactive** (team prompt, additional toolbar captures) — cleanup needs a user-done boundary, not poll-and-kill.

---

## Key Technical Decisions

All confirmed interactively in the 2026-08-12 engineering review (issue/tension IDs preserved):

- **1A — Scale-to-fit capture page.** The capture page renders the SVG at `width:100%; max-height:100vh` so any viewport contains the whole diagram; the spike asserts Figma reconstructs from viewBox coordinates, not display pixels. Prevents silent cropping on small screens.
- **2A/8A — Self-terminating server, injectable timeouts.** `serve` exits at `--max-lifetime` (generous default sized for the interactive Figma session), deleting its own capture dir on exit; both timeout flags accept any positive value so CI expiry proofs run in ~2s. **Idle-timeout is not armed in the interactive flow** — after the initial capture Figma sends no further loopback traffic, so an armed idle timer would kill the server mid-session while the user is still working in Figma. `--idle-timeout` exists for CI expiry proofs and abandoned-session cleanup only (when armed, it must be ≥ max-lifetime in interactive use). If the max-lifetime backstop fires while the user still needs toolbar captures, the reference scripts the recovery plainly: re-run `/figma` — the source file is untouched, so re-capture is cheap.
- **3A/T4 — Mechanics-first, dual-client spike.** Stage 1 (go/no-go, run in Claude Code AND Codex): static zero-JS page captures at all; scale-to-fit geometry lands at viewBox coordinates; programmatic URL-targeting works; retry/destination behavior is observable; capture-vs-font-loading timing. Stage 2 (only if Stage 1 passes): fidelity bake-off vs plain SVG paste on light, dark (CSS-variable-heavy), and terminal variants.
- **4A/T1 — One extraction implementation, parser-based.** `figma_capture.py extract` uses balanced-tag (stdlib `html.parser`) SVG isolation — never first-`</svg>` regex, which truncates the 9 shipped nested-SVG examples. `build` calls it; `export.md` points agents at it (prose kept as no-script fallback). `check` rejects or flags active/external constructs (`<script>`, event handlers, `foreignObject`, external `url()`/`@import`/`href`) — the security posture states what's true instead of claiming "nothing executes."
- **5A — Fix the stale pointer** in `export.md` (`commands/export.md` → `commands/export-diagram.md`); doc-sync gate asserts every reference→command pointer resolves.
- **6A — Explicit error paths.** Missing/unusable `viewBox` → hard fail with a clear message; GUI-browser pre-flight (headless/SSH detection) routes straight to the SVG fallback before any doomed capture poll.
- **7A — Full verify-gate adoption.** All nine review-identified test additions ship in the CI gate, including the extract-parity case (CRITICAL regression guard for the export path), server self-expiry/self-cleanup proofs, the nested-SVG fixture, and the `role="img"` diagram-not-glyph assertion. Enumerated in U3.
- **T2 — Ownership-tracked cleanup.** No `--out` flag; `build` always creates its own temp directory; deletion is restricted to directories this run created. A verify case proves a pre-existing directory is never removed.
- **T3 — Trust-but-verify results.** On timeout, reconcile the same capture ID before any re-submit (retry only proven-pre-submission failures); after success, compare returned destination to the requested target and treat an unexpected new draft as a failure.
- **T5 — User-done completion boundary.** The server stays up until the user confirms they're finished in Figma (max-lifetime as backstop); capture page preloads the three font families; acceptance criterion for fonts is "visually verified," stated honestly.
- **T6 — Losing branch ships extract-only.** If SVG paste wins the spike, v1 ships `/figma` as `extract` + guided handoff: no `serve`, no capture page, verify gate shrinks to extract/doc-sync/hygiene. The Code to Canvas machinery stays designed-on-paper here.
  **Extract-only branch contract:** `/figma <html-file>` produces a standalone SVG next to the source plus step-by-step paste instructions; `--target` is dropped; seat rules, destination validation, and the capture lifecycle do not apply; R2 is void in this branch (R1's three invocation styles survive, all routing to the extract+handoff flow). U6's acceptance matrix reduces to: extract correctness on both representative diagrams, guided paste verified once in Figma, MCP-missing/headless messaging, source-hash integrity. The README section describes the SVG handoff and frames Code to Canvas as a future option.
- **T7 — Claim only what sources support.** Variable binding worded as "may bind in configured target files"; no `MAX_MCP_OUTPUT_TOKENS` error row unless the spike reproduces it; §Acceptance is a release gate (pre-tag), fleet installs are post-release smoke.

---

## Open Questions

### Resolved During Planning

- Primary mechanism: Code to Canvas vs SVG-first — resolved into a spike-gated branch structure (R7, T6).
- Extraction strategy: parser-based balanced isolation, shared with export (4A/T1).
- Cleanup ownership, retry semantics, destination validation, session lifecycle — all resolved (T2/T3/T5).

### Deferred to Implementation (the spike answers these)

- Does a zero-JS static page served by `http.server` trigger capture, or must the capture snippet be embedded in the temp page? (Plan B pre-approved: embed it — the temp page is ephemeral tooling, not a deliverable.)
- Does scaled-down display degrade Figma's reconstruction? (1A assertion.)
- Can `generate_figma_design` be pointed at a file URL programmatically, and is the returned destination observable? (3A/T3.)
- Does the initial capture beat font loading? (T5.)
- Actual inline-SVG fidelity vs SVG paste. (Stage 2.)

---

## Output Structure

    skills/diagram-design/
      scripts/figma_capture.py          # extract | check | build | serve
      references/figma.md               # source-of-truth procedure
    commands/figma.md                   # Claude Code slash command
    prompts/figma.md                    # Pi prompt (SVG fallback path)
    scripts/verify-figma-export.py      # CI verification gate
    scripts/fixtures/                   # nested-SVG fixture (from example-datalake)

---

## High-Level Technical Design

> *Directional guidance for review, not implementation specification.*

```
diagram.html
   │  figma_capture.py
   ├─ check   ── gallery? no <svg>? no viewBox? active content? ──✗ refuse w/ message
   ├─ extract ── balanced-tag SVG isolation (shared with export.md)
   ├─ build   ── capture page: source <head> styles + font preloads,
   │             body = diagram only, scale-to-fit (1A), owned temp dir,
   │             manifest {path, w×h, source sha256}
   └─ serve   ── 127.0.0.1:ephemeral/<token>/, owned-dir root, self-expiring (2A/8A)
                       │
        agent: Figma MCP present? ──no──> per-agent setup + SVG fallback
                       │ yes                         ▲
        GUI browser?  ──no──────────────────────────┤ (6A pre-flight)
                       │ yes                         │
        generate_figma_design(local URL, target) ────┤ error/timeout:
                       │                             │ reconcile capture ID (T3)
        browser opens; user completes in Figma       │ then ONE retry, else fallback
                       │ user-done boundary (T5)     │
        validate destination == requested target (T3)┘
                       │
        report Figma link ──> kill server, delete owned dirs (T2)
```

---

## Implementation Units

- U1. **Phase 0 spike — mechanics gate, then fidelity bake-off (decision gate)**

**Goal:** Prove or kill the Code to Canvas path before building it; select the winning branch for U2–U6.

**Requirements:** R7

**Dependencies:** Environment prerequisites — (1) Figma account with a Full seat and edit access to a scratch Design file (required for the URL-targeting check); (2) Figma remote MCP server connected and OAuth-authenticated in **both** Claude Code and Codex (per the remote-server-installation doc, including the Codex `rmcp_client` note); (3) a GUI browser session (not SSH/headless); (4) a throwaway drafts space for generated files.

**Files:**
- Create: `docs/plans/2026-08-12-001-feat-figma-code-to-canvas-export-plan.md` (spike ledger appended as a dated section) — no product code

**Approach:**
- Stage 1 (mechanics, run in Claude Code and Codex): hand-built capture page from `skills/diagram-design/assets/example-architecture.html`, served via `python3 -m http.server --bind 127.0.0.1`. Checks: static-page capture fires; scale-to-fit geometry lands at viewBox coordinates; URL-targeting is programmatic; destination is observable in the result; retry/reconcile behavior; capture-vs-`document.fonts.ready` timing; whether a toolbar re-capture re-fetches the local URL or reuses the already-captured DOM (determines how long `serve` must outlive the initial capture).
- Stage 2 (fidelity, only if Stage 1 passes): same diagram via Code to Canvas vs pasted `export.md` SVG, side by side in one Figma file; repeat for a dark variant and the terminal variant. Compare path geometry, markers, dashes, masks, fonts, text editability, layer structure, `<title>`/`<desc>` survival.
- **Pre-committed branch-decision rule (recorded in the ledger before Stage 2 begins):** Code to Canvas wins only if it matches plain SVG paste on path geometry and font rendering across all three variants AND delivers a concrete workflow advantage (editable text/layers or fewer user interactions than extract-plus-paste). Any geometry or font regression means SVG paste wins. The rule is written down first so mixed results can't be argued into shipping the machinery.
- Record a fidelity ledger with screenshots; the branch decision (full flow vs extract-only per T6) is written into this plan before U2 begins.

**Test scenarios:** Test expectation: none — throwaway spike; its output is the recorded ledger and branch decision.

**Verification:** Ledger records pass/fail for every Stage 1 check in both clients; branch decision committed to this plan file.

- U2. **`figma_capture.py` — extract / check / build / serve**

**Goal:** The deterministic tooling: shared SVG extraction, validation, capture-page builder, self-expiring loopback server.

**Requirements:** R2, R3, R6; decisions 1A, 2A, 4A, 6A, 8A, T1, T2

**Dependencies:** U1 (losing branch: only `extract` + `check` ship)

**Files:**
- Create: `skills/diagram-design/scripts/figma_capture.py`
- Test: `scripts/verify-figma-export.py` (written in U3; scenarios enumerated there)

**Approach:**
- Stdlib only, mirroring `drawio_extract.py` conventions. Subcommands: `extract <src> [--stdout]`, `check <src>`, `build <src>` (owned temp dir + JSON manifest), `serve <capture-dir> --max-lifetime N --idle-timeout N`.
- Balanced-tag extraction via `html.parser`; refuse gallery (`assets/index.html` / multiple sibling diagram SVGs), missing `<svg>`, missing/unusable `viewBox`, active/external constructs. External-reference policy (committed): `check` allowlists exactly the known Google Fonts hosts (`fonts.googleapis.com`, `fonts.gstatic.com`) by default with no flag — every shipped diagram legitimately loads them — and rejects every other external `url()`/`@import`/`href`; no override flag in v1.
- Capture page: source `<head>` styles + `<link rel="preload">` for Instrument Serif/Geist/Geist Mono, body = SVG only, `margin:0`, scale-to-fit CSS.
- `serve`: `http.server` bound to `127.0.0.1`, port 0, rooted at the owned capture dir; the capture page lives under a random per-session path token (e.g. `/<uuid>/index.html`) and any request missing the token gets a 404, so knowing the loopback port alone is not enough for another local process to read the diagram; exits on max-lifetime (idle-timeout only when explicitly armed — see 2A/8A); deletes only directories recorded as created by this run.

**Patterns to follow:** `drawio_extract.py` (arg handling, untrusted input, digest output), `export.md` §SVG procedure (standalone-SVG spec the `extract` output must match).

**Test scenarios:** enumerated in U3 (single verify gate drives this script).

**Verification:** All U3 verify cases pass locally on macOS; script runs on Python 3.11/3.12 with no third-party imports.

- U3. **`verify-figma-export.py` + CI wiring**

**Goal:** Pin every shipped behavior in CI; extend doc-sync coverage.

**Requirements:** R3, R6, R8; decisions 5A, 7A, T1, T2, 8A

**Dependencies:** U2

**Files:**
- Create: `scripts/verify-figma-export.py`, `scripts/fixtures/` nested-SVG fixture (derived from `example-datalake.html`)
- Modify: `.github/workflows/ci.yml` (new step + summary-table row)

**Approach:** Same shape as `verify-drawio-import.py`: drive the real artifacts, exit non-zero on any failure.

**Test scenarios:**
- Happy path: light / dark / full / terminal variants → capture page whose SVG is byte-identical to the source's first diagram SVG, styles+fonts present, scale-to-fit CSS present, body sized from viewBox.
- Happy path: `extract` output == `export.md` standalone-SVG spec (xmlns, viewBox, fonts `@import`, XML declaration) — **CRITICAL regression guard** for the export path.
- Edge: nested-SVG fixture (datalake) → extraction returns the complete outer SVG including all nested icon SVGs.
- Edge: extracted SVG carries `role="img"` (proves diagram, not decorative glyph); `<title>`/`<desc>`/`aria-labelledby` survive verbatim.
- Edge: spaces and unicode in source paths.
- Error: missing `<svg>`, gallery file, malformed HTML, missing `viewBox`, embedded `<script>`/event-handler content → non-zero exit, nothing written, message names the cause.
- Edge: external-reference policy pinned from both sides — the Google Fonts link passes `check`; any other external `url()`/`@import`/`href` fails it.
- Error: `serve` request outside the capture dir → refused; asserted bind address is `127.0.0.1`.
- Integration: `serve --max-lifetime 2` exits ≈2s and removes its owned dir; `--idle-timeout 2` likewise; a pre-existing user directory passed as cwd context is never deleted.
- Integration: source SHA-256 identical before/after every subcommand.
- Hygiene: no credential/token patterns, no user-absolute paths in any generated artifact.
- Doc-sync: `commands/figma.md`, `prompts/figma.md`, `references/figma.md`, `SKILL.md` consistent (flags, target names, fallback wording); every reference→command pointer in `references/` resolves to an existing file (catches the 5A class repo-wide).

**Verification:** Gate green on all 6 matrix jobs; deliberate mutations (break a pointer, re-introduce regex extraction) fail it.

- U4. **Agent workflow surfaces — reference, command, prompt, routing**

**Goal:** The procedure agents follow, in the repo's reference-as-source-of-truth pattern.

**Requirements:** R1, R2, R4, R5; decisions 3A, 6A, T3, T4, T5, T7

**Dependencies:** U1 (wording depends on branch), U2

**Files:**
- Create: `skills/diagram-design/references/figma.md`, `commands/figma.md`, `prompts/figma.md`
- Modify: `skills/diagram-design/SKILL.md` (§12 routing paragraph + version 2.3)

**Approach:**
- `references/figma.md` carries: the contract; MCP detection with per-agent setup lines (Claude Code and Codex, including the `rmcp_client` note); GUI-browser pre-flight; check → build → serve → `generate_figma_design` → user-done boundary → destination validation → report link → cleanup; the error table (no token-cap row); fallback rules; honest variable-binding wording; Codex = natural-language routing (no slash command until packaging supports it).
- `commands/figma.md`: thin wrapper, `<html-file> [--target=draft|clipboard|<figma-url>]`, delegates to the reference.
- `prompts/figma.md` (Pi): routes to the SVG fallback procedure.

**Patterns to follow:** `references/export.md` trigger/edge-case structure; `commands/export-diagram.md` wrapper shape.

**Test scenarios:** covered by U3's doc-sync cases (behavioral testing of the live flow is U6's acceptance matrix). Test expectation for prose files beyond doc-sync: none — no executable behavior.

**Verification:** Doc-sync gate passes; a dry read-through of the reference reproduces the U1 spike flow without improvisation.

- U5. **Export path updates**

**Goal:** Make `extract` the single extraction implementation and fix the stale pointer.

**Requirements:** R8; decisions 4A, 5A

**Dependencies:** U2

**Files:**
- Modify: `skills/diagram-design/references/export.md`

**Approach:** SVG procedure points agents at `figma_capture.py extract` (prose retained as no-script fallback); fix `commands/export.md` → `commands/export-diagram.md` at line 9.

**Test scenarios:** the U3 extract-parity CRITICAL case and pointer-resolution case are this unit's regression guards.

**Verification:** Export of `example-datalake.html` via `extract` yields the complete nested-SVG diagram (previously truncated by the prose regex).

- U6. **Docs, packaging, release gate, fleet install**

**Goal:** Ship 2.3.0 honestly: README, CONTRIBUTING, manifests, pre-tag acceptance, post-release smoke.

**Requirements:** R1, R2, R8; decision T7

**Dependencies:** U3, U4, U5

**Files:**
- Modify: `README.md` (Send-to-Figma section after Export), `CONTRIBUTING.md` (validation-gates list), `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` (2.3.0, description + `figma` keyword)

**Approach & release sequencing (T7):**
1. **Release gate (pre-tag):** live acceptance matrix in fresh Claude Code and Codex sessions — new draft; existing editable file (destination validated); clipboard; MCP missing; unauthenticated; seat-denied; headless/SSH session → clean SVG fallback; fonts visually verified; source-hash unchanged after every run; kill-agent-mid-capture → server self-expires, no orphan. Pi runs the SVG-fallback path once.
2. Merge and release only after the gate + green CI + Greptile 5/5 with resolved comments.
3. **Post-release smoke:** install on local, studio, ronan, knox — verifying each machine's customized `style-guide.md` survives (accent token spot-check) — then one generate→send→edit-in-Figma round-trip per machine. Anything unexercised is reported "unverified."

**Test scenarios:** Test expectation: none — packaging/docs; the acceptance matrix above is the live verification.

**Verification:** Release tagged only after step 1 passes; per-machine smoke results recorded.

---

## System-Wide Impact

- **Interaction graph:** New entry points (`/diagram-design:figma`, SKILL.md routing) plus one modified existing surface: `export.md`'s SVG procedure now delegates to `extract` — the parity case guards existing export behavior.
- **Error propagation:** Every Figma-path failure terminates in the SVG fallback with an honest message; no path dead-ends (R4).
- **State lifecycle risks:** Temp dirs and server lifetime are process-guaranteed (2A/T2); source files are read-only by contract with hash proof (R3).
- **API surface parity:** Slash command Claude-Code-only until Codex packaging exists (T4); Pi = SVG fallback; all three documented explicitly.
- **Integration coverage:** Live acceptance matrix covers what CI can't (real MCP, real browser, real seats).
- **Unchanged invariants:** Generated diagram HTML format, the accessible-SVG contract, the no-JS-in-deliverables rule (the capture page is ephemeral tooling, not a deliverable), and all existing verify gates.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| Code to Canvas mangles inline SVG (undocumented) | U1 Stage 2 is a hard gate; T6 losing branch ships extract-only |
| Static zero-JS page doesn't trigger capture | U1 Stage 1 first check; pre-approved plan B embeds the capture snippet in the ephemeral page |
| Figma changes/renames the tool (fast-moving product) | Runtime tool detection, never hardcoded; all failures land on SVG fallback |
| Capture races font loading | Preloads + U1 timing measurement; substitution reported honestly; automated inspection deferred |
| Figma silently creates a new file for a bad target URL | T3 destination postcondition treats it as failure |
| Timeout after successful submit → duplicate drafts | T3 reconcile-same-capture-ID before any retry |
| Browser-in-the-loop surprises users | Reference scripts the exact wording: "your browser will open briefly so Figma can capture the page" |

---

## Documentation / Operational Notes

- README section mirrors the reference's contract table (targets × seat requirements) and the fallback sentence, plus two additions the plan commits to: (1) the intro tagline is reframed so the headline and this feature tell one story — Figma-independence with optional export ("No Figma required — but when you want editable layers there, one command sends any diagram over"), with the doc-sync review confirming intro and Send-to-Figma section agree; (2) the section carries the browser disclosure up front ("your browser will open briefly so Figma can capture the page", plus the finish-in-Figma/user-done step) and a three-row invocation table: Claude Code = slash command, Codex = natural language only (slash command deferred, T4), Pi = SVG fallback.
- The reviewed draft with full research narrative lives at `docs/plan-figma-export.md`; this plan supersedes it for execution.
- Fleet installs (studio, ronan, knox) must preserve onboarded style guides — verify the accent token per machine before declaring done.

---

## Sources & References

- Reviewed draft + research narrative: `docs/plan-figma-export.md`
- Related code: `skills/diagram-design/references/export.md`, `scripts/verify-drawio-import.py`, `skills/diagram-design/scripts/drawio_extract.py`
- External docs: Figma Code to Canvas / remote-server-installation / write-to-canvas (developers.figma.com)
- Eng-review task artifact: `~/.gstack/projects/cathrynlavery-diagram-design/tasks-eng-review-20260812-122240.jsonl`

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 0 | — | — |
| Codex Review | `/codex review` | Independent 2nd opinion | 1 | ABSORBED | 14 findings, 7 substantive tensions, all resolved |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | CLEAR | 15 issues, 0 critical gaps |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | — |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | — | — |

**CODEX:** Outside voice found 14 problems; 2 verified against shipped files (nested-SVG truncation in 9 examples; Codex plugin ships no commands). All 7 substantive tensions accepted and folded into the decisions above (T1–T7).

**CROSS-MODEL:** Claude review hardened lifecycle/coverage (1A–8A); Codex caught extraction correctness, cleanup data-loss, capture idempotency, and packaging honesty. No unresolved disagreements.

**VERDICT:** ENG CLEARED (15/15 findings folded) — ready to implement, starting with U1.

NO UNRESOLVED DECISIONS
