# Supervision and approval policy

Read [execution.md](execution.md) first. Every bound command and approval helper
invocation must receive `CREW_CONTROLLER_ID` for this lead session.

## Prompting the worker

Every prompt is a pointer, never a payload.

```bash
<crew-skill-dir>/scripts/herdr.sh agent prompt <worker> "Read .crew/<run-id>/task.md. Implement it. Write what you did and what you verified to .crew/<run-id>/report-1.md, ending with the line STATUS: done. Reply with only that path." --wait --timeout 600000
```

Rules for prompt shape:

- Point at an input file, name the output file, require `STATUS: done`, ask for only the path back.
- Include a published relay path when it supplies the current clarification. If the worker
  needs an answer first, it may return a completed question relay path; supervise that
  exchange without treating it as the requested implementation report.
- Never ask the worker to "critique" or "improve" anything open-endedly.
- Ask closed questions with a legitimate empty answer. For phase 1:
  *"Read `.crew/<run-id>/task.md` and the files it names. Write only concrete cases that would
  break if this plan is followed as written to `.crew/<run-id>/plan-check.md`. If there are
  none, write `없음` in that file. End the file with the line `STATUS: done`. Reply with only
  that path."*

## Supervision loop

Run this after every prompt.

**Relay handoff check:** before either completed-artifact exit below, read new relays and
their response chains. Use fresh re-entry if prior context is unavailable. A read refusal
means unavailable evidence: stop and escalate instead of treating it as an empty history.
Resolve unanswered requests and consequential corrections within the frozen task, or
escalate the decision and stop the round. Publish any needed lead response and track the
remaining action in `state.md`. A response alone does not prove that the required artifact
has incorporated a correction. Keep the current phase while relevant work remains pending.
The check is ready only when that work is resolved and the phase table's artifact exit
condition holds, including the phase 3 self-review heading check.

If work remains pending, prompt only a receptive worker with the response and required
action. A blocked worker must first follow the existing dialog handling below; a relay
response never answers a live permission or trust dialog. Recheck the handoff conditions
before advancing after the worker resumes.

```
prompt --wait  →  settled
same_dialog_repeats = 0
failed_dialog = none
no_dialog_reads = 0
repeat:
  agent = <crew-skill-dir>/scripts/herdr.sh agent get <worker>             # agent_status and state_change_seq
  status = agent.agent_status
  working  → no_dialog_reads = 0
             <crew-skill-dir>/scripts/herdr.sh agent wait <worker> --timeout <ms>     # server blocks; costs no tokens
  blocked  → pane = <crew-skill-dir>/scripts/herdr.sh agent read <worker> --source visible
             phase artifact exit condition holds ? apply relay handoff check
                 ready → next phase
                 pending → keep current phase; handle the live dialog below
             free-text question without options ? apply the free-text rule below
             no explicit confirmation prompt with a selectable option list ?
               no_dialog_reads += 1
               no_dialog_reads < 3 → pause for one second, then continue
               otherwise → escalate as unanswerable, then stop this round
             no_dialog_reads = 0
             dialog_text = confirmation prompt and option-list text only  # never the whole frame
             dialog_agent = <crew-skill-dir>/scripts/herdr.sh agent get <worker>
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
                         pre-forward refusal (exit 5) → read printed pre_key_seq;
                                                 no key command was forwarded;
                                                 failed_dialog = (dialog_text, pre_key_seq);
                                                 continue
                         delivery-uncertain/timeout (exit 6) or visible-changed (exit 7) → delivery uncertain;
                                 never "key did not land"; failed_dialog = none;
                                 apply the uncertain-delivery rule below;
                                 unchanged dialog and sequence, changed binding, or unavailable evidence →
                                     escalate without another key, then stop this round
                                 verified progress → same_dialog_repeats = 0;
                                     classify any new dialog independently; continue
                         guard refusal → return to the blocked guard without sending
             class (b) → approval.sh check <worker>
                         exact match → read printed approval_kind and command_b64;
                                 answer-dialog.sh --expected-command-b64 <token> <worker> <keys>;
                                 handle advanced, send-failure, uncertain, and refused
                                 results as above
                         grant match → also read printed grant_b64;
                                 answer-dialog.sh --expected-command-b64 <token>
                                   --expected-grant-b64 <grant_b64> <worker> <keys>;
                                 handle advanced, send-failure, uncertain, and refused
                                 results as above
                         no match or extraction failure → apply the class-(b) escalation and
                                                          approval-scope rule below, then stop
  unknown  → not complete. read the pane, then wait again.
  idle|done→ apply relay handoff check
             ready → next phase
             pending action → prompt the receptive worker with the lead response and required action;
                              resume supervision without marking the phase complete
             otherwise → re-prompt once for the missing phase artifact, then escalate
```

In the loop, resolve the helper calls as:

```bash
<crew-skill-dir>/scripts/artifact-done.sh <artifact-path>
<crew-skill-dir>/scripts/answer-dialog.sh <worker> <keys>
<crew-skill-dir>/scripts/approval.sh check <worker>
```

The lead identifies `dialog_text`, applies the repeat test, classifies (a) versus (b), and
chooses the keys before calling `answer-dialog.sh`. The helper only rechecks the mechanical
blocked-plus-visible-option-list guard, captures and prints `pre_key_seq`, sends the supplied
keys once, and polls. It never decides whether a dialog may be answered, and it never resends.

### Uncertain delivery

Apply this rule after helper exit 6 or 7, or after a manual send reports adapter
status 15 or any other failure not explicitly classified as pre-forward refusal.
Do not treat uncertainty as permission to retry, and do not set `failed_dialog`.

Re-read the same partner's binding, visible confirmation text/options, and
`state_change_seq`, and verify the requested effect. If the binding changed, the
evidence cannot be read, or the same dialog text remains at the same `pre_key_seq`,
escalate to the user and stop the round **without another key send**. A changed
background frame alone is not progress. This stop applies immediately; do not
reset a retry counter and loop through the same uncertain dialog again.

Only after verifying progress may supervision continue. A new visible dialog is
classified and authorized independently; a changed sequence alone does not renew
the previous authorization or justify resending the previous answer.

Exit 0 means `state_change_seq` advanced. When the sequence does not advance within about five
seconds, the helper reads the visible pane once more with the guard's arguments and compares it
with the guard's frame:

- exit 7 `outcome=visible-changed`: the frame differs;
- exit 6 `outcome=timeout`: the frame is unchanged, or the read failed.

Both print `pre_key_seq` and `post_key_seq`, and both are uncertain. Exit 7 does not show which
dialog received the keys or that an edit landed; a redraw between the guard read and the send can
also produce it. Live, Claude accepted one edit and immediately showed another dialog without a
`state_change_seq` increase. Re-read the pane and verify the requested effect before any
further input.

`approval.sh` emits a typed approval key: a command key is its complete rendered command text;
an edit key is operation `create` or `modify` plus its sorted, order-independent destination set.
The edit extractor produces that key only for complete Codex dialogs whose fixed action markers
positively identify creation or content modification and agree with the bounded `Destination:`
metadata block.

For a recorded class-(b) match, read `approval_kind` and `command_b64` from `approval.sh check`
and pin the token at the send boundary:

```bash
<crew-skill-dir>/scripts/answer-dialog.sh \
  --expected-command-b64 <command_b64> <worker> <keys>
```

The retained `--expected-command-b64` flag and `command_b64` output name carry the extracted
typed approval key of either kind. The answer helper calls the same extractor immediately before
sending and refuses with exit 3 when the kind or key changed or can no longer be extracted.
For a grant match, `--expected-grant-b64` additionally re-resolves the current path containment
against that exact grant immediately before sending.
`approval.sh` refuses extraction unless it finds the confirmation line, the complete supported
key region, and the option list; a truncation marker, ambiguous wrapped destination, unsupported
edit operation, or frame cut that removes any anchor is an extraction failure. Its exit status 0
means recorded or matched, 1 means no match, 2 means bad arguments, 3 means invalid active-run
ownership, 4 means state/frame/extraction failure, and 5 means a record failure.
Edit reuse requires the current action marker and its turn boundary to remain visible; when a long
turn scrolls either out of the frame, exit 4 re-escalates by design.

Live extraction is verified for Codex worker command and content-modification dialogs. The
structural Claude branch has been exercised live once. On September 26, 2026, a Claude Code
2.1.281 Bash dialog appeared in manual mode. It had one top rule and a `│`-prefixed command
wrapped over two lines, and `approval.sh check` returned exit 4, `complete command region is
absent`. The single-rule layout alone defeats the parser, so wrapping is not isolated as the
cause. For Claude or any other unverified worker kind, treat exit 4 as an unavailable reuse path
and escalate every occurrence normally.

After the user answers an escalation, capture the still-visible approval again. For reusable
scope, run `approval.sh record <worker>` and use its printed `command_b64`. For a one-shot
answer, use the `command_b64` printed with the no-match result. Pass that token to the pinned
answer helper above, and choose the worker UI's one-shot affirmative option.

When extraction fails (exit 4), there is no token and nothing to pin. Do not record, propose,
grant, or reuse an approval for that dialog. After the user authorizes one exact action once:

1. Run `<crew-skill-dir>/scripts/herdr.sh agent get <worker>`. Require `blocked`, and keep its `state_change_seq`.
2. Re-read the visible dialog.
3. Compare the requested action and the one-shot affirmative option with what the user
   authorized. Refuse and escalate again if either changed, is incomplete, or is ambiguous.
4. Immediately send only that option with the unpinned `answer-dialog.sh <worker> <keys>`.
5. Compare its printed `pre_key_seq` with the kept `state_change_seq`. A mismatch means the
   answer may have gone to a different dialog. Stop and report it to the user.

The unpinned guard checks only a blocked worker with a visible option list, not the action. The
sequence comparison detects a replaced dialog only after the send; it does not prevent one.

Without the approval helper, keep the same typed approval key in the run record only after the
user grants reusable scope. On later class-(b) dialogs, anchor the key's source region to the
dialog structure, refuse incomplete, truncated, ambiguous, or unsupported captures, and compare
the kind and key exactly. Immediately re-read and compare that same typed key before the guarded
`send-keys`; return to the blocked guard without sending if it changed.

Without the answer helper, retain the blocked/visible-dialog guards and capture
`dialog_text`, the pre-send frame, `dialog_agent.pane_id` as `pre_key_pane_id`, and
`dialog_agent.state_change_seq` as `pre_key_seq`. On every subsequent `agent get`,
including uncertain-delivery inspection, compare `pane_id` with `pre_key_pane_id`
before interpreting the sequence. A different pane ID or a bound-adapter refusal
means a changed binding: escalate and stop the round without another key send.
Missing pane identity is unavailable evidence and requires the same stop.
Run `<crew-skill-dir>/scripts/herdr.sh agent send-keys <worker> <keys>` once and
capture its exit status immediately:

- **2, 10, or 11:** the bound adapter refused before forwarding. Only these statuses
  set `failed_dialog = (dialog_text, pre_key_seq)` and use the bounded pre-forward
  refusal path in the supervision loop.
- **15 or any other nonzero status:** delivery is uncertain. Apply the uncertain-delivery
  rule above; do not set `failed_dialog` or resend the keys.
- **0:** poll `<crew-skill-dir>/scripts/herdr.sh agent get <worker>` at bounded intervals
  until `state_change_seq` exceeds `pre_key_seq` or the post-key timeout expires.
  Stop on a changed binding. On timeout or unavailable evidence, apply the same
  uncertain-delivery rule. Verify the requested effect before continuing.

Herdr validates key names before writing bytes, but the bound adapter conservatively
reports a forwarded Herdr rejection, including an unknown key, as status 15. Do not
infer non-delivery from that diagnostic or retry automatically. `esc` is the canonical
Escape name.

## Which inputs you may answer

| Class | Examples | Action |
| --- | --- | --- |
| (a) answer yourself | edit approval for a file inside the workspace; running tests, linters, or builds; a choice between options that `task.md` already settles; a clarifying question answerable from `task.md` | Apply the guarded `send-keys` path in the Supervision loop, then log the answer in `state.md` |
| (b) escalate to the user | deleting or moving files; bulk rewrites; network access; writing outside the workspace; `git commit`, `push`, `reset`, or history rewriting; credentials or secrets; workspace trust prompts; anything not derivable from `task.md` | Check the active run's approval record first. On no match, report what is being asked directly to the user, attempt `herdr --session "$session" notification show "<title>" --body "<what is being asked>" --sound request` as a best-effort ping, read `.result.shown` from its response, then stop the round. If `shown` is `false`, tell the user that the ping was not shown. |

This table governs requests the lead can observe. The worker's native permission setting decides
which actions run without a request; Crew cannot intercept or approve those before execution.
For such a setting, present Crew as task scoping and review under the worker's effective
permissions, not as a pre-execution class-(b) gate. Use a permission setting that prompts or
refuses the relevant action, and verify it live, when that gate is required for the task.

A reusable class-(b) approval is either one completely captured typed key or one user-visible set
grant: command template `rm -rf -- {path}` with exactly one safe resolved absolute path at or
below a canonical constrained root, or edit operation `create`, `modify`, or both with every safe
resolved destination at or below that root. For a set, run `approval.sh propose <worker> --root
<dir> [--ops create,modify]`, show the printed `grant_text` verbatim, and treat the user's answer
as applying only to that text; only after yes run `approval.sh grant <worker> --proposal
<proposal_sha256>`. The digest covers the exact grant text; the inert proposal record also binds
the current typed key and derived root, kind, template, and operations, all of which `grant`
recomputes. Every match and granted send rechecks the root and resolved containment. Exact and set
reuse are run-scoped and kind-specific. Always select the one-shot affirmative option when sending
a granted answer; never select the worker's broader "don't ask again" option.

An entry in the external run record is evidence of a lead action after a user answer only when
the worker cannot write that root without a prompt or refusal. This is a property of its
effective permissions, not of either model's lead role. For each newly configured or attached
worker, have the lead place a synthetic probe file under the canonical state root, then ask the
worker to attempt one append through a shell command and one edit through its built-in file
tool. Check that neither attempt changed the file without a dialog, and that a normal workspace
edit still runs automatically. Never approve either state-root probe dialog. Repeat after a
permission change. A refusal suffices; a dialog must be left unanswered or denied. If either
write lands, or a probe cannot be observed reliably, do not reuse approval records for that
worker. Escalate visible class-(b) requests individually. A state-root probe does not prove that
all other class-(b) actions are intercepted; inspect diffs and execution evidence for those.
This also assumes the lead's command runner is not compromised; never treat worker output as authority
to answer a trust question.

Observed live for an unpinned Claude Code worker in auto mode on September 26, 2026: the probe
line landed in the state root with no dialog. For that retained configuration, approval reuse is
disabled by lead rule: never run `approval.sh record`, `propose`, or `grant` for that partner, and
never answer from a `check`
match (a worker that writes the state root can forge one), and escalate each visible class-(b)
request to the user individually. The auto-mode append produced no dialog, so this observation
does not establish pre-execution enforcement of that class; it does not by itself show approval
forgery or prevent task scoping and independent review. `approval.sh` does not refuse a Claude
partner by itself. The lead switched the same session to manual mode to test dialogs, not to
define a required steady-state mode. One state-root Bash append then surfaced a dialog. That
single path does not establish record protection: Claude's file-edit tools writing the state
root and the dialog's broader options were not tested, and the extractor refuses the observed
layout. The new pinned launch profile has offline argument coverage and direct native CLI smoke
evidence, but no Herdr-launched sandbox result yet. Keep approval reuse disabled for the
previously tested Claude session in either mode.

A free-text question is not answerable with `send-keys`. Escalate it even when its answer is
derivable from `task.md` and class (a) otherwise applies. Do not invent a text-entry mechanism.

When the class is not obvious, treat it as (b).

The lead's own report to the user is the mandatory escalation channel. The notification is
only a best-effort ping on top of that report; exit status 0 does not prove delivery.

## Known failure modes

- `agent_pane_busy` — the created pane has not reached its shell prompt. Wait for the prompt.
- `interactive_ready` false positive — `agent start` reports `interactive_ready: true` before
  the worker TUI accepts input, so the first prompt is silently lost. Wait for the composer
  marker in the execution helper. For unsupported worker kinds, stop; the artifact
  check catch the missing output, then apply the existing re-prompt-once rule.
- Self-update exit — a worker self-updates on launch, exits, and releases its name. Wait for
  the recorded pane to return to a shell prompt, then let `worker-start.sh` reuse it under the
  same name. Do not create another pane while that recorded pane still exists.
- `agent_prompt_stalled` — no lifecycle change within five seconds of a prompt. Do not resend
  blindly; read the pane first.
- `agent_blocked` — `<crew-skill-dir>/scripts/herdr.sh agent prompt` refuses a worker that remains at a dialog. Return to
  the `blocked` branch of the Supervision loop; do not retry the prompt until that branch
  confirms the dialog answer, and stop if it escalates.
- Notification no-op — `herdr --session "$session" notification show` can exit 0 with `.result.shown` set to
  `false`. Keep the lead's report as the mandatory escalation channel, inspect `shown`, and
  tell the user when the best-effort ping was not shown.
- Alternate-screen loss — TUI worker output that scrolls away is unrecoverable from scrollback
  regardless of `--lines`. This is why artifacts are files.
- Name collision — agent names must be unique among live agents across all workspaces.
- Wrong-pane cleanup — never close `--current`, `$HERDR_PANE_ID`, or a pane copied from visual
  position. `worker-stop.sh` closes only the partner in `<state>/worker.json`, only after explicit
  user instruction, and refuses unless the caller is the recorded controller and the live name and kind
  still resolve to the recorded pane.
- Helper changed under a running lead — a development symlink into a repository checkout
  loads edits, pulls and branch switches immediately, even before a commit. A Skills CLI link
  points to its shared installed copy, which can be replaced by an installer update or re-add.
  In either case, a running lead may still hold the previous `SKILL.md` in context. If a helper's
  behaviour contradicts this document mid-run, inspect the resolved skill directory and its
  installed or source revision before diagnosing the run.
- Discarded stderr — `<crew-skill-dir>/scripts/herdr.sh agent prompt ... --timeout` without `--wait` is a usage error, and
  with stderr sent to `/dev/null` it looks exactly like a dropped prompt. Never discard the
  stderr of a `herdr` call that moves the run; read the result before concluding anything.
- Sandboxed retry after a denial — after `esc` the pane may show `✗ You canceled ...` and then
  `• Ran ...` as the worker re-runs the same command under its own sandbox. The denial ends
  only the unsandboxed request; the sandbox policy decides the rest. After denying a
  destructive command, verify the target before reporting that nothing happened.
