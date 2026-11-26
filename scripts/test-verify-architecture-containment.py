#!/usr/bin/env python3
"""Adversarial and legal Architecture containment fixtures (ADR 0005).

Synthetic fixtures exercise the public contract independently of the shipped
layout; all three published variants and CLI discovery are checked as well.
Run: python3 scripts/test-verify-architecture-containment.py
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
CHECKER = ROOT / "scripts/verify-architecture-containment.py"
SPEC = importlib.util.spec_from_file_location("architecture_containment_verifier", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def scope(identity, kind, x, y, w, h, parent=None, rx=None, dashed=None):
    if rx is None:
        rx = 4 if kind == "admin" else 8
    if dashed is None:
        dashed = kind == "admin"
    parent_attr = f' data-parent="{parent}"' if parent else ""
    dash_attr = ' stroke-dasharray="4,4"' if dashed else ""
    return (f'<rect data-role="bounds" data-scope-id="{identity}" data-scope-kind="{kind}"'
            f'{parent_attr} x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"'
            f' fill="none" stroke="#000"{dash_attr}/>')


def node(identity, kind, x, y, parent, target=None, size=40):
    target_attr = f' data-target="{target}"' if target else ""
    return (f'<g data-node-id="{identity}" data-kind="{kind}" data-parent="{parent}"{target_attr}>'
            f'<rect data-role="bounds" x="{x}" y="{y}" width="{size}" height="{size}"/>'
            f'<text>{identity}</text></g>')


def fixture():
    parts = [
        '<html><head><style>svg {width:100%;height:auto} body {margin:0}</style></head><body>',
        '<svg data-grammar="architecture-containment" viewBox="0 0 400 280">',
        scope("subscription", "admin", 16, 16, 368, 248),
        scope("rg", "admin", 24, 24, 352, 232, parent="subscription"),
        scope("hub", "traffic", 32, 88, 160, 144, parent="rg"),
        scope("spoke", "traffic", 208, 88, 160, 144, parent="rg"),
        node("sql", "managed", 32, 36, "rg"),
        node("app", "compute", 56, 144, "hub"),
        node("pe", "endpoint", 232, 144, "spoke", target="sql"),
        '<line data-peering="hub-spoke" data-from="hub" data-to="spoke" x1="192" y1="112" x2="208" y2="112"/>',
        "</svg></body></html>",
    ]
    return "\n".join(parts)


GOOD = fixture()
SYNTHETIC_PATH = Path("synthetic-architecture-containment.html")


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

    def test_files_without_grammar_are_skipped(self):
        source = GOOD.replace('data-grammar="architecture-containment"', "")
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])
        self.assertFalse(checker.looks_like_containment(source))

    def test_comments_entities_and_unquoted_attributes(self):
        source = GOOD.replace("</svg>", "<!-- <rect data-scope-id=\"bogus\"/> --></svg>")
        source = source.replace("<text>sql</text>", "<text>sql&gt;db</text>")
        source = source.replace('data-scope-kind="admin"', "DATA-SCOPE-KIND=admin")
        self.clean(source)

    def test_duplicate_scope_id(self):
        self.rejects(GOOD.replace('data-scope-id="hub"', 'data-scope-id="spoke"', 1), "duplicate ID")

    def test_duplicate_node_id(self):
        self.rejects(GOOD.replace('data-node-id="app"', 'data-node-id="sql"', 1), "duplicate ID")

    def test_scope_and_node_share_one_namespace(self):
        self.rejects(GOOD.replace('data-node-id="app"', 'data-node-id="hub"', 1), "duplicate ID")

    def test_unresolved_parent(self):
        self.rejects(GOOD.replace('data-parent="rg"', 'data-parent="missing"', 1), "does not match any data-scope-id")

    def test_blank_parent_on_nested_scope(self):
        self.rejects(GOOD.replace('data-parent="subscription"', 'data-parent=""', 1), "data-parent")

    def test_parent_cycle(self):
        source = GOOD.replace(
            'data-scope-id="subscription"',
            'data-scope-id="subscription" data-parent="rg"',
            1,
        )
        self.rejects(source, "parent cycle")

    def test_child_outside_parent(self):
        self.rejects(GOOD.replace('x="32" y="88" width="160" height="144"', 'x="0" y="88" width="160" height="144"', 1), "not geometrically inside parent")

    def test_admin_must_be_dashed_rx4_band(self):
        self.rejects(GOOD.replace('rx="4"', 'rx="8"', 1), "admin band must use rx=4")
        self.rejects(GOOD.replace(' stroke-dasharray="4,4"', "", 1), "admin band must use a dashed stroke")
        tall = GOOD.replace(
            'data-scope-id="subscription" data-scope-kind="admin" x="16" y="16" width="368" height="248"',
            'data-scope-id="subscription" data-scope-kind="admin" x="16" y="16" width="120" height="248"',
            1,
        )
        self.rejects(tall, "admin band must be a horizontal rectangle")

    def test_traffic_must_be_solid_rx8_box(self):
        self.rejects(GOOD.replace('rx="8"', 'rx="4"', 1), "traffic box must use rx=8")
        dashed = GOOD.replace(
            'data-scope-id="hub" data-scope-kind="traffic" data-parent="rg" x="32" y="88" width="160" height="144" rx="8" fill="none" stroke="#000"',
            'data-scope-id="hub" data-scope-kind="traffic" data-parent="rg" x="32" y="88" width="160" height="144" rx="8" fill="none" stroke="#000" stroke-dasharray="4,4"',
            1,
        )
        self.rejects(dashed, "traffic box must use a solid stroke")

    def test_managed_must_not_sit_inside_traffic(self):
        self.rejects(GOOD.replace('x="32" y="36"', 'x="56" y="144"'), "must not sit inside traffic scope")

    def test_managed_must_parent_to_admin(self):
        self.rejects(GOOD.replace('data-node-id="sql" data-kind="managed" data-parent="rg"',
                                  'data-node-id="sql" data-kind="managed" data-parent="hub"'),
                     "managed node must parent to an admin band")

    def test_endpoint_must_parent_to_traffic_and_target_managed(self):
        self.rejects(GOOD.replace('data-parent="spoke" data-target="sql"',
                                  'data-parent="rg" data-target="sql"'),
                     "endpoint node must parent to a traffic box")
        self.rejects(GOOD.replace('data-target="sql"', 'data-target="app"'), "must name a managed node")
        self.rejects(GOOD.replace(' data-target="sql"', ""), "endpoint must declare data-target")

    def test_peering_must_join_traffic_scopes(self):
        self.rejects(GOOD.replace('data-from="hub" data-to="spoke"', 'data-from="rg" data-to="spoke"'),
                     "peering data-from and data-to must name traffic scopes")
        self.rejects(GOOD.replace('data-from="hub" data-to="spoke"', 'data-from="hub" data-to="hub"'),
                     "two distinct traffic scopes")

    def test_sibling_axis_and_overlap(self):
        mixed = GOOD.replace(
            'data-scope-id="spoke" data-scope-kind="traffic" data-parent="rg" x="208" y="88"',
            'data-scope-id="spoke" data-scope-kind="traffic" data-parent="rg" x="208" y="120"',
            1,
        )
        self.rejects(mixed, "sibling traffic scopes must share one axis")
        overlap = GOOD.replace(
            'data-scope-id="spoke" data-scope-kind="traffic" data-parent="rg" x="208" y="88" width="160" height="144"',
            'data-scope-id="spoke" data-scope-kind="traffic" data-parent="rg" x="80" y="88" width="160" height="144"',
            1,
        )
        self.rejects(overlap, "overlap")

    def test_off_grid_bounds(self):
        self.rejects(GOOD.replace('x="32" y="88"', 'x="33" y="88"'), "4px grid")

    def test_unknown_kinds_and_duplicate_attributes(self):
        self.rejects(GOOD.replace('data-scope-kind="traffic"', 'data-scope-kind="vpc"', 1), "data-scope-kind")
        self.rejects(GOOD.replace('data-kind="compute"', 'data-kind="vm"', 1), "data-kind")
        self.rejects(GOOD.replace('data-scope-id="hub"', 'data-scope-id="hub" DATA-SCOPE-ID="ignored"', 1),
                     "duplicate attributes")

    def test_empty_and_invalid_ids(self):
        for value in ("", " hub", "1hub", "hub spoke"):
            with self.subTest(value=value):
                self.rejects(GOOD.replace('data-scope-id="hub"', f'data-scope-id="{value}"', 1), "identity")

    def test_budget(self):
        extra_admin = GOOD.replace(
            "</svg>",
            scope("extra-admin", "admin", 16, 16, 368, 40) + "</svg>",
        )
        self.rejects(extra_admin, "admin budget")
        extra_traffic = GOOD.replace(
            "</svg>",
            scope("a", "traffic", 32, 88, 40, 40, parent="rg")
            + scope("b", "traffic", 80, 88, 40, 40, parent="rg")
            + scope("c", "traffic", 128, 88, 40, 40, parent="rg")
            + "</svg>",
        )
        self.rejects(extra_traffic, "traffic budget")
        extra_nodes = GOOD
        for identity in ("n1", "n2", "n3", "n4", "n5", "n6"):
            extra_nodes = extra_nodes.replace("</svg>", node(identity, "compute", 56, 144, "hub") + "</svg>")
        self.rejects(extra_nodes, "node budget")

    # Item 1: transforms and positional CSS move rendered geometry away from
    # the raw x/y/width/height the checker reads, so they are rejected.
    def test_transform_attribute_on_node_group(self):
        self.rejects(GOOD.replace('<g data-node-id="sql"', '<g transform="translate(0,264)" data-node-id="sql"', 1),
                     "moves checked bounds")

    def test_inline_style_transform_on_node_group(self):
        self.rejects(GOOD.replace('<g data-node-id="sql"', '<g style="transform:translate(0px,264px)" data-node-id="sql"', 1),
                     "moves checked bounds")

    def test_ancestor_group_transform(self):
        source = GOOD.replace('<g data-node-id="sql"', '<g transform="translate(0,264)"><g data-node-id="sql"', 1)
        source = source.replace("<text>sql</text></g>", "<text>sql</text></g></g>", 1)
        self.rejects(source, "moves checked bounds")

    def test_transform_attribute_on_scope_bounds(self):
        self.rejects(GOOD.replace('<rect data-role="bounds" data-scope-id="hub"',
                                  '<rect transform="translate(400,0)" data-role="bounds" data-scope-id="hub"', 1),
                     "moves checked bounds")

    def test_positional_inline_css_on_bounds(self):
        for style in ("translate: 0 100px", "x: 0px", "rotate: 90deg", "position:absolute;top:10px", "margin-left: 4px"):
            with self.subTest(style=style):
                self.rejects(GOOD.replace('<rect data-role="bounds" x="56" y="144"',
                                          f'<rect style="{style}" data-role="bounds" x="56" y="144"', 1),
                             "moves checked bounds")

    def test_nested_svg_viewport_ancestor(self):
        source = GOOD.replace('<g data-node-id="sql"', '<svg x="0" y="264"><g data-node-id="sql"', 1)
        source = source.replace("<text>sql</text></g>", "<text>sql</text></g></svg>", 1)
        self.rejects(source, "moves checked bounds")

    def test_stylesheet_rule_transforming_checked_element(self):
        for rule in ('[data-node-id="sql"] { transform: translate(0, 264px); }',
                     "svg g { translate: 0 264px }",
                     "rect { x: 0 }"):
            with self.subTest(rule=rule):
                self.rejects(GOOD.replace("body {margin:0}", "body {margin:0} " + rule, 1), "moves checked bounds")

    def test_geometry_animation(self):
        self.rejects(GOOD.replace("<text>sql</text></g>",
                                  '<text>sql</text><animateTransform attributeName="transform" type="translate" to="0 264"/></g>', 1),
                     "moves checked bounds")

    def test_harmless_page_css_is_clean(self):
        source = GOOD.replace("body {margin:0}", "body {margin:0} .card li { position: relative; left: 0; transform: none }", 1)
        self.clean(source)

    def test_page_only_style_rules_are_clean(self):
        # The full selector is matched against the element and its real
        # ancestors, so rules that cannot reach a checked element pass.
        for rule in (":root { height: 100% }",
                     "html, body { height: 100% }",
                     ".card rect { x: 0 }",
                     "svg { width: 100% }",
                     "#other rect { transform: translate(4px, 0) }",
                     "body > rect { x: 0 }",
                     "rect::after { transform: scale(2) }",
                     'g[data-kind="vm"] { translate: 0 8px }'):
            with self.subTest(rule=rule):
                self.clean(GOOD.replace("body {margin:0}", "body {margin:0} " + rule, 1))

    def test_style_rule_through_page_ancestor(self):
        wrapped = GOOD.replace("<svg data-grammar", '<div class="card"><svg data-grammar', 1)
        wrapped = wrapped.replace("</svg>", "</svg></div>", 1)
        self.clean(wrapped)
        for rule in (".card rect { x: 0 }",
                     "body > .card rect { x: 0 }",
                     'div.card > svg > g[data-kind="managed"] { transform: translate(0, 264px) }',
                     "h1 + .card rect { x: 0 }",
                     ":not(.other) rect { x: 0 }"):
            with self.subTest(rule=rule):
                self.rejects(wrapped.replace("body {margin:0}", "body {margin:0} " + rule, 1),
                             "moves checked bounds")

    @staticmethod
    def omitted_tag_pages():
        # Valid HTML may omit <html>, <head> and <body>; a browser implies them.
        no_html = GOOD.replace("<html>", "", 1).replace("</html>", "", 1)
        no_body = GOOD.replace("<body>", "", 1).replace("</body>", "", 1)
        neither = no_html.replace("<body>", "", 1).replace("</body>", "", 1)
        bare = neither.replace("<head>", "", 1).replace("</head>", "", 1)
        pages = {"no-html": no_html, "no-body": no_body, "neither": neither, "bare": bare}
        for page in pages.values():
            assert page != GOOD and "body {margin:0}" in page
        return pages

    def test_omitted_html_and_body_still_anchor_style_rules(self):
        for label, page in self.omitted_tag_pages().items():
            with self.subTest(page=label):
                self.clean(page)
            for rule in ('body [data-node-id="sql"] { transform: translate(0,108px) }',
                         'html [data-node-id="sql"] { transform: translate(0,108px) }',
                         ':root [data-node-id="sql"] { transform: translate(0,108px) }',
                         'html > body > svg [data-node-id="sql"] { transform: translate(0,108px) }'):
                with self.subTest(page=label, rule=rule):
                    self.rejects(page.replace("body {margin:0}", "body {margin:0} " + rule, 1),
                                 "moves checked bounds")

    def test_omitted_tag_pages_keep_page_only_rules_clean(self):
        for label, page in self.omitted_tag_pages().items():
            for rule in (":root { height: 100% }", "body > rect { x: 0 }", "head rect { x: 0 }",
                         "html > rect { x: 0 }", ":root > g { transform: translate(4px, 0) }"):
                with self.subTest(page=label, rule=rule):
                    self.clean(page.replace("body {margin:0}", "body {margin:0} " + rule, 1))

    def test_child_combinator_outside_svg_survives_implied_end_tags(self):
        # A browser closes the <p> at <div>, so body > .card matches; the
        # stdlib parser nests the div in the p, so the checker must not trust it.
        source = GOOD.replace("<svg data-grammar", '<p>intro<div class="card"><svg data-grammar', 1)
        source = source.replace("</svg>", "</svg></div>", 1)
        self.clean(source)
        self.rejects(source.replace("body {margin:0}", "body {margin:0} body > .card rect { x: 0 }", 1),
                     "moves checked bounds")

    # Item 2: a scope or node enclosed by another scope must declare its
    # parent, and that parent must be the innermost enclosing scope.
    def test_missing_parent_on_enclosed_scope(self):
        self.rejects(GOOD.replace(' data-parent="subscription"', "", 1), "data-parent is required")

    def test_parent_must_be_innermost_enclosing_scope(self):
        self.rejects(GOOD.replace('data-scope-id="hub" data-scope-kind="traffic" data-parent="rg"',
                                  'data-scope-id="hub" data-scope-kind="traffic" data-parent="subscription"', 1),
                     "innermost enclosing scope")
        self.rejects(GOOD.replace('data-node-id="sql" data-kind="managed" data-parent="rg"',
                                  'data-node-id="sql" data-kind="managed" data-parent="subscription"', 1),
                     "innermost enclosing scope")

    def test_shipped_missing_parent_cannot_hide_misaligned_sibling(self):
        path = ROOT / "skills/diagram-design/assets/example-architecture-containment.html"
        source = path.read_text(encoding="utf-8")
        mutated = source.replace('data-scope-id="vnet-hub" data-scope-kind="traffic" data-parent="rg"',
                                 'data-scope-id="vnet-hub" data-scope-kind="traffic"', 1)
        self.assertNotEqual(mutated, source)
        findings = "\n".join(checker.check_source(path, mutated))
        self.assertIn("data-parent is required", findings)
        mutated = source.replace(' data-parent="subscription"', "", 1)
        self.assertNotEqual(mutated, source)
        self.assertIn("data-parent is required", "\n".join(checker.check_source(path, mutated)))

    # Item 3: stroke-dasharray is parsed, not merely tested for presence.
    def test_dasharray_none_is_solid(self):
        for value in ("none", "0", "0,0", " 0 0 "):
            with self.subTest(value=value):
                self.rejects(GOOD.replace('stroke-dasharray="4,4"', f'stroke-dasharray="{value}"', 1),
                             "admin band must use a dashed stroke")
                traffic = GOOD.replace(
                    'data-scope-id="hub" data-scope-kind="traffic" data-parent="rg" x="32" y="88" width="160" height="144" rx="8" fill="none" stroke="#000"',
                    f'data-scope-id="hub" data-scope-kind="traffic" data-parent="rg" x="32" y="88" width="160" height="144" rx="8" fill="none" stroke="#000" stroke-dasharray="{value}"',
                    1,
                )
                self.assertNotEqual(traffic, GOOD)
                self.clean(traffic)

    def test_important_dasharray_wins_over_later_normal_declaration(self):
        for style in (
            "stroke-dasharray:none!important;stroke-dasharray:4,4",
            "stroke-dasharray:none ! IMPORTANT;stroke-dasharray:4,4",
        ):
            with self.subTest(style=style):
                self.rejects(GOOD.replace('stroke-dasharray="4,4"',
                                         f'style="{style}"', 1),
                             "admin band must use a dashed stroke")
        for style in (
            "stroke-dasharray:4,4!important;stroke-dasharray:none",
            "stroke-dasharray:4,4 ! IMPORTANT;stroke-dasharray:none",
        ):
            with self.subTest(style=style):
                self.clean(GOOD.replace('stroke-dasharray="4,4"',
                                        f'style="{style}"', 1))

    def test_equal_dasharray_priority_keeps_later_declaration(self):
        for style in (
            "stroke-dasharray:none;stroke-dasharray:4,4",
            "stroke-dasharray:none!important;stroke-dasharray:4,4!important",
        ):
            with self.subTest(style=style):
                self.clean(GOOD.replace('stroke-dasharray="4,4"',
                                        f'style="{style}"', 1))
        for style in (
            "stroke-dasharray:4,4;stroke-dasharray:none",
            "stroke-dasharray:4,4!important;stroke-dasharray:none!important",
        ):
            with self.subTest(style=style):
                self.rejects(GOOD.replace('stroke-dasharray="4,4"',
                                         f'style="{style}"', 1),
                             "admin band must use a dashed stroke")

    def test_invalid_literal_values_do_not_acquire_declaration_priority(self):
        invalid = ("", " ", "/**/", "nope", "-1", "4,-1", "4,,4", ",4", "4,")
        for value in invalid:
            for style in (
                f"stroke-dasharray:{value}!important;stroke-dasharray:4,4",
                f"stroke-dasharray:4,4!important;stroke-dasharray:{value}!important",
                f"stroke-dasharray:4,4;stroke-dasharray:{value}",
            ):
                with self.subTest(style=style, scope="admin"):
                    self.clean(GOOD.replace('stroke-dasharray="4,4"', f'style="{style}"', 1))
                with self.subTest(style=style, scope="traffic"):
                    traffic = GOOD.replace(
                        'data-scope-id="hub" data-scope-kind="traffic"',
                        f'data-scope-id="hub" data-scope-kind="traffic" style="{style}"', 1,
                    )
                    self.rejects(traffic, "traffic box must use a solid stroke")

    def test_unresolved_dash_values_fail_closed_only_when_they_win(self):
        for value in ("var(--dash, 4)", "calc(2px + 2px)", "4cap", r"n\6f ne"):
            with self.subTest(value=value):
                self.rejects(GOOD.replace(
                    'stroke-dasharray="4,4"',
                    f'style="stroke-dasharray:{value}!important;stroke-dasharray:4,4"', 1,
                ), "unsupported stroke-dasharray value")
                self.clean(GOOD.replace(
                    'stroke-dasharray="4,4"',
                    f'style="stroke-dasharray:4,4!important;stroke-dasharray:{value}"', 1,
                ))

    def test_css_wide_dash_keywords_are_retained_in_priority_resolution(self):
        for value in ("inherit", "initial", "unset", "revert", "revert-layer"):
            with self.subTest(value=value):
                self.assertEqual(checker.declarations(
                    f"stroke-dasharray:{value}!important;stroke-dasharray:4,4"
                )["stroke-dasharray"], value)

    def test_css_wide_dash_priority_matches_attribute_and_parent_inheritance(self):
        for value in ("inherit", "initial", "unset", "revert", "revert-layer"):
            style = f"stroke-dasharray:{value}!important;stroke-dasharray:4,4"
            with self.subTest(value=value, source="presentation attribute"):
                source = GOOD.replace('stroke-dasharray="4,4"',
                                      f'stroke-dasharray="4,4" style="{style}"', 1)
                if value == "revert-layer":
                    self.clean(source)
                else:
                    self.rejects(source, "admin band must use a dashed stroke")
            with self.subTest(value=value, source="dashed parent"):
                source = GOOD.replace('stroke-dasharray="4,4"', f'style="{style}"', 1)
                source = re.sub(
                    r'<rect\b[^>]*data-scope-id="subscription"[^>]*/>',
                    lambda match: '<g stroke-dasharray="4,4">' + match.group() + '</g>',
                    source, count=1,
                )
                if value == "initial":
                    self.rejects(source, "admin band must use a dashed stroke")
                else:
                    self.clean(source)

    def test_comments_do_not_fabricate_dash_keywords_units_or_priority(self):
        for style in (
            "stroke-dasharray:no/**/ne!important;stroke-dasharray:4,4",
            "stroke-dasharray:in/**/herit!important;stroke-dasharray:4,4",
            "stroke-dasharray:none!im/**/portant;stroke-dasharray:4,4",
            "stroke-dasharray:4/**/4!important;stroke-dasharray:none",
        ):
            with self.subTest(style=style, scope="admin"):
                self.clean(GOOD.replace('stroke-dasharray="4,4"', f'style="{style}"', 1))
            with self.subTest(style=style, scope="traffic"):
                self.rejects(GOOD.replace(
                    'data-scope-id="hub" data-scope-kind="traffic"',
                    f'data-scope-id="hub" data-scope-kind="traffic" style="{style}"', 1,
                ), "traffic box must use a solid stroke")
        for style in (
            "stroke-dasharray:4/**/px!important;stroke-dasharray:none",
            "stroke-dasharray:none!/**/important;stroke-dasharray:4,4",
        ):
            with self.subTest(style=style, scope="admin"):
                self.rejects(GOOD.replace('stroke-dasharray="4,4"', f'style="{style}"', 1),
                             "admin band must use a dashed stroke")
            with self.subTest(style=style, scope="traffic"):
                self.clean(GOOD.replace(
                    'data-scope-id="hub" data-scope-kind="traffic"',
                    f'data-scope-id="hub" data-scope-kind="traffic" style="{style}"', 1,
                ))

    def test_comment_scanning_preserves_quoted_strings_escapes_and_rule_bodies(self):
        source = r'label:"escaped\"/*literal;{}*/";stroke-dasharray:4/**/4!important;stroke-dasharray:none'
        values = checker.declarations(source)
        self.assertEqual(values["label"], r'"escaped\"/*literal;{}*/"')
        self.assertEqual(values["stroke-dasharray"], "4 4")
        rules = checker.css_rules('rect/**/.bounds {' + source + '}')
        self.assertEqual(rules, [("rect.bounds", values)])
        self.assertEqual(checker.declarations("stroke-dasharray:4,4;/* unterminated"),
                         {"stroke-dasharray": "4,4"})

    def test_dasharray_resolves_style_and_inheritance(self):
        self.rejects(GOOD.replace(' stroke-dasharray="4,4"', ' stroke-dasharray="4,4" style="stroke-dasharray: none"', 1),
                     "admin band must use a dashed stroke")
        inherited = GOOD.replace('<rect data-role="bounds" data-scope-id="hub"',
                                 '<g stroke-dasharray="4 4"><rect data-role="bounds" data-scope-id="hub"', 1)
        inherited = inherited.replace(
            '<rect data-role="bounds" data-scope-id="spoke"', '</g><rect data-role="bounds" data-scope-id="spoke"', 1)
        self.rejects(inherited, "traffic box must use a solid stroke")
        self.rejects(GOOD.replace("body {margin:0}", "body {margin:0} rect { stroke-dasharray: none }", 1),
                     "overrides the checked stroke-dasharray")

    # Item 4: bounds are rects, not any element that happens to carry x/y/width/height.
    def test_scope_bounds_must_be_rect(self):
        self.rejects(GOOD.replace('<rect data-role="bounds" data-scope-id="hub"', '<image data-role="bounds" data-scope-id="hub"', 1),
                     "bounds must be a <rect>")

    def test_node_bounds_must_be_rect(self):
        self.rejects(GOOD.replace('<rect data-role="bounds" x="56" y="144"', '<image data-role="bounds" x="56" y="144"', 1),
                     "bounds must be a <rect>")

    # Item 5: nested sibling traffic scopes take the axis perpendicular to
    # their parent's own axis (type-architecture.md, Sibling axis).
    @staticmethod
    def nested(first, second):
        return GOOD.replace("</svg>", scope("n1", "traffic", *first, parent="hub")
                            + scope("n2", "traffic", *second, parent="hub") + "</svg>", 1)

    def test_nested_siblings_take_perpendicular_axis(self):
        # hub and spoke form a row in rg, so hub's own children stack in a column.
        self.clean(self.nested((112, 100, 72, 56), (112, 164, 72, 56)))

    def test_nested_siblings_on_parent_axis_rejected(self):
        self.rejects(self.nested((112, 100, 32, 120), (152, 100, 32, 120)), "perpendicular")

    def test_all_shipped_variants(self):
        for suffix in ("", "-dark", "-full"):
            path = ROOT / f"skills/diagram-design/assets/example-architecture-containment{suffix}.html"
            with self.subTest(variant=suffix):
                self.assertTrue(path.is_file(), f"missing shipped variant: {path.name}")
                source = path.read_text(encoding="utf-8")
                self.assertEqual(checker.check_source(path, source), [])
                self.assertIn('data-grammar="architecture-containment"', source)
                self.assertIn('data-kind="managed"', source)
                self.assertIn('data-kind="endpoint"', source)
                self.assertIn("data-peering=", source)

    def test_shipped_boundary_labels_use_soft(self):
        # type-architecture.md: zone labels use `soft`, never ink at an opacity.
        soft = {"": "#5a6580", "-dark": "#949eb2", "-full": "#5a6580"}
        for suffix, colour in soft.items():
            path = ROOT / f"skills/diagram-design/assets/example-architecture-containment{suffix}.html"
            scanner = checker.Scanner()
            scanner.finish(path.read_text(encoding="utf-8"))
            labels = [item for item in scanner.nodes
                      if item.tag == "text" and item.attrs.get("letter-spacing") == "0.14em"]
            with self.subTest(variant=suffix):
                self.assertEqual(len(labels), 6)
                self.assertEqual({item.attrs.get("fill") for item in labels}, {colour})

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
            path.write_text(GOOD.replace('data-kind="managed"', 'data-kind="compute"', 1), encoding="utf-8")
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1)
            path.unlink()
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
