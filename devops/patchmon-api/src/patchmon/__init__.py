"""PatchMon thin async client package."""

from __future__ import annotations

from pathlib import Path

__version__ = "2.0.0-async"

from . import cache
from .cache import (
    _TOKEN_CACHE_DIR,
    TOKEN_CACHE_PATH,
    TOKEN_MAX_AGE,
    _read_cached_token,
    _write_cached_token,
)
from .cli import _die, create_parser, main
from .client import POLL_INITIAL_INTERVAL, POLL_MAX_INTERVAL, POLL_TIMEOUT
from .utils import DEFAULT_BASE, TERMINAL_STATUSES

# Backward compat: subprocess tests invoke patchmon.__file__ as the CLI entry.
_SHIM_PATH = Path(__file__).resolve().parents[2] / "scripts" / "patchmon.py"
__file__ = str(_SHIM_PATH)

__all__ = [
    "cache",
    "DEFAULT_BASE",
    "POLL_INITIAL_INTERVAL",
    "POLL_MAX_INTERVAL",
    "POLL_TIMEOUT",
    "TERMINAL_STATUSES",
    "TOKEN_CACHE_PATH",
    "TOKEN_MAX_AGE",
    "_TOKEN_CACHE_DIR",
    "_die",
    "_read_cached_token",
    "_write_cached_token",
    "__version__",
    "create_parser",
    "main",
]
