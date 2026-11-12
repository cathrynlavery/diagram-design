# ADR 0016: Merges need a same-head Greptile score of 4 or 5

**Status:** accepted

## Context

Greptile reviews pull requests here and posts a confidence score out of 5. The maintainer policy (`.maintainer-policy.json`) listed no review provider, so nothing stopped a merge on a score Greptile had given to an earlier commit of the branch, or on no score at all. Several recent merges landed on a 4/5 that predated the final commits, so those commits reached `main` without a review.

## Decision

`gates.review` in `.maintainer-policy.json` names `greptile` as the provider, with a minimum score of `4` and `require_same_head: true`. A pull request merges only when Greptile has scored its current head at 4 or 5. The existing gates still apply: an up-to-date base, no conflicts, resolved conversations, no requested changes, the complete local suite, and green CI on that same head.

Any new commit needs a fresh Greptile review before merge. That includes a merge of `main` made only to satisfy branch protection's up-to-date rule. An open Greptile thread blocks merge at any score, because conversations must be resolved.

## Consequences

Updating a branch from `main` adds one Greptile round before merge. A 4/5 is enough to merge, and a 5/5 is not required. Greptile is one gate among several and does not replace the local suite or CI.
