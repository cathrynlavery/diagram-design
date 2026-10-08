#!/usr/bin/env python3
"""Deterministic tests for the documented Playwright renderer.

Drives the exact python snippet shipped in
skills/diagram-design/references/export.md against local fixtures:

- unapproved network requests are denied before they reach a local listener;
- the allowlist distinguishes the source and intended fonts from private or
  sibling resources;
- a normal load captures cleanly with no warning;
- non-timeout errors are not swallowed by the fallback.

Requires Playwright (and its Chromium); skips otherwise, matching the export
procedure's own detection step.
"""

from __future__ import annotations

import contextlib
import io
import re
import subprocess
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


RASTERIZE_HEADING = re.compile(r"^### Rasterize\b.*$", re.M)
NEXT_HEADING = re.compile(r"^#{1,3} ", re.M)
PYTHON_FENCE = re.compile(r"^( *)```python[ \t]*\n(.*?)^\1```[ \t]*$", re.M | re.S)


def select_rasterize_block(text: str) -> str:
    """Return the python block under the Rasterize heading.

    export.md carries other python blocks (the SVG color normalization, for
    one), so the snippet is located by its section and by the code it runs,
    never by counting blocks in the whole file.
    """
    heading = RASTERIZE_HEADING.search(text)
    if heading is None:
        raise AssertionError(f"{EXPORT_DOC.name} has no '### Rasterize' section")
    section = text[heading.end():]
    following = NEXT_HEADING.search(section)
    if following is not None:
        section = section[: following.start()]
    blocks = [
        "\n".join(line[len(indent):] for line in body.splitlines()) + "\n"
        for indent, body in PYTHON_FENCE.findall(section)
    ]
    if len(blocks) != 1:
        raise AssertionError(
            "expected exactly one python block in the Rasterize section of "
            f"{EXPORT_DOC.name}, found {len(blocks)}"
        )
    if "sync_playwright" not in blocks[0]:
        raise AssertionError(
            "the Rasterize section's python block does not use sync_playwright"
        )
    return blocks[0]


def require_block_selection() -> None:
    """The selector must ignore python blocks outside the Rasterize section."""
    rasterize = (
        "### Rasterize\n\nRun this:\n\n```python\n"
        "from playwright.sync_api import sync_playwright\nprint('rasterize')\n"
        "```\n\nAfter the block.\n"
    )
    other = "   ```python\n   import re\n   svg = re.sub('a', 'b', 'a')\n   ```\n"
    doc = (
        "# Export\n\n## SVG export procedure\n\n4. Normalize colors:\n\n"
        f"{other}\n## PNG export procedure\n\n{rasterize}\n"
        "### Output naming\n\n```python\nprint('later block')\n```\n"
    )
    selected = select_rasterize_block(doc)
    if "print('rasterize')" not in selected or "re.sub" in selected or "later block" in selected:
        raise AssertionError(f"selector picked the wrong python block:\n{selected}")
    try:
        select_rasterize_block(doc.replace("### Rasterize", "### Capture"))
    except AssertionError:
        pass
    else:
        raise AssertionError("selector accepted a doc with no Rasterize section")
    print("OK: snippet selector finds the Rasterize block among other python blocks")


def load_snippet() -> str:
    snippet = select_rasterize_block(EXPORT_DOC.read_text(encoding="utf-8"))
    for anchor in (
        "except PlaywrightTimeoutError:",
        'page.evaluate("window.stop()")',
        WARNING_ANCHOR,
        "timeout=15000",
        "chromium_sandbox=os.environ",
        "DIAGRAM_EXPORT_CHROMIUM_SANDBOX",
        "service_workers=\"block\"",
        "accept_downloads=False",
        "--host-resolver-rules=MAP * ~NOTFOUND",
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


def start_stall_server(handler: type[BaseHTTPRequestHandler] = _StallHandler) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
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


def run_snippet_with_timeout(snippet: str, src: Path, out: Path) -> str:
    result = subprocess.run(
        [sys.executable, "-c", snippet, str(src), str(out)],
        capture_output=True,
        text=True,
        timeout=FALLBACK_BUDGET_SECONDS,
    )
    if result.returncode:
        raise AssertionError(
            f"renderer exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stderr


def require_png(out: Path, name: str) -> None:
    if not out.exists() or out.stat().st_size == 0:
        raise AssertionError(f"{name}: expected a non-empty screenshot at {out}")


def require_unapproved_network_blocked(snippet: str, tmp: Path) -> None:
    fast = snippet.replace("timeout=15000", FAST_IDLE_TIMEOUT).replace(
        "wait_for_timeout(4000)", FAST_SETTLE
    )

    requested = threading.Event()

    class CanaryHandler(_StallHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            requested.set()
            super().do_GET()

    server = start_stall_server(CanaryHandler)
    try:
        port = server.server_address[1]
        sibling = tmp / "secret.txt"
        sibling.write_text("sibling-file-canary", encoding="utf-8")
        src = tmp / "network-canary.html"
        src.write_text(
            "<!doctype html>\n<html>\n<head>\n<meta charset='utf-8'>\n"
            f"<link rel='stylesheet' href='http://127.0.0.1:{port}/stall.css'>\n"
            "</head>\n<body>\n"
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 240' "
            "width='400' height='240' role='img' aria-labelledby='stall-title'>\n"
            "<title id='stall-title'>Network canary diagram</title>\n"
            "<rect width='400' height='240' fill='#ffffff'/>\n"
            "<text x='200' y='124' text-anchor='middle' font-family='sans-serif' "
            "font-size='24' fill='#111111'>network canary</text>\n"
            "</svg>\n<script>\n"
            f"const target = '127.0.0.1:{port}';\n"
            "try { new WebSocket('ws://' + target + '/ws'); } catch (e) {}\n"
            "try { fetch('http://' + target + '/fetch').catch(() => {}); } catch (e) {}\n"
            "try { new EventSource('http://' + target + '/sse'); } catch (e) {}\n"
            "const img = new Image(); img.src = 'http://' + target + '/image';\n"
            f"fetch({sibling.as_uri()!r}).catch(() => {{}});\n"
            "</script>\n</body>\n</html>\n",
            encoding="utf-8",
        )
        out = tmp / "network-canary.png"

        started = time.monotonic()
        stderr = run_snippet_with_timeout(fast, src, out)
        elapsed = time.monotonic() - started

        require_png(out, "network-canary")
        if requested.wait(timeout=0.25):
            raise AssertionError("network-canary: unapproved loopback request escaped")
        if WARNING_ANCHOR in stderr:
            raise AssertionError(f"network-canary: blocked request stalled the renderer\n{stderr}")
        if elapsed > FALLBACK_BUDGET_SECONDS:
            raise AssertionError(
                f"network-canary: capture took {elapsed:.1f}s, over the "
                f"{FALLBACK_BUDGET_SECONDS:.0f}s budget"
            )
        print(f"OK: unapproved loopback request is blocked in {elapsed:.1f}s")
    finally:
        server.shutdown()
        server.server_close()


def require_request_policy(snippet: str, tmp: Path) -> None:
    prelude = snippet.split("with sync_playwright()", 1)[0]
    old_argv = sys.argv
    sys.argv = ["export", str(tmp / "diagram #1.html"), str(tmp / "out.png")]
    scope: dict[str, object] = {}
    try:
        exec(compile(prelude, str(EXPORT_DOC), "exec"), scope)
    finally:
        sys.argv = old_argv
    request_allowed = scope["request_allowed"]
    source_uri = (tmp / "diagram #1.html").resolve().as_uri()

    def request(url: str, kind: str):
        return type("Request", (), {"url": url, "resource_type": kind})()

    allowed = {
        (source_uri, "document"),
        (source_uri + "?motion=static", "document"),
        ("data:image/svg+xml,%3Csvg/%3E", "image"),
        ("blob:null/id", "image"),
        ("https://fonts.googleapis.com/css2?family=Geist", "stylesheet"),
        ("https://fonts.gstatic.com/s/geist/v1/font.woff2", "font"),
    }
    denied = {
        ((tmp / "secret.txt").resolve().as_uri(), "image"),
        ("http://fonts.googleapis.com/css2?family=Geist", "stylesheet"),
        ("https://fonts.googleapis.com.evil.test/css2", "stylesheet"),
        ("https://fonts.googleapis.com:444/css2", "stylesheet"),
        ("https://fonts.googleapis.com/css2", "script"),
        ("https://fonts.gstatic.com:444/s/geist/v1/font.woff2", "font"),
        ("https://fonts.gstatic.com/s/geist/v1/font.ttf", "font"),
        ("https://127.0.0.1/private", "fetch"),
        ("http://169.254.169.254/latest/meta-data", "fetch"),
        ("ws://127.0.0.1/socket", "websocket"),
    }
    if any(not request_allowed(request(url, kind)) for url, kind in allowed):
        raise AssertionError("request-policy: allowed request was denied")
    if any(request_allowed(request(url, kind)) for url, kind in denied):
        raise AssertionError("request-policy: prohibited request was allowed")
    print("OK: request policy allows only the source, embedded data, and HTTPS Google Fonts")


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
    require_block_selection()
    snippet = load_snippet()
    compile(snippet, str(EXPORT_DOC), "exec")
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("SKIP: playwright is not installed; export snippet tests skipped")
        return 0

    with tempfile.TemporaryDirectory(prefix="diagram-export-wait-") as raw_tmp:
        tmp = Path(raw_tmp)
        require_unapproved_network_blocked(snippet, tmp)
        require_request_policy(snippet, tmp)
        require_normal_load(snippet, tmp)
        require_encoded_paths(snippet, tmp)
        require_other_errors_propagate(snippet, tmp)
        require_static_motion_frame(snippet, tmp)
    print("All export-wait cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
