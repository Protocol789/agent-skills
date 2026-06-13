#!/usr/bin/env python3
"""patchmon.py — thin client for the PatchMon Application + Integration APIs.
Designed to be called by an LLM. Every subcommand prints JSON to stdout and
exits non-zero on error. No interactive prompts.

Auth precedence (highest first):
  1. --token <jwt>
  2. PATCHMON_TOKEN env var
  3. --username + --password (will call /auth/login)
  4. PATCHMON_USERNAME + PATCHMON_PASSWORD env vars
  5. For read-only commands only: PATCHMON_KEY + PATCHMON_SECRET (Basic Auth
     against Integration API)

Base URL precedence: --base-url > PATCHMON_URL > https://patchmon.net

Examples:
  patchmon.py hosts                          # list hosts with stats
  patchmon.py outdated <host_id>             # list packages with updates
  patchmon.py patch <host_id>                # patch_all, no dry-run, poll until done
  patchmon.py patch <host_id> --dry-run --packages curl openssl
  patchmon.py approve <run_id>               # approve a validated dry-run, poll new run
  patchmon.py run <run_id>                   # fetch a single run
  patchmon.py runs --active                  # currently running jobs
  patchmon.py stop <run_id>
"""
from __future__ import annotations

import argparse
import hashlib
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
def cmd_login(args) -> None:
    """Print a fresh JWT. Useful for debugging or caching in env."""
    base = _resolve_base(args)
    u = args.username or os.environ.get("PATCHMON_USERNAME")
    p = args.password or os.environ.get("PATCHMON_PASSWORD")
    if not (u and p):
        _die("Need --username and --password (or PATCHMON_USERNAME/PASSWORD env).")
    print(json.dumps({"token": _login(base, u, p)}))


def cmd_hosts(args) -> None:
    """List hosts. Uses Integration API if Basic creds available, else Bearer."""
    # Prefer Integration API for read-only when available — cheaper, no token expiry
    key = os.environ.get("PATCHMON_KEY")
    secret = os.environ.get("PATCHMON_SECRET")
    base = _resolve_base(args)
    if key and secret:
        cred = b64encode(f"{key}:{secret}".encode()).decode()
        headers = {"Authorization": f"Basic {cred}"}
        url = f"{base}/api/v1/api/hosts?include=stats"
        if args.hostgroup:
            url += f"&hostgroup={args.hostgroup}"
        print(json.dumps(_request("GET", url, headers), indent=2))
        return
    # Fall back to Application API dashboard
    base, headers = _bearer_headers(args)
    print(json.dumps(_request("GET", f"{base}/api/v1/dashboard/hosts", headers), indent=2))


def cmd_outdated(args) -> None:
    """List packages with updates available for a host."""
    base, headers = _basic_headers(args)
    # Integration API path (works with both Basic and Bearer)
    url = f"{base}/api/v1/api/hosts/{args.host_id}/packages?updates_only=true"
    print(json.dumps(_request("GET", url, headers), indent=2))


def cmd_patch(args) -> None:
    """Trigger a patch. If --wait (default), poll until terminal."""
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
        print(json.dumps(res, indent=2))
        return
    print(json.dumps({"queued": run_id}), file=sys.stderr)
    final = _poll(base, headers, run_id)
    print(json.dumps(final, indent=2))


def cmd_approve(args) -> None:
    """Approve a validated dry-run. Polls the new live run until terminal."""
    base, headers = _bearer_headers(args)
    res = _request("POST", f"{base}/api/v1/patching/runs/{args.run_id}/approve",
                   headers, {"approved_by": args.approved_by})
    new_id = res.get("patch_run_id") or res.get("new_run_id")
    if not new_id:
        _die(f"Approve response missing new run id: {res}")
    if args.no_wait:
        print(json.dumps(res, indent=2))
        return
    print(json.dumps({"approved": args.run_id, "new_run": new_id}), file=sys.stderr)
    final = _poll(base, headers, new_id)
    print(json.dumps(final, indent=2))


def cmd_run(args) -> None:
    base, headers = _bearer_headers(args)
    print(json.dumps(_request("GET", f"{base}/api/v1/patching/runs/{args.run_id}",
                              headers), indent=2))


def cmd_runs(args) -> None:
    base, headers = _bearer_headers(args)
    path = "/api/v1/patching/runs/active" if args.active else "/api/v1/patching/runs"
    print(json.dumps(_request("GET", f"{base}{path}", headers), indent=2))


def cmd_stop(args) -> None:
    base, headers = _bearer_headers(args)
    print(json.dumps(_request("POST",
                              f"{base}/api/v1/patching/runs/{args.run_id}/stop",
                              headers, {}), indent=2))


def _poll(base: str, headers: dict, run_id: str) -> dict:
    """Poll a run until status is terminal. Uses connection reuse and adaptive backoff."""
    deadline = time.time() + POLL_TIMEOUT
    last_status = None
    interval = POLL_INITIAL_INTERVAL
    parsed = urlparse(base)
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443,
                                       context=ctx, timeout=30)
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
                conn = http.client.HTTPSConnection(
                    parsed.hostname, parsed.port or 443, context=ctx, timeout=30)
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
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", help="Override PATCHMON_URL")
    p.add_argument("--token", help="Bearer JWT (skips login)")
    p.add_argument("--username")
    p.add_argument("--password")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login").set_defaults(func=cmd_login)

    sp = sub.add_parser("hosts", help="List hosts with stats")
    sp.add_argument("--hostgroup", help="Filter by host group name")
    sp.set_defaults(func=cmd_hosts)

    sp = sub.add_parser("outdated", help="List packages with updates for a host")
    sp.add_argument("host_id")
    sp.set_defaults(func=cmd_outdated)

    sp = sub.add_parser("patch", help="Trigger a patch run")
    sp.add_argument("host_id")
    sp.add_argument("--packages", nargs="+",
                    help="Specific packages (forces patch_package mode)")
    sp.add_argument("--dry-run", action="store_true",
                    help="Validate without applying (packages mode only)")
    sp.add_argument("--no-wait", action="store_true",
                    help="Return immediately after queuing")
    sp.set_defaults(func=cmd_patch)

    sp = sub.add_parser("approve", help="Approve a validated dry-run")
    sp.add_argument("run_id")
    sp.add_argument("--approved-by", default="patchmon-api-skill")
    sp.add_argument("--no-wait", action="store_true")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("run", help="Get a single run by id")
    sp.add_argument("run_id")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("runs", help="List runs")
    sp.add_argument("--active", action="store_true", help="Only active runs")
    sp.set_defaults(func=cmd_runs)

    sp = sub.add_parser("stop", help="Cancel a queued or running patch")
    sp.add_argument("run_id")
    sp.set_defaults(func=cmd_stop)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
