#!/usr/bin/env python3
"""Adversarial tests for verify-treemap.py — both polarities.

Per ADR 0005, a geometric contract in this repo is a checker plus fixtures that
prove it fires when it should and stays quiet when it shouldn't. The mutations
below are the two defects that actually shipped in review: a sliver cell drawn a
third too small, and a label longer than the cell holding it.

Usage: python3 scripts/test-verify-treemap.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import runpy
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-treemap.py"
GOOD = ROOT / "skills/diagram-design/assets/example-treemap.html"
SHIPPED = sorted(GOOD.parent.glob("example-treemap*.html"))
VERIFY_NAMESPACE = runpy.run_path(str(CHECKER), run_name="verify_treemap_test")
ESTIMATED_ADVANCE = VERIFY_NAMESPACE["estimated_advance"]
PARSE_CELLS = VERIFY_NAMESPACE["parse_cells"]
KOREAN_LABEL = "남아메리카 인구 구성 비율 요약"
JAPANESE_LABEL = "南アメリカ人口構成比率の概要"


def run(path: Path) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def write(directory: Path, name: str, source: str) -> Path:
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def main() -> int:
    source = GOOD.read_text(encoding="utf-8")
    failures: list[str] = []

    # Pin the estimator independently from CLI diagnostics. The Korean fixture
    # has 13 wide glyphs and four narrow spaces; the Japanese fixture has 14
    # wide glyphs. This catches a width-contract regression without coupling
    # the overflow fixture to its human-readable pixel message.
    for label, expected, language in (
        (KOREAN_LABEL, 15.4, "Korean"),
        (JAPANESE_LABEL, 14.0, "Japanese"),
    ):
        actual = ESTIMATED_ADVANCE(label, False)
        if abs(actual - expected) > 1e-9:
            failures.append(
                f"{language} estimator contract moved: expected {expected:g}em, got {actual:g}em"
            )
        else:
            print(f"OK: {language} wide-glyph estimator contract is {expected:g}em")

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # 1. Every shipped Latin example must pass untouched, proving the
        #    Unicode estimator did not move the calibrated Latin baseline.
        shipped_clean = True
        for path in SHIPPED:
            code, output = run(path)
            if code != 0:
                shipped_clean = False
                failures.append(f"clean example {path.name} was rejected: {output.strip()}")
        if shipped_clean:
            print(f"OK: all {len(SHIPPED)} shipped Latin treemaps pass")

        # 2. Shrink a labelled cell below the share it prints. This is the
        #    defect that shipped in review — a cell drawn smaller than it claims
        #    — caught here on Africa, which carries a label to contradict.
        shrunk = source.replace(
            '<rect x="576" y="40" width="252" height="252"',
            '<rect x="576" y="40" width="200" height="252"',
        )
        if shrunk == source:
            failures.append("could not build the undersized-cell fixture (anchor moved)")
        else:
            code, output = run(write(directory, "undersized.html", shrunk))
            if code == 0:
                failures.append("cell drawn under its stated share was accepted")
            elif "relative" not in output:
                failures.append(f"undersized cell reported without an area finding: {output.strip()}")
            else:
                print("OK: a cell drawn smaller than its label is rejected")

        # 3. Inflate Asia instead — the opposite direction of the same defect.
        #    Both rects move: a cell is painted as a paper mask then a body, and
        #    mutating only one leaves the original size still present, which the
        #    smallest-host rule would quietly measure instead.
        inflated = source.replace(
            '<rect x="40" y="40" width="532" height="380"',
            '<rect x="40" y="40" width="700" height="380"',
        )
        if inflated == source:
            failures.append("could not build the oversized-cell fixture (anchor moved)")
        else:
            code, _ = run(write(directory, "oversized.html", inflated))
            if code == 0:
                failures.append("oversized focal cell was accepted")
            else:
                print("OK: a cell drawn larger than its label is rejected")

        # 4. Overrun a label past its own cell.
        overflowing = source.replace(
            ">South America</text>",
            ">South America and the Caribbean Basin</text>",
        )
        if overflowing == source:
            failures.append("could not build the overflowing-label fixture (anchor moved)")
        else:
            code, output = run(write(directory, "overflow.html", overflowing))
            if code == 0:
                failures.append("label overflowing its cell was accepted")
            elif "overflows" not in output:
                failures.append(f"overflow reported without a fit finding: {output.strip()}")
            else:
                print("OK: a label wider than its cell is rejected")

        # 4a. Reproduce #115: most glyphs in this Korean translation are
        #     full-width. The old 0.60em character-count estimate called it
        #     122.4px wide and accepted it in 132px of available space, while
        #     Chromium measured 146.2px. A conservative 1em wide-glyph advance
        #     must fail closed without changing the Latin estimate.
        korean = source.replace(
            '<text x="804" y="324" fill="#2d3142" font-size="12" font-weight="600" '
            'font-family="\'Geist\', sans-serif">South America</text>',
            '<text x="804" y="324" fill="#2d3142" font-size="12" font-weight="600" '
            'font-family="\'Geist\', \'Apple SD Gothic Neo\', \'Noto Sans KR\', '
            f'\'Malgun Gothic\', sans-serif">{KOREAN_LABEL}</text>',
        )
        if korean == source:
            failures.append("could not build the Korean-overflow fixture (anchor moved)")
        else:
            code, output = run(write(directory, "korean-overflow.html", korean))
            if code == 0:
                failures.append("full-width Korean label overflowing its cell was accepted")
            elif "label" not in output or "overflows" not in output:
                failures.append(f"Korean fixture lacked a label-overflow finding: {output.strip()}")
            else:
                print("OK: a Korean label in the old-estimator boundary gap is rejected")

        # 4b. Japanese Han and kana are also Unicode-wide. Cover the documented
        #     CJK contract beyond Hangul with another label that fits under the
        #     old 0.60em estimate but overflows under the conservative contract.
        japanese = source.replace(
            '<text x="804" y="324" fill="#2d3142" font-size="12" font-weight="600" '
            'font-family="\'Geist\', sans-serif">South America</text>',
            '<text x="804" y="324" fill="#2d3142" font-size="12" font-weight="600" '
            'font-family="\'Geist\', \'Hiragino Sans\', \'Noto Sans JP\', '
            f'\'Yu Gothic\', sans-serif">{JAPANESE_LABEL}</text>',
        )
        if japanese == source:
            failures.append("could not build the Japanese-overflow fixture (anchor moved)")
        else:
            code, output = run(write(directory, "japanese-overflow.html", japanese))
            if code == 0:
                failures.append("full-width Japanese label overflowing its cell was accepted")
            elif "label" not in output or "overflows" not in output:
                failures.append(f"Japanese fixture lacked a label-overflow finding: {output.strip()}")
            else:
                print("OK: a Japanese full-width label is rejected when it overflows")

        # 4c. Overflow off the LEFT edge, via an end-anchored label. Checking
        #     only the right and bottom edges would pass this silently, and the
        #     text would read as belonging to the cell next door.
        left_over = source.replace(
            '<text x="804" y="324" fill="#2d3142" font-size="12" font-weight="600"',
            '<text x="804" y="324" text-anchor="end" fill="#2d3142" font-size="12" font-weight="600"',
        )
        if left_over == source:
            failures.append("could not build the left-overflow fixture (anchor moved)")
        else:
            code, output = run(write(directory, "leftoverflow.html", left_over))
            if code == 0:
                failures.append("label hanging off the left of its cell was accepted")
            elif "left" not in output:
                failures.append(f"left overflow not named in the finding: {output.strip()}")
            else:
                print("OK: a label overflowing the left edge is rejected")

        # 4d. Overflow off the TOP edge — the label's ascent clears the cell.
        top_over = source.replace(
            '<text x="592" y="68" fill="#2d3142" font-size="13"',
            '<text x="592" y="44" fill="#2d3142" font-size="13"',
        )
        if top_over == source:
            failures.append("could not build the top-overflow fixture (anchor moved)")
        else:
            code, output = run(write(directory, "topoverflow.html", top_over))
            if code == 0:
                failures.append("label overflowing the top of its cell was accepted")
            elif "top" not in output:
                failures.append(f"top overflow not named in the finding: {output.strip()}")
            else:
                print("OK: a label overflowing the top edge is rejected")

        # 4e. A sliver can be narrower than the fixed 10px information-mark
        #     disc. The marker must never cross into the neighbouring cell.
        marker_over = source.replace(
            '<rect x="940" y="296" width="16" height="124"',
            '<rect x="940" y="296" width="8" height="124"',
        ).replace('cx="948" cy="358"', 'cx="944" cy="358"').replace(
            '<text x="948" y="361"', '<text x="944" y="361"'
        )
        if marker_over == source:
            failures.append("could not build the overflowing-marker fixture (anchor moved)")
        else:
            code, output = run(write(directory, "markeroverflow.html", marker_over))
            if code == 0:
                failures.append("information mark overflowing a sliver cell was accepted")
            elif "information marker" not in output:
                failures.append(f"marker overflow not named in the finding: {output.strip()}")
            else:
                print("OK: an information mark overflowing its cell is rejected")

        # 4f. Combining marks do not advance independently. Eighteen decomposed
        #     accented glyphs fit by the unchanged Latin baseline (129.6px in
        #     132px), but counting every acute accent as a character would
        #     incorrectly double the estimate and reject the label.
        decomposed = ("e\N{COMBINING ACUTE ACCENT}" * 18)
        combining = source.replace(">South America</text>", f">{decomposed}</text>")
        if combining == source:
            failures.append("could not build the combining-mark fixture (anchor moved)")
        else:
            code, output = run(write(directory, "combining-marks.html", combining))
            if code != 0:
                failures.append(f"non-advancing combining marks were overcounted: {output.strip()}")
            else:
                print("OK: combining marks do not create phantom label overflow")

        # 5. The shipped example leaves its smallest cell deliberately
        #    unlabelled. That must not switch the area check off for the cells
        #    that ARE labelled — the failure mode where a checker reports clean
        #    because it found nothing to compare.
        unlabelled_shrunk = source.replace(
            '<rect x="576" y="296" width="208" height="124"',
            '<rect x="576" y="296" width="140" height="124"',
        )
        if unlabelled_shrunk == source:
            failures.append("could not build the still-checks-labelled-cells fixture")
        else:
            code, _ = run(write(directory, "unlabelled.html", unlabelled_shrunk))
            if code == 0:
                failures.append(
                    "area check went silent when a cell was unlabelled — a labelled "
                    "cell was resized and no finding was reported"
                )
            else:
                print("OK: an unlabelled sliver does not disable the area check")

        # 6. The unlabelled sliver, both directions. This is the gap issue #89
        #    reported: with the basis derived from in-cell labels, the one cell
        #    carrying no label was the one cell nothing verified — and it is the
        #    cell a 4px grid distorts most. Both rects of the pair move, because
        #    a mask and a body at different sizes are two cells, not one.
        for label, width, direction in (("oversized", "24", "larger"), ("undersized", "8", "smaller")):
            mutated = source.replace(
                '<rect x="940" y="296" width="16" height="124"',
                f'<rect x="940" y="296" width="{width}" height="124"',
            )
            if mutated == source:
                failures.append(f"could not build the {label}-sliver fixture (anchor moved)")
                continue
            code, output = run(write(directory, f"sliver-{label}.html", mutated))
            if code == 0:
                failures.append(
                    f"{label} unlabelled sliver was accepted — the cell with no label "
                    f"is exactly the one that must still be checked"
                )
            elif "declares" not in output:
                failures.append(f"{label} sliver reported without an area finding: {output.strip()}")
            else:
                print(f"OK: an unlabelled sliver drawn {direction} than it declares is rejected")

        # 7. Fail closed. A cell with no declared share is unverifiable, and
        #    reporting OK on it is the defect, not a tolerable gap.
        stripped = source.replace(' data-share="0.56"', "", 1)
        if stripped == source:
            failures.append("could not build the missing-metadata fixture (anchor moved)")
        else:
            code, output = run(write(directory, "nometa.html", stripped))
            if code == 0:
                failures.append("a cell with no data-share was accepted — must fail closed")
            elif "no data-share" not in output:
                failures.append(f"missing metadata reported without the right finding: {output.strip()}")
            else:
                print("OK: a cell with no declared share fails closed")

        # 8. A label that disagrees with the metadata it sits on.
        divergent = source.replace("4.78B · 59% of world", "4.78B · 42% of world")
        if divergent == source:
            failures.append("could not build the label-divergence fixture (anchor moved)")
        else:
            code, output = run(write(directory, "divergent.html", divergent))
            if code == 0:
                failures.append("a label contradicting its own data-share was accepted")
            elif "same fact" not in output:
                failures.append(f"divergence reported without the right finding: {output.strip()}")
            else:
                print("OK: a label contradicting its cell's declared share is rejected")

        # 9. Invalid shares fail closed without raising or slipping through
        #    float edge cases. Zero used to divide by zero; NaN/Infinity made
        #    comparisons false; negative and >100 values are not shares of a
        #    whole even though float() accepts them.
        for label, value in (
            ("non-numeric", "unknown"),
            ("zero", "0"),
            ("negative", "-1"),
            ("non-finite-nan", "NaN"),
            ("non-finite-infinity", "Infinity"),
            ("over-100", "101"),
        ):
            invalid = source.replace('data-share="59.04"', f'data-share="{value}"', 1)
            if invalid == source:
                failures.append(f"could not build the {label}-share fixture")
                continue
            code, output = run(write(directory, f"share-{label}.html", invalid))
            if code == 0:
                failures.append(f"{label} data-share was accepted")
            elif "invalid share metadata" not in output:
                failures.append(f"{label} share lacked a metadata finding: {output.strip()}")
            else:
                print(f"OK: {label} data-share fails closed")

        # 10. The mask/body pair is one logical cell. If both copies state a
        #     share, they must agree; retaining whichever rect was parsed first
        #     silently discards contradictory source data.
        asia_mask = '<rect x="40" y="40" width="532" height="380" rx="2" fill="#f5f5f5"/>'
        conflicting = source.replace(
            asia_mask,
            asia_mask.replace(' fill=', ' data-share="42" fill='),
            1,
        )
        if conflicting == source:
            failures.append("could not build the conflicting-twin fixture")
        else:
            code, output = run(write(directory, "conflicting-twins.html", conflicting))
            if code == 0:
                failures.append("conflicting duplicate data-share values were accepted")
            elif "conflicting data-share" not in output:
                failures.append(f"conflicting twins lacked the right finding: {output.strip()}")
            else:
                print("OK: conflicting mask/body shares are rejected")

        asia_body = (
            '<rect x="40" y="40" width="532" height="380" rx="2" '
            'data-share="59.04" fill="rgba(235,108,54,0.16)" '
            'stroke="#eb6c36" stroke-width="1.5"/>'
        )
        triplicated = source.replace(asia_body, f"{asia_body}\n      {asia_body}", 1)
        if triplicated == source:
            failures.append("could not build the triplicated-cell fixture")
        else:
            code, output = run(write(directory, "triplicated-cell.html", triplicated))
            if code == 0:
                failures.append("a triplicated logical cell was silently deduplicated")
            elif "duplicate rects" not in output:
                failures.append(f"triplicated cell lacked the right finding: {output.strip()}")
            else:
                print("OK: extra duplicate cell rects are rejected")

        # 11. The shares describe one whole, so a plausible individual number
        #     cannot hide an incomplete or over-counted set.
        incomplete_total = source.replace('data-share="59.04"', 'data-share="50"', 1)
        code, output = run(write(directory, "incomplete-share-total.html", incomplete_total))
        if code == 0:
            failures.append("data-share values that do not total the whole were accepted")
        elif "not approximately 100%" not in output:
            failures.append(f"bad share total lacked the right finding: {output.strip()}")
        else:
            print("OK: shares must total approximately 100%")

        # 12. A treemap with too few parseable cells is unchecked, not clean.
        unparsable = source.replace(' rx="2"', ' rx="3"')
        unparsable = re.sub(r' data-share="[^"]+"', "", unparsable)
        code, output = run(write(directory, "too-few-cells.html", unparsable))
        if code == 0:
            failures.append("a treemap with no parseable cells was accepted")
        elif "expected at least 3 parseable treemap cells" not in output:
            failures.append(f"too-few-cells fixture lacked the right finding: {output.strip()}")
        else:
            print("OK: too few parseable cells fails closed")

        # 13. An explicitly metadata-bearing cell remains a cell even below
        #     the generic 400px decorative-rect threshold. Oceania at 2x124
        #     used to disappear with its mask, leaving a plausible 99.43%
        #     total that slipped through the rounding tolerance.
        below_threshold = source.replace(
            '<rect x="940" y="296" width="16" height="124"',
            '<rect x="940" y="296" width="2" height="124"',
        ).replace('cx="948" cy="320"', 'cx="941" cy="320"').replace(
            '<text x="948" y="323"', '<text x="941" y="323"'
        )
        if below_threshold == source:
            failures.append("could not build the below-threshold-cell fixture")
        else:
            sliver = next(
                (cell for cell in PARSE_CELLS(below_threshold) if cell.w == 2 and cell.h == 124),
                None,
            )
            if sliver is None or sliver.rect_count != 2:
                failures.append(
                    "the below-threshold metadata cell lost its same-geometry mask/body association"
                )
            code, output = run(write(directory, "below-threshold-cell.html", below_threshold))
            if code == 0:
                failures.append("a metadata-bearing cell below CELL_MIN_AREA was discarded")
            elif "cell 2x124" not in output:
                failures.append(
                    f"below-threshold cell was not preserved as a logical cell: {output.strip()}"
                )
            else:
                print("OK: metadata-bearing cells bypass the decorative-area threshold")

        no_rounding_marker = source.replace(
            'rx="2" data-share="0.56"', 'rx="3" data-share="0.56"', 1
        )
        code, output = run(write(directory, "metadata-with-nonstandard-rx.html", no_rounding_marker))
        if code != 0:
            failures.append(
                f"an otherwise valid data-share rect depended on decorative rx=2: {output.strip()}"
            )
        else:
            print("OK: data-share identifies a cell independently of decorative rx")

        # 14. Every percentage claim hosted by a cell must agree. Reading only
        #     the first match accepted a later contradiction when 59% appeared
        #     before 42% in the same cell.
        conflicting_labels = source.replace(
            "4.78B · 59% of world",
            "4.78B · 59% of world · alternate claim 42%",
            1,
        )
        code, output = run(write(directory, "conflicting-label-claims.html", conflicting_labels))
        if code == 0:
            failures.append("distinct percentage claims in one cell were accepted")
        elif "conflicting percentage claims" not in output:
            failures.append(f"conflicting labels lacked the right finding: {output.strip()}")
        else:
            print("OK: every hosted percentage claim must agree")

        # 15. Explicit metadata outranks both sides of the decorative-rect
        #     heuristic. A declared cell cannot disappear merely because a bad
        #     edit makes it implausibly wide or tall.
        for label, old, new, dimensions in (
            (
                "above-max-width",
                '<rect x="940" y="296" width="16" height="124"',
                '<rect x="40" y="296" width="901" height="124"',
                "901x124",
            ),
            (
                "above-max-height",
                '<rect x="940" y="296" width="16" height="124"',
                '<rect x="940" y="40" width="16" height="461"',
                "16x461",
            ),
        ):
            oversized_declared = source.replace(old, new)
            if oversized_declared == source:
                failures.append(f"could not build the {label} fixture")
                continue
            code, output = run(write(directory, f"{label}.html", oversized_declared))
            if code == 0:
                failures.append(f"metadata-bearing {label} cell was discarded")
            elif f"cell {dimensions}" not in output:
                failures.append(f"{label} cell was not retained: {output.strip()}")
            else:
                print(f"OK: metadata-bearing {label} cells bypass decorative limits")

        # 16. Geometry on a declared cell is untrusted metadata too. Missing,
        #     malformed, non-finite, zero, or negative dimensions must be a
        #     finding and must never poison the area total with NaN/Infinity.
        asia_declared = (
            '<rect x="40" y="40" width="532" height="380" rx="2" '
            'data-share="59.04"'
        )
        for label, replacement in (
            ("missing", '<rect x="40" y="40" height="380" rx="2" data-share="59.04"'),
            ("nonnumeric", asia_declared.replace('width="532"', 'width="wide"')),
            ("nan", asia_declared.replace('width="532"', 'width="NaN"')),
            ("infinity", asia_declared.replace('width="532"', 'width="Infinity"')),
            ("zero", asia_declared.replace('width="532"', 'width="0"')),
            ("negative", asia_declared.replace('width="532"', 'width="-1"')),
        ):
            bad_geometry = source.replace(asia_declared, replacement, 1)
            if bad_geometry == source:
                failures.append(f"could not build the {label}-geometry fixture")
                continue
            code, output = run(write(directory, f"geometry-{label}.html", bad_geometry))
            if code == 0:
                failures.append(f"{label} data-share geometry was accepted")
            elif "data-share rect" not in output:
                failures.append(f"{label} geometry lacked an explicit finding: {output.strip()}")
            else:
                print(f"OK: {label} data-share geometry fails closed")

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"\n{len(failures)} case(s) failed.")
        return 1
    print("\nOK verify-treemap: both polarities behave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
