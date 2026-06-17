"""Async PatchMon API client facade."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

import httpx

from .auth import AuthStrategy, BasicAuthStrategy
from .exceptions import PatchmonError, PollTimeout
from .models import PollConfig
from .utils import TERMINAL_STATUSES

POLL_INITIAL_INTERVAL = 2.0
POLL_MAX_INTERVAL = 5.0
POLL_TIMEOUT = 60 * 30


class AsyncPatchmonClient:
    """Central facade for PatchMon HTTP interactions and polling."""

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        auth: AuthStrategy,
        base_url: str,
        poll_config: PollConfig | None = None,
    ) -> None:
        self._http_client = http_client
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._poll_config = poll_config or PollConfig(
            initial_interval=POLL_INITIAL_INTERVAL,
            max_interval=POLL_MAX_INTERVAL,
            timeout=POLL_TIMEOUT,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: AuthStrategy | None = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        strategy = auth or self._auth
        auth_headers = await strategy.prepare(
            client=self._http_client, base_url=self._base_url
        )
        merged = {**auth_headers, **(headers or {})}
        if json_body is not None:
            merged = {**merged, "Content-Type": "application/json"}
        resp = await self._http_client.request(
            method, url, json=json_body, headers=merged
        )
        text = resp.text
        if resp.is_error:
            raise PatchmonError(f"HTTP {resp.status_code} {method} {url}: {text[:500]}")
        if text.lstrip().startswith("<"):
            raise PatchmonError(
                f"Got HTML, not JSON, from {url}. Wrong endpoint prefix or wrong auth?"
            )
        try:
            return resp.json()
        except json.JSONDecodeError:
            raise PatchmonError(f"Non-JSON response from {url}: {text[:300]}") from None

    async def login(self, username: str, password: str) -> dict[str, Any]:
        resp = await self._http_client.post(
            f"{self._base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        text = resp.text
        if resp.is_error:
            raise PatchmonError(
                f"HTTP {resp.status_code} POST {self._base_url}/api/v1/auth/login: "
                f"{text[:500]}"
            )
        if text.lstrip().startswith("<"):
            raise PatchmonError(
                f"Got HTML, not JSON, from {self._base_url}/api/v1/auth/login. "
                "Wrong endpoint prefix or wrong auth?"
            )
        try:
            data: dict[str, Any] = resp.json()
        except json.JSONDecodeError:
            raise PatchmonError(
                "Non-JSON response from "
                f"{self._base_url}/api/v1/auth/login: {text[:300]}"
            ) from None
        if not data.get("token"):
            raise PatchmonError(f"Login response missing token: {data}")
        return data

    async def list_hosts(
        self, *, hostgroup: str | None = None, use_basic: bool = False
    ) -> Any:
        if use_basic:
            basic = BasicAuthStrategy()
            path = "/api/v1/api/hosts?include=stats"
            if hostgroup:
                path += f"&hostgroup={hostgroup}"
            return await self._request("GET", path, auth=basic)
        return await self._request("GET", "/api/v1/dashboard/hosts")

    async def list_outdated_packages(self, host_id: str) -> Any:
        basic = BasicAuthStrategy()
        return await self._request(
            "GET",
            f"/api/v1/api/hosts/{host_id}/packages?updates_only=true",
            auth=basic,
        )

    async def trigger_patch(
        self,
        *,
        host_id: str,
        patch_type: str,
        package_names: list[str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "host_id": host_id,
            "patch_type": patch_type,
            "dry_run": dry_run,
        }
        if package_names:
            body["package_names"] = package_names
        result = await self._request("POST", "/api/v1/patching/trigger", json_body=body)
        if not isinstance(result, dict):
            raise PatchmonError(f"Unexpected trigger response: {result}")
        return result

    async def approve_run(self, *, run_id: str, approved_by: str) -> dict[str, Any]:
        result = await self._request(
            "POST",
            f"/api/v1/patching/runs/{run_id}/approve",
            json_body={"approved_by": approved_by},
        )
        if not isinstance(result, dict):
            raise PatchmonError(f"Unexpected approve response: {result}")
        return result

    async def get_run(self, run_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/api/v1/patching/runs/{run_id}")
        if not isinstance(result, dict):
            raise PatchmonError(f"Unexpected run response: {result}")
        return result

    async def list_runs(self, *, active: bool = False) -> Any:
        path = "/api/v1/patching/runs/active" if active else "/api/v1/patching/runs"
        return await self._request("GET", path)

    async def stop_run(self, run_id: str) -> dict[str, Any]:
        result = await self._request(
            "POST", f"/api/v1/patching/runs/{run_id}/stop", json_body={}
        )
        if not isinstance(result, dict):
            raise PatchmonError(f"Unexpected stop response: {result}")
        return result

    async def poll_until_terminal(self, run_id: str) -> dict[str, Any]:
        async def _poll() -> dict[str, Any]:
            last_status: str | None = None
            interval = self._poll_config.initial_interval
            path = f"/api/v1/patching/runs/{run_id}"
            while True:
                try:
                    run = await self._request("GET", path)
                except (httpx.RemoteProtocolError, httpx.ReadError, OSError):
                    run = await self._request("GET", path)
                if not isinstance(run, dict):
                    raise PatchmonError(f"Unexpected poll response: {run}")
                status = run.get("status")
                if status != last_status:
                    print(
                        json.dumps({"run_id": run_id, "status": status}),
                        file=sys.stderr,
                    )
                    last_status = str(status) if status is not None else None
                if status in TERMINAL_STATUSES:
                    return run
                await asyncio.sleep(interval)
                interval = min(interval * 2, self._poll_config.max_interval)

        try:
            return await asyncio.wait_for(_poll(), timeout=self._poll_config.timeout)
        except asyncio.TimeoutError as exc:
            raise PollTimeout(
                f"Polling timed out after {self._poll_config.timeout}s for run {run_id}"
            ) from exc

    async def aclose(self) -> None:
        await self._http_client.aclose()
