#!/bin/sh
# Exit statuses:
#   0  Keys were sent and state_change_seq advanced; sequence data is printed.
#   2  Worker or keys were omitted, or the expected approval token was invalid.
#   3  Guard refused: the worker was not blocked on the expected visible confirmation option list.
#   4  Herdr state or pane output could not be read before sending keys.
#   5  send-keys rejected the requested keys; the captured sequence is printed.
#   6  state_change_seq did not advance before timeout, and the visible frame was unchanged or
#      unreadable; sequence data is printed. Delivery is uncertain.
#   7  state_change_seq did not advance before timeout, but the visible frame changed; sequence
#      data is printed. This shows only a changed frame, not which dialog received the keys.

set -u

expected_approval_b64=
expected_approval_present=no
expected_grant_b64=
expected_grant_present=no
if [ "${1-}" = --expected-command-b64 ]; then
  if [ "$#" -lt 4 ]; then
    printf '%s\n' 'usage: answer-dialog.sh [--expected-command-b64 <token> [--expected-grant-b64 <token>]] <worker> <key>...' >&2
    exit 2
  fi
  expected_approval_b64=$2
  expected_approval_present=yes
  shift 2
fi

if [ "${1-}" = --expected-grant-b64 ]; then
  if [ "$expected_approval_present" != yes ] || [ "$#" -lt 4 ]; then
    printf '%s\n' 'usage: answer-dialog.sh [--expected-command-b64 <token> [--expected-grant-b64 <token>]] <worker> <key>...' >&2
    exit 2
  fi
  expected_grant_b64=$2
  expected_grant_present=yes
  shift 2
fi

if [ "$#" -lt 2 ]; then
  printf '%s\n' 'usage: answer-dialog.sh [--expected-command-b64 <token> [--expected-grant-b64 <token>]] <worker> <key>...' >&2
  exit 2
fi

if [ "$expected_approval_present" = yes ]; then
  if [ -z "$expected_approval_b64" ]; then
    printf '%s\n' 'invalid expected-command token' >&2
    exit 2
  fi
  if ! python3 -c '
import base64, sys
try:
    base64.b64decode(sys.argv[1].encode("ascii"), altchars=b"-_", validate=True).decode("utf-8")
except (UnicodeError, ValueError):
    raise SystemExit(1)
' "$expected_approval_b64"; then
    printf '%s\n' 'invalid expected-command token' >&2
    exit 2
  fi
fi

if [ "$expected_grant_present" = yes ]; then
  if [ -z "$expected_grant_b64" ]; then
    printf '%s\n' 'invalid expected-grant token' >&2
    exit 2
  fi
  if ! python3 -c '
import base64, sys
try:
    base64.b64decode(sys.argv[1].encode("ascii"), altchars=b"-_", validate=True).decode("utf-8")
except (UnicodeError, ValueError):
    raise SystemExit(1)
' "$expected_grant_b64"; then
    printf '%s\n' 'invalid expected-grant token' >&2
    exit 2
  fi
fi

worker=$1
shift

json_field() {
  python3 -c '
import json, sys
agent = json.loads(sys.argv[1])["result"]["agent"]
value = agent[sys.argv[2]]
print(value)
' "$1" "$2"
}

refuse() {
  printf '%s\n' 'outcome=refused'
  printf 'reason=%s\n' "$1"
  exit 3
}

# Existing v1/no-receipt invocations retain their published ambient transport.
# A controller receipt always routes through the verified, session-bound adapter.
script_dir=${0%/*}
[ "$script_dir" != "$0" ] || script_dir=.
state_json=$("$script_dir/state-root.sh") || exit 4
transport_mode=$(python3 - "$state_json" <<'PYMODE'
import json, os, sys
from pathlib import Path
path = Path(json.loads(sys.argv[1])["state_root"]) / "worker.json"
if os.path.lexists(path):
    if path.is_symlink() or not path.is_file():
        raise SystemExit("unsafe partner receipt")
    receipt = json.loads(path.read_text())
    if not isinstance(receipt, dict) or receipt.get("version") not in (1, 2):
        raise SystemExit("invalid partner receipt")
    if os.environ.get("CREW_CONTROLLER_ID") and receipt["version"] != 2:
        raise SystemExit("controller-bound receipt required")
    print("bound" if receipt["version"] == 2 else "legacy")
else:
    if os.environ.get("CREW_CONTROLLER_ID"):
        raise SystemExit("controller-bound receipt required")
    print("legacy")
PYMODE
) || exit 4
herdr() {
  if [ "$transport_mode" = bound ]; then
    "$script_dir/herdr.sh" "$@"
  else
    command herdr "$@"
  fi
}

first_json=$(herdr agent get "$worker") || exit 4
first_status=$(json_field "$first_json" agent_status) || exit 4
first_seq=$(json_field "$first_json" state_change_seq) || exit 4

if [ "$first_status" != blocked ]; then
  refuse 'agent-not-blocked'
fi

frame=$(herdr agent read "$worker" --source visible --lines 120 --format text) || exit 4
if ! printf '%s' "$frame" | python3 -c '
import re, sys

text = sys.stdin.read()
confirmation = re.search(
    r"(?im)^\s*(?:do you want to|would you like to|are you sure|"
    r"allow\b.*\?|approve\b.*\?|run\b.*\?|execute\b.*\?).*$",
    text,
)
option = re.compile(
    r"(?im)^\s*(?:[❯›>]\s*)?(?:\d+[.):]|"
    r"(?:yes|no|allow|deny|approve|cancel|continue|proceed)\b)"
)
raise SystemExit(0 if confirmation and len(option.findall(text)) >= 2 else 1)
'; then
  refuse 'no-visible-confirmation-option-list'
fi

if [ "$expected_approval_present" = yes ]; then
  approval_helper=$(dirname "$0")/approval.sh
  if [ "$expected_grant_present" = yes ]; then
    verification=$(
      "$approval_helper" check "$worker" --expect-b64 "$expected_approval_b64" \
        --grant-b64 "$expected_grant_b64"
    )
    verification_status=$?
  else
    verification=$(
      "$approval_helper" check "$worker" --expect-b64 "$expected_approval_b64"
    )
    verification_status=$?
  fi
  if [ "$verification_status" -eq 0 ]; then
    printf '%s\n' "$verification"
  else
    if [ -n "$verification" ]; then
      printf '%s\n' "$verification"
    fi
    case "$verification_status" in
      1)
        refuse 'approval-changed'
        ;;
      2)
        printf '%s\n' 'invalid expected-command token' >&2
        exit 2
        ;;
      *)
        refuse 'approval-revalidation-failed'
        ;;
    esac
  fi
fi

second_json=$(herdr agent get "$worker") || exit 4
second_status=$(json_field "$second_json" agent_status) || exit 4
pre_key_seq=$(json_field "$second_json" state_change_seq) || exit 4

if [ "$second_status" != blocked ]; then
  refuse 'agent-left-blocked-state'
fi
if [ "$pre_key_seq" != "$first_seq" ]; then
  refuse 'state-changed-during-guard'
fi

if ! herdr agent send-keys "$worker" "$@" >/dev/null; then
  printf 'pre_key_seq=%s\n' "$pre_key_seq"
  printf '%s\n' 'outcome=send-failed'
  exit 5
fi

deadline=$(python3 -c 'import time; print(time.monotonic() + 5.0)') || exit 6
last_seq=$pre_key_seq

while :; do
  current_json=$(herdr agent get "$worker" 2>/dev/null) || current_json=
  if [ -n "$current_json" ]; then
    current_seq=$(json_field "$current_json" state_change_seq 2>/dev/null) || current_seq=
    if [ -n "$current_seq" ]; then
      last_seq=$current_seq
      if [ "$current_seq" -gt "$pre_key_seq" ] 2>/dev/null; then
        printf 'pre_key_seq=%s\n' "$pre_key_seq"
        printf 'post_key_seq=%s\n' "$current_seq"
        printf '%s\n' 'outcome=advanced'
        exit 0
      fi
    fi
  fi

  expired=$(python3 -c 'import sys, time; print("yes" if time.monotonic() >= float(sys.argv[1]) else "no")' "$deadline") || expired=yes
  if [ "$expired" = yes ]; then
    printf 'pre_key_seq=%s\n' "$pre_key_seq"
    printf 'post_key_seq=%s\n' "$last_seq"
    # One final read with the guard's arguments; the keys are never sent again.
    if final_frame=$(
      herdr agent read "$worker" --source visible --lines 120 --format text 2>/dev/null
    ) && [ "$final_frame" != "$frame" ]; then
      printf '%s\n' 'outcome=visible-changed'
      exit 7
    fi
    printf '%s\n' 'outcome=timeout'
    exit 6
  fi
  python3 -c 'import time; time.sleep(0.2)'
done
