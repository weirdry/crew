#!/bin/sh
# Exit statuses:
#   0  Keys were sent and state_change_seq advanced; sequence data is printed.
#   2  Worker or keys were omitted.
#   3  Guard refused: the worker was not blocked on a visible confirmation option list.
#   4  Herdr state or pane output could not be read before sending keys.
#   5  send-keys rejected the requested keys; the captured sequence is printed.
#   6  state_change_seq did not advance before timeout; sequence data is printed.

set -u

if [ "$#" -lt 2 ]; then
  printf '%s\n' 'usage: answer-dialog.sh <worker> <key>...' >&2
  exit 2
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
    printf '%s\n' 'outcome=timeout'
    exit 6
  fi
  python3 -c 'import time; time.sleep(0.2)'
done
