#!/usr/bin/env python3
"""Regression tests for verify-sequence-oauth.py.

verify-sequence-oauth.py drives its checks against the real shipped
sequence-diagram assets from a top-level main(), so it is exercised here as a
CLI smoke test (pass) plus an adversarial case that mutates a temporary copy
of the shipped OAuth examples to confirm a broken guard/return is rejected.
This mirrors the CLI smoke-test pattern used by test-verify-motion.py for
verify-motion.py.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-sequence-oauth.py"


def run_verifier(cwd: Path, verifier: Path = VERIFIER) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(verifier)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    # The shipped repo must pass all gates as-is.
    result = run_verifier(ROOT)
    if result.returncode != 0 or "ALL GATES PASSED" not in result.stdout:
        raise AssertionError(
            f"shipped repo failed verify-sequence-oauth.py\n{result.stdout}{result.stderr}"
        )
    print("OK: shipped repo passes verify-sequence-oauth.py")

    # Removing the dashed-return marker from the 401 response must be rejected.
    # verify-sequence-oauth.py resolves every path relative to its own file
    # location (ROOT = parent of scripts/), so the adversarial case runs
    # against a full temporary copy of the repository tree.
    with tempfile.TemporaryDirectory(prefix="verify-sequence-oauth-") as temp_dir:
        temp_root = Path(temp_dir) / "repo"
        shutil.copytree(ROOT, temp_root)
        oauth_copy = (
            temp_root
            / "skills/diagram-design/assets/example-sequence-oauth.html"
        )
        original = oauth_copy.read_text(encoding="utf-8")
        target_line = (
            '<line x1="476" y1="368" x2="168" y2="368" stroke="#4f5d75" '
            'stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>'
        )
        if target_line not in original:
            raise AssertionError(
                "expected shipped example-sequence-oauth.html to contain the dashed "
                "401 return line at y1=368"
            )
        broken = original.replace(
            target_line,
            target_line.replace('stroke-dasharray="5,4" ', ""),
            1,
        )
        if broken == original:
            raise AssertionError("failed to mutate example-sequence-oauth.html for the test")
        oauth_copy.write_text(broken, encoding="utf-8")

        # verify-sequence-oauth.py resolves ROOT from its own __file__, so the
        # adversarial run must invoke the copy inside temp_root, not VERIFIER.
        temp_verifier = temp_root / "scripts/verify-sequence-oauth.py"
        broken_result = run_verifier(temp_root, verifier=temp_verifier)
        if broken_result.returncode == 0:
            raise AssertionError(
                f"broken dashed return was accepted\n{broken_result.stdout}{broken_result.stderr}"
            )
        if "must be dashed" not in broken_result.stdout + broken_result.stderr:
            raise AssertionError(
                "expected a 'must be dashed' failure, got "
                f"{broken_result.stdout}{broken_result.stderr}"
            )
        print("OK: removing the dashed 401 return marker is rejected")

    print("All sequence-oauth verifier tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
