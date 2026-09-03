#!/usr/bin/env python3
"""Adversarial tests for the block registry verifier (verify-block-registry.py)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-block-registry.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_block_registry", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass's deferred-annotation resolution looks the module up by name
    # in sys.modules, so it must be registered before exec_module runs it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SVG_HEAD = (
    '<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="t-title t-desc">'
    "<title id=\"t-title\">T</title><desc id=\"t-desc\">T.</desc>"
)


def document(body: str) -> str:
    return f"<!DOCTYPE html><html><body>{SVG_HEAD}{body}</svg></body></html>"


def block(block_id: str, parent: str | None = None, name: str | None = "Name", extra: str = "") -> str:
    parent_attr = f' data-block-parent="{parent}"' if parent is not None else ""
    name_attr = f' data-block-name="{name}"' if name is not None else ""
    return (
        f'<rect x="0" y="0" width="160" height="48" rx="6" data-block-id="{block_id}"'
        f"{parent_attr}{name_attr}{extra}/>"
    )


def main() -> int:
    module = load_verifier()
    failures: list[str] = []

    def check(label: str, source: str, expect_findings: int) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            findings = module.check(candidate)
        if len(findings) != expect_findings:
            failures.append(
                f"{label}: expected {expect_findings} finding(s), got "
                f"{len(findings)}: {findings}"
            )
        else:
            print(f"OK: {label}")

    # A single root block, no parent attribute at all, is legal.
    check("single root block", document(block("FC3-001")), 0)

    # A valid parent-child pair, parent resolves to a real sibling id.
    check(
        "valid parent-child pair",
        document(block("FC3-001") + block("FC3-001-01", parent="FC3-001")),
        0,
    )

    # A valid three-level chain, root -> child -> grandchild.
    check(
        "valid three-level chain",
        document(
            block("FC3-001")
            + block("FC3-001-01", parent="FC3-001")
            + block("FC3-001-01-01", parent="FC3-001-01")
        ),
        0,
    )

    # Two children sharing one valid parent is ordinary breadth, not a defect.
    check(
        "shared parent, two children",
        document(
            block("FC3-001")
            + block("FC3-001-01", parent="FC3-001")
            + block("FC3-001-02", parent="FC3-001")
        ),
        0,
    )

    # Two blocks copy-pasted with the same id is the defect this exists to catch.
    check(
        "duplicate id",
        document(block("FC3-001") + block("FC3-001", name="Renamed")),
        1,
    )

    # A parent attribute pointing at an id absent from the file — a renamed or
    # deleted parent left a dangling reference behind.
    check(
        "orphan parent reference",
        document(block("FC3-001-01", parent="FC3-999")),
        1,
    )

    # A block whose own id is its parent — the smallest possible cycle.
    check(
        "self-parent cycle",
        document(block("FC3-001", parent="FC3-001")),
        1,
    )

    # Two blocks whose parents point at each other — no root either could reach.
    check(
        "two-node cycle",
        document(
            block("FC3-001", parent="FC3-002") + block("FC3-002", parent="FC3-001")
        ),
        1,
    )

    # An id with no data-block-name attribute at all.
    check(
        "missing name attribute",
        document(block("FC3-001", name=None)),
        1,
    )

    # data-block-name present but empty is the same defect as absent.
    check(
        "empty name attribute",
        document(block("FC3-001", name="")),
        1,
    )

    # data-block-name present but whitespace-only is the same defect as empty.
    check(
        "whitespace-only name attribute",
        document(block("FC3-001", name="   ")),
        1,
    )

    # data-block-id present but empty must not silently satisfy itself as a
    # valid, resolvable identifier.
    check(
        "empty id attribute",
        document(block("")),
        1,
    )

    # data-block-id present but whitespace-only is the same defect as empty.
    check(
        "whitespace-only id attribute",
        document(block("   ")),
        1,
    )

    # A blank id must never act as a resolvable identifier. Two otherwise-valid
    # blocks joined only by "" used to report 0 findings — a coherent tree
    # built from an empty string. Now both broken attributes are reported: the
    # blank id itself, and the child's blank data-block-parent as unresolved.
    check(
        "blank id never satisfies a blank parent",
        document(block("") + block("FC3-001", parent="")),
        2,
    )

    # data-block-parent present but empty is a dangling reference, not root;
    # absent-means-root is the only root convention (export-registry.md).
    check(
        "blank parent attribute is unresolved",
        document(block("FC3-001") + block("FC3-001-01", parent="")),
        1,
    )

    # A diagram that doesn't use the pattern at all has no data-block-id
    # anywhere — legal; most Tree diagrams will look like this.
    check(
        "no blocks in file",
        document('<rect x="0" y="0" width="160" height="48" rx="6"/>'),
        0,
    )

    # A node carrying an unrelated data-* attribute, but no data-block-id, is
    # not a block and must not be collected as one.
    check(
        "unrelated data attribute is not a block",
        document('<rect x="0" y="0" width="160" height="48" rx="6" data-foo="bar"/>'),
        0,
    )

    # The full optional metadata set (input/output/constraint/assumption/impl)
    # must parse cleanly without tripping any check.
    check(
        "full optional metadata set present",
        document(
            block(
                "FC3-001",
                extra=(
                    ' data-block-input="clip list" data-block-output="timeline state"'
                    ' data-block-constraint="single writer" data-block-assumption="60fps"'
                    ' data-block-impl="src/timeline/engine.ts"'
                ),
            )
        ),
        0,
    )

    # Two unrelated root blocks (no shared ancestor) in one file — a diagram
    # can legally show more than one top-level block.
    check(
        "multiple independent trees",
        document(block("FC3-001") + block("FC3-002")),
        0,
    )

    # A literal '>' inside a quoted attribute value, positioned BEFORE
    # data-block-id in the tag, is valid HTML and must not truncate the tag
    # match — a naive [^>]* match would lose data-block-id entirely and the
    # block would silently vanish (0 findings AND 0 blocks, a false-clean
    # pass on a file that has a real, valid block).
    check(
        "literal greater-than before id does not truncate the tag",
        document(
            '<rect data-block-constraint="output > input" data-block-id="FC3-001" '
            'data-block-name="X" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # Same hazard with the '>' positioned after id/name — must also survive;
    # this ordering happened to work even before the fix, so it guards
    # against a regression that only re-breaks the before-id ordering above.
    check(
        "literal greater-than after id does not truncate the tag",
        document(
            '<rect data-block-id="FC3-001" data-block-name="X" '
            'data-block-constraint="output > input" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        0,
    )

    # Single-quoted attribute values are valid HTML; the parser must not
    # silently see zero blocks on a file that uses them.
    check(
        "single-quoted attribute values are recognized",
        document(
            "<rect data-block-id='FC3-001' data-block-name='X' "
            "x='0' y='0' width='160' height='48' rx='6'/>"
        ),
        0,
    )

    # Mixed quoting within one tag -- an adversarial author (or a hand-edit)
    # might quote some attributes one way and others another; both must be
    # read, not just whichever style the parser happens to expect.
    check(
        "mixed quoting styles in one tag",
        document(
            '<rect data-block-id="FC3-001" data-block-name=\'X\' '
            'data-block-parent="FC3-000" x="0" y="0" width="160" height="48" rx="6"/>'
        ),
        1,  # data-block-parent references FC3-000, which this document never defines
    )

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All block registry tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
