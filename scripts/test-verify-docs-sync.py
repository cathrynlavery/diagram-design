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

        counted = root / "commands"
        counted.mkdir(parents=True, exist_ok=True)
        drawio = counted / "import-drawio.md"
        mermaid = counted / "import-mermaid.md"
        routed = "`--type` forces one of the visual types in SKILL.md \u00a73.\n"
        for path in (drawio, mermaid):
            path.write_text(routed, encoding="utf-8")

        errors = []
        verify.check_type_counts(errors, root)
        if errors:
            raise AssertionError(f"a command pointing at SKILL.md failed: {errors}")

        # The stale wording the gate was written for, the same wording wrapped
        # across the line the real commands wrap on, and the rewrites a later
        # edit would reach for. Each is the only defect in the tree, so the gate
        # has to report exactly one error.
        for stale in (
            "`--type` forces one of the 27.\n",
            "`--type` forces one of the\n27 visual types.\n",
            "`--type` forces one of 28.\n",
            "The skill draws 28 visual types.\n",
            "The skill draws 28 supported visual diagram types.\n",
        ):
            mermaid.write_text(stale, encoding="utf-8")
            errors = []
            verify.check_type_counts(errors, root)
            if len(errors) != 1 or "hardcodes the visual-type count" not in errors[0]:
                raise AssertionError(
                    f"a hardcoded count was not reported for {stale!r}: {errors}"
                )

        # Counts that are not the visual-type count must pass. A gate that
        # rejects "accepts 2 file types" is one contributors route around, and
        # both commands already carry unrelated numbers in their flag docs.
        for benign in (
            "`--type` accepts 2 file types.\n",
            "Produces 3 output types.\n",
            "`--detail=faithful` allows 24 nodes.\n",
        ):
            mermaid.write_text(routed + benign, encoding="utf-8")
            errors = []
            verify.check_type_counts(errors, root)
            if errors:
                raise AssertionError(
                    f"a count unrelated to the taxonomy was rejected for {benign!r}: {errors}"
                )

        # Restore the routed wording first: leaving a stale count behind lets
        # this case pass on the wrong error and never names the missing surface.
        mermaid.write_text(routed, encoding="utf-8")
        drawio.unlink()
        errors = []
        verify.check_type_counts(errors, root)
        expected = "type-count surface is missing: commands/import-drawio.md"
        if errors != [expected]:
            raise AssertionError(f"a missing command surface was not reported: {errors}")

    print(
        "PASS: docs sync checks reference links, Claude/Pi profile-surface parity, "
        "the Factory install contract, and hardcoded type counts"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
