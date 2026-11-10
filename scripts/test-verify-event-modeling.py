#!/usr/bin/env python3
"""Adversarial cases for event-stage and typed-link validation."""

from __future__ import annotations

import importlib.util
import re
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
    label_tag = re.search(r'<text\b[^>]*>(?=CMD-01</text>)', source)
    assert label_tag is not None
    label_tag = label_tag[0]
    cases = (
        *((first_group, first_group.replace("<g ", f"<g {attributes} "), "hidden or too faint")
          for attributes in (
              'style="display:none !important"', 'style="opacity:0 !important"',
              'opacity="0.00"', 'opacity="0%"', 'style="opacity:.0"', 'opacity="0.01"',
              'display="NONE"', 'display=" none"', 'visibility="collapse"',
          )),
        *((first_group, first_group.replace("<g ", f"<g {attributes} "), "unsupported SVG")
          for attributes in (
              'style="filter:opacity(0)"', 'clip-path="inset(50%)"',
              'clip-path="url(#empty)"', 'mask="url(#empty)"',
          )),
        *((label_tag, label_tag.replace('fill="#4f5d75"', f'fill="{paint}"').replace('fill="#2e5aa8"', f'fill="{paint}"'),
           "house ink")
          for paint in ("rgba(0,0,0,0)", "#0000", "#f5f5f5")),
        (label_tag, re.sub(r'font-size="[^"]+"', 'font-size="0"', label_tag), "font size"),
        ('data-event-kind="command"', 'transform="scale(0)" data-event-kind="command"', "unsupported SVG"),
        *((label_tag, motion + label_tag, "unsupported SVG")
          for motion in ('<set attributeName="display" to="none"/>',
                         '<animate attributeName="opacity" to="0" fill="freeze"/>')),
        ("</svg>", '<rect width="1200" height="720" fill="#f5f5f5"/></svg>', "cover"),
        ("</svg>", '<line x1="0" x2="1200" y1="360" y2="360" stroke="#f5f5f5" stroke-width="720"/></svg>', "cover"),
        (first_group, first_group.replace("<g ", r'<g style="display:n\6f ne" '), "hidden or too faint"),
        *((("</style>", rule + "</style>", "stylesheet")
          for rule in (
              '[data-event-kind]{display:none}', 'g g{display:none}', 'svg>g{display:none}',
              '@media screen{svg g g{opacity:0}}', 'g text{fill:transparent!important}',
              'text{visibility:hidden}', 'svg{display:none!important}',
          ))),
        ('d="M 224 302 V 363"', 'd="M 0 0"', "visible arrow"),
        ('data-event-rel="emits"',  'display="none" data-event-rel="emits"', "visible arrow"),
        ("</style>", "[data-event-rel]{display:none}</style>", "stylesheet"),
        (first_group, first_group.replace("<g ", '<g display="none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g style="display:none" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g opacity="0" '), "is not printed"),
        (first_group, first_group.replace("<g ", '<g transform="scale(0)" '), "unsupported SVG"),
        (first_group, first_group.replace("<g ", '<g style="transform:scale(0)" '), "unsupported SVG"),
        (first_group, first_group.replace("<g ", '<g style="scale:0" '), "unsupported SVG"),
        ("</style>", "g[data-event-stage]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", "g[*|data-event-stage]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", "g[|data-event-stage]{display:none}</style>", "stylesheet must not select SVG"),
        ("</style>", r"g[data-\65 vent-stage]{display:none}</style>", "stylesheet must not select SVG"),
        ('data-stage-order="2"', 'data-stage-order="1"', "stage order"),
        ('data-event-stage="STAGE-02"', 'data-event-stage="STAGE-01"', "duplicate stage ID"),
        ('data-diagram-role="timeframe"', 'data-diagram-role="unknown"', "stage role must be timeframe"),
        ('data-diagram-role="command"', 'data-diagram-role="unknown"', "command node role must be command"),
        ('data-diagram-role="event-link"', 'data-diagram-role="unknown"', "link role must be event-link"),
        ('data-from="CMD-01"', 'data-from="CMD-99"', "emits endpoints"),
        ('data-to="VIEW-01"', 'data-to="VIEW-99"', "projects endpoints"),
        ('data-event-rel="emits"',  'data-event-rel="unknown"', "unknown link"),
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
            assert old in source and old != new, (old, new)
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
        transformed = wrapped.replace('display="none"', 'transform="scale(0)"', 1)
        candidate.write_text(transformed, encoding="utf-8")
        errors = module.check(candidate)
        if not any("unsupported SVG property on g: transform" in error for error in errors):
            failures.append(("transformed SVG wrapper", "unsupported SVG", errors))
        boxes = list(re.finditer(r"<rect\b[^>]*/>", source))
        assert len(boxes) > 2
        last_box = boxes[-1]
        cover = '<rect x="0" y="0" width="1200" height="720" fill="#f5f5f5"/>'
        candidate.write_text(source[:last_box.start()] + cover + source[last_box.end():], encoding="utf-8")
        errors = module.check(candidate)
        if not any("overlaps another cell" in error for error in errors):
            failures.append(("cross-cell cover", "overlaps another cell", errors))
        assert not failures, failures

        # A comment and an escaped bracket in a class name are not attribute selectors.
        inert_css = r"/* g[data-event-stage]{display:none} */ .literal\[data-event-stage\]{display:none}"
        assert "</style>" in source
        candidate.write_text(source.replace("</style>", inert_css + "</style>", 1), encoding="utf-8")
        assert module.check(candidate) == []
    print("OK event modeling: ordered stages, typed roles, and link endpoints")


if __name__ == "__main__":
    main()
