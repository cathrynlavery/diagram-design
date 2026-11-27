# Style Guide

**The single source of truth for colors, typography, and tokens.** Every diagram draws from this — not from hex values inlined in other reference files. If you want to change the visual skin, change this file.

The shipped skin is **QUIND**: white paper, deep-navy ink, QUIND orange as the one accent, teal for links and external calls. It mirrors the tokens of the QUIND page kit (`quind-page.css`), so a diagram sits inside a QUIND document or page without a seam. QUIND is the default and needs no onboarding. To draw for another brand, see [`onboarding.md`](onboarding.md) and [`profiles.md`](profiles.md).

---

## Tokens

### Semantic roles

Every token is referred to by **semantic role**, not by its hex value. Type references (`type-*.md`) and SKILL.md say `accent`, not `#cc3b10`.

| Role | Purpose | Default (light) | Default (dark) |
|---|---|---|---|
| `paper` | Page background, default node fill | `#ffffff` (QUIND paper) | `#0e1920` (QUIND ink) |
| `paper-2` | Diagram container bg, secondary fill | `#f3f6f8` | `#16242c` |
| `ink` | Primary text, primary stroke | `#0e1920` (QUIND ink) | `#ffffff` |
| `ink-strong` | High-contrast text on accent fills | `#111111` | `#111111` |
| `muted` | Secondary text, default arrow stroke | `#5b6770` | `#9ba9b2` |
| `soft` | Sublabels, boundary labels | `#66727c` | `#8695a0` |
| `rule` | Hairline borders | `rgba(14,25,32,0.12)` | `rgba(255,255,255,0.12)` |
| `rule-solid` | Stronger borders, baselines | `#c9d1d8` | `rgba(155,169,178,0.25)` |
| `accent` | Focal / 1–2 max per diagram | `#cc3b10` (QUIND orange, text grade) | `#ff8a5c` |
| `accent-tint` | Fill for accent-bordered boxes | `rgba(204,59,16,0.08)` | `rgba(255,138,92,0.10)` |
| `link` | HTTP/API calls, external arrows | `#0b6e80` (QUIND teal, text grade) | `#5fd6ec` |

> **Brand palette source:** the QUIND page kit. `ink` is `--ink`, `muted` is `--muted`, `paper-2` is `--soft`, `rule-solid` is `--gray-2`. The light `accent` is `--orange-ink` (`#cc3b10`), not the raw brand orange `#f54718`: raw orange reads 3.62:1 on white, too faint for a label or a thin arrow, and the kit itself uses `--orange-ink` wherever orange is text. `link` is `--teal-ink` for the same reason (raw teal `#00bcdb` is 2.28:1). `soft` is derived (a lighter step of `muted`) and `rule` is ink at opacity. Every value is held to the contrast contract below.

### Contrast contract

Every token must clear the threshold for each role it plays, against the background it actually sits on, in both skins. `scripts/verify-contrast.py` computes the WCAG 2.x ratio for every row above against the `paper` of its skin (`ink-strong` against the 0.85 `accent` fill it labels) and fails CI when one falls short.

| Use | Minimum vs. its actual background |
|---|---|
| Regular text, including any `soft`, `link`, or `accent` used as text | 4.5:1 |
| Large text (24px+, or 18.7px+ at weight 600+) | 3:1 |
| Essential non-text marks: lines, arrows, borders, focus outlines, data points | 3:1 against the adjacent color |
| Decorative rules and translucent tints (`rule`, `rule-solid`, `paper-2`, `accent-tint`, fills at opacity) | No minimum, but never the only carrier of meaning |

- **A token used in several roles must pass each one.** `accent` is a stroke in one place and a label in another, so it is held to 4.5:1, not the 3:1 its strokes alone would need. Don't assume a token is non-text because it usually is.
- **Translucent colors are composited first.** An `rgba()` fill or stroke is blended over `paper` before its ratio is measured. A value that clears the bar at full strength can fail at 0.5 opacity.
- **Surfaces other than `paper` cost contrast.** Inside an `accent-tint` box or on `paper-2` every ratio drops. Measure text placed there against that surface, not against `paper`.
- **Current defaults:** light `accent` 5.00:1, `soft` 4.93:1, `link` 5.91:1, `muted` 5.80:1 on `#ffffff`; dark `accent` 7.67:1, `soft` 5.79:1, `link` 10.45:1 on `#0e1920`.

### Inversion rule (light → dark)

Any `rgba(14,25,32, X)` in light becomes `rgba(255,255,255, X)` in dark. Same opacities, RGB flipped. The accent and link move to their brighter kit values (`--orange-bar`, dark `--teal-ink`) to read on dark paper.

### Series palette (multi-series chart types only)

A small set of QUIND chart colors, each at a grade that holds 3:1 as a stroke, for chart types that genuinely need to distinguish multiple overlapping entities (currently: **radar**). The "1-focal" rule still holds — `accent` is reserved for the focal series; the palette below covers the rest.

| Token | Light | Dark | Notes |
|---|---|---|---|
| `series-1` | `#2fa36b` (green) | `#6fd3a0` | Non-focal series |
| `series-2` | `#0b6e80` (teal) | `#5fd6ec` | Non-focal series |
| `series-3` | `#9a6400` (amber) | `#ffc85a` | Non-focal series |
| `series-4` | `#7a8791` (gray) | `#6c7b85` | Non-focal series |
| `series-5` | `#24323c` (navy) | `#b8c2ca` | Non-focal series |

Fills sit at `0.18` opacity light, `0.22` dark; strokes use the full color. **Don't backfill these tokens to non-chart types** — architecture, swimlane, etc. continue to use muted-ink variants. The series palette is opt-in for diagrams where overlapping shapes demand distinguishable color, not a license to add color elsewhere.

### Terminal skin (opt-in alternate)

A self-contained palette for the terminal-window primitive (see [primitive-terminal.md](primitive-terminal.md)) — a CLI-chrome register for dev-tool posts and technical social cards. It does not replace the default skin above and isn't affected by onboarding; it's a second, fixed skin you opt into per-diagram.

| Token | Hex | Purpose |
|---|---|---|
| `terminal-page` | `#0a0a0a` | Page background behind the window |
| `terminal-paper` | `#141414` | Window body, node fill |
| `terminal-bar` | `#1b1b1b` | Titlebar strip |
| `terminal-border` | `#2b2b2b` | Window border, hairlines |
| `terminal-ink` | `#f5f5f5` | Primary text, primary stroke |
| `terminal-muted` | `#9a9a9a` | Secondary text, sublabels, ring stroke |
| `terminal-soft` | `#5c5c5c` | Tertiary — inactive dots, spokes |
| `terminal-accent` | `#ff5a36` | The one accent — focal station, prompt sign, active dot |
| `terminal-accent-tint` | `rgba(255,90,54,0.12)` | Fill for accent-bordered boxes |

**1-accent rule still holds.** Everything that isn't `terminal-ink` or `terminal-muted`/`terminal-soft` should be `terminal-accent` — never introduce a second hue.

---

## Typography

| Role | Family | Size | Weight | Usage |
|---|---|---|---|---|
| `title` | Poppins | 1.75rem | 600 | Page H1 |
| `node-name` | Inter (sans) | 12px | 600 | Human-readable labels |
| `sublabel` | Roboto Mono | 9px | 400 | Port, protocol, URL, field type |
| `eyebrow` | Roboto Mono | 7–8px | 500, tracked 0.18em, uppercase | Type tags, axis labels |
| `arrow-label` | Roboto Mono | 8px | 400, tracked 0.06em | Arrow annotations |
| `callout` | Inter *italic* | 14px | 400 | Editorial asides only |

These are the three families of the QUIND page kit: Poppins for headings (`--f-head`), Inter for body (`--f-body`), Roboto Mono for technical content (`--f-mono`). Templates keep upstream's CSS variable names, so `--font-serif` holds the **title** family (Poppins) even though it is no longer a serif.

### Font stack

```html
<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&family=Inter:ital,wght@0,400;0,500;0,600;1,400&family=Roboto+Mono:wght@400;500;600&family=Noto+Sans+KR:wght@400;500;600&family=Noto+Sans+TC:wght@400;500;600&display=swap" rel="stylesheet">
```

### Font source

The font source decides whether a diagram makes any network request. It is a skin setting, so a saved profile carries it too.

Font source: `web`

| Value | What ships | Network |
|---|---|---|
| `web` (default) | The Google Fonts `<link>` above; text renders in Poppins, Inter, and Roboto Mono | One stylesheet request to `fonts.googleapis.com`, plus the font files |
| `system` | No font `<link>`; every family stack falls through to the platform's own serif, sans, and monospace faces | None |

Use `system` when the user asks for offline output, system fonts, or no Google Fonts, or when this line says `system`. In `system` mode:

- Omit the font `<link>` (and the export `@import`) entirely. Keep every `font-family` stack as written: each one already ends in a generic family (`system-ui, sans-serif`, `ui-monospace, monospace`), so a viewer who has Inter installed still gets it and everyone else gets their system face.
- Fallback faces have different metrics from Inter, so keep the 8px label padding intact rather than trimming boxes to the Inter measurement.
- Export with `python3 scripts/export_svg.py <file> --system-fonts`, and verify with `python3 scripts/self_check.py --offline <file>`, which fails if the Google Fonts link is still present.

The render linter's default run (`lint-render.py` with network blocked) measures exactly this fallback rendering, so every shipped template and example is already checked in system-font mode.

To keep the QUIND faces with no network at all, install Poppins, Inter (both SIL Open Font License) and Roboto Mono (Apache 2.0) locally and use `system`: the stacks resolve to the installed faces first.

### Korean labels

Inter and Poppins carry no Hangul. A Korean `<text>` element extends its own family — never swap the skin:

```svg
<text font-family="'Inter', 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif">결제 서비스</text>
```

Noto Sans KR ships in the font link above, so the web font resolves before any locally installed one and the same file renders identically on macOS, Windows, and a reviewer's browser. The local families follow it for offline viewing. Page titles take the same fallback — `'Poppins', 'Inter', 'Noto Sans KR', sans-serif` — or a mixed Latin/Korean title resolves Hangul through the platform's generic sans and the two halves disagree. Google's `css2` endpoint slices Korean by unicode-range, so a diagram with a handful of Korean labels downloads only the slices it touches. The four templates carry the face because a new diagram may contain Hangul; the shipped Latin-only examples keep the shorter link, since a file with no Hangul has nothing to resolve.

**Width budget.** Measure per character, not per script: **every Unicode wide or full-width character costs 1em, every other character costs its face's Latin advance** (0.60em sans, 0.62em mono), and nonspacing/enclosing marks cost nothing. Sum over the string and multiply by the font size for the text width, then add padding and round the box up to the next multiple of 4. `verify-treemap.py` enforces exactly this text width for treemap cell labels. The skill's `scripts/self_check.py` applies the same width, plus any letter-spacing, to text inside a visible box of any type, and fails a label that runs more than 0.3em past the box edge. Padding, rounding, and labels on paper-coloured arrow-label masks are not checked, so those stay yours to hold.

Counting by script is the trap. `주문 v2.1` is two full-width syllables and five narrow characters; a formula that tallies Hangul, Latin letters, and spaces silently drops `2`, `.`, and `1` and sizes the box for four of its seven characters. Every rendered character costs something — measure per character, never per script.

Three rules follow from Hangul metrics:

- **Sublabels stay Latin.** Ports, protocols, field types, and URLs are Latin anyway — keep `Roboto Mono` there and don't translate them. Hangul in a 9px mono sublabel is unreadable and has no mono face to fall back to.
- **Floor of 12px.** Hangul goes muddy below 12px. If a Korean name doesn't fit at 12px, cut the name — don't shrink the type.
- **Arrow labels, eyebrows, and legend text switch register.** Those slots are 7–8px Roboto Mono, uppercase and tracked, which Hangul has neither a face nor legibility for. A Korean label in one of those slots becomes 12px sans at weight 500 with no tracking and no uppercase transform, and its mask rect grows to match (16px tall, width from the budget above, still rounded to a multiple of 4). Latin labels in the same diagram keep the mono treatment.

**Load-bearing rule:** Mono is for *technical* content (ports, commands, URLs, field types). Names go in Inter. Page title is Poppins. Italic Inter is reserved for annotation callouts (see [primitive-annotation.md](primitive-annotation.md)). **Never JetBrains Mono** as a blanket "dev" font.

### Traditional Chinese labels

Inter and Poppins carry no Han. A Traditional Chinese `<text>` element extends its own family — never swap the skin:

```svg
<text font-family="'Inter', 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif">請求項比對</text>
```

Noto Sans TC ships in the font link above, so the web font resolves before any locally installed one and the same file renders identically on macOS, Windows, and a reviewer's browser. The local families follow it for offline viewing. Page titles take the same fallback — `'Poppins', 'Inter', 'Noto Sans TC', sans-serif` — or a mixed Latin/Han title resolves Han through the platform's generic sans and the two halves disagree. Google's `css2` endpoint slices Chinese by unicode-range, so a diagram with a handful of Chinese labels downloads only the slices it touches.

**Width budget.** The per-character contract above is unchanged: every Unicode wide or full-width character costs 1em, every other character costs its face's Latin advance, and nonspacing marks cost nothing. Full-width punctuation — `（）「」，。：` — is wide and costs 1em as well, which is the part most often dropped.

Counting by script is the trap. `請求項 v2.1` is three full-width characters and five narrow ones; a formula that tallies Han and Latin letters silently drops `2`, `.`, and `1` and sizes the box for six of its nine characters.

Three rules follow from Han metrics, mirroring the Hangul ones:

- **Sublabels stay Latin.** Ports, protocols, field types, and URLs are Latin anyway — keep `Roboto Mono` there and don't translate them. Han in a 9px mono sublabel is unreadable and has no mono face to fall back to. A sublabel that is prose rather than a value may be Chinese, but it then switches register by the third rule below.
- **Floor of 12px.** Han packs more strokes than Hangul into the same em box, so the 12px floor binds at least as hard here. If a Chinese name doesn't fit at 12px, cut the name — don't shrink the type.
- **Arrow labels, eyebrows, and legend text switch register.** Those slots are 7–8px Roboto Mono, uppercase and tracked, which Han has neither a face nor legibility for. A Chinese label in one of those slots becomes 12px sans at weight 500 with no tracking and no uppercase transform, and its mask rect grows to match (16px tall, width from the budget above, still rounded to a multiple of 4). Latin labels in the same diagram keep the mono treatment.

Simplified Chinese takes the same three rules with the Simplified stack (`'Noto Sans SC'`, `'PingFang SC'`, `'Microsoft YaHei'`). That face does not ship in the link, so Simplified labels still resolve through whatever the viewer has locally.

### Cyrillic labels

Inter and Roboto Mono ship Cyrillic (`cyrillic` and `cyrillic-ext` on Google Fonts), so names, sublabels, arrow labels, eyebrows, and legend text in Bulgarian, Russian, Ukrainian, or Serbian keep the Latin treatment: same faces, sizes, tracking, and uppercase. There is no register switch.

Poppins carries no Cyrillic. The title stack lists Inter right after it — `'Poppins', 'Inter', system-ui, sans-serif` — so a Cyrillic title resolves through Inter. Set a fully Cyrillic title in Inter 600 outright, so a mixed Latin/Cyrillic title does not change face mid-line.

**Width budget.** The per-character contract above is unchanged: every character costs its face's Latin advance (0.60em sans, 0.62em mono). It fits Roboto Mono exactly and Inter only on average. Roboto Mono is monospaced: a Cyrillic glyph advances exactly as far as a Latin one, so sublabels, arrow labels, eyebrows, legend text, and their mask rects are sized as for Latin. Inter is not. Its wide Cyrillic letters, capitals and lowercase alike (such as `Ж Ш Щ Ю Ы`, `ж ш щ ы ю`), run well past the 0.60em average: `Шкаф ODF-2` at 12px is budgeted at 72px and draws at about 76. Rounding the box up to a multiple of 4 recovers at most 3px, so it is not the remedy. Leave the overshoot in the box padding and measure a Cyrillic sans name in the browser — `verify-treemap.py` holds the budget, not the drawn width, so it will not catch the overshoot.

Counting by script is still the trap. `Шкаф ODF-2` is four Cyrillic letters, a space, three Latin letters, a hyphen, and a digit; a formula that tallies Cyrillic letters, Latin letters, and spaces silently drops `-` and `2` and sizes the box for eight of its ten characters.

**Preserve printed labels.** A label the reader matches against a physical thing — a cabinet, a splice closure, a port map — carries the exact printed string. Don't transliterate it and don't re-case it; if one has to sit in an uppercase slot such as an eyebrow, drop the transform for that label rather than re-case the printed string. `Шкаф ODF-2` stays `Шкаф ODF-2`, not `Shkaf ODF-2`.

---

## Stroke, radius, spacing

| Token | Value | Use |
|---|---|---|
| `stroke-thin` | `0.8` | Tag-box outlines, leaf nodes |
| `stroke-default` | `1` | Most strokes |
| `stroke-strong` | `1.2` | Emphasis strokes |
| `radius-sm` | `4` | Small tags |
| `radius-md` | `6` | Node boxes |
| `radius-lg` | `8` | Containers, rings |
| `grid` | `4` | Every coord, size, and gap is divisible by 4 (hard rule) |

---

## Node type → treatment

Semantic role combinations — reference these by name in type specs.

| Type | Fill | Stroke |
|---|---|---|
| `focal` (1–2 max) | `accent-tint` | `accent` |
| `backend` | `#ffffff` (white) | `ink` |
| `store` | `ink @ 0.05` | `muted` |
| `external` | `ink @ 0.03` | `ink @ 0.30` |
| `input` | `muted @ 0.10` | `soft` |
| `optional` | `ink @ 0.02` | `ink @ 0.20` dashed `4,3` |
| `security` | `accent @ 0.05` | `accent @ 0.50` dashed `4,4` |

---

## Customizing the skin

Four options:

1. **Run onboarding** — see [`onboarding.md`](onboarding.md). Drop a URL; the skill extracts the palette + fonts and rewrites this file.
2. **Edit by hand** — change the hex values in the tables above. Run the pre-output taste gate afterward to verify the accent still reads as "focal" against the new paper color.
3. **Brand handoff** — paste your existing design-token JSON into a new section here and map its tokens to the semantic roles above.
4. **Client profiles** — save and switch named skins, or bind one to a project, using [`profiles.md`](profiles.md).

### Constraints (don't break these)

- **Contrast**: every text token (`ink`, `muted`, `soft`, `link`, and `accent`) must clear 4.5:1 on `paper`, in both skins. See the [contrast contract](#contrast-contract); `scripts/verify-contrast.py` checks it.
- **One accent**: pick one color for `accent`. Two accents erases the focal signal.
- **No rainbow palette**: the kit also ships teal, amber, and green. Teal is `link`; amber and green appear only in the series palette and in BPMN task types ([`type-bpmn.md`](type-bpmn.md)). They never become a second accent.
- **Head + body + mono**: three families, not more — Poppins, Inter, Roboto Mono. Hierarchy comes from Poppins at weight 600 against Inter, not from a serif.
- **Paper is white**: QUIND documents and pages are white sheets, and a figure has to sit on them without a tinted box around it. Nodes separate from the paper by their 1px `ink` stroke, never by a fill difference or a shadow.
- **Dot pattern is optional, not default**: the 22×22 dot pattern is an opt-in "dotted paper" variant (good for long-form editorial hero diagrams). The default background is a clean `paper` fill, no pattern. When the pattern is enabled, it should sit at ~10% opacity of `ink` on `paper` — visible but quiet.
- **Container is clean by default**: the diagram sits directly on the page paper, no secondary container background or border. A framed variant (`paper-2` bg + `rule` border + 8px radius + padding) is available as an opt-in for card-heavy layouts, but don't reach for it by default — the extra chrome fights the figure.
