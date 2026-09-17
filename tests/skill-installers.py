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
    files, contents = {}, {}
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        assert kind == "blob" and mode in {"100644", "100755"}
        data = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        path = name.decode().removeprefix("skills/crew/")
        contents[path] = data
        files[path] = {
            "sha256": hashlib.sha256(data).hexdigest(), "executable": mode == "100755"}
    assert "SKILL.md" in files and "scripts/relay.sh" in files
    return files, contents


def published_tree():
    """Use fetched Git objects as the controlled API response, never the worktree."""
    entries = subprocess.check_output(["git", "ls-tree", "-rtz", TAG], cwd=ROOT)
    tree = []
    for entry in entries.split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            mode, kind, sha = metadata.decode().split()
            tree.append({"path": path.decode(), "mode": mode, "type": kind, "sha": sha})
    return {"sha": run(["git", "rev-parse", TAG + "^{tree}"]).strip(),
            "tree": tree, "truncated": False}


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
    expected, contents = expected_files()
    source = run(["git", "rev-parse", TAG + "^{commit}"]).strip()
    tree_hash = run(["git", "rev-parse", TAG + ":skills/crew"]).strip()
    node = Path(run(["node", "-p", "process.execPath"]).strip())
    # Skills CLI 1.6.0's fallback hashes path + bytes in JS localeCompare order.
    ordered = json.loads(run([str(node), "-e",
                              "console.log(JSON.stringify(JSON.parse(process.argv[1])"
                              ".sort((a, b) => a.localeCompare(b))))", json.dumps(list(contents))]))
    content_hash = hashlib.sha256()
    for path in ordered:
        content_hash.update(path.encode())
        content_hash.update(contents[path])
    content_hash = content_hash.hexdigest()
    with tempfile.TemporaryDirectory(prefix="crew-skill-installer-") as temporary:
        work = Path(temporary).resolve()
        home, scratch = work / "home", work / "tmp"
        for path in (home / ".codex", home / ".claude", scratch):
            path.mkdir(parents=True)
        tree_fixture = work / "published-tree.json"
        tree_fixture.write_text(json.dumps(published_tree()))
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
            "NODE_OPTIONS": "--require " + json.dumps(str(ROOT / "tests/skill-installer-http.cjs")),
            "CREW_TEST_TREE_URL": "https://api.github.com/repos/weirdry/crew/git/trees/" + TAG + "?recursive=1",
            "CREW_TEST_TREE_FIXTURE": str(tree_fixture),
        }

        def cli(label, *args, mode="live", extra_env=None):
            # Both confirmations are suppressed only for these disposable fixtures.
            http_log = work / (label + "-http.jsonl")
            assert not http_log.exists(), "Use a distinct label for each CLI invocation"
            try:
                output = run(["npx", "--yes", PACKAGE, *args], cwd=work, env=env | {
                    "CREW_TEST_TREE_MODE": mode, "CREW_TEST_HTTP_LOG": str(http_log),
                } | (extra_env or {}))
            finally:
                events = [json.loads(line) for line in http_log.read_text().splitlines()] if http_log.exists() else []
                print(json.dumps({"step": label, "tree_http": events}), flush=True)
            if args[0] in {"add", "update"}:
                assert events, "The tree request observer was not exercised"
                assert all(event["url"] == env["CREW_TEST_TREE_URL"] for event in events)
                if mode != "live":
                    status = 200 if mode == "tree" else 503
                    assert all(event.get("status") == status for event in events)
            return output

        add = ("add", "weirdry/crew#" + TAG, "-g", "-a", "codex", "claude-code", "-y")
        cli("live-add", *add)
        codex = home / ".agents/skills/crew"
        claude = home / ".claude/skills/crew"
        assert codex.is_dir() and not codex.is_symlink()
        assert claude.is_symlink() and claude.resolve() == codex
        assert inventory(codex) == inventory(claude) == expected
        lock_path = home / ".agents/.skill-lock.json"

        def check_ref(expected_hash=None):
            entry = json.loads(lock_path.read_text())["skills"]["crew"]
            assert entry["source"] == "weirdry/crew" and entry["ref"] == TAG
            assert entry["skillPath"] == "skills/crew/SKILL.md"
            folder_hash = entry.get("skillFolderHash", "")
            accepted = {expected_hash} if expected_hash else {tree_hash, content_hash}
            assert folder_hash in accepted, "Skills CLI source hash differs from the published source"
            return "git-tree" if folder_hash == tree_hash else "content"

        live_hash_kind = check_ref()
        assert "crew" in cli("live-list", "list", "-g")
        report = work / "report.md"
        for root in (codex, claude):
            report.write_text("Synthetic report\nSTATUS: done\n")
            run([str(root / "scripts/artifact-done.sh"), str(report)], cwd=work, env=env)
            report.write_text("STATUS: blocked\n")
            run([str(root / "scripts/artifact-done.sh"), str(report)], cwd=work, env=env, expected=1)
            output = run([str(root / "scripts/relay.sh")], cwd=work, env=env, expected=2)
            assert "usage:" in output.lower()
        assert inventory(codex) == expected
        print(json.dumps({"live_installation_and_helpers": "passed", "source_hash": live_hash_kind}), flush=True)

        # Control API availability independently of the actual npm/Git install.
        # The response is derived from the fetched release; CLI lock files are never edited.
        cli("tree-add", *add, mode="tree")
        assert inventory(codex) == expected
        check_ref(tree_hash)
        skill = codex / "SKILL.md"
        skill.write_bytes(skill.read_bytes() + b"\nSynthetic local edit.\n")
        edited = inventory(codex)
        require_current_update(cli("tree-update", "update", "crew", "-g", "-y", mode="tree"))
        assert inventory(codex) == edited
        check_ref(tree_hash)
        require_current_update(cli("tree-git-update", "update", "crew", "-g", "-y", mode="unavailable"))
        assert inventory(codex) == edited
        check_ref(tree_hash)

        cli("fallback-add", *add, mode="unavailable")
        assert inventory(codex) == expected
        check_ref(content_hash)
        skill.write_bytes(skill.read_bytes() + b"\nSynthetic local edit.\n")
        edited = inventory(codex)
        require_current_update(cli("fallback-update", "update", "crew", "-g", "-y", mode="unavailable"))
        assert inventory(codex) == edited
        check_ref(content_hash)
        # When API access returns, unlike hashes trigger a same-tag replacement.
        recovered = cli("api-recovered-update", "update", "crew", "-g", "-y", mode="tree")
        assert "failed to check" not in recovered.lower() and "failed to update" not in recovered.lower()
        assert inventory(codex) == expected
        check_ref(tree_hash)

        # Reproduce the real CLI's misleading success with both transports down.
        failed_bin = work / "failed-bin"
        failed_bin.mkdir()
        git = failed_bin / "git"
        git.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CREW_TEST_GIT_FAILURE_LOG"\n'
                       'echo "synthetic Git transport failure" >&2\nexit 128\n')
        git.chmod(0o755)
        git_log = work / "git-failure.log"
        before_files, before_lock = inventory(codex), lock_path.read_bytes()
        failed_output = cli("failed-source-update", "update", "crew", "-g", "-y", mode="unavailable", extra_env={
            "PATH": str(failed_bin) + os.pathsep + env["PATH"],
            "npm_config_offline": "true",  # Reuse the package fetched by add.
            "CREW_TEST_GIT_FAILURE_LOG": str(git_log),
        })
        assert "clone" in git_log.read_text()
        assert "failed to check" in failed_output.lower() and "up to date" in failed_output.lower()
        try:
            require_current_update(failed_output)
        except RuntimeError:
            pass
        else:
            raise AssertionError("The update validator accepted a failed source check")
        assert inventory(codex) == before_files and lock_path.read_bytes() == before_lock

        skill.write_bytes(skill.read_bytes() + b"\nSynthetic local edit.\n")
        cli("live-readd", *add)
        assert inventory(codex) == expected  # Re-add replaces the local edit.
        check_ref()
        print(json.dumps({"installer": PACKAGE, "release": TAG, "source": source,
                          "files_per_layout": len(expected), "layouts": ["codex", "claude"],
                          "live_installation_and_helpers": "passed", "live_readd": "passed",
                          "controlled_update_scenarios": "passed",
                          "failed_source_check_rejected": "passed"}))


if __name__ == "__main__":
    main()
