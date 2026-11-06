---
description: Run one-shot environment diagnostics for Diagram Design readiness
argument-hint: "[--strict] [--json] [--host claude-code|cowork|codex|cursor|pi|auto]"
allowed-tools:
  - Read
  - Bash
  - Glob
---

Run environment diagnostics for Diagram Design by following [`skills/diagram-design/references/doctor.md`](../skills/diagram-design/references/doctor.md). Treat that reference as the source of truth and do not reimplement its logic here.

Full argument string: `$ARGUMENTS`

## Required behavior

1. Locate and apply the exact checks and output contract from `references/doctor.md`, including host-profile and install-channel resolution (`--host`, default `auto`) and the host-specific checks for marketplace version alignment, Pi pinning, and the Cowork organization mirror.
2. Keep this command read-only: do not install dependencies, do not edit files, and do not run destructive git operations.
3. If a check command fails, capture stderr, mark the check `warn` or `fail` per the reference, and continue remaining checks.
4. Print the compact summary line plus per-check statuses, and include `Next actions` only when needed.
5. If `--json` is passed, append the structured JSON block defined by the reference.

Report only verified results from this run.
