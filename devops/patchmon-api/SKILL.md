---
name: patchmon-api
description: Query and patch Linux servers managed by PatchMon (patchmon.net)
version: 1.0.0
author: Daniel
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [DevOps, Linux, PatchManagement, PatchMon, API]
    related_skills: []
required_environment_variables:
  - name: PATCHMON_URL
    prompt: "PatchMon base URL (e.g. https://patchmon.example.com)"
    help: "The base URL of the PatchMon instance you want to manage."
    required_for: "All API calls"
  - name: PATCHMON_USERNAME
    prompt: "PatchMon username"
    help: "An account on your PatchMon instance. Used to mint a Bearer JWT for action-capable endpoints."
    required_for: "Action-capable calls (patch, approve, stop)"
  - name: PATCHMON_PASSWORD
    prompt: "PatchMon password"
    help: "Password for the account above. Prefer setting PATCHMON_TOKEN instead if you already have a valid JWT."
    required_for: "Minting a Bearer JWT when PATCHMON_TOKEN is not set"
  - name: PATCHMON_KEY
    prompt: "PatchMon Integration API key (read-only)"
    help: "Scoped Basic-Auth key from the PatchMon UI. Optional — falls back to Bearer auth if unset."
    required_for: "Read-only endpoints via Integration API (outdated, hosts with stats)"
  - name: PATCHMON_SECRET
    prompt: "PatchMon Integration API secret"
    help: "Paired with PATCHMON_KEY for Basic Auth."
    required_for: "Read-only endpoints via Integration API"
---

# PatchMon API

PatchMon is a Linux patch-management service. This skill wraps its
two-tier API (read-only Integration API + action-capable Application
API) in a small CLI, plus a Playwright-based dashboard screenshot
helper. Use the script; do not hand-roll curl.

## When to use

- Listing managed hosts, host groups, or host stats
- Inspecting outstanding package updates on a host
- Triggering a patch run (full fleet, or specific packages)
- Dry-running a patch and approving it after review
- Polling a run to terminal status, stopping a queued run
- Capturing a visual screenshot of the PatchMon dashboard

The bundled script handles login, polling, and SPA-HTML detection
automatically. Every subcommand prints JSON to stdout; errors print
JSON to stderr and exit non-zero.

## Quick reference

```bash
# All paths below are substituted at skill-load time; do not hardcode.
SKILL_DIR="${HERMES_SKILL_DIR:-$(dirname "$0")/..}"
cd "$SKILL_DIR"

# All PATCHMON_* env vars are passed through from the host. Run:
python3 scripts/patchmon.py hosts              # list hosts
python3 scripts/patchmon.py outdated <host_id> # see what's pending
python3 scripts/patchmon.py patch <host_id>    # patch_all + poll to done
python3 scripts/patchmon.py runs --active      # what's running now
```

The script accepts `--username`/`--password`/`--token`/`--base-url`
flags as overrides. See `references/endpoints.md` for the full
endpoint catalog and `references/discrepancies.md` for known docs
that disagree with the deployed instance.

## Procedure

1. **Confirm credentials are present.** Hermes will prompt for any
   missing `PATCHMON_*` variables listed in the frontmatter. If you
   skipped the prompts, set them manually in your shell before
   proceeding, or pass the corresponding `--flag` to the script.
2. **Identify what to patch.**

   ```bash
   python3 scripts/patchmon.py hosts
   # Pick host_id(s) with non-zero updates_count
   python3 scripts/patchmon.py outdated "$HOST_ID"
   ```
3. **Trigger a patch run.**

   ```bash
   # Safe path — dry-run on specific packages
   python3 scripts/patchmon.py patch "$HOST_ID" --dry-run --packages curl openssl

   # Fast path — patch_all, applies immediately
   python3 scripts/patchmon.py patch "$HOST_ID"
   ```
4. **If you dry-ran, approve the run.** `approve` returns a NEW
   `patch_run_id` for the live run — track that one, not the dry-run
   id.

   ```bash
   python3 scripts/patchmon.py approve "$DRY_RUN_ID"
   ```
5. **Poll to terminal status.** `patch` and `approve` poll
   automatically (use `--no-wait` to skip).
6. **Inspect failures.** `run <run_id>` returns the full run object
   including `shell_output` and `error_message`. `apt-get update
   failed: exit status 100` and similar are usually transient — retry.

## Pitfalls

The six that actually bite:

1. **`host_id`, not `host_ids`.** The trigger endpoint takes a single
   host per call. Loop in the script (or your shell).
2. **`dry_run` requires `patch_type: "patch_package"`.** The script
   rejects `--dry-run` combined with `patch_all` automatically.
3. **`approve` returns a new `patch_run_id`.** Don't track the
   dry-run id; the script does this for you.
4. **No streaming.** `shell_output` is only populated after terminal
   status. The script polls `GET /patching/runs/{id}` every ~5s.
5. **JWT expires in 1 hour.** If you saved a `PATCHMON_TOKEN` and it
   returns `Invalid token`, drop it and let the script re-login from
   username/password.
6. **`outdated` requires Integration API Basic Auth.** It calls
   `_basic_headers()` which needs `PATCHMON_KEY` + `PATCHMON_SECRET`.
   If you only have app credentials, use the Application API
   fallback: `GET /api/v1/dashboard/packages` with a Bearer token —
   returns all outdated packages grouped by host.

### Data freshness caveat

The Integration API reflects the **last agent check-in**. A stale
host (`isStale: true`) may show 0 pending updates even when the
dashboard shows many. Use the Application API
`GET /api/v1/dashboard/packages` for an always-current view.

### Token cache

`patchmon.py` persists a freshly-minted JWT to
`${XDG_CACHE_HOME:-$HOME/.cache}/patchmon/token` (parent dir mode
0700, file mode 0600) so repeated invocations within an hour don't
re-authenticate. Pass `--token` to bypass the cache, or set
`PATCHMON_TOKEN` to override it.

## Verification

After any state-changing call, confirm the action landed:

```bash
python3 scripts/patchmon.py run "$NEW_RUN_ID" | jq '.status, .error_message'
```

`status` should be `completed`. If `failed`, inspect
`error_message` and `shell_output`. If the kernel updated, check
`needs_reboot` in the host stats from `hosts --hostgroup <name>`.

For a visual confirmation, use the screenshot helper. It logs in
with `PATCHMON_USERNAME`/`PATCHMON_PASSWORD` and saves a 1920×1080
PNG; emit `[[as_document]]` somewhere in your response so the
gateway delivers the file as a downloadable attachment instead of an
inline preview.

```bash
# First-time setup (Playwright + Chromium, ~300 MB into $PWD/node_modules):
npm install playwright && npx playwright install chromium

# Capture the dashboard:
node scripts/screenshot.js /tmp/patchmon_dash.png
```

Output: `/tmp/patchmon_dash.png` → include `[[as_document]]` in the
reply to deliver it.

## Notes

- Stdlib-only Python — no `pip install` needed for the API client.
- `screenshot.js` requires Node 18+ and a one-time Playwright install
  (see above).
- All paths in this file use `${HERMES_SKILL_DIR}` so the skill
  works regardless of where it's installed.
