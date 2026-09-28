#!/usr/bin/env python3
"""Regression tests for verify-semantic-motion.py.

Covers the two entry points (verify_markdown, verify_example) against the
shipped skill docs / animated example, plus a handful of adversarial cases
that mirror the pattern used by test-verify-docs-sync.py and
test-verify-motion.py for the other verifiers in this repo.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-semantic-motion.py"


def load_verifier():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(
        "diagram_design_verify_semantic_motion", VERIFIER
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-semantic-motion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_verifier()

    # Shipped docs and example must pass as-is.
    markdown_errors = module.verify_markdown()
    if markdown_errors:
        raise AssertionError(f"shipped skill docs failed verify_markdown: {markdown_errors}")
    print("OK: shipped SKILL.md / semantic-patterns.md / animation.md pass verify_markdown")

    example_errors = module.verify_example()
    if example_errors:
        raise AssertionError(f"shipped example failed verify_example: {example_errors}")
    print("OK: shipped policy-trace example passes verify_example")

    original_skill = module.SKILL
    try:
        with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-") as temp_dir:
            scratch = Path(temp_dir)

            # Missing semantic-pattern router link must be rejected.
            missing_router = scratch / "missing-router.md"
            missing_router.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "semantic-patterns.md", "patterns.md"
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_router
            errors = module.verify_markdown()
            if not any("must link to semantic-patterns.md" in error for error in errors):
                raise AssertionError(f"missing semantic router was accepted: {errors}")
            print("OK: missing semantic-pattern router link is rejected")

            # Dropping one of the nine named patterns must be rejected.
            missing_pattern = scratch / "missing-pattern.md"
            missing_pattern.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "Fan-in queue / bottleneck", "Fan-in queue removed"
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_pattern
            errors = module.verify_markdown()
            if not any(
                "does not route semantic pattern: Fan-in queue / bottleneck" in error
                for error in errors
            ):
                raise AssertionError(f"missing semantic pattern was accepted: {errors}")
            print("OK: missing semantic-pattern name is rejected")

            # The new lifecycle route must remain discoverable from SKILL.md.
            missing_lifecycle = scratch / "missing-lifecycle.md"
            missing_lifecycle.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "**Lifecycle phase map** → State Machine",
                    "**Generic lifecycle** → State Machine",
                ),
                encoding="utf-8",
            )
            module.SKILL = missing_lifecycle
            errors = module.verify_markdown()
            if not any(
                "does not route semantic pattern: Lifecycle phase map" in error
                for error in errors
            ):
                raise AssertionError(f"missing lifecycle route was accepted: {errors}")
            print("OK: missing lifecycle phase-map route is rejected")

            # The byte cap is inclusive and measures LF-normalized bytes, so a
            # checkout with core.autocrlf=true measures the same as the
            # committed file (#246). Pad the real SKILL.md after its final
            # newline so every other check still reads the shipped content,
            # and run each boundary with LF and CRLF line endings.
            skill_bytes = original_skill.read_bytes().replace(b"\r\n", b"\n")
            if len(skill_bytes) > 40_000:
                raise AssertionError(
                    f"shipped SKILL.md is already {len(skill_bytes)} bytes; "
                    "the boundary cases need it at or under 40000"
                )
            if skill_bytes.count(b"\n") < 100:
                raise AssertionError("shipped SKILL.md has too few lines to test CRLF")
            for size, expected in (
                (None, []),
                (40_000, []),
                (40_001, ["SKILL.md exceeds 40000 bytes: 40001 bytes"]),
            ):
                lf = skill_bytes if size is None else skill_bytes + b" " * (size - len(skill_bytes))
                for label, content in (("LF", lf), ("CRLF", lf.replace(b"\n", b"\r\n"))):
                    padded = scratch / f"skill-{size}-{label}.md"
                    padded.write_bytes(content)
                    module.SKILL = padded
                    errors = module.verify_markdown()
                    if errors != expected:
                        raise AssertionError(
                            f"SKILL.md byte cap, {label}, "
                            f"{size or 'shipped'} normalized bytes: expected {expected}, got {errors}"
                        )
            # Mixed endings normalize the same way and still fail past the cap.
            over = skill_bytes + b" " * (40_001 - len(skill_bytes))
            head, tail = over[: len(over) // 2], over[len(over) // 2 :]
            mixed = scratch / "skill-mixed.md"
            mixed.write_bytes(head.replace(b"\n", b"\r\n") + tail)
            module.SKILL = mixed
            if module.verify_markdown() != ["SKILL.md exceeds 40000 bytes: 40001 bytes"]:
                raise AssertionError(f"mixed line endings loosened the cap: {module.verify_markdown()}")
            print(
                "OK: SKILL.md passes at 40000 LF-normalized bytes and is rejected at "
                "40001, with LF, CRLF, and mixed line endings alike"
            )

            # The repository pins SKILL.md to LF, so the committed file is what
            # the cap measures. The gate asks git, so every rule form counts the
            # way git counts it; each case runs in a scratch repository.
            module.SKILL = original_skill
            if shutil.which("git") is None:
                print("SKIP: git not found; the SKILL.md LF pin cases were not run")
            else:
                pin = "skills/diagram-design/SKILL.md text eol=lf\n"
                original_root = module.GIT_ROOT
                for label, attributes, pinned in (
                    ("no pin", "*.png binary\n", False),
                    ("exact pin", pin, True),
                    ("glob pin", "*.md text eol=lf\n", True),
                    ("unrelated later rule", pin + "docs/*.md eol=crlf\n", True),
                    ("later eol=crlf", pin + "*.md eol=crlf\n", False),
                    ("later -text", pin + "skills/**/SKILL.md -text\n", False),
                    ("later binary", pin + "SKILL.md binary\n", False),
                    ("later unset eol", pin + "SKILL.md !eol\n", False),
                    ("later character class", pin + "SKILL.[m]d eol=crlf\n", False),
                    ("later negated class that misses", pin + "SKILL.[!m]d eol=crlf\n", True),
                    ("later class with an escaped bracket", pin + "SKILL.[m\\]]d eol=crlf\n", False),
                ):
                    repo = scratch / f"repo-{label.replace(' ', '-')}"
                    repo.mkdir()
                    subprocess.run(["git", "init", "-q", str(repo)], check=True)
                    (repo / ".gitattributes").write_text(attributes, encoding="utf-8")
                    module.GIT_ROOT = repo
                    try:
                        errors = module.verify_markdown()
                    finally:
                        module.GIT_ROOT = original_root
                    flagged = any(".gitattributes must pin" in error for error in errors)
                    if flagged == pinned:
                        raise AssertionError(f".gitattributes {label}: pinned={pinned}, got {errors}")
                # A contributor's own git configuration must not stand in for
                # the repository pin: a global `*.md text eol=lf` rule, and a
                # repo-local info/attributes rule, are both ignored.
                masked = scratch / "repo-masked-by-global-attributes"
                masked.mkdir()
                subprocess.run(["git", "init", "-q", str(masked)], check=True)
                (masked / ".gitattributes").write_text("*.png binary\n", encoding="utf-8")
                (masked / ".git" / "info").mkdir(parents=True, exist_ok=True)
                (masked / ".git" / "info" / "attributes").write_text("*.md text eol=lf\n", encoding="utf-8")
                global_attributes = scratch / "global-attributes"
                global_attributes.write_text("*.md text eol=lf\n", encoding="utf-8")
                global_config = scratch / "global-gitconfig"
                global_config.write_text(
                    f"[core]\n\tattributesFile = {global_attributes.as_posix()}\n", encoding="utf-8"
                )
                saved = os.environ.get("GIT_CONFIG_GLOBAL")
                os.environ["GIT_CONFIG_GLOBAL"] = str(global_config)
                module.GIT_ROOT = masked
                try:
                    errors = module.verify_markdown()
                finally:
                    module.GIT_ROOT = original_root
                    if saved is None:
                        os.environ.pop("GIT_CONFIG_GLOBAL", None)
                    else:
                        os.environ["GIT_CONFIG_GLOBAL"] = saved
                if not any(".gitattributes must pin" in error for error in errors):
                    raise AssertionError(f"global or local attributes masked a missing pin: {errors}")
                # Git hooks export GIT_DIR. An inherited repository location must
                # neither redirect the scratch repository nor let that
                # repository's local attributes mask the missing pin.
                masked_config = (masked / ".git" / "config").read_bytes()
                saved_dir = os.environ.get("GIT_DIR")
                os.environ["GIT_DIR"] = str(masked / ".git")
                module.GIT_ROOT = masked
                try:
                    errors = module.verify_markdown()
                finally:
                    module.GIT_ROOT = original_root
                    if saved_dir is None:
                        os.environ.pop("GIT_DIR", None)
                    else:
                        os.environ["GIT_DIR"] = saved_dir
                if not any(".gitattributes must pin" in error for error in errors):
                    raise AssertionError(f"an inherited GIT_DIR masked a missing pin: {errors}")
                if (masked / ".git" / "config").read_bytes() != masked_config:
                    raise AssertionError("the pin check modified the repository named by GIT_DIR")
                print("OK: .gitattributes must pin SKILL.md to LF, as git resolves it")
    finally:
        module.SKILL = original_skill


    # semantic-patterns.md states the visual-type count in its opening line; it
    # must agree with the counters.
    original_patterns = module.PATTERNS
    try:
        with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-patterns-") as temp_dir:
            stale_patterns = Path(temp_dir) / "semantic-patterns.md"
            count = module.VISUAL_TYPE_COUNT
            stale_patterns.write_text(
                original_patterns.read_text(encoding="utf-8").replace(
                    f"the {count} visual types", f"the {count - 1} visual types", 1
                ),
                encoding="utf-8",
            )
            module.PATTERNS = stale_patterns
            errors = module.verify_markdown()
            if not any("semantic-patterns.md must name" in e for e in errors):
                raise AssertionError(f"a stale type count in semantic-patterns.md was accepted: {errors}")
            # A later paragraph that still names the right count must not
            # stand in for a stale opening paragraph.
            stale_opening = Path(temp_dir) / "semantic-patterns-stale-opening.md"
            stale_opening.write_text(
                stale_patterns.read_text(encoding="utf-8")
                + f"\nThe {count} visual types each have a reference; the {count} visual types count.\n",
                encoding="utf-8",
            )
            module.PATTERNS = stale_opening
            errors = module.verify_markdown()
            if not any("semantic-patterns.md must name" in e for e in errors):
                raise AssertionError(f"a stale opening paragraph was accepted: {errors}")
        print("OK: semantic-patterns.md must state the enforced visual-type count")
    finally:
        module.PATTERNS = original_patterns

    # ADR 0002 must record the visual-type count the counters enforce, in date order.
    original_adr = module.ADR_0002
    try:
        with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-adr-") as temp_dir:
            adr_text = original_adr.read_text(encoding="utf-8")
            if module.verify_type_count_record():
                raise AssertionError(
                    f"shipped ADR 0002 failed: {module.verify_type_count_record()}"
                )
            amendments = [
                line for line in adr_text.splitlines()
                if line.startswith("**") and " the count is " in line
            ]
            stale = Path(temp_dir) / "adr-stale.md"
            stale.write_text(adr_text.replace(amendments[-1], ""), encoding="utf-8")
            module.ADR_0002 = stale
            errors = module.verify_type_count_record()
            if not any("latest amendment records the visual-type count" in e for e in errors):
                raise AssertionError(f"stale ADR 0002 count was accepted: {errors}")
            out_of_order = Path(temp_dir) / "adr-order.md"
            out_of_order.write_text(
                adr_text.replace(amendments[0], amendments[0].replace("**2026-", "**2027-", 1)),
                encoding="utf-8",
            )
            module.ADR_0002 = out_of_order
            errors = module.verify_type_count_record()
            if not any("not in date order" in e for e in errors):
                raise AssertionError(f"out-of-order ADR 0002 amendments were accepted: {errors}")
            untitled = Path(temp_dir) / "adr-untitled.md"
            untitled.write_text(
                adr_text.replace(
                    amendments[-1],
                    amendments[-1].replace("the count is ", "New type admitted, ", 1),
                ),
                encoding="utf-8",
            )
            module.ADR_0002 = untitled
            errors = module.verify_type_count_record()
            if not any("title it 'the count is N'" in e for e in errors):
                raise AssertionError(f"an unreadable amendment title was accepted: {errors}")
            last = amendments[-1]
            last_date = last[2:12]
            for label, replacement, needle in (
                ("short date", last.replace(last_date, "2026-10-1", 1), "not a YYYY-MM-DD date"),
                ("impossible date", last.replace(last_date, "2026-13-01", 1), "not a real date"),
                (
                    "nonsense pattern count",
                    last.replace("the count is", "the pattern count is", 1).replace(
                        "is " + str(module.VISUAL_TYPE_COUNT), "is banana", 1
                    ),
                    "title it 'the count is N'",
                ),
            ):
                broken = Path(temp_dir) / f"adr-{label.replace(' ', '-')}.md"
                broken.write_text(adr_text.replace(last, replacement), encoding="utf-8")
                module.ADR_0002 = broken
                errors = module.verify_type_count_record()
                if not any(needle in e for e in errors):
                    raise AssertionError(f"ADR 0002 {label} was accepted: {errors}")
        print(
            "OK: ADR 0002 must record the enforced visual-type count, in date order, "
            "with readable amendment titles"
        )
    finally:
        module.ADR_0002 = original_adr

    # A duplicated HTML/SVG id in the animated example must be rejected.
    with tempfile.TemporaryDirectory(prefix="verify-semantic-motion-example-") as temp_dir:
        source = module.EXAMPLE.read_text(encoding="utf-8")
        first_id_start = source.find(' id="')
        if first_id_start < 0:
            raise AssertionError("shipped example unexpectedly has no id attributes to duplicate")
        # Re-use an existing id value on a second, unrelated element to force a collision.
        quote_start = first_id_start + len(' id="')
        quote_end = source.find('"', quote_start)
        duplicated_id = source[quote_start:quote_end]
        insertion_point = source.rfind("</body>")
        if insertion_point < 0:
            raise AssertionError("shipped example unexpectedly has no </body> to anchor the test")
        broken = (
            source[:insertion_point]
            + f'<div id="{duplicated_id}"></div>'
            + source[insertion_point:]
        )
        broken_path = Path(temp_dir) / "duplicate-id.html"
        broken_path.write_text(broken, encoding="utf-8")
        errors = module.verify_example(broken_path)
        if not any("duplicate HTML/SVG IDs" in error for error in errors):
            raise AssertionError(f"duplicate id was accepted: {errors}")
        print("OK: duplicate HTML/SVG id in the animated example is rejected")

    print("All semantic-motion verifier tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
