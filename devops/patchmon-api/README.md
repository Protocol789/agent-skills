# patchmon-api

A [Hermes Agent](https://hermes-agent.nousresearch.com) skill that
wraps the [PatchMon](https://patchmon.net) Linux patch-management API.

See [`SKILL.md`](./SKILL.md) for the full description, required
environment variables, and step-by-step procedure.

## Install

```bash
# From a git tap
hermes skills tap add <owner>/agent-skills
hermes skills install patchmon-api

# Or copy this directory into a Hermes skills/ folder:
#   ~/.hermes/skills/devops/patchmon-api/
```

## Test

The skill ships with a minimal pytest suite covering the CLI, the
hygiene constants, and the JWT cache. The client uses `httpx` for
async HTTP; install runtime and dev deps from `pyproject.toml`.

```bash
cd devops/patchmon-api
pip install -e ".[dev]"

# Run the suite
pytest tests/ -v
```

The suite runs in <1 s and touches no network. Tests that need a
live PatchMon instance (or that mock `_request`) are intentionally
left as `pytest.mark.skip` placeholders for progressive enhancement.

## Live testing

To smoke-test against a real instance (credentials from Bitwarden
Secrets Manager via `bws`):

```bash
cd devops/patchmon-api
pip install -e ".[dev]"   # once

# Default target: https://patchmon.zorab.im
./scripts/live-smoke.sh

# Or point at another instance:
PATCHMON_URL=https://patchmon.example.com ./scripts/live-smoke.sh
```

One-off CLI calls with secrets injected:

```bash
bws run --project-id aeba6904-3785-4087-891c-b45601575cab -- \
  env PATCHMON_URL=https://patchmon.zorab.im \
  python scripts/patchmon.py hosts
```

Global flags such as `--field` must come **before** the subcommand
(e.g. `patchmon.py --field hosts.0.id hosts`).

## License

MIT. See [`../../LICENSE`](../../LICENSE) at the repo root.
