# Existing skill installers: decisions and evidence

Issue: [#8](https://github.com/weirdry/crew/issues/8). Observed 2026-09-17.

## Decision

Use the existing Skills CLI as the default personal installation route for both
Codex and Claude, with the installer version and Crew release tag stated
separately. The primary command uses a tag that has actually been published:

```sh
npx skills@1.6.0 add 'weirdry/crew#v0.1.0' -g -a codex claude-code
```

No new bootstrap, package or runtime adapter is needed. Keep the managed archive
installer available with its existing marker, content checks, refusal and update
semantics. No automatic cross-tool adoption is introduced. `INSTALL.md` is part
of the archive, so changing it prepares **0.1.1** under the existing version
policy; it does not publish that version. Examples continue to select the
already published **0.1.0**, whose tag and assets are unchanged.

## Reproduction

Run from a checkout that has fetched `v0.1.0`, with Node.js 22.20+, npm and Python
3.11+. The script performs its own complete environment isolation:

```sh
python3 -B tests/skill-installers.py
```

Local exploratory checks used macOS, Node.js 26.3.0, npm 11.16.0 and Skills CLI
1.6.0. CI repeats the primary path on Linux/macOS with Node.js 22.20.0 and Python
3.11. The source is the immutable `v0.1.0` tag at
`b0ecc6fc484579559d1ee9eae3c6e88649057aa9`. All 15 skill files, including scripts,
references and templates, were compared with that published source.

| Check | Observed outcome |
| --- | --- |
| Pinned Skills CLI installation | All bytes and executable permissions match; canonical `~/.agents/skills/crew`, Claude link to that directory |
| Installed completion helper | Completed report accepted (0), blocked report rejected (1), both layouts |
| Installed relay entry point | Usage exit 2 in both layouts; no live run or agent started |
| Source record | Global `.agents/.skill-lock.json` retains `ref: v0.1.0` and `skills/crew/SKILL.md` |
| Pinned `update crew -g`, API tree hash recorded at add | Keeps the selected ref; reports up to date even with a synthetic local edit |
| HTTP unavailable during add, available during update | A fallback content hash is compared with a Git tree SHA; update reinstalls the unchanged tag and replaces a synthetic local edit |
| Failed HTTP lookup and Git fallback | CLI exits 0 with both `Failed to check` and `up to date`; the update validator rejects it and preserves the files/source record |
| Re-add same tag | Restores source bytes by replacing that local edit; not a preservation/no-op guarantee |
| Published managed installer checks a CLI installation | Both hosts report `conflicting`; installed files preserved |

The failure regression uses the real pinned CLI with a Node preload returning
HTTP 503 for the tree API and a temporary Git wrapper that rejects clone. It
checks that both were invoked, then requires the same validator used by the
healthy update check to reject the resulting output. Exit status and a success
phrase alone cannot establish that a source check completed in Skills CLI 1.6.0.

### Live installation and controlled updates

On 2026-09-17, [CI run 35209988574](https://github.com/weirdry/crew/actions/runs/35209988574)
passed file/mode verification on macOS but stopped at the old tree-hash-only
guard in both attempts. The CLI had recorded a fallback content hash. Those logs
did not retain the API response, so they cannot establish whether the underlying
cause was a rate limit, another HTTP failure or a transport error.

The smoke test now accepts either source hash only when it matches the selected
published Git objects: the skill's tree SHA or the CLI 1.6.0 content hash over
relative paths and file bytes in JavaScript `localeCompare` order. It still
compares the full installed inventory and executes installed helpers. Live add
and re-add use unmodified HTTP responses. A pass-through observer logs tree HTTP
status, rate-limit/retry headers, or exception name and cause code without
request headers or response bodies.

Update scenarios control only the tree response, using the published Git tree
as the success fixture and HTTP 503 for unavailability. npm/Git installation
still uses the actual pinned CLI and release. Separate scenarios verify stable
tree-hash updates through both API and Git, stable fallback-hash updates through
Git, and replacement of a local edit when the API returns after a fallback-hash
installation. The CLI creates all source records itself; the test does not
rewrite its lock or silently omit cases based on API availability.

These controlled results prove behavior for the stated responses, not current
API availability. Live installation/re-add and controlled update evidence are
reported separately. Pinning the tag alone does not make update read-only or
protect local edits. The smoke test uses `-y`, which selects the default Symlink
method; it does not establish the full interactive flow. No credentials are
passed to the third-party CLI.

## Codex skill-installer experiment

The bundled `install-skill-from-github.py` tested locally had SHA-256
`38f311b75664bb063808f982c600271ebc4b560830f491705190f88a94e3e781`.
It was invoked with `--repo weirdry/crew --path skills/crew --ref v0.1.0`, using
separate disposable homes and explicit `--dest` paths for each method.

- `--method download`: all 15 file contents matched, but ZIP extraction produced
  shell scripts with mode 0644. Direct helper execution raised `PermissionError`.
- `--method git`: file contents and modes matched; the same completion and relay
  checks passed from the isolated Codex installation.

Therefore the Codex-only alternative explicitly requests Git. The ZIP result is
an observation about this helper revision, not an assertion about all future
Codex versions. It is not patched or vendored into Crew, and the local bundled
helper is not assumed to exist on GitHub runners.

## Ownership and evidence limits

Skills CLI source checks, Crew managed content checks, and actual host skill
discovery are different operations. Do not use a successful `skills list` or
`skills update` to claim byte integrity or permission to replace edited files.
Changing installation owners requires preserving and deliberately retiring the
previous entries; the implementation adds no migration or cleanup mechanism.

The tests use temporary homes and synthetic reports. They do not prove a fresh
agent loaded Crew, live Herdr delivery/permission behavior, arbitrary host
configuration, or publication of 0.1.1. Git-tag installation relies on GitHub/Git
and the selected tag; it does not consume the release archive's checksum or
managed ownership marker.

Sources: [Skills CLI](https://github.com/vercel-labs/skills),
[OpenAI skill installation](https://learn.chatgpt.com/docs/build-skills#install-curated-skills-for-local-use),
and the local helper revision identified above. The Skills CLI package declares
Node.js `>=22.20.0`; the executable npm distribution was used for the experiments.
