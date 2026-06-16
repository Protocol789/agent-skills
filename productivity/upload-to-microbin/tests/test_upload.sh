#!/usr/bin/env bash
set -euo pipefail

# Basic structure + script check
SCRIPT="../scripts/microbin-upload.sh"

if [[ ! -x "$SCRIPT" ]]; then
    echo "❌ Script not executable: $SCRIPT"
    exit 1
fi

if ! grep -q 'MICROBIN_URL' "$SCRIPT"; then
    echo "❌ Script does not check MICROBIN_URL"
    exit 1
fi

echo "✅ upload-to-microbin basic checks passed"
