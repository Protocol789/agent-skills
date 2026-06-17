---
name: patchmon-api
description: Query and patch Linux servers managed by PatchMon. Use when the user asks for patch status/summary, outstanding package updates on a host, listing managed hosts or host groups, or to trigger/approve/poll/stop a patch run.
version: 1.0.0
author: Daniel
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [DevOps, Linux, PatchManagement, PatchMon, API]
    related_skills: []
    references:
      - references/output-format.md
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

Query and patch Linux servers via PatchMon's two-tier API (read-only Integration + action-capable Application). Use the bundled script — do not hand-roll curl.

## DEFAULT REQUEST HANDLING

For any **status / summary / what's pending / what's going on** request, run `status` **once**, format the returned JSON into your answer, and **STOP**. Do **not** run `hosts`, `runs`, `outdated`, `run`, `--help`, or any other subcommand unless the user names a specific host or run. No discovery. Do not call `--help`; commands are documented here and in `references/endpoints.md`.

## Canonical Usage

```bash
SKILL_DIR="${HERMES_SKILL_DIR}"
"${SKILL_DIR}/scripts/patchmon.py" status
```

Returns `{"pending_hosts": [...], "active_runs": [...]}` in one invocation. Format it (see `references/output-format.md`), then ask the user before any follow-up calls.

## When to use

- Patching status summary — start with `status` (see DEFAULT REQUEST HANDLING)
- Triggering a patch run (full fleet or specific packages)
- Dry-running a patch and approving it after review
- Drill-down on a **named** host or run (see `references/endpoints.md`)

The script handles login, polling, and SPA-HTML detection. Subcommands print JSON to stdout (or a scalar via `--field`); errors print JSON to stderr and exit non-zero.

## Quick reference

```bash
SKILL_DIR="${HERMES_SKILL_DIR}"

# Default path
"${SKILL_DIR}/scripts/patchmon.py" status

# Patch flow
"${SKILL_DIR}/scripts/patchmon.py" patch "$HOST_ID" --dry-run --packages curl openssl
"${SKILL_DIR}/scripts/patchmon.py" patch "$HOST_ID"
"${SKILL_DIR}/scripts/patchmon.py" approve "$DRY_RUN_ID"
```

Pass `--username`/`--password`/`--token`/`--base-url` to override env vars. Global options like `--field` go **before** the subcommand. Full subcommand catalog: `references/endpoints.md`. Docs-vs-deployed quirks: `references/discrepancies.md`.

## Output handling

**Never pipe `patchmon.py` output to `jq`, `python -c`, `column`, `awk`, or similar.** Hermes sandboxes shell execution and flags those patterns as dangerous.

Do all selection, filtering, and shaping with built-in flags — especially `--field`. The tool returns JSON (or a scalar) directly to you; format your user-facing table in your response from that data.

## Procedure (patch / approve)

1. **Credentials.** Hermes prompts for missing `PATCHMON_*` vars (see frontmatter). Or set them in the shell / pass the matching `--flag`.
2. **Patch.**

   ```bash
   "${SKILL_DIR}/scripts/patchmon.py" patch "$HOST_ID" --dry-run --packages curl openssl
   "${SKILL_DIR}/scripts/patchmon.py" patch "$HOST_ID"
   ```

3. **Approve after dry-run.** `approve` returns a **new** `patch_run_id` for the live run — track that one.
4. **Poll.** `patch` and `approve` poll automatically (`--no-wait` to skip).
5. **Failures.** See `references/endpoints.md` — `run <run_id>` for `shell_output` and `error_message`. Transient apt errors (e.g. exit status 100) — retry.

## Pitfalls

The seven that actually bite:

1. **`host_id`, not `host_ids`.** One host per trigger call; loop in the script or your shell.
2. **`dry_run` requires `patch_type: "patch_package"`.** The script rejects `--dry-run` with `patch_all`.
3. **`approve` returns a new `patch_run_id`.** Do not track the dry-run id.
4. **No streaming.** `shell_output` appears only after terminal status (~5s poll on `GET /patching/runs/{id}`).
5. **JWT expires in 1 hour.** Stale `PATCHMON_TOKEN` → `Invalid token`; drop it and let the script re-login.
6. **Fleet-wide outdated detail:** one call to `GET /api/v1/dashboard/packages` (Bearer) — never loop per-host `outdated`. Per-host `outdated` needs Integration API Basic Auth (`PATCHMON_KEY` + `PATCHMON_SECRET`).
7. **HTTP vs HTTPS.** Supports both; for `https://`, server certs must be trusted.

**Data freshness:** Integration API reflects the last agent check-in. Stale hosts (`isStale: true`) may show 0 pending updates while the dashboard differs — use `GET /api/v1/dashboard/packages` for a current view.

## Verification

After state-changing calls, confirm with `--field` (see Output handling):

```bash
"${SKILL_DIR}/scripts/patchmon.py" --field status run "$NEW_RUN_ID"
"${SKILL_DIR}/scripts/patchmon.py" --field error_message run "$NEW_RUN_ID"
```

Expect `status: completed`. On `failed`, read `error_message` and `shell_output`.

**Dashboard screenshot (optional):** `browser_navigate` to `${PATCHMON_URL}`, `browser_snapshot` for refs, `browser_type` username/password, `browser_click` sign-in, `browser_wait_for` network idle, then capture via `browser_get_images` or describe the page.

## Notes

- Stdlib-only Python — no `pip install` for the API client.
- Credentials via `PATCHMON_*` env vars or CLI overrides (see frontmatter).
- JWT cache: `${XDG_CACHE_HOME:-$HOME/.cache}/patchmon/token` (dir `0700`, file `0600`). Override with `--token` or `PATCHMON_TOKEN`.
- All paths use `${HERMES_SKILL_DIR}`; never hardcode or search the filesystem.
- Progressive disclosure: `references/endpoints.md`, `references/discrepancies.md`, `references/output-format.md`.