#!/usr/bin/env python3
"""Adversarial tests for verify-dumbbell.py - both polarities.

A checker that only proves the good cases pass is half a checker: it cannot
tell you it would have caught the bug. Every rule below is tested twice, once
for the case that must pass and once for the case that must be rejected.

The zero cases are the reason this file exists. A sign-based domain rule reads
naturally and silently omits two inputs - data that only touches zero, and data
that is entirely zero - and the second one divides by zero in the position
formula. Both are exercised through the real scaling path here, not asserted in
prose.

Usage:
    python3 scripts/test-verify-dumbbell.py

Exit: 0 all passed, 1 a case behaved wrongly.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER = ROOT / "scripts/verify-dumbbell.py"


def _load_checker():
    """Import the checker despite its hyphenated filename."""
    spec = importlib.util.spec_from_file_location("verify_dumbbell", CHECKER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load %s" % CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_dumbbell = _load_checker()

resolve_domain = verify_dumbbell.resolve_domain
scale = verify_dumbbell.scale
contrast = verify_dumbbell.contrast
composite = verify_dumbbell.composite
is_truncated = verify_dumbbell.is_truncated
DomainError = verify_dumbbell.DomainError

FAILURES = []


def ok(condition, label):
    if condition:
        sys.stdout.write("OK: %s\n" % label)
    else:
        FAILURES.append(label)
        sys.stdout.write("FAIL: %s\n" % label)


# === DOMAIN - the cases a sign-based rule drops =============================

def test_all_zero_is_finite():
    """The case that divides by zero if the rule stops at 'positive/negative'."""
    floor, ceiling = resolve_domain([0, 0, 0, 0])
    ok(ceiling > floor, "all-zero data yields a non-degenerate domain")
    coordinates = [scale(v, floor, ceiling) for v in (0, 0, 0, 0)]
    ok(all(math.isfinite(x) for x in coordinates),
       "all-zero data produces finite coordinates")
    ok(all(x == verify_dumbbell.PLOT_X0 for x in coordinates),
       "all-zero data puts every dot on the floor, which is the truth")


def test_zero_touching_domains():
    floor, ceiling = resolve_domain([0, 5, 12])
    ok((floor, ceiling) == (0.0, 20.0),
       "positive data touching zero anchors the floor at zero")
    floor, ceiling = resolve_domain([-12, -5, 0])
    ok((floor, ceiling) == (-20.0, 0.0),
       "negative data touching zero anchors the ceiling at zero")
    for values in ([0, 5, 12], [-12, -5, 0]):
        floor, ceiling = resolve_domain(values)
        ok(all(math.isfinite(scale(v, floor, ceiling)) for v in values),
           "zero-touching %s scales finitely" % ("positive" if values[-1] else "negative"))


def test_sign_cases_resolve():
    ok(resolve_domain([18, 66, 71]) == (0.0, 100.0),
       "all-positive data anchors the floor at zero")
    ok(resolve_domain([-71, -18]) == (-100.0, 0.0),
       "all-negative data anchors the ceiling at zero")
    floor, ceiling = resolve_domain([-20, 5, 40])
    ok(floor < 0 < ceiling, "data crossing zero brackets both sides")


def test_identical_and_tiny_values():
    floor, ceiling = resolve_domain([7, 7])
    ok(ceiling > floor and math.isfinite(scale(7, floor, ceiling)),
       "a pair of identical non-zero values still scales")
    floor, ceiling = resolve_domain([0.0004, 0.0009])
    ok(ceiling > floor, "sub-unit magnitudes still yield a usable domain")


def test_empty_and_non_finite_rejected():
    """The other polarity: garbage in must raise, not return a silent domain."""
    for label, values in (("empty input", []),
                          ("NaN in input", [1.0, float("nan")]),
                          ("infinity in input", [1.0, float("inf")])):
        try:
            resolve_domain(values)
        except DomainError:
            ok(True, "%s is rejected" % label)
        else:
            ok(False, "%s was NOT rejected" % label)


def test_truncated_bounds_are_detected():
    """The honesty rule, executable: observed min/max must read as truncation."""
    values = [18, 66, 34, 71]
    ok(is_truncated(values, 18.0, 71.0),
       "bounds taken from the observed extremes are reported as truncation")
    resolved = resolve_domain(values)
    ok(not is_truncated(values, *resolved),
       "correctly resolved bounds are NOT reported as truncation")


def test_scaling_preserves_gap_ratios():
    """Two rows on one scale: drawn gaps must stay proportional to real ones."""
    values = [10, 30, 40, 80]
    floor, ceiling = resolve_domain(values)
    gap_a = scale(30, floor, ceiling) - scale(10, floor, ceiling)
    gap_b = scale(80, floor, ceiling) - scale(40, floor, ceiling)
    ok(abs(gap_b / gap_a - 2.0) < 1e-9,
       "a doubled data gap draws exactly twice as wide")


# === CONTRAST - both polarities =============================================

def test_documented_marks_clear_the_threshold():
    for label, ink, alpha, paper in verify_dumbbell.CONNECTORS:
        ratio = contrast(composite(ink, alpha, paper), paper)
        ok(ratio >= 3.0, "%s clears 3:1 (%.3f:1)" % (label, ratio))
    for label, stroke, paper in verify_dumbbell.ENDPOINT_STROKES:
        ratio = contrast(stroke, paper)
        ok(ratio >= 3.0, "%s clears 3:1 (%.3f:1)" % (label, ratio))


def test_rejected_treatments_are_caught():
    """The other polarity: the treatments this PR replaced must still fail."""
    hairline = composite("#2d3142", 0.25, "#f5f5f5")
    ok(contrast(hairline, "#f5f5f5") < 3.0,
       "the original 25%% hairline connector is correctly under 3:1")
    ok(contrast("#eb6c36", "#f5f5f5") < 3.0,
       "an unstroked accent endpoint is correctly under 3:1 on light paper")
    ok(contrast("#7a8399", "#f5f5f5") < 4.5,
       "the soft token is correctly under 4.5:1 and unusable for text")


def test_checker_fails_closed_on_a_stripped_reference(tmp_path: Path):
    empty = tmp_path / "type-bar.md"
    empty.write_text("# Bar\n\nNo variants here.\n", encoding="utf-8")
    findings = verify_dumbbell.check_reference(empty)
    ok(bool(findings), "a reference with no dumbbell section is a finding, not a pass")

    missing = tmp_path / "partial.md"
    missing.write_text("# Bar\n\n## Variants\n\n- Dumbbell: floor and ceil.\n",
                       encoding="utf-8")
    findings = verify_dumbbell.check_reference(missing)
    ok(bool(findings),
       "a dumbbell section missing the connector tokens is a finding")

    absent = tmp_path / "nope.md"
    ok(bool(verify_dumbbell.check_reference(absent)),
       "a missing reference file is a finding, not a pass")


def test_shipped_reference_passes():
    findings = verify_dumbbell.check_reference(verify_dumbbell.REFERENCE)
    ok(not findings,
       "the shipped reference documents every token the checker verifies")


def main() -> int:
    import tempfile

    test_all_zero_is_finite()
    test_zero_touching_domains()
    test_sign_cases_resolve()
    test_identical_and_tiny_values()
    test_empty_and_non_finite_rejected()
    test_truncated_bounds_are_detected()
    test_scaling_preserves_gap_ratios()
    test_documented_marks_clear_the_threshold()
    test_rejected_treatments_are_caught()
    with tempfile.TemporaryDirectory() as directory:
        test_checker_fails_closed_on_a_stripped_reference(Path(directory))
    test_shipped_reference_passes()

    if FAILURES:
        sys.stderr.write("\n%d case(s) behaved wrongly:\n" % len(FAILURES))
        for failure in FAILURES:
            sys.stderr.write("  - %s\n" % failure)
        return 1
    sys.stdout.write("\nAll dumbbell checker tests passed\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
