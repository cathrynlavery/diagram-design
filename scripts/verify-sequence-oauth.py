#!/usr/bin/env python3
"""Structural + skin-lint verification for sequence combined-fragment work.

Drives the real shipped artifacts (type-sequence.md, oauth examples, lint-skin.py).
Exit 0 only when all gates pass. Intended for local/PR checks alongside:
  python scripts/lint-skin.py --all --baseline
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPE_SEQ = ROOT / "skills/diagram-design/references/type-sequence.md"
ASSETS = ROOT / "skills/diagram-design/assets"
COLD = [
    ASSETS / "example-sequence.html",
    ASSETS / "example-sequence-dark.html",
    ASSETS / "example-sequence-full.html",
]
OAUTH = [
    ASSETS / "example-sequence-oauth.html",
    ASSETS / "example-sequence-oauth-dark.html",
    ASSETS / "example-sequence-oauth-full.html",
]
LINT = ROOT / "scripts/lint-skin.py"


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def main() -> int:
    if not TYPE_SEQ.is_file():
        fail(f"missing {TYPE_SEQ}")

    text = TYPE_SEQ.read_text(encoding="utf-8")
    required_sections = [
        "## Combined fragments",
        "### Open arrowhead (async)",
        "## Complexity budget",
        "## Anti-patterns",
        "arrow-open",
    ]
    for needle in required_sections:
        if needle not in text:
            fail(f"type-sequence.md missing {needle!r}")
    for op in ("ALT", "OPT", "LOOP"):
        if op not in text:
            fail(f"type-sequence.md missing operator {op}")
    if "[token valid]" not in text and "guard" not in text.lower():
        fail("type-sequence.md missing guard documentation")
    ok("type-sequence.md fragments + async + budget present")

    for path in COLD:
        if not path.is_file():
            fail(f"cold-cache example missing: {path.name}")
        body = path.read_text(encoding="utf-8")
        if "cold cache" not in body.lower() and "Article request" not in body:
            fail(f"{path.name} no longer looks like the cold-cache example")
        if "ALT" in body and "example-sequence-oauth" not in path.name:
            # cold-cache must not grow an ALT frame (special example only)
            # allow the word only in unrelated comments; require no ALT operator tab content
            if re.search(r">ALT<", body):
                fail(f"{path.name} unexpectedly contains ALT fragment tab")
    ok("cold-cache sequence trio intact (no ALT tab)")

    for path in OAUTH:
        if not path.is_file():
            fail(f"oauth example missing: {path.name}")
        body = path.read_text(encoding="utf-8")
        if ">ALT<" not in body and ">ALT</text>" not in body:
            # tab text is ALT
            if not re.search(r">\s*ALT\s*<", body):
                fail(f"{path.name} missing ALT operator label")
        if "[token valid]" not in body:
            fail(f"{path.name} missing [token valid] guard")
        if "[else" not in body and "[else · 401]" not in body:
            fail(f"{path.name} missing else-region guard")
        if "arrow-open" not in body:
            fail(f"{path.name} missing arrow-open async marker")
        if "Bearer" not in body and "BEARER" not in body:
            fail(f"{path.name} missing bearer call")
        # Return grammar: 401 and retry 200 body must be dashed (not solid calls)
        for y, label in (("368", "401"), ("544", "retry 200")):
            # line at y1=y must include stroke-dasharray when present
            m = re.search(
                rf'<line[^>]*y1="{y}"[^>]*/?>',
                body,
            )
            if not m:
                fail(f"{path.name} missing return line at y1={y} ({label})")
            if "stroke-dasharray" not in m.group(0):
                fail(f"{path.name} {label} return at y1={y} must be dashed")
        # First API activation must span past M2 (y=272)
        act = re.search(
            r'<rect x="476" y="180" width="8" height="(\d+)"',
            body,
        )
        if not act or int(act.group(1)) < 100:
            fail(f"{path.name} first API activation height must cover M2 (height>=100)")
    ok("oauth trio has ALT two-region structure + async open + dashed returns")

    # Drive real skin linter entry point on new files
    cmd = [
        sys.executable,
        str(LINT),
        *[str(p) for p in OAUTH],
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        fail(f"lint-skin.py failed on oauth examples (exit {proc.returncode})")
    if "0 finding(s)" not in proc.stdout:
        fail("lint-skin.py did not report 0 findings on oauth examples")
    ok("lint-skin.py clean on oauth examples")

    # Full repo gate
    proc2 = subprocess.run(
        [sys.executable, str(LINT), "--all", "--baseline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    print(proc2.stdout, end="")
    if proc2.returncode != 0:
        fail(f"lint-skin.py --all --baseline failed (exit {proc2.returncode})")
    if "0 finding(s)" not in proc2.stdout:
        fail("lint-skin.py --all --baseline did not report 0 findings")
    ok("lint-skin.py --all --baseline green")

    print("ALL GATES PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
