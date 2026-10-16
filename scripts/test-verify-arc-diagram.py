#!/usr/bin/env python3
"""Adversarial cases for verify-arc-diagram.py, both polarities.

Every case is named for exactly what it asserts. The negative half matters
as much as the positive: a checker that fires on an honest figure, on the
parent dependency graph, or on a sibling contract's files gets widened or
switched off, and then it guards nothing.

The scope treaty is pinned here in both directions: fixtures prove that
`data-value` on a <circle> (the beeswarm contract) never claims a file for
this checker, and every sibling per-file verifier present on the branch is
run as a subprocess against the shipped arc-diagram examples and must skip
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

verify = __import__("verify-arc-diagram")

ASSETS = ROOT / "skills/diagram-design/assets"
SHIPPED = [ASSETS / name for name in (
    "example-arc-diagram.html", "example-arc-diagram-dark.html",
    "example-arc-diagram-full.html",
)]

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="arc-diagram-title arc-diagram-desc">
  <title id="arc-diagram-title">t</title>
  <desc id="arc-diagram-desc">Arc diagram fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

Y = 400
PITCH = 140
ORIGIN = 80
INK = "rgba(45,49,66,0.45)"
ACCENT = "#bf4520"


def x_of(index: int) -> float:
    return ORIGIN + index * PITCH


def node(name: str, index: int, *, cy=None, cx=None, extra=""):
    cx = x_of(index) if cx is None else cx
    cy = Y if cy is None else cy
    return (
        '  <circle data-name="%s" cx="%g" cy="%g" r="6" fill="rgba(45,49,66,0.55)" '
        'stroke="#4f5d75"%s/>\n'
        '  <text data-name="%s" x="%g" y="428">%s</text>\n'
        % (name, cx, cy, (" " + extra) if extra else "", name, cx, name)
    )


def arc(frm: str, to: str, span: int, i: int, j: int, *,
        r=None, sweep="1", stroke=None, extra="", d=None):
    xa, xb = sorted([x_of(i), x_of(j)])
    radius = (xb - xa) / 2.0 if r is None else r
    stroke = INK if stroke is None else stroke
    if d is None:
        d = "M %g,%g A %g,%g 0 0 %s %g,%g" % (xa, Y, radius, radius, sweep, xb, Y)
    return (
        '  <path data-from="%s" data-to="%s" data-span="%s" d="%s" fill="none" '
        'stroke="%s" stroke-width="1.2"%s/>\n'
        % (frm, to, span, d, stroke, (" " + extra) if extra else "")
    )


def honest(*extra: str) -> str:
    return document(
        node("A", 0), node("B", 1), node("C", 2), node("D", 3), node("E", 4),
        arc("A", "B", 1, 0, 1),
        arc("B", "C", 1, 1, 2),
        arc("C", "D", 1, 2, 3),
        arc("D", "E", 1, 3, 4),
        arc("A", "C", 2, 0, 2),
        arc("A", "E", 4, 0, 4, stroke=ACCENT),
        *extra,
    )


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


class Harness:
    def __init__(self):
        self.failures = 0
        self.count = 0
        self.dir = Path(tempfile.mkdtemp(prefix="arc-diagram-fixtures-"))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-arc-diagram-fixture.html") -> list:
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
        detected = verify.looks_like_arc_diagram(
            path, path.read_text(encoding="utf-8")
        )
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

    h.expect_clean("an honest synthetic arc diagram passes", honest())

    tall = honest().replace(
        arc("A", "B", 1, 0, 1),
        arc("A", "B", 1, 0, 1, r=140),
        1,
    )
    h.expect_findings(
        "a neighbour drawn at a skip's radius is one finding",
        tall, 1, "height encodes the skip",
    )

    wrong_span = honest().replace(
        'data-from="A" data-to="E" data-span="4"',
        'data-from="A" data-to="E" data-span="2"',
        1,
    )
    h.expect_named(
        "a declared span that is not the seat count is a finding",
        wrong_span, "seats are",
    )

    h.expect_findings(
        "a second accent arc is one finding",
        document(
            node("A", 0), node("B", 1), node("C", 2), node("D", 3),
            arc("A", "B", 1, 0, 1, stroke=ACCENT),
            arc("B", "C", 1, 1, 2, stroke=ACCENT),
            arc("C", "D", 1, 2, 3),
        ),
        1, "at most one focal",
    )

    h.expect_findings(
        "sweep 0 draws the import under the seats",
        honest().replace(
            arc("A", "C", 2, 0, 2),
            arc("A", "C", 2, 0, 2, sweep="0"),
            1,
        ),
        1, "sweep=0",
    )

    h.expect_named(
        "a transform on an arc is a finding",
        honest().replace(
            arc("A", "B", 1, 0, 1),
            arc("A", "B", 1, 0, 1, extra='transform="translate(8,0)"'),
            1,
        ),
        "positions a mark",
    )

    h.expect_named(
        "two nodes sharing a name is a finding",
        document(
            node("A", 0), node("A", 1), node("C", 2), node("D", 3),
            arc("A", "C", 2, 0, 2),
            arc("C", "D", 1, 2, 3),
            arc("A", "D", 3, 0, 3, stroke=ACCENT),
        ),
        "share data-name",
    )

    h.expect_findings(
        "three nodes is fail-closed",
        document(
            node("A", 0), node("B", 1), node("C", 2),
            arc("A", "B", 1, 0, 1),
            arc("B", "C", 1, 1, 2),
            arc("A", "C", 2, 0, 2, stroke=ACCENT),
        ),
        1, "3 verifiable",
    )

    h.expect_named(
        "an omitted fill is a finding",
        honest().replace('fill="none" stroke="%s"' % INK,
                         'stroke="%s"' % INK, 1),
        "fill=",
    )

    uneven = honest().replace(
        node("C", 2),
        node("C", 2, cx=x_of(2) + 40),
        1,
    )
    h.expect_named(
        "an uneven pitch is a finding",
        uneven, "pitch is shared",
    )

    h.expect_out_of_scope(
        "the parent dependency graph is not an arc diagram",
        "<svg role='img'><title>t</title><desc>A ranked dependency graph of "
        "packages.</desc>"
        '<rect x="80" y="80" width="160" height="56" rx="6"/>'
        "</svg>",
        "example-dependency-fixture.html",
    )

    h.expect_out_of_scope(
        "data-value on a <circle> never claims a file — the beeswarm contract",
        "<svg role='img'><title>t</title><desc>A beeswarm of requests.</desc>"
        '<circle data-value="90" cx="260" cy="230" r="4"/>'
        "</svg>",
        "fixture.html",
    )

    h.check(
        "no shipped arc-diagram file declares data-value on a circle, "
        "data-q1, data-series, data-ranks or data-size, so no sibling "
        "verifier claims one",
        all(not re.search(r"<circle[^>]*data-value\s*=",
                          path.read_text(encoding="utf-8"))
            and not re.search(r"data-(q1|series|ranks|size)\s*=",
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
            "%s skips all three shipped arc-diagram files" % sibling,
            result.returncode == 0
            and "3 file(s) skipped as out of scope" in result.stdout,
            "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
        )

    sentinel = ROOT / "example-arc-diagram-fixture.html"
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
    print("OK arc-diagram checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
