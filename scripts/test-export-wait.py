#!/usr/bin/env python3
"""Deterministic tests for the packaged PNG exporter's stalled-load fallback.

Drives ``skills/diagram-design/scripts/export_png.py`` against local fixtures:

- a stalled stylesheet request is cancelled with window.stop(), the renderer
  warns about fallback typography, and capture completes quickly;
- a normal load captures cleanly with no warning;
- non-timeout errors are not swallowed by the fallback.

Requires Playwright (and its Chromium); skips otherwise, matching the export
procedure's own detection step.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
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


def start_stall_server() -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _StallHandler)
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


def require_normal_load(exporter, tmp: Path) -> None:
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

    stderr = run_export(exporter, src, out)

    require_png(out, "normal-load")
    if WARNING_ANCHOR in stderr:
        raise AssertionError(f"normal-load: fallback warning fired unexpectedly\n{stderr}")
    print("OK: normal load captures with no fallback warning")


def require_other_errors_propagate(exporter, tmp: Path) -> None:
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


def main() -> int:
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("SKIP: playwright is not installed; packaged export tests skipped")
        return 0

    exporter = load_exporter()
    with tempfile.TemporaryDirectory(prefix="diagram-export-wait-") as raw_tmp:
        tmp = Path(raw_tmp)
        require_stalled_fallback(exporter, tmp)
        require_normal_load(exporter, tmp)
        require_other_errors_propagate(exporter, tmp)
    print("All export-wait cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
