#!/usr/bin/env python3
"""Validate diagram HTML and extract its SVG for Figma-oriented workflows.

This branch-independent core isolates SVG markup with balanced-tag parsing,
checks that it is safe and self-contained, and can write a standalone SVG
without modifying the source HTML.  Future capture commands can be added as
additional subcommands.

Usage:
    python3 figma_capture.py extract <src> [--stdout | --out PATH]
    python3 figma_capture.py check <src>

Exit codes: 0 ok, 2 unreadable / invalid input.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import math
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import NoReturn
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

# --------------------------------------------------------------------------
# constants + errors
# --------------------------------------------------------------------------

MAX_INPUT_BYTES = 32 * 1024 * 1024
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
FONT_IMPORT = (
    "@import url('https://fonts.googleapis.com/css2?"
    "family=Instrument+Serif:ital@0;1&family=Geist:wght@400;500;600&"
    "family=Geist+Mono:wght@400;500;600&display=swap');"
)
FONT_IMPORT_XML = html.escape(FONT_IMPORT, quote=False)
FONT_STYLE = f"<style>{FONT_IMPORT_XML}</style>"
FONT_DEFS = f"<defs>{FONT_STYLE}</defs>"
ALLOWED_EXTERNAL_HOSTS = frozenset(
    {"fonts.googleapis.com", "fonts.gstatic.com"}
)

CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
CSS_URL_RE = re.compile(
    r"url\(\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|"
    r"(?P<bare>[^)]*?))\s*\)",
    re.IGNORECASE | re.DOTALL,
)
CSS_IMPORT_RE = re.compile(
    r"@import\s+(?P<target>"
    r"url\(\s*(?:\"[^\"]*\"|'[^']*'|[^)]*?)\s*\)"
    r"|\"[^\"]*\"|'[^']*'|[^\s;]+)",
    re.IGNORECASE | re.DOTALL,
)
CSS_ESCAPE_RE = re.compile(r"\\(?:([0-9a-fA-F]{1,6})[ \t\r\n\f]?|([^\r\n\f]))")
XMLNS_RE = re.compile(
    r"(?P<prefix>\sxmlns\s*=\s*)"
    r"(?P<value>\"[^\"]*\"|'[^']*'|[^\s>]+)"
)


def _fail(msg: str) -> NoReturn:
    print(f"figma_capture: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _warn(msg: str) -> None:
    print(f"figma_capture: warning: {msg}", file=sys.stderr)


@dataclass(frozen=True)
class ViewBox:
    raw: str
    min_x: float
    min_y: float
    width: float
    height: float


@dataclass(frozen=True)
class CheckedDiagram:
    source: Path
    source_sha256: str
    svg: str
    viewbox: ViewBox


# --------------------------------------------------------------------------
# balanced SVG isolation
# --------------------------------------------------------------------------


class SvgIsolationParser(HTMLParser):
    """Locate top-level SVG spans while retaining source-text offsets."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer("\n", source))
        self.svg_depth = 0
        self.current_start: int | None = None
        self.spans: list[tuple[int, int]] = []

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _token_end(self, start: int) -> int:
        end = self.source.find(">", start)
        if end < 0:
            raise ValueError("unterminated SVG tag")
        return end + 1

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag.lower() != "svg":
            return
        if self.svg_depth == 0:
            self.current_start = self._offset()
        self.svg_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        if tag.lower() == "svg" and self.svg_depth == 0:
            start = self._offset()
            self.spans.append((start, self._token_end(start)))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "svg" or self.svg_depth == 0:
            return
        self.svg_depth -= 1
        if self.svg_depth == 0:
            if self.current_start is None:
                raise ValueError("SVG nesting is inconsistent")
            self.spans.append(
                (self.current_start, self._token_end(self._offset()))
            )
            self.current_start = None


def _is_gallery_path(path: Path) -> bool:
    return path.name.lower() == "index.html" and path.parent.name.lower() == "assets"


def _read_source(path: Path) -> tuple[bytes, str]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        _fail(f"{path}: cannot read source: {exc.strerror or exc}")
    if not path.is_file():
        _fail(f"{path}: not a regular file")
    if size > MAX_INPUT_BYTES:
        _fail(
            f"{path.name}: input is {size} bytes; maximum is "
            f"{MAX_INPUT_BYTES // (1024 * 1024)} MiB"
        )
    try:
        data = path.read_bytes()
    except OSError as exc:
        _fail(f"{path}: cannot read source: {exc.strerror or exc}")
    try:
        return data, data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        _fail(f"{path}: source is not valid UTF-8: {exc}")


def _isolate_svg(path: Path, source: str) -> str:
    if _is_gallery_path(path):
        _fail(f"{path}: gallery source is not a single diagram")

    parser = SvgIsolationParser(source)
    try:
        parser.feed(source)
        parser.close()
    except (ValueError, AssertionError) as exc:
        _fail(f"{path}: cannot parse HTML: {exc}")

    if parser.svg_depth:
        _fail(f"{path}: unterminated <svg> element")
    if not parser.spans:
        _fail(f"{path}: no <svg> element found")
    if len(parser.spans) > 1:
        _fail(
            f"{path}: gallery source contains {len(parser.spans)} "
            "top-level <svg> elements"
        )
    start, end = parser.spans[0]
    return source[start:end]


# --------------------------------------------------------------------------
# SVG validation
# --------------------------------------------------------------------------


def _css_unescape(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1) is not None:
            codepoint = int(match.group(1), 16)
            if codepoint == 0 or codepoint > 0x10FFFF:
                return "\ufffd"
            return chr(codepoint)
        return match.group(2) or ""

    return CSS_ESCAPE_RE.sub(replace, value)


def _compact_for_scheme(value: str) -> str:
    decoded = html.unescape(_css_unescape(value)).strip()
    return re.sub(r"[\x00-\x20\x7f]+", "", decoded)


def _reference_error(
    value: str, *, context: str, allow_data_image: bool
) -> str | None:
    reference = html.unescape(_css_unescape(value)).strip()
    compact = _compact_for_scheme(reference)
    lowered = compact.lower()

    if lowered.startswith("javascript:"):
        return f"active javascript: URL in {context}"
    if reference.startswith("#"):
        return None
    if lowered.startswith("data:"):
        if allow_data_image and lowered.startswith("data:image/"):
            return None
        return f"non-image data: URI in {context} is not allowed"

    parsed = urlsplit(f"https:{reference}" if reference.startswith("//") else reference)
    if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
        host = parsed.hostname.lower().rstrip(".")
        if host in ALLOWED_EXTERNAL_HOSTS:
            return None
        return f"external {context} host {host!r} is not allowed"
    if parsed.scheme:
        return f"external {context} scheme {parsed.scheme!r} is not allowed"
    return f"external {context} reference {reference!r} is not allowed"


def _css_url_value(match: re.Match[str]) -> str:
    for name in ("double", "single", "bare"):
        value = match.group(name)
        if value is not None:
            return value.strip()
    return ""


def _import_value(target: str) -> str:
    target = target.strip()
    if target.lower().startswith("url"):
        match = CSS_URL_RE.fullmatch(target)
        return _css_url_value(match) if match else target
    if len(target) >= 2 and target[0] == target[-1] and target[0] in "\"'":
        return target[1:-1]
    return target


def _audit_css(css: str, context: str) -> str | None:
    css = _css_unescape(html.unescape(CSS_COMMENT_RE.sub("", css)))
    compact = _compact_for_scheme(css).lower()
    if "javascript:" in compact:
        return f"active javascript: URL in {context}"

    for match in CSS_IMPORT_RE.finditer(css):
        error = _reference_error(
            _import_value(match.group("target")),
            context="@import",
            allow_data_image=False,
        )
        if error:
            return error
    for match in CSS_URL_RE.finditer(css):
        error = _reference_error(
            _css_url_value(match), context="url()", allow_data_image=True
        )
        if error:
            return error
    return None


class SvgAuditParser(HTMLParser):
    """Collect the outer attributes and the first unsafe SVG construct."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.outer_attrs: list[tuple[str, str | None]] | None = None
        self.error: str | None = None
        self.has_foreign_object = False
        self.style_depth = 0
        self.style_parts: list[str] = []

    def _record(self, message: str) -> None:
        if self.error is None:
            self.error = message

    def _audit_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered_tag = tag.lower()
        if self.outer_attrs is None:
            if lowered_tag != "svg":
                self._record("extracted markup does not begin with <svg>")
                return
            self.outer_attrs = attrs

        if lowered_tag == "script":
            self._record("active <script> element is not allowed")
        elif lowered_tag == "foreignobject":
            self.has_foreign_object = True

        for name, value in attrs:
            lowered_name = name.lower()
            if lowered_name.startswith("on"):
                self._record(f"event-handler attribute {name!r} is not allowed")
            if value is None:
                continue
            decoded_value = _css_unescape(html.unescape(value))
            if _compact_for_scheme(value).lower().startswith("javascript:"):
                self._record(f"active javascript: URL in attribute {name!r}")
            if lowered_name in {"href", "xlink:href"}:
                error = _reference_error(
                    value,
                    context=lowered_name,
                    allow_data_image=lowered_tag in {"image", "feimage"},
                )
                if error:
                    self._record(error)
            attribute_css = CSS_COMMENT_RE.sub("", decoded_value)
            for match in CSS_URL_RE.finditer(attribute_css):
                error = _reference_error(
                    _css_url_value(match), context="url()", allow_data_image=True
                )
                if error:
                    self._record(error)
            if lowered_name == "style":
                error = _audit_css(value, "style attribute")
                if error:
                    self._record(error)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._audit_tag(tag, attrs)
        if tag.lower() == "style":
            self.style_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._audit_tag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style" and self.style_depth:
            self.style_depth -= 1
            if self.style_depth == 0:
                error = _audit_css("".join(self.style_parts), "<style>")
                if error:
                    self._record(error)
                self.style_parts.clear()

    def handle_data(self, data: str) -> None:
        if self.style_depth:
            self.style_parts.append(data)

    def finish(self) -> None:
        if self.style_parts:
            error = _audit_css("".join(self.style_parts), "<style>")
            if error:
                self._record(error)
            self.style_parts.clear()


def _parse_viewbox(attrs: list[tuple[str, str | None]]) -> ViewBox:
    values = [value for name, value in attrs if name.lower() == "viewbox"]
    if not values or values[0] is None:
        _fail("diagram <svg> is missing a viewBox")
    if len(values) > 1:
        _fail("diagram <svg> has duplicate viewBox attributes")

    raw = values[0]
    assert raw is not None
    parts = re.split(r"\s*,\s*|\s+", raw.strip())
    if len(parts) != 4:
        _fail(f"diagram <svg> has malformed viewBox {raw!r}; expected 4 numbers")
    try:
        numbers = tuple(float(part) for part in parts)
    except ValueError:
        _fail(f"diagram <svg> has malformed viewBox {raw!r}; expected 4 numbers")
    if not all(math.isfinite(number) for number in numbers):
        _fail(f"diagram <svg> has non-finite viewBox {raw!r}")
    min_x, min_y, width, height = numbers
    if width <= 0 or height <= 0:
        _fail(
            f"diagram <svg> viewBox must have positive width and height; got {raw!r}"
        )
    return ViewBox(raw, min_x, min_y, width, height)


def _check_source(path: Path) -> CheckedDiagram:
    data, source = _read_source(path)
    svg = _isolate_svg(path, source)
    parser = SvgAuditParser()
    try:
        parser.feed(svg)
        parser.close()
        parser.finish()
    except (ValueError, AssertionError) as exc:
        _fail(f"{path}: cannot parse extracted SVG: {exc}")
    if parser.error:
        _fail(f"{path}: {parser.error}")
    if parser.outer_attrs is None:
        _fail(f"{path}: no usable <svg> element found")
    viewbox = _parse_viewbox(parser.outer_attrs)
    if parser.has_foreign_object:
        _warn(
            f"{path}: <foreignObject> present — "
            "Figma/import fidelity is not guaranteed"
        )
    return CheckedDiagram(path, hashlib.sha256(data).hexdigest(), svg, viewbox)


# --------------------------------------------------------------------------
# standalone SVG construction
# --------------------------------------------------------------------------


class SvgLayoutParser(HTMLParser):
    """Find insertion points without re-serializing any source markup."""

    def __init__(self, svg: str) -> None:
        super().__init__(convert_charrefs=True)
        self.svg = svg
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer("\n", svg))
        self.stack: list[str] = []
        self.root_seen = False
        self.root_self_closing = False
        self.opening_end: int | None = None
        self.first_defs: tuple[int, int, bool] | None = None
        self.preamble_open = True
        self.preamble_end: int | None = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _raw_end(self) -> int:
        raw = self.get_starttag_text()
        if raw is None:
            raise ValueError("cannot locate start tag")
        return self._offset() + len(raw)

    def _endtag_end(self) -> int:
        end = self.svg.find(">", self._offset())
        if end < 0:
            raise ValueError("unterminated end tag")
        return end + 1

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        lowered = tag.lower()
        start = self._offset()
        end = self._raw_end()
        if not self.root_seen:
            self.root_seen = True
            self.opening_end = end
            self.stack.append(lowered)
            return

        direct_child = len(self.stack) == 1
        if lowered == "defs" and self.first_defs is None:
            self.first_defs = (start, end, False)
        if direct_child and self.preamble_open and lowered not in {"title", "desc"}:
            self.preamble_open = False
        self.stack.append(lowered)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        lowered = tag.lower()
        start = self._offset()
        end = self._raw_end()
        if not self.root_seen:
            self.root_seen = True
            self.root_self_closing = True
            self.opening_end = end
            return

        direct_child = len(self.stack) == 1
        if lowered == "defs" and self.first_defs is None:
            self.first_defs = (start, end, True)
        if direct_child and self.preamble_open:
            if lowered in {"title", "desc"}:
                self.preamble_end = end
            else:
                self.preamble_open = False

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in self.stack:
            matching_index = len(self.stack) - 1 - self.stack[::-1].index(lowered)
            direct_child = matching_index == 1
            self.stack = self.stack[:matching_index]
            if (
                direct_child
                and self.preamble_open
                and lowered in {"title", "desc"}
            ):
                self.preamble_end = self._endtag_end()

    def handle_data(self, data: str) -> None:
        if self.root_seen and len(self.stack) == 1 and data.strip():
            self.preamble_open = False


def _ensure_xmlns(opening: str) -> str:
    match = XMLNS_RE.search(opening)
    if match:
        value = match.group("value")
        unquoted = value[1:-1] if value[:1] in {"\"", "'"} else value
        if unquoted == SVG_NAMESPACE:
            return opening
        return opening[: match.start("value")] + f'"{SVG_NAMESPACE}"' + opening[match.end("value") :]

    insert_at = len(opening) - 1
    cursor = insert_at - 1
    while cursor >= 0 and opening[cursor].isspace():
        cursor -= 1
    if cursor >= 0 and opening[cursor] == "/":
        insert_at = cursor
    return opening[:insert_at] + f' xmlns="{SVG_NAMESPACE}"' + opening[insert_at:]


def _expand_self_closing(opening: str) -> str:
    close = re.search(r"/\s*>$", opening)
    if close is None:
        return opening
    return opening[: close.start()] + opening[close.start() + 1 :]


def _standalone_svg(svg: str) -> str:
    layout = SvgLayoutParser(svg)
    try:
        layout.feed(svg)
        layout.close()
    except (ValueError, AssertionError) as exc:
        _fail(f"cannot prepare standalone SVG: {exc}")
    if layout.opening_end is None:
        _fail("cannot locate the diagram <svg> opening tag")

    opening = _ensure_xmlns(svg[: layout.opening_end])
    if layout.root_self_closing:
        body = _expand_self_closing(opening) + FONT_DEFS + "</svg>"
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + body

    body = opening + svg[layout.opening_end :]
    opening_delta = len(opening) - layout.opening_end
    if layout.first_defs is not None:
        defs_start, defs_end, self_closing = layout.first_defs
        defs_start += opening_delta
        defs_end += opening_delta
        if self_closing:
            defs_open = _expand_self_closing(body[defs_start:defs_end])
            body = (
                body[:defs_start]
                + defs_open
                + FONT_STYLE
                + "</defs>"
                + body[defs_end:]
            )
        else:
            body = body[:defs_end] + FONT_STYLE + body[defs_end:]
    else:
        insert_at = (
            layout.preamble_end
            if layout.preamble_end is not None
            else layout.opening_end
        )
        insert_at += opening_delta
        body = body[:insert_at] + FONT_DEFS + body[insert_at:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body


def _verify_xml_clean(svg: str, source: Path) -> None:
    try:
        ET.fromstring(svg)
    except ET.ParseError as exc:
        _fail(f"{source}: source SVG is not XML-clean: {exc}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _format_number(number: float) -> str:
    return f"{number:.15g}"


def _run_check(args: argparse.Namespace) -> int:
    diagram = _check_source(Path(args.src))
    dimensions = (
        f"{_format_number(diagram.viewbox.width)}x"
        f"{_format_number(diagram.viewbox.height)}"
    )
    print(
        f'ok source={diagram.source} viewBox="{diagram.viewbox.raw}" '
        f"dimensions={dimensions} sha256={diagram.source_sha256}"
    )
    return 0


def _write_stdout_bytes(data: bytes) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(data)
        buffer.flush()
    else:  # Useful for callers that replace stdout with io.StringIO.
        sys.stdout.write(data.decode("utf-8"))


def _run_extract(args: argparse.Namespace) -> int:
    diagram = _check_source(Path(args.src))
    standalone = _standalone_svg(diagram.svg)
    _verify_xml_clean(standalone, diagram.source)
    output = standalone.encode("utf-8")
    if args.stdout:
        _write_stdout_bytes(output)
        return 0

    out_path = Path(args.out) if args.out else diagram.source.with_suffix(".svg")
    same_file = out_path.resolve() == diagram.source.resolve()
    try:
        same_file = same_file or (out_path.exists() and out_path.samefile(diagram.source))
    except OSError:
        pass
    if same_file:
        _fail(f"output path {out_path} would overwrite the source HTML")
    try:
        out_path.write_bytes(output)
    except OSError as exc:
        _fail(f"{out_path}: cannot write output: {exc.strerror or exc}")
    print(f"source: {diagram.source}")
    print(f"output: {out_path}")
    print(f"viewBox: {diagram.viewbox.raw}")
    print(f"source_sha256: {diagram.source_sha256}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract", help="validate diagram HTML and emit a standalone SVG"
    )
    extract_parser.add_argument("src", help="source diagram HTML file")
    output_group = extract_parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--stdout", action="store_true", help="write only the SVG to stdout"
    )
    output_group.add_argument(
        "--out", metavar="PATH", help="write SVG to PATH instead of next to source"
    )
    extract_parser.set_defaults(handler=_run_extract)

    check_parser = subparsers.add_parser(
        "check", help="validate diagram HTML without writing output"
    )
    check_parser.add_argument("src", help="source diagram HTML file")
    check_parser.set_defaults(handler=_run_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
