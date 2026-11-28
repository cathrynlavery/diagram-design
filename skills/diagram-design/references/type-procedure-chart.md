# Procedure chart

**Best for:** an administrative procedure where the paperwork matters as much as the people: who handles a form, what happens to it at each step, where it waits, who checks it, and where each copy ends up. Typical uses are a claim, request or approval routed between offices, a records workflow, or a before/after methods study. The grammar follows the procedure chart in AFMAN 38-102 (5 July 2024) §11.3 and its Figure 11.4 symbols.

**Not this type:**

- Decision logic with branches → **Flowchart** (`type-flowchart.md`). On a procedure chart a diamond is an **inspection**; on a flowchart it is a **decision**. Never put both meanings in one figure or one legend.
- Who owns which step, without what happens to the paperwork → **Swimlane** (`type-swimlane.md`).
- Payload handoffs between system actors → **Process** (`type-process.md`) or **Sequence** (`type-sequence.md`).
- What the customer sees against what stays backstage → **Service blueprint** (`type-service-blueprint.md`).

Authoring-only: the procedure arrives as text. Write the step narrative first (who does the work, where, and what happens to each document), as §11.3.4 asks, then chart it.

## Layout conventions

- **Rows are steps, top to bottom.** Charting starts top left and runs down the page (§11.3.4.2). Number the rows in a mono gutter. Every activity in one step shares that row's centre line.
- **One personnel column, on the left.** Exactly one personnel column per chart (§11.3.4.3). It holds what people do, in the present tense ("Checks receipt against claim"). Each personnel symbol records the role doing the work (`data-proc-role`), which is printed under its comment.
- **One element column per organizational element.** Each office or team gets a column. A document's symbols sit in the column of whoever holds it, in the past tense ("Claim verified").
- **One line per artifact.** Each document keeps one line offset in every column it visits, so the reader can follow it across. Use stable IDs assigned to activities and handoffs, not their position in the chart. Plain vertical flow lines join consecutive symbols in one column. Flow lines have no arrowheads; the row order gives the direction.
- **Handoffs are labelled.** When a document changes column it does so at a **move** symbol. An arrowed, orthogonal handoff then runs to the next column, labelled `<ID> <from column> → <to column>` 8px above the stroke. A column change without a handoff, or a handoff without a corresponding personnel move on the sending row, is a defect. On a row with paperwork, the printed personnel role must match its declared role and at least one holding column.
- **Time and distance are optional.** Processing time goes after a document symbol (§11.3.4.5); distance goes with a move. The header prints the procedure ID, the charting date and the analyst. When any step time or a total is declared, print a separate `charted time <duration>` field whose duration is the sum of the declared step times, including `0 min` for an explicit zero. Separate it from adjacent header fields with `·`.
- **Artifact key below the rows.** Each document gets one line: ID, title, number of copies, source and final disposition (§11.3.3.1, §11.3.3.5).
- **1 coral focal:** the step the figure exists to show, usually the longest delay. At most two accent elements: the symbol and its time label.

### Symbols (Figure 11.4)

Shape carries meaning; colour never does. Symbols sit in a 20×20 box on the paperwork track and a 24×24 box on the personnel track.

| Symbol | Shape | Track | Use |
|---|---|---|---|
| `origination` | Square | paperwork | A new document is created |
| `operation` | Circle | both | Something is done to the document, or a person does a step |
| `move` | Down block arrow | both | The document changes location or person; a person carries it |
| `delay` | D shape | paperwork | The document is idle |
| `file` | Inverted triangle | paperwork | The document goes into a formally organized file |
| `inspection` | Diamond | both | A mental verification is performed |
| `information-take-off` | `>` chevron on the line | paperwork | Data is moved from this document to another (`data-proc-target-artifact`) |
| `destroy` | X across the line | paperwork | The document is destroyed |
| `gap` | Hourglass | paperwork | Activity not pertinent to the study is omitted |
| `cross-over` | Hop on the line | paperwork | A document line passes another without meeting it |
| `item-change` | Two bars across the line | paperwork | The document has taken on a different meaning |

The personnel track uses **operation, inspection and move only**. Figure 11.4 defines no personnel delay, file or origination.

```svg
<!-- A paperwork inspection: block IDs from the traceable block pattern -->
<g data-proc-symbol="inspection" data-proc-track="paperwork"
   data-block-id="EXP-001-07" data-block-parent="EXP-001" data-block-name="Claim verified"
   data-proc-step="4" data-proc-at="564 334" data-proc-column="approver"
   data-proc-artifact="EXP-001-A1" data-proc-elapsed-min="10">
  <polygon data-role="mark" points="564,324 574,334 564,344 554,334"
           fill="#ffffff" stroke="#4f5d75" stroke-width="1.2"/>
  <text data-proc-label="comment" x="584" y="335" …>Claim verified</text>
  <text x="584" y="347" …><tspan data-proc-label="meta">EXP-001-07 · 10 min</tspan></text>
</g>

<!-- A handoff: from a move symbol to the next column, with its own ID -->
<path data-proc-connector="handoff" data-proc-connector-id="EXP-H1"
      data-from="EXP-001-04" data-to="EXP-001-05" data-proc-artifact="EXP-001-A1"
      d="M 324,208 V 224 Q 324,232 332,232 H 556 Q 564,232 564,240 V 256"
      fill="none" stroke="#4f5d75" stroke-width="1.2" marker-end="url(#arrow)"/>
```

## Machine-readable contract

The file has exactly one `<svg data-diagram="procedure-chart">`. The procedure is declared, not inferred, and `scripts/verify-procedure-chart.py` reads it back against the drawing.

- **Columns.** Each column is a `<rect>` carrying `data-proc-column` (`personnel` or `element`), `data-proc-column-id` and `data-proc-column-label`. There is exactly one personnel column, and it is the leftmost.
- **Registry.** The procedure root (`data-proc-kind="procedure"`), every artifact (`data-proc-kind="artifact"`) and every activity carry `data-block-id`, `data-block-name` and, below the root, `data-block-parent`. These are the [Traceable block decomposition](semantic-patterns.md) attributes, so `scripts/verify-block-registry.py` checks uniqueness, parents and cycles. The [Procedure chart registry export](export-registry.md) preserves the authored procedure fields and writes the typed connectors separately. ID prefixes are the author's choice. Keep existing IDs attached to their meaning when inserting steps. Unlike structural Tree blocks, procedure activity names are action phrases (present tense for personnel, past tense for paperwork).
- **Activities.** Each activity declares `data-proc-symbol`, `data-proc-track`, `data-proc-step` and `data-proc-at="x y"` (the symbol centre). A personnel activity also declares `data-proc-role`, an element column ID. A paperwork activity also declares `data-proc-column` and `data-proc-artifact`. Optional: `data-proc-elapsed-min` (paperwork only), `data-proc-distance-m` (move only), and `data-proc-target-artifact` (required on an information take-off). Each activity holds one `data-role="mark"` that draws its symbol, a `data-proc-label="comment"` equal to its `data-block-name`, and a `data-proc-label="meta"` that prints the ID plus any time and distance.
- **Artifacts.** Each artifact declares `data-proc-copies`, `data-proc-source` and `data-proc-disposition` (`file`, `destroy` or `move`). The source is an element column ID and must match the origination column when shown. If origination is shown, it is the first activity and is not repeated. Destroy ends the artifact line. The disposition must equal the symbol on its line's last activity. Different artifacts cannot share overlapping symbol lanes within one column.
- **Connectors.** Lines are a separate registry, not blocks. A `<line data-proc-connector="flow">` joins two consecutive symbols of one line in one column and carries its own `data-proc-connector-id`. If a paperwork flow specifies `data-proc-artifact`, it must match its endpoints; omit it on a personnel flow. A `<path data-proc-connector="handoff">` carries its own `data-proc-connector-id`, plus `data-from`, `data-to` and `data-proc-artifact`. Its label sits in `<g data-proc-label-for="<connector id>">`. An `information-take-off` connector links the take-off activity to an activity of the named receiving artifact on the same or next row, and the source activity prints the target ID, whose title is in the artifact key. Handoff and take-off arrows use a local `marker-end` reference with a nonempty, painted tip, such as a filled triangle or a stroked chevron.
- **Legend.** Each entry is `<g data-proc-legend="<symbol>" data-proc-at="x y">` with its own mark and the Figure 11.4 name. Every symbol used on the chart appears there. No entry may name a decision.
- **Illustrative trace (optional).** `<g data-role="trace" data-proc-illustrative="true">` holds events with `data-proc-trace-id` and `data-proc-trace-of="<activity ID>"`, printed in step order under a visible "illustrative" caption. A trace is one imagined run, kept apart from the procedure's definition. It never carries `data-block-*`, and it is not live employee or document telemetry.

The verifier fails a mark that does not draw its declared symbol (a diamond that is not an inspection), a personnel symbol Figure 11.4 does not define, duplicate or unresolved IDs, an activity outside its column or off its row, a flow line or handoff that does not join its two symbols, a column change with no labelled handoff from a move symbol, a disposition that contradicts the last symbol, a printed ID, time or header total that disagrees with the declaration, a legend that is incomplete or names a decision, a trace that carries block IDs, points at nothing or runs backwards, and `data-proc-*` vocabulary in a file that is not a procedure chart. Symbols are placed with presentation attributes; a checked mark, comment, or connector must have visible paint and no transform. Malformed or unsupported path syntax returns a finding rather than crashing. Marker paint and geometry checks are static; they are not a substitute for inspecting the rendered chart.

The shipped examples are generated by `scripts/build-procedure-chart-examples.py` from one declared procedure. Edit the model there and rebuild; `--check` fails a hand-edited example.

## Budget

≤12 steps, 1 personnel column plus ≤4 element columns, ≤3 artifacts, ≤24 activities, ≤6 handoffs, 2 accent elements. This replaces SKILL.md §7's 9-node and 12-arrow rows for this type only (see [layout-budget.md](layout-budget.md#complexity-budget-per-diagram)). A longer procedure splits by phase, with the last artifact disposition of one chart naming the first step of the next.

## Anti-patterns

- A diamond used for a decision, or a legend that lists "Decision" beside "Inspection". Branching logic goes in a companion flowchart.
- Personnel and paperwork symbols in the same column. The tracks are kept apart on purpose.
- A second personnel column for a second person. Record the role on each personnel symbol instead.
- A document that jumps columns without a move symbol and a labelled handoff.
- A delay drawn as a long line instead of a delay symbol. Idle time is the finding.
- Colour as the only difference between symbols. The shapes must read in greyscale.
- Presenting the illustrative trace as measured data. Real timings belong in the declared `data-proc-elapsed-min` values, with their source named in the prose.

## Examples

- `assets/example-procedure-chart.html`: a fictional expense claim, minimal light
- `assets/example-procedure-chart-dark.html`: identical IDs, steps and coordinates, dark
- `assets/example-procedure-chart-full.html`: full editorial, with the complete Figure 11.4 key and an illustrative trace
