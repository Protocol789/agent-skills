"""pytest setup for the patchmon-api skill."""

import sys
from pathlib import Path

import pytest

pytest_plugins = ("pytest_asyncio",)

SKILL_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = SKILL_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SHIM_PATH = SKILL_ROOT / "scripts" / "patchmon.py"


@pytest.fixture
def skill_root() -> Path:
    return SKILL_ROOT


@pytest.fixture
def shim_path() -> Path:
    return SHIM_PATH


@pytest.fixture
def isolated_token_path(tmp_path, monkeypatch):
    """Redirect TOKEN_CACHE_PATH to a tmp dir for the duration of one test."""
    import patchmon

    p = tmp_path / "token"
    monkeypatch.setattr(patchmon, "TOKEN_CACHE_PATH", p)
    monkeypatch.setattr(patchmon.cache, "TOKEN_CACHE_PATH", p)
    return p


@pytest.fixture
def sample_host_with_stats() -> dict:
    return {
        "host_id": "host-1",
        "name": "web-01",
        "stats": {"pending_updates": 3, "needs_reboot": True},
    }


@pytest.fixture
def sample_run():
    def _factory(status: str, run_id: str = "run-abc") -> dict:
        return {"patch_run_id": run_id, "status": status}

    return _factory


@pytest.fixture
def patchmon_env() -> dict[str, str]:
    return {
        "PATCHMON_URL": "https://patchmon.test",
        "PATCHMON_USERNAME": "user",
        "PATCHMON_PASSWORD": "pass",
        "PATCHMON_KEY": "key",
        "PATCHMON_SECRET": "secret",
    }
