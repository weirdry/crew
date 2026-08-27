#!/bin/sh
# Exit statuses:
#   0  The named run matched the active pointer and the pointer was removed.
#   2  Wrong argument count or an invalid run id.
#   3  The active-run pointer could not be read.
#   4  The requested run did not match the active-run pointer; both ids are printed.
#   5  The named run directory was absent.
#   6  The active-run pointer could not be removed.

set -u

if [ "$#" -ne 1 ]; then
  printf '%s\n' 'usage: run-finish.sh <run-id>' >&2
  exit 2
fi

python3 - "$1" <<'PY'
from pathlib import Path
import re
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

current_run = pointer_value(current_path)
if current_run != run_id:
    report_mismatch(run_id, current_run)
    raise SystemExit(4)

try:
    current_path.unlink()
except OSError as error:
    fail(f"cannot remove {current_path}: {error}", 6)

print(f"finished_run={run_id}")
print("removed_pointer=.crew/.current")
PY
