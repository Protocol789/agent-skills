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

## License

MIT. See [`../../LICENSE`](../../LICENSE) at the repo root.
