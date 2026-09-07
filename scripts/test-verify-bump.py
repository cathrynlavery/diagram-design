#!/usr/bin/env python3
"""Adversarial tests for verify-bump.py — both polarities.

Per ADR 0005, a geometric contract is a checker plus fixtures proving it fires
when it should and stays quiet when it shouldn't. Each mutation below renders
perfectly and no other gate would catch it: a vertex nudged off its rank row,
two series tying at a rank the footnote's tie-break rule forbids, a spline
invented between quarterly snapshots, a printed rank disagreeing with the
declared one, a label drawn on a neighbour's row.

The endpoint-placement cases (9b-9g) pin the half of that contract a row
check cannot see. A label states two things - which series it belongs to
(its row) and which END of that series (its column) - and the second was
previously unverified, so a coordinate could be deleted or slid along its
row and still be certified. Each case names one coordinate and one
direction, because a case named for more than it proves hides the rest.

The synthetic figures at the end prove the checker reads the FIGURE's own grid
rather than memorising the shipped layout: a valid bump chart at a different
top and pitch must pass, and the budget rules must fire on series and snapshot
counts the shipped example cannot be mutated into. The last case pins the
scope treaty with the sibling checker: verify-slopegraph must skip a bump
chart rather than reject it for lacking <line> elements it never claimed.

Usage: python3 scripts/test-verify-bump.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-bump.py"
SIBLING = ROOT / "scripts/verify-slopegraph.py"
GOOD = ROOT / "skills/diagram-design/assets/example-bump.html"

CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# Anchors, all literal excerpts of the shipped example. A fixture that fails to
# build means the example moved, which is itself worth knowing.
FOCAL_D = 'd="M320,88 L440,144 L560,256 L680,368"'
FOCAL_PATH = ('<path data-series="legacy-http" data-ranks="1,2,4,6" '
              'd="M320,88 L440,144 L560,256 L680,368" fill="none" '
              'stroke="#eb6c36" stroke-width="2.4"/>')
# The focal series' left-gutter name label, and the gutter it shares with the
# five other series. The shipped left gutter is x=272 (names) against a first
# column at x=320; the right gutter mirrors it from x=728.
FIRST_NAME = ('data-series="legacy-http" data-end="first" data-role="name" '
              'x="272" y="91.5"')
FIRST_NAME_GUTTER = 'data-role="name" x="272"'


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
    path.write_text(source, encoding="utf-8")
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


def synthetic(n_series, n_cols, top=100, pitch=40, x0=200, dx=150):
    """A minimal valid bump chart: n_series over n_cols, ranks rotating."""
    xs = [x0 + i * dx for i in range(n_cols)]
    parts = [
        '<html><head><title>synthetic bump chart</title></head><body>',
        '<svg viewBox="0 0 1000 600" role="img" aria-labelledby="t d">',
        '<title id="t">synthetic bump chart</title>',
        '<desc id="d">bump chart fixture</desc>',
    ]
    for i, x in enumerate(xs):
        parts.append('<text data-axis="%d" data-state="T%d" x="%d" y="560">T%d</text>'
                     % (i, i, x, i))
    for s in range(n_series):
        ranks = [((s + c) % n_series) + 1 for c in range(n_cols)]
        pts = ["%d,%d" % (x, top + (r - 1) * pitch) for x, r in zip(xs, ranks)]
        d = "M" + pts[0] + " " + " ".join("L" + p for p in pts[1:])
        focal = s == 0
        stroke = "#eb6c36" if focal else "rgba(45,49,66,0.70)"
        width = "2.4" if focal else "1.2"
        parts.append('<path data-series="s%d" data-ranks="%s" d="%s" fill="none" '
                     'stroke="%s" stroke-width="%s"/>'
                     % (s, ",".join(map(str, ranks)), d, stroke, width))
        radius = "4" if focal else "3"
        for x, r in zip(xs, ranks):
            parts.append('<circle cx="%d" cy="%d" r="%s" fill="%s"/>'
                         % (x, top + (r - 1) * pitch, radius, stroke))
        first_y = top + (ranks[0] - 1) * pitch + 3.5
        last_y = top + (ranks[-1] - 1) * pitch + 3.5
        parts.append('<text data-series="s%d" data-end="first" data-role="name" '
                     'x="%d" y="%g" text-anchor="end">s%d</text>'
                     % (s, xs[0] - 48, first_y, s))
        parts.append('<text data-series="s%d" data-end="first" data-role="rank" '
                     'x="%d" y="%g" text-anchor="end">#%d</text>'
                     % (s, xs[0] - 16, first_y, ranks[0]))
        parts.append('<text data-series="s%d" data-end="last" data-role="rank" '
                     'x="%d" y="%g">#%d</text>'
                     % (s, xs[-1] + 16, last_y, ranks[-1]))
        parts.append('<text data-series="s%d" data-end="last" data-role="name" '
                     'x="%d" y="%g">s%d</text>'
                     % (s, xs[-1] + 48, last_y, s))
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
            print("OK: the shipped bump chart passes")

        # 2. Nudge one vertex off its rank row, dot moved with it so only the
        #    grid lies. Reads as a rank between two ranks.
        case(
            failures, directory, "off-grid",
            source.replace("L560,256 L680,368", "L560,250 L680,368")
                  .replace('<circle cx="560" cy="256" r="4"',
                           '<circle cx="560" cy="250" r="4"'),
            source, "grid puts that rank",
            "a vertex nudged off its rank row",
        )

        # 3. A tie: two series both claiming #1 at the last snapshot, leaving
        #    #2 empty. Both directions of the permutation rule fire.
        case(
            failures, directory, "tied-rank",
            source.replace('data-series="authx" data-ranks="2,3,3,2"',
                           'data-series="authx" data-ranks="2,3,3,1"')
                  .replace("L560,200 L680,144", "L560,200 L680,88")
                  .replace('<circle cx="680" cy="144" r="3" fill="rgba(45,49,66,0.80)"/>',
                           '<circle cx="680" cy="88" r="3" fill="rgba(45,49,66,0.80)"/>')
                  .replace('data-series="authx" data-end="last" data-role="rank" x="696" y="147.5" fill="#4f5d75" font-size="9" font-family="\'Geist Mono\', monospace">#2<',
                           'data-series="authx" data-end="last" data-role="rank" x="696" y="91.5" fill="#4f5d75" font-size="9" font-family="\'Geist Mono\', monospace">#1<')
                  .replace('data-series="authx" data-end="last" data-role="name" x="728" y="147.5"',
                           'data-series="authx" data-end="last" data-role="name" x="728" y="91.5"'),
            source, "tie-break",
            "two series tying at one rank",
        )

        # 4. A curved segment. The endpoints are identical; only the path
        #    between them - which nobody measured - changes.
        case(
            failures, directory, "spline",
            source.replace('d="M320,88 L440,144 L560,256 L680,368"',
                           'd="M320,88 C400,88 400,144 440,144 L560,256 L680,368"'),
            source, "invents a trajectory",
            "a spline between two snapshots",
        )

        # 4b. Relative commands: `l120,56` renders against the previous point
        #     while the parsed numbers read as absolute, so folding case would
        #     certify a figure at positions it never drew. Refused outright.
        case(
            failures, directory, "relative-path",
            source.replace('d="M320,88 L440,144 L560,256 L680,368"',
                           'd="M320,88 l120,56 l120,112 l120,112"'),
            source, "relative path commands",
            "a series drawn with relative path commands",
        )

        # 5. A printed rank disagreeing with the declared one.
        case(
            failures, directory, "mislabelled",
            source.replace('font-family="\'Geist Mono\', monospace">#6<',
                           'font-family="\'Geist Mono\', monospace">#5<', 1),
            source, "must state one number",
            "a printed rank its geometry does not draw",
        )

        # 6. A rank label without its # sigil reads as a magnitude.
        case(
            failures, directory, "bare-rank",
            source.replace('font-family="\'Geist Mono\', monospace">#6<',
                           'font-family="\'Geist Mono\', monospace">6<', 1),
            source, "cannot be mistaken for a magnitude",
            "a rank label printed without its sigil",
        )

        # 7. A label drawn on a neighbour's row renames the line.
        case(
            failures, directory, "wrong-row",
            source.replace('data-series="legacy-http" data-end="last" data-role="name" x="728" y="371.5"',
                           'data-series="legacy-http" data-end="last" data-role="name" x="728" y="315.5"'),
            source, "renames the line",
            "a name label drawn beside another series' endpoint",
        )

        # 8. A name label whose visible text disagrees with its binding.
        case(
            failures, directory, "renamed",
            source.replace('font-family="\'Geist\', sans-serif">legacy-http</text>',
                           'font-family="\'Geist\', sans-serif">legacy</text>', 1),
            source, "binding must agree",
            "a name label reading a different name than it binds",
        )

        # 9. A missing label: the reader traces a line to an unlabelled end.
        case(
            failures, directory, "unlabelled",
            source.replace('      <text data-series="legacy-http" data-end="first" data-role="rank" x="304" y="91.5" fill="#4f5d75" font-size="9" font-family="\'Geist Mono\', monospace" text-anchor="end">#1</text>\n', "", 1),
            source, "prints no first rank",
            "a series with no first rank label",
        )

        # 9b. A coordinate that is absent is not a coordinate that is
        #     unverified: SVG defaults a missing x or y to 0, so the browser
        #     draws the label at the edge of the frame. Deleting one used to
        #     be certified, because the check compared nothing and said OK.
        case(
            failures, directory, "label-no-y",
            source.replace(FIRST_NAME, FIRST_NAME.replace(' y="91.5"', ""), 1),
            source, "has no readable y",
            "an endpoint label with no y coordinate",
        )
        case(
            failures, directory, "label-no-x",
            source.replace(FIRST_NAME, FIRST_NAME.replace(' x="272"', ""), 1),
            source, "has no readable x",
            "an endpoint label with no x coordinate",
        )

        # 9c. Present but unreadable is the same defect wearing an attribute.
        case(
            failures, directory, "label-empty-y",
            source.replace(FIRST_NAME, FIRST_NAME.replace('y="91.5"', 'y=""'), 1),
            source, "has no readable y",
            "an endpoint label whose y is present but empty",
        )

        # 9d. "1e400" parses as a number and overflows to inf, which sits
        #     further than any tolerance from every real coordinate - so a
        #     distance test passes it by default unless finiteness is required.
        case(
            failures, directory, "label-non-finite-x",
            source.replace(FIRST_NAME, FIRST_NAME.replace('x="272"', 'x="1e400"'), 1),
            source, "has no readable x",
            "an endpoint label whose x overflows to infinity",
        )

        # 9e. The reported repro: one first-end label slid from its gutter
        #     toward the middle of the plot. Its row is untouched and every
        #     rank it prints is still correct, so row proximity alone clears it.
        case(
            failures, directory, "label-x-inboard",
            source.replace(FIRST_NAME, FIRST_NAME.replace('x="272"', 'x="500"'), 1),
            source, "inboard of the first endpoint",
            "a first-end label moved toward the middle of the chart",
        )

        # 9f. The same displacement applied to every name label in the gutter.
        #     The gutter stays perfectly self-consistent, so only the endpoint
        #     test can fire - which is what makes it independent of 9g.
        case(
            failures, directory, "label-gutter-inboard",
            source.replace(FIRST_NAME_GUTTER, 'data-role="name" x="500"'),
            source, "inboard of the first endpoint",
            "a whole first-end name gutter moved inside the plot",
        )

        # 9g. And the other direction: one label slid further out. It stays
        #     outboard of its endpoint, so only its disagreement with the
        #     gutter its five peers share reveals it.
        case(
            failures, directory, "label-off-gutter",
            source.replace(FIRST_NAME, FIRST_NAME.replace('x="272"', 'x="240"'), 1),
            source, "gutter its",
            "a first-end label moved off the gutter its peers share",
        )

        # 10. Transforms: on the series, on an ancestor, and from CSS. Raw
        #     coordinates are the basis, so any of the three moves the rendered
        #     mark away from the rank it was checked against.
        case(
            failures, directory, "transformed",
            source.replace('<path data-series="legacy-http"',
                           '<path transform="translate(0 8)" data-series="legacy-http"'),
            source, "moves the rendered mark",
            "a transform on a series path",
        )
        case(
            failures, directory, "wrapped",
            source.replace(FOCAL_PATH, '<g transform="translate(0 8)">' + FOCAL_PATH + "</g>", 1),
            source, "ancestor",
            "a series wrapped in a transformed group",
        )
        case(
            failures, directory, "css-transform",
            source.replace("<style>", "<style>\n    svg path { transform: scaleY(1.1); }", 1),
            source, "CSS `transform`",
            "a CSS transform reaching the figure",
        )
        for label, style, prop in (
            ("inline-transform", "transform: translateY(100px)", "transform"),
            ("inline-translate", "translate: 0 100px", "translate"),
            ("inline-y", "y: 100px", "y"),
            ("inline-d", 'd: path("M0,0 L10,10")', "d"),
            ("inline-offset", 'offset: path("M0,0 L10,10") 100%', "offset"),
        ):
            case(
                failures,
                directory,
                label,
                source.replace(FOCAL_PATH, FOCAL_PATH.replace(
                    "<path ", '<path style="%s" ' % style, 1
                ), 1),
                source,
                "the %s property" % prop,
                "an inline %s style moving a series path" % prop,
            )
        case(
            failures,
            directory,
            "inline-ancestor-translate",
            source.replace(
                FOCAL_PATH,
                '<g style="translate: 0 100px">' + FOCAL_PATH + "</g>",
                1,
            ),
            source,
            "ancestor <g>/<svg> style transform",
            "an inline translate style moving a series ancestor",
        )
        case(
            failures,
            directory,
            "css-y",
            source.replace("<style>", "<style>\n    svg path { y: 100px; }", 1),
            source,
            "CSS `y`",
            "a CSS geometry property reaching the figure",
        )

        # 11. Caption text swapped while the bindings stay put — the exact
        #     defect data-state exists to catch.
        case(
            failures, directory, "caption-swap",
            source.replace('text-anchor="middle">Q1</text>', 'text-anchor="middle">Q2</text>', 1),
            source, "binding must agree",
            "a caption whose visible text was edited without its binding",
        )
        case(
            failures, directory, "caption-gone",
            source.replace('      <text data-axis="2" data-state="Q3" x="560" y="416" fill="#4f5d75" font-size="9" font-family="\'Geist Mono\', monospace" letter-spacing="0.14em" text-anchor="middle">Q3</text>\n', "", 1),
            source, "no caption for snapshot 3",
            "a snapshot with no caption",
        )

        # 12. A second accent series spends the accent entirely.
        case(
            failures, directory, "two-focal",
            source.replace('d="M320,144 L440,200 L560,200 L680,144" fill="none" stroke="rgba(45,49,66,0.80)" stroke-width="1.2"',
                           'd="M320,144 L440,200 L560,200 L680,144" fill="none" stroke="#eb6c36" stroke-width="2.4"'),
            source, "exactly one editorially focal",
            "two series carrying the accent stroke",
        )

        # 13. Colour and weight sending focus to different series.
        case(
            failures, directory, "weight-mismatch",
            source.replace('stroke="#eb6c36" stroke-width="2.4"/>',
                           'stroke="#eb6c36" stroke-width="1.2"/>', 1),
            source, "focus cue",
            "a focal stroke at non-focal weight",
        )

        # 14. Dots: a vertex with no dot, and a focal dot at non-focal size.
        case(
            failures, directory, "dotless",
            source.replace('      <circle cx="560" cy="256" r="4" fill="#eb6c36"/>\n', "", 1),
            source, "no dot at",
            "a vertex with no dot",
        )
        case(
            failures, directory, "small-dot",
            source.replace('<circle cx="680" cy="368" r="4" fill="#eb6c36"/>',
                           '<circle cx="680" cy="368" r="3" fill="#eb6c36"/>'),
            source, "dot size",
            "a focal vertex with a non-focal dot",
        )

        # 15. Unreadable declarations are findings, never skips.
        case(
            failures, directory, "no-ranks",
            source.replace(' data-ranks="1,2,4,6"', "", 1),
            source, "no data-ranks",
            "a series path with no declared ranks",
        )
        case(
            failures, directory, "junk-ranks",
            source.replace('data-ranks="1,2,4,6"', 'data-ranks="1,2,four,6"', 1),
            source, "not a rank",
            "a rank that is not a whole number",
        )
        case(
            failures, directory, "junk-path",
            source.replace(FOCAL_D, 'd="M banana"', 1),
            source, "cannot verify its positions",
            "a series path this checker cannot read",
        )

        # Scientific notation is part of SVG's number grammar. Its exponent
        # marker is not an `e` path command, so a browser-valid path spelling
        # the same points this way must still verify.
        scientific = source.replace(
            FOCAL_D,
            'd="M3.2e2,8.8e1 L4.4e2,1.44e2 L5.6e2,2.56e2 L6.8e2,3.68e2"',
            1,
        )
        code, output = run(write(directory, "scientific-notation.html", scientific))
        if code != 0:
            failures.append(
                "scientific notation in a valid path was rejected: %s" % output.strip()
            )
        else:
            print("OK: scientific notation is parsed as numbers, not path commands")

        # SVG's number grammar also permits a decimal point with no following
        # fractional digits, including before an exponent marker.
        trailing_decimal = source.replace(
            FOCAL_D,
            'd="M320.,88. L440.e0,144. L560.,256. L680.,368."',
            1,
        )
        code, output = run(write(directory, "trailing-decimal.html", trailing_decimal))
        if code != 0:
            failures.append(
                "trailing-decimal coordinates in a valid path were rejected: %s"
                % output.strip()
            )
        else:
            print("OK: trailing-decimal coordinates follow the SVG number grammar")

        # Restricting command recognition to SVG's real command alphabet must
        # not make unknown letters disappear from otherwise plausible data.
        case(
            failures, directory, "unknown-command",
            source.replace(FOCAL_D, 'd="M320,88 X440,144 L560,256 L680,368"', 1),
            source, "cannot verify its positions",
            "an unknown SVG path command",
        )
        case(
            failures, directory, "count-mismatch",
            source.replace('data-ranks="1,2,4,6"', 'data-ranks="1,2,4"', 1),
            source, "every declared rank needs its vertex",
            "a series with more points than ranks",
        )

        # 16. A series visiting a private column redraws time.
        case(
            failures, directory, "own-columns",
            source.replace("L560,256 L680,368", "L564,256 L680,368")
                  .replace('<circle cx="560" cy="256" r="4"', '<circle cx="564" cy="256" r="4"'),
            source, "visit the same snapshots",
            "a series visiting its own private column",
        )

        # 17. Single-quoted attributes must be read, not silently dropped —
        #     the same fault the slopegraph checker fixed. Positive case: the
        #     figure verifies; the falsified twin proves it was read at all.
        singled = source.replace(FOCAL_PATH,
                                 FOCAL_PATH.replace('"', "'").replace("<path", "<path", 1), 1)
        code, output = run(write(directory, "single-quoted.html", singled))
        if code != 0:
            failures.append("single-quoted attributes were rejected: %s" % output.strip())
        else:
            print("OK: single-quoted attributes are read")
        case(
            failures, directory, "single-quoted-lie",
            singled.replace("data-ranks='1,2,4,6'", "data-ranks='1,2,4,5'", 1),
            source, "grid puts that rank",
            "a falsified rank in single-quoted attributes",
        )

        # 18. Fail closed on a file that claims the type and yields nothing.
        empty = ("<html><head><title>quarterly bump chart</title></head>"
                 "<body><svg><title>bump chart of nothing</title></svg></body></html>")
        code, output = run(write(directory, "empty.html", empty))
        if code == 0:
            failures.append("a bump chart with no verifiable series was accepted")
        elif "Refusing to report OK" not in output:
            failures.append("empty figure reported without the fail-closed reason: %s"
                            % output.strip())
        else:
            print("OK: a bump chart this checker cannot read is refused")

        # 19. Synthetics: the checker reads the figure's own grid, and the
        #     budget rules fire on counts a mutation cannot reach.
        clean = synthetic(4, 4)
        code, output = run(write(directory, "synthetic.html", clean))
        if code != 0:
            failures.append("a valid synthetic at a different top/pitch was rejected: %s"
                            % output.strip())
        else:
            print("OK: a valid bump chart on a different grid passes")

        for name, fixture, expect, describe in (
            ("too-many-series", synthetic(9, 4), "budget",
             "nine series against a budget of eight"),
            ("too-few-series", synthetic(3, 4), "budget",
             "three series against a budget floor of four"),
            ("too-many-cols", synthetic(4, 7), "budget",
             "seven snapshots against a budget of six"),
            ("too-few-cols", synthetic(4, 2), "slopegraph",
             "two snapshots, which is a slopegraph"),
        ):
            code, output = run(write(directory, "%s.html" % name, fixture))
            if code == 0:
                failures.append("%s was accepted" % describe)
            elif expect not in output:
                failures.append("%s was reported without the expected reason: %s"
                                % (describe, output.strip()))
            else:
                print("OK: %s is rejected" % describe)

        # 20. The scope treaty. verify-slopegraph binds its contract to <line>
        #     elements; a bump chart binds the same data-series vocabulary to
        #     <path>. The sibling must SKIP the shipped bump example - holding
        #     it to the slopegraph contract rejects it for lacking elements it
        #     never claimed to have.
        code, output = invoke([sys.executable, str(SIBLING), str(GOOD)])
        if code != 0:
            failures.append("verify-slopegraph claims the bump example: %s" % output.strip())
        elif "no slopegraph found" not in output:
            failures.append("verify-slopegraph checked the bump example instead of "
                            "skipping it: %s" % output.strip())
        else:
            print("OK: verify-slopegraph skips the bump chart (scope treaty holds)")

    for failure in failures:
        print("FAIL: %s" % failure)
    if failures:
        print("\n%d case(s) failed." % len(failures))
        return 1
    print("\nAll bump checker cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
