#!/usr/bin/env python3
"""Adversarial tests for the packaged skill self-check (self_check.py)."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF_CHECK = ROOT / "skills/diagram-design/scripts/self_check.py"
ASSET_DIR = ROOT / "skills/diagram-design/assets"
TEMPLATE = ASSET_DIR / "template-motion.html"
EXAMPLE = ASSET_DIR / "example-policy-trace-animated.html"
STATIC_EXAMPLE = ASSET_DIR / "example-architecture.html"


def load_self_check():
    spec = importlib.util.spec_from_file_location("self_check", SELF_CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_self_check()
    failures: list[str] = []

    def check_pass(label: str, path: Path) -> None:
        errors = module.verify(path)
        if errors:
            failures.append(f"{label}: expected pass, got {errors}")
        else:
            print(f"OK: {label} passes")

    def check_fail(label: str, source: str, needle: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            errors = module.verify(candidate)
        if not any(needle in error for error in errors):
            failures.append(f"{label}: expected an error containing {needle!r}, got {errors}")
        else:
            print(f"OK: {label} rejected")

    def check_source_pass(label: str, source: str) -> None:
        with tempfile.TemporaryDirectory() as scratch:
            candidate = Path(scratch) / "candidate.html"
            candidate.write_text(source, encoding="utf-8")
            check_pass(label, candidate)

    check_pass("shipped template", TEMPLATE)
    check_pass("shipped animated example", EXAMPLE)
    check_pass("shipped static example", STATIC_EXAMPLE)

    static = STATIC_EXAMPLE.read_text(encoding="utf-8")
    animated = EXAMPLE.read_text(encoding="utf-8")

    check_fail(
        "executable attribute",
        static.replace("<body>", '<body onload="fetch(1)">', 1),
        "executable attribute",
    )
    check_fail(
        "remote image",
        static.replace("<body>", '<body><img src="https://tracker.example/p.gif">', 1),
        "remote reference",
    )
    check_fail(
        "CSS import",
        static.replace(
            "</style>", '@import "https://tracker.example/theme.css";</style>', 1
        ),
        "CSS @import",
    )
    check_fail(
        "external CSS URL",
        static.replace(
            "</style>",
            ".tracked { background: url(https://tracker.example/p.gif); }</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "escaped CSS import",
        static.replace(
            "</style>", '@\\69mport "https://tracker.example/theme.css";</style>', 1
        ),
        "CSS @import",
    )
    check_fail(
        "escaped CSS URL",
        static.replace(
            "</style>",
            ".tracked { background: \\75rl(https\\3a //tracker.example/p.gif); }</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    continuation = chr(92) + "\n"
    check_fail(
        "CSS continuation URL",
        static.replace(
            "</style>",
            ".tracked { background: "
            f'\\75rl("https:{continuation}/{continuation}/tracker.example/p.gif"); '
            "}</style>",
            1,
        ),
        "non-fragment CSS url()",
    )
    for label, newline in (
        ("LF", "\n"),
        ("CRLF", "\r\n"),
        ("CR", "\r"),
        ("form feed", "\f"),
    ):
        continuation = chr(92) + newline
        normalized = module.normalize_css_escapes(
            f'url("https:{continuation}/{continuation}/tracker.example/p.gif")'
        )
        if normalized != 'url("https://tracker.example/p.gif")':
            failures.append(f"CSS {label} continuation was not removed: {normalized!r}")
        else:
            print(f"OK: CSS {label} continuation normalized")
    check_fail(
        "CSS image set",
        static.replace(
            "</style>",
            '.tracked { background: image-set("https://tracker.example/p.gif" 1x); }</style>',
            1,
        ),
        "CSS image-set()",
    )
    check_fail(
        "inline style URL",
        static.replace("<body>", '<body style="background:url(local.png)">', 1),
        "non-fragment CSS url()",
    )
    check_fail(
        "SVG presentation URL",
        static.replace(
            "</svg>",
            '<rect fill="url(https://tracker.example/p.svg#paint)"></rect></svg>',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "duplicate style URL",
        static.replace(
            "<body>",
            '<body style="background:url(remote.png)" style="background:none">',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_fail(
        "CSS string comment bypass",
        static.replace(
            "</style>",
            '.tracked { content: "/*"; background: url(remote.png); --x: "*/"; }</style>',
            1,
        ),
        "non-fragment CSS url()",
    )
    check_source_pass(
        "CSS-looking prose",
        static.replace(
            "<body>", "<body><p>Document @import and url(example) syntax.</p>", 1
        ),
    )
    check_fail(
        "lookalike fonts host",
        static.replace(
            "https://fonts.googleapis.com/css2",
            "https://fonts.googleapis.com.evil.tld/css2",
            1,
        ),
        "approved Google Fonts",
    )
    check_fail(
        "javascript URL",
        static.replace("<body>", '<body><a href="javascript:alert(1)">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "data html URL",
        static.replace("<body>", '<body><a href="data:text/html,x">x</a>', 1),
        "executable URL",
    )
    check_fail(
        "iframe injection",
        static.replace("<body>", "<body><iframe></iframe>", 1),
        "not allowed",
    )
    check_fail(
        "arbitrary script",
        static.replace("</body>", "<script>alert(1)</script></body>", 1),
        "canonical data-diagram-controls attribute",
    )
    check_fail(
        "missing svg role",
        static.replace('role="img"', 'role="presentation"', 1),
        "role=img",
    )
    check_fail(
        "modified controller",
        animated.replace("'motion-ready'", "'motion-ready' /* patched */", 1),
        "exactly match the controller",
    )
    check_fail(
        "second script",
        animated.replace("</body>", "<script data-x></script></body>", 1),
        "at most one script",
    )
    check_fail(
        "hidden motion item",
        animated.replace(
            '<g data-motion-item data-step="1"',
            '<g style="opacity:0" data-motion-item data-step="1"',
            1,
        ),
        "hidden in source",
    )
    check_fail(
        "missing noscript",
        animated.replace("<noscript>", "<div>", 1).replace("</noscript>", "</div>", 1),
        "<noscript>",
    )
    check_fail(
        "non-decimal step count",
        animated.replace('data-step-count="5"', 'data-step-count="٥"', 1),
        "ASCII decimal",
    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("All self-check tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
