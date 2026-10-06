#!/usr/bin/env python3
"""Adversarial tests for verify-axonometric-plan.py, both polarities.

Per ADR 0005, a geometric contract is a checker plus fixtures that prove it
fires when it should and stays quiet when it should not. Every mutation below
still renders as a believable plan; the defects are geometric lies that only
reprojection catches.

Usage: python3 scripts/test-verify-axonometric-plan.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-axonometric-plan.py"
BUILDER = ROOT / "scripts/build-axonometric-plan-examples.py"
ASSETS = ROOT / "skills/diagram-design/assets"
OFFICE = ASSETS / "example-axonometric-plan.html"
CAMPUS = ASSETS / "example-axonometric-plan-campus.html"
SHIPPED = sorted(ASSETS.glob("example-axonometric-plan*.html"))


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def builder():
    spec = importlib.util.spec_from_file_location("build_axonometric_plan", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def once(pattern, repl, source, flags=0):
    out, n = re.subn(pattern, repl, source, count=1, flags=flags)
    if n != 1:
        raise AssertionError(f"mutation pattern did not match: {pattern}")
    return out


def shift(delta):
    return lambda m: f"{m.group(1)}{float(m.group(2)) + delta:g}"


def main() -> int:
    failures: list[str] = []
    office = OFFICE.read_text(encoding="utf-8")
    campus = CAMPUS.read_text(encoding="utf-8")
    module = builder()

    for path in SHIPPED:
        code, output = run(str(path))
        if code != 0:
            failures.append(f"shipped example failed: {path.name}\n{output}")
        else:
            print(f"OK: shipped {path.name} passes")
    code, output = run("--all")
    if code != 0:
        failures.append(f"--all failed on the shipped set\n{output}")
    else:
        print("OK: --all passes on the shipped set")

    # Two tags on one spot: the real builder with Dorm A's tag moved onto Dorm B's.
    plan = module.campus()
    dorm_a = next(b for b in plan.boxes if b.name == "Dorm A")
    dorm_b = next(b for b in plan.boxes if b.name == "Dorm B")
    dorm_a.tag_at = (dorm_b.tag_at[0], dorm_b.tag_at[1] - 30)
    body, vh = module.build_svg(plan, "light", False, "mutant")
    sk = module.SKINS["light"]
    crowded = module.MINIMAL.format(eyebrow=module.EYEBROW, title=plan.title, font=module.FONT_LINK, slug="mutant",
                                    desc=plan.desc, vh=vh, body=body, **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})

    def build(plan):
        body, vh = module.build_svg(plan, "light", False, "mutant")
        return module.MINIMAL.format(eyebrow=module.EYEBROW, title=plan.title, font=module.FONT_LINK, slug="mutant",
                                     desc=plan.desc, vh=vh, body=body, **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})

    # A room tag moved onto the next room, still centred on its own declared point.
    office_plan = module.office()
    next(r for r in office_plan.rooms if r.name == "Booth").tag_at = (40, 190)
    wrong_room = build(office_plan)
    # A building tag moved onto another roof.
    site = module.campus()
    next(b for b in site.boxes if b.name == "Labs").tag_at = (75, 70)
    wrong_roof = build(site)

    # A desk lifted 10 units off the floor, with a silhouette redrawn to match its new height,
    # so floating is the only thing wrong with it.
    origin = tuple(float(v) for v in re.search(r'data-axo-plan data-origin="([^"]+)"', office).group(1).split())
    m = re.search(r'<g data-box data-rect="24 28 68 52 0" data-z="(\d+)" data-h="(\d+)"[^>]*><path data-role="silhouette" d="([^"]+)"', office)
    z0, h = float(m.group(1)), float(m.group(2))
    lifted = module.prism(module.Proj(*origin), module.Rect(24, 28, 68, 52, 0), z0 + 10, z0 + 10 + h)["sil"]
    floating = office.replace(m.group(0), m.group(0).replace(f'data-z="{m.group(1)}"', f'data-z="{z0 + 10:g}"').replace(m.group(3), lifted), 1)

    first_box = re.search(r'<g data-box [^>]*>.*?</g>', office, re.S).group(0)
    booth_tag = re.search(r'<g data-role="tag" data-name="Booth".*?</g>', office, re.S).group(0)

    cases = {
        "silhouette vertex moved": (
            once(r'(data-box [^>]*><path data-role="silhouette" d="M )(-?\d+(?:\.\d+)?)', shift(3), office),
            "silhouette vertex 0"),
        "plate corner arc sweeps the wrong way": (
            once(r'(data-plate [^>]*><path data-role="silhouette" d="M [^"]*?A \d+(?:\.\d+)? \d+(?:\.\d+)? 0 0 )1', r"\g<1>0", campus),
            "corner arc flags"),
        "box outside the plate": (
            once(r'(data-plate data-rect="0 0 )360', r"\g<1>300", office),
            "stands outside the plate"),
        "two boxes share floor": (
            once(r'(data-box data-rect=")24 28 68 52', r"\g<1>84 28 128 52", office),
            "overlap on the plate"),
        "box painted out of order": (
            office.replace(first_box, "", 1).replace("</g>\n        <g data-role=\"tag\"", first_box + "</g>\n        <g data-role=\"tag\"", 1)
            if office.count(first_box) == 1 else office,
            "but painted after it"),
        "tag off its plan point": (
            once(r'(<g data-role="tag" data-name="Kitchen"[^>]*><rect x=")(-?\d+(?:\.\d+)?)', shift(10), office),
            "its plan point projects to"),
        "two tags overlap": (crowded, "overlap"),
        "three-word tag": (
            office.replace('data-name="Open office"', 'data-name="Open plan office"').replace(">Open office</text>", ">Open plan office</text>"),
            "keep tags to one or two"),
        "room with no tag": (office.replace(booth_tag, "", 1), "has 0 tags"),
        "room with two tags": (office.replace(booth_tag, booth_tag + booth_tag, 1), "has 2 tags"),
        "tag text disagrees with its name": (
            once(r'(<g data-role="tag" data-name="Lobby".*?>)Lobby(</text>)', r"\1Foyer\2", office, re.S),
            "disagrees with its data-name"),
        "second focal element": (
            once(r'(data-room data-name="Kitchen")', r"\1 data-focal", office),
            "focal elements"),
        "transform moves a box": (
            once(r'(<g data-box )', r'\1transform="translate(0 -8)" ', office),
            "carries transform="),
        "style positions a box": (
            once(r'(<g data-box )', r'\1style="translate: 0 -8px" ', office),
            "carries style="),
        "room tag on another room": (wrong_room, "must sit inside its room"),
        "building tag on another roof": (wrong_roof, "must sit inside its roof"),
        "box floating off the plate": (floating, "it must stand on the plate top"),
        "silhouette missing": (
            once(r'data-box ([^>]*)><path data-role="silhouette"', r'data-box \1><path data-role="outline"', office),
            "has no data-role=silhouette"),
    }

    with tempfile.TemporaryDirectory() as tmp:
        for name, (source, expect) in cases.items():
            path = Path(tmp) / f"example-axonometric-plan-{re.sub(r'[^a-z]+', '-', name)}.html"
            path.write_text(source, encoding="utf-8")
            code, output = run(str(path))
            if code == 0:
                failures.append(f"mutation passed: {name}")
            elif expect not in output:
                failures.append(f"mutation {name!r} failed for the wrong reason (wanted {expect!r}):\n{output}")
            else:
                print(f"OK: fails on {name}")

    code, _ = run()
    if code != 2:
        failures.append(f"usage error should exit 2, got {code}")
    else:
        print("OK: usage error exits 2")

    if failures:
        print("\nFAIL verify-axonometric-plan tests:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nOK: verify-axonometric-plan passes {len(SHIPPED)} shipped files and fails all {len(cases)} mutations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
