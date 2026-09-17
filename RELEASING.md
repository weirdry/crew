# Releasing Crew

This document owns versioning, packaging, publication and release evidence.
[CONTRIBUTING.md](CONTRIBUTING.md) owns review and branch integration;
[INSTALL.md](INSTALL.md) owns the consumer's installation/check contract.
The design attachment in [issue #6](https://github.com/weirdry/crew/issues/6) is a
planning snapshot; these repository documents and executable tools are the
implementation authority.

## One unit and one version

`VERSION` contains one numeric `X.Y.Z`. The tag is `vX.Y.Z`, and
`CHANGELOG.md` must have exactly one nonempty `## X.Y.Z` section for it.
The first governed release is **0.1.0**, an early development release. Preparing
that value on `dev` does not publish it or claim stable 1.0 compatibility.

Use SemVer deliberately: during 0.x, incompatible behavior or new capabilities
normally advance the minor version; compatible corrections advance the patch.
After 1.0, incompatible released behavior advances the major version. Explain
user-visible changes, installation effects and known limits in the changelog.
Do not turn each development commit into a release version. Changes accumulated
before a version is published evolve together in place. Existing installed copies
and retained state still require concrete compatibility assessment.

The same published tag is also an installation source for the existing Skills
CLI. [INSTALL.md](INSTALL.md) makes that the primary user path; the managed
archive remains available with its original ownership and content-checking
contract. Skill installers do not consume the archive's marker or checksum.
Preserve published tags/assets and the managed installer when improving user
guidance; do not adopt existing installations implicitly.

The allowlist in `tools/release/package.py` includes:

- `skills/crew/SKILL.md`, supported helper scripts, references and templates,
  installed as the complete `skill/` directory;
- `install.py` and its standard-library `release_lib.py`, for installation/checks;
- `VERSION`, `CHANGELOG.md`, `INSTALL.md` and `LICENSE`.

The packaging implementation also participates in the release-input digest.
Tests, CI, publisher code, repository-only documentation and real runtime data
are not payload files. An unknown file under the skill requires an explicit
packaging decision. File bytes, paths and executable modes are recorded. Input
changes require a newer version than the one on `main`; README-only or workflow
changes can keep the same version when all release inputs remain identical.

The build reads a **clean exact Git commit**, never unstaged working files. It
produces deterministic tar/gzip bytes with fixed ordering, timestamps and owners.
The same commit produces the same archive. Archives have a 16 MiB compressed and
expanded-content bound, comfortably above this sub-1 MiB payload; it is a basic
input-safety bound, not a capacity target.

## Candidate and published artifacts

From a clean checkout, select a new output directory outside the repository:

```sh
python3 -B tools/release/package.py --output /absolute/disposable/candidate
```

There are three published assets:

| Asset | Meaning |
| --- | --- |
| `crew-vX.Y.Z.tar.gz` | The one installable payload |
| `SHA256SUMS` | SHA-256 of that archive, with its exact filename |
| `release.json` | Version, repository owner, exact source commit, source-input digest, and file/mode inventory |

The archive contains the same `release.json`. The manifest excludes itself from
its payload hash. The checksum is external to the archive, avoiding a circular
hash. `release-notes.md` is a fourth **CI candidate file** generated from the
changelog; it becomes the Release body, not another published asset. The installed
`.crew-install.json` is generated from the verified manifest and hashes the skill
files, excluding itself. These identities serve different purposes.

Checksums detect drift; they are not independent signatures. Consumers trust the
official GitHub HTTPS repository and its immutable publication. Asset verification
checks actual downloaded bytes and inventory, not just marker claims.

## Before the first promotion

The release workflow can bootstrap from the first push that adds it to `main`.
It does not need a dispatch workflow already present on the default branch.
Before authorizing that push, the maintainer must:

1. Review and integrate the implementation into `dev`, complete hosted CI, and
   verify the intended `VERSION` and changelog against the accumulated changes.
2. Enable **native GitHub immutable releases** for `weirdry/crew`, then read back
   the setting using an account with repository Administration access. Confirm
   `enabled: true` (and record any owner enforcement):

   ```sh
   gh api --method PUT repos/weirdry/crew/immutable-releases
   gh api repos/weirdry/crew/immutable-releases
   ```

3. Confirm Actions is enabled and the workflow token may receive `contents: write`
   for the publisher and evidence jobs. Inspect any repository/organization tag
   rules that could prevent creating `vX.Y.Z` or conflict with immutability.
4. Record the setting read-back and reviewed source in the promotion handoff.
   Use the existing fast-forward-only promotion procedure.

The immutable-releases setting endpoint requires **Administration read**, which
is not granted by the workflow's contents-only token. The workflow therefore
does not pretend to perform that pre-promotion administrative check or require
an administration PAT. It verifies `immutable: true` on the published Release
and fails if enforcement was not active. Such a failure can occur **after
publication**; it is not a rollback or proof that nothing was published. Enabling
the native setting and recording its read-back before promotion is required.

These are hosted setup actions. Committing the workflow does not enable the
setting, configure branch protection, publish a release, or update a workstation.

## Workflow and authority

[CI](.github/workflows/ci.yml) runs on PRs to `dev`/`main` and pushes to `dev`.
It tests Python 3.11 on Linux/macOS and Python 3.14 on Linux, with read-only
repository permissions. It runs the existing helper suite, focused release tests,
version policy, candidate packaging and isolated consumption.
The Python 3.11 Linux/macOS jobs also exercise the documented Skills CLI against
the published tag selected in `tests/skill-installers.py`. That check proves the
existing installation path; it does not publish or validate a future unpublished
tag, and does not replace candidate or public-archive consumption.

[Release](.github/workflows/release.yml) runs only on a push to `main`:

1. **Validate:** rerun checks, build once from `github.sha`, consume that candidate
   locally, and retain the exact candidate as a workflow artifact.
2. **Publish:** download the retained artifact by ID; verify its source and all
   candidate files. Create/verify the tag at that exact commit. Create or resume
   a draft, upload only missing matching assets, verify every asset by reading
   it back, then publish and verify immutable source/tag/asset identity.
3. **Consume:** without publication credentials, download the actual public
   archive and checksum. On Linux and macOS, use fresh homes to install both
   Codex and Claude layouts, repeat installation, check all installed content,
   and execute representative completion and relay helper checks.
4. **Record evidence:** after both consumer jobs finish, update only the mutable
   Release notes with separate publication and per-platform verification results,
   exact run links, and live-validation limits. Missing or failed consumer results
   remain **incomplete**. The tag and assets are never rewritten by this step.

Only the publisher and final note-writing job have `contents: write`. Credentials
are passed only to their designated Python commands; checkout does not persist
credentials. Public consumers do not send those credentials. API redirects remove
Authorization when changing hosts. Third-party actions are pinned to full SHAs.
Publication is serialized with `cancel-in-progress: false`. GitHub concurrency
can replace an older **pending** run; it does not cancel the active publisher.
Inspect skipped/pending runs before assuming every main commit published.

Job records are retained as workflow artifacts and summaries. Release notes keep
the verification verdict and run links after transient artifacts expire. A failed
note update leaves the previous notes plus the producing-run link; the workflow
is incomplete until the evidence step is retried successfully. Never infer a
completed release from an uploaded archive alone.

## After publication

The README's installation command owns the current verified release selection.
After publication and public consumption succeed, update that command, `TAG` in
`tests/skill-installers.py`, and the test prerequisites in `tests/README.md`
together on `dev`, then rerun the installer smoke test. These repository-only
files are not release inputs. A routine tag refresh leaves `VERSION`,
`CHANGELOG.md` and `INSTALL.md` unchanged; it does not prepare another release.

`INSTALL.md` is the versioned installation contract shipped in the archive. Its
concrete tag examples are fixed, valid published selections and may be older
than the README's current recommendation. Do not refresh those packaged examples
solely because another tag was published. A deliberate change to the packaged
installation contract still participates in a reviewed release with a newer
version, just like any other release-input change. When another release-input
change requires the next release, refresh these examples to the latest published
tag with completed public-download verification as part of the same
version/changelog update. Keep dated historical evidence and published tags/assets
unchanged.

When the repository-only refresh is later promoted to `main`, the existing
publisher verifies the original publication and reports `publication: unchanged`.
It preserves the original source, archive digest, assets and consumer evidence;
it does not publish the later commit's candidate or rerun consumption for it.
Prepare the next version and changelog only when intended release inputs change.
If a routine tag refresh alone accidentally prepared an unpublished version,
withdraw it in a follow-up commit by restoring that refresh's release-input
changes to the published baseline. Preserve independent pending release work;
published versions are never rewritten.

## Retry and correction rules

Inspect the failed run and the actual remote tag, Release, and assets before
retrying. Rerun the **same source workflow**, including all jobs when uncertain.
GitHub's failed-job retry can reuse successful dependencies: artifact names are
stable within a run, and an actually rerun stage replaces only its own transient
workflow artifact. Successful consumer records identify their own attempts.
The evidence job also requires the consumer jobs to have succeeded, so an older
record cannot hide a new setup/download failure before an outcome file was written.
If artifacts have expired, rerun all jobs for that source.

| Observed state | Behavior |
| --- | --- |
| No tag/Release | Create exact tag and draft, attach and verify all assets, publish |
| Matching tag, no Release | Continue with the draft |
| Matching partial draft | Preserve matching uploads and upload missing assets only |
| Draft contains an empty `starter` asset after an upload failure | Stop for the explicit operator recovery below; do not delete automatically |
| Wrong source, conflicting bytes, duplicate or unexpected assets | Stop; preserve evidence and resolve deliberately |
| Exact source already published and immutable | Verify existing bytes, then retry public consumption |
| Publication succeeded but consumption failed | Keep it published; report verification incomplete and retry consumption/evidence |
| Same version on a later main commit, all release inputs unchanged | Verify the original publication and skip; preserve its original source and verification evidence |
| Same version with changed inputs | Refuse; prepare a correction version through `dev` |

A lost response can follow a successful remote mutation. It is reported as an
attempt requiring inspection; the next run reads remote state before continuing.
Never delete/recreate a tag, replace a published asset, silently force a draft
conflict, or report a published-but-unverified version as unpublished. If the
artifact itself is defective, publish a reviewed correction version. A docs-only
push does not repair an earlier incomplete consumer run; retry that original run.

### Empty draft upload after a 502

GitHub documents that an upload returning `502 Bad Gateway` can leave an empty
asset in the `starter` state. This is an incomplete upload, not a published
artifact correction. The publisher refuses it and names the asset; it never
deletes remote assets automatically.

Before recovery, preserve the failed run and asset metadata, then verify that the
Release is still a **draft**, is not immutable, and its tag and source match the
candidate. Confirm the specific asset ID, expected filename, `state: starter`,
and `size: 0`. Obtain explicit maintainer authorization to delete **only that
empty asset**, recheck these conditions immediately before deletion, and rerun
the same source workflow. Existing matching uploads remain intact, and the
missing asset is uploaded and verified through the normal draft path.

This procedure does not authorize deleting nonempty, uploaded, unexpected or
published assets, altering a tag, or removing a whole Release. If any condition
differs, preserve the conflict and investigate it. See GitHub's
[upload failure documentation](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset).

## Acceptance and limits

Implementation, hosted CI, `dev` integration, `main` promotion, publication,
public-download consumption, normal installation and live operation are separate.
Each release requires publication and public-download consumption evidence;
passing candidate tests or integrating into `dev` is insufficient.

The first governed release, [v0.1.0](https://github.com/weirdry/crew/releases/tag/v0.1.0),
completed on 2026-09-17. Its
[release workflow](https://github.com/weirdry/crew/actions/runs/35200530242)
verified publication, native immutability and public-download consumption on
Linux and macOS. [Issue #6](https://github.com/weirdry/crew/issues/6) closed with
that evidence.

Synthetic tests do not prove GitHub permissions, native immutability or public
asset propagation. Each actual release must establish those hosted outcomes.
Isolated consumer checks prove installation/content and representative helper
execution; they do not prove actual host discovery, model comprehension, live
Herdr delivery, permission dialogs or worker sandbox access to the lead's state.
Those limits remain explicit in the release notes. No release job starts agents,
installs into a normal workstation, or reads/writes retained Crew runtime state.

References: [GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases),
[repository setting API](https://docs.github.com/en/enterprise-cloud@latest/rest/repos/repos#check-if-immutable-releases-are-enabled-for-a-repository),
and [Release API](https://docs.github.com/en/rest/releases/releases).
