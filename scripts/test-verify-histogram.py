#!/usr/bin/env python3
"""Adversarial cases for verify-histogram.py, both polarities.

Every case is named for exactly what it asserts. The negative half matters as
much as the positive: a checker that fires on the honest shipped examples, or
on the other example types, gets widened or switched off, and then it guards
nothing.

Fixtures live in a per-process temporary directory, mutated from the shipped
light example so each case differs from a known-good file by exactly the
defect under test.

Exit: 0 all pass, 1 any failure.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

verify = __import__("verify-histogram")

SHIPPED = ROOT / "skills/diagram-design/assets/example-histogram.html"
SHIPPED_DARK = ROOT / "skills/diagram-design/assets/example-histogram-dark.html"
SHIPPED_FULL = ROOT / "skills/diagram-design/assets/example-histogram-full.html"
BAR = ROOT / "skills/diagram-design/assets/example-bar.html"

TMP = Path(tempfile.mkdtemp(prefix="verify-histogram-test-"))

FAILURES: list = []


def case(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print("PASS  %s" % name)
    else:
        print("FAIL  %s%s" % (name, "  [%s]" % detail if detail else ""))
        FAILURES.append(name)


def mutate(tag: str, old: str, new: str, count: int = 1) -> Path:
    source = SHIPPED.read_text(encoding="utf-8")
    assert old in source, "mutation anchor missing: %r" % old
    mutated = source.replace(old, new, count)
    path = TMP / ("example-histogram-%s.html" % tag)
    path.write_text(mutated, encoding="utf-8")
    return path


def findings_of(path: Path) -> list:
    return verify.check(path)


# ── positive polarity: the shipped examples are clean ────────────────────────

case("shipped light example passes", findings_of(SHIPPED) == [],
     "; ".join(findings_of(SHIPPED)[:2]))
case("shipped dark example passes", findings_of(SHIPPED_DARK) == [],
     "; ".join(findings_of(SHIPPED_DARK)[:2]))
case("shipped full example passes", findings_of(SHIPPED_FULL) == [],
     "; ".join(findings_of(SHIPPED_FULL)[:2]))

# ── negative polarity: other example types stay out of scope ─────────────────

case("shipped bar example is out of scope, not flagged",
     findings_of(BAR) == [])

# ── equal bins ────────────────────────────────────────────────────────────────

unequal_declared = mutate("unequal-declared",
                          'data-bin-start="900" data-bin-end="1000"',
                          'data-bin-start="900" data-bin-end="1100"')
case("unequal declared bin width is a finding",
     any("unequal bins" in f for f in findings_of(unequal_declared)))

unequal_pixel = mutate("unequal-pixel",
                       'data-bin-start="900" data-bin-end="1000" data-count="3" x="872" y="412.88" width="88"',
                       'data-bin-start="900" data-bin-end="1000" data-count="3" x="872" y="412.88" width="120"')
case("unequal drawn bar width is a finding",
     any("equal intervals must draw equal widths" in f
         for f in findings_of(unequal_pixel)))

# ── tiling ────────────────────────────────────────────────────────────────────

declared_gap = mutate("declared-gap",
                      'data-bin-start="900" data-bin-end="1000"',
                      'data-bin-start="910" data-bin-end="1010"')
case("a hole between declared bins is a finding",
     any("do not tile" in f for f in findings_of(declared_gap)))

pixel_gap = mutate("pixel-gap",
                   'data-count="3" x="872"', 'data-count="3" x="878"')
case("a drawn gap between adjacent bars is a finding",
     any("gap or overlap" in f for f in findings_of(pixel_gap)))

# ── baseline and count scale ─────────────────────────────────────────────────

floating_bar = mutate("floating-bar",
                      'data-count="36" x="520" y="334.5" width="88" height="85.5"',
                      'data-count="36" x="520" y="322.5" width="88" height="85.5"')
case("a bar off the shared baseline is a finding",
     any("off the shared baseline" in f for f in findings_of(floating_bar)))

inflated_bar = mutate("inflated-bar",
                      'data-count="36" x="520" y="334.5" width="88" height="85.5"',
                      'data-count="36" x="520" y="298.5" width="88" height="121.5"')
case("a bar taller than its count is a finding",
     any("height must be proportional to count" in f
         for f in findings_of(inflated_bar)))

no_zero_tick = mutate("no-zero-tick",
                      '<text data-count-tick="0"   x="72" y="424" fill="#4f5d75" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="end">0</text>',
                      '')
case("a missing 0 tick is a finding",
     any("baseline must be zero" in f for f in findings_of(no_zero_tick)))

bent_tick = mutate("bent-tick",
                   'data-count-tick="80"  x="72" y="234"',
                   'data-count-tick="80"  x="72" y="260"')
case("a count tick off the one linear scale is a finding",
     any("bent or truncated count axis" in f for f in findings_of(bent_tick)))

# ── n and labels ─────────────────────────────────────────────────────────────

n_mismatch = mutate("n-mismatch",
                    'data-role="n" data-value="550"', 'data-role="n" data-value="600"')
case("n disagreeing with the bins' sum is a finding",
     any("silently dropped or invented" in f for f in findings_of(n_mismatch)))

n_print_mismatch = mutate("n-print",
                          '>n = 550</text>', '>n = 600</text>')
case("n printing a number other than it declares is a finding",
     any("n label prints" in f for f in findings_of(n_print_mismatch)))

label_lies = mutate("label-lies",
                    'data-bin-start="200" data-role="count" x="300" y="41.5" fill="#eb6c36" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle" font-weight="600">156<',
                    'data-bin-start="200" data-role="count" x="300" y="41.5" fill="#eb6c36" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle" font-weight="600">165<')
case("a count label disagreeing with its bin is a finding",
     any("count label prints" in f for f in findings_of(label_lies)))

edge_lies = mutate("edge-lies",
                   'data-edge="500"  x="520"', 'data-edge="500"  x="540"')
case("an edge numeral off its boundary is a finding",
     any("names a boundary it is not on" in f for f in findings_of(edge_lies)))

# ── marker honesty ───────────────────────────────────────────────────────────

moved_marker = mutate("moved-marker",
                      'x1="360.72" y1="56" x2="360.72" y2="420"',
                      'x1="300.72" y1="56" x2="300.72" y2="420"')
case("a marker away from its declared value is a finding",
     any("drawn at x=" in f for f in findings_of(moved_marker)))

flattering_mean = mutate("flattering-mean",
                         'data-marker="mean" data-value="319" x1="360.72" y1="56" x2="360.72" y2="420"',
                         'data-marker="mean" data-value="250" x1="300" y1="56" x2="300" y2="420"')
case("a 'mean' half a bin from the binned mean is a finding",
     any("placement by eye" in f for f in findings_of(flattering_mean)))

# ── transforms ───────────────────────────────────────────────────────────────

group_transform = mutate("group-transform",
                         '<svg viewBox="0 0 1000 500"',
                         '<svg transform="translate(0 20)" viewBox="0 0 1000 500"')
case("a transform on an enclosing group is a finding",
     any("transform on a group" in f for f in findings_of(group_transform)))

bound_transform = mutate("bound-transform",
                         'data-bin-start="0" data-bin-end="100" data-count="18" x="80"',
                         'data-bin-start="0" data-bin-end="100" data-count="18" transform="translate(0 12)" x="80"')
case("a transform on verified geometry is a finding",
     any("transform on verified geometry" in f for f in findings_of(bound_transform)))

# ── repeated n declarations (single-slot reading kept only the last one) ─────

n_twice_disagree = mutate("n-twice-disagree",
                          '<text data-role="n" data-value="550"',
                          '<text data-role="n" data-value="550" x="700" y="497">n = 550</text>'
                          '<text data-role="n" data-value="490"')
n_twice_disagree.write_text(
    n_twice_disagree.read_text(encoding="utf-8").replace(
        'data-value="490" x="960" y="497" fill="#4f5d75" font-size="8.5" font-family="\'Geist Mono\', monospace" text-anchor="end">n = 550<',
        'data-value="490" x="960" y="497" fill="#4f5d75" font-size="8.5" font-family="\'Geist Mono\', monospace" text-anchor="end">n = 490<'),
    encoding="utf-8")
case("two n declarations that disagree are a finding",
     any("n declarations disagree" in f for f in findings_of(n_twice_disagree)))
case("the wrong duplicate n is also checked against the sum, not shadowed",
     any("silently dropped or invented" in f for f in findings_of(n_twice_disagree)))

n_twice_agree = mutate("n-twice-agree",
                       '<text data-role="n" data-value="550"',
                       '<text data-role="n" data-value="550" x="700" y="497">n = 550</text>'
                       '<text data-role="n" data-value="550"')
case("two n declarations that agree are not a finding",
     findings_of(n_twice_agree) == [],
     "; ".join(findings_of(n_twice_agree)[:2]))

# ── CSS transform scope: reachability, not document-wide rejection ───────────

css_chrome = mutate("css-chrome",
                    "svg { width: 100%; min-width: 760px; display: block; }",
                    "svg { width: 100%; min-width: 760px; display: block; }\n"
                    "    .frame:hover { transform: translateY(-2px); }")
case("a CSS transform scoped to page chrome the SVG never uses is allowed",
     findings_of(css_chrome) == [],
     "; ".join(findings_of(css_chrome)[:2]))

css_element = mutate("css-element",
                     "svg { width: 100%; min-width: 760px; display: block; }",
                     "svg { width: 100%; min-width: 760px; display: block; }\n"
                     "    text { transform: translate(0, 80px); }")
case("a CSS transform on an SVG element type is a finding",
     any("can reach verified geometry" in f for f in findings_of(css_element)))

css_attr = mutate("css-attr",
                  "svg { width: 100%; min-width: 760px; display: block; }",
                  "svg { width: 100%; min-width: 760px; display: block; }\n"
                  "    [data-bin-start] { transform: scaleY(0.5); }")
case("a CSS transform on an attribute selector is a finding",
     any("can reach verified geometry" in f for f in findings_of(css_attr)))

css_svg_class = mutate("css-svg-class",
                       'data-bin-start="0" data-bin-end="100" data-count="18" x="80"',
                       'class="bin" data-bin-start="0" data-bin-end="100" data-count="18" x="80"')
css_svg_class.write_text(
    css_svg_class.read_text(encoding="utf-8").replace(
        "svg { width: 100%; min-width: 760px; display: block; }",
        "svg { width: 100%; min-width: 760px; display: block; }\n"
        "    .bin { transform: translateY(-4px); }"),
    encoding="utf-8")
case("a CSS transform on a class the SVG uses is a finding",
     any("targets a class or id the SVG uses" in f
         for f in findings_of(css_svg_class)))

# ── fail closed ──────────────────────────────────────────────────────────────

husk = TMP / "example-histogram-husk.html"
husk.write_text("<html><body><svg><title>Histogram</title></svg></body></html>",
                encoding="utf-8")
case("a file that presents as a histogram but parses no bins is a finding",
     any("reported, never passed" in f for f in findings_of(husk)))

stub_reference = TMP / "stub-type-bar.md"
stub_reference.write_text("# Bar\n\nNothing about the variant here.\n", encoding="utf-8")
drifted = verify.check_source(SHIPPED, SHIPPED.read_text(encoding="utf-8"), stub_reference)
case("a reference without the documented tokens is a finding, not a default",
     any("drifted apart" in f for f in drifted))

# ── --all scope assertion ────────────────────────────────────────────────────

scope_dir = TMP / "assets-missing-one"
scope_dir.mkdir()
for shipped in (SHIPPED, SHIPPED_DARK):   # deliberately omit -full
    (scope_dir / shipped.name).write_text(shipped.read_text(encoding="utf-8"),
                                          encoding="utf-8")
original_dir, original_argv = verify.ASSET_DIR, sys.argv
try:
    verify.ASSET_DIR = scope_dir
    sys.argv = ["verify-histogram.py", "--all"]
    with contextlib.redirect_stdout(io.StringIO()) as captured:
        code = verify.main()
    case("--all fails when a shipped example is missing from scope",
         code == 1 and "did not verify example-histogram-full.html" in captured.getvalue())
finally:
    verify.ASSET_DIR, sys.argv = original_dir, original_argv

# ── negatives that keep the checker honest ───────────────────────────────────

zero_bin = mutate("zero-bin",
                  'data-bin-start="900" data-bin-end="1000" data-count="3" x="872" y="412.88" width="88" height="7.12"',
                  'data-bin-start="900" data-bin-end="1000" data-count="0" x="872" y="420" width="88" height="0"')
zero_bin_source = zero_bin.read_text(encoding="utf-8").replace(
    'data-bin-start="900" data-role="count" x="916" y="404.88" fill="#4f5d75" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle">3<',
    'data-bin-start="900" data-role="count" x="916" y="412" fill="#4f5d75" font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle">0<').replace(
    'data-role="n" data-value="550"', 'data-role="n" data-value="547"').replace(
    '>n = 550<', '>n = 547<')
zero_bin.write_text(zero_bin_source, encoding="utf-8")
zero_findings = [f for f in findings_of(zero_bin) if "placement by eye" not in f]
case("an empty bin drawn at height 0 with its label is not a finding",
     zero_findings == [], "; ".join(zero_findings[:2]))

rotated_caption = mutate("rotated-caption",
                         'transform="rotate(-90 24 230)"',
                         'transform="rotate(-90 24 230)" ')
case("the rotated unbound axis caption is not a finding",
     findings_of(rotated_caption) == [])

# ── fixture hygiene ──────────────────────────────────────────────────────────

case("fixtures were written to a per-process temp dir, not the repo",
     all(str(p).startswith(str(TMP)) for p in TMP.iterdir()))
case("no fixture landed in the shipped assets directory",
     not list((ROOT / "skills/diagram-design/assets").glob("example-histogram-*-*.html")))

print()
if FAILURES:
    print("%d case(s) failed: %s" % (len(FAILURES), ", ".join(FAILURES)))
    raise SystemExit(1)
print("OK test-verify-histogram: every adversarial case caught, every honest case clean")
raise SystemExit(0)
