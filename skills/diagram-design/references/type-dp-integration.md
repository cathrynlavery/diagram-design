# DP integration

**Best for:** the integration topology of a data platform — which source systems plug in, which consumer surfaces plug out, and which protocol each one speaks. Hub-and-spoke layout wrapped in an explicit **Data platform** layer; no time/phase axis.

Use when the question is *"what surfaces does this platform expose, and over what wire?"* rather than *"how does data move through phases?"*.

This type is **parametric** — like `type-high-level.md`, every coord is derived from a small inputs schema. Two generations from the same inputs must produce visually identical SVG.

---

## 1. Inputs — the parameter contract

```yaml
sources:                            # left column, 0..6 nodes
  - { name: "Databases",  type: "db",        subtitle: "SQL · MariaDB",
      connects_to: [{to: "NiFi", label: "JDBC"},
                    {to: "Trino", label: "FEDERATE", style: "federated"}] }
  - { name: "SFTP drops", type: "sftp",      subtitle: "scheduled pulls",
      connects_to: [{to: "NiFi", label: "SFTP"}] }
  - { name: "Email",      type: "mail",      subtitle: "IMAP attachments",
      connects_to: [{to: "NiFi", label: "IMAP"}] }
  - { name: "IBM legacy", type: "mainframe", subtitle: "file export",
      connects_to: [{to: "NiFi", label: "FILE"}] }

platform:
  name: "DATA PLATFORM"             # zone label (paper-masked top border)
  rows:                             # ordered top→bottom; each is bar or row
    - { kind: bar, name: "Trino",   icon: trino,   subtitle: "federated query · push-down",
        role: "SQL", focal: true }
    - { kind: row, nodes: [
        { name: "Apache NiFi",  icon: nifi,    role: "INGEST",   subtitle: "flow-based ETL" },
        { name: "MinIO",        icon: minio,   role: "STORE",    subtitle: "S3 object store · medallion", focal: true },
        { name: "JupyterLab",   icon: jupyter, role: "NOTEBOOK", subtitle: "Python · R · pandas" }
      ]}
    - { kind: bar, name: "Apache Airflow", icon: airflow,
        subtitle: "scheduler · DAG triggers · backfill", role: "DAG" }

consumers:                          # right column, 0..6 nodes
  - { name: "Desktop apps",   type: "monitor", subtitle: "SPSS · SAS · Stata",
      connects_from: [{from: "Trino", label: "ODBC"}] }
  - { name: "BI & reports",   type: "chart",   subtitle: "Tableau · Power BI",
      connects_from: [{from: "Trino", label: "JDBC"}] }
  - { name: "Public website", type: "globe",   subtitle: "NatStat portal",
      connects_from: [{from: "Trino", label: "HTTPS"}] }
  - { name: "API gateway",    type: "api",     subtitle: "3rd-party / OAuth2",
      connects_from: [{from: "Trino", label: "REST"}] }

footer:                             # 0..N cross-cutting bars stacked below zone (full-canvas width)
  - { name: "Active Directory", icon: key,        subtitle: "LDAP · SSO · group RBAC",
      color: "#b85450" }            # tinted red to flag the security concern
  # additional footer nodes (Observability, Backup, …) stack below this one

internal_connections:               # explicit platform-component edges
  - { from: "NiFi",        to: "MinIO",      style: "primary",   label: "WRITE" }
  - { from: "MinIO",       to: "JupyterLab", style: "secondary", label: "READ"  }
  - { from: "MinIO",       to: "Trino",      style: "secondary" }
  - { from: "JupyterLab",  to: "Trino",      style: "secondary", dashed: true }
  - { from: "Airflow",     to: ["Apache NiFi", "MinIO", "JupyterLab"], style: "trigger" }

focal_accent: "#eb6c36"             # one color for all focal components (default = SKILL accent)
dark: false
```

**Reserved `kind` values for `platform.rows`:**
- `bar` — full-zone-width strip. Default height 44 px (focal bars get 56 px). Required fields: `name`, `icon`. Optional: `subtitle`, `role`, `color`, `focal`.
- `row` — N nodes evenly spaced across zone width. Required: `nodes` list. Each node has `name`, `icon`, optional `role`, `subtitle`, `color`, `focal`.

**Source/consumer `type` values** → icon mapping (extends `references/primitive-icons.md`):
- `db` → cylinder, `sftp` → folder-with-arrow, `mail` → envelope, `mainframe` → server-with-vents
- `monitor` → desktop screen, `chart` → bar-chart, `globe` → globe, `api` → curly braces
- `key` → key + ring (identity / IDP)
- Any explicit icon name in `primitive-icons.md` is also accepted.

**Per-component `color: "#hex"`** is optional on any node, bar, or footer entry. See §4.

---

## 2. Layout formulas — deterministic geometry

```
# Canvas
viewBox_w        = 1200
n_sources        = len(sources)
n_consumers      = len(consumers)
n_footer         = len(footer)

# Side columns (sources left, consumers right)
col_top          = 92
col_node_h       = 64
col_gap          = 24                    # stride = col_node_h + col_gap = 88
col_h_min        = 336                   # default fits 4 sources (4 * 88 - 24)
col_h            = max(col_h_min, max(n_sources, n_consumers) * 88 - 24)
left_x           = 40
left_w           = 160
right_x          = 1000
right_w          = 160
col_node_y(k)    = col_top + k * 88
col_node_cy(k)   = col_node_y(k) + col_node_h/2     # 124, 212, 300, 388 by default

# Platform zone
zone_x           = 260
zone_w           = 696
zone_y           = 72
zone_h           = col_h                            # zone always matches column height
zone_cx          = zone_x + zone_w/2                # 608
zone_pad_x       = 16                               # inside left/right padding for bars
zone_label_y     = zone_y + 3                       # paper-masked label across top border

# Footer bars (below zone — each cross-cutting concern is a full-width bar)
footer_top       = zone_y + zone_h + 52             # 52-px gap below zone
footer_bar_h     = 56
footer_bar_x     = 40                               # aligned with source column left edge
footer_bar_w     = viewBox_w - 80                   # = 1120 — spans from source col left to consumer col right
footer_gap       = 8
footer_y(k)      = footer_top + k * (footer_bar_h + footer_gap)
footer_bottom    = footer_top + n_footer * (footer_bar_h + footer_gap) - footer_gap

viewBox_h        = max(600, footer_bottom + 84)     # 84 reserved for legend

# Platform.rows allocation inside zone
bar_h_focal      = 56
bar_h_default    = 44
row_h            = 72
row_gap          = 16
```

### 2.1 Row placement (cursor algorithm)

Allocate each `platform.rows` entry top-to-bottom. The single `row` (or first row when N>1) anchors to side-column row 2 so its connectors stay horizontal:

```
primary_row_idx  = index of first kind=row in platform.rows
primary_row_top  = col_node_y(1) - (row_h - col_node_h)/2     # 176 by default
                                                              # 4-px nudge so cy aligns with side row 2

# Place rows above primary
y = primary_row_top
for entry in platform.rows[:primary_row_idx] reversed:
    y -= row_gap
    entry.h     = bar_h_focal if (entry.kind == bar and entry.focal) else bar_h_default
    y          -= entry.h
    entry.y_top = y                                            # Trino bar lands at y=104

# Place primary row
platform.rows[primary_row_idx].y_top = primary_row_top         # NiFi/MinIO/Jupyter at y=176
platform.rows[primary_row_idx].h     = row_h

# Place rows below primary
y = primary_row_top + row_h
for entry in platform.rows[primary_row_idx+1:]:
    y          += row_gap
    entry.y_top = y
    entry.h     = bar_h_focal if (entry.kind == bar and entry.focal) else bar_h_default
    y          += entry.h

# Constraint: y <= zone_y + zone_h
```

This produces the canonical layout for the standard shape (top bar / 3-node row / bottom bar): Trino at `y=104 h=56`, primary row at `y=176 h=72`, Airflow at `y=324 h=44`. Bottom anchor of Airflow at y=368 (40-px clear from zone bottom at y=408). **Note**: with the canonical layout there's a 76-px gap between the primary row's bottom (y=248) and Airflow's top (y=324). That gap is intentional — Airflow visually sits at the same y-band as source/consumer row 4 (cy=388), so it reads as a sibling of the bottom side-column row.

### 2.2 Node placement inside a `row` entry

```
N            = len(row.nodes)
node_w       = (zone_w - 2*zone_pad_x - (N-1) * 16) / N
node_x(j)    = zone_x + zone_pad_x + j * (node_w + 16)
node_cx(j)   = node_x(j) + node_w/2
```

For the canonical 3-node row: `node_w = (696 - 32 - 32) / 3 = 210.67`. The shipped example uses fixed `node_w=160` with custom x positions (`288, 480, 672`) chosen so each node's `cx` aligns to the column for connector convenience: 368, 560, 752. **Both layouts are valid**; the formula above is the default for new diagrams. Document any deviation in the rendered SVG with a comment.

### 2.3 Bar (full-zone-width) placement

```
bar_x      = zone_x + zone_pad_x         # 276
bar_w      = zone_w - 2*zone_pad_x       # 664
bar_cx     = zone_cx                     # 608
```

Bars span the full zone width minus 16-px padding on each side. Bars marked `focal: true` use `bar_h_focal=56` and accent styling (fill `rgba(focal_accent, 0.08)`, stroke `focal_accent`). Non-focal bars use `bar_h_default=44` with muted styling (fill `rgba(45,49,66,0.05)`, stroke `rgba(45,49,66,0.32)`).

### 2.4 Source / consumer placement (side columns)

```
source_y(k)       = col_top + k * 88            # 92, 180, 268, 356, …
source_cy(k)      = source_y(k) + col_node_h/2  # 124, 212, 300, 388, …
consumer_y(k)     = source_y(k)                 # mirrored
consumer_cy(k)    = source_cy(k)
```

All side-column nodes use fixed `w=160 h=64`. Same fill / stroke pattern: fill `rgba(79,93,117,0.06)`, stroke `#7a8399`, stroke-width 1.

---

## 3. Connector rules (mandatory)

Five styles, bound to topology. Don't let user override style on focal-touching, bar-originating, or Trino → consumer edges — those are fixed by rule.

| `style` | Stroke | Width | Dash | Marker | When required |
|---|---|---|---|---|---|
| `primary` | `#eb6c36` (focal_accent) | 1.4 | — | `arrow-accent` | Every edge whose endpoint is a `focal: true` component. Also every Trino → consumer edge (serve-flow rule). |
| `secondary` | `#4f5d75` (muted) | 1.2 | — | `arrow` | Default for internal platform-component edges and source → platform edges that don't touch focal. |
| `federated` | `#2e5aa8` (link-blue) | 1.0 | `4,3` | `arrow-link` | Federation queries (e.g., source DB → Trino). |
| `trigger` | `#4f5d75` (muted) | 1.0 | `4,3` | `arrow` | Every edge originating from a `kind: bar` component (Airflow drops). Unlabelled. |
| `auth` | `#eb6c36` | 1.2 | `5,4` | `arrow-accent` | Every edge from a footer node up to the zone bottom edge. **Never to a specific component.** |

**Defs block** (required, five markers — exactly):

```svg
<defs>
  <marker id="arrow"        markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker>
  <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#eb6c36"/></marker>
  <marker id="arrow-link"   markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#2e5aa8"/></marker>
  <marker id="arrow-sm"     markerWidth="6" markerHeight="5" refX="5" refY="2.5" orient="auto"><polygon points="0 0, 6 2.5, 0 5" fill="#4f5d75"/></marker>
  <marker id="arrow-dim"    markerWidth="8" markerHeight="6" refX="7" refY="3"   orient="auto"><polygon points="0 0, 8 3, 0 6" fill="rgba(45,49,66,0.45)"/></marker>
</defs>
```

### 3.1 Exit / entry sides (non-negotiable)

| Edge kind | Exit side of source | Entry side of target |
|---|---|---|
| Source → platform component | **right** of source | **left** of target |
| Platform → platform (same row) | **right** | **left** |
| Bar → row node (vertical drop) | **bottom** of bar at `node_cx(target)` | **top** of target |
| Platform → consumer | **right** of source platform component | **left** of consumer |
| Footer → zone | **top** of footer (at `footer_auth_x(k)`) | zone bottom edge `y = zone_y + zone_h` |
| Footer → component (any specific one) | **forbidden** |

### 3.2 Routing

- Orthogonal elbows with at most two bends; Q-bezier `r=8` at every corner.
- **Fan-out staggering:** when one node fans out to N targets on the same side, stagger the exit y by ±4 px per index so arrows don't overlap (e.g., Trino → 4 consumers exits at y=124, 132, 140, 148). The vertical segments run in the corridor between the zone edge and the consumer column, also y-staggered.
- **Z-order:** all connectors drawn **before** any rect (so node fills mask the line ends).
- **Markers:** exactly one `marker-end` per `<line>` / `<path>`. Never `marker-start`.
- **Labels:** every `primary`, `secondary`, `federated`, `auth` edge gets a protocol label (Geist Mono 8 px, paper-filled rect mask with 6–10 px clear gap above the stroke). `trigger` edges are unlabelled.

### 3.3 Footer → zone trunk

When N=1 footer: single vertical line at `x = zone_cx` from `footer_y(0)` to `zone_y + zone_h`.

When N≥2 footers: stagger AUTH lines so they don't overlap stacked footers. For footer index `k`:

```
footer_auth_x(k) = zone_cx + (k - (N-1)/2) * 32     # 32-px stride per footer
```

Examples:
- N=1 → 560
- N=2 → 544, 576
- N=3 → 528, 560, 592

Each AUTH line goes from `(footer_auth_x(k), footer_y(k))` up to `(footer_auth_x(k), zone_y + zone_h)`. AUTH labels sit just above the arrowhead at the zone bottom edge.

### 3.4 Crossings

Avoid. Re-route via the corridor x positions before accepting a crossing. If unavoidable, the path drawn second carries a 6-px arc hop over the first.

---

## 4. Component color override (mirrors `type-high-level.md` §3.4)

Any source, consumer, platform component (node or bar), or footer node accepts an optional `color: "#hex"`. Mirrors high-level so the rule reads identically across types.

**Where the color is applied** (`C = color`):

| Element | Light | Dark |
|---|---|---|
| Container fill (`rect` body) | `rgba(C, 0.06)` | `rgba(C_light, 0.10)` |
| Container stroke | `rgba(C, 0.35)` (`stroke-width=1` for nodes, `0.8` for bars) | `rgba(C_light, 0.45)` |
| Role badge stroke | `rgba(C, 0.40)` | `rgba(C_light, 0.55)` |
| Role badge text | `rgba(C, 0.85)` | `rgba(C_light, 1.0)` |
| Icon stroke / fill | `C` | `C_light` |
| Name text | `C` | `C_light` |
| Subtitle text | **unchanged** (muted) | **unchanged** (muted) |
| Connectors touching this component | **unchanged** — topology-driven | **unchanged** |

`C_light` = the same hex lightened ~15% for dark-mode contrast (e.g., `#b85450` → `#d97a78`).

**Rules:**

- **Never on focal components.** `focal_accent` always wins — a `color` on a focal component is ignored.
- **Never on connectors.** If you want a colored edge, pick a different `style` from §3, not a color override.
- **Cap at 2 custom-colored components** per diagram (in addition to the focal pair).

**Semantic palette** (use these unless brand demands otherwise):
- `#b85450` rust-red — Security / Identity (AD, Keycloak, Vault)
- `#5a7d9a` slate-blue — Observability (Prometheus, Datadog, OpenTelemetry)
- `#7a8c47` olive-green — Governance / Lineage (OpenMetadata, DataHub)
- `#8c6d3f` warm-brown — Backup / DR (Velero, Restic)

---

## 5. Focal rule

**Exactly two focal components.** Default: the storage hub (MinIO / S3 / similar) and the federation engine (Trino / Dremio / similar). These two surfaces distinguish a "platform" from a pile of tools. Everything else (NiFi, Jupyter, Airflow, AD, all sources, all consumers) stays ink / muted.

- Mark with `focal: true` on the component entry.
- A focal `kind: bar` uses `bar_h_focal=56` (taller) and accent styling.
- A focal `kind: row` node keeps `row_h=72` but uses accent styling.
- The **Trino → all consumers** edges are always `primary` (accent), regardless of focal flag on each consumer — this is the serve-flow rule.
- If fewer than 2 or more than 2 components are marked `focal: true`, halt and ask the user.

---

## 6. Dark mode

| Token | Light | Dark |
|---|---|---|
| Page paper | `#f5f5f5` | `#2d3142` |
| Ink | `#2d3142` | `#f5f5f5` |
| Muted | `#4f5d75` | `#bfc0c0` |
| Accent | `#eb6c36` | `#f08a59` |
| Link (federated) | `#2e5aa8` | `#6a95d8` |
| Side-column fill | `rgba(79,93,117,0.06)` | `rgba(245,245,245,0.06)` |
| Side-column stroke | `#7a8399` | `rgba(245,245,245,0.30)` |
| Zone fill | `rgba(45,49,66,0.025)` | `rgba(245,245,245,0.04)` |
| Zone stroke | `rgba(45,49,66,0.32)` | `rgba(245,245,245,0.30)` |
| Non-focal bar fill | `rgba(45,49,66,0.05)` | `rgba(245,245,245,0.06)` |
| Focal fill | `rgba(235,108,54,0.08)` | `rgba(240,138,89,0.12)` |
| Focal stroke | `#eb6c36` | `#f08a59` |
| Custom component colors | `C` | `C_light` (lighten ~15%) |

---

## 7. Reproducibility checklist (taste gate)

Before emitting SVG, verify **every** item:

1. `viewBox = "0 0 1200 {viewBox_h}"` where `viewBox_h = max(600, footer_bottom + 84)`.
2. Platform zone at `x=260 y=72 w=696 h=col_h`. Zone label paper-masked across top border at `y=zone_y+3`.
3. Left column at `x=40..200`, right column at `x=1000..1160` — both 160 wide.
4. Source / consumer rows top at `y=92`, stride 88 px.
5. `platform.rows` entries stack inside zone via the §2.1 cursor algorithm; total y-span ≤ `zone_h`.
6. Inside each `kind: row`, node x-centers are evenly spaced across zone width (§2.2).
7. **Exactly 2** focal components (`focal: true`).
8. Every edge originating from a `kind: bar` component uses `style: trigger` (dashed, unlabelled).
9. Every Trino → consumer edge uses `style: primary` (the serve-flow rule).
10. Footer nodes connect only to the zone bottom edge via `auth` style. **No** edge from a footer to a specific component.
11. Custom component colors ≤ 2 (in addition to the focal pair). Connectors never recolored by component `color`.
12. All connectors emitted before any node rect (z-order rule).

---

## 8. Sources and consumers — icon library

Define each icon as `<g id="ico-…">` in `<defs>`, drawn at translate(cx, cy) with `stroke="currentColor"` so it inherits the surrounding text color. Common icons:

- `ico-db` (cylinder) — relational sources
- `ico-sftp` (folder with down arrow) — file drops
- `ico-mail` (envelope) — email pulls
- `ico-mainframe` (server with vents) — legacy systems
- `ico-monitor` — desktop analytics tools
- `ico-chart` (bars) — BI / report tools
- `ico-globe` — public websites
- `ico-api` (brackets `{}`) — gateways and 3rd-party clients
- `ico-key` — identity / IDP
- `ico-monitoring` (chart-line) — observability stack

If you need more icons, browse `assets/icons.html` and define matching `<symbol>` blocks.

---

## 9. Identity, common services → connect to the layer, not to components

**Active Directory** (or Keycloak, IAM, OPA, any cross-cutting identity / policy / secrets store) authenticates *every* component in the platform. Wiring it to one specific tool would understate the trust scope. Connect it instead with a single arrow to the bottom edge of the platform zone, labeled `AUTH` (§3.3).

The same rule applies to any other layer-wide service: centralized logging, secrets vault, observability stack, audit sink, mTLS root. Each goes in the `footer` list, each gets its own row, each gets its own AUTH line up to the zone bottom edge (staggered by index per §3.3). The visual reading is "the platform layer delegates to all of these," which is the architectural truth.

---

## 10. Budget — this type exceeds the default

This is the one type where the default 9-node / 12-arrow budget is intentionally exceeded. A realistic platform integration shows:

- 4–6 source nodes
- 5 platform components
- 4–6 consumer nodes
- 1–3 footer nodes (identity, observability, backup, …)

That's **14–20 nodes**. The complexity is the point — the diagram is making a claim about the *number of distinct integration surfaces*. Compressing them collapses the claim.

When this gets unwieldy:
- Combine clearly-identical source rows (e.g., four MariaDB databases → one `Databases` node with sublabel `4 × MariaDB`)
- Split into two diagrams (one per integration plane: data vs. identity vs. observability)

---

## 11. Anti-patterns

- **Sources or consumers as a single collapsed node** when ≥3 distinct items exist — defeats the whole point of this type. Use Architecture or High-level if you want collapsing.
- **One bus arrow from "sources" to "the platform"** — every wire is labeled with its protocol; this is how integration teams read the diagram.
- **Per-tool color coding** (teal-NiFi, magenta-MinIO, yellow-Jupyter) inside the zone — collapses hierarchy; only the two focal accents earn coral, plus up to 2 custom colors on cross-cutting components (§4 cap).
- **More than 2 focal components** — focal exists to distinguish "platform" from "pile of tools"; >2 erases the signal (same rule as SKILL.md §1).
- **`color` override on a focal component** — ignored. Focal_accent always wins.
- **Footer wired to one specific tool** (e.g., AD → Airflow only) — wrong unless that service truly only protects one tool. The default is the layer-wide connection.
- **Footer or identity inside the zone** — identity gates the layer from outside. Drawing it inside misrepresents the trust model.
- **Phase chevrons across the top** — those belong on `high-level`.
- **Custom-colored connectors** — connectors are topology-driven. Style picks the color; `color` on a component never spreads to its edges.

---

## 12. Examples

- `assets/example-dp-integration.html` — minimal light (1 footer = AD). Gallery default.
- `assets/example-dp-integration-dark.html` — same, dark skin.
- `assets/example-dp-integration-full.html` — same, editorial-card frame.
- `assets/example-dp-integration-extended.html` — exercises §4 color override + multi-footer: AD in rust-red, Observability (Prometheus/Grafana/Loki) in slate-blue. Canvas height grown to fit 2 footer rows.
- `assets/example-dp-integration-extended-dark.html` — extended pattern, dark skin.
- `assets/example-dp-integration-extended-full.html` — extended pattern, editorial-card frame.
