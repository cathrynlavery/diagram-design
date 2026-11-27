#!/usr/bin/env python3
"""Adversarial cases for verify-git-graph.py, both polarities.

Every case is named for exactly what it asserts. The negative half matters
as much as the positive: a checker that fires on an honest figure, on a
timeline, or on a sibling contract's files gets widened or switched off,
and then it guards nothing.

The scope treaty is pinned here in both directions: fixtures prove that
`data-value` on a <circle> (the beeswarm contract) never claims a file for
this checker, and every sibling per-file verifier present on the branch is
run as a subprocess against the shipped git-graph examples and must skip
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

verify = __import__("verify-git-graph")

ASSETS = ROOT / "skills/diagrams-design-quind/assets"
SHIPPED = [ASSETS / name for name in (
    "example-git-graph.html", "example-git-graph-dark.html",
    "example-git-graph-full.html",
)]

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title></head><body>
<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="git-graph-title git-graph-desc">
  <title id="git-graph-title">Feature merge on main</title>
  <desc id="git-graph-desc">Git graph fixture. Main on top; a feature branch merges back.</desc>
"""
TAIL = "</svg></body></html>\n"

MAIN_Y = 240
FEAT_Y = 380
ORIGIN = 280
PITCH = 120
INK = "#0e1920"
ACCENT = "#cc3b10"


def col(index: int) -> float:
    return ORIGIN + index * PITCH


def lane(name: str, y: float, x1: float, x2: float) -> str:
    return (
        '  <line data-lane="%s" data-y="%g" x1="%g" y1="%g" x2="%g" y2="%g" '
        'stroke="#5b6770"/>\n'
        '  <text data-lane="%s" x="88" y="%g">%s</text>\n'
        % (name, y, x1, y, x2, y, name, y + 4, name)
    )


def commit(name: str, lane_name: str, column: int, y: float, *,
           merge=False, fill=INK, cx=None, cy=None, extra=""):
    cx = col(column) if cx is None else cx
    cy = y if cy is None else cy
    kind = ' data-kind="merge"' if merge else ""
    extra_attr = (" " + extra) if extra else ""
    return (
        '  <circle data-commit="%s" data-lane="%s" data-column="%d"%s '
        'cx="%g" cy="%g" r="8" fill="%s"%s/>\n'
        % (name, lane_name, column, kind, cx, cy, fill, extra_attr)
    )


def connector(frm: str, to: str, d: str, extra="") -> str:
    extra_attr = (" " + extra) if extra else ""
    return (
        '  <path data-from="%s" data-to="%s" d="%s" fill="none" '
        'stroke="#5b6770"%s/>\n' % (frm, to, d, extra_attr)
    )


def tag(label: str, commit_name: str, column: int, y: float) -> str:
    return (
        '  <text data-tag="%s" data-commit="%s" x="%g" y="%g">%s</text>\n'
        % (label, commit_name, col(column), y, label)
    )


def honest(*extra: str) -> str:
    """Two lanes, four commits, one merge, one tag, one coral."""
    return document(
        lane("main", MAIN_Y, col(0), col(3)),
        lane("feat", FEAT_Y, col(1), col(2)),
        connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(3))),
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
        connector("c1", "c2", "M %g,%g H %g" % (col(1), FEAT_Y, col(2))),
        connector("c2", "m1", "M %g,%g H %g V %g" % (col(2), FEAT_Y, col(3), MAIN_Y)),
        commit("c0", "main", 0, MAIN_Y),
        commit("c1", "feat", 1, FEAT_Y),
        commit("c2", "feat", 2, FEAT_Y),
        commit("m1", "main", 3, MAIN_Y, merge=True, fill=ACCENT),
        tag("v1", "m1", 3, MAIN_Y - 28),
        *extra,
    )


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


class Harness:
    def __init__(self):
        self.failures = 0
        self.count = 0
        self.dir = Path(tempfile.mkdtemp(prefix="git-graph-fixtures-"))

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-git-graph-fixture.html") -> list:
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
        detected = verify.looks_like_git_graph(
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

    h.expect_clean("an honest synthetic git graph passes", honest())

    def gapped() -> str:
        """Four commits on columns 0, 1, 2, 4 — an unused column is still one pitch."""
        return document(
            lane("main", MAIN_Y, col(0), col(4)),
            lane("feat", FEAT_Y, col(1), col(2)),
            connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(4))),
            connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
            connector("c1", "c2", "M %g,%g H %g" % (col(1), FEAT_Y, col(2))),
            connector("c2", "m1", "M %g,%g H %g V %g" % (col(2), FEAT_Y, col(4), MAIN_Y)),
            commit("c0", "main", 0, MAIN_Y),
            commit("c1", "feat", 1, FEAT_Y),
            commit("c2", "feat", 2, FEAT_Y),
            commit("m1", "main", 4, MAIN_Y, merge=True, fill=ACCENT),
            tag("v1", "m1", 4, MAIN_Y - 28),
        )

    h.expect_clean(
        "empty columns on a shared pitch pass",
        gapped(),
    )

    def styled(css: str) -> str:
        return honest().replace("</head>", "<style>%s</style></head>" % css, 1)

    h.expect_clean(
        "quoted CSS data that looks like transform is not a declaration",
        styled('body { --notes: "literal;transform:translate(999px)" }'),
    )
    h.expect_clean(
        "single-quoted CSS data that looks like transform is not a declaration",
        styled("body { --notes: 'literal;transform:translate(999px)' }"),
    )
    h.expect_named(
        "a live transform in a <style> rule is a finding",
        styled("rect { transform: translate(999px) }"),
        "positions a mark with CSS",
    )
    h.expect_named(
        "a live transform after a quoted string is still a finding",
        styled('body { --a: "x" } rect { transform: translate(999px) }'),
        "positions a mark with CSS",
    )
    h.expect_clean(
        "a layout-only width/height rule passes",
        styled("svg { display: block; width: 100% }"),
    )
    h.expect_named(
        "a <style> rule that moves marks inside <!-- --> is still refused",
        honest().replace(
            "</head>",
            "<style><!--\npath{transform:translate(1px)}\n--></style></head>",
            1,
        ),
        "positions a mark with CSS",
    )

    one_parent = honest().replace(
        connector("c2", "m1", "M %g,%g H %g V %g" % (col(2), FEAT_Y, col(3), MAIN_Y)),
        "",
        1,
    )
    h.expect_named(
        "a merge with one parent is a finding",
        one_parent,
        "exactly two incoming connectors",
    )

    h.expect_named(
        "a merge elbow that passes through an unrelated commit is a finding",
        honest(commit("c3", "feat", 3, FEAT_Y)),
        "passes through commit 'c3'",
    )

    backwards = honest().replace(
        connector("c1", "c2", "M %g,%g H %g" % (col(1), FEAT_Y, col(2))),
        connector("c2", "c1", "M %g,%g H %g" % (col(2), FEAT_Y, col(1))),
        1,
    )
    h.expect_named(
        "a connector going backwards is a finding",
        backwards,
        "right-to-left",
    )

    branch_along_parent = honest().replace(
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
        connector("c0", "c1", "M %g,%g H %g V %g" % (col(0), MAIN_Y, col(1), FEAT_Y)),
        1,
    )
    h.expect_named(
        "a branch that runs along the parent lane is a finding",
        branch_along_parent,
        "turns at the parent column",
    )
    h.expect_named(
        "a branch collinear with the parent lane is a finding",
        branch_along_parent,
        "collinear with lane",
    )

    merge_along_dest = honest().replace(
        connector("c2", "m1", "M %g,%g H %g V %g" % (col(2), FEAT_Y, col(3), MAIN_Y)),
        connector("c2", "m1", "M %g,%g V %g H %g" % (col(2), FEAT_Y, MAIN_Y, col(3))),
        1,
    )
    h.expect_named(
        "a merge that runs along the destination lane is a finding",
        merge_along_dest,
        "turns at the merge column",
    )
    h.expect_named(
        "a merge collinear with the destination lane is a finding",
        merge_along_dest,
        "collinear with lane",
    )

    h.expect_named(
        "a commit off its lane is a finding",
        honest().replace(
            commit("c1", "feat", 1, FEAT_Y),
            commit("c1", "feat", 1, FEAT_Y, cy=FEAT_Y + 24),
            1,
        ),
        "off its lane",
    )

    h.expect_named(
        "a commit off the shared pitch is a finding",
        honest().replace(
            commit("c1", "feat", 1, FEAT_Y),
            commit("c1", "feat", 1, FEAT_Y, cx=col(1) + 40),
            1,
        ),
        "shared pitch",
    )

    h.expect_named(
        "a tag attached to a missing commit is a finding",
        honest().replace(
            tag("v1", "m1", 3, MAIN_Y - 28),
            tag("v1", "no-such", 3, MAIN_Y - 28),
            1,
        ),
        "does not exist",
    )

    three_coral = honest().replace(
        commit("c1", "feat", 1, FEAT_Y),
        commit("c1", "feat", 1, FEAT_Y, fill=ACCENT),
        1,
    ).replace(
        commit("c2", "feat", 2, FEAT_Y),
        commit("c2", "feat", 2, FEAT_Y, fill=ACCENT),
        1,
    )
    h.expect_named(
        "three coral commits are a finding",
        three_coral,
        "at most two coral commits",
    )

    style_coral = honest().replace(
        commit("c1", "feat", 1, FEAT_Y),
        commit("c1", "feat", 1, FEAT_Y, extra='style="fill:#cc3b10"'),
        1,
    ).replace(
        commit("c2", "feat", 2, FEAT_Y),
        commit("c2", "feat", 2, FEAT_Y, extra='style="fill:#cc3b10"'),
        1,
    )
    h.expect_named(
        "three coral commits via style fill are a finding",
        style_coral,
        "at most two coral commits",
    )

    inherited_coral = honest().replace(
        commit("c1", "feat", 1, FEAT_Y),
        '  <g fill="#cc3b10">\n'
        '  <circle data-commit="c1" data-lane="feat" data-column="1" '
        'cx="%g" cy="%g" r="8"/>\n  </g>\n' % (col(1), FEAT_Y),
        1,
    ).replace(
        commit("c2", "feat", 2, FEAT_Y),
        commit("c2", "feat", 2, FEAT_Y, fill=ACCENT),
        1,
    )
    h.expect_named(
        "three coral commits via inherited fill are a finding",
        inherited_coral,
        "at most two coral commits",
    )

    overlapping = honest().replace(
        lane("feat", FEAT_Y, col(1), col(2)),
        lane("feat", MAIN_Y + 40, col(1), col(2)),
        1,
    ).replace(
        commit("c1", "feat", 1, FEAT_Y),
        commit("c1", "feat", 1, MAIN_Y + 40),
        1,
    ).replace(
        commit("c2", "feat", 2, FEAT_Y),
        commit("c2", "feat", 2, MAIN_Y + 40),
        1,
    )
    h.expect_named(
        "overlapping lanes are a finding",
        overlapping,
        "lanes do not overlap",
    )

    h.expect_named(
        "a fifth lane at the 140px pitch falls off the 720px canvas",
        honest(lane("l2", 520, col(1), col(2)), lane("l3", 660, col(1), col(2)),
               lane("l4", 800, col(1), col(2))),
        "outside the 720-high viewBox",
    )
    h.expect_clean(
        "five lanes at the 96px pitch stay on the 720px canvas",
        honest(lane("l2", 476, col(1), col(2)), lane("l3", 572, col(1), col(2)),
               lane("l4", 668, col(1), col(2))),
    )

    h.expect_named(
        "a transform on a commit is a finding",
        honest().replace(
            commit("c1", "feat", 1, FEAT_Y),
            commit("c1", "feat", 1, FEAT_Y, extra='transform="translate(8,0)"'),
            1,
        ),
        "positions a mark",
    )

    for hide in ('style="display:none"', 'display="none"',
                 'visibility="hidden"', 'opacity="0"'):
        h.expect_named(
            "a bound commit with %s is a finding" % hide,
            honest().replace(
                commit("c1", "feat", 1, FEAT_Y),
                commit("c1", "feat", 1, FEAT_Y, extra=hide),
                1,
            ),
            "hides a bound mark",
        )

    c2_m1 = connector("c2", "m1", "M %g,%g H %g V %g"
                      % (col(2), FEAT_Y, col(3), MAIN_Y))
    for hide in ('stroke="none"', 'stroke="transparent"',
                 'stroke="rgba(0,0,0,0)"', 'style="stroke:none"'):
        h.expect_named(
            "a connector with %s is a finding" % hide,
            honest().replace(
                c2_m1, c2_m1.replace('stroke="#5b6770"', hide), 1
            ),
            "no visible stroke",
        )
    for hide in ('stroke-width="0"', 'style="stroke-width:0px"'):
        h.expect_named(
            "a connector with %s is a finding" % hide,
            honest().replace(c2_m1, c2_m1.replace("/>", " %s/>" % hide), 1),
            "stroke-width",
        )
    h.expect_named(
        "a connector with no stroke anywhere is a finding",
        honest().replace(
            c2_m1, c2_m1.replace(' stroke="#5b6770"', ""), 1
        ),
        "no visible stroke",
    )
    h.expect_named(
        "a connector inheriting stroke-width 0 from its group is a finding",
        honest().replace(
            c2_m1,
            '  <g stroke-width="0">\n' + c2_m1 + "  </g>\n", 1
        ),
        "stroke-width",
    )
    h.expect_clean(
        "a connector inheriting its stroke from a group passes",
        honest().replace(
            c2_m1,
            '  <g stroke="#5b6770" stroke-width="1.5">\n'
            + c2_m1.replace(' stroke="#5b6770"', "") + "  </g>\n", 1
        ),
    )
    h.expect_clean(
        "a connector in a visible-stroke group nested in a stroke:none group passes",
        honest().replace(
            c2_m1,
            '  <g stroke="none">\n  <g stroke="#5b6770">\n'
            + c2_m1.replace(' stroke="#5b6770"', "") + "  </g>\n  </g>\n", 1
        ),
    )
    h.expect_clean(
        "a connector in a positive stroke-width group nested in a zero-width group passes",
        honest().replace(
            c2_m1,
            '  <g stroke-width="0">\n  <g stroke-width="1.5">\n'
            + c2_m1 + "  </g>\n  </g>\n", 1
        ),
    )
    h.expect_named(
        "a connector in a stroke:none group nested in a visible-stroke group is a finding",
        honest().replace(
            c2_m1,
            '  <g stroke="#5b6770">\n  <g stroke="none">\n'
            + c2_m1.replace(' stroke="#5b6770"', "") + "  </g>\n  </g>\n", 1
        ),
        "no visible stroke",
    )
    h.expect_named(
        "an inline stroke:none outranks a visible stroke attribute",
        honest().replace(
            c2_m1, c2_m1.replace("/>", ' style="stroke: none"/>'), 1
        ),
        "no visible stroke",
    )

    shipped_light = SHIPPED[0].read_text(encoding="utf-8")
    shipped_c2 = (
        '<circle data-commit="c2" data-lane="feat/billing" data-column="2" '
        'cx="520" cy="520" r="8" fill="#0e1920"/>'
    )
    h.check("shipped example contains expected c2 circle", shipped_c2 in shipped_light)
    h.expect_named(
        'shipped c2 circle changed to fill="none" is a finding',
        shipped_light.replace(
            shipped_c2, shipped_c2.replace('fill="#0e1920"', 'fill="none"'), 1
        ),
        "commit c2 has no visible paint",
    )

    c2_dot = commit("c2", "feat", 2, FEAT_Y)
    for bad_fill in ("none", "transparent", "rgba(0,0,0,0)"):
        h.expect_named(
            "a commit with fill=%r and no stroke is a finding" % bad_fill,
            honest().replace(
                c2_dot, commit("c2", "feat", 2, FEAT_Y, fill=bad_fill), 1
            ),
            "commit c2 has no visible paint",
        )
    h.expect_named(
        "an inline style fill:none outranks a visible fill attribute",
        honest().replace(
            c2_dot, commit("c2", "feat", 2, FEAT_Y, extra='style="fill: none"'), 1
        ),
        "commit c2 has no visible paint",
    )
    c2_unset = (
        '  <circle data-commit="c2" data-lane="feat" data-column="2" '
        'cx="%g" cy="%g" r="8"/>\n' % (col(2), FEAT_Y)
    )
    h.expect_named(
        'a commit inheriting fill="none" from an enclosing <g fill="none"> is a finding',
        honest().replace(
            c2_dot, '  <g fill="none">\n' + c2_unset + "  </g>\n", 1
        ),
        "commit c2 has no visible paint",
    )
    h.expect_named(
        'a commit in a fill="none" group nested in a visible-fill group is a finding',
        honest().replace(
            c2_dot,
            '  <g fill="#0e1920">\n  <g fill="none">\n'
            + c2_unset + "  </g>\n  </g>\n",
            1,
        ),
        "commit c2 has no visible paint",
    )
    h.expect_clean(
        'a commit in a visible-fill group nested in a fill="none" group passes',
        honest().replace(
            c2_dot,
            '  <g fill="none">\n  <g fill="#0e1920">\n'
            + c2_unset + "  </g>\n  </g>\n",
            1,
        ),
    )
    h.expect_clean(
        "a commit with unset fill and no enclosing fill uses SVG default black and passes",
        honest().replace(c2_dot, c2_unset, 1),
    )
    h.expect_clean(
        'a commit with fill="none" and a visible stroke passes',
        honest().replace(
            c2_dot,
            commit("c2", "feat", 2, FEAT_Y, fill="none",
                   extra='stroke="#0e1920" stroke-width="1.5"'),
            1,
        ),
    )
    h.expect_clean(
        'a commit with fill="none" inheriting a visible stroke from a group passes',
        honest().replace(
            c2_dot,
            '  <g stroke="#0e1920" stroke-width="1.5">\n'
            + commit("c2", "feat", 2, FEAT_Y, fill="none")
            + "  </g>\n",
            1,
        ),
    )
    for bad_stroke in ('stroke="none"', 'stroke="transparent"',
                       'stroke="#0e1920" stroke-width="0"',
                       'stroke="#0e1920" style="stroke-width:0px"'):
        h.expect_named(
            'a commit with fill="none" and %s is a finding' % bad_stroke,
            honest().replace(
                c2_dot,
                commit("c2", "feat", 2, FEAT_Y, fill="none", extra=bad_stroke),
                1,
            ),
            "commit c2 has no visible paint",
        )
    h.expect_named(
        'a commit with fill="none" and stroke inheriting stroke-width 0 is a finding',
        honest().replace(
            c2_dot,
            '  <g stroke-width="0">\n'
            + commit("c2", "feat", 2, FEAT_Y, fill="none", extra='stroke="#0e1920"')
            + "  </g>\n",
            1,
        ),
        "commit c2 has no visible paint",
    )

    h.expect_named(
        "a <style> rule that hides a bound commit is a finding",
        styled('[data-commit="c2"] { display: none; }'),
        "hides or resets a bound mark",
    )
    h.expect_clean(
        "a hiding rule aimed at page chrome passes",
        styled(".modal { display: none }"),
    )

    disconnected = honest().replace(
        connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(3))),
        connector("c0", "m1", "M %g,%g M %g,%g" % (col(0), MAIN_Y, col(3), MAIN_Y)),
        1,
    )
    h.expect_named(
        "a second moveto is not a continuous connector",
        disconnected,
        "single continuous orthogonal",
    )
    dropped_curve = honest().replace(
        connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(3))),
        connector("c0", "m1", "M %g,%g C 400,240 520,240 %g,%g"
                  % (col(0), MAIN_Y, col(3), MAIN_Y)),
        1,
    )
    h.expect_named(
        "an unsupported path command is not dropped",
        dropped_curve,
        "single continuous orthogonal",
    )

    wiggly = honest().replace(
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
        connector("c0", "c1", "M 280,240 V 380 H 320 V 420 H 360 V 380 H 400"),
        1,
    )
    h.expect_named(
        "a branch that leaves its route after the first turn is a finding",
        wiggly,
        "leaves its branch route",
    )
    h.expect_named(
        "a branch that turns more than once is a finding",
        wiggly,
        "turns more than once",
    )
    diagonal = honest().replace(
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
        connector("c0", "c1", "M 280,240 V 380 H 320 L 360,420 L 400,380"),
        1,
    )
    h.expect_named(
        "a later diagonal segment is a finding",
        diagonal,
        "diagonal segment",
    )

    overlap_cell = honest().replace(
        "</svg>",
        commit("duplicate", "main", 0, MAIN_Y) + "</svg>",
        1,
    )
    h.expect_named(
        "two commits on the same lane and column are a finding",
        overlap_cell,
        "overlapping dots cannot share a cell",
    )

    shared_vertical = document(
        lane("main", MAIN_Y, col(0), col(5)),
        lane("release", FEAT_Y, col(3), col(4)),
        lane("feat", 520, col(1), col(2)),
        connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(3))),
        connector("m1", "m2", "M %g,%g H %g" % (col(3), MAIN_Y, col(5))),
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, 520, col(1))),
        connector("c1", "c2", "M %g,%g H %g" % (col(1), 520, col(2))),
        connector("c2", "m1", "M %g,%g H %g V %g" % (col(2), 520, col(3), MAIN_Y)),
        connector("m1", "r0", "M %g,%g V %g H %g" % (col(3), MAIN_Y, FEAT_Y, col(4))),
        connector("r0", "m2", "M %g,%g H %g V %g" % (col(4), FEAT_Y, col(5), MAIN_Y)),
        commit("c0", "main", 0, MAIN_Y),
        commit("c1", "feat", 1, 520),
        commit("c2", "feat", 2, 520),
        commit("m1", "main", 3, MAIN_Y, merge=True, fill=ACCENT),
        commit("r0", "release", 4, FEAT_Y),
        commit("m2", "main", 5, MAIN_Y, merge=True),
        tag("v1", "m1", 3, MAIN_Y - 28),
    )
    h.expect_named(
        "a feature merge and a release branch sharing a vertical are a finding",
        shared_vertical,
        "may meet at a commit, not share a segment",
    )

    h.expect_named(
        "three commits is fail-closed",
        document(
            lane("main", MAIN_Y, col(0), col(2)),
            lane("feat", FEAT_Y, col(1), col(1)),
            connector("c0", "m1", "M %g,%g H %g" % (col(0), MAIN_Y, col(2))),
            connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
            connector("c1", "m1", "M %g,%g H %g V %g" % (col(1), FEAT_Y, col(2), MAIN_Y)),
            commit("c0", "main", 0, MAIN_Y),
            commit("c1", "feat", 1, FEAT_Y),
            commit("m1", "main", 2, MAIN_Y, merge=True, fill=ACCENT),
        ),
        "3 verifiable",
    )

    h.expect_named(
        "one lane is fail-closed",
        document(
            lane("main", MAIN_Y, col(0), col(3)),
            connector("c0", "c1", "M %g,%g H %g" % (col(0), MAIN_Y, col(1))),
            connector("c1", "c2", "M %g,%g H %g" % (col(1), MAIN_Y, col(2))),
            connector("c2", "c3", "M %g,%g H %g" % (col(2), MAIN_Y, col(3))),
            commit("c0", "main", 0, MAIN_Y),
            commit("c1", "main", 1, MAIN_Y),
            commit("c2", "main", 2, MAIN_Y),
            commit("c3", "main", 3, MAIN_Y, merge=True),
        ),
        "1 verifiable lane",
    )

    no_merge = document(
        lane("main", MAIN_Y, col(0), col(3)),
        lane("feat", FEAT_Y, col(1), col(2)),
        connector("c0", "c3", "M %g,%g H %g" % (col(0), MAIN_Y, col(3))),
        connector("c0", "c1", "M %g,%g V %g H %g" % (col(0), MAIN_Y, FEAT_Y, col(1))),
        connector("c1", "c2", "M %g,%g H %g" % (col(1), FEAT_Y, col(2))),
        commit("c0", "main", 0, MAIN_Y),
        commit("c1", "feat", 1, FEAT_Y),
        commit("c2", "feat", 2, FEAT_Y),
        commit("c3", "main", 3, MAIN_Y),
    )
    h.expect_named(
        "no merge commit is fail-closed",
        no_merge,
        "no merge commit",
    )

    h.expect_out_of_scope(
        "a timeline is not a git graph",
        "<svg role='img'><title>t</title><desc>Events on a calendar.</desc>"
        '<circle cx="80" cy="80" r="6"/>'
        "</svg>",
        "example-timeline-fixture.html",
    )

    h.expect_out_of_scope(
        "data-value on a <circle> never claims a file — the beeswarm contract",
        "<svg role='img'><title>t</title><desc>A beeswarm of requests.</desc>"
        '<circle data-value="90" cx="260" cy="230" r="4"/>'
        "</svg>",
        "fixture.html",
    )

    h.check(
        "no shipped git-graph file declares data-value on a circle, "
        "data-q1, data-span, data-series, data-ranks or data-size, so no "
        "sibling verifier claims one",
        all(not re.search(r"<circle[^>]*data-value\s*=",
                          path.read_text(encoding="utf-8"))
            and not re.search(r"data-(q1|span|series|ranks|size)\s*=",
                              path.read_text(encoding="utf-8"))
            for path in SHIPPED),
    )

    for sibling in ("verify-arc-diagram.py", "verify-beeswarm.py",
                    "verify-box-plot.py", "verify-bubble.py",
                    "verify-slopegraph.py", "verify-bump.py"):
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
            "%s skips all three shipped git-graph files" % sibling,
            result.returncode == 0
            and "3 file(s) skipped as out of scope" in result.stdout,
            "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
        )

    sentinel = ROOT / "example-git-graph-fixture.html"
    existed = sentinel.exists()
    if existed:
        original = sentinel.read_bytes()
    else:
        original = b"KEEP ME\n"
        sentinel.write_bytes(original)
    try:
        h.run(honest())
        h.check(
            "a pre-existing file sharing a fixture name is never touched",
            sentinel.exists() and sentinel.read_bytes() == original,
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
    print("OK git-graph checker: %d case(s), both polarities" % h.count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
