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
        with self.assertRaises(ValueError):
            self.mod.export_svg_document(
                html, Path("orphan-station.html"), font_canary=True
            )
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
