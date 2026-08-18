#!/usr/bin/env python3
"""Verify the machine-readable contract for quantitative polar diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from math import cos, hypot, isfinite, pi, radians, sin
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills" / "diagram-design" / "assets"
DEFAULT_PATHS = (
    ASSET_DIR / "example-polar.html",
    ASSET_DIR / "example-polar-dark.html",
    ASSET_DIR / "example-polar-full.html",
)
TOLERANCE = 0.75


@dataclass
class Category:
    name: str
    index: int
    value: float
    focal: bool
    rays: list[dict[str, str]]
    markers: list[dict[str, str]]
    value_labels: int


@dataclass
class Chart:
    attrs: dict[str, str]
    categories: list[Category]
    wedge_count: int


def _float(value: str | None) -> float:
    try:
        parsed = float(value) if value is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")
    return parsed if isfinite(parsed) else float("nan")


def _int(value: str | None) -> int:
    try:
        return int(value) if value is not None else -1
    except (TypeError, ValueError):
        return -1


class PolarParser(HTMLParser):
    """Capture charts and the geometry-bearing descendants of each category."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.charts: list[Chart] = []
        self._stack: list[str] = []
        self._chart_depth: int | None = None
        self._chart: Chart | None = None
        self._category_stack: list[tuple[int, Category]] = []

    def _in_chart(self) -> bool:
        return self._chart is not None and self._chart_depth is not None

    def _current_category(self) -> Category | None:
        if not self._category_stack:
            return None
        return self._category_stack[-1][1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data = {key.casefold(): value or "" for key, value in attrs}
        depth = len(self._stack)

        if "data-polar-chart" in data:
            chart = Chart(dict(data), [], 0)
            self.charts.append(chart)
            if self._chart is None:
                self._chart = chart
                self._chart_depth = depth

        if self._in_chart():
            if tag == "g" and "data-polar-category" in data:
                category = Category(
                    name=data.get("data-polar-category", ""),
                    index=_int(data.get("data-polar-index")),
                    value=_float(data.get("data-polar-value")),
                    focal=data.get("data-polar-focal", "").casefold() == "true",
                    rays=[],
                    markers=[],
                    value_labels=0,
                )
                assert self._chart is not None
                self._chart.categories.append(category)
                self._category_stack.append((depth, category))
            current = self._current_category()
            if current is not None:
                if tag == "line" and "data-polar-ray" in data:
                    current.rays.append(data)
                elif tag == "circle" and "data-polar-marker" in data:
                    current.markers.append(data)
                elif tag == "text" and "data-polar-value-label" in data:
                    current.value_labels += 1
            if tag == "path" and "data-polar-wedge" in data:
                assert self._chart is not None
                self._chart.wedge_count += 1

        self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self._stack:
            self._stack.pop()
        depth = len(self._stack)

        while self._category_stack and self._category_stack[-1][0] >= depth:
            self._category_stack.pop()
        if self._chart_depth is not None and depth <= self._chart_depth:
            self._chart = None
            self._chart_depth = None
            self._category_stack.clear()


def _parse(path: Path) -> PolarParser:
    parser = PolarParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def _point(attrs: dict[str, str], x_key: str, y_key: str) -> tuple[float, float] | None:
    x = _float(attrs.get(x_key))
    y = _float(attrs.get(y_key))
    if not isfinite(x) or not isfinite(y):
        return None
    return x, y


def check(path: Path) -> list[str]:
    """Return all contract violations found in one HTML document."""

    parser = _parse(path)
    findings: list[str] = []
    if not parser.charts:
        return ["missing data-polar-chart"]
    if len(parser.charts) != 1:
        findings.append(f"duplicate data-polar-chart elements ({len(parser.charts)})")
    chart = parser.charts[0]
    attrs = chart.attrs
    required = (
        "data-polar-cx",
        "data-polar-cy",
        "data-polar-radius",
        "data-polar-min",
        "data-polar-max",
        "data-polar-start-angle",
        "data-polar-clockwise",
        "data-polar-radius-encoding",
        "data-polar-inner-radius",
    )
    numeric_keys = {
        "data-polar-cx",
        "data-polar-cy",
        "data-polar-radius",
        "data-polar-min",
        "data-polar-max",
        "data-polar-start-angle",
        "data-polar-inner-radius",
    }
    metadata: dict[str, float | bool] = {}
    for key in required:
        raw = attrs.get(key)
        if raw is None or raw == "":
            findings.append(f"missing metadata {key}")
            continue
        if key in numeric_keys:
            parsed = _float(raw)
            if not isfinite(parsed):
                findings.append(f"non-numeric metadata {key}")
            else:
                metadata[key] = parsed
        elif key == "data-polar-clockwise":
            value = raw.casefold()
            if value not in {"true", "false"}:
                findings.append(f"non-numeric metadata {key}")
            else:
                metadata[key] = value == "true"

    minimum = metadata.get("data-polar-min")
    maximum = metadata.get("data-polar-max")
    radius = metadata.get("data-polar-radius")
    inner_radius = metadata.get("data-polar-inner-radius")
    cx = metadata.get("data-polar-cx")
    cy = metadata.get("data-polar-cy")
    start_angle = metadata.get("data-polar-start-angle")
    clockwise = metadata.get("data-polar-clockwise")

    if isinstance(minimum, float) and minimum != 0:
        findings.append(f"minimum must be zero (got {minimum:g})")
    if isinstance(maximum, float) and maximum <= 0:
        findings.append(f"maximum must be positive (got {maximum:g})")
    if isinstance(radius, float) and radius <= 0:
        findings.append(f"radius must be positive (got {radius:g})")
    if attrs.get("data-polar-radius-encoding") not in {None, "linear"}:
        findings.append("non-linear radius encoding")
    if isinstance(inner_radius, float) and inner_radius != 0:
        findings.append(f"inner radius must be zero (got {inner_radius:g})")

    count = len(chart.categories)
    if not 4 <= count <= 8:
        findings.append(f"category count {count} outside 4..8")
    indices = [category.index for category in chart.categories]
    if sorted(indices) != list(range(count)):
        findings.append(f"indices must be contiguous 0..{count - 1}")
    names = [category.name.strip() for category in chart.categories]
    if len(names) != len(set(names)):
        findings.append("duplicate trimmed category names")
    if sum(category.focal for category in chart.categories) > 1:
        findings.append("more than one focal category")

    geometry_ready = (
        isinstance(cx, float)
        and isinstance(cy, float)
        and isinstance(radius, float)
        and isinstance(maximum, float)
        and isinstance(start_angle, float)
        and isinstance(clockwise, bool)
        and maximum > 0
        and count > 0
    )
    for category in chart.categories:
        value = category.value
        if not isfinite(value):
            findings.append(f"non-numeric category value for {category.name!r}")
            continue
        if isinstance(minimum, float) and isinstance(maximum, float) and not minimum <= value <= maximum:
            findings.append(f"value {value:g} outside {minimum:g}..{maximum:g}")
        if category.value_labels != 1:
            findings.append(
                f"category {category.name!r} value-label count is {category.value_labels}, expected one"
            )
        if value == 0:
            if category.rays or category.markers:
                findings.append(f"zero category {category.name!r} must not carry a ray or marker")
        elif value > 0:
            if len(category.rays) != 1 or len(category.markers) != 1:
                findings.append(
                    f"positive category {category.name!r} must carry exactly one ray and marker"
                )

        if not geometry_ready or value <= 0 or len(category.rays) != 1:
            continue
        assert isinstance(cx, float)
        assert isinstance(cy, float)
        assert isinstance(radius, float)
        assert isinstance(maximum, float)
        assert isinstance(start_angle, float)
        assert isinstance(clockwise, bool)
        expected_angle = radians(start_angle) + (1 if clockwise else -1) * 2 * pi * category.index / count
        expected_radius = radius * value / maximum
        expected_x = cx + expected_radius * cos(expected_angle)
        expected_y = cy + expected_radius * sin(expected_angle)
        ray = category.rays[0]
        ray_start = _point(ray, "x1", "y1")
        ray_end = _point(ray, "x2", "y2")
        if ray_start is None:
            findings.append(f"ray geometry non-numeric for {category.name!r}")
        elif hypot(ray_start[0] - cx, ray_start[1] - cy) > TOLERANCE:
            findings.append(f"ray start not at center for {category.name!r}")
        if ray_end is None:
            findings.append(f"ray endpoint non-numeric for {category.name!r}")
        elif hypot(ray_end[0] - expected_x, ray_end[1] - expected_y) > TOLERANCE:
            findings.append(
                f"linear endpoint outside tolerance for {category.name!r}: "
                f"expected ({expected_x:g},{expected_y:g}), got ({ray_end[0]:g},{ray_end[1]:g})"
            )
        marker = category.markers[0] if category.markers else None
        marker_end = _point(marker, "cx", "cy") if marker is not None else None
        if marker_end is None:
            if marker is not None:
                findings.append(f"marker endpoint non-numeric for {category.name!r}")
        elif hypot(marker_end[0] - expected_x, marker_end[1] - expected_y) > TOLERANCE:
            findings.append(f"marker endpoint outside tolerance for {category.name!r}")

    if chart.wedge_count:
        findings.append(f"wedge elements are forbidden ({chart.wedge_count})")
    return findings


def _signature(path: Path) -> tuple[object, ...] | None:
    parser = _parse(path)
    if len(parser.charts) != 1:
        return None
    chart = parser.charts[0]
    attrs = chart.attrs
    values = [_float(attrs.get(key)) for key in (
        "data-polar-cx",
        "data-polar-cy",
        "data-polar-radius",
        "data-polar-min",
        "data-polar-max",
        "data-polar-start-angle",
    )]
    clockwise = attrs.get("data-polar-clockwise", "").casefold() == "true"
    if any(not isfinite(value) for value in values):
        return None
    cx, cy, radius, minimum, maximum, start_angle = values
    return (
        cx,
        cy,
        radius,
        minimum,
        maximum,
        start_angle,
        clockwise,
        tuple(
            (category.index, category.name, category.value, category.focal)
            for category in sorted(chart.categories, key=lambda category: category.index)
        ),
    )


def _check_variants_with_paths(paths: Sequence[Path]) -> list[tuple[Path, str]]:
    """Return variant findings while retaining the file that owns each finding."""

    findings: list[tuple[Path, str]] = []
    signatures: list[tuple[object, ...] | None] = []
    for path in paths:
        if not path.exists():
            findings.append((path, f"file not found: {path}"))
            signatures.append(None)
            continue
        findings.extend((path, finding) for finding in check(path))
        signatures.append(_signature(path))
    present = [signature for signature in signatures if signature is not None]
    if len(present) >= 2 and any(signature != present[0] for signature in present[1:]):
        findings.append((paths[0], "variant data drift"))
    return findings


def check_variants(paths: Sequence[Path]) -> list[str]:
    """Check each variant and ensure all variants carry one shared dataset."""

    return [finding for _path, finding in _check_variants_with_paths(paths)]


def main(argv: Sequence[str] | None = None) -> int:
    paths = [Path(argument) for argument in (argv if argv is not None else sys.argv[1:])]
    if not paths:
        paths = list(DEFAULT_PATHS)
    findings = _check_variants_with_paths(paths)
    if findings:
        for path, finding in findings:
            print(f"FAIL {path}: {finding}")
        return 1
    for path in paths:
        print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
