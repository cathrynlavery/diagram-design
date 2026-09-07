#!/usr/bin/env python3
"""Adversarial tests for verify-skin-polarity.py - both polarities, both skins.

Per ADR 0005, a contract in this repo is a checker plus fixtures proving it fires
when it should and stays quiet when it shouldn't. This checker needs the second
half more than most, because the cheap version of it - banning `darker` in files
named `*-dark.html` - passes the obvious test while being wrong twice over: it
cannot see the same defect on light paper, and it condemns a dark variant whose
copy is accurate.

So the mutations below run the defect in **both directions on both skins**:

- `darker is larger` over a white-ink ramp (the defect that shipped) must fail;
- `darker is larger` over a dark-ink ramp must pass, in the very same words;
- `lighter is larger` must fail on light paper and pass on dark.

A second gap, raised in review on #156, gets the same treatment: wording the
grammar cannot parse used to be silently treated as no claim, so the gate was
widest open exactly where an author phrased things in their own words. The cases
below pin both halves of the fix - the widened forms are checked against the
ramp rather than merely accepted, and anything still unparsed fails closed.

Each case is named for exactly what it asserts and nothing more. A case named
for more than it proves is how a verification gap hides.

Usage: python3 scripts/test-verify-skin-polarity.py
Exit: 0 all pass, 1 a case failed.
"""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-skin-polarity.py"
ASSETS = ROOT / "skills/diagram-design/assets"
LIGHT = ASSETS / "example-treemap.html"
DARK = ASSETS / "example-treemap-dark.html"
FULL = ASSETS / "example-treemap-full.html"

SHIPPED_KEY = "Other continents · stronger contrast is larger"

NAMESPACE = runpy.run_path(str(CHECKER), run_name="verify_skin_polarity_test")
COLLECT_MEMBERS = NAMESPACE["collect_members"]
PARSE_CLAIMS = NAMESPACE["parse_claims"]
RESOLVE_PAPER = NAMESPACE["resolve_paper"]
COMPOSITE = NAMESPACE["composite"]
RELATIVE_LUMINANCE = NAMESPACE["relative_luminance"]
PARSE_FILL = NAMESPACE["parse_fill"]

# The five non-focal cells of the shipped treemaps, as (rank, light ink opacity,
# dark ink opacity). The ramp is one set of numbers per skin; only the ink role
# behind it changes.
LIGHT_RAMP = (("18.29", "0.16"), ("9.23", "0.13"), ("7.52", "0.10"), ("5.35", "0.07"), ("0.56", "0.04"))
DARK_RAMP = (("18.29", "0.14"), ("9.23", "0.11"), ("7.52", "0.08"), ("5.35", "0.06"), ("0.56", "0.04"))
LIGHT_INK = "45,49,66"
DARK_INK = "245,245,245"


def run(*paths):
    result = subprocess.run(
        [sys.executable, str(CHECKER)] + [str(path) for path in paths],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def write(directory, name, source):
    path = directory / name
    path.write_text(source, encoding="utf-8")
    return path


def flatten_ramp(source, ramp, ink, alpha="0.10"):
    """Paint every ramp member at one opacity, leaving the ranks alone."""
    for rank, original in ramp:
        source = source.replace(
            'data-share="{}" fill="rgba({},{})"'.format(rank, ink, original),
            'data-share="{}" fill="rgba({},{})"'.format(rank, ink, alpha),
            1,
        )
    return source


def invert_ramp(source, ramp, ink):
    """Reverse the ramp against its ranks, so the largest cell is the faintest."""
    for index, (rank, _original) in enumerate(ramp):
        replacement = ramp[len(ramp) - 1 - index][1]
        source = source.replace(
            'data-share="{}" fill="rgba({},'.format(rank, ink),
            'data-share="{}" fill="rgba({},@{}@'.format(rank, ink, replacement),
            1,
        )
    # Drop each original opacity, now stranded behind its placeholder.
    source = re.sub(r"@([\d.]+)@[\d.]+\)", r"\1)", source)
    return source


def main():
    failures = []
    light_source = LIGHT.read_text(encoding="utf-8")
    dark_source = DARK.read_text(encoding="utf-8")

    # 1. The shipped state is the baseline. If this is not clean, nothing below
    #    means anything.
    code, output = run(LIGHT, DARK, FULL)
    if code != 0:
        failures.append("shipped_treemap_variants_pass: exit {} - {}".format(code, output.strip()))
    else:
        print("OK: shipped_treemap_variants_pass")

    code, output = run("--all")
    if code != 0:
        failures.append("shipped_assets_pass: --all exited {} - {}".format(code, output.strip()))
    elif "making a directional tone claim" not in output:
        failures.append("shipped_assets_pass: summary omits the claim count - " + output.strip())
    else:
        print("OK: shipped_assets_pass")

    # 2. The summary must report how many files actually asserted something. A
    #    run that parsed no claim at all would otherwise print the same "OK" as
    #    a run that checked six.
    if re.search(r"\b0 making a directional tone claim", output):
        failures.append("shipped_assets_pass: --all parsed no claims, so it verified nothing")
    else:
        print("OK: all_run_reports_a_nonzero_claim_count")

    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)

        # SVG accepts both quote styles. Convert every rank-bearing ramp member
        # to single-quoted attributes; the checker must still discover all five
        # members and verify the shipped claim.
        single_quoted = light_source
        quoted_edits = 0
        for rank, alpha in LIGHT_RAMP:
            anchor = 'data-share="{}" fill="rgba({},{})"'.format(
                rank, LIGHT_INK, alpha
            )
            replacement = "data-share='{}' fill='rgba({},{})'".format(
                rank, LIGHT_INK, alpha
            )
            if anchor in single_quoted:
                single_quoted = single_quoted.replace(anchor, replacement, 1)
                quoted_edits += 1
        if quoted_edits != len(LIGHT_RAMP):
            failures.append("could not build the single-quoted ramp fixture")
        else:
            code, output = run(write(directory, "single-quoted.html", single_quoted))
        if quoted_edits == len(LIGHT_RAMP) and code != 0:
            failures.append(
                "single_quoted_ramp_attributes_pass: exit {} - {}".format(
                    code, output.strip()
                )
            )
        elif quoted_edits == len(LIGHT_RAMP):
            print("OK: single_quoted_ramp_attributes_pass")

        # CSS Color 4's space-separated channels, percentage channels, slash
        # alpha, and alpha-bearing hex spellings are all browser-valid fills.
        # Pin the numeric interpretation directly so merely accepting but
        # mismeasuring a color cannot satisfy the test.
        color_cases = (
            ("#2d314280", ((45.0, 49.0, 66.0), 128.0 / 255.0)),
            ("#abc8", ((170.0, 187.0, 204.0), 136.0 / 255.0)),
            ("rgb(45 49 66 / 16%)", ((45.0, 49.0, 66.0), 0.16)),
            ("rgb(17.647% 19.216% 25.882% / .16)",
             ((44.99985, 49.0008, 65.9991), 0.16)),
        )
        for spelling, expected in color_cases:
            parsed = PARSE_FILL(spelling)
            if parsed is None or any(
                abs(actual - wanted) > 0.001
                for actual, wanted in zip(parsed[0] + (parsed[1],), expected[0] + (expected[1],))
            ):
                failures.append(
                    "browser_valid_color_is_measured[{}]: got {!r}, expected {!r}".format(
                        spelling, parsed, expected
                    )
                )
            else:
                print("OK: browser_valid_color_is_measured[{}]".format(spelling))

        modern_rgb = light_source
        rgb_edits = 0
        for rank, alpha in LIGHT_RAMP:
            anchor = 'data-share="{}" fill="rgba({},{})"'.format(
                rank, LIGHT_INK, alpha
            )
            replacement = 'data-share="{}" fill="rgb(45 49 66 / {}%)"'.format(
                rank, float(alpha) * 100
            )
            if anchor in modern_rgb:
                modern_rgb = modern_rgb.replace(anchor, replacement, 1)
                rgb_edits += 1
        if rgb_edits != len(LIGHT_RAMP):
            failures.append("could not build the space-separated RGB ramp fixture")
        else:
            code, output = run(write(directory, "modern-rgb.html", modern_rgb))
        if rgb_edits == len(LIGHT_RAMP) and code != 0:
            failures.append(
                "space_separated_rgb_ramp_passes: exit {} - {}".format(code, output.strip())
            )
        elif rgb_edits == len(LIGHT_RAMP):
            print("OK: space_separated_rgb_ramp_passes")

        # 3. The defect exactly as it shipped: the light skin's sentence over the
        #    dark skin's white-ink ramp.
        reintroduced = dark_source.replace(SHIPPED_KEY, "Other continents · darker is larger", 1)
        if reintroduced == dark_source:
            failures.append("could not build the dark_ramp_called_darker_is_larger fixture")
        else:
            code, output = run(write(directory, "dark-darker.html", reintroduced))
            if code != 1:
                failures.append(
                    "dark_ramp_called_darker_is_larger_fails: exit {} - {}".format(code, output.strip())
                )
            elif "draws larger as lighter" not in output:
                failures.append(
                    "dark_ramp_called_darker_is_larger_fails: finding does not name the drawn "
                    "direction - " + output.strip()
                )
            else:
                print("OK: dark_ramp_called_darker_is_larger_fails")

        # 4. The identical sentence over the light skin's dark-ink ramp is true,
        #    and must pass. This is what separates reading the ramp from banning
        #    a word.
        original_wording = light_source.replace(SHIPPED_KEY, "Other continents · darker is larger", 1)
        code, output = run(write(directory, "light-darker.html", original_wording))
        if code != 0:
            failures.append(
                "light_ramp_called_darker_is_larger_passes: exit {} - {}".format(code, output.strip())
            )
        else:
            print("OK: light_ramp_called_darker_is_larger_passes")

        # 5. The mirror defect, on the skin a filename-based check would never
        #    look at: a light variant claiming the ramp lightens as it grows.
        light_lighter = light_source.replace(SHIPPED_KEY, "Other continents · lighter is larger", 1)
        code, output = run(write(directory, "light-lighter.html", light_lighter))
        if code != 1:
            failures.append(
                "light_ramp_called_lighter_is_larger_fails: exit {} - {}".format(code, output.strip())
            )
        elif "draws larger as darker" not in output:
            failures.append(
                "light_ramp_called_lighter_is_larger_fails: finding does not name the drawn "
                "direction - " + output.strip()
            )
        else:
            print("OK: light_ramp_called_lighter_is_larger_fails")

        # 6. ...and the same words are accurate on dark paper, so they pass.
        dark_lighter = dark_source.replace(SHIPPED_KEY, "Other continents · lighter is larger", 1)
        code, output = run(write(directory, "dark-lighter.html", dark_lighter))
        if code != 0:
            failures.append(
                "dark_ramp_called_lighter_is_larger_passes: exit {} - {}".format(code, output.strip())
            )
        else:
            print("OK: dark_ramp_called_lighter_is_larger_passes")

        # 7. The shipped contrast wording is not merely tolerated - it is checked
        #    against opacity, so inverting the ramp beneath it must fail on both
        #    skins while the sentence stays put.
        for label, source, ramp, ink in (
            ("light", light_source, LIGHT_RAMP, LIGHT_INK),
            ("dark", dark_source, DARK_RAMP, DARK_INK),
        ):
            inverted = invert_ramp(source, ramp, ink)
            if inverted == source or re.search(r"@[\d.]+@", inverted):
                failures.append("could not build the {} inverted-ramp fixture".format(label))
                continue
            code, output = run(write(directory, "inverted-{}.html".format(label), inverted))
            if code != 1:
                failures.append(
                    "contrast_wording_fails_when_the_{}_ramp_is_inverted: exit {} - {}".format(
                        label, code, output.strip()
                    )
                )
            elif "draws larger as weaker" not in output:
                failures.append(
                    "contrast_wording_fails_when_the_{}_ramp_is_inverted: finding does not name "
                    "the drawn direction - {}".format(label, output.strip())
                )
            else:
                print("OK: contrast_wording_fails_when_the_{}_ramp_is_inverted".format(label))

        # 8. Fail closed: a ramp painted at one opacity has no direction, so a
        #    claim about it cannot be substantiated either way.
        flat = flatten_ramp(light_source, LIGHT_RAMP, LIGHT_INK)
        if flat == light_source:
            failures.append("could not build the flat-ramp fixture")
        else:
            code, output = run(write(directory, "flat.html", flat))
            if code != 1:
                failures.append(
                    "flat_ramp_with_a_claim_fails_closed: exit {} - {}".format(code, output.strip())
                )
            elif "does not move strictly one way" not in output:
                failures.append(
                    "flat_ramp_with_a_claim_fails_closed: finding does not say the ramp is "
                    "flat - " + output.strip()
                )
            else:
                print("OK: flat_ramp_with_a_claim_fails_closed")

        # 9. Fail closed: two cells declaring one rank leave no ordering to read.
        tied = light_source.replace('data-share="9.23"', 'data-share="18.29"', 1)
        if tied == light_source:
            failures.append("could not build the tied-ranks fixture")
        else:
            code, output = run(write(directory, "tied.html", tied))
            if code != 1:
                failures.append(
                    "tied_ranks_with_a_claim_fail_closed: exit {} - {}".format(code, output.strip())
                )
            elif "ranks are not distinct" not in output:
                failures.append(
                    "tied_ranks_with_a_claim_fail_closed: finding does not name the tie - "
                    + output.strip()
                )
            else:
                print("OK: tied_ranks_with_a_claim_fail_closed")

        # 10. Fail closed: a claim with no rank metadata at all is unverifiable,
        #     and an unverifiable claim is exactly the state this defect shipped
        #     in. Passing it silently would rebuild the gap.
        rankless = re.sub(r'\s*data-share="[\d.]+"', "", light_source)
        if rankless == light_source:
            failures.append("could not build the rankless fixture")
        else:
            code, output = run(write(directory, "rankless.html", rankless))
            if code != 1:
                failures.append(
                    "claim_without_a_ramp_fails_closed: exit {} - {}".format(code, output.strip())
                )
            elif "no ramp to check it against" not in output:
                failures.append(
                    "claim_without_a_ramp_fails_closed: finding does not say the ramp is "
                    "missing - " + output.strip()
                )
            else:
                print("OK: claim_without_a_ramp_fails_closed")

        # 11. Fail closed: without a paper color there is nothing to composite
        #     against, so lightness has no defined direction.
        paperless = re.sub(r"\s*--color-paper:\s*[^;]+;", "", light_source)
        paperless = paperless.replace('<rect width="100%" height="100%" fill="#f5f5f5"/>', "", 1)
        if paperless == light_source:
            failures.append("could not build the paperless fixture")
        else:
            code, output = run(write(directory, "paperless.html", paperless))
            if code != 1:
                failures.append(
                    "claim_without_paper_fails_closed: exit {} - {}".format(code, output.strip())
                )
            elif "no paper color" not in output:
                failures.append(
                    "claim_without_paper_fails_closed: finding does not name the missing "
                    "paper - " + output.strip()
                )
            else:
                print("OK: claim_without_paper_fails_closed")

        # 12. A file that asserts no direction is not making a claim to check,
        #     and must not be dragged into a finding.
        silent = light_source.replace(SHIPPED_KEY, "Other continents", 1)
        code, output = run(write(directory, "silent.html", silent))
        if code != 0:
            failures.append(
                "file_without_a_tone_claim_passes: exit {} - {}".format(code, output.strip())
            )
        elif "0 making a directional tone claim" not in output:
            failures.append(
                "file_without_a_tone_claim_passes: summary claims it checked one - " + output.strip()
            )
        else:
            print("OK: file_without_a_tone_claim_passes")

        # 13. A `<tspan>` splitting the sentence must not hide it. A reader still
        #     receives the whole claim, so the checker has to as well.
        split_claim = dark_source.replace(
            SHIPPED_KEY, "Other continents · dar<tspan>ker is</tspan> larger", 1
        )
        code, output = run(write(directory, "tspan.html", split_claim))
        if code != 1:
            failures.append(
                "claim_split_across_tspans_is_still_read: exit {} - {}".format(code, output.strip())
            )
        else:
            print("OK: claim_split_across_tspans_is_still_read")

        # 14. `verify-treemap.py` accepts `data-share` on either rect of a cell's
        #     mask/body pair. A rank declared on the mask must still reach the
        #     ramp, or a legal file would silently lose a member and fail closed
        #     for the wrong reason.
        on_mask = light_source.replace(
            '<rect x="576" y="40" width="252" height="252" rx="2" fill="#f5f5f5"/>',
            '<rect x="576" y="40" width="252" height="252" rx="2" data-share="18.29" fill="#f5f5f5"/>',
            1,
        ).replace(
            '<rect x="576" y="40" width="252" height="252" rx="2" data-share="18.29" '
            'fill="rgba(45,49,66,0.16)"',
            '<rect x="576" y="40" width="252" height="252" rx="2" fill="rgba(45,49,66,0.16)"',
            1,
        )
        if on_mask == light_source:
            failures.append("could not build the rank-on-mask fixture")
        else:
            path = write(directory, "rank-on-mask.html", on_mask)
            members = COLLECT_MEMBERS(on_mask)
            ramp = max(members.values(), key=len) if members else []
            code, output = run(path)
            if len(ramp) != 5:
                failures.append(
                    "rank_declared_on_the_mask_rect_still_joins_the_ramp: read {} member(s), "
                    "expected 5".format(len(ramp))
                )
            elif code != 0:
                failures.append(
                    "rank_declared_on_the_mask_rect_still_joins_the_ramp: exit {} - {}".format(
                        code, output.strip()
                    )
                )
            else:
                print("OK: rank_declared_on_the_mask_rect_still_joins_the_ramp")

        # 15. The fail-open path raised in review on #156: a claim phrased
        #     outside the grammar was treated as no claim at all. Wording a
        #     reader receives as directional must never pass unchecked.
        for label, phrasing in (
            ("comma_correlative", "the larger the cell, the darker it is"),
            ("passive_voice", "bigger cells are painted darker"),
        ):
            fixture = light_source.replace(SHIPPED_KEY, "Other continents · " + phrasing, 1)
            code, output = run(write(directory, "unparsed-{}.html".format(label), fixture))
            if code != 1:
                failures.append(
                    "unparseable_directional_wording_fails_closed[{}]: exit {} - {}".format(
                        label, code, output.strip()
                    )
                )
            elif "no supported sentence form binds it" not in output:
                failures.append(
                    "unparseable_directional_wording_fails_closed[{}]: finding does not name "
                    "the parse failure - {}".format(label, output.strip())
                )
            else:
                print("OK: unparseable_directional_wording_fails_closed[{}]".format(label))

        # 16. A widened connector must be CHECKED, not merely accepted: one
        #     phrasing, opposite verdicts on the two skins. Accepting it without
        #     measuring would trade a silent gap for a silent pass.
        for label, source, expected in (("light", light_source, 0), ("dark", dark_source, 1)):
            fixture = source.replace(
                SHIPPED_KEY, "Other continents · darker represents larger", 1
            )
            code, output = run(write(directory, "represents-{}.html".format(label), fixture))
            if code != expected:
                failures.append(
                    "darker_represents_larger_passes_on_light_and_fails_on_dark[{}]: exit {} "
                    "- {}".format(label, code, output.strip())
                )
            else:
                print(
                    "OK: darker_represents_larger_passes_on_light_and_fails_on_dark[{}]".format(
                        label
                    )
                )

        # 17. One correct sentence must not launder an unparsed one beside it,
        #     which is why overlap is judged per span rather than per element.
        mixed = light_source.replace(
            SHIPPED_KEY,
            "Other continents · stronger contrast is larger. Bigger cells are painted darker.",
            1,
        )
        code, output = run(write(directory, "mixed.html", mixed))
        if code != 1:
            failures.append(
                "bound_claim_does_not_excuse_unparsed_wording_beside_it: exit {} - {}".format(
                    code, output.strip()
                )
            )
        else:
            print("OK: bound_claim_does_not_excuse_unparsed_wording_beside_it")

        # Duplicate SVG attributes are resolved first-wins by browsers. The
        # verifier must measure the same rank the reader's renderer keeps,
        # otherwise a later duplicate can launder a contradictory first value.
        browser_ranks = tuple(reversed([rank for rank, _alpha in LIGHT_RAMP]))
        duplicate_rank = light_source
        for (parsed_rank, alpha), browser_rank in zip(LIGHT_RAMP, browser_ranks):
            duplicate_rank = duplicate_rank.replace(
                'data-share="{}" fill="rgba({},{})"'.format(
                    parsed_rank, LIGHT_INK, alpha
                ),
                'data-share="{}" data-share="{}" fill="rgba({},{})"'.format(
                    browser_rank, parsed_rank, LIGHT_INK, alpha
                ),
                1,
            )
        if duplicate_rank == light_source:
            failures.append("could not build the duplicate-rank fixture")
        else:
            code, output = run(write(directory, "duplicate-rank.html", duplicate_rank))
            if code != 1:
                failures.append(
                    "first_duplicate_rank_matches_browser_semantics: exit {} - {}".format(
                        code, output.strip()
                    )
                )
            elif "draws larger as weaker" not in output:
                failures.append(
                    "first_duplicate_rank_matches_browser_semantics: finding does not expose "
                    "the contradicted ramp - {}".format(output.strip())
                )
            else:
                print("OK: first_duplicate_rank_matches_browser_semantics")

        # 18. The backstop is a proximity rule, not a word blocklist. A tone word
        #     and a magnitude word far apart in one sentence are not a claim;
        #     flagging them would make the gate unusable and get it switched off.
        distant = light_source.replace(
            SHIPPED_KEY,
            "Darker cells sit to the right of the layout, while the source line below the "
            "rule states a larger total",
            1,
        )
        code, output = run(write(directory, "distant.html", distant))
        if code != 0:
            failures.append(
                "tone_word_far_from_magnitude_word_is_not_a_claim: exit {} - {}".format(
                    code, output.strip()
                )
            )
        else:
            print("OK: tone_word_far_from_magnitude_word_is_not_a_claim")

        # 19. Usage errors are exit 2, distinct from a finding.
        code, output = run(directory / "does-not-exist.html")
        if code != 2:
            failures.append("missing_file_is_a_usage_error: exit {} - {}".format(code, output.strip()))
        else:
            print("OK: missing_file_is_a_usage_error")

    code, output = run()
    if code != 2:
        failures.append("no_arguments_is_a_usage_error: exit {} - {}".format(code, output.strip()))
    elif "EXAMPLES:" not in output:
        failures.append("no_arguments_is_a_usage_error: help output carries no EXAMPLES block")
    else:
        print("OK: no_arguments_is_a_usage_error")

    # 16. The accent cell is painted off-ramp in a different ink triple. It must
    #     never join the group, or one off-ramp tint would break the monotonic
    #     test and fail every honest treemap closed.
    groups = COLLECT_MEMBERS(light_source)
    ramp = max(groups.values(), key=len)
    accent_in_ramp = [member for member in ramp if member.ink != (45.0, 49.0, 66.0)]
    if accent_in_ramp:
        failures.append(
            "accent_cell_is_excluded_from_the_ramp: {} off-ink member(s) joined".format(
                len(accent_in_ramp)
            )
        )
    elif len(ramp) != 5:
        failures.append(
            "accent_cell_is_excluded_from_the_ramp: ramp has {} member(s), expected the "
            "5 non-focal cells".format(len(ramp))
        )
    else:
        print("OK: accent_cell_is_excluded_from_the_ramp")

    # 17. The polarity arithmetic itself, independent of any CLI diagnostic: one
    #     opacity, two ink roles, opposite lightness. This is the whole defect in
    #     four lines, and it is what the shipped legend contradicted.
    light_paper = RESOLVE_PAPER(light_source)
    dark_paper = RESOLVE_PAPER(dark_source)
    light_strong = RELATIVE_LUMINANCE(COMPOSITE((45.0, 49.0, 66.0), 0.16, light_paper))
    light_weak = RELATIVE_LUMINANCE(COMPOSITE((45.0, 49.0, 66.0), 0.04, light_paper))
    dark_strong = RELATIVE_LUMINANCE(COMPOSITE((245.0, 245.0, 245.0), 0.14, dark_paper))
    dark_weak = RELATIVE_LUMINANCE(COMPOSITE((245.0, 245.0, 245.0), 0.04, dark_paper))
    if not light_strong < light_weak:
        failures.append("dark_ink_on_light_paper_darkens_as_opacity_rises: it did not")
    elif not dark_strong > dark_weak:
        failures.append("white_ink_on_dark_paper_lightens_as_opacity_rises: it did not")
    else:
        print("OK: dark_ink_on_light_paper_darkens_as_opacity_rises")
        print("OK: white_ink_on_dark_paper_lightens_as_opacity_rises")

    # 18. The shipped sentence must parse as a CONTRAST claim in every variant.
    #     A phrasing the checker cannot bind is a claim nothing verifies, which
    #     is indistinguishable from the defect.
    for path in (LIGHT, DARK, FULL):
        claims = PARSE_CLAIMS(path.read_text(encoding="utf-8"))
        contrast_claims = [claim for claim in claims if claim.axis == "contrast"]
        if not contrast_claims:
            failures.append(
                "shipped_wording_binds_as_a_contrast_claim: {} bound {} claim(s), none on the "
                "contrast axis".format(path.name, len(claims))
            )
            break
    else:
        print("OK: shipped_wording_binds_as_a_contrast_claim")

    for failure in failures:
        print("FAIL: {}".format(failure))
    if failures:
        print("\n{} case(s) failed.".format(len(failures)))
        return 1
    print("\nOK verify-skin-polarity: both polarities behave, on both skins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
