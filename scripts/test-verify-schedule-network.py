#!/usr/bin/env python3
"""Independent CPM oracles and adversarial rendered schedule contracts."""

from __future__ import annotations
import importlib.util
from decimal import Decimal
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from verify_static_svg_visibility import TEMPLATE_CSS, FONTS_HREF

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-schedule-network.py"
# Hand-derived oracle, never produced by the implementation being tested.
ROWS = [
    ("A", "Scope", "2", "0", "2", "0", "2", "0", True, 0, 48, 240),
    ("B", "Build", "4", "2", "6", "2", "6", "0", True, 1, 336, 96),
    ("C", "Prepare", "3", "2", "5", "3", "6", "1", False, 1, 336, 384),
    ("D", "Integrate", "2", "6", "8", "6", "8", "0", True, 2, 624, 240),
    ("E", "Release", "1", "8", "9", "8", "9", "0", True, 3, 912, 240),
]
ROUTES = [
    (
        "A",
        "B",
        True,
        "M 288 300 H 304 Q 312 300 312 292 V 192 Q 312 184 320 184 H 324",
        "M 328 178 L 336 184 L 328 190",
    ),
    (
        "A",
        "C",
        False,
        "M 288 356 H 304 Q 312 356 312 364 V 464 Q 312 472 320 472 H 324",
        "M 328 466 L 336 472 L 328 478",
    ),
    (
        "B",
        "D",
        True,
        "M 576 184 H 592 Q 600 184 600 192 V 292 Q 600 300 608 300 H 612",
        "M 616 294 L 624 300 L 616 306",
    ),
    (
        "C",
        "D",
        False,
        "M 576 472 H 592 Q 600 472 600 464 V 364 Q 600 356 608 356 H 612",
        "M 616 350 L 624 356 L 616 362",
    ),
    ("D", "E", True, "M 864 328 H 900", "M 904 322 L 912 328 L 904 334"),
]


def fixture(dark=False, full=False):
    paper, ink, muted, accent = (
        ("#2d3142", "#f5f5f5", "#bfc0c0", "#f08a59")
        if dark
        else ("#f5f5f5", "#2d3142", "#4f5d75", "#bf4520")
    )
    css = TEMPLATE_CSS
    if dark:
        css = (
            css.replace("#2d3142", "TEMP")
            .replace("#f5f5f5", "#2d3142")
            .replace("TEMP", "#f5f5f5")
            .replace("#4f5d75", "#bfc0c0")
            .replace("#bf4520", "#f08a59")
            .replace("solid #bfc0c0", "solid rgba(245,245,245,0.12)")
        )

    def text(x, y, value, attrs="", size=12):
        return f'<text x="{x}" y="{y}" fill="{ink}" font-size="{size}" font-family="Geist Mono, monospace" {attrs}>{value}</text>'

    slug = "schedule-network" + ("-dark" if dark else "-full" if full else "")
    body = [
        f'<rect width="1200" height="720" fill="{paper}"/>',
        text(48, 48, "PROJECT FINISH 9 days", 'data-schedule-summary="finish"', 16),
    ]
    for a, b, critical, shaft, head in ROUTES:
        width = "2" if critical else "1"
        colour = ink if critical else muted
        body.append(
            f'<g data-schedule-link="finish-to-start" data-from="{a}" data-to="{b}" data-critical="{str(critical).lower()}" data-diagram-role="precedence">'
            + "".join(
                f'<path d="{p}" fill="none" stroke="{colour}" stroke-width="{width}"/>'
                for p in (shaft, head)
            )
            + "</g>"
        )
    for id, name, dur, es, ef, ls, lf, tf, critical, rank, x, y in ROWS:
        body.append(
            f'<g data-task-id="{id}" data-task-name="{name}" data-duration="{dur}" data-critical="{str(critical).lower()}" data-rank="{rank}" data-diagram-role="task"><rect x="{x}" y="{y}" width="240" height="176" rx="4" fill="{paper}" stroke="{ink}" stroke-width="{2 if critical else 1}"/>'
        )
        for field, value, dx, dy, size in [
            ("name", id + ": " + name, 16, 24, 12),
            ("duration", "DUR " + dur + " days", 16, 48, 12),
            ("es", "ES " + es, 16, 76, 12),
            ("ef", "EF " + ef, 128, 76, 12),
            ("ls", "LS " + ls, 16, 104, 12),
            ("lf", "LF " + lf, 128, 104, 12),
            ("tf", "TF " + tf, 16, 132, 12),
            ("status", "CRITICAL" if critical else "FLOAT", 16, 156, 12),
        ]:
            body.append(
                text(x + dx, y + dy, value, f'data-schedule-field="{field}"', size)
            )
        body.append("</g>")
    body.append(
        text(
            48,
            660,
            "ILLUSTRATIVE SCHEDULE · days · ORIGIN 0 · FINISH-TO-START · ZERO LAG",
            'data-schedule-summary="assumptions"',
        )
    )
    body.append(
        text(
            48,
            688,
            "Task widths and spacing are not proportional to time.",
            'data-schedule-summary="scale"',
        )
    )
    cards = (
        '<div class="cards"><section><h2>Critical chain</h2><p>A, B, D and E determine the nine-day finish.</p></section><section><h2>One day of float</h2><p>C can move from day 2 to day 3 without delaying D.</p></section><section><h2>Boundary</h2><p>Illustrative durations; no calendar or resource constraints.</p></section></div>'
        if full
        else ""
    )
    return f'<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>Schedule network · Diagram Design</title><link href="{FONTS_HREF}" rel="stylesheet"><style>{css}</style></head><body><div class="frame"><p class="eyebrow">Schedule network · Diagram Design</p><h1>The parallel task has one day of float</h1><p class="subtitle">An illustrative task plan. Follow precedence, then read the schedule in each box.</p><div class="canvas"><svg viewBox="0 0 1200 720" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc" data-diagram-type="schedule-network" data-time-unit="days" data-project-duration="9" data-schedule-origin="0"><title id="{slug}-title">Illustrative five-task schedule</title><desc id="{slug}-desc">A branches into B and C, then joins at D before E. Finish is nine days; C has one day of float.</desc>{"".join(body)}</svg></div>{cards}</div></body></html>\n'


class ScheduleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert VERIFIER.exists(), "Schedule verifier has not been implemented"
        spec = importlib.util.spec_from_file_location("schedule_verifier", VERIFIER)
        cls.v = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.v)

    def check_source(self, source):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "schedule.html"
            p.write_bytes(source.encode("utf-8"))
            return self.v.check(p)

    def test_valid_all_skins(self):
        for dark, full in [(False, False), (True, False), (False, True)]:
            self.assertEqual(self.check_source(fixture(dark, full)), [])

    def test_each_printed_field_is_checked(self):
        source = fixture()
        for field in ("name", "duration", "es", "ef", "ls", "lf", "tf", "status"):
            changed, n = re.subn(
                r'(data-schedule-field="' + field + r'"[^>]*>)[^<]+',
                r"\g<1>WRONG",
                source,
                count=1,
            )
            self.assertEqual(n, 1)
            with self.subTest(field=field):
                self.assertTrue(self.check_source(changed))

    def test_plausible_wrong_float(self):
        source = fixture().replace(">TF 1</text>", ">TF 0</text>")
        self.assertTrue(any("tf" in s.casefold() for s in self.check_source(source)))

    def test_adversarial_source_mutations(self):
        source = fixture()
        cases = [
            ('data-project-duration="9"', 'data-project-duration="8"'),
            ("PROJECT FINISH 9", "PROJECT FINISH 8"),
            ('data-duration="2"', 'data-duration="NaN"'),
            ('data-duration="2"', 'data-duration="Infinity"'),
            ('data-duration="2"', 'data-duration="0"'),
            ('data-duration="2"', 'data-duration="-1"'),
            ('data-duration="2"', 'data-duration="2_0"'),
            ('data-duration="2"', 'data-duration="٢"'),
            ('data-time-unit="days"', 'data-time-unit="weeks"'),
            ('data-schedule-origin="0"', 'data-schedule-origin="1"'),
            ('data-task-id="B"', 'data-task-id="A"'),
            ('data-from="A" data-to="B"', 'data-from="E" data-to="B"'),
            ('data-from="A" data-to="B"', 'data-from="Z" data-to="B"'),
            ('data-from="A" data-to="B"', 'data-from="A" data-to="A"'),
            (
                'data-schedule-link="finish-to-start"',
                'data-schedule-link="start-to-start"',
            ),
            (
                'data-schedule-link="finish-to-start"',
                'data-lag="1" data-schedule-link="finish-to-start"',
            ),
            ('data-critical="true"', 'data-critical="false"'),
            (">A: Scope</text>", ">B: Build</text>"),
            ('data-schedule-field="es"', 'data-schedule-field="unknown"'),
            ('data-schedule-field="es"', 'data-schedule-field="ef"'),
            ('data-schedule-field="es"', ""),
            ('data-task-id="A"', 'style="display:none" data-task-id="A"'),
            ('data-task-id="A"', 'transform="translate(1)" data-task-id="A"'),
            ('data-task-id="A"', 'opacity="0.01" data-task-id="A"'),
            ('data-schedule-field="tf"', 'fill-opacity="0" data-schedule-field="tf"'),
            ("</style>", "text{fill:transparent!important}</style>"),
            ("</style>", r"g{tr\61nsform:translateX(200px)}</style>"),
            ("</style>", r"g{\64 isplay:none}</style>"),
            ("M 904 322 L 912 328 L 904 334", "M 904 322 L 912 300 L 904 334"),
            ("M 288 300 H 304", "M 288 30 H 304"),
            ("Q 312 300 312 292", "Q 900 900 312 292"),
            ('data-rank="3"', 'data-rank="1"'),
            ('x="64" y="264"', 'x="900" y="264"'),
            ('data-schedule-summary="finish"', 'data-schedule-summary="other"'),
            ("Task widths and spacing are not proportional to time.", "Time to scale."),
            ("ILLUSTRATIVE SCHEDULE", "VERIFIED PROJECT"),
            ("</svg>", '<rect width="1200" height="720" fill="#f5f5f5"/></svg>'),
            ('data-task-id="A"', 'data-task-id="A" data-task-id="Z"'),
            (
                'data-diagram-type="schedule-network"',
                'data-diagram-type="schedule-network" style="display:none"',
            ),
        ]
        for old, new in cases:
            with self.subTest(old=old, new=new):
                self.assertIn(old, source)
                self.assertTrue(self.check_source(source.replace(old, new, 1)))

    def test_summary_position_and_unbound_text(self):
        source = fixture()
        for old, new in [
            ('x="48" y="48"', 'x="47" y="264"'),
            (
                'data-schedule-summary="finish"',
                'text-anchor="end" data-schedule-summary="finish"',
            ),
            (
                "</svg>",
                '<text x="47" y="264" fill="#2d3142" font-size="16" font-family="Geist Mono, monospace">PROJECT FINISH 8 days</text></svg>',
            ),
        ]:
            with self.subTest(new=new):
                self.assertTrue(self.check_source(source.replace(old, new, 1)))

    def test_geometry_ports_and_routes(self):
        source = fixture()
        cases = [
            ("M 864 328 H 900", "M 864 328 V 400 H 900 V 328"),
            ("M 288 356 H 304", "M 288 300 H 296 V 356 H 304"),
            ("M 864 328 H 900", "M 864 328 H 884 V 304 H 900 V 328"),
        ]
        for old, new in cases:
            with self.subTest(route=new):
                self.assertTrue(self.check_source(source.replace(old, new)))

    def test_invisible_task_borders_are_rejected(self):
        source = fixture()
        # Put the transparent stroke on the border, rather than hiding text.
        for opacity in ("0", "0.01", "0%", "0.0"):
            changed = re.sub(
                r'(<rect x="[^>]+)(/>)',
                rf'\g<1> stroke-opacity="{opacity}"\g<2>',
                source,
            )
            with self.subTest(opacity=opacity):
                self.assertNotEqual(changed, source)
                self.assertTrue(self.check_source(changed))

    def test_visible_border_opacity_remains_valid(self):
        source = fixture()
        for opacity in ("1", "100%"):
            changed = re.sub(
                r'(<rect x="[^>]+)(/>)',
                rf'\g<1> stroke-opacity="{opacity}"\g<2>',
                source,
            )
            with self.subTest(opacity=opacity):
                self.assertEqual(self.check_source(changed), [])

    def test_namespace_prefixed_text_cannot_replace_visible_labels(self):
        # XML resolves this alias to SVG text, but HTML renders x:text as an
        # unknown zero-width element. Check the actual authored tag too.
        source = fixture().replace(
            "<svg ", '<svg xmlns:x="http://www.w3.org/2000/svg" '
        )
        source = source.replace("<text ", "<x:text ").replace("</text>", "</x:text>")
        self.assertTrue(self.check_source(source))

    def test_extra_lines_cannot_cover_summary(self):
        source = fixture()
        lines = "".join(
            f'<line x1="48" x2="260" y1="{y}" y2="{y}" stroke="#2d3142" stroke-width="4"/>'
            for y in range(32, 53, 4)
        )
        self.assertTrue(self.check_source(source.replace("</svg>", lines + "</svg>")))

    def test_missing_backdrop_reports_a_finding(self):
        source = fixture().replace(
            '<rect width="1200" height="720" fill="#f5f5f5"/>', ""
        )
        self.assertTrue(self.check_source(source))

    def test_hidden_right_value_cannot_replace_visible_wrong_value(self):
        source = fixture().replace(
            ">TF 1</text>", '>TF 0<tspan display="none">TF 1</tspan></text>'
        )
        self.assertTrue(self.check_source(source))

    def test_missing_task_or_edge_or_duplicate_link(self):
        source = fixture()
        edge = re.search(r"<g data-schedule-link=.*?</g>", source).group()
        for changed in (source.replace(edge, ""), source.replace(edge, edge + edge)):
            self.assertTrue(self.check_source(changed))

    def test_nonrendered_task_or_edge_is_rejected(self):
        source = fixture()
        task = re.search(r'<g data-task-id="A".*?</g>', source).group()
        edge = re.search(r"<g data-schedule-link=.*?</g>", source).group()
        summary = re.search(
            r'<text[^>]*data-schedule-summary="finish"[^>]*>.*?</text>', source
        ).group()
        for mark in (task, edge, summary):
            for wrapper in ("defs", "title", "desc"):
                with self.subTest(wrapper=wrapper, mark=mark[:40]):
                    self.assertTrue(
                        self.check_source(
                            source.replace(
                                mark, "<" + wrapper + ">" + mark + "</" + wrapper + ">"
                            )
                        )
                    )

    def test_model_rejects_disconnected_and_unsupported_graphs(self):
        for durations, edges in [
            ({"A": Decimal(1), "B": Decimal(1), "C": Decimal(1)}, [("A", "B")]),
            ({"A": Decimal(1), "B": Decimal(1)}, [("A", "B"), ("B", "A")]),
            ({"A": Decimal(1), "B": Decimal(1)}, [("A", "B"), ("A", "B")]),
            ({"A": Decimal(0), "B": Decimal(1)}, [("A", "B")]),
        ]:
            with self.subTest(edges=edges):
                with self.assertRaises(ValueError):
                    self.v.calculate(durations, edges)

    def test_exact_fractional_arithmetic_and_ties(self):
        d = {
            k: Decimal(v)
            for k, v in {"A": ".1", "B": ".2", "C": ".2", "D": ".1"}.items()
        }
        edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"), ("A", "D")]
        result = self.v.calculate(d, edges)
        self.assertEqual(result["finish"], Decimal(".4"))
        self.assertEqual(result["tasks"]["D"]["es"], Decimal(".3"))
        self.assertEqual(
            result["critical_edges"], {("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")}
        )

    def test_multiple_starts_ends_and_small_float(self):
        result = self.v.calculate(
            {
                k: Decimal(v)
                for k, v in {"A": "1", "B": "1.000001", "C": "1", "D": "1"}.items()
            },
            [("A", "C"), ("B", "C"), ("B", "D")],
        )
        self.assertEqual(result["finish"], Decimal("2.000001"))
        self.assertEqual(result["tasks"]["A"]["tf"], Decimal(".000001"))
        self.assertNotIn(("A", "C"), result["critical_edges"])

    def test_unrelated_sibling_is_not_claimed(self):
        self.assertEqual(
            self.check_source(
                '<html><svg data-diagram-type="event-modeling"></svg></html>'
            ),
            [],
        )
        self.assertTrue(
            self.check_source(
                fixture().replace('data-diagram-type="schedule-network"', "")
            )
        )

    def test_canonical_file_without_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "example-schedule-network.html"
            p.write_bytes(b"<html><svg></svg></html>")
            self.assertTrue(self.v.check(p))

    def test_shipped_sibling_scope(self):
        for p in (ROOT / "skills/diagram-design/assets").glob("example-*.html"):
            if "schedule-network" not in p.name:
                with self.subTest(file=p.name):
                    self.assertEqual(self.v.check(p), [])

    def test_all_shipped_examples(self):
        for suffix in ("", "-dark", "-full"):
            p = (
                ROOT
                / f"skills/diagram-design/assets/example-schedule-network{suffix}.html"
            )
            self.assertTrue(p.is_file(), str(p))
            self.assertEqual(self.v.check(p), [])


if __name__ == "__main__":
    unittest.main()
