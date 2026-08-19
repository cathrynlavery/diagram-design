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

    print("OK: draw.io verifier rejects a stale slash command name")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
