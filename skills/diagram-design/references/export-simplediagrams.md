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
- **Content SimpleDiagrams cannot hold** (images of any kind, which are never fetched or stored; clipping and masks, whose shapes are drawn unclipped; filters such as blur and shadow; blend modes; gradients; text on a path; holes in filled shapes; styled words inside a line, which take the line's style; a wide sideways gap inside a line, which becomes one space; words after hidden words in a line, which move into their place; rich HTML text, kept as plain text; line breaks in HTML text, joined into one line; HTML layout such as flex or grid centring, which is not read, so the text sits at the top; HTML padding, also not read; visible text inside a hidden HTML block, which is left out; an HTML box's background, border or shadow, which is left out while its text is kept; words moved up or down inside a line, which start a line of their own; a line placed inside another span, which joins that span's line; sizes, places and corners set in CSS rather than as attributes, which are not read; a see-through or unknown icon colour, stored solid; an icon cropped to its box, which is drawn whole; CSS transforms it cannot read; stylesheet rules it cannot read; line endings other than an arrow, a circle or a diamond; arrowheads that do not point away from their line, drawn pointing away; line endings painted another colour, which take the line's colour; markers between a line's ends, on closed shapes or on lines with no stroke; rounded corners of a skewed rectangle, drawn square; see-through words inside a line, and see-through groups whose shapes overlap; outlined text, drawn filled; vertical text, drawn horizontally; crossed-out and overlined text, drawn plain; letters turned one by one, drawn upright; letters placed one by one, sideways gaps inside nested spans and runs of preserved spaces; text that is skewed, stretched or mirrored, or sized beyond 1 to 720 points): the helper prints one `note:` line per kind. Pass the notes on to the user.
- **Styling it does not read:** only selectors built from tags, `*`, classes, IDs and descendants apply, and only hex, `rgb()`, `rgba()`, `currentColor` and the basic colour names are understood. `dominant-baseline` and `letter-spacing` do not move or space a label.

## What this never does

- Modifies the source HTML.
- Replaces or deletes an existing file.
- Writes a timestamp, user name or tool version into the document.
