#!/usr/bin/env python3
"""Verify that a ridgeline chart's drawn ridges match the bins they declare.

A ridgeline makes one claim above all others: **every ridge is drawn at the same
amplitude**. The whole type exists so silhouettes can be compared down a column,
and per-ridge normalisation destroys exactly that while rendering beautifully -
a rare, flat distribution given its own scale wears the same shape as a tight
one, and no other gate in this repo would notice. `lint-skin.py` reads colours
and fonts, `verify-geometry.py` reads label masks; neither compares a drawn
outline against the values sitting in the markup.

Eight invariants, in the spirit of ADR 0005 and the slopegraph checker:

1. ONE AMPLITUDE - one figure-wide px-per-unit, derived from the figure itself
   (median of (baseline - y) / value over nonzero bins, so a single dishonest
   ridge cannot drag the scale it is measured against) and then enforced on
   every vertex of every ridge. This is the invariant the type lives on.

2. EVEN PITCH - baselines run strictly downward at one fixed pitch, and each
   ridge's declared data-baseline is the row it is actually drawn against. A
   baseline nudged to give one ridge more headroom is the same lie as a private
   amplitude, told with different arithmetic.

3. SHARED BINS - every ridge samples the same x positions in the same order, so
   a peak at one x means the same latency on every row.

4. CLOSED BY ZERO - the outline is absolute M/L*/Z, one point per declared bin,
   with the first and last bin at zero so the shape starts and ends on its own
   baseline. No vertex may sit below the baseline: a negative share is not a
   share, and a clipped end is a distribution cut off mid-mass.

5. NO SMOOTHING - straight segments only. A spline through binned counts invents
   extrema the sample never had, and the footnote states the drawing is
   unsmoothed. Relative commands are REFUSED rather than folded into their
   absolute twins - `l30,-62` renders against the previous point while the
   numbers this checker reads look absolute, so accepting them would certify a
   figure at positions it never drew. Lowercase `z` is the one exception and is
   accepted: closepath takes no coordinates, so it has no relative form. One
   explicit command per vertex is required — implicit repetition after an L is
   legal SVG but would leave commands paired with the wrong coordinates here.

6. OVERLAP WITHOUT OCCLUSION - overlap is a feature of the type; a peak hidden
   behind a peak is not. No ridge may rise past the baseline two rows above it.
   The fix for a collision is more pitch, never a smaller amplitude on one ridge.

7. LABELS BOUND TO MEANING - each ridge prints its name and its range, bound by
   data-ridge / data-role, sitting on its own baseline row, with the name
   agreeing with its binding and the printed range agreeing with the first and
   last nonzero bin read through the figure's own tick scale.

8. FAIL CLOSED - zero parseable ridges, a path that declares data-bins but
   cannot be read, a missing baseline rule, or a transform anywhere near
   verified geometry is a finding, never a skip.

WHAT THIS DOES NOT CHECK, deliberately:

- **What the values mean.** Share, density or count, and how the bins were cut -
  that is the source line's job, and prose is not parsed. Every check here is
  internal consistency between the markup and the drawing.
- **The tone ramp.** Fill and stroke opacity are `lint-skin.py`'s territory;
  this gate only pairs the accent with its stroke weight.

SCOPE: this contract binds `data-bins` on a `<path>`, which no other chart in
this repo declares. `data-series` (slopegraph), `data-ranks` (bump) and
`data-layer` (streamgraph) are their checkers' vocabulary and are not read here,
so the sibling gates and this one never claim the same file.

Usage:
    python3 scripts/verify-ridgeline.py --all
    python3 scripts/verify-ridgeline.py skills/diagram-design/assets/example-ridgeline.html

Exit: 0 clean, 1 findings, 2 usage.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "skills/diagram-design/assets"

PATH_RE = re.compile(r"<path\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
LINE_RE = re.compile(r"<line\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE)
TEXT_RE = re.compile(r"<text\b(?P<attrs>[^>]*)>(?P<body>.*?)</text>", re.IGNORECASE | re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
NAMED_RE = re.compile(r"<(?P<tag>title|desc)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
                      re.IGNORECASE | re.DOTALL)
GROUP_OPEN_RE = re.compile(r"<(?:g|svg)\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>", re.IGNORECASE)
GROUP_CLOSE_RE = re.compile(r"</(?:g|svg)\s*>", re.IGNORECASE)
STYLE_RE = re.compile(r"<style\b[^>]*>(?P<body>.*?)</style>", re.IGNORECASE | re.DOTALL)
# `transform:` but not `text-transform:` - the editorial template uses the latter.
CSS_TRANSFORM_RE = re.compile(r"(?<![\w-])transform\s*:", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
# Both quote styles, for the same reason verify-slopegraph gives: a
# single-quoted attribute must be read, not silently dropped from the set.
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
DECLARES_BINS_RE = re.compile(r"\bdata-bins\s*=", re.IGNORECASE)
NUM_RE = re.compile(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")
# Path-data tokens, number branch FIRST so an exponent's `e` is consumed as part
# of its number instead of being read as a command. See parse_d.
D_TOKEN_RE = re.compile(
    r"(?P<num>[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"|(?P<cmd>[A-Za-z])"
    r"|(?P<sep>[\s,]+)"
    r"|(?P<junk>[\s\S])"
)
# En dash or hyphen, because a range printed with either reads the same.
RANGE_LABEL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*[–-]\s*(\d+(?:\.\d+)?)\s*(\S.*)?$")

# The shipped coordinates carry one decimal, so a vertex can sit 0.05px from
# its true position honestly. Everything past that is an edit.
AMPLITUDE_TOLERANCE = 0.06   # px, a vertex against the figure's one amplitude
PITCH_TOLERANCE = 0.01       # px, a baseline against the derived pitch
BIN_TOLERANCE = 0.01         # px, a ridge's x samples against the shared bins
RULE_TOLERANCE = 0.5         # px, a baseline rule against its row and the bin run
TICK_TOLERANCE = 0.5         # px, a tick caption against a bin position
SCALE_TOLERANCE = 0.5        # in x-axis units, a printed range against its bin
LABEL_ROW_OFFSET = 3.5       # px, a label baseline below its row, per the reference
MIN_RIDGES, MAX_RIDGES = 3, 12
MIN_BINS, MAX_BINS = 8, 40
FOCAL_WIDTH, PLAIN_WIDTH = 2.4, 1.2
ACCENTS = {"#eb6c36", "#f08a59"}   # light and dark skin accent tokens


class Ridge:
    __slots__ = ("name", "values", "points", "baseline", "stroke", "width", "offset")

    def __init__(self, name, values, points, baseline, stroke, width, offset):
        self.name = name
        self.values = values
        self.points = points
        self.baseline = baseline
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
    if value is None:
        return None
    match = NUM_RE.fullmatch(value.strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


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


def median(values):
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def looks_like_ridgeline(path: Path, source: str) -> bool:
    """Does this file present itself as a ridgeline?

    Generous on the vocabulary this contract binds: `data-bins` belongs to no
    other chart in this repo, so any file declaring it is held to the contract
    even if nothing else parses - that combination is the fail-closed case.
    """
    if path.name.startswith("example-ridgeline"):
        return True
    if DECLARES_BINS_RE.search(source):
        return True
    described = named_text(source)
    return any(word in described for word in ("ridgeline", "ridge line", "joyplot"))


def parse_d(d: str):
    """(commands, points) for a closed polygon path, or (None, None).

    Tokenised left to right with numbers tried BEFORE letters, because `e` and
    `E` are letters inside a valid coordinate: `3.5e2` is one number, not a
    number followed by an `e` command. Scanning for `[A-Za-z]` separately would
    invent that command and then reject a perfectly good path for having one
    token too many. A letter that survives the number branch is a real command
    (and is held to the M/L/Z vocabulary by the caller); anything else makes the
    path unreadable, which is a finding rather than a skip.
    """
    commands, numbers = [], []
    for match in D_TOKEN_RE.finditer(d):
        kind = match.lastgroup
        if kind == "num":
            try:
                numbers.append(float(match.group()))
            except ValueError:
                return None, None
        elif kind == "cmd":
            commands.append(match.group())
        elif kind == "junk":
            return None, None
    if len(numbers) % 2 != 0:
        return None, None
    points = list(zip(numbers[0::2], numbers[1::2]))
    return commands, points


def parse_ridges(source: str, findings: list, name: str) -> list:
    ridges = []
    seen = set()
    for match in PATH_RE.finditer(source):
        raw = match.group("attrs")
        attrs = attrs_of(raw)
        label = attrs.get("data-ridge")
        if label is None:
            # A <path> with no data-ridge is scenery. One whose raw text DOES
            # declare data-bins and still parsed to nothing is markup this
            # checker could not read, which is a finding rather than scenery.
            if DECLARES_BINS_RE.search(raw):
                findings.append(
                    "%s:%d: a <path> declares data-bins but no data-ridge — a "
                    "distribution outline must say whose distribution it draws, or "
                    "its labels cannot be bound to it"
                    % (name, line_of(source, match.start()))
                )
            continue
        if label in seen:
            findings.append(
                "%s:%d: a second path declares data-ridge=%r — one ridge, one "
                "outline, or the reader has two shapes and no way to pick"
                % (name, line_of(source, match.start()), label)
            )
            continue
        seen.add(label)
        bins_raw = attrs.get("data-bins")
        if bins_raw is None:
            findings.append(
                "%s:%d: ridge %r declares data-ridge but no data-bins — the declared "
                "bins are the basis every drawn vertex is verified against, so an "
                "outline without them cannot be checked"
                % (name, line_of(source, match.start()), label)
            )
            continue
        values = [number(token) for token in bins_raw.split(",")]
        if not values or any(v is None for v in values):
            findings.append(
                "%s:%d: ridge %r has data-bins=%r, which is not a comma list of "
                "numbers" % (name, line_of(source, match.start()), label, bins_raw)
            )
            continue
        if any(v < 0 for v in values):
            findings.append(
                "%s:%d: ridge %r declares a negative bin — a share of requests below "
                "zero is not a share, and it would draw below the baseline"
                % (name, line_of(source, match.start()), label)
            )
            continue
        baseline = number(attrs.get("data-baseline"))
        if baseline is None:
            findings.append(
                "%s:%d: ridge %r has no data-baseline — the baseline is the zero of "
                "this ridge's amplitude, so an unstated one can be moved to give the "
                "ridge headroom and nothing here would notice"
                % (name, line_of(source, match.start()), label)
            )
            continue
        commands, points = parse_d(attrs.get("d", ""))
        if commands is None or not points:
            findings.append(
                "%s:%d: ridge %r has a path this checker cannot read — cannot verify "
                "its outline" % (name, line_of(source, match.start()), label)
            )
            continue
        # Absolute M + L* + Z is the entire permitted grammar. A relative
        # command is refused rather than folded into its absolute twin: it
        # renders against the previous point while the numbers parsed here read
        # as absolute coordinates, so folding case would certify positions the
        # figure never drew. `z` is the one exception and is NOT relative -
        # closepath takes no coordinates, so it has no relative form and the two
        # spellings are the same command.
        if any(c.islower() and c != "z" for c in commands):
            findings.append(
                "%s:%d: ridge %r uses relative path commands (%s) — a relative "
                "coordinate renders against the previous point, so the numbers this "
                "checker reads are not where the outline lands. Write the path in "
                "absolute M/L/Z commands"
                % (name, line_of(source, match.start()), label, "/".join(commands))
            )
            continue
        commands = ["Z" if c == "z" else c for c in commands]
        # The vocabulary first, so a curve is reported as a curve. A C/S/Q/A
        # command also carries control points, which would otherwise trip the
        # count rule below and hide the real defect behind an arithmetic one.
        if set(commands) - {"M", "L", "Z"}:
            findings.append(
                "%s:%d: ridge %r draws %s — a ridgeline joins adjacent bins with "
                "straight segments and closes with Z. A spline through binned counts "
                "invents extrema the sample never had, and the source line states the "
                "drawing is unsmoothed"
                % (name, line_of(source, match.start()), label, "/".join(commands))
            )
            continue
        # One command letter per point. SVG lets `L` take repeated coordinate
        # pairs, and that shorthand is legal - but this checker pairs commands
        # with points positionally, so it is required to be written out rather
        # than silently mis-paired.
        if len(commands) != len(points) + 1:
            findings.append(
                "%s:%d: ridge %r writes %d path command(s) for %d point(s) — this "
                "contract needs one explicit command per vertex (implicit repetition "
                "after an L is legal SVG but leaves the checker pairing commands with "
                "the wrong coordinates). Write M, then one L per bin, then Z"
                % (name, line_of(source, match.start()), label,
                   len(commands), len(points))
            )
            continue
        expected = ["M"] + ["L"] * (len(points) - 1) + ["Z"]
        if commands != expected:
            findings.append(
                "%s:%d: ridge %r draws %s — the outline opens with one M, walks the "
                "bins with L, and closes with a single Z. A second subpath or a "
                "mid-path M lifts the pen inside one distribution"
                % (name, line_of(source, match.start()), label, "/".join(commands))
            )
            continue
        if len(points) != len(values):
            findings.append(
                "%s:%d: ridge %r declares %d bins but draws %d points — every declared "
                "bin needs its vertex and every vertex its bin"
                % (name, line_of(source, match.start()), label, len(values), len(points))
            )
            continue
        width = number(attrs.get("stroke-width"))
        ridges.append(Ridge(label, values, points, baseline,
                            (attrs.get("stroke") or "").strip().lower(),
                            width, match.start()))
    return ridges


def transformed_spans(source: str) -> list:
    events = []
    for match in GROUP_OPEN_RE.finditer(source):
        if match.group("selfclose"):
            continue
        attrs = attrs_of(match.group("attrs"))
        events.append((match.start(), "open", "transform" in attrs))
    for match in GROUP_CLOSE_RE.finditer(source):
        events.append((match.start(), "close", False))
    events.sort()
    spans, stack = [], []
    for position, kind, transformed in events:
        if kind == "open":
            stack.append((position, transformed))
        elif stack:
            start, was_transformed = stack.pop()
            if was_transformed:
                spans.append((start, position))
    for start, was_transformed in stack:
        if was_transformed:
            spans.append((start, len(source)))
    return spans


def check_transforms(source: str, findings: list, name: str) -> None:
    """No transform may move verified geometry or a bound label."""
    spans = transformed_spans(source)

    def enclosed(offset):
        return any(start <= offset <= end for start, end in spans)

    def report(offset, what, how):
        findings.append(
            "%s:%d: %s carries %s — this checker validates raw coordinates, so a "
            "transform moves the rendered mark away from the bin it was checked "
            "against. Bake the offset into the coordinates instead"
            % (name, line_of(source, offset), what, how)
        )

    for pattern, key in ((PATH_RE, "data-ridge"), (LINE_RE, "data-ridge")):
        for match in pattern.finditer(source):
            attrs = attrs_of(match.group("attrs"))
            if key not in attrs:
                continue
            what = "ridge %r" % attrs[key]
            if "transform" in attrs:
                report(match.start(), what, "transform=%r" % attrs["transform"])
            elif enclosed(match.start()):
                report(match.start(), what, "an ancestor <g>/<svg> transform")

    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if "data-ridge" not in attrs and "data-tick" not in attrs:
            continue
        what = "a bound label (%s)" % plain(match.group("body"))[:20]
        if "transform" in attrs:
            report(match.start(), what, "transform=%r" % attrs["transform"])
        elif enclosed(match.start()):
            report(match.start(), what, "an ancestor <g>/<svg> transform")

    for match in STYLE_RE.finditer(source):
        found = CSS_TRANSFORM_RE.search(match.group("body"))
        if found:
            findings.append(
                "%s:%d: a CSS `transform` declaration — this checker cannot tell "
                "which marks it applies to, and a transform on verified geometry "
                "invalidates every coordinate here"
                % (name, line_of(source, match.start("body") + found.start()))
            )


def check_bins(ridges: list, findings: list, source: str, name: str) -> bool:
    """Every ridge samples the same x positions, in increasing order."""
    reference = [round(x, 3) for x, _ in ridges[0].points]
    if sorted(set(reference)) != reference:
        findings.append(
            "%s:%d: ridge %r samples x=%s, which is not strictly increasing — bins "
            "are ordered, and an x visited twice or out of order redraws the scale"
            % (name, line_of(source, ridges[0].offset), ridges[0].name,
               "/".join("%g" % x for x in reference[:6]) + "…")
        )
        return False
    shared = True
    for r in ridges[1:]:
        xs = [round(x, 3) for x, _ in r.points]
        if len(xs) != len(reference) or any(
            abs(a - b) > BIN_TOLERANCE for a, b in zip(xs, reference)
        ):
            findings.append(
                "%s:%d: ridge %r samples its own x positions — every ridge must share "
                "one x-scale or a peak at one x stops meaning one latency"
                % (name, line_of(source, r.offset), r.name)
            )
            shared = False
    return shared


def check_baselines(ridges: list, source: str, findings: list, name: str):
    """Baselines strictly downward at one pitch, each with its drawn rule.

    Returns the derived pitch, or None when the rows could not be read.
    """
    ordered = sorted(ridges, key=lambda r: r.baseline)
    rows = [r.baseline for r in ordered]
    if len(set(rows)) != len(rows):
        findings.append(
            "%s: two ridges declare the same baseline — ridges are stacked, and two "
            "sharing a row is one ridge drawn over another" % name
        )
        return None
    pitch = (rows[-1] - rows[0]) / (len(rows) - 1)
    if pitch <= 0:
        findings.append(
            "%s: no downward baseline pitch could be derived — refusing to report OK "
            "on a stack this checker could not read" % name
        )
        return None
    for index, r in enumerate(ordered):
        expected = rows[0] + index * pitch
        if abs(r.baseline - expected) > PITCH_TOLERANCE:
            findings.append(
                "%s:%d: ridge %r sits on a baseline at y=%g, but a fixed pitch of %g "
                "puts row %d at y=%g — an unevenly pitched stack reads relative "
                "amplitude wrong, and a row nudged for headroom is the same lie as a "
                "private scale"
                % (name, line_of(source, r.offset), r.name, r.baseline, pitch,
                   index + 1, expected)
            )

    # Each ridge's outline must actually start and end on its own baseline.
    for r in ridges:
        for end, (_, y) in (("first", r.points[0]), ("last", r.points[-1])):
            if abs(y - r.baseline) > AMPLITUDE_TOLERANCE:
                findings.append(
                    "%s:%d: ridge %r starts or ends off its baseline (%s vertex at "
                    "y=%g, baseline y=%g) — the outline closes along the baseline, so "
                    "a distribution cut off mid-mass would be drawn as a cliff and "
                    "read as data"
                    % (name, line_of(source, r.offset), r.name, end, y, r.baseline)
                )
        for _, y in r.points:
            if y - r.baseline > AMPLITUDE_TOLERANCE:
                findings.append(
                    "%s:%d: ridge %r draws a vertex at y=%g, below its own baseline "
                    "y=%g — a ridge rises from its baseline and never dips through it"
                    % (name, line_of(source, r.offset), r.name, y, r.baseline)
                )
                break

    # One drawn rule per ridge, on its row, spanning the bin run.
    x_first = min(x for x, _ in ridges[0].points)
    x_last = max(x for x, _ in ridges[0].points)
    rules = {}
    for match in LINE_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        if attrs.get("data-role") != "baseline":
            continue
        label = attrs.get("data-ridge")
        if label is None:
            findings.append(
                "%s:%d: a baseline rule declares no data-ridge — an unbound rule can "
                "be moved off the row it belongs to and nothing here would notice"
                % (name, line_of(source, match.start()))
            )
            continue
        rules[label] = (attrs, match.start())

    declared = {r.name: r for r in ridges}
    for label, (attrs, offset) in sorted(rules.items(), key=lambda item: item[1][1]):
        if label not in declared:
            findings.append(
                "%s:%d: a baseline rule names ridge %r, which no path declares — a "
                "rule with no ridge reads as a row that is not there"
                % (name, line_of(source, offset), label)
            )
            continue
        r = declared[label]
        y1, y2 = number(attrs.get("y1")), number(attrs.get("y2"))
        rx1, rx2 = number(attrs.get("x1")), number(attrs.get("x2"))
        if y1 is None or y2 is None or abs(y1 - y2) > RULE_TOLERANCE:
            findings.append(
                "%s:%d: the baseline rule for ridge %r is not horizontal — a sloped "
                "baseline makes every amplitude on that row a different number"
                % (name, line_of(source, offset), label)
            )
            continue
        if abs(y1 - r.baseline) > RULE_TOLERANCE:
            findings.append(
                "%s:%d: the baseline rule for ridge %r is drawn at y=%g but the ridge "
                "declares its baseline at y=%g — the drawn zero and the measured zero "
                "must be one line" % (name, line_of(source, offset), label, y1, r.baseline)
            )
        if rx1 is None or rx2 is None \
                or abs(min(rx1, rx2) - x_first) > RULE_TOLERANCE \
                or abs(max(rx1, rx2) - x_last) > RULE_TOLERANCE:
            findings.append(
                "%s:%d: the baseline rule for ridge %r does not span the bin run "
                "(x=%g to x=%g) — a short rule reads as a narrower support than the "
                "ridge was sampled over"
                % (name, line_of(source, offset), label, x_first, x_last))

    for r in ridges:
        if r.name not in rules:
            findings.append(
                "%s:%d: ridge %r has no baseline rule (a <line> with data-ridge and "
                "data-role=\"baseline\") — the baseline is where a zero bin sits, and "
                "an undrawn one leaves the reader estimating the zero of every "
                "amplitude" % (name, line_of(source, r.offset), r.name)
            )
    return pitch


def check_amplitude(ridges: list, findings: list, source: str, name: str) -> None:
    """One figure-wide amplitude, derived robustly then enforced exactly."""
    # Median of PER-RIDGE medians, not of every vertex pooled. Pooling would let
    # one ridge with many nonzero bins outvote several honest ridges with few,
    # so the figure's scale would be derived from the very ridge under suspicion.
    # One ridge per vote makes a single private amplitude a minority by
    # construction whenever the figure has three or more ridges.
    samples = []
    for r in ridges:
        own = [(r.baseline - y) / value
               for value, (_, y) in zip(r.values, r.points) if value > 0]
        if own:
            samples.append(median(own))
    if not samples:
        findings.append(
            "%s: every declared bin is zero — there is no amplitude to verify, and a "
            "figure of five flat lines is not a ridgeline. Refusing to report OK" % name
        )
        return
    amplitude = median(samples)
    if amplitude <= 0:
        findings.append(
            "%s: the figure's amplitude derives as %g — a ridge rises from its "
            "baseline, so amplitude is positive by construction. Refusing to report "
            "OK on a scale this checker could not read" % (name, amplitude)
        )
        return
    for r in ridges:
        for value, (x, y) in zip(r.values, r.points):
            expected = r.baseline - amplitude * value
            if abs(y - expected) > AMPLITUDE_TOLERANCE:
                findings.append(
                    "%s:%d: ridge %r draws its %g bin at x=%g, y=%g, but the figure's "
                    "one amplitude (%.4gpx per unit) puts it at y=%g — a ridge on its "
                    "own scale wears a silhouette it did not earn, which is the one "
                    "lie this type is built to tell"
                    % (name, line_of(source, r.offset), r.name, value, x, y,
                       amplitude, expected)
                )
                break


def check_overlap(ridges: list, pitch, findings: list, source: str, name: str) -> None:
    """Overlap is a feature; a peak hidden behind a peak is not."""
    if pitch is None:      # the stack could not be read; check_baselines said so
        return
    for r in ridges:
        intrusion = r.baseline - min(y for _, y in r.points)
        if intrusion >= 2 * pitch:
            findings.append(
                "%s:%d: ridge %r rises %gpx above its baseline, past the row two above "
                "it (pitch %gpx) — overlap is how a ridgeline reads as depth, but a "
                "peak reaching that far is occluded by the peaks it passes. Increase "
                "the pitch; never shrink one ridge's amplitude to fit"
                % (name, line_of(source, r.offset), r.name, intrusion, pitch)
            )


def check_focus(ridges: list, findings: list, source: str, name: str) -> None:
    """Exactly one accent ridge, with stroke weight agreeing with stroke colour."""
    focal = [r for r in ridges if r.focal]
    if len(focal) != 1:
        findings.append(
            "%s: %d ridges carry the accent stroke — the accent marks exactly one "
            "editorially focal distribution, and spending it twice spends it entirely"
            % (name, len(focal))
        )
    for r in ridges:
        want = FOCAL_WIDTH if r.focal else PLAIN_WIDTH
        if r.width is None or abs(r.width - want) > 1e-9:
            findings.append(
                "%s:%d: ridge %r has stroke-width=%s but a %s ridge takes %g — weight "
                "is the focus cue that survives greyscale, so a mismatch between "
                "colour and weight sends the two cues to different ridges"
                % (name, line_of(source, r.offset), r.name,
                   "%g" % r.width if r.width is not None else "?",
                   "focal" if r.focal else "non-focal", want)
            )


def check_ticks(ridges: list, source: str, findings: list, name: str):
    """Bin ticks bound to their printed value, on bin positions, one linear scale.

    Returns a callable mapping x to an axis value, or None when the scale could
    not be read - in which case the range labels are reported as unverifiable
    rather than silently passed.
    """
    bin_xs = [x for x, _ in ridges[0].points]
    seen = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        index = attrs.get("data-tick")
        if index is None:
            continue
        body = plain(match.group("body"))
        if not index.isdigit():
            findings.append(
                "%s:%d: a bin tick has data-tick=%r, which is not a tick index"
                % (name, line_of(source, match.start()), index)
            )
            continue
        position = int(index)
        if position in seen:
            findings.append(
                "%s:%d: a second tick with data-tick=%r — one tick, one caption"
                % (name, line_of(source, match.start()), index)
            )
            continue
        declared = number(attrs.get("data-bin"))
        if declared is None:
            findings.append(
                "%s:%d: the tick reading %r has no data-bin — its visible text is "
                "unbound, so it can be exchanged with another tick and nothing here "
                "would notice" % (name, line_of(source, match.start()), body[:20])
            )
            continue
        printed = number(body)
        if printed is None or abs(printed - declared) > 1e-9:
            findings.append(
                "%s:%d: the tick at data-bin=%g prints %r — the visible caption and "
                "its binding must state one number"
                % (name, line_of(source, match.start()), declared, body[:20])
            )
            continue
        x = number(attrs.get("x"))
        if x is None or not any(abs(x - bx) <= TICK_TOLERANCE for bx in bin_xs):
            findings.append(
                "%s:%d: the tick reading %r is drawn at x=%s, which is not a bin "
                "position — a tick off the bins labels a latency the figure never "
                "sampled" % (name, line_of(source, match.start()), body[:20],
                             "%g" % x if x is not None else "?")
            )
            continue
        seen[position] = (x, declared, match.start())

    if len(seen) < 2:
        findings.append(
            "%s: %d readable bin tick(s) — a shared x-scale is only shared if it is "
            "printed, and two ticks are the minimum that fixes one" % (name, len(seen))
        )
        return None

    ordered = [seen[k] for k in sorted(seen)]
    (x0, v0, _), (xn, vn, _) = ordered[0], ordered[-1]
    if abs(xn - x0) < 1e-9:
        findings.append(
            "%s: two bin ticks share an x position — a scale needs two distinct "
            "points" % name
        )
        return None
    slope = (vn - v0) / (xn - x0)
    for x, value, offset in ordered:
        if abs((v0 + slope * (x - x0)) - value) > SCALE_TOLERANCE:
            findings.append(
                "%s:%d: the tick at x=%g reads %g, off the straight line the other "
                "ticks set — a non-linear x-axis makes every printed range a "
                "different distance" % (name, line_of(source, offset), x, value)
            )
            return None
    return lambda x: v0 + slope * (x - x0)


def check_labels(ridges: list, source: str, findings: list, name: str, scale) -> None:
    """Name and range printed per ridge, bound, agreeing, and on its own row."""
    bound = {}
    for match in TEXT_RE.finditer(source):
        attrs = attrs_of(match.group("attrs"))
        label = attrs.get("data-ridge")
        if label is None:
            continue
        role = attrs.get("data-role")
        key = (label, role)
        if key in bound:
            findings.append(
                "%s:%d: a second %s label for ridge %r — one label per binding, or a "
                "reader has two statements and no way to pick"
                % (name, line_of(source, match.start()), role, label)
            )
            continue
        bound[key] = (plain(match.group("body")), number(attrs.get("y")), match.start())

    declared = {r.name: r for r in ridges}
    for (label, role), (body, y, offset) in sorted(bound.items(),
                                                   key=lambda item: item[1][2]):
        if label not in declared:
            findings.append(
                "%s:%d: a %s label names ridge %r, which no path declares — a label "
                "with no mark is not verifiable and reads as data"
                % (name, line_of(source, offset), role, label)
            )
            continue
        if role not in ("name", "range"):
            findings.append(
                "%s:%d: a label for ridge %r has data-role=%r, which is neither "
                "'name' nor 'range'" % (name, line_of(source, offset), label, role)
            )
            continue
        r = declared[label]
        # Row placement: nearer another ridge's baseline than its own means the
        # label renames a distribution, with every number still correct.
        if y is not None:
            own = abs(y - (r.baseline + LABEL_ROW_OFFSET))
            for other in ridges:
                if other.name == label:
                    continue
                if abs(y - (other.baseline + LABEL_ROW_OFFSET)) < own:
                    findings.append(
                        "%s:%d: the %s label for ridge %r is drawn at y=%g, nearer "
                        "%r's baseline than its own — a label on the wrong row renames "
                        "the distribution"
                        % (name, line_of(source, offset), role, label, y, other.name)
                    )
                    break
        if role == "name":
            if body != label:
                findings.append(
                    "%s:%d: a name label bound to ridge %r reads %r — the visible name "
                    "and its binding must agree"
                    % (name, line_of(source, offset), label, body)
                )
            continue

        match = RANGE_LABEL_RE.match(body)
        if not match:
            findings.append(
                "%s:%d: ridge %r prints its range as %r — a range label is two numbers "
                "on the x-axis scale, low to high, so the reader can place the mass "
                "without a gridline" % (name, line_of(source, offset), label, body)
            )
            continue
        if scale is None:
            findings.append(
                "%s:%d: ridge %r prints the range %r, which this checker cannot verify "
                "because the figure's bin ticks did not read as one scale"
                % (name, line_of(source, offset), label, body)
            )
            continue
        live = [i for i, v in enumerate(r.values) if v > 0]
        if not live:
            findings.append(
                "%s:%d: ridge %r prints a range but declares no nonzero bin — an "
                "empty distribution has no range"
                % (name, line_of(source, offset), label)
            )
            continue
        want_low = scale(r.points[live[0]][0])
        want_high = scale(r.points[live[-1]][0])
        low, high = float(match.group(1)), float(match.group(2))
        if low > high:
            findings.append(
                "%s:%d: ridge %r prints the range %r low end first — %g is above %g"
                % (name, line_of(source, offset), label, body, low, high)
            )
            continue
        if abs(low - want_low) > SCALE_TOLERANCE or abs(high - want_high) > SCALE_TOLERANCE:
            findings.append(
                "%s:%d: ridge %r prints the range %r but its nonzero bins run %g to %g "
                "on the figure's own tick scale — a stated range wider than the mass "
                "claims support the bins do not show, and a narrower one hides the "
                "tail this chart exists to make visible"
                % (name, line_of(source, offset), label, body, want_low, want_high)
            )

    for r in ridges:
        for role in ("name", "range"):
            if (r.name, role) not in bound:
                findings.append(
                    "%s:%d: ridge %r prints no %s label — a ridgeline names each ridge "
                    "beside its baseline and states the span of its mass, or the "
                    "reader has a silhouette and no numbers"
                    % (name, line_of(source, r.offset), r.name, role)
                )


def check_source(path: Path, raw: str) -> list:
    source = blank_comments(raw)
    findings: list = []
    ridges = parse_ridges(source, findings, path.name)

    if len(ridges) < 2:
        findings.append(
            "%s: presents as a ridgeline but declares %d verifiable ridge(s) — every "
            "distribution needs data-ridge with data-bins and data-baseline. Refusing "
            "to report OK on a file this checker could not read"
            % (path.name, len(ridges))
        )
        return findings

    if len(ridges) > MAX_RIDGES:
        findings.append(
            "%s: %d ridges against a budget of %d — past that the stack is taller than "
            "a reader can hold one silhouette in mind across"
            % (path.name, len(ridges), MAX_RIDGES)
        )
    elif len(ridges) < MIN_RIDGES:
        findings.append(
            "%s: %d ridges against a budget of %d-%d — below %d there is no family of "
            "shapes to compare, and two distributions are a pair of small multiples"
            % (path.name, len(ridges), MIN_RIDGES, MAX_RIDGES, MIN_RIDGES)
        )
    bins = len(ridges[0].values)
    if not MIN_BINS <= bins <= MAX_BINS:
        findings.append(
            "%s: %d bins against a budget of %d-%d — below %d the outline is a "
            "histogram wearing a curve's clothes, and past %d the bins are narrower "
            "than the noise in them"
            % (path.name, bins, MIN_BINS, MAX_BINS, MIN_BINS, MAX_BINS)
        )

    check_transforms(source, findings, path.name)
    shared = check_bins(ridges, findings, source, path.name)
    pitch = check_baselines(ridges, source, findings, path.name)
    check_amplitude(ridges, findings, source, path.name)
    check_overlap(ridges, pitch, findings, source, path.name)
    check_focus(ridges, findings, source, path.name)
    scale = check_ticks(ridges, source, findings, path.name) if shared else None
    check_labels(ridges, source, findings, path.name, scale)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify ridgeline outlines against the bins they declare."
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument(
        "--all", action="store_true",
        help="check every shipped example that presents as a ridgeline",
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
        if not looks_like_ridgeline(path, raw):
            skipped += 1
            continue
        findings.extend(check_source(path, raw))
        checked += 1

    for finding in findings:
        print(finding)
    tail = " (%d file(s) skipped as out of scope)" % skipped if skipped else ""
    if findings:
        print("\n%d ridgeline finding(s) across %d file(s).%s"
              % (len(findings), checked, tail))
        return 1
    if not checked:
        print("OK ridgeline: no ridgeline found to check%s" % tail)
        return 0
    print("OK ridgeline: %d file(s), every vertex on one shared amplitude, baselines "
          "evenly pitched and drawn, straight segments only, and every printed name, "
          "range and tick bound to what it describes%s" % (checked, tail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
