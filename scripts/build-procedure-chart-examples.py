#!/usr/bin/env python3
"""Build the three Procedure chart examples from one declared procedure.

The minimal light, minimal dark and full editorial variants share one model:
the same steps, symbols, IDs, coordinates and connectors. Only the palette and
the editorial frame differ, and the full variant adds the illustrative event
trace. Generating the files keeps the three in lockstep, so a symbol moved in
one variant cannot silently drift from the others.

The model is a fictional expense claim (two paper artifacts, three
organizational elements). It is illustrative only: no person, organization or
real record is charted.

Usage:
    python3 scripts/build-procedure-chart-examples.py          # write the files
    python3 scripts/build-procedure-chart-examples.py --check  # fail if stale
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"

# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

WIDTH = 1120
HEADER_Y = 40
COLUMN_TOP = 64
COLUMN_LABEL_Y = 84
ROW_TOP = 96
ROW_H = 68
PERSONNEL_R = 11  # personnel symbols sit in a 24x24 box
PAPER_HALF = 10  # paperwork symbols sit in a 20x20 box


def cy(step: int) -> int:
    return ROW_TOP + ROW_H * (step - 1) + ROW_H // 2


@dataclass(frozen=True)
class Column:
    id: str
    label: str
    kind: str  # personnel | element
    x0: int
    x1: int


COLUMNS = (
    Column("personnel", "Personnel", "personnel", 64, 296),
    Column("requester", "Requester", "element", 296, 536),
    Column("approver", "Approver", "element", 536, 776),
    Column("finance", "Finance office", "element", 776, 1096),
)
COLUMN = {c.id: c for c in COLUMNS}
PERSONNEL_X = 92
# Each artifact keeps one line offset inside every element column it visits.
ARTIFACT_OFFSET = {"EXP-001-A1": 28, "EXP-001-A2": 168}


@dataclass(frozen=True)
class Artifact:
    id: str
    name: str
    copies: int
    source: str
    disposition: str  # file | destroy | move


ARTIFACTS = (
    Artifact("EXP-001-A1", "Expense claim form", 1, "requester", "file"),
    Artifact("EXP-001-A2", "Payment voucher", 1, "finance office", "move"),
)
DISPOSITION_WORD = {"file": "filed", "destroy": "destroyed", "move": "moved out"}


@dataclass(frozen=True)
class Activity:
    step: int
    track: str  # personnel | paperwork
    symbol: str
    name: str
    column: str  # role column for personnel, holding column for paperwork
    artifact: str | None = None
    elapsed: int | None = None  # minutes
    distance: int | None = None  # metres, move symbols only
    target: str | None = None  # information take-off target artifact
    accent: bool = False


# Personnel symbols speak in the present tense, paperwork symbols in the past
# tense (AFMAN 38-102 §11.3.4.4).
STEPS = (
    Activity(1, "personnel", "operation", "Completes claim", "requester"),
    Activity(1, "paperwork", "origination", "Claim created", "requester", "EXP-001-A1", elapsed=15),
    Activity(2, "personnel", "move", "Takes claim to approver", "requester"),
    Activity(2, "paperwork", "move", "Claim moved", "requester", "EXP-001-A1", distance=40),
    Activity(3, "paperwork", "delay", "Claim waited in tray", "approver", "EXP-001-A1", elapsed=1440, accent=True),
    Activity(4, "personnel", "inspection", "Checks receipt against claim", "approver"),
    Activity(4, "paperwork", "inspection", "Claim verified", "approver", "EXP-001-A1", elapsed=10),
    Activity(5, "personnel", "move", "Sends claim to finance", "approver"),
    Activity(5, "paperwork", "move", "Claim moved", "approver", "EXP-001-A1"),
    Activity(6, "personnel", "operation", "Keys amount into voucher", "finance"),
    Activity(6, "paperwork", "information-take-off", "Amount taken off", "finance", "EXP-001-A1",
             elapsed=5, target="EXP-001-A2"),
    Activity(6, "paperwork", "origination", "Voucher created", "finance", "EXP-001-A2"),
    Activity(7, "personnel", "operation", "Files claim", "finance"),
    Activity(7, "paperwork", "file", "Claim filed", "finance", "EXP-001-A1", elapsed=2),
    Activity(8, "personnel", "move", "Releases voucher to bank", "finance"),
    Activity(8, "paperwork", "move", "Voucher released to bank", "finance", "EXP-001-A2"),
)
ROOT_ID = "EXP-001"
ROOT_NAME = "Expense claim reimbursement"
CHART_DATE = "2026-11-27"
ANALYST = "J. Doe"
STEP_COUNT = max(a.step for a in STEPS)
IDS = {a: f"{ROOT_ID}-{i:02d}" for i, a in enumerate(STEPS, 1)}

TRACE = (
    ("TR-01", 4, "Mon 09:05", "claim leaves requester"),
    ("TR-02", 5, "Mon 09:20", "claim lands in tray"),
    ("TR-03", 7, "Tue 09:32", "claim verified"),
    ("TR-04", 14, "Tue 10:02", "claim filed"),
)


def fmt_minutes(total: int) -> str:
    days, rest = divmod(total, 1440)
    hours, minutes = divmod(rest, 60)
    parts = [f"{days} d" if days else "", f"{hours} h" if hours else "", f"{minutes} min" if minutes else ""]
    return " ".join(p for p in parts if p) or "0 min"


def symbol_x(a: Activity) -> int:
    if a.track == "personnel":
        return PERSONNEL_X
    assert a.artifact is not None
    return COLUMN[a.column].x0 + ARTIFACT_OFFSET[a.artifact]


def half(a: Activity) -> int:
    return PERSONNEL_R + 1 if a.track == "personnel" else PAPER_HALF


def meta_text(a: Activity) -> str:
    parts = [IDS[a]]
    if a.elapsed is not None:
        parts.append(fmt_minutes(a.elapsed))
    if a.distance is not None:
        parts.append(f"{a.distance} m")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

LIGHT = {
    "paper": "#f5f5f5", "ink": "#2d3142", "muted": "#4f5d75", "soft": "#5a6580",
    "accent": "#bf4520", "fill": "#ffffff", "accent_tint": "rgba(191,69,32,0.08)",
    "band": "rgba(45,49,66,0.03)", "rule": "rgba(45,49,66,0.12)", "dots": "rgba(45,49,66,0.10)",
}
DARK = {
    "paper": "#2d3142", "ink": "#f5f5f5", "muted": "#bfc0c0", "soft": "#949eb2",
    "accent": "#f08a59", "fill": "#2d3142", "accent_tint": "rgba(240,138,89,0.08)",
    "band": "rgba(245,245,245,0.03)", "rule": "rgba(245,245,245,0.12)", "dots": "rgba(245,245,245,0.10)",
}

SANS = "'Geist', sans-serif"
MONO = "'Geist Mono', monospace"


# ---------------------------------------------------------------------------
# Symbol marks (AFMAN 38-102 Figure 11.4)
# ---------------------------------------------------------------------------


def mark(symbol: str, x: int, y: int, track: str, stroke: str, fill: str) -> str:
    """One `data-role="mark"` element drawing the symbol centred on x,y."""
    common = f'fill="{fill}" stroke="{stroke}" stroke-width="1.2"'
    open_common = f'fill="none" stroke="{stroke}" stroke-width="1.4"'
    if symbol == "operation":
        r = PERSONNEL_R if track == "personnel" else 9
        return f'<circle data-role="mark" cx="{x}" cy="{y}" r="{r}" {common}/>'
    if symbol == "origination":
        return f'<rect data-role="mark" x="{x - 8}" y="{y - 8}" width="16" height="16" {common}/>'
    if symbol == "inspection":
        s = PERSONNEL_R if track == "personnel" else 10
        return (f'<polygon data-role="mark" points="{x},{y - s} {x + s},{y} {x},{y + s} {x - s},{y}" '
                f'{common}/>')
    if symbol == "move":
        s = PERSONNEL_R if track == "personnel" else 10
        w = s // 2
        return (f'<polygon data-role="mark" points="{x - w},{y - s} {x + w},{y - s} {x + w},{y - 1} '
                f'{x + s},{y - 1} {x},{y + s} {x - s},{y - 1} {x - w},{y - 1}" {common}/>')
    if symbol == "delay":
        return (f'<path data-role="mark" d="M {x - 8},{y - 9} H {x} A 9,9 0 0,1 {x},{y + 9} H {x - 8} Z" '
                f'{common}/>')
    if symbol == "file":
        return f'<polygon data-role="mark" points="{x - 10},{y - 9} {x + 10},{y - 9} {x},{y + 9}" {common}/>'
    if symbol == "information-take-off":
        return f'<path data-role="mark" d="M {x - 6},{y - 8} L {x + 6},{y} L {x - 6},{y + 8}" {open_common}/>'
    if symbol == "destroy":
        return (f'<path data-role="mark" d="M {x - 8},{y - 8} L {x + 8},{y + 8} M {x + 8},{y - 8} '
                f'L {x - 8},{y + 8}" {open_common}/>')
    if symbol == "gap":
        return (f'<polygon data-role="mark" points="{x - 8},{y - 9} {x + 8},{y - 9} {x - 8},{y + 9} '
                f'{x + 8},{y + 9}" {common}/>')
    if symbol == "cross-over":
        return (f'<path data-role="mark" d="M {x},{y - 10} V {y - 6} A 6,6 0 0,1 {x},{y + 6} V {y + 10}" '
                f'{open_common}/>')
    if symbol == "item-change":
        return (f'<path data-role="mark" d="M {x - 9},{y - 3} H {x + 9} M {x - 9},{y + 3} H {x + 9}" '
                f'{open_common}/>')
    raise ValueError(symbol)


LEGEND_NAMES = {
    "origination": "Origination", "operation": "Operation", "move": "Move", "delay": "Delay",
    "file": "File", "inspection": "Inspection", "information-take-off": "Information take-off",
    "destroy": "Destroy", "gap": "Gap", "cross-over": "Cross over", "item-change": "Item change",
}
ALL_SYMBOLS = tuple(LEGEND_NAMES)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


def handoffs() -> list[tuple[str, Activity, Activity]]:
    """A move on an artifact line whose next symbol sits in another column."""
    found = []
    for artifact in ARTIFACTS:
        line = [a for a in STEPS if a.artifact == artifact.id]
        for here, nxt in zip(line, line[1:]):
            if here.column != nxt.column:
                found.append((f"EXP-H{len(found) + 1}", here, nxt))
    return found


def flows() -> list[tuple[Activity, Activity]]:
    pairs = []
    personnel = [a for a in STEPS if a.track == "personnel"]
    pairs.extend(zip(personnel, personnel[1:]))
    for artifact in ARTIFACTS:
        line = [a for a in STEPS if a.artifact == artifact.id]
        pairs.extend((a, b) for a, b in zip(line, line[1:]) if a.column == b.column)
    return pairs


def svg(p: dict[str, str], slug: str, with_trace: bool, full_key: bool) -> str:
    rows_bottom = ROW_TOP + ROW_H * STEP_COUNT
    key_top = rows_bottom + 16
    legend_top = key_top + 48
    trace_top = legend_top + (88 if full_key else 48)
    height = trace_top + (96 if with_trace else 0)
    total = sum(a.elapsed or 0 for a in STEPS)
    out: list[str] = []
    w = out.append
    w(f'<svg viewBox="0 0 {WIDTH} {height}" xmlns="http://www.w3.org/2000/svg" role="img"')
    w(f'     aria-labelledby="{slug}-title {slug}-desc" data-diagram="procedure-chart">')
    w(f'  <title id="{slug}-title">An expense claim waits a day for its approver</title>')
    w(f'  <desc id="{slug}-desc">A procedure chart of a fictional expense claim: the personnel column shows what '
      f'each role does and three organizational columns show what happens to the claim form and payment voucher, '
      f'including a one-day delay in the approver tray.</desc>')
    w('  <defs>')
    w('    <pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">')
    w(f'      <circle cx="1" cy="1" r="0.9" fill="{p["dots"]}"/>')
    w('    </pattern>')
    w(f'    <marker id="arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">'
      f'<polygon points="0 0, 8 3, 0 6" fill="{p["muted"]}"/></marker>')
    w('  </defs>')
    w(f'  <rect width="100%" height="100%" fill="{p["paper"]}"/>')
    w('  <rect width="100%" height="100%" fill="url(#dots)" opacity="0.55"/>')

    # Columns first: zones are painted before connectors, labels and symbols.
    w('  <g data-role="columns">')
    for i, c in enumerate(COLUMNS):
        fill = p["band"] if i % 2 == 0 else "none"
        w(f'    <rect data-proc-column="{c.kind}" data-proc-column-id="{c.id}" data-proc-column-label="{c.label}" '
          f'x="{c.x0}" y="{COLUMN_TOP}" width="{c.x1 - c.x0}" height="{rows_bottom - COLUMN_TOP}" fill="{fill}"/>')
        w(f'    <text x="{c.x0 + 12}" y="{COLUMN_LABEL_Y}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
          f'letter-spacing="0.18em">{c.label.upper()}</text>')
    for c in COLUMNS[1:]:
        w(f'    <line x1="{c.x0}" y1="{COLUMN_TOP}" x2="{c.x0}" y2="{rows_bottom}" stroke="{p["rule"]}" '
          f'stroke-width="0.8"/>')
    w(f'    <line x1="24" y1="{ROW_TOP}" x2="{COLUMNS[-1].x1}" y2="{ROW_TOP}" stroke="{p["rule"]}" '
      f'stroke-width="0.8"/>')
    for step in range(1, STEP_COUNT + 1):
        w(f'    <text x="44" y="{cy(step) + 3}" fill="{p["soft"]}" font-size="9" font-family="{MONO}" '
          f'text-anchor="middle">{step:02d}</text>')
    w('  </g>')

    # Procedure header (AFMAN 38-102 §11.3.4.1: title, date, analyst).
    w(f'  <g data-proc-kind="procedure" data-block-id="{ROOT_ID}" data-block-name="{ROOT_NAME}" '
      f'data-proc-date="{CHART_DATE}" data-proc-analyst="{ANALYST}" data-proc-elapsed-total-min="{total}">')
    w(f'    <text x="24" y="{HEADER_Y}" fill="{p["ink"]}" font-size="11" font-weight="600" font-family="{SANS}">'
      f'{ROOT_NAME}</text>')
    w(f'    <text data-proc-label="header" x="{WIDTH - 24}" y="{HEADER_Y}" fill="{p["muted"]}" font-size="8" '
      f'font-family="{MONO}" text-anchor="end" letter-spacing="0.06em">{ROOT_ID} · charted {CHART_DATE} · '
      f'analyst {ANALYST} · charted time {fmt_minutes(total)}</text>')
    w('  </g>')

    # Flow lines, plain, behind the symbols.
    w('  <g data-role="flow">')
    for a, b in flows():
        x = symbol_x(a)
        w(f'    <line data-proc-connector="flow" data-from="{IDS[a]}" data-to="{IDS[b]}" x1="{x}" '
          f'y1="{cy(a.step) + half(a)}" x2="{x}" y2="{cy(b.step) - half(b)}" stroke="{p["muted"]}" '
          f'stroke-width="1.2"/>')
    w('  </g>')

    # Handoffs: a move symbol, then an arrowed elbow into the next column.
    w('  <g data-role="handoffs">')
    for cid, a, b in handoffs():
        x1, x2 = symbol_x(a), symbol_x(b)
        y_turn = cy(a.step) + ROW_H // 2
        y1, y2 = cy(a.step) + half(a), cy(b.step) - half(b)
        d = (f"M {x1},{y1} V {y_turn - 8} Q {x1},{y_turn} {x1 + 8},{y_turn} H {x2 - 8} "
             f"Q {x2},{y_turn} {x2},{y_turn + 8} V {y2}")
        w(f'    <path data-proc-connector="handoff" data-proc-connector-id="{cid}" data-from="{IDS[a]}" '
          f'data-to="{IDS[b]}" data-proc-artifact="{a.artifact}" d="{d}" fill="none" stroke="{p["muted"]}" '
          f'stroke-width="1.2" marker-end="url(#arrow)"/>')
    for cid, a, b in handoffs():
        x1, x2 = symbol_x(a), symbol_x(b)
        y_turn = cy(a.step) + ROW_H // 2
        text = f"{cid} {COLUMN[a.column].label} → {COLUMN[b.column].label}"
        width = 8 + 5 * len(text)
        end = x2 - 16
        # The label sits above its connector, 8px clear of the stroke, ending
        # before the elbow into the receiving column.
        w(f'    <g data-proc-label-for="{cid}">')
        w(f'      <rect x="{end - width + 4}" y="{y_turn - 18}" width="{width}" height="12" rx="2" '
          f'fill="{p["paper"]}"/>')
        w(f'      <text x="{end}" y="{y_turn - 9}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
          f'text-anchor="end">{text}</text>')
        w('    </g>')
    w('  </g>')

    # Activities: one symbol, a comment, and the ID with any charted time.
    w('  <g data-role="activities">')
    for a in STEPS:
        x, y = symbol_x(a), cy(a.step)
        stroke = p["accent"] if a.accent else (p["ink"] if a.track == "personnel" else p["muted"])
        fill = p["accent_tint"] if a.accent else p["fill"]
        attrs = [
            f'data-proc-symbol="{a.symbol}"', f'data-proc-track="{a.track}"',
            f'data-block-id="{IDS[a]}"', f'data-block-parent="{ROOT_ID}"', f'data-block-name="{a.name}"',
            f'data-proc-step="{a.step}"', f'data-proc-at="{x} {y}"',
        ]
        if a.track == "personnel":
            attrs.append(f'data-proc-role="{a.column}"')
        else:
            attrs += [f'data-proc-column="{a.column}"', f'data-proc-artifact="{a.artifact}"']
        if a.elapsed is not None:
            attrs.append(f'data-proc-elapsed-min="{a.elapsed}"')
        if a.distance is not None:
            attrs.append(f'data-proc-distance-m="{a.distance}"')
        if a.target is not None:
            attrs.append(f'data-proc-target-artifact="{a.target}"')
        w(f'    <g {" ".join(attrs)}>')
        w(f'      {mark(a.symbol, x, y, a.track, stroke, fill)}')
        tx = x + half(a) + 10
        w(f'      <text data-proc-label="comment" x="{tx}" y="{y + 1}" fill="{p["ink"]}" font-size="10" '
          f'font-family="{SANS}">{a.name}</text>')
        meta_fill = p["accent"] if a.accent else p["muted"]
        role = f"{COLUMN[a.column].label.lower()} · " if a.track == "personnel" else ""
        w(f'      <text x="{tx}" y="{y + 13}" fill="{meta_fill}" font-size="8" font-family="{MONO}">{role}'
          f'<tspan data-proc-label="meta">{meta_text(a)}</tspan></text>')
        w('    </g>')
    w('  </g>')

    # Artifacts (AFMAN 38-102 §11.3.3.1 and §11.3.3.5).
    w('  <g data-role="artifacts">')
    w(f'    <text x="24" y="{key_top + 4}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
      f'letter-spacing="0.18em">ARTIFACTS</text>')
    for i, art in enumerate(ARTIFACTS):
        y = key_top + 20 + 14 * i
        copies = "1 copy" if art.copies == 1 else f"{art.copies} copies"
        text = (f"{art.id} {art.name} · {copies} · source {art.source} · "
                f"{DISPOSITION_WORD[art.disposition]}")
        w(f'    <g data-proc-kind="artifact" data-block-id="{art.id}" data-block-parent="{ROOT_ID}" '
          f'data-block-name="{art.name}" data-proc-copies="{art.copies}" data-proc-source="{art.source}" '
          f'data-proc-disposition="{art.disposition}">')
        w(f'      <text data-proc-label="artifact" x="24" y="{y}" fill="{p["ink"]}" font-size="9" '
          f'font-family="{MONO}">{text}</text>')
        w('    </g>')
    w('  </g>')

    # Legend: procedure-chart meanings only. A diamond here is Inspection.
    used = [s for s in ALL_SYMBOLS if s in {a.symbol for a in STEPS}]
    shown = list(ALL_SYMBOLS) if full_key else used
    w('  <g data-role="legend">')
    w(f'    <line x1="24" y1="{legend_top}" x2="{WIDTH - 24}" y2="{legend_top}" stroke="{p["rule"]}" '
      f'stroke-width="0.8"/>')
    caption = "PROCEDURE CHART SYMBOLS · AFMAN 38-102 FIG. 11.4" if full_key else "LEGEND · AFMAN 38-102 FIG. 11.4"
    w(f'    <text x="24" y="{legend_top + 16}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
      f'letter-spacing="0.18em">{caption}</text>')
    per_row, pitch = (6, 176) if full_key else (7, 150)
    w(f'    <text x="{WIDTH - 24}" y="{legend_top + 16}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
      f'text-anchor="end">personnel track: operation, inspection, move · diamond = inspection, never a decision</text>')
    for i, s in enumerate(shown):
        col, row = i % per_row, i // per_row
        x = 36 + col * pitch
        y = legend_top + 36 + row * 28
        w(f'    <g data-proc-legend="{s}" data-proc-at="{x} {y}">')
        w(f'      {mark(s, x, y, "paperwork", p["muted"], p["fill"])}')
        w(f'      <text x="{x + 18}" y="{y + 3}" fill="{p["muted"]}" font-size="9" font-family="{SANS}">'
          f'{LEGEND_NAMES[s]}</text>')
        w('    </g>')
    w('  </g>')

    if with_trace:
        w(f'  <g data-role="trace" data-proc-illustrative="true">')
        w(f'    <line x1="24" y1="{trace_top}" x2="{WIDTH - 24}" y2="{trace_top}" stroke="{p["rule"]}" '
          f'stroke-width="0.8"/>')
        w(f'    <text x="24" y="{trace_top + 16}" fill="{p["muted"]}" font-size="8" font-family="{MONO}" '
          f'letter-spacing="0.18em">ILLUSTRATIVE TRACE · ONE IMAGINED RUN · NOT TELEMETRY</text>')
        ids = {i + 1: IDS[a] for i, a in enumerate(STEPS)}
        for i, (tid, index, at, note) in enumerate(TRACE):
            x = 24 + i * 268
            w(f'    <g data-proc-trace-id="{tid}" data-proc-trace-of="{ids[index]}">')
            w(f'      <text x="{x}" y="{trace_top + 40}" fill="{p["ink"]}" font-size="9" font-family="{MONO}">'
              f'{tid} {at}</text>')
            w(f'      <text x="{x}" y="{trace_top + 54}" fill="{p["muted"]}" font-size="8" font-family="{MONO}">'
              f'{ids[index]} · {note}</text>')
            w('    </g>')
        w('  </g>')
    w('</svg>')
    return "\n".join("        " + line for line in out)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600'
         '&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">')
H1 = "An expense claim waits a day for its approver"
EYEBROW = "Procedure chart · AFMAN 38-102 §11.3"


def minimal(p: dict[str, str], slug: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{H1} · Procedure chart</title>
  {FONTS}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --color-paper:   {p["paper"]};
      --color-ink:     {p["ink"]};
      --color-muted:   {p["muted"]};
      --color-accent:  {p["accent"]};
      --font-sans:     'Geist', system-ui, sans-serif;
      --font-serif:    'Instrument Serif', serif;
      --font-mono:     'Geist Mono', ui-monospace, monospace;
    }}
    body {{
      font-family: var(--font-sans);
      background: var(--color-paper);
      color: var(--color-ink);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 3rem 2rem;
    }}
    .frame {{ max-width: 1200px; width: 100%; }}
    .diagram-container {{ width: 100%; overflow-x: auto; }}
    .eyebrow {{
      font-family: var(--font-mono);
      font-size: 0.66rem;
      font-weight: 500;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--color-muted);
      margin-bottom: 0.5rem;
    }}
    h1 {{
      font-family: var(--font-serif);
      font-size: clamp(1.5rem, 2.4vw + 0.75rem, 2rem);
      font-weight: 400;
      letter-spacing: -0.02em;
      line-height: 1.15;
      color: var(--color-ink);
      margin-bottom: 1.5rem;
    }}
    svg {{ width: 100%; min-width: 1000px; display: block; }}
    @media print {{
      .diagram-container {{ overflow-x: visible; }}
      svg {{ min-width: 0; }}
    }}
  </style>
</head>
<body>
  <div class="frame">
    <p class="eyebrow">{EYEBROW}</p>
    <h1>{H1}</h1>
    <div class="diagram-container">
{svg(p, slug, with_trace=False, full_key=False)}
    </div>
  </div>
</body>
</html>
"""


def full(p: dict[str, str], slug: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{H1} · Procedure chart</title>
  {FONTS}
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --color-paper: #f5f5f5; --color-paper-2: #ececec;
      --color-ink: #2d3142; --color-muted: #4f5d75; --color-soft: #5a6580;
      --color-rule: rgba(45,49,66,0.12);
      --color-accent: #bf4520; --color-accent-tint: rgba(191,69,32,0.08);
      --color-link: #2e5aa8;
      --font-sans: 'Geist', system-ui, sans-serif;
      --font-serif: 'Instrument Serif', serif;
      --font-mono: 'Geist Mono', ui-monospace, monospace;
    }}
    body {{ font-family: var(--font-sans); background: var(--color-paper); min-height: 100vh; padding: 3rem 2rem; color: var(--color-ink); }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    .header {{ margin-bottom: 2.5rem; }}
    .header-eyebrow {{ font-family: var(--font-mono); font-size: 0.66rem; font-weight: 500; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.75rem; }}
    h1 {{ font-family: var(--font-serif); font-size: clamp(1.75rem, 3vw + 1rem, 2.5rem); font-weight: 400; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 0.5rem; }}
    .subtitle {{ font-size: 1rem; line-height: 1.55; color: var(--color-muted); max-width: 58ch; }}
    .diagram-container {{ background: var(--color-paper-2); border-radius: 8px; border: 1px solid var(--color-rule); padding: 1.5rem; overflow-x: auto; }}
    svg {{ width: 100%; min-width: 1000px; display: block; }}
    .cards {{ display: grid; grid-template-columns: 1.1fr 1fr 0.9fr; gap: 1rem; margin-top: 1.5rem; }}
    @media (max-width: 820px) {{ .cards {{ grid-template-columns: 1fr; }} }}
    .card {{ background: #fff; border-radius: 6px; border: 1px solid var(--color-rule); padding: 1.25rem; }}
    .card .eyebrow {{ font-family: var(--font-mono); font-size: 0.5rem; letter-spacing: 0.18em; text-transform: uppercase; color: var(--color-muted); margin-bottom: 0.5rem; }}
    .card-header {{ display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.875rem; padding-bottom: 0.875rem; border-bottom: 1px solid rgba(45,49,66,0.08); }}
    .card-dot {{ width: 7px; height: 7px; border-radius: 50%; }}
    .card-dot.ink {{ background: var(--color-ink); }} .card-dot.muted {{ background: var(--color-muted); }} .card-dot.coral {{ background: var(--color-accent); }}
    .card h3 {{ font-size: 0.875rem; font-weight: 600; letter-spacing: -0.005em; }}
    .card p, .card ul {{ color: var(--color-muted); font-size: 0.8125rem; line-height: 1.55; list-style: none; }}
    .card li {{ margin-bottom: 0.3rem; padding-left: 0.875rem; position: relative; }}
    .card li::before {{ content: '—'; position: absolute; left: 0; color: rgba(45,49,66,0.25); font-size: 0.75rem; }}
    .footer {{ margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(45,49,66,0.10); font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.06em; color: var(--color-soft); display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem; }}
    @media print {{
      .diagram-container {{ overflow-x: visible; }}
      svg {{ min-width: 0; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <p class="header-eyebrow">{EYEBROW}</p>
      <h1>{H1}</h1>
      <p class="subtitle">People on the left, paper on the right. Of 1 d 32 min of charted time, the claim spends a full day idle in the approver tray before anyone inspects it.</p>
    </div>
    <div class="diagram-container">
{svg(p, slug, with_trace=True, full_key=True)}
    </div>

    <div class="cards">
      <div class="card">
        <p class="eyebrow">THE HEADLINE</p>
        <div class="card-header"><span class="card-dot coral"></span><h3>The wait is the procedure</h3></div>
        <p>EXP-001-05 is a delay symbol: the claim sat for a day. Every other charted step takes minutes.</p>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-dot ink"></span><h3>Two tracks, one chart</h3></div>
        <ul>
          <li>Personnel symbols say what a role does, present tense</li>
          <li>Paperwork symbols say what happened to the form, past tense</li>
          <li>Each handoff starts at a move symbol and names both columns</li>
        </ul>
      </div>
      <div class="card">
        <div class="card-header"><span class="card-dot muted"></span><h3>A diamond is an inspection</h3></div>
        <p>On a procedure chart the diamond means a mental verification, not a branch. Decision logic belongs in a flowchart, with its own legend.</p>
      </div>
    </div>

    <div class="footer">
      <span>fictional expense claim · illustrative trace is not telemetry</span>
      <span>example · procedure chart</span>
    </div>
  </div>
</body>
</html>
"""


def render_all() -> dict[Path, str]:
    return {
        ASSETS / "example-procedure-chart.html": minimal(LIGHT, "procedure-chart"),
        ASSETS / "example-procedure-chart-dark.html": minimal(DARK, "procedure-chart-dark"),
        ASSETS / "example-procedure-chart-full.html": full(LIGHT, "procedure-chart-full"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if any generated example differs from disk")
    args = parser.parse_args()
    files = render_all()
    stale = []
    for path, html in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != html:
            if args.check:
                stale.append(path.relative_to(ROOT).as_posix())
            else:
                path.write_text(html, encoding="utf-8")
                print(f"wrote {path.relative_to(ROOT).as_posix()}")
    if stale:
        print("stale procedure chart examples (run scripts/build-procedure-chart-examples.py):")
        for name in stale:
            print(f"  - {name}")
        return 1
    if args.check:
        print(f"OK procedure chart examples: {len(files)} files up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
