# Export to SimpleDiagrams (`--simplediagrams`)

Write a diagram as an editable `.simplediagram` document for the SimpleDiagrams editor on macOS. **Manual only — never run unprompted, and only on `--simplediagrams`.**

## Trigger

Load this file when the user invokes `/diagram-design:export-diagram <html-file> --simplediagrams`, or asks to keep editing a diagram in SimpleDiagrams.

## Scope

The output is a new document in [document format 19](https://github.com/mcquilleninteractive/simplediagrams-file-formats/tree/main/document/19), drawn in SimpleDiagrams' hand-drawn style. Like the other exports it holds the `<svg>` diagram only. Boxes become shapes from SimpleDiagrams' built-in Basic library and keep their text; arrows become connectors attached to the boxes they touch, carrying their labels, and a square route keeps only its corners (rounded corners and hops over crossing lines are drawn plain); lanes become a Swimlanes shape; anything drawn on a box is grouped with it; other lines and text keep their place. An outline is replaced by a Basic shape only when it is labelled or an arrow ends on it, so the faces of an exploded or axonometric drawing keep their exact geometry.

## Procedure

From this skill's directory run:

```
python3 scripts/export_simplediagrams.py <html-file> [<out.simplediagram>]
```

It reads the diagram through `scripts/export_svg.py`, needs only the Python standard library, and makes no network request. The default output is `<basename>.simplediagram` next to the source. Re-exporting an unchanged diagram produces identical files.

## Edge cases

- **The output already exists:** refuse and ask for another name. An existing document may hold the user's edits, so it is never replaced.
- **Source is `assets/index.html`:** refuse, as for SVG/PNG — ask which diagram file.
- **Icons:** icons placed with `<use>` or a nested `<svg>` are stored in the document as vector artwork. An icon holding anything active, filtered or linked is left out with a note.
- **Content SimpleDiagrams cannot hold** (images of any kind, which are never fetched or stored; clipping and masks, whose shapes are drawn unclipped; gradients; text on a path; holes in filled shapes; styled words inside a line, which take the line's style): the helper prints one `note:` line per kind. Pass the notes on to the user.

## What this never does

- Modifies the source HTML.
- Replaces or deletes an existing file.
- Writes a timestamp, user name or tool version into the document.
