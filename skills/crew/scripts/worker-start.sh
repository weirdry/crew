#!/bin/sh
# Exit statuses:
#   0  Worker started; pane_id, composer_wait, and ownership_receipt are printed.
#   2  Wrong argument count.
#   3  Herdr caller context or pane geometry could not be resolved.
#   4  The sibling pane could not be created.
#   5  The new pane did not reach a shell prompt; it was closed.
#   6  The agent could not be started; the new pane was closed.
#   7  A documented composer marker did not appear; the new pane was closed.
#   8  Cleanup failed after a post-split error; pane_id is printed for manual cleanup.
#   9  The run-owned pane receipt could not be written; the new pane was closed.

set -u

if [ "$#" -ne 2 ]; then
  printf '%s\n' 'usage: worker-start.sh <name> <kind>' >&2
  exit 2
fi

worker_name=$1
worker_kind=$2

if [ "${HERDR_ENV:-}" != 1 ] || [ -z "${HERDR_PANE_ID:-}" ]; then
  printf '%s\n' 'worker-start.sh must run inside a Herdr pane' >&2
  exit 3
fi

layout_json=$(herdr pane layout --pane "$HERDR_PANE_ID") || exit 3
direction=$(python3 -c '
import json, sys
data = json.loads(sys.argv[1])["result"]["layout"]
pane_id = sys.argv[2]
rect = next(item["rect"] for item in data["panes"] if item["pane_id"] == pane_id)
print("right" if rect["width"] > rect["height"] else "down")
' "$layout_json" "$HERDR_PANE_ID") || exit 3
caller_cwd=$(python3 -c 'import os; print(os.getcwd())') || exit 3
receipt_path=$(python3 -c '
from pathlib import Path
import re, sys

cwd = Path(sys.argv[1])
current = cwd / ".crew" / ".current"
run_id = current.read_text(encoding="utf-8").strip()
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
    raise SystemExit("invalid .crew/.current")
run_dir = cwd / ".crew" / run_id
if not run_dir.is_dir():
    raise SystemExit(f"active run directory does not exist: {run_dir}")
receipt = run_dir / "worker-pane.json"
if receipt.exists():
    raise SystemExit(f"worker pane already recorded: {receipt}")
print(receipt)
' "$caller_cwd") || exit 3

split_json=$(herdr pane split --pane "$HERDR_PANE_ID" --direction "$direction" --cwd "$caller_cwd" --no-focus) || exit 4
pane_id=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["result"]["pane"]["pane_id"])
' "$split_json") || exit 4

cleanup_after_failure() {
  failure_status=$1
  if herdr pane close "$pane_id" >/dev/null 2>&1; then
    exit "$failure_status"
  fi
  printf 'pane_id=%s\n' "$pane_id"
  printf '%s\n' 'cleanup=failed'
  exit 8
}

if ! herdr pane wait-output "$pane_id" --regex '[#$%>❯] ?$' --source detection --lines 5 --timeout 60000 >/dev/null; then
  cleanup_after_failure 5
fi

if ! herdr agent start "$worker_name" --kind "$worker_kind" --pane "$pane_id" --timeout 60000 >/dev/null; then
  cleanup_after_failure 6
fi

case "$worker_kind" in
  codex)
    marker='Ask Codex'
    composer_wait=matched
    ;;
  claude)
    marker='Try "'
    composer_wait=matched
    ;;
  *)
    marker=
    composer_wait='skipped:no-documented-marker'
    ;;
esac

if [ -n "$marker" ]; then
  if ! herdr pane wait-output "$pane_id" --regex "$marker" --source visible --timeout 60000 >/dev/null; then
    cleanup_after_failure 7
  fi
fi

if ! python3 -c '
from pathlib import Path
import json, os, sys

receipt = Path(sys.argv[1])
temporary = Path(f"{receipt}.{os.getpid()}.tmp")
payload = {
    "version": 1,
    "lead_pane_id": sys.argv[2],
    "worker_pane_id": sys.argv[3],
    "worker_name": sys.argv[4],
    "worker_kind": sys.argv[5],
}
try:
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
    os.link(temporary, receipt)
finally:
    temporary.unlink(missing_ok=True)
' "$receipt_path" "$HERDR_PANE_ID" "$pane_id" "$worker_name" "$worker_kind"; then
  cleanup_after_failure 9
fi

printf 'pane_id=%s\n' "$pane_id"
printf 'composer_wait=%s\n' "$composer_wait"
printf 'ownership_receipt=%s\n' "$receipt_path"
