#!/usr/bin/env python3
"""Verify the machine-readable contract for quantitative polar diagrams."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from math import cos, hypot, isfinite, pi, radians, sin
from pathlib import Path
import re
import sys
from typing import Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills" / "diagram-design" / "assets"
DEFAULT_PATHS = (
    ASSET_DIR / "example-polar.html",
    ASSET_DIR / "example-polar-dark.html",
    ASSET_DIR / "example-polar-full.html",
)
TOLERANCE = 0.75
ALLOWED_CHART_ELEMENTS = frozenset({"svg", "g", "line", "circle", "rect", "text", "title", "desc"})
VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})
CSS_GEOMETRY_PROPERTY = re.compile(
    r"(?:^|[;{])\s*(?:fill|stroke-width|transform|filter|clip-path|mask|"
    r"marker-(?:start|mid|end)|r|cx|cy|x|y|x1|y1|x2|y2|rx|ry|d|points)\s*:",
    re.IGNORECASE,
)
CSS_STYLESHEET_LOADING = re.compile(r"@import\b|url\s*\(", re.IGNORECASE)
REFERENCE_ATTRIBUTES = frozenset({
    "href", "xlink:href", "filter", "clip-path", "mask",
    "marker-start", "marker-mid", "marker-end",
})
SAFE_HTML_STYLE_TARGETS = frozenset({
    "html", "body", "div", "main", "header", "footer", "section", "article",
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
})
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CSS_COMBINATOR = re.compile(r"\s+|[>+~]")


@dataclass
class ValueLabel:
    attrs: dict[str, str]
    text: str


@dataclass
class Category:
    name: str
    index: int
    value: float
    focal: bool
    rays: list[dict[str, str]]
    markers: list[dict[str, str]]
    value_labels: list[ValueLabel]


@dataclass
class Chart:
    attrs: dict[str, str]
    categories: list[Category]
    tag: str
    backgrounds: list[dict[str, str]]
    rings: list[dict[str, str]]
    spokes: list[dict[str, str]]
    rules: list[dict[str, str]]
    unsupported_elements: list[str]
    duplicate_attributes: list[tuple[str, str]]
    url_attributes: list[str]
    unmarked_circle_count: int
    unmarked_line_count: int
    unmarked_rect_count: int
    transformed_element_count: int
    css_geometry_count: int
    inline_style_count: int
    class_attribute_count: int


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


def _geometry_tolerance(radius: float | None) -> float:
    if radius is None or not isfinite(radius) or radius <= 0:
        return TOLERANCE
    return min(TOLERANCE, radius / 20)


def _contains_geometry_css(css: str) -> bool:
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return "\\" in without_comments or CSS_GEOMETRY_PROPERTY.search(without_comments) is not None


def _contains_stylesheet_loading(css: str) -> bool:
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    return CSS_STYLESHEET_LOADING.search(without_comments) is not None


def _canonical_svg_layout(declarations: str) -> bool:
    parsed: dict[str, str] = {}
    for declaration in declarations.split(";"):
        if not declaration.strip():
            continue
        if ":" not in declaration:
            return False
        name, value = declaration.split(":", 1)
        key = name.strip().casefold()
        if key in parsed:
            return False
        parsed[key] = value.strip().casefold()
    return parsed == {"width": "100%", "min-width": "900px", "display": "block"}


def _selector_can_target_chart(selector: str) -> bool:
    selector = selector.strip()
    if not selector or "[" in selector or "#" in selector or "\\" in selector:
        return True
    if selector == ":root":
        return False
    target = CSS_COMBINATOR.split(selector)[-1]
    target = target.split(":", 1)[0]
    if target.startswith("."):
        return False
    return target.casefold() not in SAFE_HTML_STYLE_TARGETS


def _stylesheet_can_target_chart(css: str) -> bool:
    without_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    if "\\" in without_comments:
        return True
    for prelude, declarations in CSS_RULE.findall(without_comments):
        prelude = prelude.strip()
        if prelude.startswith("@"):
            continue
        for selector in prelude.split(","):
            if selector.strip() == "svg" and _canonical_svg_layout(declarations):
                continue
            if _selector_can_target_chart(selector):
                return True
    return False


def _allowed_stylesheet(href: str) -> bool:
    parsed = urlsplit(href.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname == "fonts.googleapis.com"
        and parsed.path == "/css2"
    )


def _style_property(attrs: dict[str, str], property_name: str) -> str | None:
    result: str | None = None
    for declaration in attrs.get("style", "").split(";"):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        if name.strip().casefold() == property_name:
            result = raw_value.split("!", 1)[0].strip().casefold()
    return result


def _presentation_property(attrs: dict[str, str], property_name: str) -> str:
    style_value = _style_property(attrs, property_name)
    if style_value is not None:
        return style_value
    return attrs.get(property_name, "").strip().casefold()


class PolarParser(HTMLParser):
    """Capture charts and the geometry-bearing descendants of each category."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.charts: list[Chart] = []
        self.parse_findings: list[str] = []
        self.style_blocks: list[str] = []
        self.stylesheet_urls: list[str] = []
        self._stack: list[str] = []
        self._style_stack: list[tuple[int, int]] = []
        self._chart_depth: int | None = None
        self._chart: Chart | None = None
        self._category_stack: list[tuple[int, Category]] = []
        self._value_label_stack: list[tuple[int, ValueLabel]] = []

    def _in_chart(self) -> bool:
        return self._chart is not None and self._chart_depth is not None

    def _current_category(self) -> Category | None:
        if not self._category_stack:
            return None
        return self._category_stack[-1][1]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        data: dict[str, str] = {}
        duplicate_attributes: list[str] = []
        for raw_key, raw_value in attrs:
            key = raw_key.casefold()
            if key in data:
                duplicate_attributes.append(key)
            else:
                data[key] = raw_value or ""
        depth = len(self._stack)

        if tag == "style":
            self.style_blocks.append("")
            self._style_stack.append((depth, len(self.style_blocks) - 1))
        if tag == "link" and "stylesheet" in data.get("rel", "").casefold().split():
            self.stylesheet_urls.append(data.get("href", ""))

        if "data-polar-chart" in data:
            chart = Chart(
                attrs=dict(data),
                categories=[],
                tag=tag,
                backgrounds=[],
                rings=[],
                spokes=[],
                rules=[],
                unsupported_elements=[],
                duplicate_attributes=[],
                url_attributes=[],
                unmarked_circle_count=0,
                unmarked_line_count=0,
                unmarked_rect_count=0,
                transformed_element_count=0,
                css_geometry_count=0,
                inline_style_count=0,
                class_attribute_count=0,
            )
            chart.duplicate_attributes.extend((tag, key) for key in duplicate_attributes)
            self.charts.append(chart)
            if self._chart is None:
                self._chart = chart
                self._chart_depth = depth

        if self._in_chart():
            assert self._chart is not None
            assert self._chart_depth is not None
            is_chart_root = depth == self._chart_depth
            if not is_chart_root:
                self._chart.duplicate_attributes.extend(
                    (tag, key) for key in duplicate_attributes
                )
            if tag not in ALLOWED_CHART_ELEMENTS or (tag == "svg" and not is_chart_root):
                self._chart.unsupported_elements.append(tag)
            if "transform" in data or _style_property(data, "transform") is not None:
                self._chart.transformed_element_count += 1
            if _contains_geometry_css(data.get("style", "")):
                self._chart.css_geometry_count += 1
            if "style" in data:
                self._chart.inline_style_count += 1
            if "class" in data:
                self._chart.class_attribute_count += 1
            for key, value in data.items():
                normalized_value = value.strip().casefold()
                if key in REFERENCE_ATTRIBUTES and normalized_value not in {"", "none"}:
                    self._chart.url_attributes.append(key)
                elif key in {"fill", "stroke"} and "url(" in normalized_value:
                    self._chart.url_attributes.append(key)
            if tag == "g" and "data-polar-category" in data:
                category = Category(
                    name=data.get("data-polar-category", ""),
                    index=_int(data.get("data-polar-index")),
                    value=_float(data.get("data-polar-value")),
                    focal=data.get("data-polar-focal", "").casefold() == "true",
                    rays=[],
                    markers=[],
                    value_labels=[],
                )
                self._chart.categories.append(category)
                self._category_stack.append((depth, category))
            current = self._current_category()
            if current is not None:
                if tag == "text" and "data-polar-value-label" in data:
                    label = ValueLabel(attrs=data, text="")
                    current.value_labels.append(label)
                    self._value_label_stack.append((depth, label))
            if tag == "line":
                is_ray = "data-polar-ray" in data
                is_spoke = "data-polar-spoke" in data
                is_rule = "data-polar-rule" in data
                if is_ray and not is_spoke and not is_rule and current is not None:
                    current.rays.append(data)
                elif is_spoke and not is_ray and not is_rule:
                    self._chart.spokes.append(data)
                elif is_rule and not is_ray and not is_spoke:
                    self._chart.rules.append(data)
                else:
                    self._chart.unmarked_line_count += 1
            elif tag == "circle":
                is_marker = "data-polar-marker" in data
                is_ring = "data-polar-ring" in data
                if is_marker and not is_ring and current is not None:
                    current.markers.append(data)
                elif is_ring and not is_marker:
                    self._chart.rings.append(data)
                else:
                    self._chart.unmarked_circle_count += 1
            elif tag == "rect":
                if "data-polar-background" in data:
                    self._chart.backgrounds.append(data)
                else:
                    self._chart.unmarked_rect_count += 1

        if tag not in VOID_ELEMENTS:
            self._stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self._style_stack:
            style_index = self._style_stack[-1][1]
            self.style_blocks[style_index] += data
        if self._value_label_stack:
            self._value_label_stack[-1][1].text += data

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in VOID_ELEMENTS:
            return
        if not self._stack or self._stack[-1] != tag:
            if self._in_chart():
                self.parse_findings.append(f"mismatched closing tag </{tag}>")
            return
        self._stack.pop()
        depth = len(self._stack)

        while self._style_stack and self._style_stack[-1][0] >= depth:
            self._style_stack.pop()
        while self._value_label_stack and self._value_label_stack[-1][0] >= depth:
            self._value_label_stack.pop()
        while self._category_stack and self._category_stack[-1][0] >= depth:
            self._category_stack.pop()
        if self._chart_depth is not None and depth <= self._chart_depth:
            self._chart = None
            self._chart_depth = None
            self._category_stack.clear()
            self._value_label_stack.clear()

    def close(self) -> None:
        super().close()
        if self._chart is not None:
            self.parse_findings.append("unterminated data-polar-chart element")


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


def _explicitly_hidden(attrs: dict[str, str]) -> bool:
    if "hidden" in attrs or attrs.get("aria-hidden", "").strip().casefold() == "true":
        return True
    if attrs.get("display", "").strip().casefold() == "none":
        return True
    if attrs.get("visibility", "").strip().casefold() == "hidden":
        return True
    if "opacity" in attrs and _float(attrs["opacity"].strip()) == 0:
        return True
    for declaration in attrs.get("style", "").split(";"):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        name = name.strip().casefold()
        value = raw_value.split("!", 1)[0].strip().casefold()
        if (name == "display" and value == "none") or (
            name == "visibility" and value == "hidden"
        ):
            return True
        if name == "opacity" and _float(value) == 0:
            return True
    return False


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
    findings.extend(parser.parse_findings)
    if any(_contains_stylesheet_loading(css) for css in parser.style_blocks):
        findings.append("CSS stylesheet loading is forbidden in polar documents")
    if any(_contains_geometry_css(css) for css in parser.style_blocks):
        findings.append("CSS geometry properties are forbidden in polar documents")
    if any(_stylesheet_can_target_chart(css) for css in parser.style_blocks):
        findings.append("CSS selectors must not target data-polar-chart")
    if any(not _allowed_stylesheet(href) for href in parser.stylesheet_urls):
        findings.append("external stylesheets are forbidden in polar documents")
    for tag, key in chart.duplicate_attributes:
        findings.append(f"duplicate attribute {key} on <{tag}>")
    for key in sorted(set(chart.url_attributes)):
        findings.append(f"URL-valued SVG attribute {key} is forbidden")
    if chart.css_geometry_count:
        findings.append(
            "inline CSS geometry properties are forbidden inside data-polar-chart "
            f"({chart.css_geometry_count})"
        )
    if chart.inline_style_count:
        findings.append(
            "inline styles are forbidden inside data-polar-chart "
            f"({chart.inline_style_count})"
        )
    if chart.class_attribute_count:
        findings.append(
            "class attributes are forbidden inside data-polar-chart "
            f"({chart.class_attribute_count})"
        )
    if chart.tag != "svg":
        findings.append("data-polar-chart must be an SVG element")
    for tag in sorted(set(chart.unsupported_elements)):
        count = chart.unsupported_elements.count(tag)
        findings.append(
            f"unsupported SVG element <{tag}> can create forbidden wedge or area encoding ({count})"
        )
    if chart.unmarked_circle_count:
        findings.append(
            "circle must be a ring or category marker "
            f"({chart.unmarked_circle_count} unmarked)"
        )
    if chart.unmarked_line_count:
        findings.append(
            "line must be a spoke, category ray, or rule "
            f"({chart.unmarked_line_count} unmarked)"
        )
    if chart.unmarked_rect_count:
        findings.append(
            f"rect must be the chart background ({chart.unmarked_rect_count} unmarked)"
        )
    if chart.transformed_element_count:
        findings.append(
            "transforms are forbidden inside data-polar-chart "
            f"({chart.transformed_element_count})"
        )
    if len(chart.backgrounds) > 1:
        findings.append(f"chart background count is {len(chart.backgrounds)}, expected at most one")
    for background in chart.backgrounds:
        x = _float(background.get("x", "0"))
        y = _float(background.get("y", "0"))
        if (
            background.get("width", "").strip() != "100%"
            or background.get("height", "").strip() != "100%"
            or x != 0
            or y != 0
        ):
            findings.append("background must cover the full chart")
    if len(chart.rules) > 1:
        findings.append(
            f"chart rule count is {len(chart.rules)}, expected at most one"
        )
    for rule in chart.rules:
        stroke_width = _float(_presentation_property(rule, "stroke-width"))
        if stroke_width != 0.8:
            findings.append(
                f"rule stroke-width {stroke_width:g} does not match expected 0.8"
            )
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
    geometry_tolerance = _geometry_tolerance(radius if isinstance(radius, float) else None)

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

    if len(chart.rings) != 5:
        findings.append(f"grid-ring count is {len(chart.rings)}, expected five")
    for ring in chart.rings:
        ring_radius = _float(ring.get("r"))
        if _presentation_property(ring, "fill") != "none":
            findings.append("ring must use fill none")
        ring_center = _point(ring, "cx", "cy")
        if (
            ring_center is None
            or not isinstance(cx, float)
            or not isinstance(cy, float)
            or hypot(ring_center[0] - cx, ring_center[1] - cy) > geometry_tolerance
        ):
            findings.append("ring center must match the polar chart center")
        if isinstance(radius, float) and radius > 0 and isfinite(ring_radius):
            expected_radii = [radius * step / 5 for step in range(1, 6)]
            if min(abs(ring_radius - expected) for expected in expected_radii) > geometry_tolerance:
                findings.append(
                    f"ring radius {ring_radius:g} is not a 20% scale interval"
                )
        elif not isfinite(ring_radius):
            findings.append("ring radius must be finite numeric")
        stroke_width = _float(_presentation_property(ring, "stroke-width"))
        if stroke_width != 0.8:
            findings.append(
                f"ring stroke-width {stroke_width:g} does not match expected 0.8"
            )
    if isinstance(radius, float) and radius > 0 and len(chart.rings) == 5:
        observed_radii = sorted(_float(ring.get("r")) for ring in chart.rings)
        expected_radii = [radius * step / 5 for step in range(1, 6)]
        if any(
            not isfinite(observed) or abs(observed - expected) > geometry_tolerance
            for observed, expected in zip(observed_radii, expected_radii)
        ):
            findings.append("ring radii must cover 20% through 100% intervals")

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
        and radius > 0
        and maximum > 0
        and count > 0
    )
    spoke_indices = [_int(spoke.get("data-polar-index")) for spoke in chart.spokes]
    if sorted(spoke_indices) != list(range(count)):
        findings.append(f"spoke indices must be contiguous 0..{count - 1}")
    for spoke, spoke_index in zip(chart.spokes, spoke_indices):
        stroke_width = _float(_presentation_property(spoke, "stroke-width"))
        if stroke_width != 0.8:
            findings.append(
                f"spoke {spoke_index} stroke-width {stroke_width:g} "
                "does not match expected 0.8"
            )
        if not geometry_ready or not 0 <= spoke_index < count:
            continue
        assert isinstance(cx, float)
        assert isinstance(cy, float)
        assert isinstance(radius, float)
        assert isinstance(start_angle, float)
        assert isinstance(clockwise, bool)
        expected_angle = radians(start_angle) + (1 if clockwise else -1) * 2 * pi * spoke_index / count
        expected_x = cx + radius * cos(expected_angle)
        expected_y = cy + radius * sin(expected_angle)
        spoke_start = _point(spoke, "x1", "y1")
        spoke_end = _point(spoke, "x2", "y2")
        if spoke_start is None or hypot(spoke_start[0] - cx, spoke_start[1] - cy) > geometry_tolerance:
            findings.append(f"spoke {spoke_index} must start at chart center")
        if spoke_end is None or hypot(spoke_end[0] - expected_x, spoke_end[1] - expected_y) > geometry_tolerance:
            findings.append(f"spoke {spoke_index} endpoint outside tolerance")
    for category in chart.categories:
        value = category.value
        ray = category.rays[0] if len(category.rays) == 1 else None
        if ray is not None:
            ray_stroke_width = _float(_presentation_property(ray, "stroke-width"))
            expected_ray_stroke_width = 2.4 if category.focal else 2.0
            if ray_stroke_width != expected_ray_stroke_width:
                findings.append(
                    f"category {category.name!r} ray stroke-width {ray_stroke_width:g} "
                    f"does not match expected {expected_ray_stroke_width:g}"
                )
        marker = category.markers[0] if len(category.markers) == 1 else None
        if marker is not None:
            marker_radius = _float(marker.get("r"))
            expected_marker_radius = 5.0 if category.focal else 4.0
            if marker_radius != expected_marker_radius:
                findings.append(
                    f"category {category.name!r} marker radius {marker_radius:g} "
                    f"does not match expected {expected_marker_radius:g}"
                )
            marker_stroke_width = _float(_presentation_property(marker, "stroke-width"))
            if marker_stroke_width != 1.2:
                findings.append(
                    f"category {category.name!r} marker stroke-width {marker_stroke_width:g} "
                    "does not match expected 1.2"
                )
        if len(category.value_labels) != 1:
            findings.append(
                f"category {category.name!r} value-label count is {len(category.value_labels)}, expected one"
            )
        else:
            label = category.value_labels[0]
            label_value = _float(label.text.strip())
            if _explicitly_hidden(label.attrs):
                findings.append(f"category {category.name!r} value label is explicitly hidden")
            if not isfinite(label_value):
                findings.append(f"category {category.name!r} value label must be finite numeric")
            elif isfinite(value) and label_value != value:
                findings.append(
                    f"category {category.name!r} value label {label_value:g} "
                    f"does not match data-polar-value {value:g}"
                )
        if not isfinite(value):
            findings.append(f"non-numeric category value for {category.name!r}")
            continue
        if isinstance(minimum, float) and isinstance(maximum, float) and not minimum <= value <= maximum:
            findings.append(f"value {value:g} outside {minimum:g}..{maximum:g}")
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
        assert ray is not None
        ray_start = _point(ray, "x1", "y1")
        ray_end = _point(ray, "x2", "y2")
        if ray_start is None:
            findings.append(f"ray geometry non-numeric for {category.name!r}")
        elif hypot(ray_start[0] - cx, ray_start[1] - cy) > geometry_tolerance:
            findings.append(f"ray start not at center for {category.name!r}")
        if ray_end is None:
            findings.append(f"ray endpoint non-numeric for {category.name!r}")
        elif hypot(ray_end[0] - expected_x, ray_end[1] - expected_y) > geometry_tolerance:
            findings.append(
                f"linear endpoint outside tolerance for {category.name!r}: "
                f"expected ({expected_x:g},{expected_y:g}), got ({ray_end[0]:g},{ray_end[1]:g})"
            )
        marker_end = _point(marker, "cx", "cy") if marker is not None else None
        if marker_end is None:
            if marker is not None:
                findings.append(f"marker endpoint non-numeric for {category.name!r}")
        elif hypot(marker_end[0] - expected_x, marker_end[1] - expected_y) > geometry_tolerance:
            findings.append(f"marker endpoint outside tolerance for {category.name!r}")

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
