#!/usr/bin/env python3
"""Verify that routing and browsing surfaces stay in sync with the skill.

Eight drift classes, each of which has shipped before:

1. The SKILL.md frontmatter description is the only text an agent sees before
   deciding to load the skill — every visual type in the selection table must
   keep a lexical hook there.
2. The gallery (assets/index.html) must reach every shipped example, and every
   gallery tab must point at a file that exists.
3. Every concrete file named in README.md's architecture tree must exist.
4. Every relative references/*.md link in SKILL.md must resolve.
5. Claude and Pi profile surfaces must both route to the profile reference.
6. The plugin manifests repeat the SKILL.md description verbatim. They are the
   text a user reads *before installing*, so by ADR 0004's own argument they
   need every type's lexical hook too - and nothing else notices when they
   drift, because they are four separate copies of one sentence.
7. Factory Droid's README install commands and native manifest path must agree
   with the package metadata instead of becoming a second hand-maintained API.
8. Every support path a strict skill bundler can extract from SKILL.md must be
   a literal file shipped inside the skill package.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills/diagram-design/SKILL.md"
GALLERY = ROOT / "skills/diagram-design/assets/index.html"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
README = ROOT / "README.md"
VARIANTS = ("", "-dark", "-full")
# Types whose selection-table name differs from its description vocabulary.
DESCRIPTION_ALIASES = {
    "bar chart": "bar",
    "line chart": "line",
    "scatter plot": "scatter",
}
PROFILE_SURFACES = (
    Path("commands/profile.md"),
    Path("prompts/profile.md"),
)
FACTORY_MANIFEST = Path(".factory-plugin/plugin.json")
FACTORY_MARKETPLACE = Path(".factory-plugin/marketplace.json")
SUPPORT_DIRECTORIES = frozenset(
    {"references", "templates", "scripts", "assets", "examples"}
)
# Mirrors Hermes Agent's support-file scanner. It intentionally sees Markdown
# links, code spans, and path-like prose because strict bundlers may require
# every extracted path before they install any part of the skill.
SCANNER_VISIBLE_SUPPORT_REFERENCE = re.compile(
    r"(?:\]\(|`|(?:^|[\s\"']))"
    r"((?:references|templates|scripts|assets|examples)/[^\s)`\"'<>]+)",
    re.MULTILINE,
)
REQUIRED_PACKAGED_RUNTIME_FILES = frozenset(
    {
        "scripts/self_check.py",
        "scripts/drawio_extract.py",
        "scripts/mermaid_extract.py",
        "assets/template.html",
        "assets/template-dark.html",
        "assets/template-full.html",
        "assets/template-motion.html",
        "assets/template-terminal.html",
    }
)


def normalized(text: str) -> str:
    text = text.casefold()
    text = re.sub(r"\s*/\s*", "/", text)
    return re.sub(r"\s+", " ", text)


def frontmatter_description(markdown: str) -> str:
    parts = markdown.split("---")
    if len(parts) < 3:
        return ""
    match = re.search(r"^description:\s*(.+)$", parts[1], re.MULTILINE)
    return match.group(1).strip() if match else ""


def selection_table_types(markdown: str) -> list[str]:
    start = markdown.find("### Visual-type guide")
    end = markdown.find("Rules of thumb", start)
    if start < 0 or end < 0:
        return []
    names = re.findall(r"^\|[^|]*\|\s*\*\*([^*]+)\*\*\s*\|", markdown[start:end], re.MULTILINE)
    return [name.strip() for name in names]


def check_description(errors: list[str]) -> None:
    markdown = SKILL.read_text(encoding="utf-8")
    description = normalized(frontmatter_description(markdown))
    if not description:
        errors.append("SKILL.md frontmatter description is missing")
        return
    types = selection_table_types(markdown)
    if len(types) != 38:
        errors.append(f"expected 38 visual types in the selection table; found {len(types)}")
    for name in types:
        key = normalized(name)
        key = DESCRIPTION_ALIASES.get(key, key)
        if key not in description:
            errors.append(
                f"description lost the lexical hook for type {name!r} "
                f"(expected {key!r} in the SKILL.md frontmatter description)"
            )


def gallery_types(source: str) -> list[str]:
    return re.findall(r'data-type="([^"]+)"', source)


def check_gallery(errors: list[str]) -> None:
    source = GALLERY.read_text(encoding="utf-8")
    types = gallery_types(source)
    if not types:
        errors.append("gallery has no data-type tabs")
        return
    reachable = {f"example-{name}{variant}.html" for name in types for variant in VARIANTS}
    on_disk = {path.name for path in ASSET_DIR.glob("example-*.html")}
    for name in sorted(on_disk - reachable):
        errors.append(f"gallery cannot reach shipped example {name}; add a tab to assets/index.html")
    for name in sorted(types):
        if f"example-{name}.html" not in on_disk:
            errors.append(f"gallery tab {name!r} points at a missing example-{name}.html")


def readme_tree_tokens(markdown: str) -> list[str]:
    blocks = re.findall(r"```\n(diagram-design/\n.*?)```", markdown, re.DOTALL)
    tokens: list[str] = []
    for block in blocks:
        tokens.extend(
            re.findall(r"([A-Za-z0-9][A-Za-z0-9_.*-]*\.(?:md|html|py|yml|yaml|json|txt|mmd|drawio|png))", block)
        )
    return tokens


def check_readme_tree(errors: list[str]) -> None:
    markdown = README.read_text(encoding="utf-8")
    tokens = readme_tree_tokens(markdown)
    if not tokens:
        errors.append("README architecture tree not found or names no files")
        return
    for token in sorted(set(tokens)):
        matches = list(ROOT.rglob(token))
        if not matches:
            errors.append(f"README architecture tree names {token!r} but no such file exists")


def skill_reference_links(markdown: str) -> list[str]:
    """Return direct relative links from SKILL.md into references/."""
    return re.findall(
        r"\]\((references/[A-Za-z0-9][A-Za-z0-9_.-]*\.md)(?:#[^)]*)?\)",
        markdown,
    )


def check_skill_reference_links(
    errors: list[str], markdown: str, skill_directory: Path
) -> None:
    for target in sorted(set(skill_reference_links(markdown))):
        if not (skill_directory / target).is_file():
            errors.append(f"SKILL.md links to missing reference {target!r}")


def scanner_visible_support_references(markdown: str) -> list[str]:
    """Return the local support paths a strict skill bundler will request."""
    normalized_markdown = markdown.replace("\\", "/")
    references: set[str] = set()
    for match in SCANNER_VISIBLE_SUPPORT_REFERENCE.finditer(normalized_markdown):
        raw = match.group(1).rstrip(".,;:")
        references.add(unquote(urlsplit(raw).path))
    return sorted(references)


def check_packaged_support_references(
    errors: list[str], markdown: str, skill_directory: Path
) -> None:
    """Require every scanner-visible path to be a safe, packaged file."""
    scanner_references = scanner_visible_support_references(markdown)
    for target in scanner_references:
        normalized_target = target.replace("\\", "/")
        path = PurePosixPath(normalized_target)
        parts = [part for part in path.parts if part not in {"", "."}]
        if (
            not parts
            or parts[0] not in SUPPORT_DIRECTORIES
            or normalized_target.startswith("/")
            or path.is_absolute()
            or any(part == ".." or ":" in part for part in parts)
        ):
            errors.append(f"SKILL.md exposes unsafe packaged support path {target!r}")
        elif not (skill_directory / "/".join(parts)).is_file():
            errors.append(
                f"SKILL.md exposes missing packaged support file {target!r}; "
                "strict skill bundlers will abort installation"
            )
    for target in sorted(REQUIRED_PACKAGED_RUNTIME_FILES - set(scanner_references)):
        errors.append(
            f"SKILL.md does not expose required packaged runtime file {target!r}; "
            "strict skill bundlers will omit it"
        )


def check_profile_surfaces(errors: list[str], root: Path) -> None:
    reference = root / "skills/diagram-design/references/profiles.md"
    if not reference.is_file():
        errors.append("profile source of truth is missing: skills/diagram-design/references/profiles.md")
    for relative in PROFILE_SURFACES:
        path = root / relative
        if not path.is_file():
            errors.append(f"profile surface is missing: {relative.as_posix()}")
            continue
        if "references/profiles.md" not in path.read_text(encoding="utf-8"):
            errors.append(
                f"profile surface does not route to references/profiles.md: {relative.as_posix()}"
            )


def check_factory_install_surface(errors: list[str], root: Path) -> None:
    markdown = (root / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((root / FACTORY_MANIFEST).read_text(encoding="utf-8"))
    marketplace = json.loads((root / FACTORY_MARKETPLACE).read_text(encoding="utf-8"))
    code_blocks = re.findall(
        r"^```[^\n]*\n(.*?)^```[ \t]*$", markdown, re.MULTILINE | re.DOTALL
    )

    marketplace_command = f"droid plugin marketplace add {manifest['repository']}"
    install_command = f"droid plugin install {manifest['name']}@{marketplace['name']}"
    command_blocks = [
        [line.strip() for line in block.splitlines() if line.strip()]
        for block in code_blocks
    ]
    install_is_documented = any(
        any(
            line == install_command or line.startswith(f"{install_command} ")
            for line in lines[lines.index(marketplace_command) + 1 :]
        )
        for lines in command_blocks
        if marketplace_command in lines
    )
    if not install_is_documented:
        errors.append(
            "README Factory install block must match native metadata: "
            f"`{marketplace_command}` then `{install_command}`"
        )

    native_directory = f"{FACTORY_MANIFEST.parent.as_posix()}/"
    architecture_blocks = [
        block
        for block in code_blocks
        if "diagram-design/" in block and "commands/" in block
    ]
    native_path_is_documented = any(
        line.lstrip(" │├─└").startswith(native_directory)
        for block in architecture_blocks
        for line in block.splitlines()
    )
    if not native_path_is_documented:
        errors.append(
            f"README architecture tree must list Factory's native {native_directory} path"
        )


MANIFEST_DESCRIPTIONS = (
    (Path(".claude-plugin/plugin.json"), ("description",)),
    (Path(".claude-plugin/marketplace.json"), ("description",)),
    (Path(".codex-plugin/plugin.json"), ("description", "longDescription")),
    (FACTORY_MANIFEST, ("description",)),
)


def find_key(node: object, key: str) -> str | None:
    """First value for *key* anywhere in a nested JSON document."""
    if isinstance(node, dict):
        if isinstance(node.get(key), str):
            return node[key]
        for value in node.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def check_manifest_descriptions(errors: list[str], root: Path) -> None:
    markdown = SKILL.read_text(encoding="utf-8")
    description = normalized(frontmatter_description(markdown))
    if not description:
        return
    types = selection_table_types(markdown)
    for relative, keys in MANIFEST_DESCRIPTIONS:
        path = root / relative
        if not path.exists():
            errors.append(f"missing plugin manifest: {relative.as_posix()}")
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        for key in keys:
            value = find_key(document, key)
            if value is None:
                errors.append(f"{relative.as_posix()} has no {key!r}")
                continue
            text = normalized(value)
            for name in types:
                hook = DESCRIPTION_ALIASES.get(normalized(name), normalized(name))
                if hook not in text:
                    errors.append(
                        f"{relative.as_posix()} {key!r} lost the lexical hook for "
                        f"type {name!r} (expected {hook!r}) — it must name every "
                        f"type the SKILL.md description names"
                    )


def main() -> int:
    errors: list[str] = []
    check_description(errors)
    check_manifest_descriptions(errors, ROOT)
    check_factory_install_surface(errors, ROOT)
    check_gallery(errors)
    check_readme_tree(errors)
    check_skill_reference_links(
        errors,
        SKILL.read_text(encoding="utf-8"),
        SKILL.parent,
    )
    check_packaged_support_references(
        errors,
        SKILL.read_text(encoding="utf-8"),
        SKILL.parent,
    )
    check_profile_surfaces(errors, ROOT)
    if errors:
        print("FAIL docs sync")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "OK docs sync: description hooks, gallery reachability, README tree, "
        "reference links, packaged support files, profile surfaces, manifest descriptions, "
        "Factory install contract"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
