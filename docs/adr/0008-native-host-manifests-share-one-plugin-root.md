# ADR 0008 — Native host manifests share one plugin root

**Status:** accepted (v2.5.14)

## Context

Diagram Design serves Claude Code, Codex, Pi, and Factory Droid. Factory can translate the Claude plugin layout, but relying on that fallback leaves Droid installation undocumented and outside the package-version gate. Copying the skill or commands into host-specific directories would create multiple sources of truth.

## Decision

Claude, Codex, and Factory each receive the smallest native manifest and marketplace metadata their host needs. Every marketplace resolves to the repository root, where all three hosts reuse `skills/diagram-design/` and `commands/` without duplication. Pi continues to use the same root package surfaces.

The three native plugin manifests carry identical shared identity, description, version, author, repository, license, and keyword metadata. The package verifier rejects drift, deletion, unsafe marketplace paths, or a version that does not advance from the base ref. A newly tracked native manifest may be absent at the base ref only during bootstrap: its current metadata and version must match the established manifests, and those established manifests must advance.

## Consequences

Each native host has an explicit install path while diagram behavior remains single-sourced. Adding another host requires native metadata, package-gate coverage, documentation, and a synchronized version bump; it never justifies copying the skill or command surface. Git-based Factory installs are updated by marketplace commit, while the synchronized manifest version remains release metadata and a review gate.

## Amendments

**2026-10-02: DeepSeek Harness joins as a fourth native host, and its metadata is not a `plugin.json`.** DSH removed the `.dsh-plugin` authoring format in commit `993550e6c8` (2026-08-09) with no compatibility parser retained, so there is no directory manifest to register and no marketplace document to resolve: DSH installs the repository root with `dsh plugin add` and reads the root `package.json`, whose `dsh.bundle.patch` points at `cordis.patch.yml`. It reuses `skills/diagram-design/` and `commands/` without duplication, and its description is checked against the `SKILL.md` selection table by `verify-docs-sync.py` alongside the three manifests. It therefore does not join the version-sync list in `.maintainer-policy.json` — that list describes manifest files that `bump-plugin-version.py` advances together, and a `package.json` version is not release metadata for this repository. ADR 0013 records the host, the routed skill body, and the provider rank.

**2026-10-02: the Consequences paragraph above says "a synchronized version bump" as a requirement for a new host.** DSH is the exception: `package.json` carries the same version string as the three manifests today, but the auto-bump workflow does not touch it, and the repository is not published to npm.
