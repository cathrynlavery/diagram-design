#!/usr/bin/env python3
"""Adversarial cases for verify-box-plot.py, both polarities.

Every case is named for exactly what it asserts. The negative half matters
as much as the positive: a checker that fires on an honest figure, on the
parent scatter, or on a sibling contract's files gets widened or switched
off, and then it guards nothing.

The scope treaty is pinned here in both directions: fixtures prove that
`data-value` on a <circle> (the beeswarm contract) never claims a file for
this checker, and every sibling per-file verifier present on the branch is
run as a subprocess against the shipped box-plot examples and must skip
all three.

Fixtures live in a per-process temporary directory, never under the
repository root.

Exit: 0 all pass, 1 any failure.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

verify = __import__("verify-box-plot")

ASSETS = ROOT / "skills/diagram-design/assets"
SHIPPED = [ASSETS / name for name in (
    "example-box-plot.html", "example-box-plot-dark.html",
    "example-box-plot-full.html",
)]

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="box-plot-title box-plot-desc">
  <title id="box-plot-title">t</title>
  <desc id="box-plot-desc">Box plot fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

INK = "rgba(45,49,66,0.15)"
STROKE = "#4f5d75"
ACCENT_FILL = "rgba(191,69,32,0.12)"
ACCENT_STROKE = "#bf4520"


def x(value: float) -> float:
    return 160 + 2 * value


def series(name, q1, q2, q3, wlo, whi, cy, *, focal=False, outliers=(),
           q1_x=None, q3_x=None, q2_x=None, wlo_x=None, whi_x=None,
           omit=None, extra="", outlier_x=None, outlier_inside=False,
           label=None, label_y=None, median_x2=None, box_fill=None):
    omit = omit or set()
    box_x = x(q1) if q1_x is None else q1_x
    box_r = x(q3) if q3_x is None else q3_x
    med = x(q2) if q2_x is None else q2_x
    lo = x(wlo) if wlo_x is None else wlo_x
    hi = x(whi) if whi_x is None else whi_x
    fill, stroke = (ACCENT_FILL, ACCENT_STROKE) if focal else (INK, STROKE)
    if box_fill is not None:
        fill = box_fill
    y = cy - 16
    attrs = []
    if "name" not in omit:
        attrs.append('data-name="%s"' % name)
    if "q1" not in omit:
        attrs.append('data-q1="%s"' % q1)
    if "q2" not in omit:
        attrs.append('data-q2="%s"' % q2)
    if "q3" not in omit:
        attrs.append('data-q3="%s"' % q3)
    if "wlo" not in omit:
        attrs.append('data-wlo="%s"' % wlo)
    if "whi" not in omit:
        attrs.append('data-whi="%s"' % whi)
    body = []
    if "whisker-lo" not in omit:
        body.append(
            '    <line data-role="whisker-lo" x1="%g" y1="%g" x2="%g" y2="%g" '
            'stroke="rgba(45,49,66,0.55)" stroke-width="1"/>'
            % (lo, cy, box_x, cy)
        )
    if "whisker-hi" not in omit:
        body.append(
            '    <line data-role="whisker-hi" x1="%g" y1="%g" x2="%g" y2="%g" '
            'stroke="rgba(45,49,66,0.55)" stroke-width="1"/>'
            % (box_r, cy, hi, cy)
        )
    if "box" not in omit:
        body.append(
            '    <rect data-role="box" x="%g" y="%g" width="%g" height="32" '
            'fill="%s" stroke="%s" stroke-width="1"/>'
            % (box_x, y, box_r - box_x, fill, stroke)
        )
    if "median" not in omit:
        body.append(
            '    <line data-role="median" x1="%g" y1="%g" x2="%g" y2="%g" '
            'stroke="#2d3142" stroke-width="1.5"/>'
            % (med, y, med if median_x2 is None else median_x2, y + 32)
        )
    for ov in outliers:
        ox = x(ov) if outlier_x is None else outlier_x
        if outlier_inside:
            ox = med
        body.append(
            '    <circle data-outlier="%s" data-x="%s" cx="%g" cy="%g" r="4" '
            'fill="rgba(45,49,66,0.55)" stroke="#4f5d75"/>'
            % (name, ov, ox, cy)
        )
    if "label" not in omit:
        body.append(
            '    <text data-name="%s" x="148" y="%g" text-anchor="end">%s</text>'
            % (name, cy + 4 if label_y is None else label_y,
               name if label is None else label)
        )
    return '  <g %s%s>\n%s\n  </g>\n' % (
        " ".join(attrs), (" " + extra) if extra else "", "\n".join(body)
    )


def tick(value, position=None, shown=None, declared=None, axis="x", extra=""):
    if position is None:
        position = x(value)
    bind = "" if declared == "omit" else \
        ' data-value="%s"' % (value if declared is None else declared)
    return (
        '  <text data-tick="%s"%s x="%g" y="440"%s>%s</text>\n'
        % (axis, bind, position, (" " + extra) if extra else "",
           ("%g" % value) if shown is None else shown)
    )


TICKS = tick(0) + tick(200) + tick(400)


def honest(*extra: str) -> str:
    return document(
        series("A", 20, 30, 40, 10, 50, 80),
        series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,)),
        series("C", 15, 22, 28, 8, 40, 240),
        TICKS,
        *extra,
    )


def prepend_style(css: str) -> str:
    return honest().replace("<svg ", "<style>%s</style>\n<svg " % css, 1)


A_LABEL = '<text data-name="A" x="148" y="84" text-anchor="end">A</text>'
A_BOX = 'data-role="box" x="200"'


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


class Harness:
    def __init__(self):
        self.failures = 0
        self.count = 0
        self.dir = Path(tempfile.mkdtemp(prefix="box-plot-fixtures-"))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-box-plot-fixture.html") -> list:
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            return verify.check(path)
        except Exception as error:  # pragma: no cover - the checker must not raise
            return ["<exception> %s: %s" % (type(error).__name__, error)]

    def check(self, title: str, ok: bool, detail: str = "") -> None:
        self.count += 1
        if ok:
            print("ok    %s" % title)
            return
        self.failures += 1
        print("FAIL  %s" % title)
        if detail:
            print("      %s" % detail)

    def expect_clean(self, title: str, source: str, **kw) -> None:
        findings = self.run(source, **kw)
        self.check(title, findings == [], "findings=%s" % findings)

    def expect_findings(self, title: str, source: str, n: int, needle: str,
                        **kw) -> None:
        findings = self.run(source, **kw)
        ok = len(findings) == n and any(needle in item for item in findings)
        self.check(
            title, ok,
            "expected %d finding(s) containing %r; got %s"
            % (n, needle, findings),
        )

    def expect_named(self, title: str, source: str, needle: str, **kw) -> None:
        findings = self.run(source, **kw)
        self.check(
            title,
            bool(findings) and any(needle in item for item in findings),
            "expected at least one finding containing %r; got %s"
            % (needle, findings),
        )

    def expect_out_of_scope(self, title: str, source: str, name: str) -> None:
        path = self.path_for(name)
        path.write_text(
            "<!DOCTYPE html><html><body>%s</body></html>" % source,
            encoding="utf-8",
        )
        findings = verify.check(path)
        detected = verify.looks_like_box_plot(path, path.read_text(encoding="utf-8"))
        self.check(
            title,
            findings == [] and not detected,
            "detected=%s findings=%s" % (detected, findings),
        )


def main() -> int:
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


def run_cases(h: Harness) -> int:
    for path in SHIPPED:
        h.check("shipped %s exists" % path.name, path.is_file())
        findings = verify.check(path)
        h.check(
            "shipped %s is clean" % path.name,
            findings == [],
            "findings=%s" % findings,
        )

    h.expect_clean("an honest synthetic box plot passes", honest())

    h.expect_findings(
        "a median drawn off q2 is one finding",
        honest().replace(
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,)),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,),
                   q2_x=x(60) + 12),
            1,
        ),
        1, "median line",
    )

    h.expect_named(
        "a box whose right edge is not q3 is a finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, q3_x=x(40) + 20),
            1,
        ),
        "right edge",
    )

    h.expect_findings(
        "a low whisker that misses wlo is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, wlo_x=x(10) + 16),
            1,
        ),
        1, "low whisker",
    )

    h.expect_findings(
        "an outlier declared inside the whiskers is one finding",
        document(
            series("A", 20, 30, 40, 10, 50, 80),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(80,)),
            series("C", 15, 22, 28, 8, 40, 240),
            TICKS,
        ),
        1, "inside the whiskers",
    )

    h.expect_findings(
        "a second accent series is one finding",
        document(
            series("A", 20, 30, 40, 10, 50, 80, focal=True),
            series("B", 40, 60, 90, 20, 120, 160, focal=True),
            series("C", 15, 22, 28, 8, 40, 240),
            TICKS,
        ),
        1, "at most one focal",
    )

    h.expect_findings(
        "q2 greater than q3 is one finding",
        document(
            series("A", 20, 45, 40, 10, 50, 80),
            series("B", 40, 60, 90, 20, 120, 160, focal=True),
            series("C", 15, 22, 28, 8, 40, 240),
            TICKS,
        ),
        1, "ordered",
    )

    h.expect_named(
        "a transform on a box is a finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, extra='transform="translate(8,0)"'),
            1,
        ),
        "positions a mark",
    )

    h.expect_findings(
        "an outlier outside the whiskers but inside the Tukey fence is one finding",
        honest().replace(
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,)),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(150,)),
            1,
        ),
        1, "Tukey fences",
    )

    h.expect_findings(
        "a whisker that reaches past the Tukey fence is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 75, 80),
            1,
        ),
        1, "reach past the Tukey fences",
    )

    h.expect_findings(
        "a slanted median whose second end misses q2 is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, median_x2=x(30) + 40),
            1,
        ),
        1, "median line",
    )

    h.expect_findings(
        "a high whisker detached from the box is one finding",
        honest().replace(
            '<line data-role="whisker-hi" x1="%g" y1="80"' % x(40),
            '<line data-role="whisker-hi" x1="%g" y1="80"' % (x(40) + 10),
            1,
        ),
        1, "high whisker's box end",
    )

    h.expect_findings(
        "a whisker drawn on another row is one finding",
        honest().replace(
            'x2="%g" y2="80" stroke="rgba(45,49,66,0.55)"' % x(50),
            'x2="%g" y2="160" stroke="rgba(45,49,66,0.55)"' % x(50),
            1,
        ),
        1, "off the row centre",
    )

    h.expect_clean(
        "series wrapped in a plain <g> are all still read",
        document(
            "  <g class=\"series\">\n",
            series("A", 20, 30, 40, 10, 50, 80),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,)),
            series("C", 15, 22, 28, 8, 40, 240),
            "  </g>\n",
            TICKS,
        ),
    )

    h.expect_named(
        "a wrapped series is not dropped from the checks",
        document(
            "  <g class=\"series\">\n",
            series("A", 20, 30, 40, 10, 50, 80, q3_x=x(40) + 20),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(180,)),
            series("C", 15, 22, 28, 8, 40, 240),
            series("D", 12, 18, 24, 6, 36, 320),
            "  </g>\n",
            TICKS,
        ),
        "series 'A' the box's right edge",
    )

    h.expect_named(
        "an inline style width on a box is a finding",
        honest().replace(
            'width="40" height="32" fill="%s"' % INK,
            'width="40" height="32" style="width: 60px" fill="%s"' % INK,
            1,
        ),
        "the width property",
    )

    h.expect_findings(
        "a <style> rule sizing rect is one finding",
        honest().replace("<svg ", "<style>rect { width: 300px; }</style>\n<svg ", 1),
        1, "box-size",
    )

    h.expect_clean(
        "a <style> rule sizing only the <svg> is not a finding",
        honest().replace("<svg ", "<style>svg { width: 100%; }</style>\n<svg ", 1),
    )

    h.expect_findings(
        "a label that names another series is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, label="C"),
            1,
        ),
        1, "must name the series",
    )

    h.expect_findings(
        "a label parked beside another row is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, label_y=164),
            1,
        ),
        1, "off its row",
    )

    h.expect_findings(
        "a series with no bound label is one finding",
        honest().replace(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 20, 30, 40, 10, 50, 80, omit={"label"}),
            1,
        ),
        1, "bound category labels",
    )

    for accent in (ACCENT_FILL, "rgba(240,138,89,0.12)"):
        h.expect_findings(
            "a second box with an accent fill %s and muted stroke is one finding"
            % accent,
            honest().replace(
                series("A", 20, 30, 40, 10, 50, 80),
                series("A", 20, 30, 40, 10, 50, 80, box_fill=accent),
                1,
            ),
            1, "at most one focal",
        )

    h.expect_findings(
        "an accent outlier on a muted series is one finding",
        honest().replace(
            series("C", 15, 22, 28, 8, 40, 240),
            series("C", 15, 22, 28, 8, 40, 240, outliers=(60,)).replace(
                'fill="rgba(45,49,66,0.55)" stroke="#4f5d75"/>',
                'fill="rgba(191,69,32,0.55)" stroke="#bf4520"/>'),
            1,
        ),
        1, "at most one focal",
    )

    h.expect_findings(
        "a declared outlier with no data-x is one finding",
        honest().replace('data-outlier="B" data-x="180" ', 'data-outlier="B" ', 1),
        1, "no data-x",
    )

    h.expect_findings(
        "a tick that prints the wrong number is one finding",
        honest().replace(tick(200), tick(200, shown="350"), 1),
        1, "prints",
    )

    h.expect_findings(
        "a data-tick=y label is one finding",
        honest() + tick(0, axis="y"),
        1, 'data-tick="y"' if False else "label rail",
    )

    h.expect_findings(
        "two series sharing a name is one finding",
        document(
            series("A", 20, 30, 40, 10, 50, 80),
            series("A", 40, 60, 90, 20, 120, 160, focal=True),
            series("C", 15, 22, 28, 8, 40, 240),
            TICKS,
        ),
        1, "share data-name",
    )

    h.expect_findings(
        "two series is fail-closed",
        document(
            series("A", 20, 30, 40, 10, 50, 80),
            series("B", 40, 60, 90, 20, 120, 160, focal=True),
            TICKS,
        ),
        1, "2 verifiable",
    )

    h.expect_named(
        "a missing median is a finding",
        document(
            series("A", 20, 30, 40, 10, 50, 80, omit={"median"}),
            series("B", 40, 60, 90, 20, 120, 160, focal=True),
            series("C", 15, 22, 28, 8, 40, 240),
            series("D", 12, 18, 24, 6, 36, 320),
            TICKS,
        ),
        "median",
    )

    h.expect_findings(
        "a data-outlier circle outside its series group is one finding",
        honest().replace(
            "</svg>",
            '  <circle data-outlier="B" data-x="300" cx="760" cy="160" r="4"/>\n'
            "</svg>",
            1,
        ),
        1, "not inside that",
    )

    b_dot = (
        '    <circle data-outlier="B" data-x="180" cx="%g" cy="160" r="4" '
        'fill="rgba(45,49,66,0.55)" stroke="#4f5d75"/>' % x(180)
    )
    h.expect_findings(
        "outliers moved into their own layer are one finding",
        honest().replace(b_dot + "\n", "").replace(
            "</svg>",
            '<g class="outliers">\n%s\n</g>\n</svg>'
            % b_dot.replace('data-x="180"', 'data-x="300"'),
            1,
        ),
        1, "not inside that",
    )

    h.expect_findings(
        "a :nth-child size rule reaches a box",
        prepend_style('g[data-name="A"] > :nth-child(6) { width: 300px }'),
        1, "box-size",
    )
    h.expect_findings(
        "a :not() size rule with no typed subject reaches a box",
        prepend_style("[data-q1] :not(text):not(line):not(circle) { width: 300px }"),
        1, "box-size",
    )
    h.expect_findings(
        "a backslash escape in a selector is one finding",
        prepend_style(r"r\000065ct { width: 300px }"),
        1, "backslash",
    )
    h.expect_findings(
        "a CSS comment hiding a width rule is one finding",
        prepend_style("rect{/**/width:300px}"),
        1, "box-size",
    )
    h.expect_findings(
        "a CSS comment hiding a transform is one finding",
        prepend_style("rect{/**/transform:translateX(100px)}"),
        1, "positions a mark",
    )
    h.expect_named(
        "an inline style comment hiding a width is a finding",
        honest().replace(
            'width="40" height="32" fill="%s"' % INK,
            'width="40" height="32" style="/**/width:300px" fill="%s"' % INK,
            1,
        ),
        "the width property",
    )
    h.expect_named(
        "a backslash escape in an inline style is a finding",
        honest().replace(
            'width="40" height="32" fill="%s"' % INK,
            'width="40" height="32" style="width:\\33 00px" fill="%s"' % INK,
            1,
        ),
        "backslash",
    )
    h.expect_findings(
        "a stylesheet link other than the font link is one finding",
        honest().replace(
            "<svg ",
            '<link rel="stylesheet" href="data:text/css,rect%7Bwidth:300px%7D">\n'
            "<svg ",
            1,
        ),
        1, "stylesheet link",
    )
    h.expect_clean(
        "the Google font stylesheet link is not a finding",
        honest().replace(
            "<svg ",
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
            'family=Geist&display=swap">\n<svg ',
            1,
        ),
    )
    h.expect_findings(
        "a <set> inside the figure is one finding",
        honest().replace(
            "    <rect %s" % A_BOX,
            '    <set attributeName="width" to="300"/>\n    <rect %s' % A_BOX,
            1,
        ),
        1, "<set>",
    )
    h.expect_findings(
        "an <animate> inside the figure is one finding",
        honest().replace(
            "</svg>",
            '  <animate attributeName="x" to="120"/>\n</svg>',
            1,
        ),
        1, "<animate>",
    )

    h.expect_findings(
        "dx/dy on a bound label is one finding",
        honest().replace(A_LABEL, A_LABEL.replace(" y=", ' dy="136" y=', 1), 1),
        1, "dx/dy",
    )
    h.expect_findings(
        "a positioned tspan in a bound label is one finding",
        honest().replace(
            A_LABEL,
            '<text data-name="A" x="148" y="84" text-anchor="end">'
            '<tspan y="220">A</tspan></text>',
            1,
        ),
        1, "<tspan>",
    )
    h.expect_clean(
        "an unpositioned tspan in a bound label is not a finding",
        honest().replace(
            A_LABEL,
            '<text data-name="A" x="148" y="84" text-anchor="end">'
            "<tspan>A</tspan></text>",
            1,
        ),
    )
    h.expect_findings(
        "a label drawn off the label rail is one finding",
        honest().replace(A_LABEL, A_LABEL.replace('x="148"', 'x="-500"', 1), 1),
        1, "label rail",
    )
    h.expect_findings(
        "a hidden bound label is one finding",
        honest().replace(
            A_LABEL,
            A_LABEL.replace("<text ", '<text opacity="0" ', 1)
            + '<text x="148" y="84">Catalog</text>',
            1,
        ),
        1, "hides its bound label",
    )

    h.expect_findings(
        "an inline accent fill on a muted box is one finding",
        honest().replace(
            'x="200" y="64" width="40" height="32" fill="%s"' % INK,
            'x="200" y="64" width="40" height="32" style="fill:#bf4520" fill="%s"'
            % INK,
            1,
        ),
        1, "at most one focal",
    )
    h.expect_findings(
        "a class rule painting a muted box with the accent is one finding",
        prepend_style(".hot{fill:#bf4520}").replace(
            A_BOX, 'data-role="box" class="hot" x="200"', 1),
        1, "at most one focal",
    )
    for accent in ("#bf4520ff", "rgb(191,69,32)"):
        h.expect_findings(
            "accent fill %s on a muted box is one finding" % accent,
            honest().replace(
                series("A", 20, 30, 40, 10, 50, 80),
                series("A", 20, 30, 40, 10, 50, 80, box_fill=accent),
                1,
            ),
            1, "at most one focal",
        )
    h.expect_findings(
        "an accent fill on the paper underlay is one finding",
        honest().replace(
            "    <rect %s" % A_BOX,
            '    <rect x="200" y="64" width="40" height="32" fill="#bf4520"/>\n'
            "    <rect %s" % A_BOX,
            1,
        ),
        1, "at most one focal",
    )
    h.expect_findings(
        "an accent stroke on the median is one finding",
        honest().replace(
            'data-role="median" x1="220" y1="64" x2="220" y2="96" stroke="#2d3142"',
            'data-role="median" x1="220" y1="64" x2="220" y2="96" stroke="#bf4520"',
            1,
        ),
        1, "at most one focal",
    )

    block = series("A", 20, 30, 40, 10, 50, 80)
    h.expect_findings(
        "a nested svg viewport shifting a series is one finding",
        honest().replace(
            block, '<svg x="120" overflow="visible">\n%s</svg>\n' % block, 1),
        1, "nested <svg>",
    )
    h.expect_findings(
        "a <use> shifting a series is one finding",
        honest().replace("</svg>", '  <use href="#auth" x="120"/>\n</svg>', 1),
        1, "<use>",
    )
    hidden = block.replace("<g ", '<g id="auth" ', 1)
    drawn = block.replace(' data-q1="20"', "", 1)
    stashed = honest().replace(
        block, "<defs>\n%s</defs>\n%s" % (hidden, drawn), 1)
    h.expect_named(
        "a series stashed in <defs> is a finding",
        stashed, "non-rendering",
    )
    h.expect_named(
        "a series stashed in <defs> after a self-closing <mask/> is a finding",
        honest().replace(
            block, "<defs>\n<mask/>\n%s</defs>\n%s" % (hidden, drawn), 1),
        "non-rendering",
    )
    h.expect_named(
        "a drawn copy with no data-q1 is a finding",
        stashed, "outside every series",
    )

    h.expect_findings(
        "a second median off q2 is one finding",
        honest().replace(
            'data-role="median" x1="220" y1="64" x2="220" y2="96" '
            'stroke="#2d3142" stroke-width="1.5"/>',
            'data-role="median" x1="220" y1="64" x2="220" y2="96" '
            'stroke="#2d3142" stroke-width="1.5"/>\n'
            '    <line data-role="median" x1="500" y1="64" x2="500" y2="96" '
            'stroke="#2d3142" stroke-width="1.5"/>',
            1,
        ),
        1, "median line",
    )
    h.expect_findings(
        "a cap off the whisker end is one finding",
        honest().replace(
            '    <line data-role="whisker-hi" x1="240" y1="80" x2="260" y2="80" '
            'stroke="rgba(45,49,66,0.55)" stroke-width="1"/>',
            '    <line data-role="whisker-hi" x1="240" y1="80" x2="260" y2="80" '
            'stroke="rgba(45,49,66,0.55)" stroke-width="1"/>\n'
            '    <line data-role="cap" x1="800" y1="72" x2="800" y2="88" '
            'stroke="#4f5d75"/>',
            1,
        ),
        1, "cap",
    )
    h.expect_findings(
        "an unbound circle inside a series is one finding",
        honest().replace(
            A_LABEL,
            '    <circle cx="300" cy="80" r="4" fill="#4f5d75"/>\n    ' + A_LABEL,
            1,
        ),
        1, "paper mask",
    )
    papered = honest().replace(
        "  <g ", '  <rect width="100%" height="100%" fill="#f5f5f5"/>\n  <g ', 1)
    mask = '<circle cx="520" cy="160" r="4" fill="#f5f5f5"/>\n    '
    h.expect_clean(
        "a paper mask on a bound outlier is not a finding",
        papered.replace('<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1),
    )
    h.expect_findings(
        "a paper mask repainted by an inline style is one finding",
        papered.replace(
            '<circle data-outlier="B"',
            mask.replace("/>", ' style="fill:#4f5d75"/>', 1) + '<circle data-outlier="B"',
            1,
        ),
        1, "paper mask",
    )
    h.expect_findings(
        "an <animateColor> inside the figure is one finding",
        honest().replace(
            "</svg>", '  <animateColor attributeName="fill" to="#bf4520"/>\n</svg>', 1),
        1, "<animatecolor>",
    )
    h.expect_findings(
        "an accent fill inherited from a muted series group is one finding",
        honest().replace(block, block.replace("<g ", '<g fill="#bf4520" ', 1), 1),
        1, "at most one focal",
    )
    h.expect_findings(
        "an accent path inside a muted series is one finding",
        honest().replace(
            A_LABEL, '<path d="M200 64h40v32h-40z" fill="#bf4520"/>\n    ' + A_LABEL, 1),
        1, "at most one focal",
    )
    h.expect_findings(
        "a paper mask inheriting a group stroke is one finding",
        papered.replace(
            '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
        ).replace('<g data-name="B"', '<g stroke="#4f5d75" data-name="B"', 1),
        1, "paper mask",
    )
    h.expect_findings(
        "a paper mask inheriting a wrapper stroke is one finding",
        papered.replace(
            '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
        ).replace('  <g data-name="B"', '  <g stroke="#4f5d75">\n  <g data-name="B"', 1
        ).replace("</svg>", "  </g>\n</svg>", 1),
        1, "paper mask",
    )
    h.expect_findings(
        "a hidden tspan inside a bound label is one finding",
        honest().replace(
            A_LABEL,
            '<text data-name="A" x="148" y="84" text-anchor="end">'
            '<tspan opacity="0">A</tspan></text>',
            1,
        ),
        1, "hides its bound label",
    )
    h.expect_findings(
        "a descendant class rule painting a muted series with the accent is one finding",
        prepend_style(".hot rect{fill:#bf4520}").replace(
            block, block.replace("<g ", '<g class="hot" ', 1), 1),
        1, "at most one focal",
    )
    h.expect_findings(
        "a polygon class rule painting a muted series with the accent is one finding",
        prepend_style("polygon.hot{fill:#bf4520}").replace(
            A_LABEL,
            '<polygon class="hot" points="200,64 240,64 240,96"/>\n    ' + A_LABEL,
            1,
        ),
        1, "at most one focal",
    )
    h.expect_findings(
        "a cap on the whisker end but off its row is one finding",
        honest().replace(
            A_LABEL,
            '<line data-role="cap" x1="260" y1="200" x2="260" y2="216" '
            'stroke="#4f5d75"/>\n    ' + A_LABEL,
            1,
        ),
        1, "cap runs",
    )

    h.expect_out_of_scope(
        "the parent scatter is not a box plot",
        "<svg role='img'><title>t</title><desc>A scatter of latency against "
        "errors.</desc>"
        '<circle cx="200" cy="200" r="5" fill="rgba(45,49,66,0.20)"/>'
        "</svg>",
        "example-scatter-fixture.html",
    )

    h.expect_out_of_scope(
        "data-value on a <circle> never claims a file — the beeswarm contract",
        "<svg role='img'><title>t</title><desc>A beeswarm of requests.</desc>"
        '<circle data-value="90" cx="260" cy="230" r="4"/>'
        "</svg>",
        "fixture.html",
    )

    h.check(
        "no shipped box-plot file declares data-value on a circle, data-series, "
        "data-ranks or data-size, so no sibling verifier claims one",
        all(not re.search(r"<circle[^>]*data-value\s*=",
                          path.read_text(encoding="utf-8"))
            and not re.search(r"data-(series|ranks|size)\s*=",
                              path.read_text(encoding="utf-8"))
            for path in SHIPPED),
    )

    for sibling in ("verify-slopegraph.py", "verify-bump.py",
                    "verify-bubble.py", "verify-beeswarm.py"):
        script = ROOT / "scripts" / sibling
        if not script.is_file():
            print("skip  %s not on this branch; treaty case not applicable"
                  % sibling)
            continue
        result = subprocess.run(
            [sys.executable, str(script)] + [str(p) for p in SHIPPED],
            capture_output=True, text=True,
        )
        h.check(
            "%s skips all three shipped box-plot files" % sibling,
            result.returncode == 0
            and "3 file(s) skipped as out of scope" in result.stdout,
            "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
        )

    sentinel = ROOT / "example-box-plot-fixture.html"
    existed = sentinel.exists()
    if not existed:
        sentinel.write_text("KEEP ME\n", encoding="utf-8")
    try:
        h.run(honest())
        h.check(
            "a pre-existing file sharing a fixture name is never touched",
            sentinel.exists() and sentinel.read_text(encoding="utf-8") == "KEEP ME\n",
            "%s was overwritten or deleted by the harness" % sentinel,
        )
    finally:
        if not existed and sentinel.exists():
            sentinel.unlink()

    h.check(
        "fixtures are written outside the repository",
        not str(h.dir).startswith(str(ROOT)),
        "fixture dir %s is inside %s" % (h.dir, ROOT),
    )

    print()
    if h.failures:
        print("%d of %d case(s) failed." % (h.failures, h.count))
        return 1
    print("OK box-plot checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
