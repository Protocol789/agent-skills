"""Authentication strategies for PatchMon API requests."""

from __future__ import annotations

import os
from base64 import b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, final

import httpx

from . import cache
from .exceptions import AuthError


class AuthStrategy(Protocol):
    """Return headers for a request. May perform login (Bearer) as side effect."""

    async def prepare(
        self, *, client: httpx.AsyncClient, base_url: str
    ) -> dict[str, str]: ...


@final
@dataclass
class BearerAuthStrategy:
    """Bearer JWT auth with token, cache, or login fallback."""

    token: str | None = None
    username: str | None = None
    password: str | None = None
    cache_path: os.PathLike[str] | None = None

    async def prepare(
        self, *, client: httpx.AsyncClient, base_url: str
    ) -> dict[str, str]:
        token = self.token
        cache_path = Path(self.cache_path) if self.cache_path is not None else None
        if not token:
            token = await cache.read_cached_token(cache_path)
        if not token:
            if not (self.username and self.password):
                raise AuthError(
                    "No auth: provide --token, or --username/--password, "
                    "or set PATCHMON_TOKEN, or PATCHMON_USERNAME+PATCHMON_PASSWORD."
                )
            token = await self._login(client, base_url, self.username, self.password)
            await cache.write_cached_token(cache_path, token)
        return {"Authorization": f"Bearer {token}"}

    async def _login(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        username: str,
        password: str,
    ) -> str:
        resp = await client.post(
            f"{base_url}/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        if resp.is_error:
            body = resp.text[:500]
            raise AuthError(
                f"HTTP {resp.status_code} POST {base_url}/api/v1/auth/login: {body}"
            )
        text = resp.text
        if text.lstrip().startswith("<"):
            raise AuthError(
                f"Got HTML, not JSON, from {base_url}/api/v1/auth/login. "
                "Wrong endpoint prefix or wrong auth?"
            )
        try:
            data: dict[str, Any] = resp.json()
        except ValueError as exc:
            raise AuthError(
                f"Non-JSON response from {base_url}/api/v1/auth/login: {text[:300]}"
            ) from exc
        token = data.get("token")
        if not token:
            raise AuthError(f"Login response missing token: {data}")
        return str(token)


@final
@dataclass
class BasicAuthStrategy:
    """Integration API Basic auth from PATCHMON_KEY + PATCHMON_SECRET."""

    key: str | None = None
    secret: str | None = None

    async def prepare(
        self, *, client: httpx.AsyncClient, base_url: str
    ) -> dict[str, str]:
        del client, base_url  # unused
        key = self.key or os.environ.get("PATCHMON_KEY")
        secret = self.secret or os.environ.get("PATCHMON_SECRET")
        if key and secret:
            cred = b64encode(f"{key}:{secret}".encode()).decode()
            return {"Authorization": f"Basic {cred}"}
        raise AuthError(
            "Integration API credentials required. "
            "Set PATCHMON_KEY and PATCHMON_SECRET env vars."
        )


def create_bearer_auth(
    *,
    token: str | None = None,
    username: str | None = None,
    password: str | None = None,
    cache_path: os.PathLike[str] | None = None,
) -> BearerAuthStrategy:
    return BearerAuthStrategy(
        token=token,
        username=username,
        password=password,
        cache_path=cache_path,
    )


def create_basic_auth(
    *, key: str | None = None, secret: str | None = None
) -> BasicAuthStrategy:
    return BasicAuthStrategy(key=key, secret=secret)


def create_auth_strategy_from_args(args: Any) -> BearerAuthStrategy:
    """Build Bearer auth from CLI args + env (Application API precedence)."""
    return create_bearer_auth(
        token=getattr(args, "token", None) or os.environ.get("PATCHMON_TOKEN"),
        username=getattr(args, "username", None) or os.environ.get("PATCHMON_USERNAME"),
        password=getattr(args, "password", None) or os.environ.get("PATCHMON_PASSWORD"),
    )
