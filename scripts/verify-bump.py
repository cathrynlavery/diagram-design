#!/usr/bin/env python3
"""Verify that a bump chart's drawn positions match the ranks it declares.

A bump chart makes one claim: **vertical position is rank, and nothing else**.
Rank is ordinal, so unlike every other chart gate in this repo the geometry is
EXACT - each vertex belongs on `y = top + (rank - 1) x pitch` with no tolerance
worth granting, because rank has no fractions and no rounding. Every way of
breaking the claim renders perfectly: a vertex nudged off its row reads as a
rank between two ranks, two series sharing a row at one snapshot claim a tie
the ranking key cannot produce, and a curved segment invents a trajectory
between snapshots that were only measured quarterly.

Six invariants:

1. ONE RANK GRID - every vertex of every series maps rank to y through the same
   linear map, derived from the figure itself and then enforced exactly. A
   figure whose rows are unevenly pitched reads relative movement wrong.

2. PERMUTATION PER SNAPSHOT - each column's declared ranks are exactly
   1..N, each used once. A duplicated rank is a tie the footnote's tie-break
   rule says cannot happen; a skipped rank is an empty row the reader fills
   with a series that is not there.

3. STRAIGHT SEGMENTS - a data-series path is absolute M followed by absolute
   L commands only. A spline between two quarterly snapshots draws data nobody
   measured; the draft this gate came from calls them subway curves and bans
   them outright. Relative commands are refused rather than folded into their
   absolute twins, because their numbers are not where the marks land.

4. SHARED COLUMNS - every series visits the same x positions in the same
   order, and each snapshot caption sits on the column it names, bound with
   data-axis and data-state exactly as the slopegraph binds its two.

5. LABELS BOUND TO MEANING AND PLACED ON BOTH AXES - each series prints its
   name and its rank at first and last appearance, each label bound by
   data-series / data-end / data-role, each printed "#k" agreeing with the
   declared rank, each sitting on its own series' row rather than a
   neighbour's, and each in the gutter outboard of the end it names. Row and
   column answer different questions - WHICH SERIES and WHICH END - so a
   label with an impeccable row and a deleted or displaced x is misplaced
   and used to be certified.

6. FAIL CLOSED - zero parseable series, a path that declares data-series but
   cannot be read, a vertex with no dot, a label coordinate that is absent,
   empty or non-finite, or a transform anywhere near verified geometry is a
   finding, never a skip. A checker that reports OK because it found nothing
   to compare is the bug, not the gate. An absent attribute is the loudest
   version of this: it is not an unspecified position, it is the browser's
   default one, and it renders.

WHAT THIS DOES NOT CHECK, deliberately:

- **The ranking key.** Rank by what, ties broken how - that is the footnote's
  job, and prose is not parsed. Every check here is internal consistency.
- **Late entry and early exit.** The draft permits a series to start or stop
  mid-figure; the shipped grammar does not use it yet, so a series with fewer
  vertices than columns is a finding until the grammar grows a way to declare
  a gap. Widening this without a declaration attribute would let a truncated
  series pass as a deliberate exit.

Usage:
    python3 scripts/verify-bump.py --all
    python3 scripts/verify-bump.py skills/diagram-design/assets/example-bump.html

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

PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
CIRCLE_RE = re.compile(r"<circle\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
# Every CSS property that can move verified SVG geometry without changing the
# attributes this checker reads. Declaration-start anchoring avoids matching
# `text-transform` and custom-property values.
CSS_MOVES_MARK_RE = re.compile(
    r"(?:^|[{;}\n])\s*(?:-(?:webkit|moz|ms|o)-)?"
    r"(?P<prop>transform|translate|rotate|scale"
    r"|cx|cy|r|x|y|d"
    r"|offset(?:-(?:path|distance|position|anchor|rotate))?)"
    r"\s*:",
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
# Both quote styles, for the same reason verify-slopegraph gives: a
# single-quoted attribute must be read, not silently dropped from the set.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_RANKS_RE = re.compile(r"\bdata-ranks\s*=", re.IGNORECASE)
# Full SVG number grammar: the fractional digits after a decimal point are
# optional when an integer part is present, so both `320.` and `320.e2` are
# valid spellings of coordinates this verifier must measure.
NUM_RE = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
PATH_COMMAND_RE = re.compile(r"[AaCcHhLlMmQqSsTtVvZz]")
RANK_LABEL_RE = re.compile(r"^#(\d+)$")

# Rank is ordinal and the shipped coordinates are integers, so the only slack
# granted is float formatting - far below half a pixel, let alone half a row.
GRID_TOLERANCE = 0.01     # px, a vertex against the rank grid
DOT_TOLERANCE = 0.01      # px, a dot against its vertex
CAPTION_TOLERANCE = 0.5   # px, a snapshot caption against its column
LABEL_ROW_OFFSET = 3.5    # px, a label baseline below its vertex, per the reference
MIN_SNAPSHOTS, MAX_SNAPSHOTS = 3, 6
MIN_SERIES, MAX_SERIES = 4, 8
FOCAL_WIDTH, PLAIN_WIDTH = 2.4, 1.2
ACCENTS = {"#eb6c36", "#f08a59"}   # light and dark skin accent tokens


class Series:
    __slots__ = ("name", "ranks", "points", "stroke", "width", "offset")

    def __init__(self, name, ranks, points, stroke, width, offset):
        self.name = name
        self.ranks = ranks
        self.points = points
        self.stroke = stroke
        self.width = width
        self.offset = offset

    @property
    def focal(self):
        return self.stroke in ACCENTS


def attrs_of(raw: str) -> dict:
    found = {}
    for match in ATTR_RE.finditer(raw):
        name = match.group("name").lower()
        if name not in found:            # a browser keeps the FIRST of a repeat
            found[name] = html.unescape(match.group("value"))
    return found


def number(value):
    """An SVG coordinate, or None when it cannot be placed.

    None covers absent, unparseable AND non-finite, because every caller
    treats None as "report this" rather than "skip this". "1e400" parses and
    overflows to inf, which compares further-than-any-tolerance from every
    real coordinate and would otherwise sail through a naive distance test.
    """
    if value is None:
        return None
    match = NUM_RE.fullmatch(value.strip())
    if not match:
        return None
    try:
        parsed = float(match.group(0))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def line_of(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def plain(body: str) -> str:
    return TAG_RE.sub("", html.unescape(body)).strip()


def blank_comments(source: str) -> str:
    """Comments replaced with spaces, offsets preserved."""
    return COMMENT_RE.sub(lambda m: " " * len(m.group(0)), source)


def named_text(source: str) -> str:
    return " ".join(
        plain(m.group("body")).lower() for m in NAMED_RE.finditer(source)
    )


def looks_like_bump(path: Path, source: str) -> bool:
    """Does this file present itself as a bump chart?

    Generous on the vocabulary this contract binds: `data-ranks` belongs to no
    other chart in this repo, so any file declaring it is held to the contract
    even if nothing else parses - that combination is the fail-closed case.
    """
    if path.name.startswith("example-bump"):
        return True
    if DECLARES_RANKS_RE.search(source):
        return True
    return "bump chart" in named_text(source)


def parse_d(d: str):
    """(commands, points) for a polyline path, or (None, None) if unreadable."""
    # `e` and `E` belong to scientific-notation numbers, not SVG's command
    # alphabet. Remove complete numbers before checking the residue so valid
    # coordinates such as 4.4e2 are not mistaken for relative commands, while
    # an actual unknown letter still fails closed.
    residue = NUM_RE.sub("", d)
    residue = PATH_COMMAND_RE.sub("", residue)
    if re.sub(r"[\s,]+", "", residue):
        return None, None
    commands = PATH_COMMAND_RE.findall(d)
    numbers = [float(n) for n in NUM_RE.findall(d)]
    if len(numbers) % 2 != 0:
        return None, None
    points = list(zip(numbers[0::2], numbers[1::2]))
    return commands, points


def parse_series(source: str, findings: list, name: str) -> list:
    series = []
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        label = attrs.get("data-series")
        if label is None:
            if DECLARES_RANKS_RE.search(raw):
                findings.append(
                    "%s:%d: a <path> declares data-ranks but no data-series — a "
                    "ranked line must say which series it draws, or its labels "
                    "cannot be bound to it"
                    % (name, line_of(source, match.start()))
                )
            continue
        ranks_raw = attrs.get("data-ranks")
        if ranks_raw is None:
            findings.append(
                "%s:%d: series %r declares data-series but no data-ranks — the "
                "declared ranks are the basis every drawn position is verified "
                "against, so a path without them cannot be checked"
                % (name, line_of(source, match.start()), label)
            )
            continue
        try:
            ranks = [int(part.strip()) for part in ranks_raw.split(",")]
        except ValueError:
            findings.append(
                "%s:%d: series %r has data-ranks=%r, which is not a comma list of "
                "integers — rank is ordinal, and a rank that is not a whole number "
                "is not a rank"
                % (name, line_of(source, match.start()), label, ranks_raw)
            )
            continue
        commands, points = parse_d(attrs.get("d", ""))
        if commands is None or not points:
            findings.append(
                "%s:%d: series %r has a path this checker cannot read — cannot "
                "verify its positions" % (name, line_of(source, match.start()), label)
            )
            continue
        # Straight segments in ABSOLUTE commands only: M + L* is the entire
        # permitted grammar. A curve between two snapshots draws data nobody
        # measured. And a relative command is refused rather than folded into
        # its absolute twin - `l120,56` renders against the previous point
        # while the numbers this checker reads look like absolute coordinates,
        # so folding case would certify a figure at positions it never drew.
        if any(c.islower() for c in commands):
            findings.append(
                "%s:%d: series %r uses relative path commands (%s) — a relative "
                "coordinate renders against the previous point, so the numbers "
                "this checker reads are not where the marks land. Write the path "
                "in absolute M/L commands"
                % (name, line_of(source, match.start()), label, "/".join(commands))
            )
            continue
        if commands != ["M"] + ["L"] * (len(points) - 1):
            findings.append(
                "%s:%d: series %r draws %s — a bump chart joins adjacent snapshots "
                "with straight segments only. A spline invents a trajectory between "
                "ranks that were only measured at the snapshots"
                % (name, line_of(source, match.start()), label, "/".join(commands))
            )
            continue
        if len(points) != len(ranks):
            findings.append(
                "%s:%d: series %r declares %d ranks but draws %d points — every "
                "declared rank needs its vertex and every vertex its rank"
                % (name, line_of(source, match.start()), label, len(ranks), len(points))
            )
            continue
        width = number(attrs.get("stroke-width"))
        series.append(Series(label, ranks, points,
                             (attrs.get("stroke") or "").strip().lower(),
                             width, match.start()))
    return series


def transform_carrier(attrs: dict):
    """Describe the attribute or inline-style property that moves an element."""
    if "transform" in attrs:
        return "transform=%r" % attrs["transform"]
    style = attrs.get("style")
    if style is not None:
        found = CSS_MOVES_MARK_RE.search(style)
        if found is not None:
            return "style=%r (the %s property)" % (
                style,
                found.group("prop").lower(),
            )
    return None


def transformed_spans(source: str) -> list:
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        how = None
        if "transform" in attrs:
            how = "an ancestor <g>/<svg> transform"
        elif transform_carrier(attrs) is not None:
            how = "an ancestor <g>/<svg> style transform"
        events.append((match.start(), 0, how))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), 1, None))
    events.sort(key=lambda event: (event[0], event[1]))
    spans, stack = [], []
    for position, kind, how in events:
        if kind == 0:
            stack.append((position, how))
        elif stack:
            start, was_transformed = stack.pop()
            if was_transformed:
                spans.append((start, position, was_transformed))
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source), was_transformed))
    return spans


def check_transforms(source: str, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label."""
    spans = transformed_spans(source)

    def enclosing(offset):
        for start, end, how in spans:
            if start <= offset <= end:
                return how
        return None

    def report(offset, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw coordinates, so a "
            "transform moves the rendered mark away from the rank it was checked "
            "against. Bake the offset into the coordinates instead"
            % (name, line_of(source, offset), what, how)
        )

    def check_element(offset, attrs, what):
        how = transform_carrier(attrs)
        if how is None:
            how = enclosing(offset)
        if how is not None:
            report(offset, what, how)

    for match in PATH_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-series" not in attrs:
            continue
        what = "series %r" % attrs["data-series"]
        check_element(match.start(), attrs, what)

    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-series" not in attrs and "data-axis" not in attrs:
            continue
        what = "a bound label (%s)" % plain(match.group("body"))[:20]
        check_element(match.start(), attrs, what)

    for match in STYLE_RE.finditer(source):
        found = CSS_MOVES_MARK_RE.search(match.group("body"))
        if found:
            findings.append(
                "%s:%d: a CSS `%s` declaration — this checker cannot tell "
                "which marks it applies to, and a transform on verified geometry "
                "invalidates every coordinate here"
                % (
                    name,
                    line_of(source, match.start("body") + found.start()),
                    found.group("prop").lower(),
                )
            )


def check_columns(series: list, findings: list, source: str, name: str) -> None:
    """Every series visits the same x positions, in increasing order."""
    reference = [round(x, 3) for x, _ in series[0].points]
    if sorted(set(reference)) != reference:
        findings.append(
            "%s:%d: series %r visits columns at x=%s, which is not strictly "
            "increasing — snapshots are ordered, and a column visited twice or out "
            "of order redraws time"
            % (name, line_of(source, series[0].offset), series[0].name,
               "/".join("%g" % x for x in reference))
        )
        return
    for s in series[1:]:
        xs = [round(x, 3) for x, _ in s.points]
        if xs != reference:
            findings.append(
                "%s:%d: series %r visits columns at x=%s but %r set them at %s — "
                "every series must visit the same snapshots or the columns stop "
                "meaning moments"
                % (name, line_of(source, s.offset), s.name,
                   "/".join("%g" % x for x in xs), series[0].name,
                   "/".join("%g" % x for x in reference))
            )


def rank_map(series: list):
    """(top, pitch) derived from the figure, or None if it cannot be derived."""
    pairs = {}
    for s in series:
        for rank, (_, y) in zip(s.ranks, s.points):
            pairs.setdefault(rank, y)
    if len(pairs) < 2:
        return None
    ranks = sorted(pairs)
    r0, r1 = ranks[0], ranks[-1]
    pitch = (pairs[r1] - pairs[r0]) / (r1 - r0)
    top = pairs[r0] - (r0 - 1) * pitch
    if pitch <= 0:
        return None
    return top, pitch


def check_grid(series: list, findings: list, source: str, name: str) -> None:
    """Every vertex sits exactly on the one rank grid; every column is a permutation."""
    derived = rank_map(series)
    if derived is None:
        findings.append(
            "%s: no downward rank grid could be derived — the figure's vertices "
            "must place rank 1 at the top and each further rank one fixed pitch "
            "below it. Refusing to report OK on a grid this checker could not read"
            % name
        )
        return
    top, pitch = derived
    for s in series:
        for rank, (x, y) in zip(s.ranks, s.points):
            if rank < 1:
                findings.append(
                    "%s:%d: series %r declares rank %d — ranks count from 1"
                    % (name, line_of(source, s.offset), s.name, rank)
                )
                continue
            expected = top + (rank - 1) * pitch
            if abs(y - expected) > GRID_TOLERANCE:
                findings.append(
                    "%s:%d: series %r draws rank %d at y=%g, but the figure's grid "
                    "puts that rank at y=%g — rank is ordinal, so there is no honest "
                    "reason for a vertex to sit off its row. A nudge to dodge a "
                    "label collision reads as a rank between two ranks"
                    % (name, line_of(source, s.offset), s.name, rank, y, expected)
                )

    total = len(series)
    columns = len(series[0].points)
    for column in range(columns):
        seen = {}
        for s in series:
            if column < len(s.ranks):
                seen.setdefault(s.ranks[column], []).append(s.name)
        for rank, owners in sorted(seen.items()):
            if len(owners) > 1:
                findings.append(
                    "%s: snapshot %d ranks %s all at #%d — the footnote's tie-break "
                    "rule exists so that a rank is held by exactly one series"
                    % (name, column + 1, "/".join(repr(o) for o in owners), rank)
                )
        missing = [r for r in range(1, total + 1) if r not in seen]
        for rank in missing:
            findings.append(
                "%s: snapshot %d has no series at rank #%d — with %d series each "
                "snapshot must use each rank 1..%d exactly once, or an empty row "
                "invites the reader to fill it"
                % (name, column + 1, rank, total, total)
            )


def check_dots(series: list, source: str, findings: list, name: str) -> None:
    """Every vertex carries its dot, sized by focus."""
    dots = []
    for match in CIRCLE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        cx, cy, r = (number(attrs.get(k)) for k in ("cx", "cy", "r"))
        if None not in (cx, cy, r):
            dots.append((cx, cy, r))
    for s in series:
        want = 4.0 if s.focal else 3.0
        for rank, (x, y) in zip(s.ranks, s.points):
            hit = [r for cx, cy, r in dots
                   if abs(cx - x) <= DOT_TOLERANCE and abs(cy - y) <= DOT_TOLERANCE]
            if not hit:
                findings.append(
                    "%s:%d: series %r has no dot at its rank-%d vertex (%g,%g) — "
                    "the dots are the readable positions, so a vertex without one "
                    "is a rank the reader cannot fix on a row"
                    % (name, line_of(source, s.offset), s.name, rank, x, y)
                )
            elif want not in hit:
                findings.append(
                    "%s:%d: series %r has a dot of r=%s at (%g,%g), but a %s series "
                    "takes r=%g — dot size is the focus cue that survives greyscale"
                    % (name, line_of(source, s.offset), s.name,
                       "/".join("%g" % r for r in hit), x, y,
                       "focal" if s.focal else "non-focal", want)
                )


def check_focus(series: list, findings: list, source: str, name: str) -> None:
    """Exactly one focal series, and stroke weight agreeing with stroke colour."""
    focal = [s for s in series if s.focal]
    if len(focal) != 1:
        findings.append(
            "%s: %d series carry the accent stroke — the accent marks exactly one "
            "editorially focal series, and spending it twice spends it entirely"
            % (name, len(focal))
        )
    for s in series:
        want = FOCAL_WIDTH if s.focal else PLAIN_WIDTH
        if s.width is None or abs(s.width - want) > 1e-9:
            findings.append(
                "%s:%d: series %r has stroke-width=%s but a %s series takes %g — "
                "weight is the focus cue, so a mismatch between colour and weight "
                "sends the two cues to different series"
                % (name, line_of(source, s.offset), s.name,
                   "%g" % s.width if s.width is not None else "?",
                   "focal" if s.focal else "non-focal", want)
            )


def collect_bound_labels(source: str, findings: list, name: str) -> dict:
    bound = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label = attrs.get("data-series")
        if label is None:
            continue
        end = attrs.get("data-end")
        role = attrs.get("data-role")
        key = (label, end, role)
        if key in bound:
            findings.append(
                "%s:%d: a second %s %s label for series %r — one label per binding, "
                "or a reader has two statements and no way to pick"
                % (name, line_of(source, match.start()), end, role, label)
            )
            continue
        bound[key] = (plain(match.group("body")), number(attrs.get("x")),
                      number(attrs.get("y")), match.start())
    return bound


def check_labels(series: list, source: str, findings: list, name: str) -> None:
    """Names and ranks printed at both ends, bound, agreeing, and placed.

    Placement is verified on BOTH axes, because each answers a different
    question and neither implies the other. The row (y) says which series a
    label belongs to; the column (x) says which END of that series it belongs
    to. A first-end label slid along its own row into the middle of the plot
    keeps every rank correct and every row correct while reading against the
    wrong snapshot - so a row-only check certifies it.
    """
    bound = collect_bound_labels(source, findings, name)
    declared = {s.name: s for s in series}
    # check_columns has already established that every series shares these.
    columns = [x for x, _ in series[0].points]
    gutters = {}

    for (label, end, role), (body, x, y, offset) in sorted(
        bound.items(), key=lambda item: item[1][3]
    ):
        if label not in declared:
            findings.append(
                "%s:%d: a %s label names series %r, which no path declares — a "
                "label with no mark is not verifiable and reads as data"
                % (name, line_of(source, offset), role, label)
            )
            continue
        if end not in ("first", "last"):
            findings.append(
                "%s:%d: label for series %r has data-end=%r, which is neither "
                "'first' nor 'last'" % (name, line_of(source, offset), label, end)
            )
            continue
        s = declared[label]
        vertex_y = s.points[0][1] if end == "first" else s.points[-1][1]
        endpoint_x = columns[0] if end == "first" else columns[-1]

        # Both coordinates must be readable before either can be judged. An
        # absent x or y is not "unspecified": SVG defaults it to 0, so the
        # browser draws the label hard against the edge of the frame while a
        # checker that skips the comparison reports the figure clean. That
        # skip is invariant 6's named failure, so it is a finding here.
        unplaced = [axis for axis, value in (("x", x), ("y", y)) if value is None]
        if unplaced:
            findings.append(
                "%s:%d: the %s %s label for series %r has no readable %s — the "
                "browser falls back to 0 and draws it at the edge of the frame, "
                "so an unreadable coordinate is a misplaced label, never an "
                "unchecked one"
                % (name, line_of(source, offset), end, role, label,
                   " or ".join(unplaced))
            )
            continue

        gutters.setdefault((end, role), []).append((x, label, offset))

        # Column placement: a label inboard of its own endpoint sits over the
        # plot, beside a snapshot it does not describe.
        if (end == "first" and x > endpoint_x + GRID_TOLERANCE) or (
            end == "last" and x < endpoint_x - GRID_TOLERANCE
        ):
            findings.append(
                "%s:%d: the %s %s label for series %r is drawn at x=%g, inboard "
                "of the %s endpoint at x=%g — a label inside the plot is read "
                "against whichever snapshot it lands on"
                % (name, line_of(source, offset), end, role, label, x, end,
                   endpoint_x)
            )

        # Row placement: nearer another series' same-end vertex than its own
        # means the label renames a line, with every number still correct.
        own = abs(y - (vertex_y + LABEL_ROW_OFFSET))
        for other in series:
            if other.name == label:
                continue
            other_y = other.points[0][1] if end == "first" else other.points[-1][1]
            if abs(y - (other_y + LABEL_ROW_OFFSET)) < own:
                findings.append(
                    "%s:%d: the %s %s label for series %r is drawn at y=%g, "
                    "nearer %r's endpoint than its own — a label on the wrong "
                    "row renames the line"
                    % (name, line_of(source, offset), end, role, label, y,
                       other.name)
                )
                break
        if role == "rank":
            match = RANK_LABEL_RE.match(body)
            declared_rank = s.ranks[0] if end == "first" else s.ranks[-1]
            if not match:
                findings.append(
                    "%s:%d: series %r prints its %s rank as %r — a rank label is "
                    "'#' and the rank, so it cannot be mistaken for a magnitude"
                    % (name, line_of(source, offset), label, end, body)
                )
            elif int(match.group(1)) != declared_rank:
                findings.append(
                    "%s:%d: series %r prints %s rank %r but declares rank %d — the "
                    "label and the geometry must state one number"
                    % (name, line_of(source, offset), label, end, body, declared_rank)
                )
        elif role == "name":
            if body != label:
                findings.append(
                    "%s:%d: a name label bound to series %r reads %r — the visible "
                    "name and its binding must agree"
                    % (name, line_of(source, offset), label, body)
                )

    for s in series:
        for end in ("first", "last"):
            for role in ("name", "rank"):
                if (s.name, end, role) not in bound:
                    findings.append(
                        "%s:%d: series %r prints no %s %s label — a bump chart "
                        "labels each series where it enters and where it leaves, or "
                        "the reader traces a line to an unlabelled end"
                        % (name, line_of(source, s.offset), s.name, end, role)
                    )

    # Every label sharing an end and a role is one gutter, so the figure
    # declares its own gutter x the way it declares its own rank grid: by
    # agreement across series, with no constant written down here. The
    # inboard test above catches a label dragged across its endpoint; this
    # catches one slid the other way, which stays outboard and keeps its row.
    # How far out the gutter as a whole sits is a layout question and belongs
    # to lint-render.py - this gate only requires that there BE one gutter.
    for (end, role), placed in sorted(gutters.items()):
        if len(placed) < 2:
            continue
        tally = {}
        for x, _, _ in placed:
            tally[x] = tally.get(x, 0) + 1
        gutter = max(sorted(tally), key=lambda value: tally[value])
        for x, label, offset in placed:
            if abs(x - gutter) > GRID_TOLERANCE:
                findings.append(
                    "%s:%d: the %s %s label for series %r is drawn at x=%g, off "
                    "the x=%g gutter its %d peers share — one label out of "
                    "column points at a snapshot of its own"
                    % (name, line_of(source, offset), end, role, label, x,
                       gutter, tally[gutter])
                )


def check_captions(series: list, source: str, findings: list, name: str) -> None:
    """One caption per snapshot column, on its column, text bound by data-state."""
    columns = [x for x, _ in series[0].points]
    seen = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        axis = attrs.get("data-axis")
        if axis is None:
            continue
        if not axis.isdigit() or not 0 <= int(axis) < len(columns):
            findings.append(
                "%s:%d: a snapshot caption has data-axis=%r, which is not a column "
                "index 0..%d" % (name, line_of(source, match.start()), axis,
                                 len(columns) - 1)
            )
            continue
        index = int(axis)
        if index in seen:
            findings.append(
                "%s:%d: a second caption for snapshot %d — one column, one caption"
                % (name, line_of(source, match.start()), index + 1)
            )
            continue
        seen[index] = (number(attrs.get("x")), plain(match.group("body")),
                       attrs.get("data-state"), match.start())

    labels = []
    for index in range(len(columns)):
        if index not in seen:
            findings.append(
                "%s: no caption for snapshot %d (data-axis=\"%d\") — unbound "
                "captions can be swapped, which redraws when everything happened"
                % (name, index + 1, index)
            )
            continue
        x, body, declared, offset = seen[index]
        if x is None or abs(x - columns[index]) > CAPTION_TOLERANCE:
            findings.append(
                "%s:%d: the caption for snapshot %d (%r) is drawn at x=%s but its "
                "column is at x=%g — a caption off its column renames the moment"
                % (name, line_of(source, offset), index + 1, body[:20],
                   "%g" % x if x is not None else "?", columns[index])
            )
        if declared is None:
            findings.append(
                "%s:%d: the caption for snapshot %d (%r) has no data-state — its "
                "visible text is unbound, so it can be exchanged with another "
                "caption and nothing here would notice"
                % (name, line_of(source, offset), index + 1, body[:20])
            )
        elif body != declared:
            findings.append(
                "%s:%d: the caption for snapshot %d reads %r but declares "
                "data-state=%r — the visible caption and its binding must agree"
                % (name, line_of(source, offset), index + 1, body[:20], declared)
            )
        labels.append(body)
    if len(labels) == len(columns) and len(set(labels)) != len(labels):
        findings.append(
            "%s: two snapshot captions read the same — two moments the reader "
            "cannot tell apart is not an ordering" % name
        )


def check_source(path: Path, raw: str) -> list:
    source = blank_comments(raw)
    findings: list = []
    series = parse_series(source, findings, path.name)

    if len(series) < 2:
        findings.append(
            "%s: presents as a bump chart but declares %d verifiable series — every "
            "ranked line needs data-series with data-ranks. Refusing to report OK "
            "on a file this checker could not read" % (path.name, len(series))
        )
        return findings

    if len(series) > MAX_SERIES:
        findings.append(
            "%s: %d series against a budget of %d — past that the crossings stop "
            "being readable and the figure becomes spaghetti with a legend"
            % (path.name, len(series), MAX_SERIES)
        )
    elif len(series) < MIN_SERIES:
        findings.append(
            "%s: %d series against a budget of %d-%d — below %d a sentence or a "
            "pair of slopes says it shorter, and rank stops being a crowd worth "
            "charting"
            % (path.name, len(series), MIN_SERIES, MAX_SERIES, MIN_SERIES)
        )
    columns = len(series[0].points)
    if not MIN_SNAPSHOTS <= columns <= MAX_SNAPSHOTS:
        findings.append(
            "%s: %d snapshots against a budget of %d-%d — two snapshots are a "
            "slopegraph, and past %d the columns compress until rank changes "
            "cannot be followed"
            % (path.name, columns, MIN_SNAPSHOTS, MAX_SNAPSHOTS, MAX_SNAPSHOTS)
        )

    check_transforms(source, findings, path.name)
    check_columns(series, findings, source, path.name)
    check_grid(series, findings, source, path.name)
    check_dots(series, source, findings, path.name)
    check_focus(series, findings, source, path.name)
    check_labels(series, source, findings, path.name)
    check_captions(series, source, findings, path.name)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify bump chart positions against the ranks they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a bump chart",
    )
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    if args.all:
        targets = sorted(ASSET_DIR.glob("example-*.html"))
    else:
        targets = [Path(p) for p in args.paths]

    findings: list = []
    checked = 0
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
        if not looks_like_bump(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d bump finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK bump: no bump chart found to check%s" % tail)
        return 0
    print("OK bump: %d file(s), every vertex exactly on one rank grid, every "
          "snapshot a permutation, straight segments only, and every printed rank, "
          "name and caption bound to what it describes%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
