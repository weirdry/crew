#!/bin/sh
# Exit statuses:
#   0  Run directory, pointer, state skeleton, and exclude entry created.
#   2  Arguments other than the optional --replace-current flag.
#   3  Repository metadata or its real exclude path could not be resolved.
#   4  The exclude entry could not be read or written.
#   5  Run state could not be created without overwriting an existing run.
#   6  An existing .crew/.current was preserved; its current run id is printed.

set -u

case "$#:$*" in
  0:|1:--replace-current)
    ;;
  *)
    printf '%s\n' 'usage: run-init.sh [--replace-current]' >&2
    exit 2
    ;;
esac

python3 - "$@" <<'PY'
import os
from pathlib import Path
import sys
import time


def fail(message: str, status: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(status)


def pointer_value(path: Path) -> str:
    try:
        content = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return "<unreadable>"
    lines = content.splitlines()
    return lines[0] if lines else "<empty>"


def report_existing(path: Path) -> None:
    print(f"current_run={pointer_value(path)}", file=sys.stderr)
    print("outcome=current-exists", file=sys.stderr)


replace_current = sys.argv[1:] == ["--replace-current"]
cwd = Path.cwd()
git_dir = None

for directory in (cwd, *cwd.parents):
    dot_git = directory / ".git"
    if dot_git.is_dir():
        git_dir = dot_git.resolve()
        break
    if dot_git.is_file():
        try:
            declaration = dot_git.read_text(encoding="utf-8").strip()
        except OSError as error:
            fail(f"cannot read {dot_git}: {error}", 3)
        prefix = "gitdir:"
        if not declaration.lower().startswith(prefix):
            fail(f"invalid gitdir file: {dot_git}", 3)
        candidate = Path(declaration[len(prefix) :].strip())
        if not candidate.is_absolute():
            candidate = dot_git.parent / candidate
        git_dir = candidate.resolve()
        break

if git_dir is None or not git_dir.is_dir():
    fail("cannot resolve repository metadata from the current directory", 3)

common_dir = git_dir
common_file = git_dir / "commondir"
if common_file.is_file():
    try:
        common_value = common_file.read_text(encoding="utf-8").strip()
    except OSError as error:
        fail(f"cannot read {common_file}: {error}", 3)
    common_dir = Path(common_value)
    if not common_dir.is_absolute():
        common_dir = git_dir / common_dir
    common_dir = common_dir.resolve()

if not common_dir.is_dir():
    fail(f"resolved Git common directory does not exist: {common_dir}", 3)

exclude_file = common_dir / "info" / "exclude"

try:
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    previous = exclude_file.read_bytes() if exclude_file.exists() else b""
    if b".crew/" not in previous.splitlines():
        separator = b"" if not previous or previous.endswith(b"\n") else b"\n"
        with exclude_file.open("ab") as handle:
            handle.write(separator + b".crew/\n")
except OSError as error:
    fail(f"cannot update {exclude_file}: {error}", 4)

run_id = time.strftime("%Y%m%d-%H%M%S")
run_root = cwd / ".crew"
run_dir = run_root / run_id
current_path = run_root / ".current"
current_tmp = run_root / f".current.{os.getpid()}.tmp"
created_run_dir = False
replaced_current = None

if os.path.lexists(current_path):
    if not replace_current:
        report_existing(current_path)
        raise SystemExit(6)
    replaced_current = pointer_value(current_path)

try:
    run_dir.mkdir(parents=True, exist_ok=False)
    created_run_dir = True
    state = (
        "# Crew state\n\n"
        "- Phase: 0 — scope not frozen\n"
        "- Round: 0 of 3\n"
        "- Worker: none\n"
        "- Pane: none\n"
    )
    (run_dir / "state.md").write_text(state, encoding="utf-8")
    current_tmp.write_text(f"{run_id}\n", encoding="utf-8")
    if replace_current:
        os.replace(current_tmp, current_path)
    else:
        try:
            os.link(current_tmp, current_path)
        except FileExistsError:
            current_tmp.unlink(missing_ok=True)
            (run_dir / "state.md").unlink(missing_ok=True)
            run_dir.rmdir()
            report_existing(current_path)
            raise SystemExit(6)
        try:
            current_tmp.unlink()
        except OSError:
            pass
except SystemExit:
    raise
except (FileExistsError, OSError) as error:
    try:
        current_tmp.unlink(missing_ok=True)
        if created_run_dir:
            state_file = run_dir / "state.md"
            state_file.unlink(missing_ok=True)
            run_dir.rmdir()
    except OSError:
        pass
    fail(f"cannot create run state: {error}", 5)

if replaced_current is not None:
    print(f"replaced_current={replaced_current}", file=sys.stderr)
print(run_id)
PY
