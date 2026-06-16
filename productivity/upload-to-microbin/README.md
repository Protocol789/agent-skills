# upload-to-microbin

A [Hermes Agent](https://hermes-agent.nousresearch.com) skill for uploading text and files to a self-hosted [MicroBin](https://github.com/kanthaus/microbin) instance.

See [`SKILL.md`](./SKILL.md) for usage, environment variables, and raw curl examples.

## Install

```bash
# Via tap
hermes skills tap add Protocol789/agent-skills
hermes skills install upload-to-microbin

# Or manually copy into ~/.hermes/skills/productivity/upload-to-microbin/
```

## Test

```bash
MICROBIN_URL=https://your-instance.com ./scripts/microbin-upload.sh --text "test"
```