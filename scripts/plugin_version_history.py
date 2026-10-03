#!/usr/bin/env python3
"""Inspect synchronized plugin-version changes across git history."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATHS = (
    Path(".claude-plugin/plugin.json"),
    Path(".codex-plugin/plugin.json"),
    Path(".factory-plugin/plugin.json"),
)
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class VersionHistoryError(ValueError):
    """Raised when version history cannot be inspected safely."""


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise VersionHistoryError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def versions_at(root: Path, ref: str) -> Tuple[str, ...]:
    versions = []
    for relative in MANIFEST_PATHS:
        raw = git(root, "show", f"{ref}:{relative.as_posix()}")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VersionHistoryError(
                f"{relative} at {ref} is not valid JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise VersionHistoryError(f"{relative} at {ref} must contain an object")
        version = payload.get("version")
        if not isinstance(version, str) or SEMVER.fullmatch(version) is None:
            raise VersionHistoryError(
                f"{relative} at {ref} has an invalid version: {version!r}"
            )
        versions.append(version)
    if len(set(versions)) != 1:
        rendered = ", ".join(
            f"{path}={version}" for path, version in zip(MANIFEST_PATHS, versions)
        )
        raise VersionHistoryError(
            f"manifest versions at {ref} are not synchronized: {rendered}"
        )
    return tuple(versions)


def versions_changed(root: Path, before: str, after: str) -> bool:
    return versions_at(root, before) != versions_at(root, after)


def first_parent(root: Path, commit: str) -> str | None:
    fields = git(root, "rev-list", "--parents", "-n", "1", commit).split()
    return fields[1] if len(fields) > 1 else None


def last_version_bump(root: Path, source: str) -> str:
    commits = git(
        root,
        "rev-list",
        "--first-parent",
        source,
        "--",
        *(path.as_posix() for path in MANIFEST_PATHS),
    ).splitlines()
    for commit in commits:
        parent = first_parent(root, commit)
        if parent is not None and versions_changed(root, parent, commit):
            return commit
    raise VersionHistoryError(
        f"no synchronized plugin version bump found at {source}"
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    changed = subparsers.add_parser(
        "changed", help="print whether synchronized versions differ between two refs"
    )
    changed.add_argument("before")
    changed.add_argument("after")
    last = subparsers.add_parser(
        "last-bump", help="print the newest first-parent commit with a version change"
    )
    last.add_argument("source")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "changed":
            changed = versions_changed(ROOT, args.before, args.after)
            print("true" if changed else "false")
        else:
            print(last_version_bump(ROOT, args.source))
    except VersionHistoryError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
