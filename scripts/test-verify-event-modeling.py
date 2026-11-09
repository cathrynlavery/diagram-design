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
    first_group = '<g data-event-stage="STAGE-01"'
    second_group = '<g data-event-stage="STAGE-02"'
    cases = (
        (first_group, first_group.replace("<g ", '<g display="none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g style="display:none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g opacity="0" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g transform="scale(0)" '), "event stage must not use transform"),
        (first_group, first_group.replace("<g ", '<g style="transform:scale(0)" '), "event stage must not use transform"),
        (first_group, first_group.replace("<g ", '<g style="scale:0" '), "event stage must not use transform"),
        ("</style>", "g[data-event-stage]{display:none}</style>", "stylesheet must not select data-event-stage"),
        ("</style>", "g[*|data-event-stage]{display:none}</style>", "stylesheet must not select data-event-stage"),
        ("</style>", "g[|data-event-stage]{display:none}</style>", "stylesheet must not select data-event-stage"),
        ("</style>", r"g[data-\65 vent-stage]{display:none}</style>", "stylesheet must not select data-event-stage"),
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
        failures = []
        for old, new, expected in cases:
            assert old in source, old
            candidate.write_text(source.replace(old, new, 1), encoding="utf-8")
            errors = module.check(candidate)
            if not any(expected in error for error in errors):
                failures.append((new, expected, errors))
        assert first_group in source and second_group in source
        wrapped = source.replace(first_group, '<g display="none">' + first_group, 1)
        wrapped = wrapped.replace(second_group, "</g>" + second_group, 1)
        candidate.write_text(wrapped, encoding="utf-8")
        errors = module.check(candidate)
        if not any("STAGE-01:" in error and "is not printed" in error for error in errors):
            failures.append(("hidden SVG wrapper", "is not printed", errors))
        assert not failures, failures

        # A comment and an escaped bracket in a class name are not attribute selectors.
        inert_css = r"/* g[data-event-stage]{display:none} */ .literal\[data-event-stage\]{display:none}"
        assert "</style>" in source
        candidate.write_text(source.replace("</style>", inert_css + "</style>", 1), encoding="utf-8")
        assert module.check(candidate) == []
    print("OK event modeling: ordered stages, typed roles, and link endpoints")


if __name__ == "__main__":
    main()
