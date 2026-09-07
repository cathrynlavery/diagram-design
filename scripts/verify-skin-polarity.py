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

1. RAMP - translucent rgb()/rgba() or hex fills that share one ink triple and each
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

A claim the grammar cannot *parse* is unverifiable in exactly the same way, so
it fails too. A tone word sitting within six words of a magnitude word is read
as a directional claim; if no supported sentence form binds it, the file is
reported rather than passed. Without that backstop the gate would be widest
open precisely where an author phrased the claim in their own words - and the
narrower the grammar, the quieter the hole. Widening the vocabulary alone
cannot fix this: there is always one more phrasing, and every one of them would
have been silently exempt.

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
ATTR_RE = re.compile(
    r"""(?P<name>[\w:-]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)""",
    re.DOTALL,
)
RGB_RE = re.compile(r"^\s*rgba?\(\s*(?P<body>.*?)\s*\)\s*$", re.IGNORECASE)
HEX_RE = re.compile(
    r"^\s*#(?P<hex>[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{4}|[0-9a-fA-F]{3})\s*$"
)
PAPER_VAR_RE = re.compile(r"--color-paper\s*:\s*(?P<value>[^;}]+)", re.IGNORECASE)

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
    (
        r"largest|larger|biggest|bigger|greatest|greater|highest|higher|"
        r"longest|longer|tallest|taller|most|more",
        +1,
    ),
    (
        r"smallest|smaller|fewest|fewer|lowest|lower|shortest|shorter|"
        r"lesser|least|less",
        -1,
    ),
)
MAGNITUDE_ALT = "|".join(term[0] for term in MAGNITUDE_TERMS)

# `X is Y` and its mirror `Y is X` assert the same relation, so both are read.
# The optional intervening words let `darker means a larger share` bind without
# letting the two halves drift into separate sentences.
CONNECTOR = (
    r"(?:is|are|was|were|means?|equals?|indicates?|shows?|represents?|denotes?|"
    r"marks?|signals?|reads as|maps to|stands for|=|->|→)"
)
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

# The backstop. Deliberately loose where the grammars above are strict: any tone
# word within six words of a magnitude word reads as a directional claim to a
# human, whether or not a supported sentence form binds it. Six words spans the
# natural constructions ("the larger the cell, the darker it is") without
# reaching across a sentence boundary into unrelated copy. Measured across every
# shipped asset it flags nothing the strict grammars already bind, so it costs no
# false positives and converts the silent gap into a finding.
LOOSE_GAP = r"(?:\W+\w+){0,6}?\W+"
LOOSE_CLAIM_RE = re.compile(
    r"\b(?:" + TONE_ALT + r")\b" + LOOSE_GAP + r"(?:" + MAGNITUDE_ALT + r")\b"
    r"|\b(?:" + MAGNITUDE_ALT + r")\b" + LOOSE_GAP + r"(?:" + TONE_ALT + r")\b",
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

    __slots__ = (
        "axis", "tone_dir", "magnitude_dir", "phrase", "copy", "offset", "span"
    )

    def __init__(self, axis, tone_dir, magnitude_dir, phrase, copy, offset, span):
        self.axis = axis
        self.tone_dir = tone_dir
        self.magnitude_dir = magnitude_dir
        self.phrase = phrase
        self.copy = copy
        self.offset = offset
        # Span within `copy`, so an unbound directional phrase elsewhere in the
        # same sentence is not excused by this one having parsed.
        self.span = span

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


def parse_hex_fill(value):
    """(ink triple, alpha) for CSS's 3/4/6/8-digit hex forms."""
    match = HEX_RE.match(value)
    if match is None:
        return None
    digits = match.group("hex")
    if len(digits) in (3, 4):
        digits = "".join(character * 2 for character in digits)
    channels = tuple(float(int(digits[index : index + 2], 16)) for index in (0, 2, 4))
    alpha = 1.0 if len(digits) == 6 else int(digits[6:8], 16) / 255.0
    return channels, alpha


def parse_channel(token):
    token = token.strip()
    try:
        if token.endswith("%"):
            value = float(token[:-1]) * 2.55
        else:
            value = float(token)
    except ValueError:
        return None
    return value if 0.0 <= value <= 255.0 else None


def parse_alpha(token):
    token = token.strip()
    try:
        value = float(token[:-1]) / 100.0 if token.endswith("%") else float(token)
    except ValueError:
        return None
    return value if 0.0 <= value <= 1.0 else None


def parse_rgb(value):
    """(ink triple, alpha) for legacy and CSS Color 4 rgb()/rgba()."""
    match = RGB_RE.match(value)
    if match is None:
        return None
    body = match.group("body")
    if body.count("/") > 1:
        return None
    color_part, separator, alpha_part = body.partition("/")
    if "," in color_part:
        parts = [part.strip() for part in color_part.split(",")]
        # The legacy fourth comma component is alpha. Slash alpha cannot be
        # mixed with legacy comma channels.
        if separator:
            return None
        elif len(parts) == 4:
            alpha_part = parts.pop()
            separator = "/"
        elif len(parts) != 3:
            return None
    else:
        parts = color_part.split()
        if len(parts) != 3:
            return None
    channels = tuple(parse_channel(part) for part in parts)
    if any(channel is None for channel in channels):
        return None
    alpha = parse_alpha(alpha_part) if separator else 1.0
    if alpha is None:
        return None
    return channels, alpha


def parse_fill(value):
    """(ink triple, alpha) for a solid or translucent fill, else None."""
    return parse_rgb(value) or parse_hex_fill(value)


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
        parsed = parse_fill(match.group("value"))
        if parsed is not None and parsed[1] == 1.0:
            return parsed[0]
    # The full-bleed backdrop is the fallback when no stylesheet token exists.
    # Parse it through the same quote-neutral attribute reader as ramp members.
    for element in ELEMENT_RE.finditer(source):
        if element.group("tag").lower() != "rect":
            continue
        attrs = {}
        for attribute in ATTR_RE.finditer(element.group("attrs")):
            if attribute.group("name") not in attrs:
                attrs[attribute.group("name")] = attribute.group("value")
        if attrs.get("width") != "100%" or attrs.get("height") != "100%":
            continue
        parsed = parse_fill(attrs.get("fill", ""))
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
        attrs = {}
        for attribute in ATTR_RE.finditer(match.group("attrs")):
            name = attribute.group("name")
            if name not in attrs:  # browsers keep the first duplicate attribute
                attrs[name] = attribute.group("value")
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
            parsed_fill = parse_fill(value) if name == "fill" else None
            if name not in existing[0] or (
                name == "fill" and parsed_fill is not None and 0.0 < parsed_fill[1] < 1.0
            ):
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
                    Claim(
                        axis, tone_dir, magnitude, hit.group(0), copy,
                        match.start(), hit.span(),
                    )
                )
    return claims


def find_unparsed(source, claims):
    """Directional wording no supported sentence form bound.

    Overlap is judged per span, not per element: a sentence that binds one claim
    must not excuse a second, differently-phrased one beside it.
    """
    bound = {}
    for claim in claims:
        bound.setdefault(claim.offset, []).append(claim.span)

    unparsed = []
    for match in COPY_RE.finditer(source):
        copy = plain(match.group("body"))
        if not copy:
            continue
        spans = bound.get(match.start(), [])
        for hit in LOOSE_CLAIM_RE.finditer(copy):
            start, end = hit.span()
            if any(start < known_end and known_start < end for known_start, known_end in spans):
                continue
            unparsed.append((hit.group(0), copy, match.start()))
    return unparsed


def check(path):
    """(findings, made_a_claim) for one file."""
    source = path.read_text(encoding="utf-8")
    claims = parse_claims(source)
    unparsed = find_unparsed(source, claims)
    if not claims and not unparsed:
        # Nothing is asserted, so nothing can contradict the ramp.
        return [], False

    findings = []
    for phrase, copy, offset in unparsed:
        findings.append(
            '{}:{}: copy reads as a directional tone claim - "{}" in "{}" - but no '
            "supported sentence form binds it, so it would go unchecked. Rephrase it "
            "as <tone> <is|means|represents> <magnitude> (\"stronger contrast is "
            "larger\"), or separate the two words so it no longer reads as a "
            "claim".format(path.name, line_of(source, offset), phrase, excerpt(copy))
        )
    if not claims:
        return findings, True
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
