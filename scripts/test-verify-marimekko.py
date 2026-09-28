#!/usr/bin/env python3
"""Adversarial cases for verify-marimekko.py, both polarities.

Every case is named for exactly what it asserts — a name that overclaims is
itself a defect. The negative half matters as much as the positive: a checker
that fires on an honest figure, on the parent treemap, or on a sibling
contract's files gets widened or switched off, and then it guards nothing.

The scope treaty is pinned here in both directions: fixtures prove that the
parent's `data-share` on a <rect> and the siblings' `data-value` on a <circle>
never claim a file for this checker, and every sibling per-file verifier
present on the branch is run as a subprocess against the shipped marimekko
examples and must skip all three.

The parser cases are the ones the HTMLParser rewrite exists for: a quoted `>`
inside an attribute value must not end the tag, a repeated attribute must keep
its FIRST value, and a tag inside a comment must never be live markup. Scope
detection is held to the same reading: a commented-out rect claims nothing, a
live rect behind a quoted `>` is claimed and verified, and a data-segment
swallowed by an unbalanced quote fails closed. The CSS cases pin the SVG 2
size properties (`width`/`height` resize a rect behind its attributes) and
comment blanking (`/**/` is whitespace to the browser) in both polarities.

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

verify = __import__("verify-marimekko")

ASSETS = ROOT / "skills/diagram-design/assets"
SHIPPED = [ASSETS / name for name in (
    "example-marimekko.html", "example-marimekko-dark.html",
    "example-marimekko-full.html",
)]
TREEMAPS = sorted(ASSETS.glob("example-treemap*.html"))

HEAD = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>t</title>
<style>svg { width: 100%; } .eyebrow { text-transform: uppercase; }</style>
</head><body>
<svg viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg" role="img"
     aria-labelledby="marimekko-title marimekko-desc">
  <title id="marimekko-title">t</title>
  <desc id="marimekko-desc">Marimekko fixture.</desc>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
"""
TAIL = "</svg></body></html>\n"

# The fixture plot: x 40 → 940 with two 4px gutters, y 40 → 420. Three
# columns totalling 900, so shares read as whole numbers: A 500 (Linux 300,
# macOS 200), B 300 (Linux 240, Windows 60), C 100 (Linux only - a series
# absent from a column is omitted, never drawn at zero). Widths are exact to
# three decimals so no honest fixture ever leans on the tolerance.
TOP, HEIGHT, GUTTER = 40.0, 380.0, 4.0
INK = "rgba(45,49,66,0.16)"
HAIR = "rgba(45,49,66,0.30)"
ACCENT_FILL = "rgba(235,108,54,0.16)"

WA, WB, WC = 495.556, 297.333, 99.111
XA = 40.0
XB = round(XA + WA + GUTTER, 3)
XC = round(XB + WB + GUTTER, 3)


def segment(column: str, series: str, amount, x, y, w, h, fill: str = INK,
            stroke: str = HAIR, omit: str = "", extra: str = "",
            mask: bool = True) -> str:
    parts = []
    if omit != "data-column":
        parts.append('data-column="%s"' % column)
    if omit != "data-segment":
        parts.append('data-segment="%s"' % series)
    if omit != "data-amount":
        parts.append('data-amount="%s"' % amount)
    for key, value in (("x", x), ("y", y), ("width", w), ("height", h)):
        if omit != key:
            parts.append('%s="%s"' % (key, value))
    if extra:
        parts.append(extra)
    out = ""
    if mask:
        out += '  <rect x="%s" y="%s" width="%s" height="%s" rx="2" fill="#f5f5f5"/>\n' % (x, y, w, h)
    out += '  <rect %s rx="2" fill="%s" stroke="%s" stroke-width="1"/>\n' % (
        " ".join(parts), fill, stroke)
    return out


def label(column: str, series: str, x, y, text: str, size: float = 9,
          mono: bool = True, extra: str = "", role: str = "label") -> str:
    family = "'Geist Mono', monospace" if mono else "'Geist', sans-serif"
    return ('  <text data-column="%s" data-segment="%s" data-role="%s" x="%s" y="%s" '
            'font-size="%s" font-family="%s"%s>%s</text>\n'
            % (column, series, role, x, y, size, family,
               (" " + extra) if extra else "", text))


def caption(column: str, x, text=None, extra: str = "", bind=None) -> str:
    return ('  <text data-column="%s" data-role="caption" x="%s" y="438" font-size="9" '
            'font-family="\'Geist Mono\', monospace" text-anchor="middle"%s>%s</text>\n'
            % (column if bind is None else bind, x, (" " + extra) if extra else "",
               column if text is None else text))


def key(series: str, text=None, bind=None) -> str:
    return ('  <text data-segment="%s" data-role="key" x="272" y="497" font-size="8.5" '
            'font-family="\'Geist\', sans-serif">%s</text>\n'
            % (series if bind is None else bind, series if text is None else text))


def columns(a_linux: float = 228.0, a_mac: float = 152.0, wa: float = WA,
            b_linux: float = 304.0, b_win: float = 76.0,
            xb: float = XB, xc: float = XC, focal: bool = True,
            a_mac_y=None) -> str:
    body = segment("A", "Linux", 300, XA, TOP, wa, a_linux)
    body += segment("A", "macOS", 200, XA, TOP + a_linux if a_mac_y is None else a_mac_y,
                    wa, a_mac,
                    fill=ACCENT_FILL if focal else INK,
                    stroke="#eb6c36" if focal else HAIR)
    body += segment("B", "Linux", 240, xb, TOP, WB, b_linux)
    body += segment("B", "Windows", 60, xb, TOP + b_linux, WB, b_win)
    body += segment("C", "Linux", 100, xc, TOP, WC, HEIGHT)
    return body


CAPTIONS = (caption("A", round(XA + WA / 2, 3), "A · 56%")
            + caption("B", round(XB + WB / 2, 3), "B · 33%")
            + caption("C", round(XC + WC / 2, 3), "C · 11%"))
KEYS = key("Linux") + key("macOS") + key("Windows")
LABELS = (label("A", "Linux", XA + 16, TOP + 28, "300 min · 60%")
          + label("A", "macOS", XA + 16, TOP + 228 + 28, "200 min · 40%")
          + label("B", "Windows", XB + 16, TOP + 304 + 28, "60 min · 20%"))


def document(*blocks: str) -> str:
    return HEAD + "".join(blocks) + TAIL


def honest(*extra: str) -> str:
    return document(columns(), CAPTIONS, KEYS, LABELS, *extra)


class Harness:
    def __init__(self) -> None:
        self.failures = 0
        self.count = 0
        # A private temp dir per instance: fixture names are meaningful to the
        # checker (it keys detection off the filename) but their directory is
        # not, so there is no reason to put them anywhere a real file lives.
        self.dir = Path(tempfile.mkdtemp(prefix="marimekko-fixtures-"))

    def close(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def path_for(self, name: str) -> Path:
        return self.dir / name

    def run(self, source: str, name: str = "example-marimekko-fixture.html") -> list:
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
        """Not merely finding-free — genuinely outside this checker's scope."""
        self.count += 1
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            detected = verify.looks_like_marimekko(path, source)
            found = verify.check(path)
        finally:
            path.unlink()
        if detected or found:
            self.failures += 1
            print("FAIL  %s\n        detected=%s findings=%d"
                  % (case, detected, len(found)))
            return
        print("ok    %s" % case)

    def expect_detected(self, case: str, source: str, name: str) -> None:
        self.count += 1
        path = self.path_for(name)
        path.write_text(source, encoding="utf-8")
        try:
            detected = verify.looks_like_marimekko(path, source)
        finally:
            path.unlink()
        if detected:
            print("ok    %s" % case)
            return
        self.failures += 1
        print("FAIL  %s\n        not detected" % case)

    def check(self, case: str, condition: bool, detail: str = "") -> None:
        self.count += 1
        if condition:
            print("ok    %s" % case)
            return
        self.failures += 1
        print("FAIL  %s%s" % (case, ("\n        " + detail) if detail else ""))


def run_cases(h: Harness) -> int:
    # ── Shipped examples and the honest fixture ───────────────────────────
    for path in SHIPPED:
        h.expect_clean("shipped %s passes untouched" % path.name,
                       path.read_text(encoding="utf-8"), path.name)
    h.expect_clean("an honest three-column fixture passes", honest())
    h.expect_clean("a column with one series is honest: an absent series is omitted, "
                   "not drawn at zero", honest())
    h.expect_clean("scenery rects (background, paper masks, legend swatches) are ignored",
                   honest('  <rect x="40" y="488" width="16" height="10" rx="2" fill="%s"/>\n'
                          % INK))
    h.expect_clean("no focal segment is a valid figure", document(
        columns(focal=False), CAPTIONS, KEYS, LABELS))
    h.expect_clean("a printed integer percentage within 1pp of the true share passes",
                   document(columns(), CAPTIONS, KEYS,
                            label("A", "Linux", XA + 16, TOP + 28, "300 min · 60.4%")))
    h.expect_clean("the stylesheet's `text-transform` and `width` on the svg are not "
                   "geometry moves", honest())
    h.expect_clean("an information marker inside a segment passes",
                   honest('  <circle cx="%s" cy="%s" r="5" fill="#2d3142"/>\n'
                          % (XC + WC / 2, TOP + 24)))

    # ── The parser reads what the browser reads ───────────────────────────
    h.expect_clean("a segment rect inside a comment is not live markup", honest(
        '  <!-- <rect data-column="Z" data-segment="Linux" data-amount="900" '
        'x="0" y="0" width="1" height="1"/> -->\n'))
    h.expect_clean("a repeated attribute keeps its FIRST value (honest first, junk second)",
                   document(
                       segment("A", "Linux", 300, XA, TOP, WA, 228.0, extra='width="1"'),
                       segment("A", "macOS", 200, XA, TOP + 228, WA, 152.0),
                       segment("B", "Linux", 240, XB, TOP, WB, 304.0),
                       segment("B", "Windows", 60, XB, TOP + 304, WB, 76.0),
                       segment("C", "Linux", 100, XC, TOP, WC, HEIGHT),
                       CAPTIONS, KEYS))
    h.expect_finding("a repeated attribute keeps its FIRST value (junk first, honest second)",
                     document(
                         '  <rect data-column="A" data-segment="Linux" data-amount="300" '
                         'x="%s" y="%s" width="1" width="%s" height="228" rx="2" fill="%s"/>\n'
                         % (XA, TOP, WA, INK),
                         segment("A", "macOS", 200, XA, TOP + 228, WA, 152.0),
                         segment("B", "Linux", 240, XB, TOP, WB, 304.0),
                         segment("B", "Windows", 60, XB, TOP + 304, WB, 76.0),
                         segment("C", "Linux", 100, XC, TOP, WC, HEIGHT),
                         CAPTIONS, KEYS),
                     r"full width of its column")
    h.expect_finding("a quoted `>` inside an attribute does not end the tag: the ancestor "
                     "transform behind it is still seen",
                     document('<g data-note=">" transform="translate(0 -80)">\n',
                              columns(), "</g>\n", CAPTIONS, KEYS, LABELS),
                     r"ancestor <g>/<svg> transform")
    h.expect_clean("upper-case tag and attribute names parse as their canonical form",
                   honest().replace("<rect ", "<RECT ").replace("data-amount=", "DATA-AMOUNT="))

    # ── Width is category share ───────────────────────────────────────────
    h.expect_finding("a column drawn wider than its share is rejected",
                     document(columns(wa=WA + 150, xb=XB + 150, xc=XC + 150), CAPTIONS, KEYS),
                     r"column 'A' is .* wide, .* but its 500 of 900")
    h.expect_finding("a segment narrower than its column is rejected",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-amount="200" x="%s" y="%s" width="%s"' % (XA, TOP + 228, WA),
                         'data-amount="200" x="%s" y="%s" width="%s"' % (XA, TOP + 228, WA - 40)),
                     r"full width of its column")

    # ── Segments tile the column; height is within-column share ──────────
    h.expect_finding("a segment boundary moved off its share is rejected",
                     document(columns(a_linux=260.0, a_mac=120.0), CAPTIONS, KEYS),
                     r"segment A × Linux is 260 px tall")
    h.expect_finding("a gap between segments is rejected",
                     document(columns(a_linux=200.0, a_mac_y=TOP + 228), CAPTIONS, KEYS),
                     r"starts 28 px below the end of A × Linux")
    h.expect_finding("overlapping segments are rejected",
                     document(columns(a_linux=250.0, a_mac_y=TOP + 228), CAPTIONS, KEYS),
                     r"starts 22 px above the end of A × Linux")
    h.expect_finding("a column shorter than the plot is rejected",
                     document(columns(b_linux=280.0, b_win=70.0), CAPTIONS, KEYS),
                     r"full plot height")

    # ── Area is joint share ───────────────────────────────────────────────
    h.expect_finding("an inflated column is also caught by the area check, on every "
                     "segment it holds",
                     document(columns(a_linux=228.0, a_mac=152.0, wa=WA + 150,
                                      xb=XB + 150, xc=XC + 150),
                              CAPTIONS, KEYS),
                     r"segment A × Linux draws .* of the area but 300 of 900")

    # ── Columns tile the plot ─────────────────────────────────────────────
    h.expect_finding("an unequal gutter is rejected",
                     document(columns(xc=XC + 12), CAPTIONS, KEYS),
                     r"gutter before column 'C' is 16 px but the first gutter is 4 px")
    h.expect_finding("overlapping columns are rejected",
                     document(columns(xb=XB - 20, xc=XC - 20), CAPTIONS, KEYS),
                     r"columns never overlap")

    # ── One series order ──────────────────────────────────────────────────
    h.expect_only_one("a series drawn in a different order in one column is rejected, once",
                      document(
                          segment("A", "Linux", 300, XA, TOP, WA, 228.0),
                          segment("A", "macOS", 200, XA, TOP + 228, WA, 152.0),
                          segment("B", "macOS", 240, XB, TOP, WB, 304.0),
                          segment("B", "Linux", 60, XB, TOP + 304, WB, 76.0),
                          segment("C", "Linux", 100, XC, TOP, WC, HEIGHT),
                          CAPTIONS, key("Linux"), key("macOS")),
                      r"column 'B' draws 'macOS' above 'Linux', but column 'A'")

    # ── One accent ────────────────────────────────────────────────────────
    h.expect_only_one("a second accent segment is rejected, once",
                      document(columns(), CAPTIONS, KEYS).replace(
                          'data-column="C" data-segment="Linux" data-amount="100" x="%s" y="%s" '
                          'width="%s" height="%s" rx="2" fill="%s" stroke="%s"'
                          % (XC, TOP, WC, HEIGHT, INK, HAIR),
                          'data-column="C" data-segment="Linux" data-amount="100" x="%s" y="%s" '
                          'width="%s" height="%s" rx="2" fill="%s" stroke="#eb6c36"'
                          % (XC, TOP, WC, HEIGHT, ACCENT_FILL)),
                      r"one focal segment max")

    # ── Unpositioned geometry: three carriers, element and ancestor ──────
    h.expect_finding("a transform attribute on a segment is refused",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-column="C" data-segment="Linux"',
                         'transform="translate(0 -10)" data-column="C" data-segment="Linux"'),
                     r"segment C × Linux carries transform=")
    h.expect_finding("an inline style translate on a bound label is refused",
                     document(columns(), CAPTIONS, KEYS,
                              label("A", "Linux", XA + 16, TOP + 28, "300 min",
                                    extra='style="translate: 0 40px"')),
                     r"bound label .* carries style=.*the translate property")
    h.expect_finding("an inline style transform on a caption is refused",
                     document(columns(), KEYS,
                              caption("A", round(XA + WA / 2, 3), extra='style="transform: translateX(300px)"'),
                              caption("B", round(XB + WB / 2, 3)),
                              caption("C", round(XC + WC / 2, 3))),
                     r"bound label \(A\) carries style=")
    h.expect_finding("a transform on an ancestor <g> is refused",
                     document('<g transform="scale(1.1)">\n', columns(), "</g>\n", CAPTIONS, KEYS),
                     r"ancestor <g>/<svg> transform")
    h.expect_finding("a transform in a <style> block is refused",
                     honest("<style>rect { transform: translateY(-8px); }</style>\n"),
                     r"CSS `transform` declaration")
    h.expect_finding("a CSS `x` geometry property in a <style> block is refused",
                     honest("<style>text { x: 0; }</style>\n"),
                     r"CSS `x` declaration")
    h.expect_finding("a vendor-prefixed transform in a <style> block is refused",
                     honest("<style>rect { -webkit-transform: rotate(1deg); }</style>\n"),
                     r"CSS `transform` declaration")

    # ── CSS width/height resize a rect behind its attributes (SVG 2) ─────
    h.expect_finding("an inline style width on a segment rect is refused",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-column="C" data-segment="Linux"',
                         'style="width: 600px" data-column="C" data-segment="Linux"'),
                     r"segment C × Linux carries style=.*the width property")
    h.expect_finding("an inline style height on a segment rect is refused",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-column="C" data-segment="Linux"',
                         'style="height: 10px" data-column="C" data-segment="Linux"'),
                     r"segment C × Linux carries style=.*the height property")
    h.expect_finding("an inline style width on an ancestor <g> is refused",
                     document('<g style="width: 600px">\n', columns(), "</g>\n", CAPTIONS, KEYS),
                     r"ancestor <g>/<svg> style transform")
    h.expect_finding("an inline style height on an ancestor <g> is refused",
                     document('<g style="height: 10px">\n', columns(), "</g>\n", CAPTIONS, KEYS),
                     r"ancestor <g>/<svg> style transform")
    h.expect_finding("a `width` rule selecting rects in a <style> block is refused",
                     honest("<style>rect { width: 600px; }</style>\n"),
                     r"CSS `width` declaration")
    h.expect_finding("a `height` rule selecting by data-segment in a <style> block is refused",
                     honest("<style>[data-segment] { height: 10px; }</style>\n"),
                     r"CSS `height` declaration")
    h.expect_finding("a `width` rule reaching rects through a `*` subject is refused",
                     honest("<style>svg > * { width: 600px; }</style>\n"),
                     r"CSS `width` declaration")
    h.expect_clean("a `width`/`height` rule whose subject no segment rect can be "
                   "(the svg, a legend swatch class) is not a geometry move",
                   honest("<style>svg { width: 100%; } .card-dot { width: 7px; height: 7px; }"
                          " .legend text { height: 1em; }</style>\n"))

    # ── A CSS comment is whitespace to the browser, so it is here too ─────
    h.expect_finding("a `/**/`-prefixed inline transform on a segment is refused",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-column="C" data-segment="Linux"',
                         'style="/**/transform: translateY(-8px)" data-column="C" '
                         'data-segment="Linux"'),
                     r"segment C × Linux carries style=.*the transform property")
    h.expect_finding("a `/**/`-prefixed width in a <style> rule is refused",
                     honest("<style>rect { /**/ width: 600px; }</style>\n"),
                     r"CSS `width` declaration")
    h.expect_clean("a transform inside a CSS comment, inline or in a <style> block, is "
                   "not a geometry move",
                   document(columns(), CAPTIONS, KEYS,
                            label("A", "Linux", XA + 16, TOP + 28, "300 min",
                                  extra='style="fill: #2d3142 /* transform: translateY(40px) */"'),
                            "<style>rect { /* transform: translateY(-8px); */ fill: red; }"
                            "</style>\n"))

    # ── Labels bound to meaning ───────────────────────────────────────────
    h.expect_finding("a caption anchored off its column centre is rejected",
                     document(columns(), KEYS,
                              caption("A", round(XA + WA / 2 + 30, 3)),
                              caption("B", round(XB + WB / 2, 3)),
                              caption("C", round(XC + WC / 2, 3))),
                     r"caption for column 'A' is anchored at x=.* but the column is centred")
    h.expect_finding("a caption that does not name its column is rejected",
                     document(columns(), KEYS,
                              caption("A", round(XA + WA / 2, 3), text="B · 56%"),
                              caption("B", round(XB + WB / 2, 3)),
                              caption("C", round(XC + WC / 2, 3))),
                     r"caption for column 'A' reads 'B · 56%', which does not name")
    h.expect_finding("a caption printing the wrong column share is rejected",
                     document(columns(), KEYS,
                              caption("A", round(XA + WA / 2, 3), text="A · 40%"),
                              caption("B", round(XB + WB / 2, 3)),
                              caption("C", round(XC + WC / 2, 3))),
                     r"caption for column 'A' prints 40% but the column is 55.6%")
    h.expect_finding("a missing caption is rejected",
                     document(columns(), KEYS,
                              caption("A", round(XA + WA / 2, 3)),
                              caption("B", round(XB + WB / 2, 3))),
                     r"column 'C' has no caption")
    h.expect_finding("a second caption for one column is rejected",
                     honest(caption("A", round(XA + WA / 2, 3))),
                     r"second caption for column 'A'")
    h.expect_finding("a caption binding an undeclared column is rejected",
                     honest(caption("Q", 500)),
                     r"caption 'Q' binds column 'Q', which no segment declares")
    h.expect_finding("a missing legend key is rejected",
                     document(columns(), CAPTIONS, key("Linux"), key("macOS")),
                     r"series 'Windows' has no legend key")
    h.expect_finding("a legend key that does not name its series is rejected",
                     document(columns(), CAPTIONS, key("Linux"), key("macOS"),
                              key("Windows", text="Win")),
                     r"legend key for series 'Windows' reads 'Win'")
    h.expect_finding("a second legend key for one series is rejected",
                     honest(key("Linux")),
                     r"second legend key for series 'Linux'")
    h.expect_finding("a legend key naming an undeclared series is rejected",
                     honest(key("BSD")),
                     r"legend key 'BSD' names series 'BSD', which no segment declares")
    h.expect_finding("a label anchored outside the segment it binds is rejected",
                     honest(label("A", "Linux", XB + 16, TOP + 28, "300 min")),
                     r"anchored at .* outside the .* segment A × Linux")
    h.expect_finding("a label that overflows its segment is rejected",
                     honest(label("C", "Linux", XC + 16, TOP + 28,
                                  "one hundred minutes on Linux runners")),
                     r"overflows its .* segment C × Linux by .* right")
    h.expect_finding("a label printing the wrong amount is rejected",
                     honest(label("B", "Linux", XB + 16, TOP + 28, "250 min")),
                     r"label '250 min' prints 250 but segment B × Linux declares data-amount=240")
    h.expect_finding("a label printing the wrong within-column share is rejected",
                     honest(label("B", "Linux", XB + 16, TOP + 28, "240 min · 70%")),
                     r"prints 70% but segment B × Linux is 80.0% of its column")
    h.expect_finding("a label binding a segment no rect declares is rejected",
                     honest(label("C", "Windows", XC + 8, TOP + 28, "1 min")),
                     r"binds segment C × Windows, which no rect declares")
    h.expect_finding("a bound text with an unknown role is rejected",
                     honest(label("A", "Linux", XA + 16, TOP + 28, "note", role="note")),
                     r"declares data-role='note'")
    h.expect_finding("a bound text with no role is rejected",
                     honest('  <text data-column="A" x="60" y="60">A</text>\n'),
                     r"declares data-role=None")
    h.expect_finding("an information marker crossing its segment edge is rejected",
                     honest('  <circle cx="%s" cy="%s" r="5" fill="#2d3142"/>\n'
                            % (XC + WC - 2, TOP + 24)),
                     r"information marker overflows its .* segment C × Linux by .* right")

    # ── Declarations ──────────────────────────────────────────────────────
    h.expect_finding("a second rect for one segment is rejected",
                     honest(segment("C", "Linux", 100, XC, TOP, WC, HEIGHT, mask=False)),
                     r"second rect declares segment C × Linux")
    h.expect_finding("a zero amount is rejected: an absent series is omitted, never drawn",
                     honest(segment("C", "Windows", 0, XC, TOP + HEIGHT, WC, 0.0001, mask=False)),
                     r"declares data-amount='0'")
    h.expect_finding("a non-numeric amount is rejected",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-amount="100"', 'data-amount="lots"'),
                     r"declares data-amount='lots'")
    h.expect_finding("a NaN amount is rejected, not silently accepted by every tolerance",
                     document(columns(), CAPTIONS, KEYS).replace(
                         'data-amount="100"', 'data-amount="nan"'),
                     r"declares data-amount='nan'")
    h.expect_finding("a segment with no data-amount is rejected",
                     honest(segment("C", "Windows", 5, XC, TOP, WC, 10, omit="data-amount", mask=False)),
                     r"segment C × Windows declares no data-amount")
    h.expect_finding("a segment with no data-column is rejected",
                     honest(segment("C", "Windows", 5, XC, TOP, WC, 10, omit="data-column", mask=False)),
                     r"must name both its column")
    h.expect_finding("a segment with unparseable geometry is rejected",
                     honest(segment("C", "Windows", 5, XC, TOP, WC, 10, omit="height", mask=False)),
                     r"segment C × Windows has missing or unparseable")

    # ── Fail closed ───────────────────────────────────────────────────────
    h.expect_finding("a file named for the type that declares nothing is a finding, not a pass",
                     document(), r"declares 0 verifiable column\(s\)")
    h.expect_finding("a single column is not a marimekko",
                     document(segment("A", "Linux", 300, XA, TOP, WA, 228.0),
                              segment("A", "macOS", 200, XA, TOP + 228, WA, 152.0)),
                     r"declares 1 verifiable column\(s\)")
    h.expect_finding("a file whose description claims the type is held to the contract",
                     document().replace("Marimekko fixture.", "A marimekko of nothing."),
                     r"declares 0 verifiable column\(s\)", name="example-anything.html")
    h.expect_detected("data-segment on a <rect> claims a file whatever it is called",
                      document(columns()), "example-anything.html")

    # ── Scope is read the way the browser reads, not by a tag regex ───────
    # Each fixture is named and described for another family, so the only
    # signal that could claim it is the data-segment in its markup.
    commented_out = (HEAD.replace("Marimekko fixture.", "Bar fixture.")
                     + '  <!-- <rect data-column="Z" data-segment="Linux" data-amount="900" '
                     'x="0" y="0" width="1" height="1"/> -->\n' + TAIL)
    h.expect_out_of_scope("a data-segment rect that exists only inside a comment never "
                          "claims a file", commented_out, "example-bar-fixture.html")
    commented_path = h.path_for("example-bar-fixture.html")
    commented_path.write_text(commented_out, encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify-marimekko.py"), str(commented_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    finally:
        commented_path.unlink()
    h.check(
        "the CLI skips the commented-out fixture cleanly, as an --all run would",
        result.returncode == 0 and "1 file(s) skipped as out of scope" in result.stdout,
        "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
    )
    broken = (HEAD.replace("Marimekko fixture.", "Bar fixture.")
              + '  <rect data-note=">" x="%s data-segment="Linux" data-column="A" '
              'data-amount="300" y="%s" width="%s" height="228"/>\n' % (XA, TOP, WA)
              + TAIL)
    h.expect_detected("a data-segment swallowed by an unbalanced quote, behind a quoted `>`, "
                      "still claims the file", broken, "example-anything.html")
    h.expect_finding("a data-segment that no parsed element carries is a finding, never "
                     "a skip", broken,
                     r"declares data-segment but no complete <rect> could be parsed",
                     name="example-anything.html")
    quoted = document(columns(), CAPTIONS, KEYS, LABELS).replace(
        "Marimekko fixture.", "Bar fixture.").replace(
        "<rect data-column=", '<rect data-note=">" data-column=')
    h.expect_detected("a live rect with a quoted `>` before its data-segment claims the file",
                      quoted, "example-anything.html")
    h.expect_clean("... and an honest one passes", quoted, name="example-anything.html")
    h.expect_finding("... and a dishonest one is verified, not skipped",
                     quoted.replace('width="%s" height="228.0"' % WA,
                                    'width="%s" height="228.0"' % (WA + 150)),
                     r"full width of its column", name="example-anything.html")

    # ── Scope treaty with the parent and the siblings ─────────────────────
    h.expect_out_of_scope(
        "the parent treemap's data-share on a <rect> never claims a file for this checker",
        HEAD.replace("Marimekko fixture.", "Treemap fixture.")
        + '  <rect x="40" y="40" width="400" height="300" rx="2" data-share="50"/>\n'
        + '  <rect x="444" y="40" width="400" height="300" rx="2" data-share="50"/>\n' + TAIL,
        "example-treemap-fixture.html")
    h.expect_out_of_scope(
        "data-segment on a <text> alone (no <rect>) never claims a file",
        HEAD.replace("Marimekko fixture.", "Bar fixture.")
        + '  <text data-segment="Linux" x="10" y="10">Linux</text>\n' + TAIL,
        "example-bar-fixture.html")
    h.expect_out_of_scope(
        "the beeswarm's data-value on a <circle> never claims a file",
        HEAD.replace("Marimekko fixture.", "Beeswarm fixture.")
        + '  <circle data-value="12" cx="80" cy="230" r="4"/>\n' + TAIL,
        "example-beeswarm-fixture.html")
    for path in TREEMAPS:
        h.expect_out_of_scope("shipped %s is out of scope" % path.name,
                              path.read_text(encoding="utf-8"), path.name)

    # Every sibling per-file verifier present on the branch must SKIP the
    # shipped marimekko files — a treaty is two-sided. Checked against the
    # siblings' real CLIs, not a re-implementation; siblings not on this
    # branch are reported as skipped rather than failed.
    for sibling in ("verify-slopegraph.py", "verify-bump.py", "verify-ridgeline.py",
                    "verify-bubble.py", "verify-beeswarm.py", "verify-streamgraph.py"):
        script = ROOT / "scripts" / sibling
        if not script.exists():
            print("skip  %s is not on this branch; treaty case not run" % sibling)
            continue
        result = subprocess.run(
            [sys.executable, str(script)] + [str(p) for p in SHIPPED],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        h.check(
            "%s skips all three shipped marimekko files" % sibling,
            result.returncode == 0
            and "3 file(s) skipped as out of scope" in result.stdout,
            "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
        )
    # The parent gate's treaty line is its filename glob: `verify-treemap.py
    # --all` reads example-treemap*.html and nothing else, so the marimekko
    # files are never held to the treemap contract in CI. Pinned against the
    # real CLI so a widened glob upstream is caught here.
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify-treemap.py"), "--all"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    h.check(
        "verify-treemap.py --all never reads the shipped marimekko files",
        result.returncode == 0 and "marimekko" not in result.stdout,
        "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()[:200]),
    )

    # ── The CLI ───────────────────────────────────────────────────────────
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify-marimekko.py")] + [str(p) for p in TREEMAPS],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    h.check(
        "the CLI reports the parent's files as skipped, not as passing",
        result.returncode == 0 and "no marimekko found to check" in result.stdout
        and "%d file(s) skipped" % len(TREEMAPS) in result.stdout,
        "exit=%d stdout=%s" % (result.returncode, result.stdout.strip()),
    )
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/verify-marimekko.py")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    h.check("the CLI exits 2 with no arguments", result.returncode == 2)

    # ── The fixture-isolation guarantees, held in place ───────────────────
    sentinel = ROOT / "example-marimekko-fixture.html"
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
    print("OK marimekko checker: %d case(s), both polarities" % h.count)
    return 0


def main() -> int:
    h = Harness()
    try:
        return run_cases(h)
    finally:
        h.close()


if __name__ == "__main__":
    raise SystemExit(main())
