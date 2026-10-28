#!/usr/bin/env python3
"""Adversarial cases for event-stage and typed-link validation."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-event-modeling.py"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-event-modeling.html"


def main() -> None:
    spec = importlib.util.spec_from_file_location("verify_event_modeling", VERIFIER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = EXAMPLE.read_text(encoding="utf-8")
    assert module.check(EXAMPLE) == []
    cases = (
        ('data-stage-order="2"', 'data-stage-order="1"', "stage order"),
        ('data-event-stage="STAGE-02"', 'data-event-stage="STAGE-01"', "duplicate stage ID"),
        ('data-diagram-role="timeframe"', 'data-diagram-role="unknown"', "stage role must be timeframe"),
        ('data-diagram-role="command"', 'data-diagram-role="unknown"', "command node role must be command"),
        ('data-diagram-role="event-link"', 'data-diagram-role="unknown"', "link role must be event-link"),
        ('data-from="CMD-01"', 'data-from="CMD-99"', "emits endpoints"),
        ('data-to="VIEW-01"', 'data-to="VIEW-99"', "projects endpoints"),
        ('data-event-rel="emits"', 'data-event-rel="unknown"', "unknown link"),
        ('>EVT-01</text>', '>EVT-99</text>', "is not printed"),
        ('>EVT-01</text>', '>Unprinted</text><desc>EVT-01</desc>', "is not printed"),
        ('>EVT-01</text>', '>Unprinted</text><defs><text>EVT-01</text></defs>', "is not printed"),
        ('data-diagram-role="event"', 'display="none" data-diagram-role="event"', "is not printed"),
        ('>READ MODEL</text>', '>Unlabeled</text><desc>READ MODEL</desc>', "missing visible read model label"),
        ('data-event-id="CMD-01"', 'data-event-id=""', "invalid or duplicate command ID"),
    )
    with tempfile.TemporaryDirectory() as directory:
        candidate = Path(directory) / "candidate.html"
        for old, new, expected in cases:
            assert old in source, old
            candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
            errors = module.check(candidate)
            assert any(expected in error for error in errors), (old, errors)
    print("OK event modeling: ordered stages, typed roles, and link endpoints")


if __name__ == "__main__":
    main()
