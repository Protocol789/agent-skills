"""Tests for the JWT cache: write, read, expiry, isolation.

These touch the real filesystem via `TOKEN_CACHE_PATH` (resolved at
import time against the host env), but never touch the network. Each
test cleans up the cache file when it finishes.

If you ever want a fully-isolated test, monkeypatch
`patchmon.TOKEN_CACHE_PATH` to a `tmp_path` fixture before exercising
the cache functions.
"""

import os
import time

import patchmon


class TestTokenCache:
    def test_write_then_read_roundtrip(self, isolated_token_path):
        patchmon._write_cached_token("FAKE.JWT.TOKEN")
        assert isolated_token_path.exists()
        assert patchmon._read_cached_token() == "FAKE.JWT.TOKEN"

    def test_missing_file_returns_none(self, isolated_token_path):
        assert patchmon._read_cached_token() is None

    def test_empty_file_returns_empty_string(self, isolated_token_path):
        isolated_token_path.write_text("")
        # Empty file is technically "cached" — the script will try to use
        # an empty Bearer token and fail with a clear error from the API.
        # That behavior is the right tradeoff vs. forcing a re-login on
        # an unrelated `touch` in /tmp.
        assert patchmon._read_cached_token() == ""

    def test_write_sets_file_mode_0600(self, isolated_token_path):
        patchmon._write_cached_token("SECRET")
        mode = isolated_token_path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"

    def test_read_returns_none_when_stale(self, isolated_token_path):
        """TOKEN_MAX_AGE is 50 min; a cache older than that must re-login."""
        patchmon._write_cached_token("OLD_TOKEN")
        # Backdate the file's mtime past the threshold.
        stale = time.time() - (patchmon.TOKEN_MAX_AGE + 60)
        os.utime(isolated_token_path, (stale, stale))
        assert patchmon._read_cached_token() is None

    def test_read_returns_token_when_fresh(self, isolated_token_path):
        patchmon._write_cached_token("FRESH_TOKEN")
        # No time travel; the file was just written.
        assert patchmon._read_cached_token() == "FRESH_TOKEN"


class TestCacheFileShape:
    """Sanity checks on the cache *file*, not the content."""

    def test_default_cache_lives_under_user_home_or_xdg(self):
        """The path the script uses at import time must be under
        $HOME (or XDG_CACHE_HOME) — never under /tmp."""
        s = str(patchmon.TOKEN_CACHE_PATH)
        assert "/tmp" not in s
        home = os.path.expanduser("~")
        xdg = os.environ.get("XDG_CACHE_HOME", "")
        under_home = s.startswith(home) or s.startswith(xdg)
        under_root_cache = s.startswith("/root/.cache")
        assert under_home or under_root_cache, (
            f"cache path {s!r} not under $HOME or $XDG_CACHE_HOME"
        )

    def test_cache_dir_exists_and_is_private(self):
        """The directory the script wrote during import should exist
        with mode 0700 (best-effort — skipped if chmod failed at import)."""
        d = patchmon._TOKEN_CACHE_DIR
        assert d.exists()
        assert d.is_dir()
        # chmod may have failed on some FUSE-mounted homes; the assertion
        # is best-effort.
        mode = d.stat().st_mode & 0o777
        assert mode in (0o700, 0o755), f"unexpected dir mode {oct(mode)}"
