"""Generate the downscaled README preview images.

README.md renders the screenshots in `docs/screenshots/`. The originals are
2400-2800px wide because they are the artifacts people download and inspect,
but the README grid paints them at 252 CSS px and the three inline figures at
838 CSS px. Serving the originals means several MB and hundreds of MB of
decoded bitmap for one page of thumbnails, and a burst of 40 oversized
requests loses races: individual previews stall in flight and paint blank with
no broken-image icon.

This script writes right-sized copies to `docs/screenshots/thumbs/`, which is
what README.md points at. The originals stay in place and every preview links
to its own, so full detail is one click away.

  - grid previews   ->  600px wide, WebP q82  (252 CSS px at 2x)
  - inline figures  -> 1400px wide, WebP q90  (838 CSS px, listed in WIDE below)

WebP rather than PNG: at these sizes it is a third of the palette-PNG bytes,
and the higher quality on the wide figures keeps the dot grid and the small
caps legible.

Freshness is tracked in `docs/screenshots/thumbs/manifest.json`, which records
the SHA-256 of both the source PNG and the generated thumb, alongside the
render settings used -- the same two-digest convention as
`verify-screenshot-freshness.py`. `--check` compares digests rather than
re-encoding, so it is independent of the local libwebp, and it decodes every
thumb it accepts so a corrupt file cannot pass on a matching digest alone.

Run:    python scripts/build-readme-thumbs.py
        python scripts/build-readme-thumbs.py --check   # verify, write nothing
Reqs:   Pillow

The generated files are committed; users of the skill never need to run this.
Re-run it whenever a screenshot in `docs/screenshots/` changes.
"""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO / "docs" / "screenshots"
THUMB_DIR = SOURCE_DIR / "thumbs"
MANIFEST = THUMB_DIR / "manifest.json"
README = REPO / "README.md"

GRID_WIDTH, GRID_QUALITY = 600, 82
WIDE_WIDTH, WIDE_QUALITY = 1400, 90

# Screenshots README renders as full-width figures rather than grid cells.
WIDE = {"architecture.png", "loop.png", "import-drawio.png"}


def target(name: str) -> tuple[int, int]:
    """Return the (width, WebP quality) for a screenshot, by how README uses it."""
    if name in WIDE:
        return WIDE_WIDTH, WIDE_QUALITY
    return GRID_WIDTH, GRID_QUALITY


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decoded_size(payload: bytes) -> tuple[int, int]:
    """Return the pixel dimensions of `payload`, raising if it will not decode."""
    from PIL import Image

    with Image.open(io.BytesIO(payload)) as handle:
        handle.load()
        return handle.size


def render(source: pathlib.Path, width: int, quality: int) -> bytes:
    """Return the WebP bytes of `source` downscaled to `width`."""
    from PIL import Image

    with Image.open(source) as handle:
        image = handle.convert("RGB")
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.LANCZOS)

        buffer = io.BytesIO()
        image.save(buffer, "WEBP", quality=quality, method=6)
        return buffer.getvalue()


def spec_for(source: pathlib.Path) -> dict[str, object]:
    """Return the part of a manifest record fixed by `source` and its settings."""
    width, quality = target(source.name)
    source_width, source_height = decoded_size(source.read_bytes())
    return {
        "thumb": f"{source.stem}.webp",
        "source": source.relative_to(REPO).as_posix(),
        "source_sha256": sha256(source),
        "width": width,
        "height": round(source_height * width / source_width),
        "quality": quality,
    }


def load_manifest() -> dict[str, dict[str, object]]:
    """Return the committed manifest keyed by thumb name, empty if unreadable."""
    try:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if payload.get("schema_version") != 1:
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {}
    return {
        entry["thumb"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("thumb"), str)
    }


def stale_reason(
    record: dict[str, object] | None,
    spec: dict[str, object],
    destination: pathlib.Path,
) -> str:
    """Explain why a committed thumb could not be reused, for the --check report."""
    if not destination.is_file():
        return "missing"
    if record is None:
        return "not in the manifest"
    if any(record.get(key) != value for key, value in spec.items()):
        return "source or render settings changed"
    return "thumb does not match its recorded digest"


def readme_wiring_errors(sources: list[pathlib.Path]) -> list[str]:
    """Return screenshots whose preview does not link to the full PNG."""
    try:
        readme = README.read_text(encoding="utf-8")
    except OSError:
        return [f"cannot read {README}"]

    errors: list[str] = []
    for source in sources:
        original = source.relative_to(REPO).as_posix()
        thumb = f"{THUMB_DIR.relative_to(REPO).as_posix()}/{source.stem}.webp"
        markdown = re.compile(
            rf"\[!\[[^\]]*\]\({re.escape(thumb)}\)\]\({re.escape(original)}\)"
        )
        html = re.compile(
            rf'<a href="{re.escape(original)}"><img src="{re.escape(thumb)}"(?=[\s>])'
        )
        if not markdown.search(readme) and not html.search(readme):
            errors.append(f"{source.name} (README preview must link to the full PNG)")
    return errors


def readme_sources() -> tuple[list[pathlib.Path], list[str]]:
    """Return the full-size PNGs the README actually renders or links."""
    try:
        readme = README.read_text(encoding="utf-8")
    except OSError:
        return [], [f"cannot read {README}"]
    relative_paths = sorted(
        set(re.findall(r"docs/screenshots/(?!thumbs/)[A-Za-z0-9_.-]+\.png", readme))
    )
    sources = [REPO / relative for relative in relative_paths]
    errors = [f"{source.relative_to(REPO)} (missing source PNG)" for source in sources if not source.is_file()]
    thumb_stems = set(
        re.findall(r"docs/screenshots/thumbs/([A-Za-z0-9_.-]+)\.webp", readme)
    )
    source_stems = {source.stem for source in sources}
    for stem in sorted(thumb_stems - source_stems):
        errors.append(f"{stem}.webp (README thumbnail has no full-size PNG link)")
    return sources, errors


def main(argv: list[str]) -> int:
    check_only = "--check" in argv

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("build-readme-thumbs: Pillow is required (pip install Pillow)")
        return 1

    sources, source_errors = readme_sources()
    if source_errors:
        print("build-readme-thumbs: README sources are stale:")
        for error in source_errors:
            print(f"  {error}")
        return 1
    if not sources:
        print(f"build-readme-thumbs: README names no screenshots from {SOURCE_DIR}")
        return 1

    wiring_errors = readme_wiring_errors(sources)
    if wiring_errors:
        print("build-readme-thumbs: README wiring is stale:")
        for error in wiring_errors:
            print(f"  {error}")
        return 1

    if not check_only:
        THUMB_DIR.mkdir(parents=True, exist_ok=True)
    committed = load_manifest()

    stale: list[str] = []
    entries: list[dict[str, object]] = []
    before = after = 0
    for source in sources:
        spec = spec_for(source)
        destination = THUMB_DIR / str(spec["thumb"])
        before += source.stat().st_size

        # Reuse the committed thumb only when the manifest still describes this
        # source AND the file on disk is byte-for-byte what was recorded, so a
        # swapped, truncated, or hand-edited WebP is never trusted unread.
        record = committed.get(destination.name)
        reusable = (
            record is not None
            and destination.is_file()
            and all(record.get(key) == value for key, value in spec.items())
            and record.get("thumb_sha256") == sha256(destination)
        )
        if reusable:
            payload = destination.read_bytes()
        elif check_only:
            stale.append(f"{destination.name} ({stale_reason(record, spec, destination)})")
            after += destination.stat().st_size if destination.is_file() else 0
            continue
        else:
            payload = render(source, int(spec["width"]), int(spec["quality"]))
            destination.write_bytes(payload)

        try:
            thumb_width, thumb_height = decoded_size(payload)
        except OSError:
            stale.append(f"{destination.name} (does not decode)")
            continue
        if (thumb_width, thumb_height) != (spec["width"], spec["height"]):
            stale.append(
                f"{destination.name} (is {thumb_width}×{thumb_height}px, expected "
                f"{spec['width']}×{spec['height']}px)"
            )
            continue

        entries.append(dict(spec, thumb_sha256=sha256(destination)))
        after += len(payload)

    expected = {f"{source.stem}.webp" for source in sources} | {MANIFEST.name}
    orphans = (
        sorted(
            p.name for p in THUMB_DIR.iterdir() if p.is_file() and p.name not in expected
        )
        if THUMB_DIR.is_dir()
        else []
    )
    for name in orphans:
        if check_only:
            stale.append(f"{name} (not generated from a screenshot)")
            continue
        (THUMB_DIR / name).unlink()

    manifest = json.dumps(
        {
            "schema_version": 1,
            "renderer": {"format": "WEBP", "method": 6, "resample": "LANCZOS"},
            "entries": entries,
        },
        indent=2,
    )
    manifest += "\n"
    committed_manifest = (
        MANIFEST.read_text(encoding="utf-8") if MANIFEST.is_file() else None
    )
    if not check_only:
        MANIFEST.write_text(manifest, encoding="utf-8")
    elif committed_manifest != manifest:
        stale.append(f"{MANIFEST.name} (out of date)")

    if stale:
        if check_only:
            print("build-readme-thumbs: thumbs are stale, re-run the script:")
        else:
            print("build-readme-thumbs: could not produce a usable thumb:")
        for name in stale:
            print(f"  {name}")
        return 1

    print(
        f"OK readme thumbs: {len(sources)} images, "
        f"{before // 1024} KB -> {after // 1024} KB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
