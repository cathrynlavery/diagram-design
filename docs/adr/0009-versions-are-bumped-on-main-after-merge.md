# ADR 0009 — Versions are bumped on main after merge, never in a pull request

**Status:** accepted (v2.6.12)

## Context

Every pull request used to be required to increment the synchronized Claude, Codex, and Factory manifest versions before merge. Because all open branches edited the same three version lines, every merge to `main` instantly put every other open PR into merge conflict; with ~17 community PRs open, a single squash-merge forced seventeen rebase-and-rebump rounds, and the next merge invalidated them all again. The bump requirement served release integrity — installs resolve from `main`, so each new tip needs a version greater than the last — but serialized all contribution on three shared lines.

## Decision

Pull requests must leave the three manifest versions untouched; `verify-plugin-package.py --require-no-bump` enforces this in CI on every PR. After each push to `main`, the Auto Version Bump workflow (`.github/workflows/auto-bump.yml`) runs `scripts/bump-plugin-version.py`, verifies the result with the classic increase gate against the pre-bump commit, and prepares an allowlisted patch. A separate publisher independently verifies that patch before pushing the bump commit directly to `main`. A `release:minor` or `release:major` label on any merged PR since the previous bump selects the strongest required bump size; the default is a patch. The bump tool also rewrites SKILL.md's `metadata.version` to the new MAJOR.MINOR in the same step, so the two never drift.

Rapid consecutive merges may coalesce into a single bump: a queued workflow run superseded by a newer push bumps once for every merge since the previous bump and preserves the strongest release label in that range. If `main` advances after a bump is prepared, the publisher declines to push so the newer queued run can recompute from the new tip. Versions still strictly increase at every bump commit, which is the only property installs and the marketplaces depend on. The workflow skips itself when the tip of `main` already carries a manifest version change, so manual maintainer bumps and the workflow's own commits never trigger a second bump.

## Consequences

Open PRs no longer conflict with each other through the manifests; they conflict only when they genuinely touch the same content. Contributors never run the bump helper, and a PR that edits a manifest version fails CI with instructions to drop the change. Release numbering moves from one-version-per-PR to one-version-per-bump-commit, and a version may cover more than one merged PR. The workflow pushes past branch protection's required status checks, so its final push needs a token from an actor the protection exempts. Newly merged repository code runs in an unprivileged job that never receives that token; the publisher introduces it only for the final `git push`, after independently constraining the patch to the synchronized version fields and SKILL.md metadata. All third-party actions are pinned to immutable commits. The bump commit is also validated by CI's current-tree check on push.
