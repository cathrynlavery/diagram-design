# Threat Model

Diagram Design is a skill for coding agents. The agent reads its instructions
alongside the user's request and relevant project, diagram, or website content,
then chooses which local files and tools to use. Those tools parse imports,
write diagrams and profiles, and may fetch a user-selected website or run a
browser for PNG export.

Filesystem, process, and network restrictions depend on the agentic harness.
Diagram Design does not provide a sandbox, cannot protect an already-compromised
harness, and cannot narrow permissions that the operator intentionally grants.

The current working directory is assumed to be trusted when diagram generation 
begins.

## Security expectations

### Import and output pipeline

- The agent does not interpret supported diagram files directly. It works from
  the representation produced by the deterministic format extractor.
- To reduce indirect prompt-injection risk during intermediate steps, the agent
  sees only the strictly required extracted fields rather than the raw source;
  extractors normalize and bound those values and discard links, directives,
  styling, and other executable or irrelevant metadata.
- Deterministic tools treat fields as data: they do not execute, render, or
  fetch embedded content, and they resist injection and unintended file access.
- Input, decompression, features, and output limits bound resource use.
- A failure of these limits that causes only denial of service or resource
  exhaustion is an ordinary reliability defect, not a security issue. Submit
  availability-only fixes directly through the pull request process.
- Untrusted source content handled by an `/import-*` command cannot introduce
  active content into its output. `/export-diagram` likewise treats its input
  as untrusted: it does not execute source-controlled behavior, and exported
  artifacts retain no source-controlled scripts, event handlers, executable
  URLs, unsafe CSS, or external resources.
- Generated files are static by default. Validation rejects JavaScript URLs,
  event handlers, unsafe CSS, and unapproved external resources. Animated
  diagrams may include only the repository's canonical motion script;
  validation rejects modified, additional, or remote scripts.

### Skill distribution, CI, and integrations

- Packaging stops instead of publishing when a manifest, package path,
  symlink, or required file is invalid to prevent malformed metadata from
  silently changing which files reach users.
- GitHub Actions workflows and their dependencies pass the zizmor security
  audit enforced in CI.
- Only maintainer-reviewed changes from `main` reach plugin users or the
  gallery. Merging, disclosure, and release-sensitive changes remain human
  decisions.
