---
description: Run one-shot environment diagnostics for Diagram Design readiness
argument-hint: "[--strict] [--json] [--host claude-code|cowork|codex|cursor|pi|auto]"
---

Run environment diagnostics for Diagram Design. Locate the available `diagram-design` skill using its `SKILL.md` path advertised by Pi. Read that `SKILL.md`, then read `references/doctor.md` relative to its directory. Treat that reference as the source of truth. Do not assume the package lives under the current working directory.

Full argument string: `$ARGUMENTS`

## Required behavior

1. Run the exact checks and output contract defined in `references/doctor.md`, including host-profile and install-channel resolution (`--host`, default `auto`; under Pi prefer `--host pi` when detection is ambiguous) and the host-specific checks for marketplace version alignment, Pi install pinning, and the Cowork organization mirror.
2. Keep diagnostics read-only: do not install dependencies, do not edit files, and do not run destructive git commands.
3. If a check command fails, capture stderr, classify as `warn` or `fail` per the reference, and continue remaining checks.
4. Print the summary line plus per-check statuses, and include `Next actions` only when warn/fail exists.
5. If `--json` is passed, append the structured JSON object defined by the reference.

Report only verified results from this run.
