#!/usr/bin/env python3
"""Verify that a slopegraph's drawn slopes match the values it prints.

A slopegraph makes exactly one claim: **both axes carry the same scale**, so the
angle of a line is a rate of change and two angles are comparable. Break that
claim and nothing errors - the figure renders, every label is present, and the
lie is in the geometry. `lint-skin.py` reads colors and fonts, `verify-geometry.py`
reads label masks against later-painted nodes, and neither compares a drawn
endpoint against the number sitting beside it.

Four invariants, each of which has shipped broken in a draft of this type:

1. SHARED SCALE - the left and right axes must map value to y through the same
   linear transform. Both halves are checked, slope *and* origin: a second axis
   that is rescaled makes every slope wrong by a factor, and one that is merely
   shifted makes every slope wrong by a constant. Checking the slope alone would
   pass the shifted case, which is the easier mistake to make.

2. NO JITTER - each declared value must sit where the shared scale puts it. The
   draft this checker was written against nudged two series apart by 3px because
   their labels collided at identical values; both then read as different
   numbers. Crowded endpoint labels are data, not a coordinate problem.

3. LABEL EQUALS METADATA - the printed endpoint value must exist, must be unique,
   and must equal the declared one. A label and a `data-` attribute are two
   statements of one number, so they are worth cross-checking.

4. FAIL CLOSED - a file that presents as a slopegraph but yields nothing
   parseable is a finding, never a pass. A checker that reports OK because it
   found nothing to compare is the bug, not the gate. `verify-treemap.py`
   returned early on `len(cells) < 3` and that is precisely how an undersized
   cell went unverified.

The basis is the `data-from` / `data-to` attribute pair each series line
declares, never the rendered text. Deriving the basis from text is what let a
treemap cell with no label drop silently out of the checked set; here a series
whose label is missing or restyled stays in the set and its missing label is
itself reported.

WHAT THIS DOES NOT CHECK, deliberately:

- **Direction.** An axis whose y grows with value is accepted. That is correct
  for a rank slopegraph, where rank 1 belongs at the top, and this checker has no
  way to tell an intended inversion from a mistaken one.
- **Absolute truth.** Every check here is internal consistency. If every label
  and every declared value is wrong by the same constant, the figure is
  self-consistent and passes; nothing in the file could reveal otherwise. The
  source line is where the domain is stated to a reader, and prose is not parsed.
- **Curvature below tolerance.** A value-to-y map that bends by less than
  RESIDUAL_TOLERANCE at every point is indistinguishable from a straight one.
  See the tolerance note below for what that permits in data units.

Usage:
    python3 scripts/verify-slopegraph.py --all
    python3 scripts/verify-slopegraph.py skills/diagram-design/assets/example-slopegraph.html

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

LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
# Full numeric syntax an author may reasonably print: sign, leading-dot decimals,
# and exponents. Matching only `-?\d+(\.\d+)?` read "1e3" as the number 1 and
# reported an honest label as contradicting its own metadata.
NUMBER_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")

# Both quote styles. Matching only double quotes made a single-quoted series
# line invisible: the detector below sees `data-series` in the raw source either
# way, but the attribute parser returned nothing, so the line was dropped from
# the verified set without a word - a file carrying a 400px lie reported clean.
# Single quotes are legal SVG, and a gate must not be silent about markup it
# cannot read; see DECLARES_SERIES_RE for the net that catches the rest.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
# Quote-agnostic presence test, used to tell "this element is not a series" from
# "this element claims to be a series and I could not read it".
DECLARES_SERIES_RE = re.compile(r"\bdata-series\s*=", re.IGNORECASE)

# Coordinates ship rounded to one decimal, so a point can sit 0.05px from its
# true position honestly; an author rounding to whole pixels can sit 0.5px off.
# 1.0px clears both and still catches the smallest dishonest nudge worth making
# (the draft's was 3px). In data units at the shipped 0.844 px-per-ms scale that
# is 1.2ms of slack on values running 121-512 - about a quarter of one percent,
# which is below the precision the labels themselves claim.
RESIDUAL_TOLERANCE = 1.0   # px, per endpoint, against the shared scale
ORIGIN_TOLERANCE = 0.5     # px, between the two axes at mid-domain
SCALE_TOLERANCE = 1.0      # px, worst-case slope disagreement across the range
VALUE_TOLERANCE = 0.001    # printed label vs declared attribute


class Series:
    __slots__ = ("name", "frm", "to", "x1", "y1", "x2", "y2", "offset")

    def __init__(self, name, frm, to, x1, y1, x2, y2, offset):
        self.name = name
        self.frm, self.to = frm, to
        self.x1, self.y1 = x1, y1
        self.x2, self.y2 = x2, y2
        self.offset = offset


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def blank_comments(source: str) -> str:
    """Comments out, length and line numbers preserved.

    Markup inside a comment is not rendered, so treating it as data reports a
    commented-out old draft as a live defect. Replacing each comment with spaces
    of the same length keeps every later offset and line number honest.
    """
    return COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def attrs_of(raw: str) -> dict:
    return {m.group("name"): m.group("value") for m in ATTR_RE.finditer(raw)}


def plain(body: str) -> str:
    return html.unescape(TAG_RE.sub("", body)).strip()


def number(value: str):
    """A finite float, or None.

    `float("nan")` succeeds and then every `abs(x) > tolerance` comparison is
    False, so a NaN coordinate silently satisfied every check in the file. Any
    non-finite value is treated as unreadable instead.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def median(values: list) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def fit(points: list) -> tuple:
    """Robust (slope, intercept) for y = slope * value + intercept.

    Theil-Sen - the median of all pairwise slopes - rather than least squares, so
    that one dishonest point does not drag the line it is being measured against.
    Returns (None, None) when every value is the same, which is legitimate on an
    indexed axis and handled by the caller.
    """
    slopes = [
        (yb - ya) / (vb - va)
        for index, (va, ya) in enumerate(points)
        for vb, yb in points[index + 1:]
        if vb != va
    ]
    if not slopes:
        return None, None
    slope = median(slopes)
    return slope, median([y - slope * v for v, y in points])


def outliers(points: list, tolerance: float) -> list:
    """Points that disagree with the line their PEERS describe.

    Leave-one-out, because measuring a point against a fit that includes it lets
    it hide inside its own influence. Theil-Sen's breakdown point is around 29%,
    which is zero outliers on a three-point axis: an indexed three-series figure
    with one endpoint 3px wrong produced a whole-set fit that called all three
    points clean, because the contaminated slope passed within 1px of every one
    of them. Excluding the point under test removes that escape - the same figure
    now reports 2.9px on the endpoint that moved.

    Returns [(index, drawn, expected)]. Needs four points, so that each fit is
    made from at least three.
    """
    if len(points) < 4:
        return []
    found = []
    for index, (value, drawn) in enumerate(points):
        peers = points[:index] + points[index + 1:]
        slope, intercept = fit(peers)
        if slope is None:
            continue
        expected = slope * value + intercept
        if abs(drawn - expected) > tolerance:
            found.append((index, drawn, expected))
    return found


def named_text(source: str) -> str:
    """The accessible name and description, which is where a figure says what it is."""
    return " ".join(plain(m.group("body")) for m in NAMED_RE.finditer(source)).casefold()


def looks_like_slopegraph(path: Path, source: str) -> bool:
    """Does this file present itself as a slopegraph?

    Deliberately generous. Anything that claims the type in its name, its
    accessible description, or its markup is held to the contract even if it
    declares no parseable series - that combination is the fail-closed case, not
    a pass. The whole document is searched: a 4000-character window missed a file
    whose only declaration sat behind a long stylesheet.
    """
    if path.name.startswith("example-slopegraph"):
        return True
    if DECLARES_SERIES_RE.search(source):
        return True
    described = named_text(source)
    return "slopegraph" in described or "slope graph" in described


def parse_series(source: str, findings: list, name: str) -> list:
    """Series lines, with anything unparseable reported rather than dropped."""
    series = []
    for match in LINE_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        label = attrs.get("data-series")
        if label is None:
            # A <line> with no data-series is scenery - an axis rule, a legend
            # swatch - and skipping it is correct. But one whose raw text DOES
            # declare data-series and still parsed to nothing is markup this
            # checker cannot read, and dropping it silently is how a lie ships.
            if DECLARES_SERIES_RE.search(raw):
                findings.append(
                    "%s:%d: a <line> declares data-series but its attributes could "
                    "not be parsed — the checker will not silently skip markup it "
                    "cannot read. Use plain double-quoted attributes"
                    % (name, line_of(source, match.start()))
                )
            continue
        missing = [key for key in ("data-from", "data-to", "x1", "y1", "x2", "y2")
                   if key not in attrs]
        if missing:
            findings.append(
                "%s:%d: series %r declares data-series but is missing %s — a series "
                "line must state both values and both endpoints or it cannot be verified"
                % (name, line_of(source, match.start()), label, ", ".join(missing))
            )
            continue
        parsed = [number(attrs[key])
                  for key in ("data-from", "data-to", "x1", "y1", "x2", "y2")]
        if any(value is None for value in parsed):
            findings.append(
                "%s:%d: series %r has a value or coordinate that is not a finite "
                "number — cannot verify its slope"
                % (name, line_of(source, match.start()), label)
            )
            continue
        series.append(Series(label, parsed[0], parsed[1], parsed[2], parsed[3],
                             parsed[4], parsed[5], match.start()))
    return series


def check_axes(series: list, findings: list, source: str, name: str) -> None:
    """Every series must span the same two axis positions."""
    for attr, getter in (("x1", lambda s: s.x1), ("x2", lambda s: s.x2)):
        positions = sorted({round(getter(s), 3) for s in series})
        if len(positions) > 1:
            offenders = ", ".join("%s at %g" % (s.name, getter(s)) for s in series)
            findings.append(
                "%s:%d: series do not share one %s — found %s (%s). Every line must "
                "run between the same two axes or the slopes are not comparable"
                % (name, line_of(source, series[0].offset), attr,
                   "/".join("%g" % p for p in positions), offenders)
            )


def check_scale(series: list, findings: list, source: str, name: str) -> None:
    """The two axes must share one linear value-to-y map, and no point may drift."""
    left = [(s.frm, s.y1) for s in series]
    right = [(s.to, s.y2) for s in series]
    combined = left + right
    values = [v for v, _ in combined]
    span = max(values) - min(values)
    mid = (max(values) + min(values)) / 2.0
    line = line_of(source, series[0].offset)

    left_fit = fit(left)
    right_fit = fit(right)

    if left_fit[0] is not None and right_fit[0] is not None:
        slope_drift = abs(left_fit[0] - right_fit[0]) * span
        if slope_drift > SCALE_TOLERANCE:
            findings.append(
                "%s:%d: the two axes are not on the same scale — %.4g px/unit on the "
                "left against %.4g on the right, which puts the same value up to "
                "%.1f px apart across the plotted range. Both axes must use one scale "
                "or every slope is a lie"
                % (name, line, left_fit[0], right_fit[0], slope_drift)
            )
            return
        # Compared at mid-domain, not at value zero. Raw intercepts are the
        # predicted y AT zero, so on values in the billions two axes sharing one
        # transform disagreed by hundreds of pixels there through nothing but
        # float cancellation, and an honest figure was reported as shifted.
        origin_drift = abs((left_fit[0] * mid + left_fit[1])
                           - (right_fit[0] * mid + right_fit[1]))
        if origin_drift > ORIGIN_TOLERANCE:
            findings.append(
                "%s:%d: the two axes share a scale but not an origin — offset by "
                "%.1f px at mid-domain. A shifted axis tilts every slope by the same "
                "amount, so the comparison between series survives and every rate is "
                "wrong" % (name, line, origin_drift)
            )
            return
        # Both returns above are deliberate. Per-point residuals are measured
        # against "the" shared scale, so once the two axes disagree about what
        # that scale is there is nothing meaningful to measure against - every
        # point reports an error and the one finding that names the cause is
        # buried in its own consequences.
    elif left_fit[0] is None and right_fit[0] is None:
        findings.append(
            "%s:%d: neither axis has two distinct values, so the scale cannot be "
            "derived and no slope here is verifiable" % (name, line)
        )
        return

    # One shared scale is now established (or one axis is flat - an indexed
    # slopegraph, which is legitimate). Hold every point on both axes to the line
    # its peers describe.
    ends = ["from"] * len(left) + ["to"] * len(right)
    for index, drawn, expected in outliers(combined, RESIDUAL_TOLERANCE):
        s = series[index % len(series)]
        value = combined[index][0]
        findings.append(
            "%s:%d: series %r draws its %s endpoint (%g) at y=%g where the shared "
            "scale its peers describe puts %g at y=%.1f — off by %.1f px. Do not move "
            "a point to make room for its label"
            % (name, line_of(source, s.offset), s.name, ends[index], value, drawn,
               value, expected, abs(drawn - expected))
        )


def check_labels(series: list, source: str, findings: list, name: str) -> None:
    """Printed endpoint values must exist, be unique, and equal the declared ones."""
    printed = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label, end = attrs.get("data-series"), attrs.get("data-end")
        if label is None or end is None:
            continue
        body = plain(match.group("body"))
        found = NUMBER_RE.search(body)
        if found is None:
            findings.append(
                "%s:%d: endpoint label for %r (%s) prints no number (%r) — label both "
                "endpoints with their actual values"
                % (name, line_of(source, match.start()), label, end, body[:24])
            )
            continue
        if (label, end) in printed:
            # A second label for the same endpoint used to overwrite the first,
            # so a figure could print two contradictory numbers for one point and
            # be judged on whichever came last.
            findings.append(
                "%s:%d: a second %s label for series %r — one endpoint, one printed "
                "value, or the figure states two numbers for one point"
                % (name, line_of(source, match.start()), end, label)
            )
            continue
        printed[(label, end)] = (number(found.group()), match.start(), body)

    declared = {s.name for s in series}
    for (label, end), (_shown, offset, _body) in sorted(
        printed.items(), key=lambda item: item[1][1]
    ):
        if label not in declared:
            findings.append(
                "%s:%d: an endpoint label names series %r, which no line declares — "
                "a label with no mark is not verifiable and reads as data"
                % (name, line_of(source, offset), label)
            )

    for s in series:
        for end, value in (("from", s.frm), ("to", s.to)):
            entry = printed.get((s.name, end))
            if entry is None:
                findings.append(
                    "%s:%d: series %r prints no %s endpoint value — a slopegraph must "
                    "label both ends, or the reader has a slope and no magnitude"
                    % (name, line_of(source, s.offset), s.name, end)
                )
                continue
            shown, offset, body = entry
            if shown is None or abs(shown - value) > VALUE_TOLERANCE:
                findings.append(
                    "%s:%d: series %r prints %r at its %s endpoint but declares %g — "
                    "the label and the geometry must state one number"
                    % (name, line_of(source, offset), s.name, body, end, value)
                )


def check_source(path: Path, raw: str) -> list:
    """Findings for one already-read document."""
    source = blank_comments(raw)
    findings: list = []
    series = parse_series(source, findings, path.name)

    if len(series) < 2:
        findings.append(
            "%s: presents as a slopegraph but declares %d verifiable series — every "
            "line needs data-series with data-from and data-to. Refusing to report "
            "OK on a file this checker could not read" % (path.name, len(series))
        )
        return findings

    check_axes(series, findings, source, path.name)
    check_scale(series, findings, source, path.name)
    check_labels(series, source, findings, path.name)
    return findings


def check(path: Path) -> list:
    """Findings for one file on disk, or [] if it is not a slopegraph."""
    raw = path.read_text(encoding="utf-8")
    if not looks_like_slopegraph(path, raw):
        return []
    return check_source(path, raw)


def targets(args: argparse.Namespace) -> list:
    if args.all:
        return sorted(ASSET_DIR.glob("example-*.html"))
    return [Path(p) for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify slopegraph slopes against the values they are labelled with."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a slopegraph",
    )
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    findings: list = []
    checked = 0
    skipped = 0
    for path in targets(args):
        if not path.is_file():
            print("error: %s is not a readable file" % path, file=sys.stderr)
            return 2
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            print("error: cannot read %s: %s" % (path, error), file=sys.stderr)
            return 2
        # Read once, then decide. Scope is reported separately from verification
        # in both modes: printing "1 file(s) verified" for a bar chart that was
        # skipped is a claim the run never made good on.
        if not looks_like_slopegraph(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d slopegraph finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK slopegraph: no slopegraph found to check%s" % tail)
        return 0
    print("OK slopegraph: %d file(s), one shared scale on both axes and every drawn "
          "endpoint matches its printed value%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
