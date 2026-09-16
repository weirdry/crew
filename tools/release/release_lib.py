"""Shared archive and content checks. Python standard library only."""

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import zlib


OWNER = "weirdry/crew"
MANIFEST = "release.json"
MARKER = ".crew-install.json"
VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
# This payload is currently below 1 MiB. Bound untrusted archive expansion.
MAX_BYTES = 16 * 1024 * 1024


class Invalid(ValueError):
    """A release or installation does not satisfy its recorded identity."""


def require(condition, message):
    if not condition:
        raise Invalid(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    require(isinstance(name, str) and bool(name), "empty or invalid file path")
    p = PurePosixPath(name)
    require(name != "." and not p.is_absolute() and p.as_posix() == name and
            all(part not in (".", "..") for part in p.parts) and
            not any(c in name for c in "\\\x00\r\n:"), f"unsafe path: {name!r}")
    return name


def record(data, mode):
    return {"sha256": sha256(data), "mode": mode}


def content_digest(files):
    return sha256(encoded(files))


def validate_inventory(files):
    require(isinstance(files, dict) and files, "invalid file inventory")
    folded = set()
    spellings = {}
    for name, value in files.items():
        safe_name(name)
        require(name.casefold() not in folded, f"case-colliding path: {name}")
        folded.add(name.casefold())
        for component in (PurePosixPath(name), *PurePosixPath(name).parents):
            text = str(component)
            prior = spellings.setdefault(text.casefold(), text)
            require(prior == text, f"case-colliding path component: {name}")
        require(isinstance(value, dict) and set(value) == {"mode", "sha256"},
                f"invalid inventory entry: {name}")
        require(value["mode"] in (0o644, 0o755) and
                isinstance(value["sha256"], str) and DIGEST_RE.fullmatch(value["sha256"]),
                f"invalid file identity: {name}")
    for name in files:
        require(not any(str(p).casefold() in folded for p in PurePosixPath(name).parents),
                f"file/directory collision: {name}")


def validate_manifest(value):
    require(isinstance(value, dict) and set(value) == {
        "schema", "owner", "version", "source", "inputs_sha256", "files", "content_sha256"
    }, "invalid release manifest fields")
    require(value["schema"] == 1 and value["owner"] == OWNER, "unknown release owner/schema")
    require(isinstance(value["version"], str) and VERSION_RE.fullmatch(value["version"]),
            "invalid release version")
    require(isinstance(value["source"], str) and SHA_RE.fullmatch(value["source"]),
            "invalid source commit")
    require(isinstance(value["inputs_sha256"], str) and DIGEST_RE.fullmatch(value["inputs_sha256"]),
            "invalid source input digest")
    validate_inventory(value["files"])
    require(MANIFEST not in value["files"] and MARKER not in value["files"],
            "generated records cannot hash themselves")
    require(value["content_sha256"] == content_digest(value["files"]), "manifest digest mismatch")
    require({"skill/SKILL.md", "install.py", "release_lib.py", "VERSION", "INSTALL.md", "LICENSE"}
            <= set(value["files"]), "required release files missing")
    return value


def inventory(root, excluded=()):
    """Hash all regular files and reject links, special files and empty additions."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), f"not a regular directory: {root}")
    files = {}
    directories = set()
    for base, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(base) / name
            rel = path.relative_to(root).as_posix()
            st = path.lstat()
            require(not stat.S_ISLNK(st.st_mode), f"unexpected symlink: {rel}")
            if stat.S_ISDIR(st.st_mode):
                directories.add(rel)
            else:
                require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, f"not a single regular file: {rel}")
                if rel in excluded:
                    continue
                require(st.st_size <= MAX_BYTES, f"oversized file: {rel}")
                mode = stat.S_IMODE(st.st_mode)
                require(mode in (0o644, 0o755), f"unexpected permissions: {rel}")
                files[rel] = record(path.read_bytes(), mode)
    expected_dirs = {str(p) for name in files for p in PurePosixPath(name).parents if str(p) != "."}
    require(directories == expected_dirs, "unexpected empty directory")
    validate_inventory(files)
    return files


def load_payload(root):
    root = Path(root)
    manifest_path = root / MANIFEST
    require(manifest_path.is_file() and not manifest_path.is_symlink(), "release.json missing or linked")
    require(manifest_path.stat().st_size <= MAX_BYTES, "manifest too large")
    value = validate_manifest(json.loads(manifest_path.read_text()))
    require(inventory(root, (MANIFEST,)) == value["files"], "release payload content mismatch")
    require((root / "VERSION").read_text() == value["version"] + "\n", "VERSION mismatch")
    return value


def read_archive(archive, expected_sha256):
    try:
        return _read_archive(archive, expected_sha256)
    except (tarfile.TarError, EOFError, gzip.BadGzipFile, zlib.error) as exc:
        raise Invalid(f"invalid release archive: {exc}") from None


def _read_archive(archive, expected_sha256):
    archive = Path(archive)
    require(DIGEST_RE.fullmatch(expected_sha256 or ""), "a SHA-256 checksum is required")
    require(archive.stat().st_size <= MAX_BYTES, "archive too large")
    raw = archive.read_bytes()
    require(sha256(raw) == expected_sha256, "archive checksum mismatch")
    import io
    # Bound the complete tar stream, including metadata, before tarfile parses it.
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        expanded = compressed.read(MAX_BYTES + 1)
    require(len(expanded) <= MAX_BYTES, "archive expansion limit exceeded")
    files = {}
    modes = {}
    total = 0
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as tar:
        for member in tar:
            name = safe_name(member.name)
            require(name not in files and member.isfile() and member.mode in (0o644, 0o755),
                    f"unexpected archive entry: {name}")
            total += member.size
            require(0 <= member.size <= MAX_BYTES and total <= MAX_BYTES, "archive expansion limit exceeded")
            files[name] = tar.extractfile(member).read()
            modes[name] = member.mode
    require(MANIFEST in files, "archive manifest missing")
    manifest = validate_manifest(json.loads(files[MANIFEST]))
    actual = {name: record(data, modes[name]) for name, data in files.items() if name != MANIFEST}
    require(actual == manifest["files"], "archive inventory mismatch")
    require(files["VERSION"] == (manifest["version"] + "\n").encode(), "archive VERSION mismatch")
    return manifest, files, modes


def extract_verified(archive, checksum, destination):
    manifest, files, modes = read_archive(archive, checksum)
    destination = Path(destination)
    # Always create a fresh child of a caller-owned disposable directory.
    destination.mkdir(mode=0o755)
    for name, data in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(modes[name])
    return manifest
