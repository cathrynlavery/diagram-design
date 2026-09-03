#!/usr/bin/env python3
"""Adversarial tests for verify-heatmap.py — both polarities.

Per ADR 0005, a geometric contract is a checker plus fixtures proving it fires
when it should and stays quiet when it shouldn't. Each mutation below renders
visually identical to the good example (or plausibly so) and no other gate
would catch it.

Positive cases (must PASS):
  P1 — the shipped light example passes clean.
  P2 — the shipped dark example passes clean.
  P3 — the shipped full example passes clean.

Negative cases (must FAIL):
  N1 — two focal cells (data-focal on two different cells).
  N2 — missing cell (one (row,col) pair removed from the grid).
  N3 — duplicate cell (one (row,col) pair appears twice, different values).
  N4 — non-monotone fill (higher value gets lower opacity).
  N5 — inconsistent fill (same value, two different opacities in the same figure).
  N6 — no parseable cells (data-row attribute removed from all cells).
  N7 — non-focal cell with no rgba fill.
  N8 — CSS transform present in <style> block.

Usage: python3 scripts/test-verify-heatmap.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-heatmap.py"
GOOD = ROOT / "skills/diagram-design/assets/example-heatmap.html"
GOOD_DARK = ROOT / "skills/diagram-design/assets/example-heatmap-dark.html"
GOOD_FULL = ROOT / "skills/diagram-design/assets/example-heatmap-full.html"

CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}

# Anchors — literal excerpts of the shipped light example.
FOCAL_CELL = (
    'data-row="payments" data-col="S4" data-value="47" data-focal="true" '
    'x="520" y="124" width="116" height="56" fill="rgba(235,108,54,0.85)"'
)
FIRST_NONFOCAL = (
    'data-row="auth" data-col="S1" data-value="4" '
    'x="160" y="64" width="116" height="56" fill="rgba(45,49,66,0.29)"'
)
HIGH_VALUE_CELL = (
    'data-row="billing" data-col="S3" data-value="9" '
    'x="400" y="244" width="116" height="56" fill="rgba(45,49,66,0.65)"'
)
LOW_VALUE_CELL = (
    'data-row="notifications" data-col="S1" data-value="1" '
    'x="160" y="304" width="116" height="56" fill="rgba(45,49,66,0.07)"'
)
# A non-focal cell used as the "missing" anchor in N2
MISSING_TARGET = (
    'data-row="billing" data-col="S6" data-value="3" '
    'x="760" y="244" width="116" height="56" fill="rgba(45,49,66,0.22)"'
)
# A cell with value=5 used as the inconsistent-opacity anchor in N5
FIVE_VALUE_CELL = (
    'data-row="auth" data-col="S2" data-value="5" '
    'x="280" y="64" width="116" height="56" fill="rgba(45,49,66,0.36)"'
)


def invoke(argv: list[str]) -> tuple[int, str]:
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=CHILD_ENV,
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
    expect_pass: bool,
    describe: str,
) -> None:
    if source == original and not expect_pass:
        failures.append(f"could not build the {name!r} fixture (anchor not found in source)")
        return
    path = write(directory, name, source)
    code, output = run(path)
    passed = code == 0
    if passed != expect_pass:
        direction = "pass" if expect_pass else "fail"
        actual = "passed" if passed else f"failed:\n  {output.strip()}"
        failures.append(f"{name}: expected {direction} but {actual}")


def main() -> int:
    original = GOOD.read_text(encoding="utf-8")
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)

        # ── Positive: shipped examples must pass ──────────────────────────────

        for label, path in [
            ("P1-light", GOOD),
            ("P2-dark", GOOD_DARK),
            ("P3-full", GOOD_FULL),
        ]:
            code, output = run(path)
            if code != 0:
                failures.append(f"{label}: shipped example failed:\n  {output.strip()}")

        # ── Negative: mutations that must be rejected ─────────────────────────

        # N1: two focal cells
        second_focal = FIRST_NONFOCAL.replace(
            'fill="rgba(45,49,66,0.29)"',
            'data-focal="true" fill="rgba(235,108,54,0.85)"',
        )
        case(
            failures, d, "N1-two-focal.html",
            original.replace(FIRST_NONFOCAL, second_focal),
            original, False,
            "two data-focal cells",
        )

        # N2: missing cell (remove one complete <rect> pair — underlay + data)
        # We remove just the data rect for billing·S6; the grid becomes 29 cells.
        missing_rect = f'<rect {MISSING_TARGET}/>'
        case(
            failures, d, "N2-missing-cell.html",
            original.replace(missing_rect, ""),
            original, False,
            "missing (billing, S6) cell",
        )

        # N3: duplicate cell — replace the billing·S6 cell's col with S5
        # so we have two (billing, S5) cells.
        duplicate = MISSING_TARGET.replace('data-col="S6"', 'data-col="S5"')
        case(
            failures, d, "N3-duplicate-cell.html",
            original.replace(MISSING_TARGET, duplicate),
            original, False,
            "duplicate (billing, S5) cell",
        )

        # N4: non-monotone fill — swap opacities of high-value (9, 0.65) and
        # low-value (1, 0.07) cells so a lower value gets higher opacity.
        inverted = original.replace(
            HIGH_VALUE_CELL,
            HIGH_VALUE_CELL.replace("0.65", "0.07"),
        ).replace(
            LOW_VALUE_CELL,
            LOW_VALUE_CELL.replace("0.07", "0.65"),
        )
        case(
            failures, d, "N4-non-monotone.html",
            inverted, original, False,
            "non-monotone opacity (value=9 gets opacity=0.07, value=1 gets 0.65)",
        )

        # N5: inconsistent fill — give one of the value=5 cells a different opacity.
        inconsistent = original.replace(
            FIVE_VALUE_CELL,
            FIVE_VALUE_CELL.replace("0.36", "0.55"),
        )
        case(
            failures, d, "N5-inconsistent-opacity.html",
            inconsistent, original, False,
            "same value=5 with two different opacities (0.36 vs 0.55)",
        )

        # N6: no parseable cells — strip data-row from every rect.
        no_cells = re.sub(r'\s+data-row="[^"]*"', "", original)
        case(
            failures, d, "N6-no-cells.html",
            no_cells, original, False,
            "no parseable heatmap cells",
        )

        # N7: non-focal cell with no rgba fill — replace with a named color.
        no_rgba = original.replace(
            'fill="rgba(45,49,66,0.07)"',
            'fill="#f0eeec"',
            1,  # only the first occurrence
        )
        case(
            failures, d, "N7-no-rgba-fill.html",
            no_rgba, original, False,
            "non-focal cell with no rgba fill",
        )

        # N8: CSS transform in <style> block.
        css_transform = original.replace(
            "svg { width: 100%",
            "svg { width: 100%; transform: scale(1)",
        )
        case(
            failures, d, "N8-css-transform.html",
            css_transform, original, False,
            "CSS transform property in <style>",
        )

    if failures:
        for f in failures:
            print("FAIL:", f, file=sys.stderr)
        return 1

    print(f"OK — {8 + 3} cases ({3} positive, {8} negative), all passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
