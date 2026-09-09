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


class FakeCompletedProcess:
    """Just enough of subprocess.CompletedProcess for the probe to read."""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@contextlib.contextmanager
def fake_python_path(module, resolved: dict[str, str], responses: dict[str, object]):
    """Pretend PATH resolves `resolved` and each interpreter answers `responses`."""
    real_which, real_run = module.shutil.which, module.run_command
    module.shutil.which = lambda name: resolved.get(name)
    module.run_command = lambda command: responses[command[0]]
    try:
        yield
    finally:
        module.shutil.which, module.run_command = real_which, real_run


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

        # A name on PATH is not an interpreter. Windows ships a `python3` App
        # Execution Alias that exits non-zero with a Microsoft Store prompt, so
        # the probe has to fall through to `python` rather than report that a
        # perfectly healthy machine has no usable Python.
        alias_path = r"C:\Users\dev\AppData\Local\Microsoft\WindowsApps\python3.exe"
        real_path = r"C:\Program Files\Python312\python.exe"
        store_alias = FakeCompletedProcess(
            9009,
            stderr=(
                "Python was not found; run without arguments to install from the "
                "Microsoft Store, or disable this shortcut from Settings"
            ),
        )
        working_python = FakeCompletedProcess(0, stdout="3.12.9\n")

        with fake_python_path(
            verify,
            {"python3": alias_path, "python": real_path},
            {"python3": store_alias, "python": working_python},
        ):
            check, python_cmd = verify.check_python_runtime()
            expect_status(check, verify.PASS, "Python 3.12.9 found via python")
            if python_cmd != "python":
                raise AssertionError(f"expected downstream checks to use python, got {python_cmd!r}")
            probe = verify.probe_python_command()
            if (probe.command, probe.version) != ("python", "3.12.9"):
                raise AssertionError(f"probe did not fall through a non-running python3: {probe}")
        print("OK: a python3 that cannot report its version falls through to python")

        # When nothing on PATH runs, the failure still names the first candidate
        # tried and carries that interpreter's own stderr.
        with fake_python_path(
            verify,
            {"python3": alias_path, "python": alias_path},
            {"python3": store_alias, "python": store_alias},
        ):
            check, python_cmd = verify.check_python_runtime()
            expect_status(check, verify.FAIL, "Could not query version via python3")
            if "Microsoft Store" not in check.message:
                raise AssertionError("probe failure dropped the interpreter's own stderr")
            # That FAIL still hands a command name downstream, so the Playwright
            # check runs against an interpreter already known not to answer.
            expect_status(
                verify.check_playwright(python_cmd),
                verify.WARN,
                "Playwright package is not available",
            )
        print("OK: no runnable interpreter still fails, naming the first candidate")

        # Some names on PATH cannot be launched at all rather than exiting
        # non-zero. A directory stands in for the broken alias or dangling
        # symlink: spawning it raises OSError on every platform we support.
        launch_failure = verify.run_command([str(root), "-c", verify.VERSION_PROBE])
        if launch_failure.returncode == 0 or not launch_failure.stderr:
            raise AssertionError(
                f"unlaunchable command did not report a failure: {launch_failure}"
            )
        print("OK: a command that cannot be launched is reported, not raised")

        # And that reported shape has to fall through like any other dud, or the
        # doctor dies on the candidate this fallback exists to survive.
        with fake_python_path(
            verify,
            {"python3": alias_path, "python": real_path},
            {
                "python3": FakeCompletedProcess(1, stderr=str(launch_failure.stderr)),
                "python": working_python,
            },
        ):
            probe = verify.probe_python_command()
            if (probe.command, probe.version) != ("python", "3.12.9"):
                raise AssertionError(f"a python3 that cannot be launched did not fall through: {probe}")
        print("OK: a python3 that cannot be launched falls through to python")

        # No interpreter on PATH at all remains a hard failure.
        with fake_python_path(verify, {}, {}):
            check, python_cmd = verify.check_python_runtime()
            expect_status(check, verify.FAIL, "No python3 or python command was found")
            if python_cmd is not None:
                raise AssertionError(f"expected no python command, got {python_cmd!r}")
        print("OK: an empty PATH fails without naming a command")

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
