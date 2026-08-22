#!/bin/sh
# Exit statuses:
#   0  The file exists and its last line is exactly STATUS: done.
#   1  The file is absent or its last line is not exactly STATUS: done.
#   2  Wrong argument count.

set -u

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: artifact-done.sh <path>' >&2
  exit 2
fi

python3 -c '
from pathlib import Path
import sys

path = Path(sys.argv[1])
try:
    content = path.read_bytes()
except (OSError, ValueError):
    raise SystemExit(1)

if content.endswith(b"\n"):
    content = content[:-1]
last_line = content.rsplit(b"\n", 1)[-1]
raise SystemExit(0 if last_line == b"STATUS: done" else 1)
' "$1"
