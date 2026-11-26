#!/usr/bin/env python3
"""Adversarial tests for verify-doctor.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import time
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


def ready_timeout_probe(module, command: list[str], child_marker: Path):
    """Separate fixture startup from the unchanged short cleanup wait."""
    real_popen = module.subprocess.Popen
    ready_at, child_pid, setup_error = None, None, None

    def fixture_popen(probe_command, **kwargs):
        setup_deadline = time.monotonic() + 5
        process = real_popen(probe_command, **kwargs)
        if probe_command != command:
            return process  # e.g. Windows taskkill during owned-tree cleanup
        real_wait = process.wait
        setup_checked = False

        def wait_after_ready(timeout=None):
            nonlocal setup_checked, ready_at, child_pid, setup_error
            if setup_checked:
                return real_wait(timeout=timeout)
            setup_checked = True
            while time.monotonic() < setup_deadline:
                try:
                    pid = int(child_marker.read_text())
                except (OSError, ValueError):
                    pid = 0  # the file may not exist yet or still be written
                if pid > 0:
                    child_pid, ready_at = pid, time.monotonic()
                    return real_wait(timeout=timeout)
                if process.poll() is not None:
                    setup_error = f"parent exited {process.returncode} before writing a child PID"
                    break
                time.sleep(0.01)
            if setup_error is None:
                setup_error = "child PID was not ready within the separate 5-second startup budget"
            # Enter the real verifier's owned-tree cleanup even when setup
            # failed; never raise out of it with a freshly spawned tree alive.
            raise subprocess.TimeoutExpired(command, timeout)

        process.wait = wait_after_ready
        return process

    module.subprocess.Popen = fixture_popen
    try:
        result = module.run_command(command, timeout=0.5)
    finally:
        module.subprocess.Popen = real_popen
    if setup_error is not None:
        raise AssertionError(f"Cleanup fixture setup failed: {setup_error}; {result.stderr}")
    if ready_at is None or child_pid is None:
        raise AssertionError("Cleanup fixture did not reach the readiness handshake")
    return result, child_pid, time.monotonic() - ready_at


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

        # Exercise the probe through a real subprocess against Playwright's
        # import contract: the package need not expose a __version__ attribute.
        fake_package = root / "import-probe" / "playwright"
        touch(fake_package / "__init__.py", "# No __version__ attribute.\n")
        # A supported headless-only installation has no full Chromium path.
        # Model the public launch/close contract in a real probe subprocess.
        browser_path = root / "import-probe" / "missing-full-chromium"
        closed_path = root / "import-probe" / "browser-closed"
        api_source = (
            "from pathlib import Path\n"
            "from types import SimpleNamespace\n"
            "class Browser:\n"
            "    version = 'test-chromium'\n"
            f"    def close(self): Path({str(closed_path)!r}).write_text('closed')\n"
            "class Chromium:\n"
            f"    executable_path = {str(browser_path)!r}\n"
            "    def launch(self, *, timeout):\n"
            "        assert timeout == 5000, timeout\n"
            "        return Browser()\n"
            "class sync_playwright:\n"
            "    def __enter__(self): return SimpleNamespace(chromium=Chromium())\n"
            "    def __exit__(self, *args): pass\n"
        )
        touch(fake_package / "sync_api.py", api_source)
        original_pythonpath = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = str(fake_package.parent)
        real_run = verify.run_command
        calls = []

        def record_probe(command, **kwargs):
            calls.append((command, kwargs))
            return real_run(command, **kwargs)

        verify.run_command = record_probe
        try:
            expect_status(verify.check_playwright(sys.executable), verify.PASS,
                          "Chromium test-chromium launches for PNG export")
            if browser_path.exists() or closed_path.read_text() != "closed":
                raise AssertionError("headless-only readiness did not launch and close the browser")
            if calls[-1][1] != {"timeout": 10}:
                raise AssertionError(f"browser subprocess probe must be bounded: {calls[-1]}")
            print("OK: working default headless browser passes without a full executable path")

            closed_path.unlink()
            touch(fake_package / "sync_api.py", api_source.replace(
                "        return Browser()\n",
                "        raise RuntimeError('Chromium browser unavailable')\n",
            ))
            expect_status(verify.check_playwright(sys.executable), verify.WARN,
                          "Chromium browser unavailable")
            if closed_path.exists():
                raise AssertionError("failed launch must not pretend a browser was created")
            print("OK: unlaunchable Chromium stays WARN with its actual failure")

            touch(fake_package / "sync_api.py", api_source.replace(
                "    version = 'test-chromium'\n",
                "    @property\n"
                "    def version(self): raise RuntimeError('version query failed')\n",
            ))
            expect_status(verify.check_playwright(sys.executable), verify.WARN,
                          "version query failed")
            if closed_path.read_text() != "closed":
                raise AssertionError("readiness probe must close a browser even if inspection fails")
            print("OK: browser is closed when its version inspection fails")

            touch(fake_package / "__init__.py", "raise ModuleNotFoundError('playwright unavailable')\n")
            expect_status(verify.check_playwright(sys.executable), verify.WARN,
                          "Playwright package is not available")
        finally:
            verify.run_command = real_run
            if original_pythonpath is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = original_pythonpath
        print("OK: real import probe does not require Playwright version metadata")

        timeout_probe = verify.run_command(
            [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1,
        )
        if timeout_probe.returncode == 0 or "timed out" not in timeout_probe.stderr:
            raise AssertionError(f"stalled probe was not reported as a bounded failure: {timeout_probe}")
        print("OK: a stalled subprocess probe becomes a diagnostic failure")

        # The child inherits the probe's output handles and outlives its parent
        # unless timeout cleanup owns the entire freshly launched process tree.
        child_marker = root / "timeout-child.pid"
        child_code = "import time; time.sleep(10)"
        parent_code = (
            "import subprocess, sys, time; from pathlib import Path; "
            f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
            f"Path({str(child_marker)!r}).write_text(str(child.pid)); time.sleep(10)"
        )
        descendant_probe, child_pid, elapsed = ready_timeout_probe(
            verify, [sys.executable, "-c", parent_code], child_marker,
        )
        if descendant_probe.returncode == 0 or "timed out" not in descendant_probe.stderr:
            raise AssertionError(f"descendant probe did not time out: {descendant_probe}")
        if elapsed > 5:
            raise AssertionError(f"inherited output handles stalled cleanup: {elapsed:.2f}s")
        if os.name == "posix":
            state = subprocess.run(
                ["ps", "-p", str(child_pid), "-o", "stat="],
                capture_output=True, text=True, check=False,
            ).stdout.strip()
            # A reparented zombie has exited; it cannot be waited on here.
            if state and not state.startswith("Z"):
                raise AssertionError(f"timed probe left a running child: {child_pid} {state}")
        else:
            if "cleanup failed" in descendant_probe.stderr:
                raise AssertionError(descendant_probe.stderr)
            state = subprocess.run(
                ["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=False, timeout=2,
            ).stdout
            if f'"{child_pid}"' in state:
                raise AssertionError(f"timed probe left a running child: {state}")
        print("OK: inherited output handles cannot stall timeout tree cleanup")

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
