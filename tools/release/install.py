#!/usr/bin/env python3
"""Install or check a verified Crew release in explicit host skill directories."""

import sys
sys.dont_write_bytecode = True

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import stat

from release_lib import (Invalid, MARKER, OWNER, VERSION_RE, SHA_RE, DIGEST_RE,
                         content_digest, encoded, inventory, load_payload,
                         require, validate_inventory)


def exists(path):
    return os.path.lexists(path)


def plain_parents(path):
    for parent in reversed((path, *path.parents)):
        if exists(parent):
            require(parent.is_dir() and not parent.is_symlink(), f"unsafe directory: {parent}")


def expected_marker(manifest, host):
    files = {name.removeprefix("skill/"): value for name, value in manifest["files"].items()
             if name.startswith("skill/")}
    return {"schema": 1, "owner": OWNER, "host": host,
            "version": manifest["version"], "source": manifest["source"],
            "release_sha256": manifest["content_sha256"], "files": files,
            "content_sha256": content_digest(files)}


def validate_marker(marker, host):
    require(isinstance(marker, dict) and set(marker) == {
        "schema", "owner", "host", "version", "source", "release_sha256", "files", "content_sha256"
    }, "unknown installation marker")
    require(marker["schema"] == 1 and marker["owner"] == OWNER and marker["host"] == host,
            "installation owner/host mismatch")
    require(isinstance(marker["version"], str) and VERSION_RE.fullmatch(marker["version"]) and
            isinstance(marker["source"], str) and SHA_RE.fullmatch(marker["source"]) and
            isinstance(marker["release_sha256"], str) and DIGEST_RE.fullmatch(marker["release_sha256"]),
            "invalid installation identity")
    validate_inventory(marker["files"])
    require("SKILL.md" in marker["files"] and MARKER not in marker["files"] and
            content_digest(marker["files"]) == marker["content_sha256"], "invalid installed inventory")
    return marker


def inspect(destination, wanted):
    result = {"host": wanted["host"], "destination": str(destination),
              "requested_version": wanted["version"], "source": wanted["source"]}
    try:
        plain_parents(destination.parent)
        if not exists(destination):
            return result | {"status": "missing"}
        require(destination.is_dir() and not destination.is_symlink(), "unmanaged directory or development symlink")
        path = destination / MARKER
        require(path.is_file() and not path.is_symlink() and path.stat().st_size < 1024 * 1024,
                "installation ownership record missing or unsafe")
        marker = validate_marker(json.loads(path.read_text()), wanted["host"])
    except (Invalid, ValueError, OSError) as exc:
        return result | {"status": "conflicting", "reason": str(exc)}
    result["installed_version"] = marker["version"]
    try:
        require(inventory(destination, (MARKER,)) == marker["files"], "installed content differs from its record")
    except (Invalid, OSError) as exc:
        return result | {"status": "modified", "reason": str(exc)}
    if marker == wanted:
        return result | {"status": "current"}
    if marker["version"] == wanted["version"]:
        return result | {"status": "conflicting", "reason": "same version has another release identity"}
    return result | {"status": "stale"}


def host_paths(args, host):
    home = args.home.expanduser().resolve()
    normal = home / (".agents/skills" if host == "codex" else ".claude/skills")
    selected = getattr(args, f"{host}_root") or normal
    roots = {normal, selected}
    if host == "codex":
        roots.add(home / ".codex/skills")
        if args.home == Path.home() and os.environ.get("CODEX_HOME"):
            roots.add(Path(os.environ["CODEX_HOME"]) / "skills")
        roots.add(Path("/etc/codex/skills"))
    roots.update(args.extra_skill_root)
    # Check the invocation's repository scope, without scanning unrelated workspaces.
    for parent in (Path.cwd(), *Path.cwd().parents):
        roots.add(parent / (".agents/skills" if host == "codex" else ".claude/skills"))
        if (parent / ".git").exists() or parent == home:
            break
    # Resolve roots once, then append the managed name. Never resolve away a
    # development symlink at the crew directory itself or treat it as ownership.
    destinations = {root: root.expanduser().resolve() / "crew" for root in roots}
    destination = destinations[selected]
    candidates = set(destinations.values())
    conflicts = sorted(str(p) for p in candidates if p != destination and exists(p))
    return destination, conflicts


def replace_managed(payload, destination, wanted):
    """A per-destination lock and preserved backup protect the directory swap."""
    plain_parents(destination.parent)
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.parent / ".crew-install.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_nlink == 1, "unsafe installer lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pending = destination.parent / ".crew-install-pending"
        require(not exists(pending), f"unfinished installation preserved at {pending}; inspect it before retrying")
        before = inspect(destination, wanted)
        require(before["status"] in ("current", "missing", "stale"), before.get("reason", "installation conflict"))
        if before["status"] == "current":
            return before | {"action": "none"}
        original_marker = json.loads((destination / MARKER).read_text()) if before["status"] == "stale" else None
        pending.mkdir(mode=0o700)
        stage, backup = pending / "new", pending / "previous"
        swapped = False
        try:
            shutil.copytree(payload / "skill", stage)
            (stage / MARKER).write_bytes(encoded(wanted))
            (stage / MARKER).chmod(0o644)
            require(inspect(stage, wanted)["status"] == "current", "staged installation check failed")
            require(inspect(destination, wanted) == before, "installation changed during staging")
            if original_marker is not None:
                # Preserve the old content until the complete new directory is verified.
                os.rename(destination, backup)
            else:
                require(not exists(destination), "destination appeared during staging")
            os.rename(stage, destination)
            swapped = True
            require(inspect(destination, wanted)["status"] == "current", "replacement verification failed")
            if original_marker is not None:
                require(inspect(backup, original_marker)["status"] == "current", "previous installation changed; backup retained")
                shutil.rmtree(backup)
            pending.rmdir()
        except BaseException:
            if not swapped:
                if exists(backup) and not exists(destination):
                    os.rename(backup, destination)
                if not exists(backup):
                    if exists(stage):
                        shutil.rmtree(stage)
                    pending.rmdir()
            # After a swap or failed restoration, preserve evidence for the operator.
            raise
        return inspect(destination, wanted) | {"action": "installed" if original_marker is None else "updated"}
    finally:
        os.close(fd)


def run(args):
    payload = args.payload.resolve()
    manifest = load_payload(payload)
    results = []
    for host in (["codex", "claude"] if args.host == "all" else [args.host]):
        wanted = expected_marker(manifest, host)
        destination, conflicts = host_paths(args, host)
        if conflicts:
            results.append({"host": host, "destination": str(destination), "status": "conflicting",
                            "reason": "another Crew installation exists", "conflicts": conflicts})
            continue
        result = inspect(destination, wanted)
        if args.command == "install" and result["status"] in ("missing", "stale"):
            try:
                require(args.inactive, "finish active Crew work and pass --inactive; start a fresh agent session afterwards")
                result = replace_managed(payload, destination, wanted)
            except (Invalid, OSError) as exc:
                result |= {"status": "error", "reason": str(exc)}
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check"))
    parser.add_argument("--payload", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--host", choices=("codex", "claude", "all"), required=True)
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--codex-root", type=Path)
    parser.add_argument("--claude-root", type=Path)
    parser.add_argument("--extra-skill-root", type=Path, action="append", default=[])
    parser.add_argument("--inactive", action="store_true", help="confirm no active Crew session uses this installation")
    args = parser.parse_args()
    try:
        results = run(args)
    except (Invalid, ValueError, OSError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 2
    print(json.dumps({"results": results}, sort_keys=True))
    return 0 if all(r["status"] == "current" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
