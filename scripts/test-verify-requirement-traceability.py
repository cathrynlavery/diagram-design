#!/usr/bin/env python3
"""Adversarial cases for requirement traceability source and link checks."""

from __future__ import annotations

import importlib.util
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-requirement-traceability.py"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-requirement-traceability.html"
DARK = ROOT / "skills/diagram-design/assets/example-requirement-traceability-dark.html"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_requirement_traceability", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    verifier = load_verifier()
    source = EXAMPLE.read_text(encoding="utf-8")
    assert verifier.check(EXAMPLE) == []
    first_group = '<g data-trace-row="REQ-01"'
    second_group = '<g data-trace-row="REQ-02"'
    label_tag = re.search(r'<text\b[^>]*>(?=REQ-01</text>)', source)
    assert label_tag is not None
    label_tag = label_tag[0]
    root = re.search(r"<svg\b[^>]*>", source)[0]
    cases = (
        *((first_group, first_group.replace("<g ", f"<g {attributes} "), "hidden or too faint")
          for attributes in (
              'style="display:none !important"', 'style="opacity:0 !important"',
              'opacity="0.00"', 'opacity="0%"', 'style="opacity:.0"', 'opacity="0.01"',
              'display="NONE"', 'display=" none"', 'visibility="collapse"',
          )),
        *((first_group, first_group.replace("<g ", f"<g {attributes} "), "unsupported SVG")
          for attributes in (
              'style="filter:opacity(0)"', 'clip-path="inset(50%)"',
              'clip-path="url(#empty)"', 'mask="url(#empty)"',
          )),
        *((label_tag, label_tag.replace('fill="#4f5d75"', f'fill="{paint}"').replace('fill="#2e5aa8"', f'fill="{paint}"'),
           "house ink")
          for paint in ("rgba(0,0,0,0)", "#0000", "#f5f5f5")),
        (label_tag, re.sub(r'font-size="[^"]+"', 'font-size="0"', label_tag), "font size"),
        ('data-trace-kind="source"', 'transform="scale(0)" data-trace-kind="source"', "unsupported SVG"),
        *((label_tag, motion + label_tag, "unsupported SVG")
          for motion in ('<set attributeName="display" to="none"/>',
                         '<animate attributeName="opacity" to="0" fill="freeze"/>')),
        ("</svg>", '<rect width="1200" height="720" fill="#f5f5f5"/></svg>', "cover"),
        ("</svg>", '<line x1="0" x2="1200" y1="360" y2="360" stroke="#f5f5f5" stroke-width="720"/></svg>', "cover"),
        (first_group, first_group.replace("<g ", r'<g style="display:n\6f ne" '), "hidden or too faint"),
        *((("</style>", rule + "</style>", "stylesheet")
          for rule in (
              '[data-trace-kind]{display:none}', 'g g{display:none}', 'svg>g{display:none}',
              '@media screen{svg g g{opacity:0}}', 'g text{fill:transparent!important}',
              'text{visibility:hidden}', 'svg{display:none!important}',
          ))),
        (first_group, first_group.replace("<g ", '<g display="none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g style="display:none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g opacity="0" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g transform="scale(0)" '), "unsupported SVG"),
        (first_group, first_group.replace("<g ", '<g style="transform:scale(0)" '), "unsupported SVG"),
        (first_group, first_group.replace("<g ", '<g style="scale:0" '), "unsupported SVG"),
        ("</style>", "g[data-trace-row]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", "g[*|data-trace-row]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", "g[|data-trace-row]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", r"g[data-\74 race-row]{display:none}</style>", "stylesheet must not select SVG"),
        ('data-trace-source="Review brief §1"', 'data-trace-source=""', "missing source reference"),
        ('data-trace-row="REQ-02"', 'data-trace-row="REQ-01"', "duplicate requirement row ID"),
        ('data-trace-from="DES-01"', 'data-trace-from="DES-99"', "source does not resolve"),
        ('data-trace-rel="satisfies"', 'data-trace-rel="unknown"', "unknown relationship"),
        ('data-trace-missing="true"', 'data-trace-missing="false"', "source does not resolve"),
        ('>REQ-01</text>', '>REQ-99</text>', "is not printed"),
        ('>REQ-01</text>', '>Unprinted</text><desc>REQ-01</desc>', "is not printed"),
        ('>REQ-01</text>', '>Unprinted</text><defs><text>REQ-01</text></defs>', "is not printed"),
        ('data-diagram-role="coverage-gap"', 'display="none" data-diagram-role="coverage-gap"', "needs a visible gap label"),
        ('data-source-ref="Review brief §1"', 'data-source-ref="Review brief §9"', "source reference does not match"),
        ('>Review brief §1</text>', '>Uncited</text>', "source citation is not printed"),
        # Root, page and wrapper changes that hide or clip the whole SVG.
        *((root, root.replace("<svg ", f"<svg {attributes} "), "SVG root")
          for attributes in ('height="0"', 'width="1" height="1"', 'style="opacity:.1"')),
        *((root, root.replace('viewBox="0 0 1200 720"', f'viewBox="{box}"'), "SVG root")
          for box in ("5000 0 1200 720", "0 0 1200000 720000")),
        *(('<div class="canvas">', f'<div class="canvas" {attributes}>', "HTML")
          for attributes in ("hidden", 'style="display:none"', 'style="width:0;overflow:hidden"')),
        *(('<div class="canvas">', f'<div class="canvas"><{tag}>', "HTML") for tag in ("details", "template", "noscript")),
        ("</body>", "<script>document.querySelector('svg').remove()</script></body>", "HTML"),
        ("</head>", '<link rel="stylesheet" href="hide.css"></head>', "HTML"),
        ('<div class="canvas">', "<!--" + root + "</svg>-->" + '<div class="canvas">', "HTML"),
        *(("</style>", rule + "</style>", "unsupported page rule")
          for rule in (".frame{max-width:0}", ".canvas{overflow-x:hidden}", "body{padding:48px 3000px}")),
        # Labels and cells moved off the canvas or out of their cell.
        (label_tag, label_tag.replace('x="272"', 'x="5272"'), "label is outside the viewBox"),
        (label_tag, label_tag.replace('x="272"', 'x="1000"'), "outside its cell"),
        (label_tag, label_tag.replace('y="154"', 'y="-5000"'), "label is outside the viewBox"),
        ('>REQ-01</text>', '><tspan x="5000">REQ-01</tspan></text>', "label is outside the viewBox"),
        ('<rect x="64" y="124"', '<rect x="5064" y="124"', "rectangle is outside the viewBox"),
        # Paper-coloured rules and rules drawn across cells.
        ("</svg>", '<line x1="0" x2="1200" y1="150" y2="150" stroke="#f5f5f5" stroke-width="4"/></svg>', "rule colour"),
        ("</svg>", '<line x1="0" x2="1200" y1="150" y2="150" stroke="#bfc0c0" stroke-width="4"/></svg>', "crosses a cell"),
        # Faint ink: 10% opacity is about 1.2:1 against the paper.
        (first_group, first_group.replace("<g ", '<g opacity="0.1" '), "too faint"),
        (label_tag, label_tag.replace("<text ", '<text fill-opacity="0.1" '), "too faint"),
        # Page CSS that moves the canvas, and style blocks the browser applies.
        *(("</style>", rule + "</style>", "unsupported page rule") for rule in (
            "h1{margin:-5000px 0 12px}", ".eyebrow{margin:0 0 -5000px}", ".subtitle{position:relative;top:-5000px}",
            ".cards p{font-size:1200px;line-height:1;margin:-1100px 0 0}", "h1{transform:translateY(-5000px)}",
        )),
        ("line-height:1.1;margin:0 0 12px}", "line-height:1.1;margin:-5000px 0 12px}", "unsupported page rule"),
        ('<title>Illustrative requirement traceability · Diagram Design</title>',
         '<title>x <!--</title><style>svg{visibility:hidden}</style>', "unsupported page rule"),
        ("</body>", "<style>svg{visibility:hidden}</style></body>", "<style> must sit in <head>"),
        ("</style>", "</style><style>svg{visibility:hidden}</style>", "exactly one <style>"),
        ('<meta charset="UTF-8">', '<meta charset="UTF-8"><meta name="description" content="<!--">', "HTML"),
        ("css2?family=", "css2?family=Flow+Block&family=", "HTML"),
        *(("</svg></div>", "</svg></div>" + extra, "template order")
          for extra in ("<h1>x</h1>", '<div class="cards"><section><p>x</p></section></div>')),
        # Strokes that paint the paper over labels.
        (label_tag, label_tag.replace("<text ", '<text stroke="#f5f5f5" stroke-width="4" '), "may not set stroke"),
        (first_group, first_group.replace("<g ", '<g stroke="#f5f5f5" stroke-width="4" '), "may not set stroke"),
        ('>REQ-01</text>', '><tspan stroke="#f5f5f5">REQ-01</tspan></text>', "may not set stroke"),
        # Oversized, unshipped or re-anchored labels, and headings drawn inside cells.
        (label_tag, label_tag.replace('font-size="16"', 'font-size="3000"'), "font size must be at most"),
        (label_tag, label_tag.replace('font-family="Geist, sans-serif"', 'font-family="Flow Block"'), "font family"),
        (label_tag, label_tag.replace("<text ", '<text text-anchor="end" '), "text-anchor"),
        (first_group, first_group.replace("<g ", '<g text-anchor="middle" '), "text-anchor"),
        ('<text x="864" y="64"', '<text x="900" y="200"', "inside a cell"),
        # A taller viewBox needs a matching backdrop.
        (root, root.replace('viewBox="0 0 1200 720"', 'viewBox="0 0 1200 896"'), "backdrop"),
    )
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "candidate.html"
        failures = []
        for old, new, expected in cases:
            assert old in source and old != new, (old, new)
            candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
            errors = verifier.check(candidate)
            if not any(expected in error for error in errors):
                failures.append((new, expected, errors))
        assert first_group in source and second_group in source
        wrapped = source.replace(first_group, '<g display="none">' + first_group, 1)
        wrapped = wrapped.replace(second_group, "</g>" + second_group, 1)
        candidate.write_text(wrapped, encoding="utf-8")
        errors = verifier.check(candidate)
        if not any("REQ-01:" in error and "is not printed" in error for error in errors):
            failures.append(("hidden SVG wrapper", "is not printed", errors))
        transformed = wrapped.replace('display="none"', 'transform="scale(0)"', 1)
        candidate.write_text(transformed, encoding="utf-8")
        errors = verifier.check(candidate)
        if not any("unsupported SVG property on g: transform" in error for error in errors):
            failures.append(("transformed SVG wrapper", "unsupported SVG", errors))
        boxes = list(re.finditer(r"<rect\b[^>]*/>", source))
        assert len(boxes) > 2
        last_box = boxes[-1]
        cover = '<rect x="0" y="0" width="1200" height="720" fill="#f5f5f5"/>'
        candidate.write_text(source[:last_box.start()] + cover + source[last_box.end():], encoding="utf-8")
        errors = verifier.check(candidate)
        if not any("overlaps another cell" in error for error in errors):
            failures.append(("cross-cell cover", "overlaps another cell", errors))
        # Cells moved, labels and rects together, beside the wrong requirement or under the wrong heading.
        def cell(cell_id: str) -> str:
            return re.search(rf'<g [^>]*data-trace-id="{cell_id}".*?</g>', source, re.S)[0]

        def moved(block: str, dx: int, dy: int) -> str:
            block = re.sub(r'\bx="(\d+)"', lambda m: f'x="{int(m[1]) + dx}"', block)
            return re.sub(r'\by="(\d+)"', lambda m: f'y="{int(m[1]) + dy}"', block)

        for swap, expected in (
            ((("TST-01", 0, 176), ("TST-02", 0, -176)), "outside its row"),
            ((("DES-01", 296, 0), ("TST-01", -296, 0)), "not under its column heading"),
        ):
            page = source
            for cell_id, dx, dy in swap:
                page = page.replace(cell(cell_id), moved(cell(cell_id), dx, dy), 1)
            assert page != source
            candidate.write_text(page, encoding="utf-8")
            errors = verifier.check(candidate)
            if not any(expected in error for error in errors):
                failures.append((f"swapped {swap}", expected, errors))
        # Four rows at the shipped 176px pitch in a 0 0 1200 896 canvas.
        start, end = source.index(first_group), source.index(second_group)
        fourth = re.sub(r'\by="(\d+)"', lambda m: f'y="{int(m[1]) + 528}"', source[start:end].replace("-01", "-04"))
        footer = source.index('<line x1="64" y1="668"')
        tall = source[:footer] + fourth + source[footer:].replace('y1="668" x2="1136" y2="668"', 'y1="844" x2="1136" y2="844"').replace('y="700"', 'y="876"', 1)
        tall = tall.replace('viewBox="0 0 1200 720"', 'viewBox="0 0 1200 896"').replace('<rect width="1200" height="720"', '<rect width="1200" height="896"')
        candidate.write_text(tall, encoding="utf-8")
        if verifier.check(candidate):
            failures.append(("four rows at 896", "no errors", verifier.check(candidate)))
        # House font spellings and a centred footer outside every cell.
        passing = {
            "quoted Geist": source.replace('font-family="Geist, sans-serif"', "font-family=\"'Geist', sans-serif\""),
            "Geist Mono ID": source.replace(
                'font-weight="700" font-family="Geist, sans-serif">SRC-01', "font-weight=\"700\" font-family=\"'Geist Mono', monospace\">SRC-01"),
            "centred footer": source.replace('<text x="64" y="700"', '<text x="600" y="700" text-anchor="middle"'),
        }
        for name, page in passing.items():
            assert page != source, name
            candidate.write_text(page, encoding="utf-8")
            if verifier.check(candidate):
                failures.append((name, "no errors", verifier.check(candidate)))
        # Title text is raw text in the browser, so markup inside it is not an element.
        candidate.write_text(source.replace("<title>Illustrative", "<title><b>Illustrative", 1), encoding="utf-8")
        if verifier.check(candidate):
            failures.append(("markup inside <title>", "no errors", verifier.check(candidate)))
        # The dark rule colour written with spaces is the same colour.
        dark = DARK.read_text(encoding="utf-8")
        assert "rgba(245,245,245,0.12)" in dark
        candidate.write_text(dark.replace("rgba(245,245,245,0.12)", "rgba(245, 245, 245, 0.12)"), encoding="utf-8")
        if verifier.check(candidate):
            failures.append(("spaced rgba rule colour", "no errors", verifier.check(candidate)))
        for new, expected, errors in failures:
            print(f"BYPASS expected {expected!r}: {new[:90]!r} -> {errors[:2]}")
        assert not failures, f"{len(failures)} adversarial cases passed"

        # A comment and an escaped bracket in a class name are not attribute selectors.
        inert_css = r"/* g[data-trace-row]{display:none} */ .literal\[data-trace-row\]{display:none}"
        assert "</style>" in source
        candidate.write_text(source.replace("</style>", inert_css + "</style>", 1), encoding="utf-8")
        assert verifier.check(candidate) == []
    print("OK requirement traceability: source, IDs, typed links, and explicit gaps")


if __name__ == "__main__":
    main()
