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

**2026-09-10 — OMP (oh-my-pi) is a fourth native host, via the root `package.json`.** OMP installs Git sources as npm packages (bun installs the spec into the profile's `plugins/node_modules` and then reads `node_modules/<name>/package.json`), so unlike the Claude/Codex/Factory directory manifests its native metadata must live at the repository root. The root `package.json` repeats the shared identity fields verbatim and adds the two keys OMP's runtime needs: `private` (never an npm package) and an `omp` manifest object. The `omp` key is what makes OMP's enabled-plugin loader recognize the package at all — its loader skips packages without an `omp`/`pi` manifest — and it stays empty because OMP discovers capabilities by convention from the shared plugin root (`skills/`, `commands/`, `prompts/`), not from manifest entries. No fourth marketplace catalog was added: OMP reads the Claude Code-compatible `.claude-plugin/marketplace.json` as its fallback catalog, so the existing catalog serves both hosts. Package-gate coverage follows this ADR's existing rule — `package.json` joins `verify-plugin-package.py` and `bump-plugin-version.py` as the fourth synchronized manifest (the auto-bump workflow allowlists and `.maintainer-policy.json` with it), the bootstrap rule already permits it to be absent at the base ref while its metadata and version match the established manifests, and `verify-docs-sync.py` covers its short installation description alongside the other native manifests.
