# DP security matrix

**Best for:** documenting per-role / per-component access permissions for a data platform — a grid where each row is a platform component (Keycloak, MinIO bucket, Trino catalog, JupyterHub, NiFi, …) and each column is a role / AD group (Data Administrators, Data Engineers, Data Scientists, Data Consumers, …). Each intersection cell holds a permission value (Admin / Full / R/W / Read / SELECT / Login / No access) with a visual category that matches the permission level. One cell may be marked focal to flag a critical access rule (e.g., "Data Consumers can ONLY `SELECT` from the aggregated catalog — sole consumer access").

Use when stakeholders need to audit *who can do what* across the platform. Prefer **DP integration** when the question is *who can talk to what* (topology/protocol) rather than *who can write/read what* (permissions).

This type is **parametric** — the inputs schema in §1 drives every coordinate via the formulas in §2. The rule shape mirrors `type-medallion.md` / `type-process.md` / `type-data-flow.md` so the focal rule, color override, dark mode, and reproducibility checklist read identically across types.

---

## 1. Inputs — the parameter contract

```yaml
title:    "Platform Access Matrix"
subtitle: "Four canonical groups × platform components"

roles:                                  # 2..6 columns, ordered left → right
  - { name: "Data Administrators", code: "DL-DataAdmins"      }
  - { name: "Data Engineers",      code: "DL-DataEngineers"   }
  - { name: "Data Scientists",     code: "DL-DataScientists"  }
  - { name: "Data Consumers",      code: "DL-DataConsumers"   }

components:                             # 2..14 rows, ordered top → bottom
  - { name: "Keycloak",                          hint: "SSO" }   # `hint` = right-aligned aside in label cell
  - { name: "MinIO · raw bucket" }
  - { name: "MinIO · anon · staging · agg" }
  - { name: "Trino · raw catalog" }
  - { name: "Trino · anon-staging" }
  - { name: "Trino · aggregated" }
  - { name: "JupyterHub" }
  - { name: "NiFi" }

cells:                                  # explicit (row, col) entries; omitted → defaults to "none"
  # value = displayed text (free-form)
  # level = visual category: full | rw | read | none  (closed vocabulary, drives styling)
  # focal: true (max 1)            — overrides level to focal styling
  # sub: "second-line text"        — used inside focal cell
  # color: "#hex"                  — optional per-cell color override (§4)
  - { row: 0, col: 0, value: "Admin", level: "full" }
  - { row: 0, col: 1, value: "Login", level: "read" }
  - { row: 0, col: 2, value: "Login", level: "read" }
  - { row: 0, col: 3, value: "Login", level: "read" }

  - { row: 1, col: 0, value: "Full",       level: "full" }
  - { row: 1, col: 1, value: "R/W",        level: "rw"   }
  - { row: 1, col: 2, value: "No access",  level: "none" }
  - { row: 1, col: 3, value: "No access",  level: "none" }

  # ... rows 2..4 follow the same pattern ...

  - { row: 5, col: 0, value: "Full",       level: "full" }
  - { row: 5, col: 1, value: "R/W",        level: "rw"   }
  - { row: 5, col: 2, value: "SELECT",     level: "read" }
  - { row: 5, col: 3, value: "SELECT only", sub: "sole consumer access", focal: true }

  # ... rows 6..7 ...

none_label: "No access"                 # default text rendered when a cell is omitted
dark: false
```

**Reserved field semantics:**
- `roles[j].name` — primary role label (Montserrat, 11px, white text on navy banner)
- `roles[j].code` — secondary AD-group identifier (JetBrains Mono, 9px, white text at 0.85 opacity)
- `components[i].hint` — optional right-aligned mono text in the label cell (e.g., `"SSO"`, `"S3 API"`)
- `cells[k].level` — closed vocabulary `full | rw | read | none`. Drives fill/stroke/text-color per §2.4.
- `cells[k].value` — free-form display text. Domain-specific labels (`"R/W"`, `"SELECT"`, `"Login"`) work without inventing new levels.
- `cells[k].focal: true` — exactly **one** cell may declare this. Overrides `level` to focal styling.
- `cells[k].sub` — optional 2nd-line text (used with focal). Renders at 8px mono below the primary value.
- `cells[k].color: "#hex"` — optional per-cell color override (§4).

---

## 2. Layout formulas — deterministic geometry

```
# Constants
left_pad         = 12
right_pad        = 48
comp_col_w       = 208
comp_role_gap    = 12
role_col_w       = 148
role_col_gap     = 16
header_h         = 52
row_h            = 36
row_stride       = 40

# Counts
n_roles          = len(roles)        # 2..6
n_components     = len(components)   # 2..14

# Canvas
viewBox_w        = left_pad + comp_col_w + comp_role_gap
                   + n_roles * role_col_w + (n_roles - 1) * role_col_gap
                   + right_pad
                   # 4 roles → 12 + 208 + 12 + 592 + 48 + 48 = 920

header_y         = 72
row_y(k)         = 140 + k * row_stride                  # 140, 180, 220, ...
rows_bottom      = row_y(n_components - 1) + row_h       # 8 rows → 456
legend_y_top     = rows_bottom + 20                      # 476 for 8-row canonical
viewBox_h        = legend_y_top + 44                     # 520 for 8-row canonical

# Column positions
comp_col_x       = left_pad                                                       # 12
role_col_x(j)    = left_pad + comp_col_w + comp_role_gap
                   + j * (role_col_w + role_col_gap)
                                                                                  # 232, 396, 560, 724
role_col_cx(j)   = role_col_x(j) + role_col_w / 2                                 # 306, 470, 634, 798
```

### 2.1 Background

Solid paper fill across the full viewBox. No dot pattern.

### 2.2 Header row (`y = 72, h = 52`)

**Component-column header cell:**
- Rect: `(comp_col_x, header_y, comp_col_w, header_h)`, fill white, stroke `rgba(11,31,56,0.12)` 0.8, `rx=6`
- Two-line label centered at `(comp_col_x + comp_col_w/2, header_y+24)` and `(…, header_y+40)`:
  - Line 1: `"Component"` — Montserrat 11, weight 600, ink
  - Line 2: `"vs. AD group"` — JetBrains Mono 9, muted

**Role banners (one per role):**
- Rect: `(role_col_x(j), header_y, role_col_w, header_h)`, fill `#0F3D6E` (D4N navy), `rx=6`
- Two-line label centered:
  - Line 1 at `y=92`: `roles[j].name` — Montserrat 11, weight 600, white
  - Line 2 at `y=108`: `roles[j].code` — JetBrains Mono 9, white at opacity 0.85

### 2.3 Data row (`y = row_y(k), h = 36`)

**Component label cell:**
- Rect: `(comp_col_x, row_y(k), comp_col_w, row_h)`, fill white, stroke `rgba(11,31,56,0.12)` 0.8, `rx=4`
- Name at `(comp_col_x + 12, row_y(k) + 22)`: Montserrat 11, weight 600, ink, left-aligned
- Hint (if present) at `(comp_col_x + comp_col_w − 12, row_y(k) + 22)`: JetBrains Mono 9, muted, right-aligned

**Value cells (one per role × component):**
- Rect: `(role_col_x(j), row_y(k), role_col_w, row_h)`, `rx=4`, stroke `rgba(11,31,56,0.12)` 0.6
- Fill and text-color depend on `level` (or focal flag) — see §2.4
- Value text centered at `(role_col_cx(j), row_y(k) + 22)`: Montserrat 10
- Focal cell uses a slightly raised primary text at `y=18` and a sub-line at `y=30` (JetBrains Mono 8)

### 2.4 Cell style table

| `level` | Fill | Stroke | Text color | Text weight |
|---|---|---|---|---|
| `full` | `rgba(11,31,56,0.08)` | `rgba(11,31,56,0.12)` | `#0B1F38` (ink) | 600 |
| `rw` | `#FFFFFF` | `rgba(11,31,56,0.12)` | `#0B1F38` (ink) | 400 |
| `read` | `rgba(90,107,130,0.08)` | `rgba(11,31,56,0.12)` | `#5A6B82` (muted) | 400 |
| `none` | `#F4F6FA` (paper) | `rgba(11,31,56,0.12)` | `#8A99AE` (soft) | 400 |
| **focal** | `rgba(230,53,88,0.07)` | `#E63558` (1.4) | `#E63558` (accent) | 600 |

The focal cell can carry a 2nd line (`sub:`) rendered in `#E63558` JetBrains Mono 8 at 0.85 opacity.

### 2.5 Legend (`y_top = legend_y_top, h ≈ 30`)

Hairline separator at `legend_y_top`. Below the separator, one row of style swatches with their labels — only the styles actually used in the diagram appear in the legend.

- "LEGEND" eyebrow at `(left_pad, legend_y_top + 20)`: JetBrains Mono 8, muted, letter-spacing 0.14em
- Each style: swatch rect (14×12 `rx=2`) followed by a JetBrains Mono 9 label
- Item x-positions are tabulated left-to-right with ~120-px stride; legend wraps onto a second visual row only if `n_roles ≥ 6` (otherwise fits in one line)

---

## 3. Cells, not connectors

A matrix diagram has **no connectors** — there are no arrows between cells, no flow lines. The diagram's information is entirely in the cell content + cell styling. The only "connector-like" element is the focal cell's accent border, which visually "calls out" a specific intersection.

Cells emit **no edges**. Don't add arrows pointing into cells or between cells — they belong in a different diagram type.

---

## 4. Color overrides

Three independent override axes — per-cell, per-component (row), per-role (column). All optional, all use the same `color: "#hex"` field, all draw from the same recommended palette. Mirrors §3.4 of `type-high-level.md`, §4 of `type-process.md`, §4 of `type-medallion.md`.

### 4.1 Per-cell `color`

Tints a specific intersection cell. Applied to:

| Element | Light | Dark |
|---|---|---|
| Cell fill | `rgba(C, 0.08)` | `rgba(C_light, 0.12)` |
| Cell stroke | `rgba(C, 0.45)` width 1.0 | `rgba(C_light, 0.55)` width 1.0 |
| Value text | `C` | `C_light` |
| Sub text (if present) | `rgba(C, 0.85)` | `rgba(C_light, 0.95)` |

`C_light` = the same hex lightened ~15% for dark-mode contrast.

### 4.2 Per-component `color`  (`components[i].color`)

Tints the row's **label cell only** (left column). The data cells in that row keep their per-cell `level` styling — the row color flags *what* this component is, not *what permissions live in it*.

| Element | Light | Dark |
|---|---|---|
| Label cell fill | `rgba(C, 0.06)` | `rgba(C_light, 0.10)` |
| Label cell stroke | `rgba(C, 0.45)` width 0.8 | `rgba(C_light, 0.55)` width 0.8 |
| Component name | `C` | `C_light` |
| Hint text | unchanged (muted) | unchanged (muted) |

### 4.3 Per-role `color`  (`roles[j].color`)

Tints the **column banner only** (top row). Cells underneath keep their `level` styling. Replaces the default navy banner fill with the chosen hex.

| Element | Light & Dark (banner is the same in both modes) |
|---|---|
| Banner fill | `C` |
| Role name + code text | `#FFFFFF` if `C` is dark (luminance ≤ 0.5), else `#0B1F38` |

If you pick a mid-luminance hex (e.g., yellow `#c9a23a`), the text auto-flips to ink for contrast. Pair `roles[j].text_color: "#hex"` to override this auto-pick.

### 4.4 Rules

- **Focal cell wins.** A focal cell ignores `color` overrides — accent always.
- **Per-cell `color` overrides `level` styling** for that one cell.
- **Per-component / per-role overrides are scoped:** component → row label only; role → banner only. They do **not** spread into the matrix body. To flag a specific intersection, use per-cell.
- **Cap:** keep total custom-colored entities ≤ 5 per diagram (combining cells + components + roles). Above 5, the matrix reads as colored noise — split into multiple diagrams or rethink which color carries which concern.

### 4.5 Recommended palette (same as the other parametric types)

- `#b85450` rust-red — Security elevation / break-glass / SoX-flagged
- `#5a7d9a` slate-blue — Quality / monitoring / observability gate
- `#7a8c47` olive-green — Approved / governance-cleared / publication-ready
- `#c9a23a` warm yellow — Working / sandbox / data-scientist zone
- `#8c6d3f` warm-brown — Archive / cold / DR

---

## 5. Focal rule

Exactly **one** focal cell per diagram (or zero). The focal cell:
- Uses focal styling (accent fill + accent stroke 1.4 + accent text bold)
- May carry a 2-line content: primary `value` at `y = row_y(k) + 18`, `sub` at `y = row_y(k) + 30`
- Calls out the diagram's central security claim — the *one* access rule that distinguishes this platform's posture from a generic permissions table

If zero or >1 `focal: true` cells are declared, halt and ask the user.

---

## 6. Dark mode

| Token | Light | Dark |
|---|---|---|
| Paper | `#F4F6FA` | `#0B1F38` |
| Ink | `#0B1F38` | `#F4F6FA` |
| Muted | `#5A6B82` | `#8A99AE` |
| Soft (no-access text) | `#8A99AE` | `#5A6B82` |
| Accent | `#E63558` | `#EE5570` |
| Role-banner fill | `#0F3D6E` (D4N navy) | `#0F3D6E` (unchanged — contrasts both light and dark paper) |
| Header / row stroke | `rgba(11,31,56,0.12)` | `rgba(244,246,250,0.18)` |
| Full / Admin fill | `rgba(11,31,56,0.08)` | `rgba(244,246,250,0.10)` |
| R/W fill | `#FFFFFF` | `rgba(244,246,250,0.06)` |
| Read fill | `rgba(90,107,130,0.08)` | `rgba(138,153,174,0.12)` |
| No-access fill | `#F4F6FA` | `rgba(244,246,250,0.02)` |
| Focal fill | `rgba(230,53,88,0.07)` | `rgba(238,85,112,0.12)` |
| Focal stroke | `#E63558` | `#EE5570` |
| Custom component colors | `C` | `C_light` (lighten ~15%) |

---

## 7. Reproducibility checklist (taste gate)

Before emitting SVG, verify **every** item:

1. `viewBox = "0 0 {viewBox_w} {viewBox_h}"` derived via §2 (4 roles × 8 components → 920 × 520).
2. Header row at `y=72 h=52`. Component header cell white-filled with two-line `Component / vs. AD group` label. Role banners filled `#0F3D6E` with name + AD-group code in white.
3. Data rows start at `y=140`, stride 40, height 36. `rows_bottom = 140 + (n_components−1)·40 + 36`.
4. Component label cell `rx=4`, name left-aligned at `x=24`, optional `hint` right-aligned at `x = comp_col_x + comp_col_w − 12`.
5. Every value cell `rx=4`, stroke `rgba(11,31,56,0.12)` 0.6, fill + text matching §2.4 for its `level`.
6. Exactly **one** focal cell (or zero). Focal cell stroke `#E63558` width 1.4. Primary value at `y = row_y(k) + 18`; `sub` (if present) at `y = row_y(k) + 30`.
7. Cells omitted from `cells:` render as `level: "none"` with `none_label` text (default `"No access"`).
8. Custom-colored cells ≤ 2 (in addition to the focal cell).
9. No connector elements anywhere in the SVG.
10. Legend strip at `legend_y_top`, one swatch per `level` actually used, hairline separator above.
11. `viewBox_h` grows with `n_components`; `viewBox_w` grows with `n_roles`.

---

## 8. Anti-patterns

- **More than one focal cell** — focal exists to mark *the* critical access rule; >1 erases the signal.
- **Connectors anywhere** — matrix is value-driven; arrows belong in DP integration / process diagrams.
- **Freeform `level` values** — closed vocabulary is `full | rw | read | none`. Use `value` for free-form displayed text + `color` override for arbitrary tinting.
- **Per-row or per-column color tints** — apply `color` per cell only. Whole-row or whole-column highlighting tends to over-emphasize and collapses the matrix into a list.
- **Using `none_label` as a placeholder for "TBD"** — `none` means *no access*. If the permission is unknown, leave the cell empty in inputs but document it elsewhere; don't render an ambiguous state.
- **More than 6 roles** — split into two matrices (e.g., human roles vs service accounts) before exceeding 6 columns.
- **More than 14 components** — split by domain (storage / compute / observability / governance) before exceeding 14 rows.
- **Using the matrix to document *how* permissions are granted** — that belongs in a process or sequence diagram. The matrix shows *what* each role can do, not the grant flow.

---

## 9. Examples

- `assets/example-dp-security-matrix.html` — minimal light (STATIN canonical: 4 roles × 8 components, focal at Data Consumers × Trino aggregated). Gallery default.
- `assets/example-dp-security-matrix-dark.html` — same, dark skin.
- `assets/example-dp-security-matrix-full.html` — same, editorial-card frame with subtitle + summary cards.

---

## 10. Worked YAML — full inputs for `example-dp-security-matrix.html`

The complete inputs that map to the shipped canonical example. Every coordinate in that SVG is derivable from §2 applied to these inputs.

```yaml
title:    "Platform Access Matrix"
subtitle: "Four canonical groups × platform components"

roles:
  - { name: "Data Administrators", code: "DL-DataAdmins"      }
  - { name: "Data Engineers",      code: "DL-DataEngineers"   }
  - { name: "Data Scientists",     code: "DL-DataScientists"  }
  - { name: "Data Consumers",      code: "DL-DataConsumers"   }

components:
  - { name: "Keycloak",                          hint: "SSO" }
  - { name: "MinIO · raw bucket" }
  - { name: "MinIO · anon · staging · agg" }
  - { name: "Trino · raw catalog" }
  - { name: "Trino · anon-staging" }
  - { name: "Trino · aggregated" }
  - { name: "JupyterHub" }
  - { name: "NiFi" }

cells:
  # Row 0 — Keycloak
  - { row: 0, col: 0, value: "Admin", level: "full" }
  - { row: 0, col: 1, value: "Login", level: "read" }
  - { row: 0, col: 2, value: "Login", level: "read" }
  - { row: 0, col: 3, value: "Login", level: "read" }
  # Row 1 — MinIO raw
  - { row: 1, col: 0, value: "Full", level: "full" }
  - { row: 1, col: 1, value: "R/W",  level: "rw"   }
  - { row: 1, col: 2, value: "No access", level: "none" }
  - { row: 1, col: 3, value: "No access", level: "none" }
  # Row 2 — MinIO anon/staging/agg
  - { row: 2, col: 0, value: "Full", level: "full" }
  - { row: 2, col: 1, value: "R/W",  level: "rw"   }
  - { row: 2, col: 2, value: "Read", level: "read" }
  - { row: 2, col: 3, value: "No access", level: "none" }
  # Row 3 — Trino raw catalog
  - { row: 3, col: 0, value: "Full", level: "full" }
  - { row: 3, col: 1, value: "R/W",  level: "rw"   }
  - { row: 3, col: 2, value: "No access", level: "none" }
  - { row: 3, col: 3, value: "No access", level: "none" }
  # Row 4 — Trino anon-staging
  - { row: 4, col: 0, value: "Full",   level: "full" }
  - { row: 4, col: 1, value: "R/W",    level: "rw"   }
  - { row: 4, col: 2, value: "SELECT", level: "read" }
  - { row: 4, col: 3, value: "No access", level: "none" }
  # Row 5 — Trino aggregated (focal cell at col 3)
  - { row: 5, col: 0, value: "Full",        level: "full" }
  - { row: 5, col: 1, value: "R/W",         level: "rw"   }
  - { row: 5, col: 2, value: "SELECT",      level: "read" }
  - { row: 5, col: 3, value: "SELECT only", sub: "sole consumer access", focal: true }
  # Row 6 — JupyterHub
  - { row: 6, col: 0, value: "Admin", level: "full" }
  - { row: 6, col: 1, value: "R/W",   level: "rw"   }
  - { row: 6, col: 2, value: "R/W",   level: "rw"   }
  - { row: 6, col: 3, value: "No access", level: "none" }
  # Row 7 — NiFi
  - { row: 7, col: 0, value: "Admin", level: "full" }
  - { row: 7, col: 1, value: "R/W",   level: "rw"   }
  - { row: 7, col: 2, value: "Read",  level: "read" }
  - { row: 7, col: 3, value: "No access", level: "none" }

dark: false
```

### 10.1 What this YAML proves

Run §2 with these inputs:
- `n_roles = 4`, `n_components = 8`, no color overrides, one focal cell.
- `viewBox_w = 12 + 208 + 12 + 4·148 + 3·16 + 48 = 920` ✓
- `row_y(k)` produces `140, 180, 220, 260, 300, 340, 380, 420` ✓
- `rows_bottom = 420 + 36 = 456`; `legend_y_top = 476`; `viewBox_h = 520` ✓
- `role_col_x(j) = [232, 396, 560, 724]` ✓
- Focal cell at `(row=5, col=3)` → rect `(724, 340, 148, 36)` with accent stroke 1.4 ✓

A fresh generation from this YAML produces a diagram visually indistinguishable from the shipped `example-dp-security-matrix.html`.
