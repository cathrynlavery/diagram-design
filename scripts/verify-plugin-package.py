#!/usr/bin/env python3
"""Verify synchronized version bumps and native marketplace packaging."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_NAME = "diagram-design"
MANIFEST_PATHS = {
    "Claude": Path(".claude-plugin/plugin.json"),
    "Codex": Path(".codex-plugin/plugin.json"),
    "Factory": Path(".factory-plugin/plugin.json"),
}
CLAUDE_MARKETPLACE = Path(".claude-plugin/marketplace.json")
CODEX_MARKETPLACE = Path(".agents/plugins/marketplace.json")
FACTORY_MARKETPLACE = Path(".factory-plugin/marketplace.json")
SHARED_MANIFEST_FIELDS = (
    "name",
    "description",
    "version",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"could not read {path}: {exc}")
        return None
    except json.JSONDecodeError as exc:
        errors.append(f"{path} is not valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{path} must contain a JSON object")
        return None
    return payload


def base_path_exists(root: Path, base_ref: str, relative: Path) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{base_ref}:{relative.as_posix()}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def load_base_json(
    root: Path, base_ref: str, relative: Path, errors: list[str]
) -> dict[str, Any] | None:
    result = subprocess.run(
        ["git", "show", f"{base_ref}:{relative.as_posix()}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "file not found"
        errors.append(f"could not read {relative} from {base_ref}: {detail}")
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        errors.append(f"{relative} at {base_ref} is not valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{relative} at {base_ref} must contain a JSON object")
        return None
    return payload


def parse_semver(value: object, label: str, errors: list[str]) -> tuple[int, int, int] | None:
    if not isinstance(value, str) or (match := SEMVER.fullmatch(value)) is None:
        errors.append(
            f"{label} version must be strict MAJOR.MINOR.PATCH semver; got {value!r}"
        )
        return None
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def resolve_local_path(root: Path, raw_path: object, label: str, errors: list[str]) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"{label} must be a non-empty local path string")
        return None
    if raw_path not in {".", "./"} and not raw_path.startswith("./"):
        errors.append(f"{label} must be '.' or start with './'; got {raw_path!r}")
        return None

    relative = raw_path[2:] if raw_path.startswith("./") else ""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        errors.append(f"{label} must stay inside the marketplace root; got {raw_path!r}")
        return None

    resolved_root = root.resolve()
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(resolved_root):
        errors.append(f"{label} resolves outside the marketplace root: {raw_path!r}")
        return None
    if not resolved.is_dir():
        errors.append(f"{label} target does not exist or is not a directory: {raw_path!r}")
        return None
    return resolved


def find_plugin_entry(
    marketplace: dict[str, Any], label: str, errors: list[str]
) -> dict[str, Any] | None:
    if marketplace.get("name") != PLUGIN_NAME:
        errors.append(
            f"{label} marketplace name must remain {PLUGIN_NAME!r}; "
            f"got {marketplace.get('name')!r}"
        )
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        errors.append(f"{label} marketplace plugins must be an array")
        return None
    matches = [entry for entry in plugins if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME]
    if len(matches) != 1:
        errors.append(
            f"{label} marketplace must contain exactly one {PLUGIN_NAME!r} entry; "
            f"found {len(matches)}"
        )
        return None
    return matches[0]


def verify_versions(
    root: Path,
    base_ref: str,
    manifests: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    current_versions = {label: payload.get("version") for label, payload in manifests.items()}
    version_values = list(current_versions.values())
    if any(version != version_values[0] for version in version_values[1:]):
        rendered = ", ".join(f"{label}={value!r}" for label, value in current_versions.items())
        errors.append(f"plugin manifest versions must match: {rendered}")

    base_check = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if base_check.returncode != 0:
        detail = base_check.stderr.strip() or "not a commit"
        errors.append(f"could not resolve base ref {base_ref!r}: {detail}")
        return

    base_manifest_count = 0
    for label, relative in MANIFEST_PATHS.items():
        current = parse_semver(current_versions.get(label), f"current {label}", errors)
        if not base_path_exists(root, base_ref, relative):
            continue
        base_manifest_count += 1
        base_manifest = load_base_json(root, base_ref, relative, errors)
        if base_manifest is None:
            continue
        base = parse_semver(base_manifest.get("version"), f"{label} at {base_ref}", errors)
        if current is not None and base is not None and current <= base:
            errors.append(
                f"{label} manifest version must increase relative to {base_ref}: "
                f"{base_manifest.get('version')} -> {current_versions.get(label)}"
            )
    if base_manifest_count == 0:
        errors.append(
            f"no synchronized plugin manifest exists at {base_ref}; "
            "cannot establish that the package version advanced"
        )


def verify_manifest_identity(manifests: dict[str, dict[str, Any]], errors: list[str]) -> None:
    for label, payload in manifests.items():
        if payload.get("name") != PLUGIN_NAME:
            errors.append(
                f"{label} manifest name must remain {PLUGIN_NAME!r}; got {payload.get('name')!r}"
            )
    reference_label = next(iter(MANIFEST_PATHS))
    reference = manifests[reference_label]
    for label, payload in manifests.items():
        if label == reference_label:
            continue
        for field in SHARED_MANIFEST_FIELDS:
            if payload.get(field) != reference.get(field):
                errors.append(
                    f"{label} manifest {field!r} must match {reference_label}; "
                    f"got {payload.get(field)!r}"
                )


def verify_marketplaces(root: Path, errors: list[str]) -> None:
    claude_marketplace = load_json(root / CLAUDE_MARKETPLACE, errors)
    codex_marketplace = load_json(root / CODEX_MARKETPLACE, errors)
    factory_marketplace = load_json(root / FACTORY_MARKETPLACE, errors)
    if (
        claude_marketplace is None
        or codex_marketplace is None
        or factory_marketplace is None
    ):
        return

    claude_entry = find_plugin_entry(claude_marketplace, "Claude", errors)
    codex_entry = find_plugin_entry(codex_marketplace, "Codex", errors)
    factory_entry = find_plugin_entry(factory_marketplace, "Factory", errors)
    if claude_entry is None or codex_entry is None or factory_entry is None:
        return

    claude_root = resolve_local_path(root, claude_entry.get("source"), "Claude plugin source", errors)
    factory_root = resolve_local_path(
        root, factory_entry.get("source"), "Factory plugin source", errors
    )

    codex_source = codex_entry.get("source")
    if not isinstance(codex_source, dict) or codex_source.get("source") != "local":
        errors.append("Codex plugin source must be an object with source='local'")
        codex_root = None
    else:
        codex_root = resolve_local_path(root, codex_source.get("path"), "Codex plugin source.path", errors)

    policy = codex_entry.get("policy")
    if not isinstance(policy, dict):
        errors.append("Codex marketplace entry must include a policy object")
    else:
        if policy.get("installation") != "AVAILABLE":
            errors.append("Codex policy.installation must be 'AVAILABLE'")
        if policy.get("authentication") != "ON_INSTALL":
            errors.append("Codex policy.authentication must be 'ON_INSTALL'")
    if not isinstance(codex_entry.get("category"), str) or not codex_entry.get("category"):
        errors.append("Codex marketplace entry must include a category")

    if claude_root is not None and not (claude_root / MANIFEST_PATHS["Claude"]).is_file():
        errors.append("Claude marketplace target does not contain .claude-plugin/plugin.json")
    if codex_root is not None and not (codex_root / MANIFEST_PATHS["Codex"]).is_file():
        errors.append("Codex marketplace target does not contain .codex-plugin/plugin.json")
    if factory_root is not None and not (factory_root / MANIFEST_PATHS["Factory"]).is_file():
        errors.append("Factory marketplace target does not contain .factory-plugin/plugin.json")

    plugin_roots = [
        plugin_root
        for plugin_root in (claude_root, codex_root, factory_root)
        if plugin_root is not None
    ]
    if plugin_roots and any(plugin_root != plugin_roots[0] for plugin_root in plugin_roots[1:]):
        errors.append("Claude, Codex, and Factory marketplaces must package the same plugin root")

    plugin_root = codex_root or claude_root or factory_root
    if plugin_root is None:
        return
    skill = plugin_root / "skills" / PLUGIN_NAME / "SKILL.md"
    if not skill.is_file():
        errors.append(f"packaged skill is missing: {skill.relative_to(root)}")
    commands = plugin_root / "commands"
    if not commands.is_dir() or not any(commands.glob("*.md")):
        errors.append("packaged commands are missing from the shared plugin root")


def verify_codex_skill_path(root: Path, codex_manifest: dict[str, Any], errors: list[str]) -> None:
    skills_root = resolve_local_path(root, codex_manifest.get("skills"), "Codex manifest skills", errors)
    if skills_root is None:
        return
    skill = skills_root / PLUGIN_NAME / "SKILL.md"
    if not skill.is_file():
        errors.append(f"Codex skills path does not contain {PLUGIN_NAME}/SKILL.md")


def valid_double_quoted_yaml_scalar(value: str) -> bool:
    """Validate escapes in the single-line double-quoted YAML subset we accept."""
    match = re.fullmatch(r'"(?P<body>(?:[^"\\]|\\.)*)"(?:\s+#.*)?', value)
    if match is None:
        return False
    body = match.group("body")
    simple_escapes = set('0abtnvfre "\\/N_LP')
    index = 0
    while index < len(body):
        if body[index] != "\\":
            index += 1
            continue
        index += 1
        escape = body[index]
        if escape in simple_escapes:
            index += 1
            continue
        digits = {"x": 2, "u": 4, "U": 8}.get(escape)
        if digits is None:
            return False
        encoded = body[index + 1 : index + 1 + digits]
        if len(encoded) != digits or re.fullmatch(r"[0-9A-Fa-f]+", encoded) is None:
            return False
        if int(encoded, 16) > 0x10FFFF:
            return False
        index += 1 + digits
    return True


def parse_frontmatter_metadata_version(text: str) -> str | None:
    """Return exactly one direct ``metadata.version`` from YAML frontmatter.

    This intentionally does not search the Markdown body: examples and prose
    are allowed to mention ``version:``, but they cannot validate package
    metadata. The dependency-free parser accepts the mapping subset this
    skill's frontmatter uses and fails closed on malformed structure, duplicate
    keys, collection syntax, or malformed scalar values instead of guessing.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    try:
        closing = next(
            index for index in range(1, len(lines)) if lines[index].strip() == "---"
        )
    except StopIteration:
        return None

    entries: list[tuple[tuple[str, ...], str, str]] = []
    open_mappings: list[tuple[int, str]] = []
    seen_keys: dict[tuple[str, ...], set[str]] = {}
    previous_indent = -1
    previous_opened_mapping = False

    for raw_line in lines[1:closing]:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if "\t" in raw_line:
            return None
        match = re.fullmatch(
            r"(?P<indent> *)(?P<key>[A-Za-z_][\w.-]*):(?P<value>(?: +.*)?)",
            raw_line,
        )
        if match is None:
            return None

        indent = len(match.group("indent"))
        if previous_indent >= 0 and indent > previous_indent and not previous_opened_mapping:
            return None
        while open_mappings and indent <= open_mappings[-1][0]:
            open_mappings.pop()
        if indent > 0 and not open_mappings:
            return None

        parent = tuple(key for _, key in open_mappings)
        key = match.group("key")
        value = match.group("value").strip()
        duplicate = key in seen_keys.setdefault(parent, set())
        seen_keys[parent].add(key)
        # Count metadata.version rows below even when one value is malformed;
        # all other duplicate mapping keys are immediately ambiguous.
        if duplicate and not (parent == ("metadata",) and key == "version"):
            return None

        opens_mapping = not value or value.startswith("#")
        is_metadata_version = parent == ("metadata",) and key == "version"
        if not opens_mapping and not is_metadata_version:
            # Flow collections and block scalars are not used by this package's
            # frontmatter. Rejecting them keeps malformed brackets or multiline
            # YAML from being mistaken for valid metadata without a YAML runtime.
            if value[0] in "[{|>" or any(char in value for char in "[]{}"):
                return None
            if value[0] == '"':
                if not valid_double_quoted_yaml_scalar(value):
                    return None
            elif value[0] == "'":
                if re.fullmatch(r"'[^']*'(?:\s+#.*)?", value) is None:
                    return None
            elif ": " in value:
                return None

        entries.append((parent, key, value))
        if opens_mapping:
            open_mappings.append((indent, key))
        previous_indent = indent
        previous_opened_mapping = opens_mapping

    metadata_rows = [entry for entry in entries if entry[0] == () and entry[1] == "metadata"]
    if len(metadata_rows) != 1 or metadata_rows[0][2]:
        return None

    version_rows = [
        value
        for parent, key, value in entries
        if parent == ("metadata",) and key == "version"
    ]
    if len(version_rows) != 1:
        return None
    match = re.fullmatch(
        r"(?:\"([^\"]+)\"|'([^']+)'|([0-9]+(?:\.[0-9]+)*))\s*(?:#.*)?",
        version_rows[0],
    )
    if match is None:
        return None
    return next(value for value in match.groups() if value is not None)


def verify_skill_metadata_version(root: Path, manifests: dict[str, dict[str, Any]], errors: list[str]) -> None:
    """SKILL.md's metadata version must track the manifests' MAJOR.MINOR.

    The manifests are bumped by a script; SKILL.md's `metadata.version` is
    hand-maintained, so a minor release drifts silently - 2.4 sat against
    2.5.0 manifests until a post-merge sweep caught it. Nothing else reads
    both numbers, so nothing else can notice.
    """
    skill = root / "skills" / PLUGIN_NAME / "SKILL.md"
    if not skill.is_file():
        errors.append(f"missing {skill.relative_to(root).as_posix()}")
        return
    declared = parse_frontmatter_metadata_version(skill.read_text(encoding="utf-8"))
    if declared is None:
        errors.append("SKILL.md frontmatter has no metadata.version")
        return
    manifest_version = str(manifests["Claude"].get("version", ""))
    expected = ".".join(manifest_version.split(".")[:2])
    if declared != expected:
        errors.append(
            f"SKILL.md metadata.version {declared!r} must track the manifest "
            f"MAJOR.MINOR {expected!r} (manifests are at {manifest_version})"
        )


def verify_package(root: Path, base_ref: str) -> list[str]:
    errors: list[str] = []
    manifests: dict[str, dict[str, Any]] = {}
    for label, relative in MANIFEST_PATHS.items():
        payload = load_json(root / relative, errors)
        if payload is not None:
            manifests[label] = payload

    if len(manifests) == len(MANIFEST_PATHS):
        verify_versions(root, base_ref, manifests, errors)
        verify_manifest_identity(manifests, errors)
        verify_skill_metadata_version(root, manifests, errors)
        verify_codex_skill_path(root, manifests["Codex"], errors)
    verify_marketplaces(root, errors)
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {Path(sys.argv[0]).name} <base-ref>", file=sys.stderr)
        return 2
    base_ref = sys.argv[1]
    errors = verify_package(ROOT, base_ref)
    if errors:
        print("FAIL plugin package")
        for error in errors:
            print(f"  - {error}")
        return 1
    versions = load_json(ROOT / MANIFEST_PATHS["Claude"], [])["version"]
    print(
        f"OK plugin package: Claude, Codex, and Factory {versions}, "
        f"marketplace paths, and packaged skill"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
