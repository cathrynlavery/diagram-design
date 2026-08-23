#!/usr/bin/env python3
"""One-shot environment diagnostics verifier for Diagram Design.

Runs read-only checks for local readiness and exits non-zero only on hard failures
(or warnings when --strict is supplied).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_RELATIVE = Path("skills/diagram-design/SKILL.md")

MAINTAINER_MARKERS = (
    Path("CONTRIBUTING.md"),
    Path(".github/workflows/ci.yml"),
    Path("scripts/verify-plugin-package.py"),
)

EXPECTED_SCRIPTS = (
    Path("scripts/verify-drawio-import.py"),
    Path("scripts/verify-mermaid-import.py"),
    Path("scripts/verify-motion.py"),
    Path("scripts/lint-skin.py"),
    Path("scripts/verify-docs-sync.py"),
)

ROUTING_SURFACES = {
    Path("commands/export-diagram.md"): "references/export.md",
    Path("commands/import-drawio.md"): "references/import-drawio.md",
    Path("commands/import-mermaid.md"): "references/import-mermaid.md",
    Path("commands/profile.md"): "references/profiles.md",
    Path("commands/doctor.md"): "references/doctor.md",
    Path("prompts/export-diagram.md"): "references/export.md",
    Path("prompts/import-mermaid.md"): "references/import-mermaid.md",
    Path("prompts/profile.md"): "references/profiles.md",
    Path("prompts/doctor.md"): "references/doctor.md",
}

PASS = "pass"
WARN = "warn"
FAIL = "fail"


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    fix: str | None = None


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def probe_python_command() -> tuple[str | None, str | None]:
    """Resolve python3 first, then python."""
    for candidate in ("python3", "python"):
        executable = shutil.which(candidate)
        if executable:
            return candidate, executable
    return None, None


def check_python_runtime() -> tuple[CheckResult, str | None]:
    command_name, executable = probe_python_command()
    if command_name is None or executable is None:
        return (
            CheckResult(
                name="Python runtime",
                status=FAIL,
                message="No python3 or python command was found on PATH.",
                fix="Install Python 3.10+ and ensure python3 or python is available on PATH.",
            ),
            None,
        )

    version_probe = run_command(
        [command_name, "-c", "import sys; print('.'.join(str(p) for p in sys.version_info[:3]))"]
    )
    if version_probe.returncode != 0:
        detail = version_probe.stderr.strip() or "version probe failed"
        return (
            CheckResult(
                name="Python runtime",
                status=FAIL,
                message=f"Could not query version via {command_name}: {detail}",
                fix="Ensure the selected Python command is executable and not blocked by shell aliases.",
            ),
            command_name,
        )

    version_text = version_probe.stdout.strip()
    try:
        major, minor, patch = (int(part) for part in version_text.split(".", 2))
    except ValueError:
        return (
            CheckResult(
                name="Python runtime",
                status=FAIL,
                message=f"Unexpected Python version format from {command_name}: {version_text!r}",
                fix="Use a standard CPython installation with semantic version output.",
            ),
            command_name,
        )

    if (major, minor) < (3, 10):
        return (
            CheckResult(
                name="Python runtime",
                status=FAIL,
                message=(
                    f"Python {major}.{minor}.{patch} found via {command_name} at {executable}; "
                    "Diagram Design requires Python >= 3.10."
                ),
                fix="Upgrade Python to 3.10+ and re-run /diagram-design:doctor.",
            ),
            command_name,
        )

    return (
        CheckResult(
            name="Python runtime",
            status=PASS,
            message=f"Python {major}.{minor}.{patch} found via {command_name} at {executable}.",
        ),
        command_name,
    )


def check_playwright(python_cmd: str | None) -> CheckResult:
    if python_cmd is None:
        return CheckResult(
            name="Playwright PNG export readiness",
            status=FAIL,
            message="Playwright check skipped because no Python command was available.",
            fix="Resolve Python first; then install with: pip install playwright && playwright install chromium",
        )

    import_probe = run_command([python_cmd, "-c", "import playwright; print(playwright.__version__)"])
    if import_probe.returncode != 0:
        return CheckResult(
            name="Playwright PNG export readiness",
            status=WARN,
            message="Playwright package is not available in the active Python interpreter.",
            fix="pip install playwright && playwright install chromium",
        )

    chromium_probe = run_command(
        [
            python_cmd,
            "-c",
            (
                "from pathlib import Path\n"
                "from playwright.sync_api import sync_playwright\n"
                "with sync_playwright() as p:\n"
                "    path = Path(p.chromium.executable_path)\n"
                "    print(path)\n"
                "    raise SystemExit(0 if path.is_file() else 3)\n"
            ),
        ]
    )
    if chromium_probe.returncode == 0:
        return CheckResult(
            name="Playwright PNG export readiness",
            status=PASS,
            message=f"Playwright is installed and Chromium is present at {chromium_probe.stdout.strip()}.",
        )

    detail = chromium_probe.stderr.strip() or "Chromium executable was not detected"
    return CheckResult(
        name="Playwright PNG export readiness",
        status=WARN,
        message=f"Playwright is installed but Chromium is not ready: {detail}",
        fix="pip install playwright && playwright install chromium",
    )


def is_maintainer_checkout(root: Path) -> bool:
    """Return whether root is a source checkout with maintainer-only surfaces."""
    return all((root / marker).is_file() for marker in MAINTAINER_MARKERS)


def resolve_skill_file(root: Path) -> Path | None:
    """Find SKILL.md in either a repository/plugin root or standalone skill root."""
    repository_skill = root / SKILL_RELATIVE
    if repository_skill.is_file():
        return repository_skill
    standalone_skill = root / "SKILL.md"
    if standalone_skill.is_file():
        return standalone_skill
    return None


def check_expected_scripts(root: Path) -> CheckResult:
    if not is_maintainer_checkout(root):
        return CheckResult(
            name="Expected script presence",
            status=PASS,
            message="Installed-skill mode detected; maintainer-only repository scripts are not required.",
        )

    missing = [path.as_posix() for path in EXPECTED_SCRIPTS if not (root / path).is_file()]
    if missing:
        return CheckResult(
            name="Expected script presence",
            status=FAIL,
            message="Missing required script(s): " + ", ".join(missing),
            fix="Restore missing scripts from the repository root and re-run diagnostics.",
        )
    return CheckResult(
        name="Expected script presence",
        status=PASS,
        message=f"All required scripts are present ({len(EXPECTED_SCRIPTS)} checked).",
    )


def check_routing_surfaces(root: Path) -> CheckResult:
    if not is_maintainer_checkout(root):
        return CheckResult(
            name="Plugin wiring surfaces",
            status=PASS,
            message="Installed-skill mode detected; maintainer command/prompt wiring is not required.",
        )

    missing_files: list[str] = []
    mismatched: list[str] = []

    for relative_path, reference in ROUTING_SURFACES.items():
        path = root / relative_path
        if not path.is_file():
            missing_files.append(relative_path.as_posix())
            continue
        source = path.read_text(encoding="utf-8")
        if reference not in source:
            mismatched.append(f"{relative_path.as_posix()} -> {reference}")

    if missing_files or mismatched:
        issues: list[str] = []
        if missing_files:
            issues.append("missing files: " + ", ".join(missing_files))
        if mismatched:
            issues.append("reference mismatches: " + ", ".join(mismatched))
        return CheckResult(
            name="Plugin wiring surfaces",
            status=FAIL,
            message="; ".join(issues),
            fix="Ensure each command/prompt file exists and routes to the matching references/*.md file.",
        )

    return CheckResult(
        name="Plugin wiring surfaces",
        status=PASS,
        message=f"All command/prompt routing surfaces are present and wired ({len(ROUTING_SURFACES)} checked).",
    )


def check_common_path_mistakes(root: Path, cwd: Path) -> CheckResult:
    warnings: list[str] = []
    fixes: list[str] = []

    if resolve_skill_file(root) is None:
        warnings.append(
            "Diagram Design SKILL.md was not found under the resolved installation root."
        )
        fixes.append("Reinstall or update Diagram Design, then run the doctor again.")

    if platform.system().lower().startswith("win") and " " in str(cwd):
        warnings.append(
            "Path contains spaces on Windows; unquoted shell examples can fail for import/export commands."
        )
        fixes.append('Use quoted paths, e.g. "C:/path with spaces/diagram.html".')

    if not warnings:
        return CheckResult(
            name="Common path mistakes",
            status=PASS,
            message="No common path mistakes were detected.",
        )

    return CheckResult(
        name="Common path mistakes",
        status=WARN,
        message=" ".join(warnings),
        fix=" ".join(fixes),
    )


def summarize(checks: list[CheckResult], strict: bool) -> tuple[str, dict[str, int], int]:
    counts = {PASS: 0, WARN: 0, FAIL: 0}
    for check in checks:
        counts[check.status] += 1

    if counts[FAIL] > 0:
        status = "FAIL"
    elif counts[WARN] > 0:
        status = "WARN"
    else:
        status = "PASS"

    exit_code = 0
    if counts[FAIL] > 0:
        exit_code = 1
    elif strict and counts[WARN] > 0:
        exit_code = 1

    return status, counts, exit_code


def print_report(checks: list[CheckResult], strict: bool, emit_json: bool) -> int:
    status, counts, exit_code = summarize(checks, strict)
    print(
        f"Doctor summary: {status} ({counts[PASS]} pass, {counts[WARN]} warn, {counts[FAIL]} fail)"
    )

    markers = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL"}
    for check in checks:
        print(f"[{markers[check.status]}] {check.name}: {check.message}")

    needs_next_actions = counts[WARN] > 0 or counts[FAIL] > 0
    if needs_next_actions:
        print("\nNext actions")
        for check in checks:
            if check.status in (WARN, FAIL) and check.fix:
                print(f"- {check.fix}")

    if emit_json:
        payload = {
            "status": status,
            "counts": counts,
            "checks": [asdict(check) for check in checks],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strict": strict,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python": sys.version.split()[0],
                "cwd": str(Path.cwd()),
                "root": str(ROOT),
            },
        }
        print(json.dumps(payload, indent=2))

    return exit_code


def run_doctor(root: Path, cwd: Path, strict: bool, emit_json: bool) -> int:
    checks: list[CheckResult] = []

    python_check, python_cmd = check_python_runtime()
    checks.append(python_check)
    checks.append(check_playwright(python_cmd))
    checks.append(check_expected_scripts(root))
    checks.append(check_routing_surfaces(root))
    checks.append(check_common_path_mistakes(root, cwd))

    return print_report(checks, strict, emit_json)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one-shot Diagram Design environment diagnostics."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report after the human summary.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = ROOT
    cwd = Path.cwd()
    return run_doctor(root, cwd, args.strict, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
