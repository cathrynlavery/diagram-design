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
        + '" data-unit-rows="10" data-unit-columns="10" viewBox="0 0 480 300">'
        + f'<text data-unit-percent="true" x="250" y="40" fill="{INK}" font-size="12">{filled}%</text>'
        + f'<text data-unit-count="true" x="250" y="60" fill="{INK}" font-size="12">{filled} complete · {100 - filled} remaining</text>'
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
    end -= source[end - 1] == "/"  # keep the element self-closing
    tag = source[match.start():end]
    if fill is not None:
        tag = re.sub(r'fill="[^"]*"', f'fill="{fill}"', tag, count=1)
    return source[:match.start()] + tag + " " + attrs + source[end:]


def cell_tag(source: str, index: int) -> str:
    match = next(m for m in CELL_RE.finditer(source) if int(m.group(1)) == index)
    return source[match.start():source.index(">", match.end()) + 1]


def wrap(source: str, first: int, last: int, opening: str, closing: str) -> str:
    """Wrap cells first..last (inclusive) in an element."""
    start = source.index(cell_tag(source, first))
    end = source.index(cell_tag(source, last)) + len(cell_tag(source, last))
    return source[:start] + opening + source[start:end] + closing + source[end:]


def after_cells(source: str, snippet: str) -> str:
    end = source.index(cell_tag(source, 99)) + len(cell_tag(source, 99))
    return source[:end] + snippet + source[end:]


def adversarial(source: str, ink: str, empty: str, accent: str = ACCENT) -> list[tuple[str, str, str | tuple[str, ...] | None]]:
    """Edits that change what a browser draws while the declared state stays the same."""
    def css(rule: str) -> str:
        return source.replace("</style>", rule + "</style>", 1)
    tag0, tag99 = cell_tag(source, 0), cell_tag(source, 99)
    return [
        # 1. cells are found by the HTML parser, so text that only looks like cells does not count
        ("cells in HTML comment", wrap(source, 53, 62, "<!--", "-->"), "has 90 data-unit-cell"),
        ("cells in text/plain script", wrap(source, 53, 62, '<script type="text/plain">', "</script>"), "has 90 data-unit-cell"),
        ("duplicate fill attribute", source.replace(tag99, tag99.replace(f'fill="{empty}"', f'fill="{ink}" fill="{empty}"', 1), 1), "repeats attribute fill"),
        ("duplicate x attribute", source.replace(tag0, tag0.replace(" x=", ' x="5000" x=', 1), 1), "repeats attribute x"),
        ("fake root in comment", '<!-- <svg data-unit-grid="true" data-unit-filled="1"> -->' + source, None),
        # 2. unrendered, conditional or moving ancestors
        *[(f"cells in <{tag}>", wrap(source, 53, 62, f"<{tag}>", f"</{tag}>"), f"<{tag.lower()}> ancestor")
          for tag in ("desc", "text", "foreignObject", "switch", "metadata", "svg", "symbol", "clipPath")],
        # Python 3.13+ parses <title> as raw text (cells vanish); older versions see a <title> ancestor.
        ("cells in title", wrap(source, 53, 62, "<title>", "</title>"), ("has 90 data-unit-cell", "<title> ancestor")),
        *[(f"group {attr}", wrap(source, 53, 62, f'<g {attr}="zz">', "</g>"), attr.lower())
          for attr in ("systemLanguage", "requiredExtensions", "requiredFeatures")],
        ("anchor transform", wrap(source, 53, 62, '<a href="#" transform="translate(5000 0)">', "</a>"), "transform"),
        ("anchor style transform", wrap(source, 53, 62, '<a href="#" style="transform:translate(5000px,0)">', "</a>"), "style attribute"),
        ("group style", wrap(source, 53, 62, '<g style="color:red">', "</g>"), "style attribute"),
        ("anchor allowed", wrap(source, 53, 62, '<a href="#">', "</a>"), None),
        # 3. cell paint beyond fill
        ("wide stroke on empty", source.replace(tag99, tag99.replace('stroke-width="0.8"', 'stroke-width="20"'), 1), "stroke-width"),
        ("wide stroke from group", wrap(source, 53, 53, '<g stroke-width="20">', "</g>").replace(cell_tag(source, 53), cell_tag(source, 53).replace(' stroke-width="0.8"', ""), 1), "stroke-width"),
        ("paint-order", source.replace(tag0, tag0.replace("<rect ", '<rect paint-order="stroke" ', 1), 1), "paint-order"),
        ("mix-blend-mode", source.replace(tag0, tag0.replace("<rect ", '<rect mix-blend-mode="lighten" ', 1), 1), "mix-blend-mode"),
        ("empty fill near ink", source.replace(f'fill="{empty}"', f'fill="#{(int(ink[1:], 16) ^ 1):06x}"'), "too close"),
        ("huge corner radius", source.replace(tag0, tag0.replace('rx="2"', 'rx="100"'), 1), "rx"),
        # 4. stylesheet tricks
        ("CSS hex escape", css("rect{f\\69ll:#000}"), "CSS fill"),
        ("CSS six-digit escape", css("rect{f\\000069 ll:#000}"), "CSS fill"),
        ("CSS char reference", source.replace("</svg>", "<style>rect{&#102;ill:#000}</style></svg>", 1), "CSS fill"),
        ("CSS @import", source.replace("<style>", "<style>@import url('x.css');", 1), "@import"),
        ("extra stylesheet link", source.replace("</head>", '<link rel="stylesheet" href="x.css"></head>', 1), "stylesheet"),
        ("CSS stroke", css("rect{stroke:#000;stroke-width:20px}"), "CSS stroke"),
        ("CSS stroke-width", css("rect{stroke-width:20px}"), "CSS stroke-width"),
        ("CSS all", css("rect{all:unset}"), "CSS all"),
        ("CSS mix-blend-mode", css("rect{mix-blend-mode:lighten}"), "CSS mix-blend-mode"),
        ("CSS paint-order", css("rect{paint-order:stroke}"), "CSS paint-order"),
        # 5. anything drawn after the first cell must be bounded outside the grid
        *[(f"overlay {name}", after_cells(source, snippet), "later <")
          for name, snippet in (
              ("path", f'<path d="M382 206h236v134h-236z" fill="{empty}"/>'),
              ("relative path", f'<path d="m300 200 l100 0 l0 50 z" fill="{empty}"/>'),
              ("arc path", f'<path d="M0 0 A500 500 0 0 1 900 0" fill="{empty}"/>'),
              ("circle", f'<circle cx="500" cy="300" r="60" fill="{ink}"/>'),
              ("ellipse", f'<ellipse cx="500" cy="300" rx="60" ry="10" fill="{ink}"/>'),
              ("polygon", f'<polygon points="382,230 618,230 618,330 382,330" fill="{ink}"/>'),
              ("polyline", f'<polyline points="382,230 618,330" stroke="{ink}" stroke-width="80"/>'),
              ("line", f'<line x1="382" y1="285" x2="618" y2="285" stroke="{ink}" stroke-width="120"/>'),
              ("thick line beside grid", f'<line x1="300" y1="90" x2="300" y2="300" stroke="{ink}" stroke-width="200"/>'),
              ("text", f'<text x="370" y="340" font-size="140" fill="{ink}">&#9608;&#9608;</text>'),
              ("text with tspan", '<text x="40" y="380" font-size="9"><tspan x="400" y="200">X</tspan></text>'),
              ("image", '<image x="382" y="230" width="236" height="110" href="#"/>'),
              ("use", '<use href="#c0" x="100" y="100"/>'),
              ("foreignObject", '<foreignObject x="382" y="230" width="236" height="110"></foreignObject>'),
              ("stroked empty rect", f'<rect x="440" y="250" width="120" height="40" fill="none" stroke="{ink}" stroke-width="130"/>'),
              ("rect px units", f'<rect x="382px" y="230px" width="236" height="110" fill="{ink}"/>'),
              ("rect percent", f'<rect x="38.2%" y="58.97%" width="236" height="110" fill="{ink}"/>'),
              ("rect CSS position", f'<rect style="x:382px;y:230px" width="236" height="110" fill="{ink}"/>'),
              ("rect transform", f'<rect transform="translate(382 230)" width="236" height="110" fill="{ink}"/>'),
              ("rect in moved group", f'<g transform="translate(382 230)"><rect width="1" height="1" fill="{ink}"/></g>'),
          )],
        ("label outside grid", after_cells(source, '<text x="40" y="380" font-size="9">Note</text>'), None),
        ("source note beside grid", after_cells(source, '<text x="40" y="130" font-size="11">Source: illustrative release checklist</text>'), None),
        ("note with plain tspan", after_cells(source, '<text x="660" y="230" font-size="11">Focal <tspan font-weight="600">check 64</tspan></text>'), None),
        ("source note reaching grid", after_cells(source, '<text x="300" y="130" font-size="11">Source: illustrative release checklist</text>'), "later <text> covers"),
        ("note with inherited font-size on grid", after_cells(source, '<g font-size="40"><text x="200" y="200">WWWWWWWW</text></g>'), "later <text> covers"),
        ("note with inherited end anchor on grid", after_cells(source, '<g text-anchor="end"><text x="700" y="200" font-size="11">Source note here</text></g>'), "later <text> covers"),
        ("note with positioned tspan", after_cells(source, '<text x="660" y="230" font-size="11">Focal <tspan x="400">check</tspan></text>'), "later <text> cannot be bounded"),
        ("path outside grid", after_cells(source, f'<path d="M40 340 h200 c10 0 10 10 0 10 z" fill="{ink}"/>'), None),
        # 7. CSS geometry: a stylesheet rule that can reach a cell may not resize it
        *[(f"CSS {prop} on a cell", css(f'rect[data-unit-index="0"]{{{prop}:40px}}'), f"CSS {prop}")
          for prop in ("width", "height", "rx", "ry", "r", "cx", "cy")],
        ("CSS width on every element", css("*{width:40px}"), "CSS width"),
        ("CSS width by id", source.replace(tag0, tag0.replace("<rect ", '<rect id="c0" ', 1), 1).replace("</style>", "#c0{width:40px}</style>", 1), "CSS width"),
        ("CSS width by class", source.replace(tag0, tag0.replace("<rect ", '<rect class="c" ', 1), 1).replace("</style>", ".c{width:40px}</style>", 1), "class"),
        ("inline width on a cell", source.replace(tag0, tag0.replace("<rect ", '<rect style="width:40px" ', 1), 1), "style attribute"),
        ("CSS width on page elements allowed", css(".note{width:10px}div.chart p{height:2px}"), None),
        # 8. the printed labels must be visible ink text inside the chart
        ("both labels display none", source.replace("data-unit-percent=\"true\"", 'data-unit-percent="true" display="none"', 1).replace("data-unit-count=\"true\"", 'data-unit-count="true" display="none"', 1), "the data-unit-percent label"),
        ("count label visibility hidden", source.replace("data-unit-count=\"true\"", 'data-unit-count="true" visibility="hidden"', 1), "the data-unit-count label"),
        ("percent label opacity zero", source.replace("data-unit-percent=\"true\"", 'data-unit-percent="true" opacity="0"', 1), "the data-unit-percent label"),
        ("percent label style", source.replace("data-unit-percent=\"true\"", 'data-unit-percent="true" style="font-size:1px"', 1), "the data-unit-percent label"),
        ("percent label in hidden group", source.replace("<text data-unit-percent", '<g display="none"><text data-unit-percent', 1).replace(">64%</text>", ">64%</text></g>", 1), "the data-unit-percent label"),
        ("percent label in defs", source.replace("<text data-unit-percent", "<defs><text data-unit-percent", 1).replace(">64%</text>", ">64%</text></defs>", 1), "the data-unit-percent label"),
        ("percent label painted empty", source.replace("data-unit-percent=\"true\"", "data-unit-percent=\"true\"", 1).replace(re.search(r'<text data-unit-percent[^>]*>', source).group(0), re.sub(r'fill="[^"]*"', f'fill="{empty}"', re.search(r'<text data-unit-percent[^>]*>', source).group(0), count=1), 1), "the data-unit-percent label"),
        ("percent label tiny", source.replace(re.search(r'<text data-unit-percent[^>]*>', source).group(0), re.sub(r'font-size="[^"]*"', 'font-size="4"', re.search(r'<text data-unit-percent[^>]*>', source).group(0), count=1), 1), "the data-unit-percent label"),
        ("percent label off canvas", source.replace(re.search(r'<text data-unit-percent[^>]*>', source).group(0), re.sub(r' x="[^"]*"', ' x="5000"', re.search(r'<text data-unit-percent[^>]*>', source).group(0), count=1), 1), "the data-unit-percent label"),
        ("percent label hides a tspan", source.replace(">64%</text>", '><tspan display="none">64%</tspan></text>', 1).replace(">64%</text>", ">64%</text>"), "the data-unit-percent label"),
        ("count label outside the svg", source.replace("<text data-unit-count=\"true\"", "<text data-x=\"true\"", 1).replace("</svg>", "</svg><p data-unit-count=\"true\">64 complete · 36 remaining</p>", 1), "the data-unit-count label"),
        # 9. smooth curves reflect control points the path box does not track
        ("overlay smooth quadratic", after_cells(source, f'<path d="M650 100 Q800 200 650 200 T650 300" fill="{ink}"/>'), "later <path> cannot be bounded"),
        ("overlay smooth cubic", after_cells(source, f'<path d="M650 100 C700 100 700 150 650 150 S700 300 650 300" fill="{ink}"/>'), "later <path> cannot be bounded"),
        # 10. percent rgb() channels sit on the same 0..255 scale as hex
        ("empty fill percent rgb near ink", source.replace(f'fill="{empty}"', f'fill="{percent_rgb(ink, 0.4)}"'), "too close"),
        ("empty fill percent rgb near accent", source.replace(f'fill="{empty}"', f'fill="{percent_rgb(accent, 0.4)}"'), "too close"),
        ("empty fill as percent rgb allowed", source.replace(f'fill="{empty}"', f'fill="{percent_rgb(empty)}"'), None),
        # 11. a stroke widens a later text's box
        ("stroked X beside grid", after_cells(source, f'<text x="626" y="200" font-size="20" stroke="{ink}" stroke-width="40">X</text>'), "later <text> covers"),
        ("group-stroked X beside grid", after_cells(source, f'<g stroke="{ink}" stroke-width="40"><text x="626" y="200" font-size="20">X</text></g>'), "later <text> covers"),
        ("stroked tspan beside grid", after_cells(source, f'<text x="626" y="200" font-size="20">X<tspan stroke="{ink}" stroke-width="40">Y</tspan></text>'), "later <text> cannot be bounded"),
        ("unstroked X beside grid allowed", after_cells(source, '<text x="626" y="200" font-size="20">X</text>'), None),
        # 6. a second :root rule must not break token parsing
        ("second :root rule", re.sub(r"(:root\{[^}]*?)(--accent:[^;}]*);([^}]*)\}", r"\1\3;\2}", source, count=1).replace("</style>", ":root{--grid-gap:4px}</style>", 1), None),
        ("later :root moves --ink", source.replace("</style>", f":root{{--ink:{empty}}}</style>", 1), "painted"),
    ]


def percent_rgb(hex_color: str, nudge: float = 0.0) -> str:
    """The same colour written as rgb() percentages, optionally nudged by a fraction of a percent."""
    channels = [int(hex_color[i:i + 2], 16) / 2.55 for i in (1, 3, 5)]
    return "rgb(" + ",".join(f"{min(100.0, channel + nudge):.1f}%" for channel in channels) + ")"


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
        ("cell in defs", valid.replace('<rect data-unit-cell="filled" data-unit-index="0"', '<defs><rect data-unit-cell="filled" data-unit-index="0"').replace('<rect data-unit-cell="filled" data-unit-index="1"', '</defs><rect data-unit-cell="filled" data-unit-index="1"'), "<defs> ancestor"),
        ("cell in mask", valid.replace('<rect data-unit-cell="filled" data-unit-index="0"', '<mask id="m"><rect data-unit-cell="filled" data-unit-index="0"').replace('<rect data-unit-cell="filled" data-unit-index="1"', '</mask><rect data-unit-cell="filled" data-unit-index="1"'), "<mask> ancestor"),
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
        accent = re.search(r"--accent:(#[0-9a-f]{6})", source).group(1)
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
            (f"{path.name} overlay rect", source.replace("</svg>", f'<rect x="0" y="0" width="1000" height="390" fill="{empty}"/></svg>', 1), "later <rect>"),
        ])
        cases.extend((f"{path.name} {name}", mutated, expected) for name, mutated, expected in adversarial(source, ink, empty, accent))
        cases.append((f"{path.name} moved cell", source.replace('<rect data-unit-cell=', '<rect transform="translate(300 0)" data-unit-cell=', 1), "transform"))
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        for name, source, expected in cases:
            path = Path(directory) / "fixture.html"
            path.write_text(source, encoding="utf-8")
            findings = verifier.check(path)
            if expected is None and findings:
                failures.append(f"{name} failed: {findings}")
            elif expected is not None and not any(wanted in finding for finding in findings
                                                  for wanted in (expected if isinstance(expected, tuple) else (expected,))):
                failures.append(f"{name} did not report {expected!r}: {findings}")
            else:
                print(f"OK: {name}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
