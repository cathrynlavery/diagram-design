#!/usr/bin/env python3
"""Adversarial tests for verify-exploded.py, both polarities.

Per ADR 0005, a geometric contract is a checker plus fixtures that prove it
fires when it should and stays quiet when it should not. Every mutation below
still renders as a plausible exploded view; the defects are geometric lies
that only a reprojection catches.

Usage: python3 scripts/test-verify-exploded.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from decimal import Decimal

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-exploded.py"
BUILDER = ROOT / "scripts/build-exploded-examples.py"
ASSETS = ROOT / "skills/diagram-design/assets"
STACK = ASSETS / "example-exploded.html"
PHONE = ASSETS / "example-exploded-phone.html"
ANIMATED = ASSETS / "example-exploded-phone-animated.html"
SHIPPED = sorted(ASSETS.glob("example-exploded*.html"))


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(CHECKER), *args], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def builder():
    spec = importlib.util.spec_from_file_location("build_exploded", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


def page(module, fig, slug="mutant"):
    body, vh, _ = module.build_svg(fig, "light", False, slug)
    sk = module.SKINS["light"]
    return module.MINIMAL.format(eyebrow=module.EYEBROW, title=fig.title, font=module.FONT_LINK, slug=slug, desc=fig.desc, vh=vh, body=body,
                                 **{k: sk[k] for k in ("paper", "ink", "muted", "accent")})


def once(pattern, repl, source, flags=0):
    out, n = re.subn(pattern, repl, source, count=1, flags=flags)
    if n != 1:
        raise AssertionError(f"mutation pattern did not match: {pattern}")
    return out


def bump_first_number(match):
    head, value = match.group(1), float(match.group(2))
    return f"{head}{value + 3:g}"


def main() -> int:
    failures: list[str] = []
    stack = STACK.read_text(encoding="utf-8")
    phone = PHONE.read_text(encoding="utf-8")
    animated = ANIMATED.read_text(encoding="utf-8")
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

    # A gap under the floor: the real builder with the gap factor turned down.
    low = module.FIGURES["exploded"]()
    low.gap_k = 0.2
    low_gap = page(module, low)

    # Leaders across parts and crowded labels: the real builder with the gap forced shut.
    real_explode = module.explode

    def shut(parts, gap_k):
        levels = module.levels_of(parts)
        z = 0
        for k in range(max(levels) + 1):
            members = [p for p, level in zip(parts, levels) if level == k]
            for p in members:
                p.z = z
            z += max(p.t for p in members) + 8
        return 8

    module.explode = shut
    crowded = page(module, module.FIGURES["exploded-phone"]())
    module.explode = real_explode

    # Inline SVG spans style the label without changing its visible name.
    with tempfile.TemporaryDirectory(prefix="verify-label-spans-") as tmp:
        for label, replacement in (
            ("styled span", '<tspan font-weight="600">Data</tspan>'),
            ("mixed nested span text", 'D<tspan>a<tspan>t</tspan></tspan>a'),
            ("undrawn title and desc", 'Data<title>Data part</title><desc>Storage layer</desc>'),
        ):
            path = Path(tmp) / "label-span.html"
            path.write_text(stack.replace(">Data</text>", ">" + replacement + "</text>", 1), encoding="utf-8")
            code, output = run(str(path))
            if code != 0:
                failures.append(f"{label} failed: {output}")
            else:
                print(f"OK: {label} retains the declared name")

    cases = {
        "silhouette vertex moved": (
            once(r'(data-role="silhouette" d="M )(-?\d+(?:\.\d+)?)', bump_first_number, stack),
            "silhouette vertex 0"),
        "corner arc off the 2:1 ellipse": (
            once(r'(data-role="silhouette" d="M [^"]*?A )(\d+(?:\.\d+)?) (\d+(?:\.\d+)?)', r"\g<1>20 10", stack),
            "is not the 2:1 ellipse"),
        "corner arc sweeps the wrong way": (
            once(r'(data-role="silhouette" d="M [^"]*?A \d+(?:\.\d+)? \d+(?:\.\d+)? 0 0 )1', r"\g<1>0", stack),
            "corner arc flags"),
        "transform moves a part": (
            once(r'(data-part="logic")', r'\1 transform="translate(0 -12)"', stack),
            "carries transform="),
        "transform on a silhouette": (
            once(r'(data-role="silhouette")', r'\1 transform="translate(4 0)"', stack),
            "carries transform="),
        "duplicate label for one part": (
            once(r'(<g data-role="label">.*?</g>)', lambda m: m.group(1) + m.group(1), stack, re.S),
            "has more than one label"),
        "silhouette missing": (
            once(r'data-role="silhouette"', 'data-role="outline"', stack),
            "has no data-role=silhouette"),
        "unequal gap": (
            once(r'(data-part="interface"[^>]*data-z=")(\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 4:g}", stack),
            "gaps must be equal"),
        "bottom level lifted": (
            once(r'(data-part="data"[^>]*data-z=")0"', r'\g<1>4"', stack),
            "must stay at z = 0"),
        "one level split across two heights": (
            once(r'(data-part="battery"[^>]*data-z=")(\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) - 4:g}", phone),
            "sit at different z"),
        "gap under the floor": (low_gap, "is under max(0.5"),
        "leader crosses another part": (crowded, "crosses part"),
        "labels crowd": (crowded, "px apart"),
        "second focal part": (
            once(r'(data-part="data")', r"\1 data-focal", stack),
            "focal parts"),
        "three-word label": (
            stack.replace('data-name="Logic"', 'data-name="Core logic tier"').replace(">Logic</text>", ">Core logic tier</text>"),
            "keep labels to one or two"),
        "slanted leader": (
            once(r'(data-role="leader" x1="[^"]+" y1="[^"]+" x2="[^"]+" y2=")(-?\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 5:g}", stack),
            "is not horizontal"),
        "leader off the right extreme": (
            once(r'(data-role="leader" x1=")(-?\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 10:g}", stack),
            "the part's right extreme is"),
        "label out of the column": (
            once(r'(data-role="name" x=")(-?\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 8:g}", stack),
            "columns"),
        "label without a name": (
            once(r'data-role="name"', 'data-role="caption"', stack),
            "needs a data-role=name"),
        "trace line leans": (
            once(r'(data-role="trace" x1="[^"]+" y1="[^"]+" x2=")(-?\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 6:g}", stack),
            "trace line is not vertical"),
        "trace line solid": (
            once(r'(data-role="trace"[^>]*?) stroke-dasharray="4,3"', r"\1", stack),
            "trace line must be dashed"),
        "animated lift disagrees with geometry": (
            once(r'(--lift:)(-?\d+(?:\.\d+)?)', lambda m: f"{m.group(1)}{float(m.group(2)) + 12:g}", animated),
            "minus closed z"),
        "static part positioned by style": (
            once(r'(data-part="logic")', r'\1 style="transform:translateY(-8px)"', stack),
            "carries a style attribute"),
    }

    with tempfile.TemporaryDirectory() as tmp:
        for name, (source, expect) in cases.items():
            path = Path(tmp) / f"example-exploded-{re.sub(r'[^a-z]+', '-', name)}.html"
            path.write_text(source, encoding="utf-8")
            code, output = run(str(path))
            if code == 0:
                failures.append(f"mutation passed: {name}")
            elif expect not in output:
                failures.append(f"mutation {name!r} failed for the wrong reason (wanted {expect!r}):\n{output}")
            else:
                print(f"OK: fails on {name}")

    # Standard SVG numeric spellings do not change the projected silhouette.
    with tempfile.TemporaryDirectory(prefix="silhouette-numeric-") as tmp:
        original = (ASSETS / "example-exploded-phone.html").read_text(encoding="utf-8")
        for signed in (False, True):
            def reencode_path(match):
                def number(token):
                    text = token.group(0)
                    if text in ("0", "1"):
                        return text  # SVG arc flags are single digits, not numbers.
                    encoded = format(Decimal(text), "E")
                    return ("+" if signed and not encoded.startswith("-") else "") + encoded
                return match.group(1) + re.sub(r"-?\d+(?:\.\d+)?", number, match.group(2)) + match.group(3)
            encoded = re.sub(r'(<path\b[^>]*?\bd=")([^"]+)(")', reencode_path, original)
            path = Path(tmp) / "numeric.html"
            path.write_text(encoded, encoding="utf-8")
            code, output = run(str(path))
            if code:
                failures.append(f"valid scientific path spelling (signed={signed}) rejected: {output}")
            else:
                print(f"OK: scientific path spelling, signed={signed}")

    spec = importlib.util.spec_from_file_location("verify_exploded_numeric", CHECKER)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    points, arcs, _ = verifier.parse_path("M .5 +.25 L -1e1 2E+1 Z")
    if points != [(0.5, 0.25), (-10.0, 20.0)] or arcs != [False, False]:
        failures.append(f"signed/leading-decimal operands misread: {points}, {arcs}")
    for malformed in ("M 1e+ 2 L 3 4 Z", "M 1e999 2 L 3 4 Z", "M 1 2 q 3 4 Z",
                      "M 1 2 A 3 4 0 0e0 1 5 6 Z", "M 1 2 A 3 4 0 0 1.0 5 6 Z"):
        try:
            verifier.parse_path(malformed)
        except (ValueError, IndexError):
            print("OK: malformed, non-finite, or unsupported path is rejected")
        else:
            failures.append(f"invalid path accepted: {malformed}")

    with tempfile.TemporaryDirectory(prefix="silhouette-flag-") as tmp:
        changed = once(r'(data-role="silhouette" d="M [^"]*? A [\d.]+ [\d.]+ 0 )0( 1 )',
                       r'\g<1>0e0\2', phone)
        path = Path(tmp) / "invalid-flag.html"
        path.write_text(changed, encoding="utf-8")
        code, output = run(str(path))
        if not code or "arc flags must be literal 0 or 1" not in output:
            failures.append(f"invalid native arc flag accepted: {output}")
        else:
            print("OK: invalid numeric arc-flag spelling is rejected by public verifier")

    code, _ = run()
    if code != 2:
        failures.append(f"usage error should exit 2, got {code}")
    else:
        print("OK: usage error exits 2")

    if failures:
        print("\nFAIL verify-exploded tests:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"\nOK: verify-exploded passes {len(SHIPPED)} shipped files and fails all {len(cases)} mutations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
