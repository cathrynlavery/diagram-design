#!/usr/bin/env python3
"""Adversarial tests for verify-steps.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-steps.py"
GOOD = ROOT / "skills/diagram-design/assets/example-steps.html"


def stage_fixture(count: int, stage_width: int | None = None) -> str:
    """Build a minimal legal fixture from the documented 1280px formula."""
    usable = 1280 - 2 * 80
    width = stage_width or min(224, 4 * (usable // (4 * count)))
    start = (1280 - count * width) / 2
    parts = ['<svg viewBox="0 0 1280 720">', '<rect width="100%" height="100%" fill="#f5f5f5"/>', '<g aria-hidden="true">']
    for index in range(1, count + 1):
        x = start + (index - 1) * width
        focal = ' data-focal="true"' if index == 3 else ""
        parts.append(f'<rect x="{x:g}" y="240" width="{width:g}" height="48" fill="rgba(45,49,66,0.05)" data-role="rail" data-step="s{index}" data-index="{index}"{focal}/>')
    parts.append('</g><g font-size="8" font-family="\'Geist Mono\', monospace" text-anchor="middle">')
    for index in range(1, count + 1):
        cx = start + (index - 0.5) * width
        focal = ' data-focal="true"' if index == 3 else ""
        parts.append(f'<circle cx="{cx:g}" cy="264" r="36" stroke="#2d3142" data-role="medallion" data-step="s{index}"{focal}/>')
        parts.append(f'<text x="{cx:g}" y="164" fill="#4f5d75" data-role="number" data-step="s{index}">{index:02d}</text>')
    parts.append('</g></svg>')
    return "".join(parts)


def wrapped(start: str, end: str, opener: str, closer: str) -> tuple[tuple[str, str], tuple[str, str]]:
    return (start, opener + start), (end, end + closer)


def sheet(css: str) -> tuple[str, str]:
    return "</head>", f"<style>{css}</style></head>"


def run(path: Path) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def main() -> int:
    source = GOOD.read_text(encoding="utf-8")
    failures: list[str] = []
    for path in sorted(GOOD.parent.glob("example-steps*.html")):
        code, output = run(path)
        if code:
            failures.append(f"shipped {path.name} failed\n{output}")
        else:
            print(f"OK: shipped {path.name} passes")

    cases = (
        ("gap in the rail", 'x="304" y="240" width="224"', 'x="312" y="240" width="224"', "contiguous rail"),
        ("one segment is wider", 'x="304" y="240" width="224"', 'x="304" y="240" width="232"', "equal rail"),
        ("duplicate stage index", 'data-step="research" data-index="2"', 'data-step="research" data-index="3"', "data-index"),
        ("focal rail removed", 'data-index="3" data-focal="true"', 'data-index="3"', "exactly one focal"),
        ("medallion shifted off center", 'cx="416" cy="264" r="36" stroke="#2d3142" data-role="medallion"', 'cx="424" cy="264" r="36" stroke="#2d3142" data-role="medallion"', "not centered"),
        ("printed number disagrees", 'data-role="number" data-step="research">02</text>', 'data-role="number" data-step="research">20</text>', "prints '20'"),
    )
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        for count in (6, 7):
            path = directory / f"good-{count}.html"
            path.write_text(stage_fixture(count), encoding="utf-8")
            code, output = run(path)
            if code:
                failures.append(f"documented {count}-stage fixture failed\n{output}")
            else:
                print(f"OK: documented {count}-stage fixture passes")
        clipped = directory / "bad-clipped-seven.html"
        clipped.write_text(stage_fixture(7, stage_width=224), encoding="utf-8")
        code, output = run(clipped)
        if code == 0 or "outside the viewBox" not in output:
            failures.append(f"old clipped seven-stage formula was not rejected\n{output}")
        else:
            print("OK: old clipped seven-stage formula rejected")
        for index, (name, old, new, expected) in enumerate(cases):
            if source.count(old) != 1:
                failures.append(f"fixture {name!r} anchor occurs {source.count(old)} times")
                continue
            path = directory / f"bad-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code == 0 or expected not in output:
                failures.append(f"{name}: expected rejection containing {expected!r}\n{output}")
            else:
                print(f"OK: {name} rejected")
        old = 'data-role="medallion" data-step="decide"'
        new = 'data-role="medallion" data-step="research"'
        path = directory / "bad-duplicate-and-missing-medallion.html"
        if source.count(old) != 1:
            failures.append(f"fixture duplicate and missing medallion anchor occurs {source.count(old)} times")
        else:
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            mismatch = "census: medallion steps differ from rail"
            duplicate = "census: step 'research' has more than one medallion"
            if code == 0 or mismatch not in output or duplicate not in output:
                failures.append(f"duplicate and missing medallion: expected both census findings\n{output}")
            elif output.index(mismatch) > output.index(duplicate):
                failures.append(f"duplicate and missing medallion: expected missing/extra finding first\n{output}")
            else:
                print("OK: duplicate and missing medallion reports the full census first")
        transform_cases = (
            ("rail transform", 'data-role="rail"', 'transform="translate(16 0)" data-role="rail"'),
            ("rail ancestor transform", '<g aria-hidden="true">', '<g aria-hidden="true" transform="translate(16 0)">'),
            ("rail CSS transform", '</head>', '<style>[data-role="rail"] { transform: translateX(16px); }</style></head>'),
        )
        for index, (name, old, new) in enumerate(transform_cases, len(cases)):
            if source.count(old) < 1:
                failures.append(f"fixture {name!r} anchor is missing")
                continue
            path = directory / f"bad-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code == 0 or "transform:" not in output:
                failures.append(f"{name}: expected transform rejection\n{output}")
            else:
                print(f"OK: {name} rejected")
        # A hidden, scaled, rotated or resized mark passes every attribute check
        # while the reader sees something else.
        rail = 'data-role="rail" data-step="frame"'
        group = '<g aria-hidden="true">'
        hidden_cases = (
            ("rail inline scale", rail, f'style="scale:1 0.5" {rail}', "style:"),
            ("rail inline rotate", rail, f'style="rotate:20deg" {rail}', "style:"),
            ("rail inline display", rail, f'style="display:none" {rail}', "style:"),
            ("rail inline visibility", rail, f'style="visibility:hidden" {rail}', "style:"),
            ("rail inline opacity", rail, f'style="opacity:0" {rail}', "style:"),
            ("rail inline width", rail, f'style="width:10px" {rail}', "style:"),
            ("rail ancestor inline style", group, '<g aria-hidden="true" style="opacity:0">', "style:"),
            ("medallion inline display", 'data-role="medallion" data-step="frame"', 'style="display:none" data-role="medallion" data-step="frame"', "style:"),
            ("number inline visibility", 'data-role="number" data-step="frame"', 'style="visibility:hidden" data-role="number" data-step="frame"', "style:"),
            ("rail class a stylesheet can reach", rail, f'class="r" {rail}', "style:"),
            ("rail display attribute", rail, f'display="none" {rail}', "hidden:"),
            ("rail visibility attribute", rail, f'visibility="hidden" {rail}', "hidden:"),
            ("rail ancestor opacity attribute", group, '<g aria-hidden="true" opacity="0.1">', "hidden:"),
            ("rail clip-path attribute", rail, f'clip-path="inset(0 100% 0 0)" {rail}', "hidden:"),
            ("container inline display", '<div class="diagram-container">', '<div class="diagram-container" style="display:none">', "page:"),
            ("stylesheet hides rail", *sheet('rect[data-role="rail"]{display:none}'), "hidden:"),
            ("stylesheet fades svg", *sheet("svg{opacity:0.2}"), "hidden:"),
            ("stylesheet repaints rail", *sheet('[data-role="rail"]{fill:none}'), "style:"),
            ("stylesheet resizes rail", *sheet("rect{width:10px}"), "style:"),
            ("stylesheet rotates svg", *sheet("svg{rotate:20deg}"), "transform:"),
            ("stylesheet scales rail", *sheet("rect{scale:1 0.5}"), "transform:"),
            ("malformed alpha", 'fill="rgba(191,69,32,0.08)" data-role="rail"', 'fill="rgba(191,69,32,0..08)" data-role="rail"', "paint: rail fill"),
            ("repeated attribute", group, '<g aria-hidden="true" aria-hidden="true">', "attributes:"),
            ("medallion stroke too wide", 'stroke="#2d3142" data-role="medallion" data-step="frame"', 'stroke="#2d3142" stroke-width="5" data-role="medallion" data-step="frame"', "stroke-width"),
            ("number font-size under 8", 'fill="#4f5d75" data-role="number" data-step="frame"', 'fill="#4f5d75" font-size="7" data-role="number" data-step="frame"', "font-size"),
            ("number off-house font", 'fill="#4f5d75" data-role="number" data-step="frame"', 'fill="#4f5d75" font-family="Comic Sans MS" data-role="number" data-step="frame"', "font-family"),
            ("number anchored at its end", 'fill="#4f5d75" data-role="number" data-step="frame"', 'fill="#4f5d75" text-anchor="end" data-role="number" data-step="frame"', "text-anchor"),
            ("narrow rem frame", *sheet(".frame{max-width:50rem}"), "max-width"),
            ("svg inside a list item", '<div class="diagram-container">', '<ul><li class="diagram-container">', "block containers"),
            ("number with a child", 'data-step="frame">01</text>', 'data-step="frame">01<tspan> </tspan></text>', "no child elements"),
        )
        for index, (name, old, new, expected) in enumerate(hidden_cases, 100):
            if source.count(old) < 1:
                failures.append(f"fixture {name!r} anchor is missing")
                continue
            path = directory / f"bad-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code == 0 or expected not in output:
                failures.append(f"{name}: expected rejection containing {expected!r}\n{output}")
            else:
                print(f"OK: {name} rejected")
        # A malformed value is a finding; the files after it are still checked.
        bad_alpha = directory / "bad-alpha.html"
        bad_alpha.write_text(source.replace("rgba(191,69,32,0.08)", "rgba(191,69,32,0..08)", 1), encoding="utf-8")
        result = subprocess.run([sys.executable, str(CHECKER), str(bad_alpha), str(GOOD)], capture_output=True, text=True)
        if result.returncode != 1 or "Traceback" in result.stderr or f"OK {GOOD}" not in result.stdout:
            failures.append(f"malformed alpha stopped the run\n{result.stdout}{result.stderr}")
        else:
            print("OK: malformed alpha is a finding and later files are still checked")
        # Each mutation below was rendered in Chromium and visibly hides, moves or
        # misstates a stage while the attribute geometry stays legal.
        n1 = '<text x="192" y="164" fill="#4f5d75" data-role="number" data-step="frame">01</text>'
        n5 = '<text x="1088" y="164" fill="#4f5d75" data-role="number" data-step="ship">05</text>'
        rail_group = '<g aria-hidden="true">\n          <rect x="80"'
        rail_end = 'data-index="5"/>\n        </g>'
        container = '<div class="diagram-container">'
        rendered_cases = (
            ("svg stroke", [sheet("svg{stroke:#f5f5f5;stroke-width:60}")]),
            ("container svg stroke", [sheet(".diagram-container svg{stroke:#f5f5f5;stroke-width:60}")]),
            (":root stroke", [sheet(":root{stroke:#f5f5f5;stroke-width:60}")]),
            ("body stroke", [sheet("body{stroke:#f5f5f5;stroke-width:40px}")]),
            ("zero-height container", [sheet(".diagram-container{height:0;overflow:hidden}")]),
            ("1px svg", [sheet("svg{width:1px;min-width:0}")]),
            ("frame off screen", [sheet(".frame{position:absolute;left:-99999px}")]),
            ("comment before transform", [sheet(".frame{/**/transform:scaleX(-1)}")]),
            ("webkit transform", [sheet(".frame{-webkit-transform:scaleX(-1)}")]),
            ("comment inside property", [sheet(".frame{tr/**/ansform:scaleX(-1)}")]),
            ("inline div transform", [(container, '<div class="diagram-container" style="/**/transform:scaleX(-1)">')]),
            ("inline div webkit transform", [(container, '<div class="diagram-container" style="-webkit-transform:scaleX(-1)">')]),
            ("data stylesheet link", [("</head>", '<link rel="stylesheet" href="data:text/css,rect%7Bfill:none%7D"></head>')]),
            ("@import", [sheet('@import "data:text/css,rect%7Bfill:none%7D";')]),
            ("HTML hidden", [(container, '<div class="diagram-container" hidden>')]),
            ("rail fill none", [('fill="rgba(45,49,66,0.05)" data-role="rail" data-step="frame"', 'fill="none" data-role="rail" data-step="frame"')]),
            ("rail fill-opacity 0", [(rail, f'fill-opacity="0" {rail}')]),
            ("rail systemLanguage", [(rail, f'systemLanguage="zz" {rail}')]),
            ("number font-size 0", [(n1, n1.replace("<text ", '<text font-size="0" '))]),
            ("number in paper", [(n1, n1.replace('fill="#4f5d75"', 'fill="#f5f5f5"'))]),
            ("number off canvas", [(n1, n1.replace('y="164"', 'y="-500"'))]),
            ("numbers swapped by dx", [(n1, n1.replace('x="192"', 'x="192" dx="896"')), (n5, n5.replace('x="1088"', 'x="1088" dx="-896"'))]),
            ("numbers swapped by duplicate x", [(n1, n1.replace('x="192"', 'x="1088" x="192"')), (n5, n5.replace('x="1088"', 'x="192" x="1088"'))]),
            ("number bidi override", [(n1, n1.replace("<text ", '<text direction="rtl" unicode-bidi="bidi-override" '))]),
            ("number hidden tspan", [(n1, n1.replace(">01<", '>0<tspan visibility="hidden">1</tspan><'))]),
            ("number tspan dx", [(n1, n1.replace(">01<", '>0<tspan dx="-14">1</tspan><'))]),
            ("number textLength", [(n1, n1.replace("<text ", '<text textLength="0.5" lengthAdjust="spacingAndGlyphs" '))]),
            ("rails in a comment", list(wrapped(rail_group, rail_end, "<!-- ", "-->"))),
            ("rails in defs", list(wrapped(rail_group, rail_end, "<defs>", "</defs>"))),
            ("rails in a nested svg", list(wrapped(rail_group, rail_end, '<svg x="0" y="5000">', "</svg>"))),
            ("universal svg fill", [sheet("svg *{fill:none}")]),
            ("child group stroke", [sheet("svg > g{stroke:#f5f5f5;stroke-width:60}")]),
            (":has fill", [sheet("svg:has(rect){fill:none}")]),
            ("sibling universal fill", [sheet("svg ~ *{fill:none}")]),
            ("@media rect fill", [sheet("@media screen{svg rect{fill:none}}")]),
            ("@supports", [sheet("@supports (display:grid){rect{fill:none}}")]),
            ("@layer", [sheet("@layer a{rect{fill:none}}")]),
            ("uppercase", [sheet("RECT{FILL:none}")]),
            ("escaped selector", [sheet("r\\65 ct{fill:none}")]),
            ("comment inside fill", [sheet("rect{fi/**/ll:none}")]),
            ("@keyframes", [sheet("@keyframes k{to{opacity:0}}")]),
        )
        for index, (name, edits) in enumerate(rendered_cases, 300):
            mutated = source
            for old, new in edits:
                if mutated.count(old) < 1:
                    failures.append(f"fixture {name!r} anchor is missing")
                    break
                mutated = mutated.replace(old, new, 1)
            path = directory / f"bad-{index}.html"
            path.write_text(mutated, encoding="utf-8")
            code, output = run(path)
            if code == 0:
                failures.append(f"{name}: rendered mutation was not rejected\n{output}")
            else:
                print(f"OK: {name} rejected")
        allowed_cases = (
            ("quoted custom property", *sheet(':root{--n:"transform:translate(9px)"}')),
            ("page-only class rule", *sheet(".note{width:10px;display:grid}")),
            ("page attribute selector", *sheet('.card[data-tone="warm"]{background:#fff}')),
            ("page structural pseudo-class", *sheet("li:nth-child(2){color:red}")),
            ("page pseudo-element", *sheet('h1::after{content:"x"}')),
            ("@font-face", *sheet("@font-face{font-family:X;src:url(x.woff2)}")),
            ("responsive svg", *sheet("svg{max-width:100%;height:auto}")),
            ("reduced motion", *sheet("@media (prefers-reduced-motion:reduce){*{animation:none}}")),
            ("medallion 1px outline", 'stroke="#2d3142" data-role="medallion" data-step="frame"', 'stroke="#2d3142" stroke-width="1" data-role="medallion" data-step="frame"'),
            ("rail ink with fill-opacity", 'fill="rgba(191,69,32,0.08)" data-role="rail"', 'fill="#bf4520" fill-opacity="0.08" data-role="rail"'),
            ("number typography on the text", n1, n1.replace("<text ", '<text font-size="8" font-weight="600" text-anchor="middle" font-family="\'Geist Mono\', monospace" ')),
            ("frame max-width in rem", ".frame { max-width:1280px;", ".frame { max-width:80rem;"),
        )
        full = (GOOD.parent / "example-steps-full.html").read_text(encoding="utf-8")
        card_text = "<p>One title and two lines per stage keep all five stages readable at a glance.</p>"
        full_cases = (
            ("full page with a list", [(card_text, "<ul><li>One title</li><li><strong>Two</strong> lines</li></ul>")]),
            ("full page in main", [('<div class="container">', '<main class="container">'), ("</footer>\n  </div>", "</footer>\n  </main>")]),
        )
        for index, (name, edits) in enumerate(full_cases, 250):
            mutated = full
            for old, new in edits:
                if mutated.count(old) != 1:
                    failures.append(f"fixture {name!r} anchor occurs {mutated.count(old)} times")
                mutated = mutated.replace(old, new, 1)
            path = directory / f"good-{index}.html"
            path.write_text(mutated, encoding="utf-8")
            code, output = run(path)
            if code:
                failures.append(f"{name}: expected pass\n{output}")
            else:
                print(f"OK: {name} passes")
        for index, (name, old, new) in enumerate(allowed_cases, 200):
            path = directory / f"good-{index}.html"
            path.write_text(source.replace(old, new, 1), encoding="utf-8")
            code, output = run(path)
            if code:
                failures.append(f"{name}: expected pass\n{output}")
            else:
                print(f"OK: {name} passes")
    if failures:
        print("FAIL steps verifier tests")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All Steps verifier tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
