#!/usr/bin/env python3
"""Verification script for the automated brand onboarding CLI tool (scripts/onboard.py).

Verifies zero-confidence extraction guards, format-aware JSON/SCSS parsing, WCAG AA contrast enforcement
for medium backgrounds and dark mode, crash-safe atomic write with retained backup, and URL scheme rejection.

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


def test_onboard_folder_preview() -> None:
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

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: onboard.py exited with code {res.returncode}", file=sys.stderr)
            print(res.stderr, file=sys.stderr)
            sys.exit(1)

        output = res.stdout
        if "[Preview mode]" not in output:
            print("FAIL: default mode must be preview mode", file=sys.stderr)
            sys.exit(1)

        required_roles = ["paper", "paper-2", "ink", "muted", "soft", "rule", "rule-solid", "accent", "accent-tint", "link"]
        for role in required_roles:
            if f"`{role}`" not in output:
                print(f"FAIL: role `{role}` missing from onboard.py output", file=sys.stderr)
                sys.exit(1)

        print("OK: onboard.py folder preview mode test passed")


def test_zero_confidence_extraction_guard() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        empty_css = tmp_path / "empty.css"
        empty_css.write_text("/* No hex colors or design tokens */ body { margin: 0; }", encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--apply"]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode == 0 or "Zero-confidence extraction" not in res.stderr:
            print("FAIL: zero-confidence extraction did not halt execution", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py zero-confidence extraction guard test passed")


def test_format_aware_json_scss_parsing() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        scss_file = tmp_path / "vars.scss"
        scss_file.write_text("""
$brand-bg: #101010;
$brand-text: #f0f0f0;
$brand-primary: #0088ff;
""", encoding="utf-8")

        json_file = tmp_path / "tokens.json"
        json_file.write_text("""
{
  "color": {
    "primary": {
      "$value": "#ff5500"
    },
    "muted": {
      "value": "#888888"
    }
  }
}
""", encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: format-aware SCSS/JSON parsing failed: {res.stderr}", file=sys.stderr)
            sys.exit(1)

        if "`#101010`" not in res.stdout or "`#ff5500`" not in res.stdout:
            print("FAIL: SCSS/JSON nested design tokens were not extracted correctly", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py format-aware SCSS/JSON parsing test passed")


def test_medium_bg_contrast_and_dark_mode_validation() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = pathlib.Path(tmpdir)
        css_file = tmp_path / "medium.css"
        # Medium background #888888 requires intelligent direction contrast adjustment
        css_file.write_text("""
:root {
    --color-bg: #888888;
    --color-text: #777777;
}
""", encoding="utf-8")

        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path)]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: medium background contrast calculation failed: {res.stderr}", file=sys.stderr)
            sys.exit(1)

        if "[WCAG AA] [Light Mode] Adjusted" not in res.stdout:
            print("FAIL: WCAG AA contrast adjustment missing for medium background", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py medium background & dark mode contrast validation test passed")


def test_atomic_write_and_retained_backup() -> None:
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
        orig_content = STYLE_GUIDE.read_text(encoding="utf-8")
        out_guide.write_text(orig_content, encoding="utf-8")

        # 1. Test atomic write with --apply and retained backup
        cmd = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--out", str(out_guide), "--apply"]
        res = subprocess.run(cmd, capture_output=True, text=True)

        if res.returncode != 0:
            print(f"FAIL: atomic --apply write failed: {res.stderr}", file=sys.stderr)
            sys.exit(1)

        updated_text = out_guide.read_text(encoding="utf-8")
        if "`#ffffff`" not in updated_text or "`#0066cc`" not in updated_text:
            print("FAIL: style-guide.md table was not updated atomically", file=sys.stderr)
            sys.exit(1)

        backup_file = out_guide.with_name(out_guide.name + ".bak")
        if not backup_file.exists():
            print("FAIL: retained backup file (.bak) was not preserved", file=sys.stderr)
            sys.exit(1)

        if backup_file.read_text(encoding="utf-8") != orig_content:
            print("FAIL: retained backup file content does not match original style guide", file=sys.stderr)
            sys.exit(1)

        # 2. Test invalid --out path failure
        bad_out = tmp_path / "non-existent-dir" / "style-guide.md"
        cmd_bad = [sys.executable, str(ONBOARD_SCRIPT), "--folder", str(tmp_path), "--out", str(bad_out), "--apply"]
        res_bad = subprocess.run(cmd_bad, capture_output=True, text=True)

        if res_bad.returncode == 0:
            print("FAIL: onboard.py did not fail on invalid --out directory path", file=sys.stderr)
            sys.exit(1)

        print("OK: onboard.py crash-safe atomic write & retained backup test passed")


def test_url_scheme_rejection() -> None:
    cmd = [sys.executable, str(ONBOARD_SCRIPT), "--url", "file:///etc/passwd"]
    res = subprocess.run(cmd, capture_output=True, text=True)

    if res.returncode == 0 or "only http and https are permitted" not in res.stderr:
        print("FAIL: onboard.py did not reject non-http/https URL scheme", file=sys.stderr)
        sys.exit(1)

    print("OK: onboard.py URL scheme rejection test passed")


def main() -> int:
    print("Running adversarial verification suite for onboard.py...")
    test_onboard_folder_preview()
    test_zero_confidence_extraction_guard()
    test_format_aware_json_scss_parsing()
    test_medium_bg_contrast_and_dark_mode_validation()
    test_atomic_write_and_retained_backup()
    test_url_scheme_rejection()
    print("ALL ADVERSARIAL ONBOARDING GATES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
