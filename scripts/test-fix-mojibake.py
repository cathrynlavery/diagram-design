#!/usr/bin/env python3
"""Regression tests for the mojibake repair utility."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fix-mojibake.py"


def main() -> int:
    # These are the strings produced when UTF-8 arrow bytes are decoded as
    # Windows-1252. Byte 0x90 is undefined in CP1252, hence the explicit escape.
    source = "right â†’, left \u00e2\u2020\u0090, up â†‘, down â†“\n"
    expected = "right →, left ←, up ↑, down ↓\n"
    with tempfile.TemporaryDirectory(prefix="diagram-design-mojibake-") as directory:
        path = Path(directory) / "fixture.md"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(f"repair failed: {result.stdout}{result.stderr}")
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            raise AssertionError(f"expected {expected!r}, got {actual!r}")
    print("PASS: mojibake arrow sequences repair to the intended directions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
