"""CLI layer: argparse, async orchestration, and output formatting."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx

from . import __version__
from .auth import create_auth_strategy_from_args
from .client import (
    AsyncPatchmonClient,
)
from .exceptions import AuthError, PatchmonError, PollTimeout
from .utils import DEFAULT_BASE, _extract_field


def _die(msg: str) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(1)


def _resolve_base(args: argparse.Namespace) -> str:
    return (args.base_url or os.environ.get("PATCHMON_URL") or DEFAULT_BASE).rstrip("/")


def _print_result(data: Any, field: str | None = None) -> None:
    if field:
        extracted = _extract_field(data, field)
        print(json.dumps(extracted, indent=2))
    else:
        print(json.dumps(data, indent=2))


def create_parser() -> argparse.ArgumentParser:
    doc = """patchmon.py — thin client for the PatchMon Application + Integration APIs.
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
    p = argparse.ArgumentParser(
        description=doc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--base-url", help="Override PATCHMON_URL")
    p.add_argument("--token", help="Bearer JWT (skips login)")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument(
        "--field",
        help="Extract a dotted JSON path from the response (e.g. hosts.0.host_id)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login").set_defaults(func=cmd_login)

    sp = sub.add_parser("hosts", help="List hosts with stats")
    sp.add_argument("--hostgroup", help="Filter by host group name")
    sp.add_argument(
        "--pending",
        action="store_true",
        help="Only hosts with pending package updates",
    )
    sp.add_argument(
        "--needs-reboot",
        action="store_true",
        help="Only hosts that need a reboot",
    )
    sp.set_defaults(func=cmd_hosts)

    sp = sub.add_parser("outdated", help="List packages with updates for a host")
    sp.add_argument("host_id")
    sp.set_defaults(func=cmd_outdated)

    sp = sub.add_parser("patch", help="Trigger a patch run")
    sp.add_argument("host_id")
    sp.add_argument(
        "--packages",
        nargs="+",
        help="Specific packages (forces patch_package mode)",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without applying (packages mode only)",
    )
    sp.add_argument(
        "--no-wait",
        action="store_true",
        help="Return immediately after queuing",
    )
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

    return p


def _make_client(args: argparse.Namespace) -> AsyncPatchmonClient:
    http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)
    auth = create_auth_strategy_from_args(args)
    return AsyncPatchmonClient(
        http_client=http_client,
        auth=auth,
        base_url=_resolve_base(args),
    )


async def cmd_login(args: argparse.Namespace) -> None:
    """Print a fresh JWT. Useful for debugging or caching in env."""
    u = args.username or os.environ.get("PATCHMON_USERNAME")
    p = args.password or os.environ.get("PATCHMON_PASSWORD")
    if not (u and p):
        _die("Need --username and --password (or PATCHMON_USERNAME/PASSWORD env).")
    username, password = str(u), str(p)
    client = _make_client(args)
    try:
        data = await client.login(username, password)
        if args.field:
            _print_result({"token": data["token"]}, args.field)
        else:
            print(json.dumps({"token": data["token"]}))
    finally:
        await client.aclose()


async def cmd_hosts(args: argparse.Namespace) -> None:
    """List hosts. Uses Integration API if Basic creds available, else Bearer."""
    key = os.environ.get("PATCHMON_KEY")
    secret = os.environ.get("PATCHMON_SECRET")
    use_basic = bool(key and secret)
    client = _make_client(args)
    try:
        data = await client.list_hosts(hostgroup=args.hostgroup, use_basic=use_basic)
        if use_basic and (args.pending or getattr(args, "needs_reboot", False)):
            from .utils import _filter_hosts

            if isinstance(data, list):
                data = _filter_hosts(
                    data,
                    pending=args.pending,
                    needs_reboot=args.needs_reboot,
                )
        _print_result(data, args.field)
    except (AuthError, PatchmonError) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_outdated(args: argparse.Namespace) -> None:
    """List packages with updates available for a host."""
    client = _make_client(args)
    try:
        data = await client.list_outdated_packages(args.host_id)
        _print_result(data, args.field)
    except (AuthError, PatchmonError) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_patch(args: argparse.Namespace) -> None:
    """Trigger a patch. If --wait (default), poll until terminal."""
    patch_type = "patch_package" if args.packages else "patch_all"
    if args.dry_run and patch_type == "patch_all":
        _die(
            "dry_run is only supported with patch_package. "
            "Pass --packages, or drop --dry-run."
        )
    client = _make_client(args)
    try:
        res = await client.trigger_patch(
            host_id=args.host_id,
            patch_type=patch_type,
            package_names=args.packages,
            dry_run=bool(args.dry_run),
        )
        run_id = res.get("patch_run_id")
        if not run_id:
            _die(f"Trigger response missing patch_run_id: {res}")
        if args.no_wait:
            _print_result(res, args.field)
            return
        print(json.dumps({"queued": run_id}), file=sys.stderr)
        final = await client.poll_until_terminal(str(run_id))
        _print_result(final, args.field)
    except (AuthError, PatchmonError, PollTimeout) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a validated dry-run. Polls the new live run until terminal."""
    client = _make_client(args)
    try:
        res = await client.approve_run(run_id=args.run_id, approved_by=args.approved_by)
        new_id = res.get("patch_run_id") or res.get("new_run_id")
        if not new_id:
            _die(f"Approve response missing new run id: {res}")
        if args.no_wait:
            _print_result(res, args.field)
            return
        print(
            json.dumps({"approved": args.run_id, "new_run": new_id}),
            file=sys.stderr,
        )
        final = await client.poll_until_terminal(str(new_id))
        _print_result(final, args.field)
    except (AuthError, PatchmonError, PollTimeout) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_run(args: argparse.Namespace) -> None:
    client = _make_client(args)
    try:
        data = await client.get_run(args.run_id)
        _print_result(data, args.field)
    except (AuthError, PatchmonError) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_runs(args: argparse.Namespace) -> None:
    client = _make_client(args)
    try:
        data = await client.list_runs(active=args.active)
        _print_result(data, args.field)
    except (AuthError, PatchmonError) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def cmd_stop(args: argparse.Namespace) -> None:
    client = _make_client(args)
    try:
        data = await client.stop_run(args.run_id)
        _print_result(data, args.field)
    except (AuthError, PatchmonError) as exc:
        _die(str(exc))
    finally:
        await client.aclose()


async def async_main(args: argparse.Namespace | None = None) -> None:
    parser = create_parser()
    ns = args if args is not None else parser.parse_args()
    await ns.func(ns)


def main() -> None:
    try:
        parser = create_parser()
        args = parser.parse_args()
        asyncio.run(async_main(args))
    except SystemExit:
        raise
    except Exception as e:
        _die(f"unexpected error: {e}")
