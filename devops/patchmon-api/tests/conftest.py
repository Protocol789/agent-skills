"""pytest setup for the patchmon-api skill.

Adds the `scripts/` directory to sys.path so tests can do
`import patchmon` without packaging. No fixtures here yet — add them
as the test suite grows.
"""
import sys
from pathlib import Path

# Resolve the skill root: <skill>/tests/conftest.py -> <skill>/
SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
