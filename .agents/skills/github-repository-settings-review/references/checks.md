# Repository settings security checks

Use read-only `GET` endpoints through `gh api`. If a command needs explicit API
versioning, use the current version documented by GitHub rather than copying a
stale fixed value from this skill.

All endpoints below target `cathrynlavery/diagram-design`.

## Fork pull requests and CI authority

- Read `repos/cathrynlavery/diagram-design/actions/permissions/fork-pr-contributor-approval` and
  require `approval_policy` to be `all_external_contributors`. Record that users
  with repository write access can approve runs.
- Read `repos/cathrynlavery/diagram-design/actions/permissions/workflow`; require
  `default_workflow_permissions` to be `read` and
  `can_approve_pull_request_reviews` to be `false`.
- Read `repos/cathrynlavery/diagram-design/actions/permissions`; require
  `sha_pinning_required` to be `true` (Require actions to be pinned to a
  full-length commit SHA).
- Read `repos/cathrynlavery/diagram-design/actions/permissions/access`; require
  `access_level` to be `none` (Not accessible — workflows in other repositories
  cannot access this repository).
- Read `repos/cathrynlavery/diagram-design/actions/runners` and require no
  self-hosted runners to be available to the repository.

## Privileged publication settings

- Read `repos/cathrynlavery/diagram-design/pages` and require its configured build/deployment source
  to be GitHub Actions.

## Auto-bump PAT permissions

Give the operator these instructions; the repository secret cannot reveal the
PAT's policy:

1. Identify the owner of `AUTO_BUMP_TOKEN` and have that owner open the token in
   GitHub Settings → Developer settings → Personal access tokens. Keep its value
   private.
2. Verify it is a fine-grained PAT whose repository access is limited to
   `cathrynlavery/diagram-design` and whose repository permissions are limited to
   Contents read and write. Confirm no organization or account permissions are
   granted.
3. Record the token owner, expiry, and rotation responsibility, then match its
   owner to the auto-bump identity permitted by the branch ruleset.

Mark unavailable evidence `manual confirmation required`. A classic PAT or a
fine-grained PAT with broader access fails this check.

## Branch protection rules

- List `repos/cathrynlavery/diagram-design/rulesets?includes_parents=true`, get
  each applicable ruleset, and require an active branch ruleset covering
  `refs/heads/main`.
- Require the ruleset to prevent force pushes and require pull requests with an
  approving review from a Code Owner.
- Require either dismissal of stale pull request approvals when new commits are
  pushed or approval of the most recent reviewable push.
- Require ruleset bypass access for only `cathrynlavery` and the owner of
  `AUTO_BUMP_TOKEN`, both with `bypass_mode: always`. This intentionally permits
  direct emergency owner pushes and direct auto-bump pushes. Fail unexpected or
  unidentified bypass access.
- Require legacy branch protection to be absent. A successful response from
  `repos/cathrynlavery/diagram-design/branches/main/protection` fails this check;
  the active ruleset is the single source of branch protection.

## Dependabot

- Check whether alerts are enabled with
  `repos/cathrynlavery/diagram-design/vulnerability-alerts` and whether Dependabot
  security updates are enabled and unpaused with
  `repos/cathrynlavery/diagram-design/automated-security-fixes`. Preserve HTTP
  status because not-found identifies some disabled states.
- Confirm that Insights → Dependency graph → Dependabot shows recent update runs,
  and record the most recent run's date and result.

## Result

Report the exact repository, authenticated account, tested default-branch commit,
and timestamp. For each section give the result, expected baseline, minimal
evidence, practical impact, and enforceable maintainer action. Keep admin-readable
settings and operator attestations out of committed files unless they are clearly
non-sensitive and the user asks to preserve them.
