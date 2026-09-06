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
import re
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

HOST_PROFILES = ("claude-code", "cowork", "codex", "cursor", "pi")
AUTO_HOST = "auto"

PUBLIC_REPO_SLUG = "cathrynlavery/diagram-design"

# Ordered: Cowork first because Cowork sessions can also carry Claude Code markers.
HOST_ENV_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cowork", ("COWORK_SESSION_ID", "CLAUDE_COWORK_SESSION")),
    ("claude-code", ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")),
    ("cursor", ("CURSOR_AGENT", "CURSOR_TRACE_ID")),
    ("codex", ("CODEX_HOME", "CODEX_SANDBOX")),
    ("pi", ("PI_SESSION_ID", "PI_HOME")),
)

HOST_PATH_HINTS: tuple[tuple[str, str], ...] = (
    ("cowork", "cowork"),
    ("claude-code", ".claude"),
    ("codex", ".codex"),
    ("cursor", ".cursor"),
    ("pi", ".pi"),
)

CHANNEL_MAINTAINER = "maintainer-checkout"
CHANNEL_GIT = "git"
CHANNEL_MARKETPLACE = "marketplace"
CHANNEL_COPIED = "copied"

MARKETPLACE_PATH_SEGMENTS = frozenset(
    {"plugins", "plugin-cache", "marketplace", "marketplaces"}
)

SKILL_VERSION_PATTERN = re.compile(
    r'^\s*version:\s*"?([0-9][0-9A-Za-z.\-]*)"?\s*$', re.MULTILINE
)

PLAYWRIGHT_INSTALL_HINT = "pip install playwright && playwright install chromium"

HOST_PLAYWRIGHT_HINTS = {
    "claude-code": (
        "Run it in the same Python environment Claude Code invokes, then run "
        "/reload-plugins so the session picks it up."
    ),
    "cowork": (
        "Install inside the Cowork session environment; sandboxed sessions do not "
        "see packages installed on the host machine."
    ),
    "codex": "Run it in the Codex workspace environment, then start a new session.",
    "cursor": (
        "Run it in the Cursor agent terminal so the interpreter matches the one "
        "used for PNG export."
    ),
    "pi": (
        "Run it in the interpreter Pi uses, then run /reload in the open session."
    ),
}

EXPECTED_SCRIPTS = (
    Path("scripts/verify-drawio-import.py"),
    Path("scripts/verify-mermaid-import.py"),
    Path("scripts/verify-excalidraw-import.py"),
    Path("scripts/verify-motion.py"),
    Path("scripts/lint-skin.py"),
    Path("scripts/verify-docs-sync.py"),
)

ROUTING_SURFACES = {
    Path("commands/export-diagram.md"): "references/export.md",
    Path("commands/import-drawio.md"): "references/import-drawio.md",
    Path("commands/import-mermaid.md"): "references/import-mermaid.md",
    Path("commands/import-excalidraw.md"): "references/import-excalidraw.md",
    Path("commands/profile.md"): "references/profiles.md",
    Path("commands/doctor.md"): "references/doctor.md",
    Path("prompts/export-diagram.md"): "references/export.md",
    Path("prompts/import-mermaid.md"): "references/import-mermaid.md",
    Path("prompts/import-excalidraw.md"): "references/import-excalidraw.md",
    Path("prompts/profile.md"): "references/profiles.md",
    Path("prompts/doctor.md"): "references/doctor.md",
}

VERSION_PROBE = "import sys; print('.'.join(str(p) for p in sys.version_info[:3]))"

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
    """Run a command, reporting a failure to launch the way a bad exit is reported.

    A name on PATH is not always a runnable program: an App Execution Alias for
    an uninstalled app, a dangling symlink, or a file without the exec bit raise
    instead of exiting. Every caller here only asks whether the command answered,
    so surface that as a non-zero result carrying the OS error rather than letting
    it unwind the whole doctor.
    """
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


@dataclass
class PythonProbe:
    """What resolving an interpreter name actually turned up."""

    command: str | None = None
    executable: str | None = None
    version: str | None = None
    error: str | None = None


def probe_python_command() -> PythonProbe:
    """Resolve python3 first, then python, preferring a name that actually runs.

    Presence on PATH is not evidence of an interpreter. On Windows the
    ``python3`` App Execution Alias ships on PATH by default and exits
    non-zero with a Microsoft Store prompt, so a machine with a working
    ``python`` is otherwise reported as having no usable Python at all. Fall
    through to the next candidate when the preferred name cannot report its
    own version, and keep the first name found so a total failure still says
    what was tried.
    """
    fallback = PythonProbe()
    for candidate in ("python3", "python"):
        executable = shutil.which(candidate)
        if executable is None:
            continue
        probe = run_command([candidate, "-c", VERSION_PROBE])
        version = probe.stdout.strip()
        if probe.returncode == 0 and version:
            return PythonProbe(command=candidate, executable=executable, version=version)
        if fallback.command is None:
            fallback = PythonProbe(
                command=candidate,
                executable=executable,
                error=probe.stderr.strip() or "version probe failed",
            )
    return fallback


def check_python_runtime() -> tuple[CheckResult, str | None]:
    probe = probe_python_command()
    command_name, executable = probe.command, probe.executable
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

    if probe.version is None:
        detail = probe.error or "version probe failed"
        return (
            CheckResult(
                name="Python runtime",
                status=FAIL,
                message=f"Could not query version via {command_name}: {detail}",
                fix="Ensure the selected Python command is executable and not blocked by shell aliases.",
            ),
            command_name,
        )

    version_text = probe.version
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


def playwright_fix(host: str | None = None, channel: str | None = None) -> str:
    """Compose the one-shot Playwright remediation for the resolved host/channel."""
    hints: list[str] = []
    host_hint = HOST_PLAYWRIGHT_HINTS.get(host or "")
    if host_hint:
        hints.append(host_hint)
    if channel == CHANNEL_MARKETPLACE:
        hints.append(
            "If PNG export still fails after a marketplace install, restart the "
            "session so the host reloads the plugin environment."
        )
    if not hints:
        return PLAYWRIGHT_INSTALL_HINT
    return f"{PLAYWRIGHT_INSTALL_HINT} ({' '.join(hints)})"


def check_playwright(
    python_cmd: str | None,
    host: str | None = None,
    channel: str | None = None,
) -> CheckResult:
    if python_cmd is None:
        return CheckResult(
            name="Playwright PNG export readiness",
            status=FAIL,
            message="Playwright check skipped because no Python command was available.",
            fix="Resolve Python first; then install with: " + playwright_fix(host, channel),
        )

    import_probe = run_command([python_cmd, "-c", "import playwright; print(playwright.__version__)"])
    if import_probe.returncode != 0:
        return CheckResult(
            name="Playwright PNG export readiness",
            status=WARN,
            message="Playwright package is not available in the active Python interpreter.",
            fix=playwright_fix(host, channel),
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
        fix=playwright_fix(host, channel),
    )


def detect_host(root: Path, environ: dict[str, str] | None = None) -> tuple[str | None, str]:
    """Best-effort host detection from environment markers, then install path."""
    env = os.environ if environ is None else environ
    for host, markers in HOST_ENV_MARKERS:
        for marker in markers:
            if env.get(marker):
                return host, f"environment variable {marker} is set"

    segments = [part.lower() for part in root.resolve().parts]
    for host, hint in HOST_PATH_HINTS:
        if any(hint in segment for segment in segments):
            return host, f"installation path contains {hint!r}"

    return None, "no host markers detected; pass --host to select a profile"


def detect_install_channel(root: Path) -> tuple[str, str]:
    """Classify how this installation arrived: maintainer checkout, git, marketplace, or copy."""
    if is_maintainer_checkout(root):
        return CHANNEL_MAINTAINER, "maintainer repository markers are present"
    if (root / ".git").exists():
        return CHANNEL_GIT, ".git metadata is present at the installation root"
    segments = {part.lower() for part in root.resolve().parts}
    marketplace_hits = sorted(segments & MARKETPLACE_PATH_SEGMENTS)
    if marketplace_hits:
        return (
            CHANNEL_MARKETPLACE,
            f"installation path contains marketplace cache segment {marketplace_hits[0]!r}",
        )
    return CHANNEL_COPIED, "no git metadata or marketplace cache path detected"


def update_recipe(host: str | None, channel: str | None) -> str:
    """Return the copy-pastable update/reinstall recipe for the resolved host/channel."""
    if channel == CHANNEL_MAINTAINER:
        return (
            "Maintainer checkout: update with `git pull` and re-run the "
            "CONTRIBUTING validation gates."
        )
    if channel == CHANNEL_MARKETPLACE:
        if host == "cowork":
            return (
                "Cowork updates flow through your organization's private mirror: "
                "merge a plugin version-bump PR to the mirror's default branch to "
                "trigger sync, then reinstall from the organization marketplace if "
                "the plugin is missing (README: Install -> Claude Cowork)."
            )
        if host == "codex":
            return (
                "Update with: codex plugin marketplace upgrade diagram-design, "
                "then start a new session."
            )
        return (
            "Update via /plugin -> Marketplaces -> diagram-design -> Enable "
            "auto-update, then run /reload-plugins when prompted. Reinstall with: "
            "/plugin install diagram-design@diagram-design."
        )
    if channel == CHANNEL_GIT:
        if host == "pi":
            return (
                "Update with: pi update --extensions, then run /reload in an open "
                "Pi session."
            )
        return (
            "Update with: git pull inside the installation checkout, then reload "
            "the skill in your host."
        )
    if host == "cursor":
        return (
            "Agent-installed copy: ask the agent to reinstall, or replace the "
            "copied skills/diagram-design directory from a newer checkout."
        )
    return (
        "Copied install: replace the skills/diagram-design directory from a newer "
        "checkout to update."
    )


def check_host_install_channel(
    host: str | None,
    host_evidence: str,
    channel: str,
    channel_evidence: str,
) -> CheckResult:
    host_label = host or "unknown"
    return CheckResult(
        name="Host profile and install channel",
        status=PASS,
        message=(
            f"Host profile: {host_label} ({host_evidence}). Install channel: "
            f"{channel} ({channel_evidence}). Update recipe: "
            f"{update_recipe(host, channel)}"
        ),
    )


def read_skill_metadata_version(root: Path) -> str | None:
    skill = resolve_skill_file(root)
    if skill is None:
        return None
    match = SKILL_VERSION_PATTERN.search(skill.read_text(encoding="utf-8"))
    if match is None:
        return None
    return match.group(1)


def check_marketplace_version(
    root: Path,
    host: str | None,
    channel: str,
) -> CheckResult:
    name = "Marketplace plugin version alignment"
    if channel != CHANNEL_MARKETPLACE:
        return CheckResult(
            name=name,
            status=PASS,
            message=(
                f"Install channel is {channel}; marketplace version alignment is "
                "not applicable."
            ),
        )

    version = read_skill_metadata_version(root)
    if version is None:
        return CheckResult(
            name=name,
            status=WARN,
            message=(
                "Could not read metadata.version from the installed SKILL.md, so the "
                "active plugin version cannot be compared."
            ),
            fix=update_recipe(host, channel),
        )

    return CheckResult(
        name=name,
        status=PASS,
        message=(
            f"Installed SKILL.md metadata.version is {version}. Confirm the active "
            "plugin version your host reports (for example /plugin in Claude Code) "
            "matches before debugging stale-behavior reports; marketplace "
            "auto-update can lag until the session reloads."
        ),
    )


def git_remote_urls(root: Path) -> list[str]:
    config = root / ".git" / "config"
    if not config.is_file():
        return []
    return re.findall(r"url\s*=\s*(\S+)", config.read_text(encoding="utf-8"))


def git_head_ref(root: Path) -> str | None:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return None
    return head.read_text(encoding="utf-8").strip()


def check_pi_install_pinning(root: Path, host: str | None, channel: str) -> CheckResult:
    name = "Pi install pinning"
    if host != "pi":
        return CheckResult(
            name=name,
            status=PASS,
            message=(
                "Host profile is not pi; the unpinned-ref check only applies to Pi "
                "git installs (run with --host pi to force it)."
            ),
        )
    if channel != CHANNEL_GIT:
        return CheckResult(
            name=name,
            status=PASS,
            message=(
                f"Install channel is {channel}, not a git checkout; the "
                "unpinned-ref check is not applicable."
            ),
        )

    head = git_head_ref(root)
    if head is None:
        return CheckResult(
            name=name,
            status=WARN,
            message="Could not read .git/HEAD to determine whether the Pi install is pinned.",
            fix=(
                "Reinstall from a readable git checkout, or pin a tag or commit "
                "before pi install."
            ),
        )

    if head.startswith("ref: refs/heads/"):
        branch = head.removeprefix("ref: refs/heads/")
        return CheckResult(
            name=name,
            status=WARN,
            message=(
                f"Pi install tracks the unpinned git branch {branch!r}; "
                "pi update --extensions moves it to whatever that branch points at, "
                "which can change behavior between sessions."
            ),
            fix=(
                "Pin for reproducibility: check out a release tag or commit in the "
                "package checkout before pi install, or review upstream changes "
                "before running pi update --extensions."
            ),
        )

    return CheckResult(
        name=name,
        status=PASS,
        message="Pi install is pinned to a fixed git ref (detached tag or commit).",
    )


def check_cowork_mirror(root: Path, host: str | None, channel: str) -> CheckResult:
    name = "Cowork organization mirror"
    mirror_fix = (
        "Mirror the public repository into a private or internal repository owned "
        "by your organization, add it via Organization settings -> Plugins -> Add "
        "plugin -> GitHub, enable Sync automatically, and install Diagram Design "
        "from the resulting organization marketplace (README: Install -> Claude "
        "Cowork)."
    )
    if host != "cowork":
        return CheckResult(
            name=name,
            status=PASS,
            message=(
                "Host profile is not cowork; the organization-mirror check only "
                "applies to Cowork (run with --host cowork to force it)."
            ),
        )

    if resolve_skill_file(root) is None:
        return CheckResult(
            name=name,
            status=FAIL,
            message=(
                "Cowork could not resolve the installed skill (no SKILL.md under "
                "the installation root). Cowork organization marketplaces require "
                "a private or internal mirror of this public repository; without "
                "one, skill resolution fails after install."
            ),
            fix=mirror_fix,
        )

    public_remotes = [url for url in git_remote_urls(root) if PUBLIC_REPO_SLUG in url]
    if public_remotes:
        return CheckResult(
            name=name,
            status=WARN,
            message=(
                "This Cowork install points directly at the public repository "
                f"({public_remotes[0]}). Organization marketplaces require a "
                "private or internal mirror, so updates will not sync through "
                "Cowork from this remote."
            ),
            fix=mirror_fix,
        )

    return CheckResult(
        name=name,
        status=PASS,
        message=(
            "Skill resolves under Cowork and the install does not point directly "
            "at the public repository."
        ),
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


def check_common_path_mistakes(
    root: Path,
    cwd: Path,
    host: str | None = None,
    channel: str | None = None,
) -> CheckResult:
    warnings: list[str] = []
    fixes: list[str] = []

    if resolve_skill_file(root) is None:
        warnings.append(
            "Diagram Design SKILL.md was not found under the resolved installation root."
        )
        skill_fix = "Reinstall or update Diagram Design, then run the doctor again."
        if channel is not None:
            skill_fix += " " + update_recipe(host, channel)
        fixes.append(skill_fix)

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


def print_report(
    checks: list[CheckResult],
    strict: bool,
    emit_json: bool,
    host: str | None = None,
    channel: str | None = None,
) -> int:
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
            "host": host or "unknown",
            "install_channel": channel or "unknown",
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


def run_doctor(
    root: Path,
    cwd: Path,
    strict: bool,
    emit_json: bool,
    host_arg: str = AUTO_HOST,
) -> int:
    if host_arg == AUTO_HOST:
        host, host_evidence = detect_host(root)
    else:
        host, host_evidence = host_arg, "selected via --host"
    channel, channel_evidence = detect_install_channel(root)

    checks: list[CheckResult] = []

    python_check, python_cmd = check_python_runtime()
    checks.append(python_check)
    checks.append(check_playwright(python_cmd, host, channel))
    checks.append(check_host_install_channel(host, host_evidence, channel, channel_evidence))
    checks.append(check_expected_scripts(root))
    checks.append(check_routing_surfaces(root))
    checks.append(check_marketplace_version(root, host, channel))
    checks.append(check_pi_install_pinning(root, host, channel))
    checks.append(check_cowork_mirror(root, host, channel))
    checks.append(check_common_path_mistakes(root, cwd, host, channel))

    return print_report(checks, strict, emit_json, host, channel)


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
    parser.add_argument(
        "--host",
        choices=(AUTO_HOST, *HOST_PROFILES),
        default=AUTO_HOST,
        help=(
            "Host profile to diagnose against (default: auto-detect from "
            "environment markers and installation path)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    root = ROOT
    cwd = Path.cwd()
    return run_doctor(root, cwd, args.strict, args.json, args.host)


if __name__ == "__main__":
    raise SystemExit(main())
