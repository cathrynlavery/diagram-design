# ADR 0013 — DeepSeek Harness installs from the repository root with a routed skill body

**Status:** accepted (v2.6.51)

## Context

DeepSeek Harness is an Agent Skills host. It scans `<projectRoot>/.agents/skills` for a project and `<agentsHome>/skills` globally, and its discovery expects exactly the layout this repository already ships: `<root>/<name>/SKILL.md` with the reference files beside it. Those are two of the roots the README already documents for Cursor, Cline, and Codex. A symlink therefore worked before this decision, and the skill's frontmatter (`name: diagram-design` plus the full routing description) satisfies DSH's requirements without edits.

What a symlink does not provide is the install path every other native host has. Claude, Codex, and Factory each install through a manifest their host resolves; DSH would have no manifest, no version-gate coverage, and no release tracking, which is exactly what ADR 0008 asks a new host to supply.

One host constraint shapes the implementation. DSH's base bundle mounts `@deepseek-ai/dsh-compaction-tool-result-pruner` at `thresholdChars: 8192`, `headChars: 4096`, `tailChars: 1024`, and it rewrites `tool/result` events. The `skill` tool returns a tool result, and `skills/diagram-design/SKILL.md` is 29,706 bytes. A provider that inlined it would deliver the model the opening and closing sections with the middle marked as pruned, so the agent would draw from a partial specification while appearing to have the full skill. ADR 0004's own amendment already treats SKILL.md as a router over `references/`; that is the shape this decision adopts rather than fighting.

## Decision

DeepSeek Harness is a fourth native host. It receives `.dsh-plugin/plugin.json` carrying the same shared identity, description, version, author, repository, license, and keyword metadata as the three existing manifests, plus one DSH-only key recording its install command. The manifest joins `verify-plugin-package.py`, `bump-plugin-version.py`, the auto-bump allowlists, `.maintainer-policy.json`, the manifest-description checks, and the bootstrap fixtures, so its version is bumped and reviewed exactly like the others.

DSH installs from the repository root rather than a marketplace document, so it contributes a root to the shared-plugin-root check and no marketplace of its own. The root comparison resolves it against the repository the way `resolve_local_path` resolves the others; the rule ADR 0008 states now covers four hosts.

The host package registers one packaged skill provider over the repository's own `skills/diagram-design/` tree. Nothing in that tree is copied, translated, or patched. The description is parsed from the upstream `SKILL.md` at read time, and the skill directory is handed to DSH as the skill's `resourceBase`, so the model resolves `references/`, `assets/`, and `scripts/` against the installed files.

The body sent to the model is a compact router under 4,096 characters that names the sections and reference files to read on demand, rather than `SKILL.md` itself. That router is the only new prose in this host's surface, and it routes to paths instead of restating rules, so it cannot drift from the rules it points at. A test fails the build if the router exceeds its budget or names a path that is not packaged.

## Consequences

- The skill surface stays single-sourced. `skills/diagram-design/` is untouched, and a host addition still never justifies copying the skill or command surface (ADR 0008).
- `SKILL.md` may grow toward its existing 40,000-byte cap without affecting the provider, because the provider never inlines it.
- A future host that prunes tool results below the router's budget needs the same treatment, and the budget is now enforced by a test rather than by review.
- The plugin ships no tools, no commands, and no hooks. The six Claude slash commands are not ported here: their `allowed-tools` names and `$ARGUMENTS` grammar have no DSH equivalent in this repository's supported surface, and porting them is a separate proposal.
- This repository's CI is Python-only, and adding a Node job would fail `scripts/test-maintainer-policy.py`, which fails closed on any `run:` line it cannot map to a registered local gate. The host package's JavaScript therefore has no CI job. It is covered by `node --test` and reported in the pull request, and this gap is stated here rather than left for a reader to discover.
- `python3` must remain on `PATH` for DSH users: the import and export procedures run the packaged `scripts/*.py` helpers, unchanged from every other host.