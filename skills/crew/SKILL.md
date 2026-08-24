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

In the commands below, `<crew-skill-dir>` is the directory containing this `SKILL.md`. Resolve
it from the loaded skill location; keep the shell cwd at the repository where the run belongs.

Create `<cwd>/.crew/<run-id>/` where `<run-id>` is `date +%Y%m%d-%H%M%S`. The run directory
must live inside the working tree: worker sandboxes are commonly workspace-scoped, so a path
outside the workspace turns every worker write into an approval prompt.

Initialize the run with the helper. It resolves the real Git exclude file before writing run
state, including when the cwd is below the repository root or `.git` is a linked-worktree file.
It prints the run id. It refuses with exit status 6 when `.crew/.current` already exists and
prints the run it preserved. On exit 6, read the named run's `state.md` before deciding: resume
a genuinely open run; treat the pointer as abandoned only when its lead died. Pass
`--replace-current` only after the user explicitly approves abandoning that run; its directory
remains untouched.

```bash
<crew-skill-dir>/scripts/run-init.sh
```

Only after that explicit approval, run the override instead:

```bash
<crew-skill-dir>/scripts/run-init.sh --replace-current
```

To perform the same steps by hand, resolve the exclude path through Git, add `.crew/` only when
absent, create the timestamped directory, write the state fields shown in the file table, and
then update `.crew/.current`:

```bash
exclude_file=$(git rev-parse --path-format=absolute --git-path info/exclude)
grep -qx '.crew/' "$exclude_file" 2>/dev/null || printf '%s\n' '.crew/' >> "$exclude_file"
if [ -e .crew/.current ]; then
  IFS= read -r current_run < .crew/.current
  printf 'current_run=%s\noutcome=current-exists\n' "$current_run" >&2
  exit 6
fi
run_id=$(date +%Y%m%d-%H%M%S)
mkdir -p .crew
mkdir ".crew/$run_id"
printf '%s\n' '# Crew state' '' \
  '- Phase: 0 — scope not frozen' '- Round: 0 of 3' \
  '- Worker: none' '- Pane: none' > ".crew/$run_id/state.md"
(set -C; printf '%s\n' "$run_id" > .crew/.current)
```

The noclobber write catches a concurrent creator after the manual precheck. If it fails, leave
the existing pointer untouched, remove only the run directory just created by this attempt,
and stop. Do not perform a manual replacement; use the helper's explicit override path.

Every shell invocation starts fresh, so the run id has to survive on disk. Read the active run
back from `.crew/.current` afterwards:

```bash
IFS= read -r run_id < .crew/.current
```

Files the run writes — `.crew/.current` at the `.crew/` root, the rest in the run directory:

| File | Written by | Purpose |
| --- | --- | --- |
| `.crew/.current` | lead | Active run id; present from initialization through an open run, removed after terminal Finishing |
| `worker-pane.json` | `worker-start.sh` | Immutable lead/worker pane ownership receipt used by guarded cleanup |
| `approvals.jsonl` | `approval.sh` | Run-scoped reusable approvals keyed by complete rendered command text |
| `task.md` | lead | Frozen scope; contents specified in "What `task.md` must contain" below |
| `plan-check.md` | worker | Optional pre-implementation objections |
| `report-<n>.md` | worker | What it did, what it checked, open questions |
| `review-<n>.md` | lead | Structured findings and verdict |
| `dismissed.md` | lead | Closed findings with one-line reasons; never reopened |
| `state.md` | lead | Current phase, round number, worker name, pane id |

`state.md` makes a run resumable if the lead session dies. Update it at every phase boundary.

### What `task.md` must contain

Write these sections, in this order:

- `# Task` — one paragraph naming the goal and the files that hold the evidence for it.
- `## Acceptance criteria` — numbered, each checkable by reading a file or running a command.
- `## Out of scope` — the categories below, each stated as a prohibition.
- `## Style` — the voice and structure the edit must match.
- `## Deliverable` — the report file and the required closing `STATUS: done` line.

Add `## Context`, `## Item <n>`, or `## Likely files touched` when the work needs them, and
`## Amendments` last when the user accepts a phase 1 finding.

`## Out of scope` names every category that applies to the run, and always these:

- Protected regions of the file under edit: name them explicitly.
- Other files: `README.md`, `LICENSE`, and anything else outside the named target.
- Scope creep inside the target: rewriting or adding beyond what the items require.
- Git operations of any kind.
- Network access of any kind, including package installation.
- Machine configuration.
- Panes the worker did not create.

## Completion is proved by artifacts, not by state

`herdr agent prompt --wait` settles on lifecycle transitions, not on turn boundaries. If the
worker was already busy, a settle can report the *previous* turn finishing. `unknown` never
proves completion either.

Therefore: a phase is complete only when its output file exists **and** its last line is

```
STATUS: done
```

Use the helper for that exact check:

```bash
<crew-skill-dir>/scripts/artifact-done.sh <artifact-path>
```

Exit status 0 is the only completed result. Without the helper, verify that the file exists and
compare its last line byte-for-byte with `STATUS: done`.

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

Round 1 spans phases 2 through 4. Use the round number for `<n>` in `report-<n>.md` and
`review-<n>.md`. A `block` in phase 4 starts round 2 at phase 5. After each later `block`,
increment the round before returning to phase 5. Round cap is **3**. If the increment would
start round 4, do not return to phase 5. Stop, copy every unresolved finding that caused the
`block`, including its `withdraw_if` condition, into `state.md`, and hand them to the user. Do
not keep iterating.

Phase 1 findings are objections against frozen scope, not authority to reopen it. The lead
takes them to the user as proposed amendments; neither agent disposes of one alone. Append each
accepted amendment to `task.md` under `## Amendments`, where it supersedes any earlier clause of
that file it conflicts with, `## Out of scope` included. Record each rejected finding in
`dismissed.md`. From the phase 2 prompt onward, follow the dismissal discipline under
"Review discipline" whenever that file is non-empty.

Phase 3 is deliberately cheap. A self-review by the author, in the author's own context, finds
mechanical breakage and nothing else. The review budget belongs to phase 4.

In phase 4 review the diff against **the user's original request**, not only against your own
`task.md`. You wrote the scope, so the scope itself is your blind spot.

## Starting the worker

Inspect your own pane, then split. Wide pane splits right, tall or narrow pane splits down.

Use the helper for the complete mechanical sequence. It requires an active run, records the
caller and created worker in that run's `worker-pane.json`, and prints `pane_id=<id>`, the
composer-marker result, and the receipt path:

```bash
<crew-skill-dir>/scripts/worker-start.sh <worker-name> <worker-kind>
```

The helper waits for composer markers only for the kinds in the table below. For any other kind
it prints `composer_wait=skipped:no-documented-marker`; retain the artifact check and
re-prompt-once fallback. If a post-split step fails, the helper closes its pane. Exit status 8
means that cleanup failed and prints `pane_id=<id>` for manual recovery. Exit status 9 means
the ownership receipt failed and the helper closed the new pane.

To perform the same sequence by hand, inspect the caller pane and choose the direction from its
rectangle before splitting:

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

When performing startup by hand, write `worker-pane.json` with version 1 and the exact
`lead_pane_id`, `worker_pane_id`, `worker_name`, and `worker_kind` values before the first
prompt. Create it exclusively; never overwrite an existing receipt. The guarded finishing step
depends on this ownership evidence.

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
same_dialog_repeats = 0
failed_dialog = none
no_dialog_reads = 0
repeat:
  agent = herdr agent get <worker>             # agent_status and state_change_seq
  status = agent.agent_status
  working  → no_dialog_reads = 0
             herdr agent wait <worker> --timeout <ms>     # server blocks; costs no tokens
  blocked  → pane = herdr agent read <worker> --source visible
             artifact-done.sh <artifact-path> exits 0 ? next phase
             free-text question without options ? apply the free-text rule below
             no explicit confirmation prompt with a selectable option list ?
               no_dialog_reads += 1
               no_dialog_reads < 3 → pause for one second, then continue
               otherwise → escalate as unanswerable, then stop this round
             no_dialog_reads = 0
             dialog_text = confirmation prompt and option-list text only  # never the whole frame
             dialog_agent = herdr agent get <worker>
             dialog_agent.agent_status != blocked ? continue
             failed_dialog != none and dialog_text == failed_dialog.text and
               dialog_agent.state_change_seq == failed_dialog.pre_key_seq ?
                 same_dialog_repeats += 1
               : same_dialog_repeats = 0
             same_dialog_repeats > 5 ? escalate instead of sending again, then stop this round
             classify (see below)
             class (a) → answer-dialog.sh <worker> <keys>
                         advanced → read printed pre_key_seq and post_key_seq;
                                    failed_dialog = none; same_dialog_repeats = 0; continue
                         send failure or timeout → read printed pre_key_seq;
                                                   key did not land;
                                                   failed_dialog = (dialog_text, pre_key_seq);
                                                   continue
                         guard refusal → return to the blocked guard without sending
             class (b) → approval.sh check <worker>
                         match → read printed command_b64;
                                 answer-dialog.sh --expected-command-b64 <token> <worker> <keys>;
                                 handle advanced, failed, and refused results as above
                         no match or extraction failure → apply the class-(b) escalation and
                                                          approval-scope rule below, then stop
  unknown  → not complete. read the pane, then wait again.
  idle|done→ artifact present with STATUS: done ? next phase : re-prompt once, then escalate
```

Use `herdr agent wait` for `working` turns: it blocks server-side, so a long worker turn costs
the lead nothing.

In the loop, resolve the helper calls as:

```bash
<crew-skill-dir>/scripts/artifact-done.sh <artifact-path>
<crew-skill-dir>/scripts/answer-dialog.sh <worker> <keys>
<crew-skill-dir>/scripts/approval.sh check <worker>
```

The lead identifies `dialog_text`, applies the repeat test, classifies (a) versus (b), and
chooses the keys before calling `answer-dialog.sh`. The helper only rechecks the mechanical
blocked-plus-visible-option-list guard, captures and prints `pre_key_seq`, sends the supplied
keys, and polls. It never decides whether a dialog may be answered.

For a recorded class-(b) match, read `command_b64` from `approval.sh check` and pin it at the
send boundary:

```bash
<crew-skill-dir>/scripts/answer-dialog.sh \
  --expected-command-b64 <command_b64> <worker> <keys>
```

The answer helper calls the same extractor immediately before sending and refuses with exit 3
when the complete rendered command changed or can no longer be extracted. `approval.sh` also
refuses extraction unless it finds the confirmation line, a complete command region, and the
option list; a truncation marker or a frame cut that removes any anchor is an extraction
failure. Its exit status 0 means recorded or matched, 1 means no match, 2 means bad arguments,
3 means invalid active-run ownership, 4 means state/frame/extraction failure, and 5 means a
record failure.

Live extraction is verified for Codex worker command dialogs. The structural Claude branch is
not live-verified; for Claude or any other unverified worker kind, treat exit 4 as an unavailable
reuse path and escalate every occurrence normally.

After the user answers an escalation, capture the still-visible command again. For reusable
scope, run `approval.sh record <worker>` and use its printed `command_b64`; for a one-shot
answer, use the `command_b64` printed with the no-match result. Pass that token to the pinned
answer helper above. In both cases choose the worker UI's one-shot affirmative option.

Without the approval helper, keep the complete rendered command region in the run record only
after the user grants reusable scope. On later class-(b) dialogs, anchor the region between the
confirmation and option list, refuse incomplete or truncated captures, and compare the rendered
text exactly. Immediately re-read and compare that same text before the guarded `send-keys`;
return to the blocked guard without sending if it changed.

Without the answer helper, expand its call exactly as follows: capture
`dialog_agent.state_change_seq` as `pre_key_seq`, run `herdr agent send-keys <worker> <keys>`,
then poll `herdr agent get <worker>` at bounded intervals until `state_change_seq` is greater
than `pre_key_seq` or the post-key timeout expires. Preserve `pre_key_seq` on timeout so the
lead can set `failed_dialog = (dialog_text, pre_key_seq)`.

`herdr agent send-keys` validates every key name before writing any bytes, so an unknown key
name fails safely without sending input. `esc` is the canonical Escape name.

## Which inputs you may answer

| Class | Examples | Action |
| --- | --- | --- |
| (a) answer yourself | edit approval for a file inside the workspace; running tests, linters, or builds; a choice between options that `task.md` already settles; a clarifying question answerable from `task.md` | Apply the guarded `send-keys` path in the Supervision loop, then log the answer in `state.md` |
| (b) escalate to the user | deleting or moving files; bulk rewrites; network access; writing outside the workspace; `git commit`, `push`, `reset`, or history rewriting; credentials or secrets; workspace trust prompts; anything not derivable from `task.md` | Check the active run's approval record first. On no match, report what is being asked directly to the user, attempt `herdr notification show "<title>" --body "<what is being asked>" --sound request` as a best-effort ping, read `.result.shown` from its response, then stop the round. If `shown` is `false`, tell the user that the ping was not shown. |

A reusable class-(b) approval covers only a later dialog in the same run whose completely
captured rendered command text matches the run record exactly. When escalating, tell the user
that scope and distinguish it from a one-shot answer; record it only after the user grants the
reusable scope. Always select the one-shot affirmative option when sending a granted answer;
never select the worker's broader "don't ask again" option.

The run record is a convenience, not proof that the user granted an approval. It lives inside
the worker-writable workspace, so reuse assumes a non-adversarial worker exactly as the rest of
the file-based protocol does; never treat a record entry as an independent authority boundary.

A free-text question is not answerable with `send-keys`. Escalate it even when its answer is
derivable from `task.md` and class (a) otherwise applies. Do not invent a text-entry mechanism.

When the class is not obvious, treat it as (b). The user watching a pane is the whole point of
running this in Herdr; do not spend that on convenience.

The lead's own report to the user is the mandatory escalation channel. The notification is
only a best-effort ping on top of that report; exit status 0 does not prove delivery.

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
- Use `approve-with-nits` only when no blocker remains. Send the nits to the still-live worker
  as one final pass that does not consume a round, and allow at most one such pass. If the
  worker is already gone, record the nits under `Deferred nits` in the current `review-<n>.md`
  and finish the run.
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
- `agent_blocked` — `herdr agent prompt` refuses a worker that remains at a dialog. Return to
  the `blocked` branch of the Supervision loop; do not retry the prompt until that branch
  confirms the dialog answer, and stop if it escalates.
- Notification no-op — `herdr notification show` can exit 0 with `.result.shown` set to
  `false`. Keep the lead's report as the mandatory escalation channel, inspect `shown`, and
  tell the user when the best-effort ping was not shown.
- Alternate-screen loss — TUI worker output that scrolls away is unrecoverable from scrollback
  regardless of `--lines`. This is why artifacts are files.
- Name collision — agent names must be unique among live agents across all workspaces.
- Wrong-pane cleanup — never close `--current`, `$HERDR_PANE_ID`, or a pane copied from visual
  position. `worker-stop.sh` closes only the worker in the active run's ownership receipt and
  refuses unless the caller is the recorded lead and the live worker still resolves to the
  recorded pane.
- `unknown` — Herdr cannot classify the pane. It is not evidence of completion.

## Finishing

- A run stopped at the round cap with unresolved blockers or at an unanswered class-(b)
  escalation has no terminal verdict. Keep `.crew/.current` and use its `state.md` as the resume
  point; do not enter the remaining Finishing steps.
- If `worker-pane.json` exists, close the run-owned worker with the guarded helper first:

  ```bash
  <crew-skill-dir>/scripts/worker-stop.sh
  ```

  It reads the active run's immutable `worker-pane.json`, refuses when the caller is not the
  recorded lead or the target equals the caller/lead, verifies that the recorded worker name
  still resolves to the recorded pane, and only then runs `herdr pane close
  <recorded-worker-pane-id>`. Exit status 5 alone does not prove that the worker is absent; the
  finishing helper below distinguishes an absent name from a live pane mismatch. Stop on every
  other refusal. Skip this step when no receipt exists.
- Without the worker helper, read all four receipt fields, require
  `lead_pane_id == $HERDR_PANE_ID`,
  require `worker_pane_id != $HERDR_PANE_ID`, and run `herdr agent get
  <recorded-worker-name>`. Close the pane only when its live `pane_id` exactly equals the
  receipt's `worker_pane_id`. Never use `--current` for cleanup.
- After the worker closes, or after `worker-stop.sh` exits 5 because the recorded name is no
  longer live, end the named run:

  ```bash
  <crew-skill-dir>/scripts/run-finish.sh "$run_id"
  ```

  It removes `.crew/.current` only when it still names `run_id`. A receipt makes it query the
  recorded `worker_name`: a live result refuses removal, exact `agent_not_found` proves the
  worker absent, and every other query failure stops safely. A run with no receipt proceeds.
- Without the finishing helper, compare `.crew/.current` to `run_id`, then apply the same live
  worker guard before removing only the pointer:

  ```bash
  IFS= read -r current_run < .crew/.current
  test "$current_run" = "$run_id" || exit 1
  test -d ".crew/$run_id" || exit 1
  receipt=".crew/$run_id/worker-pane.json"
  if test -e "$receipt"; then
    worker_name=$(python3 -c '
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
name = data.get("worker_name")
if not isinstance(name, str) or not name:
    raise SystemExit("invalid worker_name")
print(name)
' "$receipt") || exit 1
    if worker_result=$(herdr agent get "$worker_name" 2>&1); then
      printf 'worker_name=%s\noutcome=refused:worker-live\n' "$worker_name" >&2
      exit 1
    fi
    worker_error=$(python3 -c '
import json, sys
print(json.loads(sys.argv[1])["error"]["code"])
' "$worker_result") || exit 1
    test "$worker_error" = agent_not_found || exit 1
  fi
  IFS= read -r current_run < .crew/.current
  test "$current_run" = "$run_id" || exit 1
  rm .crew/.current
  ```

- Keep the lead pane open. Never close a pane that lacks this run's ownership receipt.
- Leave the run directory in place; it is the audit trail. Tell the user its path.
- Report: rounds used, final verdict, files changed, dismissed findings, and anything escalated
  but never answered.
- Never run `herdr server stop`. Never close panes, tabs, or workspaces you did not create.
