#!/usr/bin/env python3
"""Adversarial cases for verify-slopegraph.py, both polarities.

Every case is named for exactly what it asserts. A case called "unlabelled
sliver does not disable the check" once proved only that the *labelled* elements
stayed checked, which made a real gap look covered for days - so a name here
that overclaims is itself a defect.

The negative half matters as much as the positive: a checker that fires on an
honest indexed slopegraph, or on the other shipped example types, gets widened
or switched off, and then it guards nothing.

Exit: 0 all pass, 1 any failure.
"""

from __future__ import annotations

import re
import sys
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


def labels(name: str, frm: float, to: float,
           shown_from=None, shown_to=None, skip: str = "") -> str:
    out = ""
    if skip != "from":
        text = frm if shown_from is None else shown_from
        out += ('  <text data-series="%s" data-end="from" x="304" y="%g">%s</text>\n'
                % (name, y(frm) + 3.5, text))
    if skip != "to":
        text = to if shown_to is None else shown_to
        out += ('  <text data-series="%s" data-end="to" x="696" y="%g">%s</text>\n'
                % (name, y(to) + 3.5, text))
    return out


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


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
        self.tmp = ROOT / ".slopegraph-fixture.html"

    def run(self, source: str, name: str = "example-slopegraph-fixture.html") -> list:
        path = self.tmp.with_name(name)
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
        path = self.tmp.with_name(name)
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


def main() -> int:
    h = Harness()

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
        honest([("Search", 512, 208), ("Mirror", 512, 208),
                ("Auth", 154, 121)]),
    )

    # An indexed slopegraph has no fittable left axis. Legitimate, and the
    # fallback must verify it against the axis that can be fitted.
    h.expect_clean(
        "a correct indexed slopegraph (every series starts at the index base) "
        "is not rejected",
        honest([("api", 100, 143), ("web", 100, 118), ("worker", 100, 196)]),
    )

    # The other half of that name, which used to be assumed. A whole-set fit
    # called this file clean: with three points and one 3px error, Theil-Sen
    # has no outlier budget and the contaminated slope passed within 1px of
    # every point. Leave-one-out is what reports it.
    indexed_lie = (series("api", 100, 118) + labels("api", 100, 118)
                   + series("web", 100, 143) + labels("web", 100, 143)
                   + series("worker", 100, 196, y2=y(196) + 3)
                   + labels("worker", 100, 196))
    h.expect_finding(
        "an indexed slopegraph with one endpoint 3px wrong is reported",
        document(indexed_lie), r"'worker' draws its to endpoint",
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
    # pulled apart so their labels clear each other. Five series, as the draft
    # had - a robust fit needs more than the two usable pairs a three-series
    # axis with a coincident pair leaves it.
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

    # 2. Dual scale — the right axis rescaled.
    dual = ""
    for name, frm, to in ROWS:
        dual += series(name, frm, to, y2=round(420 - (420 - y(to)) * 0.8, 1)) \
            + labels(name, frm, to)
    h.expect_only_one(
        "a right axis compressed to 80% reports as a scale mismatch and stops there",
        document(dual), r"the two axes are not on the same scale",
    )

    # 3. Shared slope, shifted origin. Slope-only checking passes this.
    shifted = ""
    for name, frm, to in ROWS:
        shifted += series(name, frm, to, y2=y(to) - 12) + labels(name, frm, to)
    h.expect_only_one(
        "a right axis shifted 12px at an identical slope reports as an origin offset",
        document(shifted), r"share a scale but not an origin",
    )

    # 4. Label disagrees with the geometry it is drawn from.
    h.expect_finding(
        "a printed value that contradicts the declared one is reported",
        document(series("Search", 512, 208) + labels("Search", 512, 208, shown_to="180")
                 + series("Auth", 154, 121) + labels("Auth", 154, 121)
                 + series("Recommender", 238, 431) + labels("Recommender", 238, 431)),
        r"'Search' prints '180' at its to endpoint but declares 208",
    )

    # 5. An endpoint with no printed value at all.
    h.expect_finding(
        "a series missing one endpoint label is reported",
        document(series("Search", 512, 208) + labels("Search", 512, 208, skip="to")
                 + series("Auth", 154, 121) + labels("Auth", 154, 121)
                 + series("Recommender", 238, 431) + labels("Recommender", 238, 431)),
        r"'Search' prints no to endpoint value",
    )

    # 6. Fail closed: presents as a slopegraph, declares nothing checkable.
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

    # 7. A series line that cannot be read must be reported, never skipped.
    for omitted in ("data-from", "data-to", "y1", "y2"):
        h.expect_finding(
            "a series line missing %s is reported rather than dropped" % omitted,
            document(series("Search", 512, 208, omit=omitted)
                     + labels("Search", 512, 208)
                     + series("Auth", 154, 121) + labels("Auth", 154, 121)
                     + series("Recommender", 238, 431) + labels("Recommender", 238, 431)),
            r"missing %s" % omitted,
        )

    h.expect_finding(
        "a declared value that is not a finite number is reported rather than "
        "dropped",
        document('  <line data-series="Search" data-from="half a second" data-to="208" '
                 'x1="320" y1="72.1" x2="680" y2="328.8" stroke="#2d3142"/>\n'
                 + series("Auth", 154, 121) + labels("Auth", 154, 121)
                 + series("Recommender", 238, 431) + labels("Recommender", 238, 431)),
        r"not a finite number",
    )

    # 8. Quote style. The attribute parser once matched only double quotes, so a
    #    single-quoted series line tripped the slopegraph DETECTOR (which is
    #    quote-agnostic) and then vanished from the parsed set - a file carrying a
    #    400px lie reported clean. Both polarities, because the fix has to parse
    #    the legal markup, not merely refuse it.
    single_honest = ""
    for name, frm, to in ROWS:
        single_honest += (
            "  <line data-series='%s' data-from='%s' data-to='%s' "
            "x1='320' y1='%g' x2='680' y2='%g' stroke='#2d3142'/>\n"
            % (name, frm, to, y(frm), y(to))
        ) + labels(name, frm, to)
    h.expect_clean(
        "an honest slopegraph written with single-quoted attributes is parsed, not "
        "skipped", document(single_honest),
    )

    single_lie = ""
    for name, frm, to in ROWS:
        bad = 3.0 if name == "Search" else 0.0
        single_lie += (
            "  <line data-series='%s' data-from='%s' data-to='%s' "
            "x1='320' y1='%g' x2='680' y2='%g' stroke='#2d3142'/>\n"
            % (name, frm, to, y(frm), y(to) - bad)
        ) + labels(name, frm, to)
    h.expect_finding(
        "a single-quoted series line with a nudged endpoint is reported",
        document(single_lie), r"'Search' draws its to endpoint",
    )

    # And the fail-closed net behind the parser: markup that declares a series
    # but cannot be read at all must be reported, never skipped.
    h.expect_finding(
        "a <line> declaring data-series whose attributes cannot be parsed is "
        "reported, not skipped",
        document(honest_rows_block()
                 + "  <line data-series=unquoted data-from=1 data-to=2 "
                   "x1=320 y1=40 x2=680 y2=420 stroke='#2d3142'/>\n"),
        r"declares data-series but its attributes could not be parsed",
    )

    # The same net must stay silent on scenery. An axis rule and a legend swatch
    # are <line> elements with no data-series, and skipping them is correct.
    h.expect_clean(
        "axis rules and legend swatches without data-series are skipped silently",
        document(honest_rows_block()
                 + '  <line x1="320" y1="40" x2="320" y2="420" stroke="#2d3142"/>\n'
                   '  <line x1="40" y1="492" x2="64" y2="492" stroke="#eb6c36"/>\n'),
    )

    # 9. Both axis positions, not just one. A series drawn to its own right-hand
    #    x is a different chart superimposed on this one.
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

    # 9. Degenerate: no axis has two distinct values, so nothing is verifiable.
    h.expect_finding(
        "a figure where every series holds one value on each axis is reported "
        "as unverifiable",
        honest([("api", 100, 120), ("web", 100, 120)]),
        r"neither axis has two distinct values",
    )


    # ── The nine fixes the adversarial review produced ────────────────────

    # NaN parses as a float and then satisfies every `> tolerance` comparison,
    # so a figure made entirely of NaN reported clean.
    h.expect_finding(
        "a NaN coordinate is reported, not silently accepted",
        document('  <line data-series="a" data-from="nan" data-to="nan" x1="320" '
                 'y1="nan" x2="680" y2="nan" stroke="#2d3142"/>\n'
                 + honest_rows_block()),
        r"not a finite number",
    )

    # Markup inside a comment is not rendered, so reading it as data reports a
    # commented-out old draft as a live defect.
    h.expect_clean(
        "a commented-out series line is ignored, not read as data",
        document(honest_rows_block()
                 + '  <!-- old draft: <line data-series="ghost" data-from="999" '
                   'data-to="1" x1="320" y1="10" x2="680" y2="410"/> -->\n'),
    )

    # Two labels for one endpoint used to overwrite each other, so a figure could
    # print two contradictory numbers for one point and be judged on the last.
    h.expect_finding(
        "a second label for the same endpoint is reported",
        document(honest_rows_block()
                 + '  <text data-series="Search" data-end="from" x="304" y="80">999'
                   '</text>\n'),
        r"a second from label for series 'Search'",
    )

    # A label naming a series no line declares is data with no mark.
    h.expect_finding(
        "an endpoint label for a series with no line is reported",
        document(honest_rows_block()
                 + '  <text data-series="Ghost" data-end="from" x="304" y="80">300'
                   '</text>\n'),
        r"names series 'Ghost', which no line declares",
    )

    # NUMBER_RE read "1e3" as 1 and reported an honest label as contradicting its
    # own metadata.
    h.expect_clean(
        "scientific-notation labels are parsed, not truncated to the mantissa",
        honest([("a", 1e3, 2e3), ("b", 2e3, 1e3), ("c", 1.5e3, 1.8e3),
                ("d", 1.2e3, 1.1e3)]),
    )

    # Raw intercepts are the predicted y at value zero, so on values in the
    # billions two axes sharing one transform disagreed through float
    # cancellation alone and an honest figure was reported as shifted.
    base = 1000000000
    h.expect_clean(
        "a shared scale on billion-magnitude values is not reported as shifted",
        honest([(n, base + f, base + t) for n, f, t in ROWS]),
    )

    # A slopegraph whose only declaration sits past 4000 characters used to go
    # undetected, which turned invariant 4 into a pass.
    h.expect_finding(
        "a slopegraph declared only in a desc past 4000 chars is still detected",
        "<!doctype html><style>/*" + ("x" * 4200) + "*/</style>"
        + '<svg role="img"><title>t</title>'
        + "<desc>Slopegraph of latency with no declared series.</desc>"
        + '<line x1="1" y1="1" x2="2" y2="2"/></svg>',
        r"presents as a slopegraph but declares 0 verifiable series",
        name="figure.html",
    )

    print()
    if h.failures:
        print("%d of %d case(s) failed." % (h.failures, h.count))
        return 1
    print("OK slopegraph checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
