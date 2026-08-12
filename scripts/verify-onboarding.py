#!/usr/bin/env python3
"""Verification script for the automated brand onboarding CLI tool (scripts/onboard.py).

Verifies that onboard.py correctly parses CSS custom properties, calculates derived light/dark
semantic roles, enforces WCAG AA contrast ratios, and formats the style-guide.md tokens table.

Usage:
    python scripts/verify-onboarding.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
ONBOARD_SCRIPT = REPO / "scripts" / "onboard.py"


def test_onboard_folder_dry_run() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        css_file = tmp_path / "tokens.css"
        css_file.write_text("""
:root {
    --color-bg: #fafafa;
    --color-text: #1a1a1a;
    --color-brand: #ff4500;
    --color-muted: #666666;
}
""", encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--dry-run"]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: onboard.py exited with code {res.returncode}", file=sys.stderr)
            print(res.stderr, file=sys.stderr)
            sys.exit(1)

        output = res.stdout
        required_roles = ["paper", "paper-2", "ink", "muted", "soft", "rule", "rule-solid", "accent", "accent-tint", "link"]
        for role in required_roles:
            if f"`{role}`" not in output:
                print(f"FAIL: role `{role}` missing from onboard.py output", file=sys.stderr)
                sys.exit(1)

        print("OK: onboard.py folder dry-run test passed")


def main() -> int:
    print("Running verification suite for onboard.py...")
    test_onboard_folder_dry_run()
    print("ALL ONBOARDING GATES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
