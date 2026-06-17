"""Pure, synchronous utility functions (no I/O)."""

from __future__ import annotations

from typing import Any

DEFAULT_BASE = "https://patchmon.net"
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "validated"}


def _extract_field(data: Any, path: str) -> Any:
    """Extract a dotted path from nested dicts/lists (e.g. hosts.0.host_id)."""
    if not path:
        return data
    current: Any = data
    for part in path.split("."):
        if current is None:
            return None
        if part.isdigit():
            if not isinstance(current, list):
                return None
            idx = int(part)
            if idx < 0 or idx >= len(current):
                return None
            current = current[idx]
        elif isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
    return None


def _filter_hosts(
    hosts: list[dict[str, Any]],
    *,
    pending: bool = False,
    needs_reboot: bool = False,
) -> list[dict[str, Any]]:
    """Filter host list by pending updates and/or reboot requirement."""
    if not pending and not needs_reboot:
        return hosts
    result: list[dict[str, Any]] = []
    for host in hosts:
        stats = host.get("stats") or {}
        pending_count = _coerce_int(stats.get("pending_updates")) or 0
        reboot = _coerce_bool(stats.get("needs_reboot")) or False
        if pending and pending_count <= 0:
            continue
        if needs_reboot and not reboot:
            continue
        result.append(host)
    return result
