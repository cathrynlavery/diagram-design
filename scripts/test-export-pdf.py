#!/usr/bin/env python3
"""Deterministic tests for the packaged vector PDF exporter.

Drives ``skills/diagram-design/scripts/export_pdf.py`` against shipped diagrams
and local fixtures:

- static structural anchors (stalled-load cancellation, ?motion=static, no bare except);
- CLI validation (missing input, gallery refusal, missing/invalid viewBox exit 2);
- exact viewBox-sized single-page vector PDF output on light, dark, and animated diagrams,
  including the animated diagram's final-step labels and a broken-controller refusal;
- landscape sheet sizing (--page-size a4) and --full-page editorial wrapper capture;
- stalled stylesheet cancellation via window.stop() with fallback typography warning.

Requires Playwright (and Chromium); skips browser cases otherwise, matching
``scripts/test-export-wait.py``.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_PDF = ROOT / "skills/diagram-design/scripts/export_pdf.py"
ASSETS = ROOT / "skills/diagram-design/assets"

FAST_IDLE_TIMEOUT_MS = 1_500
FAST_SETTLE_MS = 150
STALL_HOLD_SECONDS = 30
FALLBACK_BUDGET_SECONDS = 15.0
WARNING_ANCHOR = "fallback typography"


def check_source_anchors() -> None:
    source = EXPORT_PDF.read_text(encoding="utf-8")
    for anchor in (
        "except PlaywrightTimeoutError:",
        'page.evaluate("window.stop()")',
        "NETWORK_IDLE_TIMEOUT_MS = 15_000",
        "?motion=static",
        "document.fonts.ready",
        "[data-motion-root]",
        "print_background=True",
    ):
        if anchor not in source:
            raise AssertionError(f"export_pdf.py missing required anchor {anchor!r}")
    if "except Exception" in source or "except:" in source:
        raise AssertionError("export_pdf.py must not swallow non-timeout errors")
    print("OK: source anchors verified")


def parse_pdf_mediaboxes(pdf_bytes: bytes) -> list[tuple[float, float, float, float]]:
    if not pdf_bytes.startswith(b"%PDF-"):
        raise AssertionError("output does not start with %PDF- header")
    boxes: list[tuple[float, float, float, float]] = []
    for match in re.finditer(
        rb"/MediaBox\s*\[\s*([0-9.+-]+)\s+([0-9.+-]+)\s+([0-9.+-]+)\s+([0-9.+-]+)\s*\]",
        pdf_bytes,
    ):
        boxes.append(tuple(float(v) for v in match.groups()))  # type: ignore[arg-type]
    return boxes


def pdf_has_vector_content(pdf_bytes: bytes) -> bool:
    """Confirm at least one Flate-compressed content stream contains PDF drawing/text ops."""
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf_bytes, re.DOTALL):
        raw = match.group(1)
        try:
            decoded = zlib.decompress(raw)
        except zlib.error:
            decoded = raw
        if b"BT" in decoded or b" re" in decoded or b" m\n" in decoded:
            return True
    return False


def _iter_pdf_objects(pdf_bytes: bytes):
    """Yield ``(obj_num, dict_bytes, stream_or_none)`` for each body object."""
    position = 0
    while True:
        match = re.search(rb"(\d+)\s+0\s+obj", pdf_bytes[position:])
        if match is None:
            break
        cursor = position + match.end()
        while cursor < len(pdf_bytes) and pdf_bytes[cursor] in b" \r\n\t":
            cursor += 1
        if not pdf_bytes.startswith(b"<<", cursor):
            position = position + match.end()
            continue
        depth = 0
        end = cursor
        while end < len(pdf_bytes):
            if pdf_bytes.startswith(b"<<", end):
                depth += 1
                end += 2
                continue
            if pdf_bytes.startswith(b">>", end):
                depth -= 1
                end += 2
                if depth == 0:
                    break
                continue
            end += 1
        dict_bytes = pdf_bytes[cursor:end]
        cursor = end
        while cursor < len(pdf_bytes) and pdf_bytes[cursor] in b" \r\n\t":
            cursor += 1
        stream = None
        if pdf_bytes.startswith(b"stream", cursor):
            cursor += len(b"stream")
            if pdf_bytes.startswith(b"\r\n", cursor):
                cursor += 2
            elif pdf_bytes.startswith(b"\n", cursor):
                cursor += 1
            length_match = re.search(rb"/Length\s+(\d+)\b(?!\s+0\s+R)", dict_bytes)
            if length_match is None:
                endstream = pdf_bytes.find(b"endstream", cursor)
                raw = pdf_bytes[cursor:endstream]
                if raw.endswith(b"\r\n"):
                    raw = raw[:-2]
                elif raw.endswith(b"\n"):
                    raw = raw[:-1]
                cursor = endstream + len(b"endstream")
            else:
                length = int(length_match.group(1))
                raw = pdf_bytes[cursor : cursor + length]
                cursor += length
            try:
                stream = zlib.decompress(raw)
            except zlib.error:
                stream = raw
        yield int(match.group(1)), dict_bytes, stream
        position = cursor


def _decode_pdf_unicode(hex_text: bytes) -> str:
    raw = bytes.fromhex(hex_text.decode())
    if len(raw) == 1:
        return raw.decode("latin-1")
    if len(raw) % 2:
        raw = raw[:-1]
    return raw.decode("utf-16-be", "replace")


def _parse_tounicode(cmap: bytes) -> tuple[dict[int, str], int]:
    """Map glyph ids from a ToUnicode CMap, plus the source code width in bytes."""
    mapping: dict[int, str] = {}
    width = 1

    def remember(source: bytes, character: str) -> None:
        nonlocal width
        width = max(width, max(1, len(source) // 2))
        mapping[int(source, 16)] = character

    for block in re.finditer(rb"beginbfchar(.*?)endbfchar", cmap, re.DOTALL):
        for source, dest in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block.group(1)):
            remember(source, _decode_pdf_unicode(dest))
    for block in re.finditer(rb"beginbfrange(.*?)endbfrange", cmap, re.DOTALL):
        body = block.group(1)
        for source_start, _source_end, array in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]",
            body,
            re.DOTALL,
        ):
            padded = len(source_start)
            for offset, dest in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", array)):
                glyph = int(source_start, 16) + offset
                remember(format(glyph, f"0{padded}X").encode(), _decode_pdf_unicode(dest))
        body = re.sub(
            rb"<[0-9A-Fa-f]+>\s*<[0-9A-Fa-f]+>\s*\[.*?\]",
            b"",
            body,
            flags=re.DOTALL,
        )
        for source_start, source_end, dest in re.findall(
            rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>",
            body,
        ):
            start, end = int(source_start, 16), int(source_end, 16)
            character = _decode_pdf_unicode(dest)
            padded = len(source_start)
            if len(character) != 1:
                remember(source_start, character)
                continue
            base = ord(character)
            for glyph in range(start, end + 1):
                remember(format(glyph, f"0{padded}X").encode(), chr(base + glyph - start))
    return mapping, width


def _decode_pdf_literal(body: bytes) -> str:
    output = bytearray()
    index = 0
    escapes = {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t", ord("b"): b"\b", ord("f"): b"\f", ord("("): b"(", ord(")"): b")", ord("\\"): b"\\"}
    while index < len(body):
        byte = body[index]
        if byte != 0x5C:
            output.append(byte)
            index += 1
            continue
        index += 1
        if index >= len(body):
            break
        escaped = body[index]
        if escaped in escapes:
            output.extend(escapes[escaped])
            index += 1
        elif 48 <= escaped <= 55:
            octal = bytearray((escaped,))
            index += 1
            for _ in range(2):
                if index < len(body) and 48 <= body[index] <= 55:
                    octal.append(body[index])
                    index += 1
                else:
                    break
            output.append(int(octal, 8) & 0xFF)
        elif escaped in (10, 13):
            index += 1
            if escaped == 13 and index < len(body) and body[index] == 10:
                index += 1
        else:
            output.append(escaped)
            index += 1
    return output.decode("utf-8", "replace")


def _decode_show_text(hex_body: bytes, mapping: dict[int, str], width: int) -> str:
    compact = re.sub(rb"\s+", b"", hex_body)
    if not compact:
        return ""
    if len(compact) % 2:
        compact = b"0" + compact
    raw = bytes.fromhex(compact.decode())
    step = width if width > 0 else 1
    if step > 1 and len(raw) % step:
        step = 1
    characters: list[str] = []
    for index in range(0, len(raw), step):
        glyph = raw[index : index + step]
        if len(glyph) < step:
            break
        characters.append(mapping.get(int.from_bytes(glyph, "big"), ""))
    return "".join(characters)


def _decode_content_stream(content: bytes, fonts: dict[str, tuple[dict[int, str], int]]) -> str:
    current: tuple[dict[int, str], int] | None = next(iter(fonts.values())) if len(fonts) == 1 else None
    pieces: list[str] = []
    show = re.compile(
        rb"/([A-Za-z0-9]+)\s+[0-9.]+\s+Tf"
        rb"|<([0-9A-Fa-f\s]*)>\s*Tj"
        rb"|\(((?:\\.|[^\\)])*)\)\s*Tj"
        rb"|\[(.*?)\]\s*TJ",
        re.DOTALL,
    )
    inner = re.compile(rb"<([0-9A-Fa-f\s]*)>|\(((?:\\.|[^\\)])*)\)")
    for match in show.finditer(content):
        font_name, hex_text, literal, array = match.groups()
        if font_name is not None:
            current = fonts.get(font_name.decode(), current)
            continue
        if current is None:
            continue
        mapping, width = current
        if hex_text is not None:
            pieces.append(_decode_show_text(hex_text, mapping, width))
        elif literal is not None:
            pieces.append(_decode_pdf_literal(literal))
        elif array is not None:
            for inner_hex, inner_literal in inner.findall(array):
                if inner_hex:
                    pieces.append(_decode_show_text(inner_hex, mapping, width))
                else:
                    pieces.append(_decode_pdf_literal(inner_literal))
    return "".join(pieces)


def pdf_text(pdf_bytes: bytes) -> str:
    """Extract shown text using each font's ToUnicode CMap.

    Chromium writes glyph ids rather than literal characters. This is the text
    half of the vector-stream check ``pdf_has_vector_content`` already applies
    to light and dark exports.
    """
    objects = {
        number: (dictionary, stream)
        for number, dictionary, stream in _iter_pdf_objects(pdf_bytes)
    }
    cmaps: dict[int, tuple[dict[int, str], int]] = {}
    for number, (_dictionary, stream) in objects.items():
        if stream and (b"beginbfchar" in stream or b"beginbfrange" in stream):
            cmaps[number] = _parse_tounicode(stream)
    font_cmaps: dict[int, tuple[dict[int, str], int]] = {}
    for number, (dictionary, _stream) in objects.items():
        link = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", dictionary)
        if link and int(link.group(1)) in cmaps:
            font_cmaps[number] = cmaps[int(link.group(1))]
    chunks: list[str] = []
    for dictionary, _stream in objects.values():
        array = re.search(rb"/Contents\s*\[(.*?)\]", dictionary, re.DOTALL)
        if array:
            contents = [int(number) for number in re.findall(rb"(\d+)\s+0\s+R", array.group(1))]
        else:
            contents = [int(number) for number in re.findall(rb"/Contents\s+(\d+)\s+0\s+R", dictionary)]
        if not contents:
            continue
        font_block = re.search(rb"/Font\s*<<(.*?)>>", dictionary, re.DOTALL)
        fonts: dict[str, tuple[dict[int, str], int]] = {}
        if font_block:
            for name, ref in re.findall(rb"/([A-Za-z0-9]+)\s+(\d+)\s+0\s+R", font_block.group(1)):
                cmap = font_cmaps.get(int(ref))
                if cmap is not None:
                    fonts[name.decode()] = cmap
        for content_number in contents:
            content = objects.get(content_number, (b"", None))[1]
            if content:
                chunks.append(_decode_content_stream(content, fonts))
    return re.sub(r"\s+", " ", "".join(chunks)).strip()


def last_motion_step_labels(html: str) -> list[str]:
    """Visible ``<text>`` labels on the highest ``data-step`` group."""
    count_match = re.search(r'data-step-count="(\d+)"', html)
    if count_match is None:
        return []
    step = count_match.group(1)
    group = re.search(rf'<g\b[^>]*\bdata-step="{step}"[^>]*>(.*?)</g>', html, re.DOTALL)
    if group is None:
        return []
    labels: list[str] = []
    for raw in re.findall(r"<text\b[^>]*>(.*?)</text>", group.group(1), re.DOTALL):
        label = re.sub(r"<[^>]+>", "", raw)
        label = label.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
        label = re.sub(r"\s+", " ", label).strip()
        if label and label not in labels:
            labels.append(label)
    return labels


class _StallHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/stall"):
            time.sleep(STALL_HOLD_SECONDS)
            self.send_error(500)
            return
        self.send_error(404)

    def log_message(self, *args: object) -> None:
        pass


def start_stall_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StallHandler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_cli(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(EXPORT_PDF), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def require_cli_errors(tmp: Path) -> None:
    # Missing input
    r = run_cli(str(tmp / "does-not-exist.html"), str(tmp / "out.pdf"))
    if r.returncode != 2:
        raise AssertionError(f"missing file should exit 2, got {r.returncode}: {r.stderr}")

    # Gallery refusal
    gallery = ASSETS / "index.html"
    if gallery.is_file():
        r = run_cli(str(gallery), str(tmp / "gallery.pdf"))
        if r.returncode != 2 or "gallery" not in r.stderr.lower():
            raise AssertionError(f"gallery refusal expected exit 2, got {r.returncode}: {r.stderr}")

    # Invalid --page-size
    r = run_cli("--page-size", "tabloid", str(tmp / "x.html"))
    if r.returncode != 2:
        raise AssertionError(f"invalid page-size should exit 2, got {r.returncode}")

    # Missing SVG
    no_svg = tmp / "no-svg.html"
    no_svg.write_text("<!doctype html><html><body><p>text only</p></body></html>\n", encoding="utf-8")
    r = run_cli(str(no_svg), str(tmp / "no-svg.pdf"))
    if r.returncode != 2:
        raise AssertionError(f"no-svg should exit 2, got {r.returncode}: {r.stderr}")

    # Missing viewBox
    bad_vb = tmp / "no-viewbox.html"
    bad_vb.write_text(
        "<!doctype html><html><body><svg width='200' height='100'><rect width='200' height='100'/></svg></body></html>\n",
        encoding="utf-8",
    )
    r = run_cli(str(bad_vb), str(tmp / "no-viewbox.pdf"))
    if r.returncode != 2:
        raise AssertionError(f"missing viewBox should exit 2, got {r.returncode}: {r.stderr}")

    print("OK: CLI fail-closed error cases verified")


def require_diagram_exports(tmp: Path) -> None:
    # Light diagram (default output path next to copy)
    light_src = ASSETS / "example-architecture.html"
    light_out = tmp / "arch-light.pdf"
    r = run_cli(str(light_src), str(light_out))
    if r.returncode != 0:
        raise AssertionError(f"light export failed ({r.returncode}): {r.stderr}")
    data = light_out.read_bytes()
    boxes = parse_pdf_mediaboxes(data)
    if len(boxes) != 1:
        raise AssertionError(f"expected single-page exact-bounds PDF, got {len(boxes)} MediaBoxes: {boxes}")
    w_pt, h_pt = boxes[0][2] - boxes[0][0], boxes[0][3] - boxes[0][1]
    # Parse actual viewBox from example-architecture.html (px * 72/96 -> PDF pt)
    vb_match = re.search(r'viewBox="([^"]+)"', light_src.read_text(encoding="utf-8"))
    if not vb_match:
        raise AssertionError("example-architecture.html missing viewBox")
    _, _, vb_w, vb_h = (float(v) for v in vb_match.group(1).split())
    exp_w, exp_h = vb_w * 0.75, vb_h * 0.75
    if not (exp_w - 5 <= w_pt <= exp_w + 5 and exp_h - 5 <= h_pt <= exp_h + 5):
        raise AssertionError(
            f"unexpected MediaBox for {vb_w:.0f}x{vb_h:.0f} viewBox: {w_pt:.1f}x{h_pt:.1f}pt "
            f"(expected {exp_w:.1f}x{exp_h:.1f}pt)"
        )
    if not pdf_has_vector_content(data):
        raise AssertionError("light PDF missing vector drawing/text operations")
    print(f"OK: light exact-bounds PDF verified ({w_pt:.0f}x{h_pt:.0f}pt, {len(data)} bytes)")

    # Dark diagram
    dark_src = ASSETS / "example-architecture-dark.html"
    dark_out = tmp / "arch-dark.pdf"
    r = run_cli(str(dark_src), str(dark_out))
    if r.returncode != 0:
        raise AssertionError(f"dark export failed ({r.returncode}): {r.stderr}")
    dark_boxes = parse_pdf_mediaboxes(dark_out.read_bytes())
    if len(dark_boxes) != 1:
        raise AssertionError(f"expected single-page dark PDF, got {len(dark_boxes)}")
    print(f"OK: dark exact-bounds PDF verified ({dark_out.stat().st_size} bytes)")

    # Animated diagram (?motion=static enforcement). The final frame has to carry
    # the last step's labels; a header-only check would accept a blank page.
    anim_src = ASSETS / "example-policy-trace-animated.html"
    if anim_src.is_file():
        anim_html = anim_src.read_text(encoding="utf-8")
        labels = last_motion_step_labels(anim_html)
        if not labels:
            raise AssertionError("example-policy-trace-animated.html has no last-step labels")
        anim_out = tmp / "anim.pdf"
        r = run_cli(str(anim_src), str(anim_out))
        if r.returncode != 0:
            raise AssertionError(f"animated export failed ({r.returncode}): {r.stderr}")
        anim_bytes = anim_out.read_bytes()
        parse_pdf_mediaboxes(anim_bytes)
        if not pdf_has_vector_content(anim_bytes):
            raise AssertionError("animated PDF missing vector drawing/text operations")
        extracted = pdf_text(anim_bytes)
        missing = [label for label in labels if label not in extracted]
        if missing:
            raise AssertionError(
                f"animated PDF missing last-step labels {missing!r}; extracted text starts {extracted[:500]!r}"
            )
        print(f"OK: animated ?motion=static PDF verified ({len(anim_bytes)} bytes, last step {labels[0]!r})")

        # A broken controller must fail closed instead of writing a partial frame.
        broken_html = re.sub(r"<link\b[^>]*>", "", anim_html, flags=re.I)
        broken_html = re.sub(r"<script\b[^>]*>.*?</script>", "", broken_html, flags=re.I | re.S)
        broken_html = broken_html.replace(
            'data-frame="static" data-static-frame=',
            'data-frame="start" data-static-frame=',
            1,
        )
        broken_src = tmp / "broken-motion.html"
        broken_out = tmp / "broken-motion.pdf"
        broken_src.write_text(broken_html, encoding="utf-8")
        r = run_cli(str(broken_src), str(broken_out))
        if r.returncode == 0 or broken_out.exists():
            raise AssertionError(
                "broken motion controller should exit non-zero and write no PDF, "
                f"got exit {r.returncode}, pdf_exists={broken_out.exists()}: {r.stderr}"
            )
        if "static" not in r.stderr:
            raise AssertionError(f"broken motion controller failed without a static-frame diagnostic: {r.stderr}")
        print("OK: broken motion controller writes no PDF")

    # Landscape A4 sheet mode
    a4_out = tmp / "arch-a4.pdf"
    r = run_cli("--page-size", "a4", str(light_src), str(a4_out))
    if r.returncode != 0:
        raise AssertionError(f"A4 export failed ({r.returncode}): {r.stderr}")
    a4_boxes = parse_pdf_mediaboxes(a4_out.read_bytes())
    if len(a4_boxes) != 1:
        raise AssertionError(f"expected 1 A4 page, got {len(a4_boxes)}")
    aw, ah = a4_boxes[0][2] - a4_boxes[0][0], a4_boxes[0][3] - a4_boxes[0][1]
    # 11.69in x 8.27in -> ~841.7pt x 595.4pt
    if not (835 <= aw <= 848 and 590 <= ah <= 602):
        raise AssertionError(f"unexpected A4 landscape MediaBox: {aw:.1f}x{ah:.1f}pt")
    print(f"OK: --page-size a4 landscape PDF verified ({aw:.0f}x{ah:.0f}pt)")

    # Full-page editorial wrapper mode
    full_src = ASSETS / "example-architecture-full.html"
    if full_src.is_file():
        full_out = tmp / "arch-full.pdf"
        r = run_cli("--full-page", str(full_src), str(full_out))
        if r.returncode != 0:
            raise AssertionError(f"full-page export failed ({r.returncode}): {r.stderr}")
        full_boxes = parse_pdf_mediaboxes(full_out.read_bytes())
        if not full_boxes:
            raise AssertionError("full-page PDF has no MediaBox")
        fh = full_boxes[0][3] - full_boxes[0][1]
        if fh <= h_pt:
            raise AssertionError(f"full-page height ({fh:.1f}pt) should exceed diagram-only height ({h_pt:.1f}pt)")
        print(f"OK: --full-page editorial PDF verified ({full_boxes[0][2]:.0f}x{fh:.0f}pt)")


def require_stalled_fallback(tmp: Path) -> None:
    server = start_stall_server()
    try:
        port = server.server_address[1]
        src = tmp / "stall-pdf.html"
        src.write_text(
            "<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n"
            f"<link rel='stylesheet' href='http://127.0.0.1:{port}/stall.css'>\n"
            "</head>\n<body>\n"
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 240' "
            "width='400' height='240' role='img' aria-labelledby='s-title'>\n"
            "<title id='s-title'>Stall PDF fixture</title>\n"
            "<rect width='400' height='240' fill='#ffffff'/>\n"
            "<text x='200' y='124' text-anchor='middle' font-family='sans-serif' "
            "font-size='20' fill='#111111'>stall fixture</text>\n"
            "</svg>\n</body>\n</html>\n",
            encoding="utf-8",
        )
        out = tmp / "stall-pdf.pdf"
        runner = (
            "import importlib.util, pathlib, sys; "
            "spec = importlib.util.spec_from_file_location('export_pdf', sys.argv[1]); "
            "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); "
            "m.export_pdf(pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3]), "
            "network_idle_timeout_ms=int(sys.argv[4]), fallback_settle_ms=int(sys.argv[5]))"
        )
        started = time.monotonic()
        res = subprocess.run(
            [
                sys.executable,
                "-c",
                runner,
                str(EXPORT_PDF),
                str(src),
                str(out),
                str(FAST_IDLE_TIMEOUT_MS),
                str(FAST_SETTLE_MS),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=FALLBACK_BUDGET_SECONDS,
        )
        elapsed = time.monotonic() - started
        if not out.is_file() or not out.read_bytes().startswith(b"%PDF-"):
            raise AssertionError("stalled-fallback did not produce a valid PDF")
        if WARNING_ANCHOR not in res.stderr:
            raise AssertionError(f"expected {WARNING_ANCHOR!r} warning on stderr, got {res.stderr!r}")
        print(f"OK: stalled stylesheet fallback verified in {elapsed:.1f}s")
    finally:
        server.shutdown()
        server.server_close()


def main() -> int:
    check_source_anchors()
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("SKIP: playwright not installed; skipped browser PDF export tests")
        return 0

    with tempfile.TemporaryDirectory(prefix="diagram-export-pdf-") as raw_tmp:
        tmp = Path(raw_tmp)
        require_cli_errors(tmp)
        require_diagram_exports(tmp)
        require_stalled_fallback(tmp)
    print("ALL PDF EXPORT TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
