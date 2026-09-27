#!/bin/sh
# Controller-bound partner start/attach. See references/execution.md.
exec python3 -I -B "$(dirname "$0")/partner.py" start "$@"
