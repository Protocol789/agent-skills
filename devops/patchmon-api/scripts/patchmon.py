#!/usr/bin/env python3
"""patchmon.py — thin launcher for the async PatchMon client.

Designed to be called by an LLM via Hermes skills. Delegates to
``patchmon.cli.main`` after making the local ``src/`` package importable.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from patchmon.cli import main

if __name__ == "__main__":
    main()
