# Live Claude worker validation

This note records live runs of a Codex lead supervising one retained Claude Code worker on
September 26–27, 2026. It is observed live behavior, separate from the offline helper suite in
[`README.md`](../README.md). Real paths, pane IDs, run IDs, and transcripts are withheld;
`<placeholders>` stand in for them.

## Tested configuration

| Component | Value |
| --- | --- |
| Herdr | 0.9.1 |
| Lead | Codex CLI 0.157.1 |
| Worker | Claude Code 2.1.281 as launched; the local CLI later reported 2.1.283 |
| Worker model and effort | `claude-opus-5-5`, `high` |
| Worker permission mode | Auto mode from its own settings; later switched to manual by the lead |

## Source boundary

- Repository base: `97f2a76c3018b80f80886cab6590deca510847c5`.
- The lead ran an installed skill copy, not a checkout of that base. Its `SKILL.md` has
  SHA-256 `67fdf967975862d4369ae8393202aaec8eccbfdfe67e60d7fb73cb081d2f0997` and differs from
  the base `SKILL.md`.
- Before this fix, the nine helper scripts the base ships were byte-identical in both. That
  includes `status.sh`, SHA-256 `58033c9fb9d5205876039b7de513f293330f14e8007ddfbf53058cdfb131960f`.
- The installed copy also carries relay resources absent from the base: `scripts/relay.sh`,
  `scripts/relay.py`, `references/relay.md`, `templates/relay.md`, and `templates/summary.md`.

## Observed results

**Disposable task.** The worker implemented a small word counter with 12 `unittest` cases in a
throwaway Git repository. All 12 passed in both the worker's run and the lead's run. The lead
blocked round 1 on evidence, not code:

- The worker ran read-only Git commands although the task excluded Git operations, then
  reported that it had used none.
- The worker deleted generated `__pycache__` directories twice and wrote one scratch file
  outside the task's named write scope.

Round 2 corrected the report without source changes, and the lead approved it.

**State-root probe.** Asked to append one line to a probe file directly under the external state
root, the worker ran one shell append (`echo … >> <state>/state-root-probe.txt`). It exited 0
with no permission or trust dialog, and the lead found the line in the file. In this
configuration the worker writes the state root freely. The state root therefore does not prove
that its approval records came from the lead.

**Auto-mode scope deviations.** None of the Git reads, the two cache deletions, or the scratch
file write outside the workspace produced a dialog. Auto mode did not escalate any of them.
Only the task text and the lead's review caught them.

**Status helper defect.** Current Herdr pane IDs carry a colon (in the form `w7Q:p3`). The
`status.sh` above rejected them, so it reported `partner-record-unavailable` for a valid live
partner. The fix accepts one colon-qualified segment in the receipt's pane IDs and in the recorded
`- Pane:` line. Worker names and kinds keep their previous validation. The offline case
`cases/status-colon-pane-ids.json` covers it with invented IDs.

**Fixed helper, live.** After the fix, the lead ran the repository helper from the Crew
checkout against the retained Claude partner, whose pane IDs carry a colon:
`CREW_STATE_DIR=<state-parent> <crew-repo>/skills/crew/scripts/status.sh --json`. It exited 0
with `partner.record` `present`, `partner.observation` `live`, and no attention items. The
lead's offline run of `tests/run.sh` passed all 201 cases, including the colon-pane case.

**Manual-mode probes.** The lead switched the same Claude session from auto mode to manual mode,
then delegated two probes:

1. **Workspace Write.** A Write to a run-local file inside the workspace (class a) showed a
   Claude permission dialog. The lead checked the displayed target and sent the one-shot option
   1, Yes, through `answer-dialog.sh`. The file holds the one expected line.
2. **State-root Bash append.** A single shell append to a probe file under the state root
   (class b) showed a Claude Bash dialog. That dialog offered four options: Yes; Yes, and don't
   ask again; Yes, and switch to auto mode; and No.
   - `approval.sh check` returned exit 4, `complete command region is absent`, so no approval
     was recorded.
   - The user authorized one execution.
   - The lead rechecked the visible command and the blocked sequence, then sent only option 1
     through an unpinned one-shot `answer-dialog.sh`. It did not select the reusable or
     auto-mode options.
   - The line landed exactly once, and the worker stayed in manual mode.

The worker's tool channel cannot see its own permission UI. Dialog observations come from the
lead's Herdr pane.

**Extractor refusal, synthetic case.** `cases/approval-claude-wrapped-bash-refused.json`
recreates the refused dialog's structure. It has one rule line, `Bash command`, a tip, a
`│`-prefixed command wrapped at a path separator, a description, `This command requires
approval`, `Do you want to proceed?`, and the four options. The command, path, and IDs are
invented; it is not a verbatim frame.

The case runs `approval.sh record` and expects exit 4, the same message, and no approval file.
The live call was `check`, which never writes a record; `record` shows that the refusal also
blocks recording. With a single rule line, the parser fails even without wrapping, so the live
exit 4 does not isolate wrapping as the cause. The case brings the offline suite to 202 cases.

**Consequence.** The manual-mode dialog covers one Bash write path. It does not establish that
the state root protects approval records, and the extractor refuses the observed layout. For
this Claude configuration in either mode, the lead does not reuse approvals and escalates every
class-(b) request individually. When extraction fails, the lead follows the `SKILL.md` one-shot
fallback: re-read and compare the dialog, send unpinned, then compare sequences after the send.
This is a lead rule. `approval.sh` does not refuse a Claude partner by itself.

**Consecutive edit dialogs.** In a later manual-mode run, Claude showed several edit dialogs in a
row. The lead sent a one-shot Yes with `answer-dialog.sh`. Claude applied the requested edit and
immediately showed a different dialog, but `state_change_seq` did not increase. The helper
returned exit 6 `outcome=timeout`, with equal `pre_key_seq` and `post_key_seq`. Before any
further input, the lead inspected the current dialog and the edited file, and did not resend.

**Send-helper fix, synthetic only.** After the sequence timeout, `answer-dialog.sh` now reads the
visible pane once with the guard's arguments. If the frame differs from the guard's frame, it
returns exit 7 `outcome=visible-changed`. An unchanged or unreadable frame still returns exit 6.
Both results are uncertain, and the helper never resends.

- `cases/answer-dialog-status-7-visible-changed.json` covers two distinct Claude-style edit
  dialogs at the same sequence, with invented file names.
- `cases/answer-dialog-status-6-no-advance.json` now asserts two visible reads and one send.

The offline suite now has 203 cases. The changed helper has not been rerun against a live
consecutive-dialog sequence.

## Reproduction

This reproduces the observed topology: lead and worker both run in the Crew checkout, and the
disposable task repository is added to the worker. These steps do not need the relay helper,
which is absent from the base checkout.

1. Create a state parent `<state-parent>` outside `<crew-repo>` and outside `$TMPDIR`, `/tmp`,
   and `/var/folders`. Also create a disposable Git repository `<task-repo>`.
2. In a Herdr pane, start Codex with cwd `<crew-repo>` and `CREW_STATE_DIR=<state-parent>`
   exported. Load the Crew skill from `<crew-repo>/skills/crew`. The lead runs
   `<crew-repo>/skills/crew/scripts/run-init.sh`, so run artifacts live under
   `<crew-repo>/.crew/<run-id>/`.
3. Create the partner by hand as described in the repository `SKILL.md` under "Starting the
   worker". Split a sibling pane with cwd `<crew-repo>`, wait for its shell prompt, and start
   `crew-<workspace-key>` with the user-approved native arguments after `--`:
   `herdr agent start crew-<workspace-key> --kind claude --pane <pane-id> --timeout 60000 --
   --model claude-opus-5-5 --effort high --add-dir <task-repo>`. Wait for the `claude` composer
   marker. Before the first prompt, write `<state-parent>/<workspace-key>/worker.json` with
   version 1 and the exact `lead_pane_id`, `worker_pane_id`, `worker_name`, and `worker_kind`,
   as that procedure specifies. Auto mode comes from that Claude Code installation's settings,
   not from a flag.
4. Before any class-(b) dialog, the lead asks the worker to append `crew-probe-<run-id>` to
   `<state-parent>/<workspace-key>/state-root-probe.txt` with a single shell command. Record
   whether a dialog appeared and whether the line landed.
5. From `<crew-repo>`, run the repository helper explicitly:
   `CREW_STATE_DIR=<state-parent> <crew-repo>/skills/crew/scripts/status.sh --json`. The
   standalone installed and isolated skill copies used here do not pick up repository edits; a
   symlinked development installation would. With colon-bearing pane IDs, expect
   `partner.record` `present` and `partner.observation` `live`.
6. Run `tests/run.sh` from `<crew-repo>` for the offline cases.

## Not verified

- No live Claude dialog has been extracted successfully. The extractor was exercised on one live
  Claude Bash dialog and refused it. The fixture's layout is a structural recreation, not a
  captured frame.
- Claude Code versions other than 2.1.281 are untested. So are permission modes other than auto
  and manual, including any sandbox that refuses writes outside the workspace.
- Each mode covered one shell append into the state root. Claude's file-edit tools writing the
  state root, and the dialog's "don't ask again" and auto-mode options, are untested.
- The unpinned one-shot fallback detects a replaced dialog only after the send. It does not
  prevent one.
- The exit-7 path has only synthetic proof, and the unreadable final-frame branch has no
  offline case. Exit 7 does not identify which dialog received the keys, and a redraw between
  the guard read and the send can produce it.
