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

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-treemap.py"
GOOD = ROOT / "skills/diagram-design/assets/example-treemap.html"


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

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # 1. The shipped example must pass untouched.
        code, output = run(write(directory, "clean.html", source))
        if code != 0:
            failures.append(f"clean example was rejected: {output.strip()}")
        else:
            print("OK: the shipped treemap passes")

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

        # 4b. Overflow off the LEFT edge, via an end-anchored label. Checking
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

        # 4c. Overflow off the TOP edge — the label's ascent clears the cell.
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

        # 4d. A sliver can be narrower than the fixed 10px information-mark
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

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"\n{len(failures)} case(s) failed.")
        return 1
    print("\nOK verify-treemap: both polarities behave")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
