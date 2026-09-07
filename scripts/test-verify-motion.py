#!/usr/bin/env python3
"""Adversarial tests for verify-motion.py and its canonical template."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-motion.py"
SEMANTIC_VERIFIER = ROOT / "scripts/verify-semantic-motion.py"
TEMPLATE = ROOT / "skills/diagram-design/assets/template-motion.html"
EXAMPLE = ROOT / "skills/diagram-design/assets/example-policy-trace-animated.html"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_motion", VERIFIER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-motion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_semantic_verifier():
    spec = importlib.util.spec_from_file_location("verify_semantic_motion", SEMANTIC_VERIFIER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load verify-semantic-motion.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = load_verifier()
    semantic_module = load_semantic_verifier()
    source = TEMPLATE.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="verify-motion-") as temporary:
        directory = Path(temporary)

        def check(name: str, html: str, expected: str | None) -> None:
            path = directory / f"{name}.html"
            path.write_text(html, encoding="utf-8")
            errors = module.verify(path)
            if expected is None:
                if errors:
                    raise AssertionError(f"{name}: expected pass, got {errors}")
                print(f"OK: {name} accepted")
            else:
                if not any(expected in error for error in errors):
                    raise AssertionError(f"{name}: expected {expected!r}, got {errors}")
                print(f"OK: {name} rejected — {expected}")

        check("canonical-template", source, None)
        script_free_none = re.sub(
            r"<script\b[^>]*>.*?</script\s*>", "", source, flags=re.IGNORECASE | re.DOTALL
        )
        script_free_none = re.sub(
            r"<div data-motion-controls.*?</div>", "", script_free_none, flags=re.DOTALL
        )
        script_free_none = re.sub(
            r"<p class=\"sr-only\" data-motion-status.*?</p>", "", script_free_none, flags=re.DOTALL
        )
        script_free_none = re.sub(
            r"\sdata-motion-item\sdata-step=\"\d+\"", "", script_free_none
        )
        script_free_none = script_free_none.replace(
            'data-motion-mode="step" data-step-count="5"',
            'data-motion-mode="none" data-step-count="0"',
            1,
        )
        check("script-free-none", script_free_none, None)
        none_with_controls = script_free_none.replace(
            "</main>", '<div data-motion-controls></div></main>', 1
        )
        check(
            "none-with-controls",
            none_with_controls,
            "none mode must not expose playback controls or live status",
        )
        loop_two = script_free_none.replace(
            'data-motion-mode="none" data-step-count="0"',
            'data-motion-mode="loop" data-step-count="2"',
            1,
        ).replace(
            "</main>",
            '<span data-motion-item data-step="1" aria-label="one"></span>'
            '<span data-motion-item data-step="2" aria-label="two"></span></main>',
            1,
        )
        check(
            "loop-two-semantic-items",
            loop_two,
            "loop mode allows at most one semantic item",
        )
        example_errors = module.verify(EXAMPLE)
        if example_errors:
            raise AssertionError(f"shipped example: expected pass, got {example_errors}")
        print("OK: shipped animated example accepted")

        shipped = module.shipped_motion_files()
        required_shipped = {TEMPLATE, EXAMPLE}
        if not required_shipped.issubset(set(shipped)):
            raise AssertionError(f"incomplete shipped motion inventory: {shipped}")
        print("OK: required shipped motion inventory is parsed and complete")
        check(
            "bad-mode",
            source.replace('data-motion-mode="step"', 'data-motion-mode="cinematic"', 1),
            "data-motion-mode must be one of",
        )
        check(
            "too-many-steps",
            source.replace('data-step-count="5"', 'data-step-count="9"', 1),
            "semantic step count must be 1..8",
        )
        check(
            "step-gap",
            source.replace('data-step="4" aria-label="Step 4', 'data-step="3" aria-label="Step 4', 1),
            "semantic steps must be contiguous",
        )
        check(
            "missing-pause",
            source.replace('data-motion-action="pause"', 'data-motion-action="stop"', 1),
            "missing actions: pause",
        )
        check(
            "bad-live-region",
            source.replace('aria-live="polite"', 'aria-live="assertive"', 1),
            "motion status needs role=status",
        )
        status_line = (
            '    <p class="sr-only" data-motion-status role="status" '
            'aria-live="polite" aria-atomic="true"></p>'
        )
        check(
            "status-inside-hidden-controls",
            source.replace(
                f"    </div>\n{status_line}",
                f"{status_line}\n    </div>",
                1,
            ),
            "motion status must be outside data-motion-controls",
        )
        check(
            "hidden-fallback",
            source.replace('data-motion-item data-step="1"', 'data-motion-item data-step="1" style="opacity:0"', 1),
            "fallback must be visible",
        )
        check(
            "decorative-focus",
            source.replace('data-motion-decorative aria-hidden="true" focusable="false"', 'data-motion-decorative aria-hidden="false" focusable="true"', 1),
            "needs aria-hidden=true and focusable=false",
        )
        check(
            "missing-reduced-motion",
            source.replace("prefers-reduced-motion", "user-reduced-motion"),
            "missing reduced-motion CSS fallback",
        )
        check(
            "comment-cannot-spoof-reduced-motion",
            source.replace(
                "@media (prefers-reduced-motion: reduce)",
                "@media (user-reduced-motion: reduce)",
                1,
            ).replace("</style>", "  /* prefers-reduced-motion */\n  </style>", 1),
            "missing reduced-motion CSS fallback",
        )
        check(
            "reduced-motion-controls-visible",
            source.replace(
                "[data-motion-controls] { display: none !important; }",
                "[data-motion-controls] { display: flex !important; }",
                1,
            ),
            "missing reduced-motion hidden controls",
        )
        check(
            "hidden-controls-overridden",
            source.replace("[data-motion-controls][hidden] { display: none !important; }", "", 1),
            "missing hidden control override",
        )
        check(
            "comment-cannot-spoof-script-contract",
            source.replace("'visibilitychange'", "'pagehide'", 1).replace(
                "    })();",
                "      // visibilitychange\n    })();",
                1,
            ),
            "missing background-tab pause",
        )
        check(
            "missing-static-override",
            source.replace('data-motion="static"', 'data-motion="still"'),
            "missing deterministic static override",
        )
        check(
            "late-title",
            source.replace(
                '<title id="template-motion-title">',
                '<g></g><title id="template-motion-title">',
                1,
            ),
            "title must be its first child",
        )
        check(
            "color-only-stage",
            source.replace('aria-label="Step 1: Request received"', 'aria-description="accent stage"', 1),
            "needs a non-color aria-label",
        )
        check(
            "unicode-step-count",
            source.replace('data-step-count="5"', 'data-step-count="٥"', 1),
            "data-step-count must be an ASCII decimal integer",
        )
        check(
            "underscored-item-step",
            source.replace('data-step="1"', 'data-step="1_0"', 1),
            "non-ASCII-decimal data-step",
        )
        check(
            "double-space-ready-scope",
            source.replace(
                ".motion-ready [data-motion-item] {",
                ".motion-ready  [data-motion-item] {",
                1,
            ),
            None,
        )
        check(
            "comma-unscoped-opacity",
            source.replace(
                ".motion-ready [data-motion-item] {\n      opacity: .12;",
                ".motion-ready [data-motion-item], [data-motion-item] {\n      opacity: 0;",
                1,
            ),
            "unscoped data-motion-item hiding",
        )
        check(
            "unscoped-visibility",
            source.replace(
                "</style>",
                "  [data-motion-root] > [data-motion-item] { visibility: hidden; }\n  </style>",
                1,
            ),
            "unscoped data-motion-item hiding",
        )
        check(
            "unscoped-display",
            source.replace(
                "</style>",
                "  [data-motion-item] { display: none; }\n  </style>",
                1,
            ),
            "unscoped data-motion-item hiding",
        )
        check(
            "unscoped-infinite-iteration-count",
            source.replace(
                "</style>",
                "  .motion-ready [data-motion-item] { animation-iteration-count: infinite; }\n  </style>",
                1,
            ),
            "infinite animation must be scoped to data-motion-mode=loop",
        )
        check(
            "null-test-frame",
            source.replace("requestedStep !== null", "true", 1),
            "missing non-null test frame validation",
        )
        check(
            "fractional-test-frame",
            source.replace("Number.isSafeInteger(parsedStep)", "Number.isFinite(parsedStep)", 1),
            "missing integer test frame validation",
        )
        check(
            "negative-test-frame",
            source.replace("/^\\d+$/.test(requestedStep)", "/^-?\\d+$/.test(requestedStep)", 1),
            "missing non-negative decimal test frame validation",
        )
        check(
            "modified-replay-shortcut",
            source.replace(
                "!event.ctrlKey && !event.metaKey && !event.altKey && ",
                "",
                1,
            ),
            "missing modified-shortcut guard",
        )
        check(
            "over-budget-test-frame",
            source.replace(" && parsedStep <= count", "", 1),
            "missing bounded test frame validation",
        )
        check(
            "modified-controller",
            source.replace(
                "const params = new URLSearchParams(location.search);",
                "const params = new URLSearchParams(location.search); void 0;",
                1,
            ),
            "must exactly match the controller in template-motion.html",
        )
        ready_line = "        root.classList.add('motion-ready');\n"
        check(
            "early-motion-ready",
            source.replace(ready_line, "", 1).replace(
                "        if (staticOverride) {",
                ready_line + "        if (staticOverride) {",
                1,
            ),
            "motion-ready must be added only after the initial render succeeds",
        )
        check(
            "remote-controller",
            source.replace(
                "<script data-diagram-controls>",
                '<script data-diagram-controls src="https://example.invalid/controller.js">',
                1,
            ),
            "must carry only the canonical data-diagram-controls attribute",
        )
        check(
            "duplicate-controller-attribute",
            source.replace(
                "<script data-diagram-controls>",
                "<script data-diagram-controls data-diagram-controls>",
                1,
            ),
            "must carry only the canonical data-diagram-controls attribute",
        )
        controls_outside = source.replace(
            "    <div data-motion-controls",
            "  </main>\n    <div data-motion-controls",
            1,
        ).replace("  </main>\n\n  <script data-diagram-controls>", "\n  <script data-diagram-controls>", 1)
        check(
            "controls-outside-root",
            controls_outside,
            "controlled mode needs one in-root control group; found 0",
        )
        check(
            "unclosed-controller",
            source.replace("</script>", "", 1),
            "must have a closing script tag",
        )

        broken_trace = directory / "broken-trace.html"
        broken_trace.write_text(
            EXAMPLE.read_text(encoding="utf-8").replace(
                'data-trace-connector="trace-b" x1="936" y1="104" x2="936" y2="336"',
                'data-trace-connector="trace-b" x1="936" y1="104" x2="936" y2="576"',
                1,
            ),
            encoding="utf-8",
        )
        trace_errors = semantic_module.verify_example(broken_trace)
        if not any("must terminate at the first FAIL" in error for error in trace_errors):
            raise AssertionError(f"broken Trace B connector was accepted: {trace_errors}")
        print("OK: Trace B connector cannot continue through terminal rows")

        decorative_example = directory / "decorative-trace.html"
        decorative_example.write_text(
            EXAMPLE.read_text(encoding="utf-8").replace(
                "      </svg>",
                '        <circle data-motion-item data-step="3" data-motion-decorative '
                'aria-hidden="true" focusable="false" cx="0" cy="0" r="1"/>\n'
                "      </svg>",
                1,
            ),
            encoding="utf-8",
        )
        decorative_errors = semantic_module.verify_example(decorative_example)
        if decorative_errors:
            raise AssertionError(
                f"decorative semantic-verifier item was rejected: {decorative_errors}"
            )
        print("OK: semantic verifier accepts an accessible decorative motion item")

        original_skill = semantic_module.SKILL
        try:
            missing_router = directory / "missing-router.md"
            missing_router.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "semantic-patterns.md", "patterns.md"
                ),
                encoding="utf-8",
            )
            semantic_module.SKILL = missing_router
            markdown_errors = semantic_module.verify_markdown()
        finally:
            semantic_module.SKILL = original_skill
        if not any("must link to semantic-patterns.md" in error for error in markdown_errors):
            raise AssertionError(f"missing semantic router was accepted: {markdown_errors}")
        print("OK: missing semantic-pattern router anchor is rejected")

        try:
            missing_guide = directory / "missing-guide.md"
            missing_guide.write_text(
                original_skill.read_text(encoding="utf-8").replace(
                    "### Visual-type guide (39)", "### Visual guide"
                ),
                encoding="utf-8",
            )
            semantic_module.SKILL = missing_guide
            markdown_errors = semantic_module.verify_markdown()
        finally:
            semantic_module.SKILL = original_skill
        if not any("must contain the 39-row visual-type guide" in error for error in markdown_errors):
            raise AssertionError(f"missing visual-guide anchor was accepted: {markdown_errors}")
        print("OK: missing visual-type guide anchor is rejected")

        cli_result = subprocess.run(
            [sys.executable, str(VERIFIER), str(TEMPLATE)],
            capture_output=True,
            text=True,
            check=False,
        )
        if cli_result.returncode != 0 or f"OK {TEMPLATE}" not in cli_result.stdout:
            raise AssertionError(f"CLI smoke test failed\n{cli_result.stdout}{cli_result.stderr}")
        print("OK: CLI accepts canonical template")

    print("All motion contract tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
