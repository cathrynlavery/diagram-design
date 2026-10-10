Run Diagram Design's environment diagnostics.

The installed skill directory is `{{SKILL_DIR}}`. `references/doctor.md` is the source of truth
for the checks, the output contract, and the safety rules. Do not reimplement its logic.

Defaults: no arguments means a full, read-only run. `--strict` and `--json` are described in
`references/doctor.md`.

Required behaviour

1. Apply the exact checks and output contract from `references/doctor.md`.
2. Keep the run read-only: do not install dependencies, do not edit files, do not run destructive
   git operations.
3. If a check command fails, capture its stderr, mark that check `warn` or `fail` as the reference
   specifies, and continue with the remaining checks.
4. Print the compact summary line and the per-check statuses. Include `Next actions` only when the
   reference calls for it.
5. With `--json`, append the structured JSON block the reference defines.

Report only results verified during this run. Never infer a check you did not execute.