#!/usr/bin/env python3
"""Independent bit-layout fixtures and adversarial packet mutations."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verify_static_svg_visibility import FONTS_HREF, TEMPLATE_CSS

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-packet-structure.py"


def specimen() -> str:
    # Literal positions are hand-derived at 32 pixels/bit, independent of the checker.
    rows = (
        (0, 156, (("version", "Version", 0, 4, 128, 128),
                  ("flags", "Flags", 4, 4, 256, 128),
                  ("length", "Length", 8, 16, 384, 512),
                  ("kind", "Kind", 24, 8, 896, 256))),
        (32, 324, (("sequence", "Sequence", 32, 32, 128, 1024),)),
    )
    content = '<text x="128" y="48" fill="#4f5d75" font-size="14" font-family="Geist, sans-serif">BIT BOUNDARIES</text>'
    content += '<g data-packet-axis="32" data-packet-source="Illustrative frame schema">'
    content += '<line data-packet-baseline="true" x1="128" x2="1152" y1="112" y2="112" stroke="#4f5d75" stroke-width="2"/>'
    for bit, x in ((0, 128), (8, 384), (16, 640), (24, 896), (32, 1152)):
        content += (
            f'<g data-bit-boundary="{bit}"><line x1="{x}" x2="{x}" y1="104" y2="120" stroke="#4f5d75" stroke-width="2"/>'
            f'<text x="{x}" y="88" fill="#4f5d75" font-size="12" font-family="Geist Mono, monospace" text-anchor="middle">{bit}</text></g>'
        )
    content += '</g>'
    for offset, top, fields in rows:
        content += f'<g data-packet-row="{offset}">'
        content += f'<text data-packet-row-label="true" x="64" y="{top + 60}" fill="#4f5d75" font-size="12" font-family="Geist Mono, monospace">{offset}</text>'
        for fid, name, start, width, x, pixels in fields:
            content += (
                f'<g data-packet-field="{fid}" data-field-name="{name}" data-bit-offset="{start}" data-bit-width="{width}">'
                f'<rect x="{x}" y="{top}" width="{pixels}" height="104" fill="#f5f5f5" stroke="#4f5d75" stroke-width="2"/>'
                f'<text data-packet-label="name" x="{x + 12}" y="{top + 36}" fill="#2d3142" font-size="16" font-family="Geist, sans-serif">{name}</text>'
                f'<text data-packet-label="range" x="{x + 12}" y="{top + 76}" fill="#4f5d75" font-size="12" font-family="Geist Mono, monospace">{start}–{start + width - 1} / {width}b</text></g>'
            )
        content += '</g>'
    content += '<text data-packet-source-label="true" x="128" y="536" fill="#4f5d75" font-size="12" font-family="Geist, sans-serif">Illustrative frame schema · 64 bits</text>'
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f'<title>Packet fixture</title><link rel="stylesheet" href="{FONTS_HREF}"><style>{TEMPLATE_CSS}</style></head>'
        '<body><div class="frame"><p class="eyebrow">Packet structure</p><h1>Illustrative frame</h1>'
        '<p class="subtitle">A fixed-width illustrative header.</p><div class="canvas">'
        '<svg viewBox="0 0 1200 600" role="img" data-diagram-type="packet-structure" aria-labelledby="packet-title packet-desc">'
        '<title id="packet-title">Illustrative frame</title><desc id="packet-desc">Five fields occupy two 32-bit rows.</desc>'
        '<rect width="1200" height="600" fill="#f5f5f5"/>' + content + '</svg></div></div></body></html>'
    )


class PacketChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert VERIFIER.is_file(), "packet-structure verifier has not been implemented"
        spec = importlib.util.spec_from_file_location("verify_packet_structure", VERIFIER)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def check(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "packet.html"
            path.write_text(source, encoding="utf-8")
            return self.module.check(path)

    def test_true_layout_and_equivalent_numbers(self):
        self.assertEqual(self.check(specimen()), [])
        self.assertEqual(self.check(specimen().replace('width="128"', 'width="1.28e2"')), [])
        self.assertEqual(self.check(specimen().replace('x="140"', "x='140'")), [])
        shifted = re.sub(r'\b(x|x1|x2)="([0-9]+)"', lambda m: f'{m[1]}="{int(m[2]) + 16}"', specimen())
        self.assertEqual(self.check(shifted), [])

    def test_a_different_bit_scale_uses_the_same_geometry(self):
        source = specimen().replace('data-packet-axis="32"', 'data-packet-axis="64"')
        source = re.sub(r'(data-bit-(?:offset|width|boundary)|data-packet-row)="([0-9]+)"',
                        lambda m: f'{m[1]}="{int(m[2]) * 2}"', source)
        for old, new in (('0–3 / 4b', '0–7 / 8b'), ('4–7 / 4b', '8–15 / 8b'),
                         ('8–23 / 16b', '16–47 / 32b'), ('24–31 / 8b', '48–63 / 16b'),
                         ('32–63 / 32b', '64–127 / 64b')):
            source = source.replace(old, new)
        source = re.sub(r'>(8|16|24|32)</text>', lambda m: f'>{int(m[1]) * 2}</text>', source)
        source = source.replace('· 64 bits', '· 128 bits')
        self.assertEqual(self.check(source), [])

    def test_geometry_lies_fail_without_metadata_changes(self):
        source = specimen()
        for old, new in (
            ('width="128"', 'width="160"'),
            ('x="256" y="156"', 'x="288" y="156"'),
            ('width="1024" height="104"', 'width="512" height="104"'),
            ('y="324" width="1024"', 'y="156" width="1024"'),
            ('x1="640" x2="640"', 'x1="672" x2="672"'),
            ('y="192"', 'y="400"'),
        ):
            with self.subTest(new=new):
                self.assertIn(old, source)
                self.assertTrue(self.check(source.replace(old, new, 1)))

    def test_incorrect_bit_data_and_visible_labels_fail(self):
        source = specimen()
        for old, new in (
            ('data-bit-offset="4"', 'data-bit-offset="5"'),
            ('data-bit-offset="4"', 'data-bit-offset="3"'),
            ('data-bit-width="4"', 'data-bit-width="0"'),
            ('data-bit-width="4"', 'data-bit-width="-1"'),
            ('data-bit-width="4"', 'data-bit-width="NaN"'),
            ('data-bit-width="4"', 'data-bit-width="4.5"'),
            ('data-packet-row="32"', 'data-packet-row="64"'),
            ('data-packet-field="flags"', 'data-packet-field="version"'),
            ('data-packet-axis="32"', 'data-packet-axis="16"'),
            ('>0–3 / 4b<', '>0–4 / 4b<'),
            ('>Version<', '>Flags<'),
            ('>16</text>', '>17</text>'),
            ('>32</text>', '>0</text>'),
            ('data-packet-source="Illustrative frame schema"', 'data-packet-source=""'),
            ('Illustrative frame schema · 64 bits</text>', 'Unknown source</text>'),
        ):
            with self.subTest(new=new):
                self.assertIn(old, source)
                self.assertTrue(self.check(source.replace(old, new, 1)))

    def test_browser_visibility_and_unsupported_svg_fail(self):
        source = specimen()
        for attribute in (
            'display="none"', 'visibility="hidden"', 'opacity="0"',
            'transform="translate(32 0)"', 'style="x:999px"', 'clip-path="inset(100%)"',
            'filter="opacity(0)"', 'font-size="0"', 'aria-hidden="true"',
        ):
            with self.subTest(attribute=attribute):
                self.assertTrue(self.check(source.replace('<g data-packet-field=', f'<g {attribute} data-packet-field=', 1)))
        for old, new in (
            ('<rect width="1200" height="600" fill="#f5f5f5"/>', '<rect width="1200" height="600" fill="#f5f5f5" stroke="#2d3142" stroke-width="2400"/>'),
            ('viewBox="0 0 1200 600"', 'viewBox="0\u00a00\u00a01200\u00a0600"'),
            ('</style>', 'svg text{display:none}</style>'),
            ('</svg>', '<rect width="1200" height="600" fill="#f5f5f5"/></svg>'),
            ('>Version</text>', '>Wrong</text><desc>Version</desc>'),
            ('fill="#2d3142" font-size="16"', 'fill="#f5f5f5" font-size="16"'),
            ('data-packet-label="name"', 'style="fill:transparent" data-packet-label="name"'),
            ('</svg>', '<animate attributeName="opacity" to="0"/></svg>'),
            ('<div class="canvas">', '<div class="canvas" style="display:none">'),
            ('width="128"', 'width="128" width="1"'),
        ):
            with self.subTest(new=new):
                self.assertTrue(self.check(source.replace(old, new, 1)))

    def test_comments_do_not_supply_fields_or_select_a_fake_svg(self):
        source = specimen()
        first = re.search(r'<g data-packet-field="version".*?</g>', source).group()
        self.assertTrue(self.check(source.replace(first, '<!--' + first + '-->')))
        false_svg = source[source.index('<svg '):source.index('</svg>') + 6]
        damaged = source.replace('width="128"', 'width="1"', 1)
        self.assertTrue(self.check(damaged.replace('<body>', '<body><!--' + false_svg + '-->')))

    def test_wrong_row_and_overlong_labels_fail(self):
        source = specimen()
        self.assertTrue(self.check(source.replace('data-packet-row="0"', 'data-packet-row="32"', 1)))
        self.assertTrue(self.check(source.replace('Version', 'Version label far too long for four bits')))
        self.assertTrue(self.check(source.replace('Version', 'WWWWWWWW')))
        self.assertTrue(self.check(source.replace('height="104"', 'height="1"', 1)))

    def test_nonbreaking_spaces_cannot_hide_overflowing_range_text(self):
        source = specimen()
        self.assertTrue(self.check(source.replace('0–3 / 4b', '0–3' + '\u00a0' * 30 + '/ 4b', 1)))
        self.assertEqual(self.check(source.replace('0–3 / 4b', '0–3' + ' ' * 30 + '/ 4b', 1)), [])

    def test_invalid_svg_numbers_and_duplicate_html_attributes_fail(self):
        source = specimen()
        for value in ('1_28', '１２８', '١٢٨', 'inf', 'NaN', '128px', '\u00a0128', '128\u00a0'):
            with self.subTest(value=value):
                self.assertTrue(self.check(source.replace('width="128"', f'width="{value}"', 1)))
        link = '<link rel="stylesheet"'
        self.assertTrue(self.check(source.replace(link, '<link href="data:text/css,svg%7Bdisplay:none%7D" rel="stylesheet"', 1)))

    def test_tick_and_row_labels_cannot_intrude_on_other_bands(self):
        source = specimen()
        for old, new in (('y="88"', 'y="48"'), ('y="216"', 'y="156"'),
                         ('x="128" y="88" fill="#4f5d75" font-size="12"', 'x="128" y="72" fill="#4f5d75" font-size="28"')):
            with self.subTest(new=new):
                self.assertTrue(self.check(source.replace(old, new, 1)))

    def test_all_rejects_individually_valid_variants_with_different_field_data(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'variant-{i}.html' for i in range(3)]
            for i, path in enumerate(paths):
                path.write_text(specimen().replace('Kind', 'Type') if i == 2 else specimen(), encoding='utf-8')
                self.assertEqual(self.module.check(path), [])
            original_paths, original_argv = self.module.EXAMPLES, sys.argv
            try:
                self.module.EXAMPLES, sys.argv = paths, [str(VERIFIER), '--all']
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(self.module.main(), 1)
                self.assertIn('same bit layout', output.getvalue())
            finally:
                self.module.EXAMPLES, sys.argv = original_paths, original_argv

    def test_cli_and_all_shipped_variants(self):
        result = subprocess.run([sys.executable, str(VERIFIER), '--all'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('PASS '), 3)
        result = subprocess.run([sys.executable, str(VERIFIER), '/missing/packet.html'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
