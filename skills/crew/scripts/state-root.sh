#!/bin/sh
# Exit statuses:
#   0  The canonical workspace key and validated state root were printed as JSON.
#   2  Unexpected arguments.
#   3  The workspace, state base, or a required validation root was unusable.
#   4  The resolved state root lies at or below a worker-writable root.

set -u

if [ "$#" -ne 0 ]; then
  printf '%s\n' 'usage: state-root.sh' >&2
  exit 2
fi

python3 - <<'PY'
from pathlib import Path
import hashlib
import json
import os
import re
import sys


def fail(message: str, status: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(status)


def resolved(value: str, label: str) -> Path:
    try:
        return Path(value).resolve(strict=False)
    except (OSError, RuntimeError) as error:
        fail(f"cannot resolve {label}: {error}", 3)


def is_at_or_below(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


try:
    cwd = Path.cwd().resolve(strict=True)
except (OSError, RuntimeError) as error:
    fail(f"cannot resolve workspace: {error}", 3)

workspace = re.sub(r"[^a-z0-9]+", "-", cwd.name.lower()).strip("-") or "workspace"
workspace = workspace[:14].rstrip("-_") or "workspace"
digest = hashlib.sha256(str(cwd).encode("utf-8")).hexdigest()[:12]
workspace_key = f"{workspace}-{digest}"

state_parent_value = os.environ.get("CREW_STATE_DIR") or None
if state_parent_value is None:
    home = os.environ.get("HOME")
    if not home:
        fail("HOME is absent and CREW_STATE_DIR was not provided", 3)
    state_parent_value = str(Path(home) / ".crew")

state_parent = resolved(state_parent_value, "state parent")
state_root = resolved(str(state_parent / workspace_key), "state root")

repository_root = cwd
for directory in (cwd, *cwd.parents):
    dot_git = directory / ".git"
    if dot_git.is_dir() or dot_git.is_file():
        repository_root = resolved(str(directory), "repository root")
        break

refused_values = [str(repository_root), "/tmp", "/private/tmp", "/var/folders"]
temporary_root = os.environ.get("TMPDIR")
if temporary_root:
    refused_values.append(temporary_root)

refused_roots: list[Path] = []
for value in refused_values:
    root = resolved(value, "worker-writable root")
    if root not in refused_roots:
        refused_roots.append(root)

for root in refused_roots:
    if is_at_or_below(state_root, root):
        fail(f"refusing state root at or below worker-writable root: {state_root} <= {root}", 4)

print(
    json.dumps(
        {
            "cwd": str(cwd),
            "partner_name": f"crew-{workspace_key}",
            "repository_root": str(repository_root),
            "state_parent": str(state_parent),
            "state_root": str(state_root),
            "workspace_key": workspace_key,
        },
        sort_keys=True,
    )
)
PY
