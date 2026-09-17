#!/usr/bin/env python3
"""Network smoke test of the documented Skills CLI in a disposable home."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "skills@1.6.0"
TAG = "v0.1.0"  # An actually published release, not the candidate VERSION.


def run(argv, *, cwd=ROOT, env=None, expected=0):
    result = subprocess.run(argv, cwd=cwd, env=env, text=True, capture_output=True, timeout=180)
    if result.returncode != expected:
        raise RuntimeError(f"{argv!r}: exit {result.returncode}, expected {expected}\n"
                           + result.stdout + result.stderr)
    return result.stdout + result.stderr


def require_current_update(output):
    # Skills CLI 1.6.0 can print success and exit 0 after a failed source check.
    lower = output.lower()
    if "failed to check" in lower or "failed to update" in lower:
        raise RuntimeError("Skills CLI update failed:\n" + output)
    if "all global skills are up to date" not in lower:
        raise RuntimeError("Skills CLI did not confirm the pinned source:\n" + output)


def expected_files():
    entries = subprocess.check_output(["git", "ls-tree", "-rz", TAG, "skills/crew"], cwd=ROOT)
    files = {}
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        assert kind == "blob" and mode in {"100644", "100755"}
        data = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        files[name.decode().removeprefix("skills/crew/")] = {
            "sha256": hashlib.sha256(data).hexdigest(), "executable": mode == "100755"}
    assert "SKILL.md" in files and "scripts/relay.sh" in files
    return files


def inventory(directory):
    files = {}
    for path in directory.rglob("*"):
        assert not path.is_symlink(), f"unexpected nested link: {path}"
        if path.is_file():
            files[str(path.relative_to(directory))] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "executable": bool(path.stat().st_mode & 0o111)}
    return files


def main():
    expected = expected_files()
    source = run(["git", "rev-parse", TAG + "^{commit}"]).strip()
    tree_hash = run(["git", "rev-parse", TAG + ":skills/crew"]).strip()
    node = Path(run(["node", "-p", "process.execPath"]).strip())
    with tempfile.TemporaryDirectory(prefix="crew-skill-installer-") as temporary:
        work = Path(temporary).resolve()
        home, scratch = work / "home", work / "tmp"
        for path in (home / ".codex", home / ".claude", scratch):
            path.mkdir(parents=True)
        # No user credentials, host configuration, installations or runtime state.
        env = {
            "PATH": os.pathsep.join((str(node.parent), str(Path(sys.executable).parent), os.defpath)),
            "HOME": str(home), "CODEX_HOME": str(home / ".codex"),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "XDG_CONFIG_HOME": str(home / ".config"), "XDG_CACHE_HOME": str(home / ".cache"),
            "GH_CONFIG_DIR": str(home / ".gh"), "TMPDIR": str(scratch),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
            "npm_config_cache": str(work / "npm-cache"), "npm_config_userconfig": str(home / ".npmrc"),
            "DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1", "CI": "1",
        }

        def cli(*args, extra_env=None):
            # Both confirmations are suppressed only for these disposable fixtures.
            return run(["npx", "--yes", PACKAGE, *args], cwd=work, env=env | (extra_env or {}))

        add = ("add", "weirdry/crew#" + TAG, "-g", "-a", "codex", "claude-code", "-y")
        cli(*add)
        codex = home / ".agents/skills/crew"
        claude = home / ".claude/skills/crew"
        assert codex.is_dir() and not codex.is_symlink()
        assert claude.is_symlink() and claude.resolve() == codex
        assert inventory(codex) == inventory(claude) == expected
        lock_path = home / ".agents/.skill-lock.json"

        def check_ref():
            entry = json.loads(lock_path.read_text())["skills"]["crew"]
            assert entry["source"] == "weirdry/crew" and entry["ref"] == TAG
            assert entry["skillPath"] == "skills/crew/SKILL.md"
            folder_hash = entry.get("skillFolderHash", "")
            if len(folder_hash) == 64 and all(c in "0123456789abcdef" for c in folder_hash):
                raise RuntimeError(
                    "GitHub tree API unavailable during add: Skills CLI recorded a fallback content hash. "
                    "The pinned-update scenario requires an API tree hash; rerun this isolated smoke "
                    "test when the API is available. Do not pass credentials to the third-party CLI.")
            assert folder_hash == tree_hash, "Skills CLI source hash differs from the published Git tree"

        check_ref()
        assert "crew" in cli("list", "-g")
        report = work / "report.md"
        for root in (codex, claude):
            report.write_text("Synthetic report\nSTATUS: done\n")
            run([str(root / "scripts/artifact-done.sh"), str(report)], cwd=work, env=env)
            report.write_text("STATUS: blocked\n")
            run([str(root / "scripts/artifact-done.sh"), str(report)], cwd=work, env=env, expected=1)
            output = run([str(root / "scripts/relay.sh")], cwd=work, env=env, expected=2)
            assert "usage:" in output.lower()
        assert inventory(codex) == expected

        # Pin the documented ownership limits: source checks are not drift checks.
        skill = codex / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\nSynthetic local edit.\n")
        require_current_update(cli("update", "crew", "-g", "-y"))
        assert inventory(codex) != expected
        check_ref()

        # Reproduce the real CLI's misleading success with both transports down.
        failed_bin = work / "failed-bin"
        failed_bin.mkdir()
        git = failed_bin / "git"
        git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CREW_TEST_GIT_FAILURE_LOG"\n'
                       'echo "synthetic Git transport failure" >&2\nexit 128\n')
        git.chmod(0o755)
        hook = work / "failed-fetch.cjs"
        hook.write_text('globalThis.fetch = async () => {\n'
                        '  require("node:fs").appendFileSync(process.env.CREW_TEST_HTTP_FAILURE_LOG, "fetch\\n");\n'
                        '  throw new Error("synthetic HTTP transport failure");\n};\n')
        http_log, git_log = work / "http-failure.log", work / "git-failure.log"
        before_files, before_lock = inventory(codex), lock_path.read_bytes()
        failed_output = cli("update", "crew", "-g", "-y", extra_env={
            "PATH": str(failed_bin) + os.pathsep + env["PATH"],
            "NODE_OPTIONS": "--require " + json.dumps(str(hook)),
            "npm_config_offline": "true",  # Reuse the package fetched by add.
            "CREW_TEST_HTTP_FAILURE_LOG": str(http_log),
            "CREW_TEST_GIT_FAILURE_LOG": str(git_log),
        })
        assert http_log.read_text() and "clone" in git_log.read_text()
        assert "failed to check" in failed_output.lower() and "up to date" in failed_output.lower()
        try:
            require_current_update(failed_output)
        except RuntimeError:
            pass
        else:
            raise AssertionError("The update validator accepted a failed source check")
        assert inventory(codex) == before_files and lock_path.read_bytes() == before_lock

        cli(*add)
        assert inventory(codex) == expected  # Re-add replaces the local edit.
        check_ref()
        print(json.dumps({"installer": PACKAGE, "release": TAG, "source": source,
                          "files_per_layout": len(expected), "layouts": ["codex", "claude"],
                          "installation_and_helpers": "passed", "pinned_update_and_readd": "passed",
                          "failed_source_check_rejected": "passed"}))


if __name__ == "__main__":
    main()
