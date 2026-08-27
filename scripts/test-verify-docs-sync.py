#!/usr/bin/env python3
"""Regression tests for docs links and routing-surface verification."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERIFY = ROOT / "scripts" / "verify-docs-sync.py"

HIGH_LEVEL_REFERENCE = """\
## 2. Layout formulas — deterministic geometry

### 2.1 Canvas

```
has_vertical       = any(c.vertical for c in chevrons)
right_strip_w      = 28  if has_vertical else 0
strip_margin       = 8   if has_vertical else 0
effective_w        = 1000 - right_strip_w - strip_margin
```

## 7. Reproducibility checklist (the taste gate)

1. Check one.
2. Check two.
3. If a vertical chevron exists, `effective_w = 964`; otherwise, `effective_w = 1000`.
4. Check four.
5. Check five.
6. Check six.
7. Check seven.
8. Check eight.
9. Check nine.
10. Check ten.
11. Check eleven.
12. Check twelve.
13. Check thirteen.

## 8. Anti-patterns
"""


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
        doctor_reference = root / "skills/diagram-design/references/doctor.md"
        export_reference = root / "skills/diagram-design/references/export.md"
        drawio_reference = root / "skills/diagram-design/references/import-drawio.md"
        mermaid_reference = root / "skills/diagram-design/references/import-mermaid.md"
        export_command = root / "commands/export-diagram.md"
        drawio_command = root / "commands/import-drawio.md"
        mermaid_command = root / "commands/import-mermaid.md"
        profile_command = root / "commands/profile.md"
        doctor_command = root / "commands/doctor.md"
        export_prompt = root / "prompts/export-diagram.md"
        mermaid_prompt = root / "prompts/import-mermaid.md"
        profile_prompt = root / "prompts/profile.md"
        doctor_prompt = root / "prompts/doctor.md"
        for path in (
            profile_reference,
            doctor_reference,
            export_reference,
            drawio_reference,
            mermaid_reference,
            export_command,
            drawio_command,
            mermaid_command,
            profile_command,
            doctor_command,
            export_prompt,
            mermaid_prompt,
            profile_prompt,
            doctor_prompt,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        profile_reference.write_text("# Profiles\n", encoding="utf-8")
        doctor_reference.write_text("# Doctor\n", encoding="utf-8")
        export_reference.write_text("# Export\n", encoding="utf-8")
        drawio_reference.write_text("# Draw.io\n", encoding="utf-8")
        mermaid_reference.write_text("# Mermaid\n", encoding="utf-8")
        export_command.write_text("Follow references/export.md.\n", encoding="utf-8")
        drawio_command.write_text("Follow references/import-drawio.md.\n", encoding="utf-8")
        mermaid_command.write_text("Follow references/import-mermaid.md.\n", encoding="utf-8")
        profile_command.write_text("Follow references/profiles.md.\n", encoding="utf-8")
        doctor_command.write_text("Follow references/doctor.md.\n", encoding="utf-8")
        export_prompt.write_text("Follow references/export.md.\n", encoding="utf-8")
        mermaid_prompt.write_text("Follow references/import-mermaid.md.\n", encoding="utf-8")
        profile_prompt.write_text("Follow references/profiles.md.\n", encoding="utf-8")
        doctor_prompt.write_text("Follow references/doctor.md.\n", encoding="utf-8")

        errors = []
        verify.check_routing_surfaces(errors, root)
        if errors:
            raise AssertionError(f"valid routing surfaces failed: {errors}")

        doctor_prompt.unlink()
        errors = []
        verify.check_routing_surfaces(errors, root)
        expected = "routing surface is missing: prompts/doctor.md"
        if errors != [expected]:
            raise AssertionError(f"missing routing prompt was not reported: {errors}")

        doctor_prompt.write_text("Stale standalone instructions.\n", encoding="utf-8")
        errors = []
        verify.check_routing_surfaces(errors, root)
        expected = (
            "routing surface does not route to references/doctor.md: prompts/doctor.md"
        )
        if errors != [expected]:
            raise AssertionError(f"stale routing prompt was not reported: {errors}")

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
            "The skill supports 28 types of visual diagrams.\n",
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
            "Reads 2 types of visual file.\n",
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

        errors = []
        verify.check_high_level_reference(errors, HIGH_LEVEL_REFERENCE)
        if errors:
            raise AssertionError(f"valid High-Level reference failed: {errors}")

        errors = []
        verify.check_high_level_reference(
            errors,
            HIGH_LEVEL_REFERENCE.replace("effective_w = 964", "effective_w = 972", 1),
        )
        expected = (
            "High-Level checklist item 3 has effective_w=972; "
            "expected 1000 - 28 - 8 = 964"
        )
        if errors != [expected]:
            raise AssertionError(f"stale effective width was not reported: {errors}")

        errors = []
        verify.check_high_level_reference(
            errors,
            HIGH_LEVEL_REFERENCE.replace("13. Check thirteen.", "11. Check thirteen."),
        )
        expected = (
            "High-Level reproducibility checklist numbering is not sequential: "
            "expected 1..13, found 1,2,3,4,5,6,7,8,9,10,11,12,11"
        )
        if errors != [expected]:
            raise AssertionError(f"duplicate checklist number was not reported: {errors}")

    # ── gallery guard tests ───────────────────────────────────────────────────
    # Helper: build a minimal gallery HTML with arbitrary tab markup.
    def make_tab(type_name: str, eyebrow: str, *, single: bool = False, parent: str | None = None) -> str:
        single_attr = " data-single" if single else ""
        parent_attr = f' data-parent-type="{parent}"' if parent else ""
        return (
            f'<button class="tab" data-type="{type_name}"{single_attr}{parent_attr}>'
            f'<span class="eyebrow">{eyebrow}</span>{type_name}</button>'
        )

    def make_gallery_html(*tabs: str) -> str:
        return (
            '<!doctype html><html><body><div id="type-tabs">'
            + "".join(tabs)
            + "</div></body></html>"
        )

    with tempfile.TemporaryDirectory(prefix="verify-docs-sync-gallery-") as gal_tmp:
        gal_dir = Path(gal_tmp)
        gallery_file = gal_dir / "index.html"
        asset_dir = gal_dir / "assets"
        asset_dir.mkdir()

        def run_gallery_check(html: str, filenames: list[str]) -> list[str]:
            for f in asset_dir.glob("example-*.html"):
                f.unlink()
            gallery_file.write_text(html, encoding="utf-8")
            for fname in filenames:
                (asset_dir / fname).write_text("", encoding="utf-8")
            orig_gallery = verify.GALLERY
            orig_asset_dir = verify.ASSET_DIR
            verify.GALLERY = gallery_file
            verify.ASSET_DIR = asset_dir
            errs: list[str] = []
            try:
                verify.check_gallery(errs)
            finally:
                verify.GALLERY = orig_gallery
                verify.ASSET_DIR = orig_asset_dir
            return errs

        full_trio = ["example-x.html", "example-x-dark.html", "example-x-full.html"]

        # 1. Duplicate eyebrow number is caught.
        html = make_gallery_html(make_tab("x", "01"), make_tab("y", "01"))
        files = full_trio + ["example-y.html", "example-y-dark.html", "example-y-full.html"]
        errs = run_gallery_check(html, files)
        if not any("duplicate eyebrow" in e and "01" in e for e in errs):
            raise AssertionError(f"duplicate eyebrow not caught: {errs}")
        print("OK gallery: duplicate eyebrow number caught")

        # 2. Unique eyebrow numbers pass without error.
        html = make_gallery_html(make_tab("x", "01"), make_tab("y", "02"))
        errs = run_gallery_check(html, files)
        if any("duplicate eyebrow" in e for e in errs):
            raise AssertionError(f"unique eyebrows raised false positive: {errs}")
        print("OK gallery: unique eyebrow numbers produce no error")

        # 3. Non-single tab missing -dark variant is caught.
        html = make_gallery_html(make_tab("x", "01"))
        errs = run_gallery_check(html, ["example-x.html", "example-x-full.html"])
        if not any("x" in e and "dark" in e for e in errs):
            raise AssertionError(f"missing -dark not caught: {errs}")
        print("OK gallery: missing -dark variant caught")

        # 4. Non-single tab missing -full variant is caught.
        errs = run_gallery_check(html, ["example-x.html", "example-x-dark.html"])
        if not any("x" in e and "full" in e for e in errs):
            raise AssertionError(f"missing -full not caught: {errs}")
        print("OK gallery: missing -full variant caught")

        # 5. data-single tab with only the light file passes (no false positive).
        html = make_gallery_html(make_tab("x", "01", single=True))
        errs = run_gallery_check(html, ["example-x.html"])
        if any("x" in e and ("dark" in e or "full" in e) for e in errs):
            raise AssertionError(f"data-single tab raised false variant error: {errs}")
        print("OK gallery: data-single tab exempt from variant check")

        # 6. Complete non-single tab (all three variants present) passes.
        html = make_gallery_html(make_tab("x", "01"))
        errs = run_gallery_check(html, full_trio)
        if any("x" in e for e in errs):
            raise AssertionError(f"complete tab raised unexpected error: {errs}")
        print("OK gallery: complete non-single tab passes")

        line_trio = ["example-line.html", "example-line-dark.html", "example-line-full.html"]
        ridge_trio = ["example-ridgeline.html", "example-ridgeline-dark.html", "example-ridgeline-full.html"]

        # 7. Variant sharing its parent's eyebrow is allowed (no error).
        html = make_gallery_html(make_tab("line", "20"), make_tab("ridgeline", "20", parent="line"))
        errs = run_gallery_check(html, line_trio + ridge_trio)
        if any("eyebrow" in e or "parent" in e for e in errs):
            raise AssertionError(f"valid parent/variant reuse raised error: {errs}")
        print("OK gallery: variant sharing parent eyebrow is allowed")

        # 8. Variant with wrong eyebrow number is caught.
        html = make_gallery_html(make_tab("line", "20"), make_tab("ridgeline", "99", parent="line"))
        errs = run_gallery_check(html, line_trio + ridge_trio)
        if not any("ridgeline" in e and "eyebrow" in e for e in errs):
            raise AssertionError(f"variant with wrong eyebrow not caught: {errs}")
        print("OK gallery: variant with wrong eyebrow number caught")

        # 9. Variant declaring a missing parent is caught.
        html = make_gallery_html(make_tab("ridgeline", "20", parent="line"))
        errs = run_gallery_check(html, ridge_trio)
        if not any("ridgeline" in e and "line" in e for e in errs):
            raise AssertionError(f"variant with missing parent not caught: {errs}")
        print("OK gallery: variant with missing parent caught")

    print(
        "PASS: docs sync checks references, strict-bundler packaging, routing surfaces, "
        "Factory install contract, type-count routing, High-Level invariants, "
        "and gallery guards (parent/variant model)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
