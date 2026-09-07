#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-unit-grid.py"


def load_verifier():
    spec = importlib.util.spec_from_file_location("verify_unit_grid", VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def chart(cells: str, filled: int = 2) -> str:
    return (
        '<svg data-unit-grid="true" data-unit-total="100" data-unit-filled="' + str(filled)
        + '" data-unit-rows="10" data-unit-columns="10">' + cells + '</svg>'
    )


def cell(index: int, state: str = "empty", width: int = 20) -> str:
    return (
        f'<rect data-unit-cell="{state}" data-unit-index="{index}" '
        f'x="{index % 10 * 24}" y="{index // 10 * 24}" width="{width}" height="20"/>'
    )


def main() -> int:
    verifier = load_verifier()
    valid_cells = "".join(cell(index, "filled" if index < 2 else "empty") for index in range(100))
    cases = [
        ("valid chart", chart(valid_cells), None),
        ("wrong filled count", chart(valid_cells, 3), "declares 3 filled units"),
        ("nonuniform cell", chart(valid_cells.replace('width="20"', 'width="24"', 1)), "identical dimensions"),
        ("duplicate index", chart(valid_cells.replace('data-unit-index="99"', 'data-unit-index="98"')), "indices"),
        ("missing cell", chart(valid_cells.rsplit("<rect", 1)[0]), "has 99 data-unit-cell"),
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        for name, source, expected in cases:
            path = Path(directory) / "fixture.html"
            path.write_text(source, encoding="utf-8")
            findings = verifier.check(path)
            if expected is None and findings:
                failures.append(f"{name} failed: {findings}")
            elif expected is not None and not any(expected in finding for finding in findings):
                failures.append(f"{name} did not report {expected!r}: {findings}")
            else:
                print(f"OK: {name}")
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

