#!/usr/bin/env python3
"""Regression tests for the canonical screenshot freshness gate.

A checkout that rewrites LF blobs to CRLF (`core.autocrlf=true`) must not make
committed canonical examples look changed, and canonicalizing text sources must
not loosen the gate: a real source edit, or a recorded PNG digest that was
folded rather than taken from the bytes, still has to fail.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
VERIFIER = SCRIPTS / "verify-screenshot-freshness.py"
sys.path.insert(0, str(SCRIPTS))

import screenshot_catalog

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IEND = bytes.fromhex("0000000049454e44ae426082")
WIDTH = 1440
HEIGHT = 1000
SCREENSHOT = (
    PNG_SIGNATURE
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">II", WIDTH, HEIGHT)
    + IEND
)
SCREENSHOT_CRLF = SCREENSHOT + b"\r\n"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_screenshot_freshness", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def source_text(slug: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        f"<body><h1>{slug}</h1></body>\n"
        "</html>\n"
    )


class Checkout:
    """A throwaway copy of the canonical catalog layout for the gate to read."""

    def __init__(self, base: Path, slugs: list[str]) -> None:
        self.base = base
        self.slugs = list(slugs)
        self.assets = base / "skills/diagram-design/assets"
        self.shots = base / "docs/screenshots"
        self.assets.mkdir(parents=True)
        self.shots.mkdir(parents=True)
        self.manifest = self.shots / "manifest.json"

    def source(self, slug: str) -> Path:
        return self.assets / f"example-{slug}.html"

    def screenshot(self, slug: str) -> Path:
        return self.shots / f"{slug}.png"

    def write_sources(self, newline: str) -> None:
        for slug in self.slugs:
            self.source(slug).write_bytes(source_text(slug).replace("\n", newline).encode("utf-8"))

    def write_screenshots(self, blob: bytes) -> None:
        for slug in self.slugs:
            self.screenshot(slug).write_bytes(blob)

    def write_manifest(self, source_digest, screenshot_digest) -> None:
        entries = [
            {
                "slug": slug,
                "source": self.source(slug).relative_to(self.base).as_posix(),
                "screenshot": self.screenshot(slug).relative_to(self.base).as_posix(),
                "source_sha256": source_digest(slug),
                "screenshot_sha256": screenshot_digest(slug),
                "width": WIDTH,
                "height": HEIGHT,
            }
            for slug in self.slugs
        ]
        payload = {
            "schema_version": 1,
            "renderer": {
                "engine": "playwright-chromium",
                "scale": 2.0,
                "viewport": [WIDTH, HEIGHT],
                "capture": "first-svg",
                "font_gate": "document.fonts.ready",
            },
            "entries": entries,
        }
        self.manifest.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))


def run_gate(checkout: Checkout) -> tuple[int, str]:
    """Point the gate at a synthetic checkout and capture its verdict."""

    verifier = load_verifier()
    verifier.canonical_slugs = lambda: list(checkout.slugs)
    verifier.source_path = checkout.source
    verifier.screenshot_path = checkout.screenshot
    verifier.MANIFEST = checkout.manifest
    verifier.ROOT = checkout.base
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        code = verifier.main()
    return code, stream.getvalue()


def main() -> int:
    slugs = screenshot_catalog.canonical_slugs()
    failures: list[str] = []
    passed = 0

    def record(label: str, ok: bool, detail: str) -> None:
        nonlocal passed
        if ok:
            passed += 1
        else:
            failures.append(f"{label}: {detail}")

    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def source_bytes(slug: str, newline: str = "\n") -> bytes:
        return source_text(slug).replace("\n", newline).encode("utf-8")

    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch)

        # Unchanged sources in a CRLF checkout: the manifest holds the digest of
        # the committed LF text, so the gate must pass.
        checkout = Checkout(root / "crlf", slugs)
        checkout.write_sources("\r\n")
        checkout.write_screenshots(SCREENSHOT)
        checkout.write_manifest(
            lambda slug: digest(source_bytes(slug)),
            lambda slug: digest(SCREENSHOT),
        )
        code, out = run_gate(checkout)
        record("a CRLF checkout of unchanged sources passes", code == 0, out.strip())

        # Canonicalizing must not hide a real edit.
        checkout = Checkout(root / "drift", slugs)
        checkout.write_sources("\r\n")
        checkout.write_screenshots(SCREENSHOT)
        checkout.write_manifest(
            lambda slug: digest(source_bytes(slug) + b"<!-- edited -->\n"),
            lambda slug: digest(SCREENSHOT),
        )
        code, out = run_gate(checkout)
        record(
            "an edited source still fails on a CRLF checkout",
            code == 1 and "source changed" in out,
            out.strip(),
        )

        # PNG digests stay raw, so a recorded raw digest is accepted even when
        # the PNG bytes themselves contain a CRLF pair.
        checkout = Checkout(root / "png-raw", slugs)
        checkout.write_sources("\n")
        checkout.write_screenshots(SCREENSHOT_CRLF)
        checkout.write_manifest(
            lambda slug: digest(source_bytes(slug)),
            lambda slug: digest(SCREENSHOT_CRLF),
        )
        code, out = run_gate(checkout)
        record("a PNG digest recorded from raw bytes passes", code == 0, out.strip())

        # A digest folded the way a text source is folded must be rejected.
        checkout = Checkout(root / "png-folded", slugs)
        checkout.write_sources("\n")
        checkout.write_screenshots(SCREENSHOT_CRLF)
        checkout.write_manifest(
            lambda slug: digest(source_bytes(slug)),
            lambda slug: screenshot_catalog.sha256_text(checkout.screenshot(slug)),
        )
        code, out = run_gate(checkout)
        record(
            "a folded PNG digest is rejected",
            code == 1 and "screenshot changed without a matching manifest refresh" in out,
            out.strip(),
        )

        # sha256_text folds CRLF and a lone CR, and leaves LF bytes untouched.
        probe = root / "probe.txt"
        probe.write_bytes(b"a\r\nb\rc\nd\n")
        folded = screenshot_catalog.sha256_text(probe)
        probe.write_bytes(b"a\nb\nc\nd\n")
        record(
            "sha256_text folds CRLF and lone CR",
            folded == screenshot_catalog.sha256_text(probe),
            folded,
        )
        record(
            "sha256_text agrees with the raw digest on LF content",
            folded == screenshot_catalog.sha256(probe),
            folded,
        )

    # The committed manifest already holds canonical digests, so normalizing
    # text sources changes no recorded value and needs no regeneration.
    manifest = json.loads(screenshot_catalog.MANIFEST.read_text(encoding="utf-8"))
    canonical: list[str] = []
    raw: list[str] = []
    for entry in manifest["entries"]:
        slug = entry["slug"]
        source = screenshot_catalog.source_path(slug)
        screenshot = screenshot_catalog.screenshot_path(slug)
        if entry["source_sha256"] != screenshot_catalog.sha256_text(source):
            canonical.append(slug)
        if entry["source_sha256"] != screenshot_catalog.sha256(source):
            raw.append(f"{slug} source")
        if entry["screenshot_sha256"] != screenshot_catalog.sha256(screenshot):
            raw.append(f"{slug} png")
    record(
        "committed manifest digests survive canonicalization",
        not canonical and not raw,
        f"canonical_mismatch={canonical} raw_mismatch={raw}",
    )

    if failures:
        print("FAIL screenshot freshness regression tests")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK screenshot freshness regression tests: {passed} checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
