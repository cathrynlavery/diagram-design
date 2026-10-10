# Changelog

All notable changes to diagram-design are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning note: pull requests do not edit the plugin version. After each merge to `main`, the Auto Version Bump workflow raises the Claude, Codex, and Factory manifest versions together, a patch by default or a minor or major when a merged PR carries a `release:minor` or `release:major` label. Rapid merges can share one bump, and before that workflow existed some patch numbers were reserved and never shipped, so the patch numbers below have gaps. See [ADR 0009](docs/adr/0009-versions-are-bumped-on-main-after-merge.md). This file groups releases by minor version and summarizes them; dates come from the git history of the manifest version field.

## [Unreleased]

### Added

- A WCAG contrast gate in CI.
- An offline option that uses system fonts, so generated output works without loading Google Fonts.
- `CONTRIBUTING.md` now holds the contributor internals that used to live in the README.

### Changed

- The default light skin's accent is darker, `#bf4520`, so accent text reaches 4.71:1 on paper. The soft and link tokens were adjusted on both skins to match (#161).
- Type references use the skin's role tokens instead of the default skin's hex values, so they follow whichever skin is active (#65, based on #66).
- The README is reorganized around a demo, a comparison table, and separate install sections.

### Fixed

- Gallery numbering uses one number per diagram type, 44 in total.

## [2.6] - 2026-08-20

Covers 2.6.0 to 2.6.70 (2026-08-20 to 2026-10-09).

### Added

- Polar chart as a quantitative visual type, `doctor` diagnostics, and a lint pass that renders every diagram in Chromium (#134).
- Line variants: ridgeline (#143), bump chart (#160), and streamgraph (#140).
- Scatter variants: bubble for three-value comparisons (#141) and beeswarm (#160).
- Treemap variant: marimekko (#231).
- New visual types: waterfall, a running-total grammar with a conservation verifier (#191); heatmap (#164); architecture delta, with Before, Changes, and After panels and a change ledger (#241); exploded axonometric (#268); and axonometric plan (#270). The taxonomy now stands at 44 types.
- Axonometric teaching examples: an AI agent stack, a keyboard, a coffee shop, and a warehouse (#274).
- Excalidraw import, a third redraw pipeline next to draw.io and Mermaid (#192).
- Semantic patterns: traceable block decomposition with a `.registry.json` export mode (#169), and lifecycle phase map, routed to the State Machine type (#228).
- A `print-a3-landscape` size preset (#248).
- Traditional Chinese fonts and a labels section (#186), a Cyrillic title fallback (#221), and CJK faces in the exported SVG font import (#196).
- Install paths for GitHub Copilot (#218) and `npx skills add` (#199).
- Codex manifest fields and an upload ZIP builder for OpenAI's plugin directory, plus `PRIVACY.md` (#264, #265).
- Light and dark README hero banner and a social preview image (#263), and diagramdesign.dev as the project homepage (#273).
- Adversarial tests for the semantic motion and sequence verifiers (#69).

### Changed

- Manifest versions are bumped on `main` after each merge instead of inside pull requests, and CI rejects PRs that edit them (#172). Follow-up CI fixes allow patch bumps without SKILL.md metadata changes (#194), detect real version bumps (#207), and judge PR versions against the merge commit's first parent (#255).
- Required local gates are derived from `ci.yml` (#261).
- SKILL.md detail moved to `primitives-core` and `layout-budget` references (#259), the type ramp is documented separately from the 4px layout grid (#182), and label width budgets allow for font substitution (#240).
- The README points at the type taxonomy instead of a hardcoded count, with a gate (#212), and the directory listing names the chart variants (#266).
- Plugin descriptions fit the Cowork length limit (#216).

### Fixed

- SVG export: rgba() and `transparent` are normalized for PowerPoint (#151), CSS and namespaced defs IDs carry over into standalone SVG (#235), and a batch of export and doctor fixes covers filenames with `#` or `%`, animated diagrams captured on a hidden first frame, quoted `url("#id")` references, and named entities in labels (#348).
- PNG export: the rasterize wait is bounded so proxied networks do not hang (#183).
- Templates have a local scroller and a min-width matched to the viewBox, so they no longer break at phone widths (#245).
- Import: compact multidirectional Mermaid labels (#131), whitespace in dotted-link labels (#210), Mermaid block selection (#269), nested draw.io coordinates (#223), Excalidraw cycles through bidirectional arrows (#224), and a batch covering draw.io arrowheads, parent-relative geometry, and Mermaid composite states (#349).
- Verifiers: browser-accurate parsing for slopegraph, ridgeline, and bubble (#230), root-only title and desc in motion checks (#260), decorative SVGs exempt from naming checks (#330), translated label masks compared in canvas space (#327), example connectors that route from their own ports, with the geometry verifier now catching stacked, diagonal, and corner-exiting connectors (#279), plus batched chart, polarity, and accessibility verifier fixes (#350, #351).
- Gallery: mobile preview height (#135), duplicate slopegraph eyebrow number (#136), and contiguous ordinals 01 to 52 with a gate (#233).
- Flowchart examples and the default template match the diagram specs (#277).
- `doctor` handles a `python3` that cannot report its version (#201) and argument hints are valid YAML (#155).
- SKILL.md stays LF and its byte cap is measured on LF bytes (#256); the screenshot freshness gate hashes sources as canonical text (#253).
- Skill guidance passes Hermes Skills Guard without changing diagram or import behavior (#167).
- Asset citations point at files that exist, with a link integrity check (#193), and the README icon count is correct (#180).
- Reviewed corrections across Mermaid edge labels, the draw.io example route, the Line dark example, and Chinese font stacks (#174).

### Security

- Fetched onboarding HTML is treated as untrusted data, enforced by docs-sync tests (#160).
- The packaged self-check rejects CSS asset loading through `@import`, `url()`, and `image-set()` (#205).
- Import limits: Mermaid statements are capped at 4,096 characters (#258), Excalidraw rejects duplicate element IDs (#280), and draw.io parsing rejects duplicate cell IDs, caps pages and cells, and rejects non-finite or cyclic geometry (#281, #283).

## [2.5] - 2026-08-18

Covers 2.5.0 to 2.5.20 (2026-08-18 to 2026-08-19).

### Added

- Treemap for part-of-whole by area (#87).
- Bar variant dumbbell (#107) and Line variant slopegraph (#106).
- Ten visual types in one release: Sankey, fishbone, Wardley map, kanban, user journey, deployment, dependency graph, UML class, story map, and database schema (#118), with a refreshed 38-type gallery (#119).
- Native Factory Droid plugin packaging, sharing one plugin root with Claude and Codex (#120).

### Changed

- Datalake examples are registered as unclustered High-Level variants (#100).
- CI actions moved to Node 24 runtimes (#128).

### Fixed

- Treemap fails closed for CJK label widths and verifies every cell share (#121, #124, #127).
- Import extractors emit UTF-8 on Windows (#122).
- The linter enforces accessible SVG viewBox and title rules (#123).
- Skill references are bundle-safe, so strict bundlers include every runtime file (#125).
- The draw.io import command reference stays in sync (#109).

### Security

- Untrusted labels are escaped in the draw.io Markdown digest (#91).

## [2.4] - 2026-08-14

Covers 2.4.0 to 2.4.8 (2026-08-14 to 2026-08-18).

### Added

- Named client profiles in `~/.diagram-design/profiles/` with marker-first project resolution (#61).

### Fixed

- The linter allows the documented CJK and Korean fallback font stacks (#75, #83) and runs on Python 3.9 again (#58).
- Mermaid import handles quoted participants, `create`, the full sequence arrow vocabulary (#54), and compact labeled links (#85).
- The gallery has keyboard navigation (#56).
- The geometry verifier recognizes wider label masks (#84).
- README slash-command names match the shipped commands (#82).

## [2.3] - 2026-08-12

Covers 2.3.0 to 2.3.5 (2026-08-12 to 2026-08-14).

### Added

- Seven semantic behavior patterns and optional accessible motion with static, print, export, and reduced-motion fallbacks (#40).
- A pre-draw checkpoint, a docs-sync CI gate, a packaged `self_check.py`, and the first ADRs (#41).
- Automatic updates through each host's native marketplace, with a version gate (#44).
- Animated examples for the fan-in queue and secure paved road patterns (#49, #51).

### Changed

- Product naming is unified as diagram and diagram-design (#50).

### Fixed

- The first-run style gate checks the palette that actually ships (#42).
- Exported SVG escapes ampersands in the injected font import (#38).
- Label masks are no longer clipped by node fills (#46).

### Security

- Resource and script linting rejects remote assets, executable attributes, duplicate controllers, and modified controller code (#40).

## [2.2] - 2026-08-11

Covers 2.2.0 only.

### Added

- Mermaid import, redrawing `.mmd`, `.mermaid`, and fenced Markdown blocks at a chosen format, size, and detail level (#24).
- A CI matrix across Linux, Windows, and macOS with failure screenshots (#28).
- A live gallery on GitHub Pages (#36).
- `CONTRIBUTING.md`, a code of conduct, and issue and PR templates (#29).

### Fixed

- Mojibake arrow directions (#30), Devicon viewBox dimensions (#31), and quoted URL attributes in icons (#32).

## [2.1] - 2026-08-11

Covers 2.1.0 only.

### Added

- draw.io import and the `/diagram-design:import` redraw workflow for raw, compressed, PNG-embedded, and SVG-embedded files (#22).
- A GitHub Actions workflow that runs the lint and verification gates (#23).
- The accessible SVG pattern as a linted contract: `role="img"`, a resolving `aria-labelledby`, and `<title>` and `<desc>` slots in every template (#25).

### Security

- draw.io extraction bounds decoding and rejects DTDs and entities (#22).

## [2.0] - 2026-07-14

Covers 2.0.0 (2026-07-14 to 2026-08-11).

### Added

- Twelve diagram types from a curated fork merge: radar, bar, line, Gantt, scatter, IT current-state, high-level, process, medallion, data flow, DP integration, and DP security matrix. The merge also brought an 86-icon primitive, the export command, onboarding that pulls brand tokens from a URL, skill, or folder, and mandatory connector rules (#10).
- The Loop type for flywheels with a shared-memory hub, and the `lint-skin.py` palette linter (#11).
- A terminal primitive, a charcoal CLI-window skin (#12).
- Combined fragments (`alt`, `opt`, `loop`) for sequence diagrams and an OAuth example set (#13, #14).
- Native Pi package support (#19).
- `SECURITY.md` with a reporting process (#16).

### Fixed

- The SAS icon source URL (#15).

[Unreleased]: https://github.com/cathrynlavery/diagram-design/compare/75f47bb...main
