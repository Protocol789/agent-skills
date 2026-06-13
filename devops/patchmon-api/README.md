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
hygiene constants, and the JWT cache. The script itself stays
stdlib-only; `pytest` is a dev-only dependency.

```bash
# One-time: install pytest (system package or pipx, your call)
pip install --user pytest

# Run the suite
cd devops/patchmon-api
pytest tests/ -v
```

The suite runs in <1 s and touches no network. Tests that need a
live PatchMon instance (or that mock `_request`) are intentionally
left as `pytest.mark.skip` placeholders for progressive enhancement.

## License

MIT. See [`../../LICENSE`](../../LICENSE) at the repo root.
