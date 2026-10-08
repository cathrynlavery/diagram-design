#!/usr/bin/env python3
"""Deterministic tests for the packaged PNG exporter's stalled-load fallback.

Drives ``skills/diagram-design/scripts/export_png.py`` against local fixtures:

- a stalled stylesheet request is cancelled with window.stop(), the renderer
  warns about fallback typography, and capture completes quickly;
- an actual stalled font download is cancelled and font readiness finishes;
- a normal load captures cleanly with no warning;
- non-timeout errors are not swallowed by the fallback.

Requires Playwright (and its Chromium); skips otherwise, matching the export
procedure's own detection step.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_PNG = ROOT / "skills/diagram-design/scripts/export_png.py"

# Fast-but-deterministic substitutes for the renderer's production waits.
FAST_IDLE_TIMEOUT_MS = 1_500
FAST_SETTLE_MS = 150
STALL_HOLD_SECONDS = 30  # must outlast the test's networkidle timeout
WARNING_ANCHOR = "fallback typography"
# The full fallback (fast timeout + settle + capture) must stay far below the
# production path's 15s networkidle + 4s settle budget.
FALLBACK_BUDGET_SECONDS = 15.0


def load_exporter():
    source = EXPORT_PNG.read_text(encoding="utf-8")
    for anchor in (
        "except PlaywrightTimeoutError:",
        'page.evaluate("window.stop()")',
        WARNING_ANCHOR,
        "NETWORK_IDLE_TIMEOUT_MS = 15_000",
    ):
        if anchor not in source:
            raise AssertionError(f"packaged exporter is missing required anchor {anchor!r}")
    if "except Exception" in source or "except:" in source:
        raise AssertionError(
            "packaged exporter must not swallow non-timeout errors with a "
            "broad or bare except"
        )
    spec = importlib.util.spec_from_file_location("diagram_export_png", EXPORT_PNG)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not import {EXPORT_PNG}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _StallHandler(BaseHTTPRequestHandler):
    """Serves nothing: holds /stall* requests open so the load never settles."""

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.startswith("/stall"):
            time.sleep(STALL_HOLD_SECONDS)
            self.send_error(500)
            return
        self.send_error(404)

    def log_message(self, *args: object) -> None:
        pass


def start_stall_server(handler: type[BaseHTTPRequestHandler] = _StallHandler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def run_export(exporter, src: Path, out: Path, **kwargs: int) -> str:
    """Run the packaged renderer and return captured stderr."""
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        exporter.rasterize(src, out, 2, **kwargs)
    return stderr.getvalue()


def require_png(out: Path, name: str) -> None:
    if not out.exists() or out.stat().st_size == 0:
        raise AssertionError(f"{name}: expected a non-empty screenshot at {out}")


def run_cli_without_scale(src: Path, out: Path) -> str:
    run = subprocess.run(
        [sys.executable, str(EXPORT_PNG), str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=FALLBACK_BUDGET_SECONDS,
    )
    if run.returncode != 0:
        raise AssertionError(f"normal-load: packaged renderer failed\n{run.stderr}")
    return run.stderr


def png_dimensions(out: Path) -> tuple[int, int]:
    png = out.read_bytes()
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or len(png) < 24:
        raise AssertionError("normal-load: renderer did not produce a valid PNG header")
    return struct.unpack(">II", png[16:24])


def require_stalled_fallback(exporter, tmp: Path) -> None:
    server = start_stall_server()
    try:
        port = server.server_address[1]
        src = tmp / "stall-fixture.html"
        src.write_text(
            "<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n"
            f"<link rel='stylesheet' href='http://127.0.0.1:{port}/stall.css'>\n"
            "</head>\n<body>\n"
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 240' "
            "width='400' height='240' role='img' aria-labelledby='stall-title'>\n"
            "<title id='stall-title'>Stall fixture diagram</title>\n"
            "<rect width='400' height='240' fill='#ffffff'/>\n"
            "<text x='200' y='124' text-anchor='middle' font-family='sans-serif' "
            "font-size='24' fill='#111111'>stall fixture</text>\n"
            "</svg>\n</body>\n</html>\n",
            encoding="utf-8",
        )
        out = tmp / "stall-fixture.png"

        started = time.monotonic()
        stderr = run_export(
            exporter,
            src,
            out,
            network_idle_timeout_ms=FAST_IDLE_TIMEOUT_MS,
            fallback_settle_ms=FAST_SETTLE_MS,
        )
        elapsed = time.monotonic() - started

        require_png(out, "stalled-fallback")
        if WARNING_ANCHOR not in stderr:
            raise AssertionError(
                f"stalled-fallback: expected a {WARNING_ANCHOR!r} warning on stderr\n{stderr}"
            )
        if elapsed > FALLBACK_BUDGET_SECONDS:
            raise AssertionError(
                f"stalled-fallback: capture took {elapsed:.1f}s, over the "
                f"{FALLBACK_BUDGET_SECONDS:.0f}s budget - window.stop() did not "
                "release the stalled load"
            )
        print(
            f"OK: stalled stylesheet cancels via window.stop(), warns, "
            f"and captures in {elapsed:.1f}s"
        )
    finally:
        server.shutdown()
        server.server_close()


def require_stalled_font_fallback(snippet: str, tmp: Path) -> None:
    fast = snippet.replace("timeout=15000", FAST_IDLE_TIMEOUT).replace(
        "wait_for_timeout(4000)", FAST_SETTLE
    )
    font_requested = threading.Event()

    class FontStallHandler(_StallHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            if self.path == "/stall.woff2":
                font_requested.set()
            super().do_GET()

    server = start_stall_server(FontStallHandler)
    try:
        port = server.server_address[1]
        src = tmp / "stalled-font.html"
        src.write_text(
            "<!doctype html><meta charset='utf-8'><style>"
            "@font-face{font-family:OwnedStalledFont;src:url("
            f"http://127.0.0.1:{port}/stall.woff2) format('woff2')}}"
            "</style><svg xmlns='http://www.w3.org/2000/svg' "
            "viewBox='0 0 400 240' width='400' height='240'>"
            "<text x='20' y='120' font-family='OwnedStalledFont,sans-serif'>"
            "stalled font fixture</text></svg>",
            encoding="utf-8",
        )
        out = tmp / "stalled-font.png"
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-c", fast, str(src), str(out)],
            capture_output=True, text=True, check=True,
            timeout=FALLBACK_BUDGET_SECONDS,
        )
        stderr = result.stderr
        elapsed = time.monotonic() - started
        if not font_requested.is_set():
            raise AssertionError("stalled-font: fixture never started its font download")
        require_png(out, "stalled-font")
        if not out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise AssertionError("stalled-font: output is not a PNG")
        if WARNING_ANCHOR not in stderr:
            raise AssertionError(f"stalled-font: fallback warning did not fire\n{stderr}")
        if elapsed > FALLBACK_BUDGET_SECONDS:
            raise AssertionError(
                f"stalled-font: capture took {elapsed:.1f}s, over the "
                f"{FALLBACK_BUDGET_SECONDS:.0f}s budget after font cancellation"
            )
        print(f"OK: actual stalled font cancels, fonts.ready finishes, and PNG captures in {elapsed:.1f}s")
    finally:
        server.shutdown()
        server.server_close()


def require_normal_load(snippet: str, tmp: Path) -> None:
    src = tmp / "normal-fixture.html"
    src.write_text(
        "<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n</head>\n<body>\n"
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 240' "
        "width='400' height='240' role='img' aria-labelledby='normal-title'>\n"
        "<title id='normal-title'>Normal fixture diagram</title>\n"
        "<rect width='400' height='240' fill='#ffffff'/>\n"
        "<text x='200' y='124' text-anchor='middle' font-family='sans-serif' "
        "font-size='24' fill='#111111'>normal fixture</text>\n"
        "</svg>\n</body>\n</html>\n",
        encoding="utf-8",
    )
    out = tmp / "normal-fixture.png"

    stderr = run_cli_without_scale(src, out)

    require_png(out, "normal-load")
    if png_dimensions(out) != (800, 480):
        raise AssertionError(
            "normal-load: omitted CLI scale did not produce the default 2x dimensions"
        )
    if WARNING_ANCHOR in stderr:
        raise AssertionError(f"normal-load: fallback warning fired unexpectedly\n{stderr}")
    print("OK: normal load captures with no fallback warning")


def require_encoded_paths(snippet: str, tmp: Path) -> None:
    # Both characters are legal filename content, not a URL fragment/escape.
    original = tmp / "normal-fixture.html"
    for filename in ("diagram #1.html", "diagram %25.html", "diagram ?draft.html"):
        # Question marks are not valid Windows filename characters.
        if "?" in filename and sys.platform == "win32":
            continue
        source = tmp / filename
        source.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
        output = tmp / (filename + ".png")
        stderr = run_snippet(snippet, source, output)
        require_png(output, filename)
        if stderr:
            raise AssertionError(f"encoded-path capture emitted a warning: {stderr}")
    print("OK: legal filename characters are encoded in the file URL")


def require_other_errors_propagate(snippet: str, tmp: Path) -> None:
    missing = tmp / "does-not-exist.html"
    out = tmp / "never.png"
    try:
        run_export(exporter, missing, out)
    except Exception as exc:
        if type(exc).__name__ == "TimeoutError":
            raise AssertionError(
                "missing-source: goto failure surfaced as a TimeoutError; "
                "the fallback caught the wrong error class"
            )
        print(f"OK: non-timeout failure propagates ({type(exc).__name__})")
        return
    raise AssertionError("missing-source: expected goto on a missing file to raise")



def require_static_motion_frame(snippet: str, tmp: Path) -> None:
    # Exercise the exact shipped controller, avoiding external font requests.
    source = (ROOT / "skills/diagram-design/assets/example-policy-trace-animated.html").read_text(encoding="utf-8")
    source = re.sub(r"<link\b[^>]*>", "", source, flags=re.I)
    src = tmp / "motion-fixture.html"
    src.write_text(source, encoding="utf-8")
    observed = snippet.replace(
        "    svg.screenshot(path=out, omit_background=True)",
        "    assert page.locator('[data-motion-root]').first.get_attribute('data-frame') == 'static', 'motion frame is incomplete'\n"
        "    svg.screenshot(path=out, omit_background=True)",
    )
    first, second = tmp / "motion-first.png", tmp / "motion-second.png"
    run_snippet(observed, src, first)
    run_snippet(observed, src, second)
    require_png(first, "static-motion")
    if first.read_bytes() != second.read_bytes():
        raise AssertionError("motion captures from the same static source are not identical")

    # A broken controller must fail rather than silently capture hidden steps.
    broken = re.sub(r"<script\b[^>]*>.*?</script>", "", source, flags=re.I | re.S)
    broken = broken.replace('data-frame="static" data-static-frame=', 'data-frame="start" data-static-frame=', 1)
    src.write_text(broken, encoding="utf-8")
    never = tmp / "incomplete.png"
    try:
        run_snippet(snippet, src, never)
    except RuntimeError as exc:
        if "static" not in str(exc) or never.exists():
            raise AssertionError(f"incomplete motion frame failed incorrectly: {exc}")
    else:
        raise AssertionError("incomplete motion frame was exported without an error")
    print("OK: motion exports show the complete static frame, repeat identically, and reject incomplete roots")

def main() -> int:
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("SKIP: playwright is not installed; packaged export tests skipped")
        return 0

    exporter = load_exporter()
    with tempfile.TemporaryDirectory(prefix="diagram-export-wait-") as raw_tmp:
        tmp = Path(raw_tmp)
        require_stalled_fallback(snippet, tmp)
        require_stalled_font_fallback(snippet, tmp)
        require_normal_load(snippet, tmp)
        require_encoded_paths(snippet, tmp)
        require_other_errors_propagate(snippet, tmp)
        require_static_motion_frame(snippet, tmp)
    print("All export-wait cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
