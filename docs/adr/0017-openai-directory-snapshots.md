# ADR 0017: Prepare weekly OpenAI directory snapshots for manual publication

**Status:** proposed, awaiting Cathryn's approval before implementation

## Evidence and remaining uncertainty

Checked 2026-11-03 against main commit `3eb03b8d2984e47ddd9b083db9abdcdaa3c69635`:

- The public MIT repository has four synchronized manifests at `2.6.139`, 45 type references, and a Codex interface with category `Creativity`, developer `LittleMight`, a purpose-first long description, and the GitHub main privacy URL. The short description is count-free; the long description says 45. No screenshots are declared, only a logo and composer icon.
- The ZIP builder reads the git index, derives root `plugin.json` with `extensions["com.openai"].interface`, and writes regular-file type bits and directory entries. PR [265](https://github.com/cathrynlavery/diagram-design/pull/265) records the upload fix. Current ZIP tests pass all 64 cases. [Main CI](https://github.com/cathrynlavery/diagram-design/actions/runs/41567998142) passed those same cases, including actual repository draft builds and archive inspection. Packaging already has a CI gate.
- ADR 0009 and `auto-bump.yml` increment versions after merges, sometimes coalescing merges. Minor and major labels select larger increments. Version changes remain forbidden in PRs.
- The October 1 submission, approval, current live version, and LittleMight verification are maintainer-reported, **unverified** in the dashboard. Do not initialize a confirmed submission record from the notes or assume a historical commit equals the uploaded ZIP. Repository history corroborates the category corrections, not OpenAI's approval.

OpenAI's current [submission guide](https://developers.openai.com/plugins/deploy/submission) requires a new ZIP and review for metadata, assets, and skills. Approval is followed by a separate human Publish action; publication replaces the prior package. Only one review can be active. Inference: the prior published package stays live during review; this account's behavior remains **unverified** pending dashboard evidence. The uploaded package is the directory snapshot; a repository URL does not make its bundled skills follow main. The linked privacy page can change independently, while the ZIP's copy stays frozen.

No supported public submission API, CLI, webhook, or public-directory Git sync was found in the submission guide, [package and Codex marketplace commands](https://developers.openai.com/plugins/build/plugins), or [API/CLI reference](https://developers.openai.com/api/reference/cli). This is a documentation finding, not proof that private endpoints do not exist. [GitHub synchronization](https://learn.chatgpt.com/docs/enterprise/plugin-management) serves managed workspace plugins, a separate channel. Design for human web upload. Never automate private dashboard endpoints or use OpenAI credentials.

Before implementation, inspect screenshots of the LittleMight plugin's published version/status and update controls. If available, Cathryn can download the published release ZIP to establish its exact contents. No upload or submission is needed for this verification.

## Options

| Trigger | Benefit | Cost |
| --- | --- | --- |
| Every patch or minor bump | Simple version rule | Patches flood review; minor labels miss types and listing changes |
| Every interface, privacy, or new-type change | Fast response to visible drift | Several merges can cause several redundant reviews; other skill fixes are missed |
| Weekly, only when packaged content changed | Batches review work and catches skill-only fixes | Routine directory content can lag a week plus review time |
| Manual snapshot only | Complete control | Cathryn must remember to check drift |

## Recommendation

Use a weekly changed-content snapshot, with a manual Actions dispatch for the first catch-up or an urgent correction. Interface, privacy, type, and asset changes appear as reasons in its report, not independent submissions. Security or materially inaccurate privacy claims require immediate human triage rather than waiting for the weekly run. Nothing submits or publishes to OpenAI.

After approval, implement the following small extension of existing tooling:

1. Pin one versioned main commit after its auto-bump and successful applicable CI. Never package an intervening merge under an already submitted version. Skip or defer a pending bump or failed CI. Build from a clean checkout whose index matches that commit. A later main change does not alter a prepared snapshot.
2. Compare the actual package payload with the last submitted snapshot, ignoring only synchronized version metadata and ZIP container metadata. Include all bundled skill files, root listing fields and keywords, interface fields, declared asset bytes, licenses, and privacy text. Skip version-only and repository-tooling-only changes. Report drift from both last submitted and last published snapshots. Suppress duplicates by source commit and content digest. While a review is recorded active, report accumulated drift without creating another upload candidate; resume after Cathryn records its outcome. Never cancel a review automatically.
3. Run the existing builder's `--check`, then a strict build without `--draft`. Inspect the resulting archive using the existing structure checks. Store the ZIP, SHA-256, source commit, version, complete file hashes, field-by-field listing diff, type additions/removals, privacy diff, and upload checklist in one Actions artifact with explicit 90-day retention. The Actions summary is the ready notice. Expired artifacts require explicit recreation from the same pinned commit; never silently substitute current main.
4. Keep a small checked-in JSON submission ledger, updated through a generated PR after Cathryn explicitly records an event with a manual workflow. Preserve prepared, submitted, rejected/cancelled, approved, and published states separately. Record exact version, source SHA, ZIP digest, timestamps, public listing URL when known, and evidence reference. Building never advances submitted or published state. A rejected submission remains in history and never advances the published baseline. Initial unknown fields stay null until confirmed from dashboard evidence or the original archive. The first diff must say baseline unknown when applicable.
5. Avoid a notification service, new credentials, and automatic issues/comments. A ready snapshot is discoverable in Actions; there is no proactive inbox notice in this first version. An issue or external notice requires Cathryn's approval of that specific message. This accepts one weekly Actions check to keep the permission boundary and implementation small.

## Drift gates and scope

Extend `verify-docs-sync.py` and its adversarial tests so numeral type counts in decoded `interface.longDescription` and `shortDescription`, when present, equal the existing shipped-type count. Reuse its type-name and alias checks. A count-free short description remains valid. Keep four-host description/keyword equality in `verify-plugin-package.py`; do not create another manifest synchronizer or require every type as a keyword.

Extend the ZIP tests and existing package CI job to require a strict real-repository build as well as the existing draft and adversarial cases. Retain format, index-content, asset, and reproducibility checks. Add any snapshot/ledger helper tests and commands to the same CI job, `.maintainer-policy.json`, and CONTRIBUTING gate list. Test unchanged payloads, version-only changes, listing/skill/privacy/image changes, unknown baselines, duplicate runs, active review, rejection, publication, stale CI, and expired artifacts. No new dependency or version bump is needed.

Keywords can remain mutually equal while becoming incomplete; semantic relevance needs human review of the diff. Existing screenshot freshness gates cover README images, not directory screenshots. If directory screenshots are later declared, track their paths and bytes and review their relevance in the checklist. The live dashboard may have older screenshots or other fields absent from source, so bootstrap must inspect the published ZIP and dashboard. Privacy content can change behind an unchanged URL, so compare both the URL and policy file.

## Cathryn's recurring work

1. Check the weekly Actions summary and download the ready artifact. Review the diff and checklist. Confirm LittleMight, the existing plugin, exact version, category, publisher, policy URL, and images.
2. Upload the complete ZIP, resolve automated findings, complete review materials/attestations, and submit. Record the submitted snapshot through the manual ledger workflow and review its generated PR.
3. After approval, select Publish for that version, exercise the live listing and a representative diagram, then record publication through the same ledger workflow. Record rejection or cancellation instead when applicable.

Budget 5 to 10 minutes for a clean upload/submission and 3 to 5 minutes after approval for publication, verification, and recording. These are planning estimates, **unverified** against this dashboard; scan/review waits and corrections are additional. One initial dashboard inspection and baseline confirmation are also required. No automatic merge, submission, or publication is authorized by this ADR.
