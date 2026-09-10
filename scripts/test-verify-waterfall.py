#!/usr/bin/env python3
"""Adversarial tests for verify-waterfall.py — both polarities.

Per ADR 0005, a geometric contract in this repo is a checker plus fixtures
that prove it fires when it should and stays quiet when it shouldn't. Every
mutation below is a waterfall that still renders perfectly — the defects are
arithmetic and geometric lies, which is exactly what no other gate reads.

Usage: python3 scripts/test-verify-waterfall.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-waterfall.py"
GOOD = ROOT / "skills/diagram-design/assets/example-waterfall.html"
SHIPPED = sorted(GOOD.parent.glob("example-waterfall*.html"))


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(CHECKER), *args],
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

    # Positive polarity: every shipped variant must pass, individually and via --all.
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

    # Negative polarity: each mutation must fail with a finding that names the lie.
    # Every case below is (name, old, new, expected fragment of the finding).
    cases = (
        (
            "conservation break: a delta declares more than the walk absorbs",
            'data-role="delta" data-value="+64"',
            'data-role="delta" data-value="+70"',
            "the running total must conserve",
        ),
        (
            "geometry lie: the end total is drawn taller than its value",
            '<rect x="832" y="196" width="96" height="224" fill="rgba(45,49,66,0.08)"',
            '<rect x="832" y="160" width="96" height="260" fill="rgba(45,49,66,0.08)"',
            "shared scale puts",
        ),
        (
            "bridge lie: a bridge is stretched past its two running levels",
            '<rect x="688" y="146" width="96" height="50" fill="rgba(235,108,54,0.12)"',
            '<rect x="688" y="146" width="96" height="70" fill="rgba(235,108,54,0.12)"',
            "shared scale puts",
        ),
        (
            "missing carry: a gap has no connector conserving the total",
            '<line x1="496" y1="167" x2="544" y2="167" stroke="rgba(45,49,66,0.55)" stroke-width="1" data-carry="266"/>',
            "",
            "no carry spans it",
        ),
        (
            "misplaced carry: the connector reconnects the walk at the wrong level",
            '<line x1="496" y1="167" x2="544" y2="167" stroke="rgba(45,49,66,0.55)" stroke-width="1" data-carry="266"/>',
            '<line x1="496" y1="146" x2="544" y2="146" stroke="rgba(45,49,66,0.55)" stroke-width="1" data-carry="266"/>',
            "level sits at",
        ),
        (
            "carry declaration lie: the connector declares a different total",
            'data-carry="288"',
            'data-carry="266"',
            "running total between these bars",
        ),
        (
            "printed label mismatch: the text names a value no bar declares",
            '>+64</text>',
            '>+46</text>',
            "no printed label states its value +64",
        ),
        (
            "unsigned delta label: the printed bridge value drops its sign",
            '>−38</text>',
            '>38</text>',
            "no printed label states its value -38",
        ),
        (
            "unsigned delta declaration: data-value drops the sign",
            'data-value="+22"',
            'data-value="22"',
            "explicit sign",
        ),
        (
            "sign-treatment collapse: a decrease wears the increase fill",
            '<rect x="400" y="131" width="96" height="36" fill="#f5f5f5" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="-38"',
            '<rect x="400" y="131" width="96" height="36" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="-38"',
            "share the same fill",
        ),
        (
            "non-finite carry: a connector declares an unverifiable total",
            'data-carry="240"',
            'data-carry="nan"',
            "non-numeric data-carry",
        ),
        (
            "label stolen from elsewhere: the bar's own label is gone and a "
            "decoy on the far side of the chart carries its number",
            '<text x="448" y="179" fill="#4f5d75" font-size="8" '
            'font-family="\'Geist Mono\', monospace" text-anchor="middle">\u2212 38</text>'.replace("\u2212 ", "\u2212"),
            '<text x="5" y="5" fill="#4f5d75" font-size="8" '
            'font-family="\'Geist Mono\', monospace" text-anchor="middle">\u2212 38</text>'.replace("\u2212 ", "\u2212"),
            "no printed label states its value",
        ),
        (
            "polarity swap on a lone decrease: the only fall wears the rise tint",
            '<rect x="400" y="131" width="96" height="36" fill="#f5f5f5" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="-38"',
            '<rect x="400" y="131" width="96" height="36" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="-38"',
            "decreases require hollow paper",
        ),
        (
            "element transform: a translated bar no longer occupies its declared coordinates",
            '<rect x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75"',
            '<rect transform="translate(0 80)" x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75"',
            "waterfall bar carries transform",
        ),
        (
            "ancestor transform: a group moves a bar away from its declared coordinates",
            '<rect x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="+64" data-name="Headcount"/>',
            '<g transform="translate(0 80)"><rect x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75" stroke-width="1" data-role="delta" data-value="+64" data-name="Headcount"/></g>',
            "ancestor transform",
        ),
        (
            "CSS transform: a matching rule can move verified bars after parsing",
            "  </style>",
            '    [data-role="delta"] { transform: translateY(80px); }\n  </style>',
            "CSS 'transform' declaration",
        ),
        (
            "second accent bar: the focal treatment repeats",
            '<rect x="256" y="131" width="96" height="61" fill="rgba(79,93,117,0.15)" stroke="#4f5d75"',
            '<rect x="256" y="131" width="96" height="61" fill="rgba(235,108,54,0.12)" stroke="#eb6c36"',
            "at most one bar",
        ),
        (
            "degenerate start: a zero start total has no scale to fit",
            'data-role="total" data-value="240"',
            'data-role="total" data-value="0"',
            "totals must be positive",
        ),
        (
            "zero delta: invisible ink that still occupies a column",
            'data-role="delta" data-value="+22"',
            'data-role="delta" data-value="+0"',
            "zero delta",
        ),
        (
            "missing contract: no bar declares its role and value",
            'data-role="',
            'data-gone="',
            "data contract is missing",
        ),
    )

    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for index, (name, old, new, expected) in enumerate(cases):
            if old not in source:
                failures.append(f"fixture drift: {name} — mutation target not found in {GOOD.name}")
                continue
            mutated = source.replace(old, new)
            path = write(directory, f"example-waterfall-mutant-{index}.html", mutated)
            code, output = run(str(path))
            if code == 0:
                failures.append(f"checker stayed quiet on: {name}")
            elif expected not in output:
                failures.append(
                    f"checker fired on {name} but without naming the lie "
                    f"(wanted {expected!r}):\n{output}"
                )
            else:
                print(f"OK: fails on {name}")

        # Usage contract: no arguments is an error, not a silent pass.
        code, _ = run()
        if code != 2:
            failures.append(f"no-argument invocation must exit 2; got {code}")
        else:
            print("OK: usage error exits 2")

    if failures:
        print("\nFAIL verify-waterfall tests:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nOK: verify-waterfall passes {len(SHIPPED)} shipped files and fails all {len(cases)} mutations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
