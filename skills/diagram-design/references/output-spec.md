# Draw.io import output spec — format × size × detail × audience

Four dials decide what an imported diagram becomes. Set them **before** redrawing — they change the deliverable, layout, type ramp, node count, and wording, so retrofitting them afterwards means redrawing.

| Dial | Question it answers | Default |
|---|---|---|
| **Format** | Where does this file land? | `html` |
| **Size** | How big is the canvas, and how far away is the reader? | `doc-inline` |
| **Detail level** | Reproduce every element, or compress it? | `balanced` |
| **Audience** | How technical should the wording be? | `mixed` |

Infer choices that are clear from the request (for example, "for my deck" implies a slide preset). Ask one concise question for anything material that remains ambiguous. If the user does not care, use the defaults above and say which ones you used.

---

## 1. Format

| Format | Deliverable | Keeps | Drops |
|---|---|---|---|
| `html` | self-contained `.html` (default) | header, diagram, summary cards, footer, live fonts | nothing |
| `svg` | `.svg` next to the source | the `<svg>` node, vector text | editorial wrapper; fonts substitute in offline tools |
| `png` | `.png` at `device_scale_factor` | pixels exactly as the browser renders them | vector editability |
| `html+png` | both | — | — |

Always generate the HTML first — `svg` and `png` are produced *from* it via [`export.md`](export.md). Never hand-author an SVG file directly; the HTML is the source of truth and the only artifact the taste gate (SKILL.md §9) is written against.

Pick by destination:

| Destination | Format | Size preset |
|---|---|---|
| Blog post, README, docs site | `html` (embed) or `png` | `doc-inline` |
| Keynote / PowerPoint / Google Slides | `png` @2 | `slide-16x9` |
| Figma / Illustrator / further editing | `svg` | `fit` |
| X / LinkedIn / OG link card | `png` @2 | `social-og` |
| Printed handout, PDF deck | `png` @3 | `print-a4-landscape` |
| Confluence / Notion / internal wiki | `png` @2 | `doc-wide` |

---

## 2. Size

The preset sets the SVG `viewBox`. Every value below is divisible by 4, so the grid rule in SKILL.md §7 still holds.

| Preset | viewBox | Aspect | PNG @2 | Type ramp | Use |
|---|---|---|---|---|---|
| `doc-inline` (default) | `0 0 960 600` | 8:5 | 1920×1200 | standard | Body-width diagram in a post or README |
| `doc-wide` | `0 0 1280 720` | 16:9 | 2560×1440 | standard | Full-width docs, wiki pages |
| `slide-16x9` | `0 0 1280 720` | 16:9 | 2560×1440 | presentation | Deck slide, projected |
| `slide-4x3` | `0 0 1024 768` | 4:3 | 2048×1536 | presentation | Legacy deck templates |
| `social-og` | `0 0 1200 632` | ~1.9:1 | 2400×1264 | presentation | Link preview card |
| `social-square` | `0 0 1080 1080` | 1:1 | 2160×2160 | presentation | Feed post, carousel |
| `print-a4-landscape` | `0 0 1120 792` | ~1.41:1 | @3 → 3360×2376 | print | A4 landscape, ~10mm margins at 96dpi |
| `print-letter-landscape` | `0 0 1056 816` | ~1.29:1 | @3 → 3168×2448 | print | US Letter landscape |
| `fit` | derived from content | any | @2 | standard | Vector hand-off; no fixed frame |

### Deriving `fit`

Round the content bounding box **up** to the next multiple of 4, then add the fixed chrome: 40px outer margin on every side, plus 60px at the bottom for the legend strip. Never let the content touch the viewBox edge.

### Type ramp per size class

Node names shrink relative to the canvas as it grows — resist that. Scale the ramp with the preset so a projected slide stays readable from the back row.

| Role | standard | presentation | print |
|---|---|---|---|
| Title (Instrument Serif) | 28 | 40 | 32 |
| Node name (Geist 600) | 12 | 16 | 12 |
| Sublabel (Geist Mono) | 9 | 12 | 9 |
| Arrow label (Geist Mono) | 8 | 12 | 8 |
| Eyebrow / tag (Geist Mono) | 8 | 8 | 8 |
| Node box min height | 48 | 64 | 48 |
| Min gap between nodes | 24 | 40 | 24 |

Presentation ramp implies fewer nodes — 16px names in 64px boxes eat the canvas. If a `slide-16x9` layout won't fit, that's the size dial telling you the detail dial is set too high; drop a level rather than shrinking the type.

### Safe areas

- **All presets:** 40px outer margin; legend strip is the bottom 60px and nothing else lives there.
- **`social-og`:** keep the outer 64px clear on every side — link-card crops are unpredictable across platforms.
- **`slide-*`:** keep the bottom 80px clear if the deck template has a footer bar; ask if unsure.

---

## 3. Detail level

How much of the source survives. This is a *count* dial — it governs how many elements make it through, not how they're worded (that's §4).

| Level | Nodes | Edges | Sublabels | What survives |
|---|---|---|---|---|
| `faithful` (詳細) | ≤24, zoned | ≤32 | every port, protocol, version | Every distinct component in the source. Only exact duplicates merge. |
| `balanced` (default) | ≤12 | ≤16 | technical sublabel on ≤4 nodes | Components that carry the story; leaf clusters collapse to one node each. |
| `simplified` (簡略) | ≤7 | ≤9 | none | Capabilities and their sequence. Infrastructure disappears. |

`balanced` and `simplified` sit inside the standard complexity budget (SKILL.md §7). **`faithful` deliberately exceeds it** — that's the trade, and it comes with conditions:

1. **Zoning is mandatory.** Above 9 nodes, every node belongs to a labeled zone (2–4 zones, hairline-bordered, `paper-2` fill, mono uppercase zone label at top-left). An unzoned 20-node diagram is a wiring diagram, not a schematic.
2. **Connector rules don't relax.** SKILL.md §6 rules 1–5 still apply at 24 nodes. If you can't route it without overlaps, you're over the real ceiling — split.
3. **Above 24 nodes, split.** Produce an overview (zones as nodes, `balanced` grammar) plus one detail diagram per zone. Name them `<base>-overview.html`, `<base>-<zone>.html`. Never ship a 40-node single canvas.
4. **Accent stays at 2.** More nodes never buys more focal elements.

### Degrade ladder

When the source has more than the level allows, cut in this order and stop as soon as you're under budget. Never cut ad hoc.

1. **Decorative cells** — sticky notes, free-floating text, title blocks, watermarks, the source's own legend. (Notes worth keeping become annotation callouts — max 2, see [primitive-annotation.md](primitive-annotation.md).)
2. **Exact duplicates** — N identical workers/replicas/shards become one node labeled `Worker ×N`.
3. **Leaf clusters** — a container whose children are all leaves collapses to the container: `Core Services` replaces its three boxes. The extractor lists these under *collapsible groups*.
4. **Degree-1 sinks that don't change the story** — a monitoring hook, a log bucket, an archive tier.
5. **Cross-cutting infrastructure** — logging, metrics, secrets, CI. At `simplified` these go without asking; at `balanced` keep at most one, and only if the diagram is about it.
6. **Still over?** Split into overview + detail. Splitting beats shrinking.

Anything cut in steps 2–6 goes in the fidelity ledger (§5). Step 1 doesn't need reporting.

---

## 4. Audience level

Independent of the detail dial: the same 12 nodes get named differently for a platform team than for a steering committee. Detail sets *how many*; audience sets *what they're called*.

| Audience | Node names | Sublabels | Edge labels | Never |
|---|---|---|---|---|
| `engineer` | exact service / component names | protocol, port, version, image tag | `POST /v2/orders`, `SQL`, `gRPC` | Vague verbs like "connects to" |
| `mixed` (default) | component names, expanded acronyms | technology only where it changes a decision | plain verbs — `verifies`, `writes`, `notifies` | Ports, versions, internal codenames |
| `executive` | capabilities and outcomes | none | business verbs — `approves`, `pays out` | Vendor names, infrastructure, protocols |

Worked example — the same node through all three:

| Audience | Node name | Sublabel |
|---|---|---|
| `engineer` | `Auth Service` | `JWT · RS256 · :8443` |
| `mixed` | `Auth Service` | `token check` |
| `executive` | `Sign-in` | — |

Two rules that hold at every audience level:

- **Never invent detail to fill a slot.** If the source says `svc-04`, `executive` output says what it does only if you can tell from context — otherwise ask, don't guess a business name.
- **Keep the source's vocabulary for proper nouns.** Renaming `Kafka` to `Message Bus` is fine at `executive`; renaming it to `Event Grid` (a different product) is a factual error.

### Non-Latin labels

Geist has no CJK coverage. When labels contain Japanese, Chinese, or Korean text, extend the family on those `<text>` elements — don't swap the whole skin:

```svg
<text font-family="'Geist', 'Hiragino Sans', 'Noto Sans JP', 'Yu Gothic', sans-serif">認証サービス</text>
<text font-family="'Geist', 'Noto Sans KR', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif">인증 서비스</text>
```

The Hiragino/Yu Gothic stack carries no Hangul glyphs, so Korean labels need the Korean stack — don't reuse the Japanese one. Noto Sans KR ships in the skin's font link, so it leads that stack and the local families follow it; the register, floor, and title rules Korean needs beyond the font live in [`style-guide.md`](style-guide.md#korean-labels). For mono sublabels use `'Geist Mono', 'Noto Sans Mono CJK JP', monospace` (Japanese) or `'Geist Mono', 'Noto Sans Mono CJK KR', monospace` (Korean). Budget **1em per full-width CJK glyph**, not a small percentage over the average Latin glyph; `verify-treemap.py` uses that conservative contract for Unicode wide/full-width characters and treats combining marks as non-advancing. Prefer 12px names over 8px sublabels for CJK, which goes muddy below 10px. Actual width still varies by fallback font, so run the relevant geometry verifier after translating labels.

---

## 5. Fidelity ledger

Any time output is smaller than input — every `balanced` and `simplified` run, and most `faithful` ones — report what you cut, in chat, after the file path. Short and specific:

```
Detail: balanced · 18 source nodes → 9 drawn
Merged:  worker-01..06 → "Ingest Worker ×6"
Collapsed: "Observability" group (Grafana, Loki, Tempo) → one node
Dropped: 2 sticky notes, CI pipeline (cross-cutting)
Kept in full: the request path (Client → Gateway → Orders → Postgres)
```

The reader of the diagram can't see what's missing. The person who asked for it needs to.

---

## 6. Checklist

Run alongside the SKILL.md §9 taste gate.

- [ ] All four dials set — explicitly requested, inferred from the destination, or defaulted and stated?
- [ ] `viewBox` matches the size preset exactly, values divisible by 4?
- [ ] Type ramp matches the size class — not the standard ramp on a slide?
- [ ] 40px outer margin honoured (64px for `social-og`)?
- [ ] Node count inside the detail level's ceiling?
- [ ] `faithful` above 9 nodes → zoned, and split above 24?
- [ ] Node names, sublabels, and edge labels all at the same audience level?
- [ ] CJK labels given a font fallback?
- [ ] Fidelity ledger reported for anything cut?
- [ ] Diagram `<svg>` has `role="img"`, resolving `aria-labelledby`, a non-empty first-child `<title>`, a non-empty `<desc>`, and per-diagram/variant prefixed IDs?
- [ ] Requested non-HTML formats produced via [`export.md`](export.md), not hand-authored?
