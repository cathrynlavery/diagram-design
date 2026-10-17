#!/usr/bin/env python3
"""Regression tests for standalone SVG export (CSS carry + defs ID namespace).

Covers the packaged helper at skills/diagram-design/scripts/export_svg.py and
the contract documented in references/export.md (issues #202 and #203).
"""

from __future__ import annotations

import contextlib
import io
import importlib.util
import contextlib
import io
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "skills/diagram-design/scripts/export_svg.py"
EXPORT_MD = ROOT / "skills/diagram-design/references/export.md"
ASSETS = ROOT / "skills/diagram-design/assets"

# Shipped assets the helper refuses (loudly). Empty since #407: nested icon
# <svg> elements and `--` inside comments both export. Keep this list exact so
# a newly unexportable asset shows up here instead of in a user's export.
KNOWN_UNEXPORTABLE: frozenset[str] = frozenset()

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

    def test_nested_rule_groups_preserve_paint_and_animation_bindings(self) -> None:
        for group in ("@layer base", "@container (min-width: 1px)", "@future-group paint"):
            with self.subTest(group=group):
                html = '<style>' + group + ' {@keyframes pulse {from {opacity:0;} to {opacity:1;}} .paint {fill:red;animation:pulse 1s;}}</style>'
                html += '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
                svg = self.mod.export_svg_document(html, Path("group.html"))
                css = embedded_css(svg)
                self.assertIn(group + " {", css)
                self.assertIn("#group-root .paint { fill:red;animation:group-root-pulse 1s; }", css)
                self.assertIn("@keyframes group-root-pulse { from {opacity:0;} to {opacity:1;} }", css)
                ET.fromstring(svg)

    def test_stray_page_css_closing_braces_preserve_valid_rules(self) -> None:
        body = '<svg viewBox="0 0 10 10"><rect class="paint"/><text class="label">x</text></svg>'
        clean = '<style>.paint {fill:red;}.label {fill:blue;}</style>' + body
        recovered = '<style>} .paint {fill:red;} } }.label {fill:blue;} }</style>' + body
        self.assertEqual(self.mod.export_svg_document(recovered, Path("brace.html")),
                         self.mod.export_svg_document(clean, Path("brace.html")))

    def test_unknown_declaration_blocks_warn_without_losing_paint(self) -> None:
        html = '<style>@property --paint {syntax:"<color>";inherits:false;initial-value:red;}.paint {fill:red;}</style>'
        html += '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
        warning = io.StringIO()
        with contextlib.redirect_stderr(warning):
            svg = self.mod.export_svg_document(html, Path("property.html"))
        self.assertNotIn("@property", embedded_css(svg))
        self.assertIn("#property-root .paint { fill:red; }", embedded_css(svg))
        self.assertIn("warning: dropping unsupported CSS block", warning.getvalue())

    def test_smil_paint_values_follow_namespaced_definitions(self) -> None:
        html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/>'
                '<linearGradient id="other"/></defs><rect width="10" height="10">'
                '<set attributeName="fill" to="url(#paint)" begin="0s"/>'
                '<animate attributeName="str&#111;ke" from="url(#paint)" '
                'to="url(#other)" values="url(#paint); url(#other)" by="url(#paint)"/>'
                '</rect></svg>')
        root = ET.fromstring(self.mod.export_svg_document(html, Path("smil.html")))
        animation = next(element for element in root.iter() if element.tag.endswith("}set"))
        self.assertEqual(animation.get("to"), "url(#smil-paint)")
        animation = next(element for element in root.iter() if element.tag.endswith("}animate"))
        for name, expected in {"from": "url(#smil-paint)", "to": "url(#smil-other)",
                               "values": "url(#smil-paint); url(#smil-other)",
                               "by": "url(#smil-paint)"}.items():
            self.assertEqual(animation.get(name), expected, name)

    def test_smil_reference_values_preserve_css_escapes_and_literals(self) -> None:
        for target in ("fill", "stroke", "filter", "clip-path", "mask", "marker-end"):
            with self.subTest(target=target):
                html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/></defs>'
                        '<animate attributeName="' + target + '" '
                        'from="URL(&quot;#pa\\69 nt&quot;)" to="url(#missing)" '
                        'values="url(#paint);url(#pa\\69 nt);none" '
                        'by="url(#paint)" data-label="url(#paint)"/></svg>')
                root = ET.fromstring(self.mod.export_svg_document(html, Path("smil.html")))
                actual = next(node for node in root.iter() if node.tag.endswith("}animate"))
                self.assertEqual(actual.get("from"), 'url("#smil-pa\\69 nt")')
                self.assertEqual(actual.get("to"), "url(#missing)")
                self.assertEqual(actual.get("values"), "url(#smil-paint);url(#smil-pa\\69 nt);none")
                self.assertEqual(actual.get("by"), "url(#smil-paint)")
                self.assertEqual(actual.get("data-label"), "url(#paint)")

    def test_only_applicable_animation_attributes_carry_paint_urls(self) -> None:
        for markup in ('<g attributeName="fill" to="url(#paint)"/>',
                       '<animateTransform attributeName="fill" to="url(#paint)"/>',
                       '<set attributeName="fill" from="url(#paint)" '
                       'values="url(#paint)" by="url(#paint)"/>',
                       '<animate attributename="fill" to="url(#paint)"/>'):
            with self.subTest(markup=markup):
                html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/>'
                        '</defs>' + markup + '</svg>')
                svg = self.mod.export_svg_document(html, Path("smil.html"))
                self.assertIn(markup, svg)

    def test_unchanged_inline_css_keeps_original_attribute_spelling(self) -> None:
        style = "font-family:'Foo\\&#10;Bar'; --literal:&amp;#10;;fill:url(#external)"
        html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/>'
                '</defs><text style="' + style + '">Label</text></svg>')
        svg = self.mod.export_svg_document(html, Path("space.html"))
        self.assertIn('style="' + style + '"', svg)

    def test_animation_looking_metadata_remains_literal(self) -> None:
        for element in ("set", "animate", "animateTransform", "g"):
            for target in ("data-label", "Fill", "style"):
                with self.subTest(element=element, target=target):
                    html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/>'
                            '</defs><' + element + ' attributeName="' + target + '" '
                            'to="url(#paint)" from="url(#paint)" '
                            'values="url(#paint);url(#paint)" by="url(#paint)"/></svg>')
                    root = ET.fromstring(self.mod.export_svg_document(html, Path("smil.html")))
                    actual = next(node for node in root.iter() if node.get("attributeName"))
                    for name in ("to", "from", "by"):
                        self.assertEqual(actual.get(name), "url(#paint)")
                    self.assertEqual(actual.get("values"), "url(#paint);url(#paint)")

    def test_inline_css_attribute_whitespace_keeps_xml_semantics(self) -> None:
        whitespace = ("&#9;", "&#10;", "&#13;", "&#x9;", "&#xA;", "&#xD;",
                      "\t", "\n", "\r", "\r\n", "&amp;#10;")
        for spelling in whitespace:
            for rewrite in (False, True):
                with self.subTest(spelling=repr(spelling), rewrite=rewrite):
                    style = "font-family:'Foo\\" + spelling + "Bar'; --quoted:'a" + spelling + "b'"
                    if rewrite:
                        style += ";fill:url(#paint)"
                    html = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="paint"/>'
                            '</defs><text style="' + style + '">Label</text></svg>')
                    original = next(node for node in ET.fromstring(html).iter() if node.tag == "text")
                    exported = ET.fromstring(self.mod.export_svg_document(html, Path("space.html")))
                    actual = next(node for node in exported.iter() if node.tag.endswith("}text"))
                    expected = original.get("style")
                    if rewrite:
                        expected = expected.replace("url(#paint)", "url(#space-paint)")
                    self.assertEqual(actual.get("style"), expected)

    def test_css_comment_delimiters_inside_literals_survive_export(self) -> None:
        selectors = [
            'rect[data-label="net/*retained*/revenue"]',
            "rect[data-label='net/*retained*/revenue']",
            r'rect[data-label="net\"/*retained*/revenue"]',
            r'.net\/\*retained\*\/revenue',
        ]
        for selector in selectors:
            with self.subTest(selector=selector):
                source = '<style>' + selector + ' {fill:red}</style>'
                source += '<svg viewBox="0 0 20 20"><rect width="20" height="20"/></svg>'
                exported = self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True)
                self.assertIn('#literal-root ' + selector + ' { fill:red }', embedded_css(exported))

    def test_real_css_comments_still_leave_tokens_and_rules_intact(self) -> None:
        source = '<style>/* heading */ :root {--paint:red} rect/* between */.paint {fill:var(--paint)}</style>'
        source += '<svg viewBox="0 0 20 20"><rect class="paint" width="20" height="20"/></svg>'
        exported = self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True)
        css = embedded_css(exported)
        self.assertIn('#literal-root { --paint:red }', css)
        self.assertIn('#literal-root rect.paint { fill:var(--paint) }', css)
        self.assertNotIn('heading', css)
        self.assertNotIn('between', css)

    def test_selector_lists_preserve_quoted_and_escaped_literals(self) -> None:
        selectors = [
            'rect[data-label="Revenue, net"]',
            'rect[data-label="Revenue  net"]',
            "rect[data-label='Revenue,  net']",
            r'rect[data-label="a\"b,  c"]',
            r'.revenue\,net',
            r'.revenue\2c net',
            ':is(rect, circle):not([data-label="a,b"])',
            ':where(rect, :is(circle, path))',
        ]
        for selector in selectors:
            with self.subTest(selector=selector):
                html = '<style>' + selector + ', .other {fill:red}</style>'
                html += '<svg viewBox="0 0 40 40"><rect class="other"/></svg>'
                css = embedded_css(self.mod.export_svg_document(html, Path("literal.html")))
                self.assertIn('#literal-root ' + selector + ', #literal-root .other { fill:red }', css)
        # Hex escape terminator plus descendant whitespace must remain distinct.
        css = self.mod.diagram_css_from_html('<style>.\\31  rect {fill:red}</style>', 'literal-root')
        self.assertIn('#literal-root .\\31  rect', css)

    def test_css_escaped_local_paint_fragments_follow_namespaced_defs(self) -> None:
        references = [r'url(#\70 aint)', r"url('#\70 aint')", r'url(&quot;#\70 aint&quot;)']
        for reference in references:
            with self.subTest(reference=reference):
                source = '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
                source += '<rect fill="' + reference + '" width="20" height="20"/></svg>'
                root = ET.fromstring(self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True))
                gradient = root.find('.//{http://www.w3.org/2000/svg}linearGradient')
                rectangle = root.find('{http://www.w3.org/2000/svg}rect')
                self.assertEqual(gradient.get('id'), 'literal-paint')
                self.assertIn(r'#literal-\70 aint', rectangle.get('fill'))

    def test_url_looking_metadata_and_css_strings_remain_literal(self) -> None:
        for fragment in (r'#\70 aint', '#paint'):
            with self.subTest(fragment=fragment):
                literal = 'url(' + fragment + ')'
                selector_value = literal.replace('\\', '\\\\')
                source = '<style>rect[data-label="' + selector_value + '"]{fill:red}</style>'
                source += '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
                source += '<rect data-label="' + literal + '" width="20" height="20"/></svg>'
                exported = self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True)
                rectangle = ET.fromstring(exported).find('{http://www.w3.org/2000/svg}rect')
                self.assertEqual(rectangle.get('data-label'), literal)
                self.assertIn('[data-label="' + selector_value + '"]', embedded_css(exported))
        for carrier in ('stylesheet', 'inline'):
            with self.subTest(carrier=carrier):
                declaration = r'--note:"url(#\70 aint)";fill:url(#\70 aint)'
                source = '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
                if carrier == 'stylesheet':
                    source += '<style>.paint {' + declaration + '}</style><rect class="paint"/>'
                else:
                    source += "<rect style='" + declaration + "'/>"
                exported = self.mod.export_svg_document(source + '</svg>', Path("literal.html"), system_fonts=True)
                if carrier == 'stylesheet':
                    css = ''.join(node.text or '' for node in ET.fromstring(exported).iter() if node.tag.endswith('}style'))
                else:
                    css = ET.fromstring(exported).find('{http://www.w3.org/2000/svg}rect').get('style')
                self.assertIn(r'--note:"url(#\70 aint)"', css)
                self.assertIn(r'fill:url(#literal-\70 aint)', css)

    def test_commented_inline_paint_keeps_its_optional_definition_binding(self) -> None:
        source = '<svg viewBox="0 0 20 20"><defs><!-- <pattern id="paint"/> --></defs>'
        source += '<symbol id="paint"><rect width="10" height="10"/></symbol>'
        source += '<!-- <rect style="fill:url(#paint)"/> --><use href="#paint"/></svg>'
        exported = self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True)
        self.assertIn('<pattern id="literal-paint"/>', exported)
        self.assertIn('<rect style="fill:url(#literal-paint)"/>', exported)
        self.assertEqual(ET.fromstring(exported).find('{http://www.w3.org/2000/svg}use').get('href'), '#paint')

    def test_longer_css_function_names_are_not_local_url_functions(self) -> None:
        for function in ('noturl', 'vendor-url', '-url', '_url', '💡url'):
            for carrier in ('stylesheet', 'inline'):
                with self.subTest(function=function, carrier=carrier):
                    declaration = '--note:' + function + r'(#\70 aint);fill:red'
                    source = '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
                    if carrier == 'stylesheet':
                        source += '<style>.paint {' + declaration + '}</style><rect class="paint"/>'
                    else:
                        source += "<rect style='" + declaration + "'/>"
                    root = ET.fromstring(self.mod.export_svg_document(source + '</svg>', Path("literal.html"), system_fonts=True))
                    css = ''.join(node.text or '' for node in root.iter() if node.tag.endswith('}style')) if carrier == 'stylesheet' else root.find('{http://www.w3.org/2000/svg}rect').get('style')
                    self.assertIn(declaration, css)

    def test_escaped_function_identifiers_are_consumed_before_url_matching(self) -> None:
        functions = [r'my\31 url', r'my\000031url', r'my\0031 url', r'my\31 URL', r'my\31' + '\turl']
        for function in functions:
            for carrier in ('stylesheet', 'inline'):
                with self.subTest(function=function, carrier=carrier):
                    declaration = '--note:' + function + r'(#\70 aint);fill:red'
                    source = '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
                    if carrier == 'stylesheet':
                        source += '<style>.paint {' + declaration + '}</style><rect class="paint"/>'
                    else:
                        source += "<rect style='" + declaration + "'/>"
                    root = ET.fromstring(self.mod.export_svg_document(source + '</svg>', Path("literal.html"), system_fonts=True))
                    css = ''.join(node.text or '' for node in root.iter() if node.tag.endswith('}style')) if carrier == 'stylesheet' else root.find('{http://www.w3.org/2000/svg}rect').get('style')
                    self.assertIn(declaration.replace('\t', ' ') if carrier == 'inline' else declaration, css)

    def test_second_space_after_an_identifier_escape_starts_a_real_url(self) -> None:
        declaration = r'--note:my\31  url(#\70 aint);fill:red'
        source = '<svg viewBox="0 0 20 20"><defs><linearGradient id="paint"/></defs>'
        source += '<style>.paint {' + declaration + '}</style><rect class="paint"/></svg>'
        exported = self.mod.export_svg_document(source, Path("literal.html"), system_fonts=True)
        self.assertIn(r'--note:my\31  url(#literal-\70 aint);fill:red', exported)

    def test_rgba_parent_normalizes_with_unrelated_page_paint(self) -> None:
        for prop in ("fill", "stroke"):
            for selector in (".paint", "rect.paint", "#unrelated", ".unused .paint"):
                with self.subTest(prop=prop, selector=selector):
                    html = f'<style>{selector}{{{prop}:#000}}</style><svg viewBox="0 0 10 10"><g {prop}="rgba(255,0,0,0.5)"><rect width="5" height="5"/></g></svg>'
                    group = ET.fromstring(self.mod.export_svg_document(html, Path("parent.html"))).find("{http://www.w3.org/2000/svg}g")
                    self.assertEqual(group.get(prop), "#ff0000")
                    self.assertEqual(group.get(prop + "-opacity"), "0.5")

    def test_rgba_parent_retains_alpha_when_page_paint_can_override_children(self) -> None:
        for prop in ("fill", "stroke"):
            for selector in (".paint", "rect", "g > rect", "rect:first-child", "[width]"):
                with self.subTest(prop=prop, selector=selector):
                    html = f'<style>{selector}{{{prop}:#000}}</style><svg viewBox="0 0 10 10"><g {prop}="rgba(255,0,0,0.5)"><rect class="paint" width="5" height="5"/></g></svg>'
                    group = ET.fromstring(self.mod.export_svg_document(html, Path("parent.html"))).find("{http://www.w3.org/2000/svg}g")
                    self.assertEqual(group.get(prop), "rgba(255,0,0,0.5)")
                    self.assertNotIn(prop + "-opacity", group.attrib)

    def test_rgba_keeps_alpha_when_css_overrides_the_painted_element(self) -> None:
        for prop in ("fill", "stroke"):
            for tag in ("g", "rect"):
                html = f'<style>.paint{{{prop}:#000}}</style><svg viewBox="0 0 10 10"><{tag} class="paint" {prop}="rgba(255,0,0,0.5)"><rect width="5" height="5"/></{tag}></svg>'
                shape = ET.fromstring(self.mod.export_svg_document(html, Path("parent.html"))).find("{http://www.w3.org/2000/svg}" + tag)
                self.assertEqual(shape.get(prop), "rgba(255,0,0,0.5)")
                self.assertNotIn(prop + "-opacity", shape.attrib)

    def test_rgba_parent_with_unpainted_child_normalizes(self) -> None:
        for prop in ("fill", "stroke"):
            html = f'<svg viewBox="0 0 10 10"><g {prop}="rgba(255,0,0,0.5)" {prop}-opacity="0.5"><rect width="10" height="10"/></g></svg>'
            exported = self.mod.export_svg_document(html, Path("parent.html"))
            root = ET.fromstring(exported)
            group = root.find("{http://www.w3.org/2000/svg}g")
            self.assertEqual(group.get(prop), "#ff0000")
            self.assertEqual(group.get(prop + "-opacity"), "0.25")
    def test_cli_reports_source_read_errors_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.html"
            source.write_text('<svg viewBox="0 0 10 10"></svg>', encoding="utf-8")
            output = Path(directory) / "output.svg"
            stderr = io.StringIO()
            with patch.object(Path, "read_text", side_effect=PermissionError("source denied")):
                with contextlib.redirect_stderr(stderr):
                    result = self.mod.main([str(source), str(output)])
            self.assertEqual(result, 2)
            self.assertIn("error: source denied", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_reports_output_io_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.html"
            source.write_text('<svg viewBox="0 0 10 10"><rect width="10" height="10"/></svg>', encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                result = self.mod.main([str(source), directory])
            self.assertEqual(result, 2)
            self.assertIn("error:", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_nested_namespace_does_not_replace_root_namespace(self) -> None:
        markup = '<svg viewBox="0 0 10 10"><g xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></g></svg>'
        result = self.mod.ensure_xmlns(markup)
        self.assertEqual(ET.fromstring(result).tag, "{http://www.w3.org/2000/svg}svg")
        with self.assertRaisesRegex(ValueError, "root namespace"):
            self.mod.ensure_xmlns('<svg xmlns="https://example.invalid/other"/>')

    def test_viewbox_has_four_finite_values_and_positive_extents(self) -> None:
        for value in ("0 0 0 10", "0 0 -10 10", "0 0 nan 10", "0 0 1e309 10", "0 0 10", "0,,0,10,10", "٠ ٠ ١٠ ١٠"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "viewBox"):
                self.mod.ensure_viewbox(f'<svg viewBox="{value}"/>')
        for value in ("-10,+10,100.5,50", "0 0 1e2 1e-2", "&#48; &#48; 10 10"):
            self.mod.ensure_viewbox(f'<svg viewBox="{value}"/>')

    def test_viewbox_reads_exact_root_attribute(self) -> None:
        html = '<svg data-viewBox="preview" data-note=\'viewBox="preview"\' viewBox="0 0 100 100"></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("viewport.html")))
        self.assertEqual(root.get("viewBox"), "0 0 100 100")
        for svg in (
            '<svg data-viewBox="0 0 100 100" viewBox="0 0 0 100"></svg>',
            '<svg data-viewBox="0 0 100 100"></svg>',
            '<svg><g viewBox="0 0 100 100"/></svg>',
        ):
            with self.subTest(svg=svg), self.assertRaisesRegex(ValueError, "viewBox"):
                self.mod.export_svg_document(svg, Path("viewport.html"))

    def test_viewbox_refuses_non_svg_whitespace(self) -> None:
        for value in ("0&#160;0&#160;100&#160;100", "&#160;0 0 100 100", "0 0 100 100&#160;"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "viewBox"):
                self.mod.export_svg_document(f'<svg viewBox="{value}"></svg>', Path("viewport.html"))

    def test_css_gate_ignores_non_class_and_empty_attributes(self) -> None:
        for markup in (
            '<svg data-class="metadata"><rect fill="#fff"/></svg>',
            '<svg><!-- class="archived" --><rect fill="#fff"/></svg>',
            '<svg class="  "><rect fill="#fff"/></svg>',
            '<svg><text>class="example"</text></svg>',
        ):
            with self.subTest(markup=markup):
                self.mod.assert_export_gate(markup)
        with self.assertRaisesRegex(ValueError, "no diagram CSS"):
            self.mod.assert_export_gate('<svg><rect class="paint"/></svg>')

    def test_export_uses_live_svg_and_live_styles(self) -> None:
        html = '<!-- <svg viewBox="0 0 1 1"></svg> --><script>const sample = "<svg viewBox=\"0 0 2 2\"></svg>";</script>'
        html += '<!-- <style>.paint {fill:red;}</style> -->'
        html += '<style>.paint {fill:blue;}</style><svg viewBox="0 0 10 10"><!-- archived </svg> --><rect class="paint" width="10" height="10"/></svg>'
        document = self.mod.export_svg_document(html, Path("live.html"))
        root = ET.fromstring(document)
        self.assertEqual(root.get("viewBox"), "0 0 10 10")
        self.assertIn("fill:blue", document)
        self.assertNotIn("fill:red", document)
        self.assertIn("<!-- archived </svg> -->", document)

    def test_live_css_comment_markers_and_strings_are_preserved(self) -> None:
        css = '.x { fill:red; /* <!-- */ stroke:blue; /* --> */ } .x::before { content:"<!-- note -->"; }'
        html = f'<style>{css}</style><svg viewBox="0 0 10 10"><rect class="x" width="10" height="10"/></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("live-style.html")))
        styles = "".join(element.text or "" for element in root.iter() if element.tag.endswith("}style"))
        self.assertIn("stroke:blue", styles)
        self.assertIn('content:"<!-- note -->"', styles)

    def test_svg_cdata_comment_marker_does_not_hide_closing_svg(self) -> None:
        html = '<svg viewBox="0 0 10 10"><text><![CDATA[<!--]]></text></svg><!-- footer -->'
        document = self.mod.export_svg_document(html, Path("cdata.html"))
        root = ET.fromstring(document)
        self.assertEqual(root.get("viewBox"), "0 0 10 10")
        text = next(element for element in root.iter() if element.tag.endswith("}text"))
        self.assertEqual(text.text, "<!--")
        self.assertNotIn("footer", document)

    def test_rgba_normalization_clamps_channels_and_alpha(self) -> None:
        for value, paint, opacity in (
            ("rgba(300,0,0,0.5)", "#ff0000", "0.5"),
            ("rgba(-12,300,10,0.5)", "#00ff0a", "0.5"),
            ("rgba(45,49,66,-0.1)", "#2d3142", "0"),
            ("rgba(45,49,66,1.5)", "#2d3142", "1"),
        ):
            with self.subTest(value=value):
                normalized = self.mod.normalize_rgba_presentation_attrs(f'<svg><rect fill="{value}"/></svg>')
                rect = ET.fromstring(normalized)[0]
                self.assertEqual(rect.get("fill"), paint)
                self.assertEqual(rect.get("fill-opacity"), opacity)

    def test_manual_paint_recipe_retains_css_clamping(self) -> None:
        section = EXPORT_MD.read_text(encoding="utf-8").split("7. Normalize colors", 1)[1]
        match = re.search(r"```python\n(.*?)\n   ```", section, re.DOTALL)
        self.assertIsNotNone(match)
        recipe = "\n".join(line[3:] if line.startswith("   ") else line for line in match.group(1).splitlines())
        for svg in ('<svg><rect fill="rgba(255,0,0,0.5)" fill-opacity="0.5" style="fill:#0000ff"/></svg>', '<svg><rect stroke="rgba(255,0,0,0.5)" stroke-opacity="0.5" style="stroke:#0000ff"/></svg>', '<svg><rect fill="rgba(300,-10,20,2)"/></svg>', '<svg><rect stroke="rgba(-4,1,2,-.5)"/></svg>', '<svg><style>.paint{fill:#000}</style><g fill="rgba(255,0,0,0.5)"><rect/></g></svg>', '<svg><style>.paint{fill:#000}</style><g fill="rgba(255,0,0,0.5)"><rect class="paint"/></g></svg>', '<svg><rect fill="rgba(255,0,0,0.5)" fill-opacity="0.5"/></svg>'):
            with self.subTest(svg=svg):
                namespace = {"svg": svg}
                exec(recipe, namespace)
                self.assertEqual(namespace["svg"], self.mod.normalize_rgba_presentation_attrs(svg))

    def test_defs_id_selectors_follow_namespaced_ids(self) -> None:
        markup = '<svg><defs><linearGradient id="abc"><stop/></linearGradient></defs><style>#abc stop { stop-color:#abc; } #abc-other { fill:#fff; }</style></svg>'
        result = self.mod.namespace_defs_ids(markup, "diagram")
        self.assertIn('#diagram-abc stop { stop-color:#abc; }', result)
        self.assertIn('#abc-other { fill:#fff; }', result)
        escaped = r'<svg><defs><linearGradient id="paint.v1"/></defs><style>#paint\.v1 stop { stop-color:#fff; }</style></svg>'
        result = self.mod.namespace_defs_ids(escaped, "diagram")
        self.assertIn(r'#diagram-paint\.v1 stop', result)

    def test_defs_selector_retarget_keeps_cdata_stylesheets(self) -> None:
        css = '.paint { fill:red; } #abc stop { stop-color:#fff; }'
        markup = ('<svg viewBox="0 0 10 10"><defs><linearGradient id="abc"><stop/></linearGradient></defs>'
                  '<style><![CDATA[' + css + ']]></style><rect class="paint" width="5" height="5"/></svg>')
        result = self.mod.namespace_defs_ids(markup, "diagram")
        self.assertIn('<style><![CDATA[.paint { fill:red; } #diagram-abc stop { stop-color:#fff; }]]></style>', result)
        self.assertNotIn('&lt;![CDATA[', result)
        root = ET.fromstring(self.mod.export_svg_document(markup, Path("diagram.html")))
        texts = [element.text or "" for element in root.iter() if element.tag.endswith("}style")]
        # The SVG's own <style> keeps working CSS after the defs rename.
        self.assertIn('.paint { fill:red; } #diagram-abc stop { stop-color:#fff; }', texts)

    def test_defs_selector_retarget_survives_quotes_in_css_comments(self) -> None:
        for wrap in (lambda css: css, lambda css: "<![CDATA[" + css + "]]>"):
            css = "#shape { /* user's color */ fill:red; }"
            markup = ('<svg><defs><g id="shape"/></defs><style>' + wrap(css) + '</style>'
                      '<use href="#shape"/></svg>')
            with self.subTest(markup=markup):
                result = self.mod.namespace_defs_ids(markup, "diagram")
                self.assertIn("#diagram-shape { /* user's color */ fill:red; }", result)

    def test_cdata_url_references_stay_raw_after_defs_rename(self) -> None:
        markup = ('<svg><defs><linearGradient id="A&amp;B"/></defs>'
                  '<style><![CDATA[.paint { fill:url(#A&B); }]]></style></svg>')
        result = self.mod.namespace_defs_ids(markup, "diagram")
        self.assertIn('id="diagram-A&amp;B"', result)
        self.assertIn("<![CDATA[.paint { fill:url(#diagram-A&B); }]]>", result)
        plain = ('<svg><defs><linearGradient id="A&amp;B"/></defs>'
                 '<style>.paint { fill:url(#A&amp;B); }</style></svg>')
        self.assertIn(".paint { fill:url(#diagram-A&amp;B); }", self.mod.namespace_defs_ids(plain, "diagram"))

    def test_unfinished_rule_with_repeated_comments_does_not_stall(self) -> None:
        import subprocess
        markup = ('<svg><defs><g id="shape"/></defs><style>.paint { fill:red;'
                  + "/*x*/" * 40 + '</style><use href="#shape"/></svg>')
        code = ("import importlib.util, sys; spec = importlib.util.spec_from_file_location('e', sys.argv[1]); "
                "mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); "
                "print(mod.namespace_defs_ids(sys.stdin.read(), 'diagram'))")
        try:
            result = subprocess.run([sys.executable, "-c", code, str(HELPER)], input=markup,
                                    capture_output=True, text=True, timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("an unfinished rule followed by repeated CSS comments stalled the rule matcher")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('id="diagram-shape"', result.stdout)

    def test_style_closing_tag_whitespace_keeps_selectors_retargeted(self) -> None:
        markup = '<svg><defs><g id="shape"/></defs><style>#shape { fill:red; }</style ><use href="#shape"/></svg>'
        self.assertIn("#diagram-shape { fill:red; }", self.mod.namespace_defs_ids(markup, "diagram"))

    def test_defs_selectors_decode_xml_and_preserve_escaped_braces(self) -> None:
        for ident, selector, expected_id, expected_selector in (
            ("p&#46;v", r"#p\.v", "diagram-p.v", r"#diagram-p\.v"),
            ("paint{v", r"#paint\{v", "diagram-paint{v", r"#diagram-paint\{v"),
            ("A&amp;B", r"#A\&amp;B", "diagram-A&B", r"#diagram-A\&B"),
        ):
            with self.subTest(ident=ident):
                html = '<svg viewBox="0 0 10 10"><defs><linearGradient id="' + ident + '"/></defs>'
                html += '<style>' + selector + ' stop { stop-color:#fff; }</style></svg>'
                root = ET.fromstring(self.mod.export_svg_document(html, Path("diagram.html")))
                gradient = next(element for element in root.iter() if element.tag.endswith("}linearGradient"))
                self.assertEqual(gradient.get("id"), expected_id)
                css = "".join(element.text or "" for element in root.iter() if element.tag.endswith("}style"))
                self.assertIn(expected_selector + " stop { stop-color:#fff; }", css)

    def test_reusable_defs_shapes_are_namespaced(self) -> None:
        for tag in ("g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text", "image", "use"):
            with self.subTest(tag=tag):
                markup = f'<svg><defs><{tag} id="shape"/></defs><use href="#shape"/><use xlink:href="#shape"/></svg>'
                result = self.mod.namespace_defs_ids(markup, "diagram")
                self.assertIn('id="diagram-shape"', result)
                self.assertIn('href="#diagram-shape"', result)
                self.assertIn('xlink:href="#diagram-shape"', result)

    def test_reusable_shapes_keep_css_id_styles_after_public_export(self) -> None:
        html = '<style>#abc { fill:#abc; } #holder > path { stroke:red; }</style>'
        html += '<svg viewBox="0 0 10 10"><defs><g id="holder"><path id="abc" d="M0 0H10V10H0Z"/></g></defs>'
        html += '<use href="#holder"/></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("diagram.html")))
        css = "".join(element.text or "" for element in root.iter() if element.tag.endswith("}style"))
        self.assertIn("#diagram-abc { fill:#abc; }", css)
        self.assertIn("#diagram-holder > path { stroke:red; }", css)
        self.assertEqual(next(element for element in root.iter() if element.tag.endswith("}path")).get("id"), "diagram-abc")
        self.assertEqual(next(element for element in root.iter() if element.tag.endswith("}use")).get("href"), "#diagram-holder")

    def test_defs_references_compare_decoded_xml_ids(self) -> None:
        markup = '<svg><defs><linearGradient id="A&#38;B"/></defs><use href="#A&amp;B"/><rect fill="url(#A&#x26;B)"/></svg>'
        result = self.mod.namespace_defs_ids(markup, "diagram")
        root = ET.fromstring(result)
        self.assertEqual(root[0][0].get("id"), "diagram-A&B")
        self.assertEqual(root[1].get("href"), "#diagram-A&B")
        self.assertEqual(root[2].get("fill"), "url(#diagram-A&B)")

    def test_distinct_once_decoded_ids_keep_distinct_definitions_and_references(self) -> None:
        markup = '<svg><defs><linearGradient id="A&#38;B"/><linearGradient id="A&amp;#38;B"/></defs>'
        markup += '<use href="#A&#38;B"/><use href="#A&amp;#38;B"/>'
        markup += '<rect fill="url(#A&#38;B)"/><rect fill="url(#A&amp;#38;B)"/></svg>'
        root = ET.fromstring(self.mod.namespace_defs_ids(markup, "diagram"))
        self.assertEqual([element.get("id") for element in root.find("defs")],
                         ["diagram-A&B", "diagram-A&#38;B"])
        self.assertEqual([element.get("href") for element in root.findall("use")],
                         ["#diagram-A&B", "#diagram-A&#38;B"])
        self.assertEqual([element.get("fill") for element in root.findall("rect")],
                         ["url(#diagram-A&B)", "url(#diagram-A&#38;B)"])

    def test_style_selectors_follow_once_decoded_distinct_defs_ids(self) -> None:
        # #376 selector retargeting combined with #381 single-decode IDs:
        # A&#38;B and A&amp;#38;B are different IDs and keep different rules.
        html = r'<svg viewBox="0 0 10 10"><defs><linearGradient id="A&#38;B"/><linearGradient id="A&amp;#38;B"/></defs>'
        html += r'<style>#A\&amp;B stop { stop-color:red; } #A\&amp;\#38\;B stop { stop-color:blue; }</style>'
        html += '<rect fill="url(#A&#38;B)"/><rect fill="url(#A&amp;#38;B)"/></svg>'
        root = ET.fromstring(self.mod.export_svg_document(html, Path("diagram.html")))
        css = "".join(element.text or "" for element in root.iter() if element.tag.endswith("}style"))
        self.assertIn(r"#diagram-A\&B stop { stop-color:red; }", css)
        self.assertIn(r"#diagram-A\&\#38\;B stop { stop-color:blue; }", css)
        self.assertEqual([element.get("fill") for element in root.iter() if element.tag.endswith("}rect")],
                         ["url(#diagram-A&B)", "url(#diagram-A&#38;B)"])
    def test_unquoted_data_url_semicolons_preserve_conditional_paint(self) -> None:
        image = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/iZk9HQAAAABJRU5ErkJggg=="
        for url in ("data:image/png;base64,AAAA", "data:image/png;base64," + image):
            for quote in ("", '"'):
                with self.subTest(url=url, quote=quote):
                    condition = f"@supports (background: url({quote}{url}{quote}))"
                    html = '<style>' + condition + ' { .paint {fill:red;} }</style>'
                    html += '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
                    css = embedded_css(self.mod.export_svg_document(html, Path("function.html")))
                    self.assertIn(condition + " {", css)
                    self.assertIn("#function-root .paint { fill:red; }", css)
                    self.assertNotIn("#function-root base64", css)

    def test_function_semicolon_keeps_nested_layer_order_and_animation(self) -> None:
        condition = "@supports (background: url(data:image/png;base64,AAAA))"
        html = '<style>@keyframes pulse {to{opacity:1}} ' + condition
        html += ' { @layer second, first; @layer first { .paint {fill:red;animation:pulse 1s;} } }</style>'
        html += '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
        css = embedded_css(self.mod.export_svg_document(html, Path("nested-function.html")))
        self.assertIn(condition + " {", css)
        self.assertIn("@layer second, first;", css)
        self.assertIn("animation:nested-function-root-pulse 1s", css)

    def test_font_face_and_supports_do_not_block_export(self) -> None:
        html = '<style>@font-face {font-family: Custom; src:url("custom.woff2");}'
        html += '@supports (display: grid) {.paint {fill:#ff0000;}}</style>'
        html += '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(html, Path("custom-font.html"))
        css = embedded_css(result)
        self.assertIn('@font-face', css)
        self.assertIn('font-family: Custom', css)
        self.assertIn('@supports (display: grid)', css)
        self.assertIn('#custom-font-root .paint', css)

    def test_system_fonts_omits_custom_font_face(self) -> None:
        html = '<style>@supports (display: grid) {@font-face {font-family: Custom; src:url("custom.woff2");} .label {font-family: Custom;}}</style>'
        html += '<svg viewBox="0 0 10 10"><text class="label">Label</text></svg>'
        css = embedded_css(self.mod.export_svg_document(html, Path("system-custom.html"), system_fonts=True))
        self.assertNotIn("@font-face", css)
        self.assertNotIn("custom.woff2", css)
        self.assertNotIn("fonts.googleapis.com", css)
        self.assertIn("#system-custom-root .label", css)
    def test_optional_defs_387_template_dots_keep_namespace(self) -> None:
        source = ASSETS / "template.html"
        exported = self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
        self.assertIn('id="template-dots"', exported)
        self.assertIn('url(#template-dots)', exported)

    def test_metadata_defs_382_ignores_data_id_inside_defs(self) -> None:
        markup = '<svg><defs><marker id="arrow"/><g data-id="ghost"/></defs><g data-id="arrow" data-href="#arrow"/><use href="#arrow"/></svg>'
        root = ET.fromstring(self.mod.namespace_defs_ids(markup, "d"))
        self.assertEqual(root.find("g").get("data-id"), "arrow")
        self.assertEqual(root.find("g").get("data-href"), "#arrow")
        self.assertEqual(root.find("use").get("href"), "#d-arrow")
        self.assertEqual(self.mod.find_defs_ids(markup), ["arrow"])

    def test_metadata_defs_382_does_not_retarget_a_data_id_definition(self) -> None:
        markup = '<svg><defs><g data-id="ghost"/></defs><g id="ghost"/><use href="#ghost"/></svg>'
        self.assertEqual(self.mod.find_defs_ids(markup), [])
        self.assertEqual(self.mod.namespace_defs_ids(markup, "d"), markup)

    def test_metadata_defs_382_template_dots_keep_namespace(self) -> None:
        source = ASSETS / "template.html"
        exported = self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)
        self.assertIn('id="template-dots"', exported)
        self.assertIn('url(#template-dots)', exported)

    def test_metadata_defs_382_shared_live_symbol_references_resolve(self) -> None:
        markup = '<svg viewBox="0 0 10 10"><defs><!-- <pattern id="dot"/> --></defs><symbol id="dot"><rect width="5" height="5" fill="red"/></symbol><use href="#dot"/></svg>'
        exported = self.mod.export_svg_document(markup, Path("b.html"))
        root = ET.fromstring(exported)
        symbol = next(element for element in root.iter() if element.tag.endswith("}symbol"))
        use = next(element for element in root.iter() if element.tag.endswith("}use"))
        self.assertEqual(use.get("href"), "#" + symbol.get("id"))

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

    def test_system_fonts_export_makes_no_font_request(self) -> None:
        source = ASSETS / "example-loop.html"
        html = source.read_text(encoding="utf-8")
        default = self.mod.export_svg_document(html, source)
        self.assertIn("fonts.googleapis.com", default)
        offline = self.mod.export_svg_document(html, source, system_fonts=True)
        self.assertNotIn("fonts.googleapis.com", offline)
        self.assertNotIn("@import", offline)
        # The diagram CSS still ships, so class-styled marks keep their fills.
        self.assertIn("#example-loop-root .station", offline)
        ET.fromstring(offline.split("\n", 1)[1])

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

    def test_rgba_retains_alpha_with_css_or_inherited_opacity(self) -> None:
        for prop in ("fill", "stroke"):
            paint = f'{prop}="rgba(255,0,0,0.5)"'
            snippets = (
                f'<style>.paint {{ {prop}-opacity:0.5 }}</style><rect class="paint" {paint} {prop}-opacity="0.8"/>',
                f'<g {prop}-opacity="0.5"><rect {paint}/></g>',
                f'<rect {paint} {prop}-opacity="0.8" style="{prop}-opacity:0.5"/>',
            )
            for snippet in snippets:
                with self.subTest(prop=prop, snippet=snippet):
                    result = self.mod.export_svg_document(f'<svg viewBox="0 0 10 10">{snippet}</svg>', Path("cascade.html"))
                    shape = ET.fromstring(result).find("{http://www.w3.org/2000/svg}rect")
                    if shape is None:
                        shape = ET.fromstring(result).find(".//{http://www.w3.org/2000/svg}rect")
                    self.assertEqual(shape.get(prop), "rgba(255,0,0,0.5)")

    def test_rgba_parent_preserves_independent_child_paints(self) -> None:
        for prop in ("fill", "stroke"):
            html = f'<svg viewBox="0 0 10 10"><g {prop}="rgba(255,0,0,0.5)" {prop}-opacity="0.5"><rect {prop}="#0000ff"/></g></svg>'
            result = ET.fromstring(self.mod.export_svg_document(html, Path("parent.html")))
            group = result.find("{http://www.w3.org/2000/svg}g")
            self.assertEqual(group.get(prop), "rgba(255,0,0,0.5)")
            self.assertEqual(group.get(f"{prop}-opacity"), "0.5")
            self.assertEqual(group[0].get(prop), "#0000ff")

    def test_rgba_keeps_opacity_when_own_inline_paint_overrides_color(self) -> None:
        for prop in ("fill", "stroke"):
            for declaration in (f"{prop}:#0000ff", f"{prop.upper()}:#0000ff", f"/* inline */ {prop}:#0000ff"):
                with self.subTest(paint=prop, declaration=declaration):
                    html = (f'<svg viewBox="0 0 10 10"><rect {prop}="rgba(255,0,0,0.5)" '
                            f'{prop}-opacity="0.5" style="{declaration}"/></svg>')
                    root = ET.fromstring(self.mod.export_svg_document(html, Path("inline.html")))
                    rect = root.find("{http://www.w3.org/2000/svg}rect")
                    self.assertEqual(rect.get(f"{prop}-opacity"), "0.5")
                    self.assertEqual(rect.get(prop), "rgba(255,0,0,0.5)")
                    self.assertEqual(rect.get("style"), declaration)

    def test_rgba_css_guard_reads_entities_and_escaped_property_names(self) -> None:
        for prop in ("fill", "stroke"):
            declarations = (f"{prop}-opacity&#58;0.5", f"{prop}\\2d opacity:0.5", f"{prop}&#92;2d opacity&#58;0.5")
            for declaration in declarations:
                html = f'<svg viewBox="0 0 10 10"><rect {prop}="rgba(255,0,0,0.5)" style="{declaration}"/></svg>'
                result = ET.fromstring(self.mod.export_svg_document(html, Path("encoded.html")))
                self.assertEqual(result.find("{http://www.w3.org/2000/svg}rect").get(prop), "rgba(255,0,0,0.5)")
            html = f'<svg viewBox="0 0 10 10"><style>rect {{ {prop}\\2d opacity:0.5 }}</style><rect {prop}="rgba(255,0,0,0.5)"/></svg>'
            result = ET.fromstring(self.mod.export_svg_document(html, Path("escaped.html")))
            self.assertEqual(result.find("{http://www.w3.org/2000/svg}rect").get(prop), "rgba(255,0,0,0.5)")

    def test_escaped_animation_properties_keep_keyframe_bindings(self) -> None:
        properties = (r'anim\61 tion', r'animation\2d name', r'-webkit-anim\61 tion',
                      r'\61 nimation-name', r'\000061nimation', r'ANIM\41 TION')
        for prop in properties:
            with self.subTest(prop=prop):
                value = 'pulse' if 'name' in prop else 'pulse 1s'
                html = '<style>@keyframes pulse {to {opacity:1}} .paint {' + prop + ':' + value + ';}</style>'
                html += '<svg viewBox="0 0 40 40"><rect class="paint" style="' + prop + ':' + value + '"/></svg>'
                result = self.mod.export_svg_document(html, Path('escaped-property.html'))
                self.assertIn(prop + ':' + value.replace('pulse', 'escaped-property-root-pulse'), embedded_css(result))
                shape = next(element for element in ET.fromstring(result).iter() if element.tag.endswith('}rect'))
                self.assertEqual(shape.get('style'), prop + ':' + value.replace('pulse', 'escaped-property-root-pulse'))
                self.assertIn('@keyframes escaped-property-root-pulse', embedded_css(result))

    def test_escaped_nested_animation_properties_are_refused(self) -> None:
        for prop in (r'anim\61 tion', r'animation\2d name', r'-webkit-anim\61 tion'):
            for nested in ('& {' + prop + ':pulse;}', '& {fill:red;} ' + prop + ':pulse;',
                           '@media print {' + prop + ':pulse;}'):
                with self.subTest(prop=prop, nested=nested):
                    html = '<style>@keyframes pulse {to {opacity:1}} .paint {' + nested + '}</style>'
                    html += '<svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
                    with self.assertRaisesRegex(ValueError, 'unsupported nested CSS animation declaration'):
                        self.mod.export_svg_document(html, Path('nested-escaped.html'))

    def test_escaped_svg_local_animation_properties_are_refused(self) -> None:
        for prop in (r'anim\61 tion', r'animation\2d name', r'-webkit-anim\61 tion'):
            with self.subTest(prop=prop):
                html = '<style>@keyframes pulse {to {opacity:1}}</style><svg viewBox="0 0 40 40">'
                html += '<style>.paint {' + prop + ':pulse;}</style><rect class="paint"/></svg>'
                with self.assertRaisesRegex(ValueError, 'unsupported SVG-local animation stylesheet'):
                    self.mod.export_svg_document(html, Path('local-escaped.html'))

    def test_animation_property_looking_literals_remain_literal(self) -> None:
        declaration = r'content:";anim\61 tion:pulse;";--anim\61 tion:pulse;anim\;ation:pulse;anim\:ation:pulse;fill:red;'
        html = '<style>@keyframes pulse {to {opacity:1}} .paint {' + declaration + '}</style>'
        html += '<svg viewBox="0 0 40 40"><style>.paint {' + declaration + '}</style><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(html, Path('literal-property.html'))
        self.assertIn(declaration, embedded_css(result))
        self.assertIn(declaration, result)

    def test_reserved_animation_values_stay_disabled_or_reset(self) -> None:
        for value in ("none", "inherit", "initial", "unset", "revert", "revert-layer"):
            with self.subTest(value=value):
                html = '<style>@keyframes "' + value + '" {to {opacity:1}}'
                html += '.paint {animation-name:' + value + '; animation:' + value + ';}'
                html += '</style><svg viewBox="0 0 40 40"><rect class="paint" style="animation-name:' + value + '"/></svg>'
                result = self.mod.export_svg_document(html, Path("reserved.html"))
                css = embedded_css(result)
                self.assertIn('animation-name:' + value + ';', css)
                self.assertIn('animation:' + value + ';', css)
                self.assertIn('style="animation-name:' + value + '"', result)
                self.assertIn('@keyframes "reserved-root-' + value + '"', css)
                self.assertEqual(self.mod._animation_declarations('animation-name:' + value.upper(), {value.upper():'prefixed'}), 'animation-name:' + value.upper())
                for quote in ('"', "'"):
                    body = 'animation-name:' + quote + value + quote + ';animation:' + quote + value + quote + ' 1s'
                    expected = 'animation-name:' + quote + 'reserved-' + value + quote + ';animation:' + quote + 'reserved-' + value + quote + ' 1s'
                    self.assertEqual(self.mod._animation_declarations(body, {value:'reserved-' + value}), expected)
        self.assertEqual(self.mod._animation_declarations('animation-name:linear', {'linear':'prefixed-linear'}), 'animation-name:prefixed-linear')
        self.assertEqual(self.mod._animation_declarations('animation:none 1s linear', {'none':'prefixed-none'}), 'animation:none 1s linear')

    def test_nested_animation_bindings_fail_clearly_before_export(self) -> None:
        for nested in ('& {animation:pulse 1s;}', '@media print {animation-name:pulse;}', '& { & { -webkit-animation:pulse 1s; } }'):
            with self.subTest(nested=nested):
                html = '<style>@keyframes pulse {to {opacity:1}} .paint {fill:red;' + nested + '}</style>'
                html += '<svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
                with self.assertRaisesRegex(ValueError, 'unsupported nested CSS animation declaration'):
                    self.mod.export_svg_document(html, Path("nested.html"))
        html = '<style>@keyframes pulse {to {opacity:1}} .paint {animation:pulse 1s; & {fill:red;content:"animation:pulse; { }";transform:translate(1px, 2px); animation:hover {fill:blue;} }}</style>'
        html += '<svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(html, Path("nested.html"))
        self.assertIn('animation:nested-root-pulse 1s', embedded_css(result))
        self.assertIn('content:"animation:pulse; { }"', embedded_css(result))
        self.assertIn('transform:translate(1px, 2px)', embedded_css(result))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'nested.html'
            output = Path(directory) / 'nested.svg'
            source.write_text(html.replace('fill:red;content:', 'animation:pulse 1s;content:'), encoding='utf-8')
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(self.mod.main([str(source), str(output)]), 2)
            self.assertFalse(output.exists())
            self.assertIn('unsupported nested CSS animation declaration', errors.getvalue())
            self.assertNotIn('Traceback', errors.getvalue())

    def test_animation_after_nested_block_is_refused(self) -> None:
        html = '<style>@keyframes pulse {to{opacity:1}} .paint { & {fill:red;} animation:pulse 1s; }</style><svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        with self.assertRaisesRegex(ValueError, 'unsupported nested CSS animation declaration'):
            self.mod.export_svg_document(html, Path("trailing.html"))

    def test_animation_between_nested_blocks_is_refused(self) -> None:
        html = '<style>@keyframes pulse {to{opacity:1}} .paint { & {fill:red;} animation:pulse 1s; & {stroke:blue;} }</style><svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        with self.assertRaisesRegex(ValueError, 'unsupported nested CSS animation declaration'):
            self.mod.export_svg_document(html, Path("middle.html"))

    def test_animation_before_nested_block_is_namespaced(self) -> None:
        html = '<style>@keyframes pulse {to{opacity:1}} .paint {animation:pulse 1s; & {fill:red;}}</style><svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(html, Path("prefix.html"))
        self.assertIn('animation:prefix-root-pulse 1s', embedded_css(result))

    def test_important_priority_is_not_a_keyframe_name(self) -> None:
        html = '<style>@keyframes pulse {to{opacity:1}} @keyframes important {to{opacity:0}} .paint {animation:pulse 1s !important;}</style><svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        result = self.mod.export_svg_document(html, Path("priority.html"))
        self.assertIn('animation:priority-root-pulse 1s !important', embedded_css(result))
        self.assertNotIn('!priority-root-important', result)

    def test_comment_prefixed_svg_local_animation_is_refused(self) -> None:
        html = '<style>@keyframes pulse {to{opacity:1}}</style><svg viewBox="0 0 40 40"><style>#paint {/*note*/animation:pulse 1s;}</style><rect id="paint"/></svg>'
        with self.assertRaisesRegex(ValueError, 'unsupported SVG-local animation stylesheet'):
            self.mod.export_svg_document(html, Path("local-comment.html"))

    def test_custom_property_value_blocks_are_not_nested_animation_rules(self) -> None:
        for value in ('{animation:pulse 1s;}', '{ .nested {animation-name:pulse;} }'):
            with self.subTest(value=value):
                html = '<style>@keyframes pulse {to {opacity:1}} .paint {'
                html += '--unused:' + value + ';fill:red;animation:pulse 1s;}</style>'
                html += '<svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
                result = self.mod.export_svg_document(html, Path("custom-block.html"))
                css = embedded_css(result)
                self.assertIn('--unused:' + value, css)
                self.assertIn('animation:custom-block-root-pulse 1s', css)
                ET.fromstring(result)
        html = '<style>@keyframes pulse {to {opacity:1}} .paint {'
        html += '--unused:{animation:pulse 1s;}; & {animation:pulse 1s;}}</style>'
        html += '<svg viewBox="0 0 40 40"><rect class="paint"/></svg>'
        with self.assertRaisesRegex(ValueError, 'unsupported nested CSS animation declaration'):
            self.mod.export_svg_document(html, Path("custom-block.html"))

    def test_nested_layer_statement_does_not_hide_animation_declaration(self) -> None:
        for declaration in ('animation:pulse 1s;', '-webkit-animation-name:pulse;'):
            with self.subTest(declaration=declaration), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'layer-gap.html'
                output = Path(directory) / 'layer-gap.svg'
                source.write_text(
                    '<style>@keyframes pulse {to{opacity:1}} .paint {&{@layer first,second;'
                    + declaration + '}}</style><svg viewBox="0 0 10 10"><rect class="paint"/></svg>',
                    encoding='utf-8',
                )
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    self.assertEqual(self.mod.main([str(source), str(output)]), 2)
                self.assertFalse(output.exists())
                self.assertIn('unsupported nested CSS animation declaration', errors.getvalue())
                self.assertNotIn('Traceback', errors.getvalue())

    def test_keyframes_and_bindings_are_scoped_together(self) -> None:
        html = '<style>@keyframes pulse {from {fill:#ff0000} to {fill:#ff0000}}'
        html += '@-webkit-keyframes other {to {opacity:1}}'
        html += '.paint {animation:pulse var(--duration) linear, other 2s; animation-name:"pulse", other; content:"pulse; other";}'
        html += '@media print {.paint {animation:none !important}}</style>'
        html += '<svg viewBox="0 0 40 40"><rect class="paint" style="animation-name:pulse"/></svg>'
        result = self.mod.export_svg_document(html, Path("frames.html"))
        css = embedded_css(result)
        self.assertIn('@keyframes frames-root-pulse { from {fill:#ff0000} to {fill:#ff0000} }', css)
        self.assertIn('@-webkit-keyframes frames-root-other', css)
        self.assertIn('animation:frames-root-pulse var(--duration) linear, frames-root-other 2s', css)
        self.assertIn('animation-name:"frames-root-pulse", frames-root-other', css)
        self.assertIn('content:"pulse; other"', css)
        self.assertIn('style="animation-name:frames-root-pulse"', result)
        self.assertIn('animation:none !important', css)
        self.assertEqual(self.mod._animation_declarations('animation:pulse 1s steps(2, end)', {'pulse':'frames-pulse','steps':'frames-steps'}), 'animation:frames-pulse 1s steps(2, end)')
        other = self.mod.export_svg_document(html, Path("second.html"))
        self.assertNotIn('frames-root-pulse', other)
        for value in ('var(--name)', 'pulse 1s, var(--other)'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'unresolved CSS animation name'):
                self.mod._animation_declarations(f'animation:{value}', {'pulse':'frames-root-pulse'})
        with self.assertRaisesRegex(ValueError, 'ambiguous CSS animation name'):
            self.mod._animation_declarations('animation:linear 1s', {'linear':'frames-root-linear'})
        with self.assertRaisesRegex(ValueError, 'unsupported SVG-local animation stylesheet'):
            self.mod.export_svg_document(html.replace('<rect', '<style>.paint {animation:pulse 1s}</style><rect'), Path("local.html"))

    def test_inline_animation_literals_decode_once_and_keep_comments(self) -> None:
        for attribute in ('style="animation:&quot;linear&quot; 1s both"', "style='animation:\"linear\" 1s both'"):
            html = '<style>@keyframes "linear" {to {fill:#ff0000}}</style>'
            html += f'<svg viewBox="0 0 40 40"><rect {attribute}/></svg>'
            result = self.mod.export_svg_document(html, Path("literal.html"))
            shape = ET.fromstring(result).find("{http://www.w3.org/2000/svg}rect")
            self.assertEqual(shape.get("style"), 'animation:"literal-root-linear" 1s both')
        html = '<style>@keyframes pulse {to {fill:#ff0000}}</style><svg viewBox="0 0 40 40">'
        html += '<rect style="/*note: retained;*/ animation-name:pulse; content:&quot;&amp;copy;&quot;"/></svg>'
        result = self.mod.export_svg_document(html, Path("comment.html"))
        shape = ET.fromstring(result).find("{http://www.w3.org/2000/svg}rect")
        self.assertEqual(shape.get("style"), '/*note: retained;*/ animation-name:comment-root-pulse; content:"&copy;"')
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

    def test_cli_carries_cdata_styles_after_root_rename(self) -> None:
        styles = (
            '<![CDATA[#original .paint { fill: red; }]]>',
            '<![CDATA[/* colors */ #original .paint { fill: red; }]]>'
            '<![CDATA[#original .outline { stroke: blue; }]]>',
            '#original .outline { stroke: blue; }'
            '<![CDATA[#original .paint { fill: red; }]]>',
        )
        for style in styles:
            with self.subTest(style=style), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "cdata.html"
                source.write_text(
                    '<svg id="original" viewBox="0 0 10 10">'
                    f'<style>{style}</style>'
                    '<rect class="paint outline" width="5" height="5"/></svg>',
                    encoding="utf-8",
                )
                self.assertEqual(self.mod.main([str(source), "--system-fonts"]), 0)
                document = ET.fromstring(source.with_suffix(".svg").read_text(encoding="utf-8"))
                carried = document.find(
                    "{http://www.w3.org/2000/svg}defs/{http://www.w3.org/2000/svg}style"
                ).text
                self.assertIn("#cdata-root .paint { fill: red; }", carried)
                self.assertNotIn("<![CDATA[", carried)
                self.assertNotIn("]]>", carried)
                if ".outline" in style:
                    self.assertIn("#cdata-root .outline { stroke: blue; }", carried)

    def test_html_style_cdata_looking_literal_is_not_unwrapped(self) -> None:
        diagram = '<svg viewBox="0 0 10 10"><rect class="paint"/></svg>'
        style = '<style>.paint::after { content: "<![CDATA[literal]]>"; }</style>'
        sources = (
            style + diagram,
            diagram + '<div title="<svg>"></div>' + style,
            diagram + "<div title='<svg>'></div>" + style,
            diagram + '<div title="before > <svg> after"></div>' + style,
            diagram + '<div data-example="<svg>">' + style + '</div>',
            *(diagram + f'<{tag}><svg></{tag}>' + style
              for tag in ("textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript")),
        )
        for html in sources:
            with self.subTest(html=html):
                carried = self.mod.diagram_css_from_html(html, "literal-root")
                self.assertIn('content: "&lt;![CDATA[literal]]>"', carried)
                with tempfile.TemporaryDirectory() as tmp:
                    source = Path(tmp) / "literal.html"
                    source.write_text(html, encoding="utf-8")
                    self.assertEqual(self.mod.main([str(source), "--system-fonts"]), 2)
                    self.assertFalse(source.with_suffix(".svg").exists())

    def test_html_text_elements_do_not_supply_svg_or_styles(self) -> None:
        diagram = '<svg id="real" viewBox="0 0 10 10"><rect/></svg>'
        for tag in ("textarea", "title", "xmp", "iframe", "noembed", "noframes", "noscript"):
            with self.subTest(tag=tag):
                html = (f'<{tag} title="before > after"><svg id="fake">'
                        '<style>.fake { fill: red; }</style></svg>'
                        f'</{tag}>' + diagram)
                self.assertEqual(self.mod.extract_first_svg(html), diagram)
                self.assertEqual(self.mod.diagram_css_from_html(html, "scope-root"), "")

    def test_foreign_object_textarea_does_not_change_style_namespace(self) -> None:
        html = ('<svg><foreignObject><textarea><svg></textarea><style>'
                '.paint::after { content: "<![CDATA[literal]]>"; }'
                '</style></foreignObject><style><![CDATA[.paint { fill:red }]]></style></svg>')
        carried = self.mod.diagram_css_from_html(html, "scope-root")
        self.assertIn('content: "&lt;![CDATA[literal]]>"', carried)
        self.assertIn("#scope-root .paint { fill:red }", carried)

    def test_foreign_object_html_style_is_not_unwrapped(self) -> None:
        html = ('<svg id="original" viewBox="0 0 10 10"><foreignObject>'
                '<div xmlns="http://www.w3.org/1999/xhtml"><style>'
                '#original .paint::after { content: "<![CDATA[literal]]>"; }'
                '</style></div></foreignObject></svg>')
        carried = self.mod.diagram_css_from_html(html, "literal-root", "original")
        self.assertIn('content: "&lt;![CDATA[literal]]>"', carried)
        # Preserve the existing refusal of invalid XML rather than silently
        # changing the HTML CSS string so the document can be exported.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "literal.html"
            source.write_text(html, encoding="utf-8")
            self.assertEqual(self.mod.main([str(source), "--system-fonts"]), 2)
            self.assertFalse(source.with_suffix(".svg").exists())

    def test_nested_svg_styles_inside_foreign_object_are_unwrapped(self) -> None:
        html = ('<svg id="original" viewBox="0 0 10 10"><foreignObject>'
                '<div xmlns="http://www.w3.org/1999/xhtml">'
                '<svg xmlns="http://www.w3.org/2000/svg"><style>'
                '<![CDATA[#original .paint { fill: red; }]]>'
                '</style><rect class="paint" width="5" height="5"/></svg>'
                '<style>.paint::after { content: "<![CDATA[literal]]>"; }</style>'
                '</div></foreignObject><style><![CDATA[.outline { stroke: blue; }]]></style></svg>')
        carried = self.mod.diagram_css_from_html(html, "nested-root", "original")
        self.assertIn("#nested-root .paint { fill: red; }", carried)
        self.assertIn('content: "&lt;![CDATA[literal]]>"', carried)
        self.assertIn("#nested-root .outline { stroke: blue; }", carried)
        valid_html = html.replace(
            '<style>.paint::after { content: "<![CDATA[literal]]>"; }</style>', "")
        exported = self.mod.export_svg_document(valid_html, Path("nested.html"), system_fonts=True)
        document = ET.fromstring(exported)
        carried_style = document.find(
            "{http://www.w3.org/2000/svg}defs/{http://www.w3.org/2000/svg}style"
        ).text
        self.assertIn("#nested-root .paint { fill: red; }", carried_style)
        self.assertIn("#nested-root .outline { stroke: blue; }", carried_style)

    def test_svg_html_integration_points_preserve_style_literals(self) -> None:
        for tag in ("foreignObject", "desc", "title"):
            with self.subTest(tag=tag):
                html = (f'<svg><{tag}><style>'
                        '.paint::after { content: "<![CDATA[literal]]>"; }'
                        f'</style></{tag}><style><![CDATA[.paint {{ fill:red }}]]></style></svg>')
                carried = self.mod.diagram_css_from_html(html, "scope-root")
                self.assertIn('content: "&lt;![CDATA[literal]]>"', carried)
                self.assertIn("#scope-root .paint { fill:red }", carried)

    def test_cli_carries_svg_styles_after_stray_closing_svg(self) -> None:
        html = ('<div></svg></div><svg id="original" viewBox="0 0 10 10">'
                '<style><![CDATA[#original .paint { fill: red; }]]></style>'
                '<rect class="paint" width="5" height="5"/></svg>')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "stray.html"
            source.write_text(html, encoding="utf-8")
            self.assertEqual(self.mod.main([str(source), "--system-fonts"]), 0)
            document = ET.fromstring(source.with_suffix(".svg").read_text(encoding="utf-8"))
            carried = document.find(
                "{http://www.w3.org/2000/svg}defs/{http://www.w3.org/2000/svg}style"
            ).text
            self.assertIn("#stray-root .paint { fill: red; }", carried)
            self.assertNotIn("&lt;![CDATA[", carried)

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

    def test_optional_defs_387_preserve_live_reusable_shape_ids(self) -> None:
        svg = '<svg><defs><path id="live" d="M0 0"/></defs><g id="dots"/><!-- <defs><pattern id="dots"/><g id="optional-shape"/></defs> --><use href="#live"/></svg>'
        result = self.mod.namespace_defs_ids(svg, "demo")
        self.assertIn('<g id="dots"/>', result)
        self.assertIn('<pattern id="demo-dots"/>', result)
        self.assertIn('<g id="optional-shape"/>', result)
        self.assertIn('<path id="demo-live"', result)
        self.assertIn('href="#demo-live"', result)

    def test_optional_defs_387_preserve_live_title_ids(self) -> None:
        svg = '<svg aria-labelledby="name"><title id="name">Title</title><!-- <defs><marker id="name"/></defs> --></svg>'
        self.assertEqual(self.mod.find_defs_ids(svg), ["name"])
        result = self.mod.namespace_defs_ids(svg, "demo")
        self.assertIn('aria-labelledby="name"><title id="name">Title</title>', result)
        self.assertIn('<marker id="demo-name"/>', result)

    def test_optional_defs_387_cdata_text_is_not_a_live_id_collision(self) -> None:
        svg = ('<svg viewBox="0 0 10 10"><metadata><![CDATA[<g id="dots"/>]]></metadata>'
               '<defs><!-- <pattern id="dots"><rect width="1" height="1"/></pattern> --></defs>'
               '<rect width="10" height="10" fill="url(#dots)"/></svg>')
        result = self.mod.export_svg_document(svg, Path("cdata-pattern.html"))
        self.assertIn('<![CDATA[<g id="dots"/>]]>', result)
        self.assertIn('<pattern id="cdata-pattern-dots">', result)
        root = ET.fromstring(result)
        rect = root.find("{http://www.w3.org/2000/svg}rect")
        self.assertEqual(rect.get("fill"), "url(#cdata-pattern-dots)")
        restored = ET.fromstring(result.replace('<!--', '').replace('-->', ''))
        pattern = restored.find('.//{http://www.w3.org/2000/svg}pattern')
        self.assertEqual(pattern.get('id'), 'cdata-pattern-dots')

    def test_optional_defs_387_opaque_delimiters_keep_real_id_ownership(self) -> None:
        for metadata in ('<![CDATA[<!-- literal]]>', '<!-- <![CDATA[ literal -->'):
            with self.subTest(metadata=metadata):
                svg = '<svg viewBox="0 0 10 10"><metadata>' + metadata + '</metadata>'
                svg += '<symbol id="dots"><rect width="1" height="1"/></symbol>'
                svg += '<defs><!-- <pattern id="dots"/> --></defs><use href="#dots"/></svg>'
                result = self.mod.export_svg_document(svg, Path("opaque-collision.html"))
                root = ET.fromstring(result)
                self.assertEqual(root.find('{http://www.w3.org/2000/svg}symbol').get('id'), 'dots')
                self.assertEqual(root.find('{http://www.w3.org/2000/svg}use').get('href'), '#dots')
                self.assertIn('<pattern id="opaque-collision-dots"/>', result)

    def test_optional_defs_387_live_collision_survives_actual_export(self) -> None:
        svg = ('<svg viewBox="0 0 10 10"><defs><!-- <pattern id="dot"/> --></defs>'
               '<symbol id="dot"><rect width="5" height="5" fill="red"/></symbol>'
               '<use href="#dot"/></svg>')
        result = self.mod.export_svg_document(svg, Path("b.html"))
        root = ET.fromstring(result)
        symbol = root.find("{http://www.w3.org/2000/svg}symbol")
        use = root.find("{http://www.w3.org/2000/svg}use")
        self.assertEqual(symbol.get("id"), "dot")
        self.assertEqual(use.get("href"), "#dot")
        self.assertIn('<pattern id="b-dot"/>', result)

    def test_optional_defs_387_collision_preserves_live_css_and_xlink(self) -> None:
        svg = ('<svg viewBox="0 0 10 10" xmlns:xlink="http://www.w3.org/1999/xlink">'
               '<defs><!-- <pattern id="dot"/><use href="#dot" fill="url(#dot)"/> --></defs>'
               '<symbol id="dot"><rect width="5" height="5"/></symbol>'
               '<use xlink:href="#dot" fill="url(#dot)" style="stroke:url(#dot)"/>'
               '<style>#dot {fill:url(#dot)}</style></svg>')
        result = self.mod.export_svg_document(svg, Path("b.html"))
        root = ET.fromstring(result)
        use = root.find("{http://www.w3.org/2000/svg}use")
        self.assertEqual(use.get("{http://www.w3.org/1999/xlink}href"), "#dot")
        self.assertEqual(use.get("fill"), "url(#dot)")
        self.assertEqual(use.get("style"), "stroke:url(#dot)")
        self.assertIn('#dot {fill:url(#dot)}', result)
        self.assertIn('<pattern id="b-dot"/><use href="#b-dot" fill="url(#b-dot)"/>', result)

    def test_optional_defs_387_comments_only_namespace_traditional_defs(self) -> None:
        traditional = ('marker', 'pattern', 'linearGradient', 'radialGradient',
                       'filter', 'clipPath', 'mask', 'symbol')
        optional = ''.join(f'<{tag} id="{tag}"/>' for tag in traditional)
        svg = ('<svg><defs><path id="live" d="M0 0"/></defs><!-- <defs>'
               + optional + '<path id="commented-path"/><g id="commented-group"/>'
               '</defs> --><use href="#live"/></svg>')
        result = self.mod.namespace_defs_ids(svg, "b")
        for tag in traditional:
            with self.subTest(tag=tag):
                self.assertIn(f'<{tag} id="b-{tag}"/>', result)
        self.assertIn('<path id="commented-path"/>', result)
        self.assertIn('<g id="commented-group"/>', result)
        self.assertIn('<path id="b-live"', result)
        self.assertIn('href="#b-live"', result)

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

    def test_escaped_selector_keeps_parent_alpha_from_overriding_child_paint(self) -> None:
        for selector in (r'.revenue\,net\31 foo', r'.revenue\2c net\31 foo'):
            with self.subTest(selector=selector):
                html = '<style>' + selector + ' {fill:blue}</style>'
                html += '<svg viewBox="0 0 10 10"><g fill="rgba(255,0,0,0.5)">'
                html += '<rect class="revenue,net1foo" width="10" height="10"/></g></svg>'
                result = self.mod.export_svg_document(html, Path("escaped-paint.html"))
                group = ET.fromstring(result).find('.//{http://www.w3.org/2000/svg}g')
                self.assertEqual(group.get('fill'), 'rgba(255,0,0,0.5)')
                self.assertIsNone(group.get('fill-opacity'))
        html = '<style>.other {fill:blue}</style>'
        html += '<svg viewBox="0 0 10 10"><g fill="rgba(255,0,0,0.5)">'
        html += '<rect class="paint" width="10" height="10"/></g></svg>'
        group = ET.fromstring(self.mod.export_svg_document(html, Path("ordinary-paint.html"))).find('.//{http://www.w3.org/2000/svg}g')
        self.assertEqual(group.get('fill'), '#ff0000')
        self.assertEqual(group.get('fill-opacity'), '0.5')

    def test_rgba_combines_existing_presentation_opacity(self) -> None:
        for prop in ("fill", "stroke"):
            for quote in ('"', "'"):
                for alpha, original, expected in (("0.5", "0.5", "0.25"), ("0.5", "50%", "0.25"), ("2", "0.5", "0.5")):
                    with self.subTest(prop=prop, quote=quote, alpha=alpha, opacity=original):
                        source = '<svg viewBox="0 0 40 40"><rect width="40" height="40" '
                        source += f'{prop}={quote}rgba(255,0,0,{alpha}){quote} {prop}-opacity="{original}"/></svg>'
                        result = self.mod.export_svg_document(source, Path("opacity.html"))
                        shape = ET.fromstring(result).find('{http://www.w3.org/2000/svg}rect')
                        self.assertEqual(shape.get(prop), '#ff0000')
                        self.assertEqual(shape.get(f'{prop}-opacity'), expected)
        source = '<svg viewBox="0 0 10 10"><text>fill="rgba(255,0,0,0.5)"</text>'
        source += '<!-- fill="rgba(255,0,0,0.5)" --><![CDATA[stroke="rgba(255,0,0,0.5)"]]>'
        source += '<rect data-fill="rgba(255,0,0,0.5)" fill="#ff0000"/></svg>'
        result = self.mod.export_svg_document(source, Path("inert.html"))
        self.assertIn('<text>fill="rgba(255,0,0,0.5)"</text>', result)
        self.assertIn('<!-- fill="rgba(255,0,0,0.5)" -->', result)
        self.assertIn('<![CDATA[stroke="rgba(255,0,0,0.5)"]]>', result)
        self.assertIn('data-fill="rgba(255,0,0,0.5)"', result)

    def test_conditional_diagram_css_retains_media_wrappers(self) -> None:
        html = '<style>.paint {fill: #ff0000;} @media print { .paint {fill: #0000ff;} '
        html += 'body {padding: 40px;} @media (min-width: 10px) {.edge {stroke: #00ff00;}} }</style>'
        html += '<svg viewBox="0 0 40 40"><rect class="paint" width="40" height="40"/></svg>'
        result = self.mod.export_svg_document(html, Path("media.html"))
        css = embedded_css(result)
        self.assertIn('@media print {', css)
        self.assertIn('@media (min-width: 10px) {', css)
        self.assertIn('#media-root .paint { fill: #0000ff; }', css)
        self.assertNotIn('padding', css)
        blocks = list(self.mod._css_blocks(css[css.index("');") + 3:]))
        self.assertEqual(blocks[0][0], '#media-root .paint')
        self.assertEqual(blocks[1][0], '@media print')
        self.assertIn('#media-root .paint', blocks[1][1])
        # Braces inside a string are not a nested block.
        css = self.mod.diagram_css_from_html('<style>.label {content: "{x}";}</style>', 'root')
        self.assertIn('content: "{x}"', css)
        warnings = io.StringIO()
        with contextlib.redirect_stderr(warnings):
            css = self.mod.diagram_css_from_html('<style>@unknown {.paint {fill: red;}}</style>', 'root')
        self.assertEqual(css, "@unknown {\n#root .paint { fill: red; }\n}")
        self.assertEqual(warnings.getvalue(), "")
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
                root = ET.fromstring(svg)
                for element in root.iter():
                    for paint in ("fill", "stroke"):
                        self.assertNotRegex(
                            element.get(paint, ""), r"(?i)^\s*rgba\(",
                            f"{source.name}: {paint} presentation paint must export without rgba",
                        )
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

    def test_nested_icon_svg_does_not_end_the_extraction(self) -> None:
        html = ('<p>intro</p><svg viewBox="0 0 100 50"><g><svg x="2" y="2" width="8" height="8" viewBox="0 0 8 8">'
                '<path d="M0 0h8v8z"/></svg><svg x="12" y="2" width="8" height="8"/></g>'
                '<rect id="after" width="10" height="10"/></svg><svg viewBox="0 0 1 1"><rect id="second"/></svg>')
        extracted = self.mod.extract_first_svg(html)
        self.assertTrue(extracted.startswith('<svg viewBox="0 0 100 50">'))
        self.assertTrue(extracted.endswith('<rect id="after" width="10" height="10"/></svg>'))
        self.assertNotIn('id="second"', extracted)
        root = ET.fromstring(self.mod.export_svg_document(html, Path("nested.html")))
        self.assertTrue(any(element.get("id") == "after" for element in root.iter()))

    def test_comments_with_double_hyphens_export_as_xml(self) -> None:
        html = ('<svg viewBox="0 0 10 10"><!-- focal -- and worse --><!-- trailing dash--->'
                '<!-- fine --><style><![CDATA[.a { --x: 1; }]]></style><rect class="a"/></svg>')
        svg = self.mod.export_svg_document(html, Path("comments.html"))
        ET.fromstring(svg)
        self.assertIn("<!-- fine -->", svg)
        self.assertIn("<!-- focal - - and worse -->", svg)
        self.assertIn("<!-- trailing dash- -->", svg)
        self.assertIn("<![CDATA[.a { --x: 1; }]]>", svg)
        for comment in re.findall(r"<!--(.*?)-->", svg, flags=re.DOTALL):
            self.assertNotIn("--", comment)
            self.assertFalse(comment.endswith("-"), comment)

    def test_svg_extraction_reads_quoted_attributes_and_whole_tag_names(self) -> None:
        html = ('<svg-icon name="x"></svg-icon><svg viewBox="0 0 9 9" aria-label="in/out />">'
                '<svg viewBox="0 0 8 8"><path id="icon"/></svg><rect id="after"/></svg>')
        extracted = self.mod.extract_first_svg(html)
        self.assertTrue(extracted.startswith('<svg viewBox="0 0 9 9"'), extracted)
        self.assertTrue(extracted.endswith('<rect id="after"/></svg>'), extracted)

    def test_comments_browsers_close_early_are_refused(self) -> None:
        for comment in ("<!-- a --!>", "<!-->", "<!--->"):
            html = '<svg viewBox="0 0 9 9">' + comment + '<rect id="live"/><!-- x --></svg>'
            with self.subTest(comment=comment), self.assertRaises(ValueError):
                self.mod.export_svg_document(html, Path("comment.html"))

    def test_known_unexportable_assets_are_refused_loudly(self) -> None:
        for name in sorted(KNOWN_UNEXPORTABLE):
            with self.subTest(name=name):
                source = ASSETS / name
                self.assertTrue(source.is_file(), f"{name} is listed but not shipped")
                with self.assertRaises(ValueError):
                    self.mod.export_svg_document(source.read_text(encoding="utf-8"), source)

    def test_deep_css_nesting_cli_fails_cleanly_without_output(self) -> None:
        css = "@media screen {" * 3000 + ".paint{fill:red}" + "}" * 3000
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "deep.html"
            output = Path(folder) / "deep.svg"
            source.write_text('<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>', encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                result = self.mod.main([str(source), str(output), "--system-fonts"])
            self.assertEqual(result, 2)
            self.assertIn("diagram CSS nesting", errors.getvalue())
            self.assertNotIn("Traceback", errors.getvalue())
            self.assertFalse(output.exists())

    def test_url_braces_are_value_text_in_css_rule_tree(self) -> None:
        for url in ("image{.png", "image}.png"):
            with self.subTest(url=url):
                css = f'@supports (background: url({url})) {{ .paint {{fill:red;}} }}'
                html = '<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
                rendered = self.mod.export_svg_document(html, Path("url-braces.html"), system_fonts=True)
                self.assertIn(css.split(" {")[0], rendered)
                self.assertIn('#url-braces-root .paint', rendered)
                self.assertIn('fill:red;', rendered)
                ET.fromstring(rendered)

    def test_unknown_css_group_nesting_scans_source_once(self) -> None:
        for depth in (200, 400):
            with self.subTest(depth=depth):
                css = "@foo {" * depth + '.paint{fill:red;content:"{;}"}' + "}" * depth
                html = '<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
                with patch.object(self.mod, "_css_rule_tree", wraps=self.mod._css_rule_tree) as scans, patch.object(self.mod, "_CssRule", wraps=self.mod._CssRule) as nodes:
                    rendered = self.mod.export_svg_document(html, Path("linear.html"), system_fonts=True)
                self.assertEqual(scans.call_count, 1)
                self.assertEqual(sum(len(call.args[0]) for call in scans.call_args_list), len(css))
                self.assertEqual(nodes.call_count, depth + 1)
                self.assertEqual(rendered.count("@foo"), depth)
                self.assertIn('#linear-root .paint', rendered)
                self.assertIn('content:"{;}"', rendered)
                ET.fromstring(rendered)

    def test_export_collects_keyframes_once_from_shared_css_tree(self) -> None:
        css = '@media screen{@foo{@font-face{font-family:Demo;src:url("font.woff2")}@keyframes spin{from{opacity:0}to{opacity:1}}.paint{fill:red;animation:spin 1s}}}@unknown{font-family:Demo}'
        html = '<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
        errors = io.StringIO()
        with patch.object(self.mod, "_keyframe_names", wraps=self.mod._keyframe_names) as names, contextlib.redirect_stderr(errors):
            rendered = self.mod.export_svg_document(html, Path("shared.html"))
        self.assertEqual(names.call_count, 1)
        self.assertIn('@font-face', rendered)
        self.assertIn('@keyframes shared-root-spin', rendered)
        self.assertIn('animation:shared-root-spin 1s', rendered)
        self.assertNotIn('@unknown', rendered)
        self.assertIn('dropping unsupported CSS block', errors.getvalue())
        ET.fromstring(rendered)

    def test_definition_only_css_groups_keep_fonts_and_keyframes(self) -> None:
        keyframes = '@keyframes pulse{from{opacity:0}to{opacity:1}}'
        font = '@font-face{font-family:Demo;src:url("demo.woff2")}'
        for wrapper in ('@scope (svg)', '@future'):
            for definition in (keyframes, font, '@nested {' + keyframes + font + '}'):
                with self.subTest(wrapper=wrapper, definition=definition):
                    css = wrapper + '{' + definition + '}.paint{fill:red;animation:pulse 1s;font-family:Demo}'
                    html = '<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
                    errors = io.StringIO()
                    with contextlib.redirect_stderr(errors):
                        rendered = self.mod.export_svg_document(html, Path("definitions.html"))
                    self.assertIn(wrapper, rendered)
                    self.assertEqual(errors.getvalue(), "")
                    if keyframes in definition:
                        self.assertIn('@keyframes definitions-root-pulse', rendered)
                        self.assertIn('animation:definitions-root-pulse 1s', rendered)
                    if font in definition:
                        self.assertIn('@font-face', rendered)
                        system_fonts = self.mod.export_svg_document(html, Path("definitions.html"), system_fonts=True)
                        self.assertNotIn('@font-face', system_fonts)
                    ET.fromstring(rendered)
        html = '<style>@future{font-family:Demo}.paint{fill:red}</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            rendered = self.mod.export_svg_document(html, Path("declarations.html"))
        self.assertNotIn('@future', rendered)
        self.assertIn('dropping unsupported CSS block', errors.getvalue())

    def test_scoped_paint_fails_cleanly_before_output(self) -> None:
        for css in ('@scope (#original) {.paint{fill:red}}', '@scope (#original) {@scope (.zone) {.paint{fill:red}}}', '@scope (#\\6f riginal) to ([data-label="brace}"]) {.paint{content:"brace}";fill:red}}'):
            with self.subTest(css=css), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / "scope.html"
                output = Path(folder) / "scope.svg"
                source.write_text('<style>' + css + '</style><svg id="original" viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>', encoding="utf-8")
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                    status = self.mod.main([str(source), str(output), "--system-fonts"])
                self.assertEqual(status, 2)
                self.assertIn("unsupported CSS scope with paint rules", errors.getvalue())
                self.assertNotIn("Traceback", errors.getvalue())
                self.assertFalse(output.exists())

    def test_layer_order_statements_survive_with_important_blocks(self) -> None:
        css = '@layer second, first; @layer first { .paint {fill:red!important} } @layer second { .paint {fill:blue!important} }'
        html = '<style>' + css + '</style><svg viewBox="0 0 10 10"><rect class="paint" width="5" height="5"/></svg>'
        exported = self.mod.export_svg_document(html, Path("layers.html"), system_fonts=True)
        self.assertIn('@layer second, first;', exported)
        self.assertLess(exported.index('@layer second, first;'), exported.index('@layer first {'))
        self.assertLess(exported.index('@layer first {'), exported.index('@layer second {'))
        self.assertIn('fill:red!important', exported)
        self.assertIn('fill:blue!important', exported)
        nested = self.mod.diagram_css_from_html('<style>@media screen {@layer second, first; @layer first {.paint{fill:red}}}</style>', 'layers-root')
        self.assertIn('@media screen {\n@layer second, first;', nested)
        ET.fromstring(exported)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportSvgStandaloneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
