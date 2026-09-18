#!/usr/bin/env python3
"""Deterministic tests for the export snippet's stalled-load fallback.

Drives the exact python snippet shipped in
skills/diagram-design/references/export.md against local fixtures:

- a stalled stylesheet request is cancelled with window.stop(), the snippet
  warns about fallback typography, and capture completes quickly;
- a normal load captures cleanly with no warning;
- non-timeout errors are not swallowed by the fallback.

Requires Playwright (and its Chromium); skips otherwise, matching the export
procedure's own detection step.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_DOC = ROOT / "skills/diagram-design/references/export.md"

# Fast-but-deterministic substitutes for the snippet's production waits.
FAST_IDLE_TIMEOUT = "timeout=1500"
FAST_SETTLE = "wait_for_timeout(150)"
STALL_HOLD_SECONDS = 30  # must outlast the test's networkidle timeout
WARNING_ANCHOR = "fallback typography"
# The full fallback (fast timeout + settle + capture) must stay far below the
# production path's 15s networkidle + 4s settle budget.
FALLBACK_BUDGET_SECONDS = 15.0


def load_snippet() -> str:
    text = EXPORT_DOC.read_text(encoding="utf-8")
    blocks = re.findall(r"```python\n(.*?)```", text, re.S)
    if len(blocks) != 1:
        raise AssertionError(
            f"expected exactly one python block in {EXPORT_DOC.name}, found {len(blocks)}"
        )
    snippet = blocks[0]
    for anchor in (
        "except PlaywrightTimeoutError:",
        'page.evaluate("window.stop()")',
        WARNING_ANCHOR,
        "timeout=15000",
    ):
        if anchor not in snippet:
            raise AssertionError(
                f"export snippet is missing required anchor {anchor!r}"
            )
    if "except Exception" in snippet or re.search(r"except\s*:", snippet):
        raise AssertionError(
            "export snippet must not swallow non-timeout errors with a "
            "broad or bare except"
        )
    return snippet


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


def run_snippet(snippet: str, src: Path, out: Path) -> str:
    """Exec the doc snippet with the given argv; return captured stderr."""
    stderr = io.StringIO()
    old_argv, old_stderr = sys.argv, sys.stderr
    sys.argv = ["export", str(src), str(out)]
    try:
        with contextlib.redirect_stderr(stderr):
            exec(compile(snippet, str(EXPORT_DOC), "exec"), {"__name__": "export_snippet"})
    finally:
        sys.argv, sys.stderr = old_argv, old_stderr
    return stderr.getvalue()


def require_png(out: Path, name: str) -> None:
    if not out.exists() or out.stat().st_size == 0:
        raise AssertionError(f"{name}: expected a non-empty screenshot at {out}")


def require_stalled_fallback(snippet: str, tmp: Path) -> None:
    fast = snippet.replace("timeout=15000", FAST_IDLE_TIMEOUT).replace(
        "wait_for_timeout(4000)", FAST_SETTLE
    )
    if fast == snippet:
        raise AssertionError("could not shorten the snippet's production waits for the test")

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
        stderr = run_snippet(fast, src, out)
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

    stderr = run_snippet(snippet, src, out)

    require_png(out, "normal-load")
    if WARNING_ANCHOR in stderr:
        raise AssertionError(f"normal-load: fallback warning fired unexpectedly\n{stderr}")
    print("OK: normal load captures with no fallback warning")


def require_other_errors_propagate(snippet: str, tmp: Path) -> None:
    missing = tmp / "does-not-exist.html"
    out = tmp / "never.png"
    try:
        run_snippet(snippet, missing, out)
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
        print("SKIP: playwright is not installed; export snippet tests skipped")
        return 0

    snippet = load_snippet()
    with tempfile.TemporaryDirectory(prefix="diagram-export-wait-") as raw_tmp:
        tmp = Path(raw_tmp)
        require_stalled_fallback(snippet, tmp)
        require_normal_load(snippet, tmp)
        require_other_errors_propagate(snippet, tmp)
    print("All export-wait cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
