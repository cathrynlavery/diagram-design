#!/usr/bin/env python3
"""Adversarial tests for verify-contrast.py - both polarities, both skins.

Per ADR 0005, a contract is a checker plus fixtures proving it fires when it
should and stays quiet when it shouldn't. The red half matters most here: the
palette this gate replaced (issue #161) shipped because nothing computed a
ratio, so the first cases below restore that palette and require the gate to
name every token that failed, on the skin it failed on.

Cases:
- the shipped style guide passes (green);
- the retired palette fails on exactly the four tokens that were under their
  bars: light accent and soft, dark soft and link (red);
- a translucent value is composited over paper before it is measured, so a
  token that passes opaque fails at low alpha (red), and an rgba() at alpha 1
  measures the same as its hex (green);
- a token used as text is held to 4.5:1 even when it would clear the 3:1
  non-text bar (red);
- `ink-strong` is measured on the accent fill it sits on, not on paper (red);
- an unknown role, a missing role, and an unparseable value fail closed (red);
- every shipped preset parses with the same token roles as style-guide.md,
  passes contrast, and has exactly one accent colour per skin (green);
- a fixture whose light accent sits at 2.86:1 fails (red);
- `--all-presets` against a temporary directory: one failing preset, a
  failing series-palette stroke, a missing required slug, and an invalid
  filename each make the batch fail (red); a passing series palette is
  measured and a preset without a series table passes (green).

Usage: python3 scripts/test-verify-contrast.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-contrast.py"
STYLE_GUIDE = ROOT / "skills/diagram-design/references/style-guide.md"
PRESETS_DIR = ROOT / "skills/diagram-design/references/presets"
LOW_CONTRAST = ROOT / "scripts/fixtures/preset-low-contrast.md"

NS = runpy.run_path(str(CHECKER), run_name="verify_contrast_test")
CHECK = NS["check"]
CONTRAST = NS["contrast"]
COMPOSITE = NS["composite"]
PARSE_COLOR = NS["parse_color"]
PARSE_TOKENS = NS["parse_tokens"]
HEX_RE = NS["HEX_RE"]
RGBA_RE = NS["RGBA_RE"]
SHIPPED_PRESET_PATHS = NS["shipped_preset_paths"]
REQUIRED_PRESET_SLUGS = NS["REQUIRED_PRESET_SLUGS"]
SKINS = NS["SKINS"]
ROLE_USES = NS["ROLE_USES"]

SHIPPED = STYLE_GUIDE.read_text(encoding="utf-8")

ROWS = {
    "soft": "| `soft` | Sublabels, boundary labels | `#5a6580` | `#949eb2` |",
    "accent": "| `accent` | Focal / 1–2 max per diagram | `#bf4520` (burnt-tangerine) | `#f08a59` |",
    "link": "| `link` | HTTP/API calls, external arrows | `#2e5aa8` | `#739fdf` |",
    "ink-strong": "| `ink-strong` | High-contrast text on warm accent fills | `#111111` | `#111111` |",
}

failures: list[str] = []


def ok(condition: bool, message: str) -> None:
    if condition:
        print(f"OK: {message}")
    else:
        failures.append(message)


def with_row(source: str, role: str, replacement: str) -> str:
    row = ROWS[role]
    if source.count(row) != 1:
        raise SystemExit(f"fixture drift: the shipped `{role}` row changed; update ROWS")
    return source.replace(row, replacement)


def findings_for(source: str) -> list[str]:
    return CHECK(source)[1]


def mentions(findings: list[str], skin: str, role: str) -> bool:
    return any(f.startswith(f"{skin}: `{role}`") for f in findings)


def test_shipped_palette_passes() -> None:
    rows, findings = CHECK(SHIPPED)
    ok(not findings, f"the shipped style guide has no contrast findings ({findings})")
    ok(len(rows) == 20, f"every text and non-text use is measured in both skins ({len(rows)} rows)")


def test_retired_palette_fails_on_each_token() -> None:
    source = with_row(SHIPPED, "soft", "| `soft` | Sublabels, boundary labels | `#7a8399` | `#8e98ac` |")
    source = with_row(source, "accent",
                      "| `accent` | Focal / 1–2 max per diagram | `#eb6c36` (atomic-tangerine) | `#f08a59` |")
    source = with_row(source, "link", "| `link` | HTTP/API calls, external arrows | `#2e5aa8` | `#6a95d8` |")
    findings = findings_for(source)
    expected = {("light", "accent"), ("light", "soft"), ("dark", "soft"), ("dark", "link")}
    for skin, role in sorted(expected):
        ok(mentions(findings, skin, role), f"retired {skin} `{role}` is reported")
    ok(not mentions(findings, "dark", "accent"), "the unchanged dark accent is not reported")
    ok(not mentions(findings, "light", "link"), "the unchanged light link is not reported")
    ok(any("light: `accent` as non-text is 2.86:1" in f for f in findings),
       "retired light accent fails the 3:1 non-text bar at 2.86:1")
    code = run_cli(source)
    ok(code == 1, "the CLI exits 1 on the retired palette")


def test_alpha_is_composited_over_paper() -> None:
    translucent = with_row(SHIPPED, "soft",
                           "| `soft` | Sublabels, boundary labels | `rgba(90,101,128,0.5)` | `#949eb2` |")
    ok(mentions(findings_for(translucent), "light", "soft"),
       "soft at 0.5 opacity fails although the opaque value passes")
    opaque = with_row(SHIPPED, "soft",
                      "| `soft` | Sublabels, boundary labels | `rgba(90,101,128,1)` | `#949eb2` |")
    ok(not findings_for(opaque), "rgba() at alpha 1 measures the same as its hex")
    flat = COMPOSITE((0, 0, 0), 0.5, (255, 255, 255))
    ok(flat == (127.5, 127.5, 127.5), "compositing blends channels linearly by alpha")


def test_text_use_is_held_to_text_bar() -> None:
    # #c4562b on #f5f5f5 is about 4.0:1: enough for a stroke, not for a label.
    rgb, _ = PARSE_COLOR("`#c4562b`")
    ratio = CONTRAST(rgb, (245, 245, 245))
    ok(3.0 <= ratio < 4.5, f"fixture accent sits between the bars ({ratio:.2f}:1)")
    source = with_row(SHIPPED, "accent", "| `accent` | Focal / 1–2 max per diagram | `#c4562b` | `#f08a59` |")
    findings = findings_for(source)
    ok(any("light: `accent` as text" in f for f in findings),
       "an accent that clears 3:1 still fails as text")
    ok(not any("light: `accent` as non-text" in f for f in findings),
       "the same accent is not reported as a non-text failure")


def test_ink_strong_is_measured_on_accent_fill() -> None:
    # #5a5a5a on paper is 6:1, but on the 0.85 accent fill it is about 1.6:1.
    source = with_row(SHIPPED, "ink-strong",
                      "| `ink-strong` | High-contrast text on warm accent fills | `#5a5a5a` | `#111111` |")
    ok(mentions(findings_for(source), "light", "ink-strong"),
       "ink-strong that reads on paper but not on the accent fill is reported")


def test_fails_closed() -> None:
    unknown = SHIPPED.replace(ROWS["link"], ROWS["link"] + "\n| `halo` | Glow | `#ffffff` | `#000000` |")
    ok(any("`halo` has no contrast classification" in f for f in findings_for(unknown)),
       "an unclassified role is a finding")
    missing = SHIPPED.replace(ROWS["link"] + "\n", "")
    ok(any("`link` is missing" in f for f in findings_for(missing)), "a missing role is a finding")
    garbled = with_row(SHIPPED, "soft", "| `soft` | Sublabels, boundary labels | `slate` | `#949eb2` |")
    ok(any("light: `soft` no hex or rgba() color" in f for f in findings_for(garbled)),
       "an unparseable value is a finding")
    no_table = SHIPPED.replace("### Semantic roles", "### Roles")
    ok(bool(findings_for(no_table)), "a style guide without the table fails")


def run_cli(source: str) -> int:
    with tempfile.TemporaryDirectory() as raw:
        path = Path(raw) / "style-guide.md"
        path.write_text(source, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--style-guide", str(path), "--quiet"],
            capture_output=True, text=True, check=False,
        )
        return result.returncode


def run_cli_args(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        capture_output=True, text=True, check=False,
    )


def color_count(cell: str) -> int:
    """How many hex or rgba() colours the contrast parser would see in *cell*."""
    return len(HEX_RE.findall(cell)) + len(RGBA_RE.findall(cell))


def test_shipped_presets() -> None:
    default_tokens, default_findings = PARSE_TOKENS(SHIPPED)
    ok(not default_findings, "the shipped style guide still parses")
    default_roles = {skin: set(default_tokens[skin]) for skin in SKINS}
    paths = SHIPPED_PRESET_PATHS()
    found = {path.stem for path in paths}
    ok(
        found == set(REQUIRED_PRESET_SLUGS),
        f"shipped presets are exactly {REQUIRED_PRESET_SLUGS} (found {sorted(found)})",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        tokens, parse_findings = PARSE_TOKENS(source)
        ok(not parse_findings, f"{path.stem} parses with no table findings ({parse_findings})")
        for skin in SKINS:
            roles = set(tokens[skin])
            ok(
                roles == default_roles[skin],
                f"{path.stem} {skin} token roles match style-guide.md "
                f"(missing {sorted(default_roles[skin] - roles)}, "
                f"extra {sorted(roles - default_roles[skin])})",
            )
            ok(
                roles == set(ROLE_USES),
                f"{path.stem} {skin} has every classified role",
            )
            accent = tokens[skin].get("accent", "")
            ok(
                color_count(accent) == 1,
                f"{path.stem} {skin} accent has exactly one colour ({accent!r})",
            )
        rows, findings = CHECK(source, include_series=True)
        ok(not findings, f"{path.stem} has no contrast findings ({findings})")
        ok(
            len(rows) == 30,
            f"{path.stem} measures roles and series in both skins ({len(rows)} rows)",
        )
        series_measured = {(skin, role) for skin, role, *_ in rows if role.startswith("series-")}
        expected_series = {(skin, f"series-{i}") for skin in SKINS for i in range(1, 6)}
        ok(
            series_measured == expected_series,
            f"{path.stem} measures series-1..series-5 in both skins",
        )
        result = run_cli_args(["--style-guide", str(path), "--quiet"])
        ok(result.returncode == 0, f"the CLI exits 0 on {path.stem}")


def test_broken_preset_fixture_fails() -> None:
    source = LOW_CONTRAST.read_text(encoding="utf-8")
    findings = findings_for(source)
    ok(mentions(findings, "light", "accent"), "low-contrast fixture reports light accent")
    ok(
        any("light: `accent` as non-text is 2.86:1" in f for f in findings),
        "low-contrast fixture fails the 3:1 non-text bar at 2.86:1",
    )
    result = run_cli_args(["--style-guide", str(LOW_CONTRAST), "--quiet"])
    ok(result.returncode == 1, "the CLI exits 1 on the low-contrast fixture")


def write_preset_tree(directory: Path, files: dict[str, str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, source in files.items():
        (directory / name).write_text(source, encoding="utf-8")


def shipped_preset_sources() -> dict[str, str]:
    return {
        f"{slug}.md": (PRESETS_DIR / f"{slug}.md").read_text(encoding="utf-8")
        for slug in REQUIRED_PRESET_SLUGS
    }


def run_all_presets_dir(directory: Path) -> subprocess.CompletedProcess:
    return run_cli_args(
        ["--all-presets", "--presets-dir", str(directory), "--quiet"]
    )


def test_all_presets_cli() -> None:
    result = run_cli_args(["--all-presets"])
    ok(result.returncode == 0, "the CLI exits 0 on --all-presets")
    ok(
        "OK verify-contrast --all-presets: 3 presets, 90 role checks" in result.stdout,
        f"--all-presets summarizes three presets including series ({result.stdout.splitlines()[-1]!r})",
    )
    ok(
        "blueprint: light series-5" in result.stdout
        and "graphite: light series-5" in result.stdout
        and "mono-print: dark  series-5" in result.stdout,
        "--all-presets reports measured series rows for passing presets",
    )
    combined = run_cli_args(["--all-presets", "--style-guide", str(STYLE_GUIDE)])
    ok(combined.returncode == 1, "--all-presets refuses --style-guide")
    explicit = run_cli_args(
        ["--all-presets", "--presets-dir", str(PRESETS_DIR), "--quiet"]
    )
    ok(explicit.returncode == 0, "--all-presets --presets-dir on the shipped directory exits 0")
    lonely = run_cli_args(["--presets-dir", str(PRESETS_DIR)])
    ok(lonely.returncode == 1, "--presets-dir without --all-presets is refused")


def test_all_presets_series_palette() -> None:
    files = shipped_preset_sources()
    row = "| `series-5` | `#77849a` (mist) | `#a8b4c2` | Non-focal series |"
    if files["blueprint.md"].count(row) != 1:
        raise SystemExit("fixture drift: blueprint `series-5` row changed")
    files["blueprint.md"] = files["blueprint.md"].replace(
        row, "| `series-5` | `#8a97a8` (mist) | `#a8b4c2` | Non-focal series |"
    )
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        write_preset_tree(directory, files)
        result = run_all_presets_dir(directory)
    ok(result.returncode == 1, "a preset series row below 3:1 makes --all-presets exit 1")
    ok(
        "blueprint: light: `series-5` as non-text is 2.76:1, below 3:1" in result.stdout,
        f"the failing series token and skin are named ({result.stdout.strip()!r})",
    )

    no_series = shipped_preset_sources()
    start = no_series["graphite.md"].index("### Series palette")
    end = no_series["graphite.md"].index("### Terminal skin")
    no_series["graphite.md"] = no_series["graphite.md"][:start] + no_series["graphite.md"][end:]
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        write_preset_tree(directory, no_series)
        result = run_all_presets_dir(directory)
    ok(result.returncode == 0, "a preset without a Series palette table passes --all-presets")
    ok(
        "3 presets, 80 role checks" in result.stdout,
        f"presets with series are still measured when one preset omits the table ({result.stdout.strip()!r})",
    )


def test_all_presets_failing_preset() -> None:
    files = shipped_preset_sources()
    files["blueprint.md"] = LOW_CONTRAST.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        write_preset_tree(directory, files)
        result = run_all_presets_dir(directory)
    ok(result.returncode == 1, "one failing preset makes --all-presets exit 1")
    ok(
        "blueprint: light: `accent` as non-text is 2.86:1" in result.stdout,
        f"the failing preset is named in the batch ({result.stdout.strip()!r})",
    )


def test_all_presets_missing_required() -> None:
    files = {
        name: source
        for name, source in shipped_preset_sources().items()
        if name != "blueprint.md"
    }
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        write_preset_tree(directory, files)
        result = run_all_presets_dir(directory)
    ok(result.returncode == 1, "a missing required preset makes --all-presets exit 1")
    ok(
        "missing required shipped preset(s): blueprint" in result.stdout,
        f"the missing required preset is named ({result.stdout.strip()!r})",
    )


def test_all_presets_invalid_filename() -> None:
    files = shipped_preset_sources()
    files["not_a_slug.md"] = files["graphite.md"]
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        write_preset_tree(directory, files)
        result = run_all_presets_dir(directory)
    ok(result.returncode == 1, "an invalid preset filename makes --all-presets exit 1")
    ok(
        "not valid slugs: not_a_slug.md" in result.stdout,
        f"the invalid preset filename is named ({result.stdout.strip()!r})",
    )


def main() -> int:
    test_shipped_palette_passes()
    test_retired_palette_fails_on_each_token()
    test_alpha_is_composited_over_paper()
    test_text_use_is_held_to_text_bar()
    test_ink_strong_is_measured_on_accent_fill()
    test_fails_closed()
    ok(run_cli(SHIPPED) == 0, "the CLI exits 0 on the shipped style guide")
    test_shipped_presets()
    test_broken_preset_fixture_fails()
    test_all_presets_cli()
    test_all_presets_series_palette()
    test_all_presets_failing_preset()
    test_all_presets_missing_required()
    test_all_presets_invalid_filename()

    for failure in failures:
        print(f"FAIL: {failure}")
    if failures:
        print(f"\n{len(failures)} case(s) failed.")
        return 1
    print("\nOK verify-contrast: both polarities behave, on both skins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
