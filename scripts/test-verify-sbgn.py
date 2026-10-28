#!/usr/bin/env python3
"""Adversarial and legal SBGN fixtures (ADR 0005).

Run: python3 scripts/test-verify-sbgn.py
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-sbgn.py"
SPEC = importlib.util.spec_from_file_location("sbgn_verifier", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def fixture():
    return """<html><body>
<svg data-diagram="sbgn" viewBox="0 0 400 200">
  <rect data-kind="compartment" data-compartment-id="cyt" data-role="bounds"
        x="16" y="16" width="368" height="168" rx="8"/>
  <g data-kind="macromolecule" data-entity-id="a" data-compartment="cyt">
    <rect data-role="bounds" x="32" y="40" width="80" height="40" rx="16"/>
  </g>
  <g data-kind="process" data-process-id="p" data-compartment="cyt">
    <rect data-role="bounds" x="160" y="44" width="32" height="32" rx="2"/>
  </g>
  <g data-kind="macromolecule" data-entity-id="b" data-compartment="cyt">
    <rect data-role="bounds" x="240" y="40" width="80" height="40" rx="16"/>
  </g>
  <path data-kind="consumption" data-from="a" data-to="p" d="M 112,60 H 160"/>
  <path data-kind="production" data-from="p" data-to="b" d="M 192,60 H 240"/>
</svg></body></html>
"""


GOOD = fixture()
SYNTHETIC_PATH = Path("synthetic-sbgn.html")


class ContractTests(unittest.TestCase):
    def clean(self, source):
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])

    def rejects(self, source, reason):
        self.assertNotEqual(source, GOOD, "fixture mutation did not apply")
        findings = checker.check_source(SYNTHETIC_PATH, source)
        self.assertTrue(findings, "invalid diagram accepted")
        self.assertIn(reason, "\n".join(findings))

    def test_synthetic_is_clean(self):
        self.clean(GOOD)

    def test_files_without_diagram_are_skipped(self):
        source = GOOD.replace('data-diagram="sbgn"', "")
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])
        self.assertFalse(checker.looks_like_sbgn(source))

    def test_comments_and_unquoted(self):
        source = GOOD.replace("</svg>", "<!-- <g data-entity-id=\"bogus\"/> --></svg>")
        source = source.replace('data-kind="compartment"', "DATA-KIND=compartment")
        self.clean(source)

    def test_duplicate_id(self):
        self.rejects(GOOD.replace('data-entity-id="a"', 'data-entity-id="b"', 1), "duplicate ID")

    def test_species_process_share_namespace(self):
        self.rejects(GOOD.replace('data-process-id="p"', 'data-process-id="a"', 1), "duplicate ID")

    def test_consumption_must_be_species_to_process(self):
        self.rejects(GOOD.replace('data-from="a" data-to="p"', 'data-from="p" data-to="a"', 1),
                     "consumption must run species → process")

    def test_production_must_be_process_to_species(self):
        self.rejects(GOOD.replace('data-from="p" data-to="b"', 'data-from="a" data-to="b"', 1),
                     "production must run process → species")

    def test_modulation_and_reversible(self):
        source = GOOD.replace(
            "</svg>",
            '<path data-kind="modulation" data-from="a" data-to="p" d="M 112,80 H 160"/>'
            '<path data-kind="reversible" data-from="b" data-to="p" d="M 240,80 H 192"/></svg>',
        )
        self.clean(source)
        self.rejects(GOOD.replace("</svg>",
                                  '<path data-kind="modulation" data-from="p" data-to="a" d="M 192,80 H 112"/></svg>'),
                     "modulation must run species → process")
        self.rejects(GOOD.replace("</svg>",
                                  '<path data-kind="reversible" data-from="a" data-to="b" d="M 112,80 H 240"/></svg>'),
                     "reversible must join a species and a process")

    def test_misspelled_arc_kind_is_rejected(self):
        # A typo used to skip every endpoint check, so a species-to-species
        # arc passed as long as its kind was misspelled.
        self.rejects(GOOD.replace('data-kind="consumption" data-from="a" data-to="p"',
                                  'data-kind="consumtion" data-from="a" data-to="b"', 1),
                     'arc data-kind "consumtion" must be one of')

    def test_missing_arc_kind_is_rejected(self):
        self.rejects(GOOD.replace('data-kind="consumption" data-from="a" data-to="p"',
                                  'data-from="a" data-to="b"', 1),
                     "arc data-kind is missing")
        self.rejects(GOOD.replace("</svg>", '<path data-to="b" d="M 112,80 H 240"/></svg>'),
                     "arc data-kind is missing")

    def test_unknown_glyph_kind_is_rejected(self):
        # A misspelled glyph kind would drop the glyph from the budget and
        # containment checks without a finding.
        self.rejects(GOOD.replace('data-kind="macromolecule" data-entity-id="b"',
                                  'data-kind="macromolecul" data-entity-id="b"', 1),
                     'unknown data-kind "macromolecul"')

    def test_transform_attribute_on_glyph_is_rejected(self):
        # Valid bounds plus a translate draw the glyph outside its compartment.
        moved = GOOD.replace('data-entity-id="b" data-compartment="cyt">',
                             'data-entity-id="b" data-compartment="cyt" transform="translate(400,0)">', 1)
        self.rejects(moved, "transform attribute")
        bounds = GOOD.replace('<rect data-role="bounds" x="240" y="40"',
                              '<rect data-role="bounds" transform="translate(400,0)" x="240" y="40"', 1)
        self.rejects(bounds, "transform attribute")

    def test_positional_inline_style_on_glyph_is_rejected(self):
        for style in ("transform: translate(400px, 0)", "translate: 400px 0",
                      "x: 400px", "width: 800px"):
            with self.subTest(style=style):
                moved = GOOD.replace('data-entity-id="b" data-compartment="cyt">',
                                     f'data-entity-id="b" data-compartment="cyt" style="{style}">', 1)
                self.rejects(moved, "inline style")
        bounds = GOOD.replace('<rect data-role="bounds" x="240" y="40"',
                              '<rect data-role="bounds" style="TRANSFORM:translate(400px,0)" x="240" y="40"', 1)
        self.rejects(bounds, "inline style")

    def test_harmless_inline_style_is_clean(self):
        self.clean(GOOD.replace('data-entity-id="b" data-compartment="cyt">',
                                'data-entity-id="b" data-compartment="cyt" style="opacity: 0.9">', 1))

    def test_transform_on_ancestor_group_is_rejected(self):
        start = '<g data-kind="macromolecule" data-entity-id="b"'
        wrapped = GOOD.replace(start, '<g transform="translate(400,0)">' + start, 1)
        wrapped = wrapped.replace('  <path data-kind="consumption"', '</g>\n  <path data-kind="consumption"', 1)
        self.rejects(wrapped, "transform attribute")
        styled = GOOD.replace(start, '<g style="transform: translateX(400px)">' + start, 1)
        styled = styled.replace('  <path data-kind="consumption"', '</g>\n  <path data-kind="consumption"', 1)
        self.rejects(styled, "inline style")

    def test_nested_svg_ancestor_is_rejected(self):
        start = '<g data-kind="macromolecule" data-entity-id="b"'
        nested = GOOD.replace(start, '<svg x="400">' + start, 1)
        nested = nested.replace('  <path data-kind="consumption"', '</svg>\n  <path data-kind="consumption"', 1)
        self.rejects(nested, "nested <svg>")

    def test_positional_stylesheet_rule_is_rejected(self):
        for rule in ("rect { transform: translate(400px, 0); }",
                     '[data-entity-id="b"] { translate: 400px 0; }',
                     "svg g > rect { x: 400px; }",
                     ":is(rect, circle) { transform: scale(2); }",
                     "\\72 ect { transform: translate(400px, 0); }"):
            with self.subTest(rule=rule):
                source = GOOD.replace("<html><body>", f"<html><head><style>{rule}</style></head><body>", 1)
                self.rejects(source, "stylesheet")

    def test_page_stylesheet_is_clean(self):
        page = ("svg { width: 100%; min-width: 1000px; display: block; }"
                ".eyebrow { text-transform: uppercase; } .frame { max-width: 1200px; width: 100%; }"
                'div[class="g"] { width: 100%; }')
        self.clean(GOOD.replace("<html><body>", f"<html><head><style>{page}</style></head><body>", 1))

    def test_rules_that_cannot_match_a_glyph_are_clean(self):
        # The selector is matched against each glyph's real ancestor chain,
        # so page rules whose ancestors or root never match are not findings.
        for rule in (":root { height: 100%; }",
                     ".card rect { x: 0; }",
                     "#nothere g { transform: translate(5px, 0); }",
                     "svg { width: 100%; }",
                     "html, body { height: 100%; }",
                     '[data-name="a, b"], .frame { width: 3px; }',
                     "body > rect { transform: scale(2); }",
                     "rect::before { transform: scale(2); }"):
            with self.subTest(rule=rule):
                self.clean(GOOD.replace("<html><body>", f"<html><head><style>{rule}</style></head><body>", 1))

    def test_rules_that_match_through_real_ancestors_are_rejected(self):
        wrapped = GOOD.replace("<body>", '<body><div class="card" id="here">', 1).replace("</svg>", "</svg></div>", 1)
        for rule in (".card g { transform: translate(5px, 0); }",
                     "div.card > svg rect { x: 0; }",
                     "#here [data-kind=macromolecule] { translate: 5px 0; }",
                     ":root g { rotate: 5deg; }",
                     "body .card rect:hover { transform: none; }",
                     "div + rect, p { width: 9px; }"):
            with self.subTest(rule=rule):
                source = wrapped.replace("<html><body>", f"<html><head><style>{rule}</style></head><body>", 1)
                self.rejects(source, "stylesheet")

    def test_undeclared_connector_is_rejected(self):
        # Stripping the arc attributes used to hide a species-to-species
        # arrow from every check.
        for drawn in ('<path d="M 112,60 H 240" marker-end="url(#arrow)"/>',
                      '<line x1="112" y1="60" x2="240" y2="60"/>',
                      '<polyline points="112,60 240,60"/>',
                      '<use href="#shared-arc"/>'):
            with self.subTest(drawn=drawn):
                self.rejects(GOOD.replace("</svg>", drawn + "</svg>"), "declares no arc")
        stripped = GOOD.replace('<path data-kind="consumption" data-from="a" data-to="p" d="M 112,60 H 160"/>',
                                '<path d="M 112,60 H 240"/>', 1)
        self.rejects(stripped, "declares no arc")

    def test_marker_defs_and_glyph_parts_are_not_connectors(self):
        source = GOOD.replace(
            '<svg data-diagram="sbgn" viewBox="0 0 400 200">',
            '<svg data-diagram="sbgn" viewBox="0 0 400 200"><defs><marker id="arrow">'
            '<polygon points="0 0, 8 3, 0 6"/></marker></defs>', 1,
        ).replace(
            "</svg>",
            '<g data-kind="source-sink" data-entity-id="src" data-compartment="cyt">'
            '<rect data-role="bounds" x="32" y="120" width="24" height="24"/>'
            '<circle cx="44" cy="132" r="12"/><line x1="32" y1="144" x2="56" y2="120"/></g>'
            '<path data-kind="consumption" data-from="src" data-to="p" d="M 56,132 H 160"/></svg>',
        )
        self.clean(source)

    def test_legend_samples_are_documented_exceptions(self):
        legend = ('<g data-role="legend"><line x1="32" y1="176" x2="60" y2="176" marker-end="url(#arrow)"/>'
                  '<rect x="80" y="170" width="28" height="12"/><text x="116" y="179">Arc</text></g></svg>')
        self.clean(GOOD.replace("</svg>", legend))
        touching = legend.replace('x1="32" y1="176" x2="60" y2="176"', 'x1="112" y1="60" x2="240" y2="60"')
        self.rejects(GOOD.replace("</svg>", touching), "legend sample")
        path = legend.replace('<line x1="32" y1="176" x2="60" y2="176"', '<path d="M 32,176 H 60"')
        self.rejects(GOOD.replace("</svg>", path), "legend samples use")
        moved = legend.replace('<g data-role="legend">', '<g data-role="legend" transform="translate(0,-120)">')
        self.rejects(GOOD.replace("</svg>", moved), "transform attribute")

    def test_crossing_arcs_are_rejected(self):
        # Two same-colour strokes crossing with no gap read as a junction.
        crossing = ('<path data-kind="modulation" data-from="a" data-to="p" d="M 120,100 H 172"/>'
                    '<path data-kind="modulation" data-from="b" data-to="p" d="M 140,90 V 112"/></svg>')
        self.rejects(GOOD.replace("</svg>", crossing), "cross at (140, 100)")
        curved = crossing.replace('d="M 140,90 V 112"', 'd="M 248,80 H 148 Q 140,80 140,88 V 112"')
        self.rejects(GOOD.replace("</svg>", curved), "cross at (140, 100)")

    def test_moved_arcs_are_rejected(self):
        # Greptile P1 on #402: the crossing check reads raw path data, so a
        # transform or positional CSS could draw an unbridged crossing at
        # (140, 100) that the measured routes never show.
        apart = ('<path data-kind="modulation" data-from="a" data-to="p" d="M 120,100 H 172"/>'
                 '<path data-kind="modulation" data-from="b" data-to="p" d="M 140,128 V 148"/></svg>')
        self.clean(GOOD.replace("</svg>", apart))
        second = '<path data-kind="modulation" data-from="b"'
        moved = apart.replace(second, second + ' transform="translate(0,-30)"', 1)
        self.rejects(GOOD.replace("</svg>", moved), "transform attribute")
        styled = apart.replace(second, second + ' style="translate: 0 -30px"', 1)
        self.rejects(GOOD.replace("</svg>", styled), "inline style")
        grouped = apart.replace(second, '<g transform="translate(0,-30)">' + second, 1)
        grouped = grouped.replace("</svg>", "</g></svg>", 1)
        self.rejects(GOOD.replace("</svg>", grouped), "ancestor <g> of arc b to p")
        sheet = GOOD.replace("<html><body>", "<html><head><style>path { transform: translateY(-30px); }"
                                              "</style></head><body>", 1)
        self.rejects(sheet.replace("</svg>", apart), "stylesheet")

    def test_bridged_crossing_is_clean(self):
        # The hop from type-architecture.md leaves a gap at the crossing.
        bridged = ('<path data-kind="modulation" data-from="a" data-to="p" '
                   'd="M 120,100 H 132 a 8,8 0 0,1 16,0 H 172"/>'
                   '<path data-kind="modulation" data-from="b" data-to="p" d="M 140,90 V 112"/></svg>')
        self.clean(GOOD.replace("</svg>", bridged))

    def test_arc_ending_on_another_arc_is_rejected(self):
        touching = ('<path data-kind="modulation" data-from="a" data-to="p" d="M 120,100 H 172"/>'
                    '<path data-kind="modulation" data-from="b" data-to="p" d="M 140,120 V 100"/></svg>')
        self.rejects(GOOD.replace("</svg>", touching), "ends on arc")

    def test_overlapping_arcs_are_rejected(self):
        stacked = ('<path data-kind="modulation" data-from="a" data-to="p" d="M 120,100 H 172"/>'
                   '<path data-kind="modulation" data-from="b" data-to="p" d="M 150,100 H 190"/></svg>')
        self.rejects(GOOD.replace("</svg>", stacked), "overlap")

    def test_unreadable_arc_path_is_rejected(self):
        self.rejects(GOOD.replace('d="M 112,60 H 160"', 'd="M 112,60 X 160"', 1), "path data")

    def arcs(self, *paths):
        """GOOD plus modulation arcs (a species to process p) with these d values."""
        drawn = "".join(f'<path data-kind="modulation" data-from="a" data-to="p" d="{d}"/>' for d in paths)
        return GOOD.replace("</svg>", drawn + "</svg>")

    def test_crossing_on_a_quadratic_curve_is_rejected(self):
        # The drawn curve passes (138, 102); lines through its control points do not.
        self.rejects(self.arcs("M 120,100 H 132 Q 140,100 140,108 V 120", "M 134,102 H 139"),
                     "cross at (138, 102)")

    def test_crossing_on_a_cubic_curve_is_rejected(self):
        self.rejects(self.arcs("M 120,100 C 140,100 140,100 140,120", "M 130,104 H 150"), "cross at")
        self.rejects(self.arcs("M 120,100 C 140,100 140,100 140,120", "M 130,104 h 20"), "cross at")

    def test_crossing_at_an_internal_vertex_is_rejected(self):
        # Neither segment pair crosses strictly: the vertical meets the joint.
        self.rejects(self.arcs("M 120,100 H 140 H 172", "M 140,90 V 112"), "cross at (140, 100)")

    def test_touch_at_internal_vertices_is_rejected(self):
        self.rejects(self.arcs("M 120,100 H 140 V 120", "M 132,92 L 140,100 L 148,92"), "cross at (140, 100)")

    def test_route_over_a_hop_top_is_rejected(self):
        hop = "M 120,100 H 132 a 8,8 0 0,1 16,0 H 172"
        self.clean(self.arcs(hop, "M 140,90 V 112"))
        # A third route touching the hop's arc voids the exemption.
        self.rejects(self.arcs(hop, "M 140,90 V 112", "M 130,93 H 137"), "cross at")
        # A hop that bridges two routes at once is not the documented hop.
        self.rejects(self.arcs(hop, "M 138,90 V 112", "M 142,90 V 112"), "cross at")
        # A route crossing the hop's top without passing under it gets no exemption.
        self.rejects(self.arcs(hop, "M 130,93 H 137"), "cross at")

    def test_routes_meeting_at_a_shared_glyph_port_are_clean(self):
        self.clean(self.arcs("M 176,120 V 76", "M 200,100 L 176,76"))
        # The same meeting point away from any glyph reads as a junction.
        self.rejects(self.arcs("M 176,140 V 110", "M 200,130 L 176,110"), "away from a glyph port")

    def test_near_miss_parallel_routes_are_clean(self):
        self.clean(self.arcs("M 120,100 H 172", "M 120,102 H 172"))

    def test_unsupported_path_command_fails_closed(self):
        self.rejects(self.arcs("M 120,100 B 140,100"), "path data")
        self.rejects(self.arcs("M 120,100 a 8,8 0 2,1 16,0"), "path data")

    def test_source_sink_is_species(self):
        source = GOOD.replace(
            "</svg>",
            '<g data-kind="source-sink" data-entity-id="src" data-compartment="cyt">'
            '<rect data-role="bounds" x="32" y="120" width="24" height="24"/>'
            "</g>"
            '<path data-kind="consumption" data-from="src" data-to="p" d="M 56,132 H 160"/></svg>',
        )
        self.clean(source)

    def test_outside_compartment(self):
        self.rejects(GOOD.replace('x="32" y="40" width="80" height="40"',
                                  'x="0" y="40" width="80" height="40"', 1),
                     "not geometrically inside compartment")

    def test_bounds_must_be_a_rect(self):
        # A circle's x/y/width/height are unused, so it would be measured at
        # one place and drawn at another.
        circle = GOOD.replace('<rect data-role="bounds" x="240" y="40" width="80" height="40" rx="16"/>',
                              '<circle data-role="bounds" cx="500" cy="60" r="20" '
                              'x="240" y="40" width="80" height="40"/>', 1)
        self.rejects(circle, "bounds must be a <rect>")
        compartment = GOOD.replace('<rect data-kind="compartment"', '<ellipse data-kind="compartment"', 1)
        self.rejects(compartment, "bounds must be a <rect>")
        carrier = GOOD.replace('<g data-kind="macromolecule" data-entity-id="b" data-compartment="cyt">\n'
                               '    <rect data-role="bounds" x="240" y="40" width="80" height="40" rx="16"/>\n  </g>',
                               '<image data-kind="macromolecule" data-entity-id="b" data-compartment="cyt" '
                               'x="240" y="40" width="80" height="40"/>', 1)
        self.rejects(carrier, "bounds")

    def test_missing_compartment_ref(self):
        self.rejects(GOOD.replace('data-compartment="cyt"', 'data-compartment="missing"', 1),
                     "data-compartment must name a compartment")

    def test_off_grid(self):
        self.rejects(GOOD.replace('x="32" y="40"', 'x="33" y="40"'), "4px grid")

    def test_duplicate_attributes(self):
        self.rejects(GOOD.replace('data-entity-id="a"', 'data-entity-id="a" DATA-ENTITY-ID="ignored"', 1),
                     "duplicate attributes")

    def test_budget(self):
        extra = GOOD.replace("</svg>", "".join(
            f'<g data-kind="macromolecule" data-entity-id="m{i}" data-compartment="cyt">'
            f'<rect data-role="bounds" x="32" y="40" width="80" height="40"/></g>'
            for i in range(6)
        ) + "</svg>")
        self.rejects(extra, "macromolecule budget")

    def test_arc_budget(self):
        arcs = "".join(f'<path data-kind="modulation" data-from="a" data-to="p" d="M 112,{64 + 4 * i} H 160"/>'
                       for i in range(checker.MAX_ARC - 2))  # GOOD already draws two arcs
        self.clean(GOOD.replace("</svg>", arcs + "</svg>"))
        extra = arcs + '<path data-kind="modulation" data-from="b" data-to="p" d="M 240,72 H 192"/>'
        self.rejects(GOOD.replace("</svg>", extra + "</svg>"), f"arc budget is {checker.MAX_ARC}")

    def test_budget_docs_agree_with_checker(self):
        # SBGN replaces the shared 9 node / 12 arrow rows, so the shared
        # budget page must say so and carry the checker's numbers.
        budget = (ROOT / "skills/diagram-design/references/layout-budget.md").read_text(encoding="utf-8")
        ceiling = (f"{checker.MAX_MACRO} / {checker.MAX_PROCESS} / {checker.MAX_COMPARTMENT} / "
                   f"{checker.MAX_SOURCE} / {checker.MAX_ARC}")
        rows = [line for line in budget.splitlines() if line.startswith("|") and "(SBGN)" in line]
        self.assertEqual(len(rows), 1, "layout-budget.md needs exactly one SBGN row")
        self.assertIn(ceiling, rows[0])
        intro = budget.split("| Limit | Rule |")[0]
        self.assertRegex(intro, r"SBGN[^.]*replaces[^.]*9 nodes[^.]*12 arrows")
        reference = (ROOT / "skills/diagram-design/references/type-sbgn.md").read_text(encoding="utf-8")
        section = reference.split("## Budget", 1)[1].split("\n## ", 1)[0]
        for phrase in (f"≤{checker.MAX_MACRO} macromolecules", f"≤{checker.MAX_PROCESS} processes",
                       f"≤{checker.MAX_COMPARTMENT} compartment", f"≤{checker.MAX_SOURCE} source/sink",
                       f"≤{checker.MAX_ARC} arcs"):
            self.assertIn(phrase, section)

    def test_all_shipped_variants(self):
        for suffix in ("", "-dark", "-full"):
            path = ROOT / f"skills/diagram-design/assets/example-sbgn{suffix}.html"
            with self.subTest(variant=suffix):
                self.assertTrue(path.is_file(), f"missing shipped variant: {path.name}")
                source = path.read_text(encoding="utf-8")
                self.assertEqual(checker.check_source(path, source), [])
                self.assertIn('data-diagram="sbgn"', source)
                self.assertIn('data-kind="macromolecule"', source)
                self.assertIn('data-kind="process"', source)
                self.assertIn('data-kind="compartment"', source)

    def test_shipped_compartment_label_uses_soft_token(self):
        # The compartment name is a boundary label, so it takes the skin's
        # opaque soft role (style-guide.md), not ink at 40% opacity.
        soft = {"": "#5a6580", "-dark": "#949eb2", "-full": "#5a6580"}
        for suffix, color in soft.items():
            path = ROOT / f"skills/diagram-design/assets/example-sbgn{suffix}.html"
            with self.subTest(variant=suffix):
                source = path.read_text(encoding="utf-8")
                labels = re.findall(r"<text\b([^>]*)>\s*CYTOSOL\s*</text>", source)
                self.assertEqual(len(labels), 1, "expected one CYTOSOL compartment label")
                fill = re.search(r'\bfill="([^"]*)"', labels[0])
                self.assertIsNotNone(fill, "compartment label has no fill")
                self.assertEqual(fill.group(1).lower(), color)
                self.assertNotRegex(labels[0], r"\b(?:fill-)?opacity=")

    def test_shipped_text_is_opaque(self):
        for suffix in ("", "-dark", "-full"):
            path = ROOT / f"skills/diagram-design/assets/example-sbgn{suffix}.html"
            with self.subTest(variant=suffix):
                source = path.read_text(encoding="utf-8")
                for attrs in re.findall(r"<text\b([^>]*)>", source):
                    self.assertNotRegex(attrs, r'fill="rgba\(', f"translucent text: {attrs.strip()}")

    def test_cli_discovery_and_failures(self):
        env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        for args in ([], ["--all"]):
            result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("3 file(s)", result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "diagram.html"
            path.write_text(GOOD, encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            path.write_text(GOOD.replace('data-from="a"', 'data-from="p"', 1), encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1)
            path.unlink()
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
