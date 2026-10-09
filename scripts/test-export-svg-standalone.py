#!/usr/bin/env python3
"""Regression tests for standalone SVG export (CSS carry + defs ID namespace).

Covers the packaged helper at skills/diagram-design/scripts/export_svg.py and
the contract documented in references/export.md (issues #202 and #203).
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "skills/diagram-design/scripts/export_svg.py"
EXPORT_MD = ROOT / "skills/diagram-design/references/export.md"
ASSETS = ROOT / "skills/diagram-design/assets"

# Shipped assets the helper refuses (loudly) because their markup is not
# well-formed XML for reasons outside the CSS carry: the first `</svg>` match
# stops at a nested icon <svg>, or a comment contains `--`. Keep this list
# exact so a newly unexportable asset, or a fixed one, shows up here.
KNOWN_UNEXPORTABLE = frozenset(
    {
        # nested icon <svg> truncates the first-</svg> extraction
        "example-datalake.html",
        "example-datalake-dark.html",
        "example-datalake-full.html",
        "example-high-level.html",
        "example-high-level-dark.html",
        "example-high-level-full.html",
        "example-high-level-vertical.html",
        "example-high-level-vertical-dark.html",
        "example-high-level-vertical-full.html",
        # `--` inside an XML comment
        "example-slopegraph.html",
        "example-slopegraph-dark.html",
        "example-slopegraph-full.html",
        "example-streamgraph.html",
        "example-streamgraph-dark.html",
        "example-streamgraph-full.html",
    }
)

# Motion files named in #202; they use valueless HTML attributes.
MOTION_FILES = (
    "template-motion.html",
    "example-policy-trace-animated.html",
    "example-queue-animated.html",
)

PAGE_STYLE_RE = re.compile(r"<style\b[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)


def exportable_assets() -> list[Path]:
    return sorted(
        path
        for path in ASSETS.glob("*.html")
        if path.name not in {"index.html", "icons.html"}
        and path.name not in KNOWN_UNEXPORTABLE
    )


def embedded_css(svg: str) -> str:
    match = re.search(r"<style>(.*?)</style>", svg, re.DOTALL)
    return match.group(1) if match else ""


def load_helper():
    spec = importlib.util.spec_from_file_location("diagram_design_export_svg", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {HELPER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExportSvgStandaloneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = load_helper()

    def test_color_normalization_preserves_non_attribute_content(self) -> None:
        literal = 'fill="rgba(45,49,66,0.1)"'
        markup = f'<svg><!-- {literal} --><text>{literal}</text><rect data-{literal} fill="rgba(45,49,66,0.1)"/></svg>'
        normalized = self.mod.normalize_rgba_presentation_attrs(markup)
        self.assertIn(f'<!-- {literal} -->', normalized)
        self.assertIn(f'<text>{literal}</text>', normalized)
        self.assertIn(f'data-{literal}', normalized)
        root = ET.fromstring(normalized)
        self.assertEqual(root[1].get("fill"), "#2d3142")
        self.assertEqual(root[1].get("fill-opacity"), "0.1")

    def test_single_quoted_presentation_colors_are_normalized(self) -> None:
        markup = "<svg><rect fill='rgba(45, 49, 66, .10)' stroke='transparent'/></svg>"
        normalized = self.mod.normalize_rgba_presentation_attrs(markup)
        root = ET.fromstring(normalized)
        self.assertEqual(root[0].get("fill"), "#2d3142")
        self.assertEqual(root[0].get("fill-opacity"), ".10")
        self.assertEqual(root[0].get("stroke"), "none")
        self.assertNotIn("rgba(", normalized)

    def test_single_quoted_color_normalization_preserves_non_attributes(self) -> None:
        markup = "<svg><!-- fill='rgba(1,2,3,.5)' --><text>stroke='transparent'</text><rect data-fill='rgba(1,2,3,.5)' fill = 'rgba(1,2,3,.5)'/></svg>"
        normalized = self.mod.normalize_rgba_presentation_attrs(markup)
        root = ET.fromstring(normalized)
        self.assertEqual(root[0].text, "stroke='transparent'")
        self.assertEqual(root[1].get("data-fill"), "rgba(1,2,3,.5)")
        self.assertEqual(root[1].get("fill"), "#010203")
        self.assertEqual(root[1].get("fill-opacity"), ".5")
        self.assertIn("<!-- fill='rgba(1,2,3,.5)' -->", normalized)

    def test_manual_paint_recipe_matches_helper(self) -> None:
        section = EXPORT_MD.read_text(encoding="utf-8").split("7. Normalize colors", 1)[1]
        match = re.search(r"```python\n(.*?)\n   ```", section, re.DOTALL)
        self.assertIsNotNone(match)
        recipe = "\n".join(line[3:] if line.startswith("   ") else line for line in match.group(1).splitlines())
        for svg in (
            "<svg><rect fill = 'rgba(1,2,3,.5)' stroke='transparent'/></svg>",
            "<svg><text>stroke='transparent'</text><rect data-fill='rgba(1,2,3,.5)'/></svg>",
            '<svg><!-- fill="rgba(1,2,3,.5)" --><rect fill="rgba(1,2,3,.5)"/></svg>',
        ):
            with self.subTest(svg=svg):
                namespace = {"svg": svg}
                exec(recipe, namespace)
                self.assertEqual(namespace["svg"], self.mod.normalize_rgba_presentation_attrs(svg))

    def test_helper_and_docs_exist(self) -> None:
        self.assertTrue(HELPER.is_file())
        self.assertTrue(EXPORT_MD.is_file())

    def test_export_md_documents_helper_css_and_defs(self) -> None:
        text = EXPORT_MD.read_text(encoding="utf-8")
        self.assertIn("scripts/export_svg.py", text)
        self.assertIn("Carry page CSS into the SVG", text)
        self.assertIn("Namespace `<defs>` IDs", text)
        self.assertIn("longest-id-first", text)
        self.assertIn("class=", text)
        self.assertIn("black boxes", text)
        self.assertIn("fonts-only", text)
        self.assertIn("R&D", text)
        self.assertIn("accessible-name guarantee alone is not enough", text)
        self.assertIn("`svg .zone` becomes `#<slug>-root .zone`", text)
        self.assertIn("`stroke=\"currentColor\"` reads `color`", text)
        self.assertIn('`data-motion-item=""`', text)

    def test_loop_export_carries_scoped_css(self) -> None:
        source = ASSETS / "example-loop.html"
        html = source.read_text(encoding="utf-8")
        svg = self.mod.export_svg_document(html, source)
        self.assertTrue(svg.startswith("<?xml version="))
        self.assertIn('id="example-loop-root"', svg)
        self.assertIn("#example-loop-root .station", svg)
        self.assertIn("#example-loop-root .hub", svg)
        self.assertIn("--paper:", svg)
        # Page chrome must not leak into the fragment.
        self.assertNotIn("min-width:", svg)
        self.assertNotRegex(svg, r"#example-loop-root\s+body\b")
        self.assertNotRegex(svg, r"#example-loop-root\s+\.frame\b")
        self.assertNotRegex(svg, r"#example-loop-root\s+\.eyebrow\b")
        self.assertIn("class=\"station\"", svg)
        self.assertIn("<style>", svg)

    def test_loop_export_namespaces_defs_ids_longest_first(self) -> None:
        source = ASSETS / "example-loop.html"
        svg = self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
        self.assertIn('id="example-loop-arrow-accent"', svg)
        self.assertIn('id="example-loop-arrow"', svg)
        self.assertIn('id="example-loop-arrow-soft"', svg)
        # Loop references arrow / arrow-soft (accent is defined but unused).
        self.assertIn("url(#example-loop-arrow)", svg)
        self.assertIn("url(#example-loop-arrow-soft)", svg)
        self.assertIn('id="example-loop-dots"', svg)
        self.assertIn("url(#example-loop-dots)", svg)
        # Longest-first: accent id must not have been mangled by the arrow rewrite.
        self.assertNotIn('id="example-loop-example-loop-arrow-accent"', svg)
        # Bare shared IDs must be gone — otherwise inlining collides.
        self.assertIsNone(re.search(r'\bid="arrow"', svg))
        self.assertIsNone(re.search(r'\bid="arrow-accent"', svg))
        self.assertIsNone(re.search(r'\bid="dots"', svg))
        self.assertIsNone(re.search(r"url\(#arrow\)", svg))
        self.assertIsNone(re.search(r"url\(#dots\)", svg))

    def test_quoted_local_paint_urls_follow_namespaced_defs(self) -> None:
        references = (
            'url(#paint)', 'url("#paint")', "url('#paint')",
            'url(  "#paint"  )', 'url(&quot;#paint&quot;)', 'url(&apos;#paint&apos;)',
        )
        for reference in references:
            with self.subTest(reference=reference):
                markup = '<svg><defs><linearGradient id="paint"/></defs>'
                markup += '<rect style="fill: ' + reference.replace('"', '&quot;') + '"/>'
                markup += '<style>.node { fill: ' + reference + '; }</style></svg>'
                exported = self.mod.namespace_defs_ids(markup, "quoted")
                self.assertIn('id="quoted-paint"', exported)
                expected = reference.replace('#paint', '#quoted-paint').replace('  ', '')
                self.assertIn(expected, exported)
                self.assertIn(expected.replace('"', '&quot;'), exported)
                self.assertEqual(exported.count('#quoted-paint'), 2)
        untouched = '<svg><defs><linearGradient id="paint"/></defs>'
        untouched += '<rect fill="url(#paint-other)" stroke="url(other.svg#paint)"/></svg>'
        result = self.mod.namespace_defs_ids(untouched, "quoted")
        self.assertIn('url(#paint-other)', result)
        self.assertIn('url(other.svg#paint)', result)

    def test_light_and_dark_architecture_do_not_collide_when_inlined(self) -> None:
        light_src = ASSETS / "example-architecture.html"
        dark_src = ASSETS / "example-architecture-dark.html"
        light = self.mod.export_svg_document(light_src.read_text(encoding="utf-8"), light_src)
        dark = self.mod.export_svg_document(dark_src.read_text(encoding="utf-8"), dark_src)
        combined = light + "\n" + dark
        self.assertEqual(combined.count('id="example-architecture-arrow"'), 1)
        self.assertEqual(combined.count('id="example-architecture-dark-arrow"'), 1)
        self.assertIn("url(#example-architecture-arrow)", light)
        self.assertIn("url(#example-architecture-dark-arrow)", dark)
        # Distinct root scopes so token sheets do not overwrite each other.
        self.assertIn('id="example-architecture-root"', light)
        self.assertIn('id="example-architecture-dark-root"', dark)

    def test_class_without_style_gate(self) -> None:
        html = """<!DOCTYPE html><html><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <rect class="station" width="10" height="10"/>
        </svg></body></html>"""
        # No diagram rules: bare class SVG must be refused (fonts-only does not count).
        with self.assertRaises(ValueError) as ctx:
            self.mod.assert_export_gate(
                '<svg viewBox="0 0 1 1"><defs><style>@import url("x");</style></defs>'
                '<rect class="x" width="1" height="1"/></svg>'
            )
        self.assertIn("black boxes", str(ctx.exception))
        self.assertIn("diagram CSS", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx2:
            self.mod.export_svg_document(html, Path("orphan-station.html"))
        self.assertIn("black boxes", str(ctx2.exception))
        # With real diagram rules, the gate passes.
        ok = """<!DOCTYPE html><html><head><style>
        .station { fill: #f00; }
        </style></head><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <rect class="station" width="10" height="10"/>
        </svg></body></html>"""
        svg = self.mod.export_svg_document(ok, Path("styled-station.html"))
        self.assertIn("#styled-station-root .station", svg)
        self.assertTrue(self.mod.has_diagram_stylesheet(svg))

    def test_carried_css_escapes_xml_specials(self) -> None:
        html = """<!DOCTYPE html><html><head><style>
        .label::after { content: "R&D"; }
        .station { fill: #111; }
        </style></head><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <rect class="station" width="10" height="10"/>
          <text class="label">x</text>
        </svg></body></html>"""
        svg = self.mod.export_svg_document(html, Path("rd-label.html"))
        # Raw & would break XML; escaped form must appear in the stylesheet.
        self.assertIn('content: "R&amp;D"', svg)
        self.assertNotRegex(svg, r'content:\s*"R&D"')
        # Document must parse as XML (export already validates; assert explicitly).
        import xml.etree.ElementTree as ET
        ET.fromstring(svg)

    def test_quoted_urls_preserve_delimiters_and_exact_fragment_case(self) -> None:
        markup = '<svg><defs><linearGradient id="paint)"/></defs><style>.paint { fill:url("#paint)"); }</style></svg>'
        result = self.mod.namespace_defs_ids(markup, "quoted")
        self.assertIn('url("#quoted-paint)")', result)
        markup = '<svg><defs><linearGradient id="A"/><linearGradient id="a"/></defs>'
        markup += '<style>.paint { fill:URL("#a"); stroke:url("#A"); }</style><use HREF="#a"/></svg>'
        result = self.mod.namespace_defs_ids(markup, "quoted")
        self.assertIn('url("#quoted-a")', result)
        self.assertIn('url("#quoted-A")', result)
        self.assertIn('HREF="#quoted-a"', result)

    def test_root_selector_retarget_preserves_literals_and_escapes(self) -> None:
        selector = r"""#original .paint[data-label="#original"], [data-label='#original'], .\#original, #original-child, #original\:child, #originalé"""
        expected = r"""#export-root .paint[data-label="#original"], [data-label='#original'], .\#original, #original-child, #original\:child, #originalé"""
        self.assertEqual(self.mod.retarget_root_selector(selector, "original", "export-root"), expected)
        escaped_quote = r' .paint[data-label="escaped\"#original"] #original'
        self.assertEqual(self.mod.retarget_root_selector(escaped_quote, "original", "export-root"),
                         r' .paint[data-label="escaped\"#original"] #export-root')
        html = '<style>.paint[data-label="#original"] { fill:#00ff00 } #original .paint { stroke:#0000ff }</style>'
        html += '<svg id="original" viewBox="0 0 40 40"><rect class="paint" data-label="#original" width="40" height="40"/></svg>'
        svg = self.mod.export_svg_document(html, Path("literal.html"))
        self.assertIn('#literal-root .paint[data-label="#original"]', svg)
        self.assertIn('#literal-root .paint { stroke:#0000ff }', svg)

    def test_named_html_entities_retain_readable_text(self) -> None:
        html = '<svg viewBox="0 0 40 40"><title>R&nbsp;D &copy;</title><desc>&LT;literal&GT;</desc>'
        html += '<text data-label="&quot;A&nbsp;B&quot;">R&nbsp;D &amp;nbsp; &copy; &#160;</text></svg>'
        result = self.mod.export_svg_document(html, Path("entities.html"))
        root = ET.fromstring(result)
        text = root.find("{http://www.w3.org/2000/svg}text")
        self.assertEqual(text.text, "R\u00a0D &nbsp; © \u00a0")
        self.assertEqual(text.get("data-label"), '"A\u00a0B"')
        self.assertEqual(root.find("{http://www.w3.org/2000/svg}desc").text, "<literal>")
        opaque = '<!-- &nbsp; --><![CDATA[&nbsp;]]><style>.label {content:"&nbsp;"}</style>'
        self.assertEqual(self.mod.normalize_html_entities(opaque), opaque)
        self.assertEqual(self.mod.normalize_html_entities('&notARealEntity;'), '&notARealEntity;')

    def test_defs_reference_rewrite_leaves_visible_text_alone(self) -> None:
        markup = ('<svg><defs><linearGradient id="paint"/></defs>'
                  '<style>.a { fill:url("#paint") } .b { stroke:url(#paint) }</style>'
                  '<rect fill="url(#paint)"/><use href="#paint"/>'
                  '<text>Use url("#paint"), url(#paint) or href="#paint"</text>'
                  '<title>id="paint"</title><!-- url(#paint) --></svg>')
        result = self.mod.namespace_defs_ids(markup, "diagram")
        self.assertIn('<linearGradient id="diagram-paint"/>', result)
        self.assertIn('.a { fill:url("#diagram-paint") } .b { stroke:url(#diagram-paint) }', result)
        self.assertIn('<rect fill="url(#diagram-paint)"/><use href="#diagram-paint"/>', result)
        self.assertIn('<text>Use url("#paint"), url(#paint) or href="#paint"</text>', result)
        self.assertIn('<title>id="paint"</title>', result)
        # Comments are not visible text; a commented-out block stays consistent.
        self.assertIn('<!-- url(#diagram-paint) -->', result)

    def test_legacy_entities_without_semicolon_follow_html_contexts(self) -> None:
        html = '<svg viewBox="0 0 40 40"><title>Copyright &copy 2026</title>'
        html += '<text data-label="&copy 2026">A&nbsp B &amp C &lt D</text></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("legacy.html")))
        self.assertEqual(root.find("{http://www.w3.org/2000/svg}title").text, "Copyright \u00a9 2026")
        text = root.find("{http://www.w3.org/2000/svg}text")
        self.assertEqual(text.text, "A\u00a0 B & C < D")
        self.assertEqual(text.get("data-label"), "\u00a9 2026")
        # In attribute values HTML leaves a legacy name followed by an
        # alphanumeric or "=" undecoded; text content decodes the prefix.
        self.assertEqual(self.mod.normalize_html_entities('<a data-q="x&copy=1&notit">'),
                         '<a data-q="x&copy=1&notit">')
        self.assertEqual(self.mod.normalize_html_entities("<b>&notit</b>"), "<b>\u00acit</b>")

    def test_escaped_root_id_keeps_retargeted_styles(self) -> None:
        html = '<style>#a\\&b .paint { fill:#ff0000 }</style>'
        html += '<svg id="a&amp;b" viewBox="0 0 40 40"><rect class="paint" width="40" height="40"/></svg>'
        svg = self.mod.export_svg_document(html, Path("escaped.html"))
        self.assertIn("#escaped-root .paint { fill:#ff0000 }", svg)
        # A legacy name HTML leaves literal in an attribute stays literal here too.
        for source_id, css_id in (("x&copy2026", "x\\&copy2026"), ("n&#38;m", "n\\&m"),
                                  ("a&#128;b", "a\u20acb"), ("c&#x80;d", "c\u20acd"), ("e&#38f", "e\\&f")):
            html = f'<style>#{css_id} .paint {{ fill:#ff0000 }}</style>'
            html += f'<svg id="{source_id}" viewBox="0 0 40 40"><rect class="paint" width="40" height="40"/></svg>'
            svg = self.mod.export_svg_document(html, Path("literal-id.html"))
            self.assertIn("#literal-id-root .paint { fill:#ff0000 }", svg)

    def test_raw_text_opening_attributes_normalize_entities(self) -> None:
        for tag in ("style", "script"):
            raw = f'<{tag} title="Copyright &copy; > literal">raw &copy; content</{tag}>'
            expected = f'<{tag} title="Copyright © > literal">raw &copy; content</{tag}>'
            self.assertEqual(self.mod.normalize_html_entities(raw), expected)
        html = '<svg viewBox="0 0 10 10"><style title="Copyright &copy; > literal">.label {fill:red}</style><rect class="label" width="10" height="10"/></svg>'
        result = ET.fromstring(self.mod.export_svg_document(html, Path("style-attribute.html")))
        style = result.find("{http://www.w3.org/2000/svg}style")
        self.assertEqual(style.get("title"), "Copyright © > literal")
        self.assertEqual(style.text, ".label {fill:red}")

    def test_new_defs_preserve_leading_accessible_title(self) -> None:
        for asset in ("example-journey.html", "example-polar.html"):
            source = ASSETS / asset
            root = ET.fromstring(self.mod.export_svg_document(source.read_text(encoding="utf-8"), source))
            self.assertEqual(root[0].tag, "{http://www.w3.org/2000/svg}title")
            self.assertEqual(root[1].tag, "{http://www.w3.org/2000/svg}desc")
        html = '<svg viewBox="0 0 40 40"><!-- before title --><title><![CDATA[Literal </title> text]]></title>'
        html += '<desc>Keep description</desc><rect width="40" height="40"/></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("title.html")))
        self.assertEqual(root[0].text, "Literal </title> text")
        self.assertEqual(root[1].text, "Keep description")
        self.assertEqual(root[2].tag, "{http://www.w3.org/2000/svg}defs")

    def test_cli_writes_default_path(self) -> None:
        source = ASSETS / "example-loop.html"
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "example-loop.html"
            staged.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            rc = self.mod.main([str(staged)])
            self.assertEqual(rc, 0)
            out = staged.with_suffix(".svg")
            self.assertTrue(out.is_file())
            body = out.read_text(encoding="utf-8")
            self.assertIn("#example-loop-root .station", body)

    def test_quoted_paint_with_xml_attribute_spacing(self) -> None:
        result = self.mod.normalize_rgba_presentation_attrs("<svg><rect fill = 'rgba(1,2,3,0.5)' stroke \n= 'transparent'/></svg>")
        self.assertIn('fill="#010203"', result)
        self.assertIn('fill-opacity="0.5"', result)
        self.assertIn('stroke="none"', result)

    def test_rgba_presentation_attrs_still_split(self) -> None:
        html = """<!DOCTYPE html><html><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <defs><pattern id="dots" width="2" height="2"
            patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.5" fill="rgba(45,49,66,0.10)"/>
          </pattern></defs>
          <rect width="10" height="10" fill="url(#dots)" stroke="transparent"/>
        </svg></body></html>"""
        svg = self.mod.export_svg_document(html, Path("rgba-demo.html"))
        self.assertIn('fill="#2d3142" fill-opacity="0.10"', svg)
        self.assertIn('stroke="none"', svg)
        self.assertIn('id="rgba-demo-dots"', svg)

    def test_compound_original_root_does_not_gain_an_ancestor(self) -> None:
        for selector in ('.diagram#original .paint',
                         'svg.diagram#original .paint',
                         '[data-mode="active"]#original.diagram .paint'):
            with self.subTest(selector=selector):
                source = '<style>' + selector + ' {fill:#ff0000}</style>'
                source += '<svg id="original" class="diagram" data-mode="active" viewBox="0 0 40 40">'
                source += '<rect class="paint" width="40" height="40"/></svg>'
                result = self.mod.export_svg_document(source, Path('compound.html'))
                expected = selector.replace('#original', '#compound-root')
                self.assertIn(expected + ' { fill:#ff0000 }', embedded_css(result))
                self.assertNotIn('#compound-root ' + expected, embedded_css(result))

    def test_hex_root_escape_retains_descendant_separator(self) -> None:
        source = r'<style>.paint {fill:#00ff00} #\31  .paint {fill:#ff0000}</style>'
        source += '<svg id="1" viewBox="0 0 40 40"><rect class="paint" width="40" height="40"/></svg>'
        result = self.mod.export_svg_document(source, Path('single-hex.html'))
        self.assertIn('#single-hex-root .paint { fill:#ff0000 }', embedded_css(result))
        self.assertNotIn('#single-hex-root.paint', embedded_css(result))

    def test_root_retarget_compares_whole_decoded_css_id_tokens(self) -> None:
        cases = (
            (r'#panel.v1 .paint', 'panel.v1', r'#panel.v1 .paint'),
            (r'#panel\.v1 .paint', 'panel.v1', '#export-root .paint'),
            (r'#panel\2e v1 .paint', 'panel.v1', '#export-root .paint'),
            (r'#panel\00002Ev1 .paint', 'panel.v1', '#export-root .paint'),
            (r'#panel\:v1 .paint', 'panel:v1', '#export-root .paint'),
            (r'#panel\.v1-child .paint', 'panel.v1', r'#panel\.v1-child .paint'),
            ('#123 .paint', '123', '#123 .paint'),
            (r'#\31 23 .paint', '123', '#export-root .paint'),
            (r'#\-123 .paint', '-123', '#export-root .paint'),
            ('#-123 .paint', '-123', '#-123 .paint'),
            ('#面板 .paint', '面板', '#export-root .paint'),
        )
        for selector, original, expected in cases:
            with self.subTest(selector=selector):
                self.assertEqual(self.mod.retarget_root_selector(selector, original, 'export-root'), expected)
        self.assertEqual(self.mod.scope_selector('.paint[data-label="#export-root"]', 'export-root'),
                         '#export-root .paint[data-label="#export-root"]')
        self.assertEqual(self.mod.scope_selector('.paint:is(#export-root)', 'export-root'),
                         '#export-root .paint:is(#export-root)')

    def test_original_svg_root_selectors_follow_replaced_id(self) -> None:
        for quote in ('"', "'"):
            with self.subTest(quote=quote):
                html = '<style>#original .paint {fill: #ff0000;} '
                html += '#original-child {stroke: #00ff00;}</style>'
                html += '<svg id=' + quote + 'original' + quote + ' viewBox="0 0 40 40">'
                html += '<rect id="original-child" class="paint" width="40" height="40"/></svg>'
                result = self.mod.export_svg_document(html, Path("renamed.html"))
                css = embedded_css(result)
                self.assertIn('#renamed-root .paint { fill: #ff0000; }', css)
                self.assertIn('#original-child { stroke: #00ff00; }', css)
                self.assertIn('id="original-child"', result)
                self.assertNotIn('#original .paint', css)
        # An unrelated attribute that contains the word id is not the root id.
        source = '<style>#original .paint {fill: #f00;}</style>'
        source += '<svg data-id="original" viewBox="0 0 10 10"><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(source, Path("data-id.html"))
        self.assertIn('#original .paint', embedded_css(result))
        self.assertIn('data-id="original"', result)
        self.assertEqual(ET.fromstring(result).get('id'), 'data-id-root')

    def test_root_tokens_bind_to_svg_root(self) -> None:
        # Without the :root re-scope the tokens land on `#root :root`, which
        # matches nothing, and every var(--token) fill falls back to black.
        source = ASSETS / "example-loop.html"
        css = embedded_css(self.mod.export_svg_document(source.read_text(encoding="utf-8"), source))
        self.assertRegex(css, r"#example-loop-root\s*\{[^}]*--paper\s*:")
        self.assertRegex(css, r"#example-loop-root\s*\{[^}]*--accent\s*:")
        self.assertNotIn(":root", css)
        # A comment in front of the rule (template-full.html) must not hide it.
        html = """<!DOCTYPE html><html><head><style>
        /* Tokens, light */
        :root { --node: #fff; }
        .node { fill: var(--node); }
        </style></head><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <rect class="node" width="1" height="1"/>
        </svg></body></html>"""
        css = embedded_css(self.mod.export_svg_document(html, Path("commented-tokens.html")))
        self.assertIn("#commented-tokens-root { --node: #fff; }", css)
        self.assertNotIn(":root", css)

    def test_svg_descendant_rules_are_kept_and_scoped_to_root(self) -> None:
        # `svg .zone` / `svg text` are diagram rules, not page chrome. The
        # exported root is the <svg> itself, so they must start at the root ID.
        cases = {
            "example-it-state.html": (
                "#example-it-state-root .zone {",
                "#example-it-state-root .node.focal {",
                "#example-it-state-root .zone-mask, #example-it-state-root .node-mask",
            ),
            "example-dp-security-matrix.html": (
                "#example-dp-security-matrix-root .component-head, "
                "#example-dp-security-matrix-root .component {",
                "#example-dp-security-matrix-root .cell {",
            ),
            "example-process.html": ("#example-process-root text {",),
            "example-state-lifecycle.html": ("#example-state-lifecycle-root text {",),
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                source = ASSETS / name
                slug = source.stem
                css = embedded_css(
                    self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
                )
                for rule in expected:
                    self.assertIn(rule, css)
                self.assertNotRegex(css, rf"#{slug}-root\s+svg\b")
                # The bare `svg {{ width; min-width }}` page-layout rule stays out.
                self.assertNotIn("min-width", css)
        html = """<!DOCTYPE html><html><head><style>
        svg { width: 100%; min-width: 900px; }
        svg>.edge { stroke: #111; }
        svg .node, .plain { fill: #fff; }
        </style></head><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <path class="edge" d="M0 0L1 1"/><rect class="node" width="1" height="1"/>
        </svg></body></html>"""
        css = embedded_css(self.mod.export_svg_document(html, Path("svg-prefix.html")))
        self.assertIn("#svg-prefix-root>.edge { stroke: #111; }", css)
        self.assertIn("#svg-prefix-root .node, #svg-prefix-root .plain { fill: #fff; }", css)
        self.assertNotIn("min-width", css)

    def test_body_color_and_font_family_are_carried_onto_root(self) -> None:
        # `stroke="currentColor"` and text without a font rule inherit from
        # body. The body rule is dropped as chrome, so its color and
        # font-family must be bound to the SVG root instead.
        html = """<!DOCTYPE html><html><head><style>
        body { padding: 40px; background: #f5f5f5; color: #2d3142;
               font-family: 'Geist', sans-serif; }
        .edge { fill: none; }
        </style></head><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" role="img"
             aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <path class="edge" d="M0 0L10 10" stroke="currentColor"/>
          <text x="1" y="5">plain</text>
        </svg></body></html>"""
        css = embedded_css(self.mod.export_svg_document(html, Path("body-inherit.html")))
        self.assertRegex(css, r"#body-inherit-root\s*\{[^}]*(?<![\w-])color:\s*#2d3142")
        self.assertRegex(css, r"#body-inherit-root\s*\{[^}]*font-family:\s*'Geist', sans-serif")
        for leaked in ("padding", "background", "40px", "#body-inherit-root body"):
            self.assertNotIn(leaked, css)

        source = ASSETS / "example-dp-integration.html"
        svg = self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
        self.assertIn('stroke="currentColor"', svg)
        css = embedded_css(svg)
        self.assertRegex(
            css, r"#example-dp-integration-root\s*\{[^}]*(?<![\w-])color:\s*var\(--ink\)"
        )
        self.assertRegex(
            css, r"#example-dp-integration-root\s*\{[^}]*font-family:\s*var\(--sans\)"
        )

    def test_valueless_html_attributes_become_xml(self) -> None:
        for name in MOTION_FILES + ("example-paved-road-animated.html", "example-polar.html"):
            with self.subTest(name=name):
                source = ASSETS / name
                svg = self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
                ET.fromstring(svg)
                marker = "data-polar-chart" if "polar" in name else "data-motion-item"
                self.assertIn(f'{marker}=""', svg)
                self.assertNotRegex(svg, rf"{marker}(?=[\s/>])")
        html = """<!DOCTYPE html><html><body>
        <svg viewBox="0 0 10 10" xmlns="http://www.w3.org/2000/svg" data-flag
             role="img" aria-labelledby="t d">
          <title id="t">t</title><desc id="d">d</desc>
          <!-- <g data-in-comment> stays as written -->
          <g data-motion-item aria-label="Step 1 > Step 2" data-step=1>
            <rect width="1" height="1" hidden/>
          </g>
        </svg></body></html>"""
        svg = self.mod.export_svg_document(html, Path("valueless.html"))
        ET.fromstring(svg)
        self.assertRegex(svg, r'<svg\b[^>]*\sdata-flag=""')
        self.assertIn('<g data-motion-item="" aria-label="Step 1 > Step 2" data-step="1">', svg)
        self.assertIn('<rect width="1" height="1" hidden=""/>', svg)
        self.assertIn("<!-- <g data-in-comment> stays as written -->", svg)

    def test_shipped_corpus_exports_with_scoped_rules(self) -> None:
        # Every shipped example and template (except the pinned, loudly refused
        # ones) exports; every class the diagram uses that the page styles gets
        # a rule scoped to the root; tokens and body color move to the root.
        for source in exportable_assets():
            with self.subTest(name=source.name):
                html = source.read_text(encoding="utf-8")
                slug = source.stem
                svg = self.mod.export_svg_document(html, source)
                ET.fromstring(svg)
                css = embedded_css(svg)
                page_css = re.sub(
                    r"/\*.*?\*/", "", "\n".join(PAGE_STYLE_RE.findall(html)), flags=re.DOTALL
                )
                self.assertNotIn(":root", css)
                self.assertNotRegex(css, rf"#{re.escape(slug)}-root\s+svg\b")
                if re.search(r":root\s*\{[^}]*--", page_css):
                    self.assertRegex(css, rf"#{re.escape(slug)}-root\s*\{{[^}}]*--")
                if re.search(r"(?:^|[\s}])body\s*\{[^}]*(?<![\w-])color\s*:", page_css):
                    self.assertRegex(
                        css, rf"#{re.escape(slug)}-root\s*\{{[^}}]*(?<![\w-])color\s*:"
                    )
                used = set()
                for value in re.findall(
                    r'\bclass\s*=\s*"([^"]*)"', self.mod.extract_first_svg(html)
                ):
                    used.update(value.split())
                for cls in sorted(used):
                    if not re.search(rf"\.{re.escape(cls)}(?![\w-])", page_css):
                        continue
                    self.assertRegex(
                        css,
                        rf"#{re.escape(slug)}-root[^{{}},]*\.{re.escape(cls)}(?![\w-])",
                        f"class {cls!r} is styled on the page but has no scoped rule",
                    )

    def test_known_unexportable_assets_are_refused_loudly(self) -> None:
        for name in sorted(KNOWN_UNEXPORTABLE):
            with self.subTest(name=name):
                source = ASSETS / name
                self.assertTrue(source.is_file(), f"{name} is listed but not shipped")
                with self.assertRaises(ValueError):
                    self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportSvgStandaloneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
