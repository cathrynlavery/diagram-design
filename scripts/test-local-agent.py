#!/usr/bin/env python3
"""Tests for the offline LM Studio runner in local-agent/.

Covers the pieces that need no model: font vendoring and embedding, the SVG
export transform, model-reply extraction, plan parsing, prompt assembly, and
the full plan → draw → verify → repair → export loop against an in-process
fake of LM Studio's /v1/chat/completions endpoint. Fonts come from a tiny
synthetic manifest so the test never touches local-agent/fonts/.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = ROOT / "local-agent"
ASSETS = ROOT / "skills" / "diagram-design" / "assets"
sys.path.insert(0, str(AGENT_DIR))

import agent  # noqa: E402
import export  # noqa: E402
import fonts  # noqa: E402
import prompt  # noqa: E402
import verify  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"OK: {label}")
    else:
        FAILURES.append(f"{label}: {detail}")
        print(f"FAIL: {label} {detail}")


# -- synthetic fonts -------------------------------------------------------

def synthetic_fonts(directory: Path) -> list[fonts.Face]:
    faces = [
        fonts.Face("Geist", "normal", "400", "latin", "U+0000-00FF", "geist-400-normal-latin.woff2"),
        fonts.Face("Geist", "normal", "400", "cyrillic", "U+0400-045F", "geist-400-normal-cyrillic.woff2"),
        fonts.Face("Geist Mono", "normal", "400", "latin", "U+0000-00FF", "geist-mono-400-normal-latin.woff2"),
        fonts.Face("Instrument Serif", "italic", "400", "latin", "U+0000-00FF", "instrument-serif-400-italic-latin.woff2"),
        fonts.Face("Noto Serif", "normal", "400", "latin", "U+0000-00FF", "noto-serif-400-normal-latin.woff2"),
    ]
    for face in faces:
        # "//" inside the payload is deliberate: it must not read as a remote URL.
        (directory / face.file).write_bytes(b"woff2//" + bytes(3))
    (directory / "fonts.json").write_text(json.dumps({"faces": [f.__dict__ for f in faces]}), encoding="utf-8")
    return faces


def test_css2_parsing() -> None:
    css = """/* latin-ext */
@font-face {
  font-family: 'Geist';
  font-style: normal;
  font-weight: 500;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/geist/v5/abc.woff2) format('woff2');
  unicode-range: U+0100-02BA, U+02BD-02C5;
}
/* [3] */
@font-face {
  font-family: 'Noto Sans KR';
  font-style: normal;
  font-weight: 400;
  src: url(https://fonts.gstatic.com/s/notosanskr/v1/x.woff2) format('woff2');
  unicode-range: U+D723-D728;
}
"""
    parsed = fonts.parse_css2(css)
    check("css2 parses every @font-face", len(parsed) == 2, str(parsed))
    face, url = parsed[0]
    check("css2 face fields", (face.family, face.weight, face.subset) == ("Geist", "500", "latin-ext"), repr(face))
    check("css2 face url", url.endswith("abc.woff2"), url)
    check("css2 numbered subset slug", parsed[1][0].file == "noto-sans-kr-400-normal-3.woff2", parsed[1][0].file)
    check("css2 url builder", "family=Geist+Mono:wght@400;500;600" in fonts.css2_url(fonts.CORE_FAMILIES))


def test_font_selection_and_inlining(font_dir: Path, faces: list[fonts.Face]) -> None:
    html = (ASSETS / "example-flowchart.html").read_text(encoding="utf-8")
    chosen = fonts.select_faces(html, faces)
    names = {(f.family, f.subset) for f in chosen}
    check("latin slices of used families selected", ("Geist", "latin") in names and ("Geist Mono", "latin") in names, str(names))
    check("unused script slice skipped", ("Geist", "cyrillic") not in names, str(names))
    check("unused family skipped", not any(f.family == "Noto Serif" for f in chosen) or "Noto Serif" in html)
    cyrillic = html.replace("New workflow", "Новый процесс", 1)
    check("cyrillic text pulls the cyrillic slice", ("Geist", "cyrillic") in {(f.family, f.subset) for f in fonts.select_faces(cyrillic, faces)})

    inlined = fonts.inline_html_fonts(html, faces, font_dir)
    check("google link removed", "fonts.googleapis.com" not in inlined)
    check("font-face embedded", "@font-face{font-family:'Geist'" in inlined and "data:font/woff2;base64," in inlined)
    check("idempotent on inlined file", fonts.inline_html_fonts(inlined, faces, font_dir) == inlined)
    check("is_inlined detects", fonts.is_inlined(inlined) and not fonts.is_inlined(html))

    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "inlined.html"
        path.write_text(inlined, encoding="utf-8")
        findings = verify.verify_file(path, "0 0 1000 600")
        check("inlined file passes the gates", not findings, str(findings))


def test_svg_export(font_dir: Path, faces: list[fonts.Face]) -> None:
    html = (ASSETS / "example-architecture.html").read_text(encoding="utf-8")
    svg = export.standalone_svg(html, faces, font_dir)
    check("xml prolog", svg.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
    check("title stays first child", re.search(r"<svg[^>]*>\s*<title", svg) is not None)
    check("fonts embedded in defs", "<defs><style>" in svg and "@font-face" in svg)
    check("rgba normalised", "rgba(" not in svg)
    check("transparent normalised", 'fill="transparent"' not in svg)
    import xml.etree.ElementTree as ET

    try:
        ET.fromstring(svg.encode("utf-8"))
        check("svg is well-formed xml", True)
    except ET.ParseError as exc:
        check("svg is well-formed xml", False, str(exc))
    sample = 'fill="rgba(45, 49, 66, .03)" stroke="transparent"'
    check("normalize_colors spacing and leading dot", export.normalize_colors(sample) == 'fill="#2d3142" fill-opacity=".03" stroke="none"', export.normalize_colors(sample))
    try:
        export.extract_svg("<p>no diagram</p>")
        check("no svg rejected", False)
    except export.ExportError:
        check("no svg rejected", True)
    try:
        export.extract_svg(html, "index.html")
        check("gallery rejected", False)
    except export.ExportError:
        check("gallery rejected", True)


def test_reply_extraction() -> None:
    doc = "<!DOCTYPE html>\n<html><body><svg viewBox=\"0 0 1 1\"></svg></body></html>"
    check("fenced html extracted", verify.extract_html(f"Sure!\n```html\n{doc}\n```\nDone.") == doc + "\n")
    check("bare html extracted", verify.extract_html(f"  {doc}  ") == doc + "\n")
    check("longest fenced block wins", verify.extract_html(f"```html\n<html></html>\n```\n```html\n{doc}\n```") == doc + "\n")
    check("no html returns None", verify.extract_html("I cannot do that.") is None)
    check("plan json parsed", agent.parse_plan('<think>x</think>Here: {"type": "flowchart", "nodes": ["a"]}')["type"] == "flowchart")
    check("plan without json raises", _raises(lambda: agent.parse_plan("nope")))


def test_layout_findings() -> None:
    clean = 0
    for path in sorted(ASSETS.glob("example-*.html")):
        match = re.match(r"example-(.+?)(?:-(?:dark|full|terminal|vertical|consultant|oauth))*\.html$", path.name)
        slug = match.group(1) if match and match.group(1) in prompt.available_types() else None
        if verify.layout_findings(path.read_text(encoding="utf-8"), slug):
            check(f"no layout false positive in {path.name}", False, str(verify.layout_findings(path.read_text(encoding="utf-8"), slug)[:1]))
        else:
            clean += 1
    check("shipped examples produce no layout findings", clean > 150, str(clean))

    svg = (
        '<svg viewBox="0 0 400 300"><rect x="40" y="40" width="120" height="64"/>'
        '<rect x="300" y="40" width="120" height="64"/>'
        '<text x="360" y="72" font-size="16" text-anchor="middle">Feature Store Service</text>'
        '<line x1="160" y1="72" x2="200" y2="72" marker-end="url(#arrow)"/>'
        '<rect x="204" y="66" width="52" height="12"/>'
        '<line x1="40" y1="260" x2="360" y2="260" stroke="#ccc"/>'  # legend hairline
        '<line x1="10" y1="290" x2="40" y2="290" marker-end="url(#arrow)"/></svg>'
    )
    findings = verify.layout_findings(svg, "architecture")
    check("overflowing node reported", any("beyond the viewBox" in f for f in findings), str(findings))
    check("overflowing label reported", any("Feature Store Service" in f for f in findings), str(findings))
    check("dangling arrow reported despite label mask at tip", any("ends at (200,72)" in f for f in findings), str(findings))
    check("legend sample arrow ignored", not any("(40,290)" in f for f in findings), str(findings))
    check("arrow check skipped for chart types", not any("ends at" in f for f in verify.layout_findings(svg, "sequence")))
    origin = svg.replace('viewBox="0 0 400 300"', 'viewBox="-40 0 480 300"').replace('x="300" y="40" width="120"', 'x="300" y="40" width="100"')
    check("viewBox origin honoured", not any("beyond the viewBox" in f for f in verify.layout_findings(origin, "architecture")))


def _raises(fn) -> bool:
    try:
        fn()
    except Exception:  # noqa: BLE001
        return True
    return False


def test_prompt_assembly() -> None:
    types = prompt.available_types()
    check("41 visual types discovered", len(types) >= 41 and "flowchart" in types, str(len(types)))
    context = prompt.DrawContext("flowchart", "dark", "slide-16x9", profile="full")
    system = context.system_prompt()
    check("system prompt names the type and viewBox", "Visual type: flowchart" in system and 'viewBox="0 0 1280 720"' in system)
    check("full profile carries the style guide", any("style-guide" in name for name, _ in context.parts))
    check("dark template and example chosen", any("template-dark.html" in n for n, _ in context.parts) and any("example-flowchart-dark.html" in n for n, _ in context.parts))
    lean = prompt.DrawContext("flowchart", "light", profile="lean")
    lean.system_prompt()
    check("lean profile drops the style guide", not any("style-guide" in name for name, _ in lean.parts))
    check("lean is smaller", prompt.estimate_tokens(lean.system_prompt()) < prompt.estimate_tokens(system))
    check("unknown type rejected", _raises(lambda: prompt.DrawContext("nonsense").system_prompt()))
    guide = prompt.visual_type_guide()
    check("type guide extracted", guide.startswith("### Visual-type guide") and "Confirm before drawing" not in guide)
    check("every size preset has a 4px-grid viewBox", all(int(v.split()[2]) % 4 == 0 for v, _ in prompt.SIZE_PRESETS.values()))


# -- fake LM Studio --------------------------------------------------------

class FakeLMStudio(BaseHTTPRequestHandler):
    """Answers the planning call with JSON, then a broken diagram, then a fixed one."""

    replies: list[str] = []
    requests: list[dict] = []

    def log_message(self, *_args) -> None:  # silence
        pass

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps({"data": [{"id": "fake/model", "loaded_context_length": 32768}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
        type(self).requests.append(payload)
        reply = type(self).replies.pop(0)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for start in range(0, len(reply), 500):
            chunk = {"choices": [{"delta": {"content": reply[start : start + 500]}}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")


def test_agent_loop(font_dir: Path, faces: list[fonts.Face]) -> None:
    good = (ASSETS / "example-flowchart.html").read_text(encoding="utf-8")
    good = good.replace('viewBox="0 0 1000 600"', 'viewBox="0 0 960 600"', 1)  # doc-inline preset
    broken = good.replace("flowchart-title", "[diagram-slug]-title", 1)
    FakeLMStudio.replies = [
        '<think>choosing</think>{"type": "flowchart", "variant": "light", "size": "doc-inline", '
        '"title": "Order flow", "slug": "order-flow", "eyebrow": "FLOWCHART", "desc": "d", "nodes": ["a", "b"], "cuts": "none"}',
        f"Here you go:\n```html\n{broken}\n```",
        f"```html\n{good}\n```",
    ]
    FakeLMStudio.requests = []
    server = HTTPServer(("127.0.0.1", 0), FakeLMStudio)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = (fonts.MANIFEST, fonts.FONT_DIR)
    fonts.MANIFEST, fonts.FONT_DIR = font_dir / "fonts.json", font_dir
    try:
        with tempfile.TemporaryDirectory() as scratch:
            out = Path(scratch) / "order-flow.html"
            args = argparse.Namespace(
                request="Flowchart of an order",
                prompt_file=None, type=None, variant=None, size=None, title=None,
                out=out, model="fake/model", base_url=f"http://127.0.0.1:{server.server_port}/v1",
                profile="auto", style_guide=prompt.REFERENCES / "style-guide.md",
                max_repairs=2, max_tokens=100, temperature=0.1, timeout=30, scale=1.0,
                no_svg=False, no_png=True,
            )
            status = agent.run(args)
            check("agent loop exits 0", status == 0, str(status))
            check("three model calls: plan, draw, one repair", len(FakeLMStudio.requests) == 3, str(len(FakeLMStudio.requests)))
            repair = FakeLMStudio.requests[2]["messages"][-1]["content"]
            check("repair prompt carries the finding", "[diagram-slug]" in repair, repair[:200])
            check("draw used the lean profile under 48k context", "style-guide" not in FakeLMStudio.requests[1]["messages"][0]["content"][:3000])
            written = out.read_text(encoding="utf-8")
            check("output has fonts embedded", fonts.is_inlined(written))
            check("output passes the gates", not verify.verify_file(out, "0 0 960 600"))
            check("svg exported next to html", out.with_suffix(".svg").is_file())
    finally:
        fonts.MANIFEST, fonts.FONT_DIR = original
        server.shutdown()


def main() -> int:
    test_css2_parsing()
    with tempfile.TemporaryDirectory() as scratch:
        font_dir = Path(scratch)
        faces = synthetic_fonts(font_dir)
        test_font_selection_and_inlining(font_dir, faces)
        test_svg_export(font_dir, faces)
        test_reply_extraction()
        test_prompt_assembly()
        test_layout_findings()
        test_agent_loop(font_dir, faces)
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s)")
        for failure in FAILURES:
            print("  - " + failure)
        return 1
    print("\nAll local-agent tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
