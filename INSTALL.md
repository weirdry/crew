# Installing Crew

## Recommended: Skills CLI

For a new personal installation in Codex and Claude Code:

```sh
npx skills@1.6.0 add 'weirdry/crew#v0.1.0' -g -a codex claude-code
```

Skills CLI fetches the selected Git tag and installs `skills/crew`, including
its helpers, references and templates. Keep the confirmation prompts and review
the destinations. This example selects the already published **v0.1.0**;
choose another published tag from [Releases](https://github.com/weirdry/crew/releases)
when deliberately updating. `skills@1.6.0` pins the installation tool;
`#v0.1.0` independently pins Crew. Do not use `weirdry/crew@v0.1.0`:
the `@` shorthand selects a skill name, not a Git tag.

Installation requires Node.js **22.20+**, npm, Git and GitHub network access.
Crew itself needs Python **3.11+**, a POSIX shell and macOS or Linux. For actual
collaboration, use a Git workspace inside Herdr with two supported agent kinds
installed locally. Installation alone does not establish live Herdr behavior.

If Crew is already installed, follow [Existing installations](#existing-installations)
before running `add`. Finish affected Crew work before changing any installation;
use a fresh agent session afterwards.

With the tested Skills CLI version and default settings, the canonical files are
in `~/.agents/skills/crew` (read by Codex), and `~/.claude/skills/crew` links to
that directory. Its global source/ref record is `~/.agents/.skill-lock.json`.
Custom host configuration can change destinations; inspect the CLI's summary.

List the installation with:

```sh
npx skills@1.6.0 list -g
```

Then confirm Crew appears in a fresh host's skill selector. Listing proves
discovery by the installer, not a content-integrity check or live host operation.

### Selecting and updating a version

The recommended command stays on the selected tag.
`npx skills@1.6.0 update crew -g` checks the recorded ref; it does not select a
newer Crew release tag. Bare
`weirdry/crew` follows the repository's default branch and is not the pinned
release path described here.

To change versions, review the new Release, preserve local edits and end affected
Crew sessions, then repeat the `add` command with the chosen published `#vX.Y.Z`.
Re-adding can replace local files; it is not the archive installer's repeat no-op
or modified-content refusal. `skills update` can report "up to date" despite
local edits because it checks the source version, not all installed bytes.

### Codex-only alternative

If Codex provides `$skill-installer`, ask it:

```text
$skill-installer Install skills/crew from weirdry/crew at tag v0.1.0 using the Git method (--method git). Preserve any existing installation and report its destination.
```

The tested helper preserves executable permissions with `--method git` and
refuses an existing destination. Its default is `$CODEX_HOME/skills/crew`
(normally `~/.codex/skills/crew`); it does not install for Claude. Avoid its ZIP
`download`/`auto` path for Crew: the tested helper lost executable bits and direct
helper execution failed. This finding applies to the helper revision recorded in
the [installation evidence linked from issue #8](https://github.com/weirdry/crew/issues/8),
not every future Codex version. Follow the installer agent's reload guidance.

## Existing installations

Choose one installation owner. Skills CLI and the Codex installer do not create
`.crew-install.json`; the archive installer's `check` will report their layouts
as `conflicting`, not damaged Crew content. Its preservation/refusal rules remain
unchanged. Do not run Skills CLI over a managed archive installation, a development
link or locally edited files and expect those rules to protect them.

Before changing methods, inspect all existing Crew entries in `~/.agents/skills`,
`~/.codex/skills`, `~/.claude/skills` and any configured extra roots. End affected
sessions, preserve the current directory and edits outside all skill discovery
roots, and deliberately retire the previous entries. For a development link,
confirm its target and remove only the link, preserving the checkout. For a
Skills CLI installation, use its removal command after backing up the canonical
directory; Claude may share that directory with Codex. Never remove Crew runtime
state as part of this operation. No automatic adoption or migration is provided.

## Alternative: managed release archive

Use this path when you want Crew's installed-content checker, modified-content
refusal and whole-directory managed updates. The published v0.1.0 installer and
archive contract remain supported. A release archive and a Git-tag installation
contain the same skill at that source, but have different packaging and ownership
metadata. Skills CLI does not verify the release archive's `SHA256SUMS`.

### Archive prerequisites

- Python **3.11 or newer**, a POSIX shell and standard POSIX utilities.
- macOS or Linux. CI checks Python 3.11 on both and Python 3.14 on Linux; the
  archive contains no native binaries. Native Windows is not supported.
- For collaboration: Herdr, locally installed Codex and Claude Code (or another
  supported worker kind), a Git workspace and a session inside Herdr.
- Downloading needs HTTPS access to GitHub, `curl`, and `tar`. Installation and
  checking use only Python's standard library, without a package registry.

Installation does not prove live Herdr behavior. Finish Crew work that uses the
old installation before changing it, and start a fresh agent session afterwards.

### First archive installation or managed update

Select an exact release from GitHub. Check its tag, source commit, maturity,
known limitations and public-download verification evidence. The following
example uses the published 0.1.0 release.

Run in a new, disposable download directory:

```sh
(
set -eu
crew_version=0.1.0
crew_url="https://github.com/weirdry/crew/releases/download/v${crew_version}"
curl --fail --location --output "crew-v${crew_version}.tar.gz" \
  "${crew_url}/crew-v${crew_version}.tar.gz"
curl --fail --location --output SHA256SUMS "${crew_url}/SHA256SUMS"
# Available on macOS and Linux; compare with the Release's recorded digest too.
shasum -a 256 -c SHA256SUMS
# Continue only if the checksum succeeds. Extract the verified official archive.
mkdir payload
tar -xzpf "crew-v${crew_version}.tar.gz" -C payload
python3 -B payload/install.py install --host all --inactive
python3 -B payload/install.py check --host all
)
```

Choose `--host codex` or `--host claude` for just one host. `--inactive` asserts
that you have ended affected Crew sessions; the installer cannot inspect every
agent's context or every workspace's active runs. It does not stop agents.
Keep the extracted release when you want to run its checker again. To update,
download and verify the new exact version and run **its** installer and checker.
No permanently installed global CLI or unchecked mutable bootstrap is required.

The installer verifies the entire extracted payload before examining host
installations. The archive digest and installed-content digest are distinct.
The extraction command preserves the archive's file modes even with a restrictive
umask such as `077`; the installer checks those modes as part of file identity.
Checksums detect corruption or drift; trust in the official release comes from
GitHub's HTTPS identity and immutable release/tag/assets, not a local marker.

### Archive destinations and duplicate detection

| Host | Default personal skill directory |
| --- | --- |
| Codex | `~/.agents/skills/crew` |
| Claude Code | `~/.claude/skills/crew` |

`--home /absolute/test-home` supplies an isolated home. `--codex-root` and
`--claude-root` select **skill-root directories**; the installer appends `/crew`.
Use `--extra-skill-root` repeatedly for other known roots that should be checked
for conflicting Crew installations. Explicitly configure such roots in the host
if necessary; creating a directory alone does not configure discovery.

The installer checks the default personal location, the selected location,
Codex's legacy `~/.codex/skills/crew`, the current user's `CODEX_HOME/skills/crew`
when applicable, `/etc/codex/skills/crew`, declared extra roots, and the current
workspace's ancestor skill locations. It does not inventory unrelated workspaces,
plugins, enterprise policy or every host-specific custom discovery setting.
Review the host's skill selector in a fresh session for those additional sources.

Home and skill-root paths are resolved before inspecting installations. This
supports macOS aliases such as `/tmp` and `/var/tmp`, and dotfile-managed roots
such as a symlinked `~/.claude`. Paths to the same resolved skill root count as
one location, including defaults, selected roots and declared extra roots.
The reported destination is the canonical root followed by `/crew`.

Any other Crew location is reported before that host is written. The final
`crew` directory is never resolved through a symlink: development links remain
conflicts, including a separate discovery entry that points to a managed copy.
The installer keeps the resolved destination for the operation and rechecks its
parents before writing; a parent that has become a symlink is refused.

### Archive read-only check results

Commands print one JSON object with `results`, one entry per selected host.
Entries identify `host`, `destination`, `status`, and applicable release identity
or `reason`/`conflicts`. Exit **0** means every selected host is current; **1**
means at least one is missing, stale, modified, conflicting or failed; **2**
means invalid arguments or an invalid/unreadable release payload.

| Status | Meaning | Install behavior |
| --- | --- | --- |
| `current` | Exact requested release and all installed files/modes match | No-op |
| `missing` | No destination | Install after `--inactive` |
| `stale` | Recognized, unmodified installation of another version | Replace as a complete directory after `--inactive` |
| `modified` | Files, paths or modes differ from the stored inventory | Preserve and refuse |
| `conflicting` | Unmanaged/invalid owner, symlink, duplicate root, or reused version identity | Preserve and refuse |
| `error` | A requested operation failed | Report; inspect any retained transaction before retrying |

`.crew-install.json` records owner, host, version, source, release digest and the
installed inventory. It is excluded from the installed-content hash; it is an
ownership record, not a security credential. Checks enumerate actual files.
Each host succeeds or fails independently. The two-host command is not atomic.

### Archive conflicts and interrupted updates

There is no force/adopt switch. If an old unmanaged copy or development link
exists, the installer leaves it in place and names it. End affected sessions,
inspect the path and preserve any local changes. Then explicitly move an old
copy to a backup outside all discovery roots, or remove **only the symlink**
after confirming its target. Do not delete the development checkout. These are
deliberate operator actions, never automatic installer cleanup.

Managed updates stage a complete new directory under the selected skill root,
serialize this installer's writers with `.crew-install.lock`, and retain the
old installation until the replacement passes its content check. A failed
pre-replacement operation restores the old directory where possible. A crash
or failed restoration may leave `.crew-install-pending/{new,previous}`. Further
updates refuse that pending directory. Inspect it and the destination, keep
the valid copy and local changes, and explicitly finish recovery before retrying.
An uncooperative writer can still race an update; end sessions as instructed.

No operation touches Crew run data, external state roots, approval records,
partner receipts or workspace artifacts. Selecting an older release does not
establish that it can read newer retained state; check concrete compatibility
before deliberately installing an older version.

Host discovery references: [Codex](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)
and [Claude Code](https://code.claude.com/docs/en/skills#where-skills-live).
