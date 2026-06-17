"""JWT token file cache with async surface (sync I/O via to_thread)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from pathlib import Path
from typing import Final

TOKEN_MAX_AGE: Final[int] = 50 * 60  # seconds

_TOKEN_CACHE_DIR = (
    Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "patchmon"
)
_TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
with contextlib.suppress(OSError):
    _TOKEN_CACHE_DIR.chmod(0o700)
TOKEN_CACHE_PATH = _TOKEN_CACHE_DIR / "token"


def _read_sync(path: Path | None = None) -> str | None:
    """Return cached JWT if it exists and is less than TOKEN_MAX_AGE old."""
    cache_path = path or TOKEN_CACHE_PATH
    if cache_path.exists():
        age = time.time() - cache_path.stat().st_mtime
        if age < TOKEN_MAX_AGE:
            return cache_path.read_text().strip()
    return None


def _write_sync(token: str, path: Path | None = None) -> None:
    """Persist JWT to cache file."""
    cache_path = path or TOKEN_CACHE_PATH
    cache_path.write_text(token)
    with contextlib.suppress(OSError):
        cache_path.chmod(0o600)


def _read_cached_token() -> str | None:
    """Synchronous read for backward compatibility with existing tests."""
    return _read_sync()


def _write_cached_token(token: str) -> None:
    """Synchronous write for backward compatibility with existing tests."""
    _write_sync(token)


async def read_cached_token(path: Path | None = None) -> str | None:
    return await asyncio.to_thread(_read_sync, path)


async def write_cached_token(path: Path | None, token: str) -> None:
    target = path or TOKEN_CACHE_PATH
    await asyncio.to_thread(_write_sync, token, target)
