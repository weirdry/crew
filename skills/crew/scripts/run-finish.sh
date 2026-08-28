#!/bin/sh
# Exit statuses:
#   0  The named run matched the active pointer, its approval audit was copied when present, and the pointer was removed.
#   2  Wrong argument count or an invalid run id.
#   3  The active-run pointer could not be read.
#   4  The requested run did not match the active-run pointer; both ids are printed.
#   5  The named run directory was absent.
#   6  The active-run pointer could not be removed.
#   7  The external state root was invalid or unusable.
#   8  The approval record could not be copied to a safe audit file.

set -u

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: run-finish.sh <run-id>' >&2
  exit 2
fi

script_dir=${0%/*}
if [ "$script_dir" = "$0" ]; then
  script_dir=.
fi
state_json=$("$script_dir/state-root.sh") || exit 7
state_root=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["state_root"])
' "$state_json") || exit 7

python3 - "$1" "$state_root" <<'PY'
from pathlib import Path
import os
import re
import stat
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

state_root = Path(sys.argv[2])
run_root = Path.cwd() / ".crew"
current_path = state_root / ".current"
current_run = pointer_value(current_path)
if current_run != run_id:
    report_mismatch(run_id, current_run)
    raise SystemExit(4)

run_dir = run_root / run_id
if not run_dir.is_dir():
    fail(f"active run directory does not exist: {run_dir}", 5)

approval_record = state_root / run_id / "approvals.jsonl"
audit_path = run_dir / "approvals.audit.jsonl"
audit_copied = False
if os.path.lexists(approval_record):
    try:
        source_status = approval_record.lstat()
        if not stat.S_ISREG(source_status.st_mode):
            fail(f"approval record is not a regular file: {approval_record}", 8)
        approval_bytes = approval_record.read_bytes()
        if os.path.lexists(audit_path):
            audit_status = audit_path.lstat()
            if not stat.S_ISREG(audit_status.st_mode) or audit_path.read_bytes() != approval_bytes:
                fail(f"approval audit already exists with different or unsafe content: {audit_path}", 8)
        else:
            temporary = run_dir / f".approvals.audit.{os.getpid()}.tmp"
            try:
                with temporary.open("xb") as handle:
                    handle.write(approval_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, audit_path)
            finally:
                temporary.unlink(missing_ok=True)
        audit_copied = True
    except SystemExit:
        raise
    except OSError as error:
        fail(f"cannot copy approval audit: {error}", 8)

current_run = pointer_value(current_path)
if current_run != run_id:
    report_mismatch(run_id, current_run)
    raise SystemExit(4)

try:
    current_path.unlink()
except OSError as error:
    fail(f"cannot remove {current_path}: {error}", 6)

print(f"finished_run={run_id}")
if audit_copied:
    print(f"approval_audit=.crew/{run_id}/approvals.audit.jsonl")
print(f"removed_pointer={current_path}")
PY
