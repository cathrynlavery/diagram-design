---
name: github-repository-settings-review
description: Help a repository administrator validate the security of this project's GitHub settings with the gh CLI. Use for maintainer configuration audits; do not use for source-code vulnerability review.
---

# GitHub repository settings review

Audit this project's repository settings through authenticated, read-only `gh`
commands. Read [references/checks.md](references/checks.md) for the checks and
expected baseline.

## Admin preflight

Resolve the target only from `git remote get-url upstream`, then use `gh repo
view "$upstream_url" --json nameWithOwner,viewerPermission` to verify that it is
`cathrynlavery/diagram-design`. Stop if it does not match. Run `gh auth status` and continue only when
`viewerPermission` is `ADMIN`.

If any check fails, report the authenticated account, target, observed permission,
and missing token permission, then stop. Do not produce settings conclusions or
recommendations from incomplete public data.

## Review behavior

Gather each checklist item independently; a failed optional endpoint must not
discard evidence already collected. Use `--paginate` where a list could exceed
one page. Account for inherited settings and scope when deciding whether a
control is effective.

Record the repository, timestamp, API endpoint or `gh` command, relevant returned
fields, and any access limitation for each check. Treat unavailable organization policy, inherited
rulesets, and permission-redacted fields as unknown rather than passing. Use
`pass`, `fail`, `manual confirmation required`, or `unknown` for each result.

Keep inspection separate from remediation. Do not make changes unless the
operator explicitly asks. Redact secret values and sensitive identifiers from
evidence.
