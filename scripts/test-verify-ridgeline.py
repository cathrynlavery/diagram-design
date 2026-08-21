#!/usr/bin/env python3
"""Adversarial tests for verify-ridgeline.py — both polarities.

Per ADR 0005, a geometric contract is a checker plus fixtures proving it fires
when it should and stays quiet when it shouldn't. Each mutation below renders
perfectly and no other gate would catch it: one ridge drawn on its own
amplitude, a baseline nudged off the pitch to buy headroom, a spline through
binned counts, a printed range wider than the mass it claims, a name label
sitting on a neighbour's row.

The synthetic figures at the end prove the checker reads the FIGURE's own
amplitude and pitch rather than memorising the shipped layout: a valid ridgeline
at a different top, pitch and scale must pass, and the budget rules must fire at
BOTH ends on counts the shipped example cannot be mutated into.

The last case pins the scope treaty with the sibling Line-variant checkers.
`data-bins` on a `<path>` is this contract's vocabulary; `data-series`,
`data-ranks` and `data-layer` belong to the slopegraph, bump and streamgraph
gates. Every sibling checker present in the tree is handed the ridgeline
examples directly and must skip them without a word — a sibling that claimed one
would reject it for lacking elements it never said it had. The reverse direction
is asserted too: this checker must skip the siblings' shipped examples.

Usage: python3 scripts/test-verify-ridgeline.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-ridgeline.py"
GOOD = ROOT / "skills/diagram-design/assets/example-ridgeline.html"

# The sibling Line-variant gates. Any that exists in the tree must skip the
# ridgeline examples rather than claim them; the ones not yet landed are absent,
# and their absence is printed rather than passed over in silence.
SIBLINGS = ["verify-slopegraph.py", "verify-bump.py", "verify-streamgraph.py"]
RIDGELINES = sorted((ROOT / "skills/diagram-design/assets").glob("example-ridgeline*.html"))

CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# Anchors, all literal excerpts of the shipped example. A fixture that fails to
# build means the example moved, which is itself worth knowing.
FOCAL_D = ('d="M320,320 L350,317.6 L380,305.6 L410,279.2 L440,269.6 L470,286.4 '
           'L500,300.8 L530,305.6 L560,303.2 L590,298.4 L620,303.2 L650,310.4 L680,320 Z"')
FOCAL_PATH = ('<path data-ridge="checkout-api" data-baseline="320" '
              'data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0" '
              + FOCAL_D +
              ' fill="rgba(235,108,54,0.16)" stroke="#eb6c36" stroke-width="2.4" '
              'stroke-linejoin="round"/>')
# The same ridge redrawn at 3.6px per unit instead of the figure's 2.4. Every
# vertex still sits on a straight, closed outline over the same bins; only the
# scale is private. This is the defect the type exists to prevent.
PRIVATE_AMPLITUDE_D = ('d="M320,320 L350,316.4 L380,298.4 L410,258.8 L440,244.4 '
                       'L470,269.6 L500,291.2 L530,298.4 L560,294.8 L590,287.6 '
                       'L620,294.8 L650,305.6 L680,320 Z"')
REPORT_RULE = ('<line data-ridge="report-export" data-role="baseline" x1="320" y1="376" '
               'x2="680" y2="376" stroke="rgba(45,49,66,0.25)" stroke-width="1"/>')


def invoke(argv):
    result = subprocess.run(
        argv, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=CHILD_ENV,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def run(*paths):
    return invoke([sys.executable, str(CHECKER), *(str(p) for p in paths)])


def write(directory, name, source):
    path = directory / name
    path.write_text(source, encoding="utf-8", newline="\n")
    return path


def case(failures, directory, name, source, original, expect, describe):
    """One mutation: it must be a real edit, and it must be rejected."""
    if source == original:
        failures.append("could not build the %s fixture (anchor moved)" % name)
        return
    code, output = run(write(directory, "%s.html" % name, source))
    if code == 0:
        failures.append("%s was accepted" % describe)
    elif expect not in output:
        failures.append("%s was reported without the expected reason: %s"
                        % (describe, output.strip()))
    else:
        print("OK: %s is rejected" % describe)


def hump(n_bins, peak_at, height=12, step=3):
    """A closed distribution: zero at both ends, one interior peak."""
    values = []
    for j in range(n_bins):
        if j in (0, n_bins - 1):
            values.append(0)
        else:
            values.append(max(0, height - step * abs(j - peak_at)))
    return values


def synthetic(n_ridges, n_bins, top=100, pitch=40, amp=2.0, x0=200, dx=20, unit=10):
    """A minimal valid ridgeline: n_ridges over n_bins, on its own grid."""
    xs = [x0 + i * dx for i in range(n_bins)]
    parts = [
        '<html><head><title>synthetic ridgeline</title></head><body>',
        '<svg viewBox="0 0 2000 2000" role="img" aria-labelledby="t d">',
        '<title id="t">synthetic ridgeline</title>',
        '<desc id="d">ridgeline fixture</desc>',
    ]
    for index, (x, value) in enumerate(((xs[0], 0), (xs[-1], (n_bins - 1) * unit))):
        parts.append('<text data-tick="%d" data-bin="%d" x="%d" y="900">%d</text>'
                     % (index, value, x, value))
    for s in range(n_ridges):
        baseline = top + s * pitch
        values = hump(n_bins, 1 + (s % max(1, n_bins - 2)))
        pts = ["%g,%g" % (x, baseline - amp * v) for x, v in zip(xs, values)]
        d = "M" + pts[0] + " " + " ".join("L" + p for p in pts[1:]) + " Z"
        focal = s == 0
        stroke = "#eb6c36" if focal else "rgba(45,49,66,0.70)"
        width = "2.4" if focal else "1.2"
        live = [i for i, v in enumerate(values) if v > 0]
        parts.append('<line data-ridge="r%d" data-role="baseline" x1="%d" y1="%g" '
                     'x2="%d" y2="%g" stroke="rgba(45,49,66,0.25)" stroke-width="1"/>'
                     % (s, xs[0], baseline, xs[-1], baseline))
        parts.append('<path data-ridge="r%d" data-baseline="%g" data-bins="%s" d="%s" '
                     'fill="rgba(45,49,66,0.12)" stroke="%s" stroke-width="%s"/>'
                     % (s, baseline, ",".join(str(v) for v in values), d, stroke, width))
        parts.append('<text data-ridge="r%d" data-role="name" x="%d" y="%g" '
                     'text-anchor="end">r%d</text>' % (s, xs[0] - 16, baseline + 3.5, s))
        parts.append('<text data-ridge="r%d" data-role="range" x="%d" y="%g">%d–%d ms</text>'
                     % (s, xs[-1] + 16, baseline + 3.5,
                        live[0] * unit, live[-1] * unit))
    parts.append("</svg></body></html>")
    return "\n".join(parts)


def main() -> int:
    source = GOOD.read_text(encoding="utf-8")
    failures = []

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # 1. The shipped example must pass untouched.
        code, output = run(GOOD)
        if code != 0:
            failures.append("clean example was rejected: %s" % output.strip())
        else:
            print("OK: the shipped ridgeline passes")

        # 2. THE defect: one ridge redrawn on its own amplitude. Every other
        #    check stays green — the outline is straight, closed, on the shared
        #    bins, and its labels are correct.
        case(
            failures, directory, "private-amplitude",
            source.replace(FOCAL_D, PRIVATE_AMPLITUDE_D, 1),
            source, "one amplitude",
            "a ridge drawn on its own amplitude",
        )

        # 3. A baseline nudged off the pitch to buy one ridge headroom, with its
        #    rule, its outline and its labels all moved to match.
        case(
            failures, directory, "off-pitch",
            source.replace('data-baseline="320"', 'data-baseline="328"', 1)
                  .replace(FOCAL_D, FOCAL_D.replace(",320 ", ",328 ")
                                           .replace(",320\"", ",328\""), 1)
                  .replace('<line data-ridge="checkout-api" data-role="baseline" x1="320" '
                           'y1="320" x2="680" y2="320"',
                           '<line data-ridge="checkout-api" data-role="baseline" x1="320" '
                           'y1="328" x2="680" y2="328"', 1),
            source, "fixed pitch",
            "a baseline nudged off the stack's pitch",
        )

        # 4. The drawn zero and the measured zero pulled apart: only the rule moves.
        case(
            failures, directory, "rule-off-row",
            source.replace(REPORT_RULE, REPORT_RULE.replace('y1="376"', 'y1="368"')
                                                   .replace('y2="376"', 'y2="368"'), 1),
            source, "drawn zero and the measured zero",
            "a baseline rule drawn off its ridge's row",
        )

        # 5. A ridge with no drawn baseline at all.
        case(
            failures, directory, "rule-missing",
            source.replace("      " + REPORT_RULE + "\n", "", 1),
            source, "no baseline rule",
            "a ridge with no drawn baseline",
        )

        # 6. A spline through binned counts invents extrema the sample never had.
        case(
            failures, directory, "spline",
            source.replace("M320,320 L350,317.6 L380,305.6",
                           "M320,320 C330,320 340,317.6 350,317.6 L380,305.6", 1),
            source, "invents extrema",
            "a spline between two bins",
        )

        # 7. Relative commands render against the previous point while the parsed
        #    numbers read as absolute, so folding case would certify a figure at
        #    positions it never drew. Refused outright.
        case(
            failures, directory, "relative-path",
            source.replace(FOCAL_D,
                           'd="M320,320 l30,-2.4 l30,-12 l30,-26.4 l30,-9.6 l30,16.8 '
                           'l30,14.4 l30,4.8 l30,-2.4 l30,-4.8 l30,4.8 l30,7.2 l30,9.6 z"',
                           1),
            source, "relative path commands",
            "a ridge drawn with relative path commands",
        )

        # 7b. `z` is NOT a relative command — closepath takes no coordinates, so
        #     it has no relative form and the two spellings are one command.
        #     Rejecting it would be a false positive on valid SVG.
        lowered = source.replace(FOCAL_D, FOCAL_D.replace(" Z\"", " z\""), 1)
        if lowered == source:
            failures.append("could not build the lowercase-z fixture (anchor moved)")
        else:
            code, output = run(write(directory, "lowercase-z.html", lowered))
            if code != 0:
                failures.append("a path closed with lowercase z was rejected: %s"
                                % output.strip())
            else:
                print("OK: lowercase z is accepted (it is not a relative command)")

        # 7b-ii. `e` and `E` are letters INSIDE a valid coordinate. `4.4e2` is
        #     440, one number and no command, so a checker that scans for
        #     [A-Za-z] separately invents a command and rejects a good path.
        #     Positive case, and a falsified twin proving the number was read as
        #     the value it spells rather than skipped.
        exponent = source.replace("L440,269.6", "L4.4e2,269.6", 1)
        if exponent == source:
            failures.append("could not build the exponent fixture (anchor moved)")
        else:
            code, output = run(write(directory, "exponent.html", exponent))
            if code != 0:
                failures.append("a coordinate in scientific notation was rejected: %s"
                                % output.strip())
            else:
                print("OK: a coordinate in scientific notation is accepted")
        case(
            failures, directory, "exponent-lie",
            source.replace("L440,269.6", "L4.4e2,2.7e2", 1),
            source, "one amplitude",
            "a falsified coordinate written in scientific notation",
        )

        # 7c. Implicit command repetition (`L a,b c,d`) is legal SVG, but this
        #     checker pairs commands with points positionally, so it must say so
        #     rather than mis-pair them behind a green tick.
        case(
            failures, directory, "implicit-repeat",
            source.replace("L350,317.6 L380,305.6", "L350,317.6 380,305.6", 1),
            source, "one explicit command per vertex",
            "a path using implicit command repetition",
        )

        # 8. A distribution cut off mid-mass: the last bin stops above the
        #    baseline, so the outline closes as a cliff and reads as data.
        case(
            failures, directory, "clipped-end",
            source.replace('data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0"',
                           'data-bins="0,1,6,17,21,14,8,6,7,9,7,4,3"', 1)
                  .replace("L650,310.4 L680,320 Z", "L650,310.4 L680,312.8 Z", 1),
            source, "starts or ends off its baseline",
            "a distribution clipped mid-mass",
        )

        # 9. A vertex drawn through the baseline. A share below zero is not a share.
        case(
            failures, directory, "below-baseline",
            source.replace("L650,310.4 L680,320 Z", "L650,326 L680,320 Z", 1),
            source, "never dips through it",
            "a vertex drawn below its own baseline",
        )
        case(
            failures, directory, "negative-bin",
            source.replace('data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0"',
                           'data-bins="0,1,6,17,21,14,8,6,7,9,7,-4,0"', 1),
            source, "negative bin",
            "a ridge declaring a negative bin",
        )

        # 10. A ridge sampled on its own x positions cannot be compared down the
        #     column: a peak at one x stops meaning one latency.
        case(
            failures, directory, "own-bins",
            source.replace("L590,298.4 L620,303.2", "L594,298.4 L620,303.2", 1),
            source, "share one x-scale",
            "a ridge sampled on its own x positions",
        )

        # 11. Labels: wrong row, wrong text, missing.
        case(
            failures, directory, "wrong-row",
            source.replace('<text data-ridge="checkout-api" data-role="name" x="304" '
                           'y="323.5"',
                           '<text data-ridge="checkout-api" data-role="name" x="304" '
                           'y="379.5"', 1),
            source, "renames the distribution",
            "a name label drawn on a neighbour's row",
        )
        case(
            failures, directory, "renamed",
            source.replace('text-anchor="end">checkout-api</text>',
                           'text-anchor="end">checkout</text>', 1),
            source, "binding must agree",
            "a name label reading a different name than it binds",
        )
        case(
            failures, directory, "unlabelled",
            source.replace('      <text data-ridge="checkout-api" data-role="range" '
                           'x="696" y="323.5" fill="#4f5d75" font-size="9" '
                           'font-family="\'Geist Mono\', monospace">40–440 ms</text>\n',
                           "", 1),
            source, "prints no range label",
            "a ridge with no range label",
        )

        # 12. A printed range wider than the mass it claims. Every geometric
        #     check still passes; only the sentence beside the ridge is false.
        case(
            failures, directory, "false-range",
            source.replace(">40–440 ms<", ">40–480 ms<", 1),
            source, "on the figure's own tick scale",
            "a printed range wider than the ridge's nonzero bins",
        )

        # 13. Bin ticks: text edited without its binding, and a tick moved off
        #     the bins it labels.
        case(
            failures, directory, "tick-swap",
            source.replace('text-anchor="middle">240</text>',
                           'text-anchor="middle">280</text>', 1),
            source, "must state one number",
            "a tick whose visible text was edited without its binding",
        )
        case(
            failures, directory, "tick-off-bins",
            source.replace('data-tick="2" data-bin="240" x="500"',
                           'data-tick="2" data-bin="240" x="505"', 1),
            source, "not a bin position",
            "a tick drawn off the bins it labels",
        )

        # 14. Transforms: on the ridge, on an ancestor, and from CSS. Raw
        #     coordinates are the basis, so any of the three moves the rendered
        #     mark away from the bin it was checked against.
        case(
            failures, directory, "transformed",
            source.replace('<path data-ridge="checkout-api"',
                           '<path transform="translate(0 8)" data-ridge="checkout-api"', 1),
            source, "moves the rendered mark",
            "a transform on a ridge outline",
        )
        case(
            failures, directory, "wrapped",
            source.replace(FOCAL_PATH, '<g transform="translate(0 8)">' + FOCAL_PATH + "</g>", 1),
            source, "ancestor",
            "a ridge wrapped in a transformed group",
        )
        case(
            failures, directory, "css-transform",
            source.replace("<style>", "<style>\n    svg path { transform: scaleY(1.1); }", 1),
            source, "CSS `transform`",
            "a CSS transform reaching the figure",
        )

        # 15. A second accent spends the accent entirely; colour and weight
        #     disagreeing sends the two focus cues to different ridges.
        case(
            failures, directory, "two-focal",
            source.replace('stroke="rgba(45,49,66,0.80)" stroke-width="1.2"',
                           'stroke="#eb6c36" stroke-width="2.4"', 1),
            source, "exactly one editorially focal",
            "two ridges carrying the accent stroke",
        )
        case(
            failures, directory, "weight-mismatch",
            source.replace('stroke="#eb6c36" stroke-width="2.4"',
                           'stroke="#eb6c36" stroke-width="1.2"', 1),
            source, "focus cue",
            "a focal stroke at non-focal weight",
        )

        # 16. Unreadable declarations are findings, never skips.
        case(
            failures, directory, "no-bins",
            source.replace(' data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0"', "", 1),
            source, "no data-bins",
            "a ridge outline with no declared bins",
        )
        case(
            failures, directory, "no-baseline",
            source.replace('data-ridge="checkout-api" data-baseline="320" data-bins',
                           'data-ridge="checkout-api" data-bins', 1),
            source, "no data-baseline",
            "a ridge with no declared baseline",
        )
        case(
            failures, directory, "junk-bins",
            source.replace('data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0"',
                           'data-bins="0,1,six,17,21,14,8,6,7,9,7,4,0"', 1),
            source, "not a comma list of numbers",
            "a bin that is not a number",
        )
        case(
            failures, directory, "junk-path",
            source.replace(FOCAL_D, 'd="M banana"', 1),
            source, "cannot verify its outline",
            "a ridge outline this checker cannot read",
        )
        case(
            failures, directory, "count-mismatch",
            source.replace('data-bins="0,1,6,17,21,14,8,6,7,9,7,4,0"',
                           'data-bins="0,1,6,17,21,14,8,6,7,9,7,4"', 1),
            source, "every declared bin needs its vertex",
            "a ridge with more vertices than bins",
        )
        case(
            failures, directory, "duplicate-ridge",
            source.replace(FOCAL_PATH, FOCAL_PATH + "\n      " + FOCAL_PATH, 1),
            source, "one ridge, one outline",
            "two outlines declaring the same ridge",
        )

        # 17. Single-quoted attributes must be read, not silently dropped — the
        #     same fault the slopegraph checker fixed. Positive case: the figure
        #     verifies; the falsified twin proves it was read at all.
        singled = source.replace(FOCAL_PATH, FOCAL_PATH.replace('"', "'"), 1)
        code, output = run(write(directory, "single-quoted.html", singled))
        if code != 0:
            failures.append("single-quoted attributes were rejected: %s" % output.strip())
        else:
            print("OK: single-quoted attributes are read")
        case(
            failures, directory, "single-quoted-lie",
            singled.replace("data-bins='0,1,6,17,21,14,8,6,7,9,7,4,0'",
                            "data-bins='0,1,6,17,21,14,8,6,9,9,7,4,0'", 1),
            source, "one amplitude",
            "a falsified bin in single-quoted attributes",
        )

        # 18. Fail closed on a file that claims the type and yields nothing.
        empty = ("<html><head><title>weekly ridgeline</title></head>"
                 "<body><svg><title>ridgeline of nothing</title></svg></body></html>")
        code, output = run(write(directory, "empty.html", empty))
        if code == 0:
            failures.append("a ridgeline with no verifiable ridges was accepted")
        elif "Refusing to report OK" not in output:
            failures.append("empty figure reported without the fail-closed reason: %s"
                            % output.strip())
        else:
            print("OK: a ridgeline this checker cannot read is refused")

        # 19. Synthetics: the checker reads the figure's OWN amplitude and pitch,
        #     and the budget rules fire at both ends on counts a mutation of the
        #     shipped example cannot reach.
        code, output = run(write(directory, "synthetic.html", synthetic(5, 13)))
        if code != 0:
            failures.append("a valid synthetic at a different top/pitch/amplitude was "
                            "rejected: %s" % output.strip())
        else:
            print("OK: a valid ridgeline on a different grid passes")

        for name, fixture, expect, describe in (
            ("too-many-ridges", synthetic(13, 13), "budget",
             "thirteen ridges against a budget of twelve"),
            ("too-few-ridges", synthetic(2, 13), "budget",
             "two ridges against a budget floor of three"),
            ("too-many-bins", synthetic(5, 41), "budget",
             "forty-one bins against a budget of forty"),
            ("too-few-bins", synthetic(5, 7), "budget",
             "seven bins against a budget floor of eight"),
            ("occluded", synthetic(5, 13, amp=8.0), "occluded",
             "a peak reaching past the row two above it"),
        ):
            code, output = run(write(directory, "%s.html" % name, fixture))
            if code == 0:
                failures.append("%s was accepted" % describe)
            elif expect not in output:
                failures.append("%s was reported without the expected reason: %s"
                                % (describe, output.strip()))
            else:
                print("OK: %s is rejected" % describe)

        # 20. The scope treaty. Each sibling Line-variant gate binds its own
        #     vocabulary; none of them may claim a ridgeline, and this one must
        #     not claim theirs. Each sibling is handed the ridgeline examples
        #     directly and must neither fail nor mention them — the assertion is
        #     on THIS variant's files, not on the health of the asset directory,
        #     so an unrelated example cannot make this case red.
        for script in SIBLINGS:
            path = ROOT / "scripts" / script
            if not path.is_file():
                print("note: %s is not in this tree yet — treaty untested against it"
                      % script)
                continue
            code, output = invoke([sys.executable, str(path), *(str(p) for p in RIDGELINES)])
            if code != 0:
                failures.append("%s claims the ridgeline examples: %s"
                                % (script, output.strip()))
            elif "example-ridgeline" in output:
                failures.append("%s reported on a ridgeline example instead of "
                                "skipping it: %s" % (script, output.strip()))
            else:
                print("OK: %s skips the ridgeline examples (scope treaty holds)" % script)

        # And the reverse direction: this checker must skip the siblings' files.
        for sibling in ("example-slopegraph.html", "example-bump.html",
                        "example-streamgraph.html"):
            other = ROOT / "skills/diagram-design/assets" / sibling
            if not other.is_file():
                continue
            code, output = run(other)
            if code != 0 or "no ridgeline found" not in output:
                failures.append("verify-ridgeline claims %s instead of skipping it: %s"
                                % (sibling, output.strip()))
            else:
                print("OK: verify-ridgeline skips %s" % sibling)

    for failure in failures:
        print("FAIL: %s" % failure)
    if failures:
        print("\n%d case(s) failed." % len(failures))
        return 1
    print("\nAll ridgeline checker cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
