#!/usr/bin/env python3
"""Adversarial cases for verify-bubble.py, both polarities.

Every case is named for exactly what it asserts — a name that overclaims is
itself a defect. The negative half matters as much as the positive: a checker
that fires on an honest bubble chart, on the parent scatter, or on the shipped
slopegraph gets widened or switched off, and then it guards nothing.

Fixtures live in a per-process temporary directory, never under the repository
root, and two cases at the end hold that isolation in place.

Exit: 0 all pass, 1 any failure.
"""

from __future__ import annotations

import math
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

verify = __import__("verify-bubble")

ASSETS = ROOT / "skills/diagram-design/assets"
SHIPPED = [ASSETS / name for name in (
    "example-bubble.html", "example-bubble-dark.html", "example-bubble-full.html",
)]

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="bubble-title bubble-desc">
  <title id="bubble-title">t</title>
  <desc id="bubble-desc">Bubble chart fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

# The fixture scale, matching the shipped example: x = 80 + 1.76*v over a
# 0-500 domain, y = 420 - 95*v over 0-4, and r = 1.4*sqrt(size).
def cx(value: float) -> float:
    return round(80 + 1.76 * value, 1)


def cy(value: float) -> float:
    return round(420 - 95 * value, 1)


def radius(size: float) -> float:
    return round(1.4 * math.sqrt(size), 1)


def bubble(name: str, x: float, y: float, size: float, drawn_cx=None,
           drawn_cy=None, drawn_r=None, stroke: str = "#4f5d75",
           omit: str = "", extra: str = "") -> str:
    parts = []
    if omit != "data-name":
        parts.append('data-name="%s"' % name)
    parts.append('data-x="%s"' % x)
    parts.append('data-y="%s"' % y)
    parts.append('data-size="%s"' % size)
    if omit != "cx":
        parts.append('cx="%s"' % ("%g" % cx(x) if drawn_cx is None else drawn_cx))
    parts.append('cy="%s"' % ("%g" % cy(y) if drawn_cy is None else drawn_cy))
    parts.append('r="%s"' % ("%g" % radius(size) if drawn_r is None else drawn_r))
    if extra:
        parts.append(extra)
    return ('  <circle %s fill="rgba(45,49,66,0.20)" stroke="%s" '
            'stroke-width="1"/>\n' % (" ".join(parts), stroke))


def label(name: str, x: float, y: float, text=None, extra: str = "") -> str:
    return ('  <text data-name="%s" data-role="label" x="%g" y="%g"%s>%s</text>\n'
            % (name, x, y, (" " + extra) if extra else "",
               name.upper() if text is None else text))


def tick(axis: str, value: float, position=None, shown=None,
         declared=None, extra: str = "") -> str:
    if position is None:
        position = cx(value) if axis == "x" else cy(value) + 4
    coords = ('x="%g" y="440"' % position) if axis == "x" else \
             ('x="72" y="%g"' % position)
    bind = "" if declared == "omit" else \
        ' data-value="%s"' % (value if declared is None else declared)
    return ('  <text data-tick="%s"%s %s%s>%s</text>\n'
            % (axis, bind, coords, (" " + extra) if extra else "",
               ("%g" % value) if shown is None else shown))


TICKS = tick("x", 0) + tick("x", 500) + tick("y", 0) + tick("y", 4)

# Five honest bubbles with distinct values on every axis; none overlap.
BUBBLES = [("Edge", 100, 1.0, 400), ("Queue", 200, 2.0, 100),
           ("Batch", 300, 0.5, 225), ("Webhook", 400, 3.0, 25),
           ("Stream", 150, 1.5, 900)]


def honest_block(rows=None, focal: str = "Edge") -> str:
    body = ""
    for name, x, y, size in sorted(BUBBLES if rows is None else rows,
                                   key=lambda row: -row[3]):
        stroke = "#eb6c36" if name == focal else "#4f5d75"
        body += bubble(name, x, y, size, stroke=stroke)
    return body


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


def honest(rows=None, focal: str = "Edge") -> str:
    return document(honest_block(rows, focal), TICKS)


class Harness:
    def __init__(self) -> None:
        self.failures = 0
        self.count = 0
        # A private temp dir per instance: fixture names are meaningful to the
        # checker (it keys detection off the filename) but their directory is
        # not, so there is no reason to put them anywhere a real file lives.
        self.dir = Path(tempfile.mkdtemp(prefix="bubble-fixtures-"))

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-bubble-fixture.html") -> list:
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            return verify.check(path)
        finally:
            path.unlink()

    def expect_clean(self, case: str, source: str, name: str | None = None) -> None:
        self.count += 1
        found = self.run(source, name) if name else self.run(source)
        if found:
            self.failures += 1
            print("FAIL  %s" % case)
            for item in found:
                print("        unexpected: %s" % item)
        else:
            print("ok    %s" % case)

    def expect_finding(self, case: str, source: str, pattern: str,
                       name: str | None = None) -> None:
        self.count += 1
        found = self.run(source, name) if name else self.run(source)
        if not found:
            self.failures += 1
            print("FAIL  %s\n        expected a finding, got none" % case)
            return
        if not any(re.search(pattern, item) for item in found):
            self.failures += 1
            print("FAIL  %s\n        no finding matched %r" % (case, pattern))
            for item in found:
                print("        got: %s" % item)
            return
        print("ok    %s" % case)

    def expect_only_one(self, case: str, source: str, pattern: str) -> None:
        """A single defect must produce a single finding, not a cascade."""
        self.count += 1
        found = self.run(source)
        if len(found) == 1 and re.search(pattern, found[0]):
            print("ok    %s" % case)
            return
        self.failures += 1
        print("FAIL  %s\n        expected exactly one finding matching %r, got %d"
              % (case, pattern, len(found)))
        for item in found:
            print("        got: %s" % item)

    def expect_out_of_scope(self, case: str, source: str, name: str) -> None:
        """Not merely finding-free — genuinely outside this checker's scope.

        expect_clean cannot tell the two apart: a detected-and-clean file also
        produces no findings, which is not what "out of scope" claims.
        """
        self.count += 1
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            detected = verify.looks_like_bubble(path, source)
            found = verify.check(path)
        finally:
            path.unlink()
        if detected or found:
            self.failures += 1
            print("FAIL  %s\n        detected=%s findings=%d"
                  % (case, detected, len(found)))
            return
        print("ok    %s" % case)

    def check(self, case: str, condition: bool, detail: str = "") -> None:
        self.count += 1
        if condition:
            print("ok    %s" % case)
            return
        self.failures += 1
        print("FAIL  %s%s" % (case, ("\n        " + detail) if detail else ""))


def run_cases(h: Harness) -> int:
    # ── Positive polarity: honest figures pass ────────────────────────────
    for path in SHIPPED:
        found = verify.check(path)
        h.check("shipped %s verifies clean" % path.name, found == [],
                "; ".join(found))

    h.expect_clean("an honest synthetic bubble chart passes", honest())
    h.expect_clean("a chart with no accent bubble at all passes",
                   honest(focal="nobody"))
    h.expect_clean(
        "single-quoted attributes are parsed, not dropped",
        document(honest_block().replace('"', "'"), TICKS),
    )
    h.expect_clean(
        "a lying bubble inside a comment is markup that never renders",
        document(honest_block(), TICKS,
                 "  <!-- %s -->\n" % bubble("Ghost", 100, 1.0, 400,
                                            drawn_cx=900).strip()),
    )

    # An inverted y (value grows downward) is a legitimate design; the checker
    # verifies a SHARED scale, not a direction.
    inverted = ""
    for name, x, y, size in sorted(BUBBLES, key=lambda row: -row[3]):
        inverted += bubble(name, x, y, size, drawn_cy=round(40 + 95 * y, 1))
    inverted_ticks = (tick("x", 0) + tick("x", 500)
                      + tick("y", 0, position=44) + tick("y", 4, position=424))
    h.expect_clean("an inverted y axis with a shared scale passes",
                   document(inverted, inverted_ticks))

    # Overlap honesty. Pair that genuinely overlaps: (256, 325, r28) and
    # (273.6, 315.5, r14) are 20px apart against 42px of radius.
    big = bubble("Big", 100, 1.0, 400)
    small = bubble("Small", 110, 1.1, 100)
    h.expect_clean("overlapping bubbles drawn largest-first pass",
                   document(big, small, TICKS,
                            honest_block([("A", 300, 0.5, 225),
                                          ("B", 400, 3.0, 25)], focal="none")))
    h.expect_finding(
        "a small bubble buried under a later larger one is reported",
        document(small, big, TICKS,
                 honest_block([("A", 300, 0.5, 225), ("B", 400, 3.0, 25)],
                              focal="none")),
        r"painted\s+first — draw overlapping bubbles largest-first",
    )
    twin_a = bubble("TwinA", 200, 2.0, 100)
    twin_b = bubble("TwinB", 205, 2.05, 100)
    h.expect_clean(
        "equal-radius overlap passes in either order — order cannot bury a tie",
        document(twin_a, twin_b, TICKS,
                 honest_block([("A", 300, 0.5, 225), ("B", 400, 3.0, 25)],
                              focal="none")),
    )

    # ── Axis scale lies ───────────────────────────────────────────────────
    # Seven honest peers, so the leave-one-out Theil-Sen fit for each of them
    # stays clean even with the one liar included: with four bubbles a single
    # nudge contaminated the median and dragged a second, honest bubble past
    # tolerance — a cascade blaming the wrong mark.
    HONEST_PEERS = [("Edge", 100, 1.0, 400), ("Queue", 200, 2.0, 100),
                    ("Batch", 300, 0.5, 225), ("Webhook", 400, 3.0, 25),
                    ("Cache", 250, 0.8, 300), ("Ingest", 350, 2.4, 150),
                    ("Ledger", 450, 1.2, 60)]
    nudged = honest_block(HONEST_PEERS, focal="none")
    nudged += bubble("Stream", 150, 1.5, 900, drawn_cx=cx(150) + 8)
    h.expect_only_one(
        "one bubble nudged 8px in x is one finding, not a cascade",
        document(nudged, TICKS),
        r"bubble 'Stream' declares x=150 .* never nudge",
    )
    nudged_y = honest_block(HONEST_PEERS, focal="none")
    nudged_y += bubble("Stream", 150, 1.5, 900, drawn_cy=cy(1.5) - 6)
    h.expect_finding(
        "one bubble nudged 6px in y is reported against its peers' scale",
        document(nudged_y, TICKS),
        r"bubble 'Stream' declares y=1\.5",
    )
    h.expect_finding(
        "an axis where every bubble declares the same value is unverifiable",
        document(honest_block([("A", 100, 1.0, 400), ("B", 100, 2.0, 100),
                               ("C", 100, 0.5, 225), ("D", 100, 3.0, 25)],
                              focal="none"), TICKS),
        r"the x axis has no two distinct declared values",
    )
    # The lone bubble whose peers all share one value: its leave-one-out fit is
    # degenerate, so the residual test skips it and the full-set fit passes
    # through wherever it was drawn. Skipping silently let a bubble at a wrong
    # coordinate ship clean; it must be reported as unverifiable instead.
    lone = honest_block([("A", 100, 1.0, 400), ("B", 100, 2.0, 100),
                         ("C", 100, 0.5, 225)], focal="none")
    lone += bubble("Lone", 300, 3.0, 25, drawn_cx=cx(300) + 40)
    h.expect_finding(
        "a bubble holding the only distinct x value is reported, not skipped",
        document(lone, TICKS),
        r"bubble 'Lone' holds the only distinct x value",
    )

    # ── Area lies ─────────────────────────────────────────────────────────
    proportional = ""
    for name, x, y, size in sorted(BUBBLES, key=lambda row: -row[3]):
        proportional += bubble(name, x, y, size, drawn_r=round(size / 22.0, 1))
    h.expect_finding(
        "radius-proportional sizing is reported — r^2/size is not constant",
        document(proportional, TICKS),
        r"area must be proportional to the value",
    )
    inflated = honest_block([("Edge", 100, 1.0, 400), ("Queue", 200, 2.0, 100),
                             ("Batch", 300, 0.5, 225), ("Webhook", 400, 3.0, 25)],
                            focal="none")
    inflated += bubble("Stream", 150, 1.5, 900, drawn_r=radius(900) + 6)
    h.expect_finding(
        "one bubble drawn 6px too large is reported by name",
        document(inflated, TICKS),
        r"bubble 'Stream' declares size 900",
    )
    h.expect_finding(
        "a non-positive size is reported, not scaled",
        document(honest_block(focal="none"),
                 bubble("Void", 250, 2.5, 0), TICKS),
        r"area cannot encode a non-positive value",
    )
    h.expect_finding(
        "a zero radius is reported — a bubble with no area states no value",
        document(honest_block(focal="none"),
                 bubble("Flat", 250, 2.5, 300, drawn_r=0), TICKS),
        r"a bubble with no area states no value",
    )

    # ── Focal discipline ──────────────────────────────────────────────────
    two_accents = honest_block() + bubble("Rogue", 250, 2.5, 300,
                                          stroke="#eb6c36")
    h.expect_finding(
        "a second accent bubble is reported — one focal claim per figure",
        document(two_accents, TICKS),
        r"one accent bubble max",
    )
    dark_accent = honest_block() + bubble("Rogue", 250, 2.5, 300,
                                          stroke="#f08a59")
    h.expect_finding(
        "the dark-skin accent counts toward the same limit",
        document(dark_accent, TICKS),
        r"one accent bubble max",
    )

    # ── Label lies ────────────────────────────────────────────────────────
    h.expect_clean(
        "a small-caps label matches its mixed-case binding",
        document(honest_block(), TICKS, label("Edge", cx(100), cy(1.0) - 34)),
    )
    h.expect_finding(
        "a label naming an undeclared bubble is reported",
        document(honest_block(), TICKS, label("Phantom", 500, 250)),
        r"which no circle declares",
    )
    h.expect_finding(
        "a label whose text disagrees with its binding is reported",
        document(honest_block(), TICKS,
                 label("Edge", cx(100), cy(1.0) - 34, text="QUEUE")),
        r"the visible text and the binding must agree",
    )
    h.expect_finding(
        "a label drawn nearer another bubble renames the mark",
        document(honest_block(), TICKS,
                 label("Edge", cx(200), cy(2.0) - 4)),
        r"nearer 'Queue'",
    )
    h.expect_finding(
        "a second label for one bubble is reported",
        document(honest_block(), TICKS,
                 label("Edge", cx(100), cy(1.0) - 34),
                 label("Edge", cx(100), cy(1.0) + 42)),
        r"one bubble, one label",
    )

    # ── Tick lies ─────────────────────────────────────────────────────────
    h.expect_finding(
        "a tick printing a different number than it declares is reported",
        document(honest_block(), tick("x", 0), tick("x", 500, shown="400"),
                 tick("y", 0), tick("y", 4)),
        r"prints '400' but declares 500",
    )
    h.expect_finding(
        "a tick drawn off the scale the bubbles set is reported",
        document(honest_block(), tick("x", 0), tick("x", 500, position=760),
                 tick("y", 0), tick("y", 4)),
        r"the printed axis and the drawn positions disagree",
    )
    h.expect_finding(
        "an axis with fewer than two bound ticks is reported",
        document(honest_block(), tick("x", 0), tick("x", 500), tick("y", 0)),
        r"the y axis binds 1 distinct tick value",
    )
    h.expect_finding(
        "a tick with no data-value is reported as unbound",
        document(honest_block(), tick("x", 0), tick("x", 500, declared="omit"),
                 tick("y", 0), tick("y", 4)),
        r"no readable data-value",
    )
    h.expect_finding(
        "a tick printing two numeric tokens is ambiguous, not first-token-parsed",
        document(honest_block(), tick("x", 0),
                 tick("x", 500, shown="500 (512,000)"),
                 tick("y", 0), tick("y", 4)),
        r"prints more than one numeric token",
    )

    # ── Transforms ────────────────────────────────────────────────────────
    h.expect_finding(
        "a transform on a bubble is rejected, not resolved",
        document(honest_block(),
                 bubble("Slid", 250, 2.5, 300,
                        extra='transform="translate(0 80)"'), TICKS),
        r"bubble 'Slid' carries transform=",
    )
    h.expect_finding(
        "an ancestor <g> transform moves every mark inside it",
        document('  <g transform="translate(0 40)">\n', honest_block(),
                 "  </g>\n", TICKS),
        r"an ancestor <g>/<svg> transform",
    )
    h.expect_finding(
        "an UNCLOSED transformed group covers everything after it",
        document('  <g transform="translate(0 40)">\n', honest_block(), TICKS),
        r"an ancestor <g>/<svg> transform",
    )
    h.expect_finding(
        "a transform on a bound label is rejected",
        document(honest_block(), TICKS,
                 label("Edge", cx(100), cy(1.0) - 34,
                       extra='transform="translate(40 0)"')),
        r"a bound label .* carries transform=",
    )
    h.expect_finding(
        "a CSS transform declaration is rejected — no telling what it moves",
        "<style>.bubble { transform: translate(0, 40px); }</style>"
        + document(honest_block(), TICKS),
        r"a CSS `transform` declaration",
    )
    h.expect_clean(
        "text-transform in CSS is styling, not movement",
        "<style>.label { text-transform: uppercase; }</style>"
        + document(honest_block(), TICKS),
    )

    # ── Malformed markup: findings, never tracebacks, never silence ───────
    h.expect_finding(
        "a data-size circle whose attributes cannot be parsed is reported",
        document('  <circle data-size=broken cx="100" cy="100" r="10"/>\n',
                 honest_block(), TICKS),
        r"could not be parsed",
    )
    h.expect_finding(
        "a bubble without data-name is reported",
        document(honest_block(),
                 bubble("X", 250, 2.5, 300, omit="data-name"), TICKS),
        r"data-size but no data-name",
    )
    h.expect_finding(
        "a bubble missing cx is reported with the missing attribute named",
        document(honest_block(), bubble("Hole", 250, 2.5, 300, omit="cx"),
                 TICKS),
        r"bubble 'Hole' is missing cx",
    )
    h.expect_finding(
        "a NaN coordinate is unreadable, not silently within every tolerance",
        document(honest_block(),
                 bubble("Nan", 250, 2.5, 300, drawn_cx="NaN"), TICKS),
        r"not a finite\s+number",
    )

    # ── Fail closed ───────────────────────────────────────────────────────
    h.expect_finding(
        "three bubbles are too few for leave-one-out — refused, not passed",
        document(honest_block([("A", 100, 1.0, 400), ("B", 200, 2.0, 100),
                               ("C", 300, 0.5, 225)], focal="none"), TICKS),
        r"declares 3 verifiable bubble\(s\)",
    )
    h.expect_finding(
        "a file that claims the type by filename but parses nothing is a finding",
        HEAD + TAIL,
        r"declares 0 verifiable bubble",
        name="example-bubble-empty.html",
    )
    h.expect_finding(
        "a file that claims the type in its description is held to the contract",
        "<svg role='img'><title>t</title><desc>A bubble chart of things."
        "</desc></svg>",
        r"declares 0 verifiable bubble",
        name="fixture.html",
    )

    # ── Scope: the neighbours stay unclaimed ──────────────────────────────
    scatter = (ASSETS / "example-scatter.html").read_text(encoding="utf-8")
    h.expect_out_of_scope(
        "the parent scatter is out of scope — points are not bubbles",
        scatter, "example-scatter-fixture.html",
    )
    slopegraph = (ASSETS / "example-slopegraph.html").read_text(encoding="utf-8")
    h.expect_out_of_scope(
        "the shipped slopegraph is out of scope — data-series is not data-size",
        slopegraph, "example-slopegraph-fixture.html",
    )
    h.check(
        "no shipped bubble file declares data-series, so verify-slopegraph "
        "never claims one",
        all("data-series" not in path.read_text(encoding="utf-8")
            for path in SHIPPED),
    )

    # ── The fixture-isolation guarantees, held in place ───────────────────
    sentinel = ROOT / "example-bubble-fixture.html"
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
    print("OK bubble checker: %d case(s), both polarities" % h.count)
    return 0


def main() -> int:
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


if __name__ == "__main__":
    raise SystemExit(main())
