#!/usr/bin/env python3
"""Adversarial tests for scripts/build-openai-plugin-zip.py.

The builder packages the Codex-format plugin for OpenAI's plugin directory
upload. These cases pin what goes into the ZIP (the manifest, the shared skill,
licenses, and declared listing assets, read from the git index), what stays
out (repository tooling, docs, other hosts' manifests, untracked files), the
directory's listing limits, and asset path safety. Fixture repositories are
throwaway git checkouts, so the cases do not depend on this repository's
current assets.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "scripts" / "build-openai-plugin-zip.py"

ALLOWED_PREFIXES = (
    "plugin.json",
    ".codex-plugin/",
    "skills/",
    "assets/",
    "LICENSE",
    "THIRD_PARTY_LICENSES.md",
    "PRIVACY.md",
)
FORBIDDEN_PREFIXES = (
    "scripts/",
    "docs/",
    ".github/",
    "commands/",
    "prompts/",
    ".claude-plugin/",
    ".factory-plugin/",
    ".agents/",
)


def png(width: int, height: int) -> bytes:
    """A minimal valid grayscale PNG of the given size."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    rows = b"".join(b"\x00" + b"\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def interface(**overrides: object) -> dict:
    base = {
        "displayName": "Demo",
        "shortDescription": "Demo diagrams",
        "longDescription": "Demo plugin used by the builder tests.",
        "developerName": "Test Author",
        "category": "Productivity",
        "capabilities": ["Read", "Write"],
        "logo": "./assets/logo.png",
        "composerIcon": "./assets/icon.svg",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


def fixture(
    tmp: Path,
    name: str,
    iface: dict,
    *,
    logo: bytes | None = None,
    icon: bool = True,
    license_file: bool = True,
    track_logo: bool = True,
    extra: dict[str, bytes] | None = None,
    intent_to_add: tuple[str, ...] = (),
    manifest_overrides: dict | None = None,
    edit_after_add: dict[str, bytes] | None = None,
    symlinks: dict[str, str] | None = None,
) -> Path:
    root = tmp / name
    (root / ".codex-plugin").mkdir(parents=True)
    manifest = {
        "name": "demo",
        "version": "1.2.3",
        "description": "Demo plugin.",
        "skills": "./skills/",
        "interface": iface,
    }
    for key, value in (manifest_overrides or {}).items():
        if value is None:
            manifest.pop(key, None)
        else:
            manifest[key] = value
    (root / ".codex-plugin/plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    skill = root / "skills/demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\ndescription: Demo.\n---\n\nDemo.\n")
    (skill / "__pycache__").mkdir()
    (skill / "__pycache__/junk.pyc").write_bytes(b"\x00junk")
    (root / "scripts").mkdir()
    (root / "scripts/tool.py").write_text("print('repo tooling')\n")
    tracked = [".codex-plugin/plugin.json", "skills/demo/SKILL.md", "scripts/tool.py"]
    if license_file:
        (root / "LICENSE").write_text("MIT\n")
        tracked.append("LICENSE")
    (root / "assets").mkdir()
    if logo is not None:
        (root / "assets/logo.png").write_bytes(logo)
        if track_logo:
            tracked.append("assets/logo.png")
    if icon:
        (root / "assets/icon.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"/>\n'
        )
        tracked.append("assets/icon.svg")
    for relative, data in (extra or {}).items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)
        tracked.append(relative)
    for relative, target in (symlinks or {}).items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, root / relative)
        tracked.append(relative)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", *tracked], cwd=root, check=True)
    for relative in intent_to_add:
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text("not staged yet\n")
        subprocess.run(["git", "add", "-N", "--", relative], cwd=root, check=True)
    for relative, data in (edit_after_add or {}).items():
        (root / relative).write_bytes(data)
    return root


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(BUILDER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def built_zip(out: Path) -> Path:
    zips = sorted(out.glob("*.zip"))
    if len(zips) != 1:
        raise AssertionError(f"expected one ZIP in {out}, found {[z.name for z in zips]}")
    return zips[0]


AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
ROOT_KEYS = {"$schema", "name", "version", "description", "author", "homepage", "repository", "license", "keywords", "extensions"}
NAME_RE = r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z"


def zip_structure_problems(path: Path) -> list[str]:
    """Upload-format problems: root manifest shape, entry types, directory entries."""
    import re
    import stat

    problems = []
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    if "plugin.json" not in names:
        return ["no root plugin.json"]
    root = json.loads(archive.read("plugin.json"))
    codex = json.loads(archive.read(".codex-plugin/plugin.json"))
    if root.get("$schema") != AGENT_PLUGINS_SCHEMA:
        problems.append("root $schema is not the Agent Plugins 1.0.0 schema")
    extra = set(root) - ROOT_KEYS
    if extra:
        problems.append(f"root plugin.json has keys the schema rejects: {sorted(extra)}")
    if not re.match(NAME_RE, root.get("name", "")):
        problems.append("root name does not match the schema pattern")
    for key in ("name", "version", "description", "author"):
        if root.get(key) != codex.get(key):
            problems.append(f"root {key} differs from the Codex manifest")
    if root.get("extensions", {}).get("com.openai", {}).get("interface") != codex.get("interface"):
        problems.append("root extensions.com.openai.interface differs from the Codex interface")
    entries = set(names)
    for info in archive.infolist():
        mode = info.external_attr >> 16
        if info.is_dir():
            if not stat.S_ISDIR(mode):
                problems.append(f"{info.filename} lacks the directory type bit")
        elif not stat.S_ISREG(mode):
            problems.append(f"{info.filename} lacks the regular-file type bit")
        parts = info.filename.rstrip("/").split("/")[:-1]
        for depth in range(1, len(parts) + 1):
            parent = "/".join(parts[:depth]) + "/"
            if parent not in entries:
                problems.append(f"missing directory entry {parent}")
    return sorted(set(problems))


def main() -> int:
    failures: list[str] = []
    passed = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal passed
        if condition:
            passed += 1
        else:
            failures.append(f"{label}{': ' + detail if detail else ''}")

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        # This repository's manifest stays within the directory's listing limits.
        result = run("--root", str(ROOT), "--check")
        check("repo --check passes", result.returncode == 0, result.stdout + result.stderr)

        # A draft build of this repository ships only the plugin surface.
        out_a, out_b = tmp / "repo-a", tmp / "repo-b"
        first = run("--root", str(ROOT), "--draft", "--out", str(out_a))
        second = run("--root", str(ROOT), "--draft", "--out", str(out_b))
        check("repo draft build succeeds", first.returncode == 0, first.stdout + first.stderr)
        check("repo second draft build succeeds", second.returncode == 0, second.stdout + second.stderr)
        if first.returncode == 0 and second.returncode == 0:
            zip_a, zip_b = built_zip(out_a), built_zip(out_b)
            names = zipfile.ZipFile(zip_a).namelist()
            problems = zip_structure_problems(zip_a)
            check("repo ZIP matches the upload format", not problems, "; ".join(problems[:5]))
            for required in (
                "plugin.json",
                ".codex-plugin/plugin.json",
                "skills/diagram-design/SKILL.md",
                "LICENSE",
                "THIRD_PARTY_LICENSES.md",
                "PRIVACY.md",
            ):
                check(f"repo ZIP contains {required}", required in names)
            repo_interface = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())["interface"]
            declared = {
                value[2:]
                for key in ("logo", "composerIcon")
                for value in [repo_interface.get(key)]
                if isinstance(value, str)
            } | {value[2:] for value in repo_interface.get("screenshots", []) if isinstance(value, str)}
            stray = [n for n in names if not n.startswith(ALLOWED_PREFIXES) and n not in declared]
            check("repo ZIP has only plugin-surface entries", not stray, ", ".join(stray[:5]))
            forbidden = [n for n in names if n.startswith(FORBIDDEN_PREFIXES)]
            check("repo ZIP excludes repository tooling", not forbidden, ", ".join(forbidden[:5]))
            check(
                "repo ZIP excludes caches",
                not any("__pycache__" in n or n.endswith(".pyc") for n in names),
            )
            check(
                "repo ZIP is byte-reproducible",
                hashlib.sha256(zip_a.read_bytes()).digest()
                == hashlib.sha256(zip_b.read_bytes()).digest(),
            )
            index_manifest = subprocess.run(
                ["git", "show", ":.codex-plugin/plugin.json"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            check(
                "repo ZIP manifest matches the git index",
                zipfile.ZipFile(zip_a).read(".codex-plugin/plugin.json") == index_manifest,
            )

        # A complete fixture builds for submission and carries its assets.
        good = fixture(tmp, "good", interface(), logo=png(64, 64))
        out = tmp / "good-out"
        result = run("--root", str(good), "--out", str(out))
        check("complete fixture builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            names = zipfile.ZipFile(built_zip(out)).namelist()
            problems = zip_structure_problems(built_zip(out))
            check("fixture ZIP matches the upload format", not problems, "; ".join(problems[:5]))
            check("fixture ZIP has logo", "assets/logo.png" in names)
            check("fixture ZIP has composer icon", "assets/icon.svg" in names)
            check("fixture ZIP excludes untracked cache", not any("__pycache__" in n for n in names))
            check("fixture ZIP excludes repo scripts", "scripts/tool.py" not in names)
            check("fixture ZIP is named for its version", built_zip(out).name == "demo-1.2.3-openai.zip")

        # Submission builds refuse a missing required asset; drafts allow it.
        no_logo = fixture(tmp, "no-logo", interface(logo=None), logo=None)
        result = run("--root", str(no_logo), "--out", str(tmp / "no-logo-out"))
        check(
            "missing logo blocks a submission build",
            result.returncode == 1 and "logo" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )
        result = run("--root", str(no_logo), "--draft", "--out", str(tmp / "no-logo-draft"))
        check("missing logo allowed in a draft", result.returncode == 0, result.stdout + result.stderr)
        result = run("--root", str(no_logo), "--check")
        check("missing logo is pending, not an error, for --check", result.returncode == 0, result.stdout + result.stderr)

        # Listing limits from the submission form.
        limit_cases = {
            "displayName": "x" * 31,
            "shortDescription": "x" * 31,
            "longDescription": "x" * 4001,
            "developerName": "x" * 81,
            "capabilities": [f"Cap{i}" for i in range(21)],
        }
        for field, value in limit_cases.items():
            root = fixture(tmp, f"limit-{field}", interface(**{field: value}), logo=png(64, 64))
            result = run("--root", str(root), "--check")
            check(
                f"{field} over the limit fails",
                result.returncode == 1 and field in (result.stdout + result.stderr),
                result.stdout + result.stderr,
            )
        root = fixture(tmp, "at-limit", interface(displayName="x" * 30, shortDescription="y" * 30), logo=png(64, 64))
        result = run("--root", str(root), "--check")
        check("30-character names pass", result.returncode == 0, result.stdout + result.stderr)

        # Asset paths must stay inside the package and be tracked.
        path_cases = {
            "escape": "./../logo.png",
            "no-dot-slash": "assets/logo.png",
            "absolute": "/etc/passwd",
            "dot-slash-absolute": ".//etc/passwd",
            "nested-escape": "./assets/../../x.png",
        }
        for label, value in path_cases.items():
            root = fixture(tmp, f"path-{label}", interface(logo=value), logo=png(64, 64))
            result = run("--root", str(root), "--check")
            check(f"logo path {label} fails", result.returncode == 1, result.stdout + result.stderr)
        root = fixture(tmp, "untracked-logo", interface(), logo=png(64, 64), track_logo=False)
        result = run("--root", str(root), "--check")
        check(
            "untracked logo fails",
            result.returncode == 1 and "not tracked" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )
        root = fixture(tmp, "small-logo", interface(), logo=png(32, 32))
        result = run("--root", str(root), "--check")
        check("logo under 48px fails", result.returncode == 1, result.stdout + result.stderr)
        root = fixture(tmp, "bad-ext", interface(logo="./assets/logo.gif"), logo=png(64, 64))
        result = run("--root", str(root), "--check")
        check("unsupported logo format fails", result.returncode == 1, result.stdout + result.stderr)

        # Assets may live anywhere inside the package, not only assets/.
        root = fixture(
            tmp,
            "brand-dir",
            interface(logo="./brand/logo.png"),
            extra={"brand/logo.png": png(64, 64)},
        )
        out = tmp / "brand-dir-out"
        result = run("--root", str(root), "--out", str(out))
        check("logo outside assets/ builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check("logo outside assets/ ships", "brand/logo.png" in zipfile.ZipFile(built_zip(out)).namelist())

        # Screenshots are optional, but each one is checked like the logo.
        root = fixture(
            tmp,
            "screens",
            interface(screenshots=["./assets/shot.png"]),
            logo=png(64, 64),
            extra={"assets/shot.png": png(640, 400)},
        )
        out = tmp / "screens-out"
        result = run("--root", str(root), "--out", str(out))
        check("screenshots build", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check("screenshot ships", "assets/shot.png" in zipfile.ZipFile(built_zip(out)).namelist())
        root = fixture(tmp, "screens-escape", interface(screenshots=["./../shot.png"]), logo=png(64, 64))
        result = run("--root", str(root), "--check")
        check("screenshot escape fails", result.returncode == 1, result.stdout + result.stderr)
        root = fixture(tmp, "screens-type", interface(screenshots="./assets/shot.png"), logo=png(64, 64))
        result = run("--root", str(root), "--check")
        check("screenshots must be a list", result.returncode == 1, result.stdout + result.stderr)

        # The ZIP carries staged bytes, never the working tree.
        staged = b"---\nname: demo\ndescription: Demo.\n---\n\nDemo.\n"
        root = fixture(
            tmp,
            "dirty-tree",
            interface(),
            logo=png(64, 64),
            edit_after_add={"skills/demo/SKILL.md": b"unstaged edit\n"},
        )
        out = tmp / "dirty-tree-out"
        result = run("--root", str(root), "--out", str(out))
        check("dirty working tree builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check(
                "ZIP holds staged bytes, not the working tree",
                zipfile.ZipFile(built_zip(out)).read("skills/demo/SKILL.md") == staged,
            )

        # Paths with spaces and non-ASCII characters survive intact.
        odd = "skills/demo/my caf\u00e9 notes.md"
        root = fixture(tmp, "odd-path", interface(), logo=png(64, 64), extra={odd: b"notes\n"})
        out = tmp / "odd-path-out"
        result = run("--root", str(root), "--out", str(out))
        check("unusual path builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check("unusual path ships unchanged", odd in zipfile.ZipFile(built_zip(out)).namelist())

        # Intent-to-add files have no staged content; refuse rather than ship them empty.
        root = fixture(tmp, "ita", interface(), logo=png(64, 64), intent_to_add=("skills/demo/new.md",))
        result = run("--root", str(root), "--draft", "--out", str(tmp / "ita-out"))
        check(
            "intent-to-add file fails",
            result.returncode == 1 and "new.md" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        # The manifest name and version become a filename; keep it inside --out.
        root = fixture(tmp, "bad-name", interface(), logo=png(64, 64), manifest_overrides={"name": "../escaped"})
        out = tmp / "bad-name-out"
        result = run("--root", str(root), "--draft", "--out", str(out))
        check("unsafe manifest name fails", result.returncode == 1, result.stdout + result.stderr)
        check("unsafe manifest name writes nothing outside --out", not list(tmp.glob("escaped*")))

        # Names outside the Agent Plugins pattern never reach the root manifest or the filename.
        for label, bad_name in (("trailing-newline", "demo\n"), ("double-period", "a..b"), ("double-hyphen", "a--b"), ("uppercase", "Demo")):
            root = fixture(tmp, f"name-{label}", interface(), logo=png(64, 64), manifest_overrides={"name": bad_name})
            result = run("--root", str(root), "--check")
            check(f"manifest name {label} fails", result.returncode == 1, result.stdout + result.stderr)
        check("test name pattern rejects consecutive periods", re.match(NAME_RE, "a..b") is None)
        check("test name pattern rejects a trailing newline", re.match(NAME_RE, "demo\n") is None)

        # A manifest without a skills path would ship an empty plugin.
        root = fixture(tmp, "no-skills", interface(), logo=png(64, 64), manifest_overrides={"skills": None})
        result = run("--root", str(root), "--draft", "--out", str(tmp / "no-skills-out"))
        check("manifest without skills fails", result.returncode == 1, result.stdout + result.stderr)

        # The repository root is not a skills directory; it would ship everything.
        root = fixture(tmp, "root-skills", interface(), logo=png(64, 64), manifest_overrides={"skills": "./"})
        result = run("--root", str(root), "--check")
        check("skills at the repository root fails", result.returncode == 1, result.stdout + result.stderr)

        # A truncated PNG is reported, not a traceback.
        truncated = png(64, 64)[:20]
        root = fixture(tmp, "truncated-png", interface(), logo=truncated)
        result = run("--root", str(root), "--check")
        output = result.stdout + result.stderr
        check(
            "truncated PNG is reported cleanly",
            result.returncode == 1 and "Traceback" not in output and "logo" in output,
            output,
        )

        # Symlinks would ship as text files holding their target path.
        if hasattr(os, "symlink"):
            try:
                root = fixture(
                    tmp,
                    "symlink-skill",
                    interface(),
                    logo=png(64, 64),
                    symlinks={"skills/demo/linked.md": "SKILL.md"},
                )
                result = run("--root", str(root), "--draft", "--out", str(tmp / "symlink-skill-out"))
                check(
                    "symlinked skill file fails",
                    result.returncode == 1 and "symlink" in (result.stdout + result.stderr),
                    result.stdout + result.stderr,
                )
                root = fixture(
                    tmp,
                    "symlink-logo",
                    interface(logo="./assets/link.png"),
                    logo=png(64, 64),
                    symlinks={"assets/link.png": "logo.png"},
                )
                result = run("--root", str(root), "--check")
                check(
                    "symlinked logo fails",
                    result.returncode == 1 and "symlink" in (result.stdout + result.stderr),
                    result.stdout + result.stderr,
                )
            except OSError:
                pass  # symlinks unavailable on this platform

        # The MIT notice must travel with every copy.
        root = fixture(tmp, "no-license", interface(), logo=png(64, 64), license_file=False)
        result = run("--root", str(root), "--draft", "--out", str(tmp / "no-license-out"))
        check(
            "missing LICENSE fails",
            result.returncode == 1 and "LICENSE" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

    if failures:
        print(f"{len(failures)} OpenAI plugin ZIP case(s) failed ({passed} passed):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"All OpenAI plugin ZIP cases passed ({passed}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
