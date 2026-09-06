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
        host, evidence = verify.detect_host(installed_root, environ={"CLAUDECODE": "1"})
        if host != "claude-code" or "CLAUDECODE" not in evidence:
            raise AssertionError(f"expected claude-code from env marker; got {host} ({evidence})")
        host, _ = verify.detect_host(
            installed_root, environ={"COWORK_SESSION_ID": "abc", "CLAUDECODE": "1"}
        )
        if host != "cowork":
            raise AssertionError(f"cowork markers must outrank claude-code; got {host}")
        host, evidence = verify.detect_host(
            root / ".cursor" / "skills" / "diagram-design", environ={}
        )
        if host != "cursor":
            raise AssertionError(f"expected cursor from path hint; got {host} ({evidence})")
        host, _ = verify.detect_host(installed_root, environ={})
        if host is not None:
            raise AssertionError(f"expected unknown host without markers; got {host}")
        print("OK: host detection honors env markers, precedence, and path hints")

        channel, _ = verify.detect_install_channel(root)
        if channel != verify.CHANNEL_MAINTAINER:
            raise AssertionError(f"seeded repo should be maintainer-checkout; got {channel}")
        git_root = root / "git-install"
        touch(git_root / "SKILL.md", "# Installed skill\n")
        (git_root / ".git").mkdir(parents=True)
        channel, _ = verify.detect_install_channel(git_root)
        if channel != verify.CHANNEL_GIT:
            raise AssertionError(f"git metadata should classify as git channel; got {channel}")
        marketplace_root = root / "plugins" / "diagram-design"
        touch(marketplace_root / "SKILL.md", '# Skill\nmetadata:\n  version: "2.6"\n')
        channel, _ = verify.detect_install_channel(marketplace_root)
        if channel != verify.CHANNEL_MARKETPLACE:
            raise AssertionError(f"plugin cache path should classify as marketplace; got {channel}")
        channel, _ = verify.detect_install_channel(installed_root)
        if channel != verify.CHANNEL_COPIED:
            raise AssertionError(f"plain copy should classify as copied; got {channel}")
        print("OK: install channel detection covers maintainer/git/marketplace/copied")

        for host_name, channel_name, needle in (
            ("pi", verify.CHANNEL_GIT, "pi update --extensions"),
            ("cowork", verify.CHANNEL_MARKETPLACE, "mirror"),
            ("codex", verify.CHANNEL_MARKETPLACE, "codex plugin marketplace upgrade"),
            ("claude-code", verify.CHANNEL_MARKETPLACE, "/plugin install diagram-design@diagram-design"),
            ("cursor", verify.CHANNEL_COPIED, "newer checkout"),
        ):
            recipe = verify.update_recipe(host_name, channel_name)
            if needle not in recipe:
                raise AssertionError(
                    f"update recipe for ({host_name}, {channel_name}) missing {needle!r}: {recipe}"
                )
        print("OK: update recipes match each host/channel pair")

        fix = verify.playwright_fix(None, None)
        if fix != verify.PLAYWRIGHT_INSTALL_HINT:
            raise AssertionError(f"bare playwright fix must stay copy-pastable: {fix}")
        fix = verify.playwright_fix("claude-code", verify.CHANNEL_MARKETPLACE)
        for needle in (verify.PLAYWRIGHT_INSTALL_HINT, "/reload-plugins", "restart the"):
            if needle not in fix:
                raise AssertionError(f"host-aware playwright fix missing {needle!r}: {fix}")
        print("OK: playwright fix stays copy-pastable and gains host-specific one-shot hints")

        check = verify.check_marketplace_version(marketplace_root, "claude-code", verify.CHANNEL_MARKETPLACE)
        expect_status(check, verify.PASS, "metadata.version is 2.6")
        versionless_root = root / "plugins" / "versionless"
        touch(versionless_root / "SKILL.md", "# Skill without metadata\n")
        check = verify.check_marketplace_version(
            versionless_root, "claude-code", verify.CHANNEL_MARKETPLACE
        )
        expect_status(check, verify.WARN, "metadata.version")
        check = verify.check_marketplace_version(root, None, verify.CHANNEL_MAINTAINER)
        expect_status(check, verify.PASS, "not applicable")
        print("OK: marketplace version alignment advises, warns on unreadable metadata, and skips non-marketplace")

        touch(git_root / ".git" / "HEAD", "ref: refs/heads/main\n")
        check = verify.check_pi_install_pinning(git_root, "pi", verify.CHANNEL_GIT)
        expect_status(check, verify.WARN, "unpinned git branch")
        touch(git_root / ".git" / "HEAD", "0123456789abcdef0123456789abcdef01234567\n")
        check = verify.check_pi_install_pinning(git_root, "pi", verify.CHANNEL_GIT)
        expect_status(check, verify.PASS, "pinned")
        check = verify.check_pi_install_pinning(git_root, "claude-code", verify.CHANNEL_GIT)
        expect_status(check, verify.PASS, "not pi")
        check = verify.check_pi_install_pinning(marketplace_root, "pi", verify.CHANNEL_MARKETPLACE)
        expect_status(check, verify.PASS, "not applicable")
        print("OK: Pi pinning warns on branch refs and passes on pinned or non-git installs")

        missing_skill_root = root / "cowork-broken"
        missing_skill_root.mkdir()
        check = verify.check_cowork_mirror(missing_skill_root, "cowork", verify.CHANNEL_COPIED)
        expect_status(check, verify.FAIL, "private or internal mirror")
        touch(
            git_root / ".git" / "config",
            "[remote \"origin\"]\n\turl = https://github.com/cathrynlavery/diagram-design\n",
        )
        check = verify.check_cowork_mirror(git_root, "cowork", verify.CHANNEL_GIT)
        expect_status(check, verify.WARN, "public repository")
        check = verify.check_cowork_mirror(marketplace_root, "cowork", verify.CHANNEL_MARKETPLACE)
        expect_status(check, verify.PASS, "resolves under Cowork")
        check = verify.check_cowork_mirror(missing_skill_root, None, verify.CHANNEL_COPIED)
        expect_status(check, verify.PASS, "not cowork")
        print("OK: Cowork mirror check fails without skill resolution and warns on public-repo remotes")

        check = verify.check_common_path_mistakes(
            missing_skill_root, unrelated_project, "claude-code", verify.CHANNEL_MARKETPLACE
        )
        if check.status != verify.WARN or "/plugin install diagram-design@diagram-design" not in (check.fix or ""):
            raise AssertionError(
                f"missing skill after marketplace install must print the reinstall recipe: {check}"
            )
        print("OK: missing skill after a marketplace install prints the one-shot reinstall recipe")

        args = verify.parse_args(["--host", "pi", "--strict"])
        if args.host != "pi" or not args.strict:
            raise AssertionError(f"--host parsing failed: {args}")
        args = verify.parse_args([])
        if args.host != verify.AUTO_HOST:
            raise AssertionError(f"default host must be auto; got {args.host}")
        print("OK: --host flag parses and defaults to auto")

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
