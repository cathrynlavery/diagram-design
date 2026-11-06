#!/usr/bin/env python3
"""Quoted CSS data is not a geometry declaration, in every verifier that scans for one.

Twelve verifiers refuse a CSS declaration that can move a verified mark. Each read
`body { --notes: "literal;transform:translate(999px)" }` as a `transform`
declaration, although the browser reads a quoted string that moves nothing (#431).

Both polarities, on a shipped example of each type: quoted data passes, and a live
declaration still fails when a quote, a comment, an escape, a url() or a character
reference stands near it in a way that could make a careless string reader skip it.
Each case goes into the first <style>, into a <style> of its own inside the <svg>
(where the HTML parser decodes character references) or into the inline style of a
verified mark.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

TYPES = ("architecture-delta", "beeswarm", "box-plot", "bump", "bubble", "marimekko", "ridgeline",
         "service-blueprint", "polar", "streamgraph", "slopegraph", "waterfall")

# The first element of each example that its verifier checks as a mark: (tag, attribute).
MARKS = {
    "architecture-delta": ("rect", "width"),
    "beeswarm": ("circle", "data-value"),
    "box-plot": ("rect", "data-role"),
    "bump": ("path", "data-series"),
    "bubble": ("circle", "data-name"),
    "marimekko": ("rect", "data-segment"),
    "ridgeline": ("path", "data-ridge"),
    "service-blueprint": ("rect", "data-stage"),
    "polar": ("circle", "data-polar-ring"),
    "streamgraph": ("path", "data-layer"),
    "slopegraph": ("line", "data-series"),
    "waterfall": ("rect", "data-role"),
}

# (label, passes, where, CSS): `head` adds it at the top of the first <style>, `svg`
# in a <style> right after the opening <svg> tag, `inline` as the style of a mark.
CASES = (
    ("double-quoted data", True, "head", 'body { --notes: "literal;transform:translate(999px)" }'),
    ("single-quoted data", True, "head", "body { --notes: 'literal;transform:translate(999px)' }"),
    ("a live transform", False, "head", "rect { transform: translate(999px) }"),
    ("a live transform after a string", False, "head", 'body { --a: "x" } rect { transform: translate(999px) }'),
    # The string holds `/*`: a reader that strips comments first hides the transform.
    ("a comment opener inside a string", False, "head", 'rect { --a: "/*"; transform: translate(9px); --b: "*/" }'),
    ("a quote inside a comment", False, "head", '/* " */ rect { transform: translate(9px) } /* " */'),
    # `\"` is an escaped character, not the start of a string.
    ("an escaped quote", False, "head", 'rect { --a: \\"; transform: translate(9px); --b: "x" }'),
    # A quote in an unquoted url() does not open a string either.
    ("a quote in an unquoted url()", False, "head", 'rect { background: url(a"b); transform: translate(9px); --x: "c" }'),
    # An escaped `)` does not end the url(), so the quote after it is still inside it.
    ("a quote after an escaped paren in url()", False, "head",
     'rect { background: url(a\\)"b); transform: translate(9px); --x: "c" }'),
    # Whitespace before a quote still makes a quoted url(), so the quote opens a string...
    ("whitespace before a quoted url()", False, "head",
     'rect { background: url( "a)" ); transform: translate(9px); --y: "z" }'),
    # ...but a no-break space is not CSS whitespace: the url() is unquoted and ends at `)`.
    ("a no-break space before a quote in url()", False, "head",
     'rect { background: url( "a); transform: translate(9px); --x: "c" }'),
    # `u\72 l(` is `url(` to the browser, so the quote sits inside an unquoted url().
    ("an escaped url name", False, "head", 'rect { background: u\\72 l(a"b); transform: translate(9px); --x: "c" }'),
    # A `url(` that ends a longer name is an ordinary function: the quote in it opens a string.
    ("a quote in a function whose name ends in url", False, "head",
     'rect { --a: myurl(a"b); --x: "); transform: translate(9px); --z: "c" }'),
    # `#url(` is a hash token and `@url(` an at-keyword, so the `(` opens a plain block and the
    # quote in it opens a string, as it does after a longer name.
    ("a quote after #url(", False, "head", 'rect { --a: #url(a"b); --x: "); transform: translate(9px); --z: "c" }'),
    ("a quote after @url(", False, "head", 'rect { --a: @url(a"b); --x: "); transform: translate(9px); --z: "c" }'),
    # A form feed ends a string just as a line feed does.
    ("a form feed inside a string", False, "head", 'rect { --a: "\f;transform:translate(9px);--b:" }'),
    # A string ends at its line: the next rule is live.
    ("an unterminated string", False, "head", 'body { --a: "x;\n} rect { transform: translate(9px) } body { --b: "y" }'),
    ("quoted data in an <svg> stylesheet", True, "svg", 'body { --notes: "literal;transform:translate(999px)" }'),
    # Inside <svg> the parser decodes `&#92;` to `\` and `&#39;` to `'` before CSS reads them.
    ("&#92; before a quote in an <svg> stylesheet", False, "svg", 'rect{--a:&#92;"; transform:translate(9px); --b:"x"}'),
    ("&#39; around a quote in an <svg> stylesheet", False, "svg",
     'rect{--a:&#39;"&#39;; transform:translate(9px); --b:"x"}'),
    ("quoted data inline", True, "inline", "--notes: 'literal;transform:translate(999px)'"),
    ("a live transform inline", False, "inline", "transform: translate(9px)"),
    # Attribute values are always decoded.
    ("&#92; before a quote inline", False, "inline", "--a:&#92;'; transform:translate(9px); --b:'x'"),
)


def place(source: str, kind: str, where: str, css: str) -> str:
    if where == "head":
        return re.sub(r"(<style[^>]*>)", lambda found: found.group(1) + "\n" + css + "\n", source, count=1)
    svg = source.index("<svg")
    if where == "svg":
        at = source.index(">", svg) + 1
        return source[:at] + "<style>" + css + "</style>" + source[at:]
    tag, attribute = MARKS[kind]
    at = re.compile(rf"<{tag}\b(?=[^>]*\s{attribute}[=\s>])").search(source, svg).end()
    return source[:at] + f' style="{css}"' + source[at:]


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as scratch:
        for kind in TYPES:
            example = sorted(ASSET_DIR.glob(f"example-{kind}*.html"))[0]
            source = example.read_text(encoding="utf-8")
            for number, (label, passes, where, css) in enumerate(CASES):
                # Polar refuses any inline style or <svg> stylesheet in its chart.
                passes = passes and not (kind == "polar" and where != "head")
                page = Path(scratch) / f"{kind}-{number}.html"
                page.write_text(place(source, kind, where, css), encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, str(ROOT / f"scripts/verify-{kind}.py"), str(page)],
                    capture_output=True, text=True, check=False,
                )
                if (result.returncode == 0) != passes:
                    failures.append(f"{kind}: {label} should {'pass' if passes else 'fail'}")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"OK CSS string scan: {len(TYPES)} verifier(s), {len(CASES)} case(s) each, both polarities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
