---
name: patchmon-api
description: >
  Query and patch Linux servers managed by PatchMon (e.g. patchmon.net).
  Use this skill whenever the user asks to list hosts, see outstanding updates,
  trigger patching, dry-run a patch, approve a patch, check a patch run's status,
  or stop a run. Trigger on mentions of "patchmon", "patch the server(s)",
  "Linux updates", "apt updates on host X", "kick off patching",
  "what needs patching", or similar — even if the user doesn't say "PatchMon"
  explicitly, if the context is a managed Linux fleet.
triggers:
  - patchmon
  - patchmon-api
  - patchmon\.net
  - linux patch management
  - query patches
  - initiate patching
  - patching runs
  - patch the servers
  - linux updates
  - apt updates
  - what needs patching
  - kick off patching
---

# PatchMon API

PatchMon manages Linux patching. This skill is for **doing things** — listing
hosts, triggering patches, monitoring runs. The hard parts (auth dance, polling,
dry-run-only-works-with-packages, approve-returns-new-id) are wrapped in
`scripts/patchmon.py`. Use the script; do not hand-roll curl.

## Quick start

Credentials are **pre-loaded in the environment** for this Hermes deployment:
`PATCHMON_URL`, `PATCHMON_USERNAME`, `PATCHMON_PASSWORD`, `PATCHMON_KEY`, `PATCHMON_SECRET` are all set. No need to export or provide them — just run the commands.

```bash
# All auth env vars are already set. Just run:
python3 scripts/patchmon.py hosts              # list hosts
python3 scripts/patchmon.py outdated <host_id> # see what's pending
python3 scripts/patchmon.py patch <host_id>    # patch_all + poll to done
python3 scripts/patchmon.py runs --active      # what's running now
```

Manual auth override (only if needed):
```bash
# Read-only queries via Integration API token pair:
export PATCHMON_KEY="..."
export PATCHMON_SECRET="..."

# Action-capable Bearer token:
export PATCHMON_TOKEN="$(python3 scripts/patchmon.py --username "$PATCHMON_USERNAME" --password "$PATCHMON_PASSWORD" login | jq -r .token)"
```

The script handles login, polling, and SPA-HTML detection automatically. Every
command prints JSON to stdout; errors print JSON to stderr and exit non-zero.

## The two-tier auth model (one-liner)

- **Integration API** (`/api/v1/api/...`) is read-only, uses Basic Auth with a
  key/secret pair from the UI. Cannot trigger patches.
- **Application API** (`/api/v1/...`) is action-capable, uses a Bearer JWT from
  `POST /api/v1/auth/login`. JWT expires in 1 hour.

For anything that **changes state**, you need the Bearer token. The script gets
one automatically when you set `PATCHMON_USERNAME`/`PATCHMON_PASSWORD`.

## The patch workflow

```
┌────────────────┬
│   hosts         │  ←  who needs patching?
└──────────┬──────────┘
              │
       ┌──────────┬──────────┐
       │ outdated <id> │  ←  inspect a specific host
       └──────────┬──────────┘
                    │
     ┌────────────────┬───────────────────┐
safe path  │                 │  fast path
     │      patch <id> --dry-run      patch <id>
     │      --packages a b c          (patch_all, applies immediately)
     │                 │  │
     │       review shell_output      │
     │                 │  │
     └─────────────┬────────────┘
              approve <run_id> → new run id ──────┬
                                                    │
                                          poll to terminal status
                                                    │
                                          status: completed / failed
                                                    │
                                          check needs_reboot
```

The script's `patch` subcommand polls automatically (use `--no-wait` to skip).
The `approve` subcommand approves the dry-run **and** polls the resulting live
run.

## Run statuses

| Status | Meaning |
|---|---|
| `queued` | Waiting for agent slot |
| `validated` | Dry-run completed successfully; ready for approval |
| `approved` | Dry-run was approved; a new live run was spawned |
| `completed` | Live patch run finished without errors |
| `failed` | Live patch run encountered an error (see `error_message`) |
| `cancelled` | Run was stopped via `stop` subcommand |

## When to use dry-run

- **Skip dry-run** for routine `patch_all` on hosts you trust. Fast path.
- **Use dry-run** when patching specific packages on production hosts, or
  when the host has had failures recently. Dry-run only works with `--packages`,
  never with `patch_all`.

## Inspecting failures

```bash
python3 scripts/patchmon.py run <run_id>   # full run object, incl. shell_output
python3 scripts/patchmon.py runs           # recent runs, see what failed
```

`apt-get update failed: exit status 100` and similar are usually transient repo
issues — re-trigger the patch. If a kernel updated, check `needs_reboot` in
the host stats.

## Critical gotchas (the six that actually bite)

1. **`host_id`, not `host_ids`.** The trigger endpoint takes a single host per
   call. Loop in Python; the script does this for you per invocation.
2. **`dry_run` requires `patch_type: "patch_package"`.** Will reject if combined
   with `patch_all`. The script enforces this.
3. **`approve` returns a NEW `patch_run_id`** for the live run. Track that new
   ID, not the original dry-run ID. The script does this transparently.
4. **No streaming.** The agent's `shell_output` is only populated after the
   run reaches a terminal status. Poll `GET /patching/runs/{id}` every ~5s; the
   script does this.
5. **JWT expires in 1 hour.** If a saved `PATCHMON_TOKEN` returns `Invalid
   token`, drop it and let the script re-login from username/password.
6. **`outdated` requires Integration API Basic Auth.** The `outdated` subcommand
   calls `_basic_headers()` which requires `PATCHMON_KEY`/`PATCHMON_SECRET`
   (scoped token pair from the PatchMon UI). It does NOT work with
   username/password Bearer auth. If you only have app credentials, use the
   Application API fallback: `GET /api/v1/dashboard/packages` with a Bearer
   token — returns all outdated packages grouped by host with
   `affectedHosts[].{friendlyName,currentVersion,availableVersion,isSecurityUpdate}`.

## Env var casing and auth setup

The script expects **uppercase** env vars: `PATCHMON_USERNAME`,
`PATCHMON_PASSWORD`, `PATCHMON_KEY`, `PATCHMON_SECRET`. If your shell has them
under different names, alias them before invoking the script, or pass
`--username` / `--password` / `--token` explicitly.

```bash
# Example: remap to the names the script expects
export PATCHMON_USERNAME="${MY_PM_USER:-}"
export PATCHMON_PASSWORD="${MY_PM_PASS:-}"
export PATCHMON_KEY="${MY_PM_KEY:-}"
export PATCHMON_SECRET="${MY_PM_SECRET:-}"
```

## Data freshness caveat

The Integration API (`outdated`, `hosts` with stats) reflects the **last agent
check-in**. If a host is stale (`isStale: true`), `outdated` may return 0
packages even when the dashboard shows many pending updates. Use the Application
API `GET /api/v1/dashboard/packages` (Bearer auth) for a host-aggregated view
that is always current — it pulls from the dashboard database, not the agent's
last report.

## `hosts` dual-auth behavior

The `hosts` subcommand **prefers Integration API** when `PATCHMON_KEY` and
`PATCHMON_SECRET` are available (cheaper, no token expiry). It falls back to
Application API (`PATCHMON_USERNAME`/`PATCHMON_PASSWORD`) automatically. Both
paths return similar data, but the Integration API path includes richer fields
via `?include=stats`.

## Minting a token manually

The `login` subcommand accepts credentials as **global arguments** (before the
subcommand), not after it:

```bash
# Correct:
python3 scripts/patchmon.py --username "$PATCHMON_USERNAME" --password "$PATCHMON_PASSWORD" login

# Wrong (fails with "unrecognized arguments"):
python3 scripts/patchmon.py login --username "$PATCHMON_USERNAME" --password "$PATCHMON_PASSWORD"
```

## Direct curl (only when the script can't be used)

Just the two endpoints worth memorising:

```bash
# Mint a token
TOKEN=$(curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"username":"...","password":"..."}' \
  "$PATCHMON_URL/api/v1/auth/login" | jq -r .token)

# Trigger
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"host_id":"<uuid>","patch_type":"patch_all","dry_run":false}' \
  "$PATCHMON_URL/api/v1/patching/trigger"
```

## Browser screenshots

When you need a **visual dashboard screenshot** (not API data), use the Playwright-based screenshot script. The Hermes `browser_*` tools cannot capture screenshots — they only provide text snapshots and interaction.

```bash
# Check if playwright is installed first; if not:
cd /tmp && npm install playwright && npx playwright install chromium

# Then take the screenshot:
node scripts/screenshot.js [output_path]
```

The script logs in automatically using `PATCHMON_USERNAME`/`PATCHMON_PASSWORD`, waits 3 seconds for the dashboard to render, and saves a 1920×1080 PNG. Use `MEDIA:/path/to/screenshot.png` to deliver the image to the user.

**When to use this:** User asks to "take a screenshot", "show me the dashboard", or wants visual confirmation of PatchMon state. For data queries (host lists, patch status), use the API commands above instead.

## Batch patching all hosts

To patch every host that has outstanding updates, combine `hosts` output with a loop:

```bash
cd /root/.hermes/skills/devops/patchmon-api

# Get host IDs that have updates (python for JSON since jq may not be installed)
python3 scripts/patchmon.py hosts 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for h in data.get('hosts', []):
    if h.get('updates_count', 0) > 0:
        print(f\"{h['friendly_name']}:{h['id']}\")
" > /tmp/hosts_to_patch.txt

# Trigger patch_all on each (non-blocking)
while IFS=: read -r name hid; do
  result=$(python3 scripts/patchmon.py patch "$hid" --no-wait 2>/dev/null)
  run_id=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin).get('patch_run_id','?'))" 2>/dev/null)
  printf "%-20s run=%s\n" "$name" "$run_id"
done < /tmp/hosts_to_patch.txt
```

Use `--no-wait` to fire them all off quickly, then schedule a cron job to check completion status ~10 min later.

## When to consult references/

The script and this file cover ~95% of patching work. Go to references for:

- **`references/endpoints.md`** — full Integration & Application API catalog
  (host system/network/notes/integrations/agent-queue, GetHomepage widget,
  auto-enrollment, alerts, compliance, docker, repositories, settings). Use when
  the user asks for non-patching data, e.g. "what's the kernel on host X" or
  "show me Docker containers per host".
- **`references/discrepancies.md`** — known cases where `patchmon.net/docs`
  lists endpoints that don't exist on the deployed instance. Consult before
  trusting any external doc that claims an endpoint like
  `/api/v1/patches/dry-run` or `/api/v1/jobs/{id}/stream-summary`.
