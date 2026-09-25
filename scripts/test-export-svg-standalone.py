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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "skills/diagram-design/scripts/export_svg.py"
EXPORT_MD = ROOT / "skills/diagram-design/references/export.md"
ASSETS = ROOT / "skills/diagram-design/assets"


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


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportSvgStandaloneTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
