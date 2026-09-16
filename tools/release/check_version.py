#!/usr/bin/env python3
"""Reject unchanged or regressed versions when promoted release inputs change."""

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path
import subprocess

from package import git, input_digest
from release_lib import Invalid, VERSION_RE, require


def check(root, base):
    current = git(root, "show", "HEAD:VERSION").decode().strip()
    require(VERSION_RE.fullmatch(current), "invalid candidate VERSION")
    # Validate the base ref independently; an unknown ref must not look like bootstrap.
    git(root, "rev-parse", "--verify", base + "^{commit}")
    paths = git(root, "ls-tree", "--name-only", base).decode().splitlines()
    if "VERSION" not in paths:
        return "initial release"
    previous = git(root, "show", base + ":VERSION").decode().strip()
    require(VERSION_RE.fullmatch(previous), "invalid promoted VERSION")
    old, new = tuple(map(int, previous.split("."))), tuple(map(int, current.split(".")))
    require(new >= old, "VERSION regressed")
    if input_digest(root, base) != input_digest(root, "HEAD"):
        require(new > old, "release inputs changed; prepare a newer VERSION and changelog before promotion")
    return "release version checked"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args()
    try:
        print(check(Path(__file__).resolve().parents[2], args.base))
    except (Invalid, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(2, f"version: {exc}\n")
