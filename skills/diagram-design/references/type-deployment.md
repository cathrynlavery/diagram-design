# Deployment

**Best for:** where the software actually *runs* — hosts, VMs, pods, and managed services placed inside environment or network-boundary zones, with replica counts and versioned artifacts called out. Architecture answers "what talks to what"; deployment answers "what is installed on which host, in which environment, behind which network boundary, at how many replicas." If the diagram has no physical-placement decision to show — no zone boundary, no replica count, no version that matters — use `type-architecture.md` instead; redrawing the logical architecture with hostnames bolted on is the most common deployment anti-pattern.

## Layout conventions

Three nesting levels, outermost to innermost — reuses the containment grammar from `type-nested.md`, specialized for infrastructure:

1. **Zone** — an environment or network boundary (`edge`, `prod / eu-west-1`, `data`). A large rect, `rx=8`, fill `ink @ 0.02`, stroke `ink @ 0.20` dashed `4,4`. A Geist Mono 8px (or 7px for tight layouts) uppercase tracked eyebrow label sits inside the top-left corner, on a paper-colored mask over the border. Zones are drawn **first** — before arrows and nodes — so labels and boxes paint over them (z-order: bg → zones → arrows → labels → nodes).
2. **Infrastructure node** — a host, VM, pod, or managed service inside a zone. The §6 node-box pattern (SKILL.md) at `rx=6`, with a rectangular type tag (`rx=2`, **not** a pill) carrying `POD` / `VM` / `MANAGED` / `CDN` in the top-left corner.
3. **Artifact chip** — what is deployed onto that node. A small 24px-tall rect `rx=4`, fill `ink @ 0.05`, stroke `muted`, holding the image or service name in Geist sans 12px (left-aligned) plus a Geist Mono 9px version tag (right-aligned, e.g. `v2.4.1`). A node can carry more than one chip (stacked with an 8px gap) when more than one artifact is co-located (a sidecar, for example).

**Replica badge.** A node running N copies carries a right-aligned Geist Mono 8px badge (`x3`) inside its own small `rx=2` box in the node's top-right corner. A mask fully inside a node is a badge chip and is a legitimate exception to the "mask must not overlap a later node" rule (SKILL.md §6 rule 6) — it's part of that same node.

**Network paths.** Orthogonal elbows between nodes (SKILL.md §6, elbow formula and port-selection rules in `type-architecture.md`), labelled with protocol and port in Geist Mono 8px (`HTTPS:443`, `TLS:5432`). A path that crosses a zone boundary is `link`-blue; a path that stays inside one zone is `muted`. Async or replication paths are dashed `5,4`.

**Focal rule.** The 2 accent elements are the single-point-of-failure or the newly-introduced piece — never more than 2. In the canonical example: the RDS primary (accent-tint fill, accent stroke) and the replication path to its standby (accent, dashed).

## Complexity budget

| Limit | Rule |
|---|---|
| Max zones | 3 |
| Max infrastructure nodes | 6 |
| Max artifact chips | 9 |
| Max network paths | 8 |
| Max accent elements | 2 |

Over budget → split into one deployment diagram per environment.

## Anti-patterns

- Redrawing the logical architecture with hostnames bolted on. If no placement decision is visible (which host, which zone, how many replicas), use `type-architecture.md` instead.
- Zones that are just visual grouping with no boundary meaning — a zone must be a real environment or network boundary, not a layout convenience.
- Artifact chips without a version tag. The version is why the diagram exists; an unversioned chip is a wasted box.
- One node drawn per replica instead of a single node with a replica badge.
- Cloud-vendor icon soup standing in for named nodes — name the host or service, don't decorate it.
- Unlabelled network paths. Protocol and port are the content of a deployment diagram, not decoration.
- Mixing two environments in one diagram (e.g. staging and production nodes side by side without a zone boundary that actually separates them).

## Examples

- `assets/example-deployment.html` — minimal light
- `assets/example-deployment-dark.html` — minimal dark
- `assets/example-deployment-full.html` — full editorial
