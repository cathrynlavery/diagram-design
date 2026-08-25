#!/usr/bin/env python3
"""Verify a legend's tone claim against the ramp the file actually draws.

Tone in this system is an `ink` opacity ramp, and `ink` is a *role*, not a
color: it resolves to #2d3142 on light paper and #f5f5f5 on dark. One ramp,
painted from one set of opacities, therefore composites **darker** as it
strengthens in the light skin and **lighter** in the dark one. A legend key that
names the ramp by lightness is consequently true in one variant and a lie in its
sibling - and both render perfectly, so nothing but a reader catches it.

That is exactly how `Other continents - darker is larger` shipped on
`example-treemap-dark.html`, whose ramp is white ink at 0.14 down to 0.04 over
#2d3142 paper: larger cells are *lighter* there. `lint-skin.py` reads colors,
`verify-geometry.py` reads coordinates, `verify-treemap.py` reads areas against
labels. None of them reads a claim against a ramp.

THE INVARIANT

A visible string asserting a direction of tone must agree with the ramp it
describes, measured on that file's own paper. Three steps:

1. RAMP - fills of the form `rgba(r,g,b,a)` that share one ink triple and each
   carry a rank attribute (`data-share` / `data-value` / `data-size`). Sorted by
   rank, their opacities must move strictly one way. The accent cell drops out
   for free: it is painted in a different ink triple, so it never joins the
   group.
2. POLARITY - each opacity is composited over the file's resolved paper and
   measured twice, because a claim can be about either axis and only one of them
   flips with the skin:
     - LUMINANCE (`darker`, `paler`) - WCAG relative luminance of the composite.
       Skin-dependent. This is the axis the shipped defect was on.
     - CONTRAST (`stronger`, `fainter`) - contrast ratio of the composite
       against the paper. Skin-invariant, because it measures ink against its
       own ground rather than against absolute white.
3. CLAIM - a tone word bound to a magnitude word (`darker is larger`, `paler
   means smaller`) is read out of rendered copy and checked against the measured
   direction on its own axis.

WHY THE CONTRAST AXIS IS MEASURED TOO

Inverting the word for the dark variant is the wrong fix: it swaps one
skin-specific string for another and leaves the variants free to drift apart
again. Naming the ramp by contrast (`stronger contrast is larger`) is checked
against opacity, which does not flip when the skin does - so one sentence ships
in all three variants and stays true. The gate verifies that phrasing rather
than merely tolerating it.

FAIL-CLOSED

A file with no tone claim asserts nothing and passes. A file that *makes* a
claim it cannot substantiate - no resolvable paper, fewer than three
rank-bearing ramp members, a rank or opacity order that is not strictly
monotonic, or an axis whose direction measures flat - is a finding, not a pass.
An unverifiable claim is the state this defect shipped in.

Usage:
    python3 scripts/verify-skin-polarity.py --all
    python3 scripts/verify-skin-polarity.py skills/diagram-design/assets/example-treemap-dark.html

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

# Rank sources, most specific first. A ramp member must carry one of these; the
# legend swatch that repeats the top of the ramp carries none, which is what
# keeps a 16x10 key out of a ramp measured over 250x250 cells.
RANK_ATTRS = ("data-share", "data-value", "data-size")

ELEMENT_RE = re.compile(
    r"<(?P<tag>rect|circle|path|ellipse|polygon)\b(?P<attrs>[^>]*?)/?>", re.IGNORECASE
)
ATTR_RE = re.compile(r'(?P<name>[\w:-]+)="(?P<value>[^"]*)"')
RGBA_RE = re.compile(
    r"rgba?\(\s*(?P<r>[\d.]+)\s*,\s*(?P<g>[\d.]+)\s*,\s*(?P<b>[\d.]+)\s*"
    r"(?:,\s*(?P<a>[\d.]+)\s*)?\)",
    re.IGNORECASE,
)
HEX_RE = re.compile(r"#(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
PAPER_VAR_RE = re.compile(r"--color-paper\s*:\s*(?P<value>[^;}]+)", re.IGNORECASE)
# The full-bleed backdrop, used when the stylesheet does not declare the token.
BACKDROP_RE = re.compile(
    r'<rect\b[^>]*\bwidth="100%"[^>]*\bheight="100%"[^>]*\bfill="(?P<fill>[^"]+)"',
    re.IGNORECASE,
)

# Copy a reader - or a screen reader - actually receives as a statement: rendered
# SVG strings, the accessible description, and the editorial prose the full
# variant wraps around the chart.
COPY_RE = re.compile(
    r"<(?P<tag>text|desc|p|h1|h2|h3|h4|li|figcaption)\b[^>]*>(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")

LUMINANCE = "luminance"
CONTRAST = "contrast"

# Tone vocabulary, split by the axis each word actually names. The split is the
# whole point: `darker` is a statement about lightness and inverts with the skin,
# while `stronger` is a statement about ink against its own paper and does not.
# Multi-word contrast phrases are listed first so `higher contrast` is not
# consumed as the bare magnitude word `higher`.
TONE_TERMS = (
    (r"(?:more|higher|greater|stronger) contrast", CONTRAST, +1),
    (r"(?:less|lower|weaker) contrast", CONTRAST, -1),
    (r"darker|darkest|deeper|deepest", LUMINANCE, -1),
    (r"lighter|lightest|paler|palest", LUMINANCE, +1),
    (r"stronger|strongest|bolder|boldest|denser|densest", CONTRAST, +1),
    (r"weaker|weakest|fainter|faintest|softer|softest", CONTRAST, -1),
)
TONE_ALT = "|".join(term[0] for term in TONE_TERMS)

MAGNITUDE_TERMS = (
    (r"larger|largest|bigger|biggest|greater|greatest|more|higher|longer|taller", +1),
    (r"smaller|smallest|lesser|less|fewer|fewest|lower|shorter", -1),
)
MAGNITUDE_ALT = "|".join(term[0] for term in MAGNITUDE_TERMS)

# `X is Y` and its mirror `Y is X` assert the same relation, so both are read.
# The optional intervening words let `darker means a larger share` bind without
# letting the two halves drift into separate sentences.
CONNECTOR = r"(?:is|are|was|were|means?|equals?|indicates?|shows?|=|->|→)"
CLAIM_RE = re.compile(
    r"\b(?P<tone>" + TONE_ALT + r")\b(?:\s+\w+){0,2}?\s+" + CONNECTOR + r"\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<magnitude>" + MAGNITUDE_ALT + r")\b",
    re.IGNORECASE,
)
MIRROR_RE = re.compile(
    r"\b(?P<magnitude>" + MAGNITUDE_ALT + r")\b(?:\s+\w+){0,2}?\s+" + CONNECTOR + r"\s+"
    r"(?:the\s+|a\s+|an\s+)?(?P<tone>" + TONE_ALT + r")\b",
    re.IGNORECASE,
)

EXCERPT_CHARS = 76
MIN_RAMP_MEMBERS = 3
# Two composites this close read as one step; treating them as ordered would let
# a flat ramp certify a direction it does not actually draw.
LUMINANCE_EPSILON = 1e-4
CONTRAST_EPSILON = 1e-3

DRAWN_AS = {
    (LUMINANCE, 1): "lighter",
    (LUMINANCE, -1): "darker",
    (CONTRAST, 1): "stronger",
    (CONTRAST, -1): "weaker",
}


class Member:
    """One rank-bearing translucent fill on the ramp."""

    __slots__ = ("rank", "alpha", "ink", "offset")

    def __init__(self, rank, alpha, ink, offset):
        self.rank = rank
        self.alpha = alpha
        self.ink = ink
        self.offset = offset


class Claim:
    """A directional tone assertion found in rendered copy."""

    __slots__ = ("axis", "tone_dir", "magnitude_dir", "phrase", "copy", "offset")

    def __init__(self, axis, tone_dir, magnitude_dir, phrase, copy, offset):
        self.axis = axis
        self.tone_dir = tone_dir
        self.magnitude_dir = magnitude_dir
        self.phrase = phrase
        self.copy = copy
        self.offset = offset

    @property
    def expected(self):
        """Direction the claimed axis must move in as rank rises.

        `darker is larger` is tone -1 with magnitude +1, so luminance must FALL
        as rank rises. `paler is smaller` is +1 with -1 - luminance must fall
        again, because the sentence states the same relation from the other end.
        """
        return self.tone_dir * self.magnitude_dir


def line_of(source, offset):
    return source.count("\n", 0, offset) + 1


def plain(body):
    """Text content of a copy element, child tags stripped and entities resolved.

    Both steps matter: a `<tspan>` splitting a word, or an escaped character
    inside it, would otherwise hide the claim from a substring search while a
    reader still receives the whole sentence.
    """
    return " ".join(html.unescape(TAG_RE.sub("", body)).split())


def excerpt(text):
    if len(text) <= EXCERPT_CHARS:
        return text
    return text[: EXCERPT_CHARS - 1] + "…"


def parse_hex(value):
    match = HEX_RE.search(value)
    if match is None:
        return None
    digits = match.group("hex")
    if len(digits) == 3:
        digits = "".join(character * 2 for character in digits)
    return tuple(float(int(digits[index : index + 2], 16)) for index in (0, 2, 4))


def parse_fill(value):
    """(ink triple, alpha) for a solid or translucent fill, else None."""
    match = RGBA_RE.search(value)
    if match is not None:
        try:
            channels = tuple(float(match.group(name)) for name in ("r", "g", "b"))
            alpha = 1.0 if match.group("a") is None else float(match.group("a"))
        except ValueError:
            return None
        if not all(0.0 <= channel <= 255.0 for channel in channels):
            return None
        if not 0.0 <= alpha <= 1.0:
            return None
        return channels, alpha
    triple = parse_hex(value)
    if triple is None:
        return None
    return triple, 1.0


def srgb_to_linear(channel):
    ratio = channel / 255.0
    return ratio / 12.92 if ratio <= 0.04045 else ((ratio + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    """WCAG 2.x relative luminance."""
    red, green, blue = (srgb_to_linear(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def composite(ink, alpha, paper):
    """Source-over of `ink` at `alpha` on opaque `paper`."""
    return tuple(ink[index] * alpha + paper[index] * (1.0 - alpha) for index in range(3))


def contrast_ratio(first, second):
    return (max(first, second) + 0.05) / (min(first, second) + 0.05)


def resolve_paper(source):
    """The paper this file composites onto: the declared token, else the backdrop.

    The token is preferred because the body background and the SVG backdrop are
    both painted from it; the backdrop is the fallback for a bare SVG that ships
    no stylesheet.
    """
    match = PAPER_VAR_RE.search(source)
    if match is not None:
        triple = parse_hex(match.group("value"))
        if triple is not None:
            return triple
    match = BACKDROP_RE.search(source)
    if match is not None:
        parsed = parse_fill(match.group("fill"))
        if parsed is not None and parsed[1] == 1.0:
            return parsed[0]
    return None


def collect_members(source):
    """Rank-bearing translucent fills, grouped by ink triple.

    A cell is painted twice - a paper mask, then the body - and the rank
    attribute may sit on either rect of the pair (`verify-treemap.py` tolerates
    both). Attributes are therefore merged across elements sharing one geometry
    signature before a member is built, so a rank declared on the mask still
    reaches the ramp instead of silently shortening it.
    """
    merged = []
    index_by_signature = {}
    for match in ELEMENT_RE.finditer(source):
        attrs = {
            a.group("name"): a.group("value") for a in ATTR_RE.finditer(match.group("attrs"))
        }
        signature = (
            match.group("tag").lower(),
            attrs.get("x"),
            attrs.get("y"),
            attrs.get("width"),
            attrs.get("height"),
            attrs.get("cx"),
            attrs.get("cy"),
            attrs.get("r"),
            attrs.get("d"),
            attrs.get("points"),
        )
        # An element declaring no geometry at all cannot be twinned reliably;
        # keep it distinct rather than merging every such element into one.
        twinnable = any(value is not None for value in signature[1:])
        position = index_by_signature.get(signature) if twinnable else None
        if position is None:
            merged.append([dict(attrs), match.start()])
            if twinnable:
                index_by_signature[signature] = len(merged) - 1
            continue
        existing = merged[position]
        for name, value in attrs.items():
            # A translucent fill wins over the mask's opaque one, and a rank
            # attribute is adopted from whichever twin declared it.
            if name not in existing[0] or (name == "fill" and "rgba" in value.lower()):
                existing[0][name] = value
        existing[1] = min(existing[1], match.start())

    groups = {}
    for attrs, offset in merged:
        parsed = parse_fill(attrs.get("fill", ""))
        if parsed is None:
            continue
        ink, alpha = parsed
        # A fully opaque fill is not a point on an opacity ramp.
        if not 0.0 < alpha < 1.0:
            continue
        rank = None
        for name in RANK_ATTRS:
            if name in attrs:
                try:
                    rank = float(attrs[name])
                except ValueError:
                    rank = None
                break
        # NaN compares unequal to itself and would corrupt every ordering test.
        if rank is None or rank != rank:
            continue
        groups.setdefault(ink, []).append(Member(rank, alpha, ink, offset))
    return groups


def direction(values, epsilon):
    """+1 strictly rising, -1 strictly falling, 0 neither."""
    pairs = list(zip(values, values[1:]))
    if not pairs:
        return 0
    if all(later - earlier > epsilon for earlier, later in pairs):
        return 1
    if all(earlier - later > epsilon for earlier, later in pairs):
        return -1
    return 0


def classify_tone(word):
    for term, axis, sign in TONE_TERMS:
        if re.fullmatch(term, word, re.IGNORECASE):
            return axis, sign
    return None


def classify_magnitude(word):
    for term, sign in MAGNITUDE_TERMS:
        if re.fullmatch(term, word, re.IGNORECASE):
            return sign
    return None


def parse_claims(source):
    claims = []
    for match in COPY_RE.finditer(source):
        copy = plain(match.group("body"))
        if not copy:
            continue
        seen = set()
        for pattern in (CLAIM_RE, MIRROR_RE):
            for hit in pattern.finditer(copy):
                tone = classify_tone(hit.group("tone"))
                magnitude = classify_magnitude(hit.group("magnitude"))
                if tone is None or magnitude is None:
                    continue
                axis, tone_dir = tone
                key = (axis, tone_dir, magnitude, hit.group("tone").lower())
                # The two patterns overlap on symmetric phrasings; report the
                # relation once rather than twice for one sentence.
                if key in seen:
                    continue
                seen.add(key)
                claims.append(
                    Claim(axis, tone_dir, magnitude, hit.group(0), copy, match.start())
                )
    return claims


def check(path):
    """(findings, made_a_claim) for one file."""
    source = path.read_text(encoding="utf-8")
    claims = parse_claims(source)
    if not claims:
        # Nothing is asserted, so nothing can contradict the ramp.
        return [], False

    findings = []
    paper = resolve_paper(source)
    if paper is None:
        for claim in claims:
            findings.append(
                '{}:{}: copy claims "{}" but the file declares no paper color '
                "(--color-paper, or a full-bleed backdrop rect), so the ramp cannot be "
                "composited and the claim cannot be checked".format(
                    path.name, line_of(source, claim.offset), claim.phrase
                )
            )
        return findings, True

    groups = collect_members(source)
    ramp = max(groups.values(), key=len) if groups else []
    if len(ramp) < MIN_RAMP_MEMBERS:
        for claim in claims:
            findings.append(
                '{}:{}: copy claims "{}" but only {} rank-bearing translucent fill(s) '
                "share one ink color, so there is no ramp to check it against. Give every "
                "ramp member a rank attribute ({}) or drop the directional claim".format(
                    path.name,
                    line_of(source, claim.offset),
                    claim.phrase,
                    len(ramp),
                    ", ".join(RANK_ATTRS),
                )
            )
        return findings, True

    ramp = sorted(ramp, key=lambda member: member.rank)
    ranks = [member.rank for member in ramp]
    if direction(ranks, 0.0) != 1:
        for claim in claims:
            findings.append(
                '{}:{}: copy claims "{}" but the ramp\'s ranks are not distinct ({}), '
                "so no member is unambiguously larger than another".format(
                    path.name,
                    line_of(source, claim.offset),
                    claim.phrase,
                    ", ".join("{:g}".format(rank) for rank in ranks),
                )
            )
        return findings, True

    paper_luminance = relative_luminance(paper)
    luminances = []
    contrasts = []
    for member in ramp:
        luminance = relative_luminance(composite(member.ink, member.alpha, paper))
        luminances.append(luminance)
        contrasts.append(contrast_ratio(luminance, paper_luminance))

    measured = {
        LUMINANCE: direction(luminances, LUMINANCE_EPSILON),
        CONTRAST: direction(contrasts, CONTRAST_EPSILON),
    }
    ink = ramp[0].ink
    described = "rgba({:g},{:g},{:g}) at {} over #{:02x}{:02x}{:02x}".format(
        ink[0],
        ink[1],
        ink[2],
        " -> ".join("{:g}".format(member.alpha) for member in ramp),
        int(round(paper[0])),
        int(round(paper[1])),
        int(round(paper[2])),
    )

    for claim in claims:
        actual = measured[claim.axis]
        line = line_of(source, claim.offset)
        if actual == 0:
            series = luminances if claim.axis == LUMINANCE else contrasts
            findings.append(
                '{}:{}: copy claims "{}" but the ramp\'s {} does not move strictly one '
                "way as rank rises ({}: {}), so the claim cannot be substantiated".format(
                    path.name,
                    line,
                    claim.phrase,
                    claim.axis,
                    described,
                    ", ".join("{:.4f}".format(value) for value in series),
                )
            )
            continue
        if actual == claim.expected:
            continue
        remedy = (
            "Name the ramp by contrast against the paper "
            '("stronger contrast is larger"), which stays true when the skin flips, '
            "rather than inverting the word for this one variant"
            if claim.axis == LUMINANCE
            else "Fix the claim or the ramp so they state one thing"
        )
        findings.append(
            '{}:{}: copy claims "{}" - "{}" - but the ramp draws larger as {} ({}). '
            "{}".format(
                path.name,
                line,
                claim.phrase,
                excerpt(claim.copy),
                DRAWN_AS[(claim.axis, actual)],
                described,
                remedy,
            )
        )
    return findings, True


def targets(args):
    if args.all:
        return sorted(ASSET_DIR.glob("*.html"))
    return [Path(candidate) for candidate in args.paths]


def main():
    parser = argparse.ArgumentParser(
        description="Verify a legend's tone claim against the ramp the file draws.",
        epilog=(
            "EXAMPLES:\n"
            "  # every shipped asset\n"
            "  python3 scripts/verify-skin-polarity.py --all\n"
            "\n"
            "  # one variant, while editing it\n"
            "  python3 scripts/verify-skin-polarity.py \\\n"
            "      skills/diagram-design/assets/example-treemap-dark.html\n"
            "\n"
            "  # a light/dark pair, to prove one sentence serves both\n"
            "  python3 scripts/verify-skin-polarity.py \\\n"
            "      skills/diagram-design/assets/example-treemap.html \\\n"
            "      skills/diagram-design/assets/example-treemap-dark.html\n"
            "\n"
            "EXIT: 0 clean, 1 findings, 2 usage.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("paths", nargs="*", help="HTML files to check")
    parser.add_argument("--all", action="store_true", help="check every shipped asset")
    args = parser.parse_args()
    if not args.all and not args.paths:
        parser.print_help()
        return 2

    findings = []
    checked = 0
    claiming = 0
    for path in targets(args):
        if not path.exists():
            print("error: {} does not exist".format(path), file=sys.stderr)
            return 2
        file_findings, made_claim = check(path)
        findings.extend(file_findings)
        checked += 1
        claiming += 1 if made_claim else 0

    for finding in findings:
        print(finding)
    if findings:
        print(
            "\n{} skin-polarity finding(s) across {} file(s).".format(len(findings), checked)
        )
        return 1
    # The claim count is reported so a run that checked nothing cannot be
    # mistaken for a run that found nothing.
    print(
        "OK skin polarity: {} file(s), {} making a directional tone claim, "
        "every claim matches its composited ramp".format(checked, claiming)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
