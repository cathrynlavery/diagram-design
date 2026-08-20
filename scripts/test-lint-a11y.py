#!/usr/bin/env python3
"""Adversarial tests for lint-skin.py's accessible-SVG contract."""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
LINTER = ROOT / "scripts/lint-skin.py"
BUILD_ICONS = ROOT / "scripts/build-icons.py"
MOTION_TEMPLATE = ROOT / "skills/diagram-design/assets/template-motion.html"

VALID_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 600" role="img"
     aria-labelledby="fixture-title fixture-desc">
  <title id="fixture-title">Fixture diagram</title>
  <desc id="fixture-desc">Diagram showing a fixture connected to a result.</desc>
  <rect width="10" height="10"/>
</svg>
"""


def run_linter(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(LINTER), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def require_failure(name: str, html: str, expected: str, directory: Path) -> None:
    path = directory / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    result = run_linter(path)
    if result.returncode != 1:
        raise AssertionError(
            f"{name}: expected exit 1, got {result.returncode}\n{result.stdout}{result.stderr}"
        )
    if f"a11y: {expected}" not in result.stdout:
        raise AssertionError(
            f"{name}: missing expected a11y finding {expected!r}\n{result.stdout}"
        )
    print(f"OK: {name} rejected — {expected}")


def require_pass(name: str, html: str, directory: Path) -> None:
    path = directory / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    result = run_linter(path)
    if result.returncode != 0:
        raise AssertionError(
            f"{name}: expected exit 0, got {result.returncode}\n{result.stdout}{result.stderr}"
        )
    if "a11y:" in result.stdout:
        raise AssertionError(f"{name}: unexpected a11y finding\n{result.stdout}")
    print(f"OK: {name} accepted")


def require_lint_finding(
    name: str, html: str, expected: str, directory: Path
) -> None:
    path = directory / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    result = run_linter(path)
    if result.returncode != 1 or expected not in result.stdout:
        raise AssertionError(
            f"{name}: expected finding {expected!r}\n{result.stdout}{result.stderr}"
        )
    print(f"OK: {name} rejected — {expected}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lint-a11y-") as temp_dir:
        directory = Path(temp_dir)

        require_failure(
            "missing-role",
            VALID_SVG.replace(' role="img"', ""),
            'diagram <svg> must carry role="img"',
            directory,
        )
        require_failure(
            "unresolved-labelled-by",
            VALID_SVG.replace(
                'aria-labelledby="fixture-title fixture-desc"',
                'aria-labelledby="absent-title absent-desc"',
            ),
            "aria-labelledby references missing id(s): absent-title, absent-desc",
            directory,
        )
        require_failure(
            "labels-unrelated-elements",
            VALID_SVG.replace(' id="fixture-title"', "")
            .replace(' id="fixture-desc"', "")
            .replace(
                '  <rect width="10" height="10"/>',
                '  <g id="fixture-title"></g>\n'
                '  <g id="fixture-desc"></g>\n'
                '  <rect width="10" height="10"/>',
            ),
            "aria-labelledby must name the <title> and <desc> IDs",
            directory,
        )
        require_failure(
            "late-title",
            VALID_SVG.replace(
                '  <title id="fixture-title">Fixture diagram</title>\n  <desc',
                '  <defs></defs>\n  <title id="fixture-title">Fixture diagram</title>\n  <desc',
            ),
            "<title> must be the first child element of <svg>",
            directory,
        )
        require_failure(
            "empty-desc",
            VALID_SVG.replace(
                "Diagram showing a fixture connected to a result.", "  "
            ),
            "<desc> must not be empty",
            directory,
        )
        require_failure(
            "bare-ids",
            VALID_SVG.replace("fixture-title", "title").replace(
                "fixture-desc", "desc"
            ),
            'bare id="title" and id="desc" are not allowed',
            directory,
        )
        require_failure(
            "wrong-file-slug",
            VALID_SVG,
            'accessible-name IDs must match file slug "wrong-file-slug": '
            'expected "wrong-file-slug-title" / "wrong-file-slug-desc"',
            directory,
        )
        require_failure(
            "placeholder-ids",
            VALID_SVG.replace("fixture-title", "[diagram-slug]-title").replace(
                "fixture-desc", "[diagram-slug]-desc"
            ),
            "accessible-name IDs contain unresolved placeholder(s): "
            "[diagram-slug]-title, [diagram-slug]-desc",
            directory,
        )
        require_failure(
            "duplicate-naming-ids",
            VALID_SVG + VALID_SVG,
            'duplicate accessible-name id="fixture-desc" is not allowed',
            directory,
        )
        require_failure(
            "missing-viewbox",
            VALID_SVG.replace(' viewBox="0 0 800 600"', ""),
            "diagram <svg> must have a viewBox attribute",
            directory,
        )
        require_failure(
            "invalid-viewbox",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 -10 100"'),
            'viewBox "0 0 -10 100" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_failure(
            "viewbox-zero-height",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 800 0"'),
            'viewBox "0 0 800 0" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_failure(
            "viewbox-malformed-token",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 800px 600"'),
            'viewBox "0 0 800px 600" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_failure(
            "title-too-long",
            VALID_SVG.replace("Fixture diagram", "A" * 61),
            "<title> must be 60 characters or fewer (got 61)",
            directory,
        )
        require_pass(
            "viewbox-comma-separated",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0,0,800,600"').replace(
                "fixture-title", "viewbox-comma-separated-title"
            ).replace("fixture-desc", "viewbox-comma-separated-desc"),
            directory,
        )
        require_failure(
            "viewbox-nonfinite-width",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 inf 600"').replace(
                "fixture-title", "viewbox-nonfinite-width-title"
            ).replace("fixture-desc", "viewbox-nonfinite-width-desc"),
            'viewBox "0 0 inf 600" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_failure(
            "viewbox-nonfinite-height",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 800 inf"').replace(
                "fixture-title", "viewbox-nonfinite-height-title"
            ).replace("fixture-desc", "viewbox-nonfinite-height-desc"),
            'viewBox "0 0 800 inf" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_failure(
            "viewbox-underscore-width",
            VALID_SVG.replace('viewBox="0 0 800 600"', 'viewBox="0 0 1_000 600"').replace(
                "fixture-title", "viewbox-underscore-width-title"
            ).replace("fixture-desc", "viewbox-underscore-width-desc"),
            'viewBox "0 0 1_000 600" is not valid (expected "min-x min-y width height" with positive size)',
            directory,
        )
        require_pass(
            "decorative",
            '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            '<path d="M0 0h1v1z"/></svg>\n',
            directory,
        )
        template_source = MOTION_TEMPLATE.read_text(encoding="utf-8")
        controller_match = re.search(
            r"<script\b[^>]*data-diagram-controls[^>]*>(.*?)</script\s*>",
            template_source,
            re.IGNORECASE | re.DOTALL,
        )
        if controller_match is None:
            raise AssertionError("canonical motion controller could not be extracted")
        controller_body = controller_match.group(1)
        canonical_script = f"<script data-diagram-controls>{controller_body}</script>\n"
        motion_svg = VALID_SVG.replace("fixture-title", "motion-controls-title").replace(
            "fixture-desc", "motion-controls-desc"
        )
        require_pass(
            "motion-controls",
            motion_svg + canonical_script,
            directory,
        )
        duplicate_svg = VALID_SVG.replace(
            "fixture-title", "duplicate-controller-title"
        ).replace("fixture-desc", "duplicate-controller-desc")
        require_lint_finding(
            "duplicate-controller",
            duplicate_svg + canonical_script + canonical_script,
            "script: only one canonical motion controller is allowed",
            directory,
        )
        unscoped_svg = VALID_SVG.replace("fixture-title", "unscoped-script-title").replace(
            "fixture-desc", "unscoped-script-desc"
        )
        require_lint_finding(
            "unscoped-script",
            unscoped_svg + "<script>void 0;</script>\n",
            "script: only the canonical data-diagram-controls attribute is allowed",
            directory,
        )
        controller_attacks = {
            "network-controller": "fetch('/collect');",
            "dynamic-html-controller": "document.body.innerHTML = '<p>changed</p>';",
            "import-controller": "import('./remote.js');",
            "eval-controller": "eval('1 + 1');",
            "navigation-controller": "location.assign('https://example.invalid');",
            "modified-controller": "void 0;",
        }
        for name, injected in controller_attacks.items():
            attack_svg = VALID_SVG.replace(
                "fixture-title", f"{name}-title"
            ).replace("fixture-desc", f"{name}-desc")
            modified = controller_body.replace("(() => {", f"(() => {{\n      {injected}", 1)
            require_lint_finding(
                name,
                attack_svg + f"<script data-diagram-controls>{modified}</script>\n",
                "script: motion controller must exactly match template-motion.html",
                directory,
            )
        unclosed_svg = VALID_SVG.replace("fixture-title", "unclosed-script-title").replace(
            "fixture-desc", "unclosed-script-desc"
        )
        require_lint_finding(
            "unclosed-motion-script",
            unclosed_svg + f"<script data-diagram-controls>{controller_body}\n",
            "script: motion controller must have a closing script tag",
            directory,
        )
        remote_svg = VALID_SVG.replace("fixture-title", "remote-script-title").replace(
            "fixture-desc", "remote-script-desc"
        )
        require_lint_finding(
            "remote-script",
            remote_svg
            + f'<script data-diagram-controls src="https://example.invalid/c.js">{controller_body}</script>\n',
            "script: only the canonical data-diagram-controls attribute is allowed",
            directory,
        )
        type_svg = VALID_SVG.replace("fixture-title", "script-type-title").replace(
            "fixture-desc", "script-type-desc"
        )
        require_lint_finding(
            "script-type-override",
            type_svg
            + f'<script data-diagram-controls type="application/json">{controller_body}</script>\n',
            "script: only the canonical data-diagram-controls attribute is allowed",
            directory,
        )

        inter_svg = VALID_SVG.replace("fixture-title", "inter-tight-title").replace(
            "fixture-desc", "inter-tight-desc"
        )
        require_pass(
            "inter-tight",
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;600&display=swap">\n'
            '<style>text { font-family: "Inter Tight", sans-serif; }</style>\n'
            + inter_svg,
            directory,
        )
        lookalike_svg = VALID_SVG.replace(
            "fixture-title", "google-fonts-lookalike-title"
        ).replace("fixture-desc", "google-fonts-lookalike-desc")
        require_lint_finding(
            "google-fonts-lookalike",
            '<link rel="stylesheet" href="https://fonts.googleapis.com.evil.test/css2?family=Inter+Tight">\n'
            '<style>text { font-family: "Inter Tight", sans-serif; }</style>\n'
            + lookalike_svg,
            "external-asset: external HTTP(S) <link> is not allowed",
            directory,
        )
        bad_path_svg = VALID_SVG.replace(
            "fixture-title", "google-fonts-bad-path-title"
        ).replace("fixture-desc", "google-fonts-bad-path-desc")
        require_lint_finding(
            "google-fonts-bad-path",
            '<link rel="stylesheet" href="https://fonts.googleapis.com/css2.evil?family=Inter+Tight">\n'
            + bad_path_svg,
            "external-asset: external HTTP(S) <link> is not allowed",
            directory,
        )
        protocol_relative_svg = VALID_SVG.replace(
            "fixture-title", "protocol-relative-font-title"
        ).replace("fixture-desc", "protocol-relative-font-desc")
        require_lint_finding(
            "protocol-relative-font",
            '<link rel="stylesheet" href="//fonts.googleapis.com/css2?family=Inter+Tight">\n'
            + protocol_relative_svg,
            "external-asset: external HTTP(S) <link> is not allowed",
            directory,
        )
        unquoted_remote_svg = VALID_SVG.replace(
            "fixture-title", "unquoted-remote-title"
        ).replace("fixture-desc", "unquoted-remote-desc")
        require_lint_finding(
            "unquoted-remote-link",
            '<link rel=stylesheet href=https://evil.example/x.css>\n'
            + unquoted_remote_svg,
            "external-asset: external resource in <link> href is not allowed",
            directory,
        )
        bypass_svg = VALID_SVG.replace("fixture-title", "resource-bypass-title").replace(
            "fixture-desc", "resource-bypass-desc"
        )
        require_lint_finding(
            "srcset-second-candidate",
            '<img srcset="local.png 1x, https://evil.example/remote.png 2x">\n'
            + bypass_svg,
            "external-asset: external resource in <img> srcset is not allowed",
            directory,
        )
        require_lint_finding(
            "protocol-relative-css-url",
            '<style>.x { background: url(//evil.example/x.png); }</style>\n'
            + bypass_svg,
            "external-asset: non-fragment CSS url() is not allowed",
            directory,
        )
        require_lint_finding(
            "event-handler",
            '<div onclick="alert(1)"></div>\n' + bypass_svg,
            "script: executable attribute onclick on <div> is not allowed",
            directory,
        )
        require_lint_finding(
            "javascript-url",
            '<iframe src="javascript:alert(1)"></iframe>\n' + bypass_svg,
            "script: executable attribute src on <iframe> is not allowed",
            directory,
        )
        require_lint_finding(
            "javascript-control-character",
            '<iframe src="jav&#9;ascript:alert(1)"></iframe>\n' + bypass_svg,
            "script: executable attribute src on <iframe> is not allowed",
            directory,
        )
        require_lint_finding(
            "base-href",
            '<base href="https://evil.example/">\n' + bypass_svg,
            "script: executable attribute href on <base> is not allowed",
            directory,
        )
        require_lint_finding(
            "iframe-srcdoc",
            '<iframe srcdoc="&lt;script&gt;alert(1)&lt;/script&gt;"></iframe>\n'
            + bypass_svg,
            "script: executable attribute srcdoc on <iframe> is not allowed",
            directory,
        )
        require_lint_finding(
            "css-escaped-scheme",
            '<style>.x { background: url(https\\3a //evil.example/x); }</style>\n'
            + bypass_svg,
            "external-asset: non-fragment CSS url() is not allowed",
            directory,
        )
        arbitrary_font_svg = VALID_SVG.replace(
            "fixture-title", "arbitrary-font-title"
        ).replace("fixture-desc", "arbitrary-font-desc")
        require_lint_finding(
            "arbitrary-font",
            '<style>text { font-family: "Unapproved Sans", sans-serif; }</style>\n'
            + arbitrary_font_svg,
            "font-family: unsupported font family: Unapproved Sans",
            directory,
        )
        cjk_name_svg = VALID_SVG.replace("fixture-title", "cjk-name-stack-title").replace(
            "fixture-desc", "cjk-name-stack-desc"
        )
        require_pass(
            "cjk-name-stack",
            cjk_name_svg.replace(
                "</svg>",
                '<text font-family="\'Geist\', \'Hiragino Sans\', \'Noto Sans JP\', '
                '\'Yu Gothic\', sans-serif">認証サービス</text>\n</svg>',
            ),
            directory,
        )
        cjk_mono_svg = VALID_SVG.replace("fixture-title", "cjk-mono-stack-title").replace(
            "fixture-desc", "cjk-mono-stack-desc"
        )
        require_pass(
            "cjk-mono-stack",
            cjk_mono_svg.replace(
                "</svg>",
                '<text font-family="\'Geist Mono\', \'Noto Sans Mono CJK JP\', '
                'monospace">포트 443</text>\n</svg>',
            ),
            directory,
        )
        cjk_css_svg = VALID_SVG.replace("fixture-title", "cjk-css-stack-title").replace(
            "fixture-desc", "cjk-css-stack-desc"
        )
        require_pass(
            "cjk-css-stack",
            '<style>text { font-family: "Geist", "Hiragino Sans", "Noto Sans JP", '
            '"Yu Gothic", sans-serif; }</style>\n' + cjk_css_svg,
            directory,
        )
        yu_gothic_ui_svg = VALID_SVG.replace(
            "fixture-title", "yu-gothic-ui-title"
        ).replace("fixture-desc", "yu-gothic-ui-desc")
        require_lint_finding(
            "yu-gothic-ui",
            '<style>text { font-family: "Yu Gothic UI", sans-serif; }</style>\n'
            + yu_gothic_ui_svg,
            "font-family: unsupported font family: Yu Gothic UI",
            directory,
        )
        kr_name_svg = VALID_SVG.replace("fixture-title", "kr-name-stack-title").replace(
            "fixture-desc", "kr-name-stack-desc"
        )
        require_pass(
            "kr-name-stack",
            kr_name_svg.replace(
                "</svg>",
                '<text font-family="\'Geist\', \'Apple SD Gothic Neo\', \'Noto Sans KR\', '
                '\'Malgun Gothic\', sans-serif">인증 서비스</text>\n</svg>',
            ),
            directory,
        )
        kr_mono_svg = VALID_SVG.replace("fixture-title", "kr-mono-stack-title").replace(
            "fixture-desc", "kr-mono-stack-desc"
        )
        require_pass(
            "kr-mono-stack",
            kr_mono_svg.replace(
                "</svg>",
                '<text font-family="\'Geist Mono\', \'Noto Sans Mono CJK KR\', '
                'monospace">포트 443</text>\n</svg>',
            ),
            directory,
        )
        kr_css_svg = VALID_SVG.replace("fixture-title", "kr-css-stack-title").replace(
            "fixture-desc", "kr-css-stack-desc"
        )
        require_pass(
            "kr-css-stack",
            '<style>text { font-family: "Geist", "Apple SD Gothic Neo", "Noto Sans KR", '
            '"Malgun Gothic", sans-serif; }</style>\n' + kr_css_svg,
            directory,
        )
        malgun_semilight_svg = VALID_SVG.replace(
            "fixture-title", "malgun-semilight-title"
        ).replace("fixture-desc", "malgun-semilight-desc")
        require_lint_finding(
            "malgun-gothic-semilight",
            '<style>text { font-family: "Malgun Gothic Semilight", sans-serif; }</style>\n'
            + malgun_semilight_svg,
            "font-family: unsupported font family: Malgun Gothic Semilight",
            directory,
        )

        spec = importlib.util.spec_from_file_location("build_icons", BUILD_ICONS)
        if spec is None or spec.loader is None:
            raise AssertionError("generated-icons: could not load build-icons.py")
        build_icons = importlib.util.module_from_spec(spec)
        previous_bytecode_setting = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(build_icons)
        finally:
            sys.dont_write_bytecode = previous_bytecode_setting
        generated_icons = {
            "tabler": build_icons.normalize_tabler("<svg><path/></svg>"),
            "simple": build_icons.normalize_simple("<svg><path/></svg>"),
            "url": build_icons.normalize_url(
                '<svg viewBox="0 0 24 24"><path/></svg>'
            ),
            "devicon": build_icons.normalize_devicon("<svg><path/></svg>"),
            "logz": build_icons.normalize_logz("<svg><path/></svg>"),
        }
        for source, icon in generated_icons.items():
            slug = f"generated-{source}-icon"
            require_pass(
                slug,
                VALID_SVG.replace("fixture-title", f"{slug}-title")
                .replace("fixture-desc", f"{slug}-desc")
                .replace("</svg>", f"  {icon}\n</svg>"),
                directory,
            )

        project = directory / "baseline-project"
        (project / "scripts").mkdir(parents=True)
        (project / "skills/diagram-design/assets").mkdir(parents=True)
        (project / "skills/diagram-design/references").mkdir(parents=True)
        shutil.copy2(LINTER, project / "scripts/lint-skin.py")
        shutil.copy2(
            ROOT / "skills/diagram-design/references/style-guide.md",
            project / "skills/diagram-design/references/style-guide.md",
        )
        project_style = project / "skills/diagram-design/references/style-guide.md"
        project_style.write_text(
            project_style.read_text(encoding="utf-8").replace(
                "| `title` | Instrument Serif |",
                "| `title` | Inter Tight |",
                1,
            ),
            encoding="utf-8",
        )
        brand_font_path = project / "style-guide-font.html"
        brand_font_path.write_text(
            VALID_SVG.replace("fixture-title", "style-guide-font-title")
            .replace("fixture-desc", "style-guide-font-desc")
            .replace("</svg>", '<text style="font-family: Inter Tight;">Brand</text></svg>'),
            encoding="utf-8",
        )
        brand_font_result = subprocess.run(
            [sys.executable, str(project / "scripts/lint-skin.py"), str(brand_font_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if brand_font_result.returncode != 0:
            raise AssertionError(
                "style-guide font: expected pass\n"
                f"{brand_font_result.stdout}{brand_font_result.stderr}"
            )
        print("OK: exact customized style-guide typography family accepted")
        (project / "scripts/lint-skin-baseline.txt").write_text(
            "example-baseline.html\n", encoding="utf-8"
        )
        (project / "skills/diagram-design/assets/example-baseline.html").write_text(
            '<svg style="color: #123456"></svg>\n', encoding="utf-8"
        )
        template_svg = VALID_SVG.replace(
            "fixture-title", "[diagram-slug]-title"
        ).replace("fixture-desc", "[diagram-slug]-desc")
        (project / "skills/diagram-design/assets/template.html").write_text(
            '<img src="https://evil.example/template.png">\n' + template_svg,
            encoding="utf-8",
        )
        baseline_result = subprocess.run(
            [
                sys.executable,
                str(project / "scripts/lint-skin.py"),
                "--all",
                "--baseline",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if baseline_result.returncode != 1:
            raise AssertionError(
                "baseline-a11y: expected exit 1, got "
                f"{baseline_result.returncode}\n"
                f"{baseline_result.stdout}{baseline_result.stderr}"
            )
        if "a11y: diagram <svg> must carry role=\"img\"" not in baseline_result.stdout:
            raise AssertionError(
                "baseline-a11y: missing expected accessibility finding\n"
                f"{baseline_result.stdout}"
            )
        if "color:" in baseline_result.stdout:
            raise AssertionError(
                "baseline-a11y: legacy visual finding was not exempted\n"
                f"{baseline_result.stdout}"
            )
        if "external-asset: external resource in <img> src is not allowed" not in baseline_result.stdout:
            raise AssertionError(
                "template-scan: --all did not lint template HTML\n"
                f"{baseline_result.stdout}"
            )
        if "unresolved placeholder" in baseline_result.stdout:
            raise AssertionError(
                "template-scan: canonical template placeholders were rejected\n"
                f"{baseline_result.stdout}"
            )
        print("OK: baseline file receives a11y checks but keeps visual exemptions")
        print("OK: --all scans templates and permits canonical slug placeholders")

    print("All accessible-SVG lint cases passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
