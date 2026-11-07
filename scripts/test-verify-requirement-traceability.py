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
    cases = (
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
        for old, new, expected in cases:
            assert old in source, old
            candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
            errors = verifier.check(candidate)
            assert any(expected in error for error in errors), (old, errors)
    print("OK requirement traceability: source, IDs, typed links, and explicit gaps")


if __name__ == "__main__":
    main()
