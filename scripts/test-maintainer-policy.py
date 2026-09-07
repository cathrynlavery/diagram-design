#!/usr/bin/env python3
"""Keep maintainer policy aligned with package manifests and CI truth."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / ".maintainer-policy.json"

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
    "python3 scripts/verify-bump.py --all",
    "python3 scripts/test-verify-bump.py",
    "python3 scripts/verify-beeswarm.py --all",
    "python3 scripts/test-verify-beeswarm.py",
    "python3 scripts/verify-skin-polarity.py --all",
    "python3 scripts/test-verify-skin-polarity.py",
    "python3 scripts/lint-render.py --self-test",
    "python3 scripts/lint-render.py --all",
}


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    manifests = {entry["path"] for entry in policy["versioning"]["manifests"]}
    commands = set(policy["gates"]["local_commands"])

    failures = []
    if manifests != EXPECTED_MANIFESTS:
        failures.append(
            "versioning.manifests must be exactly {}; found {}".format(
                sorted(EXPECTED_MANIFESTS), sorted(manifests)
            )
        )
    missing_commands = sorted(REQUIRED_COMMANDS - commands)
    if missing_commands:
        failures.append(
            "gates.local_commands omits current CI gates: {}".format(
                ", ".join(missing_commands)
            )
        )

    if failures:
        print("FAIL maintainer policy")
        for failure in failures:
            print("  - " + failure)
        return 1

    print(
        "OK maintainer policy: {} manifests, {} required current gates".format(
            len(manifests), len(REQUIRED_COMMANDS)
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
