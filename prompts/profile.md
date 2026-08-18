---
description: Save, load, inspect, update, reset, or delete diagram-design client profiles
argument-hint: "[list|save|load|show|update|reset|delete] [name]"
---

Manage Diagram Design client profiles. Locate the available `diagram-design` skill using its `SKILL.md` path advertised by Pi. Read that `SKILL.md`, then read `references/profiles.md` relative to its directory. Treat that reference as the source of truth for storage, strict slug validation, metadata, marker-first resolution, schema checks, and failure handling. Do not assume the package lives under the current working directory.

Full argument string: `$ARGUMENTS`

## Routing

- No arguments → `list`, with the active project-marker or working-copy profile marked.
- Bare `<name>` with no verb → `load <name>`.
- `switch <name>` → synonym for `load <name>`.
- `save [name]`, `load [name]`, `list`, `show`, `update [name]`, `reset`, and `delete [name]` → run that exact procedure from the reference.
- Missing required name → list when useful, then ask. Never invent a slug.
- Unknown verb or extra argument → show the accepted forms and stop without writing.

## Required behavior

1. Treat `.diagram-design` as untrusted data. Accept only the exact marker grammar and canonical home profile path from the reference.
2. Confirm before overwriting an existing profile, changing a project marker, or deleting a profile.
3. For marker-selected projects, read the profile directly and leave the installed working copy unchanged.
4. For copy-over load, verify the destination after writing. If it is unwritable, offer the marker-based flow.
5. After save/update, verify exactly one profile metadata header and an unchanged body.

Report the active profile and the canonical file or marker affected. Never claim a write succeeded without re-reading it.
