#!/usr/bin/env python3
"""Tests for export_png.py engine fallback and error reporting (PR #59).

Contract from review: only the expected missing-executable condition may
advance the fallback; dependency, permission, browser-crash, and
configuration errors must propagate with their real message instead of
becoming a misleading "no engine installed". Runs without Playwright — the
fallback logic is exercised with fake launchers.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills/diagram-design/scripts/export_png.py"


def load_module():
    spec = importlib.util.spec_from_file_location("export_png", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeBrowser:
    pass


def missing(name):
    def launch():
        raise RuntimeError(
            f"BrowserType.launch: Executable doesn't exist at /fake/{name}"
        )
    return launch


def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name}: FAILED {detail}")
    print(f"  ok  {name}")


def main() -> int:
    mod = load_module()

    # 1. First engine missing -> falls through to the next installed one.
    browser = FakeBrowser()
    name, picked = mod.pick_engine(
        [("webkit", missing("webkit")), ("chromium", lambda: browser)]
    )
    check("falls back past missing engine", (name, picked) == ("chromium", browser))

    # 2. First engine installed -> used, later engines never touched.
    def must_not_run():
        raise AssertionError("fallback ran past an installed engine")
    name, picked = mod.pick_engine(
        [("webkit", lambda: browser), ("chromium", must_not_run)]
    )
    check("stops at first installed engine", name == "webkit")

    # 3. A real launch failure (crash/permissions/config) propagates with its
    #    own message — never reported as "no engine installed".
    boom = PermissionError("browser sandbox: operation not permitted")
    def crashing():
        raise boom
    try:
        mod.pick_engine([("webkit", crashing), ("chromium", lambda: browser)])
    except PermissionError as exc:
        check("real failure propagates unmodified", exc is boom)
    else:
        raise AssertionError("crash was swallowed by the fallback")

    # 4. Nothing installed -> SystemExit naming every engine tried + install hint.
    try:
        mod.pick_engine([("webkit", missing("webkit")), ("firefox", missing("firefox"))])
    except SystemExit as exc:
        msg = str(exc)
        check(
            "no-engine exit lists engines and hint",
            "webkit: not installed" in msg
            and "firefox: not installed" in msg
            and "playwright install" in msg,
            f"msg={msg!r}",
        )
    else:
        raise AssertionError("expected SystemExit when no engine is installed")

    # 5. The message filter is narrow: only the documented Playwright wording.
    check(
        "filter matches Playwright wording only",
        mod.is_missing_executable(RuntimeError("Executable doesn't exist at /x"))
        and not mod.is_missing_executable(RuntimeError("executable crashed"))
        and not mod.is_missing_executable(PermissionError("denied")),
    )

    print("all export-fallback tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
