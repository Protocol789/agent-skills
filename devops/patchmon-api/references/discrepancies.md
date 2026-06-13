# Discrepancies between PatchMon docs and the deployed instance

> **Stub.** The full discrepancy log has not been transcribed yet.
> The list below is what's been observed; add new entries as you
> find them.

## Observed

- **`/api/v1/patches/dry-run` and `/api/v1/jobs/{id}/stream-summary`**
  are listed in `patchmon.net/docs` but do not exist on the deployed
  instance. Use the `/api/v1/patching/trigger` endpoint with
  `dry_run: true` + `patch_type: "patch_package"` instead.

## Why this file exists

External docs are versioned against the latest release, but the
instance you point `PATCHMON_URL` at may be on an older release that
predates some endpoints — or a newer release where they were renamed.
When debugging a 404, check here first; if you find a new mismatch,
add it.
