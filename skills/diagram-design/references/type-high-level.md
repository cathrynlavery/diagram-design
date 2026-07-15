# High-Level

**Best for:** end-to-end data stack overviews — ingestion → storage → query → analytics → visualization — deployed on a container orchestrator (Kubernetes, ECS, Nomad). Combines a phase chevron banner, deployment boundary, orchestration bar, identity footer, and (optionally) a right-side vertical chevron strip for cross-cutting concerns (Orchestration, Security, Observability).

This type is **parametric**. The diagram is fully determined by a small list of inputs (chevrons, sources, components, connections). The formulas below tell you exactly where every shape lands given those inputs — two generations from the same inputs must produce visually identical SVG.

---

## 1. Inputs — the parameter contract

Before drawing, collect these from the user (or accept them as a YAML/JSON block). Everything in this reference is derived from these inputs. Don't invent geometry on the fly.

```yaml
chevrons:                       # ordered left → right; reserved names auto-promote to vertical
  - { name: "Data sources",         columns: 1 }
  - { name: "Ingestion",            columns: 1 }
  - { name: "Storage",              columns: 1 }
  - { name: "Transformation",       columns: 1 }
  - { name: "Visualization",        columns: 1 }
  - { name: "Orchestration",        vertical: true }                     # reserved → pairs with the bar
  - { name: "Security",             vertical: true, color: "#b85450" }   # tinted to match the Identity bar below
  - { name: "Observability",        vertical: true }                     # reserved → pairs with crosscut #2

sources:                        # external; rendered in the dashed zone on the left
  - { name: "PostgreSQL", type: "db",     connects_to: ["NiFi"] }
  - { name: "SFTP drop",  type: "ftp",    connects_to: ["NiFi"] }
  - { name: "Web forms",  type: "web",    connects_to: ["NiFi"] }
  - { name: "Legacy",     type: "legacy", connects_to: ["NiFi"] }

components:                     # inside the cluster, plus bars and cross-cutting rows
  - { name: "NiFi",       chevron: "Ingestion",      kind: node,          icon: nifi,     role: "COLL"  }
  - { name: "MinIO",      chevron: "Storage",        kind: node,          icon: minio,    role: "STORE", focal: true }
  - { name: "Trino",      chevron: "Storage",        kind: node,          icon: trino,    role: "VIRT"  }
  - { name: "Notebooks",  chevron: "Transformation", kind: node,          icon: jupyter,  role: "ANLZ"  }
  - { name: "Superset",   chevron: "Visualization",  kind: node,          icon: superset, role: "DASH" }
  - { name: "Airflow",    chevron: "Orchestration",  kind: bar,           icon: airflow,    subtitle: "Apache Airflow" }
  - { name: "Identity",   chevron: "Security",       kind: cross-cutting, icon: keycloak,   subtitle: "Keycloak · LDAP · OIDC",     color: "#b85450" }
  - { name: "Monitoring", chevron: "Observability",  kind: cross-cutting, icon: prometheus, subtitle: "Prometheus · Grafana · Loki" }

connections:                    # explicit edges; focal-touching ones become accent automatically
  - { from: "NiFi",    to: "MinIO",                style: "primary" }
  - { from: "NiFi",    to: "Trino",                style: "secondary" }
  - { from: "MinIO",   to: "Notebooks",            style: "primary" }
  - { from: "Trino",   to: "MinIO",                style: "query" }   # read-back (dashed)
  - { from: "Notebooks", to: "Superset",           style: "secondary" }
  - { from: "Airflow", to: ["NiFi", "Trino", "Notebooks"], style: "trigger" }

focal: "MinIO"                  # exactly one; defaults to first kind=node under "Storage"
dark: false
```

**Reserved chevron names** (always vertical, even if `vertical: true` is omitted): `Orchestration`, `Security`, `Observability`, `Governance`, `Backup`.

**Reserved `kind` values:**
- `node` — a standard box inside the cluster (default).
- `bar` — a horizontal strip spanning the cluster top. Typically one (Orchestration); see §5 for the pairing rule.
- `cross-cutting` — a horizontal strip spanning the body width (stops at the strip margin), stacked below the cluster. **Zero or more allowed**; each stacks 44 px below the previous (§2.5) and pairs 1:1 with a vertical chevron (§5).

**Optional `color`** (per component, hex string): tints the component's container and content while leaving connectors untouched. See §3.4. Use sparingly — a custom color is a semantic flag (e.g., red = security concern), not decoration.

**Source `type` values** → icon mapping (use `references/primitive-icons.md`):
- `db` → `database`
- `ftp` → `bucket` or upload arrow
- `web` → `internet`
- `legacy` → `server`
- `api` → `api`
- Any explicit icon name in `primitive-icons.md` is also accepted.

---

## 2. Layout formulas — deterministic geometry

Every coordinate below is derived from the inputs. **No hardcoded numbers in examples that aren't justified here.**

### 2.1 Canvas

```
has_vertical       = any(c.vertical or c.name in reserved_names for c in chevrons)
right_strip_w      = 28  if has_vertical else 0
strip_margin       = 8   if has_vertical else 0   # gap between body and right strip
effective_w        = 1000 - right_strip_w - strip_margin     # 1000 or 964

n_cross            = count of components with kind == "cross-cutting"
strip_y_bot        = max(428, 388 + n_cross * 44 - 4)        # extends to last crosscut row
viewBox_h          = max(540, strip_y_bot + 112)             # 112 reserved for legend
viewBox            = f"0 0 1000 {viewBox_h}"
```

Every horizontal element (chevron banner, cluster, orchestration bar, identity / cross-cutting bars) ends at `effective_w`. The right strip sits at `x = 1000 - right_strip_w` (= 972). The 8-px band between them is visual breathing room — never put content there.

`viewBox_h` grows when more than one cross-cutting bar is declared: 1 crosscut → 540, 2 → 600 (or 584 if you want it tight; the rule rounds to the next multiple of 20 for clean grids).

### 2.2 Horizontal chevron banner

```
y_banner           = 4
h_banner           = 28
horizontals        = [c for c in chevrons if not c.vertical and c.name not in reserved_names]
sum_columns        = sum(c.columns for c in horizontals)
base_unit          = floor_to_4(effective_w / sum_columns)        # multiple of 4
widths             = [max(120, base_unit * c.columns) for c in horizontals]
widths[-1]         += effective_w - sum(widths)                   # trailing absorbs remainder
x_boundaries       = cumulative_sum([0] + widths)                 # length sum_columns+1
chevron_cx(C)      = (x_boundaries[index(C)] + x_boundaries[index(C)+1]) / 2
```

**Polygon shapes:**
- First (leftmost): `(x0,4) (x1-12,4) (x1,18) (x1-12,32) (x0,32)`
- Middle: `(x0,4) (x1-12,4) (x1,18) (x1-12,32) (x0,32) (x0+12,18)`
- Last (rightmost): `(x0,4) (effective_w,4) (effective_w,32) (x0,32) (x0+12,18)`

Fills alternate `#2d3142` / `#3d4460` (light mode) or `#3d4460` / `#4a5270` (dark mode). Labels: paper-colored mono `font-size=7`, `letter-spacing=0.14em`, `text-anchor=middle`, centered at `chevron_cx, 21`.

**Color override** (per chevron, both horizontal and vertical): a chevron may declare an optional `color: "#hex"` that replaces the alternation fill for that one chevron. Use it to flag a phase that pairs with a custom-colored component (e.g., `Security` chevron in red when the Identity bar uses `color: "#b85450"`). Rules:

- Override applies to the polygon fill only. The label stays paper-colored — never recolor chevron labels.
- The alternation index doesn't shift; neighboring chevrons keep their natural fill, even if it produces two adjacent same-fill chevrons. Don't try to "fix" this — overrides should be rare (≤ 2 per diagram).
- In dark mode, use the same hex unless contrast against paper labels suffers; if it does, pick a darker shade for dark mode and document it as a `color_dark` field on that chevron.
- A chevron color override is independent of any paired component's color, but pairing them (same hex on chevron + bar) is the conventional way to make the column "read" as one concern.

### 2.3 Source zone (dashed, external)

```
sources_x          = 4
sources_y          = 40
sources_w          = x_boundaries[1] - 8           # width of the first chevron, minus 4px gutter each side
sources_h          = 336
```

Stroke: `rgba(45,49,66,0.20)`, `stroke-width=0.8`, `stroke-dasharray=6,3`, `rx=6`. Zone fill: `rgba(45,49,66,0.02)`.

### 2.4 Cluster boundary (solid)

```
cluster_x          = x_boundaries[1] + 4           # starts at end of source zone + 4px gutter
cluster_y          = 40
cluster_w          = effective_w - cluster_x       # extends to right strip / canvas edge
cluster_h          = 336
```

Stroke: `rgba(45,49,66,0.18)`, `stroke-width=1.2`, `rx=8`. Fill: `rgba(45,49,66,0.02)`. K8s icon + label at `(cluster_x + 16, 352)` (icon) and `(cluster_x + 40, 362)` (text).

### 2.5 Cross-cutting bars (identity, observability, …)

Zero or more `kind: cross-cutting` components stack below the cluster. Each gets its own 40-px row with a 4-px gap.

```
crosscuts          = [c for c in components if c.kind == "cross-cutting"]   # ordered as declared
cross_x            = 4
cross_y(k)         = 388 + k * 44                  # 388, 432, 476, …
cross_w            = effective_w - 4               # spans body width, stops at the strip margin
cross_h            = 40
```

Stroke: `rgba(45,49,66,0.20)`, `stroke-width=0.8`, `rx=6`. Fill: `rgba(45,49,66,0.05)`. Icon at `(16, cross_y(k) + 10)`, name centered at `(effective_w / 2, cross_y(k) + 22)`, subtitle at `(effective_w / 2, cross_y(k) + 34)`.

Reserved cross-cutting *concerns* (informational; user can name the actual bar whatever they want):
- **Identity / Security** — Keycloak, LDAP/AD, Okta, Auth0, OIDC providers
- **Observability** — Prometheus + Grafana, Datadog, OpenTelemetry, Loki
- **Backup / DR** — Velero, Restic, snapshot orchestrators
- **Governance / Lineage** — OpenMetadata, DataHub, Apache Atlas
- **Secrets / config** — Vault, Sealed Secrets, External Secrets

Each cross-cutting bar pairs 1:1 with a vertical chevron in the right strip (§5).

### 2.6 Orchestration bar component (inside cluster)

```
bar_x              = cluster_x + 12
bar_y              = 52
bar_w              = cluster_w - 24
bar_h              = 44
```

Stroke: `rgba(45,49,66,0.18)`, `stroke-width=0.8`, `rx=4`. Fill: `rgba(45,49,66,0.05)`. Tool icon at the far right (`bar_x + bar_w - 50, 58`); name centered at `(bar_x + bar_w/2, 71)`; subtitle at `(bar_x + bar_w/2, 84)`.

### 2.7 Component nodes (inside cluster)

```
node_w             = 152
node_h             = 80                            # focal same height, accent border
node_cx(N)         = chevron_cx(N.chevron)         # ← non-negotiable
node_x(N)          = node_cx(N) - node_w/2
```

If a chevron has K nodes assigned, stack them vertically:

```
first_top_y        = 120 if any bar in this column else 64
gap                = 16
row_top(k)         = first_top_y + k * (node_h + gap)   # k = 0..K-1
```

**Focal node:** `fill="rgba(235,108,54,0.08)"`, `stroke="#eb6c36"`, `stroke-width=1.2`. Title text in accent color. All other nodes: white fill, `stroke=rgba(45,49,66,0.25)`, `stroke-width=1`.

Role badge top-left at `(node_x+8, node_y+6)`, size 12 high. Icon top-right at `(node_x+node_w-32, node_y+6)`, 24×24, monochrome via `currentColor`. Name centered at `(node_cx, node_y+44)` size 11 sans semibold. Subtitle at `(node_cx, node_y+56)` size 8 mono muted.

### 2.8 Source nodes (inside dashed zone)

```
src_node_w         = sources_w - 8
src_node_h         = 64                            # uniform; chosen to fit ≤ 4 sources
src_node_x         = sources_x + 4
src_first_top_y    = 60
src_gap            = 16
src_row_top(k)     = src_first_top_y + k * (src_node_h + src_gap)
```

Same role-badge / icon / name / subtitle pattern as cluster nodes (icon at `src_node_x+54, row_top(k)+6`; name centered at `src_node_x+src_node_w/2, row_top(k)+42`; subtitle one line below). Role badge text: `EXT`. Caps at 4 sources; for more, split into a separate diagram.

### 2.9 Right strip — vertical chevrons

```
strip_x            = 1000 - right_strip_w       # 972 when present
strip_w            = 28
verticals          = [c for c in chevrons if c.vertical or c.name in reserved_names]
strip_y_top        = 40
strip_y_bot        = max(428, 388 + n_cross * 44 - 4)   # extends to last crosscut row (see §2.1)
strip_h_total      = strip_y_bot - strip_y_top
heights            = [floor_to_4(strip_h_total / len(verticals))] * len(verticals)
heights[-1]       += strip_h_total - sum(heights)       # last absorbs remainder
```

Examples:
- 2 verticals (Orchestration + Security), 1 crosscut → `heights = [192, 196]`, layout `[40..232, 232..428]`.
- 3 verticals (Orchestration + Security + Observability), 2 crosscuts → `strip_y_bot = 472`, `strip_h_total = 432`, `heights = [144, 144, 144]`, layout `[40..184, 184..328, 328..472]`.

Adjacent edges share the same y (no gap), like horizontal chevrons share x at their boundary.

**Polygon shapes** (top-to-bottom flow, mirrors horizontal §2.2):
- First (topmost): flat top, point at bottom — `(strip_x, y0) (strip_x+strip_w, y0) (strip_x+strip_w, y1-12) (strip_x+strip_w/2, y1) (strip_x, y1-12)`
- Middle: notch on top, point on bottom — `(strip_x, y0) (strip_x+strip_w/2, y0+12) (strip_x+strip_w, y0) (strip_x+strip_w, y1-12) (strip_x+strip_w/2, y1) (strip_x, y1-12)`
- Last (bottommost): notch on top, flat bottom — `(strip_x, y0) (strip_x+strip_w/2, y0+12) (strip_x+strip_w, y0) (strip_x+strip_w, y1) (strip_x, y1)`

Fills alternate `#2d3142` / `#3d4460` (same palette as horizontals). Labels: paper-colored mono `font-size=7`, `letter-spacing=0.14em`, **rotated −90°**, anchored at `(strip_x + strip_w/2, (y0+y1)/2)`.

Vertical chevrons honor the per-chevron `color` override documented in §2.2 — apply the hex to the polygon fill, leave the rotated label paper-colored. Pair the override with the same hex on the chevron's paired bar/crosscut to bind them visually as one concern.

---

## 3. Connector rules (mandatory)

These are non-negotiable. Pick the style **automatically** from the topology — do not let the user override style on focal-touching or bar-originating edges.

| `style` | Stroke | Width | Dash | Marker | When required |
|---|---|---|---|---|---|
| `primary` | `#eb6c36` | 1.2 | — | `arrow-accent` | Every edge whose endpoint is the `focal` node. |
| `secondary` | `#4f5d75` | 1.0 | — | `arrow` | Default for source→component and component→component when neither endpoint is focal. |
| `trigger` | `#4f5d75` | 1.0 | `4,3` | `arrow-sm` | Every edge originating from a `kind: bar` component. |
| `query` | `rgba(45,49,66,0.30)` | 1.0 | `4,3` | `arrow` | Read-back edges (e.g., focal ↔ Trino). |

**Defs block** (required, exactly these four markers):

```svg
<defs>
  <marker id="arrow"        markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker>
  <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#eb6c36"/></marker>
  <marker id="arrow-sm"     markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto"><polygon points="0 0, 6 2.5, 0 5" fill="#4f5d75"/></marker>
  <marker id="arrow-dim"    markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="rgba(45,49,66,0.45)"/></marker>
</defs>
```

### 3.1 Exit / entry sides (non-negotiable)

| Edge kind | Exit side of source | Entry side of target |
|---|---|---|
| Source → cluster node | **right** of source node | **left** of target |
| Component → component (within cluster) | **right** | **left** |
| Bar component → node | **bottom** of bar | **top** of node |
| Cross-cutting bar | — (emits no edges) | — |
| Vertical chevron | — (labels only; emits no edges) | — |

### 3.2 Routing

- Orthogonal elbows, **at most two bends** per path.
- Use a Q-bezier 8-px corner radius at every bend.
- Z-order: draw **all connectors before any node rectangle** (so node fills mask the line ends).
- Exactly one `marker-end` per `<path>` / `<line>`. Never both `marker-start` and `marker-end`.
- Labels: every `primary` and `secondary` connector gets a label (small mono, opaque paper-filled rect mask behind). `trigger` and `query` connectors are unlabelled.

### 3.3 Crossings

- Avoid. Re-route via the chevron divider trunk (§4) before accepting a crossing.
- If unavoidable, the path drawn second carries a 6-px arc hop over the first.

### 3.4 Component color override

A component may declare an optional `color: "#hex"` (CSS color string). The override **only** retints the component's container and content — connectors are never recolored. Edges keep their topology-driven style from §3.

**Where the color is applied** (given `C = color`):

| Element | Light mode | Dark mode |
|---|---|---|
| Container fill (`rect` body) | `rgba(C, 0.06)` | `rgba(C, 0.10)` |
| Container stroke | `rgba(C, 0.35)` (`stroke-width=1` for nodes, `0.8` for bars) | `rgba(C, 0.45)` |
| Role badge stroke (nodes) | `rgba(C, 0.40)` | `rgba(C, 0.55)` |
| Role badge text (nodes) | `rgba(C, 0.85)` | `rgba(C, 1.0)` |
| Icon fill / stroke | `C` | lighten `C` by ~15% (or use `C` if already light) |
| Name text | `C` | lighten `C` |
| Subtitle text | **unchanged** (`muted`) | **unchanged** (`muted`) |
| Connectors touching this component | **unchanged** (still topology-driven) | **unchanged** |

The subtitle stays muted because it's parenthetical metadata — only the primary identity (name + icon + border) carries the color signal.

**Rules**:

- **Never on the focal node.** The focal node is already colored with the accent (§2.7). A `color` on the focal node is ignored — accent wins.
- **Never on source nodes.** Sources live outside the cluster and stay neutral.
- **Cap at 2 custom-colored components** per diagram (in addition to the focal). Three or more colored things erases the signal — the same reason §1 limits accent to 1–2 elements.
- **No color on connectors.** If you find yourself wanting a colored edge, the right move is to pick a different `style` from §3, not to override.

**Semantic uses** (recommended):
- `#b85450` (rust-red) — Security / Identity (Keycloak, Vault)
- `#5a7d9a` (slate-blue) — Observability (Prometheus, Datadog)
- `#7a8c47` (olive-green) — Governance / Lineage (OpenMetadata)
- `#8c6d3f` (warm-brown) — Backup / DR

Stick to these unless the user's brand demands otherwise. Random hex per component is exactly the failure mode this skill avoids.

---

## 4. Block branching rules (fan-out)

The single biggest reproducibility hazard. Fix these rules and the diagram becomes predictable.

### 4.1 Source fan-out (one source → N components)

```
exit_x   = source.right
trunk_x  = cluster_x - 8                     # 4-px gutter before cluster border
```

Path per target: `M exit_x,source_cy → H trunk_x → V target_cy → H target.left`. Use Q-bezier corners.

### 4.2 Component fan-out (one component → N components)

```
exit_x   = node.right
trunk_x  = x_boundaries[index(source.chevron) + 1] + 4   # 4 px past the chevron divider
```

Path per target: `M exit_x,source_cy → H trunk_x → V target_cy → H target.left`.

### 4.3 Fan-out cap

**Max 3 outgoing edges per node.** Above 3, introduce a hub (usually the `focal` node). The chevron banner is the legend; if a node is fanning out to four downstream targets, it's secretly the hub — make it explicit.

### 4.4 Bar drops (Airflow → N nodes)

```
drop_x(target) = target.cx
drop_y_start   = bar.bottom
drop_y_end     = target.top
```

Straight vertical line, `style: trigger`. One per target. No bends — bar drops never elbow.

### 4.5 Source vertical staggering

When multiple sources connect to the same single target (e.g. four sources → NiFi), stagger their entry y on the target:

```
entry_y(k) = target.top + 8 + k * (target_h - 16) / (N - 1)   # k = 0..N-1, evenly spaced
```

This avoids overlapping arrowheads at the target's left edge.

---

## 5. Vertical chevrons — semantics

Reserved names `Orchestration`, `Security`, `Observability`, `Governance`, `Backup` always render in the right strip (§2.9). Any chevron with `vertical: true` is treated as a reserved-style vertical regardless of name. The rules:

- **Pairing rule (mandatory, 1:1):** every vertical chevron pairs with exactly one cross-spanning component, and every cross-spanning component pairs with exactly one vertical chevron. The two component kinds that pair:
  - `kind: bar` — lives inside the cluster (top row). Conventionally paired with `Orchestration`.
  - `kind: cross-cutting` — lives below the cluster, one row per component. Paired with `Security`, `Observability`, `Governance`, etc.

  If the inputs declare a vertical chevron without a paired component (or vice versa), halt and ask the user — the diagram is incomplete.

- **Count constraint:** `len(verticals) == len(bars) + len(crosscuts)`. The right strip is split evenly among all verticals (§2.9), so visual alignment between a chevron and its bar/row is approximate — the *label* is what matters, not the y-pixel match.

- **Ordering convention:** declare verticals top-down in the order: bar-paired first (Orchestration), then crosscut-paired in the same order the crosscuts appear below the cluster. This keeps the visual reading order consistent.

- **No edges:** vertical chevrons emit no connectors themselves. They are *labels for a column of cross-cutting concern*.

- **No node placement:** no `kind: node` may be assigned to a vertical chevron. Nodes always belong to a horizontal phase.

- **Right strip presence:** if any vertical chevron exists, the right strip is reserved (`effective_w = 964`) and **all** horizontal chevron widths and cluster geometry shrink accordingly. Do not draw a vertical chevron on top of the cluster.

The visual contract: the vertical chevron's column visually "owns" the bar/cross-cutting row at its approximate y-band. Orchestration (top of strip) ↔ Airflow bar (top of cluster). Security ↔ Identity bar. Observability ↔ monitoring bar (below identity). And so on.

---

## 6. Dark mode

When `dark: true`, swap these tokens:

| Token | Light | Dark |
|---|---|---|
| Page paper | `#f5f5f5` | `#1c1f2e` |
| Ink | `#2d3142` | `#f5f5f5` |
| Muted text | `#4f5d75` | `rgba(245,245,245,0.65)` |
| Chevron dark fill | `#2d3142` | `#3d4460` |
| Chevron light fill | `#3d4460` | `#4a5270` |
| Chevron label | `#f5f5f5` | `#f5f5f5` (unchanged) |
| Dashed border | `rgba(45,49,66,0.20)` | `rgba(245,245,245,0.22)` |
| Cluster border | `rgba(45,49,66,0.18)` | `rgba(245,245,245,0.18)` |
| Node fill | white | `rgba(245,245,245,0.06)` |
| Node stroke | `rgba(45,49,66,0.25)` | `rgba(245,245,245,0.20)` |
| Focal fill | `rgba(235,108,54,0.08)` | `rgba(240,138,89,0.12)` |
| Focal stroke | `#eb6c36` | `#f08a59` |
| Accent connector | `#eb6c36` | `#f08a59` |
| Dot pattern | `rgba(45,49,66,0.10)` | `rgba(245,245,245,0.10)` |

---

## 7. Reproducibility checklist (the taste gate)

Before emitting SVG, verify **every** item. If any fails, fix it — don't ship.

1. Every cluster `node.cx` equals its chevron's `cx` (§2.2 + §2.7). This is what makes the chevron banner a real legend.
2. Every chevron `width` is a multiple of 4 and ≥ 120.
3. The reserved right strip (28 px) exists **iff** any vertical chevron is declared. If yes, `effective_w = 972`; if no, `effective_w = 1000`.
4. Exactly **one** `focal` node. If `focal` is unset in inputs, default to the first `kind: node` under chevron "Storage".
5. Every edge whose endpoint is the focal node uses `style: primary` (accent stroke + `arrow-accent` marker).
6. Every edge originating from a `kind: bar` component uses `style: trigger` (dashed + `arrow-sm`).
7. The cross-cutting bar (if any) emits **no** edges.
8. No node has > 3 outgoing edges, or if it does, it is the declared `focal` / hub.
9. All `<path>` and `<line>` connectors are emitted **before** any node `<rect>` (z-order).
10. Each vertical chevron pairs **1:1** with exactly one `bar` or `cross-cutting` component (§5 pairing rule). `len(verticals) == len(bars) + len(crosscuts)`.
11. `viewBox_h = max(540, strip_y_bot + 112)` — grow the canvas when multiple crosscuts are declared so the legend still fits.
12. Custom component colors (§3.4) apply only to container + icon + name; connectors stay topology-driven. Cap at 2 custom-colored components in addition to the focal.
11. The diagram passes SKILL.md §9 (4-px grid; ≤ 2 accent elements; mono only for technical content; hairlines; no shadows; no `rounded-2xl`).

---

## 8. Anti-patterns

- Chevron banner omitted — it's the key that maps visual columns to functional phases.
- Node x-center off-chevron (§7 #1) — breaks the "banner-as-legend" contract.
- Vertical chevron drawn on the cluster (overlay) instead of in a reserved right strip.
- More than one focal node — MinIO/S3 (or whichever storage hub) is *the* focal point.
- External zone with solid border — dashed border is the signal that these components are outside the cluster.
- Identity bar inside the cluster boundary — it applies to all components and must span the full canvas width.
- Vertical chevron without a paired bar/cross-cutting component — see §5 pairing rule.
- Bar-component edges drawn solid — orchestration triggers must be dashed.
- Source fanning out to >3 components without a hub.

---

## 9. Examples

- `assets/example-high-level.html` — horizontal-only, 5 phases, light skin.
- `assets/example-high-level-dark.html` — same, dark skin.
- `assets/example-high-level-full.html` — same, editorial-card frame.
- `assets/example-high-level-vertical.html` — adds vertical Orchestration + Security chevrons, Airflow bar, Keycloak cross-cutting. **Reference render of the full parametric pattern.**
- `assets/example-high-level-vertical-dark.html` — vertical pattern, dark skin.
- `assets/example-high-level-vertical-full.html` — vertical pattern, editorial-card frame.
