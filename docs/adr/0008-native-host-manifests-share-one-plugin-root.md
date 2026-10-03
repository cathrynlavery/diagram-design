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

**2026-10-02: DeepSeek Harness joins as a fourth native manifest.** DSH is registered through `.dsh-plugin/plugin.json` alongside the three existing manifests, resolves the repository root like the others, and reuses `skills/diagram-design/` and `commands/` without duplication. Its install is `dsh plugin add`, not a marketplace document, so it contributes a root to the shared-plugin-root rule and no marketplace file. Its version is bumped and reviewed by the same gates as the others. ADR 0013 records why the host was added, and why its skill body is routed to a read instead of inlined.
