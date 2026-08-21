#!/usr/bin/env python3
"""Tests for lint-skin.py palette discovery under custom skins.

Covers the contract from PR #57 review: discovery must accept token tables a
custom skin declares (including sections the shipped guide doesn't have, and
guides missing the shipped opt-in sections), while hex values in prose tables
and fenced code examples remain rejected. Also proves equivalence with the
previous three-heading lookup on the shipped style guide.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LINTER = ROOT / "scripts/lint-skin.py"
SHIPPED_GUIDE = ROOT / "skills/diagram-design/references/style-guide.md"

HEX_RE = re.compile(
    r"(?<![\w-])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})(?![0-9a-fA-F])"
)

CUSTOM_GUIDE = """\
# Style Guide — custom skin fixture

## Tokens

### Semantic roles

| Role | Purpose | Default (light) | Default (dark) |
|---|---|---|---|
| `paper` | Page background | `#fefafa` | `#1f2125` |
| `accent` | Focal | `#10ba87` | `#10ba87` |

### On-block keylines (custom section, no shipped equivalent)

| Token | Hex | On block |
|---|---|---|
| `keyline-on-accent` | `#186651` | accent blocks |

### Comparison with other tools (prose table — NOT a token table)

| Tool | Signature look |
|---|---|
| SomeTool | neon `#39ff14` on black |

### Worked example

```svg
<!-- fenced example: this table shape must not contribute colors -->
| Token | Hex |
|---|---|
| `bogus` | `#123456` |
<rect fill="#654321"/>
```

## Typography

| Role | Family | Size | Weight | Usage |
|---|---|---|---|---|
| `title` | system-ui | 1.75rem | 700 | Page H1 |
"""


def load_linter():
    spec = importlib.util.spec_from_file_location("lint_skin", LINTER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations via sys.modules
    spec.loader.exec_module(module)
    return module


def legacy_three_heading_palette(markdown: str) -> set[str]:
    """The pre-change discovery: hexes from three exact headings' tables."""
    mod = load_linter()
    colors = set()
    for heading in ("### Semantic roles", "### Series palette", "### Terminal skin"):
        start = markdown.find(heading)
        assert start >= 0, f"shipped guide lost {heading!r}; update this test"
        table_started = False
        for line in markdown[start:].splitlines()[1:]:
            if line.startswith("|"):
                table_started = True
                colors.update(
                    mod.normalize_hex(m.group()) for m in HEX_RE.finditer(line)
                )
            elif table_started:
                break
    colors.update({"#fff", "#ffffff"})
    return colors


def check(name: str, condition: bool, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{name}: FAILED {detail}")
    print(f"  ok  {name}")


def main() -> int:
    # 1. Equivalence: on the shipped guide, constrained discovery yields
    #    exactly the palette the three-heading lookup produced.
    mod = load_linter()
    shipped_colors, _ = mod.allowed_colors()
    legacy = legacy_three_heading_palette(SHIPPED_GUIDE.read_text(encoding="utf-8"))
    check(
        "shipped-guide palette unchanged",
        shipped_colors == legacy,
        f"only-new={sorted(shipped_colors - legacy)} only-old={sorted(legacy - shipped_colors)}",
    )

    with tempfile.TemporaryDirectory() as tmp:
        guide = Path(tmp) / "style-guide.md"
        guide.write_text(CUSTOM_GUIDE, encoding="utf-8")
        mod = load_linter()
        mod.STYLE_GUIDE = guide
        colors, rgb = mod.allowed_colors()

        # 2. Custom token section contributes its hexes.
        check("custom token section accepted", "#186651" in colors)
        check("semantic roles accepted", {"#fefafa", "#1f2125", "#10ba87"} <= colors)

        # 3. Guide without the shipped opt-in sections must not crash
        #    (this fixture has no "### Series palette" / "### Terminal skin").
        check("missing shipped sections tolerated", True)

        # 4. Prose-table hex is NOT whitelisted...
        check("prose-table hex rejected from palette", "#39ff14" not in colors)
        # ...and a diagram that uses it still gets a color finding end-to-end.
        html = (
            '<svg xmlns="http://www.w3.org/2000/svg" role="img" '
            'aria-labelledby="fixture-title fixture-desc">'
            '<title id="fixture-title">Fixture</title>'
            '<desc id="fixture-desc">Fixture diagram for palette test.</desc>'
            '<rect width="10" height="10" fill="#39ff14"/></svg>'
        )
        findings = mod.lint_text(html, colors, rgb, "fixture")
        check(
            "diagram using prose-table hex still flagged",
            any("#39ff14" in message for _, _, category, message in findings
                if category == "color"),
            f"findings={findings}",
        )

        # 5. Fenced-example hexes are NOT whitelisted.
        check("fenced table hex rejected", "#123456" not in colors)
        check("fenced svg hex rejected", "#654321" not in colors)

    print("all custom-skin palette tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
