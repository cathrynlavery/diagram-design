# Org Chart / Responsibility Map

**Best for:** human teams, agent teams, support escalation maps, role ownership, routing maps, and any hierarchy where the reader needs to know *who owns what* rather than just parent → child structure.

Use **Org Chart** instead of **Tree** when the nodes are people, agents, teams, roles, or accountable owners. A tree shows generic hierarchy. An org chart shows responsibility, invocation paths, and coverage gaps.

## Layout conventions
- Root owner or front door at top center. Use one coral focal node for the person/team/agent that receives ambiguous work.
- Tier 1 nodes are departments, pods, queues, or primary routing buckets. Keep them horizontally aligned.
- Tier 2 nodes are responsible owners or specialists. If there are more than 8 specialists, group them under pod nodes instead of making one giant row.
- Use orthogonal connectors: vertical drop from parent → horizontal bus → vertical drops to children. No diagonal lines.
- Each node should answer three questions when space allows:
  1. **Name** — human-readable role/person/agent in Geist sans.
  2. **How to invoke** — Slack handle, queue, issue prefix, or trigger in Geist Mono.
  3. **Scope** — 2–4 terse ownership words, not a paragraph.
- Show non-Slack / not-yet-live owners with dashed optional styling rather than hiding them. Missing routes are operationally important.
- Put escalation / approval rules in a small side callout or footer strip, not as extra org nodes.

## Node treatments
- **Front door / command center:** focal treatment (`accent-tint` + `accent`).
- **Team / pod / department:** backend treatment (white + `ink`).
- **Individual agent / owner:** store or external treatment depending on whether it is active in the system.
- **Gap / needs setup:** optional dashed treatment.
- **Approval gate:** security treatment, separate from reporting hierarchy.

## Complexity budget
- Max visible org nodes: 12. If more, create an overview org chart plus separate detail charts per pod.
- Max depth: 4 tiers.
- Max direct reports under one parent: 5. If there are more, introduce grouping nodes.
- Max coral nodes: 1. The org chart's job is clarity, not highlighting everything.
- Max side callouts: 2.

## Anti-patterns
- Using a swimlane when the user's real question is "who does what?" Swimlanes explain process; org charts explain ownership.
- Drawing every person/agent as an identical box. It hides the front door, specialists, gaps, and escalation paths.
- Cramming full job descriptions into nodes. Keep scope phrases short and move detail to summary cards below.
- Showing unavailable / not-yet-wired agents as normal active owners. Use dashed optional styling so gaps are visible.
- Repeating Slack handles in body paragraphs when a node sublabel can carry the invocation path.
- Floating legends in the org area. Use the standard bottom legend strip.

## Examples
- `assets/example-org-chart.html` — minimal light
- `assets/example-org-chart-dark.html` — minimal dark
- `assets/example-org-chart-full.html` — full editorial
