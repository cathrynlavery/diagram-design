# Optional animation

Animation explains a complete static diagram; it never supplies missing meaning. Load this reference only when motion is explicitly requested or materially clarifies order, accumulation, evaluation, containment, or propagation. Otherwise use mode `none` and ship static HTML.

## Modes

Choose one mode per figure with `data-motion-mode="none|reveal|step|loop"`.

| Mode | Behavior | Controls / implementation | Use |
|---|---|---|---|
| `none` | Complete stable figure | No JavaScript | Default, print, screenshot, export, reduced-motion fallback with playback controls unavailable |
| `reveal` | One deterministic autoplay run ending complete | CSS-only for ≤5s; otherwise use the scoped controller | Short ordered explanation; never auto-replay |
| `step` | Paused semantic states | Minimal inline JS for Play, Pause, Replay, Previous, Next | Teaching, comparison, policy traces |
| `loop` | One decorative token repeats without changing meaning | CSS-only default | Quiet flow hint; ≥3s cycle |

Only `loop` repeats. Queue state, typing, field values, policy outcomes, containment, and audit entries use `reveal` or `step` and finish complete.

`reveal` is the sole sanctioned autoplay mode: it may run once on initial load when motion was explicitly requested, then remains complete. It never restarts on viewport re-entry or without an explicit Replay action.

## Static-first enhancement contract

1. **Source is complete.** Every semantic node, label, connector, status, and outcome is visible in the HTML/SVG before enhancement. Only selectors below `.motion-ready` may hide or transform them.
2. **Stable capture.** Initial `data-frame="static"`, `?motion=static`, print, no-JS, and standalone SVG export expose the complete frame and hide controls/decorative tokens. Do not capture after an arbitrary delay.
3. **CSS owns presentation.** Use CSS transitions/keyframes for appearance and travel. Minimal inline JavaScript is allowed only to bind explicit controls, update step/state attributes, schedule deterministic steps, and update the dedicated live-status region. No fetches, markup injection, path measurement, or mutation of semantic diagram labels or values.
4. **One clock.** Use `--motion-fast: 160ms`, `--motion-step: 480ms`, `--motion-hold: 720ms`, and `--motion-total` ≤ `8000ms`; derive delays from integer steps. No randomness, springs, or transition-event timing.
5. **Explicit order.** Mark items `data-motion-item data-step="N"` for integer steps 1–8. DOM order follows narrative order. At most two items enter per step.
6. **Stable end.** Completion exposes all items and sets `data-frame="end"`. Replay resets to step 0 first. Pause clears the pending timer and resume continues from the same step.
7. **Scoped state.** Controls operate on their nearest `[data-motion-root]`; IDs, timers, live regions, and step state never cross figure boundaries.
8. **Failure-safe startup.** JavaScript adds `.motion-ready` only after controls are bound and the initial render succeeds. A script error before that point leaves the complete source visible.

## Semantic primitives

Every primitive has text, count, symbol, pattern, or outline in addition to color.

| Primitive | Mechanism | Static / reduced-motion result | Limit |
|---|---|---|---|
| **Path draw** | Decorative duplicate path with `pathLength="1"` and animated dash offset | Base labeled connector remains visible | ≤2 paths; one active |
| **Staggered reveal** (stage reveal) | `data-motion-item` + opacity/translate ≤8px | All stages visible | ≤8 steps, 12 items |
| **Queue counter** (queue accumulation) | Stable slots; item reveal plus visible numeric count | Final queue and count visible | ≤5 items; no reorder |
| **Typing / field population** | Full accessible string; clipped decorative overlay or labeled row reveal | Complete text/fields visible once | ≤32 typed chars or 6 fields |
| **Policy evaluation** (rule evaluation) | Ordered rule rows with text statuses and a current-row outline | Every state and outcome visible | 3–6 rules; 2 traces |
| **Flow token** | `aria-hidden` token on a fixed path | Token hidden; connector remains | One token; loop ≥3s |
| **Containment** | Reveal children, then persistent labeled boundary | Children and boundary visible | One boundary transition |
| **Audit append** | Chronological rows revealed; stable timestamp/sequence | Complete ordered log visible | ≤5 appended rows |

Do not animate layout coordinates, connector routes, `viewBox`, node dimensions, or semantic text. Avoid zoom, parallax, bounce, shake, glow, particles, and indefinite blinking.

```css
:root {
  --motion-fast: 160ms;
  --motion-step: 480ms;
  --motion-hold: 720ms;
  --motion-total: 3600ms; /* five steps × hold; set this per diagram */
  --motion-ease: cubic-bezier(.2,.8,.2,1);
}
.motion-ready [data-motion-item] {
  opacity: .12;
  transform: translateY(8px);
  transition: opacity var(--motion-step) var(--motion-ease),
              transform var(--motion-step) var(--motion-ease);
}
.motion-ready [data-motion-item].is-visible,
.motion-ready[data-frame="end"] [data-motion-item] {
  opacity: 1;
  transform: none;
}
[data-motion-controls][hidden] { display: none !important; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  [data-motion-item] { opacity: 1 !important; transform: none !important; }
  [data-motion-decorative] { display: none !important; }
  [data-motion-controls] { display: none !important; }
}
@media print {
  [data-motion-controls], [data-motion-decorative] { display: none !important; }
  [data-motion-item] { opacity: 1 !important; transform: none !important; }
}
```

## Interactive controls and keyboard

Every interactive `step` figure provides native buttons for **Play, Pause, Replay, Previous, and Next**, outside the SVG. Use `data-motion-action="play|pause|replay|prev|next"`, ≥44×44px targets, visible focus, disabled state for unavailable actions, and `aria-pressed` for play/pause state.

When focus is within the motion root: `ArrowRight` advances, `ArrowLeft` goes back, `Home` resets, `End` completes, `Space` toggles play/pause when focus is not already on a native control, and unmodified `R` replays. Never intercept `R` when Control, Command, or Alt is held. Do not capture keys from inputs, links, or unrelated regions. Never move focus as the frame changes.

Provide visible instructions and a scoped `role="status" aria-live="polite" aria-atomic="true"`. Keep that live region inside the motion root but outside `[data-motion-controls]`, so hiding controls for reduced/static states cannot hide announcements. Announce user actions such as “Step 3 of 5: first divergence”; do not announce every autoplay frame. Controls operate only on their nearest `[data-motion-root]`.

Use [`assets/template-motion.html`](../assets/template-motion.html) rather than inventing another controller. Its inline controller is the executable implementation contract: copy that script body verbatim. The skin linter rejects modified or additional controllers, even when they carry `data-diagram-controls`. Replace diagram content and slug-prefixed IDs, but preserve the controller and its state/control attributes.

## Reduced motion, color, and accessibility

- `prefers-reduced-motion: reduce` initializes at the complete static frame, disables and hides every playback control, hides decorative movement, and exposes `data-motion-state="reduced"` plus status text that playback is unavailable. It never presents partial-step announcements beside a complete frame.
- The SVG's `<title>` and `<desc>` describe the complete meaning, not the animation. Interaction instructions remain visible HTML text.
- Decorative overlays carry `aria-hidden="true" focusable="false"`. Semantic text exists once in the accessibility tree.
- State is never color-only: policy uses symbol + `PASS/FAIL/SKIPPED/NOT REACHED`; queues show counts; active stages use number/label/outline.
- Nothing flashes or changes luminance more than three times per second.

## Complexity and deterministic timing

Motion does not raise the static diagram budget: ≤8 semantic steps (target 3–6), ≤12 marked items, ≤2 simultaneous reveals, ≤2 drawn paths, one flow-token loop, 160–600ms transitions, 400–1200ms holds, ≤24px translation, and 3–8s total autoplay.

Declare `data-step-count`; do not infer steps from transition events. Set `--motion-total` to step count × `--motion-hold` and keep it within the 8-second budget. Use one `setTimeout` chain per root, derive its hold from `--motion-hold`, clear it on Pause/Replay/page hide and immediately after rendering the final step, and never use `setInterval` for semantic playback. Pause when `document.visibilityState` becomes hidden and do not catch up later. `?motion=step&step=N` may expose an exact zero-duration frame for visual regression only when `N` is a non-negative base-10 integer from 0 through `data-step-count`; missing, fractional, negative, and over-budget values leave normal playback in place.

The final-state capture contract is synchronous: `?motion=static`, `<html data-motion="static">`, or mode `none` exposes every semantic item, hides controls and decorative overlays, and sets `data-frame="static"`. Wait for `document.fonts.ready` before capture. Two captures from the same URL, viewport, fonts, and device scale must be pixel-identical; random delays, generated IDs, clocks, and runtime path measurement are forbidden.

## Export and verification

PNG and SVG exports are static final-state artifacts unless the user explicitly requests a named step. Before capture, open `?motion=static`, await `document.fonts.ready`, and assert `data-frame="static"`. SVG extraction omits HTML controls and scripts; source-visible semantic markup keeps the result complete.

Run:

```bash
python3 scripts/verify-motion.py path/to/animated-diagram.html
python3 scripts/test-verify-motion.py
python3 scripts/lint-skin.py path/to/animated-diagram.html
```

The verifier checks mode/state declarations, contiguous steps, motion budgets, complete SVG naming, no-JS source visibility, decorative accessibility, the full control set, live status, reduced-motion/print CSS, keyboard handling, page-hide pause, bounded static/test overrides, immediate final-step stop, and exact canonical-controller identity. Its adversarial tests mutate the canonical template to prove each failure is rejected.

Then verify in a browser:

1. Disable JavaScript: the complete diagram remains visible and meaningful.
2. Emulate `prefers-reduced-motion: reduce`: the final state is complete, playback controls are hidden and disabled, and the DOM status says playback is unavailable.
3. Use keyboard only: Tab reaches each native control; Enter/Space operate it; Left/Right/Home/End step without moving focus.
4. Pause, resume, and replay twice: ordering and final state are identical.
5. Capture `?motion=static` twice after `document.fonts.ready`: pixels are stable.
6. Print preview plus PNG/SVG export: controls and decorative tokens are absent, while all semantic labels and relationships remain.

## Anti-patterns

- Unrequested autoplay, autoplay outside the single sanctioned `reveal` run, viewport re-entry, or an endless semantic loop.
- A blank/partial no-JS or reduced-motion frame.
- Motion that rescues an over-dense or unlabeled static diagram.
- Pass/fail, queue fullness, or outcome encoded only by hue.
- Remote scripts, general application logic, runtime geometry, or duplicated semantic text.
- Capturing at wall-clock delay instead of the explicit static override.
- Disclosure that hides semantic content until hover or `:target`. Motion explains an ordered change; on-demand detail is a second diagram (overview + detail, SKILL.md §7), not a hidden panel. Hidden content is absent from PNG export, print, and touch, which breaks the static-first contract above.

One allowance: a nested `<title>` inside a node group — the native tooltip — may carry a short elaboration of something the diagram already labels. It degrades to nothing rather than to missing meaning.
