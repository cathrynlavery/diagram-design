#!/usr/bin/env python3
"""One-time online setup so every later run of the local agent is offline.

    python local-agent/bootstrap.py              # vendor the template fonts
    python local-agent/bootstrap.py --cjk        # also the Noto KR/TC slices
    python local-agent/bootstrap.py --playwright # also Chromium for PNG export
    python local-agent/bootstrap.py --check      # verify offline readiness

Downloads go to local-agent/fonts/ (git-ignored) and, with --playwright, the
Playwright package plus its Chromium build. Nothing here runs at diagram
time; `agent.py` and `export.py` only read what this script stored.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import fonts  # noqa: E402

# A browser UA makes Google return woff2 slices with unicode-range instead of
# a single legacy TTF per family.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def fetch(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def vendor_fonts(families: tuple[tuple[str, str], ...], font_dir: Path) -> list[fonts.Face]:
    font_dir.mkdir(parents=True, exist_ok=True)
    css = fetch(fonts.css2_url(families)).decode("utf-8")
    parsed = fonts.parse_css2(css)
    if not parsed:
        raise RuntimeError("Google Fonts returned no @font-face blocks; check the family list")
    stored: list[fonts.Face] = []
    seen: set[str] = set()
    for index, (face, url) in enumerate(parsed, 1):
        if face.file in seen:
            continue
        seen.add(face.file)
        target = font_dir / face.file
        if not target.is_file():
            target.write_bytes(fetch(url))
        stored.append(face)
        print(f"  [{index:>4}/{len(parsed)}] {face.family} {face.weight} {face.style} {face.subset}")
    return stored


def write_manifest(faces: list[fonts.Face], manifest: Path) -> None:
    existing = {face.file: face for face in fonts.load_manifest(manifest)}
    for face in faces:
        existing[face.file] = face
    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "https://fonts.googleapis.com/css2",
        "faces": [face.__dict__ for face in existing.values()],
    }
    manifest.write_text(json.dumps(payload, indent=1), encoding="utf-8")


def install_playwright() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


def check(font_dir: Path, manifest: Path) -> int:
    problems: list[str] = []
    faces = fonts.load_manifest(manifest)
    if not faces:
        problems.append(f"no font manifest at {manifest}; run bootstrap.py once while online")
    else:
        missing = [face.file for face in faces if not (font_dir / face.file).is_file()]
        if missing:
            problems.append(f"{len(missing)} font files listed in the manifest are missing")
        families = fonts.available_families(faces)
        for name, _ in fonts.CORE_FAMILIES:
            if name not in families:
                problems.append(f"core family not vendored: {name}")
        print(f"fonts: {len(faces)} faces, families: {', '.join(families)}")
    try:
        import playwright  # noqa: F401
    except ImportError:
        print("playwright: not installed (PNG export unavailable; --playwright to add)")
    else:
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                browser.close()
            print("playwright: chromium launches")
        except Exception as exc:  # noqa: BLE001 - report whatever Playwright raised
            problems.append(f"playwright installed but chromium cannot launch: {exc}")
    for problem in problems:
        print(f"FAIL {problem}")
    if not problems:
        print("OK offline-ready")
    return 1 if problems else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cjk", action="store_true", help="also vendor Noto Sans/Serif KR and TC")
    parser.add_argument("--playwright", action="store_true", help="pip install playwright and its Chromium")
    parser.add_argument("--check", action="store_true", help="verify everything needed offline is present")
    parser.add_argument("--font-dir", type=Path, default=fonts.FONT_DIR)
    args = parser.parse_args()
    manifest = args.font_dir / "fonts.json"

    if args.check:
        return check(args.font_dir, manifest)

    groups = [fonts.CORE_FAMILIES, fonts.TERMINAL_FAMILIES]
    if args.cjk:
        groups.append(fonts.CJK_FAMILIES)
    stored: list[fonts.Face] = []
    try:
        for families in groups:
            print("fetching " + ", ".join(name for name, _ in families))
            stored.extend(vendor_fonts(families, args.font_dir))
    except urllib.error.URLError as exc:
        print(f"FAIL cannot reach Google Fonts: {exc.reason}")
        return 1
    stored = list({face.file: face for face in stored}.values())
    write_manifest(stored, manifest)
    print(f"stored {len(stored)} faces under {args.font_dir}")

    if args.playwright:
        install_playwright()
    return check(args.font_dir, manifest)


if __name__ == "__main__":
    sys.exit(main())
