#!/usr/bin/env bash
set -euo pipefail
printf 'fake uv invoked with args: %s\n' "$*" >&2
# emulate successful run with no output
exit 0
