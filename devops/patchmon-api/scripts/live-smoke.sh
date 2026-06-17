#!/usr/bin/env bash
# Live smoke test against a PatchMon instance using Bitwarden Secrets Manager.
#
# Requires: bws CLI, BWS_ACCESS_TOKEN, and secrets PATCHMON_USERNAME,
# PATCHMON_PASSWORD, PATCHMON_KEY, PATCHMON_SECRET in the BWS project below.
#
# Usage:
#   ./scripts/live-smoke.sh
#   PATCHMON_URL=https://patchmon.example.com ./scripts/live-smoke.sh
#
# Override the BWS project if your secrets live elsewhere:
#   BWS_PROJECT_ID=<uuid> ./scripts/live-smoke.sh

set -euo pipefail

SKILL_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PATCHMON_URL="${PATCHMON_URL:-https://patchmon.zorab.im}"
BWS_PROJECT_ID="${BWS_PROJECT_ID:-aeba6904-3785-4087-891c-b45601575cab}"
PYTHON="${PYTHON:-$SKILL_ROOT/.venv/bin/python}"
CLI="$SKILL_ROOT/scripts/patchmon.py"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

if ! command -v bws >/dev/null 2>&1; then
  echo "error: bws CLI not found (install Bitwarden Secrets CLI)" >&2
  exit 1
fi

run_cli() {
  bws run --project-id "$BWS_PROJECT_ID" -- \
    env PATCHMON_URL="$PATCHMON_URL" "$PYTHON" "$CLI" "$@"
}

echo "==> PATCHMON_URL=$PATCHMON_URL"
echo "==> login"
run_cli login | "$PYTHON" -c "import json,sys; d=json.load(sys.stdin); print('  token chars:', len(d.get('token','')))"

echo "==> hosts"
HOSTS_JSON="$(run_cli hosts)"
HOST_COUNT="$("$PYTHON" -c "import json,sys; d=json.load(sys.stdin); h=d.get('hosts',d if isinstance(d,list) else []); print(len(h))" <<<"$HOSTS_JSON")"
echo "  hosts: $HOST_COUNT"
FIRST_HOST_ID="$("$PYTHON" -c "import json,sys; d=json.load(sys.stdin); h=d.get('hosts',[]); print(h[0]['id'] if h else '')" <<<"$HOSTS_JSON")"
FIRST_HOST_NAME="$("$PYTHON" -c "import json,sys; d=json.load(sys.stdin); h=d.get('hosts',[]); print(h[0].get('friendly_name') or h[0].get('hostname','') if h else '')" <<<"$HOSTS_JSON")"
if [[ -n "$FIRST_HOST_NAME" ]]; then
  echo "  first host: $FIRST_HOST_NAME ($FIRST_HOST_ID)"
fi

echo "==> runs --active"
run_cli runs --active | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin)
runs=d.get('runs', d if isinstance(d,list) else [])
print('  active runs:', len(runs))
for r in runs[:3]:
    print('   -', r.get('id','?'), 'status='+str(r.get('status','?')))
"

if [[ -n "$FIRST_HOST_ID" ]]; then
  echo "==> outdated $FIRST_HOST_NAME"
  run_cli outdated "$FIRST_HOST_ID" | "$PYTHON" -c "
import json,sys
d=json.load(sys.stdin)
pkgs=d.get('packages', d if isinstance(d,list) else [])
print('  packages with updates:', len(pkgs) if isinstance(pkgs,list) else 'n/a')
"
fi

echo "==> --field hosts.0.friendly_name"
run_cli --field hosts.0.friendly_name hosts

echo "==> live smoke passed"