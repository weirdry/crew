#!/usr/bin/env python3
"""Verify downloaded release bytes in disposable Codex and Claude skill roots."""

import sys
sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.request

from release_lib import (Invalid, OWNER, MAX_BYTES, encoded, extract_verified, require)


def download(url):
    # Public HTTPS only. This path never reads or sends a publication credential.
    response = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "crew-consumer"}), timeout=60)
    data = response.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, "download too large")
    return data


def exercise(archive, checksum, work):
    work = Path(work).resolve()
    payload, home = work / "payload", work / "home"
    manifest = extract_verified(archive, checksum, payload)
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in
           {"GH_TOKEN", "GITHUB_TOKEN", "CODEX_HOME", "CLAUDE_CONFIG_DIR", "HERDR_ENV", "HERDR_PANE_ID", "CREW_STATE_DIR"}}
    env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1")
    command = [sys.executable, "-B", str(payload / "install.py"), "install", "--host", "all", "--home", str(home), "--inactive"]
    for _ in range(2):
        result = subprocess.run(command, cwd=work, env=env, text=True, capture_output=True)
        require(result.returncode == 0, f"isolated installation failed: {result.stdout.strip()}")
        results = json.loads(result.stdout)["results"]
        require(len(results) == 2 and all(r["status"] == "current" for r in results), "host installation results incomplete")
    command[3] = "check"
    result = subprocess.run(command, cwd=work, env=env, text=True, capture_output=True)
    require(result.returncode == 0, "installed-content check failed")
    for root in (home / ".agents/skills/crew", home / ".claude/skills/crew"):
        report = work / "synthetic-report.md"
        report.write_text("Synthetic consumer check\nSTATUS: done\n")
        done = root / "scripts/artifact-done.sh"
        require(subprocess.run([str(done), str(report)], cwd=work, env=env).returncode == 0,
                "installed completion helper rejected a completed artifact")
        report.write_text("STATUS: blocked\n")
        require(subprocess.run([str(done), str(report)], cwd=work, env=env).returncode == 1,
                "installed completion helper accepted a blocked artifact")
        relay = subprocess.run([str(root / "scripts/relay.sh")], cwd=work, env=env, capture_output=True)
        require(relay.returncode == 2 and b"usage:" in relay.stderr.lower(), "installed relay entry point failed")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path, help="publisher outcome; downloads the public artifact")
    group.add_argument("--archive", type=Path, help="local candidate; does not prove publication")
    parser.add_argument("--sha256")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    result = {"verification": "incomplete", "source_kind": "published-download" if args.record else "local-candidate"}
    if os.environ.get("GITHUB_RUN_ID") and os.environ.get("GITHUB_RUN_ATTEMPT"):
        result["run_url"] = (f"https://github.com/{OWNER}/actions/runs/{int(os.environ['GITHUB_RUN_ID'])}"
                             f"/attempts/{int(os.environ['GITHUB_RUN_ATTEMPT'])}")
    status = 0
    try:
        with tempfile.TemporaryDirectory(prefix="crew-consumer-") as directory:
            work = Path(directory).resolve()
            if args.record:
                publication = json.loads(args.record.read_text())
                require(publication.get("publication") == "published" and publication.get("eligible") is True,
                        "no verified publication eligible for consumption")
                version = publication["version"]
                from release_lib import VERSION_RE, SHA_RE, DIGEST_RE
                require(VERSION_RE.fullmatch(version) and SHA_RE.fullmatch(publication["source"]) and
                        DIGEST_RE.fullmatch(publication["sha256"]), "invalid publisher identity")
                filename = f"crew-v{version}.tar.gz"
                require(publication["archive"] == filename, "unexpected archive name")
                base = f"https://github.com/{OWNER}/releases/download/v{version}/"
                archive = work / filename
                archive.write_bytes(download(base + filename))
                checksum = publication["sha256"]
                require(download(base + "SHA256SUMS") == f"{checksum}  {filename}\n".encode(), "public checksum record differs")
            else:
                archive, checksum = args.archive, args.sha256
            manifest = exercise(archive, checksum, work)
            if args.record:
                require(manifest["source"] == publication["source"] and manifest["version"] == publication["version"],
                        "downloaded release identity differs")
            result.update(verification="passed", version=manifest["version"], source=manifest["source"], sha256=checksum)
    except (Invalid, OSError, ValueError, KeyError) as exc:
        result["error"] = str(exc)
        status = 1
    finally:
        print(json.dumps(result, sort_keys=True))
        if args.result:
            args.result.parent.mkdir(parents=True, exist_ok=True)
            args.result.write_bytes(encoded(result))
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
                stream.write("## Consumer outcome\n\n```json\n" + encoded(result).decode() + "```\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
