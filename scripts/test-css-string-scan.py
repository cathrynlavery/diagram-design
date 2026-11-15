#!/usr/bin/env python3
"""Quoted CSS data is not a geometry declaration, in every verifier that scans for one.

Fifteen verifiers refuse a CSS declaration that can move a verified mark. Each read
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

from css_property_scan import escaped_property_findings

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

TYPES = ("arc-diagram", "architecture-delta", "beeswarm", "box-plot", "bump", "bubble", "marimekko", "ridgeline",
         "service-blueprint", "polar", "steps", "streamgraph", "slopegraph", "unit-grid", "waterfall")

# The first element of each example that its verifier checks as a mark: (tag, attribute).
MARKS = {
    "arc-diagram": ("circle", "data-name"),
    "architecture-delta": ("rect", "width"),
    "beeswarm": ("circle", "data-value"),
    "box-plot": ("rect", "data-role"),
    "bump": ("path", "data-series"),
    "bubble": ("circle", "data-name"),
    "marimekko": ("rect", "data-segment"),
    "ridgeline": ("path", "data-ridge"),
    "service-blueprint": ("rect", "data-stage"),
    "polar": ("circle", "data-polar-ring"),
    "steps": ("rect", "data-role"),
    "streamgraph": ("path", "data-layer"),
    "slopegraph": ("line", "data-series"),
    "unit-grid": ("rect", "data-unit-cell"),
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
    # The browser reads a NUL as U+FFFD, a name character, so `\x00url(` is an ordinary function too.
    ("a quote after NUL url(", False, "head", 'rect { --a: \x00url(a"b); --x: "); transform: translate(9px); --z: "c" }'),
    # `/*` and `*/` inside a string or a url() open and close no comment, so a comment
    # remover must not join them across the live transform between.
    ("comment delimiters in selector strings", False, "head",
     ':not([data-x="/*"]) { transform: translate(9px) } [data-x="*/"] { --x: 1 }'),
    ("comment delimiters in single-quoted selector strings", False, "head",
     ":not([data-x='/*']) { transform: translate(9px) } [data-x='*/'] { --x: 1 }"),
    ("a comment opener in a selector, a closer in a declaration", False, "head",
     ':not([data-x="/*"]) { transform: translate(9px) } body { --x: "*/" }'),
    ("a comment opener in a declaration, a closer in a selector", False, "head",
     'rect { --x: "/*"; transform: translate(9px) } [data-x="*/"] { --y: 1 }'),
    ("comment delimiters in url()", False, "head",
     'rect { --a: url(/*); transform: translate(9px); --b: url(*/) }'),
    ("comment delimiters in selector strings beside an escape", False, "head",
     ':not([data-x="/*"]) { transform: translate(9px) } [data-x="*/"] { --x: 1 } .a\\62 { --y: 1 }'),
    ("comment delimiters in selector strings beside a character reference", False, "head",
     '/* &amp; */ :not([data-x="/*"]) { transform: translate(9px) } [data-x="*/"] { --x: 1 }'),
    # A string that never closes ends at its line, and a `/*` in it opens no comment.
    ("a comment opener in an unterminated string", False, "head",
     'rect { --a: "/*\n; transform: translate(9px) } /* c */'),
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


# A quoted attribute selector selects what the bare one does, so it must be read the same:
# a checker that gates a size declaration on its selector cannot lose the selector to string
# blanking. `{a}` is the mark attribute; each rule is held to the result of the bare form.
SELECTOR_RULES = (
    ("a double-quoted attribute selector", '[{a}="v"] {{ width: 1px; height: 1px }}'),
    ("a single-quoted attribute selector", "[{a}='v'] {{ width: 1px; height: 1px }}"),
    ("a quoted attribute selector in @media", '@media screen {{ [{a}="v"] {{ width: 1px; height: 1px }} }}'),
    ("a quoted selector after quoted data", 'body {{ --n: "x" }} [{a}="v"] {{ width: 1px; height: 1px }}'),
)
BARE_RULE = "[{a}] {{ width: 1px; height: 1px }}"

# Marimekko gates width and height on whether the selector can reach a segment rect.
MARIMEKKO_SELECTOR_CASES = tuple(
    (f"[data-segment={quote}Linux{quote}] {{ {declaration} }}")
    for quote in "\"'"
    for declaration in ("width: 1px", "height: 1px", "x: 1px", "y: 1px", "transform: translate(1px)")
)


# Rules each checker refuses outside its geometry scan: a hidden, repainted or resized mark,
# a loaded stylesheet. Wrapped in strings holding `/*` and `*/` - in selectors or in
# declarations - each must fail as it does bare, so no comment remover joins the two.
GUARDED_RULES = {
    "arc-diagram": ("circle { display: none }", "circle { fill: red }"),
    "architecture-delta": ("rect { display: none }", "rect { width: 1px; height: 1px }"),
    # Box plot matches attribute values: a quoted value must reach the boxes as written.
    "box-plot": ("rect { display: none }", 'rect[fill="rgba(245,245,245,0.14)"] { display: none }',
                 "rect[fill='rgba(245,245,245,0.14)'] { display: none }"),
    "polar": ("body { display: none }", "body { background: url(x.png) }"),
    "service-blueprint": ("rect { width: 1px; height: 1px }",),
}
WRAPPERS = (
    ("between selector strings", 'body[data-q="/*"] {{ --z: 1 }} {rule} html[data-q="*/"] {{ --z: 1 }}'),
    ("between declaration strings", 'body {{ --q: "/*" }} {rule} html {{ --q: "*/" }}'),
)

def run_check(kind: str, page: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / f"scripts/verify-{kind}.py"), str(page)],
        capture_output=True, text=True, check=False,
    )


def passes_check(kind: str, page: Path) -> bool:
    return run_check(kind, page).returncode == 0


# Issue #518 item 2: these verifiers used to accept a browser-active escaped
# property. Escape spelling is unsupported, independently of the decoded name.
ESCAPED_PROPERTY_TYPES = tuple(kind for kind in TYPES
                               if kind not in ("architecture-delta", "polar", "steps", "unit-grid"))
ESCAPED_DECLARATIONS = (
    ("hex escape", False, r"tr\61nsform: translate(9px)"),
    ("leading escape", False, r"\74ransform: translate(9px)"),
    ("six-digit escape", False, r"tr\000061nsform: translate(9px)"),
    ("space-terminated escape", False, r"tr\61 nsform: translate(9px)"),
    ("tab-terminated escape", False, "tr\\61\tnsform: translate(9px)"),
    ("CRLF-terminated escape", False, "tr\\61\r\nnsform: translate(9px)"),
    ("simple escape", False, r"t\ransform: translate(9px)"),
    ("multiple escapes", False, r"\74 r\61 nsform: translate(9px)"),
    ("mixed-case escape", False, r"TR\41 NSFORM: translate(9px)"),
    ("prefixed property", False, r"-webkit-tr\61nsform: translate(9px)"),
    ("comment before colon", False, r"tr\61nsform/**/: translate(9px)"),
    ("comments around declaration", False, r"/*before*/ tr\61nsform: translate(9px) /*after*/"),
    ("escaped hiding property", False, r"displ\61y: none"),
    ("escaped size property", False, r"\77 idth: 1px"),
    ("ordinary escaped property is unsupported", False, r"c\6flor: red"),
    ("escaped custom property is unsupported", False, r"--n\6fte: 1"),
    ("escaped custom prefix with block data", False, r"\2d -notes: { data: 1; }"),
    ("quoted escape data", True, r"--notes: 'tr\61nsform: translate(9px)'"),
    ("unquoted escape data", True, r"--notes: tr\61nsform"),
    ("escape in a comment", True, r"/* tr\61nsform: translate(9px) */ --notes: 1"),
    ("escape in a URL", True, r"--notes: url(tr\61nsform:9px)"),
    ("escape in an escaped URL function", True, r"--notes: u\72 l(tr\61nsform:9px)"),
    ("escaped punctuation in data", True, r"--notes: \;tr\61nsform\:9px"),
    ("escaped declaration in custom block data", True, r"--notes: { tr\61nsform: 9px; }"),
)



def check_property_contexts() -> list[str]:
    # Browser text parsing differs between HTML raw-text styles and SVG foreign
    # content, including SVG's HTML integration points. CDATA is SVG-only.
    cases = (
        ("HTML self-closing style flag is ignored", True,
         r"<style/>* { tr\61nsform: translate(9px) }</style>"),
        ("HTML raw-text entities stay literal", False,
         r"<style>* { tr&#92;61nsform: translate(9px) }</style>"),
        ("SVG style entities decode once", True,
         r"<svg><style>* { tr&#92;61nsform: translate(9px) }</style></svg>"),
        ("SVG CDATA entities stay literal", False,
         r"<svg><style><![CDATA[* { tr&#92;61nsform: translate(9px) }]]></style></svg>"),
        ("SVG CDATA declarations are live", True,
         r"<svg><style><![CDATA[* { tr\61nsform: translate(9px) }]]></style></svg>"),
        ("SVG markup comments do not start CSS comments", True,
         r"<svg><style><!-- /* -->* { tr\61nsform: translate(9px) }<!-- */ --></style></svg>"),
        ("HTML integration point entities stay literal", False,
         r"<svg><foreignObject><style>* { tr&#92;61nsform: translate(9px) }</style></foreignObject></svg>"),
        ("HTML integration point quote references are raw", True,
         r"<svg><foreignObject><style>* { --a: &#39; tr\61nsform:translate(9px); --x:&#39; }</style></foreignObject></svg>"),
        ("HTML integration point quoted data stays quoted", False,
         r'<svg><foreignObject><style>* { --notes: "&quot;;tr\61nsform:9px"; }</style></foreignObject></svg>'),
        ("SVG desc is an HTML integration point", False,
         r"<svg><desc><style>* { tr&#92;61nsform: translate(9px) }</style></desc></svg>"),
        ("SVG title is an HTML integration point", False,
         r"<svg><title><style>* { tr&#92;61nsform: translate(9px) }</style></title></svg>"),
        ("a nested SVG re-enters foreign content", True,
         r"<svg><foreignObject><svg><style>* { tr&#92;61nsform: translate(9px) }</style></svg></foreignObject></svg>"),
        ("inline references decode once", False,
         r'<svg><circle style="tr&amp;#92;61nsform:translate(9px)"/></svg>'),
        ("the first duplicate style attribute wins", False,
         r'<svg><circle style="--notes:1" style="tr\61nsform:translate(9px)"/></svg>'),
        ("HTML breakout changes style text parsing", True,
         r"<svg><p><style>* { --a: &#39; tr\61nsform:translate(9px); --x:&#39; }</style></p></svg>"),
        ("a foreign p end tag also breaks out", True,
         r"<svg></p><style>* { --a: &#39; tr\61nsform:translate(9px); --x:&#39; }</style></svg>"),
        ("a font with presentation attributes breaks out", True,
         r"<svg><font color='red'><style>* { --a: &#39; tr\61nsform:translate(9px); --x:&#39; }</style></font></svg>"),
        ("EOF backslash in double-quoted data stays in the string", False,
         '<style>* { --notes: "ignored;tr\\61nsform:translate(9px)' + chr(92) + '</style>'),
        ("EOF backslash in single-quoted data stays in the string", False,
         "<style>* { --notes: 'ignored;tr\\61nsform:translate(9px)" + chr(92) + '</style>'),
        ("an unterminated style still applies", True,
         r"<style>* { tr\61nsform: translate(9px) }"),
    )
    return [f"CSS property context: {label}"
            for label, expected, source in cases
            if bool(escaped_property_findings(source)) != expected]

def check_escaped_properties(scratch: str) -> list[str]:
    failures = []
    for kind in ESCAPED_PROPERTY_TYPES:
        example = sorted(ASSET_DIR.glob(f"example-{kind}*.html"))[0]
        source = example.read_text(encoding="utf-8")
        page = Path(scratch) / f"{kind}-escaped.html"
        for label, passes, declaration in ESCAPED_DECLARATIONS:
            for where in ("head", "svg", "inline"):
                css = declaration if where == "inline" else "* { " + declaration + " }"
                page.write_text(place(source, kind, where, css), encoding="utf-8")
                # Box plot already refuses unquoted inline escapes, independently
                # of property position. Preserve that stronger existing contract.
                expected = passes and not (kind == "box-plot" and where == "inline"
                    and label in ("unquoted escape data", "escape in a comment",
                                  "escape in an escaped URL function", "escaped punctuation in data",
                                  "escaped declaration in custom block data"))
                result = run_check(kind, page)
                if (result.returncode == 0) != expected:
                    failures.append(f"{kind}: {label} ({where}) should {'pass' if expected else 'fail'}")
                elif not passes and "escaped CSS property names are unsupported" not in result.stdout:
                    failures.append(f"{kind}: {label} ({where}) missed the escaped-property diagnostic")
        for label, passes, where, css in (
            ("nested escaped property", False, "head", r"@media screen { * { tr\61nsform: translate(9px) } }"),
            ("escaped property in a nested rule", False, "head", r"* { &:hover { tr\61nsform: translate(9px) } }"),
            ("escaped property after an unquoted URL", False, "head", r"* { --a: url(a'b); tr\61nsform: translate(9px); --b: 'x' }"),
            ("escaped property in SVG CDATA", False, "svg", r"<![CDATA[* { tr\61nsform: translate(9px) }]]>"),
            ("SVG markup comments around CSS comments", False, "svg", r"<!-- /* -->* { tr\61nsform: translate(9px) }<!-- */ -->"),
            ("SVG CDATA references stay literal", True, "svg", r"<![CDATA[* { tr&#92;61nsform: translate(9px) }]]>"),
            ("a quoted escaped property in SVG CDATA", True, "svg", r"<![CDATA[* { --notes: 'tr\61nsform:9px' }]]>"),
            ("escaped selector", True, "head", r".esc\61ped { --notes: 1 }"),
            ("escaped pseudo-class selector", True, "head", r"\62 ody:hover { --notes: 1 }"),
            ("escaped string in selector", True, "head", r"body[data-note='tr\61nsform:9px'] { --notes: 1 }"),
            ("raw character reference in head", True, "head", r"* { tr&#92;61nsform: translate(9px) }"),
            ("decoded escape in SVG", False, "svg", r"* { tr&#92;61nsform: translate(9px) }"),
            ("decoded escape inline", False, "inline", r"tr&#92;61nsform: translate(9px)"),
        ):
            page.write_text(place(source, kind, where, css), encoding="utf-8")
            # Box plot already rejects any escaped selector.
            expected = passes and not (kind == "box-plot" and label in
                ("escaped selector", "escaped pseudo-class selector", "escaped string in selector"))
            result = run_check(kind, page)
            if (result.returncode == 0) != expected:
                failures.append(f"{kind}: {label} should {'pass' if expected else 'fail'}")
            elif not passes and "escaped CSS property names are unsupported" not in result.stdout:
                failures.append(f"{kind}: {label} missed the escaped-property diagnostic")
    return failures


def main() -> int:
    failures: list[str] = check_property_contexts()
    with tempfile.TemporaryDirectory() as scratch:
        failures.extend(check_escaped_properties(scratch))
        for kind in TYPES:
            example = sorted(ASSET_DIR.glob(f"example-{kind}*.html"))[0]
            source = example.read_text(encoding="utf-8")
            for number, (label, passes, where, css) in enumerate(CASES):
                # Polar and steps refuse any inline style or <svg> stylesheet in the chart,
                # and unit grid any inline style on a cell.
                passes = passes and not (kind in ("polar", "steps") and where != "head")
                passes = passes and not (kind == "unit-grid" and where == "inline")
                page = Path(scratch) / f"{kind}-{number}.html"
                page.write_text(place(source, kind, where, css), encoding="utf-8")
                if passes_check(kind, page) != passes:
                    failures.append(f"{kind}: {label} should {'pass' if passes else 'fail'}")
            attribute = MARKS[kind][1]
            page = Path(scratch) / f"{kind}-bare.html"
            page.write_text(place(source, kind, "head", BARE_RULE.format(a=attribute)), encoding="utf-8")
            bare = passes_check(kind, page)
            for number, (label, rule) in enumerate(SELECTOR_RULES):
                page = Path(scratch) / f"{kind}-selector-{number}.html"
                page.write_text(place(source, kind, "head", rule.format(a=attribute)), encoding="utf-8")
                if passes_check(kind, page) != bare:
                    failures.append(f"{kind}: {label} should {'pass' if bare else 'fail'} like [{attribute}]")
        for kind, rules in GUARDED_RULES.items():
            source = sorted(ASSET_DIR.glob(f"example-{kind}*.html"))[0].read_text(encoding="utf-8")
            for number, rule in enumerate(rules):
                for label, wrapper in (("bare", "{rule}"), *WRAPPERS):
                    page = Path(scratch) / f"{kind}-guarded-{number}.html"
                    page.write_text(place(source, kind, "head", wrapper.format(rule=rule)), encoding="utf-8")
                    if passes_check(kind, page):
                        failures.append(f"{kind}: {rule} ({label}) should fail")
        source = sorted(ASSET_DIR.glob("example-marimekko*.html"))[0].read_text(encoding="utf-8")
        for number, rule in enumerate(MARIMEKKO_SELECTOR_CASES):
            page = Path(scratch) / f"marimekko-segment-{number}.html"
            page.write_text(place(source, "marimekko", "head", rule), encoding="utf-8")
            if passes_check("marimekko", page):
                failures.append(f"marimekko: {rule} should fail")
    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        return 1
    print(f"OK CSS string scan: {len(TYPES)} verifier(s), {len(CASES)} case(s) and "
          f"{len(SELECTOR_RULES)} quoted-selector rule(s) each, {len(MARIMEKKO_SELECTOR_CASES)} "
          f"marimekko segment selector(s), {sum(map(len, GUARDED_RULES.values()))} guarded rule(s) "
          f"behind comment delimiters, escaped property checks across {len(ESCAPED_PROPERTY_TYPES)} verifiers, both polarities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
