#!/usr/bin/env python3
"""Increment the synchronized Claude, Codex, and Factory manifest versions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATHS = (
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
    Path(".factory-plugin/plugin.json"),
)
SKILL_PATH = Path("skills/diagram-design/SKILL.md")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class PackageVersionError(ValueError):
    """Raised when the package versions cannot be bumped safely."""


def read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageVersionError(f"could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PackageVersionError(f"{path} must contain a JSON object")
    return payload


def parse_version(value: object, label: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or (match := SEMVER.fullmatch(value)) is None:
        raise PackageVersionError(
            f"{label} version must be strict MAJOR.MINOR.PATCH semver; got {value!r}"
        )
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def bump(root: Path, part: str = "patch") -> str:
    manifests = [(relative, read_manifest(root / relative)) for relative in MANIFEST_PATHS]
    raw_versions = [payload.get("version") for _, payload in manifests]
    if any(version != raw_versions[0] for version in raw_versions[1:]):
        rendered = ", ".join(
            f"{relative}={version!r}"
            for (relative, _), version in zip(manifests, raw_versions)
        )
        raise PackageVersionError(f"manifest versions are not synchronized: {rendered}")

    major, minor, patch = parse_version(raw_versions[0], str(MANIFEST_PATHS[0]))
    if part == "major":
        next_version = (major + 1, 0, 0)
    elif part == "minor":
        next_version = (major, minor + 1, 0)
    elif part == "patch":
        next_version = (major, minor, patch + 1)
    else:
        raise PackageVersionError(f"unsupported version part: {part}")

    version = ".".join(str(value) for value in next_version)
    rendered_manifests: list[tuple[Path, str]] = []
    for relative, payload in manifests:
        payload["version"] = version
        rendered_manifests.append(
            (root / relative, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        )
    skill_path, skill_contents = render_skill_metadata_version(root, version)
    for path, contents in rendered_manifests:
        path.write_text(contents, encoding="utf-8")
    skill_path.write_text(skill_contents, encoding="utf-8")
    return version


def render_skill_metadata_version(root: Path, version: str) -> tuple[Path, str]:
    """Keep SKILL.md's hand-maintained metadata.version on the manifest MAJOR.MINOR.

    The package verifier fails when the two drift, so the bump must update both
    sides in one step. Returns the pending write (rendered before any manifest
    is written, so a malformed SKILL.md aborts the whole bump); raises when the
    frontmatter does not carry exactly one metadata.version to rewrite.
    """
    path = root / SKILL_PATH
    if not path.is_file():
        raise PackageVersionError(f"missing {SKILL_PATH}")
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise PackageVersionError(f"{SKILL_PATH} has no YAML frontmatter")
    closing = next(
        (index for index in range(1, len(lines)) if lines[index].strip() == "---"), None
    )
    if closing is None:
        raise PackageVersionError(f"{SKILL_PATH} frontmatter is unterminated")

    major_minor = ".".join(version.split(".")[:2])
    in_metadata = False
    replaced = 0
    for index in range(1, closing):
        line = lines[index]
        if re.fullmatch(r"metadata:\s*(?:#.*)?", line.rstrip("\n")):
            in_metadata = True
            continue
        if in_metadata and line.strip() and not line[0].isspace():
            in_metadata = False
        if not in_metadata:
            continue
        match = re.fullmatch(
            r'(?P<head>\s+version:\s*)"[0-9][0-9.]*"(?P<tail>\s*(?:#.*)?)',
            line.rstrip("\n"),
        )
        if match is not None:
            lines[index] = f'{match.group("head")}"{major_minor}"{match.group("tail")}\n'
            replaced += 1
    if replaced != 1:
        raise PackageVersionError(
            f"{SKILL_PATH} frontmatter must contain exactly one quoted "
            f"metadata.version; found {replaced}"
        )
    return path, "".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Increment all plugin manifests (patch by default)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--major", action="store_true", help="increment the major version")
    group.add_argument("--minor", action="store_true", help="increment the minor version")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    part = "major" if args.major else "minor" if args.minor else "patch"
    try:
        version = bump(ROOT, part)
    except PackageVersionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Updated Claude, Codex, and Factory plugin manifests to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
