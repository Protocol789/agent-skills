#!/usr/bin/env python3
"""patchmon.py — thin client for the PatchMon Application + Integration APIs.
Designed to be called by an LLM / Hermes agent. Every subcommand prints JSON
to stdout (or a scalar via --field) and exits non-zero on error. No interactive
prompts inside the script.

Use --field PATH (e.g. --field status or --field hosts.0.host_id) and
hosts --pending to obtain the data you need without shell pipes, jq, or
python -c. This avoids Hermes "dangerous command" prompts for |interpreter
patterns.

Global options (--field, --base-url, auth flags) must appear *before* the
subcommand (e.g. patchmon.py --field status run ID).

Auth precedence (highest first):
  1. --token <jwt>
  2. PATCHMON_TOKEN env var
  3. --username + --password (will call /auth/login)
  4. PATCHMON_USERNAME + PATCHMON_PASSWORD env vars
  5. For read-only commands only: PATCHMON_KEY + PATCHMON_SECRET (Basic Auth
     against Integration API)

Base URL precedence: --base-url > PATCHMON_URL > https://patchmon.net

Examples:
  patchmon.py status
  patchmon.py hosts --pending
  patchmon.py runs --active
  patchmon.py --field status run RUN_ID
  patchmon.py outdated HOST_ID
  patchmon.py patch HOST_ID
  patchmon.py stop RUN_ID
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_BASE = "https://patchmon.net"
POLL_INITIAL_INTERVAL = 2  # seconds — start fast
POLL_MAX_INTERVAL = 5  # seconds — cap
POLL_TIMEOUT = 60 * 30  # 30 minutes — patch_all on a busy host can take a while
TERMINAL_STATUSES = {"completed", "failed", "cancelled", "validated"}
# Cache the JWT under the user's XDG cache home (default ~/.cache/patchmon/token).
# Avoids leaving a plaintext token in the world-readable /tmp directory.
_TOKEN_CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
) / "patchmon"
_TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
try:
    _TOKEN_CACHE_DIR.chmod(0o700)
except OSError:
    pass
TOKEN_CACHE_PATH = _TOKEN_CACHE_DIR / "token"
TOKEN_MAX_AGE = 50 * 60  # 50 minutes (JWT expires in 60)


# ---------- HTTP ----------
def _request(method: str, url: str, headers: dict, body: dict | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    if data is not None:
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        _die(f"HTTP {e.code} {method} {url}: {raw.decode(errors='replace')[:500]}")
    text = raw.decode(errors="replace")
    # Guard against SPA HTML masquerading as 200 OK
    if text.lstrip().startswith("<"):
        _die(f"Got HTML, not JSON, from {url}. Wrong endpoint prefix or wrong auth?")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        _die(f"Non-JSON response from {url}: {text[:300]}")


def _die(msg: str) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(1)


def _extract_field(data: Any, field: str) -> Any:
    """Extract a (possibly nested) field from JSON result using dot paths.
    Supports 'status', 'error_message', 'hosts.0.friendly_name', list indexing.
    Returns None if not present.
    """
    if not field:
        return data
    cur: Any = data
    for seg in field.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, (list, tuple)):
            if seg.isdigit():
                idx = int(seg)
                cur = cur[idx] if 0 <= idx < len(cur) else None
            else:
                return None
        else:
            return None
    return cur


# ---------- Auth ----------
def _resolve_base(args) -> str:
    return (args.base_url or os.environ.get("PATCHMON_URL") or DEFAULT_BASE).rstrip("/")


def _login(base: str, username: str, password: str) -> str:
    res = _request("POST", f"{base}/api/v1/auth/login", {},
                   {"username": username, "password": password})
    token = res.get("token")
    if not token:
        _die(f"Login response missing token: {res}")
    return token


def _read_cached_token() -> str | None:
    """Return cached JWT if it exists and is less than TOKEN_MAX_AGE old."""
    if TOKEN_CACHE_PATH.exists():
        age = time.time() - TOKEN_CACHE_PATH.stat().st_mtime
        if age < TOKEN_MAX_AGE:
            return TOKEN_CACHE_PATH.read_text().strip()
    return None


def _write_cached_token(token: str) -> None:
    """Persist JWT to cache file."""
    TOKEN_CACHE_PATH.write_text(token)
    try:
        TOKEN_CACHE_PATH.chmod(0o600)
    except OSError:
        pass


def _bearer_headers(args) -> tuple[str, dict]:
    """Return (base, headers) for Application API calls."""
    base = _resolve_base(args)
    token = args.token or os.environ.get("PATCHMON_TOKEN")
    if not token:
        token = _read_cached_token()
    if not token:
        u = args.username or os.environ.get("PATCHMON_USERNAME")
        p = args.password or os.environ.get("PATCHMON_PASSWORD")
        if not (u and p):
            _die("No auth: provide --token, or --username/--password, "
                 "or set PATCHMON_TOKEN, or PATCHMON_USERNAME+PATCHMON_PASSWORD.")
        token = _login(base, u, p)
        _write_cached_token(token)
    return base, {"Authorization": f"Bearer {token}"}


def _basic_headers(args) -> tuple[str, dict]:
    """Return (base, headers) for Integration API calls."""
    base = _resolve_base(args)
    key = os.environ.get("PATCHMON_KEY")
    secret = os.environ.get("PATCHMON_SECRET")
    if key and secret:
        cred = b64encode(f"{key}:{secret}".encode()).decode()
        return base, {"Authorization": f"Basic {cred}"}
    _die("Integration API credentials required. "
         "Set PATCHMON_KEY and PATCHMON_SECRET env vars.")


# ---------- Commands ----------
def cmd_login(args) -> Any:
    """Return a fresh JWT (as {"token": "..."}) ."""
    base = _resolve_base(args)
    u = args.username or os.environ.get("PATCHMON_USERNAME")
    p = args.password or os.environ.get("PATCHMON_PASSWORD")
    if not (u and p):
        _die("Need --username and --password (or PATCHMON_USERNAME/PASSWORD env).")
    return {"token": _login(base, u, p)}


def cmd_hosts(args) -> Any:
    """List hosts. Uses Integration API if Basic creds available, else Bearer.
    Supports --pending / --needs-reboot client-side filters.
    """
    # Prefer Integration API for read-only when available — cheaper, no token expiry
    key = os.environ.get("PATCHMON_KEY")
    secret = os.environ.get("PATCHMON_SECRET")
    if key and secret:
        # Reuse _basic_headers (handles b64 + resolve_base). Safe because key+secret present.
        base, headers = _basic_headers(args)
        url = f"{base}/api/v1/api/hosts?include=stats"
        if args.hostgroup:
            url += f"&hostgroup={args.hostgroup}"
        data = _request("GET", url, headers)
    else:
        # Fall back to Application API dashboard
        base, headers = _bearer_headers(args)
        data = _request("GET", f"{base}/api/v1/dashboard/hosts", headers)

    # Apply client-side filters when requested (so agent doesn't need | python -c / jq)
    if args.pending or args.needs_reboot:
        data = _filter_hosts(data, args.pending, args.needs_reboot)

    return data


def _coerce_int(v: Any) -> int:
    """Defensively coerce count-like fields that may arrive as str/int/None/'0' etc."""
    if v in (None, "", "0", "false", False, 0):
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _coerce_bool(v: Any) -> bool:
    """Defensively coerce needs_reboot-like fields; 'false'/'0'/etc are False."""
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    s = str(v).strip().lower()
    if s in ("", "0", "false", "no", "n", "off"):
        return False
    if s in ("1", "true", "yes", "y", "on"):
        return True
    return bool(v)


def _filter_hosts(data: Any, pending: bool, needs_reboot: bool) -> Any:
    """Client-side filter so agents get only relevant hosts without shell post-processing."""
    # Normalize shape
    if isinstance(data, dict) and "hosts" in data:
        hosts_list = data.get("hosts") or []
        wrapped = True
    else:
        hosts_list = data if isinstance(data, list) else []
        wrapped = False

    def _matches(h: dict) -> bool:
        if not isinstance(h, dict):
            return False
        # Support both flat keys (some dashboard responses) and nested "stats"
        # (Integration /api/hosts?include=stats path, and as documented in SKILL.md).
        stats = h.get("stats") if isinstance(h.get("stats"), dict) else {}

        if pending:
            updates = (h.get("updatesCount") or h.get("updates_count") or h.get("updates") or
                       stats.get("updatesCount") or stats.get("updates_count") or stats.get("updates") or 0)
            security = (h.get("securityUpdatesCount") or h.get("security_updates_count") or h.get("securityUpdates") or
                        stats.get("securityUpdatesCount") or stats.get("security_updates_count") or stats.get("securityUpdates") or 0)
            updates = _coerce_int(updates)
            security = _coerce_int(security)
            if not (updates > 0 or security > 0):
                return False
        if needs_reboot:
            raw = (h.get("needs_reboot") or h.get("needsReboot") or
                   stats.get("needs_reboot") or stats.get("needsReboot") or False)
            if not _coerce_bool(raw):
                return False
        return True

    filtered = [h for h in hosts_list if _matches(h)] if isinstance(hosts_list, list) else hosts_list
    if wrapped:
        return {**data, "hosts": filtered}
    return filtered


def cmd_outdated(args) -> Any:
    """List packages with updates available for a host."""
    base, headers = _basic_headers(args)
    # Integration API path (works with both Basic and Bearer)
    url = f"{base}/api/v1/api/hosts/{args.host_id}/packages?updates_only=true"
    return _request("GET", url, headers)


def cmd_patch(args) -> Any:
    """Trigger a patch. If --wait (default), poll until terminal. Returns final run object."""
    base, headers = _bearer_headers(args)
    body = {
        "host_id": args.host_id,
        "patch_type": "patch_package" if args.packages else "patch_all",
        "dry_run": bool(args.dry_run),
    }
    if args.packages:
        body["package_names"] = args.packages
    if body["dry_run"] and body["patch_type"] == "patch_all":
        _die("dry_run is only supported with patch_package. "
             "Pass --packages, or drop --dry-run.")
    res = _request("POST", f"{base}/api/v1/patching/trigger", headers, body)
    run_id = res.get("patch_run_id")
    if not run_id:
        _die(f"Trigger response missing patch_run_id: {res}")
    if args.no_wait:
        return res
    print(json.dumps({"queued": run_id}), file=sys.stderr)
    final = _poll(base, headers, run_id)
    return final


def cmd_approve(args) -> Any:
    """Approve a validated dry-run. Polls the new live run until terminal. Returns final run."""
    base, headers = _bearer_headers(args)
    res = _request("POST", f"{base}/api/v1/patching/runs/{args.run_id}/approve",
                   headers, {"approved_by": args.approved_by})
    new_id = res.get("patch_run_id") or res.get("new_run_id")
    if not new_id:
        _die(f"Approve response missing new run id: {res}")
    if args.no_wait:
        return res
    print(json.dumps({"approved": args.run_id, "new_run": new_id}), file=sys.stderr)
    final = _poll(base, headers, new_id)
    return final


def cmd_run(args) -> Any:
    base, headers = _bearer_headers(args)
    return _request("GET", f"{base}/api/v1/patching/runs/{args.run_id}", headers)


def cmd_runs(args) -> Any:
    base, headers = _bearer_headers(args)
    path = "/api/v1/patching/runs/active" if args.active else "/api/v1/patching/runs"
    return _request("GET", f"{base}{path}", headers)


def _subcommand_args(args, **overrides) -> argparse.Namespace:
    """Reuse parent auth/globals when invoking one subcommand from another."""
    ns = argparse.Namespace(
        base_url=getattr(args, "base_url", None),
        token=getattr(args, "token", None),
        username=getattr(args, "username", None),
        password=getattr(args, "password", None),
        hostgroup=None,
        pending=False,
        needs_reboot=False,
        active=False,
    )
    for key, val in overrides.items():
        setattr(ns, key, val)
    return ns


def _list_payload(data: Any, *keys: str) -> list:
    """Normalize API/CLI payloads to a plain list for status aggregation."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def cmd_status(args) -> Any:
    """Fleet status: pending hosts and active runs in one invocation."""
    pending = cmd_hosts(_subcommand_args(args, pending=True))
    active = cmd_runs(_subcommand_args(args, active=True))
    return {
        "pending_hosts": _list_payload(pending, "hosts"),
        "active_runs": _list_payload(active, "runs", "active_runs"),
    }


def cmd_stop(args) -> Any:
    base, headers = _bearer_headers(args)
    return _request("POST", f"{base}/api/v1/patching/runs/{args.run_id}/stop", headers, {})


def _poll(base: str, headers: dict, run_id: str) -> dict:
    """Poll a run until status is terminal. Uses connection reuse and adaptive backoff."""
    deadline = time.time() + POLL_TIMEOUT
    last_status = None
    interval = POLL_INITIAL_INTERVAL
    parsed = urlparse(base)
    if parsed.scheme == "https":
        ctx = ssl.create_default_context()
        conn_factory = lambda: http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, context=ctx, timeout=30)
    else:
        ctx = None
        conn_factory = lambda: http.client.HTTPConnection(
            parsed.hostname, parsed.port or 80, timeout=30)
    conn = conn_factory()
    path = f"/api/v1/patching/runs/{run_id}"
    try:
        while time.time() < deadline:
            try:
                conn.request("GET", path, headers=headers)
                resp = conn.getresponse()
                raw = resp.read().decode(errors="replace")
            except (http.client.RemoteDisconnected, OSError):
                # Reconnect on dropped connection
                conn.close()
                conn = conn_factory()
                conn.request("GET", path, headers=headers)
                resp = conn.getresponse()
                raw = resp.read().decode(errors="replace")
            if raw.lstrip().startswith("<"):
                _die(f"Got HTML from {base}{path}. Auth expired?")
            run = json.loads(raw)
            status = run.get("status")
            if status != last_status:
                print(json.dumps({"run_id": run_id, "status": status}), file=sys.stderr)
                last_status = status
            if status in TERMINAL_STATUSES:
                return run
            time.sleep(interval)
            interval = min(interval * 2, POLL_MAX_INTERVAL)
    finally:
        conn.close()
    _die(f"Polling timed out after {POLL_TIMEOUT}s for run {run_id}")


# ---------- CLI ----------

def create_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Extracted for clarity, testability, and to follow common argparse CLI patterns.
    """
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version",
                   version="%(prog)s (patchmon-api skill)")

    # Logical grouping for nicer --help (well-known solid CLI practice)
    auth = p.add_argument_group("authentication options")
    auth.add_argument("--base-url", help="Override PATCHMON_URL")
    auth.add_argument("--token", help="Bearer JWT (skips login)")
    auth.add_argument("--username")
    auth.add_argument("--password")

    output = p.add_argument_group("output control")
    output.add_argument("--field", metavar="PATH",
                        help="Extract and print only this field (top-level key or dotted path like 'hosts.0.host_id' or 'status'). "
                             "Prints scalars directly (no quotes for strings) to simplify use without jq/python -c.")

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login").set_defaults(func=cmd_login)

    sp = sub.add_parser("status", help="Pending hosts and active runs (one call)")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("hosts", help="List hosts with stats")
    sp.add_argument("--hostgroup", help="Filter by host group name")
    sp.add_argument("--pending", action="store_true",
                    help="Only return hosts that have pending updates (supports updates_count or updatesCount)")
    sp.add_argument("--needs-reboot", action="store_true",
                    help="Only return hosts that require a reboot")
    sp.set_defaults(func=cmd_hosts)

    sp = sub.add_parser("outdated", help="List packages with updates for a host")
    sp.add_argument("host_id", metavar="HOST_ID")
    sp.set_defaults(func=cmd_outdated)

    sp = sub.add_parser("patch", help="Trigger a patch run")
    sp.add_argument("host_id", metavar="HOST_ID")
    sp.add_argument("--packages", nargs="+",
                    help="Specific packages (forces patch_package mode)")
    sp.add_argument("--dry-run", action="store_true",
                    help="Validate without applying (packages mode only)")
    sp.add_argument("--no-wait", action="store_true",
                    help="Return immediately after queuing")
    sp.set_defaults(func=cmd_patch)

    sp = sub.add_parser("approve", help="Approve a validated dry-run")
    sp.add_argument("run_id", metavar="RUN_ID")
    sp.add_argument("--approved-by", default="patchmon-api-skill")
    sp.add_argument("--no-wait", action="store_true")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("run", help="Get a single run by id")
    sp.add_argument("run_id", metavar="RUN_ID")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("runs", help="List runs")
    sp.add_argument("--active", action="store_true", help="Only active runs")
    sp.set_defaults(func=cmd_runs)

    sp = sub.add_parser("stop", help="Cancel a queued or running patch")
    sp.add_argument("run_id", metavar="RUN_ID")
    sp.set_defaults(func=cmd_stop)

    return p


def main() -> None:
    try:
        parser = create_parser()
        args = parser.parse_args()
        payload = args.func(args)
        _print_result(payload, getattr(args, "field", None))
    except SystemExit:
        raise
    except Exception as e:
        _die(f"unexpected error: {e}")


def _print_result(payload: Any, field: str | None = None) -> None:
    """Centralized output so callers (agents) get clean results.
    --field lets them obtain scalars without pipes or python -c.
    """
    if payload is None:
        return
    if field:
        val = _extract_field(payload, field)
        if val is None:
            print("null")
        elif isinstance(val, (dict, list)):
            print(json.dumps(val, indent=2))
        elif isinstance(val, str):
            print(val)
        elif val is True:
            print("true")
        elif val is False:
            print("false")
        else:
            print(val)
    else:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
