#!/usr/bin/env python3
"""Verify that a histogram's drawn geometry matches the values it declares.

A histogram makes one claim: **height is proportional to count because every
bin spans the same interval**. Every way of breaking that claim renders
perfectly - the figure looks like a distribution either way, and the lie is in
the geometry. `lint-skin.py` reads colors and fonts, `verify-geometry.py`
reads label masks, and neither compares a bar against the count printed above
it or a bin edge against the numeral printed below it.

Seven invariants:

1. EQUAL BINS - every bin's declared interval has the same width, and every
   bar the same pixel width. Widening one bin raises its bar without a single
   observation moving; it is the histogram's signature lie and the reason the
   reference forbids unequal bins outright rather than offering the
   density-normalized variant.

2. TILED EDGES - bin k ends where bin k+1 starts, in the declared values and
   in the pixels. An omitted interior bin does not read as "empty"; it reads
   as a narrower distribution than the data has. An empty bin ships as a
   zero-height bar, still declared, still counted.

3. ZERO BASELINE, ONE LINEAR SCALE - every bar stands on one shared baseline,
   the `0` tick sits on it, and a single px-per-count factor fits every bar
   AND every count tick. A histogram reads mass by area; a truncated or bent
   count axis subtracts the same lie from every bin.

4. N EQUALS THE SUM - the printed n must equal the sum of the declared bin
   counts. A histogram whose bins sum below its stated n has dropped data,
   usually the outliers, which are usually the story.

5. HONEST MARKER - an optional reference marker must sit where the x-scale
   puts its declared value, and a marker claiming to be the *mean* must lie
   within half a bin of the mean of the binned data. A "mean" placed where it
   looks balanced is annotation-by-eye, the same defect as slopegraph jitter.

6. UNTRANSFORMED GEOMETRY - coordinates are read as raw attributes, so a
   `transform` on verified geometry, on a bound label, or on any group moves
   the rendered mark away from the number that was verified. Transforms are
   rejected rather than resolved.

7. FAIL CLOSED - a file that presents as a histogram but yields fewer than
   three parseable bins is a finding, never a pass, and `--all` must find the
   shipped histogram examples themselves: a scope heuristic that quietly
   stops matching them would otherwise turn this gate green by making it
   blind (the fail-open class #127 closed for treemap).

The reference is part of the contract: the bin-count budget and the marker
weights are parsed out of `references/type-bar.md` and enforced here, the same
coupling `verify-dumbbell.py` uses, so the prose and the thresholds cannot
drift apart. A reference this cannot parse is a finding.

WHAT THIS DOES NOT CHECK, deliberately:

- **Absolute truth.** Every check is internal consistency. If every declared
  count is wrong by the same factor, the figure is self-consistent and passes;
  nothing in the file could reveal otherwise.
- **Bin-edge label completeness.** The reference allows printing every second
  edge when numerals collide, so presence is not enforced - but every edge
  label that IS printed must sit at its declared value.

Usage:
    python3 scripts/verify-histogram.py file.html [file2.html ...]
    python3 scripts/verify-histogram.py --all
    python3 scripts/verify-histogram.py --reference path/to/type-bar.md file.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import html
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"
REFERENCE = ROOT / "skills/diagram-design/references/type-bar.md"

# The three shipped histogram examples --all must find. A rename that breaks
# this list is a conscious edit here, never a silent narrowing of scope.
REQUIRED_SHIPPED = (
    "example-histogram.html",
    "example-histogram-dark.html",
    "example-histogram-full.html",
)

RECT_RE = re.compile(r"<rect\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
GROUP_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
# `transform:` but not `text-transform:` - the editorial template uses the latter.
CSS_TRANSFORM_RE = re.compile(r"(?<![\w-])transform\s*:", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
NUMBER_RE = re.compile(
    r"[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?"
)
DIGIT_RE = re.compile(r"\d")
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_BIN_RE = re.compile(r"\bdata-bin-start\s*=", re.IGNORECASE)
RGBA_RE = re.compile(r"rgba\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(0?\.\d+|1(?:\.0+)?)\s*\)")

# Reference coupling: the tokens this checker holds the examples to.
REF_BIN_BOUNDS_RE = re.compile(r"\*\*Bins:\s*(\d+)\s*[-–]\s*(\d+)")
REF_MARKER_WEIGHTS_RE = re.compile(r"ink at (\d+)% on light / (\d+)% on dark")

GEOM_TOLERANCE = 1.0     # px - coordinates ship rounded to two decimals
TICK_TOLERANCE = 3.0     # px - tick text baselines carry a designed +4 offset
TICK_OFFSET = 4.0        # px - text baseline below its gridline, house rhythm
VALUE_TOLERANCE = 0.001  # printed label vs declared attribute
MIN_BINS = 3             # below this nothing can be called a distribution

LIGHT_INK = (45, 49, 66)
DARK_INK = (245, 245, 245)


class Bin:
    __slots__ = ("start", "end", "count", "x", "y", "width", "height", "line")

    def __init__(self, start, end, count, x, y, width, height, line):
        self.start, self.end, self.count = start, end, count
        self.x, self.y, self.width, self.height = x, y, width, height
        self.line = line


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    """Comments out, length and line numbers preserved."""
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def attrs_of(raw: str) -> dict:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw)}


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value):
    """A finite float from a declared attribute, or None."""
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def printed_number(body: str):
    """(value, reason) for a label's visible text - exactly one complete token."""
    text = plain(body)
    match = NUMBER_RE.search(text)
    if match is None:
        return None, "prints no number"
    outside = text[:match.start()] + text[match.end():]
    if DIGIT_RE.search(outside):
        return None, "prints more than one numeric token"
    value = number(match.group())
    if value is None:
        return None, "prints a number this checker cannot read"
    return value, None


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def named_text(source: str) -> str:
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_histogram(path: Path, source: str) -> bool:
    """Does this file present itself as a histogram? Deliberately generous:
    anything that claims the type in its name, its accessible description, or
    its markup is held to the contract even if nothing parses - that
    combination is the fail-closed case, not a pass."""
    if path.name.startswith("example-histogram"):
        return True
    if DECLARES_BIN_RE.search(source):
        return True
    return "histogram" in named_text(source)


def reference_tokens(reference: Path, findings: list) -> dict:
    """The budget and weights the reference documents, or findings if it no
    longer says what this checker enforces - the coupling that keeps prose and
    thresholds from drifting apart."""
    tokens = {}
    try:
        text = reference.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        findings.append("%s: unreadable reference (%s); the histogram contract "
                        "has no source of truth" % (reference, error))
        return tokens
    bounds = REF_BIN_BOUNDS_RE.search(text)
    if bounds:
        tokens["bins_min"], tokens["bins_max"] = int(bounds.group(1)), int(bounds.group(2))
    else:
        findings.append("%s: cannot parse the bin-count budget (\"**Bins: N-M\"); "
                        "prose and checker have drifted apart" % reference)
    weights = REF_MARKER_WEIGHTS_RE.search(text)
    if weights:
        tokens["marker_light"] = int(weights.group(1)) / 100.0
        tokens["marker_dark"] = int(weights.group(2)) / 100.0
    else:
        findings.append("%s: cannot parse the marker weights (\"ink at N%% on light / "
                        "M%% on dark\"); prose and checker have drifted apart" % reference)
    return tokens


def parse_bins(source: str, findings: list, name: str) -> list:
    bins = []
    for match in RECT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-bin-start" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        values = {}
        broken = False
        for key in ("data-bin-start", "data-bin-end", "data-count", "x", "y", "width", "height"):
            values[key] = number(attrs.get(key))
            if values[key] is None:
                findings.append("%s: bin rect is missing or mis-declares %s" % (where, key))
                broken = True
        if broken:
            continue
        if values["data-count"] < 0:
            findings.append("%s: bin declares a negative count" % where)
            continue
        bins.append(Bin(values["data-bin-start"], values["data-bin-end"], values["data-count"],
                        values["x"], values["y"], values["width"], values["height"],
                        line_of(source, match.start())))
    bins.sort(key=lambda b: b.start)
    return bins


def check_transforms(source: str, findings: list, name: str) -> None:
    """Reject transforms on groups, on verified geometry, and on bound labels.
    A plain caption <text> may rotate; nothing verified may."""
    for match in GROUP_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "transform" in attrs:
            findings.append("%s:%d: transform on a group can move any verified "
                            "geometry it encloses; bake the offset into coordinates"
                            % (name, line_of(source, match.start())))
    for regex in (RECT_RE, LINE_RE):
        for match in regex.finditer(source):
            attrs = attrs_of(match.group("attrs"))
            if "transform" in attrs and any(k.startswith("data-") for k in attrs):
                findings.append("%s:%d: transform on verified geometry moves the "
                                "rendered mark away from the number that was verified"
                                % (name, line_of(source, match.start())))
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "transform" in attrs and any(k.startswith("data-") for k in attrs):
            findings.append("%s:%d: transform on a bound label moves the printed "
                            "number away from where it was verified"
                            % (name, line_of(source, match.start())))
    for style in STYLE_RE.finditer(source):
        if CSS_TRANSFORM_RE.search(style.group("body")):
            findings.append("%s:%d: CSS transform can move verified geometry "
                            "invisibly to an attribute reader"
                            % (name, line_of(source, style.start())))


def check_bins(bins: list, findings: list, name: str, tokens: dict) -> dict:
    """Equal widths, tiled edges, shared baseline, one linear count scale.
    Returns the fitted scales for the tick, edge and marker checks."""
    fit = {}
    for b in bins:
        if b.end <= b.start:
            findings.append("%s:%d: bin %g-%g is empty or reversed"
                            % (name, line_of_bin(b, name), b.start, b.end))
            return fit

    width_val = bins[0].end - bins[0].start
    for b in bins:
        if abs((b.end - b.start) - width_val) > VALUE_TOLERANCE:
            findings.append("%s:%d: bin %g-%g spans %g while the first bin spans %g - "
                            "unequal bins make height lie about density"
                            % (name, line_of_bin(b, name), b.start, b.end,
                               b.end - b.start, width_val))
    for prev, nxt in zip(bins, bins[1:]):
        if abs(prev.end - nxt.start) > VALUE_TOLERANCE:
            findings.append("%s:%d: declared bins do not tile - %g-%g is followed by "
                            "%g-%g" % (name, line_of_bin(nxt, name), prev.start, prev.end,
                                       nxt.start, nxt.end))
        if abs((prev.x + prev.width) - nxt.x) > GEOM_TOLERANCE:
            findings.append("%s:%d: drawn bars leave a %.2fpx gap or overlap at the "
                            "%g edge - contiguity is the variant's grammar"
                            % (name, line_of_bin(nxt, name),
                               nxt.x - (prev.x + prev.width), nxt.start))

    width_px = median([b.width for b in bins])
    for b in bins:
        if abs(b.width - width_px) > GEOM_TOLERANCE:
            findings.append("%s:%d: bar for bin %g-%g is %.2fpx wide against a "
                            "%.2fpx norm - equal intervals must draw equal widths"
                            % (name, line_of_bin(b, name), b.start, b.end,
                               b.width, width_px))

    baseline = median([b.y + b.height for b in bins])
    for b in bins:
        if abs((b.y + b.height) - baseline) > GEOM_TOLERANCE:
            findings.append("%s:%d: bar for bin %g-%g stands on y=%.2f, off the "
                            "shared baseline y=%.2f" % (name, line_of_bin(b, name),
                                                        b.start, b.end,
                                                        b.y + b.height, baseline))

    scales = [b.height / b.count for b in bins if b.count > 0]
    if not scales:
        findings.append("%s: every bin declares count 0; nothing to scale" % name)
        return fit
    s = median(scales)
    if s <= 0:
        findings.append("%s: count scale is not positive" % name)
        return fit
    for b in bins:
        expected = b.count * s
        if abs(b.height - expected) > GEOM_TOLERANCE:
            findings.append("%s:%d: bar for bin %g-%g is %.2fpx tall but its count "
                            "%g puts it at %.2fpx on the shared scale - height must "
                            "be proportional to count"
                            % (name, line_of_bin(b, name), b.start, b.end,
                               b.height, b.count, expected))

    bounds_min = tokens.get("bins_min")
    bounds_max = tokens.get("bins_max")
    if bounds_min is not None and not (bounds_min <= len(bins) <= bounds_max):
        findings.append("%s: %d bins against the reference's budget of %d-%d"
                        % (name, len(bins), bounds_min, bounds_max))

    span = bins[-1].end - bins[0].start
    fit.update(baseline=baseline, count_scale=s,
               x0=bins[0].x, v0=bins[0].start,
               px_per_value=(bins[-1].x + bins[-1].width - bins[0].x) / span)
    return fit


def line_of_bin(b: Bin, name: str) -> int:
    return b.line


def check_ticks(source: str, findings: list, name: str, fit: dict) -> None:
    if not fit:
        return
    baseline, s = fit["baseline"], fit["count_scale"]
    ticks = []
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-count-tick" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        declared = number(attrs.get("data-count-tick"))
        y = number(attrs.get("y"))
        if declared is None or y is None:
            findings.append("%s: count tick with unreadable value or position" % where)
            continue
        printed, reason = printed_number(match.group("body"))
        if reason:
            findings.append("%s: count tick %s" % (where, reason))
        elif abs(printed - declared) > VALUE_TOLERANCE:
            findings.append("%s: count tick prints %g but declares %g"
                            % (where, printed, declared))
        expected = baseline - declared * s + TICK_OFFSET
        if abs(y - expected) > TICK_TOLERANCE:
            findings.append("%s: count tick %g sits at y=%.2f, but the one linear "
                            "scale puts it at y=%.2f - a bent or truncated count "
                            "axis" % (where, declared, y, expected))
        ticks.append(declared)
    if not ticks:
        findings.append("%s: no bound count ticks (data-count-tick) - the count "
                        "axis cannot be verified" % name)
        return
    if min(ticks) != 0:
        findings.append("%s: no 0 tick - the histogram baseline must be zero, "
                        "printed" % name)


def check_edges(source: str, findings: list, name: str, fit: dict) -> None:
    if not fit:
        return
    x0, v0, ppv = fit["x0"], fit["v0"], fit["px_per_value"]
    seen = 0
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-edge" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        declared = number(attrs.get("data-edge"))
        x = number(attrs.get("x"))
        if declared is None or x is None:
            findings.append("%s: edge tick with unreadable value or position" % where)
            continue
        printed, reason = printed_number(match.group("body"))
        if reason:
            findings.append("%s: edge tick %s" % (where, reason))
        elif abs(printed - declared) > VALUE_TOLERANCE:
            findings.append("%s: edge tick prints %g but declares %g"
                            % (where, printed, declared))
        expected = x0 + (declared - v0) * ppv
        if abs(x - expected) > GEOM_TOLERANCE:
            findings.append("%s: edge tick %g sits at x=%.2f but the value scale "
                            "puts it at x=%.2f - the numeral names a boundary it "
                            "is not on" % (where, declared, x, expected))
        seen += 1
    if seen < 2:
        findings.append("%s: fewer than two bound edge ticks (data-edge) - the "
                        "value axis cannot be verified" % name)


def check_counts(source: str, bins: list, findings: list, name: str) -> None:
    by_start = {b.start: b for b in bins}
    labelled = set()
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") != "count" or "data-bin-start" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        start = number(attrs.get("data-bin-start"))
        owner = by_start.get(start)
        if owner is None:
            findings.append("%s: count label names bin %s, which no rect declares"
                            % (where, attrs.get("data-bin-start")))
            continue
        labelled.add(start)
        printed, reason = printed_number(match.group("body"))
        if reason:
            findings.append("%s: count label %s" % (where, reason))
            continue
        if abs(printed - owner.count) > VALUE_TOLERANCE:
            findings.append("%s: count label prints %g but its bin declares %g"
                            % (where, printed, owner.count))
        x = number(attrs.get("x"))
        if x is not None and abs(x - (owner.x + owner.width / 2)) > GEOM_TOLERANCE:
            findings.append("%s: count label for bin %g-%g is centred at x=%.2f, "
                            "not over its bar at x=%.2f - a label over the wrong "
                            "bar renames both" % (where, owner.start, owner.end, x,
                                                  owner.x + owner.width / 2))
    for b in bins:
        if b.start not in labelled:
            findings.append("%s:%d: bin %g-%g has no count label - the label is "
                            "what separates a small count from none"
                            % (name, line_of_bin(b, name), b.start, b.end))


def check_n(source: str, bins: list, findings: list, name: str) -> None:
    total = sum(b.count for b in bins)
    stated = None
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") != "n":
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        declared = number(attrs.get("data-value"))
        printed, reason = printed_number(match.group("body"))
        if declared is None:
            findings.append("%s: n label declares no readable data-value" % where)
            continue
        if reason:
            findings.append("%s: n label %s" % (where, reason))
        elif abs(printed - declared) > VALUE_TOLERANCE:
            findings.append("%s: n label prints %g but declares %g"
                            % (where, printed, declared))
        stated = (where, declared)
    if stated is None:
        findings.append("%s: no printed n (data-role=\"n\") - a histogram that "
                        "does not state its n cannot be checked for dropped data"
                        % name)
        return
    where, declared = stated
    if abs(declared - total) > VALUE_TOLERANCE:
        findings.append("%s: n = %g but the bins sum to %g - data has been "
                        "silently dropped or invented" % (where, declared, total))


def check_marker(source: str, bins: list, findings: list, name: str,
                 fit: dict, tokens: dict) -> None:
    if not fit:
        return
    x0, v0, ppv = fit["x0"], fit["v0"], fit["px_per_value"]
    total = sum(b.count for b in bins)
    binned_mean = (sum(((b.start + b.end) / 2) * b.count for b in bins) / total
                   if total else None)
    bin_width = bins[0].end - bins[0].start if bins else 0
    markers = 0
    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-marker" not in attrs:
            continue
        markers += 1
        where = "%s:%d" % (name, line_of(source, match.start()))
        declared = number(attrs.get("data-value"))
        x1, x2 = number(attrs.get("x1")), number(attrs.get("x2"))
        if declared is None or x1 is None or x2 is None:
            findings.append("%s: marker with unreadable value or position" % where)
            continue
        if abs(x1 - x2) > VALUE_TOLERANCE:
            findings.append("%s: marker is not vertical; it marks a span, not a "
                            "value" % where)
        expected = x0 + (declared - v0) * ppv
        if abs(x1 - expected) > GEOM_TOLERANCE:
            findings.append("%s: marker declares %g but is drawn at x=%.2f, where "
                            "the scale says %.2f" % (where, declared, x1, expected))
        if attrs.get("data-marker") == "mean" and binned_mean is not None:
            if abs(declared - binned_mean) > bin_width / 2:
                findings.append("%s: marker claims to be the mean at %g, but the "
                                "binned data's mean is %.1f - more than half a bin "
                                "away, which is placement by eye"
                                % (where, declared, binned_mean))
        stroke = attrs.get("stroke", "")
        rgba = RGBA_RE.fullmatch(stroke.strip())
        if rgba is None:
            findings.append("%s: marker stroke %r is not the documented "
                            "ink-at-alpha treatment" % (where, stroke))
        else:
            r, g, b_, alpha = (int(rgba.group(1)), int(rgba.group(2)),
                               int(rgba.group(3)), float(rgba.group(4)))
            expected_alpha = None
            if (r, g, b_) == LIGHT_INK:
                expected_alpha = tokens.get("marker_light")
            elif (r, g, b_) == DARK_INK:
                expected_alpha = tokens.get("marker_dark")
            if expected_alpha is None:
                findings.append("%s: marker stroke %r is neither theme's ink"
                                % (where, stroke))
            elif abs(alpha - expected_alpha) > 0.005:
                findings.append("%s: marker alpha %.2f against the reference's "
                                "%.2f - prose and figure have drifted apart"
                                % (where, alpha, expected_alpha))
    if markers > 1:
        findings.append("%s: %d reference markers; the reference allows one - "
                        "more is an argument the cards should be making" % (name, markers))
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-marker-label" not in attrs:
            continue
        where = "%s:%d" % (name, line_of(source, match.start()))
        declared = number(attrs.get("data-value"))
        printed, reason = printed_number(match.group("body"))
        if declared is None:
            findings.append("%s: marker label declares no readable data-value" % where)
        elif reason:
            findings.append("%s: marker label %s" % (where, reason))
        elif abs(printed - declared) > VALUE_TOLERANCE:
            findings.append("%s: marker label prints %g but declares %g"
                            % (where, printed, declared))


def check_source(path: Path, raw: str, reference: Path) -> list:
    findings: list = []
    name = str(path)
    source = blank_comments(raw)
    tokens = reference_tokens(reference, findings)
    bins = parse_bins(source, findings, name)
    if len(bins) < MIN_BINS:
        findings.append("%s: presents as a histogram but declares %d parseable "
                        "bin(s); fewer than %d cannot be a distribution and is "
                        "reported, never passed" % (name, len(bins), MIN_BINS))
        return findings
    check_transforms(source, findings, name)
    fit = check_bins(bins, findings, name, tokens)
    check_ticks(source, findings, name, fit)
    check_edges(source, findings, name, fit)
    check_counts(source, bins, findings, name)
    check_n(source, bins, findings, name)
    check_marker(source, bins, findings, name, fit, tokens)
    return findings


def check(path: Path, reference: Path = REFERENCE) -> list:
    """Findings for one file on disk, or [] if it is not a histogram."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_histogram(path, raw):
        return []
    return check_source(path, raw, reference)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a histogram's geometry against the values it declares."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true",
                        help="check every shipped example that presents as a histogram")
    parser.add_argument("--reference", type=Path, default=REFERENCE,
                        help="type-bar.md to read the documented budget and weights from")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    targets = (sorted(ASSET_DIR.glob("example-*.html")) if args.all
               else [Path(p) for p in args.paths])
    findings: list = []
    checked: list = []
    skipped = 0
    for path in targets:
        if not path.is_file():
            print("error: %s is not a readable file" % path, file=sys.stderr)
            return 2
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print("error: cannot read %s: %s" % (path, error), file=sys.stderr)
            return 2
        if not looks_like_histogram(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw, args.reference))
        checked.append(path.name)

    if args.all:
        # Scope assertion: the shipped examples themselves must be in the
        # checked set. A heuristic that stops matching them would otherwise
        # green this gate by blinding it (the treemap fail-open class).
        for required in REQUIRED_SHIPPED:
            if required not in checked:
                findings.append("--all did not verify %s; either it was removed "
                                "without editing REQUIRED_SHIPPED in this script, "
                                "or scope detection broke" % required)

    seen = set()
    findings = [f for f in findings if not (f in seen or seen.add(f))]
    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d histogram finding(s) across %d file(s).%s"
              % (len(findings), len(checked), tail))
        return 1
    if not checked:
        print("OK histogram: no histogram found to check%s" % tail)
        return 0
    print("OK histogram: %d file(s), equal contiguous bins on a zero-anchored "
          "linear count scale, n equal to the sum, markers at their declared "
          "values, and every printed numeral bound to what it names%s"
          % (len(checked), tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
