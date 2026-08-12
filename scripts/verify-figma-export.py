#!/usr/bin/env python3
"""Cross-platform verification gate for the shipped Figma SVG tooling."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
CAPTURE = ROOT / "skills/diagram-design/scripts/figma_capture.py"
EXPORT_REF = ROOT / "skills/diagram-design/references/export.md"
REFERENCES = ROOT / "skills/diagram-design/references"
COMMANDS = ROOT / "commands"
FIXTURE = ROOT / "scripts/fixtures/sample-nested-svg.html"
GALLERY = ROOT / "skills/diagram-design/assets/index.html"
MEDALLION = ROOT / "skills/diagram-design/assets/example-medallion.html"
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>\n'
VARIANTS = (
    ("light", ROOT / "skills/diagram-design/assets/example-architecture.html"),
    ("dark", ROOT / "skills/diagram-design/assets/example-architecture-dark.html"),
    ("full", ROOT / "skills/diagram-design/assets/example-architecture-full.html"),
    ("terminal", ROOT / "skills/diagram-design/assets/example-loop-terminal.html"),
)
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]")
WINDOWS_HOME_RE = re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE)


class VerificationError(Exception):
    """A verification assertion failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SvgIsolationParser(HTMLParser):
    """Find top-level SVG spans without confusing nested icon SVGs for siblings."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer("\n", source))
        self.depth = 0
        self.start: int | None = None
        self.spans: list[tuple[int, int]] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _token_end(self, start: int) -> int:
        end = self.source.find(">", start)
        if end < 0:
            raise VerificationError("unterminated SVG tag in verification input")
        return end + 1

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag.lower() != "svg":
            return
        if self.depth == 0:
            self.start = self._offset()
        self.depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag.lower() == "svg" and self.depth == 0:
            start = self._offset()
            self.spans.append((start, self._token_end(start)))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "svg" or self.depth == 0:
            return
        self.depth -= 1
        if self.depth == 0:
            require(self.start is not None, "inconsistent SVG nesting in source")
            self.spans.append((self.start, self._token_end(self._offset())))
            self.start = None


class RootAttributesParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: dict[str, str | None] | None = None

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if self.attrs is None and tag.lower() == "svg":
            self.attrs = {name.lower(): value for name, value in attrs}


def isolate_svg(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    parser = SvgIsolationParser(source)
    parser.feed(source)
    parser.close()
    require(parser.depth == 0, f"{path.name}: unterminated source SVG")
    require(len(parser.spans) == 1, f"{path.name}: expected one top-level source SVG")
    start, end = parser.spans[0]
    return source[start:end]


def root_attributes(svg: str) -> dict[str, str | None]:
    parser = RootAttributesParser()
    parser.feed(svg)
    parser.close()
    require(parser.attrs is not None, "could not read outer SVG attributes")
    return parser.attrs


def audit_generated_svg(svg: str) -> None:
    for marker in ("/Users/", "/home/"):
        require(marker not in svg, f"generated SVG leaks absolute home path {marker!r}")
    require(
        WINDOWS_HOME_RE.search(svg) is None,
        "generated SVG leaks an absolute Windows user-home path",
    )
    require(
        SECRET_RE.search(svg) is None,
        "generated SVG contains an obvious secret-token assignment pattern",
    )


class CaptureRunner:
    """Drive the real CLI while centrally enforcing source and output invariants."""

    def __init__(self) -> None:
        self.integrity_checks = 0
        self.integrity_failures: list[str] = []
        self.hygiene_checks = 0
        self.hygiene_failures: list[str] = []

    def run(self, command: str, source: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        before = sha256(source)
        proc = subprocess.run(
            [sys.executable, "-B", str(CAPTURE), command, str(source), *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
        )
        after = sha256(source)
        self.integrity_checks += 1
        if before != after:
            message = f"{command} modified source {source}"
            self.integrity_failures.append(message)
            raise VerificationError(message)

        if command == "extract" and proc.returncode == 0:
            if "--stdout" in extra:
                generated = proc.stdout
            else:
                if "--out" in extra:
                    out_arg = extra[extra.index("--out") + 1]
                    output = Path(out_arg)
                    if not output.is_absolute():
                        output = ROOT / output
                else:
                    output = source.with_suffix(".svg")
                require(output.is_file(), f"extract succeeded without writing {output}")
                generated = output.read_text(encoding="utf-8")
            self.hygiene_checks += 1
            try:
                audit_generated_svg(generated)
            except VerificationError as exc:
                self.hygiene_failures.append(str(exc))
                raise
        return proc


def require_success(proc: subprocess.CompletedProcess[str], context: str) -> None:
    require(
        proc.returncode == 0,
        f"{context} exited {proc.returncode}: {proc.stderr.strip()}",
    )


def case_happy_paths(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    for variant, source in VARIANTS:
        checked = runner.run("check", source)
        require_success(checked, f"{variant} check")
        digest = re.fullmatch(
            r'ok source=(.+) viewBox="([^"]+)" dimensions=([^\s]+) '
            r"sha256=([0-9a-f]{64})\n?",
            checked.stdout,
        )
        require(digest is not None, f"{variant} check digest has the wrong shape")

        extracted = runner.run("extract", source, "--stdout")
        require_success(extracted, f"{variant} extract")
        svg = extracted.stdout
        require(svg.startswith(XML_DECLARATION), f"{variant} XML declaration is wrong")
        try:
            root = ET.fromstring(svg)
        except ET.ParseError as exc:
            raise VerificationError(f"{variant} extract is not well-formed XML: {exc}") from exc
        source_viewbox = root_attributes(isolate_svg(source)).get("viewbox")
        require(digest.group(1) == str(source), f"{variant} check reported wrong source")
        require(digest.group(2) == source_viewbox, f"{variant} check reported wrong viewBox")
        viewbox_numbers = [float(part) for part in str(source_viewbox).replace(",", " ").split()]
        expected_dimensions = f"{viewbox_numbers[2]:g}x{viewbox_numbers[3]:g}"
        require(
            digest.group(3) == expected_dimensions,
            f"{variant} check reported wrong dimensions",
        )
        require(digest.group(4) == sha256(source), f"{variant} check reported wrong SHA-256")
        require(root.tag == f"{{{SVG_NAMESPACE}}}svg", f"{variant} root lacks SVG xmlns")
        require(
            root.attrib.get("viewBox") == source_viewbox,
            f"{variant} extract changed viewBox",
        )


def case_verbatim_source(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    source = VARIANTS[0][1]
    source_svg = isolate_svg(source)
    text_match = re.search(r"<text\b[^>]*>[^<]{4,}</text>", source_svg, re.IGNORECASE)
    path_match = re.search(r'<path\b[^>]*\bd="([^"]{24,})"', source_svg, re.IGNORECASE)
    require(text_match is not None, "could not select a source text label")
    require(path_match is not None, "could not select a source path fragment")
    snippets = (text_match.group(0), f'd="{path_match.group(1)[:80]}')

    proc = runner.run("extract", source, "--stdout")
    require_success(proc, "verbatim-source extract")
    for snippet in snippets:
        require(snippet in proc.stdout, f"source SVG content was rewritten: {snippet!r}")


def export_font_import() -> str:
    spec = EXPORT_REF.read_text(encoding="utf-8")
    require("## SVG export procedure" in spec, "export.md lacks SVG export procedure")
    section = spec.split("## SVG export procedure", 1)[1].split("## PNG export procedure", 1)[0]
    block = re.search(r"```svg\s*(.*?)\s*```", section, re.DOTALL)
    require(block is not None, "export.md SVG procedure lacks its SVG snippet")
    font_import = re.search(
        r"(@import url\('https://fonts\.googleapis\.com/[^'\n]+'\);)",
        block.group(1),
    )
    require(font_import is not None, "export.md SVG snippet lacks Google Fonts @import")
    return font_import.group(1)


def case_export_spec_parity(runner: CaptureRunner, tmp: Path) -> None:
    source = VARIANTS[0][1]
    source_svg = isolate_svg(source)
    require(
        len(re.findall(r"<defs(?=[\s>])", source_svg, re.IGNORECASE)) == 1,
        "parity source must begin with exactly one existing defs block",
    )
    proc = runner.run("extract", source, "--stdout")
    require_success(proc, "export-spec parity extract")
    output = proc.stdout
    font_import = export_font_import()
    require(font_import in output, "extract output drifted from export.md font import")
    require(
        output.count(f"<style>{font_import}</style>") == 1,
        "font import was not merged exactly once",
    )
    require(
        len(re.findall(r"<defs(?=[\s>])", output, re.IGNORECASE)) == 1,
        "extract added a duplicate defs block",
    )
    require(output.startswith(XML_DECLARATION), "export.md XML declaration is not honored")
    opening = re.match(r"<svg\b[^>]*>", output[len(XML_DECLARATION) :], re.DOTALL)
    require(opening is not None, "standalone output lacks an SVG opening tag")
    require(
        f'xmlns="{SVG_NAMESPACE}"' in opening.group(0),
        "export.md xmlns requirement is not honored",
    )

    bare = tmp / "no-defs-or-xmlns.html"
    bare.write_text(
        '<svg viewBox="0 0 20 10" role="img" aria-labelledby="bare-title bare-desc">'
        '<title id="bare-title">Bare diagram</title>'
        '<desc id="bare-desc">No namespace or definitions block.</desc>'
        '<rect width="20" height="10"/></svg>',
        encoding="utf-8",
    )
    bare_proc = runner.run("extract", bare, "--stdout")
    require_success(bare_proc, "missing-defs/missing-xmlns extract")
    bare_output = bare_proc.stdout
    bare_opening = re.match(
        r"<svg\b[^>]*>", bare_output[len(XML_DECLARATION) :], re.DOTALL
    )
    require(bare_opening is not None, "normalized SVG lacks an opening tag")
    require(
        f'xmlns="{SVG_NAMESPACE}"' in bare_opening.group(0),
        "extract did not add a missing SVG namespace",
    )
    require(bare_output.count(f"<style>{font_import}</style>") == 1, "new defs lost font style")
    require(
        bare_output.index("</desc>") < bare_output.index("<defs>") < bare_output.index("<rect"),
        "new defs block was not inserted after title/desc",
    )


def case_nested_svg(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    source_svg = isolate_svg(FIXTURE)
    proc = runner.run("extract", FIXTURE, "--stdout")
    require_success(proc, "nested-SVG extract")
    pattern = re.compile(r"<svg(?=[\s>/])", re.IGNORECASE)
    require(
        len(pattern.findall(source_svg)) == len(pattern.findall(proc.stdout)),
        "nested SVG count changed during extraction",
    )
    require(len(pattern.findall(source_svg)) >= 4, "fixture lacks three nested icon SVGs")
    try:
        ET.fromstring(proc.stdout)
    except ET.ParseError as exc:
        raise VerificationError(f"nested-SVG extract is not well-formed XML: {exc}") from exc


def raw_element(svg: str, tag: str) -> bytes:
    match = re.search(
        rf"<{tag}\b[^>]*>.*?</{tag}\s*>", svg, re.IGNORECASE | re.DOTALL
    )
    require(match is not None, f"SVG lacks <{tag}> element")
    return match.group(0).encode("utf-8")


def case_accessibility(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    for source in (FIXTURE, VARIANTS[0][1]):
        source_svg = isolate_svg(source)
        proc = runner.run("extract", source, "--stdout")
        require_success(proc, f"{source.name} accessibility extract")
        source_attrs = root_attributes(source_svg)
        output_attrs = root_attributes(proc.stdout[len(XML_DECLARATION) :])
        require(source_attrs.get("role") == "img", f"{source.name} lacks role=img")
        require(
            output_attrs.get("role") == source_attrs.get("role"),
            f"{source.name} role changed during extract",
        )
        require(
            output_attrs.get("aria-labelledby") == source_attrs.get("aria-labelledby"),
            f"{source.name} aria-labelledby changed during extract",
        )
        for tag in ("title", "desc"):
            require(
                raw_element(proc.stdout, tag) == raw_element(source_svg, tag),
                f"{source.name} {tag} element was not byte-identical",
            )


def case_path_edge(runner: CaptureRunner, tmp: Path) -> None:
    folder = tmp / "über diagramm"
    folder.mkdir()
    source = folder / "mein plan.html"
    shutil.copyfile(VARIANTS[0][1], source)
    expected_output = source.with_suffix(".svg")
    proc = runner.run("extract", source)
    require_success(proc, "spaces/non-ASCII default extract")
    require(expected_output.is_file(), "default extract did not write next to source")
    require(f"source: {source}" in proc.stdout, "file digest omitted source")
    require(f"output: {expected_output}" in proc.stdout, "file digest omitted output")
    require("viewBox: " in proc.stdout, "file digest omitted viewBox")
    require(f"source_sha256: {sha256(source)}" in proc.stdout, "file digest omitted SHA-256")

    explicit_output = folder / "maßgeschneidert.svg"
    explicit = runner.run("extract", source, "--out", str(explicit_output))
    require_success(explicit, "explicit --out extract")
    require(explicit_output.is_file(), "explicit --out path was not written")
    require(f"output: {explicit_output}" in explicit.stdout, "explicit output digest is wrong")


def write_svg_case(path: Path, body: str, viewbox: str | None = "0 0 20 10") -> None:
    viewbox_attr = "" if viewbox is None else f' viewBox="{viewbox}"'
    path.write_text(
        f'<svg{viewbox_attr} xmlns="{SVG_NAMESPACE}">{body}</svg>',
        encoding="utf-8",
    )


def case_errors(runner: CaptureRunner, tmp: Path) -> None:
    errors = tmp / "errors"
    errors.mkdir()
    missing_svg = errors / "missing-svg.html"
    missing_svg.write_text("<!doctype html><p>not a diagram</p>", encoding="utf-8")
    siblings = errors / "two-siblings.html"
    siblings.write_text(
        '<svg viewBox="0 0 10 10"></svg><svg viewBox="0 0 10 10"></svg>',
        encoding="utf-8",
    )
    missing_viewbox = errors / "missing-viewbox.html"
    write_svg_case(missing_viewbox, "<rect width=\"10\" height=\"10\"/>", None)
    malformed_viewbox = errors / "malformed-viewbox.html"
    write_svg_case(malformed_viewbox, "<rect/>", "0 0 x 10")
    nonpositive_viewbox = errors / "nonpositive-viewbox.html"
    write_svg_case(nonpositive_viewbox, "<rect/>", "0 0 0 10")
    script = errors / "script.html"
    write_svg_case(script, "<script>alert(1)</script>")
    handler = errors / "handler.html"
    write_svg_case(handler, '<rect onclick="alert(1)"/>')
    javascript_url = errors / "javascript-url.html"
    write_svg_case(javascript_url, '<a href="javascript:alert(1)"><rect/></a>')
    xml_unclean = errors / "xml-unclean.html"
    write_svg_case(xml_unclean, "<text>A & B</text>")

    cases = (
        ("missing-svg", missing_svg, "no <svg>"),
        ("gallery", GALLERY, "gallery source"),
        ("siblings", siblings, "2 top-level <svg>"),
        ("missing-viewbox", missing_viewbox, "missing a viewBox"),
        ("malformed-viewbox", malformed_viewbox, "malformed viewBox"),
        ("nonpositive-viewbox", nonpositive_viewbox, "positive width and height"),
        ("script", script, "<script>"),
        ("handler", handler, "event-handler"),
        ("javascript-url", javascript_url, "javascript:"),
        ("xml-unclean", xml_unclean, "not XML-clean"),
    )
    for name, source, cause in cases:
        output = errors / f"{name}-must-not-exist.svg"
        proc = runner.run("extract", source, "--out", str(output))
        require(proc.returncode == 2, f"{name} exited {proc.returncode}, expected 2")
        require(proc.stderr.startswith("figma_capture: "), f"{name} lacks error prefix")
        require(cause.lower() in proc.stderr.lower(), f"{name} stderr does not name {cause}")
        require(not output.exists(), f"{name} wrote an output file on failure")


def case_external_references(runner: CaptureRunner, tmp: Path) -> None:
    refs = tmp / "external-references"
    refs.mkdir()
    google = refs / "google-fonts.html"
    write_svg_case(
        google,
        "<style>@import url('https://fonts.googleapis.com/css2?family=Geist');</style>"
        '<rect width="20" height="10"/>',
    )
    other_font = refs / "other-font.html"
    write_svg_case(
        other_font,
        "<style>@import url('https://other.example/css2?family=Geist');</style>",
    )
    other_image = refs / "other-image.html"
    write_svg_case(other_image, '<image href="https://other.example/x.png"/>')
    other_css_url = refs / "other-css-url.html"
    write_svg_case(
        other_css_url,
        "<style>.remote { fill: url('https://other.example/fill.svg'); }</style>",
    )
    local_refs = refs / "local-refs.html"
    write_svg_case(
        local_refs,
        '<defs><linearGradient id="grad"><stop offset="1"/></linearGradient>'
        '<path id="shape" d="M0 0h1v1z"/></defs>'
        '<use href="#shape"/><rect width="20" height="10" fill="url(#grad)"/>'
        '<image href="data:image/png;base64,iVBORw0KGgo="/>',
    )

    for name, source in (("Google Fonts", google), ("fragment references", local_refs)):
        proc = runner.run("check", source)
        require_success(proc, f"{name} policy check")
    for name, source, cause in (
        ("other font host", other_font, "external @import host"),
        ("other image host", other_image, "external href host"),
        ("other CSS URL host", other_css_url, "external url() host"),
    ):
        proc = runner.run("check", source)
        require(proc.returncode == 2, f"{name} unexpectedly passed")
        require(cause in proc.stderr, f"{name} failure did not identify {cause}")


def case_foreign_object(runner: CaptureRunner, tmp: Path) -> None:
    proc = runner.run("check", MEDALLION)
    require_success(proc, "medallion foreignObject check")
    require("warning:" in proc.stderr, "medallion check omitted warning")
    require("foreignObject" in proc.stderr, "medallion warning omitted foreignObject")

    unsafe = tmp / "foreign-object-script.html"
    write_svg_case(unsafe, "<foreignObject><script>alert(1)</script></foreignObject>")
    proc = runner.run("check", unsafe)
    require(proc.returncode == 2, "foreignObject with script unexpectedly passed")
    require("<script>" in proc.stderr, "foreignObject script failure omitted cause")


def case_source_integrity(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    require(runner.integrity_checks > 0, "no subprocess source hashes were checked")
    require(
        not runner.integrity_failures,
        "source integrity failures: " + "; ".join(runner.integrity_failures),
    )


def case_hygiene(runner: CaptureRunner, tmp: Path) -> None:
    del tmp
    require(runner.hygiene_checks > 0, "no generated SVG outputs were audited")
    require(
        not runner.hygiene_failures,
        "output hygiene failures: " + "; ".join(runner.hygiene_failures),
    )


def case_doc_pointers(runner: CaptureRunner, tmp: Path) -> None:
    del runner, tmp
    references: list[tuple[Path, str]] = []
    target_re = re.compile(
        r"^(?:\.\./)*commands/([A-Za-z0-9._-]+\.md)(?:#[^\s]*)?$"
    )
    for document in sorted(REFERENCES.glob("*.md")):
        text = document.read_text(encoding="utf-8")
        targets = re.findall(r"`([^`\n]+)`", text)
        targets.extend(re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text))
        for target in targets:
            match = target_re.fullmatch(target.strip("<>"))
            if match:
                references.append((document, match.group(1)))
    require(references, "no commands/<name>.md references were discovered")
    missing = [
        f"{document.name}: commands/{name}"
        for document, name in references
        if not (COMMANDS / name).is_file()
    ]
    require(not missing, "stale command pointers: " + ", ".join(missing))


def main() -> int:
    required = (CAPTURE, EXPORT_REF, FIXTURE, GALLERY, MEDALLION, *(path for _, path in VARIANTS))
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        print("FAIL: missing required artifacts: " + ", ".join(missing), file=sys.stderr)
        return 1

    cases = (
        ("happy path across light/dark/full/terminal variants", case_happy_paths),
        ("extract preserves distinctive source SVG content verbatim", case_verbatim_source),
        ("extract stays in parity with export.md", case_export_spec_parity),
        ("nested SVG fixture survives complete and well-formed", case_nested_svg),
        ("accessibility metadata and title/desc survive byte-identically", case_accessibility),
        ("spaces and non-ASCII paths support default output", case_path_edge),
        ("invalid and active-content inputs fail without output", case_errors),
        ("external-reference allowlist accepts and rejects correctly", case_external_references),
        ("foreignObject warns while active content still fails", case_foreign_object),
        ("every subprocess leaves its source byte-identical", case_source_integrity),
        ("all generated SVGs pass path and secret hygiene", case_hygiene),
        ("reference command pointers resolve at the repository root", case_doc_pointers),
    )
    runner = CaptureRunner()
    failures = 0
    with tempfile.TemporaryDirectory(prefix="diagram-design-figma-") as tmp_dir:
        tmp = Path(tmp_dir)
        for number, (label, check) in enumerate(cases, start=1):
            try:
                check(runner, tmp)
            except VerificationError as exc:
                failures += 1
                print(f"FAIL {number}: {label}: {exc}", file=sys.stderr)
            else:
                print(f"PASS {number}: {label}")

    if failures:
        print(f"\n{failures} of {len(cases)} Figma export tooling cases failed.", file=sys.stderr)
        return 1
    print(f"\nAll {len(cases)} Figma export tooling cases passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
