# IT current-state

**Best for:** documenting the *before* picture of a modernization proposal — the legacy IT landscape grouped by phase or department (Collection → Processing → Dissemination, or Frontend / Backend / Storage, or Survey → Analysts → Reports), with pain-points flagged, file-based hand-offs labelled (CSV / Excel / Email / Copy), and pre-platform tooling visible. The companion to `type-dp-integration.md`: this type shows the gap that a data-platform proposal is going to close.

Use when stakeholders need to see the friction in the current setup — siloed scripts, manual file shuffles, missing version control, single-points-of-failure — and the path from those to a target platform topology.

This type is **parametric** — the inputs schema in §1 drives every coordinate via the formulas in §2. The rule shape mirrors `type-dp-integration.md` (zones + cross-cutting footer bars), `type-process.md` (rounded right-angle connectors), and `type-medallion.md` (per-element `color` override) so the focal rule, color override, dark mode, and reproducibility checklist read identically across types.

---

## 1. Inputs — the parameter contract

```yaml
title:    "Current IT Landscape"
subtitle: "Data pipeline before the platform"
eyebrow:  "NatStat · Before the platform"

orientation: horizontal      # horizontal (default, zones L→R) | vertical (zones T→B)

zones:                       # 2..4 zones, ordered along the orientation axis
  - name: "COLLECTION"
    components:              # 1..5 components per zone
      - id: survey-solutions
        name: "Survey Solutions"
        sub:  "CAPI · PostgreSQL"
        icon: postgres               # any id from references/primitive-icons.md
        kind: standard               # standard | focal | external (external → dashed stroke)
      - { id: aspnet,    name: "ASP.NET Apps",    sub: "migration · admin portals", icon: server }
      - { id: civil-reg, name: "Civil Registry",  sub: "external · CRVS data",      icon: database, kind: external }
  - name: "PROCESSING"
    components:
      - { id: shared-drive,  name: "Shared Drive",     sub: "No version control · Windows file share", icon: file,      kind: focal }
      - { id: analyst-mach,  name: "Analyst Machines", sub: "SPSS · SAS · Stata · Excel",              icon: desktop }
      - { id: sql-server,    name: "SQL Server",       sub: "on-premises · core RDBMS",                icon: sqlserver, color: "#7a8c47" }  # custom olive
  - name: "DISSEMINATION"
    components:
      - { id: legacy-portal,   name: "LegacyPortal",      sub: "manual bottleneck",     icon: cloud,    kind: focal }
      - { id: natstat-website, name: "NatStat Website",   sub: "public · static pages", icon: internet }
      - { id: ministry,        name: "Ministry Partners", sub: "~6 ministries",         icon: users,    kind: external }

connectors:                   # ordered list; each links two component ids
  - { from: survey-solutions, to: shared-drive,   label: "CSV",     icon: csv,   style: link }
  - { from: aspnet,           to: shared-drive,   label: "EMAIL",   icon: file,  style: link }      # `mail` MISSING in catalog → falls back to `file`
  - { from: civil-reg,        to: shared-drive,   label: "EXCEL",   icon: excel, style: link, dashed: true }
  - { from: shared-drive,     to: analyst-mach,   label: "COPY",                 style: accent, dashed: true }
  - { from: analyst-mach,     to: sql-server,     label: "LOAD",                 style: neutral }
  - { from: analyst-mach,     to: legacy-portal,   label: "EXCEL",  icon: excel, style: accent }
  - { from: legacy-portal,    to: natstat-website, label: "WEB",                 style: neutral }
  - { from: natstat-website,  to: ministry,        label: "CSV DL", icon: csv,   style: link, dashed: true }

footer:                       # 0..3 optional full-canvas-width bars (cross-cutting concerns)
  - { name: "Identity Manager", sub: "Active Directory · LDAP · SSO", icon: active-directory }
  - { name: "Observability",    sub: "logs · metrics · alerts",       icon: monitoring }

legend:                       # auto-generated from styles used; user can override labels
  - { swatch: link,    label: "data flow" }
  - { swatch: accent,  label: "pain-point" }
  - { swatch: dashed,  label: "external" }
  - { swatch: focal,   label: "bottleneck" }

dark: false
```

**Reserved field semantics:**

- `orientation` — `horizontal` (zones run L→R, components stack vertically inside each zone) or `vertical` (zones stack T→B, components run L→R inside each zone).
- `zones[i].name` — uppercase short label (≤ 14 chars). Rendered at the top-left of the zone box in the `eyebrow` role with letter-spacing 0.14em, on a paper-masked break in the zone border.
- `components[i][k].id` — globally unique slug; referenced by `connectors[].from/to`.
- `components[i][k].name` — `node-name` role (the human-readable label).
- `components[i][k].sub` — `sublabel` role at 10px in muted (the technical sub-label; up to 2 lines via auto-wrap when component height grows to 72).
- `components[i][k].icon` — any id from `references/primitive-icons.md`. If missing → no icon, the name shifts left. (Catalog has 41 icons; `mail` is currently missing — use `icon: file` as fallback for email hand-offs.)
- `components[i][k].kind` — `standard | focal | external`. `focal` triggers the accent palette (§5); `external` switches to a 4-2 dashed stroke and muted ink to signal "this is outside our scope."
- `components[i][k].color` — optional per-component color override (§4). Ignored on `kind: focal` (accent wins).
- `connectors[k].from` / `connectors[k].to` — refer to a component `id`. Cross-zone, cross-row, same-zone vertical, and same-zone horizontal all legal; routing chosen by §3.
- `connectors[k].label` — uppercase short text (≤ 8 chars). `arrow-label` role at 9px, weight 600.
- `connectors[k].icon` — optional inline icon to the left of the text. Same catalog as component icons.
- `connectors[k].style` — `neutral | link | accent`. Drives stroke color + marker.
- `connectors[k].dashed` — `true | false`.
- `footer[k]` — optional cross-cutting bar. Spans full canvas width minus margins. No connectors drawn from a footer.
- `legend[k].swatch` — `link | accent | dashed | focal | neutral`. Auto-curated based on what the diagram actually uses; user can re-order or rename.

---

## 2. Layout formulas — deterministic geometry

```
# Horizontal orientation (default)
left_pad        = 16
right_pad       = 16
zone_gap        = 20
zone_y          = 52
zone_h          = 360
n_zones         = len(zones)

# Zone widths: base 200 + 24 per component to give vertical room for icons + 2-line subs.
# In the canonical example (3 / 3 / 3 components) the replication used 256 / 360 / 272 —
# the formula approximates that with hand-picked widths in the worked YAML (§10).
zone_w(i)       = base + n_components_i * comp_slack             # base ≈ 200, slack ≈ 24
viewBox_w       = left_pad + Σ zone_w(i) + (n_zones-1) * zone_gap + right_pad

# Component placement within zone i
comp_pad_x      = 20                                              # x-inset from zone border
comp_h          = 56                                              # 68 for focal (2-line sub), 72 if both sub lines present
comp_gap        = 32
comp_y(i, k)    = zone_y + 28 + k * (comp_h + comp_gap)

# Component centerlines (used for connector routing)
comp_x(i)       = zone_x(i) + comp_pad_x
comp_w(i)       = zone_w(i) - 2 * comp_pad_x
comp_cx(i)      = comp_x(i) + comp_w(i)/2
comp_cy(i, k)   = comp_y(i, k) + comp_h/2

# Footer bars (if present)
footer_bar_h    = 56
footer_gap      = 8
footer_top      = zone_y + zone_h + 24
footer_y(k)     = footer_top + k * (footer_bar_h + footer_gap)
footer_bottom   = footer_top + N_footer * (footer_bar_h + footer_gap) - footer_gap

# Total canvas height
legend_block_h  = 40
content_bottom  = N_footer > 0 ? footer_bottom : zone_y + zone_h
viewBox_h       = content_bottom + legend_block_h + 24
```

### 2.1 Background and zone frame

Solid paper fill across `viewBox`. No dot pattern. Each zone box:

```svg
<rect x="zone_x(i)" y="zone_y" width="zone_w(i)" height="zone_h"
      fill="{ink @ 0.02}" stroke="{ink @ 0.10}" stroke-width="0.8" rx="8"/>
<!-- paper-masked break for the zone label -->
<rect x="zone_x(i)+20" y="zone_y-8" width="{label_w}" height="16" fill="{paper}"/>
<text x="zone_x(i)+24" y="zone_y+4" fill="{ink @ 0.40}"
      font-family="{eyebrow}" letter-spacing="0.14em">{name}</text>
```

### 2.2 Component box

Three visual kinds:

| `kind` | Fill | Stroke | Stroke width | Stroke dash | Name ink | Sub ink |
| --- | --- | --- | --- | --- | --- | --- |
| `standard` | `#FFFFFF` | `ink` | 1 | — | `ink` | `muted` |
| `focal` | `accent @ 0.07` | `accent` | 1.4 | — | `ink` | `accent` (line 1) + `muted` (line 2) |
| `external` | `#FFFFFF` | `muted` | 1 | `4,3` | `ink` | `muted` |

**Icon placement** (24×24, monochrome via `currentColor` — see `references/primitive-icons.md`):

```svg
<g transform="translate(comp_x + 12, comp_y + (comp_h - 24)/2)" color="{ink_for_kind}">
  <use href="#icon-{name}"/>            <!-- or inline the SVG path from the catalog -->
</g>
```

Icon takes 24 × 24 → 36-px total horizontal footprint with the 12-px left pad. Name and sub-label baseline shifts right by 40 px.

**Name + sub baselines** (left-aligned, with icon to the left):

```
name_x = comp_x + 44
name_y = comp_y + (comp_h/2) - 2
sub_y  = comp_y + (comp_h/2) + 14
```

### 2.3 Connector geometry (§3 holds the routing rules)

```
src_right  = comp_x(i_src) + comp_w(i_src)
src_left   = comp_x(i_src)
src_top    = comp_y(i_src, k_src)
src_bot    = src_top + comp_h_src
src_cy     = src_top + comp_h_src/2

dst_left   = comp_x(i_dst)
dst_right  = comp_x(i_dst) + comp_w(i_dst)
dst_top    = comp_y(i_dst, k_dst)
dst_bot    = dst_top + comp_h_dst
dst_cx     = comp_cx(i_dst)
dst_cy     = dst_top + comp_h_dst/2

# Corridor x for cross-zone H+Q+V routing
corridor_x = dst_cx                            # land arrow on dst horizontal center, enter via top/bot
```

### 2.4 Footer bar

```svg
<rect x="left_pad" y="footer_y(k)" width="viewBox_w - 2*left_pad" height="footer_bar_h"
      fill="{ink @ 0.03}" stroke="{ink @ 0.18}" stroke-width="0.8" rx="8"/>
<g transform="translate(left_pad + 20, footer_y(k) + (footer_bar_h - 24)/2)" color="{ink}">
  <use href="#icon-{name}"/>
</g>
<text x="left_pad + 56" y="footer_y(k) + 24" font-family="{node-name}" font-size="14" fill="{ink}">{name}</text>
<text x="left_pad + 56" y="footer_y(k) + 40" font-family="{sublabel}" font-size="12" fill="{muted}">{sub}</text>
```

Footer bars are layer-wide services. **No connectors emerge from them.** They sit visually below the zones and let the reader see the cross-cutting concerns at a glance.

### 2.5 Legend strip

Hairline divider at `y = content_bottom + 16`, then a row of swatches + labels at `y = content_bottom + 36`. Only the styles actually used by `connectors[]` (plus `focal` and `external` if those component kinds are present) appear in the legend.

---

## 3. Connector rules (mandatory)

### 3.1 Path shape — rounded right-angle Q-bezier, r = 8

Reused verbatim from `type-process.md` §3.1. No diagonals — ever.

```svg
<!-- Same zone, adjacent component (same vertical column): single vertical line -->
<line x1="{src_cx}" y1="{src_bot}" x2="{dst_cx}" y2="{dst_top}"
      stroke="…" stroke-width="…" marker-end="…"/>

<!-- Cross-zone or cross-row: exit right → H → Q-bend → V → enter top (or bottom) -->
<path d="M {src_right},{src_cy}  H {dst_cx - 8}  Q {dst_cx},{src_cy} {dst_cx},{src_cy ± 8}  V {dst_top_or_bottom}"
      fill="none" stroke="…" stroke-width="…" marker-end="…"/>
```

- Use `{src_cy + 8}` and `V {dst_top}` when destination lies BELOW source.
- Use `{src_cy − 8}` and `V {dst_bottom}` when destination lies ABOVE source.

### 3.2 Exit / entry sides (configurable; defaults below)

| Topology | Default exit side of source | Default entry side of destination |
| --- | --- | --- |
| Same zone, dst below | bottom | top |
| Same zone, dst above | top | bottom |
| Cross-zone, horizontal flow | right | top (or bottom, whichever is closer to src_cy) |
| Vertical-orientation diagram | bottom | top |

A connector can override via `connectors[k].from_side` / `connectors[k].to_side` (`top | right | bottom | left`). **Backward references** (right→left in horizontal orientation, up in vertical orientation) are permitted only when at least one endpoint has `kind: external`, and must be `dashed: true`.

### 3.3 Markers MUST touch the destination rectangle

The path's last command ends at the destination's rectangle edge (`V {dst_top}` or `H {dst_left}`), **not** at the centroid. After applying `refX=7` on the marker, the triangle sits flush against the border. Stopping the line short of the edge — or sending it to the centroid and burying the arrowhead inside the rect — is a hard fail.

### 3.4 Style → stroke + marker

| `style` | Stroke color | Stroke width | Marker |
| --- | --- | --- | --- |
| `neutral` | `muted` | 1.0 | `url(#arrow)` |
| `link` | `link` | 1.2 | `url(#arrow-link)` |
| `accent` | `accent` | 1.4 | `url(#arrow-accent)` |

Add `stroke-dasharray="4 3"` when `dashed: true`.

**Defs block** (always emit all three):

```svg
<defs>
  <marker id="arrow"        markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{muted}"/></marker>
  <marker id="arrow-link"   markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{link}"/></marker>
  <marker id="arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{accent}"/></marker>
</defs>
```

### 3.5 Connector label = inline icon + text, placed at the START of the connector with a perpendicular margin

The label sits **near the source end** of the connector (not at the mid-segment) and is **offset perpendicular to the line** so it never overlaps the stroke. Icon (when `icon:` is set) sits inside the label's paper-fill mask, to the left of the text.

```svg
<g transform="translate({label_cx}, {label_cy})">
  <rect x="-{w/2}" y="-9" width="{w}" height="18" rx="3" fill="{paper}" stroke="none"/>
  <use href="#icon-{icon}" x="-{w/2 + 4}" y="-6" width="12" height="12" color="{stroke_color}"/>     <!-- if icon set -->
  <text x="{icon ? (-(w/2) + 22) : 0}" y="3" text-anchor="{icon ? 'start' : 'middle'}"
        font-family="{arrow-label}" font-size="9" font-weight="600"
        letter-spacing="0.08em" fill="{stroke_color}">{label}</text>
</g>
```

**Placement formulas** (label box is 18px tall × `w` wide; centered on `{label_cx, label_cy}`):

| Segment exiting source | `label_cx` | `label_cy` | Effect |
| --- | --- | --- | --- |
| Horizontal (right exit) | `src_right + 6 + w/2` | `src_cy − 14` | Label sits 6 px past the source, 5 px above the line |
| Horizontal (left exit, backward) | `src_left − 6 − w/2` | `src_cy − 14` | Label sits 6 px before the source, 5 px above the line |
| Vertical (bottom exit) | `src_cx + 6 + w/2` | `src_bot + 14` | Label sits 6 px right of the line, 5 px below the source edge |
| Vertical (top exit, backward) | `src_cx + 6 + w/2` | `src_top − 14` | Label sits 6 px right of the line, 5 px above the source edge |

For cross-zone H+Q+V routes the label binds to the **horizontal** segment, since that segment is anchored at the source. Place the label early on that horizontal run — never on the Q-bend or the vertical tail.

- `w = text_w + (icon ? 30 : 12)` — auto-fit.
- Mask `fill` resolves to `paper` in light mode and `ink` in dark mode. The mask is kept as a safety pad — even though the label no longer sits on the line, it can graze zone backgrounds and component fills, and the mask preserves contrast.
- `stroke_color` follows §3.4 (text + icon inherit the connector's accent / link / neutral color).

### 3.6 Z-order

All connectors (paths + lines + labels) emit BEFORE any component rect, so node fills mask the line ends. The connector label is the exception — it draws AFTER its line so the mask sits on top.

---

## 4. Component color override (per-component `color: "#hex"`)

Per-component, same shape as every other parametric type in this skill.

| Element | Light | Dark |
| --- | --- | --- |
| Container fill | `rgba(C, 0.06)` | `rgba(C_light, 0.10)` |
| Container stroke | `rgba(C, 0.45)` (width 1) | `rgba(C_light, 0.55)` |
| Component name text | `C` | `C_light` |
| Icon glyph | inherits ink via `currentColor` (unchanged) | inherits ink (unchanged) |
| Sub-label | muted (unchanged) | muted (unchanged) |
| Connectors touching this component | **unchanged** — topology-driven | **unchanged** |

`C_light` = the same hex lightened ~15 % for dark-mode contrast (e.g., `#7a8c47` → `#9aac67`, `#b85450` → `#d97a78`).

**Rules:**
- **Never on focal components.** `kind: focal` always renders accent; `color` is silently ignored.
- **Never on connectors.** Connector style is topology-driven; if you want a colored edge, pick `style: accent` / `link` / `neutral`, not a component color.
- **Cap: ≤ 3 custom-colored components per diagram** (in addition to focal components). Above 3 the visual signal fragments.

**Recommended cross-type palette** (same as `type-medallion.md` / `type-process.md` / `type-dp-integration.md` / `type-dp-security-matrix.md`):

- `#b85450` rust-red — security / governance / pain-point that isn't focal
- `#5a7d9a` slate-blue — observability / quality / monitoring gate
- `#7a8c47` olive-green — survivor system (the one tool the new platform keeps)
- `#c9a23a` warm yellow — sandbox / dev / scratch
- `#8c6d3f` warm-brown — archive / cold / DR

---

## 5. Focal rule

- `kind: focal` components: **≤ 2 per diagram** (zero is also valid for diagrams without a single dominant pain-point).
- Auto-styling: accent stroke 1.4, accent-tinted fill 7 %, ink-bold `node-name`, accent line-1 `sublabel`.
- Any connector with a focal endpoint automatically renders in `style: accent`; the YAML `style:` is ignored.
- Custom `color: "#hex"` on a focal component is silently ignored — accent always wins.

If your diagram needs more than 2 focal components, you've collapsed two narratives. Split: one "collection pain-points" diagram + one "dissemination pain-points" diagram.

---

## 6. Dark mode

| Role | Light | Dark |
| --- | --- | --- |
| paper | `paper` | `ink` |
| ink | `ink` | `paper` |
| muted | `muted` | `muted` |
| accent | `accent` | `accent` |
| link | `link` | `link` |
| zone background | `ink @ 0.02` | `paper @ 0.04` |
| zone border | `ink @ 0.10` | `paper @ 0.14` |
| standard component fill | `#FFFFFF` | `paper @ 0.04` |
| standard component stroke | `ink` | `paper @ 0.32` |
| focal fill | `accent @ 0.07` | `accent @ 0.12` |
| focal stroke | `accent` | `accent` |
| external stroke | `muted` (dashed) | `muted` (dashed) |
| footer fill | `ink @ 0.03` | `paper @ 0.05` |
| footer stroke | `ink @ 0.18` | `paper @ 0.20` |
| label mask fill | `paper` | `ink` |
| custom-color components | `C` | `C_light` (≈ +15 %) |

---

## 7. Reproducibility checklist (taste gate)

Before emitting SVG, verify **every** item:

1. Eyebrow + title + subtitle present at canonical y-positions (24 / 36 / 52); body padding 32 px.
2. 2..4 zones; each has its uppercase label at the top-left of its zone box, on a paper-masked break in the border.
3. Every component has `id`, `name`. `sub`, `icon`, `kind`, `color` are optional.
4. ≤ 2 components with `kind: focal`; focal styling auto-applied (accent fill 7 %, accent stroke 1.4, italic line-1 sub).
5. Every connector exits the right (or bottom) of source and enters the top (or left) of destination; rounded right-angle Q-bezier `r=8` at every bend; marker triangle visibly touches the destination rectangle edge.
6. Connector labels sit at the **start** of the connector (not mid-segment) and are offset **perpendicular** to the line (5 px gap above for horizontal segments, 6 px gap to the right for vertical segments) — never overlapping the stroke. Paper-fill mask kept behind text; icon (when `icon:` is set) sits left of text inside the same mask.
7. ≤ 3 custom-colored components; none on focal.
8. ≤ 3 footer bars; each spans `viewBox_w − 2*left_pad`; no connectors emerge from any footer.
9. Legend at bottom: hairline separator + one swatch per style actually used.
10. `arrow-label` for connector labels, `eyebrow` for the page eyebrow and zone labels, `title` for the page title, `node-name` for the subtitle and component names, and `sublabel` for technical sub-labels.
11. Markers `#arrow` / `#arrow-link` / `#arrow-accent` defined once in `<defs>`; no inline marker definitions.
12. Dark variant: resolve every semantic token through its dark-mode value; custom colors are lightened ~15 %.

---

## 8. Anti-patterns

- **Diagonal arrows.** The NatStat replication has one (analyst → LegacyPortal). The new type forbids it — always rounded right-angle Q-bezier.
- **Marker not touching the target.** Path ends at the centroid or stops short of the border.
- **Inline `text` connector labels without a mask rect.** The connector line can bleed through the text and it becomes unreadable.
- **Labels sitting on top of the connector line, mid-segment.** Labels belong at the *start* of the connector with a perpendicular margin (see §3.5) — burying them in the middle of the line hides the source-to-destination direction and forces the reader's eye to fight the mask.
- **Tiny text badges as icons.** The source uses 7-px `DB` / `APP` / `EXT` badges; this type uses real 24-px catalog icons. Text badges are only acceptable as the label text, not as the component "icon."
- **Custom color on a focal component.** Focal always wins; user-set `color` silently ignored on `kind: focal`.
- **Footer bar wired to one component.** Footer = cross-cutting layer-wide concern; a connector from a footer to a specific component is a category error (use `type-dp-integration.md`'s AUTH-line pattern only when the footer service truly authenticates *all* components, and even then the line lands at the zone bottom edge, not at a specific tool).
- **> 16 total components or > 5 per zone.** Density cap; split into two diagrams.
- **Mixing orientations within one diagram.** Pick one — `horizontal` or `vertical` — and apply it to every zone.
- **Using `kind: focal` to flag every painful thing.** Focal exists for ≤ 2 narrative pain-points; for "this is bad but not headline-bad", use `color: "#b85450"` rust-red instead.

---

## 9. Examples

- `assets/example-it-state.html` — minimal light (NatStat canonical: 3 zones, 9 components, 8 connectors, 0 footer bars, SQL Server tinted olive). Gallery default.
- `assets/example-it-state-dark.html` — same, dark skin.
- `assets/example-it-state-full.html` — same, editorial-card frame with summary cards.
- `assets/example-it-state-extended.html` — exercises §4 color override + footer bars: 2 footer bars (Identity Manager + Observability) below the zones, third custom color on Analyst Machines (slate-blue, data-quality concern).
- `assets/example-it-state-extended-dark.html` — extended pattern, dark skin.

---

## 10. Worked YAML — full inputs for `example-it-state.html`

The complete inputs that map to the shipped canonical example. Every coordinate in that SVG is derivable from §2 applied to these inputs.

```yaml
title:    "Current IT Landscape"
subtitle: "Data pipeline before the platform"
eyebrow:  "NatStat · Before the platform"

orientation: horizontal

zones:
  - name: "COLLECTION"
    components:
      - { id: survey-solutions, name: "Survey Solutions", sub: "CAPI · PostgreSQL",          icon: postgres }
      - { id: aspnet,           name: "ASP.NET Apps",     sub: "migration · admin portals", icon: server   }
      - { id: civil-reg,        name: "Civil Registry",   sub: "external · CRVS data",      icon: database, kind: external }
  - name: "PROCESSING"
    components:
      - { id: shared-drive,  name: "Shared Drive",     sub: "No version control · Windows file share", icon: file,      kind: focal }
      - { id: analyst-mach,  name: "Analyst Machines", sub: "SPSS · SAS · Stata · Excel",              icon: desktop }
      - { id: sql-server,    name: "SQL Server",       sub: "on-premises · core RDBMS",                icon: sqlserver, color: "#7a8c47" }
  - name: "DISSEMINATION"
    components:
      - { id: legacy-portal,   name: "LegacyPortal",      sub: "manual bottleneck",     icon: cloud,    kind: focal }
      - { id: natstat-website, name: "NatStat Website",   sub: "public · static pages", icon: internet }
      - { id: ministry,        name: "Ministry Partners", sub: "~6 ministries",         icon: users,    kind: external }

connectors:
  - { from: survey-solutions, to: shared-drive,   label: "CSV",    icon: csv,   style: link }
  - { from: aspnet,           to: shared-drive,   label: "EMAIL",  icon: file,  style: link }
  - { from: civil-reg,        to: shared-drive,   label: "EXCEL",  icon: excel, style: link, dashed: true }
  - { from: shared-drive,     to: analyst-mach,   label: "COPY",                style: accent, dashed: true }
  - { from: analyst-mach,     to: sql-server,     label: "LOAD",                style: neutral }
  - { from: analyst-mach,     to: legacy-portal,   label: "EXCEL",  icon: excel, style: accent }
  - { from: legacy-portal,    to: natstat-website, label: "WEB",                 style: neutral }
  - { from: natstat-website,  to: ministry,        label: "CSV DL", icon: csv,   style: link, dashed: true }

dark: false
```

### 10.1 What this YAML proves

- `n_zones = 3`, components per zone `= [3, 3, 3]`, custom color count = 1 (SQL Server), focal count = 2 (Shared Drive, LegacyPortal), external count = 2 (Civil Registry, Ministry Partners).
- Zone widths in canonical: 256 / 360 / 272 ⇒ `viewBox_w = 16 + 256 + 20 + 360 + 20 + 272 + 16 = 960` ✓
- `viewBox_h = 52 + 360 + 40 + 24 = 500` (no footer bars) ✓
- Shared Drive (focal) at zone 2, row 0: `x = 340, y = 80, w = 264, h = 68` (focal stretches to 68 to fit 2-line sub) ✓
- LegacyPortal (focal) at zone 3, row 0: `x = 704, y = 80, w = 208, h = 60` ✓
- SQL Server (custom olive) at zone 2, row 2: container fill `rgba(122,140,71,0.06)`, stroke `rgba(122,140,71,0.45)`, name text `#7a8c47` ✓
- Connectors 4, 5 (within zone 2) and 7, 8 (within zone 3) are simple vertical `<line>` elements. Cross-zone connectors take rule-compliant routes (see SKILL.md §6 rules 4 & 5):
  - **All three Survey-side → Shared Drive connectors (C1 / C2 / C3) enter Shared Drive's LEFT edge.** A top-edge entry would push the marker body (7 px back along travel, given `refX = 7`) *inside* the destination box, where the box's paper-fill mask hides it — only a 1-pixel tip would peek above the stroke. Entering the left edge with a right-going path keeps the body outside the box and the arrow visible (~7 px shown to the left of the box edge). The three left-edge attach points are fanned at **y = 108 / 124 / 140** (16-px spacing, well above the 12 px rule-4 minimum).
  - **C1** (Survey → Shared Drive) source y matches landing y: single horizontal `M 252,108 H 340`. No bends needed.
  - **C2** (ASP.NET → Shared Drive) detours up through zone-2 background — vertical at `x = 316` (clear of Shared Drive's left edge at `x = 340`): `H 308 Q 316,196 316,188 V 132 Q 316,124 324,124 H 340`. Lands at `(340, 124)`.
  - **C3** (Civil Registry → Shared Drive) detours up through zone-2 background — vertical at `x = 332` (clear of Analyst Machines, which starts at `x = 340`): `H 324 Q 332,284 332,276 V 148 Q 332,140 340,140`. Lands at `(340, 140)` via a final Q-bend (no trailing H needed).
  - **C6** (Analyst Machines → LegacyPortal) cannot use a direct H+Q+V into LegacyPortal's left edge — Analyst Machines and LegacyPortal are in different rows, and the direct horizontal at `y = 268` would cross NatStat Website. It detours through the zone gap and **over** LegacyPortal: `H 654 Q 662,268 662,260 V 72 Q 662,64 670,64 H 800 Q 808,64 808,72 V 80` — vertical at `x = 662` (in zone gap), horizontal at `y = 64` (above LegacyPortal top), then down into LegacyPortal's top center. The path enters LegacyPortal from **above** going down, so the arrow body lives above the box (visible) and only the 1-px tip enters the box.

**Marker-visibility rule of thumb:** with the standard arrow marker (`markerWidth = 8`, `refX = 7`), the arrow body extends 7 px *backwards* along the path direction from the endpoint. For the arrow to remain visible, that 7-px tail must sit *outside* the destination box. Translation:
- Entering a **TOP edge going UP** (path direction up, box below) → body inside box, **only 1 px visible. Avoid this.**
- Entering a **TOP edge going DOWN** (path direction down, box below) → body above box, ~7 px visible. ✓
- Entering a **LEFT edge going RIGHT** → body to the left of box, ~7 px visible. ✓
- Entering a **RIGHT edge going LEFT** → body to the right of box, ~7 px visible. ✓
- Entering a **BOTTOM edge going DOWN** (box above) → body inside box, **only 1 px visible. Avoid this.**
- Entering a **BOTTOM edge going UP** (box above) → body below box, ~7 px visible. ✓

When the source row matches the destination row's y range (e.g., Survey at y=108 with Shared Drive at y=80–148), prefer **side-edge** entry — a single horizontal path with a fully visible arrow. When the source row is offset, detour through the destination's nearest zone background to enter a side edge rather than approaching a top/bottom edge from the wrong side.

The extended example (§9 line 4) demonstrates footer bars + a third custom color and proves `viewBox_h` grows correctly when `N_footer > 0`.
