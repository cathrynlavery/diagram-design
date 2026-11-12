#!/usr/bin/env python3
"""Repository entry point for skills/diagram-design/scripts/verify_geometry.py.

The checker ships inside the skill so installed agents can run it; this path
keeps CI and contributor commands unchanged.
"""

import runpy
from pathlib import Path

PACKAGED = (
    Path(__file__).resolve().parent.parent
    / "skills/diagram-design/scripts/verify_geometry.py"
)

if __name__ == "__main__":
    runpy.run_path(str(PACKAGED), run_name="__main__")
