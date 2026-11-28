#!/usr/bin/env python3
"""Adversarial cases for scripts/verify-procedure-chart.py.

Both polarities (ADR 0005): every shipped variant passes, every Figure 11.4
symbol is recognised as itself and only itself, and each mutation below -- a
plausible rendered error, not a syntax slip -- is rejected with the finding
that names it. Existing diagrams must stay untouched by the new vocabulary.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
import json
import re
import subprocess
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
    expect("unresolved artifact", once(src, 'data-proc-column="finance" data-proc-artifact="EXP-001-A2"',
                'data-proc-column="finance" data-proc-artifact="EXP-001-A9"'),
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


def review_regressions() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    verify.ET.register_namespace("", "http://www.w3.org/2000/svg")

    def probe(name, change, needle):
        match = verify.SVG_RE.search(source)
        svg = verify.ET.fromstring(match.group())
        blocks = {e.get("data-block-id"): e for e in svg.iter() if e.get("data-block-id")}
        edges = {e.get("data-proc-connector-id"): e for e in svg.iter() if e.get("data-proc-connector-id")}
        change(svg, blocks, edges)
        expect(name, source[:match.start()] + verify.ET.tostring(svg, encoding="unicode")
               + source[match.end():], needle)

    for attrs in ({"stroke-opacity": "0"}, {"style": "stroke-opacity:0"},
                  {"fill": "none", "stroke": "none"}):
        probe("invisible take-off mark", lambda s, b, e: verify.one_mark(b["EXP-001-11"]).attrib.update(attrs),
              "symbol is hidden")
    for attrs in ({"fill-opacity": "0"}, {"fill": "#f5f5f5"}):
        probe("invisible comment", lambda s, b, e: b["EXP-001-02"][1].attrib.update(attrs),
              "must print its data-block-name")
    for attr in ("rx", "ry"):
        probe("round origin", lambda s, b, e: verify.one_mark(b["EXP-001-02"]).set(attr, "8"),
              "does not draw a 'origination'")
    probe("disjoint handoff", lambda s, b, e: e["EXP-H1"].set("d", "M 324,208 V 224 M 564,240 V 256"),
          "one continuous path")
    def duplicate(svg, blocks, edges):
        copy = verify.ET.fromstring(verify.ET.tostring(edges["EXP-H1"]))
        copy.set("data-proc-connector-id", "EXP-H-DUP")
        svg.append(copy)
    probe("duplicate endpoints", duplicate, "duplicate handoff EXP-001-04 -> EXP-001-05")
    probe("dangling marker", lambda s, b, e: e["EXP-H1"].set("marker-end", "url(#no-such-marker)"),
          "needs an arrowhead")
    probe("unready target", lambda s, b, e: b["EXP-001-12"].set("data-proc-step", "8"),
          "take-off target needs a receiving activity")
    probe("missing transfer drawing", lambda s, b, e: e["take-off:EXP-001-11:EXP-001-12"].set(
          "data-proc-connector", "unknown"), "missing take-off connector")
    probe("custody mismatch", lambda s, b, e: b["EXP-001-10"].set("data-proc-role", "requester"),
          "does not match paperwork custody")
    probe("printed role disagrees", lambda s, b, e: setattr(b["EXP-001-10"][2][0], "text", "requester"),
          "printed role must match")
    probe("unpaired handoff", lambda s, b, e: b["EXP-001-03"].set("data-proc-step", "3"),
          "no matching personnel move")
    probe("stray reversed diamond", lambda s, b, e: verify.ET.SubElement(s, "polygon",
          {"points": "50,30 40,20 30,30 40,40"}), "undeclared inspection diamond")
    probe("stray diamond path", lambda s, b, e: verify.ET.SubElement(s, "path",
          {"d": "M 40,20 L 50,30 L 40,40 L 30,30 Z"}), "undeclared inspection diamond")
    probe("bad artifact source", lambda s, b, e: b["EXP-001-A2"].set("data-proc-source", "nobody"),
          "source must name an element column")
    probe("overlapping lines", lambda s, b, e: b["EXP-001-12"].set("data-proc-at", "804 470"),
          "overlaps another artifact line")
    def extra_coordinate(svg, blocks, edges):
        mark = verify.one_mark(blocks["EXP-001-11"])
        mark.set("d", mark.get("d") + " 798,478")
    probe("extra coordinate gets a finding", extra_coordinate, "does not draw a 'information-take-off'")

    original_steps = build.STEPS
    original_handoffs = [(cid, a.id, b.id) for cid, a, b in build.handoffs()]
    try:
        build.STEPS = (replace(original_steps[0], id="EXP-001-NEW"),) + tuple(
            replace(a, step=a.step + 1) for a in original_steps)
        actual = [(cid, a.id, b.id) for cid, a, b in build.handoffs()]
        inserted = build.full(build.LIGHT, "procedure-chart-full")
        if actual != original_handoffs or any(
            f'data-proc-trace-id="{tid}" data-proc-trace-of="{aid}"' not in inserted
            for tid, aid, _, _ in build.TRACE
        ) or any(f'data-block-id="{a.id}"' not in inserted for a in original_steps):
            failures.append("step insertion changed existing activity IDs, handoff IDs or trace targets")
    finally:
        build.STEPS = original_steps
    data = verify.registry(EXAMPLE)
    blocks = {b["id"]: b for b in data["blocks"]}
    edges = {e["id"]: e for e in data["connectors"]}
    if (data["source"] != EXAMPLE.name or len(blocks) != 19 or len(edges) != 14
            or blocks["EXP-001-11"]["procedure"]["target-artifact"] != "EXP-001-A2"
            or blocks["EXP-001-A2"]["procedure"]["kind"] != "artifact"
            or blocks["EXP-001-07"]["procedure"]["elapsed-min"] != "10"
            or edges["EXP-H1"]["from"] != "EXP-001-04"
            or edges["take-off:EXP-001-11:EXP-001-12"]["to"] != "EXP-001-12"):
        failures.append("procedure registry lost block metadata or typed connectors")

def fictional_packet_regressions() -> None:
    """Use a separate travel-packet workflow, not the shipped example builder."""
    path = SCRIPTS / "fixtures" / "procedure-chart-fictional-packet.html"
    source = path.read_text(encoding="utf-8")
    verify.ET.register_namespace("", "http://www.w3.org/2000/svg")
    match = verify.SVG_RE.search(source)
    assert match is not None

    def case(name, change=None, needle=None, rewrite=lambda s: s):
        svg = verify.ET.fromstring(match.group())
        blocks = {e.get("data-block-id"): e for e in svg.iter() if e.get("data-block-id")}
        marker = next(e for e in svg.iter() if verify.local(e.tag) == "marker")
        flow = next(e for e in svg.iter() if e.get("data-from") == "pkt-new")
        if change:
            change(blocks, marker, flow)
        markup = rewrite(source[:match.start()] + verify.ET.tostring(svg, encoding="unicode")
                         + source[match.end():])
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / path.name
            fixture.write_text(markup, encoding="utf-8")
            for flag in ([], ["--registry"]):
                result = subprocess.run(
                    [sys.executable, str(SCRIPTS / "verify-procedure-chart.py"), *flag, str(fixture)],
                    capture_output=True, text=True, encoding="utf-8",
                )
                if needle is not None:
                    if result.returncode != 1 or needle not in result.stderr or result.stdout:
                        failures.append(f"{name} {flag}: expected {needle!r}; got {result}")
                elif result.returncode != 0:
                    failures.append(f"{name} {flag}: expected a pass; got {result.stderr}")
                elif flag:
                    registry = json.loads(result.stdout)
                    if len(registry["blocks"]) != 18 or len(registry["connectors"]) != 13:
                        failures.append(f"{name}: fictional packet lost blocks or connectors in export")
                elif "1 procedure chart(s)" not in result.stdout:
                    failures.append(f"{name}: checker did not count the fictional packet as a chart")

    def reorder(activity, selection):
        mark = verify.one_mark(activity)
        pts = mark.get("points").split()
        mark.set("points", " ".join(pts[i] for i in selection))

    def replace_mark(activity, kind, comment, tag, attrs):
        mark = verify.one_mark(activity)
        activity.remove(mark)
        ns = activity.tag.rsplit("}", 1)[0] + "}"
        verify.ET.SubElement(activity, ns + tag, {"data-role": "mark", "stroke": "#26323c", **attrs})
        activity.set("data-proc-symbol", kind)
        activity.set("data-block-name", comment)
        next(e for e in activity if e.get("data-proc-label") == "comment").text = comment

    def printed_time(blocks, replacement):
        title = next(e for e in blocks["PKT-REL"] if e.get("data-proc-label") == "header")
        title.text = title.text.replace(" · charted time 0 min", replacement)

    def stroked_marker(blocks, marker, flow):
        ns = marker.tag.rsplit("}", 1)[0] + "}"
        marker.remove(marker[0])
        group = verify.ET.SubElement(marker, ns + "g", {"stroke": "#26323c", "fill": "none"})
        verify.ET.SubElement(group, ns + "path", {"d": "M 0,0 L 8,3 L 0,6"})

    case("fictional packet valid with filled arrowhead")
    case("rotated diamond start", lambda b, m, f: reorder(b["pkt-inspected"], (1, 2, 3, 0)))
    case("reversed diamond winding", lambda b, m, f: reorder(b["pkt-inspected"], (3, 2, 1, 0)))
    case("crossing diamond edges", lambda b, m, f: reorder(b["pkt-inspected"], (0, 2, 1, 3)),
         "does not draw a 'inspection' symbol")
    case("reversed file winding", lambda b, m, f: reorder(b["r-file"], (2, 1, 0)))
    case("single-quoted chart type", rewrite=lambda text: text.replace(
        'data-diagram="procedure-chart"', "data-diagram='procedure-chart'", 1))
    case("empty arrowhead", lambda b, m, f: m.remove(m[0]), "needs an arrowhead")
    case("zero-width arrowhead", lambda b, m, f: m.set("markerWidth", "0"), "needs an arrowhead")
    case("non-painted arrowhead", lambda b, m, f: m[0].set("fill", "none"), "needs an arrowhead")
    case("hidden arrowhead", lambda b, m, f: m.set("style", "opacity:0"), "needs an arrowhead")
    case("collinear arrowhead", lambda b, m, f: m[0].set("points", "0,0 1,1 2,2"), "needs an arrowhead")
    case("visible stroked chevron", stroked_marker)
    case("reuse after destroy", lambda b, m, f: replace_mark(
        b["pkt-inspected"], "destroy", "Packet destroyed", "path",
        {"d": "M 347,422 L 363,438 M 363,422 L 347,438", "fill": "none"}),
         "cannot continue after destroy")
    case("duplicate creation", lambda b, m, f: replace_mark(
        b["pkt-inspected"], "origination", "Packet created again", "rect",
        {"x": "347", "y": "422", "width": "16", "height": "16", "fill": "white"}),
         "may only originate once")
    case("false zero total", lambda b, m, f: printed_time(b, " · charted time 1 d"),
         "charted time 0 min")
    case("zero total prefix is insufficient", lambda b, m, f: printed_time(b, " · charted time 0 minutes"),
         "charted time 0 min")
    case("zero total declared but omitted from header", lambda b, m, f: printed_time(b, ""),
         "charted time 0 min")

    def no_measurement(blocks, marker, flow):
        del blocks["PKT-REL"].attrib["data-proc-elapsed-total-min"]
        printed_time(blocks, "")

    case("omitting optional total when nothing is measured", no_measurement)
    case("wrong flow artifact", lambda b, m, f: f.set("data-proc-artifact", "R"),
         "data-proc-artifact must be 'P'")
    case("optional flow artifact omitted", lambda b, m, f: f.attrib.pop("data-proc-artifact"))


def main() -> int:
    symbols()
    mutations()
    review_regressions()
    fictional_packet_regressions()
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print("All procedure-chart verifier cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
