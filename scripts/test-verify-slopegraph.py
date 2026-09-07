#!/usr/bin/env python3
"""Adversarial cases for verify-slopegraph.py, both polarities.

Every case is named for exactly what it asserts. A case called "unlabelled
sliver does not disable the check" once proved only that the *labelled* elements
stayed checked, which made a real gap look covered for days - so a name here
that overclaims is itself a defect.

The negative half matters as much as the positive: a checker that fires on an
honest indexed slopegraph, or on the other shipped example types, gets widened
or switched off, and then it guards nothing.

Fixtures live in a per-process temporary directory. They used to be written to
fixed paths under the repository root and unconditionally unlinked, which would
overwrite and then delete a real file that happened to share a fixture name, and
raced when two runs overlapped. Two cases at the end hold that fix in place.

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

verify = __import__("verify-slopegraph")

SHIPPED = ROOT / "skills/diagram-design/assets/example-slopegraph.html"

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="slopegraph-title slopegraph-desc">
  <title id="slopegraph-title">t</title>
  <desc id="slopegraph-desc">Slopegraph fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

# The bound state captions every slopegraph must carry.
CAPTIONS = (
    '  <text data-axis="from" data-state="BEFORE" x="320" y="440">BEFORE</text>\n'
    '  <text data-axis="to" data-state="AFTER" x="680" y="440">AFTER</text>\n'
)

# y = 420 - (v - 100) * 380/450, the shared scale the shipped example uses:
# p95 milliseconds over a 100-550 domain.
PX = 380.0 / 450.0


def y(value: float) -> float:
    return round(420 - (value - 100) * PX, 1)


def series(name: str, frm: float, to: float, y1=None, y2=None,
           x1: float = 320, x2: float = 680, omit: str = "") -> str:
    parts = ['data-series="%s"' % name]
    if omit != "data-from":
        parts.append('data-from="%s"' % frm)
    if omit != "data-to":
        parts.append('data-to="%s"' % to)
    parts.append('x1="%g"' % x1)
    if omit != "y1":
        parts.append('y1="%g"' % (y(frm) if y1 is None else y1))
    parts.append('x2="%g"' % x2)
    if omit != "y2":
        parts.append('y2="%g"' % (y(to) if y2 is None else y2))
    return "  <line %s stroke=\"#2d3142\" stroke-width=\"1.2\"/>\n" % " ".join(parts)


def labels(name: str, frm: float, to: float, shown_from=None, shown_to=None,
           skip: str = "", skip_name: str = "", y_from=None, y_to=None) -> str:
    """The value and name label pair for each end of one series.

    y_from / y_to place the labels independently of the value scale, so a
    fixture that moves the geometry can move its labels with it. A fixture
    whose labels stay behind reports a real row defect that has nothing to do
    with what the case is testing.
    """
    out = ""
    for end, value, shown, row in (("from", frm, shown_from, y_from),
                                   ("to", to, shown_to, y_to)):
        if skip == end:
            continue
        text = value if shown is None else shown
        baseline = (y(value) if row is None else row) + 3.5
        out += ('  <text data-series="%s" data-end="%s" x="%d" y="%g">%s</text>\n'
                % (name, end, 304 if end == "from" else 696, baseline, text))
        if skip_name != end:
            out += ('  <text data-series="%s" data-end="%s" data-role="name" '
                    'x="%d" y="%g">%s</text>\n'
                    % (name, end, 272 if end == "from" else 728, baseline, name))
    return out


def document(*blocks: str) -> str:
    return HEAD + CAPTIONS + "".join(blocks) + TAIL


def honest(rows) -> str:
    return document(honest_rows_block(rows))


def honest_rows_block(rows=None) -> str:
    """The series+labels block for a correct figure, without the wrapper."""
    body = ""
    for name, frm, to in (ROWS if rows is None else rows):
        body += series(name, frm, to) + labels(name, frm, to)
    return body


ROWS = [("Search", 512, 208), ("Catalog", 376, 164), ("Checkout", 291, 143),
        ("Auth", 154, 121), ("Recommender", 238, 431)]


class Harness:
    def __init__(self) -> None:
        self.failures = 0
        self.count = 0
        # A private temp dir per instance: fixture names are meaningful to the
        # checker (it keys detection off the filename) but their directory is
        # not, so there is no reason to put them anywhere a real file lives.
        self.dir = Path(tempfile.mkdtemp(prefix="slopegraph-fixtures-"))

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-slopegraph-fixture.html") -> list:
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            return verify.check(path)
        finally:
            path.unlink()

    def expect_clean(self, label: str, source: str, name: str | None = None) -> None:
        self.count += 1
        found = self.run(source, name) if name else self.run(source)
        if found:
            self.failures += 1
            print("FAIL  %s" % label)
            for item in found:
                print("        unexpected: %s" % item)
        else:
            print("ok    %s" % label)

    def expect_finding(self, label: str, source: str, pattern: str,
                       name: str | None = None) -> None:
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

    def expect_only_one(self, label: str, source: str, pattern: str) -> None:
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

    def expect_out_of_scope(self, label: str, source: str, name: str) -> None:
        """Not merely finding-free - genuinely outside this checker's scope.

        expect_clean cannot tell the two apart, so four cases named "out of
        scope" were only ever proving "no findings", which a detected-and-clean
        file also satisfies.
        """
        self.count += 1
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            detected = verify.looks_like_slopegraph(path, source)
            found = verify.check(path)
        finally:
            path.unlink()
        if detected or found:
            self.failures += 1
            print("FAIL  %s\n        detected=%s findings=%d"
                  % (label, detected, len(found)))
            return
        print("ok    %s" % label)

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        self.count += 1
        if condition:
            print("ok    %s" % label)
            return
        self.failures += 1
        print("FAIL  %s%s" % (label, ("\n        " + detail) if detail else ""))


def main() -> int:
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


def run_cases(h: Harness) -> int:
    # ── Negative half: honest figures must stay silent ────────────────────
    h.expect_clean("an honest slopegraph reports nothing", honest(ROWS))

    h.expect_clean(
        "the shipped light example reports nothing",
        SHIPPED.read_text(encoding="utf-8"), name="example-slopegraph.html",
    )

    # Two series holding identical values must land on identical y. This is the
    # case the draft got wrong, and the honest rendering of it must pass.
    h.expect_clean(
        "two series with identical values drawn at identical y is legal",
        honest([("Search", 512, 208), ("Mirror", 512, 208), ("Auth", 154, 121)]),
    )

    h.expect_clean(
        "a correct indexed slopegraph (every series starts at the index base) "
        "is not rejected",
        honest([("api", 100, 143), ("web", 100, 118), ("worker", 100, 196)]),
    )

    # Coordinates ship rounded to 0.1px, and an author may reasonably round to
    # whole pixels instead. Neither may read as a defect.
    for label, quantum in (("one decimal", 1), ("whole pixels", 0)):
        rounded = ""
        for name, frm, to in ROWS:
            rounded += series(name, frm, to, y1=round(y(frm), quantum),
                              y2=round(y(to), quantum)) + labels(name, frm, to)
        h.expect_clean("coordinates rounded to %s stay within tolerance" % label,
                       document(rounded))

    # The rotated value-axis caption carries a transform and must not be caught:
    # it is not verified geometry and not a bound label.
    h.expect_clean(
        "the rotated value-axis caption's transform is not reported",
        document('  <text transform="rotate(-90 24 230)" x="24" y="230">'
                 "P95 RESPONSE TIME, MS</text>\n" + honest_rows_block()),
    )

    # `text-transform` is not `transform`.
    h.expect_clean(
        "a CSS text-transform declaration is not read as a transform",
        HEAD + "<style>.eyebrow { text-transform: uppercase; }</style>\n"
        + CAPTIONS + honest_rows_block() + TAIL,
    )

    # The detector must not drag the other example types into scope.
    for other in ("example-line.html", "example-bar.html", "example-treemap.html",
                  "example-scatter.html"):
        path = ROOT / "skills/diagram-design/assets" / other
        if path.exists():
            h.expect_out_of_scope(
                "%s is not detected as a slopegraph at all" % other,
                path.read_text(encoding="utf-8"), other)

    # ── Positive half: each lie must be named as itself ───────────────────

    # 1. Jitter. One point moved to free up label space.
    jittered = ""
    for name, frm, to in ROWS:
        shift = 3.0 if name == "Search" else 0.0
        jittered += series(name, frm, to, y2=y(to) - shift) + labels(name, frm, to)
    h.expect_only_one(
        "a single endpoint nudged 3px reports as one point, not as a bad axis",
        document(jittered), r"'Search' draws its to endpoint.*off by 3\.0 px",
    )

    # The specific shape of the draft's bug: two series at identical values
    # pulled apart so their labels clear each other.
    collided = ""
    for name, frm, to in [("Search", 512, 208), ("Mirror", 512, 208),
                          ("Catalog", 376, 164), ("Checkout", 291, 143),
                          ("Auth", 154, 121)]:
        if name == "Search":
            collided += series(name, frm, to, y1=y(frm) - 3, y2=y(to) - 3)
        else:
            collided += series(name, frm, to)
        collided += labels(name, frm, to)
    h.expect_finding(
        "an equal-valued series pulled 3px clear of its twin's labels is reported",
        document(collided), r"'Search' draws its (from|to) endpoint",
    )

    # An indexed slopegraph with one endpoint wrong. A whole-set fit called this
    # clean: with three points and one 3px error Theil-Sen has no outlier budget,
    # and the contaminated slope passed within 1px of every point.
    indexed_lie = (series("api", 100, 118) + labels("api", 100, 118)
                   + series("web", 100, 143) + labels("web", 100, 143)
                   + series("worker", 100, 196, y2=y(196) + 3)
                   + labels("worker", 100, 196))
    h.expect_finding(
        "an indexed slopegraph with one endpoint 3px wrong is reported",
        document(indexed_lie), r"'worker' draws its to endpoint",
    )

    # 2. Dual scale, and a shared scale with a shifted origin.
    dual = ""
    for name, frm, to in ROWS:
        dual += series(name, frm, to, y2=round(420 - (420 - y(to)) * 0.8, 1)) \
            + labels(name, frm, to)
    h.expect_only_one(
        "a right axis compressed to 80% reports as a scale mismatch and stops there",
        document(dual), r"the two axes are not on the same scale",
    )

    shifted = ""
    for name, frm, to in ROWS:
        shifted += (series(name, frm, to, y2=y(to) - 12)
                    + labels(name, frm, to, y_to=y(to) - 12))
    h.expect_only_one(
        "a right axis shifted 12px at an identical slope reports as an origin offset",
        document(shifted), r"share a scale but not an origin",
    )

    # 3. Transforms move the rendered mark away from the checked coordinates.
    h.expect_finding(
        "a transform on a series line is reported",
        document(series("Search", 512, 208).replace(
            "  <line ", '  <line transform="translate(0 80)" ', 1)
            + labels("Search", 512, 208)
            + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"series 'Search' carries transform",
    )

    h.expect_finding(
        "a transform on a bound label is reported",
        document(honest_rows_block().replace(
            '  <text data-series="Search" data-end="from"',
            '  <text transform="translate(0 40)" data-series="Search" data-end="from"',
            1)),
        r"bound label.*carries transform",
    )

    h.expect_finding(
        "an ancestor <g> transform over the series is reported",
        document('  <g transform="translate(0 60)">\n' + honest_rows_block()
                 + "  </g>\n"),
        r"carries an ancestor <g>/<svg> transform",
    )

    h.expect_finding(
        "a CSS transform declaration is reported",
        HEAD + "<style>line { transform: translateY(40px); }</style>\n"
        + CAPTIONS + honest_rows_block() + TAIL,
        r"a CSS `transform` declaration",
    )

    # 4. The printed value must be one complete token that matches metadata.
    h.expect_finding(
        "a printed value that contradicts the declared one is reported",
        document(series("Search", 512, 208)
                 + labels("Search", 512, 208, shown_to="180")
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"'Search' prints '180' at its to endpoint but declares 208",
    )

    h.expect_finding(
        "a thousands separator that changes the value is reported",
        document(series("Search", 512, 208)
                 + labels("Search", 512, 208, shown_from="512,000")
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"prints '512,000' at its from endpoint but declares 512",
    )

    h.expect_finding(
        "a label carrying two numeric tokens is reported, not half-read",
        document(series("Search", 512, 208)
                 + labels("Search", 512, 208, shown_from="512 was 600")
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"prints more than one numeric token",
    )

    h.expect_clean(
        "a unit suffix on a printed value is accepted",
        document("".join(series(n, f, t)
                         + labels(n, f, t, shown_from="%dms" % f,
                                  shown_to="%dms" % t)
                         for n, f, t in ROWS)),
    )

    h.expect_finding(
        "a series missing one endpoint value label is reported",
        document(series("Search", 512, 208)
                 + labels("Search", 512, 208, skip="to")
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"'Search' prints no to endpoint value",
    )

    # 5. Captions and names must be bound to what they describe.
    swapped_text = document(honest_rows_block()).replace(
        ">BEFORE</text>", ">@@T@@</text>", 1).replace(
        ">AFTER</text>", ">BEFORE</text>", 1).replace(
        ">@@T@@</text>", ">AFTER</text>", 1)
    h.expect_finding(
        "swapping only the visible caption text is reported",
        swapped_text, r"state caption reads 'AFTER' but declares data-state='BEFORE'",
    )

    swapped_x = document(honest_rows_block()).replace(
        'data-state="BEFORE" x="320"', 'data-state="BEFORE" x="@@"', 1).replace(
        'data-state="AFTER" x="680"', 'data-state="AFTER" x="320"', 1).replace(
        'x="@@"', 'x="680"', 1)
    h.expect_finding(
        "swapping the caption x values is reported",
        swapped_x, r"state caption \('BEFORE'\) is drawn at x=680",
    )

    h.expect_finding(
        "a caption with no data-state is reported",
        document(honest_rows_block()).replace(' data-state="BEFORE"', "", 1),
        r"has no data-state",
    )

    h.expect_finding(
        "a missing state caption is reported",
        HEAD + '  <text data-axis="from" data-state="BEFORE" x="320" y="440">'
        "BEFORE</text>\n" + honest_rows_block() + TAIL,
        r"no 'to' state caption",
    )

    h.expect_finding(
        "two captions reading the same thing is reported",
        document(honest_rows_block()).replace(
            'data-state="AFTER" x="680" y="440">AFTER<',
            'data-state="BEFORE" x="680" y="440">BEFORE<', 1),
        r"both state captions read 'BEFORE'",
    )

    h.expect_finding(
        "two series names swapped between rows is reported",
        document(honest_rows_block()).replace(
            'data-role="name" x="272" y="%g">Search<' % (y(512) + 3.5),
            'data-role="name" x="272" y="%g">Catalog<' % (y(512) + 3.5), 1),
        r"name label bound to series 'Search' reads 'Catalog'",
    )

    h.expect_finding(
        "a name label drawn on another series' row is reported",
        document(honest_rows_block()).replace(
            'data-series="Auth" data-end="from" data-role="name" x="272" y="%g"'
            % (y(154) + 3.5),
            'data-series="Auth" data-end="from" data-role="name" x="272" y="%g"'
            % (y(512) + 3.5), 1),
        r"name label for series 'Auth' is drawn at y=.*nearer 'Search'",
    )

    h.expect_finding(
        "a series with no name label is reported",
        document(series("Search", 512, 208)
                 + labels("Search", 512, 208, skip_name="from")
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"'Search' has no from name label",
    )

    h.expect_finding(
        "a second label for the same endpoint is reported",
        document(honest_rows_block()
                 + '  <text data-series="Search" data-end="from" x="304" y="80">999'
                   "</text>\n"),
        r"a second from value label for series 'Search'",
    )

    h.expect_finding(
        "an endpoint label for a series with no line is reported",
        document(honest_rows_block()
                 + '  <text data-series="Ghost" data-end="from" x="304" y="80">300'
                   "</text>\n"),
        r"names series 'Ghost', which no line declares",
    )

    # 6. Fail closed, and read what is actually there.
    h.expect_finding(
        "a file named example-slopegraph with no series is reported, not passed",
        document('  <line x1="320" y1="40" x2="320" y2="420" stroke="#2d3142"/>\n'),
        r"presents as a slopegraph but declares 0 verifiable series",
        name="example-slopegraph-empty.html",
    )

    h.expect_finding(
        "a file whose desc says slopegraph but declares no series is reported",
        document('  <line x1="320" y1="40" x2="320" y2="420" stroke="#2d3142"/>\n'),
        r"presents as a slopegraph but declares 0 verifiable series",
        name="figure.html",
    )

    h.expect_finding(
        "a slopegraph declared only in a desc past 4000 chars is still detected",
        "<!doctype html><style>/*" + ("x" * 4200) + "*/</style>"
        + '<svg role="img"><title>t</title>'
        + "<desc>Slopegraph of latency with no declared series.</desc>"
        + '<line x1="1" y1="1" x2="2" y2="2"/></svg>',
        r"presents as a slopegraph but declares 0 verifiable series",
        name="figure.html",
    )

    for omitted in ("data-from", "data-to", "y1", "y2"):
        h.expect_finding(
            "a series line missing %s is reported rather than dropped" % omitted,
            document(series("Search", 512, 208, omit=omitted)
                     + labels("Search", 512, 208)
                     + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
            r"missing %s" % omitted,
        )

    h.expect_finding(
        "a declared value that is not a finite number is reported rather than dropped",
        document('  <line data-series="Search" data-from="half a second" '
                 'data-to="208" x1="320" y1="72.1" x2="680" y2="328.8" '
                 'stroke="#2d3142"/>\n'
                 + honest_rows_block([r for r in ROWS if r[0] != "Search"])),
        r"not a finite number",
    )

    h.expect_finding(
        "a NaN coordinate is reported, not silently accepted",
        document('  <line data-series="a" data-from="nan" data-to="nan" x1="320" '
                 'y1="nan" x2="680" y2="nan" stroke="#2d3142"/>\n'
                 + honest_rows_block()),
        r"not a finite number",
    )

    h.expect_clean(
        "a commented-out series line is ignored, not read as data",
        document(honest_rows_block()
                 + '  <!-- old draft: <line data-series="ghost" data-from="999" '
                   'data-to="1" x1="320" y1="10" x2="680" y2="410"/> -->\n'),
    )

    h.expect_clean(
        "an honest slopegraph written with single-quoted attributes is parsed",
        HEAD + CAPTIONS + "".join(
            "  <line data-series='%s' data-from='%s' data-to='%s' x1='320' "
            "y1='%g' x2='680' y2='%g' stroke='#2d3142'/>\n"
            % (n, f, t, y(f), y(t)) + labels(n, f, t) for n, f, t in ROWS) + TAIL,
    )

    h.expect_finding(
        "a single-quoted series line with a nudged endpoint is reported",
        HEAD + CAPTIONS + "".join(
            "  <line data-series='%s' data-from='%s' data-to='%s' x1='320' "
            "y1='%g' x2='680' y2='%g' stroke='#2d3142'/>\n"
            % (n, f, t, y(f), y(t) - (3.0 if n == "Search" else 0.0))
            + labels(n, f, t) for n, f, t in ROWS) + TAIL,
        r"'Search' draws its to endpoint",
    )

    h.expect_finding(
        "a <line> declaring data-series whose attributes cannot be parsed is reported",
        document(honest_rows_block()
                 + "  <line data-series=unquoted data-from=1 data-to=2 "
                   "x1=320 y1=40 x2=680 y2=420 stroke='#2d3142'/>\n"),
        r"declares data-series but its attributes could not be parsed",
    )

    h.expect_clean(
        "axis rules and legend swatches without data-series are skipped silently",
        document(honest_rows_block()
                 + '  <line x1="320" y1="40" x2="320" y2="420" stroke="#2d3142"/>\n'
                   '  <line x1="40" y1="492" x2="64" y2="492" stroke="#eb6c36"/>\n'),
    )

    for label in ("left", "right"):
        rows = ""
        for name, frm, to in ROWS:
            stray = name == "Search"
            rows += series(
                name, frm, to,
                x1=300 if (stray and label == "left") else 320,
                x2=640 if (stray and label == "right") else 680,
            ) + labels(name, frm, to)
        h.expect_finding(
            "a series that does not share the %s axis position is reported" % label,
            document(rows), r"series do not share one x[12]",
        )

    h.expect_finding(
        "a figure where every series holds one value on each axis is reported "
        "as unverifiable",
        honest([("api", 100, 120), ("web", 100, 120)]),
        r"neither axis has two distinct values",
    )

    sci = ""
    for n, f, t in (("a", 512, 208), ("b", 376, 164), ("c", 291, 143),
                    ("d", 154, 121)):
        sci += (series(n, "%ge0" % f, "%ge0" % t, y1=y(f), y2=y(t))
                + labels(n, f, t, shown_from="%ge0" % f, shown_to="%ge0" % t))
    h.expect_clean(
        "scientific-notation labels are parsed, not truncated to the mantissa",
        document(sci),
    )

    # Real geometry, values offset by a billion: the two axes share one
    # transform, and only an intercept compared at value zero would call them
    # shifted. Mapping the raw billions through the fixture scale instead put
    # every point at y = -8.4e8, where the fit is degenerate and the case
    # passed without testing anything.
    base = 1000000000
    billions = ""
    for n, f, t in ROWS:
        billions += (series(n, base + f, base + t, y1=y(f), y2=y(t))
                     + labels(n, base + f, base + t, y_from=y(f), y_to=y(t)))
    h.expect_clean(
        "a shared scale on billion-magnitude values is not reported as shifted",
        document(billions),
    )

    # ── The fixture-isolation fix, held in place ──────────────────────────
    sentinel = ROOT / "example-slopegraph-fixture.html"
    existed = sentinel.exists()
    if not existed:
        sentinel.write_text("KEEP ME\n", encoding="utf-8")
    try:
        h.run(honest(ROWS))
        h.run(honest(ROWS), name="example-slopegraph-fixture.html")
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
    print("OK slopegraph checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
