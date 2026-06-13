"""Smoke + contract tests for the patchmon-api CLI.

These are intentionally minimal — they lock in the cheap-to-lose
properties of the script so future refactors can't quietly break
them:

- The CLI parses, lists every expected subcommand, and exits 0.
- The hygiene defaults (base URL, token cache path) haven't drifted
  back to the leakier values they had at import time.
- `_die` honors the LLM-facing contract: exits non-zero, prints a
  JSON `{"error": ...}` to stderr, prints nothing to stdout.

Network-touching code paths are deliberately not tested here. Add
them in a separate `test_api.py` with mocked transport (see TODO).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import patchmon


# ---------- paths / hygiene constants ----------

class TestHygieneConstants:
    """Lock in the defaults we set during the PII / hygiene pass."""

    def test_default_base_is_neutral_domain(self):
        assert patchmon.DEFAULT_BASE == "https://patchmon.net"

    def test_token_cache_not_in_tmp(self):
        """JWT must not be written to a world-readable shared path."""
        assert "/tmp" not in str(patchmon.TOKEN_CACHE_PATH)

    def test_token_cache_under_user_xdg(self):
        # Resolved against the user's actual env, no network needed.
        expected = (
            Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
            / "patchmon"
            / "token"
        )
        assert patchmon.TOKEN_CACHE_PATH == expected

    def test_terminal_statuses_are_a_frozenset_or_set(self):
        # The skill checks `status in TERMINAL_STATUSES`; the value must
        # behashable for fast containment and JSON-serializable for the
        # error path.
        assert isinstance(patchmon.TERMINAL_STATUSES, (set, frozenset))
        for status in ("completed", "failed", "cancelled", "validated"):
            assert status in patchmon.TERMINAL_STATUSES

    def test_poll_timeout_is_generous(self):
        """A patch_all run on a busy host can take >5 min; the cap
        should be at least 15 minutes (the script uses 30)."""
        assert patchmon.POLL_TIMEOUT >= 15 * 60


# ---------- CLI smoke ----------

EXPECTED_SUBCOMMANDS = {
    "login", "hosts", "outdated", "patch", "approve",
    "run", "runs", "stop",
}


class TestCli:
    """The CLI is what the LLM actually invokes; keep it honest."""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(Path(patchmon.__file__).resolve()), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "usage" in result.stdout.lower()

    def test_all_subcommands_listed_in_help(self):
        result = subprocess.run(
            [sys.executable, str(Path(patchmon.__file__).resolve()), "--help"],
            capture_output=True, text=True, timeout=10,
        )
        for sub in EXPECTED_SUBCOMMANDS:
            assert sub in result.stdout, f"subcommand {sub!r} missing from --help"

    def test_module_invocation_runs(self):
        """`python3 scripts/patchmon.py --help` should not crash even if
        the user forgot to set PATCHMON_* env vars."""
        env = {**os.environ}
        for k in ("PATCHMON_URL", "PATCHMON_USERNAME", "PATCHMON_PASSWORD",
                  "PATCHMON_KEY", "PATCHMON_SECRET", "PATCHMON_TOKEN"):
            env.pop(k, None)
        result = subprocess.run(
            [sys.executable, str(Path(patchmon.__file__).resolve()), "--help"],
            capture_output=True, text=True, env=env, timeout=10,
        )
        assert result.returncode == 0


# ---------- LLM-facing error contract ----------

class TestDieContract:
    """`_die` is the function the agent sees when things go wrong.
    The shape of its output is part of the public contract."""

    def test_die_prints_json_to_stderr(self, capsys):
        with pytest.raises(SystemExit) as exc:
            patchmon._die("something broke")
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload == {"error": "something broke"}

    def test_die_escapes_quotes_safely(self, capsys):
        with pytest.raises(SystemExit):
            patchmon._die('has "quotes" and a \nnewline')
        payload = json.loads(capsys.readouterr().err)
        # The error string must round-trip through JSON, not break it.
        assert "quotes" in payload["error"]
        assert "newline" in payload["error"]


# ---------- TODO markers ----------

@pytest.mark.skip(reason="placeholder; fill in when network tests are added")
def test_request_rejects_html_response_with_200():
    """`_request` should `_die` when a 200 response body starts with `<`
    (the SPA-HTML guard at L66-67 of patchmon.py)."""
    raise NotImplementedError
