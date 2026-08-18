# ADR 0006 — Client profiles use marker-first resolution

**Status:** accepted (v2.4)

## Context

Customizing an installed `style-guide.md` supports only one client, creates races between parallel projects, and can be erased by managed plugin updates.

## Decision

Named profiles are full style-guide snapshots in `~/.diagram-design/profiles/`, with one metadata header naming the active profile. An optional project-root `.diagram-design` marker selects a validated slug and reads that home profile directly; only an explicit markerless load copies a profile into the installed working file. Loads check the current semantic-role and typography schema and backfill missing rows from shipped defaults.

We rejected in-install profile storage because updates replace it, token-only override merging because agents would have to interpret a versioned merge format, a central path-to-profile index because paths differ across machines and moves, and copy-over-only selection because it preserves the parallel-workspace race.

## Consequences

Profiles survive updates and can be shared by Claude, Codex, and Pi installs. Marker projects are isolated from shared mutable state. Snapshot files are simple and inspectable, at the cost of a load-time schema check and an explicit re-save when new required rows appear.
