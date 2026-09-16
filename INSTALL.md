# Installing a Crew release

Crew is one release unit: the procedure, helpers, references, templates and
installer share `VERSION`. The first governed version is **0.1.0**, an early
development release. It is prepared on `dev`; availability requires an actual
published [GitHub Release](https://github.com/weirdry/crew/releases).

## Prerequisites

- Python **3.11 or newer**, a POSIX shell and standard POSIX utilities.
- macOS or Linux. CI checks Python 3.11 on both and Python 3.14 on Linux; the
  archive contains no native binaries. Native Windows is not supported.
- For collaboration: Herdr, locally installed Codex and Claude Code (or another
  supported worker kind), a Git workspace and a session inside Herdr.
- Downloading needs HTTPS access to GitHub, `curl`, and `tar`. Installation and
  checking use only Python's standard library, without a package registry.

Installation does not prove live Herdr behavior. Finish Crew work that uses the
old installation before changing it, and start a fresh agent session afterwards.

## First installation or managed update

Select an exact release from GitHub. Check its tag, source commit, maturity,
known limitations and public-download verification evidence. The following
example uses 0.1.0; it works only after that release has been published.

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
tar -xzf "crew-v${crew_version}.tar.gz" -C payload
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
Checksums detect corruption or drift; trust in the official release comes from
GitHub's HTTPS identity and immutable release/tag/assets, not a local marker.

## Destinations and duplicate detection

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

Any other matching location is reported before that host is written. Symlinked
destinations and skill-root parents are refused. The home path is resolved once
so a symlinked home can still use its canonical personal directories.

## Read-only check results

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

## Existing copies, development links and interrupted updates

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
and [Claude Code](https://code.claude.com/docs/en/skills#choose-where-skills-load).
