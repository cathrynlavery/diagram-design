#!/usr/bin/env python3
"""Adversarial cases for verify-streamgraph.py, both polarities.

Every case is named for exactly what it asserts, and the negative half matters
as much as the positive: a checker that fires on an honest pinch-to-zero, on
honest rounding, or on the other shipped example types gets widened or switched
off, and then it guards nothing.

Fixtures are built from the same math the shipped example uses - a symmetric
baseline, one shared scale, Catmull-Rom boundaries at 1/6 chord - so a mutation
breaks exactly the invariant its case names. Fixtures live in a per-process
temporary directory; two cases at the end hold that isolation in place.

Exit: 0 all pass, 1 any failure.
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

verify = __import__("verify-streamgraph")

SHIPPED = ROOT / "skills/diagram-design/assets/example-streamgraph.html"

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="streamgraph-title streamgraph-desc">
  <title id="streamgraph-title">t</title>
  <desc id="streamgraph-desc">Streamgraph fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

# The shared geometry the shipped example uses: 1.25px per unit about y=230.
SCALE = 1.25
MIDLINE = 230.0
XS = [80 + 80 * i for i in range(6)]
PERIODS = ["W01", "W02", "W03", "W04", "W05", "W06"]

# Stack order bottom-first. Names deliberately digit-free: the legend prints
# one numeric token per entry, and a digit in a name is ambiguous by design.
ROWS = [
    ("Docs", [8, 9, 7, 6, 0, 0]),
    ("Unit", [58, 60, 62, 61, 64, 66]),
    ("Suite", [12, 15, 19, 26, 34, 45]),
]


def boundaries(rows, scale=SCALE, midline=MIDLINE, shift=None):
    """boundary[0] = envelope bottom, boundary[k] = top of layer k-1.

    shift, when given, is a per-period y offset applied to the whole stack -
    the tool for building a drifting or bottom-pinned baseline whose layers
    still tile and still match their declared thicknesses.
    """
    periods = len(rows[0][1])
    totals = [sum(values[i] for _, values in rows) for i in range(periods)]
    offsets = shift or [0.0] * periods
    out = [[round(midline + totals[i] * scale / 2 + offsets[i], 1)
            for i in range(periods)]]
    running = [midline + totals[i] * scale / 2 + offsets[i] for i in range(periods)]
    for _name, values in rows:
        running = [running[i] - values[i] * scale for i in range(periods)]
        out.append([round(y, 1) for y in running])
    return out


def fmt(value):
    text = ("%.1f" % value).rstrip("0").rstrip(".")
    return text if text else "0"


def catmull_segments(points):
    segments = []
    count = len(points)
    for i in range(count - 1):
        p0 = points[i - 1] if i > 0 else points[i]
        p1, p2 = points[i], points[i + 1]
        p3 = points[i + 2] if i + 2 < count else points[i + 1]
        c1 = (p1[0] + (p2[0] - p0[0]) / 6.0, p1[1] + (p2[1] - p0[1]) / 6.0)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6.0, p2[1] - (p3[1] - p1[1]) / 6.0)
        segments.append("C %s %s, %s %s, %s %s" % (
            fmt(round(c1[0], 1)), fmt(round(c1[1], 1)),
            fmt(round(c2[0], 1)), fmt(round(c2[1], 1)),
            fmt(p2[0]), fmt(p2[1])))
    return segments


def layer_path(top_pts, bottom_pts):
    rev = list(reversed(bottom_pts))
    parts = ["M %s %s" % (fmt(top_pts[0][0]), fmt(top_pts[0][1]))]
    parts.extend(catmull_segments(top_pts))
    parts.append("L %s %s" % (fmt(rev[0][0]), fmt(rev[0][1])))
    parts.extend(catmull_segments(rev))
    parts.append("Z")
    return " ".join(parts)


def layer_markup(name, values, top_pts, bottom_pts, quote='"'):
    d = layer_path(top_pts, bottom_pts)
    q = quote
    return ("  <path data-layer=%s%s%s data-values=%s%s%s d=%s%s%s "
            "fill=%s#2d3142%s/>\n"
            % (q, name, q, q, ",".join(str(v) for v in values), q, q, d, q,
               q, q))


def captions(xs=None, periods=None):
    xs = XS if xs is None else xs
    periods = PERIODS[:len(xs)] if periods is None else periods
    out = ""
    for i, (x, period) in enumerate(zip(xs, periods)):
        out += ('  <text data-period="%s" data-index="%d" x="%g" y="440">%s'
                "</text>\n" % (period, i, x, period))
    return out


def legend(rows):
    out = ""
    for name, values in rows:
        total = sum(values)
        out += ('  <text data-layer="%s" data-total="%g" x="40" y="496">'
                "%s · %g min</text>\n" % (name, total, name, total))
    return out


def figure(rows=None, shift=None, quote='"'):
    """The layer paths + captions + legend for an honest figure."""
    rows = ROWS if rows is None else rows
    bounds = boundaries(rows, shift=shift)
    body = ""
    for k, (name, values) in enumerate(rows):
        top = list(zip(XS, bounds[k + 1]))
        bottom = list(zip(XS, bounds[k]))
        body += layer_markup(name, values, top, bottom, quote=quote)
    return body + captions() + legend(rows)


def document(*blocks):
    return HEAD + "".join(blocks) + TAIL


class Harness:
    def __init__(self):
        self.failures = 0
        self.count = 0
        self.dir = Path(tempfile.mkdtemp(prefix="streamgraph-fixtures-"))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name):
        return self.dir / name

    def run(self, source, name="example-streamgraph-fixture.html"):
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            return verify.check(path)
        finally:
            path.unlink()

    def expect_clean(self, label, source, name=None):
        self.count += 1
        found = self.run(source, name) if name else self.run(source)
        if found:
            self.failures += 1
            print("FAIL  %s" % label)
            for item in found:
                print("        unexpected: %s" % item)
        else:
            print("ok    %s" % label)

    def expect_finding(self, label, source, pattern, name=None):
        self.count += 1
        found = self.run(source, name) if name else self.run(source)
        if not found:
            self.failures += 1
            print("FAIL  %s\n        expected a finding, got none" % label)
            return
        if not any(re.search(pattern, item) for item in found):
            self.failures += 1
            print("FAIL  %s\n        no finding matched %r" % (label, pattern))
            for item in found:
                print("        got: %s" % item)
            return
        print("ok    %s" % label)

    def expect_only_one(self, label, source, pattern):
        """A single defect must produce a single finding, not a cascade."""
        self.count += 1
        found = self.run(source)
        if len(found) == 1 and re.search(pattern, found[0]):
            print("ok    %s" % label)
            return
        self.failures += 1
        print("FAIL  %s\n        expected exactly one finding matching %r, got %d"
              % (label, pattern, len(found)))
        for item in found:
            print("        got: %s" % item)

    def expect_out_of_scope(self, label, source, name):
        """Not merely finding-free - genuinely outside this checker's scope."""
        self.count += 1
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            detected = verify.looks_like_streamgraph(path, source)
            found = verify.check(path)
        finally:
            path.unlink()
        if detected or found:
            self.failures += 1
            print("FAIL  %s\n        detected=%s findings=%d"
                  % (label, detected, len(found)))
            return
        print("ok    %s" % label)

    def check(self, label, condition, detail=""):
        self.count += 1
        if condition:
            print("ok    %s" % label)
            return
        self.failures += 1
        print("FAIL  %s%s" % (label, ("\n        " + detail) if detail else ""))


def main():
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


def run_cases(h):
    # ── Negative half: honest figures must stay silent ────────────────────
    h.expect_clean("an honest streamgraph reports nothing", document(figure()))

    h.expect_clean(
        "the shipped light example reports nothing",
        SHIPPED.read_text(encoding="utf-8"), name="example-streamgraph.html",
    )

    # The pinch is data: Docs holds two zero periods in the default rows, and a
    # figure where one period's TOTAL is zero must also pass - both boundaries
    # of every layer meet on the midline there.
    h.expect_clean(
        "a period where every layer is zero pinches the whole stream and passes",
        document(figure(rows=[("Docs", [8, 6, 0, 5, 8, 9]),
                              ("Unit", [30, 20, 0, 24, 30, 33])])),
    )

    h.expect_clean(
        "an honest figure written with single-quoted attributes is parsed",
        document(figure(quote="'")),
    )

    # The rotated value-axis caption carries a transform and is not bound.
    h.expect_clean(
        "the rotated value-axis caption's transform is not reported",
        document('  <text transform="rotate(-90 24 230)" x="24" y="230">'
                 "BUILD MINUTES PER WEEK</text>\n" + figure()),
    )

    h.expect_clean(
        "a CSS text-transform declaration is not read as a transform",
        HEAD + "<style>.eyebrow { text-transform: uppercase; }</style>\n"
        + figure() + TAIL,
    )

    h.expect_clean(
        "scenery paths without data-layer are skipped silently",
        document(figure()
                 + '  <path d="M 0 0 L 4 4 Z" fill="#2d3142"/>\n'),
    )

    h.expect_clean(
        "a commented-out layer is ignored, not read as data",
        document(figure()
                 + '  <!-- old draft: <path data-layer="ghost" data-values="1,2" '
                   'd="M 0 0 Z"/> -->\n'),
    )

    # The detector must not drag the other example types into scope.
    for other in ("example-line.html", "example-slopegraph.html",
                  "example-sankey.html", "example-treemap.html"):
        path = ROOT / "skills/diagram-design/assets" / other
        if path.exists():
            h.expect_out_of_scope(
                "%s is not detected as a streamgraph at all" % other,
                path.read_text(encoding="utf-8"), other)

    # ── Positive half: each lie must be named as itself ───────────────────

    # 2. One scale. The geometry stays where it is; the declaration changes.
    # The legend is kept consistent with the mutated declaration, so the only
    # lie left is the one between the values and the drawn thickness.
    inflated = document(figure()).replace(
        'data-values="8,9,7,6,0,0"', 'data-values="8,9,12,6,0,0"', 1).replace(
        'data-total="30"', 'data-total="35"', 1).replace(
        ">Docs · 30 min<", ">Docs · 35 min<", 1)
    h.expect_only_one(
        "a declared value the drawn thickness contradicts reports as one point",
        inflated, r"'Docs' draws .* at period 2 where its declared value 12",
    )

    zero_lie = document(figure()).replace(
        'data-values="8,9,7,6,0,0"', 'data-values="8,9,7,6,4,0"', 1).replace(
        'data-total="30"', 'data-total="34"', 1).replace(
        ">Docs · 30 min<", ">Docs · 34 min<", 1)
    h.expect_only_one(
        "a zero-thickness pinch declared as a nonzero value is reported",
        zero_lie, r"'Docs' draws .* period 4 .* declared value 4",
    )

    # 3. Tiled stack. Shift the TOP layer up 6px whole: its thicknesses and
    # curves survive, the seam against its neighbour does not.
    rows = ROWS
    bounds = boundaries(rows)
    shifted_body = ""
    for k, (name, values) in enumerate(rows):
        lift = 6.0 if name == "Suite" else 0.0
        top = [(x, y - lift) for x, y in zip(XS, bounds[k + 1])]
        bottom = [(x, y - lift) for x, y in zip(XS, bounds[k])]
        shifted_body += layer_markup(name, values, top, bottom)
    h.expect_only_one(
        "a layer floated 6px off its neighbour reports as one seam, not a cascade",
        document(shifted_body + captions() + legend(rows)),
        r"'Suite'.*bottom boundary sits 6\.0 px above layer 'Unit'",
    )

    # A per-period reorder: at one period two layers exchange places in the
    # stack while every thickness stays true to its declared value and the
    # envelope stays centred. The only lie is the order - and it must surface
    # through the seam checks, or the fixed-order guarantee is decorative.
    swap_at = 3
    crossed_body = ""
    positions = {}
    for i in range(len(ROWS[0][1])):
        order = ["Docs", "Unit", "Suite"]
        if i == swap_at:
            order = ["Docs", "Suite", "Unit"]
        total = sum(values[i] for _name, values in ROWS)
        y = MIDLINE + total * SCALE / 2
        for name in order:
            values = dict(ROWS)[name]
            positions.setdefault(name, {})[i] = (round(y - values[i] * SCALE, 1),
                                                 round(y, 1))
            y -= values[i] * SCALE
    for name, values in ROWS:
        top = [(XS[i], positions[name][i][0]) for i in range(len(values))]
        bottom = [(XS[i], positions[name][i][1]) for i in range(len(values))]
        crossed_body += layer_markup(name, values, top, bottom)
    h.expect_finding(
        "two layers exchanged at one period are reported as a broken seam",
        document(crossed_body + captions() + legend(ROWS)),
        r"must tile with no gaps and no overlaps, in one fixed order",
    )

    # 4. Symmetric baseline. Pin the envelope bottom to y=420: every layer
    # still tiles and every thickness still matches, so the only lie left is
    # the baseline - and it must be named alone.
    periods = len(ROWS[0][1])
    totals = [sum(values[i] for _, values in ROWS) for i in range(periods)]
    pinned = [420.0 - (MIDLINE + totals[i] * SCALE / 2) for i in range(periods)]
    h.expect_only_one(
        "a bottom-pinned baseline reports as asymmetric and stops there",
        document(figure(shift=pinned)),
        r"baseline is not symmetric",
    )

    # 5. Determined curves. Bulge one control point 8px.
    honest_doc = document(figure())
    match = re.search(r"C ([\d.]+) ([\d.]+),", honest_doc)
    assert match is not None
    bulged = honest_doc.replace(
        match.group(0),
        "C %s %s," % (match.group(1), float(match.group(2)) - 8.0), 1)
    h.expect_only_one(
        "a control point pulled 8px off Catmull-Rom is reported as editorialising",
        bulged, r"bends away from its vertices",
    )

    # Shared columns.
    offgrid_body = ""
    for k, (name, values) in enumerate(rows):
        xs = [x + (12 if name == "Unit" else 0) for x in XS]
        top = list(zip(xs, bounds[k + 1]))
        bottom = list(zip(xs, bounds[k]))
        offgrid_body += layer_markup(name, values, top, bottom)
    h.expect_finding(
        "a layer sampling its own period columns is reported",
        document(offgrid_body + captions() + legend(rows)),
        r"must share one set of period columns",
    )

    # Transforms move the rendered mark away from the checked coordinates.
    h.expect_finding(
        "a transform on a layer path is reported",
        document(figure()).replace(
            '  <path data-layer="Docs"',
            '  <path transform="translate(0 80)" data-layer="Docs"', 1),
        r"layer 'Docs' carries transform",
    )

    h.expect_finding(
        "a transform on a bound label is reported",
        document(figure()).replace(
            '  <text data-period="W01"',
            '  <text transform="translate(0 40)" data-period="W01"', 1),
        r"bound label.*carries transform",
    )

    h.expect_finding(
        "an ancestor <g> transform over the layers is reported",
        document('  <g transform="translate(0 60)">\n' + figure() + "  </g>\n"),
        r"carries an ancestor <g>/<svg> transform",
    )

    h.expect_finding(
        "a CSS transform declaration is reported",
        HEAD + "<style>path { transform: translateY(40px); }</style>\n"
        + figure() + TAIL,
        r"a CSS `transform` declaration",
    )

    # 6. Legend bindings.
    h.expect_only_one(
        "a printed total that contradicts its binding is reported",
        document(figure()).replace(">Docs · 30 min<", ">Docs · 28 min<", 1),
        r"legend entry for 'Docs' prints .* but declares 30",
    )

    h.expect_finding(
        "a declared total that is not the sum of the values is reported",
        document(figure()).replace('data-total="30"', 'data-total="34"', 1)
        .replace(">Docs · 30 min<", ">Docs · 34 min<", 1),
        r"'Docs' declares a total of 34 but its values sum to 30",
    )

    h.expect_finding(
        "a layer with no legend entry is reported, not dropped from the reading",
        document(figure()).replace(
            '  <text data-layer="Docs" data-total="30" x="40" y="496">'
            "Docs · 30 min</text>\n", "", 1),
        r"'Docs' has no legend entry",
    )

    h.expect_finding(
        "a legend entry for a layer no path declares is reported",
        document(figure()
                 + '  <text data-layer="Ghost" data-total="9" x="40" y="496">'
                   "Ghost · 9 min</text>\n"),
        r"names layer 'Ghost', which no path declares",
    )

    h.expect_finding(
        "a second legend entry for one layer is reported",
        document(figure()
                 + '  <text data-layer="Docs" data-total="30" x="40" y="496">'
                   "Docs · 30 min</text>\n"),
        r"a second legend entry for layer 'Docs'",
    )

    digit_rows = [("Docs", ROWS[0][1]), ("Unit", ROWS[1][1]), ("E2E", ROWS[2][1])]
    h.expect_finding(
        "a digit in a layer name makes its legend total ambiguous and is reported",
        document(figure(rows=digit_rows)),
        r"prints more than one numeric token",
    )

    # The wrong-name case: data-layer and data-total both stay correct, so
    # every numeric check passes and only the string a reader actually sees is
    # wrong. This is the shape a legend lies in.
    h.expect_only_one(
        "a legend entry printing another layer's name is reported",
        document(figure()).replace(
            'y="496">Docs · 30 min<', 'y="496">Unit · 30 min<', 1),
        r"legend entry for 'Docs' prints 'Unit · 30 min', which does not name",
    )

    h.expect_only_one(
        "a legend entry naming two layers at once is reported",
        document(figure()).replace(
            'y="496">Docs · 30 min<', 'y="496">Docs and Unit · 30 min<', 1),
        r"legend entry for 'Docs' also prints 'Unit'",
    )

    # And the check must not tighten into "the name and nothing else": the
    # shipped entries annotate with · focal and · paused.
    h.expect_clean(
        "a legend entry may annotate beyond its layer name and its total",
        document(figure()).replace(
            'y="496">Docs · 30 min<', 'y="496">Docs · 30 min · paused<', 1),
    )

    # Period caption bindings.
    h.expect_finding(
        "a missing period caption is reported",
        document(figure()).replace(
            '  <text data-period="W03" data-index="2" x="240" y="440">W03</text>\n',
            "", 1),
        r"no caption for period 2",
    )

    h.expect_finding(
        "two captions for one column are reported",
        document(figure()
                 + '  <text data-period="W02" data-index="1" x="160" y="440">W02'
                   "</text>\n"),
        r"a second caption for period 1",
    )

    h.expect_only_one(
        "a caption drawn off its column is reported",
        document(figure()).replace(
            'data-index="2" x="240"', 'data-index="2" x="320.5"', 1),
        r"caption for period 2 .* drawn at x=320\.5 but its column is at x=240",
    )

    h.expect_finding(
        "a caption whose text contradicts its binding is reported",
        document(figure()).replace(
            'data-index="2" x="240" y="440">W03', 'data-index="2" x="240" y="440">W04', 1),
        r"caption for period 2 reads 'W04' but declares data-period='W03'",
    )

    h.expect_finding(
        "a caption index that names no column is reported",
        document(figure()
                 + '  <text data-period="W09" data-index="8" x="720" y="440">W09'
                   "</text>\n"),
        r"data-index='8', which is not a column",
    )

    h.expect_finding(
        "a caption carrying only half its binding is reported",
        document(figure()).replace(' data-period="W01"', "", 1),
        r"must carry both data-index .* and data-period",
    )

    # 7. Fail closed, and read what is actually there.
    h.expect_finding(
        "a file named example-streamgraph with no layers is reported, not passed",
        document('  <path d="M 0 0 L 4 4 Z" fill="#2d3142"/>\n'),
        r"presents as a streamgraph but declares 0 verifiable layer",
        name="example-streamgraph-empty.html",
    )

    h.expect_finding(
        "a file whose desc says streamgraph but declares no layers is reported",
        document('  <path d="M 0 0 L 4 4 Z" fill="#2d3142"/>\n'),
        r"presents as a streamgraph but declares 0 verifiable layer",
        name="figure.html",
    )

    h.expect_finding(
        "a streamgraph declared only in a desc past 4000 chars is still detected",
        "<!doctype html><style>/*" + ("x" * 4200) + "*/</style>"
        + '<svg role="img"><title>t</title>'
        + "<desc>Streamgraph of build minutes with no declared layers.</desc>"
        + '<path d="M 0 0 Z"/></svg>',
        r"presents as a streamgraph but declares 0 verifiable layer",
        name="figure.html",
    )

    h.expect_finding(
        "a layer missing data-values is reported rather than dropped",
        document(figure()).replace(' data-values="8,9,7,6,0,0"', "", 1),
        r"'Docs' is missing data-values",
    )

    h.expect_finding(
        "a declared value that is not a finite number is reported",
        document(figure()).replace(
            'data-values="8,9,7,6,0,0"', 'data-values="8,nine,7,6,0,0"', 1),
        r"'Docs' declares a value that is not a finite number",
    )

    h.expect_finding(
        "a NaN value is reported, not silently accepted",
        document(figure()).replace(
            'data-values="8,9,7,6,0,0"', 'data-values="8,nan,7,6,0,0"', 1),
        r"'Docs' declares a value that is not a finite number",
    )

    h.expect_finding(
        "a negative value is reported",
        document(figure()).replace(
            'data-values="8,9,7,6,0,0"', 'data-values="8,-9,7,6,0,0"', 1),
        r"'Docs' declares a negative value",
    )

    h.expect_finding(
        "a value count that disagrees with the drawn periods is reported",
        document(figure()).replace(
            'data-values="8,9,7,6,0,0"', 'data-values="8,9,7,6,0"', 1),
        r"'Docs' declares 5 values but draws 6 period vertices",
    )

    h.expect_finding(
        "a second path declaring the same layer is reported",
        document(figure() + layer_markup(
            "Docs", ROWS[0][1],
            list(zip(XS, boundaries(ROWS)[1])), list(zip(XS, boundaries(ROWS)[0])))),
        r"a second path declares data-layer='Docs'",
    )

    h.expect_finding(
        "a relative path command is refused rather than half-parsed",
        document(figure()).replace('d="M ', 'd="m ', 1),
        r"uses path command 'm'",
    )

    h.expect_finding(
        "a shorthand or axis-aligned command is refused rather than half-parsed",
        document(
            '  <path data-layer="Docs" data-values="1,2,3" '
            'd="M 80 100 H 160 L 240 100 L 240 120 L 160 120 L 80 120 Z"/>\n'
            + figure(rows=ROWS[1:])),
        r"uses path command 'H'",
    )

    h.expect_finding(
        "a path with two subpaths is refused",
        document(
            '  <path data-layer="Docs" data-values="1,2,3" '
            'd="M 80 100 L 160 100 Z M 80 120 L 160 120 Z"/>\n'
            + figure(rows=ROWS[1:])),
        r"exactly one",
    )

    h.expect_finding(
        "a <path> declaring data-layer whose attributes cannot be parsed is reported",
        document(figure()
                 + "  <path data-layer=unquoted data-values=1,2 d=M08Z/>\n"),
        r"declares data-layer but its attributes could not be parsed",
    )

    h.expect_finding(
        "a single-quoted layer with a contradicted value is still reported",
        document(figure(quote="'")).replace(
            "data-values='8,9,7,6,0,0'", "data-values='8,9,12,6,0,0'", 1),
        r"'Docs' draws .* period 2",
    )

    h.expect_finding(
        "a figure with a single verifiable layer fails closed",
        document(figure(rows=ROWS[:1])),
        r"declares 1 verifiable layer",
    )

    # 8. Duplicate attributes are read the way the browser reads them.
    # HTML drops a repeated attribute and keeps the first, so a last-wins
    # reader validates bytes that are not in the document. Chromium confirms
    # it on the shipped example: append a second d and the parsed DOM keeps
    # d="M 0 0 Z" while the real path is absent.
    h.check(
        "attrs_of keeps the first of a duplicated attribute",
        verify.attrs_of(' d="first" data-x="1" d="second" data-x="2"')
        == {"d": "first", "data-x": "1"},
        detail=repr(verify.attrs_of(' d="first" d="second"')),
    )

    h.expect_finding(
        "a duplicated d is read first-wins, so an invalid first d is reported",
        document(figure()).replace(' d="', ' d="M 0 0 Z" d="', 1),
        r"layer 'Docs'.s path must contain exactly one L",
    )

    h.expect_only_one(
        "a duplicated data-values is read first-wins, so a dishonest first list "
        "is reported",
        document(figure()).replace(
            'data-values="8,9,7,6,0,0"',
            'data-values="0,0,6,7,9,8" data-values="8,9,7,6,0,0"', 1),
        r"'Docs' draws .* thickness at period",
    )

    h.expect_finding(
        "a duplicated data-total is read first-wins, so a dishonest first total "
        "is reported",
        document(figure()).replace(
            'data-total="30"', 'data-total="34" data-total="30"', 1),
        r"'Docs' declares a total of 34 but its values sum to 30",
    )

    # The rule is first-wins, not "a repeated attribute is an error": when the
    # first value is the honest one the browser draws an honest figure, and so
    # this checker must stay silent.
    h.expect_clean(
        "a duplicated attribute whose first value is honest still passes",
        document(figure()).replace(
            ' fill="#2d3142"/>', ' d="M 0 0 Z" fill="#2d3142"/>', 1),
    )

    # ── The fixture-isolation fix, held in place ──────────────────────────
    sentinel = ROOT / "example-streamgraph-fixture.html"
    existed = sentinel.exists()
    if not existed:
        sentinel.write_text("KEEP ME\n", encoding="utf-8")
    try:
        h.run(document(figure()))
        h.run(document(figure()), name="example-streamgraph-fixture.html")
        h.check(
            "a pre-existing file sharing a fixture name is never touched",
            sentinel.exists() and sentinel.read_text(encoding="utf-8") == "KEEP ME\n",
            "%s was overwritten or deleted by the harness" % sentinel,
        )
    finally:
        if not existed and sentinel.exists():
            sentinel.unlink()

    other = Harness()
    try:
        h.check(
            "two harnesses use different directories, so parallel runs cannot collide",
            other.dir != h.dir and not str(other.dir).startswith(str(ROOT)),
            "dirs %s and %s" % (h.dir, other.dir),
        )
    finally:
        other.close()

    h.check(
        "fixtures are written outside the repository",
        not str(h.dir).startswith(str(ROOT)),
        "fixture dir %s is inside %s" % (h.dir, ROOT),
    )

    print()
    if h.failures:
        print("%d of %d case(s) failed." % (h.failures, h.count))
        return 1
    print("OK streamgraph checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
