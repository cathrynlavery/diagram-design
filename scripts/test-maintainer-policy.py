#!/usr/bin/env python3
"""Keep maintainer policy aligned with package manifests and CI truth.

``gates.local_commands`` in ``.maintainer-policy.json`` must list exactly the
gates that ``.github/workflows/ci.yml`` runs, so the local suite a maintainer
runs on a pull request head is the same suite CI enforces. The set of CI gates
is derived from the workflow's ``run:`` steps with these rules:

- Every ``python``/``python3`` invocation of a ``.py`` file is one gate, even
  inside ``$(...)`` or an ``if`` branch. ``python`` is spelled ``python3``
  locally.
- Shell glue is not a gate: the commands in ``SHELL_GLUE`` install or print
  tools (``playwright install``, ``python -c``, ``echo``) or
  steer control flow (``if``/``then``/``else``/``fi``, ``[``, ``git
  rev-parse``, ``exit``). The list is read off the run lines ci.yml has.
- A line starting with ``npx`` or the locked local Claude executable is one
  gate (the Claude plugin validator).
- A ``git diff ... --exit-code`` line checks what the command before it in
  the same step generated, so it joins that command with ``&&`` (the
  build-icons freshness gate). Backslash continuations are joined first.
- Matrix legs and ``if:`` guards (for example the ubuntu/3.12-only steps) do
  not matter: a step that runs on any leg is a gate.
- The version gate depends on the event. Pull requests run
  ``verify-plugin-package.py --require-no-bump <base>`` against a base that
  only exists in CI (``"$BASE_REF"`` or ``HEAD^1``). Locally the policy runs
  ``--require-no-bump origin/main``, which performs the current-tree checks
  plus the base comparison; the two are the same gate. Pushes run
  ``--current-only``, which skips the base comparison, so it is allowed in CI
  as the push leg but mirrors nothing: CI must still run a pull-request
  ``--require-no-bump`` for the policy entry to count.
- Every other command fails this test until the rules above say how it maps
  to a local command. Each command in a line (split on ``&&``, ``||``, and
  ``;``) counts, including an ``if`` condition; a pipeline is judged by its
  first command.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / ".maintainer-policy.json"
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"

EXPECTED_MANIFESTS = {
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".factory-plugin/plugin.json",
}

REQUIRED_COMMANDS = {
    "python3 scripts/test-maintainer-policy.py",
    "python3 scripts/test-verify-semantic-motion.py",
    "python3 scripts/test-verify-sequence-oauth.py",
    "python3 scripts/test-verify-doctor.py",
    "python3 scripts/test-verify-polar.py",
    "python3 scripts/verify-polar.py",
    "python3 scripts/verify-sankey.py --all",
    "python3 scripts/test-verify-sankey.py",
    "python3 scripts/verify-streamgraph.py --all",
    "python3 scripts/test-verify-streamgraph.py",
    "python3 scripts/verify-bump.py --all",
    "python3 scripts/test-verify-bump.py",
    "python3 scripts/verify-marimekko.py --all",
    "python3 scripts/test-verify-marimekko.py",
    "python3 scripts/verify-beeswarm.py --all",
    "python3 scripts/test-verify-beeswarm.py",
    "python3 scripts/verify-skin-polarity.py --all",
    "python3 scripts/test-verify-skin-polarity.py",
    "python3 scripts/verify-architecture-delta.py --all",
    "python3 scripts/test-verify-architecture-delta.py",
    "python3 scripts/build-exploded-examples.py --check",
    "python3 scripts/verify-exploded.py --all",
    "python3 scripts/test-verify-exploded.py",
    "python3 scripts/build-axonometric-plan-examples.py --check",
    "python3 scripts/verify-axonometric-plan.py --all",
    "python3 scripts/test-verify-axonometric-plan.py",
    "python3 scripts/lint-render.py --self-test",
    "python3 scripts/lint-render.py --all",
}

VERSION_GATE = "python3 scripts/verify-plugin-package.py --require-no-bump <base-ref>"
LOCAL_VERSION_GATE = "python3 scripts/verify-plugin-package.py --require-no-bump origin/main"
CI_VERSION_GATES = {
    'python3 scripts/verify-plugin-package.py --require-no-bump "$BASE_REF"',
    "python3 scripts/verify-plugin-package.py --require-no-bump HEAD^1",
}
# The push leg of the CI version step: current-tree checks only, no base
# comparison, so it stands in for nothing the policy runs.
PUSH_ONLY_VERSION_CHECK = "python3 scripts/verify-plugin-package.py --current-only"

# Commands in ci.yml run steps that install or print tools or steer control
# flow, matched on their leading words (``python3`` read as ``python``).
# Anything not listed here, not a python gate, and not an npx gate fails closed.
SHELL_GLUE = (
    ("echo",),
    ("exit",),
    ("then",),
    ("else",),
    ("fi",),
    ("case",),
    ("esac",),
    ("[",),
    ("git", "rev-parse"),
    ("npm", "ci"),
    ("pip", "install"),
    ("python", "-m", "pip", "install"),
    ("playwright", "install"),
    ("python", "-m", "playwright", "install"),
    ("python", "-c"),
)
CONDITION = re.compile(r"^(?:if|elif)(?:\s+!)?(?:\s+(?P<condition>.*))?$")
# A `case` arm such as `SKIP:*) echo "skipped" && exit 1`: the pattern is glue,
# and the command after it is judged on its own.
CASE_ARM = re.compile(r"^[^\s()]+\)(?:\s+(?P<command>.*))?$")
# What is left of ``out="$(python scripts/x.py)"`` once the gate is taken out.
EMPTIED_ASSIGNMENT = re.compile(r"""^[A-Za-z_]\w*=(["']?)\$\(\s*\)\1$""")

RUN_KEY = re.compile(r"^(?P<prefix>\s*(?:-\s+)?)run:\s*(?P<value>.*?)\s*$")
PYTHON_SCRIPT = re.compile(
    r"(?<![\w./-])python3?\s+(?P<script>[\w./-]+\.py)(?P<args>(?:[ \t]+[^\s;&|()<>]+)*)"
)
UV_RUN = re.compile(r"\buv run --locked --project \.github/ci/python\s+")


def normalize(command: str) -> str:
    """Canonical form of a policy entry: CI spelling, version gate collapsed."""
    command = " ".join(command.split())
    command = re.sub(r"^npm ci --prefix \.github/ci/node && ", "", command)
    command = re.sub(r"^python(?=\s)", "python3", command)
    return VERSION_GATE if command == LOCAL_VERSION_GATE else command


def ci_gate(command: str) -> str | None:
    """Canonical form of a CI command, or None when it mirrors no local gate."""
    command = " ".join(command.split())
    command = re.sub(r"^python(?=\s)", "python3", command)
    if command in CI_VERSION_GATES:
        return VERSION_GATE
    if command == PUSH_ONLY_VERSION_CHECK:
        return None
    return command


def split_commands(line: str) -> list[str]:
    """Split a shell line on unquoted ``&&``, ``||``, and ``;``."""
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if char == "\\" and quote == '"' and index + 1 < len(line):
                current.append(line[index : index + 2])
                index += 2
                continue
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
        elif line.startswith(("&&", "||"), index) or char == ";":
            parts.append("".join(current))
            current = []
            index += 2 if char in "&|" else 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def is_glue(command: str) -> bool:
    """Whether one command, gates already removed, is shell glue."""
    condition = CONDITION.match(command)
    if condition:
        return not condition.group("condition") or is_glue(condition.group("condition"))
    if EMPTIED_ASSIGNMENT.match(command):
        return True
    arm = CASE_ARM.match(command)
    if arm:
        return not arm.group("command") or is_glue(arm.group("command"))
    words = command.split()
    if words and words[0] == "python3":
        words[0] = "python"
    return any(tuple(words[: len(glue)]) == glue for glue in SHELL_GLUE)


def run_blocks(workflow: str) -> list[list[str]]:
    """Return the shell lines of every ``run:`` step, without YAML parsing."""
    lines = workflow.splitlines()
    blocks: list[list[str]] = []
    index = 0
    while index < len(lines):
        match = RUN_KEY.match(lines[index])
        index += 1
        if match is None:
            continue
        value = match.group("value")
        if not value.startswith(("|", ">")):
            blocks.append([value])
            continue
        key_column = len(match.group("prefix"))
        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= key_column:
                break
            body.append(line)
            index += 1
        if value.startswith(">"):
            body = [" ".join(line.strip() for line in body if line.strip())]
        blocks.append(body)
    return blocks


def logical_lines(block: list[str]) -> list[str]:
    """Join backslash continuations and drop blank and comment lines."""
    joined: list[str] = []
    pending = ""
    for raw in block:
        line = raw.strip()
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        line = (pending + line).strip()
        pending = ""
        if line and not line.startswith("#"):
            joined.append(line)
    if pending.strip():
        joined.append(pending.strip())
    return joined


def ci_gates(workflow: str) -> tuple[set[str], list[str]]:
    """Return (normalized CI gate commands, CI lines this test cannot map)."""
    gates: set[str] = set()
    unmapped: list[str] = []
    for block in run_blocks(workflow):
        commands: list[str] = []
        for line in logical_lines(block):
            line = UV_RUN.sub("", line)
            if line.startswith("git diff") and "--exit-code" in line:
                if commands:
                    commands[-1] = f"{commands[-1]} && {line}"
                else:
                    commands.append(line)
                continue
            if line.startswith(("npx ", ".github/ci/node/node_modules/.bin/claude ")):
                commands.append(line)
                continue
            commands.extend(match.group(0) for match in PYTHON_SCRIPT.finditer(line))
            rest = PYTHON_SCRIPT.sub("", line)
            if "scripts/" in rest or not all(map(is_glue, split_commands(rest))):
                unmapped.append(line)
        gates.update(gate for gate in map(ci_gate, commands) if gate is not None)
    return gates, unmapped


def policy_failures(policy: dict, workflow: str) -> list[str]:
    manifests = {entry["path"] for entry in policy["versioning"]["manifests"]}
    commands = set(policy["gates"]["local_commands"])

    failures = []
    if manifests != EXPECTED_MANIFESTS:
        failures.append(
            f"versioning.manifests must be exactly {sorted(EXPECTED_MANIFESTS)}; found {sorted(manifests)}"
        )
    missing_commands = sorted(REQUIRED_COMMANDS - commands)
    if missing_commands:
        failures.append(
            "gates.local_commands omits current CI gates: {}".format(
                ", ".join(missing_commands)
            )
        )

    gates, unmapped = ci_gates(workflow)
    local = {normalize(command) for command in commands}
    for line in unmapped:
        failures.append(
            "ci.yml runs a command this test cannot map to a local gate "
            f"(extend scripts/test-maintainer-policy.py): {line}"
        )
    unregistered = sorted(gates - local)
    if unregistered:
        failures.append(
            "gates.local_commands omits gates that ci.yml runs: {}".format(
                ", ".join(unregistered)
            )
        )
    stale = sorted(local - gates)
    if stale:
        failures.append(
            "gates.local_commands lists commands that ci.yml does not run: {}".format(
                ", ".join(stale)
            )
        )
    return failures


SYNTHETIC_POLICY_COMMANDS = [
    "python3 scripts/test-maintainer-policy.py",
    "python3 scripts/verify-plugin-package.py --require-no-bump origin/main",
    "npx --yes @anthropic-ai/claude-code@2.1.229 plugin validate . --strict",
    "python3 scripts/test-lint-a11y.py",
    "python3 scripts/lint-skin.py --all --baseline",
    "python3 scripts/test-verify-polar.py",
    "python3 scripts/verify-polar.py",
    "python3 scripts/test-build-readme-thumbs.py",
    "python3 scripts/build-readme-thumbs.py --check",
    "python3 scripts/lint-render.py --self-test",
    "python3 scripts/lint-render.py --all",
    ("python3 scripts/build-icons.py && git diff --ignore-space-at-eol --exit-code -- "
    "skills/diagram-design/assets/icons.html "
    "skills/diagram-design/references/primitive-icons.md"),
]

SYNTHETIC_CI = """\
jobs:
  plugin-package:
    steps:
      - name: Verify maintainer policy tracks package and CI truth
        run: python3 scripts/test-maintainer-policy.py

      - name: Forbid manifest version changes in pull requests
        env:
          BASE_REF: ${{ github.event.pull_request.base.sha || '' }}
        shell: bash
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            python3 scripts/verify-plugin-package.py --require-no-bump "$BASE_REF"
          else
            python3 scripts/verify-plugin-package.py --current-only
          fi

      - name: Validate Claude marketplace package without warnings
        run: npx --yes @anthropic-ai/claude-code@2.1.229 plugin validate . --strict

  validate:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - name: Verify accessible SVG contract
        if: always()
        run: python scripts/test-lint-a11y.py

      - name: Run skin linter
        run: python scripts/lint-skin.py --all --baseline

      - name: Verify quantitative polar chart
        shell: bash
        run: |
          python scripts/test-verify-polar.py
          python scripts/verify-polar.py

      - name: Install Pillow for README thumbnail verification
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        run: |
          pip install "Pillow==${PILLOW_VERSION}"
          python -c "import PIL; print('Pillow', PIL.__version__)"

      - name: Verify README thumbnails
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        run: |
          python scripts/test-build-readme-thumbs.py
          python scripts/build-readme-thumbs.py --check

      - name: Install Playwright Chromium
        run: |
          pip install "playwright==${PLAYWRIGHT_VERSION}"
          playwright install --with-deps chromium

      - name: Verify render linter checks
        run: python scripts/lint-render.py --self-test

      - name: Run render linter
        run: python scripts/lint-render.py --all

      - name: Verify generated icon assets
        shell: bash
        run: |
          python scripts/build-icons.py
          git diff --ignore-space-at-eol --exit-code -- \\
            skills/diagram-design/assets/icons.html \\
            skills/diagram-design/references/primitive-icons.md

      - name: Generate CI execution summary table
        run: |
          echo "| Verification Gate | Outcome |" >> $GITHUB_STEP_SUMMARY
"""

MERGE_PARENT_VERSION_GATE = """\
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            if ! git rev-parse -q --verify HEAD^2 >/dev/null; then
              echo "expected the pull request merge commit at HEAD" >&2
              exit 1
            fi
            python3 scripts/verify-plugin-package.py --require-no-bump HEAD^1
          else
            python3 scripts/verify-plugin-package.py --current-only
          fi
"""

EXTRA_GATE_STEP = """
      - name: Verify standalone SVG export
        if: always()
        run: python scripts/test-export-svg-standalone.py
"""

SUBSTITUTED_GATE_STEP = """
      - name: Verify export snippet stalled-load fallback
        if: always() && matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'
        shell: bash
        run: |
          out="$(python scripts/test-export-wait.py)"
          echo "$out" | grep -q "All export-wait cases passed"
"""

CASE_GUARDED_STEP = """
      - name: Verify export snippet stalled-load fallback
        shell: bash
        run: |
          out="$(python scripts/test-export-wait.py)"
          echo "$out"
          case "$out" in
            SKIP:*) echo "::error::export-wait tests skipped" && exit 1 ;;
          esac
          echo "$out" | grep -q "All export-wait cases passed"
"""

UV_PREFIXED_STEP = """
      - name: Verify browser-backed export
        run: |
          uv run --locked --project .github/ci/python playwright install --with-deps chromium
          uv run --locked --project .github/ci/python python scripts/test-export-svg-standalone.py
"""

LOCKED_CLAUDE_STEP = """
      - name: Validate Claude marketplace package with locked executable
        run: .github/ci/node/node_modules/.bin/claude plugin validate . --strict
"""

UNMAPPED_STEP = """
      - name: Verify something with a shell script
        run: bash scripts/check-something.sh
"""

PUSH_ONLY_VERSION_STEP = """\
        run: |
          if [ "${{ github.event_name }}" = "pull_request" ]; then
            echo "pull requests skip the version gate"
          else
            python3 scripts/verify-plugin-package.py --current-only
          fi
"""

UNKNOWN_COMMAND_STEPS = {
    "npm run lint": """
      - name: Lint with npm
        run: npm run lint
""",
    "node tools/check.js": """
      - name: Check with node
        run: node tools/check.js
""",
    "python scripts/test-lint-a11y.py && make lint": """
      - name: Gate chained with an unknown command
        run: python scripts/test-lint-a11y.py && make lint
""",
    "if npm test; then": """
      - name: Unknown command as an if condition
        shell: bash
        run: |
          if npm test; then
            echo "tests passed"
          fi
""",
}


def synthetic_policy(commands: list[str]) -> dict:
    return {
        "versioning": {"manifests": [{"path": path} for path in sorted(EXPECTED_MANIFESTS)]},
        "gates": {"local_commands": list(REQUIRED_COMMANDS | set(commands))},
    }


def synthetic_ci(extra: str = "") -> str:
    """The synthetic workflow, plus a step running every REQUIRED_COMMANDS gate."""
    required = "".join(
        f"\n      - name: Required gate\n        run: {command}\n"
        for command in sorted(REQUIRED_COMMANDS)
    )
    return SYNTHETIC_CI + required + extra


def self_test() -> list[str]:
    """Check the CI-to-policy mapping rules on synthetic workflows."""
    problems: list[str] = []
    old_version_step = SYNTHETIC_CI[
        SYNTHETIC_CI.index("        run: |\n          if [") : SYNTHETIC_CI.index(
            "      - name: Validate Claude"
        )
    ]
    if old_version_step.count("--require-no-bump") != 1:
        return ["self-test fixture drifted: version gate step not found"]
    icons_command = SYNTHETIC_POLICY_COMMANDS[-1]
    cases: list[tuple[str, str, list[str], str | None]] = [
        ("matching workflow and policy", synthetic_ci(), SYNTHETIC_POLICY_COMMANDS, None),
        (
            "HEAD^1 version gate",
            synthetic_ci().replace(old_version_step, MERGE_PARENT_VERSION_GATE + "\n"),
            SYNTHETIC_POLICY_COMMANDS,
            None,
        ),
        (
            "CI gate missing from policy",
            synthetic_ci(EXTRA_GATE_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            ("gates.local_commands omits gates that ci.yml runs: "
            "python3 scripts/test-export-svg-standalone.py"),
        ),
        (
            "CI gate inside command substitution missing from policy",
            synthetic_ci(SUBSTITUTED_GATE_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            ("gates.local_commands omits gates that ci.yml runs: "
            "python3 scripts/test-export-wait.py"),
        ),
        (
            "policy command CI does not run",
            synthetic_ci(),
            SYNTHETIC_POLICY_COMMANDS + ["python3 scripts/test-retired.py"],
            ("gates.local_commands lists commands that ci.yml does not run: "
            "python3 scripts/test-retired.py"),
        ),
        (
            "policy drops the version gate",
            synthetic_ci(),
            [c for c in SYNTHETIC_POLICY_COMMANDS if "verify-plugin-package" not in c],
            "gates.local_commands omits gates that ci.yml runs: " + VERSION_GATE,
        ),
        (
            "icons diff flags drift from CI",
            synthetic_ci(),
            [c for c in SYNTHETIC_POLICY_COMMANDS if c != icons_command]
            + [icons_command.replace("--ignore-space-at-eol ", "")],
            ("gates.local_commands lists commands that ci.yml does not run: "
            "python3 scripts/build-icons.py && git diff --exit-code"),
        ),
        (
            "unmapped CI command",
            synthetic_ci(UNMAPPED_STEP),
            SYNTHETIC_POLICY_COMMANDS,
            ("cannot map to a local gate (extend scripts/test-maintainer-policy.py): "
            "bash scripts/check-something.sh"),
        ),
        (
            "CI gate inside command substitution registered",
            synthetic_ci(SUBSTITUTED_GATE_STEP),
            SYNTHETIC_POLICY_COMMANDS + ["python3 scripts/test-export-wait.py"],
            None,
        ),
        (
            "CI gate behind a case guard registered",
            synthetic_ci(CASE_GUARDED_STEP),
            SYNTHETIC_POLICY_COMMANDS + ["python3 scripts/test-export-wait.py"],
            None,
        ),
        (
            "uv-prefixed gate registered",
            synthetic_ci(UV_PREFIXED_STEP),
            SYNTHETIC_POLICY_COMMANDS
            + ["python3 scripts/test-export-svg-standalone.py"],
            None,
        ),
        (
            "locked Claude executable registered",
            synthetic_ci(LOCKED_CLAUDE_STEP),
            SYNTHETIC_POLICY_COMMANDS
            + [
                ("npm ci --prefix .github/ci/node && "
                ".github/ci/node/node_modules/.bin/claude plugin validate . --strict")
            ],
            None,
        ),
        (
            "pull requests stop running the version gate",
            synthetic_ci().replace(old_version_step, PUSH_ONLY_VERSION_STEP + "\n"),
            SYNTHETIC_POLICY_COMMANDS,
            "gates.local_commands lists commands that ci.yml does not run: " + VERSION_GATE,
        ),
    ]
    cases.extend(
        (
            f"unknown CI command fails closed: {line}",
            synthetic_ci(step),
            SYNTHETIC_POLICY_COMMANDS,
            "cannot map to a local gate (extend scripts/test-maintainer-policy.py): " + line,
        )
        for line, step in UNKNOWN_COMMAND_STEPS.items()
    )
    for name, workflow, commands, expected in cases:
        failures = policy_failures(synthetic_policy(commands), workflow)
        if expected is None and failures:
            problems.append(f"self-test '{name}': expected no failures, got {failures}")
        elif expected is not None and not any(expected in failure for failure in failures):
            problems.append(f"self-test '{name}': expected {expected!r}, got {failures}")
    return problems


def main() -> int:
    problems = self_test()
    if problems:
        print("FAIL maintainer policy self-test")
        for problem in problems:
            print("  - " + problem)
        return 1

    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    failures = policy_failures(policy, workflow)
    if failures:
        print("FAIL maintainer policy")
        for failure in failures:
            print("  - " + failure)
        return 1

    gates, _unmapped = ci_gates(workflow)
    print(
        f"OK maintainer policy: {len(EXPECTED_MANIFESTS)} manifests, {len(REQUIRED_COMMANDS)} required current gates, "
        f"{len(gates)} CI gates registered in local_commands"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
