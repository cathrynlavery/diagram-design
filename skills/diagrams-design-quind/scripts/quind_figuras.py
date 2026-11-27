#!/usr/bin/env python3
"""Export diagrams as figures for QUIND documents and pages.

    python3 scripts/quind_figuras.py arquitectura.html proceso.html --out figuras
    python3 scripts/quind_figuras.py arquitectura.html --out figuras --pie arquitectura="Contenedores de la plataforma"

Each diagram HTML becomes a figure whose ID is the file name without `.html`
(`arquitectura.html` -> `arquitectura`). A file named `<ID>-dark.html` is the
dark variant of `<ID>` and adds `<ID>-dark.svg`; it is not a figure of its own.

Writes into --out:
  <ID>.png        3x raster of the diagram only, for Word (`format-docs-quind`)
  <ID>.svg        standalone SVG, inlined by pages (`format-artifact-quind`)
  <ID>-dark.svg   only when the dark variant exists
  meta.json       per figure: caption (pie), alt, width_frac

`meta.json` is merged, never replaced: figures already there (charts and
schedules rendered by the QUIND page kit) are kept. In the Markdown each figure
is one block:  ```diagrama <ID>  (optionally with a line `pie: ...`).

The caption defaults to the page <h1>; the alt text is the SVG <title> plus its
<desc>. Run `self_check.py` and `verify_geometry.py` on each file first: this
script exports, it does not review.
"""

from __future__ import annotations

import argparse
import html as html_entities
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PAGE_WIDTH_IN = 6.69   # usable width of a QUIND Word page
MAX_HEIGHT_IN = 6.8    # tallest figure that still leaves room for its caption
SLUG_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def _text(pattern: str, source: str) -> str:
    match = re.search(pattern, source, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", html_entities.unescape(re.sub(r"<[^>]+>", "", match.group(1)))).strip()


def describe(source: str) -> tuple[str, str, float]:
    """Return (caption, alt, width_frac) read from a diagram HTML file."""
    svg = re.search(r"<svg\b.*?</svg>", source, re.IGNORECASE | re.DOTALL)
    if not svg:
        raise ValueError("no <svg> found")
    body = svg.group(0)
    title = _text(r"<title[^>]*>(.*?)</title>", body)
    desc = _text(r"<desc[^>]*>(.*?)</desc>", body)
    caption = _text(r"<h1[^>]*>(.*?)</h1>", source) or title
    alt = desc if not title or desc.lower().startswith(title.lower()) else f"{title}. {desc}".strip()
    view = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', body)
    if not view:
        raise ValueError("the <svg> has no viewBox")
    width, height = float(view.group(1)), float(view.group(2))
    height_in = height / width * PAGE_WIDTH_IN
    width_frac = round(min(1.0, MAX_HEIGHT_IN / height_in), 3) if height_in > MAX_HEIGHT_IN else 1.0
    return caption, alt, width_frac


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", type=Path, help="diagram .html files")
    parser.add_argument("--out", required=True, type=Path, help="figures folder (created if missing)")
    parser.add_argument("--pie", action="append", default=[], metavar="ID=TEXTO",
                        help="caption for one figure; repeatable. Default: the page <h1>")
    parser.add_argument("--scale", type=float, default=3, help="PNG scale, 1 to 4 (default 3)")
    args = parser.parse_args()

    from export_png import rasterize
    from export_svg import export_svg_document

    captions = dict(item.split("=", 1) for item in args.pie if "=" in item)
    args.out.mkdir(parents=True, exist_ok=True)
    meta_path = args.out / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    failures = 0
    for src in args.sources:
        stem = src.stem
        dark = stem.endswith("-dark")
        fig_id = stem[: -len("-dark")] if dark else stem
        if not SLUG_RE.fullmatch(fig_id):
            print(f"✗ {src}: the figure ID «{fig_id}» must be lowercase letters, digits, - or _", file=sys.stderr)
            failures += 1
            continue
        try:
            source = src.read_text(encoding="utf-8")
            caption, alt, width_frac = describe(source)
            # System fonts: the page that inlines the SVG already loads the QUIND
            # fonts, and an @import inside an inline SVG would be a second request.
            (args.out / f"{stem}.svg").write_text(
                export_svg_document(source, src, system_fonts=True), encoding="utf-8"
            )
            if dark:
                print(f"ok  {fig_id} (dark)  → {stem}.svg")
                continue
            rasterize(src, args.out / f"{fig_id}.png", args.scale)
        except Exception as exc:  # report every file, then fail
            print(f"✗ {src}: {exc}", file=sys.stderr)
            failures += 1
            continue
        entry = meta.get(fig_id, {})
        entry.update(caption=captions.get(fig_id) or caption, alt=alt, width_frac=width_frac)
        meta[fig_id] = entry
        note = "" if width_frac == 1.0 else f"  · tall figure: Word will place it at {width_frac:.0%} width"
        if width_frac < 0.75:
            note += " — text will be small; split it or make it wider"
        print(f"ok  {fig_id}  → {fig_id}.png, {fig_id}.svg{note}")

    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"meta.json: {len(meta)} figure(s) in {args.out}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
