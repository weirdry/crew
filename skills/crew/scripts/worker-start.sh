#!/bin/sh
# Exit statuses:
#   0  The workspace partner was attached or created; its identity and receipt action are printed.
#   2  Wrong arguments or an invalid worker kind.
#   3  Herdr caller context, the active run, or pane geometry could not be resolved.
#   4  The sibling pane could not be created.
#   5  The target pane did not reach a shell prompt; a newly split pane was closed.
#   6  The agent could not be started; a newly split pane was closed.
#   7  A documented composer marker did not appear; a newly split pane was closed.
#   8  Cleanup failed after a post-split error; pane_id is printed for manual cleanup.
#   9  The workspace partner receipt could not be written; a newly split pane was closed.
#  10  The recorded partner, lead, or pane state could not be verified safely.
#  11  Another live lead owns the recorded partner; attachment was refused.
#  12  The retained or requested partner kind matches the caller's kind; Crew was refused.
#  13  --create was requested while the recorded partner was live; creation was refused.
#  14  The requested worker kind does not match the recorded partner kind.

set -u

create_only=no
if [ "${1-}" = --create ]; then
  create_only=yes
  shift
fi

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: worker-start.sh [--create] <kind>' >&2
  exit 2
fi

worker_kind=$1
if ! python3 -c '
import re, sys
raise SystemExit(0 if re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", sys.argv[1]) else 1)
' "$worker_kind"; then
  printf 'invalid_worker_kind=%s\n' "$worker_kind" >&2
  exit 2
fi

if [ "${HERDR_ENV:-}" != 1 ] || [ -z "${HERDR_PANE_ID:-}" ]; then
  printf '%s\n' 'worker-start.sh must run inside a Herdr pane' >&2
  exit 3
fi

caller_cwd=$(python3 -c 'from pathlib import Path; print(Path.cwd().resolve())') || exit 3
workspace_json=$(python3 -c '
from pathlib import Path
import hashlib, json, re, sys

cwd = Path(sys.argv[1])
current = cwd / ".crew" / ".current"
try:
    lines = current.read_text(encoding="utf-8").splitlines()
except (OSError, UnicodeError) as error:
    raise SystemExit(f"cannot read active run: {error}")
if len(lines) != 1 or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", lines[0]):
    raise SystemExit("invalid .crew/.current")
run_dir = cwd / ".crew" / lines[0]
if not run_dir.is_dir():
    raise SystemExit(f"active run directory does not exist: {run_dir}")
workspace = re.sub(r"[^a-z0-9]+", "-", cwd.name.lower()).strip("-") or "workspace"
workspace = workspace[:14].rstrip("-_") or "workspace"
digest = hashlib.sha256(str(cwd).encode("utf-8")).hexdigest()[:12]
print(json.dumps({
    "derived_name": f"crew-{workspace}-{digest}",
    "receipt_path": str(cwd / ".crew" / "worker.json"),
}, sort_keys=True))
' "$caller_cwd") || exit 3

json_field() {
  python3 -c '
import json, sys
value = json.loads(sys.argv[1])
for key in sys.argv[2].split("."):
    value = value[key]
print(json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value)
' "$1" "$2"
}

derived_name=$(json_field "$workspace_json" derived_name) || exit 3
receipt_path=$(json_field "$workspace_json" receipt_path) || exit 3

agents_json=$(herdr agent list) || exit 3
lead_kind=$(python3 -c '
import json, sys
agents = json.loads(sys.argv[1])["result"]["agents"]
matches = [item.get("agent") for item in agents if item.get("pane_id") == sys.argv[2]]
if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
    raise SystemExit("cannot resolve caller agent kind")
print(matches[0])
' "$agents_json" "$HERDR_PANE_ID") || exit 3

receipt_json=$(python3 -c '
from pathlib import Path
import json, os, re, sys

path = Path(sys.argv[1])
if not os.path.lexists(path):
    print(json.dumps({"present": False}))
    raise SystemExit(0)
if path.is_symlink():
    raise SystemExit(f"refusing symlinked partner receipt: {path}")
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except (OSError, UnicodeError, json.JSONDecodeError) as error:
    raise SystemExit(f"invalid partner receipt {path}: {error}")
required = ("lead_pane_id", "worker_pane_id", "worker_name", "worker_kind")
if (
    not isinstance(data, dict)
    or data.get("version") != 1
    or any(not isinstance(data.get(key), str) or not data[key] for key in required)
    or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", data["worker_name"])
):
    raise SystemExit(f"invalid partner receipt: {path}")
print(json.dumps({"present": True, "receipt": data}, sort_keys=True))
' "$receipt_path") || exit 10

receipt_present=$(json_field "$receipt_json" present) || exit 10
recorded_receipt=
worker_name=$derived_name
recorded_pane_id=
recorded_lead_pane_id=

if [ "$receipt_present" = True ]; then
  recorded_receipt=$(json_field "$receipt_json" receipt) || exit 10
  worker_name=$(json_field "$recorded_receipt" worker_name) || exit 10
  recorded_pane_id=$(json_field "$recorded_receipt" worker_pane_id) || exit 10
  recorded_lead_pane_id=$(json_field "$recorded_receipt" lead_pane_id) || exit 10
  recorded_kind=$(json_field "$recorded_receipt" worker_kind) || exit 10
  if [ "$worker_kind" != "$recorded_kind" ]; then
    printf 'requested_worker_kind=%s\n' "$worker_kind" >&2
    printf 'recorded_worker_kind=%s\n' "$recorded_kind" >&2
    printf '%s\n' 'outcome=refused:worker-kind-mismatch' >&2
    exit 14
  fi
fi

probe_agent() {
  probe_name=$1
  probe_output=$(herdr agent get "$probe_name" 2>&1)
  probe_status=$?
  python3 -c '
import json, sys

status = int(sys.argv[1])
try:
    payload = json.loads(sys.argv[2])
except json.JSONDecodeError as error:
    raise SystemExit(f"invalid Herdr agent response: {error}")
if status == 0:
    try:
        agent = payload["result"]["agent"]
        result = {
            "state": "live",
            "name": agent["name"],
            "pane_id": agent["pane_id"],
            "kind": agent["agent"],
        }
    except (KeyError, TypeError) as error:
        raise SystemExit(f"invalid Herdr agent response: {error}")
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0)
code = payload.get("error", {}).get("code") if isinstance(payload, dict) else None
if code == "agent_not_found":
    print(json.dumps({"state": "absent"}))
    raise SystemExit(0)
detail = code or "<unknown>"
raise SystemExit(f"cannot determine agent liveness: {detail}")
' "$probe_status" "$probe_output"
}

probe_pane() {
  probe_id=$1
  probe_output=$(herdr pane get "$probe_id" 2>&1)
  probe_status=$?
  python3 -c '
import json, sys

status = int(sys.argv[1])
try:
    payload = json.loads(sys.argv[2])
except json.JSONDecodeError as error:
    raise SystemExit(f"invalid Herdr pane response: {error}")
if status == 0:
    try:
        pane_id = payload["result"]["pane"]["pane_id"]
    except (KeyError, TypeError) as error:
        raise SystemExit(f"invalid Herdr pane response: {error}")
    print(json.dumps({"state": "live", "pane_id": pane_id}, sort_keys=True))
    raise SystemExit(0)
code = payload.get("error", {}).get("code") if isinstance(payload, dict) else None
if code == "pane_not_found":
    print(json.dumps({"state": "absent"}))
    raise SystemExit(0)
detail = code or "<unknown>"
raise SystemExit(f"cannot determine pane liveness: {detail}")
' "$probe_status" "$probe_output"
}

agent_probe=$(probe_agent "$worker_name") || exit 10
agent_state=$(json_field "$agent_probe" state) || exit 10

if [ "$agent_state" = live ]; then
  live_name=$(json_field "$agent_probe" name) || exit 10
  live_pane_id=$(json_field "$agent_probe" pane_id) || exit 10
  live_kind=$(json_field "$agent_probe" kind) || exit 10
  if [ "$receipt_present" != True ] ||
     [ "$live_name" != "$worker_name" ] ||
     [ "$live_pane_id" != "$recorded_pane_id" ] ||
     [ "$live_kind" != "$worker_kind" ]; then
    printf '%s\n' 'outcome=refused:live-partner-ownership-mismatch' >&2
    exit 10
  fi
  if [ "$live_kind" = "$lead_kind" ]; then
    printf 'retained_partner_kind=%s\n' "$live_kind" >&2
    printf 'lead_kind=%s\n' "$lead_kind" >&2
    printf '%s\n' 'crew adds nothing over built-in subagents for that pair' >&2
    printf '%s\n' 'outcome=refused:same-kind' >&2
    exit 12
  fi
  if [ "$create_only" = yes ]; then
    printf 'partner_name=%s\n' "$worker_name" >&2
    printf 'pane_id=%s\n' "$live_pane_id" >&2
    printf '%s\n' 'outcome=refused:partner-live' >&2
    exit 13
  fi

  ownership=preserved
  if [ "$HERDR_PANE_ID" != "$recorded_lead_pane_id" ]; then
    lead_probe=$(probe_pane "$recorded_lead_pane_id") || exit 10
    lead_state=$(json_field "$lead_probe" state) || exit 10
    if [ "$lead_state" = live ]; then
      printf 'caller_pane_id=%s\n' "$HERDR_PANE_ID" >&2
      printf 'recorded_lead_pane_id=%s\n' "$recorded_lead_pane_id" >&2
      printf '%s\n' 'outcome=refused:recorded-lead-live' >&2
      exit 11
    fi
    if ! python3 -c '
from pathlib import Path
import json, os, sys

path = Path(sys.argv[1])
expected = json.loads(sys.argv[2])
current = json.loads(path.read_text(encoding="utf-8"))
if current != expected:
    raise SystemExit("partner receipt changed before ownership transfer")
current["lead_pane_id"] = sys.argv[3]
temporary = Path(f"{path}.{os.getpid()}.tmp")
try:
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(current, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
' "$receipt_path" "$recorded_receipt" "$HERDR_PANE_ID"; then
      exit 10
    fi
    ownership=transferred
  fi

  printf '%s\n' 'outcome=attached'
  printf 'partner_name=%s\n' "$worker_name"
  printf 'partner_kind=%s\n' "$live_kind"
  printf 'pane_id=%s\n' "$live_pane_id"
  printf 'ownership=%s\n' "$ownership"
  printf 'ownership_receipt=%s\n' "$receipt_path"
  exit 0
fi

if [ "$worker_kind" = "$lead_kind" ]; then
  printf 'requested_partner_kind=%s\n' "$worker_kind" >&2
  printf 'lead_kind=%s\n' "$lead_kind" >&2
  printf '%s\n' 'crew adds nothing over built-in subagents for that pair' >&2
  printf '%s\n' 'outcome=refused:same-kind' >&2
  exit 12
fi

if [ "$receipt_present" = True ] && [ "$HERDR_PANE_ID" != "$recorded_lead_pane_id" ]; then
  lead_probe=$(probe_pane "$recorded_lead_pane_id") || exit 10
  lead_state=$(json_field "$lead_probe" state) || exit 10
  if [ "$lead_state" = live ]; then
    printf 'caller_pane_id=%s\n' "$HERDR_PANE_ID" >&2
    printf 'recorded_lead_pane_id=%s\n' "$recorded_lead_pane_id" >&2
    printf '%s\n' 'outcome=refused:recorded-lead-live' >&2
    exit 11
  fi
fi

pane_id=
pane_source='split'
split_created=no

if [ "$receipt_present" = True ]; then
  pane_probe=$(probe_pane "$recorded_pane_id") || exit 10
  pane_state=$(json_field "$pane_probe" state) || exit 10
  if [ "$pane_state" = live ]; then
    pane_id=$recorded_pane_id
    pane_source=reused
  fi
fi

if [ -z "$pane_id" ]; then
  layout_json=$(herdr pane layout --pane "$HERDR_PANE_ID") || exit 3
  direction=$(python3 -c '
import json, sys
data = json.loads(sys.argv[1])["result"]["layout"]
pane_id = sys.argv[2]
rect = next(item["rect"] for item in data["panes"] if item["pane_id"] == pane_id)
print("right" if rect["width"] > rect["height"] else "down")
' "$layout_json" "$HERDR_PANE_ID") || exit 3
  split_json=$(herdr pane split --pane "$HERDR_PANE_ID" --direction "$direction" --cwd "$caller_cwd" --no-focus) || exit 4
  pane_id=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["result"]["pane"]["pane_id"])
' "$split_json") || exit 4
  split_created=yes
fi

cleanup_after_failure() {
  failure_status=$1
  if [ "$split_created" != yes ]; then
    exit "$failure_status"
  fi
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

path = Path(sys.argv[1])
expected = json.loads(sys.argv[2]) if sys.argv[2] else None
payload = {
    "version": 1,
    "lead_pane_id": sys.argv[3],
    "worker_pane_id": sys.argv[4],
    "worker_name": sys.argv[5],
    "worker_kind": sys.argv[6],
}
temporary = Path(f"{path}.{os.getpid()}.tmp")
try:
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    if expected is None:
        os.link(temporary, path)
    else:
        current = json.loads(path.read_text(encoding="utf-8"))
        if current != expected:
            raise SystemExit("partner receipt changed before stale replacement")
        os.replace(temporary, path)
finally:
    temporary.unlink(missing_ok=True)
' "$receipt_path" "$recorded_receipt" "$HERDR_PANE_ID" "$pane_id" "$worker_name" "$worker_kind"; then
  cleanup_after_failure 9
fi

printf '%s\n' 'outcome=created'
printf 'partner_name=%s\n' "$worker_name"
printf 'partner_kind=%s\n' "$worker_kind"
printf 'pane_id=%s\n' "$pane_id"
printf 'pane_source=%s\n' "$pane_source"
printf 'composer_wait=%s\n' "$composer_wait"
if [ "$receipt_present" = True ]; then
  printf '%s\n' 'receipt_action=replaced-stale'
else
  printf '%s\n' 'receipt_action=created'
fi
printf 'ownership_receipt=%s\n' "$receipt_path"
