# Sketchy Filter (hand-drawn variant)

Optional displacement filter that wobbles every stroke and edge slightly — turns any minimal variant into a hand-drawn "editorial" register without changing layout. Use when the diagram accompanies an essay rather than technical docs.

## Grammar

```svg
<defs>
  <filter id="sketchy" x="-2%" y="-2%" width="104%" height="104%">
    <feTurbulence type="fractalNoise" baseFrequency="0.02" numOctaves="2" seed="4"/>
    <feDisplacementMap in="SourceGraphic" scale="1.5"/>
  </filter>
</defs>

<!-- Apply to a group wrapping shapes — NOT text -->
<g filter="url(#sketchy)">
  <!-- rects, paths, circles, lines go here -->
</g>

<!-- Text sits OUTSIDE the filtered group — legibility stays crisp -->
<text ...>Labels go here</text>
```

## Tuning

| Parameter | Range | Effect |
|---|---|---|
| `baseFrequency` | 0.01–0.04 | Lower = lazy wavy lines; higher = jittery. 0.02 default. |
| `numOctaves` | 1–3 | More = more noise detail. 2 is plenty. |
| `scale` | 1–6 | 1 barely-there, 1.5 default, 2 visible, 4+ cartoon. |
| `seed` | integer | Swap for a different random pattern. |

## Critical rule
Filter shapes, NOT text. Displacement-mapped text becomes illegible. Structure your SVG so text is in a sibling group outside the filtered group.

## When to use
- Essay / blog post / newsletter where the diagram is the hero of a narrative page.
- "Working sketch" register — showing something is mid-thought, not final architecture.

## When not to use
- Technical documentation (precision matters).
- Diagrams with dense labels or tight alignments (filter reads as noise).
- Dark variants — wobble reads as artifact on dark backgrounds. Test first.
