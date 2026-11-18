# Packet structure

**Best for:** answering which named fields occupy which bit positions in a fixed-width header. A shared bit-boundary ruler, contiguous field rectangles and absolute row offsets make the layout readable without guessing from label length. Use supplied offsets and widths; if the schema is illustrative, say so visibly.

**Not this type:** Layers shows abstraction levels, Unit Grid counts equal units, and Database schema describes typed columns and relationships. None maps a field's start and width onto one bit scale. Use a table when only the field names and descriptions matter.

## Layout conventions

- Place one horizontal bit-boundary ruler above aligned rows of equal width. Label its first boundary `0` and its last boundary with the row width. The last boundary is exclusive: a 32-bit row contains bits 0–31, not 0–32.
- Use 8, 16, 32 or 64 bits per row. The same horizontal scale applies to every row. Print each row's absolute starting bit offset to its left.
- Label only enough ruler boundaries to keep at least 8px of clear space between neighboring numbers. Thin the labels on a dense ruler; never change the bit scale to make them fit.
- Draw each field as a rectangle. For row offset `r`, field offset `o`, field width `n`, left edge `x0` and pixels per bit `s`, use `x=x0+(o-r)*s` and `width=n*s`. Adjacent field rectangles share an edge; do not add a visual gutter that changes their encoded widths.
- Print a short field name and its absolute inclusive range and width, for example `8–23 / 16b`. A 16-bit field must draw four times as wide as a 4-bit field.
- Cover each row completely in source order, with no overlap or unexplained gaps. Give reserved space an explicit field name and width. This bounded overview refuses fields crossing row boundaries: split a long field into explicitly named parts or use a detail view, rather than silently wrapping it.
- Keep one focal field at most. Highlighting never substitutes for offsets or sizes. Use paper-filled rectangles with readable house-ink borders and labels; the dark variant preserves the same data and swaps house tokens.
- Logical bit position increases left to right. This does not by itself specify byte order, bit significance, on-wire transmission order, or a field's interpreted value. State those separately when supplied.

## Machine-readable contract

The shipped static SVG declares `data-diagram-type="packet-structure"` and uses:

- one `g[data-packet-axis]` whose value is the bits per row and whose `data-packet-source` names the supplied specification or the illustrative schema;
- a horizontal `line[data-packet-baseline="true"]` and ordered `g[data-bit-boundary]` ticks, each containing a vertical line and its printed boundary number;
- ordered `g[data-packet-row]` groups identified by absolute row offsets, each with a visible `text[data-packet-row-label="true"]`;
- field groups with a unique `data-packet-field`, `data-field-name`, `data-bit-offset` and positive integer `data-bit-width`;
- in each field, one rectangle followed by `text[data-packet-label="name"]` and `text[data-packet-label="range"]`;
- a visible `text[data-packet-source-label="true"]` naming the source and the complete bit length.

`scripts/verify-packet-structure.py --all` checks all three examples and their data parity. The checker reads actual HTML elements, not SVG-looking text inside comments or HTML titles. It checks the visible ruler, field geometry, printed labels, complete row coverage, source caption and bounded static page/SVG contract. The browser render gate checks painted clipping; inspect the resulting preview as well. The static label-fit bound is conservative, not a font-shaping engine.

This verifier checks consistency between authored data and its drawing. It does not parse a protocol specification or establish that the authored offsets describe a real protocol. It intentionally refuses transforms, arbitrary SVG elements, animation, SVG inline styles and page styles outside the shared static template.

## Complexity budget

- At most 6 fixed-width rows and 9 field cells in one overview.
- A 1200-wide viewBox with readable labels, at least 12px, and horizontal scrolling below that readable width.
- Short names inside narrow fields. Use an abbreviation with a visible explanation if a real name cannot fit; never widen a field or shrink its label to hide the mismatch.
- No variable-length payload, optional-field tree or inferred padding in this overview. State any excluded region explicitly.

## Worked illustrative schema

The examples adapt the bit-offset/width grammar from AxoDen Fieldbook into Diagram Design's house style. This is an illustrative 64-bit frame, not a published network protocol:

| Field | Absolute offset | Width | Printed range |
|---|---:|---:|---|
| Version | 0 | 4 | 0–3 |
| Flags | 4 | 4 | 4–7 |
| Length | 8 | 16 | 8–23 |
| Kind | 24 | 8 | 24–31 |
| Sequence | 32 | 32 | 32–63 |

The first four fields fill the first 32-bit row. Sequence fills the second. The Length cell is four times the width of Version; Sequence is twice the width of Length.

## Anti-patterns

- Equal-width boxes for unequal bit lengths, or widths chosen to accommodate labels.
- A ruler ending at `31` while its full span encodes 32 bit boundaries.
- Resetting printed absolute offsets to zero on every row without declaring a different numbering convention.
- Missing reserved bits, overlapping ranges, or a field visually placed on another row.
- Claiming protocol conformance because the SVG passed a structural checker.

## Examples

- `assets/example-packet-structure.html` — minimal light, illustrative 64-bit frame.
- `assets/example-packet-structure-dark.html` — identical bit geometry and field data on dark paper.
- `assets/example-packet-structure-full.html` — full editorial page with interpretation and scope notes.
