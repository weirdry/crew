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

The skill is plain Markdown in this repository. Nothing is published to npm.

**Direct — no tooling.** Clone anywhere, then symlink into each agent's skills directory:

```bash
git clone https://github.com/weirdry/crew.git ~/_GIT/crew
ln -s ~/_GIT/crew/skills/crew ~/.claude/skills/crew   # Claude Code
ln -s ~/_GIT/crew/skills/crew ~/.codex/skills/crew    # Codex ($CODEX_HOME/skills)
```

Because the link points at the checkout, every commit is a live deploy: it replaces the helpers
for every session using the skill at once, including a crew run in progress in another
workspace, whose lead still holds the previous `SKILL.md` in context while executing the new
scripts. Use the symlink when developing crew itself, and do not commit to it while another run
is in flight. For everyday use, install a copy with the skills CLI below and update it
deliberately.

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
  → plan check (worker, closed question; required when the change touches shared machinery)
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

Early, and used for real: every commit since the license has been produced by a crew run, and
the skill has run against a working repository outside its own. The loop, the artifact protocol,
the escalation boundary, and the two lifetimes — a bounded run, a partner that outlives it —
are settled.

Eight helper scripts carry the mechanics: run initialization and ending, partner attach-or-create
and explicit retirement, the artifact check, the guarded key send, the typed approval record
with user-visible set grants, and the external state root that keeps the lead's authority files
where the worker cannot write them. Classification, approval authority, and verdicts stay with
the lead. An offline suite of 156 cases pins the scripts' documented behaviour and runs with no
Herdr server; it is documented in [`tests/README.md`](tests/README.md) and deliberately excludes
`run-init.sh`'s Git wiring.

Not yet verified against a live Claude worker: the Claude-layout dialog extractor and the
state-root sandbox probe. Both are disclosed as such in `SKILL.md`.

## License

MIT
