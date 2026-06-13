# Endpoint catalog

> **Stub.** The full Integration and Application API catalogs have not
> been transcribed yet. The list below is what `patchmon.py` actually
> uses; everything else is TODO.

## Application API (Bearer JWT, action-capable)

| Method | Path                                          | Used by                  |
|--------|-----------------------------------------------|--------------------------|
| POST   | `/api/v1/auth/login`                          | `_login`                 |
| GET    | `/api/v1/dashboard/hosts`                     | `hosts` (fallback)       |
| GET    | `/api/v1/dashboard/packages`                  | freshness fallback note  |
| POST   | `/api/v1/patching/trigger`                    | `patch`                  |
| POST   | `/api/v1/patching/runs/{id}/approve`          | `approve`                |
| POST   | `/api/v1/patching/runs/{id}/stop`             | `stop`                   |
| GET    | `/api/v1/patching/runs/{id}`                  | `run`, `_poll`           |
| GET    | `/api/v1/patching/runs`                       | `runs`                   |
| GET    | `/api/v1/patching/runs/active`                | `runs --active`          |

## Integration API (Basic Auth, read-only)

| Method | Path                                            | Used by         |
|--------|-------------------------------------------------|-----------------|
| GET    | `/api/v1/api/hosts?include=stats`               | `hosts`         |
| GET    | `/api/v1/api/hosts/{id}/packages?updates_only=` | `outdated`      |

## TODO

Add entries for: host system / network / notes / integrations,
agent-queue, GetHomepage widget, auto-enrollment, alerts, compliance,
docker, repositories, settings. Use the deployed instance (not
`patchmon.net/docs`) as the source of truth — see
`discrepancies.md`.
