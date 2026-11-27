#!/usr/bin/env python3
"""Adversarial cases for scripts/verify-procedure-chart.py.

Both polarities (ADR 0005): every shipped variant passes, every Figure 11.4
symbol is recognised as itself and only itself, and each mutation below -- a
plausible rendered error, not a syntax slip -- is rejected with the finding
that names it. Existing diagrams must stay untouched by the new vocabulary.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
ASSETS = ROOT / "skills/diagram-design/assets"
EXAMPLE = ASSETS / "example-procedure-chart.html"
FULL = ASSETS / "example-procedure-chart-full.html"
sys.path.insert(0, str(SCRIPTS))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


verify = load("verify_procedure_chart", SCRIPTS / "verify-procedure-chart.py")
build = load("build_procedure_chart_examples", SCRIPTS / "build-procedure-chart-examples.py")
failures: list[str] = []


def run(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "example-procedure-chart-case.html"
        path.write_text(source, encoding="utf-8")
        return verify.check(path)


def expect(name: str, source: str, needle: str | None) -> None:
    errors = run(source)
    if needle is None:
        if errors:
            failures.append(f"{name}: expected a pass, got {errors}")
    elif not any(needle in error for error in errors):
        failures.append(f"{name}: expected a finding containing {needle!r}, got {errors}")


def once(source: str, old: str, new: str) -> str:
    assert source.count(old) >= 1, f"fixture drifted: {old!r} not found"
    return source.replace(old, new, 1)


def symbols() -> None:
    """Every mark the builder draws is recognised as itself and nothing else."""
    for track in ("paperwork", "personnel"):
        allowed = verify.PERSONNEL if track == "personnel" else verify.PAPERWORK
        for symbol in allowed:
            html = build.mark(symbol, 200, 300, track, "#2d3142", "#ffffff")
            element = verify.ET.fromstring(html)
            drawn = verify.mark_shape(element, 200, 300, verify.HALF[track])
            if drawn != symbol:
                failures.append(f"symbol {symbol} ({track}) was read as {drawn!r}")
            shifted = verify.mark_shape(element, 230, 300, verify.HALF[track])
            if shifted is not None:
                failures.append(f"symbol {symbol} ({track}) was accepted 30px off its declared centre")
    if set(verify.PERSONNEL) - set(verify.PAPERWORK):
        failures.append("personnel symbols must be a subset of the paperwork set (Figure 11.4)")
    if len(verify.PAPERWORK) != 11 or len(verify.PERSONNEL) != 3:
        failures.append("Figure 11.4 defines eleven paperwork and three personnel symbols")
    if verify.fmt_minutes(1472) != "1 d 32 min" or verify.fmt_minutes(90) != "1 h 30 min":
        failures.append("fmt_minutes formats charted time wrongly")


def mutations() -> None:
    src = EXAMPLE.read_text(encoding="utf-8")
    full = FULL.read_text(encoding="utf-8")
    for path in sorted(ASSETS.glob("example-procedure-chart*.html")):
        expect(path.name, path.read_text(encoding="utf-8"), None)

    # Symbols and tracks.
    expect("decision diamond", once(src, 'data-proc-symbol="inspection" data-proc-track="paperwork"',
                                     'data-proc-symbol="operation" data-proc-track="paperwork"'),
           "a diamond means inspection")
    expect("personnel delay", once(src, 'data-proc-symbol="operation" data-proc-track="personnel"',
                                   'data-proc-symbol="delay" data-proc-track="personnel"'),
           "is not a Figure 11.4 personnel symbol")
    expect("unknown symbol", once(src, 'data-proc-symbol="delay"', 'data-proc-symbol="wait"'),
           "is not a Figure 11.4 paperwork symbol")
    expect("square drawn as circle", re.sub(
        r'<rect data-role="mark" x="(\d+)" y="(\d+)" width="16" height="16"',
        lambda m: f'<circle data-role="mark" cx="{int(m[1]) + 8}" cy="{int(m[2]) + 8}" r="8"', src, count=1),
        "does not draw a 'origination' symbol")
    expect("two marks", once(src, '<text data-proc-label="comment"',
                             '<circle data-role="mark" cx="0" cy="0" r="4"/><text data-proc-label="comment"'),
           "exactly one data-role=mark")
    expect("hidden symbol", once(src, '<circle data-role="mark"', '<circle data-role="mark" opacity="0"'),
           "hidden, transparent or transformed")
    expect("transformed symbol", once(src, 'data-proc-symbol="delay"',
                                      'transform="translate(400 0)" data-proc-symbol="delay"'),
           "hidden, transparent or transformed")

    # Registry links.
    expect("duplicate block id", once(src, 'data-block-id="EXP-001-02"', 'data-block-id="EXP-001-01"'),
           "duplicate data-block-id")
    expect("orphan parent", once(src, 'data-block-parent="EXP-001" data-block-name="Claim created"',
                                 'data-block-parent="EXP-009" data-block-name="Claim created"'),
           "must be the procedure root")
    expect("unresolved artifact", once(src, 'data-proc-artifact="EXP-001-A2"', 'data-proc-artifact="EXP-001-A9"'),
           "does not resolve to an artifact")
    expect("unresolved role", once(src, 'data-proc-role="approver"', 'data-proc-role="auditor"'),
           "must name an element column")
    expect("flow to nowhere", once(src, 'data-proc-connector="flow" data-from="EXP-001-01" data-to="EXP-001-03"',
                                   'data-proc-connector="flow" data-from="EXP-001-01" data-to="EXP-001-06"'),
           "missing flow line EXP-001-01 -> EXP-001-03")
    expect("handoff id clash", once(src, 'data-proc-connector-id="EXP-H2"', 'data-proc-connector-id="EXP-H1"'),
           "duplicate handoff id")
    expect("handoff id is a block id", src.replace('"EXP-H1"', '"EXP-001-01"'), "duplicate handoff id")
    expect("undeclared handoff", re.sub(r'<path data-proc-connector="handoff"[^>]*data-from="EXP-001-09"[^>]*/>',
                                        "", src), "without a declared handoff")
    expect("handoff from a non-move", once(src, 'data-proc-symbol="move" data-proc-track="paperwork" '
                                                'data-block-id="EXP-001-09"',
                                           'data-proc-symbol="operation" data-proc-track="paperwork" '
                                           'data-block-id="EXP-001-09"'), "must start at a move symbol")
    expect("unlabelled handoff", re.sub(r'<g data-proc-label-for="EXP-H1">.*?</g>', "", src, count=1, flags=re.S),
           "must carry a visible label")
    expect("mislabelled handoff", once(src, "EXP-H1 Requester → Approver", "EXP-H1 Requester → Finance office"),
           "must carry a visible label")
    expect("handoff missing arrow", re.sub(r'(data-proc-connector-id="EXP-H1"[^>]*?) marker-end="url\(#arrow\)"',
                                           r"\1", src, count=1), "needs an arrowhead")

    # Geometry.
    expect("symbol in wrong column", once(src, 'data-proc-at="564 266"', 'data-proc-at="804 266"'),
           "outside its 'approver' column")
    expect("step on two rows", once(src, 'data-proc-at="324 130"', 'data-proc-at="324 138"'),
           "drawn on two rows")
    expect("rows out of order", src.replace('data-proc-step="8"', 'data-proc-step="9"'),
           "without gaps")
    expect("flow line off its symbols", once(src, 'x1="92" y1="142"', 'x1="92" y1="148"'),
           "must run straight down")
    expect("flow line with arrowhead", re.sub(r'(<line data-proc-connector="flow"[^>]*?)/>',
                                              r'\1 marker-end="url(#arrow)"/>', src, count=1),
           "arrowheads belong to handoffs")
    expect("handoff ends short", re.sub(r'(data-proc-connector-id="EXP-H1"[^>]*d="[^"]*V )(\d+)"',
                                        lambda m: f'{m[1]}{int(m[2]) - 12}"', src, count=1), "path must run from")
    expect("personnel column moved right", once(src, 'data-proc-column-id="personnel" data-proc-column-label="Personnel" '
                                                     'x="64"', 'data-proc-column-id="personnel" '
                                                     'data-proc-column-label="Personnel" x="1200"'),
           "personnel column must be the leftmost")
    expect("second personnel column", once(src, 'data-proc-column="element" data-proc-column-id="requester"',
                                           'data-proc-column="personnel" data-proc-column-id="requester"'),
           "exactly one personnel column")

    # Charted time, printed IDs and dispositions.
    expect("header total wrong", once(src, "charted time 1 d 32 min", "charted time 1 d 30 min"),
           "charted time 1 d 32 min")
    expect("declared total wrong", once(src, 'data-proc-elapsed-total-min="1472"', 'data-proc-elapsed-total-min="1470"'),
           "steps sum to 1472")
    expect("step time disagrees", once(src, 'data-proc-elapsed-min="1440"', 'data-proc-elapsed-min="1400"'),
           "must print")
    expect("printed ID disagrees", once(src, ">EXP-001-07 · 10 min<", ">EXP-001-08 · 10 min<"),
           "must print 'EXP-001-07 · 10 min'")
    expect("comment disagrees", once(src, ">Claim verified<", ">Claim approved<"), "data-block-name")
    expect("elapsed on personnel", once(src, 'data-proc-role="requester"',
                                        'data-proc-role="requester" data-proc-elapsed-min="5"'),
           "paperwork symbols only")
    expect("distance off a move", once(src, 'data-proc-elapsed-min="15"', 'data-proc-distance-m="3"'),
           "move symbols only")
    expect("disposition contradicts last symbol", once(src, 'data-proc-disposition="file"',
                                                       'data-proc-disposition="destroy"'),
           "last symbol is 'file'")
    expect("artifact key disagrees", once(src, "· source requester · filed", "· source requester · destroyed"),
           "must print")
    expect("take-off without target", re.sub(r' data-proc-target-artifact="[^"]*"', "", src, count=1),
           "must name its data-proc-target-artifact")
    expect("missing analyst", once(src, 'data-proc-analyst="J. Doe"', 'data-proc-analyst=""'),
           "data-proc-analyst")

    # Legend: procedure meanings only, and complete.
    expect("legend names a decision", once(src, ">Inspection</text>", ">Decision</text>"), "names a decision")
    expect("legend missing symbol", re.sub(r'<g data-proc-legend="delay".*?</g>', "", src, count=1, flags=re.S),
           "legend is missing the 'delay' symbol")
    expect("legend mark swapped", re.sub(r'(<g data-proc-legend="file"[^>]*>\s*)<polygon[^>]*/>',
                                         lambda m: m[1] + build.mark("inspection", 636, 740, "paperwork", "#4f5d75",
                                                                     "#ffffff"), src, count=1),
           "does not draw its own symbol")
    expect("flowchart markup", once(src, "</svg>", '<g data-kind="decision"></g></svg>'),
           "flowchart decision markup")

    # Illustrative trace stays apart from the definition.
    expect("trace carries a block id", once(full, 'data-proc-trace-id="TR-01"',
                                            'data-proc-trace-id="TR-01" data-block-id="TR-01"'),
           "trace carries data-block-*")
    expect("trace not illustrative", once(full, 'data-proc-illustrative="true"', 'data-proc-illustrative="false"'),
           "data-proc-illustrative")
    expect("trace points at nothing", once(full, 'data-proc-trace-of="EXP-001-07"', 'data-proc-trace-of="EXP-001-99"'),
           "names no activity")
    expect("trace runs backwards", once(full, 'data-proc-trace-of="EXP-001-14"', 'data-proc-trace-of="EXP-001-02"'),
           "runs backwards")
    expect("trace caption missing", once(full, "ILLUSTRATIVE TRACE · ONE IMAGINED RUN · NOT TELEMETRY",
                                         "TRACE · ONE RUN"), "illustrative in visible text")

    # Compatibility with existing diagrams.
    flow = (ASSETS / "example-flowchart.html").read_text(encoding="utf-8")
    expect("flowchart untouched", flow, None)
    expect("procedure vocabulary in a flowchart", once(flow, "<svg ", '<svg data-proc-symbol="inspection" '),
           "used outside a procedure chart")
    expect("two charts in one file", once(src, "</body>", "<svg data-diagram=\"procedure-chart\"></svg></body>"),
           "exactly one")
    for path in sorted(ASSETS.glob("*.html")):
        if "procedure-chart" in path.name:
            continue
        errors = verify.check(path)
        if errors:
            failures.append(f"{path.name}: an existing diagram fails the procedure-chart check: {errors}")


def main() -> int:
    symbols()
    mutations()
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print("All procedure-chart verifier cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
