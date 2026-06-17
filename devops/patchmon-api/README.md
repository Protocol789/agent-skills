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

## License

MIT. See [`../../LICENSE`](../../LICENSE) at the repo root.
