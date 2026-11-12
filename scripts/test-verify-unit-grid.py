#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-unit-grid.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_unit_grid", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


TOKENS = "<style>:root{--ink:#2d3142;--accent:#bf4520}</style>"
INK, ACCENT, EMPTY = "#2d3142", "#bf4520", "#ececec"
CELL_RE = re.compile(r'<rect data-unit-cell="[a-z]+" data-unit-index="(\d+)"')


def chart(cells: str, filled: int = 2) -> str:
    return (
        TOKENS + '<svg data-unit-grid="true" data-unit-total="100" data-unit-filled="' + str(filled)
        + '" data-unit-rows="10" data-unit-columns="10">'
        + f'<text data-unit-percent="true">{filled}%</text>'
        + f'<text data-unit-count="true">{filled} complete · {100 - filled} remaining</text>'
        + cells + '</svg>'
    )


def cell(index: int, state: str = "empty", width: int = 20) -> str:
    return (
        f'<rect data-unit-cell="{state}" data-unit-index="{index}" '
        f'x="{index % 10 * 24}" y="{index // 10 * 24}" width="{width}" height="20" '
        f'fill="{INK if state == "filled" else EMPTY}"/>'
    )


def edit_cell(source: str, index: int, attrs: str = "", fill: str | None = None) -> str:
    """Add attributes to, or repaint, the unit cell with this index."""
    match = next(m for m in CELL_RE.finditer(source) if int(m.group(1)) == index)
    end = source.index(">", match.end())
    tag = source[match.start():end]
    if fill is not None:
        tag = re.sub(r'fill="[^"]*"', f'fill="{fill}"', tag, count=1)
    return source[:match.start()] + tag + " " + attrs + source[end:]


def cell_fill(source: str, index: int) -> str:
    match = next(m for m in CELL_RE.finditer(source) if int(m.group(1)) == index)
    return re.search(r'fill="([^"]*)"', source[match.start():source.index(">", match.end())]).group(1)


def main() -> int:
    verifier = load_verifier()
    valid_cells = "".join(cell(index, "filled" if index < 2 else "empty") for index in range(100))
    swapped_indices = (
        valid_cells.replace('data-unit-index="0"', 'data-unit-index="swap"', 1)
        .replace('data-unit-index="1"', 'data-unit-index="0"', 1)
        .replace('data-unit-index="swap"', 'data-unit-index="1"', 1)
    )
    out_of_order_fill = (
        valid_cells.replace('data-unit-cell="filled"', 'data-unit-cell="swap"', 1)
        .replace('data-unit-cell="empty"', 'data-unit-cell="filled"', 1)
        .replace('data-unit-cell="swap"', 'data-unit-cell="empty"', 1)
    )
    cases = [
        ("valid chart", chart(valid_cells), None),
        ("wrong filled count", chart(valid_cells, 3), "declares 3 filled units"),
        ("nonuniform cell", chart(valid_cells.replace('width="20"', 'width="24"', 1)), "identical dimensions"),
        ("duplicate index", chart(valid_cells.replace('data-unit-index="99"', 'data-unit-index="98"')), "indices"),
        ("missing cell", chart(valid_cells.rsplit("<rect", 1)[0]), "has 99 data-unit-cell"),
        ("overlapping cells", chart(valid_cells.replace(' x="24"', ' x="19"')), "must not overlap"),
        ("irregular gutter", chart(valid_cells.replace(' x="24"', ' x="25"')), "4px gutter"),
        ("indices out of reading order", chart(swapped_indices), "reading order"),
        ("filled cells out of reading order", chart(out_of_order_fill), "filled cells must occupy"),
    ]
    valid = chart(valid_cells)
    cases.extend([
        ("single quoted chart", valid.replace('"', "'"), None),
        ("wrong headline", valid.replace(">2%</text>", ">74%</text>"), "printed percentage"),
        ("wrong printed count", valid.replace("2 complete", "3 complete"), "printed count"),
        ("wrong remaining count", valid.replace("98 remaining", "97 remaining"), "printed count"),
        ("missing headline", valid.replace('data-unit-percent="true"', ''), "printed percentage"),
        ("missing count", valid.replace('data-unit-count="true"', ''), "printed count"),
        ("cell transform", valid.replace('<rect ', '<rect transform="translate(300 0)" ', 1), "transform"),
        ("inline transform", valid.replace('<rect ', '<rect style="transform:translateX(300px)" ', 1), "transform"),
        ("group transform", valid.replace('<rect ', '<g transform="translate(300 0)"><rect ', 1).replace('</svg>', '</g></svg>'), "transform"),
        ("root transform", valid.replace('<svg ', '<svg transform="translate(300 0)" ', 1), "transform"),
        ("CSS transform", '<style>rect { transform:translateX(300px); }</style>' + valid, "transform"),
        ("CSS translate", '<style>rect { translate:300px; }</style>' + valid, "translate"),
        ("group inline translate", valid.replace('<rect ', '<g style="translate:300px"><rect ', 1).replace('</svg>', '</g></svg>'), "translate"),
        ("inline rotate", valid.replace('<rect ', '<rect style="rotate:45deg" ', 1), "rotate"),
        ("inline scale", valid.replace('<rect ', '<rect style="scale:2" ', 1), "scale"),
        ("vendor transform", '<style>rect { -webkit-transform:translateX(300px); }</style>' + valid, "transform"),
        ("CSS position", '<style>rect { x:300px; }</style>' + valid, "CSS x"),
        ("CSS offset", '<style>rect { offset-path:path(\'M 0 0 L 300 0\'); }</style>' + valid, "offset-path"),
        ("CSS comment allowed", '<style>/* rect { transform:scale(2); } */</style>' + valid, None),
        ("HTML comment allowed", '<!-- <g transform="translate(300 0)"> -->' + valid, None),
        ("CSS text transform allowed", '<style>text { text-transform:uppercase; }</style>' + valid, None),
        ("single quoted transform", valid.replace('<rect ', "<rect transform='translate(300 0)' ", 1), "transform"),
    ])
    cases.extend([
        ("group fill inherited", valid.replace(f'data-unit-index="1" x="24" y="0" width="20" height="20" fill="{INK}"', 'data-unit-index="1" x="24" y="0" width="20" height="20"').replace('<rect data-unit-cell="filled" data-unit-index="1"', f'<g fill="{EMPTY}"><rect data-unit-cell="filled" data-unit-index="1"').replace('<rect data-unit-cell="empty" data-unit-index="2"', '</g><rect data-unit-cell="empty" data-unit-index="2"'), "painted"),
        ("default black fill", valid.replace(f'width="20" height="20" fill="{INK}"/>', 'width="20" height="20"/>', 1), "painted"),
        ("group opacity", valid.replace('<rect data-unit-cell="filled" data-unit-index="0"', '<g opacity="0"><rect data-unit-cell="filled" data-unit-index="0"').replace('<rect data-unit-cell="filled" data-unit-index="1"', '</g><rect data-unit-cell="filled" data-unit-index="1"'), "hidden by opacity"),
        ("root inline opacity", valid.replace('<svg ', '<svg style="opacity:0" ', 1), "hidden by opacity"),
        ("cell in defs", valid.replace('<rect data-unit-cell="filled" data-unit-index="0"', '<defs><rect data-unit-cell="filled" data-unit-index="0"').replace('<rect data-unit-cell="filled" data-unit-index="1"', '</defs><rect data-unit-cell="filled" data-unit-index="1"'), "hidden by defs"),
        ("cell in mask", valid.replace('<rect data-unit-cell="filled" data-unit-index="0"', '<mask id="m"><rect data-unit-cell="filled" data-unit-index="0"').replace('<rect data-unit-cell="filled" data-unit-index="1"', '</mask><rect data-unit-cell="filled" data-unit-index="1"'), "hidden by mask"),
        ("missing tokens", valid.replace(TOKENS, ""), "--ink"),
        ("second accent", edit_cell(edit_cell(valid, 0, fill=ACCENT), 1, fill=ACCENT), "--accent"),
        ("one accent allowed", edit_cell(valid, 1, fill=ACCENT), None),
        ("opacity one allowed", edit_cell(valid, 0, 'opacity="1"'), None),
    ])
    for filled in (0, 100):
        marks = "".join(cell(index, "filled" if index < filled else "empty") for index in range(100))
        cases.append((f"{filled} filled cells", chart(marks, filled), None))
    for path in sorted((ROOT / "skills/diagram-design/assets").glob("example-unit-grid*.html")):
        source = path.read_text(encoding="utf-8")
        cases.append((f"{path.name} valid", source, None))
        cases.append((f"{path.name} wrong headline", source.replace('>64%</text>', '>74%</text>'), "printed percentage"))
        ink, empty = cell_fill(source, 0), cell_fill(source, 99)
        cases.extend([
            (f"{path.name} filled cell painted empty", edit_cell(source, 0, fill=empty), "painted"),
            (f"{path.name} empty cell painted filled", edit_cell(source, 99, fill=ink), "painted"),
            (f"{path.name} filled cell fill none", edit_cell(source, 0, fill="none"), "painted"),
            (f"{path.name} filled cell inline fill", edit_cell(source, 0, f'style="fill:{empty}"'), "painted"),
            (f"{path.name} filled cell translucent fill", edit_cell(source, 0, fill="rgba(45,49,66,0)"), "painted"),
            (f"{path.name} opacity zero", edit_cell(source, 0, 'opacity="0"'), "hidden by opacity"),
            (f"{path.name} fill-opacity zero", edit_cell(source, 0, 'fill-opacity="0"'), "hidden by fill-opacity"),
            (f"{path.name} inline opacity", edit_cell(source, 0, 'style="opacity:.0"'), "hidden by opacity"),
            (f"{path.name} visibility hidden", edit_cell(source, 0, 'visibility="hidden"'), "hidden by visibility"),
            (f"{path.name} display none", edit_cell(source, 0, 'display="none"'), "hidden by display"),
            (f"{path.name} mask", edit_cell(source, 0, 'mask="url(#m)"'), "hidden by mask"),
            (f"{path.name} CSS fill", source.replace("</style>", f'rect[data-unit-index="0"]{{fill:{empty}}}</style>', 1), "CSS fill"),
            (f"{path.name} CSS opacity", source.replace("</style>", "rect{opacity:0}</style>", 1), "CSS opacity"),
            (f"{path.name} CSS display none", source.replace("</style>", "rect{display:none}</style>", 1), "CSS display"),
            (f"{path.name} SMIL set", source.replace("</svg>", f'<set href="#c0" attributeName="fill" to="{empty}"/></svg>', 1), "can repaint or move"),
            (f"{path.name} overlay rect", source.replace("</svg>", f'<rect x="0" y="0" width="1000" height="390" fill="{empty}"/></svg>', 1), "covers unit cell"),
        ])
        cases.append((f"{path.name} moved cell", source.replace('<rect data-unit-cell=', '<rect transform="translate(300 0)" data-unit-cell=', 1), "transform"))
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        for name, source, expected in cases:
            path = Path(directory) / "fixture.html"
            path.write_text(source, encoding="utf-8")
            findings = verifier.check(path)
            if expected is None and findings:
                failures.append(f"{name} failed: {findings}")
            elif expected is not None and not any(expected in finding for finding in findings):
                failures.append(f"{name} did not report {expected!r}: {findings}")
            else:
                print(f"OK: {name}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
