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
            f'<line data-polar-ray="" x1="100" y1="100" x2="{x}" y2="{y}" '
            'stroke-width="2"/>'
            f'<circle data-polar-marker="" cx="{x}" cy="{y}" r="4" '
            'stroke-width="1.2"/>' + body
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
        '<rect data-polar-background="" width="100%" height="100%" fill="white"/>'
        '<circle data-polar-ring="" cx="100" cy="100" r="20" fill="none" '
        'stroke-width="0.8"/>'
        '<circle data-polar-ring="" cx="100" cy="100" r="40" fill="none" '
        'stroke-width="0.8"/>'
        '<circle data-polar-ring="" cx="100" cy="100" r="60" fill="none" '
        'stroke-width="0.8"/>'
        '<circle data-polar-ring="" cx="100" cy="100" r="80" fill="none" '
        'stroke-width="0.8"/>'
        '<circle data-polar-ring="" cx="100" cy="100" r="100" fill="none" '
        'stroke-width="0.8"/>'
        '<line data-polar-spoke="" data-polar-index="0" x1="100" y1="100" '
        'x2="100" y2="0" stroke-width="0.8"/>'
        '<line data-polar-spoke="" data-polar-index="1" x1="100" y1="100" '
        'x2="200" y2="100" stroke-width="0.8"/>'
        '<line data-polar-spoke="" data-polar-index="2" x1="100" y1="100" '
        'x2="100" y2="200" stroke-width="0.8"/>'
        '<line data-polar-spoke="" data-polar-index="3" x1="100" y1="100" '
        'x2="0" y2="100" stroke-width="0.8"/>'
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
            "unmarked quantitative wedge",
            VALID.replace(
                '</svg>',
                '<path d="M100 100 L100 20 A80 80 0 0 1 180 100 Z"/></svg>',
            ),
            "wedge",
        ),
        (
            "polygon area encoding",
            VALID.replace(
                '</svg>',
                '<polygon points="100,100 100,20 180,100" fill="red"/></svg>',
            ),
            "unsupported SVG element <polygon>",
        ),
        (
            "external referenced shape",
            VALID.replace('</svg>', '<use href="#polar-wedge"/></svg>'),
            "unsupported SVG element <use>",
        ),
        (
            "URL-valued ray marker",
            VALID.replace(
                'data-polar-ray=""',
                'data-polar-ray="" marker-end="url(https://example.com/marker.svg#tip)"',
                1,
            ),
            "URL-valued SVG attribute marker-end is forbidden",
        ),
        (
            "external chart stylesheet",
            VALID.replace(
                '<body>',
                '<head><link rel="stylesheet" href="https://example.com/chart.css"></head><body>',
            ),
            "external stylesheets are forbidden in polar documents",
        ),
        (
            "CSS geometry override",
            VALID.replace(
                '<body>',
                '<head><style>[data-polar-ray]{stroke-width:40!important}</style></head><body>',
            ),
            "CSS geometry properties are forbidden in polar documents",
        ),
        (
            "CSS imported stylesheet",
            VALID.replace(
                '<body>',
                '<head><style>@import url(https://attacker.invalid/polar.css);</style></head><body>',
            ),
            "CSS stylesheet loading is forbidden in polar documents",
        ),
        (
            "CSS marker radius override",
            VALID.replace(
                '<body>',
                '<head><style>circle[data-polar-marker]{r:40px}</style></head><body>',
            ),
            "CSS geometry properties are forbidden in polar documents",
        ),
        (
            "CSS marker position override",
            VALID.replace(
                '<body>',
                '<head><style>circle[data-polar-marker]{cx:1000px;cy:1000px}</style></head><body>',
            ),
            "CSS geometry properties are forbidden in polar documents",
        ),
        (
            "CSS all shorthand override",
            VALID.replace(
                '<body>',
                '<head><style>[data-polar-ray]{all:initial!important}</style></head><body>',
            ),
            "CSS selectors must not target data-polar-chart",
        ),
        (
            "CSS individual scale override",
            VALID.replace(
                '<body>',
                '<head><style>[data-polar-ray]{scale:10}</style></head><body>',
            ),
            "CSS selectors must not target data-polar-chart",
        ),
        (
            "inline CSS marker radius override",
            VALID.replace(
                'data-polar-marker="" cx="125"',
                'data-polar-marker="" style="r:40px" cx="125"',
                1,
            ),
            "inline CSS geometry properties are forbidden inside data-polar-chart",
        ),
        (
            "inline CSS marker position override",
            VALID.replace(
                'data-polar-marker="" cx="125"',
                'data-polar-marker="" style="cx:1000px;cy:1000px" cx="125"',
                1,
            ),
            "inline CSS geometry properties are forbidden inside data-polar-chart",
        ),
        (
            "inline CSS ray translation",
            VALID.replace(
                'data-polar-ray=""',
                'data-polar-ray="" style="translate:100px 0"',
                1,
            ),
            "inline styles are forbidden inside data-polar-chart",
        ),
        (
            "inline CSS marker offset path",
            VALID.replace(
                'data-polar-marker=""',
                'data-polar-marker="" style="offset-path:path(&quot;M0 0L100 0&quot;);offset-distance:100%"',
                1,
            ),
            "inline styles are forbidden inside data-polar-chart",
        ),
        (
            "classed chart primitive",
            VALID.replace('data-polar-marker=""', 'data-polar-marker="" class="marker"', 1),
            "class attributes are forbidden inside data-polar-chart",
        ),
        (
            "duplicate ray stroke-width",
            VALID.replace(
                'stroke-width="2"', 'stroke-width="40" stroke-width="2"', 1
            ),
            "duplicate attribute stroke-width on <line>",
        ),
        (
            "duplicate marker radius",
            VALID.replace('r="4" stroke-width="1.2"',
                          'r="40" r="4" stroke-width="1.2"', 1),
            "duplicate attribute r on <circle>",
        ),
        (
            "duplicate ring fill",
            VALID.replace('r="20" fill="none"',
                          'r="20" fill="red" fill="none"', 1),
            "duplicate attribute fill on <circle>",
        ),
        (
            "mismatched chart end tag",
            VALID.replace(
                '</svg>',
                '</bogus><polygon points="100,100 100,20 180,100"/></svg>',
            ),
            "mismatched closing tag </bogus>",
        ),
        (
            "nested SVG",
            VALID.replace('</svg>', '<svg></svg></svg>'),
            "unsupported SVG element <svg>",
        ),
        (
            "unmarked filled circle",
            VALID.replace(
                '</svg>', '<circle cx="100" cy="100" r="80" fill="red"/></svg>'
            ),
            "circle must be a ring or category marker",
        ),
        (
            "unmarked rectangle",
            VALID.replace(
                '</svg>', '<rect width="50%" height="50%" fill="red"/></svg>'
            ),
            "rect must be the chart background",
        ),
        (
            "partial chart background",
            VALID.replace('data-polar-background="" width="100%"',
                          'data-polar-background="" width="50%"'),
            "background must cover the full chart",
        ),
        (
            "filled grid ring",
            VALID.replace(
                '</svg>',
                '<circle data-polar-ring="" cx="100" cy="100" r="80" fill="red"/></svg>',
            ),
            "ring must use fill none",
        ),
        (
            "off-grid ring",
            VALID.replace(
                '</svg>',
                '<circle data-polar-ring="" cx="100" cy="100" r="70" fill="none" stroke-width="0.8"/></svg>',
            ),
            "ring radius 70 is not a 20% scale interval",
        ),
        (
            "thick grid ring",
            VALID.replace(
                '</svg>',
                '<circle data-polar-ring="" cx="100" cy="100" r="80" fill="none" stroke-width="40"/></svg>',
            ),
            "ring stroke-width 40 does not match expected 0.8",
        ),
        (
            "inline-style thick grid ring",
            VALID.replace(
                'r="80" fill="none" stroke-width="0.8"',
                'r="80" fill="none" stroke-width="0.8" style="stroke-width: 40"',
            ),
            "ring stroke-width 40 does not match expected 0.8",
        ),
        (
            "missing grid ring",
            VALID.replace(
                '<circle data-polar-ring="" cx="100" cy="100" r="20" fill="none" '
                'stroke-width="0.8"/>',
                '',
            ),
            "grid-ring count is 4, expected five",
        ),
        (
            "duplicate grid radius",
            VALID.replace('r="20" fill="none"', 'r="40" fill="none"'),
            "ring radii must cover 20% through 100% intervals",
        ),
        (
            "small-radius duplicate grid rings",
            VALID.replace('data-polar-radius="100"', 'data-polar-radius="1"')
            .replace('r="20" fill="none"', 'r="0.5" fill="none"')
            .replace('r="40" fill="none"', 'r="0.5" fill="none"')
            .replace('r="60" fill="none"', 'r="0.5" fill="none"')
            .replace('r="80" fill="none"', 'r="0.5" fill="none"')
            .replace('r="100" fill="none"', 'r="0.5" fill="none"'),
            "ring radii must cover 20% through 100% intervals",
        ),
        (
            "oversized endpoint marker",
            VALID.replace('data-polar-marker="" cx="125" cy="100" r="4"',
                          'data-polar-marker="" cx="125" cy="100" r="40"'),
            "marker radius 40 does not match expected 4",
        ),
        (
            "thick endpoint marker",
            VALID.replace('cx="125" cy="100" r="4" stroke-width="1.2"',
                          'cx="125" cy="100" r="4" stroke-width="40"'),
            "marker stroke-width 40 does not match expected 1.2",
        ),
        (
            "unmarked thick line",
            VALID.replace(
                '</svg>',
                '<line x1="100" y1="100" x2="200" y2="100" stroke-width="80"/></svg>',
            ),
            "line must be a spoke, category ray, or rule",
        ),
        (
            "thick category ray",
            VALID.replace('data-polar-ray="" x1="100" y1="100" x2="125" y2="100" '
                          'stroke-width="2"',
                          'data-polar-ray="" x1="100" y1="100" x2="125" y2="100" '
                          'stroke-width="40"'),
            "ray stroke-width 40 does not match expected 2",
        ),
        (
            "missing category spoke",
            VALID.replace(
                '<line data-polar-spoke="" data-polar-index="3" x1="100" y1="100" '
                'x2="0" y2="100" stroke-width="0.8"/>',
                '',
            ),
            "spoke indices must be contiguous 0..3",
        ),
        (
            "thick chart rule",
            VALID.replace(
                '</svg>',
                '<line data-polar-rule="" x1="0" y1="210" x2="200" y2="210" '
                'stroke-width="40"/></svg>',
            ),
            "rule stroke-width 40 does not match expected 0.8",
        ),
        (
            "duplicate chart rules",
            VALID.replace(
                '</svg>',
                '<line data-polar-rule="" x1="0" y1="210" x2="200" y2="210" '
                'stroke-width="0.8"/>'
                '<line data-polar-rule="" x1="0" y1="220" x2="200" y2="220" '
                'stroke-width="0.8"/></svg>',
            ),
            "chart rule count is 2, expected at most one",
        ),
        (
            "transformed chart geometry",
            VALID.replace('<g data-polar-category="c1"',
                          '<g transform="scale(10)" data-polar-category="c1"'),
            "transforms are forbidden inside data-polar-chart",
        ),
        (
            "non-SVG chart root",
            VALID.replace('<svg data-polar-chart=""', '<div data-polar-chart=""')
            .replace('</svg>', '</div>'),
            "data-polar-chart must be an SVG element",
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
        (
            "direct display-none value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" display=" NONE ">25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "direct visibility-hidden value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" visibility=" HiDdEn ">25</text>',
            ),
            "explicitly hidden",
        ),
        (
            "direct opacity-zero value label",
            VALID.replace(
                '<text data-polar-value-label="">25</text>',
                '<text data-polar-value-label="" opacity=" 0.0 ">25</text>',
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
