#!/usr/bin/env python3
"""Publish validated main artifacts; never rebuild or overwrite release assets."""

import sys
sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from release_lib import (Invalid, MANIFEST, OWNER, MAX_BYTES, encoded, read_archive,
                         require, sha256, validate_manifest)


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        require(urllib.parse.urlsplit(newurl).scheme == "https", "insecure GitHub redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).netloc != urllib.parse.urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, token):
        self.token = token

    def request(self, path, method="GET", data=None, *, binary=False, missing=False):
        host = "https://uploads.github.com" if path.startswith("/upload/") else "https://api.github.com"
        path = path.removeprefix("/upload")
        headers = {"Accept": "application/octet-stream" if binary and method == "GET" else "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "crew-release"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if data is not None:
            headers["Content-Type"] = "application/octet-stream" if binary else "application/json"
            data = data if binary else encoded(data)
        try:
            response = urllib.request.build_opener(PublicRedirect()).open(
                urllib.request.Request(host + path, data=data, headers=headers, method=method), timeout=60)
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "GitHub response too large")
            return raw if binary and method == "GET" else json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if missing and exc.code == 404:
                return None
            raise Invalid(f"GitHub {method} failed with HTTP {exc.code}") from None
        except urllib.error.URLError:
            raise Invalid(f"GitHub {method} response unavailable; inspect remote state before retrying") from None

    def tag(self, version):
        ref = self.request(f"/repos/{OWNER}/git/ref/tags/v{version}", missing=True)
        if ref is None:
            return None
        obj = ref["object"]
        if obj["type"] == "tag":
            obj = self.request(f"/repos/{OWNER}/git/tags/{obj['sha']}")["object"]
        require(obj["type"] == "commit", "tag does not identify a commit")
        return obj["sha"]

    def release(self, version):
        # Authenticated listing includes drafts; tag lookup alone can miss them.
        page = 1
        matches = []
        while True:
            releases = self.request(f"/repos/{OWNER}/releases?per_page=100&page={page}")
            matches.extend(r for r in releases if r["tag_name"] == "v" + version)
            if len(releases) < 100:
                break
            page += 1
        require(len(matches) <= 1, "duplicate release records")
        return matches[0] if matches else None

    def asset_bytes(self, asset):
        return self.request(f"/repos/{OWNER}/releases/assets/{int(asset['id'])}", binary=True)


def candidate(directory):
    manifest = validate_manifest(json.loads((directory / MANIFEST).read_text()))
    name = f"crew-v{manifest['version']}.tar.gz"
    require({p.name for p in directory.iterdir()} == {name, "SHA256SUMS", MANIFEST, "release-notes.md"},
            "unexpected candidate inventory")
    checksum = sha256((directory / name).read_bytes())
    require((directory / "SHA256SUMS").read_text() == f"{checksum}  {name}\n", "candidate checksum file mismatch")
    inside, _, _ = read_archive(directory / name, checksum)
    require(manifest == inside and (directory / MANIFEST).read_bytes() == encoded(inside), "candidate manifest mismatch")
    return manifest, {name: (directory / name).read_bytes(), "SHA256SUMS": (directory / "SHA256SUMS").read_bytes(),
                      MANIFEST: (directory / MANIFEST).read_bytes()}


def assets_by_name(release):
    assets = release["assets"]
    result = {asset["name"]: asset for asset in assets}
    require(len(result) == len(assets), "duplicate release asset names")
    return result


def verify_assets(api, release, expected, complete=True):
    assets = assets_by_name(release)
    require(set(assets) <= set(expected), "unexpected remote release assets")
    if complete:
        require(set(assets) == set(expected), "required remote assets missing")
    for name, asset in assets.items():
        require(asset["state"] == "uploaded" and api.asset_bytes(asset) == expected[name],
                f"remote asset conflict: {name}; preserve it and use a correction version")


def published_identity(api, release, manifest, expected):
    require(isinstance(release, dict) and release.get("immutable") is True and not release["draft"],
            "published release missing or not immutable")
    require(api.tag(manifest["version"]) == manifest["source"], "published tag/source conflict")
    verify_assets(api, release, expected)


def publish(api, directory, source, run_url, result):
    manifest, expected = candidate(directory)
    version = manifest["version"]
    require(source == manifest["source"], "candidate does not match the validated workflow commit")
    result.update(version=version, source=source, archive=f"crew-v{version}.tar.gz",
                  sha256=sha256(expected[f"crew-v{version}.tar.gz"]), run_url=run_url)
    tag = api.tag(version)
    release = api.release(version)
    if release and not release["draft"]:
        result.update(publication="published", verification="incomplete", release_url=release["html_url"])
        assets = assets_by_name(release)
        require(MANIFEST in assets, "published manifest missing")
        previous = validate_manifest(json.loads(api.asset_bytes(assets[MANIFEST])))
        require(previous["version"] == version and tag == previous["source"], "existing release identity conflict")
        require(previous["inputs_sha256"] == manifest["inputs_sha256"] and
                previous["files"] == manifest["files"], "released inputs changed without a new version")
        if previous["source"] != source:
            # A documentation-only main push must preserve the older source identity.
            require(set(assets) == set(expected), "published assets missing or unexpected")
            old_bytes = {name: api.asset_bytes(asset) for name, asset in assets.items()}
            import tempfile
            with tempfile.TemporaryDirectory(prefix="crew-published-") as temp:
                archive = Path(temp) / result["archive"]
                archive.write_bytes(old_bytes[result["archive"]])
                digest = sha256(archive.read_bytes())
                require(old_bytes["SHA256SUMS"] == f"{digest}  {archive.name}\n".encode(), "published checksum conflict")
                original, _, _ = read_archive(archive, digest)
                require(original == previous, "published manifests disagree")
            published_identity(api, release, previous, old_bytes)
            result.update(publication="unchanged", source=previous["source"], sha256=digest,
                          verification="not-requested", release_url=release["html_url"])
            return
        published_identity(api, release, manifest, expected)
    else:
        require(tag is None or tag == source, "existing tag belongs to another source")
        if release:
            require(release["target_commitish"] == source, "draft source conflict")
            verify_assets(api, release, expected, complete=False)
        if tag is None:
            result["publication"] = "attempted"
            api.request(f"/repos/{OWNER}/git/refs", "POST", {"ref": "refs/tags/v" + version, "sha": source})
        require(api.tag(version) == source, "tag read-back conflict")
        if release is None:
            result["publication"] = "attempted"
            notes = (directory / "release-notes.md").read_text().strip()
            notes += (f"\n\nSource: `{source}`\n\nArchive SHA-256: `{result['sha256']}`\n\n"
                      f"[Producing validation run]({run_url})\n\n"
                      "Publication and public-download verification are separate. See this run's consumer jobs; "
                      "an upload alone is not completed verification.\n")
            release = api.request(f"/repos/{OWNER}/releases", "POST", {
                "tag_name": "v" + version, "target_commitish": source, "name": "Crew " + version,
                "body": notes, "draft": True, "prerelease": False,
            })
        present = assets_by_name(release)
        for name, data in expected.items():
            if name not in present:
                result["publication"] = "attempted"
                api.request(f"/upload/repos/{OWNER}/releases/{int(release['id'])}/assets?name={urllib.parse.quote(name)}",
                            "POST", data, binary=True)
        release = api.release(version)
        require(release is not None and release["draft"], "draft changed during upload")
        verify_assets(api, release, expected)
        require(api.tag(version) == source, "tag changed during upload")
        result["publication"] = "attempted"
        published = api.request(f"/repos/{OWNER}/releases/{int(release['id'])}", "PATCH", {"draft": False})
        # Record the irreversible outcome before subsequent verification can fail.
        if published and not published["draft"]:
            result.update(publication="published", verification="incomplete", release_url=published["html_url"])
        release = api.release(version)
        if release and not release["draft"]:
            result["publication"] = "published"
            result["verification"] = "incomplete"
            result["release_url"] = release["html_url"]
        published_identity(api, release, manifest, expected)
    result.update(publication="published", verification="pending", eligible=True,
                  release_url=release["html_url"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    result = {"publication": "not-attempted", "verification": "not-started", "eligible": False}
    status = 0
    try:
        require(os.environ.get("GITHUB_ACTIONS") == "true" and
                os.environ.get("GITHUB_EVENT_NAME") == "push" and
                os.environ.get("GITHUB_REF") == "refs/heads/main" and
                os.environ.get("GITHUB_REPOSITORY") == OWNER, "publication is only authorized by this repository's main push workflow")
        require(bool(os.environ.get("GH_TOKEN")), "publication credential missing")
        run_url = f"https://github.com/{OWNER}/actions/runs/{int(os.environ['GITHUB_RUN_ID'])}"
        publish(GitHub(os.environ["GH_TOKEN"]), args.candidate, os.environ["GITHUB_SHA"], run_url, result)
    except (Invalid, ValueError, KeyError, OSError) as exc:
        result["error"] = str(exc)
        status = 1
    finally:
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_bytes(encoded(result))
        print(json.dumps(result, sort_keys=True))
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
                stream.write(f"eligible={str(result['eligible']).lower()}\n")
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
                stream.write("## Publication outcome\n\n```json\n" + encoded(result).decode() + "```\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
