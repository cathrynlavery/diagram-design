#!/usr/bin/env python3
"""Adversarial tests for the label geometry verifier (verify-geometry.py)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-geometry.py"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
ARCHITECTURE = ASSET_DIR / "example-architecture.html"
SWIMLANE = ASSET_DIR / "example-swimlane.html"
ZONED = ASSET_DIR / "example-dp-integration.html"
SEQUENCE_OAUTH = ASSET_DIR / "example-sequence-oauth.html"
HIGH_LEVEL = ASSET_DIR / "example-high-level.html"
QUEUE_ANIMATED = ASSET_DIR / "example-queue-animated.html"
MEDALLION = ASSET_DIR / "example-medallion.html"
DB_SCHEMA = ASSET_DIR / "example-db-schema.html"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_geometry", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SVG_HEAD = (
    '<svg viewBox="0 0 400 200" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="t-title t-desc">'
    "<title id=\"t-title\">T</title><desc id=\"t-desc\">T.</desc>"
)


def document(body: str) -> str:
    return f"<!DOCTYPE html><html><body>{SVG_HEAD}{body}</svg></body></html>"


def main() -> int:
    module = load_verifier()
    failures: list[str] = []

    def check(label: str, source: str, expect_findings: int) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if len(findings) != expect_findings:
            failures.append(
                f"{label}: expected {expect_findings} finding(s), got "
                f"{len(findings)}: {findings}"
            )
        else:
            print(f"OK: {label}")

    def check_message(label: str, source: str, expect_text: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if len(findings) != 1 or expect_text not in findings[0]:
            failures.append(f"{label}: expected one finding naming {expect_text!r}, got {findings}")
        else:
            print(f"OK: {label}")

    def check_file(label: str, path: Path, expect_findings: int) -> None:
        findings = module.check(path)
        if len(findings) != expect_findings:
            failures.append(
                f"{label}: expected {expect_findings} finding(s), got "
                f"{len(findings)}: {findings}"
            )
        else:
            print(f"OK: {label}")

    node = '<rect x="100" y="60" width="160" height="64" rx="6" fill="#f5f5f5"/>'
    badge = '<rect x="108" y="68" width="32" height="12" rx="2" fill="#f5f5f5"/>'
    zone = '<rect x="80" y="40" width="240" height="120" rx="8" fill="#eee"/>'

    # A label mask straddling a node declared later is the defect being caught.
    check(
        "mask clipped by a later node",
        document('<rect x="240" y="80" width="48" height="12" rx="2" fill="#f5f5f5"/>' + node),
        1,
    )
    # Same geometry, but the node is painted first, so the label stays on top.
    check(
        "mask over an earlier node is legal",
        document(node + '<rect x="240" y="80" width="48" height="12" rx="2" fill="#f5f5f5"/>'),
        0,
    )
    # A badge chip fully inside its own node is legal regardless of order.
    check("badge chip inside a node", document(badge + node), 0)
    # A zone eyebrow overlaps the zone container, which is painted first.
    check(
        "zone eyebrow on a zone container",
        document(zone + '<rect x="160" y="34" width="60" height="12" rx="2" fill="#f5f5f5"/>'),
        0,
    )
    # A mask entirely in open canvas is legal.
    check(
        "mask clear of every node",
        document('<rect x="10" y="10" width="48" height="12" rx="2" fill="#f5f5f5"/>' + node),
        0,
    )
    # Touching within the 1px tolerance is not a finding.
    check(
        "mask abutting a node edge",
        document('<rect x="52" y="80" width="48" height="12" rx="2" fill="#f5f5f5"/>' + node),
        0,
    )

    # A long mono plate (128px, as shipped in example-sequence-oauth.html) or a
    # wide CJK label plate must be recognized as a mask and checked like any other.
    check(
        "wide mono mask clipped by a later node",
        document('<rect x="180" y="80" width="128" height="12" rx="2" fill="#f5f5f5"/>' + node),
        1,
    )
    check(
        "wide mono mask over an earlier node is legal",
        document(node + '<rect x="180" y="80" width="128" height="12" rx="2" fill="#f5f5f5"/>'),
        0,
    )
    # Wide-but-tall rects are container header bars or row stripes, not masks —
    # the height cap stays at 14 so they are never reported.
    check(
        "container header bar is not a mask",
        document('<rect x="80" y="80" width="188" height="16" rx="2" fill="#eee"/>' + node),
        0,
    )

    # Shapes inside <defs> are definitions, not painted nodes (#306): the
    # prototype below sits at the mask's coordinates in its local space, and
    # only its <use> instance is painted, clear of the mask.
    check(
        "node prototype inside defs does not clip a mask",
        document(
            '<rect x="50" y="80" width="80" height="12" rx="2" fill="#f5f5f5"/>'
            '<defs><g id="node-prototype">'
            '<rect x="100" y="70" width="100" height="60" rx="6" fill="#fff"/>'
            "</g></defs>"
            '<use href="#node-prototype" x="300" y="200"/>'
        ),
        0,
    )
    # The same prototype in a <symbol> is likewise definition-only.
    check(
        "node prototype inside a symbol does not clip a mask",
        document(
            '<rect x="50" y="80" width="80" height="12" rx="2" fill="#f5f5f5"/>'
            '<symbol id="node-prototype">'
            '<rect x="100" y="70" width="100" height="60" rx="6" fill="#fff"/>'
            "</symbol>"
        ),
        0,
    )
    # A rect inside <defs> is not a painted label mask either.
    check(
        "mask-shaped rect inside defs is not a mask",
        document('<defs><rect x="240" y="80" width="48" height="12" rx="2"/></defs>' + node),
        0,
    )
    # A tag mentioned inside a comment is not markup. The shipped template
    # explains its optional <pattern> in a comment inside <defs>; counting
    # that mention as an opening tag would leave the definition span open
    # to the end of the file and disable the check for everything after it.
    check(
        "comment mentioning a pattern tag does not disable later checks",
        document(
            "<!-- OPTIONAL: dot-pattern background. Uncomment the <pattern> "
            "and the second <rect> below for the dotted paper look. -->"
            '<defs><pattern id="dots" width="22" height="22">'
            '<circle cx="1" cy="1" r="1"/></pattern></defs>'
            '<rect x="240" y="80" width="48" height="12" rx="2" fill="#f5f5f5"/>'
            + node
        ),
        1,
    )
    # A closing tag inside a comment does not close a real container either:
    # the prototype stays a definition and still does not clip.
    check(
        "commented closing tag does not end a definition early",
        document(
            '<rect x="50" y="80" width="80" height="12" rx="2" fill="#f5f5f5"/>'
            "<defs><!-- </defs> -->"
            '<rect x="100" y="70" width="100" height="60" rx="6" fill="#fff"/>'
            "</defs>"
        ),
        0,
    )

    # An ordinary painted group is not a definition: its node still clips.
    check(
        "node inside a painted group still clips a mask",
        document(
            '<rect x="240" y="80" width="48" height="12" rx="2" fill="#f5f5f5"/>'
            f"<g>{node}</g>"
        ),
        1,
    )

    # Connector routing. A stroked node; arrows carry a marker to count.
    stroked = '<rect x="100" y="60" width="160" height="64" rx="6" fill="#fff" stroke="#2d3142"/>'
    arrow = 'fill="none" stroke="#4f5d75" marker-end="url(#arrow)"'

    # The reported defect: leave the top edge, then run flat along the border,
    # so the arrow appears to grow out of the top-right corner.
    check(
        "connector riding a node's top border",
        document(f'<path d="M 180,60 H 332 Q 340,60 340,52 V 20" {arrow}/>' + stroked),
        1,
    )
    # The same border ride against a stroked prototype inside <defs> is not a
    # finding: the definition is not a painted node (#306).
    check(
        "connector along a defs prototype border is not a border ride",
        document(f'<path d="M 180,60 H 332 Q 340,60 340,52 V 20" {arrow}/><defs>{stroked}</defs>'),
        0,
    )
    check(
        "connector leaving the side edge at its own port",
        document(f'<path d="M 260,84 H 332 Q 340,84 340,76 V 20" {arrow}/>' + stroked),
        0,
    )
    check(
        "diagonal connector",
        document(f'<line x1="10" y1="10" x2="60" y2="40" {arrow}/>'),
        1,
    )
    check(
        "diagonal line without a marker is not a connector",
        document('<line x1="10" y1="10" x2="60" y2="40" stroke="#4f5d75"/>'),
        0,
    )
    # Loop write-back spokes are the documented radial exception.
    check(
        "loop spoke is exempt from the diagonal rule",
        document(f'<path class="spoke" d="M 10 10 L 60 40" {arrow}/>'),
        0,
    )
    check(
        "connector landing on a node corner",
        document(f'<line x1="40" y1="60" x2="100" y2="60" {arrow}/>' + stroked),
        1,
    )
    # A fork shares the port and stacks its first 20px: both rules fire.
    check(
        "two connectors forking from one port",
        document(
            f'<path d="M 260,84 H 300" {arrow}/>'
            f'<path d="M 260,84 H 280 Q 288,84 288,92 V 120" {arrow}/>' + stroked
        ),
        2,
    )
    # One arrow lands where the next leaves: a chain the reader follows in order.
    check(
        "head-to-tail chain joint is legal",
        document(
            f'<path d="M 60,60 C 60,0 180,0 180,60" {arrow}/>'
            f'<path d="M 180,60 C 180,0 300,0 300,60" {arrow}/>' + stroked
        ),
        0,
    )
    # Identical local geometry in two translated panels must not collide.
    panel = f'<path d="M 260,84 H 300" {arrow}/>' + stroked
    check(
        "translated panels are compared in canvas space",
        document(f'<g transform="translate(0 0)">{panel}</g><g transform="translate(400 0)">{panel}</g>'),
        0,
    )
    # An arrowed axis along an unstroked quadrant fill is not a border ride.
    check(
        "unstroked fill rect is not a node",
        document(
            '<rect x="100" y="60" width="160" height="64" fill="rgba(235,108,54,0.04)"/>'
            f'<line x1="100" y1="40" x2="100" y2="200" {arrow}/>'
        ),
        0,
    )
    # Compact arc flags (`0120 20` = flags 0 and 1, then 20 20) must parse, so a
    # diagonal after the arc is still found rather than the path being dropped.
    check_message(
        "diagonal after a compact-flag arc is found",
        document(f'<path d="M 20,20 A 8 8 0 0128 28 L 60 60" {arrow}/>'),
        "diagonal segment",
    )
    check_message(
        "unparseable arrowed path fails closed",
        document(f'<path d="M 10 10 L 20" {arrow}/>'),
        "cannot parse",
    )
    # Rule 4: 12px between ports on a normal edge, 8px on a very small box.
    check(
        "ports 10px apart on a 64px edge",
        document(
            f'<path d="M 260,80 H 300" {arrow}/><path d="M 260,90 H 280 Q 288,90 288,98 V 140" {arrow}/>'
            + stroked
        ),
        1,
    )
    check(
        "ports 10px apart on a 40px edge",
        document(
            f'<path d="M 260,72 H 300" {arrow}/><path d="M 260,82 H 280 Q 288,82 288,90 V 140" {arrow}/>'
            '<rect x="100" y="60" width="160" height="40" rx="6" fill="#fff" stroke="#2d3142"/>'
        ),
        0,
    )
    # Rule 3: two sources sharing one trunk stack their strokes.
    check(
        "two connectors stacked on one trunk",
        document(
            f'<path d="M 20,200 H 52 Q 60,200 60,192 V 100" {arrow}/>'
            f'<path d="M 20,240 H 52 Q 60,240 60,232 V 120" {arrow}/>'
        ),
        1,
    )
    # Shared curved run with separate straight runs: only curve sampling sees it.
    check_message(
        "two connectors sharing a curved run",
        document(
            f'<path d="M 10,100 Q 50,100 50,60 H 90" {arrow}/>'
            f'<path d="M 10,110 V 100 Q 50,100 50,60 V 20" {arrow}/>'
        ),
        "runs on top of",
    )
    # Two connectors that only cross at a right angle are not stacked.
    check(
        "perpendicular crossing is not a stacked run",
        document(f'<path d="M 10,50 H 90" {arrow}/><path d="M 50,10 V 90" {arrow}/>'),
        0,
    )
    # Two separate right-angle crossings touch briefly twice; they must not add
    # up to a shared run.
    check(
        "two separate crossings are not a stacked run",
        document(f'<path d="M 10,50 H 90" {arrow}/><path d="M 30,10 V 90 H 70 V 10" {arrow}/>'),
        0,
    )
    # A fork away from any node shares a short stroke from one start point;
    # only head-to-tail joints are exempt, so it is measured from that point.
    check_message(
        "short fork from a shared start with no node",
        document(f'<path d="M 10,50 H 16 V 10" {arrow}/><path d="M 10,50 H 16 V 90" {arrow}/>'),
        "runs on top of",
    )
    # Coordinates under a rotate are not canvas space; skip rather than misjudge.
    check(
        "connector under a non-translate transform is skipped",
        document(f'<g transform="rotate(45)"><line x1="10" y1="10" x2="60" y2="40" {arrow}/></g>'),
        0,
    )

    check_file("shipped architecture example", ARCHITECTURE, 0)
    check_file("shipped swimlane example", SWIMLANE, 0)
    check_file("shipped high-level example", HIGH_LEVEL, 0)
    check_file("shipped queue animation", QUEUE_ANIMATED, 0)
    # Medallion's promotion arcs meet head to tail at each tier; that joint stays legal.
    check_file("shipped medallion chain joints", MEDALLION, 0)
    check_file("shipped db-schema example", DB_SCHEMA, 0)
    check_file("shipped zoned example", ZONED, 0)
    check_file("shipped sequence-oauth example", SEQUENCE_OAUTH, 0)

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All label geometry tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
