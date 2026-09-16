#!/usr/bin/env python3
"""Record public-consumption evidence in mutable Release notes, never assets."""

import sys
sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path

from publish import GitHub, assets_by_name
from release_lib import Invalid, OWNER, MANIFEST, require, sha256, validate_manifest


START = "<!-- crew-consumption -->"
END = "<!-- /crew-consumption -->"
PLATFORMS = ("ubuntu-latest", "macos-latest")


def record_evidence(api, publication, records, run_url, consumer_status="success"):
    require(publication.get("eligible") is True and publication.get("publication") == "published",
            "publication is not eligible for verification evidence")
    version, source, digest = (publication[k] for k in ("version", "source", "sha256"))
    release = api.release(version)
    require(release and not release["draft"] and release.get("immutable") is True,
            "published immutable release missing")
    assets = assets_by_name(release)
    manifest = validate_manifest(json.loads(api.asset_bytes(assets[MANIFEST])))
    require(manifest["version"] == version and manifest["source"] == source and api.tag(version) == source,
            "verification source differs from the release")
    require(sha256(api.asset_bytes(assets[publication["archive"]])) == digest,
            "verification archive differs from the release")
    lines = []
    require(consumer_status in {"success", "failure", "cancelled", "skipped"}, "unknown consumer job status")
    passed = consumer_status == "success"
    for platform in PLATFORMS:
        record = records.get(platform, {})
        ok = (record.get("verification") == "passed" and record.get("source_kind") == "published-download"
              and all(record.get(k) == publication[k] for k in ("version", "source", "sha256")))
        passed = passed and ok
        link = record.get("run_url", run_url)
        require(link.startswith(f"https://github.com/{OWNER}/actions/runs/") and
                all(c.isalnum() or c in ":/.-" for c in link), "invalid evidence link")
        lines.append(f"- {platform}: {'passed' if ok else 'incomplete'} (Codex and Claude layouts; [run]({link}))")
    body = release.get("body") or ""
    require(body.count(START) == body.count(END) and body.count(START) <= 1, "conflicting evidence section")
    if START in body:
        before, rest = body.split(START)
        _, after = rest.split(END)
        body = before.rstrip() + after
    section = (f"{START}\n## Public-download verification\n\n"
               f"Publication: **published**. Verification: **{'passed' if passed else 'incomplete'}**.\n\n"
               + "\n".join(lines) + f"\n\nConsumer jobs: **{consumer_status}**. [Verification attempt]({run_url})\n\n"
               "These checks use isolated homes and representative helpers. Live Herdr delivery, "
               f"permissions and fresh-agent comprehension remain unverified.\n{END}")
    desired = body.rstrip() + "\n\n" + section + "\n"
    api.request(f"/repos/{OWNER}/releases/{int(release['id'])}", "PATCH", {"body": desired})
    require(api.release(version).get("body") == desired, "Release evidence read-back differs")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication", type=Path, required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--consumer-status", choices=("success", "failure", "cancelled", "skipped"), required=True)
    args = parser.parse_args()
    try:
        require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_NAME") == "push"
                and os.environ.get("GITHUB_REF") == "refs/heads/main" and os.environ.get("GITHUB_REPOSITORY") == OWNER,
                "evidence updates require this repository's main push workflow")
        publication = json.loads(args.publication.read_text())
        records = {}
        for platform in PLATFORMS:
            path = args.records / (platform + ".json")
            if path.exists():
                records[platform] = json.loads(path.read_text())
        run_url = f"https://github.com/{OWNER}/actions/runs/{int(os.environ['GITHUB_RUN_ID'])}/attempts/{int(os.environ['GITHUB_RUN_ATTEMPT'])}"
        passed = record_evidence(GitHub(os.environ["GH_TOKEN"]), publication, records, run_url, args.consumer_status)
        print("Publication: published; public-download verification: " + ("passed" if passed else "incomplete"))
        return 0 if passed else 1
    except (Invalid, OSError, ValueError, KeyError) as exc:
        print(f"Release evidence incomplete: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
