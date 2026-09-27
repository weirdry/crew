#!/bin/sh
# Route partner operations to the receipt's explicit session; never use UI focus.
exec python3 -I -B "$(dirname "$0")/partner-command.py" "$@"
