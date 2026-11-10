# Export to SimpleDiagrams (`--simplediagrams`)

Write a diagram as an editable `.simplediagram` document for the SimpleDiagrams editor on macOS. **Manual only — never run unprompted. Run on `--simplediagrams` or an explicit request to keep editing a diagram in SimpleDiagrams.**

## Trigger

Load this file when the user invokes `/diagram-design:export-diagram <html-file> --simplediagrams`, or asks to keep editing a diagram in SimpleDiagrams.

## Scope

The output is a new document in SimpleDiagrams document format 19, drawn in SimpleDiagrams' hand-drawn style. Like the other exports it holds the `<svg>` diagram only. Boxes become shapes from SimpleDiagrams' built-in Basic library and keep their text; arrows become connectors attached to the boxes they touch, carrying their labels, and a square route keeps only its corners (rounded corners and hops over crossing lines are drawn plain); lanes become a Swimlanes shape; anything drawn on a box is grouped with it; other lines and text keep their place. An outline is replaced by a Basic shape only when it is labelled or an arrow ends on it, so the faces of an exploded or axonometric drawing keep their exact geometry.

## Procedure

From this skill's directory run:

```
python3 scripts/export_simplediagrams.py <html-file> [<out.simplediagram>]
```

It reads the diagram through `scripts/export_svg.py`, needs only the Python standard library, and makes no network request. The default output is `<basename>.simplediagram` next to the source. Re-exporting an unchanged diagram produces identical files.

## Edge cases

- **The output already exists:** refuse and ask for another name. An existing document may hold the user's edits, so it is never replaced.
- **Source is `assets/index.html`:** refuse, as for SVG/PNG — ask which diagram file.
- **Icons:** icons placed with `<use>` or a nested `<svg>` are stored in the document as vector artwork, together with any gradient, pattern or marker they use from the page's shared `<defs>`. An icon holding anything active, filtered or linked is left out with a note.
- **Notes:** the helper prints one `note:` line per kind of content it could not keep exactly. Pass the notes on to the user.

## What it reads

The export reads the drawing as a browser draws it, within this contract:

- **Elements:** `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon`, `path`, `text` and `tspan`, `g`, nested `svg`, `use` with `symbol`, `marker`, and `foreignObject` holding plain HTML text.
- **Style:** presentation attributes, inline styles and stylesheet rules whose selectors use tags, `*`, classes, IDs, `:root` and descendants; `!important`; `var()` with fallbacks; and `inherit`, `initial`, `unset` and `revert`. Rules inside `@layer` blocks, nested rules and other selectors (attributes, children, siblings, pseudo-classes) are not applied. Conditional rules (`@media`, `@supports`) are skipped: the export draws the page's default view. Selectors can match the HTML root and body as ancestors of an embedded SVG. For a standalone SVG, `:root` selects the drawing itself.
- **Values:** lengths in `px`, `pt`, `pc`, `in`, `cm`, `mm`, `em`, `rem` (16 px) and percentages; colours as hex, `rgb()`, `rgba()`, `currentColor` and the basic colour names. A font size given with `calc()`, `clamp()` or viewport units is drawn at the surrounding size.

Lines take SimpleDiagrams' own hand-drawn line style, which the format sets for every shape: line caps, joins, miter limits, dash lengths and dash offsets are drawn in that style, a dash pattern becoming dashed or dotted. `dominant-baseline` and `letter-spacing` do not move or space a label.

## Notes it prints

Each is printed once per kind, with a count. The exporter conservatively reports possible overlap when a translucent group or path is too large to check every pair of parts. `<element>` stands for the element's tag.

- `stylesheet rules this export cannot read left unapplied`
- `CSS transform this export cannot read may misplace a shape`
- `sizes, places and corners set in CSS ignored; the SVG's own are used`
- `gradient, pattern or unknown colour, left transparent`
- `clipping and masks left out; shapes are drawn unclipped`
- `filters such as blur and shadow left out`
- `blend modes left out; shapes are drawn over one another plainly`
- `see-through groups and outlined shapes drawn part by part; where parts overlap they look darker`
- `line caps, joins, dash details and uneven stroke scaling drawn in the SimpleDiagrams line style`
- `outlines the page paints beneath their fill drawn on top of it`
- `<element> left out`
- `visible content inside a hidden <element> left out`
- `<path> with unreadable data left out`
- `hole in a filled shape, kept as an outline only`
- `holes in a path with many contours may be filled in`
- `overlapping contours may fill areas that were clear`
- `rounded corners of a skewed rectangle drawn square`
- `line endings painted another colour take the line's colour`
- `line endings with paint this export cannot read take the line's colour`
- `line endings with different opacity take the line's opacity`
- `line ending other than an arrow, a circle or a diamond drawn as an arrow`
- `arrowhead not pointing away from its line drawn pointing away`
- `markers between a line's ends left out`
- `markers on a closed shape or a line with no stroke left out`
- `vertical text drawn horizontally`
- `crossed-out and overlined text drawn plain`
- `letters turned one by one drawn upright`
- `letters placed one by one drawn as one run of text`
- `runs of spaces in text joined into one`
- `words after hidden words in a line moved into their place`
- `words moved up or down in a line start a new line`
- `a wide sideways gap inside a line became one space`
- `styled words inside a line take the line's style`
- `outlined text drawn filled with its outline colour`
- `outlines around filled text left out`
- `see-through words inside a line drawn solid`
- `a line placed inside a span joins that span's line`
- `sideways gaps inside nested spans left out`
- `text skewed, stretched or mirrored drawn plainly`
- `text sizes beyond 1 to 720 points drawn at the nearest`
- `<foreignObject> holding more than text left out`
- `line breaks in HTML text joined into one line`
- `HTML box background, border or shadow left out; its text is kept`
- `HTML padding not read; the text sits at its box's edge`
- `rich HTML text kept as plain text`
- `HTML layout such as flex or grid centring not read; the text sits at the top`
- `icon SimpleDiagrams cannot store safely left out`
- `<use> of nothing left out`
- `letter case set by CSS left unchanged in stored icons`
- `markers in stored icons may be left out by the desktop renderer`
- `see-through or unknown icon colour stored as solid`
- `icon cropped to its box drawn whole`
- `skewed or empty picture left out`

## What this never does

- Modifies the source HTML.
- Replaces or deletes an existing file.
- Writes a timestamp, user name or tool version into the document.
