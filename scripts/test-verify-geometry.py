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

    check_file("shipped architecture example", ARCHITECTURE, 0)
    check_file("shipped swimlane example", SWIMLANE, 0)
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
