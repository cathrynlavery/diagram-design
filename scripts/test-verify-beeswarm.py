#!/usr/bin/env python3
"""Adversarial cases for verify-beeswarm.py, both polarities.

Every case is named for exactly what it asserts — a name that overclaims is
itself a defect. The negative half matters as much as the positive: a checker
that fires on an honest swarm, on the parent scatter, or on a sibling
contract's files gets widened or switched off, and then it guards nothing.

The scope treaty is pinned here in both directions: fixtures prove that
`data-value` on a <text> tick alone (the bubble contract's tick grammar)
never claims a file for this checker, and every sibling per-file verifier
present on the branch is run as a subprocess against the shipped beeswarm
examples and must skip all three.

Fixtures live in a per-process temporary directory, never under the
repository root, and two cases at the end hold that isolation in place.

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

verify = __import__("verify-beeswarm")

ASSETS = ROOT / "skills/diagram-design/assets"
SHIPPED = [ASSETS / name for name in (
    "example-beeswarm.html", "example-beeswarm-dark.html",
    "example-beeswarm-full.html",
)]

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="beeswarm-title beeswarm-desc">
  <title id="beeswarm-title">t</title>
  <desc id="beeswarm-desc">Beeswarm fixture.</desc>
"""
TAIL = "</svg></body></html>\n"

# The fixture scale, matching the shipped example: x = 80 + 2*v over a
# 0-440 domain, dots r=4 on a y=230 midline with a 10px dodge pitch.
MID, PITCH, R = 230, 10, 4

INK = "rgba(45,49,66,0.55)"
ACCENT_FILL = "rgba(235,108,54,0.55)"


def cx(value: float) -> float:
    return 80 + 2 * value


def dot(value: float, row: int = 0, name=None, drawn_cx=None, drawn_cy=None,
        r: float = R, fill: str = INK, stroke: str = "#4f5d75",
        omit: str = "", extra: str = "") -> str:
    parts = ['data-value="%s"' % value]
    if name is not None:
        parts.append('data-name="%s"' % name)
    if omit != "cx":
        parts.append('cx="%s"' % ("%g" % cx(value) if drawn_cx is None else drawn_cx))
    parts.append('cy="%s"' % ("%g" % (MID + row * PITCH)
                              if drawn_cy is None else drawn_cy))
    parts.append('r="%g"' % r)
    if fill is not None:
        parts.append('fill="%s"' % fill)
    if extra:
        parts.append(extra)
    return '  <circle %s stroke="%s" stroke-width="0.75"/>\n' % (
        " ".join(parts), stroke)


def focal(value: float, row: int = 0, name=None, **kw) -> str:
    return dot(value, row, name, fill=ACCENT_FILL, stroke="#eb6c36", **kw)


def label(name: str, x: float, y: float = 150, text=None,
          extra: str = "") -> str:
    return ('  <text data-name="%s" data-role="label" x="%g" y="%g"%s>%s</text>\n'
            % (name, x, y, (" " + extra) if extra else "",
               name.upper() if text is None else text))


def tick(value: float, position=None, shown=None, declared=None,
         axis: str = "x", extra: str = "") -> str:
    if position is None:
        position = cx(value)
    bind = "" if declared == "omit" else \
        ' data-value="%s"' % (value if declared is None else declared)
    return ('  <text data-tick="%s"%s x="%g" y="440"%s>%s</text>\n'
            % (axis, bind, position, (" " + extra) if extra else "",
               ("%g" % value) if shown is None else shown))


TICKS = tick(0) + tick(100) + tick(200) + tick(400)


def swarm(n: int = 24, depth: int = 1) -> str:
    """n honest dots: columns 20px apart, `depth` dots stacked per column.

    Column spacing (20px) and row pitch (10px) both clear 2r+overlap slack,
    so no honest fixture ever trips the overprint check by accident.
    """
    body = ""
    columns = (n + depth - 1) // depth
    for c in range(columns):
        for row in range(depth):
            if c * depth + row >= n:
                break
            # rows 0, -1, +1, -2, +2 ... around the midline
            signed = (row + 1) // 2 * (1 if row % 2 else -1)
            body += dot(10 * (c + 1), signed)
    return body


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


def honest(*extra: str) -> str:
    return document(swarm(), TICKS, *extra)


class Harness:
    def __init__(self) -> None:
        self.failures = 0
        self.count = 0
        # A private temp dir per instance: fixture names are meaningful to the
        # checker (it keys detection off the filename) but their directory is
        # not, so there is no reason to put them anywhere a real file lives.
        self.dir = Path(tempfile.mkdtemp(prefix="beeswarm-fixtures-"))

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-beeswarm-fixture.html") -> list:
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
            detected = verify.looks_like_beeswarm(path, source)
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

    h.expect_clean("an honest synthetic beeswarm passes", honest())
    h.expect_clean("a swarm with no accent dot at all passes",
                   document(swarm(), TICKS))
    h.expect_clean("one accent dot passes",
                   document(swarm(23), focal(300), TICKS))
    h.expect_clean(
        "single-quoted attributes are parsed, not dropped",
        document(swarm().replace('"', "'"), TICKS),
    )
    h.expect_clean(
        "a lying dot inside a comment is markup that never renders",
        document(swarm(), TICKS,
                 "  <!-- %s -->\n" % dot(100, drawn_cx=900).strip()),
    )
    h.expect_clean(
        "dots sharing a value dodge perpendicular and pass",
        document(swarm(22), dot(300, 0), dot(300, 1), TICKS),
    )
    h.expect_clean(
        "negative and zero values are legitimate on a linear value axis",
        document(swarm(22), dot(0, 2), dot(-50, 0), TICKS),
    )
    h.expect_clean("exactly 20 dots meets the budget floor",
                   document(swarm(20), TICKS))
    h.expect_clean("exactly 300 dots meets the budget ceiling",
                   document(swarm(300, depth=5), TICKS))

    # ── Value-scale lies ──────────────────────────────────────────────────
    h.expect_only_one(
        "one dot nudged 8px along the value axis is one finding, not a cascade",
        document(swarm(23), dot(310, 0, drawn_cx=cx(310) + 8), TICKS),
        r"the dot for value 310 .* never by moving a dot along the value axis",
    )
    h.expect_finding(
        "two dots declaring one value at two positions are reported",
        document(swarm(22), dot(300, 0), dot(300, 1, drawn_cx=cx(300) + 6),
                 TICKS),
        r"dots sharing a value share a position",
    )
    h.expect_finding(
        "an axis where every dot declares the same value is unverifiable",
        document(dot(100, 0), dot(100, 1), dot(100, -1), dot(100, 2), TICKS),
        r"declares 4 verifiable dot\(s\) on 1 distinct value",
    )

    # ── Overprint ─────────────────────────────────────────────────────────
    h.expect_finding(
        "two overprinted dots are reported — density must read as thickness",
        document(swarm(22), dot(300, 0), dot(300, 0, drawn_cy=MID + 5), TICKS),
        r"overlap by .* never as a darker overprint",
    )
    h.expect_clean(
        "dots separated by exactly one pitch do not overlap",
        document(swarm(24, depth=3), TICKS),
    )

    # ── Radius and ink discipline ─────────────────────────────────────────
    h.expect_finding(
        "a bigger focal dot is reported — size is a bubble chart's encoding",
        document(swarm(23), focal(300, r=6), TICKS),
        r"one radius for every dot, focal included",
    )
    h.expect_finding(
        "a second non-focal fill is reported — tone would read as a value",
        document(swarm(23), dot(300, fill="rgba(45,49,66,0.30)"), TICKS),
        r"one fill for every non-focal dot",
    )
    h.expect_finding(
        "a dot with no fill attribute is reported, not exempted",
        document(swarm(23), dot(300, fill=None), TICKS),
        r"declares no fill attribute",
    )
    h.expect_finding(
        "a second accent dot is reported — one focal claim per figure",
        document(swarm(22), focal(300), focal(320), TICKS),
        r"one accent dot max",
    )
    h.expect_finding(
        "the dark-skin accent counts toward the same limit",
        document(swarm(22), focal(300),
                 dot(320, fill="rgba(240,138,89,0.55)", stroke="#f08a59"),
                 TICKS),
        r"one accent dot max",
    )

    # ── Label lies ────────────────────────────────────────────────────────
    h.expect_clean(
        "a small-caps label matches its mixed-case binding",
        document(swarm(23), dot(300, name="req-4c1f"), TICKS,
                 label("req-4c1f", cx(300))),
    )
    h.expect_finding(
        "a label naming an undeclared dot is reported",
        honest(label("phantom", 500)),
        r"which no circle declares",
    )
    h.expect_finding(
        "a label whose text disagrees with its binding is reported",
        document(swarm(23), dot(300, name="req-4c1f"), TICKS,
                 label("req-4c1f", cx(300), text="REQ-0000")),
        r"the visible text and the binding must agree",
    )
    h.expect_finding(
        "two outlier labels exchanged rename both marks",
        document(swarm(22), dot(300, name="req-a"), dot(400, name="req-b"),
                 TICKS, label("req-a", cx(400)), label("req-b", cx(300))),
        r"nearer 'req-b'",
    )
    h.expect_finding(
        "a second label for one dot is reported",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300)), label("req-a", cx(300), y=310)),
        r"one dot, one label",
    )
    h.expect_finding(
        "a named dot with no label is reported — a binding nothing cross-checks",
        document(swarm(23), dot(300, name="req-a"), TICKS),
        r"no label is bound to it",
    )
    seven_named = "".join(dot(200 + 10 * i, i % 3 - 1, name="req-%d" % i)
                          for i in range(7))
    seven_labels = "".join(label("req-%d" % i, cx(200 + 10 * i), 120 + 14 * i)
                           for i in range(7))
    h.expect_finding(
        "seven named dots exceed the label budget",
        document(swarm(13), seven_named, TICKS, seven_labels),
        r"7 dots carry data-name against a budget of 6",
    )
    # Identity is a map key, and a map key collides silently: two dots sharing
    # one data-name overwrote each other in the positions map, so ONE label
    # satisfied both dots and the file reported clean (review of PR #142).
    h.expect_only_one(
        "two dots sharing one data-name are reported, not collapsed into one",
        document(swarm(22), dot(300, name="req-a"), dot(400, 1, name="req-a"),
                 TICKS, label("req-a", cx(300))),
        r"a second dot declares data-name 'req-a'",
    )
    h.expect_only_one(
        "an empty data-name is reported — an identity nothing can be bound to",
        document(swarm(23), dot(300, name=""), TICKS),
        r"declares an empty data-name",
    )
    h.expect_only_one(
        "a whitespace-only data-name is empty once rendered, and reported",
        document(swarm(23), dot(300, name="  "), TICKS),
        r"declares an empty data-name",
    )

    # ── Tick lies ─────────────────────────────────────────────────────────
    h.expect_finding(
        "a tick printing a different number than it declares is reported",
        document(swarm(), tick(0), tick(400, shown="300")),
        r"prints '300' but declares 400",
    )
    h.expect_finding(
        "a tick drawn off the scale the dots set is reported",
        document(swarm(), tick(0), tick(400, position=760)),
        r"the printed axis and the drawn positions disagree",
    )
    h.expect_finding(
        "an axis with fewer than two bound ticks is reported",
        document(swarm(), tick(200)),
        r"binds 1 distinct tick value",
    )
    h.expect_finding(
        "a tick with no data-value is reported as unbound",
        document(swarm(), tick(0), tick(400, declared="omit")),
        r"no readable data-value",
    )
    h.expect_finding(
        "data-tick=\"y\" is reported — the swarm axis has no scale to tick",
        document(swarm(), TICKS, tick(2, axis="y")),
        r"the swarm axis has no scale to\s+tick",
    )
    h.expect_finding(
        "a tick printing two numeric tokens is ambiguous, not first-token-parsed",
        document(swarm(), tick(0), tick(400, shown="400 (401,000)")),
        r"prints more than one numeric token",
    )

    # ── Transforms ────────────────────────────────────────────────────────
    h.expect_finding(
        "a transform on a dot is rejected, not resolved",
        document(swarm(23),
                 dot(300, extra='transform="translate(0 80)"'), TICKS),
        r"the dot for value 300 carries transform=",
    )
    h.expect_finding(
        "an ancestor <g> transform moves every mark inside it",
        document('  <g transform="translate(0 40)">\n', swarm(), "  </g>\n",
                 TICKS),
        r"an ancestor <g>/<svg> transform",
    )
    h.expect_finding(
        "an UNCLOSED transformed group covers everything after it",
        document('  <g transform="translate(0 40)">\n', swarm(), TICKS),
        r"an ancestor <g>/<svg> transform",
    )
    h.expect_finding(
        "a transform on a bound label is rejected",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300),
                       extra='transform="translate(40 0)"')),
        r"a bound label .* carries transform=",
    )
    h.expect_finding(
        "a CSS transform declaration is rejected — no telling what it moves",
        "<style>.dot { transform: translate(0, 40px); }</style>" + honest(),
        r"a CSS `transform` declaration",
    )
    h.expect_clean(
        "text-transform in CSS is styling, not movement",
        "<style>.label { text-transform: uppercase; }</style>" + honest(),
    )
    # A transform reaches the renderer by three carriers, and the attribute is
    # only the most visible one. An inline `style="transform: …"` moved a dot,
    # a bound label, a tick and an ancestor group past every coordinate check
    # here and reported clean (review of PR #142).
    h.expect_finding(
        "an inline style transform on a dot is rejected",
        document(swarm(23),
                 dot(300, extra='style="transform: translateX(80px)"'), TICKS),
        r"the dot for value 300 carries style=",
    )
    h.expect_finding(
        "an inline style transform on a bound label is rejected",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300),
                       extra='style="transform: translate(40px, 0)"')),
        r"a bound label .* carries style=",
    )
    h.expect_finding(
        "an inline style transform on an axis tick is rejected",
        document(swarm(), tick(0),
                 tick(400, extra='style="transform: translateX(60px)"')),
        r"a bound tick .* carries style=",
    )
    h.expect_finding(
        "an inline style transform on an ancestor <g> moves every mark inside it",
        document('  <g style="transform: translateY(40px)">\n', swarm(),
                 "  </g>\n", TICKS),
        r"an ancestor <g>/<svg> style transform",
    )
    h.expect_clean(
        "text-transform in an inline style is styling, not movement",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300),
                       extra='style="text-transform: uppercase"')),
    )
    # CSS Transforms Level 2 splits the transform into four properties, so
    # `transform:` is one of four spellings and the other three moved a mark
    # with the word "transform" never appearing (greptile on PR #142).
    h.expect_finding(
        "an inline translate on a dot is rejected",
        document(swarm(23),
                 dot(300, extra='style="translate: 80px 0"'), TICKS),
        r"the dot for value 300 carries style=.*the translate property",
    )
    h.expect_finding(
        "an inline offset shorthand on a dot is rejected",
        document(
            swarm(23),
            dot(300, extra='style="offset: path(\'M0,0 L80,0\') 100%"'),
            TICKS,
        ),
        r"the dot for value 300 carries style=.*the offset property",
    )
    h.expect_finding(
        "an inline rotate on a bound label is rejected",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300), extra='style="rotate: 45deg"')),
        r"a bound label .* carries style=.*the rotate property",
    )
    h.expect_finding(
        "an inline scale on an axis tick is rejected",
        document(swarm(), tick(0),
                 tick(400, extra='style="scale: 2"')),
        r"a bound tick .* carries style=.*the scale property",
    )
    h.expect_finding(
        "an inline translate on an ancestor <g> moves every mark inside it",
        document('  <g style="translate: 0 40px">\n', swarm(),
                 "  </g>\n", TICKS),
        r"an ancestor <g>/<svg> style transform",
    )
    h.expect_finding(
        "a vendor-prefixed inline transform is not a free pass",
        document(swarm(23),
                 dot(300, extra='style="-webkit-transform: translateX(80px)"'),
                 TICKS),
        r"the dot for value 300 carries style=",
    )
    # Geometry properties are the shorter lie: CSS wins over the presentation
    # attribute, so a rule replaces the very number that was verified.
    h.expect_finding(
        "a CSS cx declaration is rejected — it overrides the verified attribute",
        "<style>circle { cx: 900px; }</style>" + honest(),
        r"a CSS `cx` declaration",
    )
    h.expect_finding(
        "a CSS translate declaration is rejected",
        "<style>.dot { translate: 80px 0; }</style>" + honest(),
        r"a CSS `translate` declaration",
    )
    h.expect_finding(
        "a CSS offset-path declaration is rejected",
        "<style>.dot { offset-path: path(\'M0,0 L80,0\'); }</style>" + honest(),
        r"a CSS `offset-path` declaration",
    )
    # The house idiom across 37 shipped examples: line-height, color, font.
    # None of it positions a mark, and firing on it would get this gate
    # switched off rather than obeyed.
    h.expect_clean(
        "line-height and color in an inline style are not movement",
        document(swarm(23), dot(300, name="req-a"), TICKS,
                 label("req-a", cx(300),
                       extra='style="line-height:1.4;color:#2d3142"')),
    )
    h.expect_clean(
        "a CSS transition naming transform is not a transform declaration",
        "<style>.dot { transition: transform 0.2s; }</style>" + honest(),
    )

    # ── Malformed markup: findings, never tracebacks, never silence ───────
    h.expect_finding(
        "a data-value circle whose attributes cannot be parsed is reported",
        document('  <circle data-value=broken cx="100" cy="230" r="4"/>\n',
                 swarm(), TICKS),
        r"could not be parsed",
    )
    h.expect_finding(
        "a dot missing cx is reported with the missing attribute named",
        document(swarm(23), dot(300, omit="cx"), TICKS),
        r"missing cx",
    )
    h.expect_finding(
        "a NaN coordinate is unreadable, not silently within every tolerance",
        document(swarm(23), dot(300, drawn_cx="NaN"), TICKS),
        r"not a finite\s+number",
    )
    h.expect_finding(
        "a zero radius is reported — an invisible dot is an uncounted omission",
        document(swarm(23), dot(300, r=0), TICKS),
        r"a dot with no area",
    )

    # ── Budgets, both ends ────────────────────────────────────────────────
    h.expect_finding(
        "19 dots fall below the documented floor",
        document(swarm(19), TICKS),
        r"19 dots against a budget of 20-300",
    )
    h.expect_finding(
        "301 dots exceed the documented ceiling",
        document(swarm(301, depth=5), TICKS),
        r"301 dots against a budget of 20-300",
    )

    # ── Fail closed ───────────────────────────────────────────────────────
    h.expect_finding(
        "three dots are too few for leave-one-out — refused, not passed",
        document(dot(100), dot(200, 1), dot(300, -1), TICKS),
        r"declares 3 verifiable dot\(s\)",
    )
    h.expect_finding(
        "a file that claims the type by filename but parses nothing is a finding",
        HEAD + TAIL,
        r"declares 0 verifiable dot",
        name="example-beeswarm-empty.html",
    )
    h.expect_finding(
        "a file that claims the type in its description is held to the contract",
        "<svg role='img'><title>t</title><desc>A beeswarm of requests."
        "</desc></svg>",
        r"declares 0 verifiable dot",
        name="fixture.html",
    )

    # ── Scope: the treaty, in both directions ─────────────────────────────
    scatter = (ASSETS / "example-scatter.html").read_text(encoding="utf-8")
    h.expect_out_of_scope(
        "the parent scatter is out of scope — its points bind nothing",
        scatter, "example-scatter-fixture.html",
    )
    slopegraph = (ASSETS / "example-slopegraph.html").read_text(encoding="utf-8")
    h.expect_out_of_scope(
        "the shipped slopegraph is out of scope — data-series is not data-value",
        slopegraph, "example-slopegraph-fixture.html",
    )
    # The treaty line itself: data-value on a <text> tick is the bubble
    # contract's grammar (and this one's), so a file whose ONLY data-value
    # sits on text must never be claimed — a source-wide regex would claim
    # every shipped bubble example.
    h.expect_out_of_scope(
        "data-value on a <text> tick alone never claims a file — the bubble "
        "contract's ticks stay unclaimed",
        "<svg role='img'><title>t</title><desc>A bubble chart of services."
        "</desc>"
        '<circle data-name="A" data-x="1" data-y="2" data-size="9" cx="81.8"'
        ' cy="230" r="4.2"/>'
        '<text data-tick="x" data-value="100" x="256" y="440">100</text>'
        "</svg>",
        "fixture.html",
    )
    h.check(
        "no shipped beeswarm file declares data-series, data-ranks or "
        "data-size, so no sibling verifier claims one",
        all(not re.search(r"data-(series|ranks|size)\s*=",
                          path.read_text(encoding="utf-8"))
            for path in SHIPPED),
    )

    # Every sibling per-file verifier present on the branch must SKIP the
    # shipped beeswarm files. Run as subprocesses so the treaty is held
    # against the siblings' real CLIs, not a re-implementation; siblings not
    # yet landed (in-flight variant PRs) are legitimately absent.
    for sibling in ("verify-slopegraph.py", "verify-bump.py",
                    "verify-bubble.py"):
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
            "%s skips all three shipped beeswarm files" % sibling,
            result.returncode == 0
            and "3 file(s) skipped as out of scope" in result.stdout,
            "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
        )

    # ── The fixture-isolation guarantees, held in place ───────────────────
    sentinel = ROOT / "example-beeswarm-fixture.html"
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
    print("OK beeswarm checker: %d case(s), both polarities" % h.count)
    return 0


def main() -> int:
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


if __name__ == "__main__":
    raise SystemExit(main())
