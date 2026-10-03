# ADR 0013 — DeepSeek Harness installs from the repository root with a routed skill body

**Status:** accepted (v2.6.51)

## Context

DeepSeek Harness is an Agent Skills host. It scans `<projectRoot>/.agents/skills` for a project and `<agentsHome>/skills` globally, and its discovery expects exactly the layout this repository already ships: `<root>/<name>/SKILL.md` with the reference files beside it. Those are two of the roots the README already documents for Cursor, Cline, and Codex. A symlink therefore worked before this decision, and the skill's frontmatter (`name: diagram-design` plus the routing description) satisfies DSH's requirements without edits.

What a symlink does not provide is the install path every other native host has. Claude, Codex, and Factory each install through a manifest their host resolves; DSH would have no install command, no release tracking, and no version gate.

Two host constraints shape the implementation.

First, DSH's base bundle mounts `@deepseek-ai/dsh-compaction-tool-result-pruner` at `thresholdChars: 8192`, `headChars: 4096`, `tailChars: 1024`, and it rewrites `tool/result` events. The `skill` tool returns a tool result, and `skills/diagram-design/SKILL.md` is 29,706 bytes. A provider that inlined it would deliver the model the opening and closing sections with the middle marked as pruned, so the agent would draw from a partial specification while appearing to have the full skill. ADR 0004's own amendment already treats `SKILL.md` as a router over `references/`; that is the shape this decision adopts rather than fighting.

Second, DSH removed its `.dsh-plugin` authoring format on 2026-09-04 with no compatibility parser retained, so there is no directory manifest to add. DSH's native metadata is the root `package.json`, whose `dsh.bundle.patch` points at `cordis.patch.yml`. This repository's three existing manifests are `plugin.json` files that their own hosts resolve; `package.json` is the same role for DSH, so the shared-metadata rule below applies to it.

## Decision

DeepSeek Harness is a fourth native host, installed with:

```bash
dsh plugin --profile <profile> add github:cathrynlavery/diagram-design
```

The host package lives at the repository root. `package.json` carries the same shared identity, description, version, author, repository, license, and keyword metadata as the three existing manifests, plus `dsh.bundle.patch`, and `cordis.patch.yml` contributes one profile row. The packaged-surface checks in `verify-plugin-package.py` already require a packaged `skills/diagram-design/SKILL.md` and `commands/` at the plugin root for every marketplace-backed host; DSH resolves that same root and is covered without new registration. Its description is checked against the `SKILL.md` selection table by `verify-docs-sync.py`, which now reads `package.json` for the DSH host alongside the three manifests.

`apply()` registers two things and nothing else: a packaged skill provider over the repository's own `skills/diagram-design/` tree, and the six slash commands from `commands/`. Nothing in the skill tree is copied, translated, or patched. The description is parsed from the upstream `SKILL.md` at read time, and the skill directory is handed to DSH as the skill's `resourceBase`, so the model resolves `references/`, `assets/`, and `scripts/` against the installed files.

The body sent to the model is a compact router under 4,096 characters that names the sections and reference files to read on demand, rather than `SKILL.md` itself. That router is the only new prose in this host's surface, and it routes to paths instead of restating rules, so it cannot drift from the rules it points at.

The provider ranks below every local root rather than at the harness's bundled rank. The filesystem provider ranks project-dsh 100, project-agents 200, custom 300, user-dsh 400, and user-agents 500; at the bundled rank of 600 a leftover symlink in `~/.agents/skills` — which this README tells users to create — would win, and the model would receive the 28,661-character `SKILL.md` that the pruner then middle-elides. Measured on 0.2.0-rc.2 before the rank was lowered, and again after.

Each command registers a description and an argument hint carried over verbatim from its upstream `commands/<name>.md` frontmatter, and its handler steers the command body plus the user's arguments into the session as one user message. `$ARGUMENTS` is `CommandInvocation.rawInput` in DSH, and the Claude `allowed-tools` lists have no direct equivalent, so the bodies route to `references/` rather than restating the procedures.

## Consequences

- The skill surface stays single-sourced. `skills/diagram-design/` and `commands/` are untouched, and a host addition still never justifies copying either (ADR 0008).
- `SKILL.md` may grow toward its existing 40,000-byte cap without affecting the provider, because the provider never inlines it.
- The router budget is enforced by `node --test`, not by review. Because this repository's CI is Python-only, those tests have no CI job; the gap is stated in the pull request rather than left for a reader to discover.
- The six commands are registered but have never been dispatched in a live session, because no model route was available during development. `agent.steer()` from a command handler is the host's own `plan-mode` idiom, but this repository's first working experience of it failed with an inactive inbox projection. The failure paths return a command error rather than throwing; the happy path is untested.
- This repository has no written host-adapter contract — ADR 0008 is the closest thing — so a fifth host has no checklist to follow. This ADR records decisions, not obligations.
- `python3` must remain on `PATH` for DSH users: the import and export procedures run the packaged `scripts/*.py` helpers, unchanged from every other host.