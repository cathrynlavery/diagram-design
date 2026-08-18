#!/usr/bin/env python3
"""Verify that routing and browsing surfaces stay in sync with the skill.

Five drift classes, each of which has shipped before:

1. The SKILL.md frontmatter description is the only text an agent sees before
   deciding to load the skill — every visual type in the selection table must
   keep a lexical hook there.
2. The gallery (assets/index.html) must reach every shipped example, and every
   gallery tab must point at a file that exists.
3. Every concrete file named in README.md's architecture tree must exist.
4. Every relative references/*.md link in SKILL.md must resolve.
5. Claude and Pi profile surfaces must both route to the profile reference.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

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
    if len(types) != 27:
        errors.append(f"expected 27 visual types in the selection table; found {len(types)}")
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


def main() -> int:
    errors: list[str] = []
    check_description(errors)
    check_gallery(errors)
    check_readme_tree(errors)
    check_skill_reference_links(
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
        "reference links, profile surfaces"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
