---
name: upload-to-microbin
description: Upload files or text snippets to a self-hosted MicroBin instance
version: 1.0.0
author: Daniel
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [paste, microbin, upload, productivity]
    related_skills: []
required_environment_variables:
  - name: MICROBIN_URL
    prompt: "Base URL of your MicroBin instance (e.g. https://paste.example.com)"
    help: "The root URL of the MicroBin server (without trailing /upload)"
    required_for: "All uploads"
---

# Upload to MicroBin

Upload files and text to a self-hosted MicroBin pastebin. Uses a small bundled helper script. No authentication required.

## When to Use

- Quick text pastes from terminal or scripts
- Sharing log snippets, config, or small files
- Piping command output directly to a shareable URL
- Uploading single files or tarballs of directories

## Quick Usage

```bash
# Text
MICROBIN_URL=https://paste.example.com microbin-upload.sh --text "hello world"

# From stdin
echo "some log" | MICROBIN_URL=https://paste.example.com microbin-upload.sh -

# File(s)
MICROBIN_URL=https://paste.example.com microbin-upload.sh file1.txt file2.log

# Directory (tar first)
tar czf /tmp/dir.tar.gz mydir/ && MICROBIN_URL=... microbin-upload.sh /tmp/dir.tar.gz
```

The script is installed as `microbin-upload.sh` when the skill is active.

## Raw curl (no script)

```bash
# Text
curl -s -X POST "${MICROBIN_URL}/upload" \
  -F "content=hello how are you?" \
  -F "expiration=1week" \
  -D - -o /dev/null | grep -i "^location:" | awk '{print $2}' | tr -d '\r'

# File
curl -s -X POST "${MICROBIN_URL}/upload" \
  -F "file=@/path/to/file.txt" \
  -F "expiration=1week" \
  -D - -o /dev/null | grep -i "^location:" | awk '{print $2}' | tr -d '\r'
```

## Notes

- Response is a 302 redirect; the `Location` header contains the final paste URL.
- Supported expiration values: `1day`, `1week`, `1month`, `never`.
- Client-side encryption is browser-only; curl uploads are plaintext.