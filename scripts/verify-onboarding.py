#!/usr/bin/env python3
"""Verification script for the automated brand onboarding CLI tool (scripts/onboard.py).

Verifies that onboard.py correctly parses CSS custom properties, calculates derived light/dark
semantic roles, enforces WCAG AA contrast ratios, rejects invalid URL schemes, and updates style-guide.md.

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
STYLE_GUIDE = REPO / "skills" / "diagram-design" / "references" / "style-guide.md"


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


def test_onboard_non_dry_run_table_update() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        css_file = tmp_path / "tokens.css"
        css_file.write_text("""
:root {
    --color-bg: #ffffff;
    --color-text: #111111;
    --color-brand: #0066cc;
    --color-muted: #555555;
}
""", encoding="utf-8")
        out_guide = tmp_path / "style-guide.md"
        out_guide.write_text(STYLE_GUIDE.read_text(encoding="utf-8"), encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--out", str(out_guide)]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: non-dry-run onboard.py failed with code {res.returncode}", file=sys.stderr)
            sys.exit(1)

        updated_text = out_guide.read_text(encoding="utf-8")
        if "`#ffffff`" not in updated_text or "`#0066cc`" not in updated_text:
            print("FAIL: style-guide.md table was not updated with extracted colors", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py non-dry-run table replacement test passed")


def test_contrast_adjustment() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        css_file = tmp_path / "tokens.css"
        # #e0e0e0 text on #fafafa paper fails WCAG AA (contrast ~1.2:1) and requires adjustment
        css_file.write_text("""
:root {
    --color-bg: #fafafa;
    --color-text: #e0e0e0;
}
""", encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--dry-run"]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if "[WCAG AA] Adjusted" not in res.stdout:
            print("FAIL: contrast adjustment note missing for low-contrast text color", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py WCAG AA contrast adjustment test passed")


def test_url_scheme_rejection() -> None:
    cmd = [sys.executable, str(ONBOARD_SCRIPT), "--url", "file:///etc/passwd", "--dry-run"]
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode == 0 or "only http and https are permitted" not in res.stderr:
        print("FAIL: onboard.py did not reject non-http/https URL scheme", file=sys.stderr)
        sys.exit(1)

    print("OK: onboard.py URL scheme rejection test passed")


def main() -> int:
    print("Running verification suite for onboard.py...")
    test_onboard_folder_dry_run()
    test_onboard_non_dry_run_table_update()
    test_contrast_adjustment()
    test_url_scheme_rejection()
    print("ALL ONBOARDING GATES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
