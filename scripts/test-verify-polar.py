#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-polar.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_polar", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def category(index: int, value: int, endpoint: tuple[float, float] | None) -> str:
    body = '<text data-polar-value-label="">{}</text>'.format(value)
    if endpoint is not None:
        x, y = endpoint
        body = (
            f'<line data-polar-ray="" x1="100" y1="100" x2="{x}" y2="{y}"/>'
            f'<circle data-polar-marker="" cx="{x}" cy="{y}" r="4"/>' + body
        )
    return (
        f'<g data-polar-category="c{index}" data-polar-index="{index}" '
        f'data-polar-value="{value}">{body}</g>'
    )


def document(categories: str, extra_svg: str = "") -> str:
    return (
        '<!DOCTYPE html><html><body>'
        '<svg data-polar-chart="" data-polar-cx="100" data-polar-cy="100" '
        'data-polar-radius="100" data-polar-min="0" data-polar-max="100" '
        'data-polar-start-angle="-90" data-polar-clockwise="true" '
        'data-polar-radius-encoding="linear" data-polar-inner-radius="0">'
        f'{extra_svg}{categories}</svg></body></html>'
    )


VALID = document(
    category(0, 0, None)
    + category(1, 25, (125, 100))
    + category(2, 50, (100, 150))
    + category(3, 100, (0, 100))
)


def main() -> int:
    module = load_verifier()
    cases = [
        (
            "25 percent hub",
            VALID.replace('data-polar-inner-radius="0"', 'data-polar-inner-radius="25"'),
            "inner radius",
        ),
        (
            "sqrt radius",
            VALID.replace('x2="125"', 'x2="150"').replace('cx="125"', 'cx="150"'),
            "linear endpoint",
        ),
        (
            "visible zero ray",
            VALID.replace(
                '<text data-polar-value-label="">0</text>',
                '<line data-polar-ray="" x1="100" y1="100" x2="100" y2="100"/>'
                '<text data-polar-value-label="">0</text>',
            ),
            "zero category",
        ),
        (
            "out of range",
            VALID.replace('data-polar-value="100"', 'data-polar-value="101"'),
            "outside 0..100",
        ),
        (
            "duplicate index",
            VALID.replace('data-polar-index="3"', 'data-polar-index="2"'),
            "indices",
        ),
        (
            "quantitative wedge",
            VALID.replace('</svg>', '<path data-polar-wedge="" d="M0 0"/></svg>'),
            "wedge",
        ),
        (
            "blank value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="">   </text>',
            ),
            "finite numeric",
        ),
        (
            "mismatched value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="">26</text>',
            ),
            "does not match",
        ),
        (
            "hidden value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" hidden>25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "aria-hidden value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" aria-hidden="true">25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "display-none value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" style="display: none">25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "visibility-hidden value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" style="visibility: hidden">25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "opacity-zero value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" style="opacity: 0">25</text>',
            ),
            "explicitly hidden",
        ),
    ]

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)
        valid_path = root / "valid.html"
        valid_path.write_text(VALID, encoding="utf-8")
        findings = module.check(valid_path)
        if findings != []:
            failures.append(f"valid fixture: expected no findings, got {findings}")

        for label, source, expected in cases:
            path = root / f"{label.replace(' ', '-')}.html"
            path.write_text(source, encoding="utf-8")
            findings = module.check(path)
            if not findings:
                failures.append(f"{label}: expected findings, got none")
            elif not any(expected in finding for finding in findings):
                failures.append(
                    f"{label}: expected a finding containing {expected!r}, got {findings}"
                )

        light = root / "light.html"
        dark = root / "dark.html"
        full = root / "full.html"
        light.write_text(VALID, encoding="utf-8")
        dark.write_text(VALID.replace('data-polar-value="25"', 'data-polar-value="26"'), encoding="utf-8")
        full.write_text(VALID, encoding="utf-8")
        findings = module.check_variants((light, dark, full))
        if not any("variant data drift" in finding for finding in findings):
            failures.append(f"variant data drift: expected finding, got {findings}")

        first = root / "first.html"
        second = root / "second.html"
        first.write_text(VALID, encoding="utf-8")
        second.write_text(
            VALID.replace('data-polar-inner-radius="0"', 'data-polar-inner-radius="25"'),
            encoding="utf-8",
        )
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = module.main([str(first), str(second)])
        rendered = output.getvalue()
        expected = f"FAIL {second}: inner radius must be zero"
        if exit_code != 1 or expected not in rendered:
            failures.append(
                f"CLI path attribution: expected {expected!r}, got exit={exit_code}, output={rendered!r}"
            )

    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("All polar verifier tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
