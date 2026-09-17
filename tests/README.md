# Helper script tests

Run the suite from the repository root:

```sh
tests/run.sh
```

The optional argument selects another directory containing the scripts under test. A normal run
defaults to `skills/crew/scripts/`; the alternate directory is used for mutation testing against
temporary copies without changing the installed helpers.

Each JSON file in `tests/cases/` is one case. The runner creates a separate temporary workspace,
writes only the files declared by that case, prepends `tests/bin/` to the existing `PATH`, invokes
the named helper, and checks its status, output, files, and recorded Herdr calls. Temporary
workspaces are removed after each case, including failures.

Grant cases use `{grant_root}`, a canonical disposable sibling of the workspace,
instead of assuming that macOS's `/private/tmp` exists on Linux. Optional
`encoded_values` entries declare exact fixture identities; after path substitution,
the runner provides `{name_b64}` and `{name_sha256}` tokens from literal strings
or canonical JSON objects. Assertions still specify approval, grant, text and outcomes;
no expected identity is obtained from the helper being tested.

A case's lead authority state — the active-run pointer, the partner receipt, the approval record
— lives under `{state}`, a sibling of the case workspace, exported to the script as
`CREW_STATE_DIR`'s per-workspace child. Case roots are created under `/var/tmp` rather than the
system temporary directory because the helpers refuse a state root at or below `$TMPDIR` or
`/var/folders`; the same refusal means the suite cannot run inside a worker sandbox that cannot
write `/var/tmp`, which is why a worker running it raises a dialog.

The `herdr` stub matches the complete subcommand and arguments. A fixture declares ordered
results for repeated identical calls and may attach a deterministic local-file side effect to a
specific result; undeclared calls and exhausted results fail. Every invocation is appended to a
per-case JSON-lines call log, which cases use to pin exact targets and forbidden operations.

Prerequisites are `sh`, `python3`, and the POSIX utilities already used by the production helpers,
including `dirname`. No Herdr server, network access, package installation, or test framework is
needed.

The suite covers `worker-start.sh`, `worker-stop.sh`, `answer-dialog.sh`, `approval.sh`,
`run-finish.sh`, `artifact-done.sh`, and `status.sh`. The `run-init.sh` cases exercise rejected
state roots; its successful initialization and Git wiring are not covered by this suite.
The Claude-layout approval frame is synthetic and does not verify the branch against a live
Claude permission dialog.

## Status inspection coverage

The status cases cover human-readable and JSON output, no active run, a retained partner,
missing or malformed records, unavailable or mismatched Herdr responses, blocked workers,
report completion versus worker state, phase-3 self-review, explicit review verdicts, and
symlinked artifacts. Regression cases exclude commented evidence, preserve literal comment
examples, flag inconsistent phase/round combinations, and distinguish an unavailable state root
from an absent partner receipt. Initial, final-round, and early Finishing states remain valid.
Lead-review cases require the current report at phases 4 and 6 even when the worker is active;
an older completed report or a CRLF completion marker does not satisfy that check. Other cases
cover verdict and heading trailing whitespace, significant heading indentation, review-round
context during rework, and help output without inspection.
Fixtures contain synthetic private-content sentinels that must not appear in output; no real
session data is used.

Cases marked `read_only: true` snapshot the workspace and external state parent before and
after invocation, comparing directory entries, permissions, modification times, file contents,
and symlink targets. Access times are ignored. Exact Herdr call assertions allow only the
recorded partner's `agent get`; fixture logs are outside the snapshotted state. The optional
`stdout_json_paths` assertions inspect JSON fields, and `stdout_absent` forbids output fragments.
These checks prove the helper's behavior against synthetic fixtures, not live Claude approval
handling, Herdr server behavior, or protection enforced by an agent sandbox.

## Context relay coverage

The same entry point also runs `tests/relay.py`: 23 standard-library unittest cases
that invoke the actual relay helper through sequential synthetic exchanges.
It uses isolated workspaces and external state under /var/tmp, including the
real state-root validator. A Herdr stub with no permitted calls catches any
unexpected agent control. The scripts-directory argument applies to both suites,
so mutation checks can still target an isolated helper copy.

Coverage includes publication and response provenance, incremental and fresh
reading, session isolation, completed-run reading, source-preserving and successive
summaries, corrections after compaction, optional byte-budget signals, invalid
coverage/cursors, changed summary sources, incomplete records, symlinks, and
concurrent name collisions. Relay and summary publication preserve completion-marker
text within sentences while accepting a standalone final marker in a draft.
Additional cases exercise a worker with a different state setting, matching-setting
publication, and diagnostics for workspace-prefixed arguments or absent reply targets.
Read-only assertions compare workspace and authority
state around each plan and refusal; plan output excludes message bodies.

Run just the relay suite with:

```sh
python3 -B tests/relay.py skills/crew/scripts
```

The [continuation walkthrough](relay-walkthrough.md) identifies the concrete
file-level outcome and its limits. A scripted synthetic packet is not evidence
that a fresh model understands it, that model-written summaries preserve every
real-world fact, or that live Herdr delivered the prompt.

## Release and installation coverage

`sh tests/ci.sh` runs shell syntax checks, the 200 helper fixture cases and 23
relay tests, the standard-library release suite, and version policy against
`origin/main`. Python 3.11+ is required. Run the focused release suite with:

```sh
python3 -B -m unittest discover -s tests -p 'test_release.py' -v
```

Release tests commit synthetic temporary repositories and use disposable payloads
and homes. They cover deterministic packaging, source/mode/inventory identity,
archive rejection before extraction, both host installations and repeat no-ops,
read-only checks, conflict/modified detection, duplicate roots, managed replacement,
restoration after a failed swap, and preserved interrupted transactions. A
root-alias regression checks that default, selected and extra paths to the same
directory remain current while separate development symlinks still conflict.
Other cases preserve refusal when a resolved parent becomes a symlink, and run
the documented tar extraction and packaged installer under `umask 077`. A
stateful fake GitHub service exercises tag/draft/asset publication, retries after
an accepted upload with a lost response, immutable publication, docs-only skips,
version reuse refusal, credential-safe redirects and separate consumer evidence.
An empty draft `starter` asset stays untouched until simulated operator recovery;
published and other conflicting assets never receive that recovery advice.
An actual candidate is installed and its packaged helper entry points executed.
No test sends a publication request or modifies a normal skill installation.

Hosted CI repeats the suite and candidate consumption on Linux/Python 3.11 and
3.14 and macOS/Python 3.11. The main Release workflow additionally downloads the
published artifact anonymously on Linux and macOS. See [RELEASING.md](../RELEASING.md)
for identity, authority, retries and evidence retention. Candidate tests do not
prove hosted publication; public consumption does not prove live host discovery,
Herdr permission handling or fresh-agent comprehension.

## Existing skill installer coverage

`python3 -B tests/skill-installers.py` is a separate network smoke test requiring
Node.js 22.20+, npm, Git, Python 3.11+ and the fetched `v0.1.0` tag. It invokes
the documented `skills@1.6.0` npm package in a disposable home with isolated
host configuration, npm cache and temporary files, and no inherited credentials.
It compares every installed skill file and executable bit with the published
Git tree, executes completion/relay helpers in both layouts, and checks pinned
update and re-add behavior. It deliberately modifies only a synthetic installed
copy to demonstrate that the third-party tool does not offer managed drift
protection. The test never starts agents or touches normal installations/state.

The Python 3.11 Linux/macOS CI jobs run it after candidate validation. It remains
outside the offline `tests/ci.sh` suite and the Release workflow. See the
[installation evidence and decisions](skill-installation.md) for the separate
Codex installer experiment and the boundaries of these checks.
