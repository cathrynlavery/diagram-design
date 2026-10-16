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
           omit=None, extra="", outlier_x=None, outlier_inside=False):
    omit = omit or set()
    box_x = x(q1) if q1_x is None else q1_x
    box_r = x(q3) if q3_x is None else q3_x
    med = x(q2) if q2_x is None else q2_x
    lo = x(wlo) if wlo_x is None else wlo_x
    hi = x(whi) if whi_x is None else whi_x
    fill, stroke = (ACCENT_FILL, ACCENT_STROKE) if focal else (INK, STROKE)
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
            % (med, y, med, y + 32)
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
        series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(160,)),
        series("C", 15, 22, 28, 8, 40, 240),
        TICKS,
        *extra,
    )


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
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(160,)),
            series("B", 40, 60, 90, 20, 120, 160, focal=True, outliers=(160,),
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
