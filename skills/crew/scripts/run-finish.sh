#!/bin/sh
# Exit statuses:
#   0  The named run had no receipt or its worker was verified absent; the pointer was removed.
#   2  Wrong argument count or an invalid run id.
#   3  The active-run pointer could not be read.
#   4  The requested run did not match the active-run pointer; both ids are printed.
#   5  The named run directory was absent or its existing worker-pane receipt was invalid.
#   6  Worker liveness could not be determined safely.
#   7  The recorded worker name still resolves to a live agent; removal was refused.
#   8  The active-run pointer could not be removed.

set -u

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: run-finish.sh <run-id>' >&2
  exit 2
fi

python3 - "$1" <<'PY'
from pathlib import Path
import json
import os
import re
import subprocess
import sys


def fail(message: str, status: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(status)


def pointer_value(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {path}: {error}", 3)
    lines = content.splitlines()
    return lines[0] if len(lines) == 1 else "<invalid>"


def report_mismatch(requested: str, actual: str) -> None:
    print(f"requested_run={requested}", file=sys.stderr)
    print(f"current_run={actual}", file=sys.stderr)
    print("outcome=refused:run-id-mismatch", file=sys.stderr)


run_id = sys.argv[1]
if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id):
    fail(f"invalid run id: {run_id}", 2)

run_root = Path.cwd() / ".crew"
current_path = run_root / ".current"
current_run = pointer_value(current_path)
if current_run != run_id:
    report_mismatch(run_id, current_run)
    raise SystemExit(4)

run_dir = run_root / run_id
if not run_dir.is_dir():
    fail(f"active run directory does not exist: {run_dir}", 5)

receipt = run_dir / "worker-pane.json"
if os.path.lexists(receipt):
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"invalid worker ownership receipt {receipt}: {error}", 5)
    worker_name = data.get("worker_name") if isinstance(data, dict) else None
    if not isinstance(worker_name, str) or not worker_name:
        fail(f"invalid worker ownership receipt: {receipt}", 5)

    try:
        result = subprocess.run(
            ["herdr", "agent", "get", worker_name],
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, UnicodeError) as error:
        fail(f"cannot query worker {worker_name}: {error}", 6)

    response_text = result.stdout if result.stdout.strip() else result.stderr
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError:
        detail = response_text.strip().replace("\n", " ")
        fail(f"cannot determine worker liveness for {worker_name}: {detail}", 6)
    if not isinstance(payload, dict):
        fail(f"cannot determine worker liveness for {worker_name}: invalid Herdr response", 6)

    if result.returncode == 0:
        result_payload = payload.get("result")
        agent = result_payload.get("agent") if isinstance(result_payload, dict) else None
        if not isinstance(agent, dict) or agent.get("name") != worker_name:
            fail(f"cannot determine worker liveness for {worker_name}: invalid Herdr response", 6)
        print(f"worker_name={worker_name}", file=sys.stderr)
        print(f"live_worker_pane_id={agent.get('pane_id', '<unknown>')}", file=sys.stderr)
        print("outcome=refused:worker-live", file=sys.stderr)
        raise SystemExit(7)

    error_payload = payload.get("error")
    error_code = error_payload.get("code") if isinstance(error_payload, dict) else None
    if error_code != "agent_not_found":
        fail(f"cannot determine worker liveness for {worker_name}: {error_code or '<unknown>'}", 6)

current_run = pointer_value(current_path)
if current_run != run_id:
    report_mismatch(run_id, current_run)
    raise SystemExit(4)

try:
    current_path.unlink()
except OSError as error:
    fail(f"cannot remove {current_path}: {error}", 8)

print(f"finished_run={run_id}")
print("removed_pointer=.crew/.current")
PY
