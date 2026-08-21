---
name: crew
description: "Run a bounded multi-model collaboration loop inside Herdr. This agent acts as lead: it scopes the work, delegates implementation to a worker agent of a DIFFERENT model kind running in a sibling Herdr pane, supervises that worker, reviews its output, and iterates for a fixed number of rounds. Use only when the user explicitly asks for crew (\"crew\", \"crew로\", \"크루로\", \"crew 써서\"). Requires HERDR_ENV=1. Do not use for same-model delegation; use the host agent's own subagent or workflow tooling for that."
---

# Crew

Crew pairs you (the **lead**) with a **worker** agent of a different model kind. The lead owns
scoping, supervision, review, and the decision to stop. The worker owns implementation.

The value of this arrangement is exactly one thing: the reviewer and the author have different
failure patterns. If both agents are the same model kind, that value is gone and the host
agent's built-in subagents are cheaper and more reliable. Refuse the same-kind case.

## Preconditions

Check all of these before creating any layout. Stop and report on the first failure.

```bash
test "${HERDR_ENV:-}" = 1
```

Not inside a Herdr pane: say so and stop.

Determine your own kind, then pick the worker kind:

```bash
herdr agent list
```

Find the entry whose `pane_id` equals `$HERDR_PANE_ID`; its `agent` field is your own kind.
The worker kind is whatever the user asked for, otherwise any supported kind that is **not**
your own. If the user asks for a worker of your own kind, tell them crew adds nothing over
built-in subagents for that case and stop.

The worker is the only writer of source files. If the cwd is a Git repository, record the
starting commit and report an already-dirty tree to the user before starting. Do not clean it.

```bash
git rev-parse HEAD 2>/dev/null; git status --short 2>/dev/null | head -20
```

## Run directory

All data moves through files. The terminal carries control signals only.

Create `<cwd>/.crew/<run-id>/` where `<run-id>` is `date +%Y%m%d-%H%M%S`. The run directory
must live inside the working tree: worker sandboxes are commonly workspace-scoped, so a path
outside the workspace turns every worker write into an approval prompt.

Keep it out of Git without touching tracked files:

```bash
grep -qx '.crew/' .git/info/exclude 2>/dev/null || echo '.crew/' >> .git/info/exclude
```

Every shell invocation starts fresh, so the run id has to survive on disk. Write it to
`.crew/.current` when the run starts and read the active run back from there afterwards.

```bash
printf '%s\n' '<run-id>' > .crew/.current
```

Files the run writes — `.crew/.current` at the `.crew/` root, the rest in the run directory:

| File | Written by | Purpose |
| --- | --- | --- |
| `.crew/.current` | lead | Active run id, written at run start; how a later invocation finds the run |
| `task.md` | lead | Frozen scope: goal, acceptance criteria, out of scope, likely files |
| `plan-check.md` | worker | Optional pre-implementation objections |
| `report-<n>.md` | worker | What it did, what it checked, open questions |
| `review-<n>.md` | lead | Structured findings and verdict |
| `dismissed.md` | lead | Closed findings with one-line reasons; never reopened |
| `state.md` | lead | Current phase, round number, worker name, pane id |

`state.md` makes a run resumable if the lead session dies. Update it at every phase boundary.

## Completion is proved by artifacts, not by state

`herdr agent prompt --wait` settles on lifecycle transitions, not on turn boundaries. If the
worker was already busy, a settle can report the *previous* turn finishing. `unknown` never
proves completion either.

Therefore: a phase is complete only when its output file exists **and** its last line is

```
STATUS: done
```

Instruct the worker to end every artifact with that exact line. A settled lifecycle state with
no artifact means the phase is still running or the worker misunderstood; re-read the pane
before deciding.

## Phases

| # | Actor | Reads | Writes | Exit condition |
| --- | --- | --- | --- | --- |
| 0 | lead + user | user request | `task.md` | User confirms the scope. Scope is now frozen. |
| 1 | worker | `task.md`, repo | `plan-check.md` | Artifact present (may be `없음`). Optional; skip on small tasks. |
| 2 | worker | `task.md` | code, `report-1.md` | Artifact present with `STATUS: done` |
| 3 | worker | own diff | appended to `report-<n>.md` | Tests/lint run, diff re-read. Keep this cheap. |
| 4 | lead | `git diff`, `task.md` | `review-<n>.md` | Verdict recorded |
| 5 | worker | `review-<n>.md`, `dismissed.md` | code, `report-<n+1>.md` | Artifact present with `STATUS: done` |
| 6 | lead | new `git diff` | `review-<n+1>.md` | `approve` → stop. `block` → round += 1, return to 5. |

Round cap is **3**. On exceeding it, stop, write the disagreement into `state.md`, and hand the
open question to the user. Do not keep iterating.

Phase 3 is deliberately cheap. A self-review by the author, in the author's own context, finds
mechanical breakage and nothing else. The review budget belongs to phase 4.

In phase 4 review the diff against **the user's original request**, not only against your own
`task.md`. You wrote the scope, so the scope itself is your blind spot.

## Starting the worker

Inspect your own pane, then split. Wide pane splits right, tall or narrow pane splits down.

```bash
herdr pane layout --pane "$HERDR_PANE_ID"
herdr pane split --current --direction right --cwd "$PWD" --no-focus
```

Read the new pane id from `.result.pane.pane_id`.

A freshly split pane is not immediately an available shell; `agent start` fails with
`agent_pane_busy` until the interactive prompt appears. Confirm the prompt first:

```bash
herdr pane wait-output <pane-id> --regex '[#$%>❯] ?$' --source detection --lines 5 --timeout 60000
```

Then start the worker with a name unique among live agents (`herdr agent list` shows the live
set; names must match `[a-z][a-z0-9_-]{0,31}`):

```bash
herdr agent start crew-<run-id-suffix> --kind <worker-kind> --pane <pane-id> --timeout 60000
```

Start with no native arguments. The worker's own configuration decides its permissions; that
is deliberate, and the supervision loop below is what keeps the run moving. Pass arguments
after `--` only when the user opts in for that run.

`agent start` returns `interactive_ready: true` on lifecycle detection, not on the worker TUI
accepting keystrokes. Wait for the worker's composer before the first prompt; a prompt sent
earlier is dropped without an error, and the markers below hold only while that composer is
empty, between `agent start` and the worker's first turn.

| Worker kind | Composer marker |
| --- | --- |
| `codex` | `Ask Codex` |
| `claude` | `Try "` |

```bash
herdr pane wait-output <pane-id> --regex <marker> --source visible --timeout 60000
```

For a kind absent from this table, fall back to the re-prompt-once rule under Known failure
modes.

## Prompting the worker

Every prompt is a pointer, never a payload. Long text, code, and Korean prose in a shell
argument invite quoting errors and scrollback loss.

```bash
herdr agent prompt <worker> "Read .crew/<run-id>/task.md. Implement it. Write what you did and what you verified to .crew/<run-id>/report-1.md, ending with the line STATUS: done. Reply with only that path." --wait --timeout 600000
```

Rules for prompt shape:

- Point at an input file, name the output file, require `STATUS: done`, ask for only the path back.
- Never ask the worker to "critique" or "improve" anything open-endedly. An open critique
  request implies that producing objections is the task, so objections get manufactured.
- Ask closed questions with a legitimate empty answer. For phase 1:
  *"Read task.md and the files it names. Report only concrete cases that would break if this
  plan is followed as written. If there are none, reply with the single word 없음."*

## Supervision loop

Run this after every prompt. It is what keeps the worker moving without handing it your
approval authority.

```
prompt --wait  →  settled
repeat:
  status = herdr agent get <worker>            # agent_status
  working  → herdr agent wait <worker> --timeout <ms>     # server blocks; costs no tokens
  blocked  → herdr agent read <worker> --source visible   # read the dialog
             classify (see below)
             class (a) → herdr agent send-keys <worker> <keys>   → continue
             class (b) → notify the user, stop this round
  unknown  → not complete. read the pane, then wait again.
  idle|done→ artifact present with STATUS: done ? next phase : re-prompt once, then escalate
```

Prefer `herdr agent wait` over polling: it blocks server-side, so a long worker turn costs the
lead nothing.

Cap automatic answers at **5 per round**. A dialog that keeps reappearing means your answers
are not landing; escalate instead of looping.

`herdr agent send-keys` validates every key name before writing any bytes, so an unknown key
name fails safely without sending input. `esc` is the canonical Escape name.

## Which inputs you may answer

| Class | Examples | Action |
| --- | --- | --- |
| (a) answer yourself | edit approval for a file inside the workspace; running tests, linters, or builds; a choice between options that `task.md` already settles; a clarifying question answerable from `task.md` | `send-keys`, then log the answer in `state.md` |
| (b) escalate to the user | deleting or moving files; bulk rewrites; network access; writing outside the workspace; `git commit`, `push`, `reset`, or history rewriting; credentials or secrets; workspace trust prompts; anything not derivable from `task.md` | `herdr notification show "<title>" --body "<what is being asked>" --sound request`, report what is being asked, stop the round |

When the class is not obvious, treat it as (b). The user watching a pane is the whole point of
running this in Herdr; do not spend that on convenience.

## Review discipline

This applies symmetrically to the lead's reviews and to any worker objection. The lead holds
decision authority, so the lead's own bias is the more dangerous one.

Every finding uses this shape:

```
- id: R1
  severity: blocker | major | nit
  location: <file:line> or <task.md clause>
  failure: <specific input or state> → <specific wrong outcome>
  withdraw_if: <condition that retracts this finding>
```

Enforced rules:

- A finding with no concrete `failure` is discarded. Discomfort is not a finding.
- A `blocker` with no `withdraw_if` is invalid. A blocker must be falsifiable and satisfiable.
- At most 5 findings per review, at most 2 blockers. Rank by severity.
- Every review ends with exactly one verdict: `approve`, `approve-with-nits`, or `block`.
- An approval must list what was actually inspected: files read, commands run, tests executed.
  An approval with no evidence of inspection is invalid; redo the review.
- Dismissed findings go to `dismissed.md` with a one-line reason. They are closed. Attach
  `dismissed.md` to every later worker prompt and state that closed items may not be re-raised.
- Objections are input, not veto. Record the reason and proceed.
- Frozen scope may not be reopened by either agent. Scope changes go to the user.

## Known failure modes

- `agent_pane_busy` — the split pane has not reached its shell prompt. Wait for the prompt.
- `interactive_ready` false positive — `agent start` reports `interactive_ready: true` before
  the worker TUI accepts input, so the first prompt is silently lost. Wait for the composer
  marker in "Starting the worker". For a worker kind with no known marker, let the artifact
  check catch the missing output, then apply the existing re-prompt-once rule.
- Self-update exit — a worker self-updates on launch, exits, and releases its name. Wait for
  the same pane to return to a shell prompt, then start the agent again in that pane under the
  same name.
- `agent_prompt_stalled` — no lifecycle change within five seconds of a prompt. Do not resend
  blindly; read the pane first.
- `agent_blocked` — the worker is at a dialog. `prompt` refuses by design; answer with
  `send-keys` if class (a), escalate if class (b).
- Alternate-screen loss — TUI worker output that scrolls away is unrecoverable from scrollback
  regardless of `--lines`. This is why artifacts are files.
- Name collision — agent names must be unique among live agents across all workspaces.
- `unknown` — Herdr cannot classify the pane. It is not evidence of completion.

## Finishing

- Close only the panes this run created: `herdr pane close <pane-id>`.
- Leave the run directory in place; it is the audit trail. Tell the user its path.
- Report: rounds used, final verdict, files changed, dismissed findings, and anything escalated
  but never answered.
- Never run `herdr server stop`. Never close panes, tabs, or workspaces you did not create.
