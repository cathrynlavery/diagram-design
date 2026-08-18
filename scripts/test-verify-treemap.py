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
