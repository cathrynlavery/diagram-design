#!/usr/bin/env python3
"""Adversarial tests for verify-service-blueprint.py — both polarities.

Per ADR 0005, a geometric contract in this repo is a checker plus fixtures
that prove it fires when it should and stays quiet when it shouldn't. Every
mutation below is a blueprint that still renders perfectly — the defects are
layer, visibility, grid, and census lies, which is exactly what no other gate
reads.

Usage: python3 scripts/test-verify-service-blueprint.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-service-blueprint.py"
GOOD = ROOT / "skills/diagram-design/assets/example-service-blueprint.html"
SHIPPED = sorted(GOOD.parent.glob("example-service-blueprint*.html"))


def run(*args: str, timeout: float | None = None) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True,
        timeout=timeout,
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

    for path in SHIPPED:
        code, output = run(str(path))
        if code != 0:
            failures.append(f"shipped example failed: {path.name}\n{output}")
        else:
            print(f"OK: shipped {path.name} passes")
    code, output = run("--all")
    if code != 0:
        failures.append(f"--all failed on the shipped set\n{output}")
    else:
        print("OK: --all passes on the shipped set")

    cases = (
        (
            "swap two layers: customer and frontstage labels trade places",
            'data-layer="customer"',
            'data-layer="frontstage-hold"',
            "layer order",
            True,
        ),
        (
            "drop the visibility line",
            '<line x1="96" y1="268" x2="1200" y2="268" stroke="rgba(45,49,66,0.55)" stroke-width="2" data-role="visibility"/>',
            "",
            "visibility",
            False,
        ),
        (
            "put the visibility line above the customer row",
            '<line x1="96" y1="268" x2="1200" y2="268" stroke="rgba(45,49,66,0.55)" stroke-width="2" data-role="visibility"/>',
            '<line x1="96" y1="50" x2="1200" y2="50" stroke="rgba(45,49,66,0.55)" stroke-width="2" data-role="visibility"/>',
            "visibility",
            False,
        ),
        (
            "shift one cell off its column",
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            '<rect x="568" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            "stage grid",
            False,
        ),
        (
            "drop a backstage cell",
            '<rect x="96" y="272" width="208" height="64" rx="4" fill="rgba(45,49,66,0.06)" stroke="#4f5d75" stroke-width="1" data-stage="sign-up" data-name="CRM write"/>',
            "",
            "census",
            False,
        ),
        (
            "two focal cells",
            'data-stage="sign-up" data-name="Welcome"',
            'data-stage="sign-up" data-name="Welcome" data-focal="true"',
            "focal",
            False,
        ),
        (
            "seven stages",
            '<rect x="96" y="24" width="208" height="48" fill="none" data-stage="sign-up"/>',
            '<rect x="96" y="24" width="208" height="48" fill="none" data-stage="sign-up"/>\n'
            '      <rect x="96" y="24" width="208" height="48" fill="none" data-stage="extra-six"/>\n'
            '      <rect x="96" y="24" width="208" height="48" fill="none" data-stage="extra-seven"/>',
            "at most 6 stages",
            False,
        ),
        (
            "CSS translate on a cell",
            "  </style>",
            '    [data-name] { transform: translateY(80px); }\n  </style>',
            "CSS 'transform' declaration",
            False,
        ),
        (
            "printed text disagrees with data-name",
            ">Retry payment</text>",
            ">Call support</text>",
            "printed",
            False,
        ),
    )

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        mutated = source
        # First case is a two-step swap.
        step = mutated.replace('data-layer="customer"', 'data-layer="frontstage-hold"', 1)
        step = step.replace('data-layer="frontstage"', 'data-layer="customer"', 1)
        step = step.replace('data-layer="frontstage-hold"', 'data-layer="frontstage"', 1)
        name, _old, _new, fragment, _ = cases[0]
        if step == mutated:
            failures.append(f"could not build the {name!r} fixture")
        else:
            path = write(directory, "swap-layers.html", step)
            code, output = run(str(path))
            if code == 0 or fragment not in output:
                failures.append(
                    f"{name}: expected a finding containing {fragment!r}, got:\n{output}"
                )
            else:
                print(f"OK: {name} fails by name")

        for name, old, new, fragment, _swap in cases[1:]:
            if old not in mutated:
                failures.append(f"could not build the {name!r} fixture (anchor missing)")
                continue
            path = write(directory, name.replace(" ", "-") + ".html", mutated.replace(old, new, 1))
            code, output = run(str(path))
            if code == 0 or fragment not in output:
                failures.append(
                    f"{name}: expected a finding containing {fragment!r}, got:\n{output}"
                )
            else:
                print(f"OK: {name} fails by name")

    if failures:
        print("FAIL")
        for item in failures:
            print(item)
        return 1
    print("OK service-blueprint verifier: shipped files pass, named mutations fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
