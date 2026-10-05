# Security Policy

## Supported versions

Of published plugin versions, only the latest minor release line receives
security support. Security fixes are developed against the latest commit
on the `main` branch, and reports should reproduce there.

## What to report

A useful report shows how an attacker can get past an importer limit, make
generated output behave unexpectedly in a browser (e.g., include
attacker-controlled HTML and JavaScript code), or provoke unintended network
and filesystem access. We are also interested in CI vulnerabilities that
could let an attacker compromise the plugin distribution supply chain. More
details are in the [threat model](THREAT_MODEL.md).

Bugs causing cosmetic output defects, fork-specific changes, or behavior that
requires intended maintainer authority are not considered vulnerabilities.

## Private reporting of vulnerabilities

Please use [GitHub private vulnerability reporting](https://github.com/cathrynlavery/diagram-design/security/advisories/new).
Do not disclose a suspected vulnerability in a public issue, pull request,
discussion, or social-media post before we have coordinated disclosure.

Include as much of the following as you can:

- the affected file, script, or workflow;
- the attacker-controlled input, prerequisites, and crossed trust
  boundary;
- a description of the impact and who could be affected;
- clear reproduction steps or a minimal proof of concept;
- a suggested mitigation, if you have one.

Agents validating a candidate report in a repository checkout must use the
[security report validation skill](.agents/skills/security-report-validation/SKILL.md).

Avoid including secrets, credentials, or personal data in the report.

## What to expect

We will acknowledge the report as soon as practical, validate the finding,
determine its scope, and coordinate remediation and disclosure with the
reporter. Please allow time for a fix to be developed and tested before public
disclosure.

## Good-faith research

Please avoid accessing, modifying, or deleting data that does not belong to
you, disrupting services, or degrading other users' experience. If testing
could affect other people or systems, stop and submit a private report first.

Do not use social engineering or attempt to compromise maintainer accounts.

Thank you for helping keep Diagram Design and its users safe.
