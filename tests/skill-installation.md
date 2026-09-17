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

The failure regression uses the real pinned CLI with a temporary Node preload
that rejects HTTP fetch and a temporary Git wrapper that rejects clone. It checks
that both were invoked, then requires the same validator used by the healthy
update check to reject the resulting output. Exit status and a success phrase
alone cannot establish that a source check completed in Skills CLI 1.6.0.

The unchanged-update scenario requires the lock's source hash to equal the
published skill's Git tree SHA. If add falls back to a 64-hex content hash, the
smoke test stops before editing the installed skill or running update and names
the unavailable API prerequisite. Retry when the API is available; do not pass
credentials to the third-party CLI. Pinning the tag alone does not make update
read-only or protect local edits. The network smoke test uses `-y`, which selects
the default Symlink method; it does not establish the full interactive flow.

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
