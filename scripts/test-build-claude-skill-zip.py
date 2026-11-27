#!/usr/bin/env python3
"""Adversarial tests for scripts/build-claude-skill-zip.py.

The builder packages skills/diagrams-design-quind for Claude Desktop's custom-skill
upload. These cases pin the include rule (SKILL.md, references, packaged
scripts, templates, icons, and default-light examples), the files left out
(gallery index, dark/full/animated variants), the host file-count and
uncompressed-size limits, that a markdown link to an omitted file fails, and
that two builds are byte-identical. Fixture repositories are throwaway git
checkouts, so the cases do not depend on this repository's current assets.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILDER = ROOT / "scripts" / "build-claude-skill-zip.py"
SKILL = "skills/diagrams-design-quind"

_spec = importlib.util.spec_from_file_location("build_claude_skill_zip", BUILDER)
_builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_builder)
MAX_UNCOMPRESSED_BYTES = _builder.MAX_UNCOMPRESSED_BYTES
include_skill_path = _builder.include_skill_path

DEFAULT_SKILL_MD = """\
---
name: diagrams-design-quind
description: Create branded architecture and flowchart diagrams as HTML.
---

# Demo

Copy [`assets/template.html`](assets/template.html).
Load [`references/type-flowchart.md`](references/type-flowchart.md).
"""

TYPE_REF = """\
# Flowchart

See [`assets/example-flowchart.html`](../assets/example-flowchart.html).
"""

TEMPLATE = "<html><body>template</body></html>\n"
EXAMPLE = "<html><body>example</body></html>\n"
SCRIPT = "print('ok')\n"


def fixture(
    tmp: Path,
    name: str,
    *,
    skill_md: str = DEFAULT_SKILL_MD,
    extra: dict[str, bytes] | None = None,
    untracked: dict[str, bytes] | None = None,
    intent_to_add: tuple[str, ...] = (),
    edit_after_add: dict[str, bytes] | None = None,
    omit: tuple[str, ...] = (),
    symlinks: dict[str, str] | None = None,
) -> Path:
    root = tmp / name
    skill = root / SKILL
    (skill / "references").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "assets").mkdir()
    files = {
        f"{SKILL}/SKILL.md": skill_md.encode("utf-8"),
        f"{SKILL}/references/type-flowchart.md": TYPE_REF.encode("utf-8"),
        f"{SKILL}/scripts/self_check.py": SCRIPT.encode("utf-8"),
        f"{SKILL}/assets/template.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/template-dark.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/template-full.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/template-motion.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/template-terminal.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/icons.html": TEMPLATE.encode("utf-8"),
        f"{SKILL}/assets/example-flowchart.html": EXAMPLE.encode("utf-8"),
        f"{SKILL}/assets/example-flowchart-dark.html": EXAMPLE.encode("utf-8"),
        f"{SKILL}/assets/example-flowchart-full.html": EXAMPLE.encode("utf-8"),
        f"{SKILL}/assets/example-queue-animated.html": EXAMPLE.encode("utf-8"),
        f"{SKILL}/assets/index.html": TEMPLATE.encode("utf-8"),
    }
    files.update(extra or {})
    for path in omit:
        files.pop(path, None)
    tracked = []
    for relative, data in files.items():
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        tracked.append(relative)
    for relative, data in (untracked or {}).items():
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    for relative, target in (symlinks or {}).items():
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, dest)
        tracked.append(relative)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "--", *tracked], cwd=root, check=True)
    for relative in intent_to_add:
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("not staged yet\n")
        subprocess.run(["git", "add", "-N", "--", relative], cwd=root, check=True)
    for relative, data in (edit_after_add or {}).items():
        (root / relative).write_bytes(data)
    return root


def write_sized_file(path: Path, size: int) -> None:
    """Create a file of *size* bytes without filling the disk with data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    try:
        os.ftruncate(fd, size)
    finally:
        os.close(fd)


def included_payload_size(root: Path) -> int:
    """Sum working-tree bytes the builder's include rule would pack."""
    total = 0
    for path in (root / SKILL).rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root).as_posix()
        if include_skill_path(rel):
            total += path.stat().st_size
    return total


def fixture_with_uncompressed_size(tmp: Path, name: str, total: int) -> Path:
    """Default fixture plus one bundled pad file so the payload is *total* bytes."""
    root = fixture(tmp, name)
    pad = f"{SKILL}/scripts/pad.bin"
    pad_size = total - included_payload_size(root)
    if pad_size < 0:
        raise AssertionError(
            f"{name}: default fixture is {included_payload_size(root)} bytes, "
            f"already over the requested {total}"
        )
    write_sized_file(root / pad, pad_size)
    subprocess.run(["git", "add", "--", pad], cwd=root, check=True)
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


def zip_file_names(path: Path) -> list[str]:
    return [info.filename for info in zipfile.ZipFile(path).infolist() if not info.is_dir()]


def zip_structure_problems(path: Path, folder: str = "diagrams-design-quind") -> list[str]:
    problems = []
    archive = zipfile.ZipFile(path)
    names = archive.namelist()
    skill_md = f"{folder}/SKILL.md"
    if skill_md not in names:
        return [f"no {skill_md}"]
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
        if not info.is_dir() and not info.filename.startswith(folder + "/"):
            problems.append(f"{info.filename} is outside {folder}/")
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

        result = run("--root", str(ROOT), "--check")
        check("repo --check passes", result.returncode == 0, result.stdout + result.stderr)

        out_a, out_b = tmp / "repo-a", tmp / "repo-b"
        first = run("--root", str(ROOT), "--out", str(out_a))
        second = run("--root", str(ROOT), "--out", str(out_b))
        check("repo build succeeds", first.returncode == 0, first.stdout + first.stderr)
        check("repo second build succeeds", second.returncode == 0, second.stdout + second.stderr)
        if first.returncode == 0 and second.returncode == 0:
            zip_a, zip_b = built_zip(out_a), built_zip(out_b)
            check("repo ZIP is named diagrams-design-quind-claude-skill.zip", zip_a.name == "diagrams-design-quind-claude-skill.zip")
            names = zip_file_names(zip_a)
            problems = zip_structure_problems(zip_a)
            check("repo ZIP matches the upload layout", not problems, "; ".join(problems[:5]))
            check("repo ZIP has SKILL.md at the skill root", "diagrams-design-quind/SKILL.md" in names)
            check(
                "repo ZIP has a type reference",
                any(n.startswith("diagrams-design-quind/references/type-") and n.endswith(".md") for n in names),
            )
            check("repo ZIP has template.html", "diagrams-design-quind/assets/template.html" in names)
            check("repo ZIP has icons.html", "diagrams-design-quind/assets/icons.html" in names)
            check("repo ZIP has a packaged script", "diagrams-design-quind/scripts/self_check.py" in names)
            check(
                "repo ZIP has a default-light example",
                "diagrams-design-quind/assets/example-flowchart.html" in names,
            )
            check("repo ZIP excludes the gallery index", "diagrams-design-quind/assets/index.html" not in names)
            with zipfile.ZipFile(zip_a) as archive:
                onboarding = archive.read("diagrams-design-quind/references/onboarding.md").decode("utf-8")
            after = onboarding.split("After onboarding, the user should:", 1)[-1].split("\n---", 1)[0]
            previews = re.findall(r"`(assets/example-[^`]+\.html)`", after)
            check(
                "repo ZIP onboarding preview step names a bundled example",
                bool(previews) and all(f"diagrams-design-quind/{p}" in names for p in previews),
                ", ".join(previews) or "no example named",
            )
            dark = [n for n in names if n.endswith("-dark.html") and "/example-" in n]
            check("repo ZIP excludes dark example variants", not dark, ", ".join(dark[:5]))
            full = [n for n in names if n.endswith("-full.html") and "/example-" in n]
            check("repo ZIP excludes full example variants", not full, ", ".join(full[:5]))
            animated = [n for n in names if n.endswith("-animated.html")]
            check("repo ZIP excludes animated example variants", not animated, ", ".join(animated[:5]))
            stray = [n for n in names if not n.startswith("diagrams-design-quind/")]
            check("repo ZIP has only the skill folder", not stray, ", ".join(stray[:5]))
            check(
                "repo ZIP is under the host file limit",
                len(names) <= 200,
                f"{len(names)} files",
            )
            check(
                "repo ZIP is byte-reproducible",
                hashlib.sha256(zip_a.read_bytes()).digest()
                == hashlib.sha256(zip_b.read_bytes()).digest(),
            )
            index_skill = subprocess.run(
                ["git", "show", ":skills/diagrams-design-quind/SKILL.md"],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            check(
                "repo ZIP SKILL.md matches the git index",
                zipfile.ZipFile(zip_a).read("diagrams-design-quind/SKILL.md") == index_skill,
            )

        good = fixture(tmp, "good")
        out = tmp / "good-out"
        result = run("--root", str(good), "--out", str(out))
        check("complete fixture builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            names = zip_file_names(built_zip(out))
            problems = zip_structure_problems(built_zip(out))
            check("fixture ZIP matches the upload layout", not problems, "; ".join(problems[:5]))
            check("fixture ZIP includes the light example", "diagrams-design-quind/assets/example-flowchart.html" in names)
            check("fixture ZIP includes templates", "diagrams-design-quind/assets/template-dark.html" in names)
            check("fixture ZIP excludes gallery index", "diagrams-design-quind/assets/index.html" not in names)
            check(
                "fixture ZIP excludes dark example",
                "diagrams-design-quind/assets/example-flowchart-dark.html" not in names,
            )
            check(
                "fixture ZIP excludes full example",
                "diagrams-design-quind/assets/example-flowchart-full.html" not in names,
            )
            check(
                "fixture ZIP excludes animated example",
                "diagrams-design-quind/assets/example-queue-animated.html" not in names,
            )
            check("fixture ZIP is named for Claude Desktop", built_zip(out).name == "diagrams-design-quind-claude-skill.zip")

        linked = fixture(
            tmp,
            "linked-excluded",
            skill_md=(
                "---\nname: diagram-design\ndescription: Demo skill for ZIP tests.\n---\n\n"
                "See the gallery at [`assets/index.html`](assets/index.html).\n"
            ),
        )
        result = run("--root", str(linked), "--check")
        output = result.stdout + result.stderr
        check(
            "markdown link to an excluded file fails",
            result.returncode == 1 and "index.html" in output,
            output,
        )

        dark_link = fixture(
            tmp,
            "linked-dark",
            skill_md=(
                "---\nname: diagram-design\ndescription: Demo skill for ZIP tests.\n---\n\n"
                "Copy [`assets/example-flowchart-dark.html`](assets/example-flowchart-dark.html).\n"
            ),
        )
        result = run("--root", str(dark_link), "--check")
        output = result.stdout + result.stderr
        check(
            "markdown link to a dark example fails",
            result.returncode == 1 and "example-flowchart-dark.html" in output,
            output,
        )

        missing_link = fixture(
            tmp,
            "missing-link",
            skill_md=(
                "---\nname: diagram-design\ndescription: Demo skill for ZIP tests.\n---\n\n"
                "See [`assets/example-missing.html`](assets/example-missing.html).\n"
            ),
        )
        result = run("--root", str(missing_link), "--check")
        output = result.stdout + result.stderr
        check(
            "markdown link to a missing file fails",
            result.returncode == 1 and "example-missing.html" in output,
            output,
        )

        extra = {
            f"{SKILL}/assets/example-pad-{i:03d}.html": EXAMPLE.encode("utf-8") for i in range(180)
        }
        over = fixture(tmp, "over-limit", extra=extra)
        result = run("--root", str(over), "--check")
        output = result.stdout + result.stderr
        check(
            "file count over the margin fails",
            result.returncode == 1 and "files" in output,
            output,
        )

        at_size = fixture_with_uncompressed_size(tmp, "at-size-limit", MAX_UNCOMPRESSED_BYTES)
        result = run("--root", str(at_size), "--check")
        check(
            "uncompressed size at the limit passes",
            result.returncode == 0,
            result.stdout + result.stderr,
        )

        over_size = fixture_with_uncompressed_size(
            tmp, "over-size-limit", MAX_UNCOMPRESSED_BYTES + 1
        )
        result = run("--root", str(over_size), "--check")
        output = result.stdout + result.stderr
        check(
            "uncompressed size one byte over the limit fails",
            result.returncode == 1 and "uncompressed" in output,
            output,
        )

        long_name = fixture(
            tmp,
            "long-name",
            skill_md="---\nname: " + ("a" * 65) + "\ndescription: Demo skill for ZIP tests.\n---\n\nDemo.\n",
        )
        result = run("--root", str(long_name), "--check")
        check("name over 64 characters fails", result.returncode == 1, result.stdout + result.stderr)

        long_desc = fixture(
            tmp,
            "long-desc",
            skill_md="---\nname: diagram-design\ndescription: " + ("x" * 1025) + "\n---\n\nDemo.\n",
        )
        result = run("--root", str(long_desc), "--check")
        check(
            "description over 1024 characters fails",
            result.returncode == 1 and "description" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        bad_name = fixture(
            tmp,
            "bad-name",
            skill_md="---\nname: Diagram Design\ndescription: Demo skill for ZIP tests.\n---\n\nDemo.\n",
        )
        result = run("--root", str(bad_name), "--check")
        check("uppercase name fails", result.returncode == 1, result.stdout + result.stderr)

        xml_desc = fixture(
            tmp,
            "xml-desc",
            skill_md="---\nname: diagram-design\ndescription: Demo <script>nope</script> skill.\n---\n\nDemo.\n",
        )
        result = run("--root", str(xml_desc), "--check")
        check("description with XML tags fails", result.returncode == 1, result.stdout + result.stderr)

        folded_words = " ".join(["word"] * 120)
        folded_long = fixture(
            tmp,
            "folded-long-desc",
            skill_md=(
                "---\nname: diagram-design\ndescription: >\n"
                + "".join(f"  {folded_words}\n" for _ in range(3))
                + "license: MIT\n---\n\nDemo.\n"
            ),
        )
        result = run("--root", str(folded_long), "--check")
        check(
            "folded > description over 1024 characters fails",
            result.returncode == 1 and "description is" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        literal_xml = fixture(
            tmp,
            "literal-xml-desc",
            skill_md=(
                "---\nname: diagram-design\ndescription: |-\n"
                "  Demo skill for ZIP tests.\n  Runs <script>nope</script> inline.\n---\n\nDemo.\n"
            ),
        )
        result = run("--root", str(literal_xml), "--check")
        check(
            "literal | description with XML tags fails",
            result.returncode == 1 and "XML" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        plain_long = fixture(
            tmp,
            "plain-continued-long-desc",
            skill_md=(
                "---\nname: diagram-design\ndescription: start\n"
                + "".join(f"  {folded_words}\n" for _ in range(3))
                + "---\n\nDemo.\n"
            ),
        )
        result = run("--root", str(plain_long), "--check")
        check(
            "plain description continued over 1024 characters fails",
            result.returncode == 1 and "description is" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        unreadable = fixture(
            tmp,
            "unreadable-desc",
            skill_md="---\nname: diagram-design\ndescription: [a, b]\n---\n\nDemo.\n",
        )
        result = run("--root", str(unreadable), "--check")
        check(
            "description in an unsupported YAML form fails",
            result.returncode == 1 and "cannot read" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        for label, indicator in (("folded", ">"), ("literal", "|")):
            short_block = fixture(
                tmp,
                f"short-{label}-desc",
                skill_md=(
                    f"---\nname: diagram-design\ndescription: {indicator}\n"
                    "  Create branded architecture\n  and flowchart diagrams as HTML.\n"
                    "license: MIT\nmetadata:\n  version: \"2.6\"\n---\n\nDemo.\n"
                ),
            )
            result = run("--root", str(short_block), "--check")
            check(
                f"short {label} {indicator} description passes",
                result.returncode == 0,
                result.stdout + result.stderr,
            )

        staged = DEFAULT_SKILL_MD.encode("utf-8")
        dirty = fixture(
            tmp,
            "dirty-tree",
            edit_after_add={f"{SKILL}/SKILL.md": b"unstaged edit\n"},
        )
        out = tmp / "dirty-tree-out"
        result = run("--root", str(dirty), "--out", str(out))
        check("dirty working tree builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check(
                "ZIP holds staged bytes, not the working tree",
                zipfile.ZipFile(built_zip(out)).read("diagrams-design-quind/SKILL.md") == staged,
            )

        junk = fixture(
            tmp,
            "untracked-junk",
            untracked={f"{SKILL}/assets/example-secret.html": b"secret\n"},
        )
        out = tmp / "untracked-out"
        result = run("--root", str(junk), "--out", str(out))
        check("untracked extra example builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check(
                "untracked file stays out of the ZIP",
                "diagrams-design-quind/assets/example-secret.html" not in zip_file_names(built_zip(out)),
            )

        ita = fixture(tmp, "ita", intent_to_add=(f"{SKILL}/references/new.md",))
        result = run("--root", str(ita), "--out", str(tmp / "ita-out"))
        check(
            "intent-to-add file fails",
            result.returncode == 1 and "new.md" in (result.stdout + result.stderr),
            result.stdout + result.stderr,
        )

        no_skill = fixture(tmp, "no-skill", omit=(f"{SKILL}/SKILL.md",))
        result = run("--root", str(no_skill), "--check")
        check("missing SKILL.md fails", result.returncode == 1, result.stdout + result.stderr)

        if hasattr(os, "symlink"):
            try:
                linked_file = fixture(
                    tmp,
                    "symlink-skill",
                    symlinks={f"{SKILL}/references/linked.md": "type-flowchart.md"},
                )
                result = run("--root", str(linked_file), "--out", str(tmp / "symlink-out"))
                check(
                    "symlinked skill file fails",
                    result.returncode == 1 and "symlink" in (result.stdout + result.stderr),
                    result.stdout + result.stderr,
                )
            except OSError:
                pass

        odd = f"{SKILL}/references/caf\u00e9 notes.md"
        odd_root = fixture(tmp, "odd-path", extra={odd: b"notes\n"})
        out = tmp / "odd-path-out"
        result = run("--root", str(odd_root), "--out", str(out))
        check("unusual path builds", result.returncode == 0, result.stdout + result.stderr)
        if result.returncode == 0:
            check(
                "unusual path ships unchanged",
                "diagrams-design-quind/references/caf\u00e9 notes.md" in zip_file_names(built_zip(out)),
            )

    if failures:
        print(f"{len(failures)} Claude Desktop skill ZIP case(s) failed ({passed} passed):")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"All Claude Desktop skill ZIP cases passed ({passed}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
