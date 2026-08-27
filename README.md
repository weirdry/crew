# crew

An agent skill for **bounded multi-model collaboration** inside [Herdr](https://herdr.dev).

One agent acts as **lead**: it scopes bounded runs and delegates implementation to a retained
**partner** — the worker agent of a different model kind in a sibling Herdr pane — supervises and
reviews that partner, and keeps its context across runs until explicit retirement.

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

The skill is plain Markdown in this repository. Nothing is published to npm.

**Direct — no tooling.** Clone anywhere, then symlink into each agent's skills directory:

```bash
git clone https://github.com/weirdry/crew.git ~/_GIT/crew
ln -s ~/_GIT/crew/skills/crew ~/.claude/skills/crew   # Claude Code
ln -s ~/_GIT/crew/skills/crew ~/.codex/skills/crew    # Codex ($CODEX_HOME/skills)
```

Because the link points at the checkout, editing the repository updates the installed skill
immediately. This is the right setup while iterating on it.

**With the skills CLI.** The [skills](https://github.com/vercel-labs/skills) CLI comes from npm,
but the skill itself is fetched from this Git repository:

```bash
npx skills add weirdry/crew --skill crew -g
```

It adds a lockfile and `npx skills update -g`, and it resolves agent directories for you —
Codex additionally reads `~/.agents/skills/`, which the CLI treats as its universal location.

Then, inside a Herdr pane:

```
crew로 이 작업 코덱스랑 같이 해줘
```

The skill only activates when it is named explicitly.

## The loop

```
scope (lead + user, frozen)
  → optional plan check (worker, closed question)
  → implement (worker)
  → cheap self-check (worker: tests, lint, diff re-read)
  → independent review (lead, against the user's original request)
  → rework (worker)
  → re-review (lead) → approve, or another round
```

Round cap is 3. Past that the lead stops and hands the disagreement to the user rather than
letting two models argue indefinitely.

## Design decisions

**Files carry data; the terminal carries control.** Herdr reads a pane's scrollback, but TUI
agents render on the alternate screen, where output that scrolls away cannot be recovered at
any `--lines` value. Every phase therefore writes an artifact file and replies with only its
path. This also keeps long prompts out of shell quoting, and makes a run resumable.

**Completion is proved by artifacts.** `agent prompt --wait` settles on lifecycle transitions,
not turn boundaries — if the worker was already busy, a settle can report the previous turn
finishing. A phase counts as done only when its output file exists and ends with `STATUS: done`.

**The lead answers work questions; the user answers trust questions.** Editing a file inside
the workspace is what the worker was sent to do, so the lead approves it and the run keeps
moving. Deleting, moving, reaching the network, writing outside the workspace, committing,
pushing — those cross the boundary the user is watching the pane for, so they escalate.
Ambiguous cases escalate. A user-granted reusable answer covers only a later dialog in the same
run whose completely captured rendered command text matches the run record exactly; the lead
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

Early. The loop, the artifact protocol, and the escalation boundary are settled. Small helper
scripts now carry the repeated run setup, partner attach-or-create, artifact check, and guarded
key-send mechanics. Partner startup records workspace-scoped pane ownership and guarded,
explicit retirement verifies that receipt before close;
classification, approval authority, and verdicts remain with the lead.
The `run-finish.sh` helper carries the run-ending step alongside them: it removes the active-run
pointer at terminal Finishing and keeps it only for an open run.

The helper test suite is documented in [`tests/README.md`](tests/README.md) and runs without a
Herdr server. It deliberately excludes `run-init.sh`.

## License

MIT
