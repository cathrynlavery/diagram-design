#!/usr/bin/env python3
"""Verify that routing and browsing surfaces stay in sync with the skill.

Twelve drift classes, each of which has shipped before:

1. The SKILL.md frontmatter description is the only text an agent sees before
   deciding to load the skill — every visual type in the selection table must
   keep a lexical hook there.
2. The gallery (assets/index.html) must reach every shipped example, and every
   gallery tab must point at a file that exists.
3. Every concrete file named in README.md's architecture tree must exist.
4. Every relative references/*.md link in SKILL.md must resolve.
5. Claude and Pi command/prompt surfaces must route to the matching reference.
6. Plugin descriptions must fit Cowork's installation limit while retaining
   every type's lexical hook. The skill and Codex longDescription keep the
   fuller feature summary without inheriting the short-description limit.
7. Factory Droid's README install commands and native manifest path must agree
   with the package metadata instead of becoming a second hand-maintained API.
8. Every support path a strict skill bundler can extract from SKILL.md must be
   a literal file shipped inside the skill package.
9. Import command surfaces must route to the visual-type taxonomy instead of
   hardcoding a count that becomes stale when a type is added.
10. The High-Level reproducibility checklist must agree with its canvas formula
   and retain sequential numbering.
11. The canonical dark Line example must keep the dark-skin tokens and canvas.
12. The SKILL.md 4px-grid section and the output-spec type ramp must agree: the
   grid table carries no font-size row, the grid section links to
   references/output-spec.md, the ramp table keeps its five type roles across all
   three presets, and every font-size in SKILL.md's §6 patterns is a canonical
   role size or falls inside a named exception.
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
HIGH_LEVEL_REFERENCE = ROOT / "skills/diagram-design/references/type-high-level.md"
ONBOARDING_REFERENCE = ROOT / "skills/diagram-design/references/onboarding.md"
LINE_DARK_EXAMPLE = ROOT / "skills/diagram-design/assets/example-line-dark.html"
OUTPUT_SPEC_REFERENCE = ROOT / "skills/diagram-design/references/output-spec.md"
VARIANTS = ("", "-dark", "-full")
VISUAL_TYPE_COUNT = 40
AGENT_SKILLS_DESCRIPTION_MAX = 1024
PLUGIN_DESCRIPTION_MAX = 500
# Types whose selection-table name differs from its description vocabulary.
DESCRIPTION_ALIASES = {
    "bar chart": "bar",
    "line chart": "line",
    "scatter plot": "scatter",
}
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
        "scripts/excalidraw_extract.py",
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


def check_onboarding_trust_boundary(errors: list[str], markdown: str) -> None:
    """Remote page ingestion must state its narrow, untrusted-data purpose."""
    text = normalized(markdown)
    has_boundary = "untrusted data" in text
    names_instruction_risk = "instruction" in text
    limits_use = (
        "use it only as a source of color, type, and spacing signals" in text
        and "never follow directive" in text
    )
    if not (has_boundary and names_instruction_risk and limits_use):
        errors.append(
            "onboarding.md fetches remote page content without an explicit "
            "untrusted-data boundary"
        )


def check_line_dark_skin(errors: list[str], source: str) -> None:
    """The dark Line example must not silently drift back to the light skin."""
    required = (
        "--color-paper:#2d3142",
        "--color-ink:#f5f5f5",
        "--color-muted:#bfc0c0",
        "--color-accent:#f08a59",
        '<rect width="100%" height="100%" fill="#2d3142"',
    )
    for token in required:
        if token not in source:
            errors.append(f"example-line-dark.html lost canonical dark-skin token {token!r}")


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


def check_description_length(errors: list[str], markdown: str) -> None:
    description = frontmatter_description(markdown)
    if len(description) > AGENT_SKILLS_DESCRIPTION_MAX:
        errors.append(
            "SKILL.md frontmatter description exceeds the Agent Skills limit "
            f"({len(description)} > {AGENT_SKILLS_DESCRIPTION_MAX} characters)"
        )


def check_description(errors: list[str]) -> None:
    markdown = SKILL.read_text(encoding="utf-8")
    check_description_length(errors, markdown)
    description = normalized(frontmatter_description(markdown))
    if not description:
        errors.append("SKILL.md frontmatter description is missing")
        return
    types = selection_table_types(markdown)
    if len(types) != VISUAL_TYPE_COUNT:
        errors.append(
            f"expected {VISUAL_TYPE_COUNT} visual types in the selection table; found {len(types)}"
        )
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
    # Parse eyebrow numbers and parent-type bindings from tab buttons.
    # Variants (data-parent-type) may share their declared parent's eyebrow
    # number; uniqueness is enforced only among independent (non-variant) types.
    tab_eyebrows: dict[str, str] = {}  # data-type → eyebrow number
    tab_parents: dict[str, str] = {}   # data-type → data-parent-type
    for m in re.finditer(r'<button([^>]*)>\s*<span class="eyebrow">(\d+)</span>', source):
        attrs, eyebrow = m.group(1), m.group(2)
        tm = re.search(r'data-type="([^"]+)"', attrs)
        pm = re.search(r'data-parent-type="([^"]+)"', attrs)
        if tm:
            tab_eyebrows[tm.group(1)] = eyebrow
            if pm:
                tab_parents[tm.group(1)] = pm.group(1)
    # Enforce uniqueness among independent (non-variant) types.
    seen_eyebrows: dict[str, str] = {}  # eyebrow → first independent type
    for t, num in tab_eyebrows.items():
        if t in tab_parents:
            continue
        if num in seen_eyebrows:
            errors.append(
                f"gallery has duplicate eyebrow number {num!r} on independent types "
                f"{seen_eyebrows[num]!r} and {t!r}; check tab order in assets/index.html"
            )
        else:
            seen_eyebrows[num] = t
    # Enforce that each variant's eyebrow matches its declared parent's.
    for t, parent in tab_parents.items():
        if parent not in tab_eyebrows:
            errors.append(
                f"gallery tab {t!r} declares data-parent-type={parent!r} "
                f"but no tab with data-type={parent!r} exists"
            )
        elif tab_eyebrows.get(t) != tab_eyebrows[parent]:
            errors.append(
                f"gallery tab {t!r} has eyebrow {tab_eyebrows.get(t)!r} but its "
                f"parent {parent!r} uses {tab_eyebrows[parent]!r}; they must match"
            )
    # Detect data-single types so we can skip the three-variant check for them.
    single_types: set[str] = set()
    for btn in re.finditer(r"<button[^>]+>", source):
        tag = btn.group(0)
        if "data-single" in tag:
            tm = re.search(r'data-type="([^"]+)"', tag)
            if tm:
                single_types.add(tm.group(1))
    # Verify that every non-single gallery tab has dark and full variants on disk.
    for name in sorted(types):
        if name in single_types:
            continue
        for variant in ("-dark", "-full"):
            fname = f"example-{name}{variant}.html"
            if fname not in on_disk:
                errors.append(
                    f"gallery tab {name!r} is missing {fname}; "
                    "add the variant or mark the tab data-single"
                )


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


def check_reference_asset_links(
    errors: list[str], skill_directory: Path
) -> None:
    """Require every asset cited across skill documentation to exist on disk."""
    asset_dir = skill_directory / "assets"
    ref_dir = skill_directory / "references"
    md_paths = [skill_directory / "SKILL.md", *sorted(ref_dir.glob("*.md"))]
    asset_pattern = re.compile(r"assets/([A-Za-z0-9_.-]+\.html)")

    for path in md_paths:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        for match in asset_pattern.finditer(content):
            asset_name = match.group(1)
            target = asset_dir / asset_name
            if not target.is_file():
                errors.append(
                    f"{path.name} cites missing asset 'assets/{asset_name}'"
                )


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


def check_routing_surfaces(errors: list[str], root: Path) -> None:
    for relative, reference_link in ROUTING_SURFACES.items():
        reference = root / "skills/diagram-design" / reference_link
        if not reference.is_file():
            errors.append(f"routing source of truth is missing: skills/diagram-design/{reference_link}")
        path = root / relative
        if not path.is_file():
            errors.append(f"routing surface is missing: {relative.as_posix()}")
            continue
        if reference_link not in path.read_text(encoding="utf-8"):
            errors.append(
                f"routing surface does not route to {reference_link}: {relative.as_posix()}"
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


# A command that spells the type count out has to be edited by every PR that
# adds a type, and is the one file such a PR has no reason to open. Both import
# commands were left at 27 while the selection table moved on.
# The phrasing varies, so match the count rather than the one sentence it went
# stale in. Two forms carry it: the bare count standing in for the table
# (`one of the 27`), and a count attached to the taxonomy noun with room for
# adjectives between, in either order (`28 visual types`, `28 supported visual
# diagram types`, `28 types of visual diagrams`). Those clauses insist on that
# noun so an unrelated quantity — `accepts 2 file types` — is not rejected by a
# gate about the visual taxonomy.
#
# Every gap is whitespace-tolerant because both commands already wrap the
# sentence that carried the stale count, so a count can land just after the
# wrap. That is why the whole file is searched at once and the line is derived
# from the match offset rather than iterating lines.
#
# Word-form numerals (`Twenty-eight visual types`) are out of scope; README and
# the docstring say "numeral" so the gate does not claim more than it checks.
HARDCODED_COUNT_RE = re.compile(
    r"one\s+of\s+(?:the\s+)?\d+\b"
    r"|\b\d+\s+(?:[\w-]+\s+){0,2}?(?:visual|diagram)[\s-]+types?\b"
    r"|\b\d+\s+types?\s+of\s+(?:[\w-]+\s+){0,2}?diagrams?\b",
    re.IGNORECASE,
)
COUNT_SURFACES = (
    Path("commands/import-drawio.md"),
    Path("commands/import-mermaid.md"),
    Path("commands/import-excalidraw.md"),
)


def check_type_counts(errors: list[str], root: Path) -> None:
    """No routing surface may write the visual-type count as a numeral."""
    for relative in COUNT_SURFACES:
        path = root / relative
        if not path.is_file():
            errors.append(f"type-count surface is missing: {relative.as_posix()}")
            continue
        text = path.read_text(encoding="utf-8")
        for match in HARDCODED_COUNT_RE.finditer(text):
            number = text.count("\n", 0, match.start()) + 1
            phrase = " ".join(match.group(0).split())
            errors.append(
                f"{relative.as_posix()}:{number} hardcodes the visual-type count "
                f"({phrase!r}); point at SKILL.md \u00a73 instead so adding a type "
                f"cannot leave it stale"
            )


def check_high_level_reference(errors: list[str], markdown: str) -> None:
    width_formula = re.search(
        r"^effective_w\s*=\s*(\d+)\s*-\s*right_strip_w\s*-\s*strip_margin",
        markdown,
        re.MULTILINE,
    )
    right_strip = re.search(r"^right_strip_w\s*=\s*(\d+)\s+if", markdown, re.MULTILINE)
    strip_margin = re.search(r"^strip_margin\s*=\s*(\d+)\s+if", markdown, re.MULTILINE)
    if not all((width_formula, right_strip, strip_margin)):
        errors.append("High-Level canvas is missing the effective-width formula")
        return

    checklist = re.search(
        r"^## 7\. Reproducibility checklist[^\n]*\n(.*?)(?=^## |\Z)",
        markdown,
        re.MULTILINE | re.DOTALL,
    )
    if checklist is None:
        errors.append("High-Level reproducibility checklist is missing")
        return

    items = re.findall(r"^(\d+)\.\s+(.+)$", checklist.group(1), re.MULTILINE)
    numbers = [int(number) for number, _ in items]
    expected_numbers = list(range(1, len(numbers) + 1))
    if numbers != expected_numbers:
        rendered = ",".join(str(number) for number in numbers)
        errors.append(
            "High-Level reproducibility checklist numbering is not sequential: "
            f"expected 1..{len(numbers)}, found {rendered}"
        )

    item_three = next((text for number, text in items if number == "3"), "")
    checklist_width = re.search(r"effective_w\s*=\s*(\d+)", item_three)
    expected_width = (
        int(width_formula.group(1))
        - int(right_strip.group(1))
        - int(strip_margin.group(1))
    )
    if checklist_width is None:
        errors.append("High-Level checklist item 3 is missing effective_w")
    elif int(checklist_width.group(1)) != expected_width:
        errors.append(
            f"High-Level checklist item 3 has effective_w={checklist_width.group(1)}; "
            f"expected {width_formula.group(1)} - {right_strip.group(1)} - "
            f"{strip_margin.group(1)} = {expected_width}"
        )


TYPE_RAMP_ROLES = ("Title", "Node name", "Sublabel", "Arrow label", "Eyebrow / tag")
# Both syntaxes the type-ramp contract claims: an SVG/HTML attribute in either
# quote style, and a CSS declaration in px. Relative CSS units are page chrome,
# not diagram type, so rem/em deliberately do not match.
FONT_SIZE_RE = re.compile(
    r"""font-size\s*(?:=\s*(?P<quote>["'])(?P<attr>\d+(?:\.\d+)?)(?P=quote)"""
    r"""|:\s*(?P<css>\d+(?:\.\d+)?)px)"""
)
SIZE_RANGE_RE = re.compile(r"^(\d+(?:\.\d+)?)(?: to (\d+(?:\.\d+)?))?$")
WATERMARK_OPACITY_RE = re.compile(r"at or under (\d+(?:\.\d+)?) opacity")
ALPHA_RE = re.compile(
    r"""(?:\bfill-)?(?<![-\w])opacity=["'](\d*\.?\d+)["']"""
    r"""|rgba\([^)]*?,\s*(\d*\.?\d+)\s*\)"""
)
LEGACY_SIZE_HEADING = "### Registered legacy sizes"
TYPE_SIZE_SUFFIXES = (".html", ".svg", ".md")
# Where diagram type lives. The gallery pages (index.html, icons.html) are site
# chrome, not diagrams, so the type ramp does not govern them.
TYPE_SIZE_SURFACES = (
    ("skills/diagram-design/assets", ("example-", "template")),
    ("skills/diagram-design/references", ("type-",)),
)


WEIGHT_RE = re.compile(r"""font-weight\s*[:=]\s*["']?(\d{3}|bold)""")


def font_classes(text: str) -> set[str]:
    """The ramp fonts a spec cell names. A cell may name more than one."""
    named = set()
    if "Instrument Serif" in text:
        named.add("serif")
    if "Mono" in text or "monospace" in text:
        named.add("mono")
    if "Geist 600" in text:
        named.add("sans-600")
    if "Geist regular" in text or "Geist sans" in text or "sans-serif" in text:
        named.add("sans")
    return named


def element_class(tag: str) -> str | None:
    """Which ramp font an element is set in, weight included.

    Geist at 600 or heavier is the node-name voice; lighter Geist is annotation.
    Keeping them apart is what stops a node name borrowing an annotation size.
    """
    if "Instrument Serif" in tag:
        return "serif"
    if "Mono" in tag or "monospace" in tag:
        return "mono"
    if "Geist" in tag or "sans-serif" in tag:
        weight = WEIGHT_RE.search(tag)
        declared = 700 if weight and weight.group(1) == "bold" else (
            int(weight.group(1)) if weight else 400
        )
        return "sans-600" if declared >= 600 else "sans"
    return None


def enclosing_tag(markup: str, index: int) -> str:
    """The open tag holding the character at *index*, plus its parent `<text>`.

    A `<tspan>` inherits its font from the `<text>` around it, so the parent is
    appended and the two are classified as one string.
    """
    start = markup.rfind("<", 0, index)
    if start < 0:
        return ""
    end = markup.find(">", index)
    if end < 0:
        return ""
    tag = markup[start : end + 1]
    # A CSS declaration inside `<style>` is not on an element. Rejecting a span
    # that swallows another `<` keeps the stylesheet from reading as one tag.
    if "<" in tag[1:]:
        return ""
    if tag.startswith("<tspan") and element_class(tag) is None:
        parent = markup.rfind("<text", 0, start)
        if parent >= 0:
            parent_end = markup.find(">", parent)
            if parent_end >= 0:
                tag += markup[parent : parent_end + 1]
    return tag


def tag_alpha(tag: str) -> float | None:
    """Smallest alpha the tag declares, whether as an attribute or in `rgba()`."""
    alphas = [
        float(explicit or in_rgba) for explicit, in_rgba in ALPHA_RE.findall(tag)
    ]
    return min(alphas) if alphas else None


class TypeContract:
    """The role ramp and its named exceptions, read off output-spec.md."""

    def __init__(self) -> None:
        self.canonical: dict[str, set[float]] = {}
        self.ranges: list[tuple[str, float, float]] = []
        self.watermark_alpha: float | None = None

    def allowed(self, klass: str | None) -> set[float]:
        if klass is None:
            return set().union(*self.canonical.values()) if self.canonical else set()
        return self.canonical.get(klass, set())

    def excepted(self, klass: str | None, value: float) -> bool:
        # An exception belongs to the font beside it, so text with no declared
        # font cannot claim one.
        return klass is not None and any(
            klass == exception_class and low <= value <= high and (value * 2) % 1 == 0
            for exception_class, low, high in self.ranges
        )

    def off_ramp(self, tag: str, value: float) -> bool:
        """Is *value* outside every role size and every exception range?

        Size only, ignoring which role the text plays. Shipped examples set type
        through CSS classes as well as attributes, so per-element role
        attribution is not reliable across the asset tree; the size floor is.
        """
        alpha = tag_alpha(tag)
        if (
            self.watermark_alpha is not None
            and alpha is not None
            and alpha <= self.watermark_alpha
        ):
            return False
        if any(value in sizes for sizes in self.canonical.values()):
            return False
        return not any(
            low <= value <= high and (value * 2) % 1 == 0
            for _, low, high in self.ranges
        )

    def violation(self, tag: str, value: float) -> str | None:
        """Why *value* is off contract on this tag, or None if it is fine."""
        klass = element_class(tag)
        alpha = tag_alpha(tag)
        if (
            self.watermark_alpha is not None
            and alpha is not None
            and alpha <= self.watermark_alpha
        ):
            return None
        if value in self.allowed(klass) or self.excepted(klass, value):
            return None
        if klass is None:
            return (
                f"font-size={format_size(value)} on text that declares no font; "
                "a size off the role ramp needs one so its exception can be checked"
            )
        sizes = ", ".join(format_size(size) for size in sorted(self.allowed(klass)))
        return (
            f"font-size={format_size(value)} on {klass} text, where the role ramp "
            f"allows {sizes or 'nothing'} and no named exception for that font "
            "covers it"
        )


def font_sizes(markup: str) -> list[tuple[float, str]]:
    """Every declared font size in *markup* with the tag it sits on."""
    found = []
    for match in FONT_SIZE_RE.finditer(markup):
        raw = match.group("attr") or match.group("css")
        found.append((float(raw), enclosing_tag(markup, match.start())))
    return found


SVG_BLOCK_RE = re.compile(r"<svg\b.*?</svg>", re.DOTALL)
CLASS_ATTR_RE = re.compile(r"""class=["']([^"']+)["']""")
SELECTOR_CLASS_RE = re.compile(r"\.([A-Za-z0-9_-]+)")


def diagram_font_sizes(markup: str) -> list[tuple[float, str]]:
    """Font sizes that govern diagram type, chrome around the diagram excluded.

    An example page is a diagram wrapped in prose. Attributes inside the `<svg>`
    count, and so does a CSS rule whose class is worn by an element in there; a
    rule for the page's own lede or heading does not.
    """
    if "<svg" not in markup:
        return font_sizes(markup)

    spans = [match.span() for match in SVG_BLOCK_RE.finditer(markup)]
    drawn = set()
    for start, end in spans:
        for value in CLASS_ATTR_RE.findall(markup[start:end]):
            drawn.update(value.split())

    sizes = []
    for match in FONT_SIZE_RE.finditer(markup):
        raw = match.group("attr") or match.group("css")
        inside = any(start <= match.start() < end for start, end in spans)
        if not inside:
            if match.group("attr"):
                continue
            brace = markup.rfind("{", 0, match.start())
            if brace < 0:
                continue
            selector = markup[max(markup.rfind("}", 0, brace), 0) : brace]
            if not drawn.intersection(SELECTOR_CLASS_RE.findall(selector)):
                continue
        sizes.append((float(raw), enclosing_tag(markup, match.start())))
    return sizes


def read_type_contract(errors: list[str], spec_markdown: str) -> TypeContract | None:
    """Parse the role ramp and exceptions table; None if the section is missing."""
    ramp = section(spec_markdown, "### Type ramp per size class")
    if not ramp:
        errors.append("output-spec.md has no '### Type ramp per size class' section")
        return None

    contract = TypeContract()
    rows = table_rows(ramp)
    for role in TYPE_RAMP_ROLES:
        row = next((cells for cells in rows if cells and cells[0].startswith(role)), None)
        if row is None:
            errors.append(f"output-spec.md type ramp is missing the {role!r} role row")
            continue
        named = font_classes(row[0])
        if not named:
            errors.append(
                f"output-spec.md type ramp row {role!r} does not name its font; "
                "the role sizes cannot be bound without one"
            )
            continue
        sizes = [cell for cell in row[1:] if re.fullmatch(r"\d+(?:\.\d+)?", cell)]
        if len(sizes) != 3:
            errors.append(
                f"output-spec.md type ramp row {role!r} has {len(sizes)} numeric "
                "sizes; expected three (standard, presentation, print)"
            )
            continue
        for klass in named:
            contract.canonical.setdefault(klass, set()).update(float(s) for s in sizes)

    # Scope the size parsing to the exceptions table. The ramp rows above it end
    # in a bare number too, and reading those as exceptions would let any ramp
    # value stand in for a missing exceptions table.
    header = re.search(r"^\|\s*Exception\s*\|", ramp, re.MULTILINE)
    for cells in table_rows(ramp[header.start() :] if header else ""):
        if len(cells) < 3:
            continue
        label, font_cell, sizes_cell = cells[0], cells[1], cells[-1]
        if label == "Exception":
            continue
        if font_cell.lower() == "any":
            opacity = WATERMARK_OPACITY_RE.search(label)
            if opacity:
                contract.watermark_alpha = float(opacity.group(1))
            continue
        named = font_classes(font_cell)
        if not named:
            errors.append(
                f"output-spec.md exception {label!r} names font {font_cell!r}, "
                "which is not one of the ramp fonts"
            )
            continue
        # A Sizes cell may qualify itself after a comma ("7 to 11, half steps
        # allowed"); the size itself is the part before it.
        match = SIZE_RANGE_RE.match(sizes_cell.split(",", 1)[0].strip())
        if match:
            low = float(match.group(1))
            high = float(match.group(2)) if match.group(2) else low
            for klass in named:
                contract.ranges.append((klass, low, high))
    if not contract.ranges:
        errors.append(
            "output-spec.md type ramp has no named font-size exceptions table; "
            "every off-ramp size needs a documented home"
        )
    return contract


def section(markdown: str, heading: str) -> str:
    """Text from *heading* to the next `### ` heading, heading excluded."""
    start = markdown.find(heading)
    if start < 0:
        return ""
    body = markdown[start + len(heading) :]
    end = re.search(r"^### ", body, re.MULTILINE)
    return body[: end.start()] if end else body


def table_rows(text: str) -> list[list[str]]:
    """Markdown table rows as cell lists, header and separator rows dropped."""
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def format_size(value: float) -> str:
    return f"{value:g}"


def check_type_ramp(errors: list[str], skill_markdown: str, spec_markdown: str) -> None:
    """The grid section and the output-spec role ramp are one contract."""
    grid = section(skill_markdown, "### 4px grid")
    if not grid:
        errors.append("SKILL.md has no '### 4px grid' section")
    else:
        if re.search(r"^\|\s*Font sizes", grid, re.MULTILINE):
            errors.append(
                "SKILL.md 4px-grid table carries a 'Font sizes' row; type sizes "
                "belong to the role ramp in references/output-spec.md, not the grid"
            )
        if "references/output-spec.md" not in grid:
            errors.append(
                "SKILL.md 4px-grid section does not link to references/output-spec.md "
                "for the type ramp"
            )

    contract = read_type_contract(errors, spec_markdown)
    if contract is None:
        return

    for value, tag in font_sizes(skill_markdown):
        violation = contract.violation(tag, value)
        if violation:
            errors.append(f"SKILL.md uses {violation}")


def check_legacy_type_sizes(errors: list[str], spec_markdown: str, root: Path) -> None:
    """The registered legacy sizes match what the shipped files actually carry."""
    contract = read_type_contract(errors, spec_markdown)
    if contract is None:
        return

    registry: dict[str, list[float]] = {}
    for cells in table_rows(section(spec_markdown, LEGACY_SIZE_HEADING)):
        if len(cells) < 2 or not cells[0].startswith("`"):
            continue
        name = cells[0].strip("`")
        registry[name] = sorted(float(size) for size in cells[1].split(","))
    if not registry:
        errors.append(
            f"output-spec.md has no '{LEGACY_SIZE_HEADING}' table; the shipped "
            "off-contract sizes need a written home"
        )
        return

    measured: dict[str, list[float]] = {}
    for directory, prefixes in TYPE_SIZE_SURFACES:
        for path in sorted((root / directory).iterdir()):
            if path.suffix.lower() not in TYPE_SIZE_SUFFIXES:
                continue
            if not path.name.startswith(prefixes):
                continue
            markup = path.read_text(encoding="utf-8")
            off = [
                value
                for value, tag in diagram_font_sizes(markup)
                if contract.off_ramp(tag, value)
            ]
            if off:
                measured[f"{path.parent.name}/{path.name}"] = sorted(off)

    for name in sorted(set(registry) | set(measured)):
        want = registry.get(name)
        got = measured.get(name)
        if want == got:
            continue
        if want is None:
            errors.append(
                f"{name} carries off-contract font sizes "
                f"{format_sizes(got)} that the registered legacy list in "
                "output-spec.md does not cover"
            )
        elif got is None:
            errors.append(
                f"output-spec.md registers legacy font sizes {format_sizes(want)} "
                f"for {name}, which no longer carries any; drop the row"
            )
        else:
            errors.append(
                f"{name} carries off-contract font sizes {format_sizes(got)} but "
                f"output-spec.md registers {format_sizes(want)}"
            )


def format_sizes(values: list[float]) -> str:
    return ", ".join(format_size(value) for value in values)


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
            if key == "description" and len(value) > PLUGIN_DESCRIPTION_MAX:
                errors.append(
                    f"{relative.as_posix()} description exceeds the Cowork limit "
                    f"({len(value)} > {PLUGIN_DESCRIPTION_MAX} characters)"
                )
            text = normalized(value)
            for name in types:
                hook = DESCRIPTION_ALIASES.get(normalized(name), normalized(name))
                if hook not in text:
                    errors.append(
                        f"{relative.as_posix()} {key!r} lost the lexical hook for "
                        f"type {name!r} (expected {hook!r}) — it must name every "
                        f"type the SKILL.md description names"
                    )


def font_families(url: str) -> set[str]:
    """The `family=` parameters a Google Fonts css2 URL actually requests."""
    return {
        part.split(":", 1)[0]
        for part in url.replace("&amp;", "&").split("&")
        if part.startswith("family=")
    }


def check_export_font_parity(errors: list[str], root: Path) -> None:
    """The exported SVG must request every face the shipped HTML link does.

    The two strings live in different files and drifted apart once already: the
    CJK faces reached assets/template.html but never the @import in export.md,
    so a Korean or Chinese diagram exported to .svg silently lost its type. That
    failure only shows up on a machine other than the author's, which is exactly
    the case the faces are in the link to prevent.
    """
    template = root / "skills/diagram-design/assets/template.html"
    export = root / "skills/diagram-design/references/export.md"
    for path in (template, export):
        if not path.is_file():
            errors.append(f"font-parity surface is missing: {path.name}")
            return

    link = re.search(r'href="([^"]*fonts\.googleapis\.com[^"]*)"',
                     template.read_text(encoding="utf-8"))
    imported = re.search(r"@import url\('([^']+)'\)",
                         export.read_text(encoding="utf-8"))
    if not link or not imported:
        errors.append(
            "could not locate the font link in assets/template.html or the "
            "@import in references/export.md"
        )
        return

    missing = sorted(font_families(link.group(1)) - font_families(imported.group(1)))
    if missing:
        names = ", ".join(name.removeprefix("family=").replace("+", " ")
                          for name in missing)
        errors.append(
            f"references/export.md @import omits {names}, which "
            f"assets/template.html requests; an exported .svg would resolve "
            f"those scripts through whatever font the viewer happens to have"
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
    check_reference_asset_links(errors, SKILL.parent)
    check_packaged_support_references(
        errors,
        SKILL.read_text(encoding="utf-8"),
        SKILL.parent,
    )
    check_type_counts(errors, ROOT)
    check_high_level_reference(errors, HIGH_LEVEL_REFERENCE.read_text(encoding="utf-8"))
    check_onboarding_trust_boundary(
        errors, ONBOARDING_REFERENCE.read_text(encoding="utf-8")
    )
    check_line_dark_skin(errors, LINE_DARK_EXAMPLE.read_text(encoding="utf-8"))
    check_type_ramp(
        errors,
        SKILL.read_text(encoding="utf-8"),
        OUTPUT_SPEC_REFERENCE.read_text(encoding="utf-8"),
    )
    check_legacy_type_sizes(
        errors, OUTPUT_SPEC_REFERENCE.read_text(encoding="utf-8"), ROOT
    )
    check_routing_surfaces(errors, ROOT)
    check_export_font_parity(errors, ROOT)
    if errors:
        print("FAIL docs sync")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "OK docs sync: description hooks, gallery reachability, README tree, "
        "reference links, asset citations, packaged support files, routing surfaces, "
        "manifest descriptions, Factory install contract, type-count routing, "
        "High-Level invariants, onboarding trust boundary, Line dark-skin contract, "
        "export font parity, type-ramp contract, registered legacy type sizes"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
