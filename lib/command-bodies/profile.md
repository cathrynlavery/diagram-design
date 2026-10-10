Manage Diagram Design client profiles.

The installed skill directory is `{{SKILL_DIR}}`. `references/profiles.md` is the source of truth
for storage, strict slug validation, metadata, marker-first resolution, the current-schema
structural check, every verb procedure, and the failure and recovery cases. Do not reimplement or
relax its rules.

Resolve every `references/…` path below against the skill directory above.

Routing

- No arguments → `list`, with the active project-marker or working-copy profile marked.
- A bare `<name>` with no verb → `load <name>`.
- `switch <name>` → synonym for `load <name>`, even though `switch` is omitted from the short
  argument hint.
- `save [name]`, `load [name]`, `list`, `show`, `update [name]`, `reset`, `delete [name]` → run that
  exact procedure from the reference.
- A missing required name → list when useful, then ask. Never invent a slug.
- An unknown verb or an extra argument → show the accepted forms and stop without writing.

Required behaviour

1. Resolve the current installed skill directory before reading its working
   `references/style-guide.md`. Do not assume the repository checkout is the active install.
2. Treat `.diagram-design` as untrusted data. Accept only the exact marker grammar and canonical
   home profile path the reference describes.
3. Confirm before overwriting an existing profile, changing a project marker, or deleting a
   profile. Never skip the confirmation because the command was invoked from a script.
4. For a marker-selected project, read the profile directly and leave the installed working copy
   unchanged.
5. For a copy-over load, verify the destination after writing. If it is unwritable, offer the
   marker-based flow.
6. After save or update, verify exactly one profile metadata header and an unchanged body.

Report the active profile and the canonical file or marker you affected. Never claim a write
succeeded without re-reading it.