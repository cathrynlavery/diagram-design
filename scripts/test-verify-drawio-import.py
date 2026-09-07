#!/usr/bin/env python3
"""Regression tests for the draw.io import verifier."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REFERENCE = Path("skills/diagram-design/references/import-drawio.md")
EXAMPLE = Path("skills/diagram-design/assets/example-import-drawio.html")
VERIFIER = Path("scripts/verify-drawio-import.py")


def run_verifier(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / VERIFIER)],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="diagram-design-drawio-test-") as tmp_dir:
        clone = Path(tmp_dir) / "repo"
        shutil.copytree(
            ROOT,
            clone,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )

        reference = clone / REFERENCE
        stale_name = "/diagram-design:import"
        valid_name = "/diagram-design:import-drawio"
        text = reference.read_text(encoding="utf-8")
        if valid_name not in text:
            raise AssertionError("test fixture lacks the valid slash name")

        valid = run_verifier(clone)
        if valid.returncode != 0:
            raise AssertionError(
                f"valid slash command failed verification:\n{valid.stdout}\n{valid.stderr}"
            )

        reference.write_text(text.replace(valid_name, stale_name), encoding="utf-8")
        stale = run_verifier(clone)
        if stale.returncode == 0:
            raise AssertionError("stale slash command unexpectedly passed verification")
        if "slash command" not in stale.stderr:
            raise AssertionError(
                f"stale slash command lacked a focused diagnostic:\n{stale.stderr}"
            )

        reference.write_text(text, encoding="utf-8")
        example = clone / EXAMPLE
        example_text = example.read_text(encoding="utf-8")
        direct_route = 'd="M560,232 H640"'
        elbow_route = 'd="M560,232 H592 V252 H640"'
        if direct_route not in example_text:
            raise AssertionError("worked-example fixture lacks the direct connector")
        example.write_text(example_text.replace(direct_route, elbow_route), encoding="utf-8")
        elbow = run_verifier(clone)
        if elbow.returncode == 0:
            raise AssertionError("elbowed gateway-to-orders connector unexpectedly passed")
        if "direct horizontal connector" not in elbow.stderr:
            raise AssertionError(
                f"elbowed connector lacked a focused diagnostic:\n{elbow.stderr}"
            )

    print("OK: draw.io verifier rejects stale command names and elbowed worked-example routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
