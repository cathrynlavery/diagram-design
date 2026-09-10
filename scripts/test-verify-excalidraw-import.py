#!/usr/bin/env python3
"""Regression tests for the Excalidraw import verifier."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REFERENCE = Path("skills/diagram-design/references/import-excalidraw.md")
EXAMPLE = Path("skills/diagram-design/assets/example-import-excalidraw.html")
FIXTURE = Path("scripts/fixtures/sample-adversarial.excalidraw")
VERIFIER = Path("scripts/verify-excalidraw-import.py")


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
    with tempfile.TemporaryDirectory(prefix="diagram-design-excalidraw-test-") as tmp_dir:
        clone = Path(tmp_dir) / "repo"
        shutil.copytree(
            ROOT,
            clone,
            ignore=shutil.ignore_patterns(".git", "__pycache__"),
        )

        valid = run_verifier(clone)
        if valid.returncode != 0:
            raise AssertionError(
                f"pristine tree failed verification:\n{valid.stdout}\n{valid.stderr}"
            )

        reference = clone / REFERENCE
        stale_name = "/diagram-design:import"
        valid_name = "/diagram-design:import-excalidraw"
        text = reference.read_text(encoding="utf-8")
        if valid_name not in text:
            raise AssertionError("test fixture lacks the valid slash name")

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
        doc_inline = 'viewBox="0 0 960 600"'
        if doc_inline not in example_text:
            raise AssertionError("worked-example fixture lacks the doc-inline viewBox")
        example.write_text(
            example_text.replace(doc_inline, 'viewBox="0 0 1000 600"'),
            encoding="utf-8",
        )
        resized = run_verifier(clone)
        if resized.returncode == 0:
            raise AssertionError("off-preset worked example unexpectedly passed")
        if "doc-inline viewBox" not in resized.stderr:
            raise AssertionError(
                f"off-preset example lacked a focused diagnostic:\n{resized.stderr}"
            )
        example.write_text(example_text, encoding="utf-8")

        example.write_text(
            example_text.replace('<div class="diagram-container">', ""),
            encoding="utf-8",
        )
        overflowing = run_verifier(clone)
        if overflowing.returncode == 0:
            raise AssertionError("worked example without its local scroller unexpectedly passed")
        if "local horizontal scroller" not in overflowing.stderr:
            raise AssertionError(
                f"mobile overflow lacked a focused diagnostic:\n{overflowing.stderr}"
            )
        example.write_text(example_text, encoding="utf-8")

        fixture = clone / FIXTURE
        document = json.loads(fixture.read_text(encoding="utf-8"))
        for element in document["elements"]:
            if element["id"] == "payload-box":
                element.pop("link", None)
        fixture.write_text(json.dumps(document, indent=2), encoding="utf-8")
        leaked = run_verifier(clone)
        if leaked.returncode == 0:
            raise AssertionError(
                "adversarial fixture without its element link unexpectedly passed"
            )
        if "discard counts" not in leaked.stderr:
            raise AssertionError(
                f"changed trust-boundary inventory lacked a focused diagnostic:\n{leaked.stderr}"
            )

    print(
        "OK: Excalidraw verifier rejects stale command names, off-preset examples, "
        "mobile overflow, and drifted trust-boundary inventories"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
