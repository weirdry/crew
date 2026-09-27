#!/bin/sh
# File-based relay publication and read-only continuation plans. See --help.
set -u
script_dir=${0%/*}
[ "$script_dir" != "$0" ] || script_dir=.
exec python3 -I "$script_dir/relay.py" "$@"
