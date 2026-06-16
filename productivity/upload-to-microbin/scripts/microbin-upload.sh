#!/usr/bin/env bash
# Upload files or text to a MicroBin instance
# Usage:
#   microbin-upload.sh <file1> [file2] ...
#   echo "text" | microbin-upload.sh -
#   microbin-upload.sh --text "Your text goes here"

set -euo pipefail

if [[ -n "${MICROBIN_URL:-}" ]]; then
    URL="${MICROBIN_URL%/}/upload"
else
    echo "❌ MICROBIN_URL is not set"
    exit 1
fi

upload_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "❌ Not found: $file"
        return 1
    fi

    echo "📤 Uploading file: $file ..."
    local location
    location=$(curl -s -X POST "$URL" \
        -F "file=@$file" \
        -F "expiration=1week" \
        -D - -o /dev/null | grep -i "^location:" | awk '{print $2}' | tr -d '\r')

    if [[ -n "$location" ]]; then
        echo "✅ $location"
    else
        echo "❌ Upload failed for: $file"
        return 1
    fi
}

upload_text() {
    local text="$1"
    echo "📤 Uploading text ..."
    local location
    location=$(curl -s -X POST "$URL" \
        -F "content=$text" \
        -F "expiration=1week" \
        -D - -o /dev/null | grep -i "^location:" | awk '{print $2}' | tr -d '\r')

    if [[ -n "$location" ]]; then
        echo "✅ $location"
    else
        echo "❌ Text upload failed"
        return 1
    fi
}

if [[ "${1:-}" == "--text" ]]; then
    shift
    upload_text "$*"
elif [[ "${1:-}" == "-" ]]; then
    text=$(cat)
    upload_text "$text"
else
    for file in "$@"; do
        upload_file "$file"
    done
fi
