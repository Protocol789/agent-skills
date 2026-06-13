# agent-skills

A small, centralized collection of [Hermes Agent](https://hermes-agent.nousresearch.com)
skills — version-controlled, portable, and free of any
environment-specific credentials. Each skill is a self-contained
directory under `devops/<category>/<skill-name>/` with a `SKILL.md`
following the Hermes skill-authoring guide.

## Install as a Hermes skills tap

```bash
# Add this repo as a tap
hermes skills tap add <owner>/agent-skills

# Install a specific skill
hermes skills install patchmon-api
```

Or copy a single skill directory into `~/.hermes/skills/devops/`.

## Contents

```
.
├── LICENSE
├── README.md
├── .gitignore
└── devops/
    └── patchmon-api/
        ├── SKILL.md
        ├── README.md
        ├── references/
        │   ├── endpoints.md
        │   └── discrepancies.md
        └── scripts/
            ├── patchmon.py
            └── screenshot.js
```

### `devops/patchmon-api/`

A skill for an LLM agent to operate a [PatchMon](https://patchmon.net)
instance — list managed Linux hosts, inspect outdated packages, trigger
patch runs (full or per-package), approve validated dry-runs, and poll to
terminal status. The bundled `patchmon.py` wraps PatchMon's Application
and Integration APIs in a CLI designed for non-interactive invocation.

`screenshot.js` provides a Playwright-based dashboard screenshot helper
when a visual confirmation is requested (text-mode browser tools cannot
capture images).

See `devops/patchmon-api/SKILL.md` for full usage, the two-tier auth
model, polling semantics, and known API gotchas. The skill declares
its required environment variables in the `SKILL.md` frontmatter —
Hermes will prompt for missing values when the skill is loaded.

## Prerequisites

- **Python 3.8+** for `patchmon.py` (no third-party dependencies; uses
  the standard library only).
- **Node.js + Playwright** for `screenshot.js`. Install on first use:
  ```bash
  cd devops/patchmon-api
  npm install playwright
  npx playwright install chromium
  ```

## Configuration

The skill reads credentials from environment variables — **never from
files in this repository**. Set these before invoking the scripts:

| Variable             | Purpose                                                  |
|----------------------|----------------------------------------------------------|
| `PATCHMON_URL`       | Base URL of your PatchMon instance.                      |
| `PATCHMON_USERNAME`  | Account username (for action-capable Bearer auth).       |
| `PATCHMON_PASSWORD`  | Account password.                                        |
| `PATCHMON_KEY`       | Integration API key (read-only, Basic Auth).             |
| `PATCHMON_SECRET`    | Integration API secret (paired with `PATCHMON_KEY`).     |
| `PATCHMON_TOKEN`     | Optional: pre-minted JWT. Skips login if set.            |

`patchmon.py` caches a freshly-minted JWT at
`${XDG_CACHE_HOME:-$HOME/.cache}/patchmon/token` (mode 0600; parent
directory mode 0700) so repeated invocations within an hour don't
re-authenticate. Pass `--token` to bypass the cache.

## License

MIT. See `LICENSE`.
