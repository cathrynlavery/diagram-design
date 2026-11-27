#!/usr/bin/env python3
"""Build the ZIP uploaded as a custom skill in Claude Desktop.

Claude Desktop's skill upload rejects an archive with more than 200 files
(issue #525, November 2026). Public Agent Skills documentation states the
frontmatter ``name``/``description`` limits and a 30 MiB uncompressed upload
size, but does not publish a file-count cap; this builder uses the 200-file
error the issue reported, with a margin so a new type cannot land on the
ceiling unnoticed.

The ZIP is a top-level folder named for the skill, with SKILL.md at its root.
Contents come from the git index under ``skills/diagrams-design-quind/``, never the
working tree, so the upload matches what the repository ships.

Include rule (product decision for this host; adjust here, not with a hand
list of names):

- SKILL.md
- every file under ``references/`` (the index and type pages the skill loads)
- every file under ``scripts/`` (the packaged extractors, export helpers, and
  checkers the skill tells the agent to run)
- ``assets/template*.html`` and ``assets/icons.html`` (copy sources)
- every file under ``assets/icons/`` (the QUIND icon libraries)
- every ``assets/example-*.html`` that is not a gallery or CI-only variant

Gallery and CI-only, left out:

- ``assets/index.html`` (the website gallery)
- ``example-*-dark.html``, ``example-*-full.html``, ``example-*-animated.html``

A markdown link in SKILL.md or ``references/*.md`` that resolves to a tracked
skill file must still be in the ZIP. If the skill text points at a file this
rule would drop, ``--check`` fails so the omit is visible.

Usage:
  python3 scripts/build-claude-skill-zip.py --check
  python3 scripts/build-claude-skill-zip.py           # dist/diagrams-design-quind-claude-skill.zip
"""

from __future__ import annotations

import argparse
import io
import re
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
SKILL_PREFIX = "skills/diagrams-design-quind/"
OUTPUT_NAME = "diagrams-design-quind-claude-skill.zip"

# Upload file count from the Claude Desktop error in issue #525. Public docs
# checked 2026-11-19 (Agent Skills overview, skills-guide, "How to create
# custom skills") do not state this number.
HOST_FILE_LIMIT = 200
FILE_COUNT_MARGIN = 20
MAX_FILES = HOST_FILE_LIMIT - FILE_COUNT_MARGIN

# Skills API / Agent Skills authoring docs: uncompressed upload under 30 MiB.
MAX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024

# Agent Skills spec / API. The claude.ai support article also cites 200
# characters for description; this repository's SKILL.md description is the
# 1,024-character routing text (ADR 0004) and is checked at that cap.
NAME_MAX = 64
DESCRIPTION_MAX = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\Z")
RESERVED_NAMES = frozenset({"anthropic", "claude"})
XML_TAG = re.compile(r"<[^>]+>")

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
UNIX_HOST = 3
FILE_ATTRS = (stat.S_IFREG | 0o644) << 16
DIR_ATTRS = (stat.S_IFDIR | 0o755) << 16 | 0x10  # 0x10 is the MS-DOS directory flag

MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
FRONTMATTER_FIELD = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
BLOCK_SCALAR = re.compile(r"^([|>])(?:([+-])([1-9])?|([1-9])?([+-])?)?\s*(?:#.*)?$")
UNPARSED = "\0unparsed"


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--literal-pathspecs", "-C", str(root), *args],
        input=data,
        capture_output=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"build-claude-skill-zip: git {' '.join(args)} failed: "
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
            raise SystemExit(f"build-claude-skill-zip: could not read blob {blob}")
        size = int(header[2])
        contents.append(stream.read(size))
        stream.read(1)  # trailing newline
    return contents


def is_gallery_or_ci_variant(name: str) -> bool:
    """Dark, full, and animated examples exist for the gallery and CI."""
    if not name.startswith("example-") or not name.endswith(".html"):
        return False
    stem = PurePosixPath(name).stem
    return stem.endswith(("-dark", "-full", "-animated"))


def include_skill_path(path: str) -> bool:
    """Return True if *path* (repo-relative) belongs in the Claude Desktop ZIP."""
    if not path.startswith(SKILL_PREFIX) or path.endswith("/"):
        return False
    rest = path[len(SKILL_PREFIX) :]
    if rest == "SKILL.md":
        return True
    if rest.startswith("references/") and rest != "references/":
        return True
    if rest.startswith("scripts/") and rest != "scripts/":
        return True
    if not rest.startswith("assets/"):
        return False
    if rest.startswith("assets/icons/"):  # QUIND icon libraries (Lucide, AWS, Azure, GCP)
        return True
    name = PurePosixPath(rest).name
    if name.startswith("template") and name.endswith(".html"):
        return True
    if name == "icons.html":
        return True
    if name == "index.html":
        return False
    if name.startswith("example-") and name.endswith(".html"):
        return not is_gallery_or_ci_variant(name)
    return False


def posix_norm(parts: list[str]) -> str:
    out: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if out:
                out.pop()
            continue
        out.append(part)
    return "/".join(out)


def resolve_skill_target(source: str, target: str) -> str | None:
    """Resolve a markdown-link target to a repo path inside the skill, or None."""
    raw = target.strip()
    if raw.startswith("<") and raw.endswith(">"):
        raw = raw[1:-1].strip()
    raw = raw.split()[0] if raw else raw
    raw = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not raw or raw.startswith(("http://", "https://", "mailto:", "data:")):
        return None
    resolved = posix_norm([*PurePosixPath(source).parent.parts, *PurePosixPath(raw).parts])
    if not resolved.startswith(SKILL_PREFIX) or resolved == SKILL_PREFIX.rstrip("/"):
        return None
    return resolved


def referenced_skill_paths(texts: dict[str, str]) -> dict[str, str]:
    """Map each skill file a markdown link points at to the first source that names it."""
    found: dict[str, str] = {}
    for source, text in texts.items():
        for match in MARKDOWN_LINK.finditer(text):
            resolved = resolve_skill_target(source, match.group(1))
            if resolved and resolved not in found:
                found[resolved] = source
    return found


def fold_block(lines: list[str]) -> str:
    """Fold block-scalar lines: line breaks become spaces, blank lines become newlines."""
    out = ""
    pending_breaks = 0
    for line in lines:
        if not line:
            pending_breaks += 1
            continue
        if out:
            out += "\n" * pending_breaks if pending_breaks else " "
        out += line
        pending_breaks = 0
    return out


def parse_frontmatter(text: str) -> dict[str, str]:
    """Read top-level scalar fields from YAML frontmatter without a YAML library.

    Handles plain and quoted single-line values, plain values continued on
    indented lines, and folded (``>``) and literal (``|``) block scalars with
    optional chomping and indentation indicators. A value this reader cannot
    take apart reliably maps to ``UNPARSED`` so the check reports it instead
    of validating the wrong text.
    """
    match = FRONTMATTER.search(text)
    if not match:
        return {}
    lines = match.group(1).splitlines()
    fields: dict[str, str] = {}
    i = 0
    while i < len(lines):
        field = FRONTMATTER_FIELD.match(lines[i])
        i += 1
        if not field:
            continue
        key, value = field.group(1), field.group(2).strip()
        body: list[str] = []
        while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
            body.append(lines[i])
            i += 1
        while body and not body[-1].strip():
            body.pop()
        block = BLOCK_SCALAR.match(value)
        if block:
            style = block.group(1)
            chomp = block.group(2) or block.group(5)
            explicit = block.group(3) or block.group(4)
            content = [line for line in body if line.strip()]
            if not content:
                fields[key] = ""
                continue
            indent = min(len(line) - len(line.lstrip(" ")) for line in content)
            if explicit:
                indent = int(explicit)
            if indent == 0 or any(
                line.strip() and len(line) - len(line.lstrip(" ")) < indent for line in body
            ):
                fields[key] = UNPARSED
                continue
            stripped = [line[indent:] for line in body]
            if style == "|":
                value = "\n".join(stripped)
            else:
                value = fold_block(stripped)
            if chomp != "-":
                value += "\n"
            fields[key] = value
            continue
        if value[:1] in "|>&*!{[" or (value[:1] in "\"'" and body):
            fields[key] = UNPARSED
            continue
        if body:
            value = fold_block([value] + [line.strip() for line in body])
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value
    return fields


def check_frontmatter(fields: dict[str, str], errors: list[str]) -> str | None:
    name = fields.get("name")
    description = fields.get("description")
    for key, value in (("name", name), ("description", description)):
        if value == UNPARSED:
            errors.append(
                f"SKILL.md frontmatter {key} uses a YAML form this check cannot read; "
                "write it as a plain, quoted, or > / | block scalar"
            )
    if name == UNPARSED:
        name = None
    elif not isinstance(name, str) or not name.strip():
        errors.append("SKILL.md frontmatter name is required")
        name = None
    else:
        if len(name) > NAME_MAX:
            errors.append(
                f"SKILL.md frontmatter name is {len(name)} characters; "
                f"Agent Skills allows {NAME_MAX}"
            )
        if not NAME_RE.match(name) or XML_TAG.search(name) or name in RESERVED_NAMES:
            errors.append(
                f"SKILL.md frontmatter name {name!r} must be lowercase letters, "
                "numbers, and hyphens, and must not be a reserved word"
            )
    if description == UNPARSED:
        pass
    elif not isinstance(description, str) or not description.strip():
        errors.append("SKILL.md frontmatter description is required")
    else:
        if len(description) > DESCRIPTION_MAX:
            errors.append(
                f"SKILL.md frontmatter description is {len(description)} characters; "
                f"Agent Skills allows {DESCRIPTION_MAX}"
            )
        if XML_TAG.search(description):
            errors.append("SKILL.md frontmatter description must not contain XML tags")
    return name


def fail(errors: list[str]) -> int:
    print(f"build-claude-skill-zip: {len(errors)} problem(s):", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


def selected_files(tracked: dict[str, str]) -> list[str]:
    return sorted(path for path in tracked if include_skill_path(path))


def archive_name(repo_path: str, folder: str) -> str:
    rest = repo_path[len(SKILL_PREFIX) :]
    return f"{folder}/{rest}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=ROOT, help="plugin repository root")
    parser.add_argument("--out", type=Path, help="output directory (default: <root>/dist)")
    parser.add_argument("--check", action="store_true", help="validate only; write nothing")
    args = parser.parse_args()
    root = args.root.resolve()

    errors: list[str] = []
    skill_md = SKILL_PREFIX + "SKILL.md"
    tracked = index_entries(root, [SKILL_PREFIX], errors)
    if skill_md not in tracked:
        return fail(errors + [f"{skill_md} is not staged under {root}"])

    files = selected_files(tracked)
    if skill_md not in files:
        errors.append(f"{skill_md} is excluded by the include rule")

    markdown_sources = {
        path: read_blobs(root, [tracked[path]])[0].decode("utf-8")
        for path in tracked
        if path == skill_md or (path.startswith(SKILL_PREFIX + "references/") and path.endswith(".md"))
    }
    fields = parse_frontmatter(markdown_sources.get(skill_md, ""))
    folder = check_frontmatter(fields, errors)

    for path, source in referenced_skill_paths(markdown_sources).items():
        if path not in tracked:
            state = "exists but is not tracked by git" if (root / path).is_file() else "does not exist"
            errors.append(f"{source} links to {path}, which {state}")
            continue
        if path not in files:
            errors.append(
                f"{source} links to {path}, which the Claude Desktop ZIP omits; "
                "include it or drop the link"
            )

    payload_names = [archive_name(path, folder or "skill") for path in files]
    uncompressed = 0
    contents: list[bytes] = []
    if not errors:
        contents = read_blobs(root, [tracked[path] for path in files])
        uncompressed = sum(len(blob) for blob in contents)

    if len(files) > HOST_FILE_LIMIT:
        errors.append(
            f"ZIP would contain {len(files)} files; Claude Desktop rejects more than "
            f"{HOST_FILE_LIMIT} (issue #525)"
        )
    elif len(files) > MAX_FILES:
        errors.append(
            f"ZIP would contain {len(files)} files; the host limit is {HOST_FILE_LIMIT} "
            f"and this check keeps a margin of {FILE_COUNT_MARGIN} "
            f"(max {MAX_FILES})"
        )
    if uncompressed > MAX_UNCOMPRESSED_BYTES:
        errors.append(
            f"ZIP uncompressed payload is {uncompressed:,} bytes; "
            f"Agent Skills allows {MAX_UNCOMPRESSED_BYTES:,}"
        )

    if errors:
        return fail(errors)

    if args.check:
        print(
            f"OK Claude Desktop skill ZIP: {len(files)} files, "
            f"{uncompressed:,} bytes uncompressed "
            f"(host limit {HOST_FILE_LIMIT} files with margin {FILE_COUNT_MARGIN}; "
            f"{MAX_UNCOMPRESSED_BYTES:,} bytes)"
        )
        return 0

    assert folder is not None
    payload = dict(zip(payload_names, contents))
    directories = {
        "/".join(path.split("/")[:depth]) + "/"
        for path in payload
        for depth in range(1, path.count("/") + 1)
    }
    out_dir = (args.out or root / "dist").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / OUTPUT_NAME
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
    print(f"OK built {target} ({len(payload)} files, {target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
