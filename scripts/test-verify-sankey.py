#!/usr/bin/env python3
"""Adversarial tests for verify-sankey.py — both polarities.

Per ADR 0005, a geometric contract in this repo is a checker plus fixtures that
prove it fires when it should and stays quiet when it shouldn't. Each mutation
below is a defect that renders perfectly and that no other gate would catch:
a ribbon that narrows as it travels, a node that loses volume between its two
sides, a stage that quietly carries less than the one before it, a printed
number that no longer matches the bar beside it, and a dark variant edited by
hand until it no longer matches the light one.

The later cases attack the checker rather than the figure. A checker that cannot
see a shape reports success, and success is indistinguishable from a clean file —
so a path it cannot parse, a ribbon attached to nothing, node bars outside the
size window, a shipped variant that has gone missing, and a reference code sample
that no longer matches the example all have to be findings, and each is tested
here.

Every anchor below is a literal excerpt of the SHIPPED example-sankey.html —
the CI budget figure — so a fixture that fails to build means the example
moved, which is itself worth knowing.

Usage: python3 scripts/test-verify-sankey.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-sankey.py"
ASSETS = ROOT / "skills/diagram-design/assets"
GOOD = ASSETS / "example-sankey.html"
REFERENCE = ROOT / "skills/diagram-design/references/type-sankey.md"

# The first ribbon of the shipped figure (Budget → Unit tests), in full and as
# the opening fragment mutations prepend attributes to.
RIBBON = ('<path d="M132,120 C316,120 316,120 500,120 L500,224 '
          'C316,224 316,224 132,224 Z" fill="rgba(79,93,117,0.18)"/>')
RIBBON_ANCHOR = '<path d="M132,120 C316,120 316,120 500,120'
RIBBON_FILL = 'fill="rgba(79,93,117,0.18)"'
# The first legend swatch — the only stroked, stroke-width-bearing element the
# stroke grammar cases can anchor on, since shipped ribbons carry no stroke.
SWATCH = 'fill="rgba(79,93,117,0.18)" stroke="#4f5d75" stroke-width="1"'
# The Failed node bar — last stage, 32px for 1,600 min at 50 min/px.
BAR = '<rect x="880" y="344" width="12" height="32" fill="#2d3142"/>'
# Insertion point for extra paths: just before the legend block.
ANNOT = "      <!-- Legend -->"
SVG_OPEN = '<svg viewBox="0 0 1000 560"'

# The checker's findings contain em dashes. Without this the child writes them
# in the Windows locale codepage while the parent decodes UTF-8, and the test
# dies on a decode error that has nothing to do with the case under test. CI
# already sets this globally; pinning it here keeps a local run honest too.
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def invoke(argv: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        argv, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=CHILD_ENV,
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def run(*paths: Path) -> tuple[int, str]:
    return invoke([sys.executable, str(CHECKER), *(str(p) for p in paths)])


def write(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def case(
    failures: list[str],
    directory: Path,
    name: str,
    source: str,
    original: str,
    expect: str,
    describe: str,
) -> None:
    """Run one mutation: it must be a real edit, and it must be rejected."""
    if source == original:
        failures.append(f"could not build the {name} fixture (anchor moved)")
        return
    code, output = run(write(directory, f"{name}.html", source))
    if code == 0:
        failures.append(f"{describe} was accepted")
    elif expect not in output:
        failures.append(f"{describe} was reported without the expected reason: {output.strip()}")
    else:
        print(f"OK: {describe} is rejected")


def refill(source_text: str, colour: str) -> str:
    """Repaint the first ribbon. Its fill is the volume, so this is the value
    every conservation sum is measured against."""
    return source_text.replace(RIBBON_FILL, f'fill="{colour}"', 1)


def onribbon(source_text: str, extra: str) -> str:
    """Add an attribute to the first ribbon, leaving every coordinate alone."""
    return source_text.replace(
        RIBBON_ANCHOR, f'<path {extra} ' + RIBBON_ANCHOR[len("<path "):], 1)


def main() -> int:
    source = GOOD.read_text(encoding="utf-8")
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # 1. The shipped example must pass untouched.
        code, output = run(GOOD)
        if code != 0:
            failures.append(f"clean example was rejected: {output.strip()}")
        else:
            print("OK: the shipped sankey passes")

        # 2. Narrow one end of a ribbon. The Unit-tests → Passed band arrives
        #    10px thinner than it left — invisible by eye across a 368px span,
        #    because a reader has no reference width to compare it against. The
        #    return-curve controls move with the edge so only the width lies.
        case(
            failures, directory, "tapered",
            source.replace(
                "L880,236 C696,236",
                "L880,226 C696,226",
            ),
            source, "change in width",
            "a ribbon that narrows along its run",
        )

        # 3. Break conservation at a node while keeping the ribbon's own width
        #    constant: the E2E node then takes in 80px and puts out 72px, and
        #    nothing about the picture looks wrong.
        case(
            failures, directory, "leaky-node",
            source.replace(
                "L880,312 C696,312 696,336 512,336 Z",
                "L880,304 C696,304 696,328 512,328 Z",
            ),
            source, "as tall as the flow",
            "a node that puts out less than it takes in",
        )

        # 4. Shrink the last node so the final stage carries less than the two
        #    before it. This is the mutation that justifies the stage-total check
        #    existing separately from the per-node one.
        case(
            failures, directory, "stage",
            source.replace(
                '<rect x="880" y="344" width="12" height="32"',
                '<rect x="880" y="344" width="12" height="24"',
            ),
            source, "every stage of a sankey",
            "a stage carrying less than the stage before it",
        )

        # 5. Change a printed value and leave the geometry alone. The figure is
        #    then internally consistent and still lying.
        case(
            failures, directory, "mislabelled",
            source.replace(">9,400 min<", ">7,400 min<"),
            source, "off the scale",
            "a node labelled with a value its height does not draw",
        )

        # 6. Move one Bezier control onto the target's x. Every endpoint stays
        #    exactly where it was, the width is unchanged, and conservation still
        #    balances — but the control now coincides with the endpoint, B'(1)
        #    vanishes, and the ribbon skews into its node bar. Nothing else here
        #    reads the control points, so nothing else would catch it.
        case(
            failures, directory, "slanted",
            source.replace(
                'd="M132,120 C316,120 316,120 500,120',
                'd="M132,120 C316,120 500,120 500,120',
            ),
            source, "meets its node bar at a slant",
            "a ribbon whose control point collapses onto its endpoint",
        )

        # 7. A path this checker cannot read must be reported, never skipped.
        case(
            failures, directory, "unreadable",
            source.replace(
                "M132,120 C316,120 316,120 500,120 L500,224 C316,224 316,224 132,224 Z",
                "M132,120 L500,120 L500,224 L132,224 Z",
            ),
            source, "neither a readable ribbon",
            "a path the checker cannot parse as a ribbon",
        )

        # 7. Detach a ribbon from the node it leaves. It still renders, and it is
        #    counted in no node's balance — so it has to be reported, not skipped.
        case(
            failures, directory, "unattached",
            source.replace('d="M132,224 C316,224', 'd="M172,224 C316,224'),
            source, "touches nothing",
            "a ribbon that leaves from no node bar",
        )

        # 8. Delete every node bar. The checker then sees ribbons and no nodes,
        #    and must say it checked nothing rather than exit clean. (It used to
        #    be enough to WIDEN the bars past the parser window; the rect-shape
        #    rule now refuses that earlier, so reaching this guard takes an
        #    actual deletion — and the guard is worth keeping reachable, because
        #    a vacuous pass is the one failure a green checker cannot show you.)
        case(
            failures, directory, "no-bars",
            re.sub(r'[ ]*<rect x="\d+" y="\d+" width="12" height="\d+" fill="#2d3142"/>\n', '', source),
            source, "Nothing here could be checked",
            "a file whose node bars the parser cannot see",
        )

        # 8a. A rect that is none of the three shapes a sankey draws — not a node
        #     bar, not a legend swatch, not the full-bleed paper. Painted last it
        #     covers whatever was measured, and widening the bars is how the
        #     parser was blinded before the rule existed.
        case(
            failures, directory, "fat-bars",
            source.replace('width="12" height=', 'width="20" height='),
            source, "neither a node bar, a legend swatch",
            "a rect that is not any shape this figure draws",
        )

        # 8a-bis. A rect's SIZE is not enough — its position decides what it may
        #     claim to be. A swatch-sized 16x8 rect is a legend key below the
        #     band floor and ink over the figure inside it, where it is exactly
        #     big enough to cover a printed value. And a bar-width rect BELOW
        #     the band is a shape parse_bars will never read: unrefused, it is
        #     ink this checker certified without examining.
        case(
            failures, directory, "swatch-in-plot",
            source.replace(ANNOT,
                '      <rect x="600" y="300" width="16" height="8" fill="#f5f5f5"/>\n'
                + ANNOT, 1),
            source, "neither a node bar",
            "a swatch-sized rect parked inside the plot band",
        )
        case(
            failures, directory, "bar-below-band",
            source.replace(ANNOT,
                '      <rect x="600" y="496" width="12" height="8" fill="#2d3142"/>\n'
                + ANNOT, 1),
            source, "neither a node bar",
            "a bar-width rect below the plot band",
        )

        # 8b. Strip every ribbon. Eight node bars remain, so the file still looks
        #     like a sankey — but there is no flow left at all, and every
        #     conservation check would pass on it vacuously.
        case(
            failures, directory, "no-ribbons",
            "\n".join(l for l in source.splitlines() if '<path d="M' not in l),
            source, "carries no flow",
            "a figure with node bars but no ribbons",
        )

        # 8c. Move a ribbon with a transform instead of editing its coordinates.
        #     Everything this checker reads is still correct; what renders is
        #     not. The same trick works with a clip path, a mask, or display:none,
        #     and it defeats all five checks at once — so a sankey using any of
        #     them is refused rather than certified. A checker that cannot see
        #     what renders must say so, not pass.
        for name, mutation in (
            ("transformed", ('<path d="M132,120', '<path transform="translate(0 16) scale(1 0.8)" d="M132,120')),
            ("clipped", ('<path d="M512,136', '<path clip-path="url(#c)" d="M512,136')),
        ):
            case(
                failures, directory, name,
                source.replace(mutation[0], mutation[1], 1),
                source, "without changing the coordinates this checker reads",
                f"a ribbon moved by {'a transform' if name == 'transformed' else 'a clip path'}",
            )

        # 8d. The reference permits one dashed, unfilled path for a relationship
        #     that is not a volume. An unfilled path encloses no area, so it
        #     cannot be claiming one — the checker must ALLOW it, or this gate
        #     forbids a feature the type documents. Both polarities: the unfilled
        #     path passes, the same shape with a fill is still reported.
        anchor = ANNOT
        dashed = source.replace(
            anchor,
            '      <path d="M140,64 L640,48" fill="none" stroke="#2d3142" '
            'stroke-width="1" stroke-dasharray="4 3"/>\n' + anchor, 1)
        if dashed == source:
            failures.append("could not build the dashed-relationship fixture (anchor moved)")
        else:
            code, output = run(write(directory, "dashed.html", dashed))
            if code != 0:
                failures.append(f"the documented dashed non-volume path was rejected: {output.strip()}")
            else:
                print("OK: a dashed unfilled path is allowed, as the reference promises")

        case(
            failures, directory, "filled-garbage",
            source.replace(anchor,
                '      <path d="M140,64 L640,48 Z" fill="rgba(45,49,66,0.13)"/>\n' + anchor, 1),
            source, "neither a readable ribbon",
            "a filled path that is not a readable ribbon",
        )

        # The exemption is narrow on purpose, and each clause needs its own
        # case. "Unfilled" alone is not enough: a fill="none" path with a fat
        # stroke renders as a band a reader reads as volume, and would skip
        # every check below. Width cap and dash pattern are both load-bearing.
        # Two routes reject these, and each case expects the one that fires. The
        # width cap catches the fat pair first and diagnoses them more directly;
        # the undashed hairline is thin enough to reach the exemption, which
        # turns it down for want of a dash pattern.
        for name, frag, expect, why in (
            ("fat-stroke",
             '<path d="M140,64 L640,48" fill="none" stroke="#2d3142" stroke-width="40"/>',
             "paints", "an unfilled path drawn as a 40px band"),
            ("fat-dashed",
             '<path d="M140,64 L640,48" fill="none" stroke="#2d3142" stroke-width="40" stroke-dasharray="4 3"/>',
             "paints", "a dashed unfilled path too wide to be a hairline"),
            ("undashed",
             '<path d="M140,64 L640,48" fill="none" stroke="#2d3142" stroke-width="1"/>',
             "neither a readable ribbon", "an unfilled hairline with no dash pattern"),
        ):
            case(
                failures, directory, name,
                source.replace(anchor, "      " + frag + "\n" + anchor, 1),
                source, expect, why,
            )

        # 8e. Blank a node's printed value. Its drawn height is then compared
        #     against nothing, and the fidelity check quietly shrinks its sample
        #     rather than failing — which is how a label-format change once
        #     stopped every value from parsing without a single test noticing.
        case(
            failures, directory, "novalue",
            source.replace(">12,000 min<", ">the whole budget<", 1),
            source, "no readable value beside it",
            "a node bar whose printed value cannot be read",
        )

        # 8f. Run a ribbon end past the bottom of the bar it attaches to. Its top
        #     edge is still inside, so a top-edge-only test counts it as attached
        #     and credits the volume to the wrong node.
        case(
            failures, directory, "overrun",
            source.replace("C696,368 696,408 512,408 Z", "C696,368 696,428 512,428 Z", 1),
            source, "touches nothing",
            "a ribbon end overrunning the bar it attaches to",
        )

        # 8g. Set stroke-width from CSS instead of an attribute. The attributes
        #     this checker reads still say "hairline"; what renders is a band.
        #     A class does it from the page stylesheet, inline style does it on
        #     the element, and the same trick widens a real ribbon past the fill
        #     it is measured by — so geometry may not carry style or class at
        #     all. All three were live holes found in review.
        styled = source.replace(
            anchor,
            '      <path d="M140,64 L640,48" fill="none" stroke="#2d3142" '
            'stroke-width="1" stroke-dasharray="4 3" style="stroke-width:40px"/>\n' + anchor, 1)
        case(
            failures, directory, "css-inline", styled, source,
            "apparent volume", "a hairline widened by an inline style",
        )

        classed = source.replace(
            anchor,
            '      <path class="fat" d="M140,64 L640,48" fill="none" stroke="#2d3142" '
            'stroke-width="1" stroke-dasharray="4 3"/>\n' + anchor, 1
        ).replace("<style>", "<style>\n    .fat { stroke-width: 40px; }", 1)
        case(
            failures, directory, "css-class", classed, source,
            "apparent volume", "a hairline widened by a stylesheet class",
        )

        case(
            failures, directory, "css-ribbon",
            source.replace('<path d="M132,120 C316,120',
                           '<path style="stroke-width:30" d="M132,120 C316,120', 1),
            source, "apparent volume",
            "a ribbon widened past its fill by an inline style",
        )

        # 8h. The indirect routes do not enumerate — a bare element selector
        #     needs no class attribute, and an ancestor's stroke-width is simply
        #     inherited. Both reach geometry without appearing on it, so the
        #     rule is stated as an invariant: stroke-width lives on the element
        #     or nowhere.
        selector = source.replace(
            anchor,
            '      <path d="M140,64 L640,48" fill="none" stroke="#2d3142" '
            'stroke-width="1" stroke-dasharray="4 3"/>\n' + anchor, 1
        ).replace("<style>", "<style>\n    svg path { stroke-width: 40px; }", 1)
        case(
            failures, directory, "css-selector", selector, source,
            "may set only",
            "a hairline widened by a bare element selector",
        )

        case(
            failures, directory, "css-inherit",
            source.replace(SVG_OPEN, '<svg stroke-width="40" viewBox="0 0 1000 560"', 1),
            source, "every descendant inherits",
            "stroke-width inherited from the svg element",
        )

        # 8i. The direct route, and the last of this class: a stroke-width
        #     attribute on a ribbon is not what the shipped figure draws — its
        #     ribbons carry fill alone — and a fat one paints outside the fill
        #     this checker measures, so the shape renders wider than the volume
        #     it is credited with.
        case(
            failures, directory, "fat-attr",
            source.replace(
                RIBBON_FILL + "/>",
                RIBBON_FILL + ' stroke="#f5f5f5" stroke-width="30"/>', 1),
            source, "paints",
            "a ribbon with a fat stroke-width attribute",
        )

        # 8j. The other polarity, and the one that matters most: a gate that
        #     rejects valid work is worse than one that misses a contrived
        #     evasion, because it blocks real contributors. Both of these are
        #     legal SVG and both were rejected by an earlier round of hardening.
        units = source.replace('stroke-width="1"', 'stroke-width="1px"')
        if units == source:
            failures.append("could not build the unit-bearing fixture (anchor moved)")
        else:
            code, output = run(write(directory, "units.html", units))
            if code != 0:
                failures.append(f"a unit-bearing stroke-width was rejected: {output.strip()}")
            else:
                print("OK: a unit-bearing stroke-width is accepted")

        # 8k. Two value lines in one node block. The bar can only draw one of
        #     them, so the other is a number the reader may take as the node's
        #     own — and binding the first and moving on validates the one the
        #     reader might not be looking at. Found by auditing the binding
        #     rather than by a failing render.
        real = next(l for l in source.splitlines() if "<text" in l and "9,400" in l)
        dupe = real.replace("9,400", "2,000").replace('y="252"', 'y="264"')
        case(
            failures, directory, "two-values",
            source.replace(real, real + "\n" + dupe, 1),
            source, "more than one value printed",
            "a node with two value lines in its block",
        )

        # 8k-bis. The same value line moved to where TWO bars could claim it —
        #     the seam between Flaked (bottom 140) and Passed (top 148), where
        #     both bars' right-hand label windows overlap. Nearest-bar binding
        #     would hand it to one of them silently; the reader has the same
        #     ambiguity, so it must be a finding instead.
        ambiguous = real.replace('y="252"', 'y="150"')
        case(
            failures, directory, "ambiguous-value",
            source.replace(real, ambiguous, 1),
            source, "could label",
            "a value line sitting where two bars could claim it",
        )

        # 8l. The SVG number grammar, both polarities. ".5" is a legal length
        #     written differently and must pass; "1em" resolves against a font
        #     this checker never sees, so it cannot be compared to a pixel
        #     threshold and has to say so rather than guess. An earlier round
        #     matched only the forms the shipped example happened to use, which
        #     rejected a contributor for writing the same number another way — a
        #     gate failing at its actual job.
        for value, should_pass in ((".5", True), ("+1", True), ("1e0", True), ("1em", False)):
            fixture = source.replace('stroke-width="1"', f'stroke-width="{value}"')
            if fixture == source:
                failures.append("could not build the length fixture (anchor moved)")
                continue
            code, output = run(write(directory, f"len-{value}.html", fixture))
            if should_pass and code != 0:
                failures.append(f"stroke-width={value!r} was rejected: {output.strip()}")
            elif not should_pass and code == 0:
                failures.append(f"stroke-width={value!r} was accepted despite being uncomparable")
            else:
                verb = "accepted" if should_pass else "reported as uncomparable"
                print(f"OK: stroke-width={value!r} is {verb}")

        # 8m. A regression from a previous round, caught by review: the
        #     documented dashed relationship written with a unit was rejected,
        #     because stroke width was parsed in two places and the fix landed
        #     on one of them.
        dashed_units = source.replace(
            anchor,
            '      <path d="M140,64 L640,48" fill="none" stroke="#2d3142" '
            'stroke-width="0.75px" stroke-dasharray="4 3"/>\n' + anchor, 1)
        if dashed_units == source:
            failures.append("could not build the unit-bearing dashed fixture (anchor moved)")
        else:
            code, output = run(write(directory, "dash-units.html", dashed_units))
            if code != 0:
                failures.append(f"a dashed relationship with a unit-bearing width was rejected: {output.strip()}")
            else:
                print("OK: a dashed relationship written 0.75px is accepted")

        # 8n. Un-fill an EXISTING ribbon. Every coordinate is untouched, so
        #     conservation still balances and no width has changed — but the
        #     shape paints nothing, and the reader sees a gap where the flow
        #     should be. An earlier probe missed this by ADDING an unfilled
        #     ribbon, which broke the sums and got caught for the wrong reason.
        for name, repl in (
            ("inv-none", 'fill="none"'),
            ("inv-transparent", 'fill="transparent"'),
            ("inv-alpha0", 'fill="rgba(79,93,117,0)"'),
        ):
            case(
                failures, directory, name,
                source.replace(RIBBON_FILL, repl, 1), source,
                "paints no fill", f"a ribbon made invisible by {name.split('-', 1)[1]}",
            )

        # 8o. Malformed attribute values must become findings, never tracebacks.
        #     A crash is the worst outcome available to a required gate: CI goes
        #     red with a stack trace that says nothing about the diagram, and the
        #     contributor cannot tell whether their file is wrong or the tool is.
        #     This case fuzzes the values that reach a numeric conversion, and
        #     asserts on the ABSENCE of a traceback rather than on any one
        #     message — a new parse added later is covered without being named.
        #     SUBSTITUTE the value; do not prepend a second copy of the
        #     attribute. ATTR_RE builds a dict, so a later duplicate wins and
        #     the fixture then tests the valid value while appearing to test
        #     the malformed one. The fill fuzz lands on the first ribbon; the
        #     stroke-width fuzz on the first legend swatch, the only shipped
        #     element that declares one.
        malformed = (
            (RIBBON_FILL, 'fill="rgba(79,93,117,zz)"', "a non-numeric rgba alpha"),
            (SWATCH, SWATCH.replace('stroke-width="1"', 'stroke-width="abc"'), "a non-numeric stroke-width"),
            (SWATCH, SWATCH.replace('stroke-width="1"', 'stroke-width="1.2.3"'), "a malformed stroke-width"),
            (SWATCH, SWATCH.replace('stroke-width="1"', 'stroke-width=""'), "an empty stroke-width"),
        )
        for original, attr, why in malformed:
            fixture = source.replace(original, attr, 1)
            if fixture == source:
                failures.append(f"could not build the {why} fixture (anchor moved)")
                continue
            code, output = run(write(directory, "fuzz.html", fixture))
            if "Traceback" in output:
                failures.append(f"{why} crashed the checker instead of reporting: {output.strip()[:200]}")
            elif code == 0:
                failures.append(f"{why} was accepted silently")
            else:
                print(f"OK: {why} is reported, not crashed")

        for attr, why in (('fill-opacity="abc"', "a non-numeric fill-opacity"),
                          ('fill-opacity="1.2.3"', "a malformed fill-opacity")):
            fixture = onribbon(source, attr)
            code, output = run(write(directory, "fuzz2.html", fixture))
            if "Traceback" in output:
                failures.append(f"{why} crashed the checker: {output.strip()[:200]}")
            elif code == 0:
                failures.append(f"{why} was accepted silently")
            else:
                print(f"OK: {why} is reported, not crashed")

        # 8p. Colour syntax, both polarities and every form. This file wrote a
        #     shape-matcher for whichever syntax was in front of it three times
        #     running, and each attempt rejected a valid colour or accepted an
        #     invisible one. The table is the point: modern space-separated rgb
        #     must pass, and an 8-digit hex with a zero alpha must not.
        for colour, visible in (
            ("rgb(79 93 117 / 0.18)", True),      # CSS Color 4, space separated
            ("rgb(79 93 117)", True),             # modern, no alpha at all
            ("rgba(79 93 117 / 18%)", True),      # percentage alpha
            ("#4f5d752e", True),                  # 8-digit hex, alpha 0x2e
            ("rgb(79 93 117 / 0)", False),        # modern, zero alpha
            ("#4f5d7500", False),                 # 8-digit hex, zero alpha
            ("hsl(215 20% 38% / 0)", False),      # not an rgb function at all
        ):
            fixture = source.replace(RIBBON_FILL, f'fill="{colour}"', 1)
            if fixture == source:
                failures.append("could not build the colour fixture (anchor moved)")
                continue
            code, output = run(write(directory, "colour.html", fixture))
            if "Traceback" in output:
                failures.append(f"fill={colour!r} crashed the checker: {output.strip()[:160]}")
            elif visible and code != 0:
                failures.append(f"fill={colour!r} is a visible colour but was rejected: {output.strip()[:160]}")
            elif not visible and code == 0:
                failures.append(f"fill={colour!r} paints nothing but was accepted")
            else:
                print(f"OK: fill={colour!r} reads as {'visible' if visible else 'invisible'}")

        # 8q. The dash pattern, both polarities. "Non-empty" is not the test:
        #     an invalid or all-zero dasharray makes the browser drop the
        #     property and draw a SOLID line, so it renders exactly like no
        #     dash at all and is not the form the reference permits.
        for dash, dashed in (
            ("4 3", True), ("4,3", True), ("2", True), ("4px 3px", True),
            ("banana", False), ("0", False), ("0 0", False),
            ("none", False), ("-4 3", False),
            # A unit decides whether the DECLARATION survives, and that is a
            # different question from what it measures. em and % resolve
            # against things this checker never sees, but their sign still
            # settles positivity, so they dash. "foo" is not a unit at all:
            # the browser drops the property and draws the solid line this
            # form exists to be distinguished from.
            ("4em 3em", True), ("4% 3%", True),
            ("4foo 3foo", False), ("4 3foo", False), ("4bar", False),
            # One review round later, the correction for `4foo` had been
            # hand-listed and rejected fifteen REAL units. So both edges of
            # the set are pinned here: one unit from each CSS Values 4
            # family, the uppercase spellings, and the invalid control.
            ("4cap 3cap", True), ("4lh 3lh", True), ("4ic 3ic", True),
            ("4rex 3rex", True), ("4rlh 3rlh", True), ("4ric 3ric", True),
            ("4vi 3vi", True), ("4vb 3vb", True), ("4dvh 3dvh", True),
            ("4svw 3svw", True), ("4lvmin 3lvmin", True),
            ("4cqw 3cqw", True), ("4cqmin 3cqmin", True),
            ("4CAP 3CAP", True), ("4Q 3Q", True),
        ):
            frag = (f'<path d="M140,64 L640,48" fill="none" stroke="#2d3142" '
                    f'stroke-width="1" stroke-dasharray="{dash}"/>')
            fixture = source.replace(anchor, "      " + frag + "\n" + anchor, 1)
            if fixture == source:
                failures.append("could not build the dash fixture (anchor moved)")
                continue
            code, output = run(write(directory, "dash.html", fixture))
            if dashed and code != 0:
                failures.append(f"stroke-dasharray={dash!r} is a real dash but was rejected: {output.strip()[:150]}")
            elif not dashed and code == 0:
                failures.append(f"stroke-dasharray={dash!r} renders solid but was exempted")
            else:
                print(f"OK: stroke-dasharray={dash!r} reads as {'dashed' if dashed else 'solid'}")

        # 8r. Fill reaching a ribbon indirectly. A ribbon with no fill of its
        #     own inherits from an <svg>/<g> ancestor or picks up a stylesheet
        #     rule, and renders invisibly while every coordinate stays correct —
        #     the same two routes closed for stroke-width one review earlier, so
        #     the guard is now the property SET rather than the one property.
        stripped = source.replace(" " + RIBBON_FILL + "/>", "/>", 1)
        if stripped == source:
            failures.append("could not build the inherited-fill fixture (anchor moved)")
        else:
            case(
                failures, directory, "inherit-svg",
                stripped.replace(SVG_OPEN, '<svg fill="none" viewBox="0 0 1000 560"', 1),
                source, "every descendant inherits",
                "a ribbon whose fill is inherited from the svg element",
            )
            case(
                failures, directory, "inherit-css",
                stripped.replace("<style>", "<style>\n    svg path { fill: none; }", 1),
                source, "may set only",
                "a ribbon whose fill comes from a stylesheet rule",
            )

        # 8s. The intersection the two earlier guards left open: a CONTAINER
        #     carrying a style or class. Geometry could not carry one and a
        #     container could not carry the paint attributes, but nothing
        #     stopped <svg style="fill:none"> — which every ribbon inherits.
        for name, mutated, why in (
            ("sty-svg",
             source.replace(SVG_OPEN, '<svg style="fill:none" viewBox="0 0 1000 560"', 1),
             "an svg carrying an inline paint style"),
            ("sty-width",
             source.replace(SVG_OPEN, '<svg style="stroke-width:30" viewBox="0 0 1000 560"', 1),
             "an svg carrying an inline stroke-width style"),
            # The element a contributor would actually reach for. There is no
            # <g> in the shipped example, so this fixture introduces the group
            # along with the style - which is how it would arrive in practice.
            ("sty-group",
             source.replace('aria-labelledby="sankey-title sankey-desc">',
                            'aria-labelledby="sankey-title sankey-desc">\n      <g style="fill:none">', 1)
                   .replace("    </svg>", "      </g>\n    </svg>", 1),
             "a group carrying an inline paint style"),
        ):
            case(failures, directory, name, mutated, source,
                 "can set a paint property", why)

        # 8t. Values a browser CLAMPS or resolves to nothing. This is one
        #     defect wearing three attribute names, and it was found three
        #     times because each fix landed on whichever name was in front of
        #     it. CSS clamps an <alpha-value> to [0,1], so a negative alpha
        #     renders fully transparent while its authored text still reads as
        #     a colour — a ribbon that balances the arithmetic and leaves a
        #     hole in the picture. And zero has more spellings than the regex
        #     that used to match it: `0` and `0.0` were caught, `.0`, `+0`,
        #     `0e5`, `0%` and every negative were not.
        for name, mutated, reject, describe in (
            ("alpha-neg", refill(source, "rgb(79 93 117 / -0.5)"), True,
             "a fill alpha CSS clamps to zero"),
            ("alpha-negpct", refill(source, "rgb(79 93 117 / -50%)"), True,
             "a percentage fill alpha CSS clamps to zero"),
            ("alpha-over", refill(source, "rgb(79 93 117 / 200%)"), False,
             "an alpha above 1, which clamps to 1 and still paints"),
            ("fo-neg", onribbon(source, 'fill-opacity="-0.5"'), True,
             "a fill-opacity CSS clamps to zero"),
            ("fo-ok", onribbon(source, 'fill-opacity="0.9"'), False,
             "an ordinary fill-opacity"),
            ("op-plain", onribbon(source, 'opacity="0"'), True,
             "the one spelling of zero opacity the old pattern caught"),
            ("op-pct", onribbon(source, 'opacity="0%"'), True,
             "zero opacity written as a percentage"),
            ("op-dot", onribbon(source, 'opacity=".0"'), True,
             "zero opacity written without its leading digit"),
            ("op-plus", onribbon(source, 'opacity="+0"'), True,
             "zero opacity written with a sign"),
            ("op-exp", onribbon(source, 'opacity="0e5"'), True,
             "zero opacity written in exponent form"),
            ("op-neg", onribbon(source, 'opacity="-1"'), True,
             "a negative opacity, which clamps to zero"),
            ("op-junk", onribbon(source, 'opacity="banana"'), True,
             "an opacity that is not a number"),
            ("op-live", onribbon(source, 'opacity="0.55"'), False,
             "an ordinary opacity, which must still pass"),
        ):
            if mutated == source:
                failures.append(f"could not build the {name} fixture (anchor moved)")
                continue
            code, output = run(write(directory, f"{name}.html", mutated))
            if reject and code == 0:
                failures.append(f"{describe} was accepted")
            elif not reject and code != 0:
                failures.append(f"{describe} was rejected: {output.strip()[:160]}")
            else:
                print(f"OK: {describe} reads the way it renders")

        # 8u. The allowlist audit. Every construct here was ACCEPTED by a
        #     checker that had already survived eleven review rounds, and every
        #     one of them renders a figure that lies while every coordinate it
        #     reads stays correct. They are not a list of seventeen bugs; they
        #     are one bug seventeen times — a blocklist fails open, so anything
        #     it was never told about is certified. Each was verified against a
        #     real browser render before it was closed, and each is pinned here
        #     because the allowlists that close them are the kind of thing a
        #     later contributor widens without knowing what they are for.
        if RIBBON not in source:
            failures.append("could not build the audit fixtures (ribbon anchor moved)")
        else:
            def wrapped(open_tag, close):
                return source.replace(RIBBON, open_tag + RIBBON + close, 1)

            def altered(old, new):
                return source.replace(RIBBON, RIBBON.replace(old, new, 1), 1)

            def alongside(markup):
                return source.replace(RIBBON, RIBBON + chr(10) + "      " + markup, 1)

            for name, mutated, expect, describe in (
                # Containers outside {svg, g}: every one of these is a place an
                # inherited paint property or a group opacity reaches a ribbon.
                ("aud-anchor", wrapped('<a fill-opacity="0">', "</a>"),
                 "does not read", "a ribbon under an <a> that zeroes its fill"),
                ("aud-anchor-style", wrapped('<a style="opacity:0">', "</a>"),
                 "does not read", "a ribbon under an <a> with a zero group opacity"),
                ("aud-switch", wrapped('<switch fill="none">', "</switch>"),
                 "does not read", "a ribbon under a <switch> that unpaints it"),
                # Geometry that never draws, but is still counted.
                ("aud-defs", wrapped("<defs>", "</defs>"),
                 "inside <defs>", "a ribbon parked in <defs>"),
                # Attributes that suppress, rescale or repaint.
                ("aud-syslang", altered("<path ", '<path systemLanguage="zxx" '),
                 "does not read", "a ribbon suppressed by conditional processing"),
                ("aud-visibility", wrapped('<g visibility="collapse">', "</g>"),
                 "a hidden element", "a ribbon hidden by visibility=collapse"),
                ("aud-paintserver", altered(RIBBON_FILL, 'fill="url(#nope)"'),
                 "paint server", "a ribbon painted from a paint server"),
                ("aud-nested-svg", wrapped('<svg x="0" y="0" width="1000" height="560" '
                                           'viewBox="0 0 1000 280">', "</svg>"),
                 "nests a second", "a nested <svg> rescaling the figure"),
                # The attribute scanner. Each of these turns every guard off.
                ("aud-charref", altered(RIBBON_FILL, 'fill="&#110;one"'),
                 "paints no fill", "a fill of none written as a character reference"),
                ("aud-singlequote", altered(RIBBON_FILL,
                                            "fill='rgba(79,93,117,0.18)' style='stroke-width:30'"),
                 "carries style", "a single-quoted style, invisible to a double-quote scan"),
                ("aud-duplicate", altered("<path ", '<path fill="none" '),
                 "paints no fill", "a duplicate fill, where the browser keeps the first"),
                ("aud-gt-in-value", altered("<path ", '<path aria-label="mobile > desktop" '),
                 "does not read", "a > inside a quoted value, which truncates a [^>]* capture"),
                # Ink that is not a ribbon.
                ("aud-fat-line", alongside('<line x1="150" y1="90" x2="150" y2="460" '
                                           'stroke="#f5f5f5" stroke-width="40"/>'),
                 "reads as a band", "a <line> wide enough to read as volume"),
                ("aud-cover", alongside('<rect x="600" y="90" width="300" height="380" '
                                        'fill="#f5f5f5"/>'),
                 "neither a node bar", "a rect painted over the figure"),
                # A dash that is not a dash.
                ("aud-zero-gap", alongside('<path d="M300,470 L700,470" fill="none" '
                                           'stroke="#4f5d75" stroke-width="1" '
                                           'stroke-dasharray="4000 0"/>'),
                 "neither a readable ribbon", "a dash pattern with no gap, which renders solid"),
                # CSS reaching the figure.
                ("aud-css-comment",
                 source.replace("<style>", "<style>" + chr(10)
                                + "    svg path { stroke-width/**/: 30px; }", 1),
                 "may set only", "a comment between a property and its colon"),
                ("aud-css-transform",
                 source.replace("<style>", "<style>" + chr(10)
                                + "    svg path { transform: scaleY(1.4); }", 1),
                 "may set only", "a CSS transform, which the attribute ban never saw"),
            ):
                case(failures, directory, name, mutated, source, expect, describe)

        # 8v. The node bar, both polarities — the same two rules that were
        #     already true of ribbons, arriving late because they had only ever
        #     been applied to ribbons.
        #
        #     A bar that paints no fill occupies the arithmetic without
        #     occupying the page: conservation balances, the stage totals agree,
        #     and the reader sees a column that is not there. And a bar written
        #     `width="12px"` is an ordinary SVG length that the file's own
        #     allowlist accepts — it used to produce no bar at all, and the
        #     figure was then rejected for having too few. One value, two
        #     parsers, disagreeing.
        if BAR not in source:
            failures.append("could not build the node-bar fixtures (bar anchor moved)")
        else:
            def rebar(old, new):
                return source.replace(BAR, BAR.replace(old, new, 1), 1)

            for name, mutated, reject, describe in (
                ("bar-nofill", rebar('fill="#2d3142"', 'fill="none"'), True,
                 "a node bar that paints no fill"),
                ("bar-transparent", rebar('fill="#2d3142"', 'fill="transparent"'), True,
                 "a node bar painted transparent"),
                ("bar-alpha-zero", rebar('fill="#2d3142"', 'fill="rgba(45,49,66,0)"'), True,
                 "a node bar whose fill alpha is zero"),
                ("bar-fill-opacity", rebar('fill="#2d3142"',
                                           'fill="#2d3142" fill-opacity="0"'), True,
                 "a node bar with a zero fill-opacity"),
                ("bar-unit-width", rebar('width="12"', 'width="12px"'), False,
                 "a node bar width carrying a unit"),
                ("bar-unit-height", rebar('height="32"', 'height="32px"'), False,
                 "a node bar height carrying a unit"),
                ("bar-signed", rebar('width="12"', 'width="+12"'), False,
                 "a node bar width carrying a sign"),
                ("bar-unit-origin", rebar('x="880" y="344"', 'x="880px" y="344px"'), False,
                 "node bar coordinates carrying units"),
            ):
                if mutated == source:
                    failures.append(f"could not build the {name} fixture (anchor moved)")
                    continue
                code, output = run(write(directory, f"{name}.html", mutated))
                if reject and code == 0:
                    failures.append(f"{describe} was accepted")
                elif not reject and code != 0:
                    failures.append(f"{describe} was rejected: {output.strip()[:160]}")
                else:
                    print(f"OK: {describe} reads the way it renders")

        # 8w. Lengths and paints the checker must not guess at.
        def rebar(old, new):
            return source.replace(BAR, BAR.replace(old, new, 1), 1)

        #
        #     A relative unit resolves against a font or a viewport that no gate
        #     here can see, so `width="12em"` was being read as 12px and every
        #     sum below computed against a bar that is not that size. An
        #     absolute one is arithmetic and must still work: 9pt IS 12px, and
        #     that bar is a bar. And a paint that cannot be parsed is refused
        #     rather than assumed — assuming it paints counts a shape that may
        #     not be there, assuming it does not drops one that is.
        for name, mutated, reject, describe in (
            ("len-em", rebar('width="12"', 'width="12em"'), True,
             "a bar width in em, which resolves against a font"),
            ("len-pct", rebar('height="32"', 'height="32%"'), True,
             "a bar height in %, which resolves against a viewport"),
            ("len-vw", rebar('x="880"', 'x="880vw"'), True,
             "a bar coordinate in vw"),
            ("len-pt", rebar('width="12"', 'width="9pt"'), False,
             "a bar width in pt, which is exactly 12px"),
            ("len-px", rebar('width="12"', 'width="12px"'), False,
             "a bar width in px"),
            ("paint-bad-fn", rebar('fill="#2d3142"', 'fill="rgba(45,49,66,zz)"'), True,
             "a bar fill whose alpha cannot be read"),
            ("paint-bad-fo", rebar('fill="#2d3142"',
                                   'fill="#2d3142" fill-opacity="abc"'), True,
             "a bar fill-opacity that is not a number"),
            ("paint-hex5", rebar('fill="#2d3142"', 'fill="#2d314"'), True,
             "a five-digit hex, which is not a colour"),
            ("paint-hex4", rebar('fill="#2d3142"', 'fill="#2d31"'), False,
             "a four-digit hex, which is RGBA and legal"),
            ("paint-hex8-zero", rebar('fill="#2d3142"', 'fill="#2d314200"'), True,
             "an eight-digit hex whose alpha is zero"),
        ):
            if mutated == source:
                failures.append(f"could not build the {name} fixture (anchor moved)")
                continue
            code, output = run(write(directory, f"{name}.html", mutated))
            if reject and code == 0:
                failures.append(f"{describe} was accepted")
            elif not reject and code != 0:
                failures.append(f"{describe} was rejected: {output.strip()[:160]}")
            else:
                print(f"OK: {describe} reads the way it renders")

        # 8x. The SVG number grammar, in path data and in label coordinates.
        #
        #     `.75`, `+1` and `1.5e-1` are all legal and all mean what they look
        #     like. The exponent form was REJECTED outright — not by the number
        #     pattern but by the command scan, which read the `e` of `5.2e2` as
        #     a path command — so a conforming ribbon was unparseable. And a
        #     leading-dot coordinate is worse than a rejection: `-?\d+` matches
        #     `75` inside `.75` and yields a different number rather than none.
        #
        #     The label half is the same fault one level over: `<text x="908px">`
        #     renders in exactly the same place, and a bare float() on it threw,
        #     was swallowed by `except ValueError: continue`, and dropped the bar
        #     from value validation while the file still passed. The last case
        #     proves the label is BOUND rather than merely tolerated.
        D = ("M132,120 C316,120 316,120 500,120 L500,224 "
             "C316,224 316,224 132,224 Z")
        LABEL = '<text x="908" y="252"'
        if D not in source or LABEL not in source:
            failures.append("could not build the number fixtures (anchor moved)")
        else:
            exponent = ("M 1.32e2,1.2e2 C 3.16e2,1.2e2 3.16e2,1.2e2 5e2,1.2e2 "
                        "L 5e2,2.24e2 C 3.16e2,2.24e2 3.16e2,2.24e2 1.32e2,2.24e2 Z")
            signed = ("M +132,+120 C +316,+120 +316,+120 +500,+120 L +500,+224 "
                      "C +316,+224 +316,+224 +132,+224 Z")
            for name, mutated, reject, describe in (
                ("num-exponent", source.replace(D, exponent, 1), False,
                 "a ribbon whose coordinates are in exponent form"),
                ("num-signed", source.replace(D, signed, 1), False,
                 "a ribbon whose coordinates carry a leading plus"),
                ("label-px", source.replace(LABEL, '<text x="908px" y="252"', 1), False,
                 "a label coordinate carrying a unit"),
                ("label-exponent", source.replace(LABEL, '<text x="9.08e2" y="252"', 1), False,
                 "a label coordinate in exponent form"),
                ("label-em", source.replace(LABEL, '<text x="33em" y="252"', 1), True,
                 "a label coordinate in em, which resolves against a font"),
                # The binding proof: falsify the value that this very label
                # prints. If the unit-bearing label were being skipped rather
                # than bound, this would pass exactly as it did before.
                ("label-px-bound",
                 source.replace(LABEL, '<text x="908px" y="252"', 1)
                       .replace(">9,400 min<", ">7,400 min<", 1), True,
                 "a falsified value on a label whose x carries a unit"),
            ):
                if mutated == source:
                    failures.append(f"could not build the {name} fixture (anchor moved)")
                    continue
                code, output = run(write(directory, f"{name}.html", mutated))
                if reject and code == 0:
                    failures.append(f"{describe} was accepted")
                elif not reject and code != 0:
                    failures.append(f"{describe} was rejected: {output.strip()[:160]}")
                else:
                    print(f"OK: {describe} reads the way it renders")

        # 9. Both polarities of the cross-variant check. --all reads the asset
        #    directory, so the variants are copied out, mutated, and checked
        #    against a checker pointed at the copy.
        sandbox = directory / "variants"
        (sandbox / "skills/diagram-design/assets").mkdir(parents=True)
        (sandbox / "skills/diagram-design/references").mkdir(parents=True)
        (sandbox / "scripts").mkdir()
        shutil.copy(CHECKER, sandbox / "scripts/verify-sankey.py")
        shutil.copy(REFERENCE, sandbox / "skills/diagram-design/references" / REFERENCE.name)
        for variant in sorted(ASSETS.glob("example-sankey*.html")):
            shutil.copy(variant, sandbox / "skills/diagram-design/assets" / variant.name)

        sandboxed = [sys.executable, str(sandbox / "scripts/verify-sankey.py"), "--all"]
        code, output = invoke(sandboxed)
        if code != 0:
            failures.append(f"untouched variants were rejected: {output.strip()}")
        else:
            print("OK: the three shipped variants agree on geometry")

        dark = sandbox / "skills/diagram-design/assets/example-sankey-dark.html"
        original_dark = dark.read_text(encoding="utf-8")
        nudged = original_dark.replace(
            '<rect x="880" y="344" width="12" height="32"',
            '<rect x="880" y="348.57" width="12" height="27.43"',
        )
        if nudged == original_dark:
            failures.append("could not build the drifted-variant fixture (anchor moved)")
        else:
            dark.write_text(nudged, encoding="utf-8")
            code, output = invoke(sandboxed)
            if code == 0:
                failures.append("a dark variant whose geometry drifted was accepted")
            elif "geometry differs" not in output:
                failures.append(f"drifted variant reported without a geometry finding: {output.strip()}")
            else:
                print("OK: a variant edited out of step with the others is rejected")
            dark.write_text(original_dark, encoding="utf-8")

        # 10. The reference-excerpt gate, both polarities. The shipped reference
        #     carries no ```svg sample today, so the gate is exercised by ADDING
        #     one to the sandbox copy: a literal excerpt of the example must
        #     pass, and the same excerpt nudged 2px must not. Nothing renders a
        #     code sample, so this is the one piece of geometry that can rot in
        #     total silence — and it is exactly what the next contributor copies.
        doc = sandbox / "skills/diagram-design/references" / REFERENCE.name
        original_doc = doc.read_text(encoding="utf-8")
        excerpt = '<rect x="500" y="120" width="12" height="104" fill="#2d3142"/>'
        if excerpt not in GOOD.read_text(encoding="utf-8"):
            failures.append("could not build the excerpt fixtures (bar anchor moved)")
        else:
            doc.write_text(original_doc + "\n```svg\n" + excerpt + "\n```\n",
                           encoding="utf-8")
            code, output = invoke(sandboxed)
            if code != 0:
                failures.append(f"a literal excerpt in the reference was rejected: {output.strip()}")
            else:
                print("OK: a reference sample that is a real excerpt passes")

            drifted = excerpt.replace('y="120"', 'y="118"')
            doc.write_text(original_doc + "\n```svg\n" + drifted + "\n```\n",
                           encoding="utf-8")
            code, output = invoke(sandboxed)
            if code == 0:
                failures.append("a reference sample that no longer matches the example was accepted")
            elif "Paste a real excerpt" not in output:
                failures.append(f"drifted sample reported without an excerpt finding: {output.strip()}")
            else:
                print("OK: a reference sample drifting from the example is rejected")
            doc.write_text(original_doc, encoding="utf-8")

        # 11. Remove a shipped variant. --all must not read two files, find
        #     nothing wrong, and call that a pass.
        (sandbox / "skills/diagram-design/assets" / "example-sankey-full.html").unlink()
        code, output = invoke(sandboxed)
        if code == 0:
            failures.append("--all passed with a shipped variant missing")
        elif "expects the three shipped variants" not in output:
            failures.append(f"missing variant reported without the expected reason: {output.strip()}")
        else:
            print("OK: --all refuses to run with a shipped variant missing")

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"\n{len(failures)} case(s) failed.")
        return 1
    print("\nAll sankey checker cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
