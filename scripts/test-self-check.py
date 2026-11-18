#!/usr/bin/env python3
"""Adversarial tests for the packaged skill self-check (self_check.py)."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF_CHECK = ROOT / "skills/diagram-design/scripts/self_check.py"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
TEMPLATE = ASSET_DIR / "template-motion.html"
EXAMPLE = ASSET_DIR / "example-policy-trace-animated.html"
STATIC_EXAMPLE = ASSET_DIR / "example-architecture.html"


def load_self_check():
    spec = importlib.util.spec_from_file_location("self_check", SELF_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_self_check()
    failures: list[str] = []

    def check_pass(label: str, path: Path) -> None:
        errors = module.verify(path)
        if errors:
            failures.append(f"{label}: expected pass, got {errors}")
        else:
            print(f"OK: {label} passes")

    def check_fail(label: str, source: str, needle: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            errors = module.verify(candidate)
        if not any(needle in error for error in errors):
            failures.append(f"{label}: expected an error containing {needle!r}, got {errors}")
        else:
            print(f"OK: {label} rejected")

    def check_source_pass(label: str, source: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            check_pass(label, candidate)

    check_pass("shipped template", TEMPLATE)
    check_pass("shipped animated example", EXAMPLE)
    check_pass("shipped static example", STATIC_EXAMPLE)

    static = STATIC_EXAMPLE.read_text(encoding="utf-8")
    animated = EXAMPLE.read_text(encoding="utf-8")

    # Document completeness: truncation, mojibake and unbalanced markup must all fail.
    # The negative controls below are valid HTML that the balance count must not flag.
    def check_mutation_fail(
        label: str, find: str, replace: str, needle: str, limit: int = 1
    ) -> None:
        if find not in static:
            failures.append(f"{label}: fixture has no {find!r} to mutate")
            return
        check_fail(label, static.replace(find, replace, limit), needle)

    def check_mutation_pass(label: str, find: str, replace: str, limit: int = 1) -> None:
        if find not in static:
            failures.append(f"{label}: fixture has no {find!r} to mutate")
            return
        check_source_pass(label, static.replace(find, replace, limit))

    check_fail("truncated document", static[: len(static) // 2], "does not end with </html>")
    check_fail("mojibake", "\ufffd" + static, "U+FFFD")
    check_mutation_fail("dropped closing tag", "</text>", "", "<text> opens")
    check_mutation_fail("swapped closing tag", "</div>", "</span>", "<div> opens")
    check_mutation_fail("stray closing tag", "</body>", "</body></span>", "<span> opens")
    check_mutation_fail("unclosed span", "<body>", "<body><span>tip", "<span> opens")
    check_mutation_fail("incomplete shell", "</html>", "", "does not end with </html>")
    # Titles and text areas are RCDATA: tag names in them are text, not elements.
    check_mutation_pass("tag names in a page title", "<title>", "<title>Using <span> and <div> labels in ")
    check_mutation_pass("tag names in a textarea", "<body>", "<body><textarea>Using <span> labels</textarea>")
    check_mutation_pass("trailing comment after the html end tag", "</html>", "</html>\n<!-- generated -->")
    check_mutation_pass("space before the html end tag's >", "</html>", "</html >")
    check_mutation_pass("newline inside the html end tag", "</html>", "</html\n>")
    check_mutation_fail("unclosed textarea", "<body>", "<body><textarea>x", "is never closed")
    check_mutation_pass("optional end tag", "</p>", "")
    check_mutation_pass("optional head end tag", "</head>", "")
    check_mutation_pass("optional body end tag", "</body>", "")
    check_mutation_pass("void element", "<body>", "<body><br>")
    check_mutation_pass(
        "opening tag text in an attribute",
        "<body>",
        '<body><span title="<div>">tip</span>',
    )
    check_mutation_pass(
        "closing tag text in an attribute",
        "<body>",
        '<body><span title="</div>">tip</span>',
    )
    check_mutation_pass(
        "markup and an unclosed CSS comment in a stylesheet",
        "</style>",
        "/* <!-- */ .probe { fill: red }</style>",
    )

    for location, markup in (
        ("heading before SVG", '<h2 id="architecture-title">Monthly traffic summary</h2>'),
        ("description duplicate", '<p id="architecture-desc">Unrelated description</p>'),
    ):
        check_fail(location, static.replace("<body>", "<body>" + markup, 1),
                   "duplicate accessible SVG naming ID")
    check_fail(
        "heading after SVG", static.replace("</body>",
            '<h2 id="architecture-title">Monthly traffic summary</h2></body>', 1),
        "duplicate accessible SVG naming ID",
    )
    check_source_pass("distinct heading ID", static.replace("<body>",
        '<body><h2 id="monthly-summary">Monthly traffic summary</h2>', 1))
    check_source_pass("unreferenced duplicate IDs", static.replace("<body>",
        '<body><span id="unused">One</span><span id="unused">Two</span>', 1))

    check_fail(
        "executable attribute",
        static.replace("<body>", '<body onload="fetch(1)">', 1),
        "executable attribute",
    )
    check_fail(
        "remote image",
        static.replace("<body>", '<body><img src="https://tracker.example/p.gif">', 1),
        "remote reference",
    )
    check_fail(
        "CSS import",
        static.replace(
            "</style>", '@import "https://tracker.example/theme.css";</style>', 1
        ),
        "CSS @import",
    )
    check_fail(
        "external CSS URL",
        static.replace(
            "</style>",
            ".tracked { background: url(https://tracker.example/p.gif); }</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "escaped CSS import",
        static.replace(
            "</style>", '@\\69mport "https://tracker.example/theme.css";</style>', 1
        ),
        "CSS @import",
    )
    check_fail(
        "escaped CSS URL",
        static.replace(
            "</style>",
            ".tracked { background: \\75rl(https\\3a //tracker.example/p.gif); }</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    continuation = chr(92) + "\n"
    check_fail(
        "CSS continuation URL",
        static.replace(
            "</style>",
            ".tracked { background: "
            f'\\75rl("https:{continuation}/{continuation}/tracker.example/p.gif"); '
            "}</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    for label, newline in (
        ("LF", "\n"),
        ("CRLF", "\r\n"),
        ("CR", "\r"),
        ("form feed", "\f"),
    ):
        continuation = chr(92) + newline
        normalized = module.normalize_css_escapes(
            f'url("https:{continuation}/{continuation}/tracker.example/p.gif")'
        )
        if normalized != 'url("https://tracker.example/p.gif")':
            failures.append(f"CSS {label} continuation was not removed: {normalized!r}")
        else:
            print(f"OK: CSS {label} continuation normalized")
    check_fail(
        "CSS image set",
        static.replace(
            "</style>",
            '.tracked { background: image-set("https://tracker.example/p.gif" 1x); }</style>',
            1,
        ),
        "CSS image-set()",
    )
    check_fail(
        "inline style URL",
        static.replace("<body>", '<body style="background:url(local.png)">', 1),
        "non-fragment CSS url()",
    )
    check_fail(
        "SVG presentation URL",
        static.replace(
            "</svg>",
            '<rect fill="url(https://tracker.example/p.svg#paint)"></rect></svg>',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "duplicate style URL",
        static.replace(
            "<body>",
            '<body style="background:url(remote.png)" style="background:none">',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "CSS string comment bypass",
        static.replace(
            "</style>",
            '.tracked { content: "/*"; background: url(remote.png); --x: "*/"; }</style>',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_source_pass(
        "CSS-looking prose",
        static.replace(
            "<body>", "<body><p>Document @import and url(example) syntax.</p>", 1
        ),
    )
    check_fail(
        "lookalike fonts host",
        static.replace(
            "https://fonts.googleapis.com/css2",
            "https://fonts.googleapis.com.evil.tld/css2",
            1,
        ),
        "approved Google Fonts",
    )
    check_fail(
        "javascript URL",
        static.replace("<body>", '<body><a href="javascript:alert(1)">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "data html URL",
        static.replace("<body>", '<body><a href="data:text/html,x">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "iframe injection",
        static.replace("<body>", "<body><iframe></iframe>", 1),
        "not allowed",
    )
    check_fail(
        "arbitrary script",
        static.replace("</body>", "<script>alert(1)</script></body>", 1),
        "canonical data-diagram-controls attribute",
    )
    check_fail(
        "missing svg role",
        static.replace('role="img"', 'role="presentation"', 1),
        "role=img",
    )
    check_fail(
        "modified controller",
        animated.replace("'motion-ready'", "'motion-ready' /* patched */", 1),
        "exactly match the controller",
    )
    check_fail(
        "second script",
        animated.replace("</body>", "<script data-x></script></body>", 1),
        "at most one script",
    )
    check_fail(
        "hidden motion item",
        animated.replace(
            '<g data-motion-item data-step="1"',
            '<g style="opacity:0" data-motion-item data-step="1"',
            1,
        ),
        "hidden in source",
    )
    check_fail(
        "missing noscript",
        animated.replace("<noscript>", "<div>", 1).replace("</noscript>", "</div>", 1),
        "<noscript>",
    )
    check_fail(
        "non-decimal step count",
        animated.replace('data-step-count="5"', 'data-step-count="٥"', 1),
        "ASCII decimal",
    )

    # Content past the viewBox is clipped silently in the render (#406).
    clipped_legend = static.replace('viewBox="0 0 1000 480"', 'viewBox="0 0 1000 400"', 1)
    check_fail("legend below the viewBox", clipped_legend, "past the viewBox bottom edge")
    for label, markup, needle in (
        ("rect past the right edge", '<rect x="980" y="10" width="40" height="10"/>',
         "past the viewBox right edge"),
        ("translated text above the top edge",
         '<g transform="translate(10, -30)"><text x="5" y="10">Late</text></g>',
         "past the viewBox top edge"),
        ("line past the left edge", '<line x1="-20" y1="5" x2="10" y2="5"/>',
         "past the viewBox left edge"),
        ("circle past the bottom edge", '<circle cx="500" cy="478" r="10"/>',
         "past the viewBox bottom edge"),
        ("polygon past the right edge", '<polygon points="990,10 1010,20 990,30"/>',
         "past the viewBox right edge"),
        ("square-cornered rect past the right edge",
         '<rect x="1100" y="20" width="10" height="10" rx="0" ry="0"/>',
         "past the viewBox right edge"),
    ):
        check_fail(label, static.replace("</svg>", markup + "</svg>", 1), needle)
    for label, markup in (
        ("rect on the viewBox edges", '<rect x="0" y="0" width="1000" height="480"/>'),
        ("overhang within tolerance", '<rect x="990" y="0" width="12" height="5"/>'),
        ("definitions off-canvas", '<defs><rect x="5000" y="5000" width="1" height="1"/></defs>'),
        ("rotated group", '<g transform="rotate(90)"><rect x="5000" y="0" width="1" height="1"/></g>'),
        ("percentage size", '<rect x="0" y="0" width="200%" height="200%"/>'),
        ("display none group", '<g display="none"><rect x="1100" y="20" width="10" height="10"/></g>'),
        ("inline display none", '<rect style="display: none" x="1100" y="20" width="10" height="10"/>'),
        ("visibility hidden group", '<g visibility="hidden"><rect x="1100" y="20" width="10" height="10"/></g>'),
        ("oversized artwork clipped inside the canvas",
         '<clipPath id="inside"><rect x="10" y="10" width="200" height="100"/></clipPath>'
         '<g clip-path="url(#inside)"><rect x="-100" y="20" width="1200" height="40"/></g>'),
        ("masked group", '<g mask="url(#m)"><rect x="1100" y="20" width="10" height="10"/></g>'),
        ("zero-width rect placeholder", '<rect x="1100" y="20" width="0" height="10"/>'),
        ("zero-height rect placeholder", '<rect x="1100" y="20" width="10" height="0"/>'),
        ("zero-radius circle placeholder", '<circle cx="1100" cy="20" r="0"/>'),
        ("zero-radius ellipse placeholder", '<ellipse cx="1100" cy="20" rx="0" ry="5"/>'),
    ):
        check_source_pass(label, static.replace("</svg>", markup + "</svg>", 1))
    def styled(rule: str, markup: str) -> str:
        return static.replace("</style>", rule + "</style>", 1).replace("</svg>", markup + "</svg>", 1)

    placed_rect = '<rect class="placed" x="1100" y="20" width="10" height="10"/>'
    check_source_pass("stylesheet transform moves it inside",
                      styled(".placed { transform: translateX(-200px); }", placed_rect))
    check_source_pass("stylesheet display none on an ancestor",
                      styled("g.off { display: none; }",
                             '<g class="off"><rect x="1100" y="20" width="10" height="10"/></g>'))
    check_source_pass("stylesheet transform under a combinator",
                      styled(".motion-ready svg > .placed:hover { transform: none; }", placed_rect))
    check_fail("stylesheet rule that only colors it",
               styled(".placed { fill: #bf4520; }", placed_rect), "past the viewBox right edge")
    check_fail("transform keyframes alone do not exempt it",
               styled("@keyframes slide { 0% { transform: translateX(0); } }", placed_rect),
               "past the viewBox right edge")
    check_source_pass("aria-hidden decorative SVG", static.replace("</body>",
        '<svg aria-hidden="true" viewBox="0 0 10 10"><rect x="50" y="50" width="5" height="5"/></svg></body>', 1))
    outside_assets = []
    for asset in sorted(ASSET_DIR.glob("*.html")):
        viewbox_errors: list[str] = []
        module.check_viewbox(asset.read_text(encoding="utf-8"), viewbox_errors)
        if viewbox_errors:
            outside_assets.append(f"{asset.name}: {viewbox_errors}")
    if outside_assets:
        failures.append(f"shipped assets reported outside their viewBox: {outside_assets}")
    else:
        print("OK: every shipped asset stays inside its viewBox")

    # Text fit: a label budgeted wider than the visible box it sits in (0.60em sans,
    # 0.62em mono per character, style-guide.md) overflows its border.
    check_mutation_fail("sans node name overflows its box", ">Astro Origin</text>",
                        ">Astro Origin Server Cluster</text>", "overflows its 160px box")
    check_mutation_fail("mono sublabel overflows its box", ">src/content/*.mdx</text>",
                        ">src/content/blog/posts/*.mdx</text>", "overflows its 144px box")
    check_mutation_fail("end-anchored ghost number flipped to start",
                        'text-anchor="end">01</text>', 'text-anchor="start">01</text>',
                        "overflows its 144px box")
    check_mutation_pass("longer name that still fits", ">Astro Origin</text>",
                        ">Astro Origin SSR</text>")
    check_mutation_pass("connector label past its paper mask", ">HTTPS</text>",
                        ">HTTPS · TLS 1.3 · H2</text>")
    check_mutation_pass("free caption with no box",
                        "</svg>", '<text x="20" y="470" font-size="12">'
                        + "A caption with no box behind it runs as long as it likes</text></svg>")
    check_source_pass("stylesheet font size leaves the estimate to the browser",
                      styled("text.wide { font-size: 4px; }", "").replace(
                          '>Astro Origin</text>', ' class="wide">Astro Origin Server Cluster</text>', 1))
    def fit_svg(body: str, root: str = "") -> str:
        return re.sub(r"(<svg viewBox=\"0 0 1000 480\"[^>]*)>", r"\1" + root + ">", static, count=1).replace(
            "</svg>", body + "</svg>", 1)

    box = '<rect x="0" y="12" width="100" height="40" fill="#ececec" stroke="#2d3142"/>'
    check_source_pass("root svg text-anchor centers the label",
                      fit_svg(box + '<text x="50" y="32" font-size="10">ABCDEFGHIJ</text>',
                              ' text-anchor="middle"'))
    check_fail("root svg font-size is inherited",
               fit_svg(box + '<text x="4" y="32">ABCDEFGHIJKLMNOPQRST</text>', ' font-size="10"'),
               "overflows its 100px box")
    check_fail("box painted through inline style",
               fit_svg('<rect x="0" y="12" width="100" height="40" style="fill:#ececec;stroke:#2d3142"/>'
                       '<text x="4" y="32" font-size="10">ABCDEFGHIJKLMNOPQRST</text>'),
               "overflows its 100px box")
    check_fail("box painted by its group",
               fit_svg('<g fill="#ececec" stroke="#2d3142"><rect x="0" y="12" width="100" height="40"/></g>'
                       '<text x="4" y="32" font-size="10">ABCDEFGHIJKLMNOPQRST</text>'),
               "overflows its 100px box")
    check_source_pass("box painted by a stylesheet rule is left alone",
                      styled(".box { fill: #f5f5f5; }",
                             '<rect class="box" x="0" y="12" width="100" height="40"/>'
                             '<text x="4" y="32" font-size="10">ABCDEFGHIJKLMNOPQRST</text>'))
    for attribute in ('dx="-40"', 'dy="2"', 'rotate="0"', 'textLength="90"'):
        check_source_pass(f"text with {attribute} is not measured",
                          fit_svg(box + f'<text x="60" y="32" {attribute} font-size="10">ABCDEFGHIJ</text>'))
    long_label = '<text x="4" y="32" font-size="10">ABCDEFGHIJKLMNOPQRST</text>'
    for hidden in ('opacity="0"', 'fill-opacity="0"', 'fill="rgba(0,0,0,0)"', 'fill="#0000"',
                   'fill="#ececec00"', 'fill="hsl(0 0% 50% / 0%)"'):
        check_source_pass(f"label over a box that draws nothing ({hidden})",
                          fit_svg(f'<rect x="0" y="12" width="100" height="40" {hidden}/>' + long_label))
    check_source_pass("label over a box inside a transparent group",
                      fit_svg('<g opacity="0"><rect x="0" y="12" width="100" height="40" fill="#ececec"'
                              ' stroke="#2d3142"/></g>' + long_label))
    check_fail("stroke still draws when only the fill is transparent",
               fit_svg('<rect x="0" y="12" width="100" height="40" fill-opacity="0" stroke="#2d3142"/>'
                       + long_label), "overflows its 100px box")
    check_fail("box still draws when a child resets opacity",
               fit_svg('<g opacity="0.5"><rect x="0" y="12" width="100" height="40" fill="#ececec"/></g>'
                       + long_label), "overflows its 100px box")
    for layout in ('direction="rtl"', 'unicode-bidi="bidi-override"', 'writing-mode="tb"',
                   'xml:space="preserve"', 'style="white-space:pre"', 'style="direction:rtl"'):
        check_source_pass(f"text with {layout} is not measured",
                          fit_svg(box + f'<text x="96" y="32" {layout} font-size="10">ABCDEFGHIJ</text>'))
    check_source_pass("root svg direction is inherited",
                      fit_svg(box + '<text x="96" y="32" font-size="10">ABCDEFGHIJ</text>', ' direction="rtl"'))
    check_source_pass("stylesheet direction leaves the text alone",
                      styled("text.r { direction: rtl; }", box + '<text class="r" x="96" y="32" '
                             'font-size="10">ABCDEFGHIJ</text>'))
    overflowing_assets = []
    for asset in sorted(ASSET_DIR.glob("*.html")):
        fit_errors: list[str] = []
        module.check_text_fit(asset.read_text(encoding="utf-8"), fit_errors)
        if fit_errors:
            overflowing_assets.append(f"{asset.name}: {fit_errors}")
    if overflowing_assets:
        failures.append(f"shipped assets reported text overflowing its box: {overflowing_assets}")
    else:
        print("OK: every shipped asset's boxed text fits the width budget")

    # --offline: system-font output must make no network request, so the one
    # remote stylesheet the default contract allows becomes a failure.
    if module.verify(STATIC_EXAMPLE, offline=False):
        failures.append("offline off: the Google Fonts link must still pass by default")
    offline_errors = module.verify(STATIC_EXAMPLE, offline=True)
    if not any("offline: file loads Google Fonts" in error for error in offline_errors):
        failures.append(f"offline: Google Fonts link not rejected, got {offline_errors}")
    else:
        print("OK: offline mode rejects the Google Fonts link")
    system_font = re.sub(r'<link[^>]*fonts\.googleapis\.com[^>]*>', "", static)
    with tempfile.TemporaryDirectory() as scratch:
        candidate = Path(scratch) / "candidate.html"
        candidate.write_text(system_font, encoding="utf-8")
        errors = module.verify(candidate, offline=True)
    if errors:
        failures.append(f"offline: a system-font file should pass, got {errors}")
    else:
        print("OK: offline mode passes a file without the font link")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("All self-check tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
