# Context relays

## Session boundary and ownership

One Crew run is one collaboration session. Its context lives under
`.crew/<run-id>/`, alongside the existing task, state, report, and review files.
Resuming that run with a fresh lead or worker keeps the same directory. The
retained partner can outlive several runs; its process lifetime does not merge
their histories. A new run starts its own history and links any needed earlier
evidence explicitly.

| Path within the run | Writer | Meaning |
| --- | --- | --- |
| `relay/000001.md`, etc. | The contribution's author | Ordered, completed messages |
| `summaries/through-000020.md`, etc. | Lead | Optional summary of the complete relay prefix through that ID |
| `state.md` | Lead | Existing current phase and round; link the relay that explains the current next action |
| Draft files outside those two subdirectories | Their author | Unpublished content; never a delivered message |

The lead writes its own requests, answers, and user-disposition records; the
worker writes its own questions, results, and corrections. The lead owns final
summary publication. These are workflow responsibilities: shared files and
author labels are not authenticated authority or a sandbox boundary. A worker
may propose a summary in its own draft or relay, but does not publish it as the
lead. Either participant or the user can request compaction.

Do not copy approval grants into this protocol as executable authority. Existing
external approval records, pane ownership, frozen scope, review rules, and run
lifecycle remain authoritative. Record an actual user decision with its source;
an agent's proposal or requested next action does not grant permission.

## Publish a relay

Run the helper from the same workspace directory used for run initialization.
The run must already contain task.md and state.md. Publication requires it to
match the validated external active-run pointer; reading a finished run does not.
The lead must put the canonical state parent reported by state-root.sh in task.md's
Context section. Use that exact value as CREW_STATE_DIR on every publication command,
even when the lead uses the default location; a new or retained worker need not share
the lead's environment. Publication reads the active-run pointer but never writes it.
If the pointer is missing, check both the active run and the supplied setting with
the lead. If access is refused, report it; do not grant worker write access or move
authority state into the workspace to make publication succeed.

1. Write a draft inside the run directory using the
   [relay template](../templates/relay.md).
2. Fill all three sections: Message, Evidence, and Next action. Use an explicit
   reason when there is no evidence or no next action.
3. Publish the complete draft, then notify the recipient with the returned path.

~~~sh
CREW_STATE_DIR='<state-parent-from-task-context>' <crew-skill-dir>/scripts/relay.sh append <run-id> \
  --author worker --to lead --kind question \
  --reply-to task.md --file draft-worker.md
~~~

The command prints only the new workspace-relative path, for example
`.crew/<run-id>/relay/000001.md`. The generated header records the session,
author role, recipient role, kind, response target, and UTC creation time.
Kinds are request, question, response, result, correction, and note.

File arguments are relative to this run. A response target is task.md, an
existing report-N.md or review-N.md, or an earlier relay/NNNNNN.md in the same
run. These targets must already exist. The printed workspace-relative path is
for opening the file or directing the recipient to it, not a file argument to
the helper. For example, reply to the printed `.crew/<run-id>/relay/000001.md`
with `--reply-to relay/000001.md`; publish `.crew/<run-id>/draft-worker.md` with
`--file draft-worker.md`. The helper refuses the `.crew/<run-id>/` prefix in
file arguments rather than silently interpreting it as another path.
Put other source references, including explicit cross-session references,
in Evidence. Link canonical artifacts instead of copying their contents.
Where exact identity matters, record the source revision or precise evidence
location. Current task and review artifacts can change; a historical link is
not a promise that their current contents equal what the author originally read.

Each author publishes after completing the draft. The helper accepts an optional
standalone final STATUS: done line in the draft; the same text within a sentence
remains message content. It adds the exact STATUS: done terminator, writes a
temporary file, and links the complete record
into its numbered name without overwriting an existing file. A sequence collision
fails; inspect the newly published record before deciding whether to republish.
Do not blindly resend after an uncertain outcome. Drafts stay in place.

Ordinary Crew interaction is sequential. This helper adds no queue, dispatcher,
parallel assignment protocol, or automatic retry. The marker proves only that
the relay file was published completely. A result relay never substitutes for
the report, self-review, or lead verdict required by the phase table.

## Delivery and continuation

Herdr carries the prompt directing an agent to the published file; the file
contains the context. Follow the existing live-agent and dialog checks before
prompting. Creating a file or printing a read plan does not prove delivery or
that its recipient understood it.

For a worker clarification, publish a question addressed to the lead, identify
the work waiting for the answer, and return the relay path. The lead reads it,
answers within the frozen task or escalates the actual decision to the user,
then publishes its response. Once the worker is receptive, send a pointer:

~~~sh
herdr agent prompt <worker> "Read .crew/<run-id>/relay/000002.md, which answers .crew/<run-id>/relay/000001.md. Continue the existing task within its scope. Write the required report and reply with its path." --wait --timeout 600000
~~~

A published clarification is distinct from a live free-text permission/trust
dialog. Existing escalation rules for those dialogs still apply. Never convert
an unknown or unanswerable live dialog into an assumed relay response.

The lead follows worker relays at every handoff before advancing the phase,
including when the expected report is already present and the worker is blocked.
Both completed-artifact exits use the skill's relay handoff check. A later correction
can qualify that report; keep the phase open until relevant pending work is resolved.
Do not prompt a blocked worker with the relay response: follow the existing dialog
handling first and prompt only when it is receptive.
Read each new addressed request and its response chain once,
record the response target, and preserve the round cap and completion checks.
A pending clarification explains an idle worker with no report; it does not
authorize further work beyond the task.

### Fresh context

~~~sh
<crew-skill-dir>/scripts/relay.sh read-plan <run-id>
<crew-skill-dir>/scripts/relay.sh read-plan <run-id> --json
~~~

This prints paths and byte counts, not message bodies. Read the listed files:
task.md, state.md, dismissed.md when present, the latest applicable summary, and
all relays after its coverage. Without a summary, read all original relays.
Follow the report, review, and source references needed for the current phase.
Independent review still requires the original user request and actual diff.

The current summary pointer is derived from the greatest published through-ID.
There is no second mutable pointer to synchronize with publication. state.md
may link that summary and the current next-action relay for human navigation;
read-plan computes the current selection from the records themselves.

### Ongoing context

~~~sh
<crew-skill-dir>/scripts/relay.sh read-plan <run-id> --after 12
~~~

Only use --after when this participant still understands the context through
that relay in this specific run. It returns original relays after the cursor,
even if a later summary exists, plus the canonical task/status/dismissal files.
The printed latest_relay is a snapshot boundary, not an automatic read receipt.
Advance a remembered cursor only after reading and understanding those records.

No reader cursor is persisted across agent instances. When the cursor or prior
context is unavailable, omit --after for fresh re-entry. Never reuse a cursor
from another run or recover it from the partner's process name.

## On-demand compaction

Compaction is manual by default. No summary is generated after each message,
round, handoff, or agent replacement. The helper never invokes a model.

An optional explicit reading budget provides an advisory signal:

~~~sh
<crew-skill-dir>/scripts/relay.sh read-plan <run-id> --budget-bytes <chosen-budget> --json
~~~

The budget uses actual UTF-8 bytes of the latest summary plus uncovered relays.
Covered originals are excluded. During incremental inspection the budget still
measures that fresh re-entry packet, not just this participant's unread suffix.
This is a portable size measure, not a token estimate: there is no universal
bytes-to-tokens ratio. No default threshold, model-capacity fraction, compression
ratio, or target summary length is imposed.

Select a budget from observed reading burden and the effective client context,
reserving room for canonical inputs, code, tool output, and continued work.
If that budget is unknown, leave the option unset and use an explicit request.
An exceeded budget suggests compaction at a coherent work boundary; it does not
block work, grant permission, or run a summarizer. Repeated inspections do not
create repeated summaries. A summary that still exceeds the budget is a signal
to reassess the packet, not an instruction to keep summarizing without new work.

To compact:

1. Select a completed relay prefix and inspect its records. An older summary may
   orient the lead, but verify retained decisions, constraints, corrections,
   disagreements, and unfinished work against their original sources.
2. Write a draft using the [summary template](../templates/summary.md). Preserve
   verified facts, proposals, and open questions as distinct claims. Name source
   relay IDs in the relevant sections and keep canonical evidence references.
3. Check the summary for omissions and changed meaning, then publish it:

~~~sh
<crew-skill-dir>/scripts/relay.sh publish-summary <run-id> \
  --through 20 --file draft-summary.md
~~~

Every summary covers the complete prefix from 000001 through its recorded end,
including important unresolved items from earlier summaries. All original
relays and previous summaries remain intact. The helper records a SHA-256 of
the covered relay bytes; fresh re-entry rejects a summary if those sources
have subsequently changed. This checks source identity, not semantic accuracy.
Required sections check shape only; the lead must check faithfulness.

The next summary must cover additional relays. Correct a summary by first
publishing a correction relay, then a new summary through that correction.
Do not overwrite the previous summary or silently fall back to an older one.
If a summary is invalid, inspect all originals explicitly with
`read-plan <run-id> --after 0` without a budget option, and resolve the problem
without deleting history.

File compaction reduces future reading cost. It neither frees a running model's
internal context immediately nor configures the provider's own compaction.

## Inspection and limits

Exit 0 means the requested publication or read plan succeeded, not that the
run is complete. Exit 1 reports missing, malformed, incomplete, or unavailable
evidence or failed publication. Exit 2 means invalid CLI arguments.

Read plans are read-only and work without a live Herdr session or active pointer.
They reject symlinked record paths, gaps, invalid response references, and
malformed records rather than skipping unknown evidence. Hidden publication
drafts are ignored. Originals can be inspected manually even when the helper
refuses an invalid history; refusal never authorizes repair or cleanup.

For an unexpected file in relay/ or summaries/, preserve it and inspect its path,
contents, and provenance without changing it. A nonmatching filename alone does
not prove that it is a disposable draft or identify its author. Report the exact
entry and proposed recovery to the lead. Any move, removal, or other state repair
requires explicit user authorization through the existing class-(b) workflow.
Do not rename the file into a hidden entry to bypass validation. Place new drafts
outside the publication directories as specified above.

The helper validates records on disk to produce a plan; it does not load all
those records into the model's context. Budget counts exclude task.md, state.md,
and dismissed.md, whose byte counts are separately listed. In JSON,
compaction.continuation_bytes is null for an incremental read without a budget,
where no fresh-packet size was requested.

Existing status.sh remains a read-only phase/report/partner snapshot. Use
relay.sh read-plan for conversational continuation. A pending question can
explain why a report has not yet appeared; it does not make the phase complete.

Keep actual relay histories, summaries, drafts, and authority state local.
Only synthetic examples and fixtures belong in Git or public issue/PR evidence.
The [test walkthrough](https://github.com/weirdry/crew/blob/v0.1.2/tests/relay-walkthrough.md)
demonstrates the file protocol; it does not establish fresh-model comprehension, summary
faithfulness on real work, or live Herdr delivery.
