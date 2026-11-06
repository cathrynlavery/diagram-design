#!/usr/bin/env python3
"""Regression tests for verify-sequence-oauth.py.

verify-sequence-oauth.py drives its checks against the real shipped
sequence-diagram assets from a top-level main(), so it is exercised here as a
CLI smoke test plus mutations of the real shipped SVGs. Pure structural checks
exercise all three skins; a temporary-copy CLI case also verifies the failure
exit code and diagnostic before the skin linter is reached.
"""

from __future__ import annotations

import re
import runpy
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERIFIER = ROOT / "scripts/verify-sequence-oauth.py"
TYPE_SEQ = ROOT / "skills/diagram-design/references/type-sequence.md"
ASSETS = ROOT / "skills/diagram-design/assets"
COLD = [
    ASSETS / "example-sequence.html",
    ASSETS / "example-sequence-dark.html",
    ASSETS / "example-sequence-full.html",
]
OAUTH = [
    ASSETS / "example-sequence-oauth.html",
    ASSETS / "example-sequence-oauth-dark.html",
    ASSETS / "example-sequence-oauth-full.html",
]

CHECK = runpy.run_path(str(VERIFIER))["check_oauth"]


def replace_once(source: str, old: str, new: str) -> str:
    if old not in source:
        raise AssertionError(f"mutation target absent: {old}")
    return source.replace(old, new, 1)


def change_return(source: str, y: int, replacement: str = "") -> str:
    match = re.search(rf'<line\b[^>]*\by1="{y}"[^>]*>', source)
    if match is None:
        raise AssertionError(f"no return at y={y}")
    return replace_once(source, match.group(), replace_once(match.group(), 'stroke-dasharray="5,4"', replacement))


def restore_child_paint(source: str, tag: str = "tspan", painted: bool = True) -> str:
    def restore(match):
        attrs = match[1]
        colour = re.search(r'\bfill="([^"]*)"', attrs)
        if colour is None:
            raise AssertionError("guard fill absent")
        paint = f' fill="{colour[1]}"' if painted else ""
        return (re.sub(r'\bfill="[^"]*"', 'fill="none"', attrs) + '>'
                + f'<{tag}{paint}>[token valid]</{tag}></text>')
    changed, count = re.subn(r'(<text\b[^>]*?)>\[token valid\]</text>', restore, source, count=1)
    if count != 1:
        raise AssertionError("guard text absent")
    return changed


def wrap_response(source: str, label: str, attrs: str = "", tag: str = "tspan") -> str:
    # The final BODY label belongs to the retry, not the headline success.
    before, separator, after = source.rpartition(f">{label}</text>")
    if not separator:
        raise AssertionError(f"response label absent: {label}")
    return before + f"><{tag} {attrs}>{label}</{tag}></text>" + after


def check_mutations() -> None:
    for path in OAUTH:
        original = path.read_text(encoding="utf-8")
        positives = {
            "shipped (solid headline success allowed)": original,
            "single-quoted attributes": re.sub(r'([\w-]+)="([^"]*)"',
                lambda m: f"{m[1]}='{m[2]}'" if "'" not in m[2] else m[0], original),
            "reordered return attributes": re.sub(r'<line\b([^>]*)/?>',
                lambda m: "<line " + " ".join(reversed(re.findall(r'[\w-]+="[^"]*"', m[1]))) + "/>", original),
            "guard split into tspans": replace_once(original, "[token valid]</text>", "<tspan>[token </tspan><tspan>valid]</tspan></text>"),
            "layout shifted down": re.sub(r'\b(y|y1|y2)="(\d+)"',
                lambda m: f'{m[1]}="{int(m[2]) + 16}.0"', original),
            "extra words in comments": original + "<!-- <text>[token valid]</text> -->",
            "SVG translated as a group": replace_once(replace_once(original,
                "</defs>", '</defs><g transform="translate(12, 16)">'), "</svg>", "</g></svg>"),
            "unfilled return lines": re.sub(r'(<line\b[^>]*\by1="(?:368|456|544)")', r'\1 fill="none"', original),
            "group fill restored by child text": replace_once(replace_once(original,
                "</defs>", '</defs><g fill="none">'), "</svg>", "</g></svg>"),
            "pixel dash lengths": original.replace('stroke-dasharray="5,4"', 'stroke-dasharray="5px,4px"'),
            "percentage dash lengths": original.replace('stroke-dasharray="5,4"', 'stroke-dasharray="5%,4%"'),
            "group stroke restored by child marks": replace_once(replace_once(original,
                "</defs>", '</defs><g stroke="none">'), "</svg>", "</g></svg>"),
            "guard paint restored by child span": restore_child_paint(original),
            "guard paint restored by linked text": restore_child_paint(original, tag="a"),
            "explicit unmarked API lifeline": replace_once(original,
                'x1="480" y1="128" x2="480" y2="624"', 'x1="480" y1="128" x2="480" y2="624" marker-end="none"'),
            "inline unmarked API lifeline": replace_once(original,
                'x1="480" y1="128" x2="480" y2="624"', 'x1="480" y1="128" x2="480" y2="624" style="marker-end: none"'),
            "literal opacity on guard": replace_once(original,
                ">[token valid]</text>", ' style="opacity: 0.5 !important">[token valid]</text>'),
            "literal percentage opacity on guard": replace_once(original,
                ">[token valid]</text>", ' opacity="50%">[token valid]</text>'),
            "responsive SVG stylesheet dimensions": original + '<style>svg { width: 100%; height: auto; }</style>',
            "responsive SVG inline dimensions": replace_once(original,
                '<svg viewBox=', '<svg style="width: 100%; height: auto" viewBox='),
            "unpositioned response spans": wrap_response(wrap_response(wrap_response(original,
                "401"), "200 · NEW ACCESS"), "200 · BODY"),
            "separate decorative SVG": original + '<svg aria-hidden="true"><rect x="0" y="0" width="8" height="8"/></svg>',
        }
        for selector in ('svg[role=img]', 'svg[role = "img"]', 'svg:not(.icon)',
                         '.frame svg[role=img]', 'body:has(svg, rect)', 'svg[role=img], .frame'):
            positives[f"responsive qualified selector {selector}"] = original + f'<style>{selector} {{ width: 100%; height: auto; }}</style>'
        for label, source in positives.items():
            findings = CHECK(source)
            if findings:
                raise AssertionError(f"{path.name}: valid {label} rejected: {findings}")

        negatives = {}
        for y in (368, 456, 544):
            negatives[f"solid return at {y}"] = (change_return(original, y), "must be dashed")
            negatives[f"none dasharray at {y}"] = (change_return(original, y, 'stroke-dasharray="none"'), "must be dashed")
            negatives[f"zero-gap dasharray at {y}"] = (change_return(original, y, 'stroke-dasharray="5,0"'), "must be dashed")
        negatives["inline solid return"] = (change_return(original, 456,
            'stroke-dasharray="5,4" style="stroke-dasharray: none"'), "must be dashed")
        for guard, diagnostic in (("[token valid]", "first ALT region"), ("[else · 401]", "second ALT region")):
            for tag in ("title", "desc", "defs"):
                negatives[f"{guard} in {tag}"] = (replace_once(original, f">{guard}</text>",
                    f"><{tag}>{guard}</{tag}></text>"), diagnostic)
            negatives[f"{guard} in comment"] = (replace_once(original, f">{guard}</text>",
                f"> </text><!-- {guard} -->"), diagnostic)
            for hiding in ('display="none"', 'visibility="hidden"', 'opacity="0"',
                           'fill-opacity="0"', 'fill="none"', 'fill="rgba(0, 0, 0, 0)"',
                           'fill="#00000000"', 'fill="#0000"',
                           'font-size="0em"',
                           'style="display: none !important"'):
                negatives[f"{guard} hidden by {hiding}"] = (replace_once(original,
                    f">{guard}</text>", f"><tspan {hiding}>{guard}</tspan></text>"), diagnostic)
            negatives[f"{guard} in hidden group"] = (re.sub(
                rf'(<text\b[^>]*>{re.escape(guard)}</text>)', r'<g opacity="0">\1</g>', original, count=1), diagnostic)
            negatives[f"{guard} hidden by CSS"] = (replace_once(original,
                f">{guard}</text>", f' class="hidden-guard">{guard}</text>')
                + "<style>.hidden-guard { display: none; }</style>", diagnostic)
        negatives["guard in wrong region"] = (replace_once(original, 'y="244"', 'y="344"'), "first ALT region")
        negatives["else guard outside frame"] = (replace_once(original, 'y="336"', 'y="636"'), "second ALT region")
        negatives["missing operator with legend ALT retained"] = (replace_once(original, ">ALT</text>", "> </text>"), "ALT operator")
        negatives["missing divider"] = (replace_once(original, 'stroke-dasharray="4,3"', 'stroke-dasharray="none"'), "ALT operator")
        negatives["short activation"] = (replace_once(original, 'width="8" height="104"', 'width="8" height="40"'), "activation")
        negatives["guard translated to wrong region"] = (replace_once(original,
            ">[token valid]</text>", ' transform="translate(0, 100)">[token valid]</text>'), "first ALT region")
        negatives["independently positioned guard span"] = (replace_once(original,
            ">[token valid]</text>", '><tspan transform="translate(0, 100)">[token valid]</tspan></text>'), "guard spans")
        negatives["activation starts after initial call"] = (replace_once(original,
            'y="180" width="8" height="104"', 'y="260" width="8" height="24"'), "activation")
        negatives["activation misses API lifeline"] = (replace_once(original,
            'x="476" y="180" width="8" height="104"', 'x="468" y="180" width="8" height="104"'), "activation")
        negatives["zero-length fragment divider"] = (replace_once(original,
            'x1="96" y1="312" x2="832"', 'x1="96" y1="312" x2="96"'), "ALT operator")
        negatives["unpainted linked guard"] = (restore_child_paint(original, tag="a", painted=False), "first ALT region")
        negatives["linked guard positioned separately"] = (restore_child_paint(original, tag="a").replace(
            '<a fill=', '<a transform="translate(0, 100)" fill=', 1), "guard spans")
        for offset in ('dy="100"', 'dx="1000"'):
            negatives[f"guard displaced by {offset}"] = (replace_once(original,
                ">[token valid]</text>", f" {offset}>[token valid]</text>"), "first ALT region")
        negatives["stylesheet makes access return solid"] = (change_return(original, 456,
            'stroke-dasharray="5,4" class="solid-return"')
            + "<style>.solid-return { stroke-dasharray: none; }</style>", "stylesheet override")
        negatives["CSS displaces guard"] = (replace_once(original,
            ">[token valid]</text>", ' style="transform: translateY(100px)">[token valid]</text>'), "inline SVG geometry")
        negatives["guard clipped away"] = (replace_once(original,
            ">[token valid]</text>", ' clip-path="inset(100%)">[token valid]</text>'), "clipping override")
        negatives["unpainted initial activation"] = (replace_once(original,
            'y="180" width="8" height="104"', 'y="180" width="8" height="104" style="fill: none; stroke: none"'), "activation")
        for paint in ('stroke-opacity="0"', 'stroke="none"', 'stroke-width="0"'):
            line = re.search(r'<line\b[^>]*\by1="368"[^>]*>', original)
            if line is None:
                raise AssertionError("no rejection return")
            changed_line = re.sub(r'\bstroke="[^"]*"', '', line.group()) if paint == 'stroke="none"' else line.group()
            changed_line = re.sub(r'\bstroke-width="[^"]*"', '', changed_line) if paint == 'stroke-width="0"' else changed_line
            changed_line = changed_line.replace('<line ', f'<line {paint} ', 1)
            negatives[f"unpainted rejection return {paint}"] = (replace_once(original, line.group(), changed_line), "ordinary OAuth return")
        for y in (368, 456, 544):
            line = re.search(rf'<line\b[^>]*\by1="{y}"[^>]*>', original)
            if line is None:
                raise AssertionError(f"no return at y={y}")
            missing = replace_once(original, line.group(), "")
            negatives[f"missing return {y} plus reversed legend"] = (replace_once(missing,
                'x1="448" y1="684" x2="476" y2="684"',
                'x1="476" y1="684" x2="448" y2="684"'), "ordinary OAuth return")
        for guard in ("[token valid]", "[else · 401]"):
            for prop in ("opacity", "fill-opacity", "stroke-opacity", "visibility", "display", "font-size", "fill", "stroke"):
                negatives[f"{guard} unresolved {prop}"] = (replace_once(original,
                    f">{guard}</text>", f' style="--hidden: 0; {prop}: var(--hidden)">{guard}</text>'), "unresolved visibility")
            negatives[f"{guard} unresolved presentation opacity"] = (replace_once(original,
                f">{guard}</text>", f' opacity="var(--hidden)">{guard}</text>'), "unresolved visibility")
            negatives[f"{guard} unresolved stylesheet opacity"] = (replace_once(original,
                f">{guard}</text>", f' class="variable-opacity">{guard}</text>')
                + '<style>.variable-opacity { --hidden: 0; opacity: var(--hidden); }</style>', "unresolved visibility")
            for attrs in ('x="0" y="400"', 'width="10" height="10" viewBox="0 0 1000 1000"'):
                negatives[f"{guard} nested SVG {attrs}"] = (re.sub(
                    rf'(<text\b[^>]*>{re.escape(guard)}</text>)',
                    rf'<svg {attrs}>\1</svg>', original, count=1), "nested SVG")
        negatives["guard in a separate SVG"] = (replace_once(original,
            ">[token valid]</text>", "> </text>")
            + '<svg><text x="100" y="244">[token valid]</text></svg>', "first ALT region")
        for prop in ("width", "height"):
            negatives[f"activation inline {prop}"] = (replace_once(original,
                'y="180" width="8" height="104"', f'y="180" width="8" height="104" style="{prop}: 1px"'), "rectangle size override")
            negatives[f"activation stylesheet {prop}"] = (replace_once(original,
                'y="180" width="8" height="104"', 'y="180" width="8" height="104" class="short-activation"')
                + f'<style>.short-activation {{ {prop}: 1px; }}</style>', "rectangle size override")
        for selector in ('rect[width = "8"]', 'svg rect:not(.safe)'):
            negatives[f"qualified rectangle size selector {selector}"] = (original
                + f'<style>{selector} {{ height: 1px; }}</style>', "rectangle size override")
        for label in ("401", "200 · NEW ACCESS", "200 · BODY"):
            for tag in ("tspan", "a"):
                for attrs in ('dy="250"', 'dx="1000"', 'x="0"', 'y="0"', 'transform="translate(0, 250)"'):
                    negatives[f"positioned response {label} {tag} {attrs}"] = (wrap_response(original,
                        label, attrs, tag), "response label spans")
            positioned = wrap_response(original, label, 'dx="1000"')
            negatives[f"positioned whitespace before response {label}"] = (replace_once(positioned,
                f'<tspan dx="1000">{label}</tspan>', f'<tspan dx="1000"> </tspan>{label}'), "response label spans")
        negatives["positioned whitespace within guard"] = (replace_once(original,
            ">[token valid]</text>", '>[token<tspan dx="1000"> </tspan>valid]</text>'), "guard spans")
        negatives["hidden positioned whitespace within guard"] = (replace_once(original,
            ">[token valid]</text>", '>[token<tspan dx="1000" opacity="0"> </tspan>valid]</text>'), "guard spans")
        for label, (source, diagnostic) in negatives.items():
            if source == original:
                raise AssertionError(f"{path.name}: {label} mutation did not change source")
            findings = CHECK(source)
            if not any(diagnostic in finding for finding in findings):
                raise AssertionError(f"{path.name}: {label} expected {diagnostic!r}, got {findings}")
        print(f"OK: {path.name}: {len(positives)} valid forms and {len(negatives)} rejected mutations")


def run_verifier(cwd: Path, verifier: Path = VERIFIER) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(verifier)],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    check_mutations()
    # The shipped repo must pass all gates as-is.
    result = run_verifier(ROOT)
    if result.returncode != 0 or "ALL GATES PASSED" not in result.stdout:
        raise AssertionError(
            f"shipped repo failed verify-sequence-oauth.py\n{result.stdout}{result.stderr}"
        )
    print("OK: shipped repo passes verify-sequence-oauth.py")

    # Removing the dashed-return marker from the 401 response must be rejected.
    # verify-sequence-oauth.py resolves every path relative to its own file
    # location (ROOT = parent of scripts/), so the adversarial case runs
    # against a minimal temporary copy that mirrors just the relative paths
    # main() reads before the dashed-return check (type-sequence.md plus the
    # cold-cache and oauth example trios) — not the full repository tree.
    with tempfile.TemporaryDirectory(prefix="verify-sequence-oauth-") as temp_dir:
        temp_root = Path(temp_dir) / "repo"
        temp_verifier = temp_root / "scripts/verify-sequence-oauth.py"
        temp_verifier.parent.mkdir(parents=True, exist_ok=True)
        temp_verifier.write_text(VERIFIER.read_text(encoding="utf-8"), encoding="utf-8")

        temp_type_seq = temp_root / TYPE_SEQ.relative_to(ROOT)
        temp_type_seq.parent.mkdir(parents=True, exist_ok=True)
        temp_type_seq.write_text(TYPE_SEQ.read_text(encoding="utf-8"), encoding="utf-8")

        for path in (*COLD, *OAUTH):
            dest = temp_root / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

        oauth_copy = temp_root / OAUTH[0].relative_to(ROOT)
        original = oauth_copy.read_text(encoding="utf-8")
        target_line = (
            '<line x1="476" y1="368" x2="168" y2="368" stroke="#4f5d75" '
            'stroke-width="1.2" stroke-dasharray="5,4" marker-end="url(#arrow)"/>'
        )
        if target_line not in original:
            raise AssertionError(
                "expected shipped example-sequence-oauth.html to contain the dashed "
                "401 return line at y1=368"
            )
        broken = original.replace(
            target_line,
            target_line.replace('stroke-dasharray="5,4" ', ""),
            1,
        )
        if broken == original:
            raise AssertionError("failed to mutate example-sequence-oauth.html for the test")
        oauth_copy.write_text(broken, encoding="utf-8")

        # verify-sequence-oauth.py resolves ROOT from its own __file__, so the
        # adversarial run must invoke the copy inside temp_root, not VERIFIER.
        broken_result = run_verifier(temp_root, verifier=temp_verifier)
        if broken_result.returncode == 0:
            raise AssertionError(
                f"broken dashed return was accepted\n{broken_result.stdout}{broken_result.stderr}"
            )
        if "must be dashed" not in broken_result.stdout + broken_result.stderr:
            raise AssertionError(
                "expected a 'must be dashed' failure, got "
                f"{broken_result.stdout}{broken_result.stderr}"
            )
        print("OK: removing the dashed 401 return marker is rejected")

    print("All sequence-oauth verifier tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
