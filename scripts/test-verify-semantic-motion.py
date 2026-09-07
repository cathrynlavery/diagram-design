#!/usr/bin/env python3
"""Regression tests for verify-semantic-motion.py.

Covers the two entry points (verify_markdown, verify_example) against the
shipped skill docs / animated example, plus a handful of adversarial cases
that mirror the pattern used by test-verify-docs-sync.py and
test-verify-motion.py for the other verifiers in this repo.
"""

from __future__ import annotations

import importlib.util
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

            # Dropping one of the seven named patterns must be rejected.
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
    finally:
        module.SKILL = original_skill

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
