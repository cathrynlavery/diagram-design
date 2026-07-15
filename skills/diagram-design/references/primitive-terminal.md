# Terminal Window (CLI-chrome variant)

Optional full-page skin that wraps any diagram in a fake terminal window — titlebar with three dots, a `$` prompt line, monospace type throughout. Use for dev-tool announcements, CLI-product posts, and technical social cards where a screenshot needs to read as "terminal," not "editorial doc."

This is a **second, fixed skin** — see [style-guide.md § Terminal skin](style-guide.md#terminal-skin-opt-in-alternate) for the token table. It does not inherit from `onboarding.md` brand tokens and isn't part of the light/dark inversion rule; every terminal example uses the same nine tokens regardless of the host site's brand.

## Grammar

```html
<div class="terminal">
  <div class="titlebar">
    <div class="dot accent"></div>
    <div class="dot"></div>
    <div class="dot"></div>
    <div class="titlebar-name">loop.sh — self-improving-loop</div>
  </div>
  <main class="frame">
    <p class="prompt">
      <span class="sign">$</span> diagram-design render --type loop
    </p>
    <h1># The self-improving loop</h1>
    <svg>...</svg>
  </main>
</div>
```

```css
body {
  background: var(--terminal-page);
}
.terminal {
  background: var(--terminal-paper);
  border: 1px solid var(--terminal-border);
  border-radius: 12px;
}
.titlebar {
  background: var(--terminal-bar);
  border-bottom: 1px solid var(--terminal-border);
}
.dot {
  background: var(--terminal-soft);
}
.dot.accent {
  background: var(--terminal-accent);
}
```

Inside the SVG, swap the default light/dark tokens 1:1 for their `terminal-*` equivalents: `paper` → `terminal-paper`, `ink` → `terminal-ink`, `muted`/`soft` → `terminal-muted`/`terminal-soft`, `accent`/`accent-tint` → `terminal-accent`/`terminal-accent-tint`. The hub/focal-node pattern (inverted fill for the one highlighted element) still applies.

## Typography

**Everything is monospace** — this is the one variant where that's correct. Drop Instrument Serif and Geist sans entirely; set the page title in mono, bold, prefixed with `# ` (reads as a comment line). The eyebrow becomes a shell prompt: `$ ` in `terminal-accent`, the command in `terminal-muted`.

Run every text role about **1–2px above** the default type scale in `style-guide.md` (e.g. `node-name` 12px → 14px, `sublabel`/`arrow-label` 8–9px → 9–10px, hub label 16px → 18px). Monospace at the default sizes reads small next to the sans/serif mix it's replacing, and these cards are usually viewed at social-feed scale, not full-bleed.

## Titlebar dots

Three 10px circles, macOS-style. The **1-accent rule caps the color use here too**: one dot is `terminal-accent`, the other two are `terminal-soft`. Do not use a red/yellow/green traffic-light triad — that's a second and third hue, which the palette forbids.

## Critical rules

- No pure black (`#000000`) — use `terminal-page` (`#0a0a0a`) / `terminal-paper` (`#141414`). Same rule as the default skin, same reason: true black clips on OLED and in print.
- One accent only. If a diagram needs a second focal element, use `terminal-ink` (white) for emphasis via weight/size, not a second color.
- Background dot-grid pattern (if used) stays `rgba(255,255,255,0.06–0.08)` — barely visible texture, not a visual competitor to the titlebar chrome.

## When to use

- Dev-tool / CLI-product launch posts (npm package, CLI flag, terminal-based workflow).
- Technical social cards where "this is a tool for engineers" is part of the message.
- Screenshots meant to pop in a dark-mode-heavy feed (X, Discord, dev blogs).

## When not to use

- Editorial / long-form posts — pair with the default light or full-editorial variant instead.
- Brand-matched output from `onboarding.md` — terminal is a fixed skin, not brand-tokenized. Don't try to reconcile the two.
- Any diagram where the audience isn't developer-coded to read `$`/`#`/titlebar-dots as chrome rather than content.
