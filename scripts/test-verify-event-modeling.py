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
        # Arrow geometry must run from the declared command or event cell to its target cell.
        speck = 'd="M 0 0 H 1"'
        geometry_cases = (
            ("every arrow a speck", re.sub(r' d="M [^"]*"', " " + speck, source)),
            ("one shaft a speck", source.replace('d="M 224 302 V 363"', speck, 1)),
            ("one arrowhead a speck", source.replace('d="M 218 360 L 224 368 L 230 360"', speck, 1)),
            ("shaft shifted to the next stage", source.replace('d="M 224 302 V 363"', 'd="M 588 302 V 363"', 1)),
            ("shaft from the wrong row", source.replace('d="M 224 302 V 363"', 'd="M 224 464 V 525"', 1)),
            ("shaft stops short", source.replace('d="M 224 302 V 363"', 'd="M 224 302 V 320"', 1)),
        )
        shaft, head = 'd="M 224 302 V 363"', 'd="M 218 360 L 224 368 L 230 360"'
        head_path = '<path d="M 218 360 L 224 368 L 230 360" fill="none" stroke="#4f5d75" stroke-width="2"/>'
        source_head = '<path d="M 218 307 L 224 299 L 230 307" fill="none" stroke="#4f5d75" stroke-width="2"/>'
        assert head_path in source

        def shift_cell(text: str, cell_id: str, offset: int) -> str:
            start = text.index(f'data-event-id="{cell_id}"')
            end = text.index("</g>", start)
            body = re.sub(r' y="(\d+)"', lambda m: f' y="{int(m[1]) + offset}"', text[start:end])
            return text[:start] + body + text[end:]

        swapped = shift_cell(shift_cell(source, "EVT-01", 162), "VIEW-01", -162)
        swapped = swapped.replace(shaft, 'd="M 224 302 V 525"', 1).replace(head, 'd="M 218 522 L 224 530 L 230 522"', 1)
        geometry_cases += (
            ("head at the source end", source.replace(head, 'd="M 218 307 L 224 299 L 230 307"', 1)),
            ("heads at both ends", source.replace(head_path, head_path + source_head, 1)),
            ("no head", source.replace(head_path, "", 1)),
            ("underscore digits", source.replace(shaft, 'd="M 2_24 302 V 363"', 1)),
            ("Arabic-Indic digits", source.replace(shaft, 'd="M \u0662\u0662\u0664 302 V 363"', 1)),
            # Browsers stop at the invalid number, so only "M 224 302" draws.
            ("Arabic-Indic digits before a valid number", source.replace(shaft, 'd="M 224 302 V \u0663\u0666\u0663 363"', 1)),
            ("shaft crosses a third cell", swapped),
            ("reversed head", source.replace(head, 'd="M 219 366 L 224 358 L 229 366"', 1)),
            ("straight-line head", source.replace(head, 'd="M 224 356 L 224 368"', 1)),
            ("collinear head", source.replace(head, 'd="M 218 366 L 224 366 L 230 366"', 1)),
            ("head wings on one side", source.replace(head, 'd="M 218 360 L 224 368 L 222 360"', 1)),
        )
        for name, mutated in geometry_cases:
            assert mutated != source, name
            candidate.write_text(mutated, encoding="utf-8")
            errors = module.check(candidate)
            if not any(error.startswith("STAGE-01: emits arrow must run from") for error in errors):
                failures.append((name, "STAGE-01: emits arrow must run from", errors))

        def stage_span(text: str, stage_id: str) -> tuple[int, int]:
            start = text.index(f'<g data-event-stage="{stage_id}"')
            following = text.find("<g data-event-stage=", start + 1)
            return start, following if following != -1 else text.index('<line x1="64" y1="666"')

        def shift_x(text: str, stage_id: str, offset: int) -> str:
            start, end = stage_span(text, stage_id)

            def path(match: re.Match[str]) -> str:
                tokens, command, position = [], "", 0
                for token in match[1].split():
                    if token.isalpha():
                        command, position = token, 0
                    else:
                        if command == "H" or (command in "ML" and position % 2 == 0):
                            token = str(int(token) + offset)
                        position += 1
                    tokens.append(token)
                return f' d="{" ".join(tokens)}"'

            body = re.sub(r' (x|x1|x2)="(\d+)"', lambda m: f' {m[1]}="{int(m[2]) + offset}"', text[start:end])
            return text[:start] + re.sub(r' d="(M [^"]*)"', path, body) + text[end:]

        columns_swapped = shift_x(shift_x(source, "STAGE-01", 364), "STAGE-02", -364)
        rows_swapped = shift_cell(shift_cell(source, "CMD-01", 162), "EVT-01", -162)
        for old, new in (
            (shaft, 'd="M 224 374 V 313"'), (head, 'd="M 218 316 L 224 308 L 230 316"'),
            ('d="M 224 464 V 525"', 'd="M 405 257 H 411 V 581 H 405"'),
            ('d="M 218 522 L 224 530 L 230 522"', 'd="M 409 575 L 403 581 L 409 587"'),
        ):
            assert old in rows_swapped
            rows_swapped = rows_swapped.replace(old, new, 1)
        for name, mutated, expected in (
            ("stage columns swapped", columns_swapped, "stage columns must run left to right"),
            ("command and event rows swapped", rows_swapped, "lanes must run command, event, read model"),
            ("command and event rows swapped", rows_swapped, "command cells must share one lane"),
        ):
            assert mutated != source, name
            candidate.write_text(mutated, encoding="utf-8")
            errors = module.check(candidate)
            if not any(expected in error for error in errors):
                failures.append((name, expected, errors))
        assert not failures, failures

        # A comment and an escaped bracket in a class name are not attribute selectors.
        inert_css = r"/* g[data-event-stage]{display:none} */ .literal\[data-event-stage\]{display:none}"
        assert "</style>" in source
        candidate.write_text(source.replace("</style>", inert_css + "</style>", 1), encoding="utf-8")
        assert module.check(candidate) == []
    print("OK event modeling: ordered stages, typed roles, and link endpoints")


if __name__ == "__main__":
    main()
