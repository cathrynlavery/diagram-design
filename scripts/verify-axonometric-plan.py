#!/usr/bin/env python3
"""Verify axonometric plans against the geometry they declare.

The plate and every box (wall, furniture, building, tree) declare their model
box (``data-rect``, ``data-z``, ``data-h`` or ``data-t``). This checker
reprojects each one with iso(x, y, z) = [x - y, (x + y) / 2 - z], using the
projection in verify-exploded.py rather than the example builder, and fails on:

- a silhouette vertex, corner arc, or arc flag off the projection of its box;
- a box outside the plate, or two box footprints that overlap;
- paint order: a box drawn after one that sits in front of it on screen;
- a box that floats above or sinks into the plate;
- a tag that is not centred on the plan point it declares, a tag whose
  point is not inside the room or on the roof it names, two tags that
  overlap, a tag longer than two words, a room or building with no tag or
  with two;
- more than one focal room or building, an SVG transform, or a style
  attribute anywhere in the figure.

    python3 scripts/verify-axonometric-plan.py --all
    python3 scripts/verify-axonometric-plan.py skills/diagram-design/assets/example-axonometric-plan.html
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "skills/diagram-design/assets"
TOL = 0.05
TRUNK = 8  # a tree canopy stands this far above the plate on its trunk

_spec = importlib.util.spec_from_file_location("verify_exploded", Path(__file__).with_name("verify-exploded.py"))
vx = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = vx
_spec.loader.exec_module(vx)


def numbers(text, count, what, errors):
    vals = vx.NUMBER.findall(text or "")
    if len(vals) != count:
        errors.append(f"{what} must be {count} numbers; found {text!r}")
        return None
    return tuple(float(v) for v in vals)


def check_silhouette(el, origin, rect, z0, z1, what, errors):
    sil = next((c for c in el.walk() if c.tag == "path" and c.attrs.get("data-role") == "silhouette"), None)
    if sil is None:
        errors.append(f"{what} has no data-role=silhouette path")
        return
    want, want_arcs = vx.expected_silhouette(origin, rect, z0, z1)
    try:
        got, got_arcs, arcs = vx.parse_path(sil.attrs.get("d", ""))
    except (ValueError, IndexError) as exc:
        errors.append(f"{what} silhouette is unreadable ({exc})")
        return
    if len(got) != len(want) or got_arcs != want_arcs:
        errors.append(f"{what} silhouette has {len(got)} vertices; its box projects to {len(want)}")
        return
    for i, (g, w) in enumerate(zip(got, want)):
        if abs(g[0] - w[0]) > TOL or abs(g[1] - w[1]) > TOL:
            errors.append(f"{what} silhouette vertex {i} is at {g}; iso() of its box puts it at ({w[0]:.2f}, {w[1]:.2f})")
            return
    r = rect[4]
    for rx, ry, rotation, large, sweep in arcs:
        if abs(rx - r * math.sqrt(2)) > TOL or abs(ry - r / math.sqrt(2)) > TOL:
            errors.append(f"{what} corner arc {rx:g}x{ry:g} is not the 2:1 ellipse of radius {r:g}")
            return
        if rotation != 0 or large != 0 or sweep != 1:
            errors.append(f"{what} corner arc flags are rotation {rotation:g}, large-arc {large:g}, sweep {sweep:g}; a projected corner is 0 0 1")
            return


def behind(a, b):
    return a[2] <= b[0] + 1e-6 or a[3] <= b[1] + 1e-6


def screen_box(origin, rect, z0, z1):
    poly = vx.silhouette_poly(origin, rect, z0, z1)
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def overlaps(a, b):
    return a[0] < b[2] - TOL and b[0] < a[2] - TOL and a[1] < b[3] - TOL and b[1] < a[3] - TOL


def verify_source(source: str, name: str) -> list[str]:
    errors: list[str] = []
    tree = vx.Tree()
    tree.feed(source)
    roots = [el for el in tree.root.walk() if el.tag == "g" and "data-axo-plan" in el.attrs]
    if len(roots) != 1:
        return [f"{name}: expected one <g data-axo-plan>; found {len(roots)}"]
    fig = roots[0]
    origin = numbers(fig.attrs.get("data-origin"), 2, f"{name}: data-origin", errors)
    if origin is None:
        return errors

    for el in [fig, *fig.walk()]:
        for attr in ("transform", "style"):
            if attr in el.attrs:
                errors.append(f"{name}: <{el.tag}> carries {attr}={el.attrs[attr]!r}; position comes from projected coordinates")

    plates = [el for el in fig.walk() if el.tag == "g" and "data-plate" in el.attrs]
    if len(plates) != 1:
        return errors + [f"{name}: expected one <g data-plate>; found {len(plates)}"]
    plate_el = plates[0]
    plate = numbers(plate_el.attrs.get("data-rect"), 5, f"{name}: plate data-rect", errors)
    pt = vx.num(plate_el.attrs.get("data-t"), f"{name}: plate data-t", errors)
    if plate is None or pt is None:
        return errors
    check_silhouette(plate_el, origin, plate, 0, pt, f"{name}: plate", errors)

    order = {id(el): i for i, el in enumerate(fig.walk())}
    boxes = []
    for el in fig.walk():
        if el.tag != "g" or "data-box" not in el.attrs:
            continue
        rect = numbers(el.attrs.get("data-rect"), 5, f"{name}: box data-rect", errors)
        z = vx.num(el.attrs.get("data-z"), f"{name}: box data-z", errors)
        h = vx.num(el.attrs.get("data-h"), f"{name}: box data-h", errors)
        if rect is None or z is None or h is None:
            continue
        label = el.attrs.get("data-name") or f"{el.attrs.get('data-kind', 'box')} at {rect[:4]}"
        boxes.append(dict(el=el, rect=rect, z=z, h=h, label=label, kind=el.attrs.get("data-kind", ""),
                          name=el.attrs.get("data-name", ""), focal="data-focal" in el.attrs))
        check_silhouette(el, origin, rect, z, z + h, f"{name}: {label}", errors)

    # Boxes stand on the plate top (a canopy on its trunk), inside the plate, and never share floor area.
    plate_top = 0 + pt
    for b in boxes:
        want_z = plate_top + (TRUNK if b["kind"] == "tree" else 0)
        if abs(b["z"] - want_z) > TOL:
            errors.append(f"{name}: {b['label']} sits at z {b['z']:g}; it must stand on the plate top at z {want_z:g}")
        x0, y0, x1, y1, _ = b["rect"]
        if x0 < plate[0] - TOL or y0 < plate[1] - TOL or x1 > plate[2] + TOL or y1 > plate[3] + TOL:
            errors.append(f"{name}: {b['label']} stands outside the plate")
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            ar, br = a["rect"], b["rect"]
            if ar[0] < br[2] - TOL and br[0] < ar[2] - TOL and ar[1] < br[3] - TOL and br[1] < ar[3] - TOL:
                errors.append(f"{name}: {a['label']} and {b['label']} overlap on the plate")

    # Paint order: whatever is behind on screen is drawn first.
    for a in boxes:
        sa = screen_box(origin, a["rect"], a["z"], a["z"] + a["h"])
        for b in boxes:
            if a is b:
                continue
            sb = screen_box(origin, b["rect"], b["z"], b["z"] + b["h"])
            if overlaps(sa, sb) and behind(a["rect"], b["rect"]) and not behind(b["rect"], a["rect"]):
                if order[id(a["el"])] > order[id(b["el"])]:
                    errors.append(f"{name}: {a['label']} is behind {b['label']} but painted after it")

    # Tags: centred on their point, one per named room or building, never overlapping.
    tags = []
    places: dict[str, list] = {}
    for el in fig.walk():
        if el.tag != "g" or el.attrs.get("data-role") != "tag":
            continue
        at = numbers(el.attrs.get("data-at"), 3, f"{name}: tag data-at", errors)
        rect = next((c for c in el.walk() if c.tag == "rect"), None)
        text = next((c for c in el.walk() if c.tag == "text" and c.attrs.get("data-role") == "name"), None)
        if at is None or rect is None or text is None:
            errors.append(f"{name}: a tag needs data-at, a backing rect, and a data-role=name text")
            continue
        x, y = origin[0] + at[0] - at[1], origin[1] + (at[0] + at[1]) / 2 - at[2]
        rx, ry = float(rect.attrs.get("x", "nan")), float(rect.attrs.get("y", "nan"))
        rw, rh = float(rect.attrs.get("width", "nan")), float(rect.attrs.get("height", "nan"))
        label = text.text.strip()
        if abs(rx + rw / 2 - x) > TOL or abs(ry - (y - 16)) > TOL:
            errors.append(f"{name}: tag {label!r} sits at ({rx + rw / 2:g}, {ry:g}); its plan point projects to ({x:.2f}, {y - 16:.2f})")
        if len(label.split()) > 2:
            errors.append(f"{name}: tag {label!r} has {len(label.split())} words; keep tags to one or two")
        if el.attrs.get("data-name") != label:
            errors.append(f"{name}: tag text {label!r} disagrees with its data-name {el.attrs.get('data-name')!r}")
        tags.append((label, (rx, ry, rx + rw, ry + rh)))
        places[label] = places.get(label, []) + [at]
    for i, (la, ra) in enumerate(tags):
        for lb, rb in tags[i + 1:]:
            if overlaps(ra, rb):
                errors.append(f"{name}: tags {la!r} and {lb!r} overlap")
    named = [el.attrs["data-name"] for el in fig.walk() if el.tag == "g" and "data-room" in el.attrs]
    named += [b["name"] for b in boxes if b["kind"] == "building"]
    counts = {}
    for label, _ in tags:
        counts[label] = counts.get(label, 0) + 1
    for n in named:
        if counts.get(n, 0) != 1:
            errors.append(f"{name}: {n!r} has {counts.get(n, 0)} tags; each room or building gets exactly one")
    for label in counts:
        if label not in named:
            errors.append(f"{name}: tag {label!r} names no room or building")

    # Each tag stands on the thing it names: inside its room on the floor, or on its building's roof.
    targets = {}
    for el in fig.walk():
        if el.tag == "g" and "data-room" in el.attrs:
            rect = numbers(el.attrs.get("data-rect"), 5, f"{name}: room data-rect", errors)
            if rect is not None:
                targets[el.attrs["data-name"]] = (rect, plate_top, "room")
    for b in boxes:
        if b["kind"] == "building":
            targets[b["name"]] = (b["rect"], b["z"] + b["h"], "roof")
    for label, points in places.items():
        if label not in targets:
            continue
        rect, z, where = targets[label]
        for at in points:
            inside = rect[0] + TOL < at[0] < rect[2] - TOL and rect[1] + TOL < at[1] < rect[3] - TOL
            if not inside or abs(at[2] - z) > TOL:
                errors.append(f"{name}: tag {label!r} stands at {at}; it must sit inside its {where} {rect[:4]} at z {z:g}")

    focal = [el for el in fig.walk() if el.tag == "g" and "data-focal" in el.attrs]
    if len(focal) > 1:
        errors.append(f"{name}: {len(focal)} focal elements; the accent goes on one room or building")
    return errors


def verify(path: Path) -> list[str]:
    try:
        display = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        display = str(path)
    return verify_source(path.read_text(encoding="utf-8"), display)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify axonometric plan geometry.")
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--all", action="store_true", help="check every shipped example-axonometric-plan*.html")
    args = parser.parse_args()
    files = sorted(ASSETS.glob("example-axonometric-plan*.html")) if args.all else args.files
    if not files:
        parser.error("name files or pass --all")
    errors = []
    for path in files:
        errors += verify(path)
    if errors:
        print(f"FAIL axonometric plan: {len(errors)} problem(s)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"OK axonometric plan: {len(files)} file(s) match their declared geometry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
