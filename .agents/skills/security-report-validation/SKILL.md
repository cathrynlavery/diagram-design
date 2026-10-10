---
name: security-report-validation
description: Validate a suspected Diagram Design security finding before reporting or patching it.
---

# Security report validation

Read and follow `SECURITY.md` and `THREAT_MODEL.md`. Use `CONTRIBUTING.md`,
`.maintainer-policy.json`, applicable ADRs, and current source as their own
sources of truth; do not restate them.

Before validating, check issues, PRs, commits, and available advisories. If the
candidate is a duplicate, record the existing item and stop. Otherwise reproduce
it on current `main` and show the attacker input, prerequisites, crossed
boundary, and concrete outcome with a minimal safe PoC. Test the relevant
existing defense, add an adversarial regression test where practical, and run
applicable validation gates from `.maintainer-policy.json`.

## Validation report

Keep the report concise and include:

- tested commit, version, harness, and platform;
- attacker input, prerequisites, user interaction, and crossed boundary;
- minimal reproduction, expected versus observed behavior, and concrete impact;
- defense tested, relevant gates, regression test, and mitigation if known.

Name unresolved assumptions; do not overstate the demonstrated impact.

Send suspected vulnerabilities only through the private route in `SECURITY.md`.
Do not disclose publicly, merge/release autonomously, or alter secrets,
credentials, permissions, or security policy without human approval. Narrow or
unsupported evidence is “needs more evidence,” not a confirmed finding.
