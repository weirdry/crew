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

        def cli(*args):
            # Both confirmations are suppressed only for these disposable fixtures.
            return run(["npx", "--yes", PACKAGE, *args], cwd=work, env=env)

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
        assert "up to date" in cli("update", "crew", "-g", "-y").lower()
        assert inventory(codex) != expected
        check_ref()
        cli(*add)
        assert inventory(codex) == expected  # Re-add replaces the local edit.
        check_ref()
        print(json.dumps({"installer": PACKAGE, "release": TAG, "source": source,
                          "files_per_layout": len(expected), "layouts": ["codex", "claude"],
                          "installation_and_helpers": "passed", "pinned_update_and_readd": "passed"}))


if __name__ == "__main__":
    main()
