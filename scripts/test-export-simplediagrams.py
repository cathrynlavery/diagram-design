#!/usr/bin/env python3
"""Tests for the SimpleDiagrams export (skills/diagram-design/scripts/export_simplediagrams.py).

Covers the export's contract: every shipped example becomes a package that
keeps the document format's rules, the translation keeps boxes, labels and
connectors editable, malformed input fails clearly instead of hanging or
writing a broken document, re-exports are byte-identical, and an existing
document is never replaced.

``format_problems`` checks the format rules most likely to break, so CI
catches a bad document without the app. Opening one in SimpleDiagrams remains
the final check.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills/diagram-design/scripts"
ASSETS = ROOT / "skills/diagram-design/assets"
HELPER = SCRIPTS / "export_simplediagrams.py"

sys.path.insert(0, str(SCRIPTS))  # the exporter imports export_svg beside it

Record = dict[str, Any]

FLOWCHART = """<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg">
  <title>Order flow</title>
  <defs><marker id="arrow" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#4f5d75"/></marker></defs>
  <rect width="100%" height="100%" fill="#f5f5f5"/>
  <line x1="160" y1="60" x2="240" y2="60" stroke="#4f5d75" stroke-width="1.2" marker-end="url(#arrow)"/>
  <rect x="40" y="40" width="120" height="40" rx="6" fill="#ffffff" stroke="#2d3142"/>
  <text x="100" y="58" font-size="12" font-weight="600" font-family="'Geist', sans-serif" text-anchor="middle">Place order</text>
  <text x="100" y="72" font-size="9" fill="#4f5d75" font-family="'Geist Mono', monospace" text-anchor="middle">web shop</text>
  <polygon points="300,20 360,60 300,100 240,60" fill="#ffffff" stroke="#2d3142"/>
  <text x="300" y="64" font-size="12" text-anchor="middle">Paid?</text>
  <text x="40" y="200" font-size="10">A free note</text>
</svg>"""


NESTED_ICON = '<svg x="1" y="1" width="8" height="8" viewBox="0 0 10 10">{}</svg>'


def load_helper() -> ModuleType:
    """Import the exporter from its file, as the skill runs it."""
    spec = importlib.util.spec_from_file_location("diagram_design_export_simplediagrams", HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {HELPER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def exportable_assets() -> list[Path]:
    """Every shipped diagram, without the gallery and the icon sheet."""
    return sorted(
        path for path in ASSETS.glob("*.html") if path.name not in {"index.html", "icons.html"}
    )


def core(element: Record) -> Record:
    """The innermost level of an element record, where its own keys live."""
    inner: Record = element["content"]["content"]["content"]
    return inner


def resolve(element: Record, fraction: Record) -> tuple[float, float]:
    """Where a connection point is drawn: mirrored by the flips, scaled, then turned."""
    item = core(element)
    frame, angle = item["frame"], math.radians(item["rotation_degrees"])
    u = 1 - fraction["x"] if element["content"]["flip_horizontal"] else fraction["x"]
    v = 1 - fraction["y"] if element["content"]["flip_vertical"] else fraction["y"]
    dx, dy = (u - 0.5) * frame["width"], (v - 0.5) * frame["height"]
    return (
        frame["x"] + frame["width"] / 2 + dx * math.cos(angle) - dy * math.sin(angle),
        frame["y"] + frame["height"] / 2 + dx * math.sin(angle) + dy * math.cos(angle),
    )


def package_bytes(package: Path) -> dict[str, bytes]:
    """Every file in a package, by its path inside it."""
    return {
        str(path.relative_to(package)): path.read_bytes()
        for path in sorted(package.rglob("*"))
        if path.is_file()
    }


def format_problems(manifest: Record, document: Record) -> list[str]:
    """The format rules an exporter change is most likely to break, as messages."""
    problems: list[str] = []
    if manifest != {
        "format": "com.simplediagrams.document",
        "format_version": 19,
        "contains_legacy_source": False,
    }:
        problems.append(f"unexpected manifest {manifest}")
    if document["schema_version"] != 18 or not {"id", "pages", "embedded_assets"} <= set(document):
        problems.append("document.json lacks a top-level key or the right schema version")
    seen = {document["id"]}
    for page in document["pages"]:
        elements = {core(e)["id"]: e for e in page["elements"]}
        for name, element in elements.items():
            path = core(element).get("path")
            if path and path["is_closed"] and len(path["nodes"]) < 3:
                problems.append(f"closed path {name} has fewer than three nodes")
        connections = [c["content"] for c in page["content"]["content"]["connections"]]
        groups = page["content"]["groups"]
        for identifier in (*elements, *(c["id"] for c in connections), *(g["id"] for g in groups)):
            if identifier in seen:
                problems.append(f"identifier {identifier} repeats")
            seen.add(identifier)
        for name, element in elements.items():
            shape = element.get("complex_shape")
            if shape and set(shape) != {"type", "version", "settings", "parts"}:
                problems.append(f"element {name} breaks the complex-shape record")
        for connection in connections:
            for end in ("start_attachment", "end_attachment"):
                if (attachment := connection.get(end)) is None:
                    continue
                target = elements.get(attachment["element_id"])
                points = core(target)["connection_points"] if target else []
                if attachment["connection_point_id"] not in {point["id"] for point in points}:
                    problems.append(f"connector {connection['id']} {end} names no real point")
    return problems


class ExportSimpleDiagramsTests(unittest.TestCase):
    """The exporter's behaviour, from the shipped examples down to single shapes."""

    mod: ModuleType
    flowchart: Record
    elements: list[Record]
    connections: list[Record]

    @classmethod
    def setUpClass(cls) -> None:
        """Load the exporter once and export the small flowchart most tests read."""
        cls.mod = load_helper()
        cls.flowchart = cls.mod.export_document(FLOWCHART, Path("order-flow.html")).document
        page = cls.flowchart["pages"][0]
        cls.elements = [core(element) for element in page["elements"]]
        cls.connections = [c["content"] for c in page["content"]["content"]["connections"]]

    def export(self, svg: str) -> tuple[Record, dict[str, int]]:
        """Export a diagram, check it keeps the format's rules, and return it with its notes."""
        result = self.mod.export_document(svg, Path("case.html"))
        self.assertEqual(format_problems(result.manifest, result.document), [])
        return result.document, result.skipped

    def icon(self, css: str, markup: str) -> str:
        """The stored SVG of the one icon a diagram holds."""
        result = self.mod.export_document(
            f'<style>{css}</style><svg viewBox="0 0 400 300">{markup}</svg>', Path("case.html")
        )
        self.assertEqual(len(result.assets), 1)
        return result.assets[0].data.decode()

    def run_cli(self, *argv: str) -> int:
        """Run the command line quietly; returns its exit status."""
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return int(self.mod.main(list(argv)))

    def element_labelled(self, string: str, document: Record | None = None) -> Record:
        """The element whose text is ``string``, in the flowchart or in ``document``."""
        elements = (
            self.elements
            if document is None
            else [core(e) for e in document["pages"][0]["elements"]]
        )
        return next(element for element in elements if element["text_content"]["string"] == string)

    def test_every_shipped_example_exports_a_valid_package(self) -> None:
        """End to end: the files the command line writes for every example keep the format."""
        with tempfile.TemporaryDirectory() as tmp:
            for source in exportable_assets():
                with self.subTest(source=source.name):
                    package = Path(tmp, f"{source.stem}.simplediagram")
                    errors = io.StringIO()
                    quiet = contextlib.redirect_stdout(io.StringIO())
                    with quiet, contextlib.redirect_stderr(errors):
                        self.assertEqual(self.mod.main([str(source), str(package)]), 0)
                    # A note appearing or vanishing on a shipped example is a change to review.
                    notes = {line.rsplit(" (", 1)[0] for line in errors.getvalue().splitlines()}
                    expected = set()
                    if source.stem == "example-quadrant-consultant":
                        expected = {"note: styled words inside a line take the line's style"}
                    if source.stem.startswith(
                        (
                            "example-exploded-keyboard",
                            "example-exploded-phone",
                            "example-exploded-unboxing",
                            "example-medallion",
                            "example-venn",
                        )
                    ):
                        expected = {"note: clipping and masks left out; shapes are drawn unclipped"}
                    self.assertEqual(notes, expected)
                    self.assertEqual(
                        sorted(p.name for p in package.iterdir()),
                        ["assets", "document.json", "manifest.json"],
                    )
                    manifest, document = (
                        json.loads((package / name).read_bytes().decode("utf-8"))
                        for name in ("manifest.json", "document.json")
                    )
                    self.assertEqual(format_problems(manifest, document), [])
                    stored = {f.name: f.read_bytes() for f in (package / "assets").iterdir()}
                    listed = {a["filename"]: a for a in document["embedded_assets"]}
                    self.assertEqual(stored.keys(), listed.keys())
                    for name, data in stored.items():
                        self.assertEqual(listed[name]["id"], hashlib.sha256(data).hexdigest())
                        self.assertEqual(listed[name]["byte_count"], len(data))
                        self.assertTrue(self.mod.is_safe_svg(ET.fromstring(data)))

    def test_boxes_keep_their_text_with_each_line_styled(self) -> None:
        """A box's lines become its label, and a line in another style gets a run."""
        box = self.element_labelled("Place order\nweb shop")
        self.assertEqual(box["symbol_reference"]["item_id"], "rounded-rectangle")
        self.assertEqual(box["style"]["fill_hex"], "#FFFFFF")
        self.assertEqual(box["text_content"]["base_style"]["weight"], "bold")
        self.assertEqual(box["text_content"]["base_style"]["font_family"], "Geist")
        [run] = box["text_content"]["character_runs"]
        self.assertEqual(run["range"], {"location": 12, "length": 8})
        self.assertEqual(run["style"]["font_family"], "Geist Mono")
        self.assertEqual(run["style"]["color_hex"], "#4F5D75")

    def test_boxes_become_hand_drawn_basic_shapes(self) -> None:
        """Rectangles, circles and labelled outlines become the matching Basic shapes."""
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <rect x="10" y="10" width="80" height="40" fill="#fff" stroke="#000"/><text x="50" y="34">A</text>
          <rect x="110" y="10" width="80" height="40" rx="6" fill="#fff" stroke="#000"/><text x="150" y="34">B</text>
          <rect x="210" y="10" width="80" height="40" rx="20" fill="#fff" stroke="#000"/><text x="250" y="34">C</text>
          <circle cx="50" cy="120" r="30" fill="#fff" stroke="#000"/><text x="50" y="124">D</text>
          <polygon points="150,90 190,120 150,150 110,120" fill="#fff" stroke="#000"/>
          <text x="150" y="124" text-anchor="middle">E</text>
          <polygon points="210,90 390,90 400,120 390,150 210,150 220,120" fill="#fff" stroke="#000"/>
          <text x="300" y="124" text-anchor="middle">F</text>
          <polygon points="50,200 80,230 50,260 20,230" fill="#fff" stroke="#000"/></svg>""")
        shapes = {
            core(e)["text_content"]["string"]: core(e).get("symbol_reference", {}).get("item_id")
            for e in document["pages"][0]["elements"]
        }
        # A wide notched banner (F) is no Basic Chevron, whose notch is half its width;
        # an unlabelled outline ("") is drawing geometry, such as a 3D face.
        expected = {"A": "Square", "B": "rounded-rectangle", "C": "pill", "D": "Circle"}
        self.assertEqual(shapes, expected | {"E": "Diamond", "F": None, "": None})

    def test_square_lines_keep_only_their_real_corners(self) -> None:
        """Rounded corners and hops are dropped, since SimpleDiagrams 5.2 draws neither."""
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <defs><marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <path d="M 40,200 V 108 Q 40,100 48,100 H 120 A 8 8 0 0 1 136 100 H 252 Q 260,100 260,92 V 60"
                fill="none" stroke="#000" marker-end="url(#a)"/>
          <path d="M 40,250 H 120 A 8 8 0 0 1 136 250 H 300" fill="none" stroke="#000" marker-end="url(#a)"/>
          <path d="M 300,40 C 350,40 380,80 380,120" fill="none" stroke="#000" marker-end="url(#a)"/></svg>""")
        bent, straight, curved = document["pages"][0]["content"]["content"]["connections"]
        self.assertEqual(bent["routing"], "right_angle")
        corners = [(p["x"], p["y"]) for p in bent["content"]["points"]]
        self.assertEqual(corners, [(40, 200), (40, 100), (260, 100), (260, 60)])
        self.assertNotIn("routing", straight)
        self.assertEqual(len(straight["content"]["points"]), 2)
        self.assertNotIn("routing", curved)  # a real curve keeps its shape
        self.assertGreater(len(curved["content"]["points"]), 2)
        # Two roundings back to back are a step, with its upright midway.
        [step] = self.mod.parse_path_data(
            "M 400,104 H 348 Q 340,104 340,112 Q 340,120 332,120 H 280"
        )
        self.assertEqual(
            self.mod.right_angle_route(step), [(400, 104), (340, 104), (340, 120), (280, 120)]
        )

    def test_an_arrow_label_becomes_the_connector_label(self) -> None:
        """The skill's arrow label, text on a small paper-coloured box, rides on the connector."""
        document, _ = self.export("""<svg viewBox="0 0 400 200">
          <defs><marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <rect x="20" y="80" width="80" height="40" fill="#fff" stroke="#000"/>
          <rect x="300" y="80" width="80" height="40" fill="#fff" stroke="#000"/>
          <line x1="100" y1="100" x2="300" y2="100" stroke="#000" marker-end="url(#a)"/>
          <rect x="230" y="80" width="40" height="12" fill="#fff"/>
          <text x="250" y="89" font-size="8" text-anchor="middle">SENDS</text></svg>""")
        page = document["pages"][0]
        [arrow] = page["content"]["content"]["connections"]
        label = arrow["content"]["label"]
        self.assertEqual(label["content"]["string"], "SENDS")
        self.assertEqual((label["position"], label["normal_offset"]), (0.75, -14))  # above the line
        self.assertEqual(len(page["elements"]), 2)  # the label's box is gone

    def test_lanes_drawn_as_dividers_become_a_swimlanes_shape(self) -> None:
        """Lanes become one Swimlanes shape holding their content; a legend rule stays a line."""
        source = ASSETS / "example-swimlane.html"
        document = self.mod.export_document(source.read_text(encoding="utf-8"), source).document
        [shape] = [e for e in document["pages"][0]["elements"] if "complex_shape" in e]
        record = shape["complex_shape"]
        self.assertEqual(record["settings"]["direction"], "horizontal")
        titles = [lane["text"]["string"] for lane in record["parts"]]
        self.assertEqual(titles, ["AUTHOR", "REVIEWER", "EDITOR", "CI / CD"])
        self.assertEqual(core(shape)["text_content"]["string"], "")  # no title the page never drew
        # Small text on an arrow's label box is hosted by a box with no record of its own.
        html = source.read_text(encoding="utf-8").replace(
            "</svg>", '<text x="530" y="144" font-size="4">zz</text></svg>', 1
        )
        self.assertTrue(self.mod.export_document(html, source).document["pages"])
        self.assertTrue(all(lane["members"] for lane in record["parts"]))
        lines = [core(e) for e in document["pages"][0]["elements"] if core(e)["kind"] == "path"]
        self.assertTrue(any(line["frame"]["y"] > 420 for line in lines))

    def test_lanes_drawn_as_columns_become_vertical_swimlanes(self) -> None:
        """Columns with a title row become vertical Swimlanes, holding what is drawn in them."""
        dividers = "".join(
            f'<line x1="{x}" y1="20" x2="{x}" y2="380" stroke="#999"/>' for x in (20, 100, 180, 260)
        )
        titles = "".join(
            f'<text x="{60 + i * 80}" y="40" font-size="10" text-anchor="middle">L{i}</text>'
            for i in range(3)
        )
        document, _ = self.export(f"""<svg viewBox="0 0 400 400">{dividers}
          <line x1="20" y1="60" x2="260" y2="60" stroke="#999"/>{titles}
          <rect x="110" y="120" width="60" height="30" fill="#fff" stroke="#000"/></svg>""")
        [shape] = [e for e in document["pages"][0]["elements"] if "complex_shape" in e]
        record = shape["complex_shape"]
        self.assertEqual(record["settings"]["direction"], "vertical")
        self.assertEqual([lane["text"]["string"] for lane in record["parts"]], ["L0", "L1", "L2"])
        self.assertEqual([len(lane["members"]) for lane in record["parts"]], [0, 1, 0])

    def test_a_small_tag_keeps_its_word_on_one_line(self) -> None:
        """A tag too small for the default label margins gets a region wide enough for its word."""
        document, _ = self.export("""<svg viewBox="0 0 200 100">
          <rect x="20" y="20" width="40" height="12" fill="#f5f5f5" stroke="#333"/>
          <text x="40" y="29" font-size="8" text-anchor="middle">SESSION</text></svg>""")
        [tag] = document["pages"][0]["elements"]
        region = tag["content"]["text_layout"]["frame"]
        self.assertGreaterEqual(region["width"] * 40, 7 * 8 * 0.7)

    def test_a_tint_over_an_opaque_copy_is_one_labelled_shape(self) -> None:
        """The skill's tinted node over a paper-coloured copy becomes one shape at the tint."""
        document, _ = self.export("""<svg viewBox="0 0 200 100">
          <rect x="10" y="10" width="160" height="48" rx="6" fill="#f5f5f5"/>
          <rect x="10" y="10" width="160" height="48" rx="6" fill="rgba(191,69,32,0.08)" stroke="#bf4520"/>
          <text x="90" y="38" text-anchor="middle">Write a skill</text></svg>""")
        [node] = [core(e) for e in document["pages"][0]["elements"]]
        self.assertEqual(node["text_content"]["string"], "Write a skill")
        self.assertEqual(node["style"]["fill_hex"], "#BF452014")
        self.assertEqual(node["style"]["stroke_hex"], "#BF4520")

    def test_arrows_attach_to_mirrored_shapes_where_they_are_drawn(self) -> None:
        """A flipped shape's connection point is stored so it resolves where the arrow ends."""
        document, _ = self.export("""<svg viewBox="0 0 300 300">
          <defs><marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <polygon points="100,100 200,100 150,190" fill="#fff" stroke="#000"/>
          <text x="150" y="125" text-anchor="middle">Down</text>
          <line x1="150" y1="260" x2="150" y2="192" stroke="#000" marker-end="url(#a)"/></svg>""")
        page = document["pages"][0]
        [triangle] = [e for e in page["elements"] if core(e)["text_content"]["string"] == "Down"]
        self.assertEqual(core(triangle)["symbol_reference"]["item_id"], "Triangle")
        self.assertTrue(triangle["content"]["flip_vertical"])
        [arrow] = page["content"]["content"]["connections"]
        self.assertEqual(arrow["content"]["end_attachment"]["element_id"], core(triangle)["id"])
        self.assertEqual(arrow["content"]["points"][-1], {"x": 150, "y": 190, "kind": "straight"})
        point_id = arrow["content"]["end_attachment"]["connection_point_id"]
        point = next(p for p in core(triangle)["connection_points"] if p["id"] == point_id)
        self.assertLess(math.dist(resolve(triangle, point), (150, 190)), 0.01)

    def test_arrows_attach_to_the_boxes_they_touch(self) -> None:
        """An arrow becomes a connector attached at both ends, so it follows the boxes."""
        [arrow] = self.connections
        self.assertEqual(arrow["end_ending"], "filledArrow")
        start = self.element_labelled("Place order\nweb shop")["id"]
        self.assertEqual(arrow["start_attachment"]["element_id"], start)
        end = self.element_labelled("Paid?")["id"]
        self.assertEqual(arrow["end_attachment"]["element_id"], end)
        self.assertEqual((arrow["points"][0]["x"], arrow["points"][-1]["x"]), (160, 240))

    def test_a_crowded_box_shares_its_connection_points(self) -> None:
        """Past the format's limit, further arrows share the nearest point and still attach."""
        arrows = "".join(
            f'<line x1="{12 + i * 2}" y1="10" x2="{12 + i * 2}" y2="49" stroke="#000"'
            ' marker-end="url(#a)"/>'
            for i in range(140)
        )
        document, _ = self.export(f"""<svg viewBox="0 0 320 100">
          <defs><marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <rect x="10" y="50" width="300" height="40" fill="#fff" stroke="#000"/>{arrows}</svg>""")
        [box] = [core(e) for e in document["pages"][0]["elements"]]
        self.assertEqual(len(box["connection_points"]), self.mod.MAX_CONNECTION_POINTS)
        connections = document["pages"][0]["content"]["content"]["connections"]
        self.assertTrue(all("end_attachment" in c["content"] for c in connections))

    def test_text_on_no_box_stays_in_place_and_paper_becomes_the_background(self) -> None:
        """Free text keeps its place, the paper colours the page, and the title names it."""
        note = self.element_labelled("A free note")
        self.assertEqual(note["kind"], "text")
        self.assertLessEqual(note["frame"]["x"], 40)
        background = self.flowchart["pages"][0]["content"]["background"]
        self.assertEqual(background, {"kind": "solid", "color_hex": "#F5F5F5"})
        self.assertEqual(self.flowchart["name"], "Order flow")

    def test_labels_inside_moved_groups_keep_their_place(self) -> None:
        """Labels in a transformed group are placed in page coordinates, not the group's."""
        document, _ = self.export("""<svg viewBox="50 20 400 200"><g transform="translate(100,50)">
          <rect width="120" height="40" fill="#fff" stroke="#000"/>
          <text x="60" y="24" font-size="12" text-anchor="middle">Centred</text>
          <rect y="60" width="120" height="60" fill="#fff" stroke="#000"/>
          <text x="8" y="76" font-size="12">Top left</text></g></svg>""")
        centred = self.element_labelled("Centred", document)
        corner = self.element_labelled("Top left", document)
        self.assertEqual(centred["frame"]["x"], 50)  # 100 across, less the viewBox origin
        page = {core(e)["id"]: e for e in document["pages"][0]["elements"]}
        self.assertNotIn("text_layout", page[centred["id"]]["content"])
        region = page[corner["id"]]["content"]["text_layout"]["frame"]
        self.assertGreater(region["width"], 0.8)  # room to the box's far edge
        self.assertLess(region["y"], 0.2)

    def test_stylesheet_classes_and_custom_properties_are_resolved(self) -> None:
        """Classes, custom properties and the font shorthand style shapes; dark mode is ignored."""
        document, _ = self.export("""<style>:root { --ink: #2d3142; --accent: #bf4520; }
          .node { fill: var(--accent); stroke: var(--ink); stroke-width: 2; }
          .title { font: 600 13px 'Geist', sans-serif; fill: var(--ink); text-transform: uppercase; }
          @media (prefers-color-scheme: dark) { .node { fill: #000000; } }</style>
          <svg viewBox="0 0 200 100"><rect class="node" x="10" y="10" width="100" height="50"/>
          <text class="title" x="60" y="40" text-anchor="middle">api</text></svg>""")
        node = self.element_labelled("API", document)
        self.assertEqual(
            node["style"], {"fill_hex": "#BF4520", "stroke_hex": "#2D3142", "line_width": 2}
        )
        self.assertEqual(node["text_content"]["base_style"]["font_size"], 13)

    def test_scaled_text_measures_in_local_coordinates_only_once(self) -> None:
        """Scaling a text-only group scales its frame and output font exactly once."""
        frames: list[Record] = []
        for scale in (1, 2):
            document, _ = self.export(f"""<svg viewBox="0 0 300 300">
              <g transform="scale({scale})"><text x="10" y="20" font-size="10">ABC</text>
              </g></svg>""")
            [label] = [core(e) for e in document["pages"][0]["elements"]]
            self.assertEqual(label["text_content"]["base_style"]["font_size"], 10 * scale)
            frames.append(label["frame"])
        self.assertEqual(frames[1], {key: value * 2 for key, value in frames[0].items()})

    def test_cards_group_with_what_is_drawn_on_them_but_zones_do_not(self) -> None:
        """A card groups with its tag and numeral; a zone holding the card stays free."""
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <rect x="10" y="10" width="380" height="280" fill="none" stroke="#999"/>
          <text x="20" y="26" font-size="9">ZONE</text>
          <rect x="40" y="60" width="160" height="60" fill="#fff" stroke="#333"/>
          <rect x="48" y="66" width="30" height="12" fill="#eee"/>
          <text x="63" y="75" font-size="8" text-anchor="middle">TAG</text>
          <text x="120" y="100" font-size="12" text-anchor="middle">Service</text>
          <text x="196" y="116" font-size="20" text-anchor="end">01</text></svg>""")
        self.assertEqual(self.element_labelled("ZONE", document)["kind"], "text")
        [group] = document["pages"][0]["content"]["groups"]
        self.assertEqual(
            {m["id"] for m in group["members"]},
            {self.element_labelled(s, document)["id"] for s in ("Service", "TAG", "01")},
        )

    def test_tspan_lines_and_em_offsets_become_one_label(self) -> None:
        """A ``<tspan>`` placed a line below, in ems, continues the same label."""
        document, _ = self.export("""<svg viewBox="0 0 200 100"><rect x="10" y="10" width="180"
          height="80" fill="#fff" stroke="#000"/><text x="100" y="40" font-size="10"
          text-anchor="middle">First<tspan x="100" dy="1.4em">second</tspan></text></svg>""")
        self.element_labelled("First\nsecond", document)

    def test_text_runs_count_utf16_units(self) -> None:
        """Run ranges count UTF-16 code units, as the format does, so an emoji counts as two."""
        document, _ = self.export("""<svg viewBox="0 0 200 100"><rect x="10" y="10" width="180"
          height="80" fill="#fff" stroke="#000"/><text x="100" y="40" font-size="12"
          text-anchor="middle">Deploy 🚀</text>
          <text x="100" y="56" font-size="9" fill="#777" text-anchor="middle">déjà vu</text></svg>""")
        text = self.element_labelled("Deploy 🚀\ndéjà vu", document)["text_content"]
        self.assertEqual(text["character_runs"][0]["range"], {"location": 10, "length": 7})

    def test_path_data_covers_relative_shorthand_and_arc_commands(self) -> None:
        """Relative, shorthand, smooth and arc commands, including packed arc flags."""
        cubic, quad = self.mod.Cubic, self.mod.Quad
        [square] = self.mod.parse_path_data("m10 10 h20 v20 h-20 z")
        self.assertTrue(square.closed)
        self.assertEqual([s.end for s in square.segments], [(30, 10), (30, 30), (10, 30)])
        [curve] = self.mod.parse_path_data(
            "M0 0 C 10 0 20 10 20 20 S 30 40 40 40 Q 50 40 50 50 T 60 60"
        )
        self.assertEqual([type(s) for s in curve.segments], [cubic, cubic, quad, quad])
        self.assertEqual(curve.segments[1].control1, (20, 30))  # S mirrors the last control
        self.assertEqual(curve.segments[3].control, (50, 60))  # and so does T
        [arc] = self.mod.parse_path_data("M0 0 A 10 10 0 0 1 20 0")
        self.assertEqual(arc.segments[-1].end, (20, 0))
        [packed] = self.mod.parse_path_data("M5 5a9.4 9.4 0 01-1.9-.4l2 2")
        self.assertEqual(packed.segments[-1].end, (5.1, 6.6))
        # S mirrors only a cubic's control point; after an arc it starts at the current point.
        [after_arc] = self.mod.parse_path_data("M0 0 A 10 10 0 0 1 20 0 S 30 10 40 0")
        self.assertEqual(after_arc.segments[-1].control1, (20, 0))

    def test_malformed_path_data_fails_instead_of_hanging(self) -> None:
        """Broken path data raises at once, rather than looping or drawing nonsense."""
        for data in ("M0 0 L10", "M0 0 L10 0 L10 10 Z 5", "L 5 5", "M0 0 L1e999 0"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.mod.parse_path_data(data)

    def test_holes_keep_their_outline_and_are_reported(self) -> None:
        """A hole keeps only its outline, with a note; an island inside it is filled again."""
        document, skipped = self.export("""<svg viewBox="0 0 200 200">
          <path d="M10 10H110V110H10ZM40 40H80V80H40Z" fill="#000" stroke="#333"/></svg>""")
        fills = sorted(core(e)["style"]["fill_hex"] for e in document["pages"][0]["elements"])
        self.assertEqual(fills, ["#000000", "#00000000"])
        self.assertEqual(skipped, {"hole in a filled shape, kept as an outline only": 1})
        document, _ = self.export("""<svg viewBox="0 0 200 200">
          <path d="M10 10H110V110H10ZM40 40H80V80H40ZM55 55H65V65H55Z" fill="#000"/></svg>""")
        fills = sorted(core(e)["style"]["fill_hex"] for e in document["pages"][0]["elements"])
        self.assertEqual(fills, ["#000000", "#000000"])

    def test_icons_are_stored_as_artwork_and_images_are_left_out(self) -> None:
        """Icons are stored once each; unsafe icons and every image are left out with a note."""
        result = self.mod.export_document(
            """<svg viewBox="0 0 400 200"><defs>
              <symbol id="db" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <ellipse cx="12" cy="6" rx="8" ry="3"/></symbol>
              <g id="key" fill="none" stroke="currentColor"><circle cx="0" cy="0" r="4"/></g>
              <g id="bad" onclick="steal()"><circle r="2"/></g></defs>
              <use href="#db" x="10" y="10" width="48" height="48" color="#bf4520"/>
              <use href="#db" x="70" y="10" width="24" height="24" color="#bf4520"/>
              <use href="#key" transform="translate(150 40)" style="color:#2e5aa8"/>
              <use href="#bad" transform="translate(200 40)"/>
              <image href="data:image/png;base64,AAAA" x="250" y="10" width="40" height="20"/>
            </svg>""",
            Path("pictures.html"),
        )
        self.assertEqual(format_problems(result.manifest, result.document), [])
        kinds = [core(e)["kind"] for e in result.document["pages"][0]["elements"]]
        self.assertEqual(kinds, ["svg_artwork"] * 3)
        self.assertEqual(len(result.assets), 2)  # the database icon, placed twice, is stored once
        svgs = [a.data.decode() for a in result.assets]
        self.assertTrue(
            any('color="#BF4520"' in svg and 'viewBox="0 0 24 24"' in svg for svg in svgs)
        )
        self.assertEqual(
            result.skipped,
            {"icon SimpleDiagrams cannot store safely left out": 1, "<image> left out": 1},
        )

    def test_icon_svg_is_stored_only_when_plainly_safe(self) -> None:
        """Doubtful SVG is refused, so a package never holds artwork the app would reject."""
        deep = "<svg>" + "<g>" * 128 + "</g>" * 128 + "</svg>"
        crowded = "<svg><g " + " ".join(f'a{i}="x"' for i in range(129)) + "/></svg>"
        cases = (
            ('<svg><circle r="4"/></svg>', True),
            ('<svg><rect fill="url( \'#b\' )" clip-path="url(#elsewhere)"/></svg>', True),
            ('<svg><g ONCLICK="x()"/></svg>', False),
            ('<svg><g base="x"/></svg>', False),
            ('<svg><linearGradient href="#a"/></svg>', False),
            ('<svg xmlns:x="http://www.w3.org/1999/xlink"><g x:href="#a"/></svg>', False),
            ('<svg xmlns:i="urn:inkscape"><g i:label="x"/></svg>', False),
            ('<svg xmlns:i="urn:inkscape"><i:g/></svg>', False),
            ("<svg><SCRIPT/></svg>", False),
            ("<svg><Use/></svg>", False),
            ("<svg><image/></svg>", False),
            ("<svg><foreignObject/></svg>", False),
            ("<svg><style>rect { fill: red }</style></svg>", False),
            ("<svg><filter/></svg>", False),
            ('<svg><feGaussianBlur stdDeviation="1"/></svg>', False),
            ('<svg><rect fill="url(http://a/b)"/></svg>', False),
            ('<svg><rect style="content: \\66"/></svg>', False),
            ('<svg><rect fill="url(#a"/></svg>', False),  # url( never closed
            ('<svg><rect fill="url(#caf\u00e9)"/></svg>', False),
            (deep, False),
            (crowded, False),
        )
        for content, safe in cases:
            with self.subTest(content=content[:80]):
                self.assertEqual(self.mod.is_safe_svg(ET.fromstring(content)), safe)

    def test_an_unclosed_url_is_refused_without_slow_backtracking(self) -> None:
        """A long run of spaces after url( is read once, not retried at every split."""
        root = ET.fromstring(f'<svg><rect fill="url({" " * 4096}"/></svg>')
        self.assertFalse(self.mod.is_safe_svg(root))
        root = ET.fromstring(f'<svg><rect fill="url({" " * 4096}#a)"/></svg>')
        self.assertTrue(self.mod.is_safe_svg(root))

    def test_icon_size_and_extent_stay_within_what_the_editor_accepts(self) -> None:
        """An oversized icon or an unusable view box is refused rather than stored."""
        part = ET.fromstring('<circle r="4"/>')
        self.assertIsNotNone(self.mod.svg_asset((0, 0, 10, 10), [part], {}))
        self.assertIsNone(self.mod.svg_asset((0, 0, 0, 10), [part], {}))
        self.assertIsNone(self.mod.svg_asset((0, 0, 20_000_000, 10), [part], {}))
        with mock.patch.object(self.mod, "MAX_ICON_BYTES", 16):
            self.assertIsNone(self.mod.svg_asset((0, 0, 10, 10), [part], {}))

    def test_clipping_and_masks_are_noted_and_their_shapes_stay_drawn(self) -> None:
        """A clipped shape stays whole, so the note is what tells the user it differs."""
        document, skipped = self.export("""<style>.crop { mask: url(#m) }</style>
          <svg viewBox="0 0 100 100"><defs><clipPath id="c"><rect width="9" height="9"/></clipPath>
          <mask id="m"/></defs><g clip-path="url(#c)"><circle cx="50" cy="50" r="40"/></g>
          <circle class="crop" r="4"/><circle style="clip-path: none" r="5"/></svg>""")
        self.assertEqual(len(document["pages"][0]["elements"]), 3)
        self.assertEqual(skipped, {"clipping and masks left out; shapes are drawn unclipped": 2})

    def test_an_open_filled_path_keeps_its_fill_below_its_line(self) -> None:
        """SVG fills an open path as if closed, so the fill must not vanish when it is exported."""
        document, _ = self.export(
            '<svg viewBox="0 0 100 100"><path d="M10 10 H90 V90 H10" fill="#bf4520"/></svg>'
        )
        [fill] = [core(e) for e in document["pages"][0]["elements"]]
        self.assertEqual(fill["style"]["fill_hex"], "#BF4520")
        self.assertEqual(fill["style"]["line_width"], 0)
        self.assertTrue(fill["path"]["is_closed"])
        document, _ = self.export(
            """<svg viewBox="0 0 100 100">
            <path d="M10 10 H90 V90 H10" fill="#bf4520" stroke="#000"/></svg>"""
        )
        [fill, line] = [core(e) for e in document["pages"][0]["elements"]]
        self.assertEqual(fill["style"]["fill_hex"], "#BF4520")
        self.assertFalse(line["path"]["is_closed"])
        self.assertEqual(line["style"]["fill_hex"], "#00000000")  # painted once, by the box below

    def test_a_line_end_never_attaches_to_its_own_fill(self) -> None:
        """An arrow with a fill stays free, and a plain line gains no fill box."""
        document, _ = self.export("""<svg viewBox="0 0 100 100"><defs>
          <marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <path d="M10 10 H90 V90" fill="#bf4520" stroke="#000" marker-end="url(#a)"/></svg>""")
        [arrow] = document["pages"][0]["content"]["content"]["connections"]
        self.assertIsNone(arrow["content"].get("start_attachment"))
        self.assertIsNone(arrow["content"].get("end_attachment"))
        document, _ = self.export(
            '<svg viewBox="0 0 99 99"><line x1="9" y1="9" x2="90" y2="90" stroke="#000"/></svg>'
        )
        self.assertEqual(len(document["pages"][0]["elements"]), 1)

    def test_shapes_sharing_bounds_merge_only_when_they_are_the_same_outline(self) -> None:
        """A star's two triangles and an X's two legs stay apart; one shape painted twice merges."""
        for first, second, count in (
            ("50,0 100,100 0,100", "50,100 0,0 100,0", 2),  # a six-pointed star
            ("20,44 0,34 70,0 90,10", "70,44 90,34 20,0 0,10", 2),  # the two legs of an X
            ("50,0 100,100 0,100", "50,0 100,100 0,100", 1),
        ):
            with self.subTest(first=first, second=second):
                document, _ = self.export(f"""<svg viewBox="0 0 100 100">
                  <polygon points="{first}" fill="#fff"/><polygon points="{second}" fill="#000"/>
                  </svg>""")
                self.assertEqual(len(document["pages"][0]["elements"]), count)

    def test_an_icon_keeps_the_paint_its_stylesheet_and_placement_gave_it(self) -> None:
        """Icons are stored without the page's CSS, so their paint must be written onto them."""
        result = self.mod.export_document(
            """<style>:root { --ink: #123456 } .brand { fill: #bf4520 }
              .inked { stroke: var(--ink) }
              .lost { fill: var(--nothing) }</style>
              <svg viewBox="0 0 200 100"><defs>
              <symbol id="a" viewBox="0 0 24 24"><path class="brand" d="M0 0H9V9Z"/></symbol>
              <symbol id="b" viewBox="0 0 24 24"><path class="inked" d="M1 1H9V9Z"/></symbol>
              <symbol id="c" viewBox="0 0 24 24"><path d="M2 2H9V9Z"/></symbol>
              <symbol id="d" viewBox="0 0 24 24"><path class="lost" d="M3 3H9V9Z"/></symbol>
              </defs><use href="#a" width="24" height="24"/>
              <use href="#b" x="30" width="24" height="24"/>
              <use href="#c" x="60" width="24" height="24" fill="#2e5aa8"/>
              <use href="#d" x="90" width="24" height="24"/></svg>""",
            Path("painted-icons.html"),
        )
        svgs = "".join(asset.data.decode() for asset in result.assets)
        self.assertEqual(len(result.assets), 3)
        for written in ('fill="#bf4520"', 'stroke="#123456"', 'fill="#2e5aa8"'):
            self.assertIn(written, svgs)
        self.assertNotIn("class=", svgs)
        self.assertNotIn("var(", svgs)
        self.assertEqual(result.skipped, {"icon SimpleDiagrams cannot store safely left out": 1})

    def test_a_nested_svg_is_an_icon_where_the_browser_draws_it(self) -> None:
        """Ignoring a nested view port piles every icon into the page's top-left corner."""
        result = self.mod.export_document(
            """<svg viewBox="0 0 400 300">
              <svg x="90" y="50" width="80" height="80" viewBox="0 0 10 10" fill="none"
                stroke="#123456" stroke-linecap="round"><rect x="1" y="1" width="8" height="8"/></svg>
              <svg x="200" y="50"><rect x="5" y="6" width="30" height="40" fill="#2e5aa8"/></svg>
              </svg>""",
            Path("nested.html"),
        )
        frames = [core(e)["frame"] for e in result.document["pages"][0]["elements"]]
        self.assertIn({"x": 90, "y": 50, "width": 80, "height": 80}, frames)  # an icon
        self.assertIn({"x": 205, "y": 56, "width": 30, "height": 40}, frames)  # only moved
        self.assertEqual(len(result.assets), 1)
        icon = result.assets[0].data.decode()
        for written in ('fill="none"', 'stroke="#123456"', 'stroke-linecap="round"'):
            self.assertIn(written, icon)

    def test_an_icon_leaves_out_what_the_page_hides(self) -> None:
        """A stored icon has no stylesheet, and the app's renderer ignores hiding attributes."""
        drawn = '<rect width="9" height="9" fill="#111111"/>'
        part = '<rect class="x" width="3" height="3" fill="#222222"/>'
        for placed in (
            NESTED_ICON,
            '<defs><symbol id="s" viewBox="0 0 10 10">{}</symbol></defs>'
            '<use href="#s" x="10" y="10" width="80" height="80"/>',
        ):
            for css, hidden in (
                (".x { display: none }", part),
                (".x { visibility: hidden }", part),
                (".x { visibility: hidden }", part.replace("/>", "><title>Tip</title></rect>")),
                (".x { display: none }", f'<g class="x">{part}</g>'),
            ):
                with self.subTest(placed=placed, css=css, hidden=hidden):
                    icon = self.icon(css, placed.format(drawn + hidden))
                    self.assertIn("#111111", icon)
                    self.assertNotIn("#222222", icon)
            for empty in (part, f"<g>{part}</g>", f"<title>Tick</title>{part}"):
                with self.subTest(placed=placed, empty=empty):
                    result = self.mod.export_document(
                        f"""<style>.x {{ display: none }}</style><svg viewBox="0 0 400 300">
                        {placed.format(empty)}</svg>""",
                        Path("case.html"),
                    )
                    self.assertEqual((result.assets, result.skipped), ([], {}))

    def test_a_stored_icon_draws_what_the_page_draws(self) -> None:
        """Each row is a way the copy could differ from the page once its stylesheet is gone."""
        line = '<path class="a" d="M1 1H9"/>'
        rect = '<rect class="a" {} width="3" height="3"/>'
        for css, part, kept, lost in (
            (".a { transform: translate(5px, 6px) }", rect.format(""), 'transform="translate(5, 6)"', "px"),
            (".a { transform: none }", rect.format('transform="translate(5,5)"'), "<rect", "transform="),
            (".a { transform: none }", rect.format(""), "<rect", "transform="),
            (".a { transform-origin: center }", rect.format(""), "<rect", "transform-origin"),
            (".a { stroke-linecap: round; stroke-linejoin: bevel; stroke-dashoffset: 2;"
             " stroke-miterlimit: 7; fill-rule: evenodd }", line,
             'fill-rule="evenodd" stroke-dashoffset="2" stroke-linecap="round" '
             'stroke-linejoin="bevel" stroke-miterlimit="7"', " style="),
            ("g { stroke-linecap: square }", '<g><path d="M1 1H9"/></g>', 'stroke-linecap="square"', "class="),
            (".a { font: italic 600 2px serif }", '<text><tspan class="a">Hi</tspan></text>',
             'font-family="serif" font-size="2" font-style="italic" font-weight="600"', " style="),
            (".a { fill: #ff0000 !important }", '<path class="a" d="M0 0H9" style="fill:#0000ff"/>',
             'fill="#ff0000"', " style="),
            (":root { --c: #123456 }", '<path d="M1 1H9" style="stroke:var(--c);stroke-linecap:round"/>',
             'stroke="#123456" stroke-linecap="round"', " style="),
            (":root { --o: stroke }", '<path d="M1 1H9" style="paint-order: var(--o)"/>',
             'style="paint-order: stroke"', "var("),
            ("", '<text style="font: italic 14pt Georgia">Hi</text>', 'style="font: italic 14pt Georgia"', "font-style="),
            ("", '<path d="M1 1H9" style="clip-path:url(#c);marker-end:url(#m)"/>',
             'clip-path="url(#c)" marker-end="url(#m)"', " style="),
            (".s { stop-color: #ff0000 }", '<linearGradient id="g"><stop class="s"/></linearGradient>'
             '<rect width="9" height="9" fill="url(#g)"/>', 'stop-color="#ff0000"', "class="),
            (".a { stroke-linejoin: var(--gone); font-family: var(--gone) }",
             line + '<text class="a">Hi</text>', "<path", '=""'),
            (".h { visibility: hidden } .a { visibility: visible }",
             '<g class="h">' + rect.format("") + "</g>", "<rect", "visibility="),
            ("", '<rect display="none" style="display: inline" width="3"/>', "<rect", "display="),
            ("", '<defs visibility="hidden"><linearGradient id="g"><stop stop-color="#ff0000"/>'
             '</linearGradient></defs><rect width="9" height="9" fill="url(#g)"/>', 'stop-color="#ff0000"', "visibility="),
            (".x { display: none }", '<text>Hi <tspan class="x">gone</tspan> there</text>', "there", "gone"),
            (".a { visibility: visible }", '<text visibility="hidden">gone<tspan class="a">Hi</tspan> gone</text>',
             "Hi", "gone"),
            (".a { font-size: 2em }", '<text class="a">Hi</text>', 'font-size="32"', "em"),
            ("", '<g style="font-size: 2em"><text>Hi</text></g>', 'font-size="32"', "!"),
            ("g { font-size: 10px } .a { font-size: 150% }", '<g><text class="a">Hi</text></g>',
             'font-size="15"', "%"),
        ):  # fmt: skip
            with self.subTest(css=css, part=part):
                icon = self.icon(css, NESTED_ICON.format(part))
                self.assertIn(kept, icon)
                self.assertNotIn(lost, icon)

    def test_an_icon_the_stored_file_cannot_draw_faithfully_is_left_out_with_a_note(self) -> None:
        """A wrong picture with no note is worse than a note: the user can fix what they see."""
        rect = '<rect class="a" width="9" height="9"/>'
        for css, part in (
            (".a { transform: translateX(5px) }", rect),
            (".a { transform: translate(50%, 0) }", rect),
            (".a { transform: rotate(90deg); transform-origin: 5px 5px }", rect),
            (".a { transform: translate(123456789012345678901234567890px) foo(1) }", rect),  # no hang
            ("", '<image href="a.png" width="9" height="9"/>'),
        ):
            with self.subTest(css=css, part=part):
                result = self.mod.export_document(
                    f"""<style>{css}</style><svg viewBox="0 0 400 300">
                    {NESTED_ICON.format(part)}</svg>""",
                    Path("case.html"),
                )
                self.assertEqual(result.assets, [])
                self.assertEqual(result.skipped, {"icon SimpleDiagrams cannot store safely left out": 1})

    def test_a_font_shorthand_reads_the_final_custom_properties(self) -> None:
        """Custom properties apply wherever they are set; a missing one must not size the label."""
        for css, attributes, size in (
            (".a { --s: 20px !important; font: 600 var(--s) serif }", "", 20),
            (".a { font: 600 var(--s) serif }", 'style="--s: 20px"', 20),
            (".a { font: 600 var(--gone) serif }", "", 16),
        ):
            with self.subTest(css=css, attributes=attributes):
                document, _ = self.export(
                    f"""<svg viewBox="0 0 400 300"><style>{css}</style>
                    <text class="a" x="9" y="50" {attributes}>Hi</text></svg>"""
                )
                self.assertIn(f'"font_size": {size},', json.dumps(document))

    def test_ordinary_diagram_constructs_keep_their_meaning(self) -> None:
        """Each row once lost or misdrew something a browser shows, with no note."""
        label = '<text x="200" y="150" text-anchor="middle">A</text>'
        for css, svg, kept, lost in (
            ("", f'<rect x="50" y="50" width="300" height="200" fill="none" stroke="#333"'
             f' stroke-dasharray="6 4"/>{label}', '"stroke_pattern_override": "dashed"', "!"),
            ("", '<rect width="400" height="300" fill="none" stroke="#123456"/>', '"#123456"', "!"),
            ("", '<rect width="400" height="300" fill="#000" fill-opacity=".03"/>', "pages", '"#000000"'),
            ("", '<circle cx="50%" cy="50%" r="10" fill="#000"/>', '"x": 190', "!"),
            (".t { font: 600 .75rem serif }", '<text class="t" y="9">A</text>', '"font_size": 12,', "!"),
            (".t { font: 12px serif }", '<g font-weight="700"><text class="t" y="9">A</text></g>', '"regular"', '"bold"'),
            (":root { --inkColor: #ff0000 } text { fill: var(--inkColor) }", '<text y="9">A</text>', '"#FF0000"', "!"),
            ("", '<text y="9" fill="#000" fill-opacity="50%">A</text>', '"#00000080"', "!"),
            ("", '<text y="9">Shown <tspan display="none">Hidden</tspan></text>', "Shown", "Hidden"),
            ("", '<text y="9"><a href="#x">Docs</a> page</text>', "Docs page", "!"),
            ("", '<text y="9">Label<tspan dx="8">note</tspan></text>', "Label note", "!"),
            ("", '<text y="9">Label<tspan dx="0">note</tspan></text>', "Labelnote", "!"),
            ("", '<text y="9">First<tspan dy="20">Second</tspan></text>', "Second", "FirstSecond"),
            ("", '<foreignObject width="90" height="40"><div><div>One</div><div>Two</div></div>'
             "</foreignObject>", "One Two", "!"),
            ("", '<path d="M10 10 Q 60 40 110 10 Z" fill="#abc" stroke="#000"/>', '"is_closed": true', "!"),
        ):  # fmt: skip
            with self.subTest(css=css, svg=svg):
                document, _ = self.export(
                    f'<svg viewBox="0 0 400 300"><style>{css}</style>{svg}</svg>'
                )
                written = json.dumps(document)
                self.assertIn(kept, written)
                self.assertNotIn(lost, written)
        # A filled box near an arrow stays a box; a corner label stays in place on an outline.
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <defs><marker id="a"><polygon points="0 0,8 3,0 6"/></marker></defs>
          <line x1="10" y1="120" x2="292" y2="120" stroke="#000" marker-end="url(#a)"/>
          <rect x="300" y="105" width="90" height="32" rx="16" fill="#2e5aa8"/>
          <text x="345" y="125" font-size="14" text-anchor="middle">API</text></svg>""")
        self.assertIn('"#2E5AA8"', json.dumps(document))
        self.assertNotIn("label", document["pages"][0]["content"]["content"]["connections"][0]["content"])
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <path d="M100 100 H300 L320 120 V200 H100 Z" fill="#fff" stroke="#000"/>
          <text x="110" y="115">Corner</text></svg>""")
        self.assertEqual(len(document["pages"][0]["elements"]), 2)
        lines = "".join(
            f'<text x="150" y="{y}" font-size="14" text-anchor="middle">L{y}</text>'
            for y in (88, 105, 122)
        )
        document, _ = self.export(f"""<svg viewBox="0 0 400 300">
          <polygon points="100,50 200,50 230,100 200,150 100,150 70,100" fill="#fff" stroke="#000"/>
          {lines}</svg>""")
        self.assertEqual(len(document["pages"][0]["elements"]), 1)  # a centred stack stays whole

    def test_what_shows_itself_inside_hidden_content_is_kept(self) -> None:
        """``visibility`` hides only an element's own drawing; a child may show itself again."""
        visible = 'visibility="visible"'
        symbol = f'<defs><symbol id="s" viewBox="0 0 10 10"><rect {visible} width="9" height="9"/>'
        for svg, kept, lost, notes in (
            (f'<g visibility="hidden"><rect {visible} width="20" height="20" fill="#123456"/></g>',
             '"#123456"', "!", {}),
            ('<g visibility="hidden"><rect width="20" height="20" fill="#123456"/></g>', "pages", "#123456", {}),
            ('<rect visibility="hidden" width="20" height="20" fill="#123456"><title>T</title></rect>',
             "pages", "#123456", {}),
            (f'<text visibility="hidden" y="9">gone<tspan {visible} x="40">Shown</tspan> gone</text>',
             '"Shown"', "gone", {}),
            (f'<text visibility="hidden" y="9" fill="#ff0000"><tspan {visible} fill="#123">Hi</tspan></text>',
             '"#112233"', "#FF0000", {}),
            (f'<text visibility="hidden" y="9">gone <tspan {visible}>Shown</tspan></text>', '"Shown"', "gone",
             {"words after hidden words in a line moved into their place": 1}),
            ('<text y="9">One <tspan visibility="hidden">two</tspan> three</text>', '"One three"', "two",
             {"words after hidden words in a line moved into their place": 1}),
            (f'{symbol}</symbol></defs><use href="#s" visibility="hidden" width="20" height="20"/>',
             '"svg_artwork"', "!", {}),
            (f'<foreignObject visibility="hidden" width="9" height="9"><p {visible}>Shown</p></foreignObject>',
             "pages", "Shown", {"visible content inside a hidden <foreignObject> left out": 1}),
        ):  # fmt: skip
            with self.subTest(svg=svg):
                document, skipped = self.export(f'<svg viewBox="0 0 400 300">{svg}</svg>')
                written = json.dumps(document)
                self.assertIn(kept, written)
                self.assertNotIn(lost, written)
                self.assertEqual(skipped, notes)

    def test_words_hidden_deep_inside_text_stay_hidden(self) -> None:
        """Hiding reaches every level of nested spans and HTML, so no hidden draft word leaks."""
        moved = {"words after hidden words in a line moved into their place": 1}
        for css, svg, label, notes in (
            ("", '<text y="9">Public<tspan> label<tspan display="none"> draft</tspan></tspan></text>',
             "Public label", {}),
            (".d { display: none }", '<text y="9"><tspan>Public <tspan class="d">draft</tspan></tspan></text>',
             "Public", {}),
            ("", '<text y="9"><tspan>Public <tspan visibility="hidden">draft</tspan> label</tspan></text>',
             "Public label", moved),
            ("", '<text y="9">A <tspan visibility="hidden">x<tspan visibility="visible">B</tspan></tspan></text>',
             "A B", moved),
            ("", '<text y="9">A <tspan>B <tspan font-weight="700">C</tspan></tspan></text>', "A B C",
             {"styled words inside a line take the line's style": 1}),
            (".d { display: none } .h { visibility: hidden }",
             ('<foreignObject width="90" height="40"><div>Shown <span class="d">one</span>'
              '<span hidden>two</span><span class="h">three</span></div></foreignObject>'),
             "Shown", {"rich HTML text kept as plain text": 1}),
            (".h { visibility: hidden }",
             ('<foreignObject width="90" height="40"><div class="h">gone '
              '<b style="visibility: visible">Shown</b></div></foreignObject>'), "Shown", {}),
        ):  # fmt: skip
            with self.subTest(css=css, svg=svg):
                document, skipped = self.export(
                    f'<svg viewBox="0 0 400 300"><style>{css}</style>{svg}</svg>'
                )
                [element] = document["pages"][0]["elements"]
                self.assertEqual(core(element)["text_content"]["string"], label)
                self.assertEqual(skipped, notes)

    def test_only_layers_under_everything_become_the_paper(self) -> None:
        """A full-page layer drawn over the diagram covers it in the browser, so it stays drawn."""
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <defs><pattern id="dots" width="9" height="9"><circle r="1"/></pattern></defs>
          <rect width="100%" height="100%" fill="#f5f5f5"/>
          <rect width="100%" height="100%" fill="url(#dots)"/>
          <rect x="10" y="10" width="50" height="50" fill="#123456"/>
          <rect width="400" height="300" fill="#ffffff" fill-opacity="0.5"/></svg>""")
        page = document["pages"][0]
        self.assertEqual(page["content"]["background"], {"kind": "solid", "color_hex": "#F5F5F5"})
        fills = [core(e)["style"]["fill_hex"] for e in page["elements"]]
        self.assertEqual(fills, ["#123456", "#FFFFFF80"])  # the cover stays above what it covers

    def test_a_symbols_opacity_layers_on_its_placement(self) -> None:
        """Opacity multiplies down the tree; one value replacing the other darkens the icon."""
        path = '<path d="M0 0H10V10Z"/>'
        for css, symbol in (
            ("", f'<symbol id="s" viewBox="0 0 10 10" opacity="0.5">{path}</symbol>'),
            (".half { opacity: .5 }", f'<symbol id="s" class="half" viewBox="0 0 10 10">{path}</symbol>'),
            ("", f'<symbol id="s" opacity="50%">{path}</symbol>'),  # no view box: drawn as placed
        ):  # fmt: skip
            with self.subTest(css=css, symbol=symbol):
                placed = '<use href="#s" width="20" height="20" opacity="0.5"/>'
                icon = self.icon(css, f"<defs>{symbol}</defs>{placed}")
                self.assertEqual(icon.count("opacity="), 1)
                self.assertIn('opacity="0.25"', icon)

    def test_an_icon_keeps_its_proportions_in_its_box(self) -> None:
        """A view box fits its box as ``preserveAspectRatio`` says; the format would stretch it."""
        circle = '<circle cx="12" cy="12" r="10"/>'
        cropped = {"icon cropped to its box drawn whole": 1}
        for setting, frame, notes in (
            (None, {"x": 12, "y": 0, "width": 24, "height": 24}, {}),
            ("xMinYMax meet", {"x": 0, "y": 0, "width": 24, "height": 24}, {}),
            ("none", {"x": 0, "y": 0, "width": 48, "height": 24}, {}),
            ("xMidYMid slice", {"x": 0, "y": -12, "width": 48, "height": 48}, cropped),
        ):
            aspect = f' preserveAspectRatio="{setting}"' if setting else ""
            symbol = f'<defs><symbol id="s" viewBox="0 0 24 24"{aspect}>{circle}</symbol></defs>'
            for placed in (
                f'{symbol}<use href="#s" width="48" height="24"/>',
                f'<svg width="48" height="24" viewBox="0 0 24 24"{aspect}>{circle}</svg>',
            ):
                with self.subTest(placed=placed):
                    document, skipped = self.export(f'<svg viewBox="0 0 400 300">{placed}</svg>')
                    [artwork] = document["pages"][0]["elements"]
                    self.assertEqual(core(artwork)["frame"], frame)
                    self.assertEqual(skipped, notes)

    def test_an_icon_of_words_alone_is_kept(self) -> None:
        """Text counts toward an icon's bounds, so words placed by ``<use>`` are not lost."""
        result = self.mod.export_document(
            '<svg viewBox="0 0 400 300"><defs><g id="t"><text font-size="10">Hi</text></g></defs>'
            '<use href="#t" x="50" y="50"/></svg>',
            Path("case.html"),
        )
        [artwork] = result.document["pages"][0]["elements"]
        self.assertEqual((core(artwork)["kind"], result.skipped), ("svg_artwork", {}))
        self.assertIn(">Hi</text>", result.assets[0].data.decode())

    def test_measuring_an_icon_never_takes_its_drawing_as_the_paper(self) -> None:
        """An icon as large as the page is drawn, and the page keeps its own background."""
        document, _ = self.export("""<svg viewBox="0 0 400 300"><defs><g id="i">
          <rect width="400" height="300" fill="#123456"/></g></defs><use href="#i"/></svg>""")
        page = document["pages"][0]
        self.assertEqual(page["content"]["background"], {"kind": "none"})
        self.assertEqual([core(e)["kind"] for e in page["elements"]], ["svg_artwork"])
        document, _ = self.export("""<svg viewBox="0 0 400 300"><defs><g id="e"/><g id="i">
          <use href="#e"/><rect width="400" height="300" fill="#123456"/></g></defs>
          <use href="#i"/></svg>""")  # measuring an icon inside it must not end the measuring
        self.assertEqual(document["pages"][0]["content"]["background"], {"kind": "none"})

    def test_font_sizes_relative_to_the_parent_follow_it(self) -> None:
        """``em`` and ``%`` scale the inherited size, as ``rem`` scales the page's."""
        document, _ = self.export("""<svg viewBox="0 0 400 300"><g font-size="10">
          <text y="20" font-size="2em">Em</text><text y="60" font-size="150%">Percent</text>
          <text y="100" font-size="2rem">Rem</text><g font-size="2em"><text y="140">Nested</text>
          </g></g></svg>""")
        for string, size in (("Em", 20), ("Percent", 15), ("Rem", 32), ("Nested", 20)):
            with self.subTest(string=string):
                label = self.element_labelled(string, document)
                self.assertEqual(label["text_content"]["base_style"]["font_size"], size)

    def test_a_line_ignoring_its_scale_keeps_its_width(self) -> None:
        """``non-scaling-stroke`` keeps the line as wide as written, however it is scaled."""
        for css, line, width in (
            ("", '<path d="M1 1H20" stroke="#000" vector-effect="non-scaling-stroke"/>', 1),
            ("path { vector-effect: non-scaling-stroke }", '<path d="M1 1H20" stroke="#000"/>', 1),
            ("", '<path d="M1 1H20" stroke="#000"/>', 4),
        ):
            with self.subTest(css=css, line=line):
                document, _ = self.export(f"""<svg viewBox="0 0 400 300"><style>{css}</style>
                  <g transform="scale(4)">{line}</g></svg>""")
                [element] = document["pages"][0]["elements"]
                self.assertEqual(core(element)["style"]["line_width"], width)

    def test_markers_sit_at_the_ends_of_the_whole_path(self) -> None:
        """A path with several subpaths gets its start and end markers once, not on every part."""
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <defs><marker id="a" orient="auto-start-reverse">
            <polygon points="0 0,8 3,0 6"/></marker></defs>
          <path d="M10 50 L100 50 M10 80 L100 80 M10 110 L100 110" stroke="#000"
                marker-start="url(#a)" marker-end="url(#a)"/></svg>""")
        page = document["pages"][0]
        lines = [c["content"] for c in page["content"]["content"]["connections"]]
        endings = [(line["start_ending"], line["end_ending"]) for line in lines]
        self.assertEqual(endings, [("filledArrow", "none"), ("none", "filledArrow")])
        self.assertEqual([core(e)["kind"] for e in page["elements"]], ["path"])  # the bare middle

    def test_an_arrowhead_the_page_turns_away_gets_a_note(self) -> None:
        """SimpleDiagrams' arrows always point away from the line, so any other is noted."""
        forward, back = 'points="0 0,8 3,0 6"', 'points="8 0,0 3,8 6"'
        across, down = 'x1="10" y1="9" x2="90" y2="9"', 'x1="50" y1="10" x2="50" y2="90"'
        turned = {"arrowhead not pointing away from its line drawn pointing away": 1}
        for orient, shape, end, line, notes in (
            ("auto", forward, "marker-end", across, {}),
            ("auto", forward, "marker-start", across, turned),
            ("auto", back, "marker-start", across, {}),
            ("auto", back, "marker-end", across, turned),
            ("auto-start-reverse", forward, "marker-start", across, {}),
            ("auto-start-reverse", forward, "marker-end", down, {}),
            ("0", forward, "marker-end", across, {}),  # already points the way the line runs
            ("0", forward, "marker-end", down, turned),
            ("90deg", forward, "marker-end", down, {}),
            ("0.5turn", back, "marker-end", across, {}),
        ):  # fmt: skip
            with self.subTest(orient=orient, shape=shape, end=end, line=line):
                _, skipped = self.export(f"""<svg viewBox="0 0 400 300">
                  <defs><marker id="a" orient="{orient}"><polygon {shape}/></marker></defs>
                  <line {line} stroke="#000" {end}="url(#a)"/></svg>""")
                self.assertEqual(skipped, notes)

    def test_styling_this_export_cannot_read_gets_a_note(self) -> None:
        """Each row draws differently in the browser; without a note the user cannot know."""
        geometry = {"sizes, places and corners set in CSS ignored; the SVG's own are used": 1}
        html_box = {"HTML box background, border or shadow left out; its text is kept": 1}
        colour = {"see-through or unknown icon colour stored as solid": 1}
        square = '<path d="M0 0H10V10Z" fill="currentColor"/>'
        icon = f'<defs><symbol id="s" viewBox="0 0 10 10">{square}</symbol></defs>'
        card = '<foreignObject width="100" height="50"><div style="{}">Card</div></foreignObject>'
        for css, svg, notes in (
            (".n { rx: 10px }", '<rect class="n" width="90" height="40" fill="#fff" stroke="#000"/>', geometry),
            ("", '<rect style="height: 20px" width="90" height="40" fill="#fff" stroke="#000"/>', geometry),
            (".i { width: 16px }", f'{icon}<use class="i" href="#s"/>', geometry),
            (".p { r: 2px }", '<svg width="20" height="20" viewBox="0 0 10 10"><circle class="p" r="3"/></svg>',
             geometry),
            ("svg { width: 100%; height: auto }", '<rect width="90" height="40" fill="#fff" stroke="#000"/>', {}),
            ("", card.format("background: #eef"), html_box),
            (".b { border: 1px solid #33f }", card.format("").replace("<div", '<div class="b"'), html_box),
            ("", card.format("border: none; background: transparent"), {}),
            ("", card.format("border-radius: 8px; border-collapse: collapse; outline-offset: 2px"), {}),
            ("", card.format("border: 1px solid transparent; outline: 0 none"), {}),
            ("", card.format("background: rgba(0, 0, 0, 0); border: 0"), {}),
            (".d { display: none }", card.format("").replace("Card", '<p class="d" style="background: red">x</p>'),
             {}),
            ("", f'{icon}<use href="#s" width="20" height="20" style="color: rgba(255,0,0,0.3)"/>', colour),
            ("", f'{icon}<use href="#s" width="20" height="20" color="hsl(0 50% 50%)"/>', colour),
            ("", f'{icon}<use href="#s" width="20" height="20" color="#ff0000"/>', {}),
            ("", icon.replace("currentColor", "#123456") + '<use href="#s" color="rgba(0,0,0,.87)"/>', {}),
            (".n { rx: 8px }", '<rect class="n" rx="8" width="90" height="40" fill="#fff" stroke="#000"/>', {}),
            ("", '<text y="20"><tspan>A<tspan x="10" dy="1em">B</tspan></tspan></text>',
             {"a line placed inside a span joins that span's line": 1}),
            ("", '<text x="10" y="20">E = mc<tspan dy="-5">2</tspan></text>',
             {"words moved up or down in a line start a new line": 1}),
            ("", '<text x="10" y="20">One<tspan x="10" dy="20">Two</tspan></text>', {}),
        ):  # fmt: skip
            with self.subTest(css=css, svg=svg):
                _, skipped = self.export(
                    f'<svg viewBox="0 0 400 300"><style>{css}</style>{svg}</svg>'
                )
                self.assertEqual(skipped, notes)

    def test_a_mirrored_icon_is_stored_flipped_not_turned(self) -> None:
        """The format mirrors artwork in its frame and then turns it; the corners must land where
        the browser draws them, or an asymmetric icon opens facing the wrong way."""
        icon = '<defs><symbol id="s" viewBox="0 0 40 30"><path d="M0 0H40L0 30Z"/></symbol></defs>'
        for transform, flips in (
            ("translate(100 0) scale(-1 1)", (True, False)),
            ("translate(0 100) scale(1 -1)", (False, True)),
            ("translate(200 150) rotate(30) scale(-1 1)", (True, False)),
            ("translate(200 150) rotate(90) scale(-1 1)", None),  # either mirror, a quarter turn
            ("translate(200 150) scale(-1 -1)", (False, False)),  # a half turn, not a mirror
        ):
            with self.subTest(transform=transform):
                document, skipped = self.export(f"""<svg viewBox="0 0 400 300">{icon}
                  <use href="#s" x="10" y="20" width="40" height="30" transform="{transform}"/></svg>""")
                self.assertEqual(skipped, {})
                [artwork] = document["pages"][0]["elements"]
                content = artwork["content"]
                if flips is not None:
                    self.assertEqual((content["flip_horizontal"], content["flip_vertical"]), flips)
                matrix = self.mod.parse_transform(transform)
                for u, v in ((0, 0), (1, 0), (0, 1)):
                    drawn = self.mod.apply(matrix, (10 + 40 * u, 20 + 30 * v))
                    self.assertLess(math.dist(resolve(artwork, {"x": u, "y": v}), drawn), 0.01)
        # Text, which the app never mirrors, stays upright where the mirror put it.
        document, _ = self.export("""<svg viewBox="0 0 400 300">
          <text transform="translate(300 0) scale(-1 1)" x="100" y="50">Mirrored</text></svg>""")
        self.assertEqual(self.element_labelled("Mirrored", document)["rotation_degrees"], 0)

    def test_a_marker_keeps_its_line_ending(self) -> None:
        """UML and ER meaning lives in the ending: hollow, filled and diamond differ."""
        triangle, diamond = 'points="0 0,8 3,0 6"', 'points="0 5,9 0,18 5,9 10"'
        for css, marker, ending in (
            ("", f'<polygon {triangle} fill="#fff" stroke="#000"/>', "solidArrow"),
            ("", f'<polygon {triangle}/>', "filledArrow"),
            ("", f'<polygon {triangle} fill="#ff0000" stroke="#000"/>', "filledArrow"),
            ("", f'<polygon {triangle} fill="#fff" stroke="#fff"/>', "filledArrow"),
            ("", f'<polygon {triangle} fill="#f5f5f5" stroke="#000"/>', "solidArrow"),
            ("", '<path d="M0 0 L8 3 L0 6 L3 3 Z"/>', "filledArrow"),
            (".o { fill: none }", '<path class="o" d="M0 0 L8 3 L0 6" stroke="#000"/>', "arrow"),
            ("", f'<polygon {diamond} fill="#fff" stroke="#000"/>', "openDiamond"),
            ("", f'<polygon {diamond}/>', "diamond"),
            ("", '<circle r="3" fill="#fff" stroke="#000"/>', "circle"),
        ):
            with self.subTest(css=css, marker=marker):
                document, _ = self.export(f"""<svg viewBox="0 0 400 300"><style>{css}</style>
                  <rect width="100%" height="100%" fill="#f5f5f5"/>
                  <defs><marker id="a">{marker}</marker></defs>
                  <line x1="10" y1="9" x2="90" y2="9" stroke="#000" marker-end="url(#a)"/></svg>""")
                [line] = document["pages"][0]["content"]["content"]["connections"]
                self.assertEqual(line["content"]["end_ending"], ending)

    def test_what_a_shape_or_rich_text_loses_gets_a_note(self) -> None:
        """A note lets the user fix what the export could not keep."""
        for transform in ("transform: none", "transform-origin: center"):
            _, skipped = self.export(
                f'<svg viewBox="0 0 400 300"><rect style="{transform}" width="9" height="9"/></svg>'
            )
            self.assertEqual(skipped, {})  # nothing is misplaced, so nothing is noted
        for svg, note in (
            ('<rect style="transform: translateX(9px)" width="9" height="9" fill="#000"/>',
             "CSS transform this export cannot read may misplace a shape"),
            ('<rect style="transform-origin: 5px 5px; transform: rotate(9deg)" width="9" height="9" fill="#000"/>',
             "CSS transform this export cannot read may misplace a shape"),
            ('<defs><marker id="a"><rect width="3" height="3"/></marker></defs>'
             '<line x1="1" y1="1" x2="90" y2="1" stroke="#000" marker-end="url(#a)"/>',
             "line ending other than an arrow, a circle or a diamond drawn as an arrow"),
            ('<foreignObject width="9" height="9"><div>One</div><div>Two</div></foreignObject>',
             "rich HTML text kept as plain text"),
            ('<text y="9">Left<tspan dx="150">Right</tspan></text>',
             "a wide sideways gap inside a line became one space"),
        ):  # fmt: skip
            with self.subTest(svg=svg):
                _, skipped = self.export(f'<svg viewBox="0 0 400 300">{svg}</svg>')
                self.assertIn(note, skipped)

    def test_an_important_declaration_beats_every_normal_one(self) -> None:
        """!important reverses the cascade, whatever the specificity or inline style says."""
        for css, attributes in (
            (".a { fill: #ff0000 !important } text.a { fill: #0000ff }", ""),
            (".a { fill: #ff0000 ! IMPORTANT }", 'style="fill: #0000ff"'),
            (".a { fill: #ff0000 !important; fill: #0000ff }", ""),
        ):
            with self.subTest(css=css):
                document, _ = self.export(
                    f"""<svg viewBox="0 0 400 300"><style>{css}</style>
                    <text class="a" x="9" y="50" {attributes}>Hi</text></svg>"""
                )
                self.assertIn('"#FF0000"', json.dumps(document))
                self.assertNotIn('"#0000FF"', json.dumps(document))

    def test_untranslatable_content_is_reported_not_silently_dropped(self) -> None:
        """Every kind of content left out or simplified is counted for a note."""
        _, skipped = self.export("""<svg viewBox="0 0 10 10"><use href="#a"/><image href="x.png"/>
          <rect width="5" height="5" fill="url(#gradient)" stroke="#000"/><walk/>
          <text><textPath href="#p">curved</textPath></text></svg>""")
        self.assertEqual(
            skipped,
            {
                "<use> of nothing left out": 1,
                "<image> left out": 1,
                "<walk> left out": 1,
                "<textPath> left out": 1,
                "gradient, pattern or unknown colour, left transparent": 1,
            },
        )

    def test_impossible_numbers_are_ignored_or_refused_clearly(self) -> None:
        """Non-finite numbers are dropped; sizes the format cannot hold are refused by name."""
        document, _ = self.export(
            '<svg viewBox="0 0 10 10"><rect x="nan" width="1e999" height="4"/>'
            '<rect width="4" height="4" transform="scale(1e999)"/></svg>'
        )
        self.assertEqual(len(document["pages"][0]["elements"]), 1)
        too_many = "".join(
            f'<rect x="{i % 100 * 3}" y="{i // 100 * 3}" width="2" height="2"/>'
            for i in range(self.mod.MAX_ITEMS + 1)
        )
        refused = (
            (
                "beyond what SimpleDiagrams can hold",
                '0 0 10 10"><rect x="2e9" width="4" height="4"/>',
            ),
            ("larger than a SimpleDiagrams page", '0 0 2e7 10"><rect width="4" height="4"/>'),
            ("this export handles up to", f'0 0 400 400">{too_many}'),
        )
        for message, content in refused:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                self.mod.export_document(f'<svg viewBox="{content}</svg>', Path("refused.html"))

    def test_reexport_is_byte_identical(self) -> None:
        """Exporting an unchanged diagram twice writes the same bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("example-architecture", "example-er", "example-dp-integration"):
                source = ASSETS / f"{name}.html"
                first, second = (Path(tmp, f"{name}-{n}.simplediagram") for n in "ab")
                for output in (first, second):
                    self.assertEqual(self.run_cli(str(source), str(output)), 0)
                self.assertEqual(package_bytes(first), package_bytes(second), name)

    def test_an_existing_document_is_never_replaced(self) -> None:
        """An existing output, a wrong suffix and the gallery are all refused untouched."""
        source = ASSETS / "example-flowchart.html"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp, "kept.simplediagram")
            output.mkdir()
            (output / "document.json").write_text("{}", encoding="utf-8")
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors):
                self.assertEqual(self.mod.main([str(source), str(output)]), 2)
                self.assertEqual(self.mod.main([str(source), str(Path(tmp, "wrong.json"))]), 2)
                self.assertEqual(self.mod.main([str(ASSETS / "index.html")]), 2)
            self.assertEqual((output / "document.json").read_text(encoding="utf-8"), "{}")
            self.assertIn("already exists", errors.getvalue())
            self.assertFalse(Path(tmp, "wrong.json").exists())


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ExportSimpleDiagramsTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
