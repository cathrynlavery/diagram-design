#!/usr/bin/env python3
"""Verifiers end an HTML comment where the browser does (#544).

The HTML tokenizer closes a comment at `<!-->`, `<!--->` and `--!>` as well as
`-->`. A verifier that blanks `<!--.*?-->` instead hides real markup from its
checks: `<!--><circle/><!-- -->` draws the circle, but the checker never sees it.

No verifier keeps the old lazy pattern, every compiled comment pattern stops at
each tokenizer ending, and every HTMLParser a verifier uses ends comments the same
way (Python before 3.13 runs `<!-->` on to the next `-->`). End to end, the
box-plot checker (regex path) flags a second accent circle and the bubble checker
(parser path) flags an off-scale bubble behind each ending.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

VERIFIERS = sorted((ROOT / "scripts").glob("verify-*.py")) + [
    ROOT / "skills/diagrams-design-quind/scripts/verify_geometry.py"
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


def check_parsers() -> int:
    from html_comments import TokenizerComments

    class Tags(TokenizerComments, HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.tags: list[str] = []
            self.comments: list[str] = []

        def handle_startendtag(self, tag, attrs) -> None:
            self.tags.append(tag)

        def handle_comment(self, data) -> None:
            self.comments.append(data)

    for source, comment in (
        ("<!--><g/>", ""), ("<!---><g/>", ""), ("<!-- a --!><g/>", " a "),
        ("<!-- a --><g/>", " a "), ("<!----><g/>", ""), ("<style><!--></style><g/>", None),
    ):
        parser = Tags()
        parser.feed(source)
        parser.close()
        if parser.tags != ["g"] or parser.comments != ([] if comment is None else [comment]):
            raise AssertionError(f"TokenizerComments read {source!r} as tags {parser.tags}, comments {parser.comments}")

    unfixed = []
    for path in VERIFIERS:
        if "HTMLParser" not in path.read_text(encoding="utf-8"):
            continue
        for name, value in vars(load(path)).items():
            if (isinstance(value, type) and issubclass(value, HTMLParser) and value is not HTMLParser
                    and value.parse_comment is not TokenizerComments.parse_comment):
                unfixed.append(f"{path.name} {name}")
    if unfixed:
        raise AssertionError("HTMLParser without TokenizerComments: " + ", ".join(unfixed))
    return len(VERIFIERS)


def run_cases(name: str, verifier: str, cases: dict, finding: str, ok: str) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for case, (source, flagged) in cases.items():
            path = Path(tmp) / f"{case}.html"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / verifier), str(path)],
                capture_output=True, text=True,
            )
            found = result.returncode == 1 and finding in result.stdout
            passed = result.returncode == 0 and result.stdout.startswith(ok)
            if not (found if flagged else passed) or "Traceback" in result.stderr:
                want = repr(finding) if flagged else "a pass"
                raise AssertionError(
                    f"{name} {case}: expected {want}, got exit {result.returncode}: {result.stdout}{result.stderr}")
    return len(cases)


def check_bubble() -> int:
    """HTMLParser path: a bubble off its scale, hidden from Python < 3.13 by `<!-->`."""
    example = (ROOT / "skills/diagrams-design-quind/assets/example-bubble.html").read_text(encoding="utf-8")
    anchor = '<circle data-name="Gateway"'
    end = example.index("/>", example.index(anchor)) + 2
    ghost = example[example.index(anchor):end].replace('"Gateway"', '"Ghost"').replace('cx="229.6"', 'cx="900"')
    cases = {
        name: (example[:end] + wrapped + example[end:], flagged)
        for name, (wrapped, flagged) in {
            "bare": (ghost, True),
            "abrupt": ("<!-->" + ghost + "<!-- -->", True),
            "abrupt-dash": ("<!--->" + ghost + "<!-- -->", True),
            "bang": ("<!-- a --!>" + ghost + "<!-- -->", True),
            "closed": ("<!-- " + ghost + " -->", False),
        }.items()
    }
    return run_cases("bubble", "verify-bubble.py", cases, "bubble 'Ghost' declares x=85", "OK bubble")


def check_box_plot() -> int:
    example = (ROOT / "skills/diagrams-design-quind/assets/example-box-plot.html").read_text(encoding="utf-8")
    start = example.index('<g data-name="Auth"')
    end = example.index("</g>", start)
    circle = '<circle cx="700" cy="80" r="6" fill="#cc3b10"/>'
    cases = {
        "bare": (circle, True),
        "abrupt": ("<!-->" + circle + "<!-- -->", True),
        "abrupt-dash": ("<!--->" + circle + "<!-- -->", True),
        "bang": ("<!-- a --!>" + circle + "<!-- -->", True),
        "closed": ("<!-- " + circle + " -->", False),
    }
    cases = {name: (example[:end] + inserted + example[end:], flagged) for name, (inserted, flagged) in cases.items()}
    return run_cases("box plot", "verify-box-plot.py", cases, "has an unbound circle", "OK box plot")


def main() -> int:
    files = check_sources()
    patterns = check_patterns()
    check_parsers()
    cases = check_box_plot() + check_bubble()
    print(f"OK HTML comment forms: {files} verifier(s), {patterns} pattern(s), {cases} end-to-end case(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
