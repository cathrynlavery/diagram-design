# Environment doctor

Load this file when the user asks to run diagnostics, health checks, or first-run troubleshooting, or when they invoke `/diagram-design:doctor` or `/doctor`.

The goal is a one-shot report that checks local readiness for Diagram Design import/export and command routing, without mutating user files or installing dependencies.

Resolve the Diagram Design installation from this loaded reference, not from the
user's current working directory. A normal project directory is the expected
place to invoke the doctor and must not be treated as a repository-path error.

Use two diagnostic modes:

- **Installed-skill mode** (default): check the runtime and the resolved skill
  installation. Do not require maintainer-only repository files. This mode
  still runs every host-aware check below — install-channel detection,
  marketplace version alignment, Pi pinning, and the Cowork mirror check all
  diagnose installed skills, not just maintainer checkouts.
- **Maintainer-checkout mode**: use this only when the resolved installation
  root contains `CONTRIBUTING.md`, `.github/workflows/ci.yml`, and
  `scripts/verify-plugin-package.py`. Add the repository integrity checks below.

## Inputs

Optional flags:

- `--strict` — treat warnings as failures in the final summary.
- `--json` — print a machine-readable JSON report in addition to human summary.
- `--host <claude-code|cowork|codex|cursor|pi|auto>` — select the host profile
  the diagnostics target. Default is `auto`.

If no flags are provided, run in standard mode with `--host auto`.

## Host profile resolution

When `--host` is `auto` (or absent), resolve the host profile best-effort and
say so in the report:

1. Environment markers first, checking Cowork before Claude Code because a
   Cowork session can also carry Claude Code markers: `COWORK_SESSION_ID` /
   `CLAUDE_COWORK_SESSION` → `cowork`; `CLAUDECODE` / `CLAUDE_CODE_ENTRYPOINT`
   → `claude-code`; `CURSOR_AGENT` / `CURSOR_TRACE_ID` → `cursor`;
   `CODEX_HOME` / `CODEX_SANDBOX` → `codex`; `PI_SESSION_ID` / `PI_HOME` → `pi`.
2. Then installation-path hints: a path segment containing `cowork`, `.claude`,
   `.codex`, `.cursor`, or `.pi` selects the matching profile.
3. Otherwise report the host as `unknown` and suggest passing `--host`.

An explicit `--host` value always wins over detection.

## Install channel resolution

Classify how the resolved installation arrived, and report the evidence:

- `maintainer-checkout` — all maintainer markers above are present.
- `git` — `.git` metadata exists at the installation root (editable installs,
  `pi install <git-url>` checkouts).
- `marketplace` — the installation path contains a marketplace cache segment
  (`plugins`, `plugin-cache`, `marketplace`, `marketplaces`).
- `copied` — none of the above (agent-installed or hand-copied skill
  directories).

## Required checks

Run all checks in this order and report each as `pass`, `warn`, or `fail`.

1. Python runtime
- Resolve `python3` first, then `python`. A name that is on PATH but cannot report
  its own version does not win the resolution: fall through to the next candidate.
  (Windows ships a `python3` App Execution Alias that is a Microsoft Store stub, not
  an interpreter, and it sits on PATH ahead of a python.org install.) A name that
  cannot be launched at all counts as the same kind of dud, and is reported as a
  failed check rather than ending the run.
- Require version >= 3.10.
- `fail` if no Python interpreter is found.
- `fail` if version is below 3.10.

2. Playwright availability for PNG export
- Check whether Playwright import works in the active Python interpreter (`import playwright`).
- Check whether Chromium is installed for Playwright (`playwright install --help` availability is sufficient for command presence; prefer also checking browser cache when practical).
- If missing, mark `warn` and print exact setup hint:
  - `pip install playwright && playwright install chromium`
- Append the host-specific hint for the resolved profile, in parentheses after
  the command, so silent PNG failures get a one-shot fix:
  - `claude-code` — run it in the Python environment Claude Code invokes, then `/reload-plugins`.
  - `cowork` — install inside the Cowork session environment; sandboxed sessions do not see host-machine packages.
  - `codex` — run it in the Codex workspace environment, then start a new session.
  - `cursor` — run it in the Cursor agent terminal so the interpreter matches the export interpreter.
  - `pi` — run it in the interpreter Pi uses, then `/reload`.
- When the install channel is `marketplace`, also advise restarting the session
  so the host reloads the plugin environment.
- Never auto-install dependencies.

3. Host profile and install channel
- Report the resolved host profile and install channel with their evidence.
- Print the matching update/reinstall recipe (all cited from the README Install
  section):
  - `marketplace` + `claude-code` — enable auto-update via `/plugin` →
    **Marketplaces** → **diagram-design**, run `/reload-plugins` when prompted;
    reinstall with `/plugin install diagram-design@diagram-design`.
  - `marketplace` + `codex` — `codex plugin marketplace upgrade diagram-design`,
    then start a new session.
  - `marketplace` + `cowork` — updates sync from the organization's private
    mirror when a plugin version-bump PR merges to its default branch.
  - `git` + `pi` — `pi update --extensions`, then `/reload` in an open session.
  - `git` (other hosts) — `git pull` in the checkout, then reload the skill.
  - `copied` — replace the copied `skills/diagram-design` directory from a
    newer checkout (for `cursor`, re-running the agent install also works).
  - `maintainer-checkout` — `git pull` and re-run the CONTRIBUTING gates.
- This check is informational (`pass`); it exists so warn/fail checks can
  reference a concrete recipe.

4. Expected script presence (maintainer-checkout mode only)
- Verify these repository scripts exist:
  - `scripts/verify-drawio-import.py`
  - `scripts/verify-mermaid-import.py`
  - `scripts/verify-excalidraw-import.py`
  - `scripts/verify-motion.py`
  - `scripts/lint-skin.py`
  - `scripts/verify-docs-sync.py`
- Missing scripts are `fail` in maintainer-checkout mode.
- In installed-skill mode, report that maintainer scripts are not applicable;
  their absence is not a warning or failure.

5. Plugin wiring surfaces (maintainer-checkout mode only)
- Verify Claude command files exist and point to their references:
  - `commands/export-diagram.md` -> `references/export.md`
  - `commands/import-drawio.md` -> `references/import-drawio.md`
  - `commands/import-mermaid.md` -> `references/import-mermaid.md`
  - `commands/import-excalidraw.md` -> `references/import-excalidraw.md`
  - `commands/profile.md` -> `references/profiles.md`
  - `commands/doctor.md` -> `references/doctor.md`
- Verify Pi prompt files exist and point to their references:
  - `prompts/export-diagram.md` -> `references/export.md`
  - `prompts/import-mermaid.md` -> `references/import-mermaid.md`
  - `prompts/import-excalidraw.md` -> `references/import-excalidraw.md`
  - `prompts/profile.md` -> `references/profiles.md`
  - `prompts/doctor.md` -> `references/doctor.md`
- Missing files are `fail`.
- Mismatched reference routing is `fail`.
- In installed-skill mode, report that maintainer command/prompt wiring is not
  applicable; partial or absent repository routing trees are not failures.

6. Marketplace plugin version alignment (installed-skill mode included)
- Only applicable when the install channel is `marketplace`; otherwise report
  `pass` with a not-applicable message.
- Read `metadata.version` from the resolved `SKILL.md` and advise confirming
  the active plugin version the host reports (for example `/plugin` in Claude
  Code) matches it before debugging stale-behavior reports — marketplace
  auto-update can lag until the session reloads.
- `warn` when `metadata.version` cannot be read, with the reinstall recipe as
  the fix.

7. Pi install pinning (installed-skill mode included)
- Only applicable when the host profile is `pi` and the install channel is
  `git`; otherwise report `pass` with a not-applicable message.
- Read `.git/HEAD` (read-only). A `ref: refs/heads/<branch>` head means the
  install tracks an unpinned branch: `warn` that `pi update --extensions`
  moves it to whatever that branch points at, and suggest pinning to a release
  tag or commit before `pi install` (or reviewing upstream changes before
  updating).
- A detached tag or commit head is `pass` (pinned).

8. Cowork organization mirror (installed-skill mode included)
- Only applicable when the host profile is `cowork`; otherwise report `pass`
  with a not-applicable message.
- If the resolved `SKILL.md` is missing, mark `fail`: Cowork organization
  marketplaces require a private or internal mirror of this public repository,
  and skill resolution fails after install without one. The fix cites the
  documented mirror steps (README: Install → Claude Cowork): mirror the public
  repository into an organization-owned private/internal repository, add it via
  **Organization settings → Plugins → Add plugin → GitHub**, enable **Sync
  automatically**, and install from the resulting organization marketplace.
- If `.git/config` shows a remote pointing directly at the public
  `cathrynlavery/diagram-design` repository, mark `warn` with the same mirror
  fix — updates will not sync through Cowork from the public remote.

9. Common path mistakes
- Verify `SKILL.md` beneath the resolved installation root. Do not search for it
  relative to the user's current project and do not instruct users to enter the
  maintainer repository.
- Detect Windows path quoting risk when paths contain spaces and the provided command examples omit quotes.
- Detect references to local installed skill paths that do not exist (if command output includes one).
- Mark these as `warn` with a precise fix suggestion.
- A missing resolved `SKILL.md` should suggest reinstalling or updating Diagram
  Design, not changing into a repository checkout, and should append the
  update/reinstall recipe for the resolved host and install channel so a
  "skill not found" failure after a marketplace install gets a one-shot fix.

## Output contract

Always print:

1. A compact summary line:
- `Doctor summary: <PASS|WARN|FAIL> (<pass_count> pass, <warn_count> warn, <fail_count> fail)`

2. A checklist with one line per check:
- `[PASS] Python 3.11.9 found at ...`
- `[WARN] Playwright not installed ...`
- `[FAIL] Missing scripts/verify-docs-sync.py`

3. A `Next actions` section only when warn/fail exists.

4. If `--json` is present, append JSON object with:
- `status`, `counts`, `checks[]` (`name`, `status`, `message`, `fix` optional), `timestamp`, `host`, `install_channel`.

## Safety and behavior rules

- Read-only diagnostics only: do not modify files, do not install packages, do not run destructive git commands.
- If any command fails unexpectedly, capture stderr and continue remaining checks.
- Never claim a check passed unless verified directly in this run.
- Prefer explicit, copy-pastable remediation commands.

## Example result

```text
Doctor summary: WARN (8 pass, 1 warn, 0 fail)
[PASS] Python 3.11.9 found at /usr/bin/python3
[WARN] Playwright package not found in active interpreter
[PASS] Host profile: claude-code (environment variable CLAUDECODE is set). Install channel: marketplace (...)
[PASS] Installed SKILL.md metadata.version is 2.6. Confirm the active plugin version your host reports ...
...

Next actions
- pip install playwright && playwright install chromium (Run it in the same Python environment Claude Code invokes, then run /reload-plugins so the session picks it up. If PNG export still fails after a marketplace install, restart the session so the host reloads the plugin environment.)
- Re-run: /diagram-design:doctor --strict
```
