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
            "move one customer cell below the visibility line",
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            '<rect x="544" y="400" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            "visibility: customer cell 'Retry payment'",
            False,
        ),
        (
            "widen one cell into the next stage",
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            '<rect x="544" y="128" width="400" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            "runs past its stage column",
            False,
        ),
        (
            "transparent visibility line",
            'stroke-width="2" data-role="visibility"/>',
            'stroke-width="2" opacity="0" data-role="visibility"/>',
            "visibility: stroke contrast",
            False,
        ),
        (
            "second cell painted with the accent but no data-focal",
            'fill="rgba(45,49,66,0.06)" stroke="#4f5d75" stroke-width="1" data-stage="sign-up" data-name="CRM write"',
            'fill="rgba(191,69,32,0.12)" stroke="#bf4520" stroke-width="1" data-stage="sign-up" data-name="CRM write"',
            "painted with the accent",
            False,
        ),
        (
            "cell label moved by a transform",
            '<text x="648" y="164"',
            '<text x="648" y="164" transform="translate(0,500)"',
            "text carries transform",
            False,
        ),
        (
            "stage header moved by a transform",
            '<rect x="96" y="24" width="208" height="48" fill="none" data-stage="sign-up"/>',
            '<rect x="96" y="24" width="208" height="48" fill="none" data-stage="sign-up" transform="translate(40,0)"/>',
            "stage header carries transform",
            False,
        ),
        (
            "cell label inside a translated group",
            '<text x="648" y="164"',
            '<g transform="translate(0,500)"><text x="648" y="164"',
            "text carries ancestor transform",
            False,
        ),
        (
            "printed text disagrees with data-name",
            ">Retry payment</text>",
            ">Call support</text>",
            "printed",
            False,
        ),
        (
            "cell widened by an inline CSS width",
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment" style="width:400px"/>',
            "sets its size in CSS",
            False,
        ),
        (
            "cells stretched by a stylesheet height",
            "  </style>",
            "    rect[data-stage] { height: 300px; }\n  </style>",
            "CSS 'height' declaration can resize",
            False,
        ),
        (
            "classed cell widened from the stylesheet",
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment"/>',
            '<rect x="544" y="128" width="208" height="64" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="hit-limit" data-name="Retry payment" class="wide"/><style>.wide { width: 400px; }</style>',
            "CSS 'width' declaration can resize",
            False,
        ),
        (
            "cell widened by a selector with a quoted space",
            "  </style>",
            '    rect[data-name="Retry payment"] { width: 400px; }\n  </style>',
            "CSS 'width' declaration can resize",
            False,
        ),
        (
            "cells widened through :is()",
            "  </style>",
            "    :is(rect, circle) { width: 400px; }\n  </style>",
            "CSS 'width' declaration can resize",
            False,
        ),
        (
            "cells widened by an attribute selector with a hash in its value",
            "  </style>",
            '    [fill="#ffffff"] { width: 400px; }\n  </style>',
            "CSS 'width' declaration can resize",
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

        # Sizing HTML around the figure is page layout, not a mark, even when
        # the selector uses an attribute.
        wrapper = source.replace(
            "  </style>", '    div[class="diagram-container"] { width: 100%; }\n  </style>', 1
        )
        if wrapper == source:
            failures.append("could not build the HTML-wrapper fixture")
        else:
            code, output = run(str(write(directory, "html-wrapper-width.html", wrapper)))
            if code != 0:
                failures.append(f"HTML-only attribute selector was rejected:\n{output}")
            else:
                print("OK: HTML-only attribute selector passes")

        # Alternatives inside :is() that only name HTML are page layout too.
        is_wrapper = source.replace(
            "  </style>",
            '    :is(div[class="diagram-container"], section) { width: 100%; }\n  </style>',
            1,
        )
        code, output = run(str(write(directory, "html-is-wrapper-width.html", is_wrapper)))
        if code != 0:
            failures.append(f":is() over HTML-only alternatives was rejected:\n{output}")
        else:
            print("OK: :is() over HTML-only alternatives passes")

        # An escaped quote inside an attribute value does not end the value.
        escaped_wrapper = source.replace(
            "  </style>", '    [data-note="6\\" preview"].frame { width: 100%; }\n  </style>', 1
        )
        code, output = run(str(write(directory, "escaped-quote-wrapper.html", escaped_wrapper)))
        if code != 0:
            failures.append(f"escaped-quote wrapper rule was rejected:\n{output}")
        else:
            print("OK: escaped-quote wrapper rule passes")

        # Every column widened past the spacing: the gutters stay equal but
        # are negative, so neighbouring stages overlap.
        overlap = source.replace('width="208"', 'width="240"').replace(
            'x2="1200" y2="268"', 'x2="1232" y2="268"'
        )
        if overlap == source:
            failures.append("could not build the overlapping-columns fixture")
        else:
            code, output = run(str(write(directory, "overlapping-columns.html", overlap)))
            if code == 0 or "columns overlap" not in output:
                failures.append(f"overlapping columns: expected 'columns overlap', got:\n{output}")
            else:
                print("OK: overlapping columns fail by name")

        # Japanese labels omit spaces: two <text> lines for one data-name must
        # pass (issue #438). Scope the no-whitespace join to one cell only.
        welcome_rect = (
            '<rect x="96" y="80" width="208" height="48" rx="4" fill="#ffffff" '
            'stroke="#2d3142" stroke-width="1" data-stage="sign-up" '
            'data-name="Welcome email"/>'
        )
        welcome_text = (
            '<text x="200" y="108" fill="#2d3142" font-size="12" '
            'font-family="\'Geist\', sans-serif" text-anchor="middle">Welcome email</text>'
        )
        if welcome_rect not in source or welcome_text not in source:
            failures.append("could not build Japanese two-line printed fixtures (anchor missing)")
        else:
            ja_rect = welcome_rect.replace('data-name="Welcome email"', 'data-name="歓迎メール"')
            ja_two_text = (
                '<text x="200" y="100" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">歓迎</text>\n'
                '        <text x="200" y="116" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">メール</text>'
            )
            ja_src = source.replace(welcome_rect, ja_rect, 1).replace(welcome_text, ja_two_text, 1)
            code, output = run(str(write(directory, "japanese-two-text-lines.html", ja_src)))
            if code != 0:
                failures.append(f"Japanese two <text> lines should pass:\n{output}")
            else:
                print("OK: Japanese two <text> lines pass")

            ja_tspan = (
                '<text x="200" y="100" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">\n'
                '          <tspan x="200" dy="0">歓迎</tspan>\n'
                '          <tspan x="200" dy="16">メール</tspan>\n'
                '        </text>'
            )
            ja_tspan_src = source.replace(welcome_rect, ja_rect, 1).replace(
                welcome_text, ja_tspan, 1
            )
            code, output = run(str(write(directory, "japanese-two-tspan.html", ja_tspan_src)))
            if code != 0:
                failures.append(f"Japanese two <tspan> lines should pass:\n{output}")
            else:
                print("OK: Japanese two <tspan> lines pass")

            en_two = (
                '<text x="200" y="100" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">Welcome</text>\n'
                '        <text x="200" y="116" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">email</text>'
            )
            en_src = source.replace(welcome_text, en_two, 1)
            code, output = run(str(write(directory, "english-two-text-lines.html", en_src)))
            if code != 0:
                failures.append(f"English two <text> lines should still pass:\n{output}")
            else:
                print("OK: English two <text> lines still pass")

            # Neighbouring cell text must not satisfy another cell's data-name
            # if we only strip whitespace globally across the plot.
            neighbor_fail = source.replace(
                welcome_rect,
                welcome_rect.replace('data-name="Welcome email"', 'data-name="歓迎メール"'),
                1,
            ).replace(welcome_text, welcome_text.replace("Welcome email", "歓迎"), 1)
            # Leave the rest of the diagram intact; compact join is cell-scoped,
            # so "歓迎" alone must not match "歓迎メール".
            code, output = run(str(write(directory, "japanese-partial-label.html", neighbor_fail)))
            if code == 0 or "printed: cell '歓迎メール'" not in output:
                failures.append(
                    f"partial Japanese label should fail printed check, got:\n{output}"
                )
            else:
                print("OK: partial Japanese label fails printed check")

            # Greptile gap: the split must NOT stitch across cells. The target
            # cell (Welcome email, x=96) prints only 歓迎, and the next cell
            # (Product UI, x=320) prints メール. The cell-scoped join collects
            # each cell's text by its own x/y, so メール in the Product UI cell
            # never reaches the Welcome email cell — the printed check must
            # still report 歓迎メール as missing. Pin this so a regression to a
            # global whitespace strip is caught.
            product_ui_text = (
                '<text x="424" y="108" fill="#2d3142" font-size="12" '
                'font-family="\'Geist\', sans-serif" text-anchor="middle">Product UI</text>'
            )
            if product_ui_text not in source:
                failures.append(
                    "could not build the cross-cell split fixture (Product UI anchor missing)"
                )
            else:
                cross_cell = (
                    source.replace(
                        welcome_rect,
                        welcome_rect.replace(
                            'data-name="Welcome email"', 'data-name="歓迎メール"'
                        ),
                        1,
                    )
                    .replace(welcome_text, welcome_text.replace("Welcome email", "歓迎"), 1)
                    .replace(product_ui_text, product_ui_text.replace("Product UI", "メール"), 1)
                )
                code, output = run(
                    str(write(directory, "japanese-cross-cell-split.html", cross_cell))
                )
                if code == 0 or "printed: cell '歓迎メール'" not in output:
                    failures.append(
                        f"cross-cell split should fail printed check (cell-scoped join must "
                        f"not stitch 歓迎 + メール across cells), got:\n{output}"
                    )
                else:
                    print("OK: cross-cell split fails printed check (cell-scoped join holds)")

        # Fixture under scripts/fixtures covers the same Japanese / tspan cases
        # on a minimal blueprint (see #438).
        fixture = ROOT / "scripts/fixtures/service-blueprint-japanese-two-line.html"
        if not fixture.is_file():
            failures.append(f"missing fixture {fixture}")
        else:
            code, output = run(str(fixture))
            if code != 0:
                failures.append(f"japanese two-line fixture should pass:\n{output}")
            else:
                print("OK: scripts/fixtures/service-blueprint-japanese-two-line.html passes")

        # Single-quoted attributes are valid SVG; a cell written that way
        # must still be checked. Evidence cells are not in the census, so a
        # skipped one could sit below the line without any finding.
        retry = '<rect x="96" y="80" width="208" height="48" rx="4" fill="#ffffff" stroke="#2d3142" stroke-width="1" data-stage="sign-up" data-name="Welcome email"/>'
        moved = retry.replace('y="80"', 'y="400"').replace('"', "'")
        if retry not in source:
            failures.append("could not build the single-quoted-cell fixture (anchor missing)")
        else:
            code, output = run(str(write(directory, "single-quoted-cell.html", source.replace(retry, moved, 1))))
            if code == 0 or "visibility: evidence cell 'Welcome email'" not in output:
                failures.append(f"single-quoted cell: expected a visibility finding, got:\n{output}")
            else:
                print("OK: single-quoted cell below the line fails by name")

    if failures:
        print("FAIL")
        for item in failures:
            print(item)
        return 1
    print("OK service-blueprint verifier: shipped files pass, named mutations fail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
