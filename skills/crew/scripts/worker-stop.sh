#!/bin/sh
# Exit statuses:
#   0  The recorded partner pane was verified and closed, and its receipt was removed.
#   2  Unexpected arguments.
#   3  The command is not running inside its recorded lead pane.
#   4  The workspace partner ownership receipt is absent or invalid.
#   5  The recorded partner resolves to a different live pane or is not live.
#   6  The receipt names the caller or lead as the worker pane; close refused.
#   7  Herdr refused to close the verified partner pane.
#   8  The verified partner receipt could not be removed after the pane closed.
#   9  The external state root was invalid or unusable.

set -u

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: worker-stop.sh' >&2
  exit 2
fi

if [ "${HERDR_ENV:-}" != 1 ] || [ -z "${HERDR_PANE_ID:-}" ]; then
  printf '%s\n' 'worker-stop.sh must run inside a Herdr pane' >&2
  exit 3
fi

script_dir=${0%/*}
if [ "$script_dir" = "$0" ]; then
  script_dir=.
fi
state_json=$("$script_dir/state-root.sh") || exit 9
state_root=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["state_root"])' "$state_json") || exit 9
receipt_json=$(python3 -c '
from pathlib import Path
import json, os, re, sys

receipt = Path(sys.argv[1]) / "worker.json"
if not os.path.lexists(receipt) or receipt.is_symlink():
    raise SystemExit(f"partner ownership receipt is absent or unsafe: {receipt}")
data = json.loads(receipt.read_text(encoding="utf-8"))
required = ("lead_pane_id", "worker_pane_id", "worker_name", "worker_kind")
if (
    not isinstance(data, dict)
    or data.get("version") != 1
    or any(not isinstance(data.get(key), str) or not data[key] for key in required)
    or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", data["worker_name"])
):
    raise SystemExit(f"invalid partner ownership receipt: {receipt}")
data["receipt_path"] = str(receipt)
print(json.dumps(data, sort_keys=True))
' "$state_root") || exit 4

receipt_field() {
  python3 -c '
import json, sys
print(json.loads(sys.argv[1])[sys.argv[2]])
' "$receipt_json" "$1"
}

lead_pane_id=$(receipt_field lead_pane_id) || exit 4
worker_pane_id=$(receipt_field worker_pane_id) || exit 4
worker_name=$(receipt_field worker_name) || exit 4
worker_kind=$(receipt_field worker_kind) || exit 4
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
live_worker_json=$(python3 -c '
import json, sys
agent = json.loads(sys.argv[1])["result"]["agent"]
print(json.dumps({"pane_id": agent["pane_id"], "kind": agent["agent"]}, sort_keys=True))
' "$worker_json") || exit 5
live_worker_pane_id=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["pane_id"])' "$live_worker_json") || exit 5
live_worker_kind=$(python3 -c 'import json, sys; print(json.loads(sys.argv[1])["kind"])' "$live_worker_json") || exit 5

if [ "$live_worker_pane_id" != "$worker_pane_id" ] || [ "$live_worker_kind" != "$worker_kind" ]; then
  printf 'recorded_worker_pane_id=%s\n' "$worker_pane_id"
  printf 'live_worker_pane_id=%s\n' "$live_worker_pane_id"
  printf 'recorded_worker_kind=%s\n' "$worker_kind"
  printf 'live_worker_kind=%s\n' "$live_worker_kind"
  printf '%s\n' 'outcome=refused:worker-identity-mismatch'
  exit 5
fi

if ! python3 -c '
from pathlib import Path
import json, sys

expected = json.loads(sys.argv[2])
expected.pop("receipt_path", None)
current = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
raise SystemExit(0 if current == expected else 1)
' "$receipt_path" "$receipt_json"; then
  printf '%s\n' 'outcome=refused:receipt-changed-before-close'
  exit 5
fi

worker_json=$(herdr agent get "$worker_name") || exit 5
if ! python3 -c '
import json, sys
agent = json.loads(sys.argv[1])["result"]["agent"]
raise SystemExit(0 if agent.get("pane_id") == sys.argv[2] and agent.get("agent") == sys.argv[3] else 1)
' "$worker_json" "$worker_pane_id" "$worker_kind"; then
  printf '%s\n' 'outcome=refused:worker-changed-before-close'
  exit 5
fi

if ! herdr pane close "$worker_pane_id" >/dev/null; then
  exit 7
fi

if ! python3 -c '
from pathlib import Path
import json, sys

path = Path(sys.argv[1])
expected = json.loads(sys.argv[2])
expected.pop("receipt_path", None)
current = json.loads(path.read_text(encoding="utf-8"))
if current != expected:
    raise SystemExit("partner receipt changed before removal")
path.unlink()
' "$receipt_path" "$receipt_json"; then
  exit 8
fi

printf 'closed_pane_id=%s\n' "$worker_pane_id"
printf 'worker_name=%s\n' "$worker_name"
printf 'removed_receipt=%s\n' "$receipt_path"
