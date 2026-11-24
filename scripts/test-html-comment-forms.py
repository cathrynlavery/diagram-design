#!/usr/bin/env python3
"""Verifiers end an HTML comment where the browser does (#544).

The HTML tokenizer closes a comment at `<!-->`, `<!--->` and `--!>` as well as
`-->`. A verifier that blanks `<!--.*?-->` instead hides real markup from its
checks: `<!--><circle/><!-- -->` draws the circle, but the checker never sees it.

Three checks: no verifier keeps the old lazy pattern, every compiled comment
pattern stops at each tokenizer ending, and the box-plot checker flags a second
accent circle that sits behind each ending.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

VERIFIERS = sorted((ROOT / "scripts").glob("verify-*.py")) + [
    ROOT / "skills/diagram-design/scripts/verify_geometry.py"
]
# A comment body read lazily up to `-->` only, in either spelling.
OLD_PATTERN_RE = re.compile(r"<!--(?:\.\*\?|\[\\s\\S\]\*\?)(?:-->|\(\?:-->)")
# (source, where the comment must end)
ENDINGS = (
    ("<!--><g/>", 5),
    ("<!---><g/>", 6),
    ("<!-- a --!><g/>", 11),
    ("<!-- a --><g/>", 10),
    ("<!----><g/>", 7),
)


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_sources() -> int:
    stale = []
    for path in VERIFIERS:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if OLD_PATTERN_RE.search(line):
                stale.append(f"{path.relative_to(ROOT)}:{number}")
    if stale:
        raise AssertionError("comment pattern ignores <!-->, <!---> and --!>: " + ", ".join(stale))
    return len(VERIFIERS)


def check_patterns() -> int:
    checked = 0
    for path in VERIFIERS:
        if "<!--" not in path.read_text(encoding="utf-8"):
            continue
        for name, pattern in vars(load(path)).items():
            if not isinstance(pattern, re.Pattern) or "<!--" not in pattern.pattern:
                continue
            for source, end in ENDINGS:
                match = pattern.match(source)
                if match is None or match.end() != end:
                    got = None if match is None else match.end()
                    raise AssertionError(f"{path.name} {name} ends {source!r} at {got}, the browser at {end}")
            checked += 1
    if checked < 19:
        raise AssertionError(f"expected at least 19 comment patterns, found {checked}")
    return checked


def check_box_plot() -> int:
    example = (ROOT / "skills/diagram-design/assets/example-box-plot.html").read_text(encoding="utf-8")
    start = example.index('<g data-name="Auth"')
    end = example.index("</g>", start)
    circle = '<circle cx="700" cy="80" r="6" fill="#bf4520"/>'
    cases = {
        "bare": (circle, True),
        "abrupt": ("<!-->" + circle + "<!-- -->", True),
        "abrupt-dash": ("<!--->" + circle + "<!-- -->", True),
        "bang": ("<!-- a --!>" + circle + "<!-- -->", True),
        "closed": ("<!-- " + circle + " -->", False),
    }
    with tempfile.TemporaryDirectory() as tmp:
        for name, (inserted, flagged) in cases.items():
            path = Path(tmp) / f"{name}.html"
            path.write_text(example[:end] + inserted + example[end:], encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/verify-box-plot.py"), str(path)],
                capture_output=True, text=True,
            )
            if (result.returncode != 0) != flagged:
                want = "a finding" if flagged else "a pass"
                raise AssertionError(f"box plot {name}: expected {want}, got exit {result.returncode}: {result.stdout}")
    return len(cases)


def main() -> int:
    files = check_sources()
    patterns = check_patterns()
    cases = check_box_plot()
    print(f"OK HTML comment forms: {files} verifier(s), {patterns} pattern(s), {cases} box-plot case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
