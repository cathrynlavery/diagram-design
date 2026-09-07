#!/usr/bin/env python3
"""Adversarial tests for verify-doctor.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-doctor.py"


def load_verify_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("diagram_design_verify_doctor", VERIFY)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-doctor.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def touch(path: Path, content: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def seed_repo(module, root: Path) -> None:
    touch(root / "skills/diagram-design/SKILL.md", "# Skill\n")
    for relative in module.MAINTAINER_MARKERS:
        touch(root / relative)
    for relative in module.EXPECTED_SCRIPTS:
        touch(root / relative)
    for relative, reference in module.ROUTING_SURFACES.items():
        touch(root / relative, f"Routes to {reference}.\n")


def expect_status(check, status: str, needle: str) -> None:
    if check.status != status or needle not in check.message:
        raise AssertionError(
            f"expected ({status}, contains {needle!r}); got ({check.status}, {check.message!r})"
        )


def main() -> int:
    verify = load_verify_module()

    with tempfile.TemporaryDirectory(prefix="verify-doctor-") as temp_dir:
        root = Path(temp_dir)
        seed_repo(verify, root)

        check = verify.check_expected_scripts(root)
        expect_status(check, verify.PASS, "All required scripts are present")
        print("OK: expected scripts pass when all are present")

        missing = root / verify.EXPECTED_SCRIPTS[0]
        missing.unlink()
        check = verify.check_expected_scripts(root)
        expect_status(check, verify.FAIL, "Missing required script")
        print("OK: missing expected script fails")
        touch(missing)

        check = verify.check_routing_surfaces(root)
        expect_status(check, verify.PASS, "routing surfaces")
        print("OK: routing surfaces pass when all are wired")

        broken_surface = root / next(iter(verify.ROUTING_SURFACES.keys()))
        broken_surface.write_text("stale standalone instructions\n", encoding="utf-8")
        check = verify.check_routing_surfaces(root)
        expect_status(check, verify.FAIL, "reference mismatches")
        print("OK: routing mismatch fails")

        check = verify.check_common_path_mistakes(root, root)
        if check.status not in (verify.PASS, verify.WARN):
            raise AssertionError(f"unexpected common path status: {check.status}")
        print("OK: common path check returns non-fail in normal repository roots")

        installed_root = root / "installed-skill"
        touch(installed_root / "SKILL.md", "# Installed skill\n")
        unrelated_project = root / "user-project"
        unrelated_project.mkdir()
        if verify.is_maintainer_checkout(installed_root):
            raise AssertionError("standalone skill was misidentified as a maintainer checkout")
        for installed_check in (
            verify.check_expected_scripts(installed_root),
            verify.check_routing_surfaces(installed_root),
            verify.check_common_path_mistakes(installed_root, unrelated_project),
        ):
            if installed_check.status != verify.PASS:
                raise AssertionError(
                    "healthy installed skill outside the maintainer repository did not pass: "
                    f"{installed_check}"
                )
        print("OK: installed skill in an arbitrary user project does not require maintainer files")

        summary_checks = [
            verify.CheckResult("a", verify.PASS, "ok"),
            verify.CheckResult("b", verify.WARN, "warn", "fix warn"),
        ]
        status, counts, exit_code = verify.summarize(summary_checks, strict=False)
        if (status, counts[verify.WARN], exit_code) != ("WARN", 1, 0):
            raise AssertionError("non-strict summarize did not preserve WARN semantics")
        status, counts, exit_code = verify.summarize(summary_checks, strict=True)
        if (status, counts[verify.WARN], exit_code) != ("WARN", 1, 1):
            raise AssertionError("strict summarize did not treat WARN as failure")
        print("OK: strict mode elevates WARN to failing exit code")

        report_out = io.StringIO()
        with contextlib.redirect_stdout(report_out):
            code = verify.print_report(summary_checks, strict=True, emit_json=True)
        report_text = report_out.getvalue()
        if code != 1:
            raise AssertionError(f"expected strict WARN report to exit 1, got {code}")
        for needle in (
            "Doctor summary: WARN",
            "Next actions",
            '"status": "WARN"',
            '"checks"',
        ):
            if needle not in report_text:
                raise AssertionError(f"report missing {needle!r}")
        print("OK: report prints summary, next actions, and JSON payload")

    print("All doctor verifier tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
