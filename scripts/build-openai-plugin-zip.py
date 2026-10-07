#!/usr/bin/env python3
"""Build the ZIP uploaded to OpenAI's plugin directory (ChatGPT and Codex).

The directory accepts a ZIP of the Codex-format plugin: `.codex-plugin/
plugin.json`, the `skills/` it points at, and the listing assets the manifest
names. This builder packages exactly those files as they are staged in the git
index, so the upload matches what the Git marketplace ships, and never includes
repository tooling, docs, or other hosts' manifests. The MIT LICENSE (required),
THIRD_PARTY_LICENSES.md, and PRIVACY.md travel with it.

It also enforces the submission form's listing limits so a manifest edit that
would be rejected at upload fails here first.

Usage:
  python3 scripts/build-openai-plugin-zip.py --check   # limits and asset paths only
  python3 scripts/build-openai-plugin-zip.py           # dist/<name>-<version>-openai.zip
  python3 scripts/build-openai-plugin-zip.py --draft   # allow missing logo/icon (private testing)

For a given Python and zlib the ZIP is byte-reproducible: entries are sorted,
timestamps and host metadata fixed, and contents read from git blobs rather
than the working tree.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import stat
import struct
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ".codex-plugin/plugin.json"

# Listing limits from the OpenAI plugin submission form.
TEXT_LIMITS = {
    "displayName": 30,
    "shortDescription": 30,
    "longDescription": 4000,
    "developerName": 80,
}
MAX_CAPABILITIES = 20
REQUIRED_TEXT = ("displayName", "shortDescription", "developerName", "category")

# Interface fields that name package files. Logo and composer icon are required
# to submit; screenshots are optional.
REQUIRED_ASSETS = ("logo", "composerIcon")
OPTIONAL_ASSETS = ("screenshots",)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
MAX_ASSET_BYTES = 5 * 1024 * 1024
MIN_LOGO_PX = 48

REQUIRED_FILES = ("LICENSE",)
OPTIONAL_FILES = ("THIRD_PARTY_LICENSES.md", "PRIVACY.md")
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
UNIX_HOST = 3
SAFE_FILENAME_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z")
# The upload reads package identity from a root plugin.json in the Agent Plugins
# format, with OpenAI's listing fields under extensions["com.openai"]. That
# schema rejects unknown top-level keys, so only these fields are copied.
AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
AGENT_PLUGINS_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\Z")
ROOT_MANIFEST_FIELDS = ("name", "version", "description", "author", "homepage", "repository", "license", "keywords")
FILE_ATTRS = (stat.S_IFREG | 0o644) << 16
DIR_ATTRS = (stat.S_IFDIR | 0o755) << 16 | 0x10  # 0x10 is the MS-DOS directory flag


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    # Manifest-supplied paths are pathspecs; never let git glob them.
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(root), *args],
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"build-openai-plugin-zip: git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def index_entries(root: Path, pathspecs: list[str], errors: list[str]) -> dict[str, str]:
    """Map each staged path under *pathspecs* to its blob id in the index."""
    raw = git(root, "ls-files", "-s", "-z", "--", *pathspecs)
    entries: dict[str, str] = {}
    unmerged: set[str] = set()
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, path_bytes = record.split(b"\t", 1)
        mode, blob, stage = meta.split()
        path = path_bytes.decode("utf-8")
        if stage != b"0":
            unmerged.add(path)
            continue
        if mode == b"160000":  # submodule, not a file
            continue
        if mode == b"120000":  # a symlink's blob is its target path, not content
            errors.append(f"{path} is a symlink; commit the file itself")
            continue
        entries[path] = blob.decode("ascii")
    for path in sorted(unmerged):
        errors.append(f"{path} has an unresolved merge conflict in the index")
    # `git add -N` records a path without content; it would ship as an empty file.
    pending = git(root, "diff", "--name-only", "-z", "--diff-filter=A", "--", *pathspecs)
    for path_bytes in pending.split(b"\0"):
        if path_bytes:
            path = path_bytes.decode("utf-8")
            entries.pop(path, None)
            errors.append(f"{path} is intent-to-add with no staged content; stage it or remove it")
    return entries


def read_blobs(root: Path, blobs: list[str]) -> list[bytes]:
    """Read blob contents in one `git cat-file --batch` round-trip."""
    if not blobs:
        return []
    stream = io.BytesIO(git(root, "cat-file", "--batch", data="\n".join(blobs).encode() + b"\n"))
    contents = []
    for blob in blobs:
        header = stream.readline().split()
        if len(header) != 3 or header[0].decode() != blob:
            raise SystemExit(f"build-openai-plugin-zip: could not read blob {blob}")
        size = int(header[2])
        contents.append(stream.read(size))
        stream.read(1)  # trailing newline
    return contents


def package_path(value: object, label: str, errors: list[str]) -> str | None:
    """Validate a manifest path and return it relative to the plugin root."""
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a non-empty path")
        return None
    if not value.startswith("./"):
        errors.append(f"{label} must start with ./ (got {value!r})")
        return None
    rest = value[2:]
    relative = PurePosixPath(rest)
    if rest.startswith("/") or relative.is_absolute() or ".." in relative.parts:
        errors.append(f"{label} must stay inside the plugin (got {value!r})")
        return None
    if not relative.parts:
        return "."
    return relative.as_posix()


def png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def check_listing(interface: dict, errors: list[str]) -> None:
    for field in REQUIRED_TEXT:
        if not isinstance(interface.get(field), str) or not interface[field].strip():
            errors.append(f"interface.{field} is required")
    for field, limit in TEXT_LIMITS.items():
        value = interface.get(field)
        if isinstance(value, str) and len(value) > limit:
            errors.append(
                f"interface.{field} is {len(value)} characters; the directory allows {limit}"
            )
    capabilities = interface.get("capabilities", [])
    if not isinstance(capabilities, list):
        errors.append("interface.capabilities must be a list")
    elif len(capabilities) > MAX_CAPABILITIES:
        errors.append(
            f"interface.capabilities has {len(capabilities)} labels; "
            f"the directory allows {MAX_CAPABILITIES}"
        )


def declared_assets(interface: dict, errors: list[str], pending: list[str]) -> list[tuple[str, str]]:
    """Return (label, relative path) for every asset the interface names."""
    paths: list[tuple[str, str]] = []
    for field in REQUIRED_ASSETS:
        if field not in interface:
            pending.append(field)
            continue
        relative = package_path(interface[field], f"interface.{field}", errors)
        if relative:
            paths.append((field, relative))
    for field in OPTIONAL_ASSETS:
        values = interface.get(field, [])
        if not isinstance(values, list):
            errors.append(f"interface.{field} must be a list of paths")
            continue
        for i, value in enumerate(values):
            relative = package_path(value, f"interface.{field}[{i}]", errors)
            if relative:
                paths.append((f"{field}[{i}]", relative))
    return paths


def check_assets(
    root: Path, paths: list[tuple[str, str]], tracked: dict[str, str], errors: list[str]
) -> list[str]:
    assets = []
    for label, relative in paths:
        if PurePosixPath(relative).suffix.lower() not in IMAGE_SUFFIXES:
            errors.append(f"interface.{label} must be PNG, JPEG, WebP, or SVG (got {relative})")
            continue
        if relative not in tracked:
            state = "exists but is not tracked by git" if (root / relative).is_file() else "does not exist"
            errors.append(f"interface.{label} file {relative} {state}")
            continue
        data = read_blobs(root, [tracked[relative]])[0]
        if len(data) > MAX_ASSET_BYTES:
            errors.append(f"interface.{label} file {relative} is larger than 5 MiB")
        if label in REQUIRED_ASSETS and relative.lower().endswith(".png"):
            size = png_size(data)
            if size is None:
                errors.append(f"interface.{label} file {relative} is not a valid PNG")
            elif min(size) < MIN_LOGO_PX:
                errors.append(
                    f"interface.{label} file {relative} is {size[0]}x{size[1]}px; "
                    f"the directory needs at least {MIN_LOGO_PX}x{MIN_LOGO_PX}"
                )
        assets.append(relative)
    return assets


def root_manifest(manifest: dict) -> bytes:
    """The Agent Plugins plugin.json for the upload, derived from the Codex manifest."""
    root = {"$schema": AGENT_PLUGINS_SCHEMA}
    root.update({field: manifest[field] for field in ROOT_MANIFEST_FIELDS if field in manifest})
    root["extensions"] = {"com.openai": {"interface": manifest["interface"]}}
    return (json.dumps(root, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def fail(errors: list[str]) -> int:
    print(f"build-openai-plugin-zip: {len(errors)} problem(s):", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="plugin repository root")
    parser.add_argument("--out", type=Path, help="output directory (default: <root>/dist)")
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    parser.add_argument(
        "--draft",
        action="store_true",
        help="build even if the logo or composer icon is missing (private testing only)",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    pending: list[str] = []
    manifest_entry = index_entries(root, [MANIFEST], errors)
    if MANIFEST not in manifest_entry:
        return fail(errors + [f"{MANIFEST} is not staged under {root}"])
    manifest = json.loads(read_blobs(root, [manifest_entry[MANIFEST]])[0].decode("utf-8"))
    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        return fail(errors + ["manifest has no interface block"])

    for field in ("name", "version"):
        value = manifest.get(field)
        if not isinstance(value, str) or not SAFE_FILENAME_PART.match(value):
            errors.append(f"manifest {field} {value!r} is not a safe filename part")

    if isinstance(manifest.get("name"), str) and not AGENT_PLUGINS_NAME.match(manifest["name"]):
        errors.append(f"manifest name {manifest['name']!r} does not match the Agent Plugins name pattern")
    check_listing(interface, errors)
    asset_paths = declared_assets(interface, errors, pending)

    skills_dir = None
    if "skills" not in manifest:
        errors.append("manifest skills is required; a plugin without skills ships nothing")
    else:
        skills_dir = package_path(manifest["skills"], "manifest skills", errors)
        if skills_dir == ".":
            errors.append("manifest skills must name a directory, not the repository root")
            skills_dir = None

    pathspecs = [MANIFEST, *REQUIRED_FILES, *OPTIONAL_FILES, *(path for _, path in asset_paths)]
    if skills_dir:
        pathspecs.append(skills_dir)
    tracked = index_entries(root, pathspecs, errors)
    assets = check_assets(root, asset_paths, tracked, errors)

    skill_files: list[str] = []
    if skills_dir:
        prefix = skills_dir.rstrip("/") + "/"
        skill_files = sorted(p for p in tracked if p.startswith(prefix) and p != MANIFEST)
        if not any(p == "SKILL.md" or p.endswith("/SKILL.md") for p in skill_files):
            errors.append(f"no staged SKILL.md under {skills_dir}")
    for name in REQUIRED_FILES:
        if name not in tracked:
            errors.append(f"{name} must be tracked; the MIT notice ships with every copy")

    if errors:
        return fail(errors)

    if args.check:
        note = f"; pending before submission: {', '.join(pending)}" if pending else ""
        print(f"OK OpenAI plugin listing: limits and asset paths valid{note}")
        return 0

    if pending and not args.draft:
        print(
            "build-openai-plugin-zip: the directory requires "
            + ", ".join(f"interface.{field}" for field in pending)
            + " to submit; add the asset(s) or pass --draft for a private test build",
            file=sys.stderr,
        )
        return 1

    files = sorted(
        {MANIFEST, *skill_files, *assets, *REQUIRED_FILES}
        | {name for name in OPTIONAL_FILES if name in tracked}
    )
    contents = read_blobs(root, [tracked[name] for name in files])
    out_dir = (args.out or root / "dist").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{manifest['name']}-{manifest['version']}-openai.zip"
    payload = dict(zip(files, contents))
    payload["plugin.json"] = root_manifest(manifest)
    directories = {
        "/".join(path.split("/")[:depth]) + "/"
        for path in payload
        for depth in range(1, path.count("/") + 1)
    }
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(payload) | directories):
            info = zipfile.ZipInfo(path, date_time=FIXED_TIME)
            info.create_system = UNIX_HOST
            if path in directories:
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = DIR_ATTRS
                archive.writestr(info, b"")
            else:
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = FILE_ATTRS
                archive.writestr(info, payload[path])
    kind = "draft " if pending else ""
    print(f"OK built {kind}{target} ({len(payload)} files, {target.stat().st_size:,} bytes)")
    if pending:
        print(f"Draft only: missing {', '.join(pending)}; do not submit this ZIP.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
