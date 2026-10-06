#!/usr/bin/env python3
"""Regression tests for Devicon viewBox preservation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "scripts" / "build-icons.py"


def load_build_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("diagram_design_build_icons", BUILD)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load build-icons.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    build_icons = load_build_module()
    svg = '<svg viewBox="0 0 32 32"><path fill="#123456" d="M0 0h32v32H0z"/></svg>'
    normalized = build_icons.normalize_devicon(svg)
    if 'viewBox="0 0 32 32"' not in normalized:
        raise AssertionError(f"source viewBox was not preserved: {normalized}")
    if 'fill="#123456"' in normalized:
        raise AssertionError("source fill escaped currentColor normalization")
    if 'fill="currentColor"' not in normalized:
        raise AssertionError("normalized icon does not inherit currentColor")
    print("PASS: Devicon normalization preserves non-128 source viewBoxes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
