# Quantitative Polar Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified 28th visual type that renders one cyclic quantitative series as radial lollipops with angle=category and linear radius=magnitude.

**Architecture:** The public contract lives in `references/type-polar.md`; three static HTML examples carry machine-readable `data-polar-*` metadata. A dependency-free Python verifier recomputes all endpoints and rejects hubs, nonlinear radius, visible zero rays, invalid values, and variant drift. Existing routing, gallery, README, CI, and package manifests are updated as one minor release.

**Tech Stack:** Python standard library 3.10+, static HTML/CSS, inline SVG, existing repository validation scripts, headless Google Chrome for the README screenshot.

**Spec:** `docs/superpowers/specs/2026-08-18-polar-chart-design.md`

## Global Constraints

- Angle encodes category; radius encodes magnitude with `radius = R * value / max`.
- The shared scale starts at exactly zero; `max` is finite and greater than zero.
- Zero renders with no value ray and no endpoint marker; its numeric label remains visible.
- One series, 4–8 unique ordered categories, and at most one focal category.
- No filled quantitative wedges, donut hub, gradients, negative values, logarithmic scale, interaction, animation, or external assets.
- All three examples use the same values, `viewBox="0 0 1000 520"`, center `(500,230)`, radius `160`, max `100`, start angle `-90`, and clockwise order.
- Static examples must satisfy the accessible SVG contract and existing skin rules.
- No new runtime or test dependency.
- Add a minor plugin release: `2.4.4 → 2.5.0` unless `origin/main` advances first; after a rebase, rerun `python3 scripts/bump-plugin-version.py --minor` from the new base.

---

### Task 1: Build the quantitative polar verifier with adversarial tests

**Files:**
- Create: `scripts/test-verify-polar.py`
- Create: `scripts/verify-polar.py`

**Interfaces:**
- Produces: `check(path: Path) -> list[str]`, `check_variants(paths: Sequence[Path]) -> list[str]`, and CLI `python3 scripts/verify-polar.py [file ...]`.
- Consumes later: Task 2 uses the verifier as the RED/GREEN gate for the three examples; Task 4 adds both commands to CI.

- [ ] **Step 1: Write the failing verifier tests**

Create `scripts/test-verify-polar.py` with a fixture builder for a four-category chart. The valid fixture has center `(100,100)`, `R=100`, max `100`, angles `-90/0/90/180`, and values `0/25/50/100`:

```python
#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-polar.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_polar", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def category(index: int, value: int, endpoint: tuple[float, float] | None) -> str:
    body = '<text data-polar-value-label="">{}</text>'.format(value)
    if endpoint is not None:
        x, y = endpoint
        body = (
            f'<line data-polar-ray="" x1="100" y1="100" x2="{x}" y2="{y}"/>'
            f'<circle data-polar-marker="" cx="{x}" cy="{y}" r="4"/>' + body
        )
    return (
        f'<g data-polar-category="c{index}" data-polar-index="{index}" '
        f'data-polar-value="{value}">{body}</g>'
    )


def document(categories: str, extra_svg: str = "") -> str:
    return (
        '<!DOCTYPE html><html><body>'
        '<svg data-polar-chart="" data-polar-cx="100" data-polar-cy="100" '
        'data-polar-radius="100" data-polar-min="0" data-polar-max="100" '
        'data-polar-start-angle="-90" data-polar-clockwise="true" '
        'data-polar-radius-encoding="linear" data-polar-inner-radius="0">'
        f'{extra_svg}{categories}</svg></body></html>'
    )


VALID = document(
    category(0, 0, None)
    + category(1, 25, (125, 100))
    + category(2, 50, (100, 150))
    + category(3, 100, (0, 100))
)
```

In `main()`, write each fixture to a temporary file and assert these results:

```python
cases = [
    ("25 percent hub", VALID.replace('data-polar-inner-radius="0"', 'data-polar-inner-radius="25"'), "inner radius"),
    ("sqrt radius", VALID.replace('x2="125"', 'x2="150"').replace('cx="125"', 'cx="150"'), "linear endpoint"),
    ("visible zero ray", VALID.replace('<text data-polar-value-label="">0</text>', '<line data-polar-ray="" x1="100" y1="100" x2="100" y2="100"/><text data-polar-value-label="">0</text>'), "zero category"),
    ("out of range", VALID.replace('data-polar-value="100"', 'data-polar-value="101"'), "outside 0..100"),
    ("duplicate index", VALID.replace('data-polar-index="3"', 'data-polar-index="2"'), "indices"),
    ("quantitative wedge", VALID.replace('</svg>', '<path data-polar-wedge="" d="M0 0"/></svg>'), "wedge"),
]
```

Assert `check(valid_path) == []`. For every invalid case, assert at least one finding exists and one finding contains the named substring; do not assert the total count because a malformed value may correctly violate more than one invariant.

Also create three valid files and change the dark fixture's `data-polar-value="25"` to `26`; assert `check_variants()` reports `variant data drift`.

- [ ] **Step 2: Run the test to verify RED**

Run:

```bash
python3 scripts/test-verify-polar.py
```

Expected: fail while importing missing `scripts/verify-polar.py`.

- [ ] **Step 3: Implement the minimal verifier**

Create `scripts/verify-polar.py` using only `dataclasses`, `html.parser`, `math`, `pathlib`, `sys`, and `typing`.

Define these data structures and parser output:

```python
@dataclass
class Category:
    name: str
    index: int
    value: float
    focal: bool
    rays: list[dict[str, str]]
    markers: list[dict[str, str]]
    value_labels: int


@dataclass
class Chart:
    attrs: dict[str, str]
    categories: list[Category]
    wedge_count: int
```

`PolarParser(HTMLParser)` must capture exactly one element carrying `data-polar-chart`; capture `g[data-polar-category]`, its `line[data-polar-ray]`, `circle[data-polar-marker]`, and `text[data-polar-value-label]`; count any `path[data-polar-wedge]`.

Implement `check()` with these exact invariants:

```python
TOLERANCE = 0.75
required = (
    "data-polar-cx", "data-polar-cy", "data-polar-radius",
    "data-polar-min", "data-polar-max", "data-polar-start-angle",
    "data-polar-clockwise", "data-polar-radius-encoding",
    "data-polar-inner-radius",
)
expected_angle = radians(start_angle) + (1 if clockwise else -1) * 2 * pi * index / count
expected_radius = radius * value / maximum
expected_x = cx + expected_radius * cos(expected_angle)
expected_y = cy + expected_radius * sin(expected_angle)
```

Return findings for: missing/duplicate chart; missing or non-numeric metadata; min not zero; max/radius not positive; non-linear encoding; non-zero inner radius; category count outside 4–8; non-contiguous indices; duplicate trimmed names; more than one focal; value outside range; value-label count not one; zero carrying a ray or marker; positive value not carrying exactly one ray and marker; ray start not at center; ray/marker endpoint outside tolerance; any wedge.

Implement `check_variants()` by comparing this signature for all paths:

```python
signature = (
    cx, cy, radius, minimum, maximum, start_angle, clockwise,
    tuple((c.index, c.name, c.value, c.focal) for c in sorted(categories, key=lambda c: c.index)),
)
```

With no CLI arguments, validate the exact shipped paths `example-polar.html`, `example-polar-dark.html`, and `example-polar-full.html`; with arguments, validate those files. Print each finding as `FAIL <path>: <message>` and return 1 if any finding exists; otherwise print `OK <path>` and return 0.

- [ ] **Step 4: Run GREEN and confirm the shipped-file gate is still RED**

Run:

```bash
python3 scripts/test-verify-polar.py
python3 scripts/verify-polar.py
```

Expected: adversarial tests pass; shipped verifier fails because the three example files do not exist yet.

- [ ] **Step 5: Commit the verifier slice**

```bash
git add scripts/test-verify-polar.py scripts/verify-polar.py
git commit -m "test(polar): verify linear radius encoding"
```

---

### Task 2: Add the type reference and three verified static examples

**Files:**
- Create: `skills/diagram-design/references/type-polar.md`
- Create: `skills/diagram-design/assets/example-polar.html`
- Create: `skills/diagram-design/assets/example-polar-dark.html`
- Create: `skills/diagram-design/assets/example-polar-full.html`

**Interfaces:**
- Consumes: `scripts/verify-polar.py` and the approved spec.
- Produces: three identical `data-polar-*` datasets consumed by Task 3 gallery/docs wiring.

- [ ] **Step 1: Preserve the missing-example RED result**

Run:

```bash
python3 scripts/verify-polar.py
```

Expected: fail naming all three missing example files.

- [ ] **Step 2: Write `type-polar.md` from the approved contract**

Create these sections in order:

```markdown
# Polar Chart

**Best for:** one quantitative series across 4–8 categories whose clockwise order is meaningful.

## Input contract
## Quantitative encoding
### Zero
## Layout conventions
## Geometry
## Visual treatment
## Complexity budget
## When not to use
## Anti-patterns
## Examples
```

Copy the formulas, zero behavior, exclusions, scale validation, label-anchor rules, and `1000×520` reference geometry verbatim from the spec. The anti-pattern list must explicitly reject donut hubs, filled wedges, tangent labels, multiple series, truncated scales, sorted-by-value categories, and treating missing as zero. Route multiple series to Radar, non-cyclic categories to Bar, and more than eight time buckets to Line.

- [ ] **Step 3: Build the minimal-light example with exact geometry**

Start from `skills/diagram-design/assets/template.html`. Use this dataset and endpoint table; retain three decimals where shown so the verifier tolerance is meaningful:

| i | label | value | spoke end | value end | label point (`R+28`) |
|---|---|---:|---|---|---|
| 0 | 00–03 | 32 | `500,70` | `500,178.8` | `500,42` |
| 1 | 03–06 | 18 | `613.137,116.863` | `520.365,209.635` | `632.936,97.064` |
| 2 | 06–09 | 24 | `660,230` | `538.4,230` | `688,230` |
| 3 | 09–12 | 58 | `613.137,343.137` | `565.62,295.62` | `632.936,362.936` |
| 4 | 12–15 | 100 focal | `500,390` | `500,390` | `500,418` |
| 5 | 15–18 | 82 | `386.863,343.137` | `407.227,322.773` | `367.064,362.936` |
| 6 | 18–21 | 76 | `340,230` | `378.4,230` | `312,230` |
| 7 | 21–24 | 45 | `386.863,116.863` | `449.088,179.088` | `367.064,97.064` |

The primary SVG opening must be:

```html
<svg viewBox="0 0 1000 520" xmlns="http://www.w3.org/2000/svg"
     role="img" aria-labelledby="polar-title polar-desc"
     data-polar-chart data-polar-cx="500" data-polar-cy="230"
     data-polar-radius="160" data-polar-min="0" data-polar-max="100"
     data-polar-start-angle="-90" data-polar-clockwise="true"
     data-polar-radius-encoding="linear" data-polar-inner-radius="0">
```

Use `<circle>` grid rings at `r=32/64/96/128/160`, eight faint full-radius spokes, then one group per category:

```html
<g data-polar-category="00–03" data-polar-index="0" data-polar-value="32">
  <line data-polar-ray x1="500" y1="230" x2="500" y2="178.8"
        stroke="#4f5d75" stroke-width="2"/>
  <circle data-polar-marker cx="500" cy="178.8" r="4"
          fill="#f5f5f5" stroke="#4f5d75" stroke-width="1.2"/>
  <text data-polar-value-label x="500" y="26" ...>32</text>
</g>
```

Set `data-polar-focal="true"` only on `12–15`; use accent stroke and a 5 px endpoint marker there. Every other group uses muted. Put the scale values `20/40/60/80/100` on the top axis and a single `0` beside the center. Add `Illustrative normalized workload profile` below a hairline at the bottom. The `<desc>` must identify `12–15 UTC` as the 100% peak and state that the other seven windows proceed clockwise.

- [ ] **Step 4: Create dark and full variants without dataset drift**

Create `example-polar-dark.html` from `template-dark.html` and `example-polar-full.html` from `template-full.html`. Keep every `data-polar-*` attribute and all chart coordinates byte-equivalent to the light variant; only skin tokens and surrounding editorial cards differ.

The full variant has three unequal cards:

- `Peak · 12–15 UTC · 100%`
- `Quietest · 03–06 UTC · 18%`
- `Evening tail · 18–21 UTC · 76%`

Use prefixed accessible IDs `polar-dark-title/desc` and `polar-full-title/desc`.

- [ ] **Step 5: Run quantitative, skin, accessibility, and visual gates**

Run:

```bash
python3 scripts/test-verify-polar.py
python3 scripts/verify-polar.py
python3 scripts/lint-skin.py \
  skills/diagram-design/assets/example-polar.html \
  skills/diagram-design/assets/example-polar-dark.html \
  skills/diagram-design/assets/example-polar-full.html
python3 scripts/verify-geometry.py \
  skills/diagram-design/assets/example-polar.html \
  skills/diagram-design/assets/example-polar-dark.html \
  skills/diagram-design/assets/example-polar-full.html
```

Expected: all commands exit 0 and report zero findings.

Open each HTML file in a fresh browser tab. Verify: the focal ray is the only accent; rings do not read as filled wedges; labels are upright and unclipped; `03–06` visibly lands at 18%; the full card layout does not change SVG geometry.

- [ ] **Step 6: Commit the reference and examples**

```bash
git add \
  skills/diagram-design/references/type-polar.md \
  skills/diagram-design/assets/example-polar.html \
  skills/diagram-design/assets/example-polar-dark.html \
  skills/diagram-design/assets/example-polar-full.html
git commit -m "feat(types): add quantitative polar chart"
```

---

### Task 3: Wire the 28th type through routing, gallery, documentation, and count gates

**Files:**
- Modify: `skills/diagram-design/SKILL.md:1-13,52,81-112,356-385`
- Modify: `skills/diagram-design/assets/index.html:197-309`
- Modify: `README.md:15-88,188,209,373,431`
- Create: `docs/screenshots/polar.png`
- Modify: `commands/import-drawio.md:25`
- Modify: `commands/import-mermaid.md:25`
- Modify: `skills/diagram-design/references/onboarding.md:162`
- Modify: `skills/diagram-design/references/semantic-patterns.md:3`
- Modify: `docs/adr/0002-semantic-patterns-do-not-expand-the-taxonomy.md:1-17`
- Modify: `CONTRIBUTING.md:11,130`
- Modify: `scripts/verify-docs-sync.py:22-79`
- Modify: `scripts/verify-semantic-motion.py:190-207,422`
- Modify: `scripts/test-verify-motion.py:401-415`

**Interfaces:**
- Consumes: `type-polar.md` and the three examples from Task 2.
- Produces: discoverable routing vocabulary, 28-row taxonomy, gallery reachability, and count assertions consumed by Task 4 CI.

- [ ] **Step 1: Raise the count gates first and verify RED**

In `scripts/verify-docs-sync.py`, add `VISUAL_TYPE_COUNT = 28` beside `VARIANTS` and replace both hardcoded `27` values in `check_description()` with the constant.

In `scripts/verify-semantic-motion.py`, add `VISUAL_TYPE_COUNT = 28`, derive `guide_heading = f"### Visual-type guide ({VISUAL_TYPE_COUNT})"`, require 28 rows, and update the success message. In `scripts/test-verify-motion.py`, replace the missing-guide fixture and expected diagnostic with `28`.

Run:

```bash
python3 scripts/verify-docs-sync.py
python3 scripts/verify-semantic-motion.py --markdown-only
```

Expected: both fail because SKILL.md still has 27 rows and the old heading.

- [ ] **Step 2: Add Polar to SKILL.md and the complexity budget**

Make these exact routing changes:

- Add `polar/radial lollipop` to the frontmatter description.
- Change `metadata.version` from `2.4` to `2.5`.
- Change `Twenty-seven` and both numeric `27` references to `Twenty-eight`/`28`.
- Rename the heading to `### Visual-type guide (28)`.
- Add this row immediately after Radar:

```markdown
| One quantitative series across cyclic categories; angle=category, radius=magnitude | **Polar chart** | [type-polar.md](references/type-polar.md) |
```

- Add complexity rows `Max polar categories | 8`, `Max polar series | 1`, and `Max focal polar categories | 1` after the radar rows.

Run `python3 scripts/verify-docs-sync.py`; expect the type-count and description/reference checks to be repaired, with the command still failing only because the new examples are not gallery-reachable yet.

- [ ] **Step 3: Register all three examples in the gallery**

Insert a non-`data-single` tab immediately after Radar:

```html
<button class="tab new" data-type="polar">
  <span class="eyebrow">16</span>Polar
</button>
```

Increment every later numeric eyebrow so gallery numbers remain unique and ascending. Do not change `data-type`, `data-single`, variant behavior, or keyboard navigation.

Run:

```bash
python3 scripts/verify-docs-sync.py
```

Expected: gallery reachability passes for `example-polar{,-dark,-full}.html`.

- [ ] **Step 4: Update every current count surface while preserving historical text**

Change active product claims from 27 to 28 in README, CONTRIBUTING, both import commands, onboarding, semantic-patterns, and ADR 0002. In ADR 0002, explain that Polar is the first admitted new grammar and the invariant is now 28. Do not alter ADR 0004's historical statement that v2.3 once carried 27 type names.

Add this README gallery cell in the final row:

```html
<td align="center"><img src="docs/screenshots/polar.png" alt="Polar chart"><br><b>Polar chart</b><br><sub>Cyclic magnitude · linear radius</sub></td>
```

Keep the third cell empty unless another type lands during rebase.

- [ ] **Step 5: Generate and inspect the README screenshot**

Run from the repository root:

```bash
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
page="file://$(pwd)/skills/diagram-design/assets/example-polar.html"
"$chrome" --headless=new --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1200,601 --screenshot=docs/screenshots/polar.png "$page"
sips -g pixelWidth -g pixelHeight docs/screenshots/polar.png
```

Expected dimensions: `2400 × 1202`. Inspect the PNG and confirm the entire chart, title, labels, and source note are visible with no browser chrome.

- [ ] **Step 6: Run routing/count tests and the SKILL.md byte cap**

```bash
python3 scripts/verify-docs-sync.py
python3 scripts/test-verify-docs-sync.py
python3 scripts/verify-semantic-motion.py --markdown-only
python3 scripts/test-verify-motion.py
```

Expected: all pass; semantic verification reports 28 visual types and SKILL.md remains below 40,000 bytes.

- [ ] **Step 7: Commit the routing and documentation slice**

```bash
git add \
  skills/diagram-design/SKILL.md \
  skills/diagram-design/assets/index.html \
  README.md docs/screenshots/polar.png \
  commands/import-drawio.md commands/import-mermaid.md \
  skills/diagram-design/references/onboarding.md \
  skills/diagram-design/references/semantic-patterns.md \
  docs/adr/0002-semantic-patterns-do-not-expand-the-taxonomy.md \
  CONTRIBUTING.md \
  scripts/verify-docs-sync.py scripts/verify-semantic-motion.py \
  scripts/test-verify-motion.py
git commit -m "docs(polar): register the 28th visual type"
```

---

### Task 4: Add CI coverage and publish the minor package version

**Files:**
- Modify: `.github/workflows/ci.yml:140-222`
- Modify: `CONTRIBUTING.md:40-82`
- Modify: `.claude-plugin/plugin.json`
- Modify: `.codex-plugin/plugin.json`

**Interfaces:**
- Consumes: verifier/tests from Task 1 and examples from Task 2.
- Produces: cross-platform CI enforcement and synchronized release version `2.5.0`.

- [ ] **Step 1: Add the polar gate to CI**

Insert after the skin linter:

```yaml
- name: Verify quantitative polar chart
  if: always()
  id: polar
  shell: bash
  run: |
    python scripts/test-verify-polar.py
    python scripts/verify-polar.py
```

Add this row to the execution summary after Color Palette & Skin Linter:

```yaml
echo "| Quantitative Polar Chart | ${{ steps.polar.outcome == 'success' && '✅ Passed' || (steps.polar.outcome == 'skipped' && '⏭️ Skipped' || '❌ Failed') }} |" >> $GITHUB_STEP_SUMMARY
```

- [ ] **Step 2: Add the local gate to CONTRIBUTING**

Add table row:

```markdown
| Quantitative polar encoding and variant parity | `python3 scripts/test-verify-polar.py && python3 scripts/verify-polar.py` |
```

Add both commands after `lint-skin.py --all --baseline` in the combined validation command.

- [ ] **Step 3: Bump both package manifests together**

Run:

```bash
python3 scripts/bump-plugin-version.py --minor
jq -r '.version' .claude-plugin/plugin.json .codex-plugin/plugin.json
```

Expected: both print `2.5.0`. If main advanced, the expected value is the next minor derived from the rebased synchronized version.

- [ ] **Step 4: Verify package and CI YAML**

```bash
python3 scripts/test-plugin-package.py
python3 scripts/verify-plugin-package.py origin/main
claude plugin validate . --strict
python3 -c 'import yaml, pathlib; yaml.safe_load(pathlib.Path(".github/workflows/ci.yml").read_text())' 2>/dev/null \
  || ruby -e 'require "yaml"; YAML.load_file(".github/workflows/ci.yml"); puts "CI YAML OK"'
```

Expected: package checks pass, both versions are synchronized and increasing, plugin validation passes, and one available YAML parser accepts the workflow.

- [ ] **Step 5: Commit CI and release metadata**

```bash
git add \
  .github/workflows/ci.yml CONTRIBUTING.md \
  .claude-plugin/plugin.json .codex-plugin/plugin.json
git commit -m "ci(polar): enforce quantitative chart contract"
```

---

### Task 5: Run the complete release gate on the exact committed tree

**Files:**
- Verify only; modify only files named by a failing, reproducible gate.

**Interfaces:**
- Consumes: every artifact from Tasks 1–4.
- Produces: evidence that the exact branch tip is PR-ready.

- [ ] **Step 1: Confirm scope and branch provenance**

```bash
git status --short --branch
git diff --stat origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

Expected: branch `feat/polar-chart`; no uncommitted files; only spec, plan, polar feature, count/docs, CI, screenshot, and version files.

- [ ] **Step 2: Run the complete CONTRIBUTING suite plus the new gate**

```bash
python3 scripts/test-plugin-package.py \
  && python3 scripts/verify-plugin-package.py origin/main \
  && claude plugin validate . --strict \
  && python3 scripts/test-lint-a11y.py \
  && python3 scripts/verify-semantic-motion.py --markdown-only \
  && python3 scripts/verify-semantic-motion.py --example-only \
  && python3 scripts/verify-motion.py --shipped \
  && python3 scripts/lint-skin.py --all --baseline \
  && python3 scripts/test-verify-polar.py \
  && python3 scripts/verify-polar.py \
  && python3 scripts/verify-sequence-oauth.py \
  && python3 scripts/verify-drawio-import.py \
  && python3 scripts/verify-mermaid-import.py \
  && python3 scripts/test-verify-motion.py \
  && python3 scripts/verify-docs-sync.py \
  && python3 scripts/test-verify-docs-sync.py \
  && python3 scripts/test-self-check.py \
  && python3 scripts/verify-geometry.py --all \
  && python3 scripts/test-verify-geometry.py \
  && python3 scripts/build-icons.py \
  && git diff --ignore-space-at-eol --exit-code -- \
       skills/diagram-design/assets/icons.html \
       skills/diagram-design/references/primitive-icons.md
```

Expected: exit 0, no failures, no warnings from plugin validation, zero lint/geometry findings, and no generated icon drift.

- [ ] **Step 3: Reconfirm a clean committed snapshot**

```bash
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: no whitespace findings and no working-tree changes. If `build-icons.py` created only line-ending changes, confirm `git diff --ignore-space-at-eol --exit-code` returns 0, then restore only the two generated icon files before reporting completion.
