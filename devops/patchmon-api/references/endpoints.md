# Endpoint & command catalog

> Use this for drill-down after `status`. Do not call `--help`; everything
> the agent needs is here.

## CLI subcommands

| Subcommand | Purpose | Auth |
|------------|---------|------|
| `status` | Pending hosts + active runs in one JSON object | Bearer and/or Integration |
| `hosts` | List hosts with stats; `--pending`, `--needs-reboot`, `--hostgroup` | Integration preferred, Bearer fallback |
| `runs` | List patch runs; `--active` for in-flight only | Bearer |
| `run RUN_ID` | Single run detail (`shell_output`, `error_message`) | Bearer |
| `outdated HOST_ID` | Packages with updates for one host | Integration (Basic) |
| `patch HOST_ID` | Trigger patch; `--packages`, `--dry-run`, `--no-wait` | Bearer |
| `approve RUN_ID` | Approve validated dry-run; `--no-wait` | Bearer |
| `stop RUN_ID` | Cancel queued or running patch | Bearer |
| `login` | Mint a fresh JWT | Username/password |

Global flags (before subcommand): `--field PATH`, `--base-url`, `--token`, `--username`, `--password`.

### Examples

```bash
SKILL_DIR="${HERMES_SKILL_DIR}"

# Drill-down (only when user names a host or run)
"${SKILL_DIR}/scripts/patchmon.py" hosts --hostgroup production
"${SKILL_DIR}/scripts/patchmon.py" --field status run "$RUN_ID"
"${SKILL_DIR}/scripts/patchmon.py" run "$RUN_ID"
"${SKILL_DIR}/scripts/patchmon.py" outdated "$HOST_ID"
"${SKILL_DIR}/scripts/patchmon.py" stop "$RUN_ID"
```

### Fleet-wide outdated packages

Do **not** loop `outdated` per host. With Bearer credentials, one call returns all outdated packages grouped by host:

`GET /api/v1/dashboard/packages`

## Application API (Bearer JWT, action-capable)

| Method | Path | Used by |
|--------|------|---------|
| POST | `/api/v1/auth/login` | `login` |
| GET | `/api/v1/dashboard/hosts` | `hosts` (fallback) |
| GET | `/api/v1/dashboard/packages` | fleet-wide outdated (Bearer) |
| POST | `/api/v1/patching/trigger` | `patch` |
| POST | `/api/v1/patching/runs/{id}/approve` | `approve` |
| POST | `/api/v1/patching/runs/{id}/stop` | `stop` |
| GET | `/api/v1/patching/runs/{id}` | `run`, `_poll` |
| GET | `/api/v1/patching/runs` | `runs` |
| GET | `/api/v1/patching/runs/active` | `runs --active`, `status` |

## Integration API (Basic Auth, read-only)

| Method | Path | Used by |
|--------|------|---------|
| GET | `/api/v1/api/hosts?include=stats` | `hosts`, `status` |
| GET | `/api/v1/api/hosts/{id}/packages?updates_only=` | `outdated` |

## TODO

Add entries for: host system / network / notes / integrations,
agent-queue, GetHomepage widget, auto-enrollment, alerts, compliance,
docker, repositories, settings. Use the deployed instance (not
`patchmon.net/docs`) as the source of truth — see `discrepancies.md`.