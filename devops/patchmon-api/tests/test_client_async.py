"""Async client, auth strategy, and polling tests."""

from __future__ import annotations

import os
from typing import Any

import httpx
import pytest
import respx

from patchmon.auth import BasicAuthStrategy, BearerAuthStrategy, create_bearer_auth
from patchmon.cache import TOKEN_MAX_AGE
from patchmon.client import AsyncPatchmonClient
from patchmon.exceptions import AuthError, PollTimeout
from patchmon.models import PollConfig
from patchmon.utils import _extract_field, _filter_hosts

BASE = "https://patchmon.test"


def _client(
    auth: Any,
    *,
    poll_config: PollConfig | None = None,
) -> AsyncPatchmonClient:
    http = httpx.AsyncClient(base_url=BASE, timeout=30.0, follow_redirects=False)
    return AsyncPatchmonClient(
        http_client=http,
        auth=auth,
        base_url=BASE,
        poll_config=poll_config,
    )


@pytest.mark.asyncio
@respx.mock
async def test_login_returns_token_and_writes_cache(isolated_token_path):
    route = respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"token": "JWT.HERE"})
    )
    strategy = BearerAuthStrategy(
        username="user", password="pass", cache_path=isolated_token_path
    )
    http = httpx.AsyncClient(base_url=BASE, timeout=30.0)
    try:
        headers = await strategy.prepare(client=http, base_url=BASE)
        assert headers == {"Authorization": "Bearer JWT.HERE"}
        assert route.called
        assert isolated_token_path.read_text().strip() == "JWT.HERE"
    finally:
        await http.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_hosts_prefers_basic_auth_when_key_secret_present():
    route = respx.get(f"{BASE}/api/v1/api/hosts?include=stats").mock(
        return_value=httpx.Response(200, json=[{"host_id": "h1"}])
    )
    os.environ["PATCHMON_KEY"] = "mykey"
    os.environ["PATCHMON_SECRET"] = "mysecret"
    client = _client(create_bearer_auth())
    try:
        data = await client.list_hosts(use_basic=True)
        assert data == [{"host_id": "h1"}]
        req = route.calls[0].request
        assert "/api/v1/api/hosts" in str(req.url)
        auth = req.headers.get("Authorization", "")
        assert auth.startswith("Basic ")
    finally:
        await client.aclose()
        os.environ.pop("PATCHMON_KEY", None)
        os.environ.pop("PATCHMON_SECRET", None)


@pytest.mark.asyncio
@respx.mock
async def test_hosts_falls_back_to_bearer():
    route = respx.get(f"{BASE}/api/v1/dashboard/hosts").mock(
        return_value=httpx.Response(200, json=[{"host_id": "h2"}])
    )
    client = _client(create_bearer_auth(token="BEARER.TOKEN"))
    try:
        data = await client.list_hosts(use_basic=False)
        assert data == [{"host_id": "h2"}]
        req = route.calls[0].request
        assert req.headers["Authorization"] == "Bearer BEARER.TOKEN"
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_outdated_calls_updates_only_true():
    route = respx.get(
        f"{BASE}/api/v1/api/hosts/host-99/packages?updates_only=true"
    ).mock(return_value=httpx.Response(200, json={"packages": []}))
    os.environ["PATCHMON_KEY"] = "k"
    os.environ["PATCHMON_SECRET"] = "s"
    client = _client(create_bearer_auth())
    try:
        await client.list_outdated_packages("host-99")
        assert "updates_only=true" in str(route.calls[0].request.url)
    finally:
        await client.aclose()
        os.environ.pop("PATCHMON_KEY", None)
        os.environ.pop("PATCHMON_SECRET", None)


@pytest.mark.asyncio
async def test_patch_dry_run_rejects_patch_all():
    import argparse

    from patchmon.cli import cmd_patch

    args = argparse.Namespace(
        host_id="h1",
        packages=None,
        dry_run=True,
        no_wait=True,
        field=None,
        base_url=BASE,
        token="t",
        username=None,
        password=None,
    )
    with pytest.raises(SystemExit):
        await cmd_patch(args)


@pytest.mark.asyncio
@respx.mock
async def test_patch_queues_then_polls_to_completed(capsys):
    respx.post(f"{BASE}/api/v1/patching/trigger").mock(
        return_value=httpx.Response(200, json={"patch_run_id": "run-1"})
    )
    respx.get(f"{BASE}/api/v1/patching/runs/run-1").mock(
        side_effect=[
            httpx.Response(200, json={"status": "queued", "patch_run_id": "run-1"}),
            httpx.Response(200, json={"status": "running", "patch_run_id": "run-1"}),
            httpx.Response(200, json={"status": "completed", "patch_run_id": "run-1"}),
        ]
    )
    client = _client(
        create_bearer_auth(token="tok"),
        poll_config=PollConfig(initial_interval=0.01, max_interval=0.02, timeout=30),
    )
    try:
        res = await client.trigger_patch(
            host_id="h1", patch_type="patch_all", dry_run=False
        )
        assert res["patch_run_id"] == "run-1"
        final = await client.poll_until_terminal("run-1")
        assert final["status"] == "completed"
        err = capsys.readouterr().err
        compact = err.replace(" ", "")
        assert '"status": "queued"' in err or '"status":"queued"' in compact
        assert "completed" in err
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_poll_times_out_raises_and_dies():
    respx.get(f"{BASE}/api/v1/patching/runs/stuck").mock(
        return_value=httpx.Response(200, json={"status": "running"})
    )
    client = _client(
        create_bearer_auth(token="tok"),
        poll_config=PollConfig(initial_interval=0.01, max_interval=0.01, timeout=0.05),
    )
    try:
        with pytest.raises(PollTimeout, match="Polling timed out"):
            await client.poll_until_terminal("stuck")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_poll_detects_html_response_and_dies():
    respx.get(f"{BASE}/api/v1/patching/runs/html-run").mock(
        return_value=httpx.Response(200, text="<html><body>SPA</body></html>")
    )
    client = _client(create_bearer_auth(token="tok"))
    try:
        with pytest.raises(Exception, match="HTML"):
            await client.poll_until_terminal("html-run")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_approve_returns_new_run_id_and_polls(capsys):
    respx.post(f"{BASE}/api/v1/patching/runs/old/approve").mock(
        return_value=httpx.Response(
            200, json={"patch_run_id": "new-run", "new_run_id": "new-run"}
        )
    )
    respx.get(f"{BASE}/api/v1/patching/runs/new-run").mock(
        side_effect=[
            httpx.Response(200, json={"status": "running", "patch_run_id": "new-run"}),
            httpx.Response(
                200, json={"status": "completed", "patch_run_id": "new-run"}
            ),
        ]
    )
    client = _client(
        create_bearer_auth(token="tok"),
        poll_config=PollConfig(initial_interval=0.01, max_interval=0.02, timeout=30),
    )
    try:
        res = await client.approve_run(run_id="old", approved_by="tester")
        assert res["patch_run_id"] == "new-run"
        final = await client.poll_until_terminal("new-run")
        assert final["status"] == "completed"
    finally:
        await client.aclose()


def test_field_extraction_unchanged():
    data = {"hosts": [{"host_id": "abc", "name": "web"}]}
    assert _extract_field(data, "hosts.0.host_id") == "abc"
    assert _extract_field(data, "hosts.0.missing") is None
    assert _extract_field(data, "missing.path") is None


@pytest.mark.asyncio
async def test_bearer_strategy_uses_fresh_cache(isolated_token_path):
    isolated_token_path.write_text("CACHED.JWT")
    strategy = BearerAuthStrategy(cache_path=isolated_token_path)
    http = httpx.AsyncClient()
    try:
        headers = await strategy.prepare(client=http, base_url=BASE)
        assert headers == {"Authorization": "Bearer CACHED.JWT"}
    finally:
        await http.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_bearer_strategy_re_logs_in_when_cache_stale(
    isolated_token_path, monkeypatch
):
    import time

    isolated_token_path.write_text("OLD.JWT")
    stale = time.time() - (TOKEN_MAX_AGE + 60)
    os.utime(isolated_token_path, (stale, stale))
    respx.post(f"{BASE}/api/v1/auth/login").mock(
        return_value=httpx.Response(200, json={"token": "NEW.JWT"})
    )
    strategy = BearerAuthStrategy(
        username="u", password="p", cache_path=isolated_token_path
    )
    http = httpx.AsyncClient(base_url=BASE)
    try:
        headers = await strategy.prepare(client=http, base_url=BASE)
        assert headers == {"Authorization": "Bearer NEW.JWT"}
        assert isolated_token_path.read_text().strip() == "NEW.JWT"
    finally:
        await http.aclose()


@pytest.mark.asyncio
async def test_basic_strategy_raises_auth_error_on_missing_env(monkeypatch):
    monkeypatch.delenv("PATCHMON_KEY", raising=False)
    monkeypatch.delenv("PATCHMON_SECRET", raising=False)
    strategy = BasicAuthStrategy()
    http = httpx.AsyncClient()
    try:
        with pytest.raises(AuthError, match="Integration API credentials"):
            await strategy.prepare(client=http, base_url=BASE)
    finally:
        await http.aclose()


def test_filter_hosts_mixed_pending_and_needs_reboot(sample_host_with_stats):
    hosts = [
        sample_host_with_stats,
        {
            "host_id": "host-2",
            "stats": {"pending_updates": 0, "needs_reboot": False},
        },
        {
            "host_id": "host-3",
            "stats": {"pending_updates": 1, "needs_reboot": False},
        },
    ]
    filtered = _filter_hosts(hosts, pending=True, needs_reboot=True)
    assert len(filtered) == 1
    assert filtered[0]["host_id"] == "host-1"


@pytest.mark.asyncio
@respx.mock
async def test_request_rejects_html_response_with_200():
    respx.get(f"{BASE}/api/v1/dashboard/hosts").mock(
        return_value=httpx.Response(200, text="<html></html>")
    )
    client = _client(create_bearer_auth(token="t"))
    try:
        with pytest.raises(Exception, match="HTML"):
            await client.list_hosts(use_basic=False)
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_poll_reconnect_on_remote_disconnect():
    call_count = 0

    def flaky_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.RemoteProtocolError("disconnected")
        return httpx.Response(200, json={"status": "completed", "patch_run_id": "r1"})

    respx.get(f"{BASE}/api/v1/patching/runs/r1").mock(side_effect=flaky_response)
    client = _client(
        create_bearer_auth(token="tok"),
        poll_config=PollConfig(initial_interval=0.01, max_interval=0.02, timeout=5),
    )
    try:
        result = await client.poll_until_terminal("r1")
        assert result["status"] == "completed"
        assert call_count >= 2
    finally:
        await client.aclose()
