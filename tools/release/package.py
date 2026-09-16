#!/usr/bin/env python3
"""Build a deterministic archive from a clean, exact Git commit."""

import sys
sys.dont_write_bytecode = True

import argparse
import fnmatch
import gzip
import io
import json
from pathlib import Path
import subprocess
import tarfile

from release_lib import (Invalid, MANIFEST, OWNER, VERSION_RE, content_digest,
                         encoded, record, require, sha256, validate_manifest)


PAYLOAD = {
    "VERSION": "VERSION", "LICENSE": "LICENSE", "INSTALL.md": "INSTALL.md",
    "CHANGELOG.md": "CHANGELOG.md", "tools/release/install.py": "install.py",
    "tools/release/release_lib.py": "release_lib.py",
}
SKILL_PATTERNS = ("SKILL.md", "scripts/*.sh", "scripts/*.py", "references/*.md", "templates/*.md")
# Packaging code participates in release identity even when not distributed.
BUILD_INPUTS = {"tools/release/package.py"}


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE)


def release_inputs(root, source):
    files = {}
    mapping = dict(PAYLOAD)
    for entry in git(root, "ls-tree", "-rz", source).split(b"\0"):
        if not entry:
            continue
        metadata, raw_path = entry.split(b"\t", 1)
        path = raw_path.decode()
        mode, kind, blob = metadata.decode().split()
        if path.startswith("skills/crew/"):
            rel = path.removeprefix("skills/crew/")
            require(any(fnmatch.fnmatchcase(rel, pattern) for pattern in SKILL_PATTERNS)
                    and not any(part.startswith(".") for part in Path(rel).parts),
                    f"skill file needs an explicit packaging decision: {path}")
            mapping[path] = "skill/" + rel
        if path in mapping or path in BUILD_INPUTS:
            require(kind == "blob" and mode in ("100644", "100755"), f"unsupported source entry: {path}")
            files[path] = (git(root, "cat-file", "blob", blob), int(mode[-3:], 8))
    require(set(PAYLOAD) | BUILD_INPUTS <= set(files), "release source files missing")
    require("skills/crew/SKILL.md" in files, "skill entry missing")
    return files, mapping


def input_digest(root, source):
    files, _ = release_inputs(root, source)
    return content_digest({p: record(*value) for p, value in files.items()})


def build(root, output):
    root, output = Path(root), Path(output)
    require(not git(root, "status", "--porcelain"), "build requires a clean Git checkout")
    source = git(root, "rev-parse", "HEAD").decode().strip()
    files, mapping = release_inputs(root, source)
    version = files["VERSION"][0].decode().strip()
    require(VERSION_RE.fullmatch(version), "VERSION must contain X.Y.Z")
    require(files["VERSION"][0] == (version + "\n").encode(), "VERSION must end with one newline")
    changelog = files["CHANGELOG.md"][0].decode()
    header = f"## {version}\n"
    require(changelog.count(header) == 1, "CHANGELOG entry missing or duplicated")
    notes = changelog.split(header, 1)[1].split("\n## ", 1)[0].strip()
    require(bool(notes), "empty release notes")
    payload = {mapping[p]: value for p, value in files.items() if p in mapping}
    inventory = {p: record(*value) for p, value in payload.items()}
    manifest = validate_manifest({
        "schema": 1, "owner": OWNER, "version": version, "source": source,
        "inputs_sha256": input_digest(root, source), "files": inventory,
        "content_sha256": content_digest(inventory),
    })
    payload[MANIFEST] = (encoded(manifest), 0o644)
    output.mkdir(parents=True, exist_ok=True)
    require(not any(output.iterdir()), "output directory must be empty")
    name = f"crew-v{version}.tar.gz"
    buffer = io.BytesIO()
    # Fixed timestamps/owners/modes; no workflow time or local paths in the archive.
    with gzip.GzipFile(fileobj=buffer, filename="", mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT) as tar:
            for path, (data, mode) in sorted(payload.items()):
                entry = tarfile.TarInfo(path)
                entry.mode, entry.size, entry.mtime = mode, len(data), 0
                tar.addfile(entry, io.BytesIO(data))
    archive = buffer.getvalue()
    (output / name).write_bytes(archive)
    (output / "SHA256SUMS").write_text(f"{sha256(archive)}  {name}\n")
    (output / MANIFEST).write_bytes(encoded(manifest))
    (output / "release-notes.md").write_text(notes + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(__file__).resolve().parents[2], args.output), sort_keys=True))
    except (Invalid, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"package: {exc}\n")


if __name__ == "__main__":
    main()
