#!/bin/sh
# Exit statuses:
#   0  The recorded worker pane was verified and closed.
#   2  Unexpected arguments.
#   3  The command is not running inside its recorded lead pane.
#   4  The active run or worker-pane ownership receipt is absent or invalid.
#   5  The recorded worker resolves to a different live pane or is not live.
#   6  The receipt names the caller or lead as the worker pane; close refused.
#   7  Herdr refused to close the verified worker pane.

set -u

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: worker-stop.sh' >&2
  exit 2
fi

if [ "${HERDR_ENV:-}" != 1 ] || [ -z "${HERDR_PANE_ID:-}" ]; then
  printf '%s\n' 'worker-stop.sh must run inside a Herdr pane' >&2
  exit 3
fi

caller_cwd=$(python3 -c 'import os; print(os.getcwd())') || exit 4
receipt_json=$(python3 -c '
from pathlib import Path
import json, re, sys

cwd = Path(sys.argv[1])
current = cwd / ".crew" / ".current"
run_id = current.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
    raise SystemExit("invalid .crew/.current")
receipt = cwd / ".crew" / run_id / "worker-pane.json"
data = json.loads(receipt.read_text(encoding="utf-8"))
required = ("lead_pane_id", "worker_pane_id", "worker_name", "worker_kind")
if data.get("version") != 1 or any(not isinstance(data.get(key), str) or not data[key] for key in required):
    raise SystemExit(f"invalid worker ownership receipt: {receipt}")
data["receipt_path"] = str(receipt)
print(json.dumps(data, sort_keys=True))
' "$caller_cwd") || exit 4

receipt_field() {
  python3 -c '
import json, sys
print(json.loads(sys.argv[1])[sys.argv[2]])
' "$receipt_json" "$1"
}

lead_pane_id=$(receipt_field lead_pane_id) || exit 4
worker_pane_id=$(receipt_field worker_pane_id) || exit 4
worker_name=$(receipt_field worker_name) || exit 4
receipt_path=$(receipt_field receipt_path) || exit 4

if [ "$HERDR_PANE_ID" != "$lead_pane_id" ]; then
  printf 'caller_pane_id=%s\n' "$HERDR_PANE_ID"
  printf 'recorded_lead_pane_id=%s\n' "$lead_pane_id"
  printf '%s\n' 'outcome=refused:not-recorded-lead'
  exit 3
fi

if [ "$worker_pane_id" = "$HERDR_PANE_ID" ] || [ "$worker_pane_id" = "$lead_pane_id" ]; then
  printf 'caller_pane_id=%s\n' "$HERDR_PANE_ID"
  printf 'recorded_worker_pane_id=%s\n' "$worker_pane_id"
  printf '%s\n' 'outcome=refused:caller-or-lead-target'
  exit 6
fi

worker_json=$(herdr agent get "$worker_name") || exit 5
live_worker_pane_id=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["result"]["agent"]["pane_id"])
' "$worker_json") || exit 5

if [ "$live_worker_pane_id" != "$worker_pane_id" ]; then
  printf 'recorded_worker_pane_id=%s\n' "$worker_pane_id"
  printf 'live_worker_pane_id=%s\n' "$live_worker_pane_id"
  printf '%s\n' 'outcome=refused:worker-pane-mismatch'
  exit 5
fi

if ! herdr pane close "$worker_pane_id" >/dev/null; then
  exit 7
fi

printf 'closed_pane_id=%s\n' "$worker_pane_id"
printf 'worker_name=%s\n' "$worker_name"
printf 'ownership_receipt=%s\n' "$receipt_path"
