#!/usr/bin/env python3
"""Adversarial tests for the committed README thumbnail pipeline."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/build-readme-thumbs.py"


def load_module():
    spec = importlib.util.spec_from_file_location("diagram_design_readme_thumbs", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load build-readme-thumbs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configure(module, root: Path) -> tuple[Path, Path, Path]:
    source_dir = root / "docs/screenshots"
    thumb_dir = source_dir / "thumbs"
    readme = root / "README.md"
    module.REPO = root
    module.SOURCE_DIR = source_dir
    module.THUMB_DIR = thumb_dir
    module.MANIFEST = thumb_dir / "manifest.json"
    module.README = readme
    return source_dir, thumb_dir, readme


def write_source(path: Path, color: str) -> None:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1200, 800), color).save(path, "PNG")


def write_wrong_size_thumb(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (600, 123), "navy").save(path, "WEBP", quality=82, method=6)


def write_readme(path: Path) -> None:
    path.write_text(
        "[![Fixture](docs/screenshots/thumbs/fixture.webp)]"
        "(docs/screenshots/fixture.png)\n",
        encoding="utf-8",
    )


def snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def run(module, args: list[str], expected: int, diagnostic: str) -> None:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        actual = module.main(args)
    if actual != expected:
        raise AssertionError(
            f"expected exit {expected}, got {actual} for {args}:\n{output.getvalue()}"
        )
    if diagnostic not in output.getvalue():
        raise AssertionError(
            f"missing diagnostic {diagnostic!r} for {args}:\n{output.getvalue()}"
        )


def update_thumb_digest(manifest: Path, thumb: Path) -> None:
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["entries"][0]["thumb_sha256"] = hashlib.sha256(thumb.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    module = load_module()
    with tempfile.TemporaryDirectory(prefix="readme-thumbs-test-") as temp_dir:
        repo = Path(temp_dir) / "repo"
        source_dir, thumb_dir, readme = configure(module, repo)
        source = source_dir / "fixture.png"
        thumb = thumb_dir / "fixture.webp"
        manifest = thumb_dir / "manifest.json"
        write_source(source, "orange")
        write_readme(readme)

        run(module, [], 0, "OK readme thumbs: 1 images")
        before = snapshot(repo)
        run(module, ["--check"], 0, "OK readme thumbs: 1 images")
        if snapshot(repo) != before:
            raise AssertionError("--check modified a current thumbnail tree")

        thumb.unlink()
        before = snapshot(repo)
        run(module, ["--check"], 1, "fixture.webp (missing)")
        if snapshot(repo) != before:
            raise AssertionError("--check modified a tree with a missing thumb")
        run(module, [], 0, "OK readme thumbs: 1 images")

        write_source(source, "purple")
        before = snapshot(repo)
        run(module, ["--check"], 1, "source or render settings changed")
        if snapshot(repo) != before:
            raise AssertionError("--check rewrote a source-drifted tree")
        run(module, [], 0, "OK readme thumbs: 1 images")

        thumb.write_bytes(thumb.read_bytes() + b"tampered")
        run(module, ["--check"], 1, "thumb does not match its recorded digest")
        thumb.unlink()
        run(module, [], 0, "OK readme thumbs: 1 images")

        thumb.write_bytes(b"not a WebP")
        update_thumb_digest(manifest, thumb)
        before = snapshot(repo)
        run(module, ["--check"], 1, "fixture.webp (does not decode)")
        if snapshot(repo) != before:
            raise AssertionError("--check rewrote a corrupt digest-matching thumb")
        thumb.unlink()
        manifest.unlink()
        run(module, [], 0, "OK readme thumbs: 1 images")

        write_wrong_size_thumb(thumb)
        update_thumb_digest(manifest, thumb)
        run(module, ["--check"], 1, "fixture.webp (is 600×123px, expected 600×400px)")
        thumb.unlink()
        manifest.unlink()
        run(module, [], 0, "OK readme thumbs: 1 images")

        (thumb_dir / "orphan.webp").write_bytes(b"orphan")
        run(module, ["--check"], 1, "orphan.webp (not generated from a screenshot)")
        (thumb_dir / "orphan.webp").unlink()

        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["renderer"]["method"] = 5
        manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        run(module, ["--check"], 1, "manifest.json (out of date)")
        run(module, [], 0, "OK readme thumbs: 1 images")

        readme.write_text("![Fixture](docs/screenshots/fixture.png)\n", encoding="utf-8")
        run(module, ["--check"], 1, "README preview must link to the full PNG")

        empty_repo = Path(temp_dir) / "empty-repo"
        empty_sources, empty_thumbs, empty_readme = configure(module, empty_repo)
        write_source(empty_sources / "fixture.png", "orange")
        write_readme(empty_readme)
        run(module, ["--check"], 1, "fixture.webp (missing)")
        if empty_thumbs.exists():
            raise AssertionError("--check created the missing thumbnail directory")

    print(
        "PASS: README thumbnails reject source, digest, decode, dimensions, orphan, "
        "manifest, and wiring drift without writing in --check mode"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
