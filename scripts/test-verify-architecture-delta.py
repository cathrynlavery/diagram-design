#!/usr/bin/env python3
"""Adversarial and legal Architecture delta fixtures (ADR 0005).

Synthetic fixtures exercise the public contract independently of the shipped
layout; all three published variants and CLI discovery are checked as well.
Run: python3 scripts/test-verify-architecture-delta.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-architecture-delta.py"
SPEC = importlib.util.spec_from_file_location("architecture_delta_verifier", CHECKER)
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def component(identity, status, signature, x, y, size=40):
    return (f'<g data-kind="component" data-object-id="{identity}" data-status="{status}" '
            f'data-signature="{signature}"><rect data-role="bounds" x="{x}" y="{y}" '
            f'width="{size}" height="{size}"/><text>{identity}</text></g>')


def relationship(identity, status, source, target, path, signature="message:v1"):
    return (f'<path data-kind="relationship" data-object-id="{identity}" data-status="{status}" '
            f'data-signature="{signature}" data-from="{source}" data-to="{target}" d="{path}"/>')


def fixture(pitch=4):
    """All five change kinds, seven ledger entries, and a rerouted stable edge."""
    parts = ['<html><head><style>svg {width:100%;height:auto} body {margin:0}</style></head><body>',
             '<svg data-diagram="architecture-delta" viewBox="0 0 760 180">']
    for state, origin in (("before", 0), ("after", 500)):
        after = state == "after"
        parts.append(f'<g data-snapshot="{state}" data-grid="240 160 {pitch}" transform="translate({origin} 0)">')
        parts.append(relationship("request", "unchanged", "client", "api", "M40 20 H80"))
        parts.append(relationship("submit", "rewired", "api", "queue" if after else "old", "M120 20 H160"))
        parts.append(relationship("queued" if after else "delivery", "added" if after else "removed",
                                  "queue" if after else "old", "worker", f'M180 40 V60 H{100 if after else 20} V80'))
        parts.append(relationship("write", "unchanged", "worker", "db", f'M{120 if after else 40} 100 H160'))
        parts.append(component("client", "unchanged", "web:v1", 0, 0))
        parts.append(component("api", "changed", "api:v2" if after else "api:v1", 80, 0))
        parts.append(component("queue" if after else "old", "added" if after else "removed", "dispatch:v1", 160, 0))
        parts.append(component("worker", "moved", "worker:v1", 80 if after else 0, 80))
        parts.append(component("db", "unchanged", "db:v1", 160, 80))
        parts.append('</g>')
    for index, (change, target) in enumerate((
        ("REMOVED", "old"), ("ADDED", "queue"), ("CHANGED", "api"), ("MOVED", "worker"),
        ("REWIRED", "submit"), ("REMOVED", "delivery"), ("ADDED", "queued"),
    )):
        parts.append(f'<text data-change="{change}" data-target="{target}" x="280" y="{20 + index * 20}">'
                     f'{change} {target}: migration detail</text>')
    parts.append('</svg></body></html>')
    return "\n".join(parts)


GOOD = fixture()
SYNTHETIC_PATH = Path("synthetic-architecture-delta.html")


class ContractTests(unittest.TestCase):
    def clean(self, source):
        self.assertEqual(checker.check_source(SYNTHETIC_PATH, source), [])

    def rejects(self, source, reason):
        self.assertNotEqual(source, GOOD, "fixture mutation did not apply")
        findings = checker.check_source(SYNTHETIC_PATH, source)
        self.assertTrue(findings, "invalid diagram accepted")
        self.assertIn(reason, "\n".join(findings))

    def test_synthetic_and_alternate_pitch(self):
        self.clean(GOOD)
        self.clean(fixture(pitch=8))

    def test_alternate_panel_translation_is_not_a_move(self):
        self.clean(GOOD.replace('translate(0 0)', 'translate(20, 40)').replace('translate(500 0)', 'translate(540, 40)'))

    def test_comments_entities_and_tspans(self):
        source = GOOD.replace('</svg>', '<!-- <g data-object-id="bogus"/> --></svg>')
        source = source.replace('web:v1', 'web:&gt;v1')
        source = source.replace('ADDED queue: migration detail', '<tspan>ADDED</tspan><tspan> queue: migration detail</tspan>')
        self.clean(source)

    def test_unquoted_attributes_and_number_syntax(self):
        self.clean(GOOD.replace('data-status="unchanged"', 'DATA-STATUS=unchanged').replace('x="80"', "x='8.e1'"))

    def test_changed_and_moved_together(self):
        source = GOOD.replace('data-object-id="worker" data-status="moved"', 'data-object-id="worker" data-status="changed moved"')
        # Only the after occurrence receives a new semantic signature.
        before, after = source.split('data-snapshot="after"', 1)
        after = after.replace('data-signature="worker:v1"', 'data-signature="worker:v2"', 1)
        source = before + 'data-snapshot="after"' + after
        source = source.replace('</svg>', '<text data-change="CHANGED" data-target="worker">CHANGED worker version</text></svg>')
        self.clean(source)

    def test_changed_and_rewired_together(self):
        source = GOOD.replace('data-object-id="submit" data-status="rewired"', 'data-object-id="submit" data-status="changed rewired"')
        before, after = source.split('data-snapshot="after"', 1)
        after = after.replace('data-object-id="submit" data-status="changed rewired" data-signature="message:v1"',
                              'data-object-id="submit" data-status="changed rewired" data-signature="message:v2"')
        source = before + 'data-snapshot="after"' + after
        source = source.replace('</svg>', '<text data-change="CHANGED" data-target="submit">CHANGED transport version</text></svg>')
        self.clean(source)

    def test_curved_orthogonal_path(self):
        self.clean(GOOD.replace('M180 40 V60 H20 V80', 'M180 40 V52 Q180 60 172 60 H28 Q20 60 20 68 V80'))

    def test_empty_and_missing_declarations(self):
        for attribute, value, reason in (
            ('data-object-id', 'client', 'data-object-id'),
            ('data-kind', 'component', 'data-kind'),
            ('data-status', 'unchanged', 'data-status'),
            ('data-signature', 'web:v1', 'data-signature'),
        ):
            for replacement in ('', f'{attribute}=""', attribute):
                with self.subTest(attribute=attribute, replacement=replacement):
                    self.rejects(GOOD.replace(f'{attribute}="{value}"', replacement, 1), reason)

    def test_duplicate_object_id(self):
        self.rejects(GOOD.replace('data-object-id="client"', 'data-object-id="api"', 1), 'duplicate object ID')

    def test_path_metadata_cannot_disappear(self):
        original = relationship('request', 'unchanged', 'client', 'api', 'M40 20 H80')
        self.rejects(GOOD.replace(original, '<path d="M40 20 H80"/>'), 'missing relationship metadata')
        self.rejects(GOOD.replace('<text>client</text></g>', '<text>client</text></g><path d="M40 20 H80"/>', 1), 'missing relationship metadata')

    def test_duplicate_attribute(self):
        self.rejects(GOOD.replace('data-object-id="client"', 'data-object-id="client" DATA-OBJECT-ID="ignored"', 1), 'duplicate attributes')

    def test_whitespace_and_multiple_ids(self):
        for value in (' client', 'client ', 'client api', '12client'):
            self.rejects(GOOD.replace('data-object-id="client"', f'data-object-id="{value}"', 1), 'data-object-id')

    def test_wrong_or_duplicate_statuses(self):
        for value in ('UNCHANGED', 'moved moved', 'unchanged moved', 'added changed', 'unknown', 'rewired'):
            with self.subTest(value=value):
                self.rejects(GOOD.replace('data-object-id="client" data-status="unchanged"', f'data-object-id="client" data-status="{value}"', 1), 'status')

    def test_relationship_cannot_be_moved(self):
        self.rejects(GOOD.replace('data-object-id="write" data-status="unchanged"', 'data-object-id="write" data-status="moved"', 1), 'data-status')

    def test_added_removed_membership(self):
        for old, new, reason in (
            ('data-object-id="queue" data-status="added"', 'data-object-id="queue" data-status="removed"', 'after-only'),
            ('data-object-id="old" data-status="removed"', 'data-object-id="old" data-status="added"', 'before-only'),
            ('data-object-id="client" data-status="unchanged"', 'data-object-id="client" data-status="added"', 'retained statuses'),
        ):
            self.rejects(GOOD.replace(old, new), reason)

    def test_missing_snapshot_membership(self):
        extra = component('outsider', 'added', 'extra:v1', 0, 0)
        self.rejects(GOOD.replace('</svg>', extra + '</svg>'), 'exactly one snapshot')

    def test_nested_snapshot_and_object(self):
        self.rejects(GOOD.replace('data-snapshot="before"', 'data-snapshot="before"').replace(
            '<g data-kind="component" data-object-id="client"', '<g data-snapshot="after"><g data-kind="component" data-object-id="client"', 1), 'exactly two snapshots')
        nested = component('nested', 'added', 'extra:v1', 0, 0)
        self.rejects(GOOD.replace('<text>client</text>', nested + '<text>client</text>', 1), 'cannot be nested')

    def test_missing_root_and_snapshots(self):
        self.rejects(GOOD.replace('data-diagram="architecture-delta"', ''), 'exactly one svg')
        self.rejects(GOOD.replace('data-snapshot="before"', 'data-snapshot="past"'), 'exactly two snapshots')
        self.rejects('<svg data-diagram="architecture-delta"></svg>', 'exactly two snapshots')

    def test_malformed_markup(self):
        self.rejects(GOOD.replace('</g>', '</path>', 1), 'malformed SVG')
        self.rejects(GOOD.replace('</svg></body></html>', ''), 'unclosed SVG')

    def test_retained_kind_mismatch(self):
        replacement = relationship('client', 'unchanged', 'api', 'db', 'M100 40 V60 H180 V80', signature='web:v1')
        source = GOOD.replace(component('client', 'unchanged', 'web:v1', 0, 0), replacement, 1)
        self.rejects(source, 'changed kind')

    def test_changed_signatures_both_directions(self):
        self.rejects(GOOD.replace('api:v2', 'api:v1'), 'CHANGED signature mismatch')
        self.rejects(GOOD.replace('web:v1', 'web:v2', 1), 'CHANGED signature mismatch')

    def test_move_both_directions(self):
        self.rejects(GOOD.replace(component('worker', 'moved', 'worker:v1', 80, 80), component('worker', 'moved', 'worker:v1', 0, 80)), 'MOVED position mismatch')
        self.rejects(GOOD.replace(component('client', 'unchanged', 'web:v1', 0, 0), component('client', 'unchanged', 'web:v1', 4, 0), 1), 'MOVED position mismatch')

    def test_size_cannot_change_silently(self):
        self.rejects(GOOD.replace('width="40"', 'width="44"', 1), 'size changed without CHANGED')

    def test_rewire_both_directions(self):
        self.rejects(GOOD.replace('data-object-id="submit" data-status="rewired"', 'data-object-id="submit" data-status="unchanged"'), 'REWIRED endpoints mismatch')
        self.rejects(GOOD.replace('data-object-id="request" data-status="unchanged"', 'data-object-id="request" data-status="rewired"'), 'REWIRED endpoints mismatch')

    def test_missing_and_dangling_endpoints(self):
        for value in ('missing', '', 'request', 'old'):
            self.rejects(GOOD.replace('data-to="queue"', f'data-to="{value}"'), 'endpoint')
        self.rejects(GOOD.replace('data-to="api"', '', 1), 'endpoint ID')

    def test_drawn_endpoints_match_declared_nodes(self):
        for path in ('M40 20 H72', 'M48 20 H80', 'M20 20 H100', 'M40 20 H160'):
            self.rejects(GOOD.replace('M40 20 H80', path, 1), 'perimeter')

    def test_matching_grids(self):
        self.rejects(GOOD.replace('data-grid="240 160 4"', 'data-grid="248 160 4"', 1), 'grids must match')
        for value in ('', '240 160', '240 160 0', '240 160 -4', '240 160 NaN', '240 160 3', '1e309 160 4', '240 160 1e-309'):
            self.rejects(GOOD.replace('data-grid="240 160 4"', f'data-grid="{value}"', 1), 'data-grid')

    def test_bounds_are_finite_positive_in_grid(self):
        for old, new in (('width="40"', 'width="0"'), ('width="40"', 'width="-4"'),
                         ('x="80"', 'x="81"'), ('x="80"', 'x="240"'),
                         ('x="80"', 'x="NaN"'), ('y="80"', 'y="1e999"'), ('x="80"', '')):
            self.rejects(GOOD.replace(old, new, 1), 'component bounds')

    def test_bounds_declared_once_on_direct_rect(self):
        self.rejects(GOOD.replace('data-role="bounds"', '', 1), 'direct rect')
        self.rejects(GOOD.replace('<rect data-role="bounds"', '<ellipse data-role="bounds"', 1), 'direct rect')
        self.rejects(GOOD.replace('<text>client</text>', '<rect data-role="bounds"/><text>client</text>', 1), 'direct rect')
        self.rejects(GOOD.replace('</svg>', '<rect data-role="bounds"/></svg>'), 'direct child of a component')

    def test_panel_transform_and_order(self):
        for value in ('', 'scale(2)', 'translate(500 0) scale(2)', 'translate(NaN 0)', 'translate(500 4)', 'translate(200 0)'):
            self.rejects(GOOD.replace('translate(500 0)', value), 'panel' if value in ('translate(500 4)', 'translate(200 0)') else 'translat')
        self.rejects(GOOD.replace('data-object-id="client"', 'transform="translate(4 0)" data-object-id="client"', 1), 'only snapshot translations')

    def test_css_geometry_overrides(self):
        for declaration in ('transform:translateX(4px)', 'translate:4px 0', 'x:4px', 'width:80px', 'height:80px'):
            self.rejects(GOOD.replace('<rect data-role="bounds"', f'<rect style="{declaration}" data-role="bounds"', 1), 'CSS geometry')
            self.rejects(GOOD.replace('</style>', f'rect {{{declaration}}}</style>'), 'CSS geometry')
        self.rejects(GOOD.replace('</style>', r'rect {tr\61nsform:translateX(4px)}</style>'), 'escaped CSS')
        for declaration in ('/**/transform:translate(32px,0)', r'tr\61nsform:translate(32px,0)',
                            '/**/width:20px', r'w\69 dth:20px'):
            self.rejects(GOOD.replace('<rect data-role="bounds"', f'<rect style="{declaration}" data-role="bounds"', 1), 'CSS')

    def test_hidden_metadata_carriers(self):
        for attribute in ('display="none"', 'visibility="hidden"', 'opacity="0"', 'hidden', 'aria-hidden="true"',
                          'style="/**/display:none !important"', 'style="opacity:0%"', 'style="visibility:collapse"'):
            self.rejects(GOOD.replace('data-object-id="client"', f'{attribute} data-object-id="client"', 1), 'must not be hidden')
            self.rejects(GOOD.replace('data-change="ADDED"', f'{attribute} data-change="ADDED"', 1), 'must not be hidden')
        for rule in ('g {display:none}', '[data-change] {visibility:hidden}', 'rect {opacity:0}'):
            self.rejects(GOOD.replace('</style>', rule + '</style>'), 'CSS must not hide')
        self.clean(GOOD.replace('</style>', '.scroll-hint {display:none}</style>'))

    def test_nonrendering_metadata(self):
        original = component('client', 'unchanged', 'web:v1', 0, 0)
        for tag in ('defs', 'symbol', 'mask', 'pattern', 'template', 'title'):
            with self.subTest(tag=tag):
                source = GOOD.replace(original, f'<{tag}>{original}</{tag}>', 1)
                # HTMLParser versions expose title contents as nodes or text.
                if tag == 'title':
                    self.assertRegex(
                        '\n'.join(checker.check_source(SYNTHETIC_PATH, source)),
                        r'nonrendering containers|dangling relationship endpoint',
                    )
                else:
                    self.rejects(source, 'nonrendering containers')

    def test_animation_use_and_nested_svg(self):
        for extra in ('<animate attributeName="x"/>', '<animateTransform/>', '<use href="#client"/>', '<svg/>'):
            self.rejects(GOOD.replace('</svg>', extra + '</svg>'), 'unsupported')

    def test_path_grammar_fails_closed(self):
        for value in ('', 'm40 20 h40', 'M40 20 H', 'M40 NaN H80', 'M40 20 H80 Z', 'M40 20 M80 20', 'M40 20 H800', 'M40 20 H1e309',
                      'M,40 20 H80', 'M40,,20 H80', 'M40 20, H80', 'M40 20 H80,'):
            self.rejects(GOOD.replace('M40 20 H80', value, 1), 'relationship geometry')

    def test_ledger_coverage(self):
        self.rejects(GOOD.replace('data-target="api"', 'data-target="client"'), 'missing ledger coverage')
        self.rejects(GOOD.replace('data-target="api"', 'data-target="missing"'), 'unexpected ledger coverage')
        self.rejects(GOOD.replace('data-change="CHANGED"', 'data-change="MOVED"'), 'missing ledger coverage')
        self.rejects(GOOD.replace('data-target="api"', 'data-target="api worker"'), 'single target ID')

    def test_ledger_cannot_claim_unchanged(self):
        self.rejects(GOOD.replace('</svg>', '<text data-change="UNCHANGED" data-target="client">UNCHANGED client</text></svg>'), 'invalid ledger change')

    def test_ledger_text_and_membership(self):
        self.rejects(GOOD.replace('CHANGED api: migration detail', 'MOVED api: migration detail'), 'ledger text')
        self.rejects(GOOD.replace('CHANGED api: migration detail', 'CHANGED'), 'ledger text')
        self.rejects(GOOD.replace('<text>client</text>', '<text data-change="ADDED" data-target="queue">ADDED queue</text>', 1), 'outside both snapshots')
        self.rejects(GOOD.replace('</html>', '<text data-change="ADDED" data-target="queue">ADDED queue</text></html>'), 'in the diagram')

    def test_duplicate_ledger(self):
        self.rejects(GOOD.replace('</svg>', '<text data-change="ADDED" data-target="queue">ADDED queue</text></svg>'), 'duplicate ledger entry')

    def test_component_budget(self):
        source = GOOD
        for identity in ('six', 'seven', 'eight'):
            source = source.replace('<text>client</text></g>', f'<text>client</text></g>{component(identity, "unchanged", identity, 0, 120)}')
        self.rejects(source, 'component budget')

    def test_relationship_budget(self):
        source = GOOD
        for index in range(6):
            source = source.replace('<text>client</text></g>', '<text>client</text></g>' + relationship(f'extra{index}', 'unchanged', 'client', 'api', 'M40 20 H80'))
        self.rejects(source, 'relationship budget')

    def test_ledger_budget(self):
        extra = ''.join(f'<text data-change="ADDED" data-target="extra{i}">ADDED extra</text>' for i in range(2))
        self.rejects(GOOD.replace('</svg>', extra + '</svg>'), 'ledger budget')

    def test_all_shipped_variants(self):
        for suffix in ('', '-dark', '-full'):
            path = ROOT / f'skills/diagram-design/assets/example-architecture-delta{suffix}.html'
            with self.subTest(variant=suffix):
                self.assertTrue(path.is_file(), f'missing shipped variant: {path.name}')
                source = path.read_text(encoding='utf-8')
                self.assertEqual(checker.check_source(path, source), [])
                for status in ('ADDED', 'REMOVED', 'CHANGED', 'MOVED', 'REWIRED'):
                    self.assertIn(f'data-change="{status}"', source)

    def test_cli_discovery_and_failures(self):
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        for args in ([], ['--all']):
            result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('3 file(s)', result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'diagram.html'
            path.write_text(GOOD, encoding='utf-8')
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            path.write_text(GOOD.replace('data-signature="web:v1"', 'data-signature=""', 1), encoding='utf-8')
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 1)
            path.unlink()
            result = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
