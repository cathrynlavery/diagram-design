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

AUTH_G = '<g data-name="Auth"'
AUTH_BOX = ('<rect data-role="box" x="196" y="64.0" width="20" height="32" rx="2" '
            'fill="rgba(45,49,66,0.15)" stroke="#4f5d75" stroke-width="1"/>')
CHECKOUT_BOX = ('<rect data-role="box" x="320" y="200.0" width="240" height="32" '
                'rx="2" fill="rgba(191,69,32,0.12)" stroke="#bf4520"')


def shipped_with(*swaps: tuple, index: int = 0) -> str:
    """A shipped example with each (old, new) swap applied exactly once."""
    source = SHIPPED[index].read_text(encoding="utf-8")
    for old, new in swaps:
        assert source.count(old) == 1, "fixture anchor %r is not unique" % old
        source = source.replace(old, new)
    return source


def auth_fill(paint: str) -> tuple:
    return AUTH_BOX, AUTH_BOX.replace('fill="rgba(45,49,66,0.15)"', paint, 1)


def styled(css: str) -> tuple:
    return "  </style>", "    %s\n  </style>" % css


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

    a_block = series("A", 20, 30, 40, 10, 50, 80)
    h.expect_findings(
        "a second box rect in a series is one finding",
        honest().replace(
            A_LABEL,
            '<rect data-role="box" x="200" y="64" width="160" height="32" '
            'fill="rgba(45,49,66,0.06)" stroke="#4f5d75"/>\n    ' + A_LABEL,
            1,
        ),
        1, "data-role=box marks",
    )
    h.expect_findings(
        "a second whisker-hi in a series is one finding",
        honest().replace(
            A_LABEL,
            '<line data-role="whisker-hi" x1="240" y1="80" x2="400" y2="80" '
            'stroke="rgba(45,49,66,0.55)" stroke-width="1"/>\n    ' + A_LABEL,
            1,
        ),
        1, "data-role=whisker-hi marks",
    )
    h.expect_named(
        "bound marks wrapped in <defs> inside a visible series are a finding",
        honest().replace(
            a_block,
            a_block.replace('    <line data-role="whisker-lo"',
                            '    <defs>\n    <line data-role="whisker-lo"', 1)
            .replace("    " + A_LABEL, "    </defs>\n    " + A_LABEL, 1),
            1,
        ),
        "non-rendering container",
    )
    shared = prepend_style(".series.focal rect{fill:#bf4520}")
    for group in ('<g data-name="A"', '<g data-name="C"'):
        shared = shared.replace(group, group.replace("<g ", '<g class="series" '), 1)
    h.expect_clean(
        "a compound class rule does not paint groups carrying only one of its classes",
        shared.replace('<g data-name="B"', '<g class="series focal" data-name="B"', 1),
    )
    h.expect_findings(
        "a compound class rule painting a second series is one finding",
        shared.replace('<g class="series" data-name="A"',
                       '<g class="series focal" data-name="A"', 1),
        1, "at most one focal",
    )
    for rule in ("rect.hot:not(.muted){fill:#bf4520}", "rect:is(.hot){fill:#bf4520}"):
        h.expect_named(
            "a %s rule painting a muted box is a finding" % rule.split("{")[0],
            prepend_style(rule).replace(A_BOX, 'class="hot" ' + A_BOX, 1),
            "at most one focal",
        )
    h.expect_clean(
        "a stroked sibling group does not repaint a paper mask",
        papered.replace(
            '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
        ).replace(
            '    <line data-role="whisker-lo" x1="200"',
            '    <g stroke="#4f5d75"><line data-role="whisker-lo" x1="200"', 1,
        ).replace(
            'x2="240" y2="160" stroke="rgba(45,49,66,0.55)" stroke-width="1"/>',
            'x2="240" y2="160" stroke="rgba(45,49,66,0.55)" stroke-width="1"/></g>', 1,
        ),
    )
    for radius, change in (("missing", ""), ("zero", ' r="0"')):
        h.expect_findings(
            "a bound outlier with a %s radius is one finding" % radius,
            re.sub(r'(<circle data-outlier="B"[^>]*?) r="4"', r"\1" + change,
                   honest(), count=1),
            1, "positive radius",
        )
    stroked_root = papered.replace(
        '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
    ).replace("<svg viewBox", '<svg stroke="#4f5d75" viewBox', 1)
    h.expect_clean(
        "a series group's stroke=\"none\" overrides a root stroke on a paper mask",
        stroked_root.replace('<g data-name="B"', '<g stroke="none" data-name="B"', 1),
    )
    h.expect_findings(
        "a root stroke reaching a paper mask with no override is one finding",
        stroked_root,
        1, "paper mask",
    )
    h.expect_findings(
        "a class rule painting stroke:none on a series' rects does not "
        "override a root stroke on a paper mask",
        stroked_root.replace("  <g ", "  <style>.hot rect{stroke:none}</style>\n  <g ", 1
        ).replace('<g data-name="B"', '<g class="hot" data-name="B"', 1),
        1, "paper mask",
    )
    outer_stroke = papered.replace(
        '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
    ).replace('  <g data-name="B"', '  <g class="outer">\n  <g stroke="none" data-name="B"', 1
    ).replace("</svg>", "  </g>\n</svg>", 1)
    h.expect_clean(
        "stroke=\"none\" on a series overrides a class stroke on an outer group",
        outer_stroke.replace("  <g ", "  <style>.outer{stroke:#4f5d75}</style>\n  <g ", 1),
    )
    h.expect_findings(
        "a class rule stroking circles under an outer group reaches a paper mask "
        "through an inner stroke=\"none\"",
        outer_stroke.replace(
            "  <g ", "  <style>.outer circle{stroke:#4f5d75}</style>\n  <g ", 1),
        1, "paper mask",
    )
    h.expect_findings(
        "a class rule stroking groups under an outer group reaches a paper mask",
        papered.replace(
            '<circle data-outlier="B"', mask + '<circle data-outlier="B"', 1,
        ).replace('  <g data-name="B"', '  <g class="outer">\n  <g data-name="B"', 1
        ).replace("</svg>", "  </g>\n</svg>", 1
        ).replace("  <g ", "  <style>.outer g{stroke:#4f5d75}</style>\n  <g ", 1),
        1, "paper mask",
    )

    h.expect_findings(
        "a class selector listed after a type-only one still repaints a paper mask",
        papered.replace(
            '<circle data-outlier="B"',
            mask.replace("<circle ", '<circle class="m" ', 1) + '<circle data-outlier="B"', 1,
        ).replace("  <g ", "  <style>line, .m{stroke:#4f5d75}</style>\n  <g ", 1),
        1, "paper mask",
    )

    # The accent and visibility as a browser resolves them, on the shipped
    # example's muted Auth series: var(), hsl(), id and attribute selectors,
    # and display/visibility/opacity on the series or a mark.
    for title, swaps in (
        ("an inline var(--color-accent) fill",
         [(AUTH_BOX, AUTH_BOX.replace("/>", ' style="fill:var(--color-accent)"/>'))]),
        ("a var() chained to the accent through another custom property",
         [auth_fill('fill="var(--color-focus)"'),
          ("--color-accent: #bf4520;",
           "--color-accent: #bf4520;\n      --color-focus: var(--color-accent);")]),
        ("an hsl() spelling of the accent", [auth_fill('fill="hsl(14,71%,44%)"')]),
        ("an hsla() spelling one rounding step off the accent",
         [auth_fill('fill="hsla(13, 72%, 43%, 0.12)"')]),
        ("a space-separated hsl() with a turn hue",
         [auth_fill('fill="hsl(0.0388turn 71% 44% / 0.12)"')]),
        ("an attribute selector", [styled('[data-name="Auth"] rect{fill:#bf4520}')]),
        ("an id selector",
         [styled("#auth rect{fill:#bf4520}"), (AUTH_G, '<g id="auth" data-name="Auth"')]),
        ("a descendant attribute selector",
         [styled('g[data-name="Auth"] [data-role="box"]{fill:#bf4520}')]),
        ("a prefix attribute selector painting var(--color-accent)",
         [styled('[data-name^="Au"] rect{stroke:var(--color-accent)}')]),
    ):
        h.expect_findings(
            "%s on a muted series is one finding" % title,
            shipped_with(*swaps), 1, "at most one focal",
        )
    h.expect_findings(
        "an hsl() spelling of the dark accent on a muted series is one finding",
        shipped_with(
            ('x="196" y="64.0" width="20" height="32" rx="2" fill="rgba(245,245,245,0.14)"',
             'x="196" y="64.0" width="20" height="32" rx="2" fill="hsl(20,83%,64%)"'),
            index=1),
        1, "at most one focal",
    )
    h.expect_named(
        "a type selector painting the accent cannot be held to one series and "
        "is a finding",
        shipped_with(styled("rect{fill:#bf4520}")),
        "at most one focal",
    )
    for title, swaps in (
        ('display="none" on the series group', [(AUTH_G, '<g display="none" data-name="Auth"')]),
        ('visibility="hidden" on the series group',
         [(AUTH_G, '<g visibility="hidden" data-name="Auth"')]),
        ('style="display:none" on the series group',
         [(AUTH_G, '<g style="display:none" data-name="Auth"')]),
        ('style="visibility:hidden" on the box',
         [(AUTH_BOX, AUTH_BOX.replace("/>", ' style="visibility:hidden"/>'))]),
        ('opacity="0" on the box', [(AUTH_BOX, AUTH_BOX.replace("/>", ' opacity="0"/>'))]),
        ('display="none" on a wrapper group',
         [(AUTH_G, '<g display="none">\n      <g data-name="Auth"'),
          ('      <g data-name="Catalog"', '      </g>\n      <g data-name="Catalog"')]),
    ):
        h.expect_findings(
            "a series hidden by %s is one finding" % title,
            shipped_with(*swaps), 1, "never drawn",
        )
    for title, swaps in (
        ("the focal series painted through var(--color-accent)",
         [(CHECKOUT_BOX, CHECKOUT_BOX.replace(
             'fill="rgba(191,69,32,0.12)" stroke="#bf4520"',
             'fill="var(--color-accent)" fill-opacity="0.12" stroke="var(--color-accent)"'))]),
        ("an attribute selector painting only the focal series",
         [styled('[data-name="Checkout"] rect{stroke:var(--color-accent)}')]),
        ("a muted box stroked through var(--color-muted)",
         [(AUTH_BOX, AUTH_BOX.replace('stroke="#4f5d75"', 'stroke="var(--color-muted)"'))]),
        ("a muted hsl() fill", [auth_fill('fill="hsl(218,19%,38%)"')]),
        ("a type selector painting a muted stroke", [styled("line{stroke:#4f5d75}")]),
        ("a series group that states visibility and a nonzero opacity",
         [(AUTH_G, '<g visibility="visible" opacity="0.9" data-name="Auth"')]),
    ):
        h.expect_clean("%s passes" % title, shipped_with(*swaps))

    # A <style> rule hides as surely as an attribute. Rules tied to one
    # series count against it; type-only rules count against every series
    # they could reach, and so does a rule hiding an element around the svg.
    for title, swaps, count in (
        ('[data-name="Auth"]{display:none}',
         [styled('[data-name="Auth"]{display:none}')], 1),
        ("#auth{display:none} on the series id",
         [styled("#auth{display:none}"), (AUTH_G, '<g id="auth" data-name="Auth"')], 1),
        ('[data-name="Auth"] rect{visibility:hidden}',
         [styled('[data-name="Auth"] rect{visibility:hidden}')], 1),
        ('[data-name="Auth"] line{display:none !important}',
         [styled('[data-name="Auth"] line{display:none !important}')], 1),
        ("a type-only g{opacity:0}", [styled("g{opacity:0}")], 5),
        (".frame{display:none} on the page element around the svg",
         [styled(".frame{display:none}")], 5),
    ):
        h.expect_findings(
            "a stylesheet rule %s is %d never-drawn finding(s)" % (title, count),
            shipped_with(*swaps), count, "never drawn",
        )
    for title, css in (
        ("a hiding rule on a class used only outside the svg", ".eyebrow{display:none}"),
        ("a type-only hiding rule no chart element can match", "p{opacity:0}"),
    ):
        h.expect_clean("%s passes" % title, shipped_with(styled(css)))

    # Every compound left of the subject must match a strict ancestor, in
    # order: never the element itself, a sibling or a descendant.
    for title, css, count, needle in (
        ("body .frame{display:none} (a real ancestor)", "body .frame{display:none}",
         5, "never drawn"),
        ('svg > g[data-name="Auth"]{display:none} (its real parent)',
         'svg > g[data-name="Auth"]{display:none}', 1, "never drawn"),
        (".frame rect painting the accent (an ancestor outside the svg)",
         ".frame rect{fill:#bf4520}", 1, "at most one focal"),
        ('[role="img"] [data-name="Auth"] rect painting the accent',
         '[role="img"] [data-name="Auth"] rect{fill:#bf4520}', 1, "at most one focal"),
    ):
        h.expect_findings(
            "a rule %s is %d finding(s)" % (title, count),
            shipped_with(styled(css)), count, needle,
        )
    for title, css in (
        (".frame .frame{display:none} (no .frame around the .frame)",
         ".frame .frame{display:none}"),
        ('g g[data-name="Auth"]{display:none} (no <g> around Auth)',
         'g g[data-name="Auth"]{display:none}'),
        ('[data-name="Auth"] [data-name="Auth"] rect painting the accent',
         '[data-name="Auth"] [data-name="Auth"] rect{fill:#bf4520}'),
        ('g [data-name="Auth"] rect painting the accent (no <g> around Auth)',
         'g [data-name="Auth"] rect{fill:#bf4520}'),
    ):
        h.expect_clean("a rule %s matches nothing and passes" % title,
                       shipped_with(styled(css)))

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
