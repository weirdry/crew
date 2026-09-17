# crew

An agent skill for **bounded multi-model collaboration** inside [Herdr](https://herdr.dev).

One agent acts as **lead**: it scopes bounded runs and delegates implementation to a retained
**partner** — the worker agent of a different model kind in a sibling Herdr pane — supervises and
reviews that partner, and keeps its context across runs — bounded by the Herdr server's
lifetime and the agent's own context window — until explicit retirement.

Either side can be either product. Install it wherever you start sessions from — the skill
detects its own agent kind at runtime and picks a different kind for the worker.

## Why a different model

The only durable reason to run two agents instead of one is that the reviewer and the author
fail differently. Two sessions of the same model share blind spots, so a same-kind pair buys
latency and token cost with no added coverage — the host agent's built-in subagents are better
for that. The skill refuses the same-kind case on purpose.

## Requirements

- Herdr, and a session started **inside** a Herdr pane (`HERDR_ENV=1`)
- Two supported agent kinds installed locally (e.g. Claude Code and Codex)
- A Git working tree, for diff-based review

## Install

For a new personal installation in Codex and Claude Code:

```sh
npx skills@1.6.0 add 'weirdry/crew#v0.1.2' -g -a codex claude-code
```

This uses the existing [Skills CLI](https://github.com/vercel-labs/skills) to
fetch the published `v0.1.2` tag and install the complete skill. No manual archive
download is needed. Installation needs Node.js 22.20+ with npm and Git; Crew's
helpers need Python 3.11+ on macOS or Linux. The npm package is the installer,
not a Crew package.

When prompted for the installation method, accept **Symlink (Recommended)**.

Already have Crew installed? Read [existing installations](INSTALL.md#existing-installations)
first: Skills CLI can overwrite files and does not provide Crew's managed
installer's drift protection. End affected Crew work before changing an
installation and start a fresh agent session afterwards.

[INSTALL.md](INSTALL.md) covers version selection, updates, the Codex installer
alternative and the existing managed archive installer. The command deliberately
pins a published release; it does not track the latest tag or `main`.

### Development installation

A deliberately maintained checkout may still be symlinked into a host's skill
root. For example, after checking that the destination is absent:

```sh
mkdir -p ~/.agents/skills
ln -s /absolute/development-checkout/skills/crew ~/.agents/skills/crew
```

Use `~/.claude/skills/crew` for Claude. Edits, branch switches, pulls and rebases
change what linked sessions execute immediately, even before a commit. Develop
and test in an isolated checkout when another session uses the linked checkout.
The managed archive installer refuses these symlinks. Skills CLI, Codex's
installer and the archive installer own separate installation layouts and
metadata; follow the [installation ownership rules](INSTALL.md#existing-installations)
when changing methods.

Then, inside a Herdr pane:

```
Use crew to work on this with Codex.
```

The skill only activates when it is named explicitly.

## The loop

```
scope (lead + user, frozen)
  → plan check (worker, closed question; required when the change touches shared machinery)
  → implement (worker)
  → cheap self-check (worker: tests, lint, diff re-read)
  → independent review (lead, against the user's original request)
  → rework (worker)
  → re-review (lead) → approve, or another round
```

Round cap is 3. Past that the lead stops and hands the disagreement to the user rather than
letting two models argue indefinitely.

## Inspect a run

From the working directory where the run was initialized, invoke the helper in your installed
skill directory:

```sh
<crew-skill-dir>/scripts/status.sh
<crew-skill-dir>/scripts/status.sh --json
<crew-skill-dir>/scripts/status.sh --help
```

The summary shows the active run, recorded phase and round, retained partner identity, live
worker state, latest report, latest completed report, and latest review verdict. Recorded
progress and observed worker state are separate: an idle worker does not prove completion, and
an older completed report does not hide a newer unfinished one. Missing or inconsistent evidence
includes a suggested next check. It also works without an active run or outside a Herdr pane;
if a partner is recorded but Herdr is unavailable, its live state stays unknown.

Inspection reads existing records and calls only `herdr agent get` for the recorded partner.
It does not initialize, resume, finish, or modify a run, answer a dialog, or change a pane.
It never queries terminal frames or approval records, and includes only selected metadata
from report and review files in its output.
Use the same `CREW_STATE_DIR` setting as the run. `--help` prints usage without inspection.
Exit 0 means help was printed or the snapshot has no reported attention items, 1 means attention
or unavailable evidence, and 2 means invalid arguments.
Neither 0 nor a report's completion marker is a run verdict. See the
[status output contract](skills/crew/SKILL.md#inspecting-run-status) for JSON and artifact semantics.

## Design decisions

### Shared context and occasional compaction

Each run is also a collaboration session with its own local relay history. Use
`relay.sh append` to publish questions, answers, corrections, or rationale that
the task/report/review files do not already capture. Each actor owns its messages.
A restarted or replacement agent can continue the same run from those records.

```sh
<crew-skill-dir>/scripts/relay.sh read-plan <run-id>
<crew-skill-dir>/scripts/relay.sh read-plan <run-id> --after <last-understood-relay>
```

The read-only plan lists canonical task/status files and either the latest summary
plus later relays or the unread original suffix. It never marks records read.
Herdr still delivers prompts and controls the agents.

Summaries are optional and authored by the lead when useful, then published with
`relay.sh publish-summary`. Original relays and older summaries remain intact.
No automatic summarization runs after every turn or handoff. An optional
`--budget-bytes` read-plan argument reports a reading-size signal; there is no
default token threshold or assumption that model capacity equals available space.
See the [context relay protocol](skills/crew/references/relay.md) for commands,
templates, ownership, and fresh-session continuation.

### Existing collaboration invariants

**Files carry data; the terminal carries control.** Herdr reads a pane's scrollback, but TUI
agents render on the alternate screen, where output that scrolls away cannot be recovered at
any `--lines` value. Every phase therefore writes an artifact file and replies with only its
path. This also keeps long prompts out of shell quoting, and makes a run resumable.
Lead-only pointers, pane ownership, and approval records live in a validated external state root,
while worker-authored artifacts remain in the workspace. A worker therefore cannot forge a lead
action without an escalated outside-workspace write.

**Completion is proved by artifacts.** `agent prompt --wait` settles on lifecycle transitions,
not turn boundaries — if the worker was already busy, a settle can report the previous turn
finishing. A phase counts as done only when its output file exists and ends with `STATUS: done`.

**The lead answers work questions; the user answers trust questions.** Editing a file inside
the workspace is what the worker was sent to do, so the lead approves it and the run keeps
moving. Deleting, moving, reaching the network, writing outside the workspace, committing,
pushing — those cross the boundary the user is watching the pane for, so they escalate.
Ambiguous cases escalate. A user-granted reusable answer covers either one exact typed dialog key
or one immutable, verbatim-shown command/edit set under a constrained resolved root; the lead
never selects the worker's broader "don't ask again" option.

**The worker starts with no extra arguments.** Permissions come from the worker's own
configuration rather than from flags the skill injects. Supervision, not privilege escalation,
is what keeps the loop unblocked.

**Objections must be falsifiable.** Every finding carries a concrete failure scenario and, if
it blocks, a condition that would retract it. Findings are capped and ranked, every review ends
in one of three verdicts, approvals must state what was actually inspected, and dismissed items
are closed permanently.

Those last rules exist because unconstrained review prompts fail in both directions: an open
"critique this" makes objections the deliverable, so they get manufactured, while an open
"looks fine?" invites rubber-stamping. Requiring evidence in both directions is what makes the
second model's opinion worth its cost.

## Status

Early, and used for real: Crew has been used to develop this repository and has run against
a working repository outside its own. The loop, the artifact protocol,
the escalation boundary, and the two lifetimes — a bounded run, a partner that outlives it —
are settled.

Ten shell entry points carry the mechanics: read-only status inspection, context relay
publication and reading plans, run initialization and ending, partner attach-or-create
and explicit retirement, the artifact check, the guarded key
send, the typed approval record with user-visible set grants, and the external state root that
keeps the lead's authority files where the worker cannot write them. Classification, approval
authority, and verdicts stay with the lead. An offline suite of 200 existing cases and
23 relay tests pins the scripts' documented behaviour and runs with no Herdr server;
it is documented in
[`tests/README.md`](tests/README.md) and deliberately excludes `run-init.sh`'s Git wiring.

Not yet verified against a live Claude worker: the Claude-layout dialog extractor and the
state-root sandbox probe. Both are disclosed as such in `SKILL.md`.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) for branch, commit, review, validation, and
release rules. Development integrates on `dev` and reaches `main` through
fast-forward promotion. Pull requests use the repository-local
[template](.github/pull_request_template.md).

Crew manages project development and maintenance through
[GitHub Issues](https://github.com/weirdry/crew/issues), including feature planning,
research, and routine improvements. Use the [work template](.github/ISSUE_TEMPLATE/work.md)
and follow the [issue workflow](CONTRIBUTING.md#issue-management). Repository
documentation, commits, issues, pull requests, comments, and status updates are
written in English.

Agent instructions live in [RULES.md](RULES.md).
[AGENTS.md](AGENTS.md) and [CLAUDE.md](CLAUDE.md) are one-line entry documents
that point to it; update shared instructions in `RULES.md`.

The offline helper suite runs with `tests/run.sh`; see
[tests/README.md](tests/README.md) for prerequisites and coverage limits.

## License

MIT
