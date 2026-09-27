#!/bin/sh
# Explicit retirement only. Completion never invokes this helper.
exec python3 -B "$(dirname "$0")/partner.py" stop "$@"
