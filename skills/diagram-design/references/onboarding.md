# Onboarding — generate your skin from a design source

**Goal:** point the skill at a design source — a website, an installed skill, or a local folder — and have it extract the palette + typography, then rewrite `style-guide.md` so every future diagram inherits that skin.

Takes about 60 seconds.

Three source methods are supported. Jump to the relevant section:

- [§ URL](#url) — fetch a live website
- [§ Skill](#skill) — read an installed Claude Code skill that carries design tokens
- [§ Folder](#folder) — read a local design-system directory (CSS, JSON, Markdown)

---

## The flow (all methods)

```
Source you provide (URL / skill name / folder path)
      ↓
[1] read / fetch the source
      ↓
[2] extract dominant colors + fonts
      ↓
[3] map to semantic roles (paper, ink, muted, accent, …)
      ↓
[4] propose a style-guide.md diff
      ↓
[5] write the diff (with your approval)
      ↓
future diagrams use your tokens
```

---

---

## § URL

### Invocation

> *"Onboard Schematic to my site — `https://example.com`"*

---

### Step 1 — fetch the page

Use `agent-browser` (preferred) or a plain `fetch`. If the site has multiple pages worth sampling (landing + blog + product), fetch 2–3 and merge the palette signals.

```bash
agent-browser navigate https://example.com --screenshot out.png --html out.html
```

---

## Step 2 — extract colors and fonts

### Colors

Parse the rendered CSS and screenshot:

- **Background color** of `<body>` or the dominant large region → `paper`
- **Primary text color** (body text) → `ink`
- **Secondary text color** (captions, meta) → `muted`
- **Most-used brand color** (CTA button, link, heading accent) → `accent`
- **Container / card background** slightly darker than paper → `paper-2`
- **Border / hairline color** → `rule` (convert to rgba of ink at ~0.12 opacity)

Prefer CSS custom properties when the site exposes them (`:root { --accent: …; }`). Otherwise pull via rendered `getComputedStyle` samples or a color-histogram pass over the screenshot.

### Fonts

Read the rendered `font-family` stack of:

- `<h1>` → `title` family
- `<body>` → `node-name` family  
- `<code>`, `<pre>`, or any mono-styled element → `sublabel` family

If the site has only one family, keep the schematic defaults for the missing roles (Instrument Serif for title, Geist Mono for mono). Don't force-pick a mono font that isn't on the site.

---

## Step 3 — map to semantic roles

Propose a diff by filling this table:

| Role | Detected | Confidence |
|---|---|---|
| paper | `#f8f6f0` | high |
| ink | `#111111` | high |
| muted | `#6b6b68` | medium |
| accent | `#c73a2b` | high |
| … | … | … |

Flag low-confidence guesses so the user can correct before applying.

### Constraint checks

Before writing, validate:

- **AA contrast**: `ink` on `paper` ≥ 4.5:1. `muted` on `paper` ≥ 4.5:1 for body text.
- **Accent is the most saturated color**: not muted-ish, not near-grey.
- **paper ≠ pure white**: if the site uses `#ffffff`, fall back to `#fafaf7` to preserve Schematic's warm-neutral feel — or ask the user to confirm pure-white is intentional.

If any check fails, propose an adjusted value and explain why.

---

## Step 4 — preview the diff

Show the user what will change in `style-guide.md`. Only the tokens table — everything else stays the same.

```diff
-| `paper`  | `#f5f4ed` | `#1c1a17` |
-| `ink`    | `#0b0d0b` | `#f1efe7` |
-| `accent` | `#f7591f` | `#ff6a30` |
+| `paper`  | `#f8f6f0` | `#1a1815` |
+| `ink`    | `#111111` | `#efeee7` |
+| `accent` | `#c73a2b` | `#e05440` |
```

Also regenerate the dark variant via the inversion rule (`rgba(11,13,11, X)` → `rgba(ink-rgb, X)`).

---

## Step 5 — apply

Write the new tokens to `style-guide.md`. Suggest running the `/regenerate-examples` flow (if it exists) or rebuilding one example to verify the new skin reads cleanly.

After onboarding, the user should:

1. Open `assets/index.html` (gallery) and confirm the new palette feels coherent across all 26 types.
2. If any type looks off, they usually need to tune `muted` (often too dark or too light against the new `paper`).

---

## When URL onboarding fails

- **Site uses webfonts you can't replicate** (custom-hosted, paid): keep the schematic defaults for typography and skin only the colors.
- **Brand has 6+ colors** and you can't identify a clear hierarchy: pick one as `accent`, demote the rest to `muted` variants or ignore them. The schematic grammar only uses 5–7 roles.
- **Site is dark-mode first**: flip the inversion — treat their dark paper as the default `paper`, and generate a light variant via inversion.
- **Homepage is all imagery, no text**: ask for a blog or docs URL instead — text-heavy pages expose the type hierarchy.

---

## § Skill

Extract tokens from an installed Claude Code skill that carries its own design system (e.g. a `brand-design` or `ui-kit` skill).

### Invocation

> *"Onboard Schematic from my `data4now-design` skill"*

Or the gate offers this as option (b) and the user names the skill.

### Step 1 — locate the skill

Search for the skill in order:

1. `~/.claude/skills/<skill-name>/` (user install)
2. `.claude/skills/<skill-name>/` (project install)
3. Any path the user provides explicitly

If not found, ask the user to confirm the skill name or provide the path.

### Step 2 — read token sources

Glob the skill directory for any of these files and read them all:

| Priority | Pattern | What to look for |
|---|---|---|
| 1 | `*.css`, `colors*.css`, `tokens.css` | CSS custom properties in `:root { --color-*: …; }` |
| 2 | `tokens.json`, `design-tokens.json`, `*.tokens.json` | Style Dictionary / Figma token JSON |
| 3 | `SKILL.md`, `README.md` | Markdown tables listing colors, fonts, hex values |
| 4 | `style-guide.md`, `*design*.md` | Any narrative design documentation |
| 5 | `*.html` (preview/example files) | Inline `<style>` blocks — scan `:root` and `body` rules |

Read all matches and merge — CSS custom properties take priority over inferred values from HTML.

### Step 3 — extract colors and fonts

**From CSS custom properties:**
Map variable names to semantic roles using name-heuristics:

| If the variable name contains… | Map to role |
|---|---|
| `background`, `bg`, `paper`, `surface`, `canvas` | `paper` |
| `foreground`, `text`, `body`, `ink`, `on-surface` | `ink` |
| `muted`, `subtle`, `secondary`, `caption` | `muted` |
| `accent`, `brand`, `primary`, `cta`, `highlight` | `accent` |
| `border`, `rule`, `divider`, `outline` | `rule` |
| `mono`, `code`, `pre` | `sublabel` font |

**From JSON tokens:** follow the same heuristics on key names. If the JSON follows Style Dictionary format (`{ "color": { "brand": { "value": "#…" } } }`), flatten the path and apply heuristics to the leaf key.

**From Markdown tables:** look for rows with hex values (`#rrggbb`) adjacent to role-like words. A row like `| accent | #eb6c36 |` maps directly.

**Fonts:** look for `font-family` rules, `@import` or `@font-face` declarations, and Markdown mentions of font names alongside size/weight.

### Step 4 — map, validate, propose diff

Same as the URL method: fill the role table, run contrast checks, show the diff, ask for approval before writing.

### When skill extraction is ambiguous

- **Skill has no CSS or token files**: fall back to reading all `.md` files and look for hex values mentioned in prose. Surface what you found and ask the user to confirm mappings before applying.
- **Multiple accent candidates**: list them and ask the user to pick one. Don't guess.
- **Skill is dark-mode first**: ask whether to treat the dark values as the `paper`/`ink` defaults or to invert.

---

## § Folder

Extract tokens from a local directory — a checked-out design system repo, a Figma export, or any folder the user points you at.

### Invocation

> *"Onboard Schematic from my design system at `~/projects/brand/design-tokens/`"*

Or the gate offers this as option (c) and the user provides the path.

### Step 1 — discover files

Glob the folder (recursively, up to 3 levels deep) for:

```
**/*.css
**/*.scss        (read @forward / $variable declarations)
**/tokens.json
**/*.tokens.json
**/design-tokens.json
**/colors.json
**/*style-guide*.md
**/*design-system*.md
**/README.md
**/*.html        (scan <style> blocks only)
```

If the result set is large (>20 files), prefer files in the root and files whose names contain `color`, `token`, `brand`, `palette`, `style`, or `theme`.

### Step 2 — read and merge

Read every discovered file. Apply the same extraction logic as the Skill method (§ Skill → Step 3). CSS custom properties and JSON tokens take priority over inferred values from prose.

**SCSS variables:** treat `$variable-name: value;` the same as a CSS custom property — apply name heuristics to `$variable-name`.

**Figma token JSON** (Figma Tokens Plugin format):

```json
{ "colors": { "brand": { "primary": { "value": "#eb6c36", "type": "color" } } } }
```

Walk the tree; the leaf `value` fields are the colors, the path segments supply the role heuristic.

### Step 3 — map, validate, propose diff

Same as the URL method: run contrast checks, show the full diff against current `style-guide.md`, and write only after the user approves.

### When folder extraction is ambiguous

- **No structured token files, only prose docs**: read every `.md` in the root and extract hex values found near role-like words. Show the user a table of what you inferred — don't silently apply uncertain mappings.
- **Multiple themes / color schemes found**: list them, ask the user which one to use as the diagram skin.
- **Folder has zero readable files**: tell the user and ask for a more specific path or switch to manual token entry.

---

## Future: per-project skins

If the user wants multiple skins (one per project), duplicate `style-guide.md` as `style-guides/<project>.md` and add a header comment pointing the build to the active one. That's a v5.2 feature — for now, one skin per skill install.
