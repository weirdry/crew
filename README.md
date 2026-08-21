# crew

An agent skill for **bounded multi-model collaboration** inside [Herdr](https://herdr.dev).

One agent acts as **lead**: it scopes the work, delegates implementation to a **worker** agent
of a different model kind running in a sibling Herdr pane, supervises that worker, reviews the
result, and iterates for a fixed number of rounds.

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

```bash
npx skills add weirdry/crew --skill crew -g
```

Pick the agents you start sessions from. Then, inside a Herdr pane:

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
Ambiguous cases escalate.

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

Early. The loop, the artifact protocol, and the escalation boundary are settled; helper scripts
are deliberately absent until real runs show which parts repeat.
