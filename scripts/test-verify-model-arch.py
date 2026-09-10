#!/usr/bin/env python3
"""Adversarial tests for the model-architecture census verifier.

Every check here is a mutation of a diagram that still renders perfectly:
the failures this script exists to catch are arithmetic ones, invisible to
the eye and to every other linter in the repository.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-model-arch.py"
SHIPPED = [
    ROOT / "skills/diagram-design/assets/example-model-arch.html",
    ROOT / "skills/diagram-design/assets/example-model-arch-dark.html",
    ROOT / "skills/diagram-design/assets/example-model-arch-full.html",
]


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_model_arch", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclass resolves deferred annotations by looking the module up in
    # sys.modules, so register it before exec_module runs the class bodies.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SVG_HEAD = (
    '<svg viewBox="0 0 400 300" xmlns="http://www.w3.org/2000/svg" role="img" '
    'aria-labelledby="t-title t-desc">'
    '<title id="t-title">T</title><desc id="t-desc">T.</desc>'
)


def document(body: str) -> str:
    return f"<!DOCTYPE html><html><body>{SVG_HEAD}{body}</svg></body></html>"


def panel(name: str = "encoder", depth: str = "4", rng: str = "0-3") -> str:
    return (
        f'<rect x="0" y="0" width="200" height="200" rx="8" data-stack="{name}" '
        f'data-depth="{depth}" data-layer-range="{rng}"/>'
    )


def group(gid: str, repeat: str, parent: str = "") -> str:
    return (
        f'<rect x="8" y="8" width="180" height="90" rx="8" data-group-id="{gid}" '
        f'data-repeat="{repeat}" data-group-parent="{parent}"/>'
    )


def chip(gid: str, text: str) -> str:
    return f'<text x="190" y="50" data-repeat-for="{gid}">{text}</text>'


def layer(kind: str, stack: str = "encoder", grp: str = "") -> str:
    return (
        f'<rect x="16" y="16" width="160" height="36" rx="4" data-layer-kind="{kind}" '
        f'data-layer-stack="{stack}" data-layer-group="{grp}"/>'
    )


# A plan that reconciles: 2x[local] + 2x[full] = 4 layers.
def sound() -> str:
    return (
        panel()
        + group("g-a", "2")
        + chip("g-a", "×2")
        + layer("local", grp="g-a")
        + layer("ffn", grp="g-a")
        + group("g-b", "2")
        + chip("g-b", "×2")
        + layer("full", grp="g-b")
        + layer("ffn", grp="g-b")
    )


# Two stacks, each repeating a group of its own: 2x[local] and 2x[full].
def two_stacks() -> str:
    return (
        panel("encoder", "2", "0-1")
        + panel("decoder", "2", "2-3")
        + group("g-enc", "2")
        + chip("g-enc", "×2")
        + layer("local", stack="encoder", grp="g-enc")
        + group("g-dec", "2")
        + chip("g-dec", "×2")
        + layer("full", stack="decoder", grp="g-dec")
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
                f"{label}: expected {expect_findings} finding(s), got {len(findings)}: {findings}"
            )

    check("a plan whose multipliers reconcile passes", document(sound()), 0)

    check(
        "a diagram of another type is not a model-architecture diagram",
        document('<rect x="0" y="0" width="40" height="10" fill="#f5f5f5"/>'),
        0,
    )

    # The headline failure: the drawing is unchanged, the network is not.
    check(
        "a repeat that no longer reaches the declared depth is caught",
        document(sound().replace('data-group-id="g-b" data-repeat="2"', 'data-group-id="g-b" data-repeat="1"')),
        2,  # census 4 -> 3, and the ×2 chip now disagrees with the group
    )

    check(
        "a chip that disagrees with its own group is caught",
        document(sound().replace(chip("g-b", "×2"), chip("g-b", "×3"))),
        1,
    )

    check(
        "an ASCII x in a chip is read as a multiplier, not as a typo",
        document(sound().replace(chip("g-b", "×2"), chip("g-b", "x2"))),
        0,
    )

    check(
        "chip text split across tspans is still compared whole",
        document(
            sound().replace(
                chip("g-b", "×2"),
                '<text x="190" y="50" data-repeat-for="g-b"><tspan>×</tspan><tspan>3</tspan></text>',
            )
        ),
        1,  # reads ×3 against a group declaring 2 -- not "unparseable"
    )

    check(
        "an unlabelled repeat group is invisible depth",
        document(sound().replace(chip("g-b", "×2"), "")),
        1,
    )

    check(
        "a chip pointing at no group is caught",
        document(sound() + chip("g-ghost", "×2")),
        1,
    )

    check(
        "nesting past one level is refused",
        document(
            panel(depth="8", rng="0-7")
            + group("g-a", "2")
            + chip("g-a", "×2")
            + group("g-b", "2", parent="g-a")
            + chip("g-b", "×2")
            + group("g-c", "2", parent="g-b")
            + chip("g-c", "×2")
            + layer("full", grp="g-c")
        ),
        1,
    )

    check(
        "a group cycle terminates instead of hanging",
        document(
            panel()
            + group("g-a", "2", parent="g-b")
            + chip("g-a", "×2")
            + group("g-b", "2", parent="g-a")
            + chip("g-b", "×2")
            + layer("full", grp="g-a")
        ),
        4,  # a cycle report per group, one per block, plus the broken census
    )

    check(
        "a block naming a group that does not exist is caught",
        document(sound().replace('data-layer-group="g-b"', 'data-layer-group="g-typo"', 1)),
        2,  # unresolved group, and the census it drops out of
    )

    check(
        "a block naming a stack with no panel is caught",
        document(sound().replace('data-layer-stack="encoder"', 'data-layer-stack="decoder"', 1)),
        2,  # unknown stack, and the census that block no longer feeds
    )

    check(
        "a misspelled layer kind is refused rather than silently uncounted",
        document(sound().replace('data-layer-kind="ffn"', 'data-layer-kind="fnn"', 1)),
        1,
    )

    check(
        "the FFN half of a layer never counts as a layer of its own",
        document(sound().replace('data-layer-kind="ffn"', 'data-layer-kind="full"', 1)),
        1,  # census 4 -> 6
    )

    check(
        "a layer range that disagrees with the declared depth is caught",
        document(sound().replace('data-layer-range="0-3"', 'data-layer-range="0-4"')),
        1,
    )

    check(
        "a backwards layer range is caught",
        document(sound().replace('data-layer-range="0-3"', 'data-layer-range="3-0"')),
        1,
    )

    check(
        "a non-numeric repeat is refused, not coerced",
        document(sound().replace('data-repeat="2"', 'data-repeat="two"', 1)),
        3,  # unparseable repeat, the broken census, and the chip mismatch
    )

    # `03` and `3.0` would each read as three to a coercing parser and as a
    # mismatch to the chip comparison. Refuse them at the source instead.
    check(
        "a zero-padded repeat is refused rather than normalised",
        document(sound().replace('data-repeat="2"', 'data-repeat="02"', 1)),
        3,  # unparseable repeat, the broken census, and the chip mismatch
    )

    check(
        "a zero repeat is refused",
        document(sound().replace('data-repeat="2"', 'data-repeat="0"', 1)),
        3,
    )

    check(
        "a duplicate group id is caught",
        document(sound().replace('data-group-id="g-b"', 'data-group-id="g-a"')),
        4,  # the duplicate, the block and chip now pointing at nothing, and the census
    )

    check(
        "a duplicate stage panel is caught",
        document(sound() + panel()),
        1,
    )

    check(
        "markup inside a comment is never scanned as a live group",
        document(sound() + "<!-- " + group("g-ghost", "9") + " -->"),
        0,
    )

    check(
        "a blank data-layer-stack is caught",
        document(sound().replace('data-layer-stack="encoder"', 'data-layer-stack=""', 1)),
        2,  # blank stack, and the census that block no longer feeds
    )

    # Group ownership. `by_gid` is one flat namespace across every stack, so
    # each of these mutations reconciles perfectly against both panels'
    # data-depth while the repeat group it leans on belongs to the other one.
    check(
        "two stacks each repeating their own group pass",
        document(two_stacks()),
        0,
    )

    check(
        "a stack borrowing another stack's repeat group is caught",
        document(
            panel("encoder", "2", "0-1")
            + panel("decoder", "4", "2-5")
            + group("g-enc", "2")
            + chip("g-enc", "×2")
            + layer("local", stack="encoder", grp="g-enc")
            + group("g-dec", "2")
            + chip("g-dec", "×2")
            + layer("full", stack="decoder", grp="g-dec")
            + layer("full", stack="decoder", grp="g-enc")
        ),
        1,  # both censuses still reconcile: 2 = 2 and 2 + 2 = 4
    )

    check(
        "a group nested under another stack's group is caught",
        document(
            panel("encoder", "2", "0-1")
            + panel("decoder", "4", "2-5")
            + group("g-enc", "2")
            + chip("g-enc", "×2")
            + layer("local", stack="encoder", grp="g-enc")
            + group("g-dec", "2", parent="g-enc")
            + chip("g-dec", "×2")
            + layer("full", stack="decoder", grp="g-dec")
        ),
        1,  # encoder 2 = 2 and decoder 2 × 2 = 4 both reconcile
    )

    check(
        "a group nested inside its own stack's parent is not an ownership error",
        document(
            panel("encoder", "6", "0-5")
            + group("g-outer", "3")
            + chip("g-outer", "×3")
            + group("g-inner", "2", parent="g-outer")
            + chip("g-inner", "×2")
            + layer("full", stack="encoder", grp="g-inner")
        ),
        0,
    )

    for path in SHIPPED:
        if not path.is_file():
            failures.append(f"missing shipped example: {path}")
            continue
        findings = module.check(path)
        if findings:
            failures.append(f"{path.name} should pass its own census: {findings}")

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All model architecture census tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
