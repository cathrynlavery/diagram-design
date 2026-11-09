#!/usr/bin/env python3
"""Adversarial cases for requirement traceability source and link checks."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-requirement-traceability.py"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-requirement-traceability.html"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_requirement_traceability", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    verifier = load_verifier()
    source = EXAMPLE.read_text(encoding="utf-8")
    assert verifier.check(EXAMPLE) == []
    first_group = '<g data-trace-row="REQ-01"'
    second_group = '<g data-trace-row="REQ-02"'
    cases = (
        (first_group, first_group.replace("<g ", '<g display="none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g style="display:none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g opacity="0" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g transform="scale(0)" '), "requirement row must not use transform"),
        (first_group, first_group.replace("<g ", '<g style="transform:scale(0)" '), "requirement row must not use transform"),
        (first_group, first_group.replace("<g ", '<g style="scale:0" '), "requirement row must not use transform"),
        ("</style>", "g[data-trace-row]{display:none}</style>", "stylesheet must not select data-trace-row"),
        ("</style>", "g[*|data-trace-row]{display:none}</style>", "stylesheet must not select data-trace-row"),
        ("</style>", "g[|data-trace-row]{display:none}</style>", "stylesheet must not select data-trace-row"),
        ("</style>", r"g[data-\74 race-row]{display:none}</style>", "stylesheet must not select data-trace-row"),
        ('data-trace-source="Review brief §1"', 'data-trace-source=""', "missing source reference"),
        ('data-trace-row="REQ-02"', 'data-trace-row="REQ-01"', "duplicate requirement row ID"),
        ('data-trace-from="DES-01"', 'data-trace-from="DES-99"', "source does not resolve"),
        ('data-trace-rel="satisfies"', 'data-trace-rel="unknown"', "unknown relationship"),
        ('data-trace-missing="true"', 'data-trace-missing="false"', "source does not resolve"),
        ('>REQ-01</text>', '>REQ-99</text>', "is not printed"),
        ('>REQ-01</text>', '>Unprinted</text><desc>REQ-01</desc>', "is not printed"),
        ('>REQ-01</text>', '>Unprinted</text><defs><text>REQ-01</text></defs>', "is not printed"),
        ('data-diagram-role="coverage-gap"', 'display="none" data-diagram-role="coverage-gap"', "needs a visible gap label"),
        ('data-source-ref="Review brief §1"', 'data-source-ref="Review brief §9"', "source reference does not match"),
        ('>Review brief §1</text>', '>Uncited</text>', "source citation is not printed"),
    )
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "candidate.html"
        failures = []
        for old, new, expected in cases:
            assert old in source, old
            candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
            errors = verifier.check(candidate)
            if not any(expected in error for error in errors):
                failures.append((new, expected, errors))
        assert first_group in source and second_group in source
        wrapped = source.replace(first_group, '<g display="none">' + first_group, 1)
        wrapped = wrapped.replace(second_group, "</g>" + second_group, 1)
        candidate.write_text(wrapped, encoding="utf-8")
        errors = verifier.check(candidate)
        if not any("REQ-01:" in error and "is not printed" in error for error in errors):
            failures.append(("hidden SVG wrapper", "is not printed", errors))
        assert not failures, failures

        # A comment and an escaped bracket in a class name are not attribute selectors.
        inert_css = r"/* g[data-trace-row]{display:none} */ .literal\[data-trace-row\]{display:none}"
        assert "</style>" in source
        candidate.write_text(source.replace("</style>", inert_css + "</style>", 1), encoding="utf-8")
        assert verifier.check(candidate) == []
    print("OK requirement traceability: source, IDs, typed links, and explicit gaps")


if __name__ == "__main__":
    main()
