# Quantitative Polar Chart Design

## Purpose

Add a 28th visual type, **Polar chart**, for one quantitative series whose categories have a meaningful circular order. The type fills the layout gap accepted in issue #60 while narrowing the earlier wheel proposal to a truthful quantitative contract:

- angle encodes category;
- radius encodes magnitude linearly from an explicit zero baseline;
- wedge area encodes nothing;
- static HTML/SVG remains the only shipped output.

The type is a radial lollipop chart, not a profile wheel. Full-radius grid spokes establish the category axes; a value ray from the center and a small endpoint marker encode each observation.

## Scope

Version 1 supports:

- one quantitative series;
- 4–8 equally spaced categories in a meaningful clockwise order;
- a shared linear scale with `min = 0` and `max > 0`;
- five circular grid rings at 20%, 40%, 60%, 80%, and 100%;
- one optional focal category rendered with the accent token;
- minimal light, minimal dark, and full-editorial examples;
- horizontal, upright category labels outside the outer ring;
- one numeric value label per category.

Version 1 excludes:

- DISC, personality, competency, and role-profile wheels whose sectors are qualitative;
- arbitrary point placement within sectors;
- filled quantitative wedges, gradient bands, or donut hubs;
- multiple series, negative values, logarithmic scales, unequal sector angles, and more than eight categories;
- animation or interaction.

Use Radar for multiple entities scored across common criteria, Line for more than eight ordered time buckets, and Bar when circular order adds no meaning.

## Input Contract

```yaml
title: "Request demand by UTC window"
unit: "% of daily peak"
scale:
  min: 0
  max: 100
categories:
  - { label: "00–03", value: 32 }
  - { label: "03–06", value: 18 }
  - { label: "06–09", value: 24 }
  - { label: "09–12", value: 58 }
  - { label: "12–15", value: 100, focal: true }
  - { label: "15–18", value: 82 }
  - { label: "18–21", value: 76 }
  - { label: "21–24", value: 45 }
start_angle: -90
clockwise: true
source_note: "Illustrative normalized workload profile"
```

Validation rules:

1. `scale.min` is exactly `0`; truncated radial scales are invalid.
2. `scale.max` is finite and greater than `0`.
3. Every value is finite and satisfies `0 <= value <= scale.max`.
4. Category labels are unique after trimming and category count is 4–8.
5. At most one category is focal.
6. Categories retain input order; sorting by value would destroy circular meaning.

## Quantitative Encoding

For category `i` of `N`, value `v`, center `(cx, cy)`, and outer radius `R`:

```text
theta_i = start_angle + clockwise_sign * 2π * i / N
radius_i = R * v / scale.max
x_i = cx + radius_i * cos(theta_i)
y_i = cy + radius_i * sin(theta_i)
```

Angles are expressed in radians for calculation; `start_angle` is supplied in degrees and defaults to `-90`, placing the first category at twelve o'clock. `clockwise_sign` is `+1` for the default clockwise order and `-1` otherwise.

The value ray is the line segment from `(cx, cy)` to `(x_i, y_i)`. Its visible length is exactly proportional to `v`. Endpoint circles have constant radius and encode no additional quantity. No filled sector may sit behind or beneath a value ray, because its area would compete with the declared radius encoding.

The element carrying `data-polar-chart` must be the chart's root `<svg>`. Its descendants are limited to `<g>`, `<line>`, `<circle>`, `<rect>`, `<text>`, `<title>`, and `<desc>`; nested SVGs, paths, polygons, external references, images, and every other element are rejected. Duplicate attributes, mismatched markup, URL-valued SVG references, transforms, CSS loading through `@import`/`url()`, and geometry-affecting CSS are forbidden. Chart elements carry neither `class` nor inline `style`; document styles may not use selectors capable of matching the chart, except the canonical root `svg` layout rule. The only external stylesheet allowed is Google Fonts. Every line carries exactly one of `data-polar-spoke`, `data-polar-ray`, or `data-polar-rule` and uses the role's declared stroke width; spoke and ray geometry is verified within `min(0.75 px, 5% of R)`. The five grid circles carry `data-polar-ring`, use `fill="none"`, a 0.8 px stroke, the chart center, and the 20% through 100% radius intervals exactly once. Every endpoint circle carries `data-polar-marker` and uses the declared 4 px radius, or 5 px for the focal category, with a 1.2 px stroke. The optional full-canvas background is the only rectangle and carries `data-polar-background`. This fail-closed allowlist prevents contributors from bypassing the radius-only encoding with an unannotated or falsely annotated filled shape.

### Zero

For `v = 0`, `radius_i = 0`. Render no value ray and no endpoint marker. Keep the faint full-radius category spoke, and render the category's numeric label as `0`. A single scale label at the center also marks the shared zero baseline. Do not add a minimum hub, minimum ray length, displaced marker, or other visible magnitude.

### Missing values

Missing values are out of scope for the first version. The agent must stop and ask whether to omit the category or supply a value; it must not coerce missing data to zero.

## Geometry and Layout

All three examples use `viewBox="0 0 1000 520"`, center `(500, 230)`, and `R = 160`.

- Grid rings: `r = 32, 64, 96, 128, 160`.
- Category spokes: center to `R`, 0.8 px rule stroke, no arrowhead.
- Non-focal value rays: 2 px muted stroke; endpoint marker radius 4.
- Focal value ray: 2.4 px accent stroke; endpoint marker radius 5.
- Ring labels: `0.2 × max` through `1.0 × max` on the first axis only, Geist Mono 8 px; the example therefore shows `20, 40, 60, 80, 100`.
- Category labels: at `R + 28`, Geist Sans 11 px semibold, horizontal and upright.
- Numeric labels: at `R + 44`, Geist Mono 8 px, including the unit in the chart subtitle rather than repeating it eight times.
- Label anchor: `middle` within 15 degrees of vertical, `start` on the right half, and `end` on the left half.
- Drawing order: background, rings, spokes, scale labels, non-focal rays, focal ray, endpoint markers, category labels, numeric labels, legend/source note.

The minimal examples use the full 1000×520 canvas. The full-editorial example places the same chart in the existing editorial frame and adds summary cards without changing chart geometry.

## Visual Semantics

- One accent category maximum. All other value rays use the muted token.
- Circular rings and spokes are structural grid marks, never category colors.
- Endpoint markers are constant-size lollipop heads, not bubbles.
- Category labels remain horizontal; tangent rotation is intentionally excluded because it lowers scanability and belongs to the rejected qualitative wheel direction.
- The chart must remain understandable in grayscale: position and numeric labels carry the data; accent only directs attention.
- The SVG accessible description names the peak category, the scale, and the clockwise category order without narrating geometry.

## Example Dataset

All three variants use the input contract above. The values are explicitly illustrative, normalized as a percentage of the daily peak, and make no external factual claim. `12–15` is the focal category at `100`; `03–06` is the minimum at `18`.

The examples intentionally do not include zero because the zero rule is validated by an adversarial verifier fixture rather than by changing the primary editorial story.

## Taxonomy and Documentation

The implementation will:

1. Add `references/type-polar.md` and route “polar chart”, “radial lollipop”, “cyclical magnitude”, and equivalent requests to it.
2. Add **Polar chart** to the SKILL.md visual-type guide and frontmatter description.
3. Change the shipped visual-type count from 27 to 28 across README, SKILL.md, onboarding/reference prose, validation scripts, and ADR 0002.
4. Add the three examples to the gallery as `example-polar.html`, `example-polar-dark.html`, and `example-polar-full.html`.
5. Add a README gallery cell and screenshot for the new type.
6. Use a minor plugin version bump because this adds a public visual type.

ADR 0002 remains valid: semantic patterns do not expand the taxonomy. Its count changes because Polar supplies a genuinely new quantitative circular layout grammar, the exception already allowed by the ADR.

## Machine Verification

Each example's primary SVG carries:

```html
<svg data-polar-chart data-polar-cx="500" data-polar-cy="230"
     data-polar-radius="160" data-polar-max="100" ...>
```

Each category is a group with `data-polar-category`, `data-polar-index`, and `data-polar-value`. Positive categories contain one `line[data-polar-ray]` and one `circle[data-polar-marker]`; zero categories contain neither.

A new `scripts/verify-polar.py` gate will:

- require the exact three shipped variants;
- enforce category count, unique indices, shared zero baseline, and at most one focal category;
- recompute every positive endpoint from angle and linearly scaled radius within `min(0.75 px, 5% of R)`;
- reject a ray or endpoint marker for zero;
- allowlist the chart's SVG elements and semantic area-bearing roles, rejecting unannotated or falsely annotated filled shapes, transforms, and non-zero inner baselines;
- confirm all three variants carry identical values and geometry metadata.

`scripts/test-verify-polar.py` will cover a valid chart plus adversarial cases for a 25% hub, square-root radius encoding, a visible zero ray, out-of-range values, duplicate indices, and variant data drift. CI and CONTRIBUTING will run both scripts.

## Acceptance Criteria

- Radius, not area, is the only graphical magnitude encoding.
- A zero-valued category produces zero ray length and remains legible through its numeric label.
- All three examples are static, self-contained, accessible, gallery-reachable, and skin-clean.
- The verifier fails on the known #64 baseline defect and passes the shipped examples.
- The visual-type count and routing vocabulary are consistent across every documented surface.
- Both plugin manifests receive the same minor version.
- The complete CONTRIBUTING validation suite passes on Python 3.11 and 3.12 without adding dependencies.
