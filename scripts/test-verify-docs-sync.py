#!/usr/bin/env python3
"""Regression tests for docs links and profile-surface verification."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-docs-sync.py"


def load_verify_module():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("diagram_design_verify_docs", VERIFY)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-docs-sync.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    verify = load_verify_module()
    with tempfile.TemporaryDirectory(prefix="verify-docs-sync-") as temp_dir:
        skill = Path(temp_dir)
        references = skill / "references"
        references.mkdir()
        (references / "present.md").write_text("# Present\n", encoding="utf-8")

        errors: list[str] = []
        verify.check_skill_reference_links(
            errors,
            "See [present](references/present.md) and [section](references/present.md#part).",
            skill,
        )
        if errors:
            raise AssertionError(f"valid reference link failed: {errors}")

        errors = []
        verify.check_skill_reference_links(
            errors,
            "See [missing](references/missing.md).",
            skill,
        )
        expected = "SKILL.md links to missing reference 'references/missing.md'"
        if errors != [expected]:
            raise AssertionError(f"broken reference was not reported: {errors}")

        errors = []
        verify.check_skill_reference_links(
            errors,
            "See [README](../../README.md), [asset](assets/example.html), and https://example.com.",
            skill,
        )
        if errors:
            raise AssertionError(f"non-reference links should be ignored: {errors}")

        scripts = skill / "scripts"
        assets = skill / "assets"
        scripts.mkdir()
        assets.mkdir()
        required_files = sorted(verify.REQUIRED_PACKAGED_RUNTIME_FILES)
        for target in required_files:
            packaged_file = skill / target
            packaged_file.parent.mkdir(parents=True, exist_ok=True)
            packaged_file.write_text("# packaged\n", encoding="utf-8")
        (assets / "example.html").write_text("<!doctype html>\n", encoding="utf-8")
        required_mentions = ", ".join(f"`{target}`" for target in required_files)
        packaged_markdown = f"""Use [the reference](references/present.md#section),
{required_mentions}, and `assets/example.html`.
From a repository checkout, run `python3 <repo-root>/scripts/verify-geometry.py <file>`.
"""
        extracted = verify.scanner_visible_support_references(packaged_markdown)
        expected = sorted(
            {"assets/example.html", "references/present.md", *required_files}
        )
        if extracted != expected:
            raise AssertionError(f"strict-bundler references drifted: {extracted}")
        errors = []
        verify.check_packaged_support_references(errors, packaged_markdown, skill)
        if errors:
            raise AssertionError(f"valid packaged support references failed: {errors}")

        for phantom in ("references/type-*.md", "references/type-<name>.md"):
            errors = []
            verify.check_packaged_support_references(
                errors,
                packaged_markdown + f"Load `{phantom}` before drawing.\n",
                skill,
            )
            if len(errors) != 1 or "strict skill bundlers will abort installation" not in errors[0]:
                raise AssertionError(
                    f"scanner-visible placeholder was not rejected: {phantom!r}: {errors}"
                )

        errors = []
        verify.check_packaged_support_references(
            errors,
            packaged_markdown + "See [unsafe](references/%2e%2e/secrets.md).\n",
            skill,
        )
        expected = "SKILL.md exposes unsafe packaged support path 'references/../secrets.md'"
        if errors != [expected]:
            raise AssertionError(f"unsafe packaged reference was not rejected: {errors}")

        errors = []
        verify.check_packaged_support_references(
            errors,
            packaged_markdown + "See [unsafe](references/%2e%2e%5csecrets.md).\n",
            skill,
        )
        if len(errors) != 1 or "unsafe packaged support path" not in errors[0]:
            raise AssertionError(f"encoded Windows traversal was not rejected: {errors}")

        actual_skill = verify.SKILL.read_text(encoding="utf-8")
        actual_references = set(
            verify.scanner_visible_support_references(actual_skill)
        )
        missing_runtime = verify.REQUIRED_PACKAGED_RUNTIME_FILES - actual_references
        if missing_runtime:
            raise AssertionError(
                "actual SKILL.md omits required packaged runtime files: "
                f"{sorted(missing_runtime)}"
            )

        missing_one = required_files[0]
        errors = []
        verify.check_packaged_support_references(
            errors,
            packaged_markdown.replace(f"`{missing_one}`", f"`{Path(missing_one).name}`"),
            skill,
        )
        expected = (
            f"SKILL.md does not expose required packaged runtime file {missing_one!r}; "
            "strict skill bundlers will omit it"
        )
        if errors != [expected]:
            raise AssertionError(f"omitted runtime helper was not reported: {errors}")

        root = Path(temp_dir) / "repo"
        profile_reference = root / "skills/diagram-design/references/profiles.md"
        command = root / "commands/profile.md"
        prompt = root / "prompts/profile.md"
        for path in (profile_reference, command, prompt):
            path.parent.mkdir(parents=True, exist_ok=True)
        profile_reference.write_text("# Profiles\n", encoding="utf-8")
        command.write_text("Follow references/profiles.md.\n", encoding="utf-8")
        prompt.write_text("Follow references/profiles.md.\n", encoding="utf-8")

        errors = []
        verify.check_profile_surfaces(errors, root)
        if errors:
            raise AssertionError(f"valid profile surfaces failed: {errors}")

        prompt.unlink()
        errors = []
        verify.check_profile_surfaces(errors, root)
        expected = "profile surface is missing: prompts/profile.md"
        if errors != [expected]:
            raise AssertionError(f"missing Pi prompt was not reported: {errors}")

        prompt.write_text("Stale standalone instructions.\n", encoding="utf-8")
        errors = []
        verify.check_profile_surfaces(errors, root)
        expected = (
            "profile surface does not route to references/profiles.md: prompts/profile.md"
        )
        if errors != [expected]:
            raise AssertionError(f"stale Pi prompt was not reported: {errors}")

        factory_manifest = root / ".factory-plugin/plugin.json"
        factory_marketplace = root / ".factory-plugin/marketplace.json"
        factory_manifest.parent.mkdir(parents=True)
        factory_manifest.write_text(
            json.dumps(
                {
                    "name": "diagram-design",
                    "repository": "https://github.com/example/diagram-design",
                }
            ),
            encoding="utf-8",
        )
        factory_marketplace.write_text(
            json.dumps({"name": "diagram-design"}),
            encoding="utf-8",
        )
        valid_readme = """# Diagram Design

```bash
droid plugin marketplace add https://github.com/example/diagram-design
droid plugin install diagram-design@diagram-design --scope user
```

```
diagram-design/
├── .factory-plugin/ — Factory Droid metadata
├── commands/
└── skills/
```
"""
        readme = root / "README.md"
        readme.write_text(valid_readme, encoding="utf-8")

        errors = []
        verify.check_factory_install_surface(errors, root)
        if errors:
            raise AssertionError(f"valid Factory install contract failed: {errors}")

        readme.write_text(
            valid_readme.replace(
                "droid plugin marketplace add https://github.com/example/diagram-design\n"
                "droid plugin install diagram-design@diagram-design --scope user",
                "droid plugin install diagram-design@diagram-design --scope user\n"
                "droid plugin marketplace add https://github.com/example/diagram-design",
            ),
            encoding="utf-8",
        )
        errors = []
        verify.check_factory_install_surface(errors, root)
        expected = (
            "README Factory install block must match native metadata: "
            "`droid plugin marketplace add https://github.com/example/diagram-design` "
            "then `droid plugin install diagram-design@diagram-design`"
        )
        if errors != [expected]:
            raise AssertionError(
                f"reversed Factory install commands were not reported: {errors}"
            )

        readme.write_text(
            valid_readme.replace(
                "diagram-design@diagram-design", "diagram-design@wrong-marketplace"
            ),
            encoding="utf-8",
        )
        errors = []
        verify.check_factory_install_surface(errors, root)
        expected = (
            "README Factory install block must match native metadata: "
            "`droid plugin marketplace add https://github.com/example/diagram-design` "
            "then `droid plugin install diagram-design@diagram-design`"
        )
        if errors != [expected]:
            raise AssertionError(
                f"drifted Factory plugin ID was not reported: {errors}"
            )

        readme.write_text(
            valid_readme.replace("├── .factory-plugin/ — Factory Droid metadata\n", ""),
            encoding="utf-8",
        )
        errors = []
        verify.check_factory_install_surface(errors, root)
        expected = (
            "README architecture tree must list Factory's native .factory-plugin/ path"
        )
        if errors != [expected]:
            raise AssertionError(f"missing Factory native path was not reported: {errors}")

    print(
        "PASS: docs sync checks references, strict-bundler packaging, profile surfaces, "
        "and Factory install contract"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
